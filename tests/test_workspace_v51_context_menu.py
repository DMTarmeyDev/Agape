from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
HTML=(ROOT/"web"/"index.html").read_text(encoding="utf-8")
JS=(ROOT/"web"/"app.js").read_text(encoding="utf-8")
CSS=(ROOT/"web"/"styles.css").read_text(encoding="utf-8")

def test_context_menu_surface_exists():
    assert 'id="workspaceContextMenu"' in HTML
    assert '.context-menu' in CSS

def test_context_menu_is_bound_to_workspace_items():
    assert 'oncontextmenu' in JS
    assert 'projectContextActions' in JS
    assert 'jobContextActions' in JS
    assert 'todoContextActions' in JS

def test_project_context_has_expected_actions():
    for text in ('Use as source','Add to to-do','Copy project ID'):
        assert text in JS

def test_todo_context_has_edit_complete_delete():
    for text in ('Mark complete','Edit','Delete'):
        assert text in JS

def test_escape_and_click_close_context_menu():
    assert "event.key==='Escape'" in JS
    assert 'contextMenuHide' in JS
