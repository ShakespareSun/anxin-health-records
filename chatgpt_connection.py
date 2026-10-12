"""Official SIWC public-client OAuth and Responses transport. No Codex token reuse."""
import base64, hashlib, hmac, json, secrets, threading, time, uuid, webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlencode, urlparse, parse_qs
import httpx, jwt
from store import DATA, setting, set_setting
from win_secret import protect_bytes

ISSUER='https://auth.openai.com'
TOKEN_URL=ISSUER+'/api/accounts/oauth/token'
API='https://api.openai.com/v1'
LOCK=threading.RLock()
LOGIN={'pending':False,'message':''}
CATALOG={}

class ConnectionError(Exception):pass

def load_credentials():
    path=DATA/'private'/'chatgpt.bin'
    if not path.exists():return {'active':'','accounts':{}}
    try:return json.loads(protect_bytes(path.read_bytes(),decrypt=True))
    except Exception:raise ConnectionError('无法解密 ChatGPT 连接；请在原 Windows 账户使用或重新连接。')

def save_credentials(data):
    path=DATA/'private'/'chatgpt.bin';path.parent.mkdir(exist_ok=True)
    temp=path.with_suffix('.tmp');temp.write_bytes(protect_bytes(json.dumps(data).encode()));temp.replace(path)

def status():
    with LOCK:
        c=load_credentials();a=c['accounts'].get(c['active'],{})
        return {'connected':bool(a.get('access_token')),'active':c['active'],
                'accounts':[{'id':cid,'label':f"{v.get('email','ChatGPT 账户')} · {cid[-6:]}",'connected':bool(v.get('access_token'))} for cid,v in c['accounts'].items()],
                'model':setting('ai_model'),'login_pending':LOGIN['pending'],'message':LOGIN['message']}

def get_metadata():
    with httpx.Client(timeout=20) as c:
        r=c.get(ISSUER+'/.well-known/openid-configuration');r.raise_for_status();m=r.json()
    if m.get('issuer')!=ISSUER:raise ConnectionError('OpenAI 登录配置校验失败')
    for key in ['authorization_endpoint','token_endpoint','jwks_uri','revocation_endpoint']:
        if key in m and urlparse(m[key]).scheme+'://'+urlparse(m[key]).netloc!=ISSUER:raise ConnectionError('OpenAI 登录地址校验失败')
    return m

def validate_identity(token,client_id,nonce,jwks_uri):
    header=jwt.get_unverified_header(token)
    if header.get('alg') not in ['RS256','ES256']:raise ConnectionError('身份令牌签名算法无效')
    with httpx.Client(timeout=20) as c:
        r=c.get(jwks_uri);r.raise_for_status();keys=r.json()['keys']
    key=next((k for k in keys if k.get('kid')==header.get('kid')),None)
    if not key:raise ConnectionError('身份签名密钥无效')
    claims=jwt.decode(token,jwt.PyJWK.from_dict(key).key,algorithms=[header['alg']],audience=client_id,issuer=ISSUER,
                      leeway=5,options={'require':['exp','iat','sub','nonce']})
    if not isinstance(claims['sub'],str) or not claims['sub'] or not hmac.compare_digest(claims['nonce'],nonce):raise ConnectionError('身份令牌随机值校验失败')
    return claims

def exchange_callback(query,pending):
    if time.time()>pending['expires'] or not hmac.compare_digest(query.get('state',''),pending['state']):raise ConnectionError('登录请求已过期或校验失败，请重新连接。')
    if query.get('error'):raise ConnectionError('未完成 ChatGPT 授权，请重新连接并检查额度授权。')
    client_id=query.get('client_id') or pending.get('client_id')
    if not client_id or client_id=='dynamic_agent_client':raise ConnectionError('注册未返回有效应用标识。')
    if pending.get('client_id') and client_id!=pending['client_id']:raise ConnectionError('返回的账户注册与所选账户不一致。')
    if not query.get('code'):raise ConnectionError('缺少登录授权码。')
    with httpx.Client(timeout=30) as c:
        r=c.post(pending['metadata']['token_endpoint'],data={'grant_type':'authorization_code','client_id':client_id,
                 'code':query['code'],'code_verifier':pending['verifier'],'redirect_uri':pending['redirect_uri'],'resource':API})
        if not r.is_success:raise ConnectionError('授权码交换失败，请重新连接。')
        t=r.json()
    claims=validate_identity(t['id_token'],client_id,pending['nonce'],pending['metadata']['jwks_uri'])
    if pending.get('subject') and claims['sub']!=pending['subject']:raise ConnectionError('登录身份与所选账户不一致。')
    scopes=t.get('scope','').split()
    if 'chatgpt.tokens.use.direct' not in scopes:raise ConnectionError('该账户尚未授权工具使用 ChatGPT 额度。')
    with LOCK:
        all_accounts=load_credentials()
        all_accounts['accounts'][client_id]={**t,'scopes':scopes,'subject':claims['sub'],'email':claims.get('email','ChatGPT 账户'),
                         'expires_at':time.time()+int(t.get('expires_in',3600))}
        all_accounts['active']=client_id;save_credentials(all_accounts);CATALOG.clear()
        set_setting('ai_model','')

