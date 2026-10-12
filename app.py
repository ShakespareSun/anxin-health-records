import io, os, json, secrets, hashlib, hmac, time, zipfile, base64, csv, re, tempfile, sqlite3
import mimetypes
mimetypes.init()
mimetypes.add_type('application/javascript','.js')
mimetypes.add_type('text/css','.css')
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from cryptography.fernet import Fernet, InvalidToken
from store import *
from clinical_analysis import build_analysis
import ai_service
import chatgpt_connection as chatgpt

init()
app=FastAPI(title='安心家庭病历',docs_url=None,redoc_url=None,openapi_url=None)
sessions={}; attempts={}

def password_hash(password,salt): return hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex()

@app.middleware('http')
async def protect(request:Request,call_next):
    path=request.url.path
    if path.startswith('/api/') and path not in ['/api/auth/status','/api/auth/setup','/api/auth/login']:
        expiry=sessions.get(request.cookies.get('health_session',''),0)
        if expiry<time.time():return JSONResponse({'detail':'请先登录'},401)
    if request.method not in ['GET','HEAD']:
        origin=request.headers.get('origin')
        if origin and origin.split('://')[-1]!=request.headers.get('host'):return JSONResponse({'detail':'来源不匹配'},403)
        if request.headers.get('x-health-client')!='1':return JSONResponse({'detail':'请求校验失败'},403)
    response=await call_next(request)
    response.headers['Cache-Control']='no-store'
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='no-referrer'
    response.headers['X-Frame-Options']='DENY'
    return response

@app.get('/api/auth/status')
def auth_status(request:Request):return {'setup':bool(setting('password_hash')),'logged_in':sessions.get(request.cookies.get('health_session',''),0)>time.time()}

@app.post('/api/auth/setup')
def setup(body:dict,request:Request):
    if request.client.host not in ['127.0.0.1','::1','testclient']:raise HTTPException(403,'首次设置须在本机完成')
    if len(body.get('password',''))<10:raise HTTPException(400,'密码至少 10 个字符')
    salt=secrets.token_hex(16)
    with connect() as c:
        c.execute('BEGIN IMMEDIATE')
        if c.execute("SELECT 1 FROM settings WHERE key='password_hash'").fetchone():raise HTTPException(409,'已设置密码')
        c.executemany('INSERT OR REPLACE INTO settings VALUES(?,?)',[('password_salt',salt),('password_hash',password_hash(body['password'],salt)),('patient_name',body.get('patient',''))])
    return {'ok':True}

@app.post('/api/auth/login')
def login(body:dict,request:Request):
    key=request.client.host; recent=[t for t in attempts.get(key,[]) if t>time.time()-300]
    if len(recent)>=10:raise HTTPException(429,'尝试次数过多，请五分钟后重试')
    attempts[key]=recent+[time.time()]
    salt=setting('password_salt')
    if not salt or not hmac.compare_digest(password_hash(body.get('password',''),salt),setting('password_hash')):raise HTTPException(401,'密码不正确')
    attempts[key]=[];token=secrets.token_urlsafe(40);sessions[token]=time.time()+43200
    response=JSONResponse({'ok':True});response.set_cookie('health_session',token,httponly=True,samesite='strict',secure=request.url.scheme=='https',max_age=43200);return response

@app.post('/api/auth/logout')
def logout(request:Request):sessions.pop(request.cookies.get('health_session',''),None);return {'ok':True}

@app.get('/api/data')
def data():
    with connect() as c:
        docs=[dict(r) for r in c.execute('SELECT * FROM documents ORDER BY name')]
        pages=[dict(r) for r in c.execute('SELECT id,document_id,number,status,error FROM pages ORDER BY document_id,number')]
        questions=[dict(r) for r in c.execute('SELECT * FROM questions')]
        findings=[{**dict(r),'source_ids':json.loads(r['source_ids'])} for r in c.execute('SELECT * FROM findings')]
    rs=reports()
    relevant_ids={r['id'] for r in rs if is_clinical(r)}
    findings=[{**f,'source_ids':[rid for rid in f['source_ids'] if rid in relevant_ids]} for f in findings if not f['source_ids'] or any(rid in relevant_ids for rid in f['source_ids'])]
    return dict(documents=docs,pages=pages,reports=rs,questions=questions,findings=findings,analysis=build_analysis(rs),ai_analysis=ai_service.saved_analysis(rs),worker_error=setting('worker_error'),patient=setting('patient_name'),updated=max([r['updated'] for r in rs] or ['']))

