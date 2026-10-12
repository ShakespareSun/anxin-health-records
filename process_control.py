"""Windows controls scoped to this checkout; never stop arbitrary Python processes."""
import ctypes, hashlib, json, os
from ctypes import wintypes as W
from pathlib import Path
import psutil

ROOT=Path(__file__).resolve().parent
kernel=ctypes.WinDLL('kernel32',use_last_error=True)
for name,args,result in [
 ('CreateJobObjectW',[ctypes.c_void_p,W.LPCWSTR],W.HANDLE),
 ('SetInformationJobObject',[W.HANDLE,ctypes.c_int,ctypes.c_void_p,W.DWORD],W.BOOL),
 ('AssignProcessToJobObject',[W.HANDLE,W.HANDLE],W.BOOL),
 ('OpenProcess',[W.DWORD,W.BOOL,W.DWORD],W.HANDLE),
 ('CreateEventW',[ctypes.c_void_p,W.BOOL,W.BOOL,W.LPCWSTR],W.HANDLE),
 ('OpenEventW',[W.DWORD,W.BOOL,W.LPCWSTR],W.HANDLE),
 ('SetEvent',[W.HANDLE],W.BOOL),('ResetEvent',[W.HANDLE],W.BOOL),
 ('WaitForSingleObject',[W.HANDLE,W.DWORD],W.DWORD),('CloseHandle',[W.HANDLE],W.BOOL)]:
 fn=getattr(kernel,name);fn.argtypes=args;fn.restype=result

class BasicLimits(ctypes.Structure):
 _fields_=[('ProcessTime',ctypes.c_longlong),('JobTime',ctypes.c_longlong),('Flags',W.DWORD),
           ('MinWorkingSet',ctypes.c_size_t),('MaxWorkingSet',ctypes.c_size_t),('ActiveProcesses',W.DWORD),
           ('Affinity',ctypes.c_size_t),('Priority',W.DWORD),('Scheduling',W.DWORD)]
class IOCounters(ctypes.Structure):
 _fields_=[(name,ctypes.c_ulonglong) for name in ['ReadOps','WriteOps','OtherOps','ReadBytes','WriteBytes','OtherBytes']]
class ExtendedLimits(ctypes.Structure):
 _fields_=[('Basic',BasicLimits),('IO',IOCounters),('ProcessMemory',ctypes.c_size_t),('JobMemory',ctypes.c_size_t),
           ('PeakProcessMemory',ctypes.c_size_t),('PeakJobMemory',ctypes.c_size_t)]

class WindowsJob:
 def __init__(self):
  self.handle=kernel.CreateJobObjectW(None,None)
  if not self.handle:raise ctypes.WinError(ctypes.get_last_error())
  limits=ExtendedLimits();limits.Basic.Flags=0x2000
  if not kernel.SetInformationJobObject(self.handle,9,ctypes.byref(limits),ctypes.sizeof(limits)):
   error=ctypes.get_last_error();self.close();raise ctypes.WinError(error)
 def attach(self,pid):
  process=kernel.OpenProcess(0x0100|0x0001,False,pid)
  if not process:raise ctypes.WinError(ctypes.get_last_error())
  try:
   if not kernel.AssignProcessToJobObject(self.handle,process):raise ctypes.WinError(ctypes.get_last_error())
  finally:kernel.CloseHandle(process)
 def close(self):
  if self.handle:kernel.CloseHandle(self.handle);self.handle=None

def event_name(root=ROOT):return 'Local\\AnxinHealthQuit-'+hashlib.sha256(str(root.resolve()).casefold().encode()).hexdigest()[:24]

class QuitEvent:
 def __init__(self,root=ROOT):
  self.handle=kernel.CreateEventW(None,True,False,event_name(root))
  if not self.handle:raise ctypes.WinError(ctypes.get_last_error())
  kernel.ResetEvent(self.handle)
 def set(self):kernel.SetEvent(self.handle)
 def wait(self,seconds):return kernel.WaitForSingleObject(self.handle,int(seconds*1000))==0
 def close(self):
  if self.handle:kernel.CloseHandle(self.handle);self.handle=None

class InstanceLock:
 def __init__(self,path):self.path=Path(path);self.file=None
 def acquire(self):
  import msvcrt
  self.path.parent.mkdir(parents=True,exist_ok=True)
  self.file=open(self.path,'a+b')
  if not self.path.stat().st_size:self.file.write(b'0');self.file.flush()
  self.file.seek(0)
  try:msvcrt.locking(self.file.fileno(),msvcrt.LK_NBLCK,1);return True
  except OSError:self.file.close();self.file=None;return False
 def close(self):
  if self.file:self.file.close();self.file=None

def terminate_tree(process,include_root=True):
 try:children=process.children(recursive=True)
 except psutil.NoSuchProcess:return
 targets=list(reversed(children))+([process] if include_root else [])
 for p in targets:
  try:p.terminate()
  except psutil.NoSuchProcess:pass
 _,alive=psutil.wait_procs(targets,timeout=3)
 for p in alive:
  try:p.kill()
  except psutil.NoSuchProcess:pass
 psutil.wait_procs(alive,timeout=2)

def recorded_process(meta,role,root=ROOT):
 try:
  p=psutil.Process(meta[role])
  if Path(p.cwd()).resolve()!=root.resolve() or 'python' not in p.name().lower():return None
  expected=meta.get('created',{}).get(role)
  if expected is not None and abs(p.create_time()-expected)>.01:return None
  args=p.cmdline()
  if role=='supervisor' and not any(Path(a).name=='launcher.py' for a in args):return None
  if role=='worker' and not any(Path(a).name=='ocr_worker.py' for a in args):return None
  if role=='server' and not ('app:app' in args and '8765' in args):return None
  return p
 except (KeyError,psutil.NoSuchProcess,psutil.AccessDenied):return None

def stop_application(root=ROOT):
 path=root/'data'/'processes.json'
 try:meta=json.loads(path.read_text())
 except (OSError,ValueError):return False
 supervisor=recorded_process(meta,'supervisor',root)
 if supervisor:
  event=kernel.OpenEventW(0x0002,False,event_name(root))
  if event:
   try:kernel.SetEvent(event)
   finally:kernel.CloseHandle(event)
   try:supervisor.wait(timeout=10);return True
   except psutil.TimeoutExpired:pass
  terminate_tree(supervisor)
 for role in ['worker','server']:
  process=recorded_process(meta,role,root)
  if process:terminate_tree(process)
 return True
