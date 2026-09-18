from __future__ import annotations
import time
from contextlib import contextmanager

class Telemetry:
    def __init__(self, db): self.db=db
    def emit(self, component,event,**kw): self.db.event(component,event,**kw)
    @contextmanager
    def span(self, component, stage, job_id=None, data=None):
        t=time.perf_counter();self.emit(component,'SPAN_START',job_id=job_id,stage=stage,data=data or {})
        try:
            yield
        except Exception as e:
            self.emit(component,'SPAN_ERROR',job_id=job_id,stage=stage,level='ERROR',data={'elapsed_ms':round((time.perf_counter()-t)*1000,2),'error':str(e)[:1000]});raise
        else:
            self.emit(component,'SPAN_END',job_id=job_id,stage=stage,data={'elapsed_ms':round((time.perf_counter()-t)*1000,2)})
