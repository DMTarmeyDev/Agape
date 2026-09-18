from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def _table_names(con: sqlite3.Connection) -> set[str]:
    return {str(r[0]) for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}


def _columns(con: sqlite3.Connection, table: str) -> set[str]:
    try:
        return {str(r[1]) for r in con.execute(f"PRAGMA table_info({table})").fetchall()}
    except Exception:
        return set()


def _valid_project_db(path: Path) -> bool:
    try:
        uri = "file:" + str(path).replace("\\", "/") + "?mode=ro"
        con = sqlite3.connect(uri, uri=True, timeout=5)
        try:
            if "projects" not in _table_names(con):
                return False
            row = con.execute("PRAGMA quick_check").fetchone()
            return bool(row and str(row[0]).lower() == "ok")
        finally:
            con.close()
    except Exception:
        return False


def canonical_core_candidates() -> list[Path]:
    override = str(os.environ.get("AGAPE_CORE_DB") or "").strip()
    if override:
        return [Path(override).expanduser()]

    home = Path.home()
    local = Path(os.environ.get("LOCALAPPDATA", str(home / "AppData" / "Local")))
    out: list[Path] = []
    dmt_root = str(os.environ.get("DMT_DATA_ROOT") or "").strip()
    if dmt_root:
        out.append(Path(dmt_root).expanduser() / "dmt_core.sqlite3")
    one = str(os.environ.get("OneDrive") or os.environ.get("OneDriveConsumer") or "").strip()
    if one:
        out.append(Path(one) / "Documents" / "DMT-CORE-V3.1" / "second-brain-data" / "dmt_core.sqlite3")
    out += [
        home / "OneDrive" / "Documents" / "DMT-CORE-V3.1" / "second-brain-data" / "dmt_core.sqlite3",
        home / "Documents" / "DMT-CORE-V3.1" / "second-brain-data" / "dmt_core.sqlite3",
        local / "DMT-Core-V3.1" / "second-brain-data" / "dmt_core.sqlite3",
    ]
    unique: list[Path] = []
    seen: set[str] = set()
    for p in out:
        key = str(p).casefold()
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return unique


def find_live_core_db() -> Path | None:
    candidates = []
    for p in canonical_core_candidates():
        try:
            if p.is_file() and p.stat().st_size > 0 and _valid_project_db(p):
                candidates.append((p.stat().st_mtime, p))
        except Exception:
            pass
    if not candidates:
        return None
    # When several historic copies exist, use the most recently modified healthy Core DB.
    return sorted(candidates, key=lambda item: item[0], reverse=True)[0][1]


def _default_scan_roots() -> list[Path]:
    raw = str(os.environ.get("AGAPE_RECOVERY_ROOTS") or "").strip()
    if raw:
        return [Path(x).expanduser() for x in raw.split(os.pathsep) if x.strip()]

    home = Path.home()
    local = Path(os.environ.get("LOCALAPPDATA", str(home / "AppData" / "Local")))
    docs: list[Path] = [home / "Documents", home / "OneDrive" / "Documents"]
    one = str(os.environ.get("OneDrive") or os.environ.get("OneDriveConsumer") or "").strip()
    if one:
        docs.insert(0, Path(one) / "Documents")

    roots: list[Path] = []
    for d in docs:
        roots += [
            d / "DMT-CORE-V3.1",
            d / "DMT-AI-BUILDER-STUDIO",
            d / "AGAPE-DATABASE-RECOVERY-BACKUPS",
        ]
        if d.is_dir():
            try:
                roots.extend(p for p in d.glob("AGAPE-*") if p.is_dir())
            except Exception:
                pass
    roots += [local / "DMT-Core-V3.1", local / "Agape-V3.1-Integration-R1"]

    out: list[Path] = []
    seen: set[str] = set()
    for p in roots:
        key = str(p).casefold()
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


_SKIP_PATH_PARTS = {
    "test-data", "_installer-test-data", "isolated-data", "startup-check",
    "pytest", "fixtures", "fixture", "__pycache__",
}


