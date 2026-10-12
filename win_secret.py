"""DPAPI: OAuth credentials can only be decrypted by the current Windows user."""
import ctypes, os
from ctypes import wintypes

class Blob(ctypes.Structure):
    _fields_=[('size',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_ubyte))]

def protect_bytes(content,decrypt=False):
    if os.name!='nt':raise RuntimeError('账户凭据存储需要 Windows 用户加密支持')
    buffer=ctypes.create_string_buffer(content)
    source=Blob(len(content),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_ubyte)));target=Blob()
    crypt=ctypes.WinDLL('crypt32',use_last_error=True)
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    if decrypt:
        ok=crypt.CryptUnprotectData(ctypes.byref(source),None,None,None,None,1,ctypes.byref(target))
    else:
        ok=crypt.CryptProtectData(ctypes.byref(source),'安心 ChatGPT 账户',None,None,None,1,ctypes.byref(target))
    if not ok:raise ctypes.WinError(ctypes.get_last_error())
    try:return ctypes.string_at(target.data,target.size)
    finally:
        kernel.LocalFree.argtypes=[wintypes.HLOCAL];kernel.LocalFree.restype=wintypes.HLOCAL
        kernel.LocalFree(ctypes.cast(target.data,wintypes.HLOCAL))
