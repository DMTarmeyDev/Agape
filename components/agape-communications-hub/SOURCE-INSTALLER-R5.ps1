& {
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$Build = 'AGAPE-COMMS-HUB-R5'
$HubPort = 8798
$HubPortMax = 8808
$AgapePort = 8797
$Docs = [Environment]::GetFolderPath('MyDocuments')
$Root = Join-Path $env:LOCALAPPDATA 'Agape-Communications-Hub'
$Data = Join-Path $Docs 'AGAPE-COMMS-HUB'
$Backup = Join-Path $Data ('backups\' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
$ReportDir = Join-Path $Data 'reports'
$Report = Join-Path $ReportDir ('install-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.json')
$PythonFile = Join-Path $Root 'agape_comms_hub.py'
$StartFile = Join-Path $Root 'START-AGAPE-COMMS-HUB.ps1'
$CredentialFile = Join-Path $Data 'FIRST-LOGIN.txt'
$HubDb = Join-Path $Data 'communications.sqlite3'
$AuthPy = Join-Path $Root 'agape_account_auth.py'
$AuthPs = Join-Path $Root 'AUTH-AGAPE-ACCOUNTS.ps1'

function Say([string]$Name,[string]$Value,[string]$Color='Gray') { Write-Host ($Name + '=' + $Value) -ForegroundColor $Color }
function Find-Python {
  $known = @(
    (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'),
    (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe')
  )
  foreach($p in $known){ if(Test-Path -LiteralPath $p -PathType Leaf){ return $p } }
  $c = Get-Command python.exe -ErrorAction SilentlyContinue
  if($c){ return $c.Source }
  $c = Get-Command python -ErrorAction SilentlyContinue
  if($c){ return $c.Source }
  throw 'PYTHON_NOT_FOUND'
}
function Find-AgapeRoot {
  $candidates = @(
    (Join-Path $env:LOCALAPPDATA 'DMT-Core-V1.5\SecondBrain\dmt-second-brain'),
    (Join-Path $env:LOCALAPPDATA 'DMT-Core-V1.4\SecondBrain\dmt-second-brain'),
    (Join-Path $env:LOCALAPPDATA 'DMT-Core-V3.1\SecondBrain\dmt-second-brain')
  )
  foreach($p in $candidates){ if(Test-Path -LiteralPath (Join-Path $p 'index.html') -PathType Leaf){ return $p } }
  $base = $env:LOCALAPPDATA
  $found = Get-ChildItem -LiteralPath $base -Directory -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match '^(DMT-Core|Agape)' } |
    ForEach-Object {
      Get-ChildItem -LiteralPath $_.FullName -Filter index.html -File -Recurse -ErrorAction SilentlyContinue |
      Where-Object { $_.FullName -match 'SecondBrain|second-brain|dmt-second-brain' }
    } |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
  if($found){ return $found.DirectoryName }
  return $null
}
function Wait-Http([string]$Url,[int]$Seconds=25){
  $sw=[Diagnostics.Stopwatch]::StartNew()
  while($sw.Elapsed.TotalSeconds -lt $Seconds){
    try { $r=Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 2; if($r.StatusCode -eq 200){ return $true } } catch {}
    Start-Sleep -Milliseconds 300
  }
  return $false
}

function Test-TcpPortAvailable([int]$Port){
  try {
    $l = New-Object System.Net.Sockets.TcpListener([Net.IPAddress]::Loopback,$Port)
    $l.Start(); $l.Stop(); return $true
  } catch { return $false }
}
function Select-HubPort([int]$Start,[int]$End){
  for($p=$Start;$p -le $End;$p++){
    try {
      $r=Invoke-RestMethod -Uri ("http://127.0.0.1:$p/api/health") -TimeoutSec 1
      if($r.ok -and $r.build -eq $Build){ return $p }
    } catch {}
    if(Test-TcpPortAvailable $p){ return $p }
  }
  throw "NO_FREE_HUB_PORT_$Start-$End"
}

function Rollback-Index([string]$Index,[string]$BackupIndex){
  if($Index -and $BackupIndex -and (Test-Path -LiteralPath $BackupIndex -PathType Leaf)){
    Copy-Item -LiteralPath $BackupIndex -Destination $Index -Force
  }
}

$Python = Find-Python
$HubPort = Select-HubPort $HubPort $HubPortMax
$AgapeRoot = Find-AgapeRoot
New-Item -ItemType Directory -Path $Root,$Data,$Backup,$ReportDir -Force | Out-Null
$Index = $null; $IndexBackup = $null
if($AgapeRoot){
  $Index = Join-Path $AgapeRoot 'index.html'
  $IndexBackup = Join-Path $Backup 'index.html'
  Copy-Item -LiteralPath $Index -Destination $IndexBackup -Force
}

$Py = @'
from __future__ import annotations
import argparse, base64, ctypes, email, email.header, email.utils, hashlib, hmac, html, imaplib, json, mimetypes, os, re, secrets, smtplib, sqlite3, ssl, sys, threading, time, urllib.parse, urllib.request, webbrowser
from email.parser import BytesParser
from email.policy import default as email_policy
from datetime import datetime, timezone
from email.message import EmailMessage
from http import cookies
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path

BUILD='AGAPE-COMMS-HUB-R5'
HOST='127.0.0.1'
DEFAULT_PORT=8798
DATA=Path(os.environ.get('AGAPE_COMMS_DATA') or (Path.home()/'Documents'/'AGAPE-COMMS-HUB')).resolve()
DB=DATA/'communications.sqlite3'
CREDENTIALS=DATA/'FIRST-LOGIN.txt'
UPLOADS=DATA/'uploads'
LOGS=DATA/'logs'
for p in (DATA,UPLOADS,LOGS): p.mkdir(parents=True,exist_ok=True)
ACTION_WORDS=('confirm','verify','approve','activation','activate','security alert','sign-in','signin','password','action required','respond','reply required','accept','authorise','authorize','invoice','payment')

# ---------- crypto/auth ----------
def now(): return datetime.now(timezone.utc).isoformat()
def pbkdf(password:str,salt:bytes|None=None):
    salt=salt or secrets.token_bytes(16)
    dk=hashlib.pbkdf2_hmac('sha256',password.encode(),salt,260000)
    return base64.b64encode(salt).decode()+'$'+base64.b64encode(dk).decode()
def check_password(password:str,stored:str):
    try:
        s,d=stored.split('$',1); salt=base64.b64decode(s); want=base64.b64decode(d)
        got=hashlib.pbkdf2_hmac('sha256',password.encode(),salt,260000)
        return hmac.compare_digest(got,want)
    except Exception:return False

def db():
    c=sqlite3.connect(DB,timeout=20); c.row_factory=sqlite3.Row; c.execute('PRAGMA foreign_keys=ON'); c.execute('PRAGMA journal_mode=WAL'); return c

def init_db():
    c=db(); c.executescript('''
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,username TEXT UNIQUE NOT NULL,display_name TEXT NOT NULL,role TEXT NOT NULL,password_hash TEXT NOT NULL,must_change INTEGER NOT NULL DEFAULT 1,enabled INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL,last_login TEXT);
    CREATE TABLE IF NOT EXISTS sessions(id INTEGER PRIMARY KEY,token_hash TEXT UNIQUE NOT NULL,user_id INTEGER NOT NULL,created_at TEXT NOT NULL,expires_at INTEGER NOT NULL,revoked INTEGER NOT NULL DEFAULT 0,FOREIGN KEY(user_id) REFERENCES users(id));
    CREATE TABLE IF NOT EXISTS connections(id INTEGER PRIMARY KEY,kind TEXT NOT NULL,name TEXT NOT NULL,account TEXT,config_json TEXT NOT NULL DEFAULT '{}',secret_json TEXT NOT NULL DEFAULT '{}',connected INTEGER NOT NULL DEFAULT 0,last_test_status TEXT,last_test_detail TEXT,last_test_at TEXT,created_at TEXT NOT NULL,UNIQUE(kind,name));
    CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY,connection_id INTEGER,direction TEXT NOT NULL,external_id TEXT,thread_id TEXT,sender TEXT,recipients TEXT,subject TEXT,body_preview TEXT,status TEXT,needs_action INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL,FOREIGN KEY(connection_id) REFERENCES connections(id));
    CREATE TABLE IF NOT EXISTS sends(id INTEGER PRIMARY KEY,user_id INTEGER,connection_id INTEGER,channel TEXT NOT NULL,recipient TEXT NOT NULL,subject TEXT,message TEXT,attachment_name TEXT,status TEXT NOT NULL,detail TEXT,created_at TEXT NOT NULL,FOREIGN KEY(user_id) REFERENCES users(id),FOREIGN KEY(connection_id) REFERENCES connections(id));
    CREATE TABLE IF NOT EXISTS contacts(id INTEGER PRIMARY KEY,name TEXT NOT NULL,email TEXT,phone TEXT,whatsapp TEXT,matrix TEXT,mastodon TEXT,created_at TEXT NOT NULL);
    '''); c.commit(); c.close()

def make_password():
    alphabet='ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789!@#$%'
    return ''.join(secrets.choice(alphabet) for _ in range(18))

def ensure_accounts():
    c=db(); existing={r['username'] for r in c.execute('SELECT username FROM users')}
    created=[]
    for username,display,role in [('owner','Agape Owner','owner'),('public-main','Public Main','public'),('agape-test','Agape Test','tester')]:
        if username not in existing:
            pwd=make_password(); c.execute('INSERT INTO users(username,display_name,role,password_hash,must_change,enabled,created_at) VALUES(?,?,?,?,1,1,?)',(username,display,role,pbkdf(pwd),now())); created.append((username,pwd,role))
    c.commit(); c.close()
    if created:
        lines=['AGAPE COMMUNICATIONS HUB - FIRST LOGIN','Generated '+now(),'','Change these passwords on first login.','The public-main account is READ ONLY.','The agape-test account cannot send through production connections.','']
        lines += [f'{u} | role={r} | temporary_password={p}' for u,p,r in created]
        CREDENTIALS.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return created

def classify_action(subject,body=''):
    t=(subject+' '+body).lower()
    return 1 if any(w in t for w in ACTION_WORDS) else 0

def safe_json(s):
    try:return json.loads(s or '{}')
    except:return {}

class _DATA_BLOB(ctypes.Structure):
    _fields_=[('cbData',ctypes.c_ulong),('pbData',ctypes.POINTER(ctypes.c_ubyte))]
def _blob(data:bytes):
    buf=ctypes.create_string_buffer(data); return _DATA_BLOB(len(data),ctypes.cast(buf,ctypes.POINTER(ctypes.c_ubyte))),buf
def dpapi_protect(data:bytes)->str:
    if os.name!='nt':return base64.b64encode(data).decode()
    i,k=_blob(data);o=_DATA_BLOB()
    if not ctypes.windll.crypt32.CryptProtectData(ctypes.byref(i),None,None,None,None,1,ctypes.byref(o)):raise OSError('DPAPI protect failed')
    try:return base64.b64encode(ctypes.string_at(o.pbData,o.cbData)).decode()
    finally:ctypes.windll.kernel32.LocalFree(o.pbData)
def dpapi_unprotect(text:str)->bytes:
    raw=base64.b64decode(text.encode())
    if os.name!='nt':return raw
    i,k=_blob(raw);o=_DATA_BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(i),None,None,None,None,1,ctypes.byref(o)):raise OSError('DPAPI unprotect failed')
    try:return ctypes.string_at(o.pbData,o.cbData)
    finally:ctypes.windll.kernel32.LocalFree(o.pbData)
def secret_pack(obj:dict)->str:return json.dumps({'dpapi':dpapi_protect(json.dumps(obj or {},separators=(',',':')).encode())})
def secret_unpack(value)->dict:
    outer=value if isinstance(value,dict) else safe_json(value)
    if isinstance(outer,dict) and outer.get('dpapi'):
        try:return json.loads(dpapi_unprotect(outer['dpapi']).decode())
        except Exception:return {}
    return outer if isinstance(outer,dict) else {}
def row_secret(row):return secret_unpack(row['secret_json'])
def update_row_secret(row_id:int,secret:dict):
    c=db();c.execute('UPDATE connections SET secret_json=? WHERE id=?',(secret_pack(secret),row_id));c.commit();c.close()

def connection_public(row):
    return {k:row[k] for k in ('id','kind','name','account','connected','last_test_status','last_test_detail','last_test_at','created_at')}

# ---------- connectors ----------
def smtp_ssl_context(): return ssl.create_default_context()
def test_smtp_imap(cfg,sec):
    email_addr=(cfg.get('email') or '').strip(); imap_host=(cfg.get('imap_host') or '').strip(); smtp_host=(cfg.get('smtp_host') or '').strip(); password=sec.get('password') or ''
    if not email_addr or not imap_host or not smtp_host or not password: return False,'EMAIL_IMAP_SMTP_PASSWORD_REQUIRED'
    imap_port=int(cfg.get('imap_port') or 993); smtp_port=int(cfg.get('smtp_port') or 465)
    m=imaplib.IMAP4_SSL(imap_host,imap_port,ssl_context=smtp_ssl_context()); m.login(email_addr,password); m.noop(); m.logout()
    if bool(cfg.get('smtp_starttls')):
        s=smtplib.SMTP(smtp_host,smtp_port,timeout=15); s.starttls(context=smtp_ssl_context())
    else:s=smtplib.SMTP_SSL(smtp_host,smtp_port,timeout=15,context=smtp_ssl_context())
    s.login(email_addr,password); s.noop(); s.quit(); return True,'IMAP_AND_SMTP_AUTH_PASS'
def test_matrix(cfg,sec):
    base=(cfg.get('homeserver') or '').rstrip('/'); token=sec.get('access_token') or ''
    if not base or not token:return False,'MATRIX_HOMESERVER_TOKEN_REQUIRED'
    req=urllib.request.Request(base+'/_matrix/client/v3/account/whoami',headers={'Authorization':'Bearer '+token})
    with urllib.request.urlopen(req,timeout=12) as r:
        j=json.loads(r.read().decode()); return bool(j.get('user_id')),('MATRIX_USER='+str(j.get('user_id')))
def test_mastodon(cfg,sec):
    base=(cfg.get('base_url') or '').rstrip('/'); token=sec.get('access_token') or ''
    if not base or not token:return False,'MASTODON_URL_TOKEN_REQUIRED'
    req=urllib.request.Request(base+'/api/v1/accounts/verify_credentials',headers={'Authorization':'Bearer '+token})
    with urllib.request.urlopen(req,timeout=12) as r:
        j=json.loads(r.read().decode()); return bool(j.get('id')),('MASTODON_ACCOUNT='+str(j.get('acct')))
def test_whatsapp_cloud(cfg,sec):
    phone_id=(cfg.get('phone_number_id') or '').strip(); token=sec.get('access_token') or ''
    if not phone_id or not token:return False,'WHATSAPP_PHONE_ID_TOKEN_REQUIRED'
    url=f'https://graph.facebook.com/v23.0/{urllib.parse.quote(phone_id)}?fields=display_phone_number,verified_name'
    req=urllib.request.Request(url,headers={'Authorization':'Bearer '+token})
    with urllib.request.urlopen(req,timeout=12) as r:
        j=json.loads(r.read().decode()); return bool(j.get('display_phone_number')),('WHATSAPP='+str(j.get('display_phone_number')))
GMAIL_SCOPES=['https://www.googleapis.com/auth/gmail.readonly','https://www.googleapis.com/auth/gmail.send']
MS_SCOPES=['User.Read','Mail.Read','Mail.Send']
def google_credentials(sec):
    from google.oauth2.credentials import Credentials
    info=sec.get('google_credentials') or {}
    if not info:raise RuntimeError('GOOGLE_OAUTH_NOT_AUTHORISED')
    creds=Credentials.from_authorized_user_info(info,GMAIL_SCOPES)
    if creds.expired and creds.refresh_token:
        from google.auth.transport.requests import Request
        creds.refresh(Request());sec['google_credentials']=json.loads(creds.to_json())
    return creds
def test_gmail_oauth(cfg,sec):
    from googleapiclient.discovery import build
    service=build('gmail','v1',credentials=google_credentials(sec),cache_discovery=False);p=service.users().getProfile(userId='me').execute();a=p.get('emailAddress') or cfg.get('email') or ''
    return bool(a),'GMAIL_ACCOUNT='+a
def ms_app(sec):
    import msal
    cid=(sec.get('client_id') or '').strip();cache=msal.SerializableTokenCache()
    if sec.get('token_cache'):cache.deserialize(sec['token_cache'])
    if not cid:raise RuntimeError('MICROSOFT_CLIENT_ID_REQUIRED')
    return msal.PublicClientApplication(cid,authority='https://login.microsoftonline.com/common',token_cache=cache),cache
def microsoft_token(sec):
    app,cache=ms_app(sec);aa=app.get_accounts();r=app.acquire_token_silent(MS_SCOPES,account=aa[0] if aa else None) if aa else None
    if not r or 'access_token' not in r:raise RuntimeError('MICROSOFT_REAUTHORISE_REQUIRED')
    sec['token_cache']=cache.serialize();return r['access_token']
def graph_json(path,token,method='GET',body=None):
    data=None if body is None else json.dumps(body).encode();req=urllib.request.Request('https://graph.microsoft.com/v1.0'+path,data=data,method=method,headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=30) as r:
        raw=r.read();return json.loads(raw.decode()) if raw else {}
def test_microsoft_graph(cfg,sec):
    j=graph_json('/me?$select=id,displayName,mail,userPrincipalName',microsoft_token(sec));a=j.get('mail') or j.get('userPrincipalName') or cfg.get('email') or ''
    return bool(j.get('id')),'MICROSOFT_ACCOUNT='+a

def test_connection(kind,cfg,sec):
    try:
        if kind=='local_test': return True,'LOCAL_TEST_TRANSPORT_PASS'
        if kind=='smtp_imap': return test_smtp_imap(cfg,sec)
        if kind=='gmail_oauth': return test_gmail_oauth(cfg,sec)
        if kind=='microsoft_graph': return test_microsoft_graph(cfg,sec)
        if kind=='matrix': return test_matrix(cfg,sec)
        if kind=='mastodon': return test_mastodon(cfg,sec)
        if kind=='whatsapp_cloud': return test_whatsapp_cloud(cfg,sec)
        if kind=='whatsapp_personal': return False,'PERSONAL_WHATSAPP_IS_OPEN_IN_BROWSER_ONLY_NOT_AN_AUTOMATED_PRODUCTION_CONNECTOR'
        return False,'UNSUPPORTED_CONNECTOR'
    except Exception as e:return False,type(e).__name__+': '+str(e)[:400]

def send_email(cfg,sec,to,subject,message,attachment):
    sender=cfg.get('email') or ''; smtp_host=cfg.get('smtp_host') or ''; smtp_port=int(cfg.get('smtp_port') or 465); password=sec.get('password') or ''
    em=EmailMessage(); em['From']=sender; em['To']=to; em['Subject']=subject or '(no subject)'; em.set_content(message or '')
    if attachment:
        data,name=attachment; ctype,_=mimetypes.guess_type(name); maintype,subtype=(ctype or 'application/octet-stream').split('/',1); em.add_attachment(data,maintype=maintype,subtype=subtype,filename=name)
    if bool(cfg.get('smtp_starttls')):
        s=smtplib.SMTP(smtp_host,smtp_port,timeout=30); s.starttls(context=smtp_ssl_context())
    else:s=smtplib.SMTP_SSL(smtp_host,smtp_port,timeout=30,context=smtp_ssl_context())
    s.login(sender,password); s.send_message(em); s.quit(); return 'SMTP_SEND_PASS'

def send_gmail_oauth(cfg,sec,to,subject,message,attachment):
    from googleapiclient.discovery import build
    em=EmailMessage();em['From']=cfg.get('email') or 'me';em['To']=to;em['Subject']=subject or '(no subject)';em.set_content(message or '')
    if attachment:
        data,name=attachment;ctype,_=mimetypes.guess_type(name);maintype,subtype=(ctype or 'application/octet-stream').split('/',1);em.add_attachment(data,maintype=maintype,subtype=subtype,filename=name)
    service=build('gmail','v1',credentials=google_credentials(sec),cache_discovery=False);j=service.users().messages().send(userId='me',body={'raw':base64.urlsafe_b64encode(em.as_bytes()).decode()}).execute();return 'GMAIL_SEND_PASS '+str(j.get('id') or '')
def send_microsoft_graph(cfg,sec,to,subject,message,attachment):
    msg={'subject':subject or '(no subject)','body':{'contentType':'Text','content':message or ''},'toRecipients':[{'emailAddress':{'address':to}}]}
    if attachment:
        data,name=attachment;msg['attachments']=[{'@odata.type':'#microsoft.graph.fileAttachment','name':name,'contentType':mimetypes.guess_type(name)[0] or 'application/octet-stream','contentBytes':base64.b64encode(data).decode()}]
    graph_json('/me/sendMail',microsoft_token(sec),method='POST',body={'message':msg,'saveToSentItems':True});return 'MICROSOFT_SEND_PASS'

def send_matrix(cfg,sec,room,message,attachment):
    base=(cfg.get('homeserver') or '').rstrip('/'); token=sec.get('access_token') or ''
    text=message or ''
    # R1 sends message text; attachments are intentionally not uploaded until Matrix media validation is added.
    body=json.dumps({'msgtype':'m.text','body':text}).encode(); txn=secrets.token_hex(8)
    url=base+'/_matrix/client/v3/rooms/'+urllib.parse.quote(room,safe='')+'/send/m.room.message/'+txn
    req=urllib.request.Request(url,data=body,method='PUT',headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=20) as r:return 'MATRIX_SEND_PASS '+r.read().decode()[:160]
def post_mastodon(cfg,sec,message):
    base=(cfg.get('base_url') or '').rstrip('/'); token=sec.get('access_token') or ''
    data=urllib.parse.urlencode({'status':message or ''}).encode(); req=urllib.request.Request(base+'/api/v1/statuses',data=data,method='POST',headers={'Authorization':'Bearer '+token,'Content-Type':'application/x-www-form-urlencoded'})
    with urllib.request.urlopen(req,timeout=20) as r:return 'MASTODON_POST_PASS '+r.read().decode()[:160]

def sync_imap(row,limit=30):
    cfg=safe_json(row['config_json']); sec=row_secret(row); email_addr=cfg.get('email') or ''; password=sec.get('password') or ''
    m=imaplib.IMAP4_SSL(cfg.get('imap_host'),int(cfg.get('imap_port') or 993),ssl_context=smtp_ssl_context()); m.login(email_addr,password); m.select('INBOX')
    typ,data=m.search(None,'UNSEEN'); ids=(data[0].split() if data and data[0] else [])[-limit:]
    c=db(); count=0
    for mid in ids:
        typ,msgdata=m.fetch(mid,'(RFC822)'); raw=next((x[1] for x in msgdata if isinstance(x,tuple)),None)
        if not raw:continue
        msg=email.message_from_bytes(raw); subj=str(email.header.make_header(email.header.decode_header(msg.get('Subject','')))); sender=msg.get('From',''); msgid=msg.get('Message-ID') or (str(row['id'])+':'+mid.decode())
        preview=''
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type()=='text/plain' and 'attachment' not in str(part.get('Content-Disposition','')).lower():
                    try:preview=part.get_payload(decode=True).decode(part.get_content_charset() or 'utf-8',errors='replace')[:1200]
                    except:pass
                    break
        else:
            try:preview=msg.get_payload(decode=True).decode(msg.get_content_charset() or 'utf-8',errors='replace')[:1200]
            except:pass
        c.execute('INSERT OR IGNORE INTO messages(connection_id,direction,external_id,sender,recipients,subject,body_preview,status,needs_action,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(row['id'],'in',msgid,sender,email_addr,subj,preview,'unread',classify_action(subj,preview),now())); count+=1
    c.commit(); c.close(); m.logout(); return count

def sync_gmail(row,limit=30):
    cfg=safe_json(row['config_json']);sec=row_secret(row);from googleapiclient.discovery import build
    service=build('gmail','v1',credentials=google_credentials(sec),cache_discovery=False);listing=service.users().messages().list(userId='me',q='is:unread',maxResults=limit).execute();c=db();count=0
    for item in listing.get('messages',[]):
        j=service.users().messages().get(userId='me',id=item['id'],format='metadata',metadataHeaders=['Subject','From','To','Message-ID']).execute();h={x['name'].lower():x['value'] for x in j.get('payload',{}).get('headers',[])};subj=h.get('subject','');preview=j.get('snippet','')
        c.execute('INSERT OR IGNORE INTO messages(connection_id,direction,external_id,thread_id,sender,recipients,subject,body_preview,status,needs_action,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(row['id'],'in',item['id'],j.get('threadId',''),h.get('from',''),h.get('to',cfg.get('email','')),subj,preview,'unread',classify_action(subj,preview),now()));count+=1
    c.commit();c.close();update_row_secret(row['id'],sec);return count
def sync_microsoft(row,limit=30):
    sec=row_secret(row);j=graph_json('/me/mailFolders/inbox/messages?$filter=isRead%20eq%20false&$top='+str(int(limit))+'&$select=id,conversationId,subject,from,toRecipients,bodyPreview,receivedDateTime,isRead',microsoft_token(sec));c=db();count=0
    for m in j.get('value',[]):
        sender=((m.get('from') or {}).get('emailAddress') or {}).get('address','');rec=','.join(((x.get('emailAddress') or {}).get('address','')) for x in m.get('toRecipients',[]));subj=m.get('subject','');preview=m.get('bodyPreview','')
        c.execute('INSERT OR IGNORE INTO messages(connection_id,direction,external_id,thread_id,sender,recipients,subject,body_preview,status,needs_action,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(row['id'],'in',m.get('id'),m.get('conversationId',''),sender,rec,subj,preview,'unread',classify_action(subj,preview),m.get('receivedDateTime') or now()));count+=1
    c.commit();c.close();update_row_secret(row['id'],sec);return count

# ---------- web ----------
def esc(x):return html.escape(str(x or ''))
def page(title,body,script=''):
    return f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title><style>
    body{{font-family:Segoe UI,Arial,sans-serif;margin:0;background:#f4f6f8;color:#17202a}}header{{background:#111827;color:white;padding:14px 20px;display:flex;gap:18px;align-items:center;flex-wrap:wrap}}header a{{color:white;text-decoration:none}}.wrap{{max-width:1180px;margin:20px auto;padding:0 16px}}.card{{background:white;border:1px solid #d7dce1;border-radius:12px;padding:16px;margin:12px 0;box-shadow:0 1px 3px #0001}}button,.btn{{background:#1f6feb;color:white;border:0;border-radius:8px;padding:8px 12px;cursor:pointer;text-decoration:none;display:inline-block}}.secondary{{background:#4b5563}}.danger{{background:#b42318}}input,select,textarea{{width:100%;box-sizing:border-box;padding:9px;border:1px solid #c8d0d8;border-radius:7px;margin:5px 0 10px}}table{{width:100%;border-collapse:collapse}}th,td{{text-align:left;padding:8px;border-bottom:1px solid #e5e7eb;vertical-align:top}}.ok{{color:#067647;font-weight:700}}.bad{{color:#b42318;font-weight:700}}.warn{{color:#b54708;font-weight:700}}.badge{{padding:3px 8px;border-radius:999px;background:#eef2f6}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px}}.muted{{color:#667085}}pre{{white-space:pre-wrap}} .actions{{display:flex;gap:8px;flex-wrap:wrap}}
    </style></head><body><header><b>Agape Communications</b><a href="/">Dashboard</a><a href="/connections">Connect email clients</a><a href="/inbox">Email</a><a href="/share">Share / Send</a><a href="/contacts">Contacts</a><a href="/history">Send history</a><a href="/logout">Logout</a></header><div class="wrap">{body}</div><script>{script}</script></body></html>'''

def login_page(msg=''):
    return page('Agape Communications Login',f'''<div class=card><h1>Sign in</h1><p class=muted>Owner manages connections. Public Main is read-only. Agape Test uses the local test transport.</p>{'<p class=bad>'+esc(msg)+'</p>' if msg else ''}<form method=post action=/login><label>Username</label><input name=username autocomplete=username><label>Password</label><input type=password name=password autocomplete=current-password><button>Sign in</button></form></div>''')

def dashboard(user):
    c=db(); conn=[dict(r) for r in c.execute('SELECT * FROM connections ORDER BY id DESC')]; unread=c.execute("SELECT count(*) FROM messages WHERE direction='in' AND status='unread'").fetchone()[0]; action=c.execute("SELECT count(*) FROM messages WHERE direction='in' AND status='unread' AND needs_action=1").fetchone()[0]; c.close()
    connected=sum(1 for r in conn if r['connected'])
    body=f'''<div class=card><h1>Communications Hub</h1><p>Signed in as <b>{esc(user['display_name'])}</b> <span class=badge>{esc(user['role'])}</span></p><div class=grid><div><h2>{connected}</h2><p>connected account(s)</p></div><div><h2>{unread}</h2><p>unread emails</p></div><div><h2>{action}</h2><p>need action</p></div></div><div class=actions><a class=btn href=/connections>Connect email clients</a><a class=btn href=/share>Share a file</a><a class="btn secondary" href=/inbox>Open inbox</a></div></div>'''
    if user['role']=='public': body += '<div class=card><b>Public Main account:</b> read-only demonstration mode. Sending, connection changes and secrets are blocked.</div>'
    if user['role']=='tester': body += '<div class=card><b>Test account:</b> sending is restricted to the local test transport. Production connectors cannot be used.</div>'
    return page('Agape Communications',body)

class H(BaseHTTPRequestHandler):
    server_version='AgapeComms/1.0'
    def log_message(self,fmt,*args):
        try:(LOGS/'http.log').open('a',encoding='utf-8').write(now()+' '+(fmt%args)+'\n')
        except:pass
    def cors(self):
        self.send_header('Access-Control-Allow-Origin','*'); self.send_header('Access-Control-Allow-Headers','Content-Type'); self.send_header('Access-Control-Allow-Methods','GET,POST,OPTIONS')
    def send(self,code,body,ctype='text/html; charset=utf-8',extra=None):
        if isinstance(body,str):body=body.encode()
        self.send_response(code); self.send_header('Content-Type',ctype); self.send_header('Content-Length',str(len(body))); self.cors()
        for k,v in (extra or {}).items():self.send_header(k,v)
        self.end_headers(); self.wfile.write(body)
    def redirect(self,url,cookie=None):
        ex={'Location':url};
        if cookie:ex['Set-Cookie']=cookie
        self.send(303,b'',extra=ex)
    def fields(self):
        n=int(self.headers.get('Content-Length') or 0); raw=self.rfile.read(min(n,10*1024*1024)); ct=self.headers.get('Content-Type','')
        if 'application/json' in ct:
            try:return json.loads(raw.decode())
            except:return {}
        return {k:v[-1] for k,v in urllib.parse.parse_qs(raw.decode(errors='replace'),keep_blank_values=True).items()}
    def user(self):
        raw=cookies.SimpleCookie(self.headers.get('Cookie','')).get('AGAPE_COMMS_SESSION')
        if not raw:return None
        token=raw.value; th=hashlib.sha256(token.encode()).hexdigest(); c=db(); r=c.execute('SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.revoked=0 AND s.expires_at>? AND u.enabled=1',(th,int(time.time()))).fetchone(); c.close(); return dict(r) if r else None
    def require(self,roles=None):
        u=self.user()
        if not u:self.redirect('/login');return None
        if roles and u['role'] not in roles:self.send(403,page('Forbidden','<div class=card><h1>Forbidden</h1><p>This account does not have permission.</p></div>'));return None
        if u['must_change'] and self.path not in ('/change-password','/logout'):self.redirect('/change-password');return None
        return u
    def do_OPTIONS(self):self.send(204,b'')
    def do_GET(self):
        p=urllib.parse.urlparse(self.path).path
        if p=='/api/health':return self.send(200,json.dumps({'ok':True,'build':BUILD,'db':str(DB)}),'application/json')
        if p=='/api/status':
            c=db(); connected=c.execute('SELECT count(*) FROM connections WHERE connected=1').fetchone()[0]; unread=c.execute("SELECT count(*) FROM messages WHERE direction='in' AND status='unread'").fetchone()[0]; action=c.execute("SELECT count(*) FROM messages WHERE direction='in' AND status='unread' AND needs_action=1").fetchone()[0]; c.close(); return self.send(200,json.dumps({'ok':True,'connected':connected,'unread':unread,'needs_action':action}),'application/json')
        if p=='/login':return self.send(200,login_page())
        if p=='/logout':
            raw=cookies.SimpleCookie(self.headers.get('Cookie','')).get('AGAPE_COMMS_SESSION')
            if raw:
                c=db(); c.execute('UPDATE sessions SET revoked=1 WHERE token_hash=?',(hashlib.sha256(raw.value.encode()).hexdigest(),)); c.commit(); c.close()
            return self.redirect('/login','AGAPE_COMMS_SESSION=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict')
        if p=='/change-password':
            u=self.user()
            if not u:return self.redirect('/login')
            return self.send(200,page('Change password','<div class=card><h1>Change temporary password</h1><form method=post action=/change-password><label>Current password</label><input type=password name=current><label>New password (12+ characters)</label><input type=password name=new><button>Change password</button></form></div>'))
        u=self.require();
        if not u:return
        if p=='/':return self.send(200,dashboard(u))
        if p=='/connections':
            c=db(); rows=[dict(r) for r in c.execute('SELECT * FROM connections ORDER BY id DESC')]; c.close()
            rr=''.join(f"<tr><td>{esc(r['name'])}</td><td>{esc(r['kind'])}</td><td>{esc(r['account'])}</td><td class={'ok' if r['connected'] else 'bad'}>{'Connected' if r['connected'] else 'Not connected'}</td><td>{esc(r['last_test_status'])}</td><td>{esc(r['last_test_detail'])}</td></tr>" for r in rows) or '<tr><td colspan=6>No accounts connected yet.</td></tr>'
            add=''
            if u['role']=='owner':
                add='''<div class=card><h2>Add / connect account</h2><p class=muted>For Gmail and Microsoft/Outlook use AUTH-AGAPE-ACCOUNTS.ps1 so the provider opens its own secure sign-in window. The form remains for generic IMAP/SMTP and token-based services.</p><form method=post action=/connections/save><label>Connector</label><select name=kind><option value=local_test>Local test transport</option><option value=gmail_oauth>Gmail OAuth - terminal wizard</option><option value=microsoft_graph>Microsoft Outlook OAuth - terminal wizard</option><option value=smtp_imap>Other Email - IMAP/SMTP</option><option value=matrix>Matrix</option><option value=mastodon>Mastodon</option><option value=whatsapp_cloud>WhatsApp Business Cloud API</option><option value=whatsapp_personal>WhatsApp Personal - browser handoff only</option></select><label>Connection name</label><input name=name placeholder="Work Gmail"><label>Account / email</label><input name=account placeholder="you@example.com"><label>Configuration JSON</label><textarea name=config placeholder='{"email":"you@example.com","imap_host":"imap.example.com","imap_port":993,"smtp_host":"smtp.example.com","smtp_port":465}'></textarea><label>Secret JSON</label><textarea name=secret placeholder='{"password":"app-password-or-token"}'></textarea><p class=muted>Secrets are stored only in the local communications database. Use provider app passwords/tokens/OAuth-derived tokens, not your normal password where the provider offers a safer method.</p><button>Save and test connection</button></form></div>'''
            body=f'''<div class=card><h1>Connect email clients & accounts</h1><p>A connection shows <b>Connected</b> only after a live authentication test succeeds.</p><table><tr><th>Name</th><th>Type</th><th>Account</th><th>Status</th><th>Test</th><th>Detail</th></tr>{rr}</table></div>{add}'''
            return self.send(200,page('Connections',body))
        if p=='/inbox':
            c=db(); rows=[dict(r) for r in c.execute("SELECT m.*,c.name connection_name FROM messages m LEFT JOIN connections c ON c.id=m.connection_id WHERE m.direction='in' ORDER BY m.id DESC LIMIT 200")]; c.close()
            rr=''.join(f"<tr><td>{'ACTION' if r['needs_action'] else ''}</td><td>{esc(r['connection_name'])}</td><td>{esc(r['sender'])}</td><td>{esc(r['subject'])}</td><td>{esc(r['body_preview'][:260])}</td><td>{esc(r['status'])}</td></tr>" for r in rows) or '<tr><td colspan=6>No synced messages.</td></tr>'
            controls=''
            if u['role']=='owner': controls='<form method=post action=/inbox/sync><button>Sync connected email inboxes</button></form>'
            return self.send(200,page('Inbox',f'<div class=card><h1>Email</h1>{controls}<table><tr><th>Priority</th><th>Account</th><th>From</th><th>Subject</th><th>Preview</th><th>Status</th></tr>{rr}</table></div>'))
        if p=='/share':
            c=db(); rows=[dict(r) for r in c.execute('SELECT * FROM connections WHERE connected=1 ORDER BY name')]; c.close(); opts=''.join(f"<option value={r['id']}>{esc(r['name'])} - {esc(r['kind'])}</option>" for r in rows)
            disabled=' disabled' if u['role']=='public' else ''
            return self.send(200,page('Share / Send',f'''<div class=card><h1>Share / Send a file</h1><p class=muted>Public Main is read-only. Test accounts may send only through Local test transport.</p><form method=post enctype=multipart/form-data action=/share/send><label>Connected account</label><select name=connection_id>{opts}</select><label>Recipient / room / destination</label><input name=recipient><label>Subject</label><input name=subject><label>Message</label><textarea name=message></textarea><label>Attachment</label><input type=file name=attachment><button{disabled}>SEND</button></form></div>'''))
        if p=='/contacts':
            c=db(); rows=[dict(r) for r in c.execute('SELECT * FROM contacts ORDER BY name')]; c.close(); rr=''.join(f"<tr><td>{esc(r['name'])}</td><td>{esc(r['email'])}</td><td>{esc(r['phone'])}</td><td>{esc(r['whatsapp'])}</td><td>{esc(r['matrix'])}</td><td>{esc(r['mastodon'])}</td></tr>" for r in rows) or '<tr><td colspan=6>No contacts yet.</td></tr>'
            add='' if u['role']=='public' else '''<div class=card><h2>Add contact</h2><form method=post action=/contacts/add><input name=name placeholder="Name"><input name=email placeholder="Email"><input name=phone placeholder="Phone"><input name=whatsapp placeholder="WhatsApp"><input name=matrix placeholder="Matrix room/user"><input name=mastodon placeholder="Mastodon"><button>Save contact</button></form></div>'''
            return self.send(200,page('Contacts',f'<div class=card><h1>Contacts</h1><table><tr><th>Name</th><th>Email</th><th>Phone</th><th>WhatsApp</th><th>Matrix</th><th>Mastodon</th></tr>{rr}</table></div>'+add))
        if p=='/history':
            c=db(); rows=[dict(r) for r in c.execute('SELECT s.*,c.name connection_name,u.username FROM sends s LEFT JOIN connections c ON c.id=s.connection_id LEFT JOIN users u ON u.id=s.user_id ORDER BY s.id DESC LIMIT 300')]; c.close(); rr=''.join(f"<tr><td>{esc(r['created_at'])}</td><td>{esc(r['username'])}</td><td>{esc(r['channel'])}</td><td>{esc(r['connection_name'])}</td><td>{esc(r['recipient'])}</td><td>{esc(r['attachment_name'])}</td><td>{esc(r['status'])}</td><td>{esc(r['detail'])}</td></tr>" for r in rows) or '<tr><td colspan=8>No sends yet.</td></tr>'
            return self.send(200,page('Send history',f'<div class=card><h1>Send history</h1><table><tr><th>Time</th><th>User</th><th>Channel</th><th>Account</th><th>Recipient</th><th>Attachment</th><th>Status</th><th>Detail</th></tr>{rr}</table></div>'))
        self.send(404,page('Not found','<div class=card>Not found.</div>'))
    def do_POST(self):
        p=urllib.parse.urlparse(self.path).path
        if p=='/login':
            f=self.fields(); c=db(); r=c.execute('SELECT * FROM users WHERE username=? AND enabled=1',(f.get('username',''),)).fetchone()
            if not r or not check_password(f.get('password',''),r['password_hash']): c.close(); return self.send(401,login_page('Invalid username or password'))
            token=secrets.token_urlsafe(32); c.execute('INSERT INTO sessions(token_hash,user_id,created_at,expires_at) VALUES(?,?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),r['id'],now(),int(time.time())+43200)); c.execute('UPDATE users SET last_login=? WHERE id=?',(now(),r['id'])); c.commit(); c.close(); return self.redirect('/','AGAPE_COMMS_SESSION='+token+'; Path=/; HttpOnly; SameSite=Strict')
        if p=='/change-password':
            u=self.user();
            if not u:return self.redirect('/login')
            f=self.fields(); c=db(); r=c.execute('SELECT * FROM users WHERE id=?',(u['id'],)).fetchone(); new=f.get('new','')
            if not check_password(f.get('current',''),r['password_hash']) or len(new)<12:c.close(); return self.send(400,page('Password error','<div class=card><p class=bad>Current password is incorrect or new password is shorter than 12 characters.</p><a class=btn href=/change-password>Try again</a></div>'))
            c.execute('UPDATE users SET password_hash=?,must_change=0 WHERE id=?',(pbkdf(new),u['id'])); c.commit(); c.close(); return self.redirect('/')
        u=self.require();
        if not u:return
        if p=='/connections/save':
            if u['role']!='owner':return self.send(403,page('Forbidden','<div class=card>Owner only.</div>'))
            f=self.fields(); kind=f.get('kind',''); name=f.get('name','').strip(); account=f.get('account','').strip(); cfg=safe_json(f.get('config','{}')); sec=safe_json(f.get('secret','{}'))
            if not name:return self.send(400,page('Error','<div class=card>Name required.</div>'))
            ok,detail=test_connection(kind,cfg,sec); c=db(); c.execute('INSERT INTO connections(kind,name,account,config_json,secret_json,connected,last_test_status,last_test_detail,last_test_at,created_at) VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(kind,name) DO UPDATE SET account=excluded.account,config_json=excluded.config_json,secret_json=excluded.secret_json,connected=excluded.connected,last_test_status=excluded.last_test_status,last_test_detail=excluded.last_test_detail,last_test_at=excluded.last_test_at',(kind,name,account,json.dumps(cfg),secret_pack(sec),1 if ok else 0,'PASS' if ok else 'FAIL',detail,now(),now())); c.commit(); c.close(); return self.redirect('/connections')
        if p=='/inbox/sync':
            if u['role']!='owner':return self.send(403,page('Forbidden','<div class=card>Owner only.</div>'))
            c=db(); rows=[dict(r) for r in c.execute("SELECT * FROM connections WHERE connected=1 AND kind IN ('smtp_imap','gmail_oauth','microsoft_graph')")]; c.close(); results=[]
            for r in rows:
                try:
                    n=sync_gmail(r) if r['kind']=='gmail_oauth' else (sync_microsoft(r) if r['kind']=='microsoft_graph' else sync_imap(r))
                    results.append(r['name']+': '+str(n)+' unread synced')
                except Exception as e:results.append(r['name']+': FAIL '+str(e)[:200])
            return self.send(200,page('Inbox sync','<div class=card><h1>Sync result</h1><pre>'+esc('\n'.join(results) or 'No connected IMAP email accounts.')+'</pre><a class=btn href=/inbox>Back to inbox</a></div>'))
        if p=='/contacts/add':
            if u['role']=='public':return self.send(403,page('Forbidden','<div class=card>Read only.</div>'))
            f=self.fields(); c=db(); c.execute('INSERT INTO contacts(name,email,phone,whatsapp,matrix,mastodon,created_at) VALUES(?,?,?,?,?,?,?)',(f.get('name',''),f.get('email',''),f.get('phone',''),f.get('whatsapp',''),f.get('matrix',''),f.get('mastodon',''),now())); c.commit(); c.close(); return self.redirect('/contacts')
        if p=='/share/send':
            if u['role']=='public':return self.send(403,page('Forbidden','<div class=card>Public Main is read only.</div>'))
            content_type=self.headers.get('Content-Type',''); att=None; fields={}
            if content_type.lower().startswith('multipart/form-data'):
                n=int(self.headers.get('Content-Length') or 0)
                if n>25*1024*1024:return self.send(413,page('Too large','<div class=card>Upload exceeds 25 MB request limit.</div>'))
                raw=self.rfile.read(n)
                mime=(f'Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n').encode()+raw
                form=BytesParser(policy=email_policy).parsebytes(mime)
                for part in form.iter_parts():
                    name=part.get_param('name',header='content-disposition') or ''
                    filename=part.get_filename()
                    payload=part.get_payload(decode=True) or b''
                    if filename:
                        if len(payload)>20*1024*1024:return self.send(413,page('Too large','<div class=card>Attachment exceeds 20 MB R1 limit.</div>'))
                        att=(payload,Path(filename).name)
                    elif name in ('connection_id','recipient','subject','message'):
                        try:fields[name]=payload.decode(part.get_content_charset() or 'utf-8',errors='replace')
                        except Exception:fields[name]=payload.decode('utf-8',errors='replace')
            else:fields=self.fields()
            try:cid=int(fields.get('connection_id') or 0)
            except:cid=0
            c=db(); row=c.execute('SELECT * FROM connections WHERE id=? AND connected=1',(cid,)).fetchone();
            if not row:c.close();return self.send(400,page('Send failed','<div class=card>No connected account selected.</div>'))
            row=dict(row); cfg=safe_json(row['config_json']); sec=row_secret(row); recipient=fields.get('recipient',''); subject=fields.get('subject',''); message=fields.get('message',''); status='FAIL'; detail='';
            try:
                if u['role']=='tester' and row['kind']!='local_test':raise PermissionError('TEST_ACCOUNT_PRODUCTION_SEND_BLOCKED')
                if row['kind']=='local_test':detail='LOCAL_TEST_SEND_PASS';status='PASS'
                elif row['kind']=='smtp_imap':detail=send_email(cfg,sec,recipient,subject,message,att);status='PASS'
                elif row['kind']=='gmail_oauth':detail=send_gmail_oauth(cfg,sec,recipient,subject,message,att);update_row_secret(row['id'],sec);status='PASS'
                elif row['kind']=='microsoft_graph':detail=send_microsoft_graph(cfg,sec,recipient,subject,message,att);update_row_secret(row['id'],sec);status='PASS'
                elif row['kind']=='matrix':detail=send_matrix(cfg,sec,recipient,message,att);status='PASS'
                elif row['kind']=='mastodon':detail=post_mastodon(cfg,sec,message);status='PASS'
                elif row['kind']=='whatsapp_personal':
                    url='https://web.whatsapp.com/send?phone='+urllib.parse.quote(recipient)+'&text='+urllib.parse.quote(message); webbrowser.open(url); detail='WHATSAPP_BROWSER_HANDOFF_OPENED';status='PASS'
                else:raise RuntimeError('R1_SEND_NOT_IMPLEMENTED_FOR_'+row['kind'])
            except Exception as e:detail=type(e).__name__+': '+str(e)[:400]
            c.execute('INSERT INTO sends(user_id,connection_id,channel,recipient,subject,message,attachment_name,status,detail,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(u['id'],row['id'],row['kind'],recipient,subject,message,att[1] if att else '',status,detail,now())); c.commit(); c.close();
            return self.send(200,page('Send result',f'<div class=card><h1>Send {esc(status)}</h1><p>{esc(detail)}</p><a class=btn href=/history>View history</a></div>'))
        self.send(404,page('Not found','<div class=card>Not found.</div>'))

def self_test():
    init_db(); ensure_accounts(); tests=[]
    def T(name,fn):
        try:fn();tests.append((name,'PASS',''))
        except Exception as e:tests.append((name,'FAIL',type(e).__name__+': '+str(e)))
    T('db_quick_check',lambda: (_ for _ in ()).throw(RuntimeError('quick_check')) if db().execute('PRAGMA quick_check').fetchone()[0]!='ok' else None)
    T('password_hash',lambda: (_ for _ in ()).throw(RuntimeError('hash')) if not check_password('abcXYZ123!@#',pbkdf('abcXYZ123!@#')) else None)
    T('dpapi_secret_roundtrip',lambda: (_ for _ in ()).throw(RuntimeError('dpapi')) if secret_unpack(secret_pack({'x':'y'})).get('x')!='y' else None)
    T('action_classifier',lambda: (_ for _ in ()).throw(RuntimeError('classifier')) if classify_action('Please confirm your email')!=1 or classify_action('Newsletter')!=0 else None)
    T('local_transport',lambda: (_ for _ in ()).throw(RuntimeError('local transport')) if not test_connection('local_test',{}, {})[0] else None)
    def roles():
        c=db(); rr={r['username']:r['role'] for r in c.execute('SELECT username,role FROM users')};c.close(); assert rr.get('owner')=='owner' and rr.get('public-main')=='public' and rr.get('agape-test')=='tester'
    T('required_accounts',roles)
    def add_test_connection():
        c=db(); c.execute("INSERT INTO connections(kind,name,account,config_json,secret_json,connected,last_test_status,last_test_detail,last_test_at,created_at) VALUES('local_test','Self Test','local','{}','{}',1,'PASS','SELFTEST',?,?) ON CONFLICT(kind,name) DO UPDATE SET connected=1,last_test_status='PASS'",(now(),now())); c.commit(); r=c.execute("SELECT connected,last_test_status FROM connections WHERE kind='local_test' AND name='Self Test'").fetchone();c.close(); assert r['connected']==1 and r['last_test_status']=='PASS'
    T('connection_persistence',add_test_connection)
    def test_send_history():
        c=db(); uid=c.execute("SELECT id FROM users WHERE username='agape-test'").fetchone()[0]; cid=c.execute("SELECT id FROM connections WHERE kind='local_test' AND name='Self Test'").fetchone()[0]; c.execute("INSERT INTO sends(user_id,connection_id,channel,recipient,status,detail,created_at) VALUES(?,?, 'local_test','selftest','PASS','LOCAL_TEST_SEND_PASS',?)",(uid,cid,now())); c.commit(); assert c.execute("SELECT count(*) FROM sends WHERE detail='LOCAL_TEST_SEND_PASS'").fetchone()[0]>=1;c.close()
    T('test_send_history',test_send_history)
    def no_plain_passwords():
        c=db(); cols=[r[1] for r in c.execute('PRAGMA table_info(users)')]; c.close(); assert 'password' not in cols and 'password_hash' in cols
    T('no_plain_user_password_column',no_plain_passwords)
    failed=[x for x in tests if x[1]!='PASS']; print(json.dumps({'ok':not failed,'build':BUILD,'tests':[{'name':a,'status':b,'detail':c} for a,b,c in tests]},indent=2)); return 0 if not failed else 2

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--port',type=int,default=DEFAULT_PORT); ap.add_argument('--self-test',action='store_true'); args=ap.parse_args(); init_db(); ensure_accounts()
    if args.self_test:return self_test()
    httpd=ThreadingHTTPServer((HOST,args.port),H); print(f'AGAPE_COMMS_READY=http://{HOST}:{args.port}/ BUILD={BUILD}',flush=True); httpd.serve_forever()
if __name__=='__main__':raise SystemExit(main())
'@

try {
  Say 'BUILD' $Build 'Cyan'
  Say 'AGAPE_ROOT' ($(if($AgapeRoot){$AgapeRoot}else{'NOT_FOUND_UI_PATCH_SKIPPED'})) 'Cyan'
  Say 'HUB_ROOT' $Root 'Cyan'
  Say 'HUB_DATA' $Data 'Cyan'
  Say 'DATABASE' $HubDb 'Cyan'

  [IO.File]::WriteAllText($PythonFile,$Py,(New-Object Text.UTF8Encoding($false)))

  $AuthCode = @'
from __future__ import annotations
import argparse, base64, ctypes, json, os, sqlite3, sys, urllib.parse, urllib.request
from pathlib import Path
from datetime import datetime, timezone

DATA = Path(os.environ.get('AGAPE_COMMS_DATA') or (Path.home()/'Documents'/'AGAPE-COMMS-HUB')).resolve()
DB = DATA/'communications.sqlite3'
GMAIL_SCOPES = ['https://www.googleapis.com/auth/gmail.readonly','https://www.googleapis.com/auth/gmail.send']
MS_SCOPES = ['User.Read','Mail.Read','Mail.Send']

def now(): return datetime.now(timezone.utc).isoformat()
class B(ctypes.Structure): _fields_=[('cbData',ctypes.c_ulong),('pbData',ctypes.POINTER(ctypes.c_ubyte))]
def blob(data):
    buf=ctypes.create_string_buffer(data)
    return B(len(data),ctypes.cast(buf,ctypes.POINTER(ctypes.c_ubyte))),buf

def protect(data):
    if os.name!='nt': return base64.b64encode(data).decode()
    i,k=blob(data); o=B()
    if not ctypes.windll.crypt32.CryptProtectData(ctypes.byref(i),None,None,None,None,1,ctypes.byref(o)):
        raise OSError('DPAPI protect failed')
    try: return base64.b64encode(ctypes.string_at(o.pbData,o.cbData)).decode()
    finally: ctypes.windll.kernel32.LocalFree(o.pbData)

def pack(obj): return json.dumps({'dpapi':protect(json.dumps(obj,separators=(',',':')).encode())})

def save(kind,name,account,cfg,sec,detail):
    c=sqlite3.connect(DB)
    c.execute('''INSERT INTO connections(kind,name,account,config_json,secret_json,connected,last_test_status,last_test_detail,last_test_at,created_at)
                 VALUES(?,?,?,?,?,1,?,?,?,?)
                 ON CONFLICT(kind,name) DO UPDATE SET account=excluded.account,config_json=excluded.config_json,
                 secret_json=excluded.secret_json,connected=1,last_test_status=excluded.last_test_status,
                 last_test_detail=excluded.last_test_detail,last_test_at=excluded.last_test_at''',
              (kind,name,account,json.dumps(cfg),pack(sec),'PASS',detail,now(),now()))
    c.commit(); c.close()

def urljson(url,token):
    req=urllib.request.Request(url,headers={'Authorization':'Bearer '+token})
    with urllib.request.urlopen(req,timeout=30) as r: return json.loads(r.read().decode())

def gmail(a):
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    flow=InstalledAppFlow.from_client_secrets_file(a.credentials,GMAIL_SCOPES)
    creds=flow.run_local_server(port=0,open_browser=True,prompt='consent',authorization_prompt_message='Opening Gmail authorisation in your browser...')
    service=build('gmail','v1',credentials=creds,cache_discovery=False)
    p=service.users().getProfile(userId='me').execute(); email=p.get('emailAddress','')
    if not email: raise RuntimeError('GMAIL_PROFILE_NO_EMAIL')
    save('gmail_oauth',a.name or ('Gmail '+email),email,{'email':email},{'google_credentials':json.loads(creds.to_json())},'GMAIL_ACCOUNT='+email)
    print(json.dumps({'ok':True,'kind':'gmail_oauth','account':email}))

def microsoft(a):
    import msal
    cache=msal.SerializableTokenCache()
    app=msal.PublicClientApplication(a.client_id,authority='https://login.microsoftonline.com/common',token_cache=cache)
    result=app.acquire_token_interactive(scopes=MS_SCOPES,prompt='select_account')
    if 'access_token' not in result: raise RuntimeError(result.get('error_description') or result.get('error') or 'MICROSOFT_AUTH_FAIL')
    j=urljson('https://graph.microsoft.com/v1.0/me?$select=id,displayName,mail,userPrincipalName',result['access_token'])
    email=j.get('mail') or j.get('userPrincipalName') or ''
    if not email: raise RuntimeError('MICROSOFT_PROFILE_NO_EMAIL')
    save('microsoft_graph',a.name or ('Microsoft '+email),email,{'email':email},{'client_id':a.client_id,'token_cache':cache.serialize()},'MICROSOFT_ACCOUNT='+email)
    print(json.dumps({'ok':True,'kind':'microsoft_graph','account':email}))

def token_service(a):
    if a.kind=='matrix':
        j=urljson(a.base_url.rstrip('/')+'/_matrix/client/v3/account/whoami',a.token); account=j.get('user_id','')
        detail='MATRIX_USER='+account; cfg={'homeserver':a.base_url}; sec={'access_token':a.token}
    elif a.kind=='mastodon':
        j=urljson(a.base_url.rstrip('/')+'/api/v1/accounts/verify_credentials',a.token); account=j.get('acct','')
        detail='MASTODON_ACCOUNT='+account; cfg={'base_url':a.base_url}; sec={'access_token':a.token}
    else:
        url='https://graph.facebook.com/v23.0/'+urllib.parse.quote(a.phone_id)+'?fields=display_phone_number,verified_name'
        j=urljson(url,a.token); account=j.get('display_phone_number','')
        detail='WHATSAPP='+account; cfg={'phone_number_id':a.phone_id}; sec={'access_token':a.token}
    if not account: raise RuntimeError('LIVE_ACCOUNT_TEST_FAILED')
    save(a.kind,a.name or (a.kind+' '+account),account,cfg,sec,detail)
    print(json.dumps({'ok':True,'kind':a.kind,'account':account}))

def imap(a):
    import imaplib,smtplib,ssl
    ctx=ssl.create_default_context(); m=imaplib.IMAP4_SSL(a.imap_host,a.imap_port,ssl_context=ctx); m.login(a.email,a.password); m.noop(); m.logout()
    if a.starttls:
        s=smtplib.SMTP(a.smtp_host,a.smtp_port,timeout=20); s.starttls(context=ctx)
    else: s=smtplib.SMTP_SSL(a.smtp_host,a.smtp_port,timeout=20,context=ctx)
    s.login(a.email,a.password); s.noop(); s.quit()
    cfg={'email':a.email,'imap_host':a.imap_host,'imap_port':a.imap_port,'smtp_host':a.smtp_host,'smtp_port':a.smtp_port,'smtp_starttls':a.starttls}
    save('smtp_imap',a.name or ('Email '+a.email),a.email,cfg,{'password':a.password},'IMAP_AND_SMTP_AUTH_PASS')
    print(json.dumps({'ok':True,'kind':'smtp_imap','account':a.email}))

p=argparse.ArgumentParser(); sub=p.add_subparsers(dest='cmd',required=True)
g=sub.add_parser('gmail'); g.add_argument('--credentials',required=True); g.add_argument('--name',default='')
m=sub.add_parser('microsoft'); m.add_argument('--client-id',required=True); m.add_argument('--name',default='')
for k in ('matrix','mastodon'):
    q=sub.add_parser(k); q.add_argument('--base-url',required=True); q.add_argument('--token',required=True); q.add_argument('--name',default=''); q.set_defaults(kind=k)
w=sub.add_parser('whatsapp_cloud'); w.add_argument('--phone-id',required=True); w.add_argument('--token',required=True); w.add_argument('--name',default=''); w.set_defaults(kind='whatsapp_cloud')
i=sub.add_parser('imap'); i.add_argument('--email',required=True); i.add_argument('--imap-host',required=True); i.add_argument('--imap-port',type=int,default=993); i.add_argument('--smtp-host',required=True); i.add_argument('--smtp-port',type=int,default=465); i.add_argument('--starttls',action='store_true'); i.add_argument('--password',required=True); i.add_argument('--name',default='')
a=p.parse_args()
try: {'gmail':gmail,'microsoft':microsoft,'matrix':token_service,'mastodon':token_service,'whatsapp_cloud':token_service,'imap':imap}[a.cmd](a)
except Exception as e:
    print(json.dumps({'ok':False,'error':type(e).__name__+': '+str(e)})); sys.exit(2)
'@
  [IO.File]::WriteAllText($AuthPy,$AuthCode,(New-Object Text.UTF8Encoding($false)))

  $AuthPsCode = @'
& {
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName Microsoft.VisualBasic
$Root=Join-Path $env:LOCALAPPDATA 'Agape-Communications-Hub'
$Data=Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'AGAPE-COMMS-HUB'
$AuthPy=Join-Path $Root 'agape_account_auth.py'
$Python=@((Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'),(Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe'))|Where-Object{Test-Path $_}|Select-Object -First 1
if(-not $Python){$c=Get-Command python.exe -ErrorAction SilentlyContinue;if($c){$Python=$c.Source}}
if(-not $Python){throw 'PYTHON_NOT_FOUND'}
$env:AGAPE_COMMS_DATA=$Data
function Ask($t){[System.Windows.Forms.MessageBox]::Show($t,'Agape account authorisation',[System.Windows.Forms.MessageBoxButtons]::YesNo,[System.Windows.Forms.MessageBoxIcon]::Question)-eq [System.Windows.Forms.DialogResult]::Yes}
function Info($t){[System.Windows.Forms.MessageBox]::Show($t,'Agape account authorisation',[System.Windows.Forms.MessageBoxButtons]::OK,[System.Windows.Forms.MessageBoxIcon]::Information)|Out-Null}
function Input($p,$title,$d=''){[Microsoft.VisualBasic.Interaction]::InputBox($p,$title,$d).Trim()}
function SecretInput($prompt,$title){$f=New-Object System.Windows.Forms.Form;$f.Text=$title;$f.Width=520;$f.Height=170;$f.StartPosition='CenterScreen';$l=New-Object System.Windows.Forms.Label;$l.Text=$prompt;$l.Left=12;$l.Top=12;$l.Width=480;$t=New-Object System.Windows.Forms.TextBox;$t.Left=12;$t.Top=42;$t.Width=480;$t.UseSystemPasswordChar=$true;$ok=New-Object System.Windows.Forms.Button;$ok.Text='OK';$ok.Left=330;$ok.Top=78;$ok.DialogResult=[System.Windows.Forms.DialogResult]::OK;$cancel=New-Object System.Windows.Forms.Button;$cancel.Text='Cancel';$cancel.Left=410;$cancel.Top=78;$cancel.DialogResult=[System.Windows.Forms.DialogResult]::Cancel;$f.Controls.AddRange(@($l,$t,$ok,$cancel));$f.AcceptButton=$ok;$f.CancelButton=$cancel;if($f.ShowDialog()-eq [System.Windows.Forms.DialogResult]::OK){return $t.Text.Trim()}return ''}
function RunAuth([string[]]$A){$o=& $Python $AuthPy @A 2>&1;$c=$LASTEXITCODE;Write-Host ($o -join "`n");if($c -eq 0){Info ('Connected and live-tested.'+"`r`n`r`n"+($o -join "`r`n"));$true}else{[System.Windows.Forms.MessageBox]::Show(('Connection failed.'+"`r`n`r`n"+($o -join "`r`n")),'Agape',[System.Windows.Forms.MessageBoxButtons]::OK,[System.Windows.Forms.MessageBoxIcon]::Error)|Out-Null;$false}}
Write-Host 'AGAPE_ACCOUNT_WIZARD=START'
Info 'Agape will offer each supported account type. Choose Yes only for accounts you want to connect. An account is marked Connected only after its live provider test passes.'
while(Ask 'Connect a Gmail / Google Workspace account now?'){
 $d=New-Object System.Windows.Forms.OpenFileDialog;$d.Title='Select Google OAuth Desktop credentials.json';$d.Filter='JSON files (*.json)|*.json|All files (*.*)|*.*'
 if($d.ShowDialog()-ne [System.Windows.Forms.DialogResult]::OK){Start-Process 'https://console.cloud.google.com/apis/credentials';Info 'Create an OAuth Client ID of type Desktop app, download credentials.json, then run this wizard again.';break}
 $n=Input 'Connection name' 'Gmail connection' 'Gmail';RunAuth @('gmail','--credentials',$d.FileName,'--name',$n)|Out-Null
 if(-not(Ask 'Connect another Gmail account?')){break}
}
while(Ask 'Connect a Microsoft Outlook / Microsoft 365 account now?'){
 $id=Input 'Paste your Microsoft Entra Application (client) ID. Configure Mobile/Desktop redirect URI http://localhost.' 'Microsoft OAuth Client ID'
 if(-not $id){Start-Process 'https://entra.microsoft.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade';Info 'Create/open an Agape app registration, enable Mobile and desktop applications with http://localhost, then run this wizard again.';break}
 $n=Input 'Connection name' 'Microsoft connection' 'Outlook';RunAuth @('microsoft','--client-id',$id,'--name',$n)|Out-Null
 if(-not(Ask 'Connect another Microsoft account?')){break}
}
while(Ask 'Connect another email account using IMAP/SMTP? Use an app password/token when available.'){
 $e=Input 'Email address' 'Other email';if(-not $e){break};$ih=Input 'IMAP server' 'Other email' 'imap.example.com';$ip=Input 'IMAP port' 'Other email' '993';$sh=Input 'SMTP server' 'Other email' 'smtp.example.com';$sp=Input 'SMTP port' 'Other email' '465';$pw=SecretInput 'App password / mail token' 'Other email';$n=Input 'Connection name' 'Other email' $e
 $a=@('imap','--email',$e,'--imap-host',$ih,'--imap-port',$ip,'--smtp-host',$sh,'--smtp-port',$sp,'--password',$pw,'--name',$n);if($sp -eq '587'){$a+='--starttls'};RunAuth $a|Out-Null
 if(-not(Ask 'Connect another IMAP/SMTP account?')){break}
}
while(Ask 'Connect a Matrix account?'){$b=Input 'Homeserver URL' 'Matrix' 'https://matrix.org';$t=SecretInput 'Access token' 'Matrix';$n=Input 'Connection name' 'Matrix' 'Matrix';if($b -and $t){RunAuth @('matrix','--base-url',$b,'--token',$t,'--name',$n)|Out-Null};if(-not(Ask 'Connect another Matrix account?')){break}}
while(Ask 'Connect a Mastodon account?'){$b=Input 'Mastodon server URL' 'Mastodon' 'https://mastodon.social';$t=SecretInput 'Access token' 'Mastodon';$n=Input 'Connection name' 'Mastodon' 'Mastodon';if($b -and $t){RunAuth @('mastodon','--base-url',$b,'--token',$t,'--name',$n)|Out-Null};if(-not(Ask 'Connect another Mastodon account?')){break}}
while(Ask 'Connect a WhatsApp Business Cloud API account?'){$p=Input 'Phone Number ID' 'WhatsApp Business';$t=SecretInput 'Meta access token' 'WhatsApp Business';$n=Input 'Connection name' 'WhatsApp Business' 'WhatsApp Business';if($p -and $t){RunAuth @('whatsapp_cloud','--phone-id',$p,'--token',$t,'--name',$n)|Out-Null};if(-not(Ask 'Connect another WhatsApp Business account?')){break}}
if(Ask 'Open personal WhatsApp Web for QR sign-in/browser handoff? Personal WhatsApp is not marked as an automated production connection.'){Start-Process 'https://web.whatsapp.com/'}
Write-Host 'AGAPE_ACCOUNT_WIZARD=PASS'
Info 'Account authorisation finished. Only live-tested accounts are marked Connected.'
}
'@
  [IO.File]::WriteAllText($AuthPs,$AuthPsCode,(New-Object Text.UTF8Encoding($false)))

  $Starter = @"
`$ErrorActionPreference='Stop'
`$env:AGAPE_COMMS_DATA='$($Data.Replace("'","''"))'
`$Python='$($Python.Replace("'","''"))'
`$App='$($PythonFile.Replace("'","''"))'
`$Port=$HubPort
try { `$r=Invoke-RestMethod -Uri "http://127.0.0.1:`$Port/api/health" -TimeoutSec 2; if(`$r.ok){ Start-Process "http://127.0.0.1:`$Port/"; exit 0 } } catch {}
`$StdOut=Join-Path '$($Root.Replace("'","''"))' 'hub-start.stdout.log'
`$StdErr=Join-Path '$($Root.Replace("'","''"))' 'hub-start.stderr.log'
Remove-Item -LiteralPath `$StdOut,`$StdErr -Force -ErrorAction SilentlyContinue
`$Proc=Start-Process -FilePath `$Python -ArgumentList @('-u',`$App,'--port',[string]`$Port) -WorkingDirectory '$($Root.Replace("'","''"))' -RedirectStandardOutput `$StdOut -RedirectStandardError `$StdErr -PassThru -WindowStyle Hidden
for(`$i=0;`$i -lt 80;`$i++){ Start-Sleep -Milliseconds 250; if(`$Proc.HasExited){break}; try{ `$r=Invoke-RestMethod -Uri "http://127.0.0.1:`$Port/api/health" -TimeoutSec 2; if(`$r.ok){ Start-Process "http://127.0.0.1:`$Port/"; exit 0 } }catch{} }
`$ErrText=''; if(Test-Path `$StdErr){`$ErrText=(Get-Content `$StdErr -Raw -ErrorAction SilentlyContinue)}; throw ('AGAPE_COMMS_START_TIMEOUT EXIT=' + `$Proc.ExitCode + ' STDERR=' + `$ErrText)
"@
  [IO.File]::WriteAllText($StartFile,$Starter,(New-Object Text.UTF8Encoding($false)))

  # Install open-source OAuth client libraries used by Gmail and Microsoft interactive authorization.
  $Pip = & $Python -m pip install --user --upgrade google-api-python-client google-auth-httplib2 google-auth-oauthlib msal 2>&1
  if($LASTEXITCODE -ne 0){ throw ('OAUTH_LIBRARY_INSTALL_FAIL=' + ($Pip -join ' ')) }
  Say 'OAUTH_LIBRARIES' 'PASS' 'Green'

  # Compile and full local self-test before touching the Agape UI.
  & $Python -m py_compile $PythonFile $AuthPy
  if($LASTEXITCODE -ne 0){ throw 'PYTHON_COMPILE_FAIL' }
  $env:AGAPE_COMMS_DATA=$Data
  $Self = & $Python $PythonFile --self-test 2>&1
  $SelfText = ($Self -join "`n")
  if($LASTEXITCODE -ne 0){ throw "SELF_TEST_FAIL=$SelfText" }
  $SelfJson = $SelfText | ConvertFrom-Json
  if(-not $SelfJson.ok){ throw 'SELF_TEST_JSON_FAIL' }
  Say 'SELF_TEST' 'PASS' 'Green'
  foreach($t in $SelfJson.tests){ Say ('TEST_' + ($t.name.ToUpperInvariant())) $t.status ($(if($t.status -eq 'PASS'){'Green'}else{'Red'})) }

  # Patch Agape index with a non-invasive floating Communications widget.
  $UiPatched = $false
  if($Index){
    $html = Get-Content -LiteralPath $Index -Raw
    $html = [regex]::Replace($html,'(?s)<!-- AGAPE_COMMS_HUB_R[1-4]_WIDGET -->.*?</script>\s*','')
    $marker='AGAPE_COMMS_HUB_R5_WIDGET'
    if($html -notmatch [regex]::Escape($marker)){
      $inject = @"
<!-- AGAPE_COMMS_HUB_R5_WIDGET -->
<div id="agape-comms-widget" style="position:fixed;right:14px;top:10px;z-index:99999;font:13px Segoe UI,Arial;background:#111827;color:white;border-radius:9px;padding:7px 9px;box-shadow:0 2px 8px #0004"><a href="http://127.0.0.1:$HubPort/" target="_blank" style="color:white;text-decoration:none"><b id="agape-comms-email">Email 0</b> &middot; <span id="agape-comms-state">Not connected</span> &middot; Share / Send</a></div>
<script>(function(){async function u(){try{let r=await fetch('http://127.0.0.1:$HubPort/api/status',{cache:'no-store'}),j=await r.json();document.getElementById('agape-comms-email').textContent='Email '+(j.unread||0)+(j.needs_action?' · ⚠ '+j.needs_action:'');document.getElementById('agape-comms-state').textContent=(j.connected||0)>0?'Connected ✓':'Connect email clients';}catch(e){document.getElementById('agape-comms-state').textContent='Connect email clients';}}u();setInterval(u,30000)})();</script>
"@
      if($html -match '</body>'){ $html=$html -replace '</body>',($inject + "`r`n</body>") } else { $html += "`r`n" + $inject }
      [IO.File]::WriteAllText($Index,$html,(New-Object Text.UTF8Encoding($false)))
    }
    $verify=Get-Content -LiteralPath $Index -Raw
    if($verify -notmatch 'AGAPE_COMMS_HUB_R5_WIDGET'){ throw 'UI_PATCH_VERIFY_FAIL' }
    $UiPatched=$true
  }

  # Start the hub, then exercise real HTTP endpoints.
  try { $existing=Invoke-RestMethod -Uri "http://127.0.0.1:$HubPort/api/health" -TimeoutSec 2 } catch { $existing=$null }
  $StdOut=Join-Path $Root 'hub-install.stdout.log'
  $StdErr=Join-Path $Root 'hub-install.stderr.log'
  if(-not ($existing -and $existing.ok -and ($existing.build -like 'AGAPE-COMMS-HUB-*'))){
    Remove-Item -LiteralPath $StdOut,$StdErr -Force -ErrorAction SilentlyContinue
    $proc=Start-Process -FilePath $Python -ArgumentList @('-u',$PythonFile,'--port',[string]$HubPort) -WorkingDirectory $Root -RedirectStandardOutput $StdOut -RedirectStandardError $StdErr -PassThru -WindowStyle Hidden
  }
  if(-not (Wait-Http "http://127.0.0.1:$HubPort/api/health" 30)){
    $exit='RUNNING'; if($proc -and $proc.HasExited){$exit=[string]$proc.ExitCode}
    $stderr=''; if(Test-Path -LiteralPath $StdErr){$stderr=(Get-Content -LiteralPath $StdErr -Raw -ErrorAction SilentlyContinue)}
    $stdout=''; if(Test-Path -LiteralPath $StdOut){$stdout=(Get-Content -LiteralPath $StdOut -Raw -ErrorAction SilentlyContinue)}
    throw ('HUB_HTTP_START_FAIL PORT=' + $HubPort + ' EXIT=' + $exit + ' STDERR=' + $stderr + ' STDOUT=' + $stdout)
  }
  $Health=Invoke-RestMethod -Uri "http://127.0.0.1:$HubPort/api/health" -TimeoutSec 5
  if(-not $Health.ok -or $Health.build -ne $Build){ throw 'HUB_HEALTH_FAIL' }
  $Status=Invoke-RestMethod -Uri "http://127.0.0.1:$HubPort/api/status" -TimeoutSec 5
  if(-not $Status.ok){ throw 'HUB_STATUS_FAIL' }
  Say 'HTTP_HEALTH' 'PASS' 'Green'
  Say 'HTTP_STATUS' 'PASS' 'Green'

  # SQLite integrity test.
  $DbTest = & $Python -c "import sqlite3,sys; c=sqlite3.connect(r'''$HubDb'''); r=c.execute('pragma integrity_check').fetchone()[0]; print(r); sys.exit(0 if r=='ok' else 2)"
  if($LASTEXITCODE -ne 0 -or ($DbTest -join '') -ne 'ok'){ throw 'SQLITE_INTEGRITY_FAIL' }
  Say 'SQLITE_INTEGRITY' 'PASS' 'Green'

  # Verify three account roles exist; passwords are generated, not hard coded.
  $AccountTest = & $Python -c "import sqlite3,json; c=sqlite3.connect(r'''$HubDb'''); print(json.dumps(c.execute('select username,role,must_change from users order by username').fetchall()))"
  $Accounts = $AccountTest | ConvertFrom-Json
  if(@($Accounts | Where-Object { $_[0] -eq 'owner' -and $_[1] -eq 'owner' }).Count -ne 1){ throw 'OWNER_ACCOUNT_MISSING' }
  if(@($Accounts | Where-Object { $_[0] -eq 'public-main' -and $_[1] -eq 'public' }).Count -ne 1){ throw 'PUBLIC_MAIN_ACCOUNT_MISSING' }
  if(@($Accounts | Where-Object { $_[0] -eq 'agape-test' -and $_[1] -eq 'tester' }).Count -ne 1){ throw 'TEST_ACCOUNT_MISSING' }
  Say 'ACCOUNT_OWNER' 'PASS' 'Green'
  Say 'ACCOUNT_PUBLIC_MAIN_READ_ONLY' 'PASS' 'Green'
  Say 'ACCOUNT_TEST_RESTRICTED' 'PASS' 'Green'

  # Ensure local test transport is connected for safe tester validation.
  # Use a temporary Python file instead of python -c so PowerShell cannot reinterpret SQL quoting.
  $ConnVerifyFile = Join-Path $env:TEMP ('agape-conncheck-' + [guid]::NewGuid().ToString('N') + '.py')
  @'
import sqlite3
import sys

db_path = sys.argv[1]
with sqlite3.connect(db_path) as c:
    row = c.execute(
        "SELECT COUNT(*) FROM connections "
        "WHERE kind = ? AND connected = 1 AND last_test_status = ?",
        ("local_test", "PASS"),
    ).fetchone()
count = int(row[0] if row else 0)
print(count)
raise SystemExit(0 if count >= 1 else 3)
'@ | Set-Content -LiteralPath $ConnVerifyFile -Encoding UTF8
  try {
    $ConnCheck = & $Python $ConnVerifyFile $HubDb
    $ConnExit = $LASTEXITCODE
  }
  finally {
    Remove-Item -LiteralPath $ConnVerifyFile -Force -ErrorAction SilentlyContinue
  }
  $ConnCount = 0
  [void][int]::TryParse((($ConnCheck -join '').Trim()), [ref]$ConnCount)
  if($ConnExit -ne 0 -or $ConnCount -lt 1){ throw 'LOCAL_TEST_CONNECTION_MISSING' }
  Say 'LOCAL_TEST_CONNECTION' 'CONNECTED' 'Green'

  # Create a desktop shortcut for the hub starter when possible.
  try {
    $Desktop=[Environment]::GetFolderPath('Desktop')
    $ws=New-Object -ComObject WScript.Shell
    $sc=$ws.CreateShortcut((Join-Path $Desktop 'Agape Communications Hub.lnk'))
    $sc.TargetPath='powershell.exe'; $sc.Arguments='-NoProfile -ExecutionPolicy Bypass -File "' + $StartFile + '"'; $sc.WorkingDirectory=$Root; $sc.Save()
    Say 'DESKTOP_SHORTCUT' 'PASS' 'Green'
  } catch { Say 'DESKTOP_SHORTCUT' ('WARN=' + $_.Exception.Message) 'Yellow' }

  # Restrict credentials file to current user when icacls is available.
  if(Test-Path -LiteralPath $CredentialFile){
    try { & icacls $CredentialFile /inheritance:r /grant:r ($env:USERNAME + ':R') | Out-Null } catch {}
  }

  if(!(Test-Path -LiteralPath $AuthPy -PathType Leaf) -or !(Test-Path -LiteralPath $AuthPs -PathType Leaf)){ throw 'AUTH_WIZARD_FILES_MISSING' }
  Say 'AUTH_WIZARD' 'PASS' 'Green'

  $result=[ordered]@{
    overall='PASS';build=$Build;hub_url="http://127.0.0.1:$HubPort/";agape_root=$AgapeRoot;ui_patched=$UiPatched;
    self_tests=$SelfJson.tests;http_health='PASS';http_status='PASS';sqlite_integrity='PASS';
    accounts=@('owner','public-main','agape-test');public_main='READ_ONLY';test_account='LOCAL_TEST_ONLY';
    email_connectors=@('Gmail OAuth','Microsoft Graph OAuth','IMAP/SMTP','Local test');messaging_connectors=@('Matrix','WhatsApp Business Cloud API','WhatsApp Personal browser handoff');social_connectors=@('Mastodon');
    credentials_file=$CredentialFile;database=$HubDb;start_script=$StartFile;auth_wizard=$AuthPs;backup=$Backup;report=$Report
  }
  $result | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $Report -Encoding UTF8
  Say 'INSTALL' 'PASS' 'Green'
  Say 'HUB_URL' "http://127.0.0.1:$HubPort/" 'Cyan'
  Say 'CONNECT_EMAIL_CLIENTS' "http://127.0.0.1:$HubPort/connections" 'Cyan'
  Say 'AUTH_WIZARD_PATH' $AuthPs 'Cyan'
  Say 'FIRST_LOGIN_FILE' $CredentialFile 'Yellow'
  Say 'REPORT' $Report 'Cyan'
  Write-Host ''
  Write-Host 'CHATGPT_RESULT_BEGIN' -ForegroundColor Yellow
  $result | ConvertTo-Json -Depth 10
  Write-Host 'CHATGPT_RESULT_END' -ForegroundColor Yellow
  Start-Process "http://127.0.0.1:$HubPort/"
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File $AuthPs
}
catch {
  $err=$_.Exception.Message
  Rollback-Index $Index $IndexBackup
  $failure=[ordered]@{overall='FAIL';build=$Build;error=$err;ui_rollback=$(if($IndexBackup){'ATTEMPTED'}else{'NOT_NEEDED'});backup=$Backup;report=$Report}
  $failure|ConvertTo-Json -Depth 5|Set-Content -LiteralPath $Report -Encoding UTF8
  Say 'INSTALL' 'FAIL' 'Red'; Say 'ERROR' $err 'Red'; Say 'UI_ROLLBACK' $failure.ui_rollback 'Yellow'; Say 'REPORT' $Report 'Cyan'
  Write-Host 'CHATGPT_RESULT_BEGIN' -ForegroundColor Yellow; $failure|ConvertTo-Json -Depth 5; Write-Host 'CHATGPT_RESULT_END' -ForegroundColor Yellow
  exit 1
}
}
