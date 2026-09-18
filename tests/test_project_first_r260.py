from pathlib import Path
from agape_mainframe.project_planner import classify_project_type, project_blueprint
from agape_mainframe.planner import plan
ROOT=Path(__file__).resolve().parents[1]

def test_explicit_project_types_drive_small_capability_sets():
    doc=project_blueprint("Create a business plan with market research","document")
    assert doc["project_type"]=="document" and not doc["show_coding_options"]
    assert "documents" in doc["required_capabilities"] and all(x["id"]!="appium-android" for x in doc["tools"])
    code=project_blueprint("Build an Android app and test the UI","development")
    assert code["project_type"]=="development" and code["subtype"]=="android" and code["show_coding_options"]
    assert any(x["id"]=="appium-android" for x in code["tools"])
    assert all(x["id"]!="document-studio" for x in code["tools"])

def test_auto_classifier_distinguishes_common_jobs():
    assert classify_project_type("Create a professional tender document")=="document"
    assert classify_project_type("Build a Python API and fix its tests")=="development"
    assert classify_project_type("Research competitors and cite the sources")=="research"
    assert classify_project_type("Automate a repeated invoice workflow")=="automation"
    assert classify_project_type("Prepare an email campaign")=="communications"

def test_execution_plan_respects_selected_project_type():
    p=plan("Create the finished thing",project_type="development",project_id=7)
    assert p["route"]=="development" and p["project_type"]=="development"
    assert p["project_blueprint"]["show_coding_options"] is True

def test_front_page_starts_with_project_decision_and_hides_source_until_continue():
    html=(ROOT/'web/index.html').read_text(encoding='utf-8');js=(ROOT/'web/app.js').read_text(encoding='utf-8')
    assert 'id="projectStartCard"' in html and 'What are you creating?' in html
    assert 'data-project-type="document"' in html and 'data-project-type="development"' in html
    assert 'id="sourceCard"' in html and 'card hero hidden' in html
    assert "api('/api/project/blueprint'" in js and 'show_coding_options' in js
    assert 'project_type: PROJECT_TYPE' in js

def test_server_exposes_blueprint_and_passes_project_type_to_execution_plan():
    server=(ROOT/'agape_mainframe/server.py').read_text(encoding='utf-8')
    assert 'if u.path=="/api/project/blueprint"' in server and 'project_blueprint(' in server
    assert 'project_type=str(b.get("project_type") or "")' in server