@app.get('/api/ai/status')
def ai_status():
    try:return chatgpt.status()
    except chatgpt.ConnectionError as e:raise HTTPException(503,str(e))

@app.post('/api/ai/login')
def ai_login(body:dict,request:Request):
    if request.client.host not in ['127.0.0.1','::1','testclient']:raise HTTPException(403,'请在电脑本机连接 ChatGPT 账户；连接完成后手机也能提问。')
    # A reverse proxy on loopback must not be mistaken for the local browser.
    if request.headers.get('x-forwarded-for') or request.headers.get('host','').split(':')[0] not in ['127.0.0.1','localhost','[','testserver']:raise HTTPException(403,'首次账户连接请使用电脑上的本机网址。')
    try:return chatgpt.begin_login(str(body.get('account_id','')))
    except chatgpt.ConnectionError as e:raise HTTPException(503,str(e))

@app.post('/api/ai/disconnect')
def ai_disconnect():return chatgpt.disconnect()

@app.get('/api/ai/models')
def ai_models():
    try:return {'models':chatgpt.models()}
    except chatgpt.ConnectionError as e:raise HTTPException(503,str(e))

@app.put('/api/ai/model')
def ai_model(body:dict):
    try:
        choices=chatgpt.models()
        if body.get('model') not in [m['id'] for m in choices]:raise HTTPException(400,'模型不在当前账户列表中')
        set_setting('ai_model',body['model']);return {'ok':True}
    except chatgpt.ConnectionError as e:raise HTTPException(503,str(e))

@app.get('/api/ai/context')
def ai_context():return ai_service.preview()

@app.get('/api/ai/messages')
def ai_messages():return {'messages':ai_service.message_list()}

@app.post('/api/ai/chat')
def ai_chat(body:dict):return ai_service.complete(body)

@app.post('/api/ai/analyze')
def ai_analyze(body:dict):return ai_service.complete(body,analysis=True)

@app.post('/api/upload')
async def upload(file:UploadFile=File(...)):
    content=await file.read(100*1024*1024+1)
    if len(content)>100*1024*1024:raise HTTPException(413,'每份 PDF 最大 100 MB')
    try:did,new=import_pdf(content,file.filename or '病历.pdf')
    except Exception as e:raise HTTPException(400,'无法读取 PDF：'+str(e))
    return {'id':did,'new':new}

@app.post('/api/pages/{pid}/retry')
def retry(pid:int):
    with connect() as c:c.execute("UPDATE pages SET status='queued',error=NULL WHERE id=? AND status!='processing'",(pid,))
    return {'ok':True}

@app.get('/api/pages/{pid}')
def page_info(pid:int):
    with connect() as c:r=c.execute('SELECT * FROM pages WHERE id=?',(pid,)).fetchone()
    if not r:raise HTTPException(404)
    return {**dict(r),'blocks':json.loads(r['blocks'])}

@app.get('/api/pages/{pid}/image')
def page_image(pid:int):
    path=DATA/'pages'/f'{pid}.png'
    if not path.exists():
        import fitz
        with connect() as c:r=c.execute('SELECT * FROM pages WHERE id=?',(pid,)).fetchone()
        if not r:raise HTTPException(404)
        with fitz.open(DATA/'originals'/f"{r['document_id']}.pdf") as d:d[r['number']-1].get_pixmap(matrix=fitz.Matrix(1.5,1.5)).save(path)
    return FileResponse(path)

@app.get('/api/documents/{did}/pdf')
def original(did:str):
    if not re.fullmatch('[a-f0-9]{64}',did):raise HTTPException(404)
    path=DATA/'originals'/f'{did}.pdf'
    if not path.exists():raise HTTPException(404)
    return FileResponse(path,media_type='application/pdf')

