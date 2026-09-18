from __future__ import annotations

def evaluate_budget(signals,limits):
    try:
        cpu=float(signals['cpu_percent']); mem=float(signals['memory_mb']); disk=float(signals['disk_free_mb'])
        mcpu=float(limits['max_cpu_percent']); mmem=float(limits['max_memory_mb']); mdisk=float(limits['min_disk_free_mb'])
    except Exception: return {'ok':False,'allowed':False,'overall':'FAIL','reasons':['invalid_or_missing_numeric_signal']}
    reasons=[]
    if cpu>mcpu: reasons.append('cpu_over_budget')
    if mem>mmem: reasons.append('memory_over_budget')
    if disk<mdisk: reasons.append('disk_below_minimum')
    return {'ok':True,'allowed':not reasons,'overall':'PASS' if not reasons else 'FAIL','reasons':reasons,'signals':{'cpu_percent':cpu,'memory_mb':mem,'disk_free_mb':disk}}
