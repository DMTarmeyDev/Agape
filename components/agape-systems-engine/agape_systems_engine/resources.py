from __future__ import annotations
import ctypes, os, shutil, time
from pathlib import Path

class MEMORYSTATUSEX(ctypes.Structure):
    _fields_=[('dwLength',ctypes.c_ulong),('dwMemoryLoad',ctypes.c_ulong),('ullTotalPhys',ctypes.c_ulonglong),('ullAvailPhys',ctypes.c_ulonglong),('ullTotalPageFile',ctypes.c_ulonglong),('ullAvailPageFile',ctypes.c_ulonglong),('ullTotalVirtual',ctypes.c_ulonglong),('ullAvailVirtual',ctypes.c_ulonglong),('ullAvailExtendedVirtual',ctypes.c_ulonglong)]

def _win_memory():
    if os.name!='nt':return None
    st=MEMORYSTATUSEX();st.dwLength=ctypes.sizeof(MEMORYSTATUSEX)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):return None
    return {'total_mb':st.ullTotalPhys/1048576,'available_mb':st.ullAvailPhys/1048576,'used_percent':float(st.dwMemoryLoad)}

def _win_cpu(sample=0.08):
    if os.name!='nt':return None
    FILETIME=ctypes.c_ulonglong
    def snap():
        idle=FILETIME();kernel=FILETIME();user=FILETIME()
        if not ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle),ctypes.byref(kernel),ctypes.byref(user)):return None
        return idle.value,kernel.value,user.value
    a=snap();time.sleep(sample);b=snap()
    if not a or not b:return None
    idle=b[0]-a[0]; total=(b[1]-a[1])+(b[2]-a[2])
    if total<=0:return None
    return max(0.0,min(100.0,100.0*(1.0-idle/total)))

def snapshot(path: str|Path):
    disk=shutil.disk_usage(str(Path(path).anchor or path))
    mem=_win_memory()
    cpu=_win_cpu()
    if os.name!='nt':
        try:
            load=os.getloadavg()[0]; cpu=max(0.0,min(100.0,100.0*load/max(1,os.cpu_count() or 1)))
        except Exception:cpu=None
        try:
            pages=os.sysconf('SC_PHYS_PAGES'); page_size=os.sysconf('SC_PAGE_SIZE'); avail=os.sysconf('SC_AVPHYS_PAGES')
            mem={'total_mb':pages*page_size/1048576,'available_mb':avail*page_size/1048576,'used_percent':100*(1-avail/pages)}
        except Exception:mem=None
    return {'cpu_percent':cpu,'memory':mem,'disk_free_mb':disk.free/1048576,'cpu_count':os.cpu_count() or 1}

def allowed(signals, limits):
    reasons=[]
    cpu=signals.get('cpu_percent');mem=(signals.get('memory') or {}).get('available_mb');disk=signals.get('disk_free_mb')
    max_cpu=limits.get('max_cpu_percent',85);min_mem=limits.get('min_memory_mb',700);min_disk=limits.get('min_disk_free_mb',1000)
    if cpu is not None and cpu>max_cpu:reasons.append(f'CPU_HIGH:{cpu:.1f}>{max_cpu}')
    if mem is not None and mem<min_mem:reasons.append(f'MEMORY_LOW:{mem:.0f}<{min_mem}')
    if disk is not None and disk<min_disk:reasons.append(f'DISK_LOW:{disk:.0f}<{min_disk}')
    return {'allowed':not reasons,'reasons':reasons,'signals':signals,'limits':limits}