def begin_login(account_id=''):
    with LOCK:
        if LOGIN['pending']:raise ConnectionError('已有登录窗口，请完成它或等待十分钟后重试。')
        credentials=load_credentials()
        saved=credentials['accounts'].get(account_id,{}) if account_id else {}
        if account_id and not saved:raise ConnectionError('所选账户不存在。')
        LOGIN.update(pending=True,message='正在打开 ChatGPT 登录，请在这台电脑的浏览器完成授权。')
    try:metadata=get_metadata()
    except Exception:
        LOGIN.update(pending=False,message='无法连接 OpenAI 登录服务，请检查网络后重试。')
        raise ConnectionError(LOGIN['message'])
    state=secrets.token_urlsafe(32);nonce=secrets.token_urlsafe(32);verifier=secrets.token_urlsafe(48)
    pending={'state':state,'nonce':nonce,'verifier':verifier,'expires':time.time()+600,'client_id':account_id,
             'subject':saved.get('subject'),'metadata':metadata}
    finished=threading.Event()
    class Callback(BaseHTTPRequestHandler):
        def log_message(self,*args):pass  # Never log codes or tokens.
        def do_GET(self):
            parsed=urlparse(self.path)
            if parsed.path!='/auth/callback':self.send_error(404);return
            query={k:v[0] for k,v in parse_qs(parsed.query).items()}
            # Random wrong-state traffic must not consume the user's valid attempt.
            if not hmac.compare_digest(query.get('state',''),state):self.send_error(400,'Invalid state');return
            try:
                exchange_callback(query,pending)
                message='连接成功。请关闭本页并返回安心病历工具。'
            except Exception as e:
                message=str(e) if isinstance(e,ConnectionError) else '连接校验失败，请返回工具重新连接。'
            with LOCK:LOGIN.update(pending=False,message=message)
            page=('<!doctype html><meta charset="utf-8"><title>安心 · ChatGPT 连接</title><p>'+message+'</p>').encode()
            self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(page)
            finished.set()
    try:server=HTTPServer(('127.0.0.1',0),Callback)
    except Exception:
        LOGIN.update(pending=False,message='无法启动本机登录回调');raise ConnectionError(LOGIN['message'])
    pending['redirect_uri']=f'http://127.0.0.1:{server.server_port}/auth/callback'
    host=setting('ai_host_id')
    if not host:host='urn:uuid:'+str(uuid.uuid4());set_setting('ai_host_id',host)
    parameters={'client_id':account_id or 'dynamic_agent_client','ext_agent_host_id':host,'response_type':'code',
                'redirect_uri':pending['redirect_uri'],'scope':'openid profile email offline_access resource.invoke chatgpt.tokens.use.direct',
                'resource':API,'state':state,'nonce':nonce,'code_challenge_method':'S256',
                'code_challenge':base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')}
    if not account_id:parameters['agent_name_hint']='安心家庭病历'
    else:
        if saved.get('id_token'):parameters['id_token_hint']=saved['id_token']
        if saved.get('email'):parameters['login_hint']=saved['email']
    def listen():
        server.timeout=1
        try:
            while not finished.is_set() and time.time()<pending['expires']:server.handle_request()
        finally:
            server.server_close()
            with LOCK:
                if not finished.is_set():LOGIN.update(pending=False,message='登录等待超时，请重新连接。')
    threading.Thread(target=listen,daemon=True).start()
    webbrowser.open(metadata['authorization_endpoint']+'?'+urlencode(parameters))
    return {'ok':True,'message':LOGIN['message']}

def access_token():
    with LOCK:
        c=load_credentials();cid=c['active'];a=c['accounts'].get(cid,{})
        if not a.get('access_token'):raise ConnectionError('请先在电脑连接 ChatGPT 账户。')
        if a['expires_at']<time.time()+90:
            if not a.get('refresh_token'):raise ConnectionError('账户连接已过期，请重新连接。')
            with httpx.Client(timeout=30) as client:
                r=client.post(TOKEN_URL,data={'grant_type':'refresh_token','client_id':cid,'refresh_token':a['refresh_token'],'resource':API})
            if not r.is_success:raise ConnectionError('账户续期失败，请重新连接 ChatGPT。')
            t=r.json()
            if t.get('scope') and 'chatgpt.tokens.use.direct' not in t['scope'].split():raise ConnectionError('ChatGPT 额度授权已撤销，请重新连接。')
            a.update(t);a['expires_at']=time.time()+int(t.get('expires_in',3600));save_credentials(c)
        return a['access_token'],cid

def models():
    token,cid=access_token()
    with httpx.Client(timeout=30) as c:
        r=c.get(API+'/models',headers={'Authorization':'Bearer '+token})
        if not r.is_success:raise ConnectionError('无法读取账户模型列表，请检查授权或网络。')
        body=r.json()
    available=[{'id':m['slug'],'name':m.get('display_name',m['slug'])} for m in body.get('models',[]) if m.get('visibility')=='list']
    if not available:raise ConnectionError('账户没有返回可选择的模型，暂时不能调用。')
    CATALOG[cid]=available
    return available

def disconnect():
    with LOCK:
        c=load_credentials();a=c['accounts'].get(c['active'],{});revoked=True
        if a.get('refresh_token'):
            try:
                m=get_metadata()
                with httpx.Client(timeout=20) as client:r=client.post(m['revocation_endpoint'],data={'token':a['refresh_token'],'token_type_hint':'refresh_token','client_id':c['active']})
                revoked=r.status_code==200
            except Exception:revoked=False
        for key in ['access_token','refresh_token','id_token']:a.pop(key,None)
        save_credentials(c);CATALOG.clear()
        return {'ok':True,'message':'已断开 ChatGPT 连接。' if revoked else '本机已断开；远程撤销未确认，可到 ChatGPT 设置中断开此应用。'}

def request_completion(model,instructions,messages):
    token,cid=access_token()
    available=CATALOG.get(cid) or models()
    if model not in [m['id'] for m in available]:raise ConnectionError('请选择当前账户返回的模型。')
    payload={'model':model,'instructions':instructions,'input':messages,'store':False,'stream':True}
    completed=None;output=[];length=0
    try:
        with httpx.Client(timeout=httpx.Timeout(180,connect=20)) as c:
            with c.stream('POST',API+'/responses',headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'},json=payload) as r:
                if not r.is_success:
                    raise ConnectionError({401:'ChatGPT 连接失效，请重新连接。',403:'账户未授权该调用或模型。',429:'ChatGPT 额度或调用频率受限，请稍后再试。'}.get(r.status_code,'OpenAI 未完成请求，请检查账户权限与网络。'))
                for line in r.iter_lines():
                    if not line.startswith('data: '):continue
                    content=line[6:]
                    if content=='[DONE]':continue
                    event=json.loads(content)
                    if event.get('type')=='response.output_text.delta':
                        delta=event.get('delta','');output.append(delta);length+=len(delta)
                        if length>45000:raise ConnectionError('回答超过工具长度限制，请缩小问题范围。此请求可能已消耗额度。')
                    elif event.get('type') in ['response.failed','response.incomplete','error']:
                        raise ConnectionError('大模型未完成回答，可能为额度、权限或服务限制；没有将部分回答作为分析报告保存。')
                    elif event.get('type')=='response.completed':completed=event.get('response',{})
    except httpx.HTTPError:raise ConnectionError('OpenAI 连接中断；未保存不完整回答，请稍后重试。请求可能已消耗额度。')
    if completed is None:raise ConnectionError('回答中断，未收到完成确认；请重试。')
    text=''.join(output)
    if not text.strip():raise ConnectionError('模型没有返回可显示的文字，请换模型或重试。')
    return {'text':text,'usage':completed.get('usage',{}),'model':model}