def _skip_path(path: Path) -> bool:
    parts = {_norm(x) for x in path.parts}
    if parts & _SKIP_PATH_PARTS:
        return True
    # Do not reject a path merely because it lives under the OS Temp directory.
    # The Windows installer stages its isolated recovery fixtures under %TEMP%, and
    # explicit recovery roots may legitimately be temporary folders. We already
    # exclude known fixture/cache directory names above, while normal recovery
    # only scans the narrow roots returned by _default_scan_roots().
    return False


def discover_project_databases(target: Path | None = None, roots: Iterable[Path] | None = None) -> list[Path]:
    roots = list(roots) if roots is not None else _default_scan_roots()
    target_key = str(target.resolve()).casefold() if target and target.exists() else ""
    found: dict[str, Path] = {}
    wanted = {"dmt_core.sqlite3", "dmt_memory.sqlite3"}
    prune = {"node_modules", ".git", ".venv", "venv", "__pycache__", "build", "dist", "site-packages"}
    for root in roots:
        if not root.is_dir():
            continue
        try:
            for dirpath, dirnames, filenames in os.walk(root):
                here = Path(dirpath)
                dirnames[:] = [d for d in dirnames if _norm(d) not in prune and not _skip_path(here / d)]
                for filename in filenames:
                    if filename.casefold() not in wanted:
                        continue
                    p = here / filename
                    try:
                        if _skip_path(p):
                            continue
                        key = str(p.resolve()).casefold()
                        if target_key and key == target_key:
                            continue
                        if p.is_file() and p.stat().st_size > 0 and _valid_project_db(p):
                            found[key] = p
                    except Exception:
                        continue
        except Exception:
            continue
    return sorted(found.values(), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)


def _project_is_recoverable(row: dict[str, Any]) -> bool:
    name = str(row.get("name") or "").strip()
    if not name:
        return False
    kind = _norm(row.get("kind") or "user")
    hidden = _norm(row.get("hidden_reason") or "")
    lower = name.casefold()
    if kind in {"template", "test", "system", "autodev"}:
        return False
    if hidden in {"template_workflow", "system", "test", "autodev"}:
        return False
    if lower.startswith("template ") or "system stress test" in lower or "snake game" in lower:
        return False
    if any(x in lower for x in ("crash recovery mock", "rollback mock project", "loop mock project")) or lower.startswith("r4 integration "):
        return False
    return True


def _fetch_projects(con: sqlite3.Connection) -> list[dict[str, Any]]:
    con.row_factory = sqlite3.Row
    return [dict(r) for r in con.execute("SELECT * FROM projects ORDER BY id").fetchall()]


def _message_fingerprint(row: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        str(row.get("role") or "user").strip().lower(),
        str(row.get("provider") or ""),
        str(row.get("model") or ""),
        str(row.get("content") or ""),
        str(row.get("created_at") or ""),
    )


def _open_ro(path: Path) -> sqlite3.Connection:
    uri = "file:" + str(path).replace("\\", "/") + "?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=8)
    con.row_factory = sqlite3.Row
    return con


def _backup_database(target: Path) -> Path:
    local = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    root = Path(os.environ.get("AGAPE_RECOVERY_BACKUP_ROOT", str(local / "Agape-Backups" / "project-recovery")))
    root.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dst = root / f"{target.stem}-before-project-recovery-{stamp}.sqlite3"
    src_con = sqlite3.connect(str(target), timeout=30)
    dst_con = sqlite3.connect(str(dst))
    try:
        src_con.backup(dst_con)
    finally:
        dst_con.close(); src_con.close()
    return dst


def _write_report(report: dict[str, Any]) -> str:
    local = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    root = Path(os.environ.get("AGAPE_RECOVERY_REPORT_ROOT", str(local / "Agape-Mainframe-V3" / "data" / "recovery")))
    root.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = root / f"project-recovery-{stamp}.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return str(path)


