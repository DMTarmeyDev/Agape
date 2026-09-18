import pathlib, tempfile
from unittest import mock
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
import sys; sys.path.insert(0,str(ROOT))
from agape_mainframe import bridge, state
JS=(ROOT/'web'/'app.js').read_text(encoding='utf-8')
SERVER=(ROOT/'agape_mainframe'/'server.py').read_text(encoding='utf-8')
BRIDGE=(ROOT/'agape_mainframe'/'bridge.py').read_text(encoding='utf-8')
STATE=(ROOT/'agape_mainframe'/'state.py').read_text(encoding='utf-8')

def test_recent_and_projects_share_canonical_status_layer():
    assert 'recent_work_with_live_status' in SERVER
    assert 'projects_with_live_status as bridge_projects' in SERVER
    assert 'sync_external_work_status(jid,payload)' in BRIDGE
    assert 'status_label' in BRIDGE

def test_live_refresh_changes_queued_history_to_complete():
    with tempfile.TemporaryDirectory() as td, mock.patch.object(state,'DB_FILE',pathlib.Path(td)/'mainframe.sqlite3'):
        state.remember_work('Status Project','task','document','J-LIVE','QUEUED',{'run_id':'MAIN-S','project_id':7})
        bridge._STATUS_SYNC_LAST=0.0
        payload={'ok':True,'job':{'id':'J-LIVE','status':'PASS','project_id':7,'message':'Complete','result':{'files':['x.docx']}}}
        with mock.patch.object(bridge,'r24_ready',return_value=True), mock.patch.object(bridge,'request_json',return_value=(200,payload)):
            rows=bridge.recent_work_with_live_status(10)
        assert rows[0]['status']=='PASS'
        assert rows[0]['status_label']=='Complete'
        assert rows[0]['project_id']==7

def test_projects_take_status_from_same_refreshed_history():
    with tempfile.TemporaryDirectory() as td, mock.patch.object(state,'DB_FILE',pathlib.Path(td)/'mainframe.sqlite3'):
        state.remember_work('Status Project','task','document','J-DONE','PASS',{'job':{'project_id':9,'status':'PASS'}})
        bridge._STATUS_SYNC_LAST=0.0
        with mock.patch.object(bridge,'projects',return_value=[{'id':9,'name':'Status Project','kind':'user'}]):
            rows=bridge.projects_with_live_status()
        assert rows[0]['status']=='PASS'
        assert rows[0]['status_label']=='Complete'
        assert rows[0]['latest_job_id']=='J-DONE'

def test_new_jobs_store_project_identity_for_cross_page_status():
    assert '"project_id":project_id,"intake_id":intake_id' in BRIDGE

def test_every_status_view_uses_human_canonical_labels():
    assert 'function canonicalStatusLabel(value)' in JS
    for label in ['Complete','Needs attention','Failed','Queued','Working']:
        assert label in JS
    assert 'canonicalStatusLabel(item)' in JS
    assert 'canonicalStatusLabel(j)' in JS
    assert 'canonicalStatusLabel(p)' in JS

def test_visible_status_pages_auto_refresh_across_devices():
    assert 'setInterval(refreshVisibleStatusView, 5000)' in JS
    assert "['results','projects','workspace']" in JS
    assert "window.addEventListener('focus'" in JS
    assert "document.addEventListener('visibilitychange'" in JS

def test_build_marker_is_v561():
    assert 'AGAPE-MAINFRAME-V5.6.1-CANONICAL-STATUS-SYNC' in STATE