@app.put('/api/reports/{rid}')
def edit_report(rid:int,body:dict):
    if body.get('status') not in ['pending','confirmed','conflict']:raise HTTPException(400,'核对状态无效')
    if body.get('priority') not in ['核心资料','复查关注','背景备查']:raise HTTPException(400,'重要程度无效')
    with connect() as c:
        c.execute('BEGIN IMMEDIATE')
        if not c.execute('SELECT 1 FROM reports WHERE id=?',(rid,)).fetchone():raise HTTPException(404)
        before=report_snapshot(c,rid)
        if body.get('updated') and body['updated']!=before['updated']:raise HTTPException(409,'此记录已在其他页面修改，请返回列表重新打开')
        relevance=body.get('relevance',before['relevance'])
        if relevance not in ['clinical','unrelated']:raise HTTPException(400,'资料相关性无效')
        if body.get('status')=='confirmed' and relevance=='clinical':
            try:datetime.date.fromisoformat(body.get('date',''))
            except ValueError:raise HTTPException(400,'确认前须填写有效检查日期')
            if not body.get('patient','').strip():raise HTTPException(400,'确认前须核实姓名')
            expected=setting('patient_name')
            if expected and body['patient']!=expected:raise HTTPException(400,'姓名与资料主人不符，请先核实')
        dup=body.get('duplicate_of') or None
        if dup:
            target=c.execute('SELECT * FROM reports WHERE id=?',(dup,)).fetchone()
            if not target or dup==rid or target['duplicate_of'] or c.execute('SELECT 1 FROM reports WHERE duplicate_of=?',(rid,)).fetchone():raise HTTPException(400,'重复关联不能形成循环或链条')
        values=[body.get(k,'') for k in ['date','patient','category','priority','reason','status','summary']]
        c.execute('UPDATE reports SET date=?,patient=?,category=?,priority=?,reason=?,status=?,summary=?,issues=?,duplicate_of=?,updated=? WHERE id=?',(*values,json.dumps(body.get('issues',[]),ensure_ascii=False),dup,now(),rid))
        c.execute('UPDATE reports SET relevance=?,relevance_reason=? WHERE id=?',(relevance,str(body.get('relevance_reason',before['relevance_reason']))[:1000],rid))
        c.execute('DELETE FROM observations WHERE report_id=?',(rid,))
        for o in body.get('observations',[]):
            if not str(o.get('name','')).strip():continue
            c.execute('INSERT INTO observations(report_id,name,code,value,unit,reference,method,flag,box) VALUES(?,?,?,?,?,?,?,?,?)',(rid,*[str(o.get(k,'')) for k in ['name','code','value','unit','reference','method','flag']],json.dumps(o.get('box',[]) if not isinstance(o.get('box'),str) else json.loads(o['box']))))
        after=report_snapshot(c,rid)
        c.execute('INSERT INTO revisions(report_id,at,before_json,after_json) VALUES(?,?,?,?)',(rid,now(),json.dumps(before,ensure_ascii=False),json.dumps(after,ensure_ascii=False)))
    return {'ok':True}

@app.put('/api/reports/{rid}/classification')
def classify_report(rid:int,body:dict):
    relevance=body.get('relevance')
    priority=body.get('priority')
    if relevance is None and priority is None:raise HTTPException(400,'请选择分类')
    if relevance is not None and relevance not in ['clinical','unrelated']:raise HTTPException(400,'资料相关性无效')
    if priority is not None and priority not in ['核心资料','复查关注','背景备查']:raise HTTPException(400,'重要程度无效')
    with connect() as c:
        c.execute('BEGIN IMMEDIATE')
        if not c.execute('SELECT 1 FROM reports WHERE id=?',(rid,)).fetchone():raise HTTPException(404)
        before=report_snapshot(c,rid)
        if 'updated' not in body or body['updated']!=before['updated']:raise HTTPException(409,'此记录已修改，请刷新列表后重试')
        c.execute('UPDATE reports SET relevance=?,relevance_reason=?,priority=?,reason=?,updated=? WHERE id=?',(
            relevance or before['relevance'],str(body.get('relevance_reason',before['relevance_reason']))[:1000],
            priority or before['priority'],str(body.get('reason',before['reason']))[:2000],now(),rid))
        after=report_snapshot(c,rid)
        c.execute('INSERT INTO revisions(report_id,at,before_json,after_json) VALUES(?,?,?,?)',(rid,now(),json.dumps(before,ensure_ascii=False),json.dumps(after,ensure_ascii=False)))
    return {'ok':True}

