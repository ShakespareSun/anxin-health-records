"""Hidden desktop launcher and tray supervisor. Runs only this project's services."""
import json, logging, os, socket, subprocess, sys, threading, urllib.request, webbrowser
import psutil
from PIL import Image
import pystray
from process_control import ROOT,WindowsJob,QuitEvent,InstanceLock,terminate_tree,event_name

URL='http://127.0.0.1:8765'

def show_error(message):
 import ctypes
 ctypes.windll.user32.MessageBoxW(None,message,'安心病历',0x10)

def main():
 os.chdir(ROOT);(ROOT/'data').mkdir(exist_ok=True)
 lock=InstanceLock(ROOT/'data'/'launcher.lock')
 if not lock.acquire():webbrowser.open(URL);return
 logging.basicConfig(filename=ROOT/'data'/'launcher.log',encoding='utf-8',level=logging.INFO,format='%(asctime)s %(message)s')
 job=None;quit_event=None;icon=None;monitor=None
 try:
  with socket.socket() as s:
   if s.connect_ex(('127.0.0.1',8765))==0:
    raise RuntimeError('本机端口 8765 已被占用。请先停止旧版病历工具或占用该端口的程序，再重新打开。')
  job=WindowsJob();job.attach(os.getpid())
  # Normal supervisor exit closes this private job, killing remaining descendants.
  quit_event=QuitEvent();state={'label':'正在启动','ready':False}
  def open_tool(*_):webbrowser.open(URL)
  def quit_tool(*_):
   state['label']='正在退出';icon.title='安心病历 · 正在退出';icon.update_menu();quit_event.set()
  icon=pystray.Icon('anxin-health',Image.open(ROOT/'assets'/'app.png'),'安心病历 · 正在启动',pystray.Menu(
   pystray.MenuItem(lambda _:'状态：'+state['label'],lambda *_:None,enabled=False),
   pystray.MenuItem('打开病历工具',open_tool,default=True,enabled=lambda _:state['ready']),
   pystray.MenuItem('打开资料文件夹',lambda *_:os.startfile(ROOT/'data')),
   pystray.Menu.SEPARATOR,
   pystray.MenuItem('退出并关闭全部进程',quit_tool)))
  def supervise():
   try:
    with open(ROOT/'data'/'server.log','a',encoding='utf-8') as serverlog,open(ROOT/'data'/'ocr.log','a',encoding='utf-8') as ocrlog:
     env={**os.environ,'PYTHONIOENCODING':'utf-8'};flags=subprocess.CREATE_NO_WINDOW
     server=subprocess.Popen([sys.executable,'-m','uvicorn','app:app','--host','127.0.0.1','--port','8765'],stdout=serverlog,stderr=serverlog,creationflags=flags,env=env)
     worker=subprocess.Popen([sys.executable,'ocr_worker.py'],stdout=ocrlog,stderr=ocrlog,creationflags=flags,env=env)
     roles={'server':server.pid,'worker':worker.pid,'supervisor':os.getpid()}
     meta={**roles,'created':{k:psutil.Process(v).create_time() for k,v in roles.items()},'version':2,'event':event_name()}
     temporary=ROOT/'data'/'processes.tmp';temporary.write_text(json.dumps(meta));temporary.replace(ROOT/'data'/'processes.json')
     for _ in range(150):
      if quit_event.wait(.2):return
      if server.poll() is not None:raise RuntimeError('网页服务启动失败，请查看资料文件夹中的 server.log。')
      try:
       with urllib.request.urlopen(URL+'/api/auth/status',timeout=1) as response:
        if 'logged_in' in json.load(response):break
      except (OSError,ValueError):continue
     else:raise RuntimeError('网页服务未能及时启动，请查看 server.log 后重新打开。')
     state.update(label='运行中',ready=True);icon.title='安心病历 · 运行中';icon.update_menu()
     icon.notify('右键此图标可打开工具，或退出并关闭全部后台进程。','安心病历已启动')
     webbrowser.open(URL);logging.info('Services ready')
     warned=False
     while not quit_event.wait(1):
      if server.poll() is not None:raise RuntimeError('网页服务已停止，请退出后重新打开工具。')
      if worker.poll() is not None and not warned:
       warned=True;state['label']='识别服务已停止';icon.title='安心病历 · 识别服务已停止';icon.update_menu()
       from store import set_setting
       set_setting('worker_error','识别服务已退出，请查看 ocr.log；可从托盘退出后重新打开工具。')
       icon.notify('识别服务已停止。已保存的资料仍可查看，请退出后重新打开工具。','安心病历')
   except Exception as e:
    logging.exception('Service error');state.update(label='启动或运行失败',ready=False)
    icon.title='安心病历 · 服务异常';icon.update_menu();icon.notify(str(e),'安心病历运行异常')
    terminate_tree(psutil.Process(),include_root=False)
    while not quit_event.wait(.5):pass
   finally:
    terminate_tree(psutil.Process(),include_root=False)
    path=ROOT/'data'/'processes.json'
    try:
     if json.loads(path.read_text()).get('supervisor')==os.getpid():path.unlink()
    except (OSError,ValueError):pass
    logging.info('All application child processes stopped');icon.stop()
  def setup(_):
   nonlocal monitor
   icon.visible=True;monitor=threading.Thread(target=supervise,name='health-supervisor');monitor.start()
  icon.run(setup=setup)
 except Exception as e:
  logging.exception('Launcher error');show_error(str(e))
 finally:
  if quit_event:quit_event.set()
  if monitor:monitor.join(timeout=8)
  terminate_tree(psutil.Process(),include_root=False)
  if quit_event:quit_event.close()
  lock.close()
  # Do not close the job explicitly while this supervisor is a member.

if __name__=='__main__':main()
