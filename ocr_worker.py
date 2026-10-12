import os, json, re, hashlib, time, traceback
os.environ['PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK']='True'
os.environ['FLAGS_use_mkldnn']='0'
from store import *
from extraction import extract_report, extract_observations

def run():
    import fitz
    from paddleocr import PaddleOCR
    init()
    # A Windows file lock prevents a second launcher from resetting an active job.
    import msvcrt
    lock=open(DATA/'worker.lock','a+b');lock.seek(0);lock.write(b'0');lock.flush();lock.seek(0)
    try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:return
    set_setting('worker_error','')
    with connect() as c: c.execute("UPDATE pages SET status='queued' WHERE status='processing'")
    engine=PaddleOCR(lang='ch',use_doc_orientation_classify=True,use_doc_unwarping=False,use_textline_orientation=True,enable_mkldnn=False,cpu_threads=4)
    while True:
        with connect() as c:r=c.execute("SELECT * FROM pages WHERE status='queued' ORDER BY document_id,number LIMIT 1").fetchone()
        if not r: time.sleep(3);continue
        try:
            with connect() as c:c.execute("UPDATE pages SET status='processing',error=NULL WHERE id=?",(r['id'],))
            doc=fitz.open(DATA/'originals'/f"{r['document_id']}.pdf")
            page=doc[r['number']-1]; pix=page.get_pixmap(matrix=fitz.Matrix(2,2)); path=DATA/'pages'/f"{r['id']}.png";pix.save(path);doc.close()
            result=list(engine.predict(str(path)))[0]
            obj=result.json;obj=obj['res'] if 'res' in obj else obj
            blocks=[dict(text=t,confidence=float(s),box=[int(x) for x in b]) for t,s,b in zip(obj['rec_texts'],obj['rec_scores'],obj['rec_boxes'])]
            # OCR boxes can refer to an orientation-corrected image. Save that image with the boxes.
            inp=result.get('doc_preprocessor_res',{}).get('output_img')
            if inp is not None:
                from PIL import Image
                Image.fromarray(inp[:,:,::-1]).save(path)
            raw='\n'.join(b['text'] for b in blocks); fields=extract_report(blocks,setting('patient_name'))
            with connect() as c:
                c.execute("UPDATE pages SET status='done',raw=?,blocks=?,image_hash=? WHERE id=?",(raw,json.dumps(blocks,ensure_ascii=False),hashlib.sha256(path.read_bytes()).hexdigest(),r['id']))
                existing=c.execute('SELECT id FROM reports WHERE page_id=?',(r['id'],)).fetchone()
                if not existing:
                    rid=c.execute('INSERT INTO reports(page_id,date,patient,category,priority,reason,summary,issues,updated) VALUES(?,?,?,?,?,?,?,?,?)',(r['id'],fields['date'],fields['patient'],fields['category'],fields['priority'],fields['reason'],fields['summary'],json.dumps(fields['issues'],ensure_ascii=False),now())).lastrowid
                    if fields['category']=='检验':
                        for o in extract_observations(blocks):
                            c.execute('INSERT INTO observations(report_id,name,code,value,unit,reference,method,flag,box) VALUES(?,?,?,?,?,?,?,?,?)',(rid,*[o[k] for k in ['name','code','value','unit','reference','method','flag']],json.dumps(o['box'])))
            if not existing:
                from audit import audit_new_report
                audit_new_report(rid)
            print(f"DONE page {r['id']} {r['number']}",flush=True)
        except Exception as e:
            with connect() as c:c.execute("UPDATE pages SET status='failed',error=? WHERE id=?",(str(e)[:1500],r['id']))
            traceback.print_exc()

if __name__=='__main__':run()
