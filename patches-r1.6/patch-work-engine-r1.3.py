from pathlib import Path
import sys
app=Path(sys.argv[1]); init=Path(sys.argv[2])
text=app.read_text(encoding='utf-8-sig'); init_text=init.read_text(encoding='utf-8-sig')
if "version':'R1.3'" in text and 'refreshSchedules' in text:
 print('WORK_ENGINE_PATCH=ALREADY_R1_3'); raise SystemExit(0)
if "version':'R1.1'" not in text and "version':'R1.2'" not in text: raise SystemExit('UNEXPECTED_WORK_ENGINE_VERSION')
needle="if u.path=='/api/status':return jsend(self,200,RUNTIME.status())"
route="if u.path=='/api/schedules':return jsend(self,200,{'schedules':RUNTIME.scheduler.list()})"
if route not in text:
 if needle not in text: raise SystemExit('STATUS_GET_ROUTE_NOT_FOUND')
 text=text.replace(needle,needle+'\n            '+route,1)
start=text.find('async function addSchedule()')
if start<0: raise SystemExit('ADD_SCHEDULE_FUNCTION_NOT_FOUND')
end=text.find('\nasync function',start+1)
if end<0: end=text.find('</script>',start+1)
if end<0: raise SystemExit('ADD_SCHEDULE_FUNCTION_END_NOT_FOUND')
new_js='''async function refreshSchedules(){let s=await api('/api/schedules');let rows=(s&&s.schedules)||[];$('schedules').innerHTML=rows.map(x=>`<tr data-schedule-id="${x.id}"><td>${x.name}</td><td>${x.schedule_type}:${x.schedule_value}</td><td>${new Date((x.next_run_at||0)*1000).toLocaleString()}</td></tr>`).join('');return rows}
async function addSchedule(){let created=await api('/api/schedules',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:'Service health every 15 minutes',kind:'service_health',payload:{recover:true},schedule_type:'interval',schedule_value:'900'})});let sid=created.schedule_id||'';for(let i=0;i<40;i++){let rows=await refreshSchedules();if(rows.some(x=>x.id===sid))return created;await new Promise(r=>setTimeout(r,100))}throw new Error('SCHEDULE_NOT_VISIBLE_AFTER_CREATE='+sid)}'''
text=text[:start]+new_js+text[end:]
old_tab="function tab(id){document.querySelectorAll('.panel').forEach(x=>x.classList.remove('active'));$(id).classList.add('active');refresh()}"
new_tab="function tab(id){document.querySelectorAll('.panel').forEach(x=>x.classList.remove('active'));$(id).classList.add('active');if(id==='schedule')refreshSchedules();else refresh()}"
if old_tab in text: text=text.replace(old_tab,new_tab,1)
elif new_tab not in text: raise SystemExit('TAB_FUNCTION_PATTERN_NOT_FOUND')
for a in ('R1.1','R1.2'):
 text=text.replace('Agape Work Engine '+a,'Agape Work Engine R1.3').replace("'version':'"+a+"'","'version':'R1.3'").replace("__version__ = '"+a+"'","__version__ = 'R1.3'")
 init_text=init_text.replace("__version__ = '"+a+"'","__version__ = 'R1.3'")
if '# AGAPE_R1_3_SCHEDULE_DECOUPLE_FIX' not in text: text=text.replace('from __future__ import annotations\n','from __future__ import annotations\n# AGAPE_R1_3_SCHEDULE_DECOUPLE_FIX\n',1)
req=["version':'R1.3'",'async function refreshSchedules()','SCHEDULE_NOT_VISIBLE_AFTER_CREATE',route]
miss=[x for x in req if x not in text]
if miss: raise SystemExit('WORK_ENGINE_R13_PATCH_INCOMPLETE='+','.join(miss))
if "__version__ = 'R1.3'" not in init_text: raise SystemExit('WORK_ENGINE_INIT_VERSION_BUMP_FAILED')
app.write_text(text,encoding='utf-8');init.write_text(init_text,encoding='utf-8')
print('WORK_ENGINE_PATCH=PASS')
print('WORK_ENGINE_VERSION=R1.3')
print('SCHEDULE_GET_ENDPOINT=PASS')
print('SCHEDULE_RENDER_DECOUPLED_FROM_STATUS=PASS')