@app.get('/api/reports/{rid}/history')
def history(rid:int):
    with connect() as c:return [dict(r) for r in c.execute('SELECT * FROM revisions WHERE report_id=? ORDER BY id DESC',(rid,))]

@app.put('/api/findings/{fid}')
def resolve_finding(fid:int,body:dict):
    with connect() as c:c.execute('UPDATE findings SET resolved=? WHERE id=?',(int(bool(body.get('resolved'))),fid))
    return {'ok':True}

@app.post('/api/questions')
def question(body:dict):
    with connect() as c:
        if body.get('id'):c.execute('UPDATE questions SET text=?,done=? WHERE id=?',(body['text'],int(body.get('done',False)),body['id']))
        else:c.execute('INSERT INTO questions(text) VALUES(?)',(body['text'],))
    return {'ok':True}

@app.get('/api/export/csv')
def export_csv():
    output=io.StringIO();w=csv.writer(output);w.writerow(['日期','项目','数值','单位','参考区间','方法','状态','来源','页码'])
    for r in reports():
        if r['duplicate_of'] or not is_clinical(r):continue
        for o in r['observations']:
            vals=[r['date'],o['name'],o['value'],o['unit'],o['reference'],o['method'],r['status'],r['filename'],r['number']]
            w.writerow(["'"+str(v) if str(v).startswith(('=','+','-','@')) else v for v in vals])
    return Response('\ufeff'+output.getvalue(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="records.csv"'})

def fernet(password,salt):
    key=hashlib.scrypt(password.encode(),salt=salt,n=16384,r=8,p=1,dklen=32)
    return Fernet(base64.urlsafe_b64encode(key))

@app.post('/api/backup')
def backup(body:dict):
    password=body.get('password','')
    if len(password)<10:raise HTTPException(400,'备份密码至少 10 个字符')
    output=io.BytesIO()
    with tempfile.TemporaryDirectory() as temp:
        snapshot=Path(temp)/'records.db'
        with connect() as c,sqlite3.connect(snapshot,factory=ClosingConnection) as dest:c.backup(dest)
        with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
            z.write(snapshot,'records.db')
            for folder in ['originals','pages']:
                for p in (DATA/folder).glob('*'):z.write(p,f'{folder}/{p.name}')
    salt=os.urandom(16);content=b'HEALTH1'+salt+fernet(password,salt).encrypt(output.getvalue())
    return Response(content,media_type='application/octet-stream',headers={'Content-Disposition':'attachment; filename="health-backup.health"'})

@app.post('/api/restore')
async def restore(file:UploadFile=File(...),password:str=Form(...)):
    content=await file.read(500*1024*1024+1)
    if len(content)>500*1024*1024 or not content.startswith(b'HEALTH1'):raise HTTPException(400,'备份文件无效或过大')
    try:plain=fernet(password,content[7:23]).decrypt(content[23:])
    except (InvalidToken,ValueError):raise HTTPException(400,'密码不正确或备份已损坏')
    # Restore into a separate validated folder; switching is performed with the service stopped.
    target=DATA/'restore-ready'
    if target.exists():raise HTTPException(409,'已有待恢复备份，请先完成或移走 restore-ready 文件夹')
    with zipfile.ZipFile(io.BytesIO(plain)) as z:
        if sum(x.file_size for x in z.infolist())>2*1024**3:raise HTTPException(400,'解压后文件过大')
        for name in z.namelist():
            if not (name=='records.db' or re.fullmatch(r'originals/[a-f0-9]{64}\.pdf|pages/\d+\.png',name)):raise HTTPException(400,'备份路径无效')
        if 'records.db' not in z.namelist():raise HTTPException(400,'备份缺少数据库')
        with tempfile.TemporaryDirectory(dir=DATA) as temp:
            z.extractall(temp)
            with sqlite3.connect(Path(temp)/'records.db',factory=ClosingConnection) as c:
                if c.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise HTTPException(400,'数据库校验失败')
                c.execute('SELECT id FROM reports LIMIT 1')
            import shutil
            shutil.copytree(temp,target)
    return {'ok':True,'message':'备份已验证。请在电脑双击「恢复备份.cmd」，程序将保留当前数据后切换。'}

if (ROOT/'dist').exists():app.mount('/',StaticFiles(directory=ROOT/'dist',html=True),name='web')
