import json, sys
req=json.loads(sys.stdin.read() or '{}')
if req.get('action')!='format_text':
    raise SystemExit('ACTION_NOT_SUPPORTED')
text=str((req.get('payload') or {}).get('text',''))
lines=[line.rstrip() for line in text.replace('\r\n','\n').replace('\r','\n').split('\n')]
while lines and lines[-1]=='': lines.pop()
out='\n'.join(lines)+'\n'
print(json.dumps({'text':out,'changed':out!=text}))
