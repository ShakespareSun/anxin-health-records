import json,os,subprocess,sys,time
from pathlib import Path
import psutil
from process_control import WindowsJob,QuitEvent,InstanceLock,recorded_process,stop_application,terminate_tree

def test_instance_lock_and_quit_event_are_scoped(tmp_path):
 a=InstanceLock(tmp_path/'lock');b=InstanceLock(tmp_path/'lock')
 try:
  assert a.acquire() and not b.acquire()
  a.close();assert b.acquire()
 finally:a.close();b.close()
 event=QuitEvent(tmp_path)
 try:
  assert not event.wait(0)
  handle=__import__('process_control').kernel.OpenEventW(0x0002,False,__import__('process_control').event_name(tmp_path))
  assert handle
  __import__('process_control').kernel.SetEvent(handle);__import__('process_control').kernel.CloseHandle(handle)
  assert event.wait(.2)
 finally:event.close()

def test_job_closes_owned_descendants_without_affecting_other_process(tmp_path):
 outside=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'],creationflags=subprocess.CREATE_NO_WINDOW)
 child=None;job=WindowsJob();tracked=[]
 try:
  ready=tmp_path/'go';pidfile=tmp_path/'child.json'
  code="import pathlib,sys,time,subprocess,json; gate=pathlib.Path(sys.argv[1]);\nwhile not gate.exists(): time.sleep(.02)\np=subprocess.Popen([sys.argv[3],'-c','import time;time.sleep(60)']);pathlib.Path(sys.argv[2]).write_text(json.dumps(p.pid));time.sleep(60)"
  # Attach the actual supervisor before it creates any children, just as launcher.py does.
  # Its child uses the venv redirector to exercise both wrapper and real interpreter.
  child=subprocess.Popen([sys._base_executable,'-c',code,str(ready),str(pidfile),sys.executable],creationflags=subprocess.CREATE_NO_WINDOW)
  job.attach(child.pid);ready.touch()
  deadline=time.monotonic()+5
  while not pidfile.exists() and time.monotonic()<deadline:time.sleep(.02)
  assert pidfile.exists()
  tracked=[psutil.Process(child.pid)]+psutil.Process(child.pid).children(recursive=True)
  job.close();child.wait(timeout=5)
  _,alive=psutil.wait_procs(tracked,timeout=5)
  assert not alive
  assert outside.poll() is None
 finally:
  job.close()
  for p in tracked:
   if p.is_running():terminate_tree(p)
  if child and child.poll() is None:terminate_tree(psutil.Process(child.pid))
  if outside.poll() is None:terminate_tree(psutil.Process(outside.pid))

def test_stale_manifest_never_stops_unrelated_python(tmp_path):
 (tmp_path/'data').mkdir()
 child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'],cwd=tmp_path,creationflags=subprocess.CREATE_NO_WINDOW)
 try:
  meta={'supervisor':child.pid,'server':child.pid,'worker':child.pid,'created':{'supervisor':1}}
  assert recorded_process(meta,'supervisor',tmp_path) is None
  (tmp_path/'data'/'processes.json').write_text(json.dumps(meta))
  stop_application(tmp_path);assert child.poll() is None
 finally:terminate_tree(psutil.Process(child.pid))
