from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT/'web'/'index.html').read_text(encoding='utf-8')
JS = (ROOT/'web'/'app.js').read_text(encoding='utf-8')
CSS = (ROOT/'web'/'styles.css').read_text(encoding='utf-8')

def test_workspace_nav_and_three_columns_exist():
    assert 'data-page="workspace"' in HTML
    assert 'id="workspaceTree"' in HTML
    assert 'id="workspacePreview"' in HTML
    assert 'id="todoList"' in HTML
    assert 'id="workspaceJobs"' in HTML
    assert 'workspace-grid' in CSS

def test_workspace_loads_existing_projects_and_jobs():
    assert "api('/api/projects')" in JS
    assert "api('/api/recent')" in JS
    assert 'renderWorkspaceTree' in JS
    assert 'renderWorkspaceJobs' in JS

def test_todos_persist_and_can_be_completed():
    assert "agape.workspace.todos.v1" in JS
    assert 'localStorage.getItem(TODO_KEY)' in JS
    assert 'localStorage.setItem(TODO_KEY' in JS
    assert 'event.target.checked' in JS

def test_workspace_actions_connect_to_existing_flows():
    assert "setSourceMode('project')" in JS
    assert 'resumeRecentJob(item.external_job_id)' in JS
