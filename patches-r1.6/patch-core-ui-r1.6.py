from pathlib import Path
import re, sys
p=Path(sys.argv[1])
text=p.read_text(encoding='utf-8-sig')
marker='<!-- AGAPE_R16_CORE_UI_COMPAT_BEGIN -->'
required=('data-page="chat"','data-page="settings"','id="workspace-manage-projects"','id="project-instructions-text"')
missing=[x for x in required if x not in text]
if missing: raise SystemExit('R8_NATIVE_UI_MARKERS_MISSING='+','.join(missing))

# R1.6: protect direct lookup.onclick assignments anywhere in compact scripts.
patterns=[
 (re.compile(r"\$\((?P<q>['\"])(?P<id>[^'\"]+)(?P=q)\)\s*\.onclick\s*="),lambda m:"($(%s%s%s)||{}).onclick="%(m.group('q'),m.group('id'),m.group('q'))),
 (re.compile(r"document\.getElementById\((?P<q>['\"])(?P<id>[^'\"]+)(?P=q)\)\s*\.onclick\s*="),lambda m:"(document.getElementById(%s%s%s)||{}).onclick="%(m.group('q'),m.group('id'),m.group('q'))),
 (re.compile(r"document\.querySelector\((?P<q>['\"])(?P<sel>[^'\"]+)(?P=q)\)\s*\.onclick\s*="),lambda m:"(document.querySelector(%s%s%s)||{}).onclick="%(m.group('q'),m.group('sel'),m.group('q'))),
]
counts=[]
for pat,fn in patterns:
 text,n=pat.subn(fn,text);counts.append(n)
# Also guard simple cached-node variable assignments at statement starts.
var_pat=re.compile(r'(?m)(?P<i>(?:^|[;{}])[ \t]*)(?P<v>[A-Za-z_$][A-Za-z0-9_$]*)\s*\.onclick\s*=')
def vr(m):
 v=m.group('v')
 return m.group(0) if v in ('this','window','document') else f"{m.group('i')}if({v}) {v}.onclick="
text,var_count=var_pat.subn(vr,text)
# Direct lookup.onclick must be gone.
checks=[r"\$\(['\"][^'\"]+['\"]\)\s*\.onclick\s*=",r"document\.getElementById\(['\"][^'\"]+['\"]\)\s*\.onclick\s*=",r"document\.querySelector\(['\"][^'\"]+['\"]\)\s*\.onclick\s*="]
left=sum(len(re.findall(x,text)) for x in checks)
if left: raise SystemExit('UNSAFE_DIRECT_ONCLICK_REMAINS='+str(left))
if marker not in text:
 pos=text.lower().rfind('</body>')
 if pos<0: raise SystemExit('CORE_UI_BODY_END_NOT_FOUND')
 note='\n'+marker+'\n<!-- Native R8 navigation retained; null-safe DOM onclick compatibility guard R1.6. -->\n<!-- AGAPE_R16_CORE_UI_COMPAT_END -->\n'
 text=text[:pos]+note+text[pos:]
p.write_text(text,encoding='utf-8')
print('CORE_UI_PATCH=PASS')
print('CORE_UI_DIRECT_DOLLAR_GUARDS='+str(counts[0]))
print('CORE_UI_GETELEMENT_GUARDS='+str(counts[1]))
print('CORE_UI_QUERYSELECTOR_GUARDS='+str(counts[2]))
print('CORE_UI_VARIABLE_GUARDS='+str(var_count))
print('CORE_UI_UNSAFE_DIRECT_ONCLICK=0')
print('CORE_UI_NATIVE_NAV=PROJECT_WORKSPACE_SETTINGS')