def recover_past_projects(target_db: Path | str | None = None, roots: Iterable[Path] | None = None, dry_run: bool = False) -> dict[str, Any]:
    target = Path(target_db).expanduser() if target_db else find_live_core_db()
    if not target or not target.is_file():
        return {"ok": False, "error": "LIVE_CORE_DATABASE_NOT_FOUND", "projects_added": 0, "messages_added": 0}
    if not _valid_project_db(target):
        return {"ok": False, "error": "LIVE_CORE_DATABASE_FAILED_QUICK_CHECK", "target_database": str(target), "projects_added": 0, "messages_added": 0}

    sources = discover_project_databases(target=target, roots=roots)
    report: dict[str, Any] = {
        "ok": True,
        "dry_run": bool(dry_run),
        "target_database": str(target),
        "databases_scanned": len(sources),
        "source_databases_used": [],
        "projects_added": 0,
        "projects_merged": 0,
        "messages_added": 0,
        "loop_settings_added": 0,
        "recovered_projects": [],
        "skipped_projects": [],
        "backup": "",
        "report": "",
    }
    if dry_run:
        for source in sources:
            try:
                con = _open_ro(source)
                try:
                    rows = [r for r in _fetch_projects(con) if _project_is_recoverable(r)]
                finally:
                    con.close()
                if rows:
                    report["source_databases_used"].append(str(source))
                    report["recovered_projects"].extend(str(r.get("name") or "") for r in rows)
            except Exception:
                continue
        report["recovered_projects"] = sorted(set(report["recovered_projects"]), key=str.casefold)
        report["report"] = _write_report(report)
        return report

    report["backup"] = str(_backup_database(target))
    target_con = sqlite3.connect(str(target), timeout=30)
    target_con.row_factory = sqlite3.Row
    target_con.execute("PRAGMA busy_timeout=30000")
    target_tables = _table_names(target_con)
    if "projects" not in target_tables or "messages" not in target_tables:
        target_con.close()
        report.update(ok=False, error="LIVE_CORE_SCHEMA_MISSING_PROJECT_TABLES")
        report["report"] = _write_report(report)
        return report

    try:
        target_con.execute("BEGIN IMMEDIATE")
        existing_projects = { _norm(r["name"]): dict(r) for r in target_con.execute("SELECT * FROM projects").fetchall() }
        existing_message_cache: dict[int, set[tuple[str,str,str,str,str]]] = {}

        for source in sources:
            try:
                src = _open_ro(source)
            except Exception:
                continue
            used = False
            try:
                src_tables = _table_names(src)
                src_projects = _fetch_projects(src)
                for old in src_projects:
                    if not _project_is_recoverable(old):
                        continue
                    name = str(old.get("name") or "").strip()
                    key = _norm(name)
                    if not key:
                        continue
                    old_id = int(old.get("id") or 0)
                    current = existing_projects.get(key)
                    if current:
                        new_id = int(current["id"])
                        report["projects_merged"] += 1
                    else:
                        created = str(old.get("created_at") or "") or time.strftime("%Y-%m-%d %H:%M:%S")
                        updated = str(old.get("updated_at") or "") or created
                        cur = target_con.execute(
                            "INSERT INTO projects(name,created_at,updated_at,kind,archived,hidden_reason) VALUES(?,?,?,?,0,'')",
                            (name, created, updated, "user"),
                        )
                        new_id = int(cur.lastrowid)
                        current = {"id": new_id, "name": name}
                        existing_projects[key] = current
                        report["projects_added"] += 1
                        report["recovered_projects"].append(name)
                    used = True

                    if new_id not in existing_message_cache:
                        existing_message_cache[new_id] = {
                            _message_fingerprint(dict(r)) for r in target_con.execute(
                                "SELECT role,provider,model,content,created_at FROM messages WHERE project_id=?", (new_id,)
                            ).fetchall()
                        }
                    fingerprints = existing_message_cache[new_id]
                    if "messages" in src_tables and old_id > 0:
                        msg_cols = _columns(src, "messages")
                        if "project_id" in msg_cols and "content" in msg_cols:
                            rows = [dict(r) for r in src.execute("SELECT * FROM messages WHERE project_id=? ORDER BY id", (old_id,)).fetchall()]
                            for msg in rows:
                                content = str(msg.get("content") or "")
                                if not content.strip():
                                    continue
                                role = str(msg.get("role") or "user").strip().lower()
                                if role == "system": role = "tool"
                                if role not in {"user", "assistant", "tool"}: role = "user"
                                clean = {
                                    "role": role,
                                    "provider": str(msg.get("provider") or ""),
                                    "model": str(msg.get("model") or ""),
                                    "content": content,
                                    "created_at": str(msg.get("created_at") or "") or time.strftime("%Y-%m-%d %H:%M:%S"),
                                }
                                fp = _message_fingerprint(clean)
                                if fp in fingerprints:
                                    continue
                                target_con.execute(
                                    "INSERT INTO messages(project_id,role,provider,model,content,created_at) VALUES(?,?,?,?,?,?)",
                                    (new_id, clean["role"], clean["provider"], clean["model"], clean["content"], clean["created_at"]),
                                )
                                fingerprints.add(fp)
                                report["messages_added"] += 1

                    if "project_loop_settings" in src_tables and "project_loop_settings" in target_tables and old_id > 0:
                        exists = target_con.execute("SELECT 1 FROM project_loop_settings WHERE project_id=?", (new_id,)).fetchone()
                        if not exists:
                            row = src.execute("SELECT * FROM project_loop_settings WHERE project_id=?", (old_id,)).fetchone()
                            if row:
                                d = dict(row)
                                target_con.execute(
                                    "INSERT INTO project_loop_settings(project_id,workspace,goal,test_command,max_steps,auto_model,model,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                                    (new_id, str(d.get("workspace") or ""), str(d.get("goal") or ""), str(d.get("test_command") or ""), int(d.get("max_steps") or 4), 1 if d.get("auto_model",1) else 0, str(d.get("model") or ""), str(d.get("updated_at") or "") or time.strftime("%Y-%m-%d %H:%M:%S")),
                                )
                                report["loop_settings_added"] += 1
                if used:
                    report["source_databases_used"].append(str(source))
            except Exception as exc:
                report.setdefault("source_errors", []).append({"database": str(source), "error": f"{type(exc).__name__}: {exc}"})
            finally:
                try: src.close()
                except Exception: pass

        target_con.commit()
    except Exception:
        target_con.rollback()
        raise
    finally:
        target_con.close()

    report["recovered_projects"] = sorted(set(report["recovered_projects"]), key=str.casefold)
    report["report"] = _write_report(report)
    return report


