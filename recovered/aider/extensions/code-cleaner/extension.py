import json, sys
req=json.loads(sys.stdin.read() or '{}')
if req.get('action')!='inspect_text': raise SystemExit('ACTION_NOT_SUPPORTED')
text=str((req.get('payload') or {}).get('text',''))
issues=[]
for no,line in enumerate(text.replace('\r\n','\n').replace('\r','\n').split('\n'),1):
    if line.endswith(' '): issues.append({'line':no,'kind':'trailing-whitespace'})
    if '\t' in line: issues.append({'line':no,'kind':'tab-character'})
    if len(line)>120: issues.append({'line':no,'kind':'long-line','length':len(line)})
print(json.dumps({'issues':issues,'count':len(issues)}))
