import json, re, sys
req=json.loads(sys.stdin.read() or '{}')
if req.get('action')!='check_text': raise SystemExit('ACTION_NOT_SUPPORTED')
text=str((req.get('payload') or {}).get('text',''))
known={'teh':'the','recieve':'receive','seperate':'separate','occured':'occurred','adress':'address','wierd':'weird'}
issues=[]
for match in re.finditer(r"\b[A-Za-z']+\b",text):
    word=match.group(0)
    replacement=known.get(word.lower())
    if replacement:
        issues.append({'word':word,'suggestion':replacement,'start':match.start(),'end':match.end()})
print(json.dumps({'issues':issues,'count':len(issues)}))