def _cli() -> int:
    try:
        result = recover_past_projects()
        print("PROJECT_RECOVERY_RESULT=" + json.dumps(result, ensure_ascii=False, default=str), flush=True)
        if result.get("ok"):
            print(f"PROJECT_RECOVERY=PASS projects_added={result.get('projects_added',0)} messages_added={result.get('messages_added',0)} databases_scanned={result.get('databases_scanned',0)}", flush=True)
            if result.get("recovered_projects"):
                print("RECOVERED_PROJECTS=" + ", ".join(result.get("recovered_projects") or []), flush=True)
            if result.get("backup"):
                print("RECOVERY_BACKUP=" + str(result.get("backup")), flush=True)
            if result.get("report"):
                print("RECOVERY_REPORT=" + str(result.get("report")), flush=True)
            return 0
        if result.get("error") == "LIVE_CORE_DATABASE_NOT_FOUND":
            print("PROJECT_RECOVERY=SKIP no previous Core database found", flush=True)
            return 0
        print("PROJECT_RECOVERY=FAIL " + str(result.get("error") or "unknown"), flush=True)
        return 3
    except Exception as exc:
        print(f"PROJECT_RECOVERY=FAIL {type(exc).__name__}: {exc}", flush=True)
        return 4


if __name__ == "__main__":
    raise SystemExit(_cli())
