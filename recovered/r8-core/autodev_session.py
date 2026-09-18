from __future__ import annotations

import uuid
from typing import Any

import db
import test_planner
import workspace_snapshot
from project_loop import validate_workspace, validate_test_command


def create_session(project_id: int, workspace: str, goal: str, test_command: str = '', max_steps: int = 4, model: str = '') -> dict[str, Any]:
    project=db.project(int(project_id))
    if not project:
        raise ValueError('PROJECT_NOT_FOUND')
    root=validate_workspace(workspace)
    clean_goal=' '.join(str(goal or '').split())
    if not clean_goal:
        raise ValueError('AUTODEV_SESSION_GOAL_REQUIRED')
    if len(clean_goal)>5000:
        raise ValueError('AUTODEV_SESSION_GOAL_TOO_LONG')
    steps=max(1,min(int(max_steps or 4),8))
    command=str(test_command or '').strip()
    if command:
        command=validate_test_command(command)
    else:
        planned=test_planner.plan_tests(str(root))
        if not planned.get('ok') or not planned.get('command'):
            raise ValueError('AUTODEV_SESSION_TEST_PLAN_REQUIRED')
        command=validate_test_command(str(planned['command']))
    snap=workspace_snapshot.create_snapshot(str(root),1000)
    session_id='AUTO-'+uuid.uuid4().hex[:20].upper()
    item=db.create_autodev_session(session_id,int(project_id),str(root),clean_goal,command,steps,str(model or ''),str(snap['snapshot_sha256']))
    return {'ok':True,'session':item,'snapshot_sha256':snap['snapshot_sha256'],'file_count':snap['file_count']}


def get_session(session_id: str) -> dict[str, Any]:
    item=db.autodev_session(str(session_id or ''))
    if not item:
        raise ValueError('AUTODEV_SESSION_NOT_FOUND')
    return {'ok':True,'session':item}


def list_sessions(project_id: int | None = None, limit: int = 100) -> dict[str, Any]:
    return {'ok':True,'sessions':db.list_autodev_sessions(project_id,limit)}
