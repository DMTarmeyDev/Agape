from __future__ import annotations
import ast
from pathlib import Path

def review_python(path):
    p=Path(path).expanduser().resolve(); findings=[]
    if not p.is_file(): return {'ok':False,'path':str(p),'findings':[{'kind':'file_not_found'}]}
    try: tree=ast.parse(p.read_text(encoding='utf-8-sig'),filename=str(p))
    except SyntaxError as exc: return {'ok':False,'path':str(p),'findings':[{'kind':'syntax_error','line':exc.lineno or 0,'detail':exc.msg}]}
    for node in ast.walk(tree):
        if isinstance(node,ast.Call):
            fn=node.func
            name=fn.id if isinstance(fn,ast.Name) else (fn.attr if isinstance(fn,ast.Attribute) else '')
            if name in {'eval','exec'}: findings.append({'kind':name,'line':getattr(node,'lineno',0)})
            shell_true=any(k.arg=='shell' and isinstance(k.value,ast.Constant) and k.value.value is True for k in node.keywords)
            if shell_true: findings.append({'kind':'shell_true','line':getattr(node,'lineno',0)})
    return {'ok':not findings,'path':str(p),'findings':findings}
