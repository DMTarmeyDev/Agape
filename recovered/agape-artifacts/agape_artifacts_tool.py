from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import secrets
import sqlite3
import subprocess
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

MODULE = "AGAPE-ARTIFACTS-R3.1"
PROJECT = None
DATA_ROOT = None
DATABASE = None
PORT = None
TOKEN = secrets.token_urlsafe(32)

ARTIFACT_TYPES = {
    "BUILD", "RELEASE", "CHECKPOINT", "DATABASE_BACKUP",
    "TEST_REPORT", "TEMPLATE", "INSTRUCTIONS",
    "PROJECT_SUMMARY", "SCREENSHOT", "EXPORT", "OTHER",
}

VALID_STATUS = {
    "CURRENT", "LAST_KNOWN_GOOD", "RELEASE",
    "ARCHIVED", "FAILED",
}

SOURCE_EXTENSIONS = {
    ".py", ".js", ".css", ".html", ".ps1", ".cmd", ".bat"
}

SKIP_DIR_NAMES = {
    "__pycache__", ".pytest_cache", "node_modules",
    ".git", ".venv", "venv", "cache", "temp",
}

def utc_now():
    return datetime.now(timezone.utc).isoformat()

def connect():
    con = sqlite3.connect(str(DATABASE), timeout=30)
    con.row_factory = sqlite3.Row
    return con

def table_columns(con, table):
    return {
        str(row[1])
        for row in con.execute(f'PRAGMA table_info("{table}")').fetchall()
    }

def ensure_column(con, table, name, definition):
    if name not in table_columns(con, table):
        con.execute(
            f'ALTER TABLE "{table}" ADD COLUMN "{name}" {definition}'
        )

def initialize_database():
    con = connect()
    try:
        con.execute("""
            CREATE TABLE IF NOT EXISTS artifacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT,
                artifact_type TEXT NOT NULL DEFAULT 'OTHER',
                name TEXT NOT NULL,
                path TEXT NOT NULL,
                sha256 TEXT,
                size_bytes INTEGER,
                version TEXT,
                git_commit TEXT,
                git_branch TEXT,
                created_by_task TEXT,
                test_status TEXT NOT NULL DEFAULT 'UNKNOWN',
                status TEXT NOT NULL DEFAULT 'CURRENT',
                notes TEXT,
                training_eligible INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                verified_at TEXT,
                UNIQUE(path, sha256)
            )
        """)

        for name, definition in {
            "path_kind": "TEXT",
            "hash_method": "TEXT",
            "source_origin": "TEXT",
            "discovery_status": "TEXT",
            "last_seen_at": "TEXT",
            "manifest_build": "TEXT",
            "git_repo": "TEXT",
            "git_remote": "TEXT",
            "auto_discovered": "INTEGER NOT NULL DEFAULT 0",
            "missing": "INTEGER NOT NULL DEFAULT 0",
            "metadata_json": "TEXT",
        }.items():
            ensure_column(con, "artifacts", name, definition)

        con.execute("""
            CREATE TABLE IF NOT EXISTS artifact_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                artifact_id INTEGER,
                event_type TEXT NOT NULL,
                details TEXT,
                created_at TEXT NOT NULL
            )
        """)

        con.execute("CREATE INDEX IF NOT EXISTS idx_artifacts_type_r21 ON artifacts(artifact_type)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_artifacts_status_r21 ON artifacts(status)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_artifacts_discovery_r21 ON artifacts(discovery_status)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_artifacts_path_r21 ON artifacts(path)")
        con.commit()
    finally:
        con.close()

def event(con, artifact_id, event_type, details=""):
    con.execute("""
        INSERT INTO artifact_events (
            artifact_id,event_type,details,created_at
        ) VALUES (?,?,?,?)
    """, (artifact_id, event_type, str(details or ""), utc_now()))

def sha256_file(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().upper()

def directory_fingerprint(path):
    manifest = path / "manifest.json"
    if manifest.exists() and manifest.is_file():
        return sha256_file(manifest), manifest.stat().st_size, "MANIFEST_SHA256"

    h = hashlib.sha256()
    total = 0
    entries = []

    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d.lower() not in SKIP_DIR_NAMES]
        root_path = Path(root)

        for name in files:
            p = root_path / name
            try:
                rel = str(p.relative_to(path)).replace("\\", "/")
                size = p.stat().st_size
                total += size
                entries.append((rel, size))
            except Exception:
                pass

    for rel, size in sorted(entries):
        p = path / Path(rel)
        h.update(rel.encode("utf-8", errors="replace"))
        h.update(b"|")
        h.update(str(size).encode("ascii"))
        h.update(b"|")
        try:
            # Meaningful artifact bundles are normally small. Hash their
            # contents so verification detects same-size edits too.
            if size <= 256 * 1024 * 1024:
                h.update(sha256_file(p).encode("ascii"))
            else:
                h.update(b"LARGE_FILE_METADATA_ONLY")
        except Exception:
            h.update(b"HASH_UNAVAILABLE")
        h.update(b"\n")

    return h.hexdigest().upper(), total, "DIRECTORY_CONTENT_SHA256"

def fingerprint(path):
    if path.is_file():
        return sha256_file(path), path.stat().st_size, "FILE_SHA256", "FILE"
    if path.is_dir():
        digest, size, method = directory_fingerprint(path)
        return digest, size, method, "DIRECTORY"
    raise FileNotFoundError(str(path))

def read_manifest():
    try:
        return json.loads(
            (PROJECT / "manifest.json").read_text(encoding="utf-8-sig")
        )
    except Exception:
        return {}

def manifest_files():
    value = read_manifest().get("files")
    if not isinstance(value, dict):
        return {}
    return {
        str(k).replace("\\", "/"): str(v)
        for k, v in value.items()
    }

def manifest_features():
    value = read_manifest().get("features")
    return [str(x) for x in value] if isinstance(value, list) else []

def recursive_values(obj, names):
    names = {
        str(x).lower().replace("-", "_")
        for x in names
    }
    found = []

    def walk(v):
        if isinstance(v, dict):
            for k, item in v.items():
                key = str(k).lower().replace("-", "_")
                if key in names:
                    found.append(item)
                walk(item)
        elif isinstance(v, list):
            for item in v:
                walk(item)

    walk(obj)
    return found

def first_manifest_value(names, default=""):
    for value in recursive_values(read_manifest(), names):
        if value not in (None, "", [], {}):
            return value
    return default

def manifest_summary():
    manifest = read_manifest()
    files = manifest_files()
    features = manifest_features()

    return {
        "build": first_manifest_value({"build", "version"}, ""),
        "architecture": first_manifest_value(
            {"architecture", "arch"}, "modular-core-v1"
        ),
        "schema_version": first_manifest_value(
            {"schema_version", "schema"}, 9
        ),
        "baseline": first_manifest_value(
            {"baseline", "baseline_build", "based_on", "baselined_from"},
            "DMT-CORE-V3.0-ALPHA-R1",
        ),
        "default_provider": first_manifest_value(
            {"default_provider", "provider"}, "ollama"
        ),
        "fast_model": first_manifest_value(
            {"fast_model", "fast_ai_model"},
            "qwen2.5-coder:1.5b-instruct",
        ),
        "project_model": first_manifest_value(
            {"project_model", "dev_model", "development_model"},
            "qwen2.5-coder:7b",
        ),
        "tracked_files": len(files),
        "feature_count": len(features),
        "features": features,
        "source_files_are_artifacts": False,
    }

def manifest_integrity():
    tracked = manifest_files()
    result = {
        "total": len(tracked),
        "match": 0,
        "changed": 0,
        "missing": 0,
        "expected_integration_changes": [],
        "unexpected_changed_files": [],
        "missing_files": [],
    }

    for rel, expected in tracked.items():
        p = PROJECT / Path(rel)

        if not p.exists():
            result["missing"] += 1
            result["missing_files"].append(rel)
            continue

        if not p.is_file():
            continue

        try:
            current = sha256_file(p)
        except Exception:
            continue

        if current.upper() == str(expected).upper():
            result["match"] += 1
            continue

        # index.html is expected to differ when the Settings launcher
        # has been installed by Artifacts R3.1.
        if rel.replace("\\", "/").lower() == "index.html":
            try:
                text = p.read_text(encoding="utf-8-sig", errors="replace")
                if "AGAPE_ARTIFACTS_R31_SETTINGS_BEGIN" in text:
                    result["expected_integration_changes"].append(rel)
                    continue
            except Exception:
                pass

        result["changed"] += 1
        result["unexpected_changed_files"].append(rel)

    return result

def run_git(repo, *args):
    if not repo:
        return ""
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=(
                subprocess.CREATE_NO_WINDOW
                if os.name == "nt"
                else 0
            ),
        )
        return proc.stdout.strip() if proc.returncode == 0 else ""
    except Exception:
        return ""

def nearest_git_repo(path):
    current = path if path.is_dir() else path.parent
    for _ in range(12):
        if (current / ".git").exists():
            return current
        if current.parent == current:
            break
        current = current.parent
    return None

def git_metadata(path):
    repo = nearest_git_repo(path)
    if not repo:
        return {"repo": "", "branch": "", "commit": "", "remote": ""}
    return {
        "repo": str(repo),
        "branch": run_git(repo, "branch", "--show-current"),
        "commit": run_git(repo, "rev-parse", "HEAD"),
        "remote": run_git(repo, "remote", "get-url", "origin"),
    }

def extract_version(name):
    for pattern in (
        r"(?i)\bv\d+(?:\.\d+)+(?:[-_.]r\d+)?\b",
        r"(?i)\br\d+\b",
    ):
        match = re.search(pattern, name)
        if match:
            return match.group(0)
    return ""

def classify(path):
    name = path.name.lower()
    text = str(path).lower()
    suffix = path.suffix.lower()

    if path.is_dir():
        if (
            "rollback" in name
            or "checkpoint" in name
            or name.startswith("before-")
            or name.startswith("backup-")
        ):
            return "CHECKPOINT"
        if any(x in name for x in ("report", "result", "audit", "diagnostic", "evidence", "qa")):
            return "TEST_REPORT"
        if "release" in name or name == "dist":
            return "RELEASE"
        if "build" in name:
            return "BUILD"
        if "export" in name:
            return "EXPORT"
        return "OTHER"

    if suffix in {".sqlite3", ".db"} and (
        "database-backup" in text
        or "database_backups" in text
        or "database-backups" in text
        or "backup" in name
        or "before-" in name
    ):
        return "DATABASE_BACKUP"

    if "project_summary" in name or "project-summary" in name:
        return "PROJECT_SUMMARY"

    if (
        "instruction" in name
        or "project_rules" in name
        or "project-rules" in name
    ):
        return "INSTRUCTIONS"

    if "template" in name:
        return "TEMPLATE"

    if suffix in {".png", ".jpg", ".jpeg"} and (
        "screenshot" in name or "evidence" in text
    ):
        return "SCREENSHOT"

    if "export" in name:
        return "EXPORT"

    if (
        "release" in name
        or "installer" in name
        or "one-package" in name
        or "one_package" in name
        or "onefile" in name
        or "one-file" in name
        or "recovery" in name
    ):
        return "RELEASE"

    if suffix in {".zip", ".7z", ".gz", ".tar", ".iso", ".bin", ".elf"}:
        return "BUILD"

    return "OTHER"


def is_manifest_source_file(path):
    try:
        rel = str(path.resolve().relative_to(PROJECT.resolve())).replace("\\", "/")
    except Exception:
        return False
    return rel in manifest_files()


def is_real_artifact(path):
    if path.resolve() == DATABASE.resolve():
        return False

    if path.name.lower() in {
        "manifest.json",
        "agape_artifacts_tool.py",
        "start-agape-artifacts.ps1",
        "agape-artifacts-config.json",
        "artifacts_module.py",
    }:
        return False

    if path.is_file() and is_manifest_source_file(path):
        return False

    return classify(path) != "OTHER"


def immediate_children_as_bundles(container, artifact_type, origin, candidates):
    if not container.exists() or not container.is_dir():
        return

    try:
        children = sorted(container.iterdir(), key=lambda p: p.name.lower())
    except Exception:
        return

    for child in children:
        lower = str(child).lower()

        if (
            "modularos" in lower
            or "dmt-modularos" in lower
            or "\\chitti\\" in lower
            or "/chitti/" in lower
            or "tinyai" in lower
        ):
            continue

        if child.is_dir():
            candidates[str(child.resolve())] = (child, artifact_type, origin)
            continue

        # Loose files directly in a known output folder may still be meaningful.
        kind = classify(child)
        if kind != "OTHER":
            candidates[str(child.resolve())] = (child, kind, origin)


def find_named_output_containers(root, max_depth=3):
    wanted = {
        "reports": "TEST_REPORT",
        "report": "TEST_REPORT",
        "results": "TEST_REPORT",
        "test-results": "TEST_REPORT",
        "test_results": "TEST_REPORT",
        "qa": "TEST_REPORT",
        "audits": "TEST_REPORT",
        "diagnostics": "TEST_REPORT",
        "evidence": "TEST_REPORT",
        "releases": "RELEASE",
        "release": "RELEASE",
        "dist": "RELEASE",
        "builds": "BUILD",
        "checkpoints": "CHECKPOINT",
        "exports": "EXPORT",
    }

    root = Path(root)
    if not root.exists() or not root.is_dir():
        return []

    found = []

    for current, dirs, _files in os.walk(root):
        current_path = Path(current)
        try:
            depth = len(current_path.relative_to(root).parts)
        except Exception:
            depth = 0

        dirs[:] = [
            d for d in dirs
            if d.lower() not in SKIP_DIR_NAMES
            and d.lower() not in {"tests", "test", "fixtures", "site-packages"}
        ]

        if depth >= max_depth:
            dirs[:] = []
            continue

        for d in list(dirs):
            key = d.lower()
            if key in wanted:
                found.append((current_path / d, wanted[key]))

    # De-duplicate nested hits by path.
    unique = {}
    for path, artifact_type in found:
        unique[str(path.resolve())] = (path, artifact_type)
    return list(unique.values())


def candidate_artifacts():
    home = Path.home()
    local_core = PROJECT.parent.parent
    candidates = {}

    def add(path, artifact_type, origin):
        path = Path(path)
        if not path.exists():
            return
        lower = str(path).lower()
        if (
            "modularos" in lower
            or "dmt-modularos" in lower
            or "\\chitti\\" in lower
            or "/chitti/" in lower
            or "tinyai" in lower
        ):
            return
        candidates[str(path.resolve())] = (path, artifact_type, origin)

    # 1. Whole rollback/backup folders become one checkpoint each.
    for base in (
        PROJECT.parent,
        local_core / "backups",
        DATA_ROOT / "artifact-manager-backups",
        home / "Documents" / "DMT-CHECKPOINTS",
    ):
        if not base.exists() or not base.is_dir():
            continue
        try:
            for child in base.iterdir():
                if not child.is_dir():
                    continue
                lower = child.name.lower()
                if (
                    "rollback" in lower
                    or "checkpoint" in lower
                    or lower.startswith("before-")
                    or lower.startswith("backup-")
                ):
                    add(child, "CHECKPOINT", "CHECKPOINT_BUNDLE")
        except Exception:
            pass

    # 2. Real database backups remain individually verifiable artifacts.
    for db_root in (
        DATA_ROOT / "database-backups",
        DATA_ROOT / "database_backups",
    ):
        if not db_root.exists():
            continue
        try:
            for p in db_root.rglob("*"):
                if p.is_file() and p.suffix.lower() in {".sqlite3", ".db"}:
                    add(p, "DATABASE_BACKUP", "DATABASE_BACKUPS")
        except Exception:
            pass

    # 3. Artifact exports are explicit outputs.
    export_root = DATA_ROOT / "artifact-exports"
    if export_root.exists():
        try:
            for p in export_root.iterdir():
                if p.is_file():
                    add(p, "EXPORT", "ARTIFACT_EXPORTS")
        except Exception:
            pass

    # 4. Project identity/control documents only - not normal source files.
    control_patterns = (
        "project_summary", "project-summary",
        "project_rules", "project-rules",
        "project_instruction", "project-instruction",
        "instructions", "template",
    )
    for base in (PROJECT, DATA_ROOT):
        if not base.exists():
            continue
        try:
            for p in base.iterdir():
                if not p.is_file():
                    continue
                lower = p.name.lower()
                if p.suffix.lower() not in {".md", ".txt", ".json", ".yaml", ".yml", ".toml"}:
                    continue
                if is_manifest_source_file(p):
                    continue
                if any(token in lower for token in control_patterns):
                    kind = classify(p)
                    if kind != "OTHER":
                        add(p, kind, "PROJECT_CONTROL")
        except Exception:
            pass

    # 5. Downloads: packages/installers only. Loose development scripts and
    #    test files are intentionally excluded from automatic discovery.
    downloads = home / "Downloads"
    if downloads.exists():
        try:
            for p in downloads.iterdir():
                if not p.is_file():
                    continue
                lower = p.name.lower()
                if not ("agape" in lower or "dmt" in lower):
                    continue
                package_ext = p.suffix.lower() in {".zip", ".7z", ".tar", ".gz", ".iso"}
                installer_name = any(x in lower for x in (
                    "installer", "install", "onefile", "one-file",
                    "one-package", "recovery", "release"
                ))
                if package_ext or (p.suffix.lower() == ".ps1" and installer_name):
                    add(p, "RELEASE" if installer_name else "BUILD", "DOWNLOAD_PACKAGE")
        except Exception:
            pass

    # 6. Related Agape-era source projects contribute only their known output
    #    containers. We do not crawl their source/test fixture trees.
    related_roots = []
    docs = home / "Documents"
    one = home / "OneDrive" / "Documents"

    for parent in (docs, one):
        if not parent.exists():
            continue
        try:
            for child in parent.iterdir():
                if not child.is_dir():
                    continue
                lower = child.name.lower()
                if lower.startswith((
                    "dmt-ai-builder", "dmt-ai-router", "dmt-core", "agape"
                )):
                    related_roots.append(child)
        except Exception:
            pass

    for root in related_roots:
        for container, artifact_type in find_named_output_containers(root, 3):
            immediate_children_as_bundles(
                container,
                artifact_type,
                "RELATED_OUTPUT_BUNDLE",
                candidates,
            )

    return list(candidates.values())


def upsert(
    path,
    artifact_type,
    origin,
    auto=True,
    project_id="Agape",
    notes="",
    test_status="UNKNOWN",
    status="CURRENT",
    training_eligible=False,
):
    path = path.resolve()
    digest, size, hash_method, path_kind = fingerprint(path)
    git = git_metadata(path)
    manifest = manifest_summary()
    now = utc_now()

    con = connect()

    try:
        previous = con.execute("""
            SELECT * FROM artifacts
            WHERE path=?
            ORDER BY id DESC
            LIMIT 1
        """, (str(path),)).fetchone()

        same = con.execute("""
            SELECT * FROM artifacts
            WHERE path=? AND sha256=?
            ORDER BY id DESC
            LIMIT 1
        """, (str(path), digest)).fetchone()

        if same:
            con.execute("""
                UPDATE artifacts
                SET
                    size_bytes=?,
                    verified_at=?,
                    last_seen_at=?,
                    discovery_status='REGISTERED',
                    missing=0,
                    path_kind=?,
                    hash_method=?,
                    source_origin=?,
                    manifest_build=?,
                    git_repo=?,
                    git_remote=?,
                    git_commit=?,
                    git_branch=?
                WHERE id=?
            """, (
                int(size), now, now, path_kind, hash_method, origin,
                manifest.get("build", ""), git["repo"], git["remote"],
                git["commit"], git["branch"], int(same["id"]),
            ))
            con.commit()
            row = con.execute(
                "SELECT * FROM artifacts WHERE id=?",
                (int(same["id"]),),
            ).fetchone()
            return dict(row)

        if previous:
            con.execute("""
                UPDATE artifacts
                SET status=CASE
                    WHEN status='LAST_KNOWN_GOOD' THEN status
                    ELSE 'ARCHIVED'
                END
                WHERE id=?
            """, (int(previous["id"]),))

        discovery = "HASH_CHANGED" if previous else "NEW"

        cur = con.execute("""
            INSERT INTO artifacts (
                project_id,artifact_type,name,path,sha256,size_bytes,
                version,git_commit,git_branch,created_by_task,
                test_status,status,notes,training_eligible,
                created_at,verified_at,path_kind,hash_method,
                source_origin,discovery_status,last_seen_at,
                manifest_build,git_repo,git_remote,auto_discovered,
                missing,metadata_json
            )
            VALUES (
                ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
            )
        """, (
            project_id,
            artifact_type,
            path.name,
            str(path),
            digest,
            int(size),
            extract_version(path.name),
            git["commit"],
            git["branch"],
            "AUTO_DISCOVERY" if auto else "MANUAL_REGISTRATION",
            test_status,
            status,
            notes,
            1 if training_eligible else 0,
            now,
            now,
            path_kind,
            hash_method,
            origin,
            discovery,
            now,
            manifest.get("build", ""),
            git["repo"],
            git["remote"],
            1 if auto else 0,
            0,
            json.dumps({
                "origin": origin,
                "hash_method": hash_method,
                "path_kind": path_kind,
            }),
        ))

        artifact_id = int(cur.lastrowid)
        event(con, artifact_id, discovery, str(path))
        con.commit()

        row = con.execute(
            "SELECT * FROM artifacts WHERE id=?",
            (artifact_id,),
        ).fetchone()

        return dict(row)
    finally:
        con.close()

def prune_auto_records(keep_paths):
    keep_paths = {str(Path(p).resolve()) for p in keep_paths}
    removed = 0
    manual_preserved = 0

    con = connect()
    try:
        manual_preserved = int(
            con.execute(
                "SELECT COUNT(*) FROM artifacts WHERE auto_discovered=0"
            ).fetchone()[0]
        )

        rows = con.execute(
            "SELECT id,path FROM artifacts WHERE auto_discovered=1"
        ).fetchall()

        for row in rows:
            path_text = str(row["path"] or "")
            try:
                normalized = str(Path(path_text).resolve())
            except Exception:
                normalized = path_text

            if normalized in keep_paths:
                continue

            artifact_id = int(row["id"])
            con.execute(
                "DELETE FROM artifact_events WHERE artifact_id=?",
                (artifact_id,),
            )
            con.execute(
                "DELETE FROM artifacts WHERE id=?",
                (artifact_id,),
            )
            removed += 1

        con.commit()
    finally:
        con.close()

    return removed, manual_preserved


def scan():
    initialize_database()

    candidates = candidate_artifacts()
    keep_paths = [str(path.resolve()) for path, _kind, _origin in candidates]
    removed, manual_preserved = prune_auto_records(keep_paths)

    observations = 0
    errors = 0

    for path, artifact_type, origin in candidates:
        try:
            upsert(path, artifact_type, origin, auto=True)
            observations += 1
        except Exception:
            errors += 1

    return {
        "ok": True,
        "candidate_count": len(candidates),
        "observations": observations,
        "errors": errors,
        "auto_records_pruned": removed,
        "manual_records_preserved": manual_preserved,
        "bundle_policy": "OUTPUT_FOLDERS_AS_SINGLE_ARTIFACTS",
        "dashboard": dashboard(),
    }


def list_artifacts(search="", artifact_type="", status="", discovery=""):
    where = []
    params = []

    if search:
        q = "%" + search + "%"
        where.append("""
            (
                name LIKE ? OR path LIKE ? OR notes LIKE ?
                OR sha256 LIKE ? OR source_origin LIKE ?
                OR git_remote LIKE ?
            )
        """)
        params.extend([q] * 6)

    if artifact_type:
        where.append("artifact_type=?")
        params.append(artifact_type)

    if status:
        where.append("status=?")
        params.append(status)

    if discovery:
        where.append("discovery_status=?")
        params.append(discovery)

    sql = "SELECT * FROM artifacts"

    if where:
        sql += " WHERE " + " AND ".join(where)

    sql += " ORDER BY id DESC LIMIT 1000"

    con = connect()
    try:
        rows = con.execute(sql, params).fetchall()
        return {
            "ok": True,
            "count": len(rows),
            "artifacts": [dict(row) for row in rows],
        }
    finally:
        con.close()

def grouped_count(con, field):
    allowed = {
        "artifact_type", "status",
        "discovery_status", "source_origin",
    }

    if field not in allowed:
        return {}

    return {
        str(row[0] or "UNKNOWN"): int(row[1])
        for row in con.execute(
            f"SELECT {field},COUNT(*) FROM artifacts GROUP BY {field}"
        ).fetchall()
    }

def dashboard():
    initialize_database()
    con = connect()

    try:
        count = int(
            con.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0]
        )

        training = int(
            con.execute("""
                SELECT COUNT(*) FROM artifacts
                WHERE training_eligible=1
            """).fetchone()[0]
        )

        return {
            "ok": True,
            "module": MODULE,
            "database": str(DATABASE),
            "artifact_count": count,
            "training_eligible_count": training,
            "by_type": grouped_count(con, "artifact_type"),
            "by_status": grouped_count(con, "status"),
            "by_discovery": grouped_count(con, "discovery_status"),
            "manifest": manifest_summary(),
            "manifest_integrity": manifest_integrity(),
            "excluded_projects": [
                "DMT ModularOS",
                "TinyAI OS",
                "CHITTI",
                "RNDIS / bare-metal networking",
            ],
        }
    finally:
        con.close()

def verify_one(artifact_id):
    artifact_id = int(artifact_id)
    con = connect()

    try:
        row = con.execute(
            "SELECT * FROM artifacts WHERE id=?",
            (artifact_id,),
        ).fetchone()

        if not row:
            raise ValueError("ARTIFACT_NOT_FOUND")

        record = dict(row)
        path = Path(record["path"])

        if not path.exists():
            con.execute("""
                UPDATE artifacts
                SET discovery_status='MISSING',
                    missing=1,
                    verified_at=?
                WHERE id=?
            """, (utc_now(), artifact_id))
            event(con, artifact_id, "VERIFY_MISSING", str(path))
            con.commit()

            return {
                "ok": False,
                "exists": False,
                "hash_match": False,
                "error": "MISSING",
            }

        digest, size, method, kind = fingerprint(path)
        match = (
            str(record.get("sha256") or "").upper()
            == digest.upper()
        )

        con.execute("""
            UPDATE artifacts
            SET verified_at=?,
                discovery_status=?,
                missing=0,
                size_bytes=?,
                path_kind=?,
                hash_method=?
            WHERE id=?
        """, (
            utc_now(),
            "REGISTERED" if match else "HASH_CHANGED",
            int(size),
            kind,
            method,
            artifact_id,
        ))

        event(
            con,
            artifact_id,
            "VERIFY_PASS" if match else "VERIFY_HASH_CHANGED",
            digest,
        )

        con.commit()

        return {
            "ok": True,
            "exists": True,
            "hash_match": match,
            "stored_sha256": record.get("sha256"),
            "current_sha256": digest,
            "hash_method": method,
        }
    finally:
        con.close()

def verify_all():
    con = connect()
    try:
        ids = [
            int(row[0])
            for row in con.execute("SELECT id FROM artifacts").fetchall()
        ]
    finally:
        con.close()

    passed = changed = missing = 0

    for artifact_id in ids:
        result = verify_one(artifact_id)

        if not result.get("exists"):
            missing += 1
        elif result.get("hash_match"):
            passed += 1
        else:
            changed += 1

    return {
        "ok": True,
        "total": len(ids),
        "pass": passed,
        "hash_changed": changed,
        "missing": missing,
    }

def manual_register(data):
    path_text = str(data.get("path") or "").strip()
    if not path_text:
        raise ValueError("PATH_REQUIRED")

    path = Path(path_text).expanduser()
    if not path.exists():
        raise ValueError("PATH_NOT_FOUND")

    artifact_type = str(
        data.get("artifact_type") or classify(path) or "OTHER"
    ).upper()

    if artifact_type not in ARTIFACT_TYPES:
        artifact_type = "OTHER"

    status = str(data.get("status") or "CURRENT").upper()
    if status not in VALID_STATUS:
        status = "CURRENT"

    return {
        "ok": True,
        "artifact": upsert(
            path,
            artifact_type,
            "MANUAL",
            auto=False,
            project_id=str(data.get("project_id") or "Agape"),
            notes=str(data.get("notes") or ""),
            test_status=str(data.get("test_status") or "UNKNOWN").upper(),
            status=status,
            training_eligible=bool(data.get("training_eligible", False)),
        ),
    }

def set_status(artifact_id, status):
    status = str(status or "").upper()
    if status not in VALID_STATUS:
        raise ValueError("INVALID_STATUS")

    artifact_id = int(artifact_id)
    con = connect()

    try:
        row = con.execute(
            "SELECT * FROM artifacts WHERE id=?",
            (artifact_id,),
        ).fetchone()

        if not row:
            raise ValueError("ARTIFACT_NOT_FOUND")

        if status == "LAST_KNOWN_GOOD":
            con.execute("""
                UPDATE artifacts
                SET status='CURRENT'
                WHERE project_id=?
                AND status='LAST_KNOWN_GOOD'
            """, (row["project_id"],))

        con.execute(
            "UPDATE artifacts SET status=? WHERE id=?",
            (status, artifact_id),
        )

        event(con, artifact_id, "STATUS", status)
        con.commit()

        updated = con.execute(
            "SELECT * FROM artifacts WHERE id=?",
            (artifact_id,),
        ).fetchone()

        return {"ok": True, "artifact": dict(updated)}
    finally:
        con.close()

def open_path(artifact_id):
    con = connect()
    try:
        row = con.execute(
            "SELECT path FROM artifacts WHERE id=?",
            (int(artifact_id),),
        ).fetchone()
    finally:
        con.close()

    if not row:
        raise ValueError("ARTIFACT_NOT_FOUND")

    p = Path(str(row["path"]))
    if not p.exists():
        raise ValueError("PATH_MISSING")

    if os.name == "nt":
        if p.is_file():
            subprocess.Popen(["explorer.exe", "/select,", str(p)])
        else:
            subprocess.Popen(["explorer.exe", str(p)])

    return {"ok": True, "path": str(p)}

def export_index():
    export_dir = DATA_ROOT / "artifact-exports"
    export_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    json_path = export_dir / f"agape-artifacts-{stamp}.json"
    csv_path = export_dir / f"agape-artifacts-{stamp}.csv"

    data = list_artifacts()["artifacts"]

    json_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )

    fields = sorted({
        key
        for item in data
        for key in item.keys()
    })

    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for item in data:
            writer.writerow(item)

    upsert(json_path, "EXPORT", "ARTIFACT_MANAGER", auto=False)
    upsert(csv_path, "EXPORT", "ARTIFACT_MANAGER", auto=False)

    return {
        "ok": True,
        "json": str(json_path),
        "csv": str(csv_path),
    }

HTML = r"""
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Agape Artifacts R3.1</title>
<style>
body{margin:0;background:#07101d;color:#e7edf6;font-family:system-ui,Segoe UI,Arial,sans-serif}
header{padding:18px 24px;background:#0c1727;border-bottom:1px solid #26364c;position:sticky;top:0;z-index:3}
header h1{margin:0;font-size:23px}
header small,.muted{color:#94a3b8}
main{max-width:1500px;margin:0 auto;padding:20px}
.card{background:#0d1828;border:1px solid #2a3a50;border-radius:13px;padding:16px;margin-bottom:14px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px}
.metric{background:#111f31;border:1px solid #2a3a50;border-radius:10px;padding:12px}
.metric b{display:block;font-size:12px;color:#93a4ba;margin-bottom:5px}
.metric span{font-size:17px}
.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
button,input,select,textarea{background:#101d2d;color:#e7edf6;border:1px solid #40536d;border-radius:8px;padding:8px 10px}
button{cursor:pointer}
button.primary{background:#1d4ed8}
button.good{background:#166534}
textarea{width:100%;min-height:70px}
table{width:100%;border-collapse:collapse;font-size:12px}
th,td{border-bottom:1px solid #27384d;padding:8px;vertical-align:top;text-align:left}
th{position:sticky;top:0;background:#0d1828}
.scroll{overflow:auto;max-height:62vh}
.good-text{color:#86efac}
.bad-text{color:#fca5a5}
.warn-text{color:#fde68a}
.path{min-width:300px;white-space:normal;overflow-wrap:anywhere}
.hash{font-family:ui-monospace,Consolas,monospace}
.rule{border-left:3px solid #3b82f6;padding-left:10px;margin:7px 0}
</style>
</head>
<body>
<header>
  <h1>Agape Artifacts R3.1</h1>
  <small>Builds, releases, checkpoints, backups, tests, instructions and project evidence</small>
</header>
<main>

<div class="card">
  <div class="row">
    <button class="primary" onclick="runScan()">Discover / Rescan</button>
    <button onclick="verifyAll()">Verify All</button>
    <button onclick="exportIndex()">Export Index</button>
    <button onclick="loadAll()">Refresh</button>
    <span id="message" class="muted"></span>
  </div>
</div>

<div class="card">
  <h2>Artifact Dashboard</h2>
  <div id="dashboard" class="grid"></div>
</div>

<div class="card">
  <h2>Source vs Artifacts</h2>
  <div class="rule">The manifest remains the source-integrity index. Normal tracked source files are not duplicated into Artifacts.</div>
  <div class="rule">Each rollback folder is represented as one CHECKPOINT artifact rather than hundreds of duplicate source files.</div>
  <div class="rule">Artifacts cover builds, releases, checkpoints, database backups, test reports, templates, instructions, summaries, screenshots and exports.</div>
  <div class="rule">ModularOS, TinyAI OS, CHITTI and bare-metal networking are excluded from Agape discovery by default.</div>
</div>

<div class="card">
  <h2>Live Manifest</h2>
  <div id="manifest" class="grid"></div>
  <div id="integrity" style="margin-top:12px"></div>
</div>

<div class="card">
  <h2>Register Artifact</h2>
  <div class="grid">
    <input id="manualProject" value="Agape" placeholder="Project">
    <select id="manualType">
      <option>BUILD</option><option>RELEASE</option><option>CHECKPOINT</option>
      <option>DATABASE_BACKUP</option><option>TEST_REPORT</option><option>TEMPLATE</option>
      <option>INSTRUCTIONS</option><option>PROJECT_SUMMARY</option><option>SCREENSHOT</option>
      <option>EXPORT</option><option>OTHER</option>
    </select>
    <select id="manualStatus">
      <option>CURRENT</option><option>LAST_KNOWN_GOOD</option>
      <option>RELEASE</option><option>ARCHIVED</option><option>FAILED</option>
    </select>
    <select id="manualTest">
      <option>UNKNOWN</option><option>PASS</option><option>FAIL</option><option>NOT_TESTED</option>
    </select>
  </div>
  <div style="margin-top:10px">
    <input id="manualPath" style="width:calc(100% - 22px)" placeholder="Full file or folder path">
  </div>
  <div style="margin-top:10px">
    <textarea id="manualNotes" placeholder="Notes / purpose"></textarea>
  </div>
  <label><input type="checkbox" id="manualTraining"> Eligible for future verified training dataset</label>
  <div style="margin-top:10px">
    <button class="primary" onclick="manualRegister()">Register</button>
  </div>
</div>

<div class="card">
  <h2>Artifacts</h2>
  <div class="row">
    <input id="search" placeholder="Search">
    <select id="filterType">
      <option value="">All types</option>
      <option>BUILD</option><option>RELEASE</option><option>CHECKPOINT</option>
      <option>DATABASE_BACKUP</option><option>TEST_REPORT</option><option>TEMPLATE</option>
      <option>INSTRUCTIONS</option><option>PROJECT_SUMMARY</option><option>SCREENSHOT</option>
      <option>EXPORT</option><option>OTHER</option>
    </select>
    <select id="filterStatus">
      <option value="">All statuses</option>
      <option>CURRENT</option><option>LAST_KNOWN_GOOD</option>
      <option>RELEASE</option><option>ARCHIVED</option><option>FAILED</option>
    </select>
    <select id="filterDiscovery">
      <option value="">All discovery states</option>
      <option>NEW</option><option>REGISTERED</option><option>HASH_CHANGED</option><option>MISSING</option>
    </select>
    <button onclick="loadArtifacts()">Search</button>
  </div>

  <div class="scroll" style="margin-top:12px">
    <table>
      <thead>
        <tr>
          <th>ID</th><th>Type</th><th>Name</th><th>Status</th><th>Discovery</th>
          <th>Test</th><th>Version</th><th>Kind</th><th>Origin</th>
          <th>Size</th><th>Git</th><th>SHA256</th><th>Path</th><th>Actions</th>
        </tr>
      </thead>
      <tbody id="artifactBody"></tbody>
    </table>
  </div>
</div>

</main>

<script>
let TOKEN='';

function esc(v){
  return String(v==null?'':v).replace(/[&<>"']/g,c=>({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
  }[c]));
}

function msg(v){document.getElementById('message').textContent=v;}

async function getJson(url){
  const r=await fetch(url);
  const d=await r.json();
  if(!r.ok || d.ok===false) throw new Error(d.error || ('HTTP '+r.status));
  return d;
}

async function postJson(url,body){
  const r=await fetch(url,{
    method:'POST',
    headers:{
      'Content-Type':'application/json',
      'X-Agape-Artifacts-Token':TOKEN
    },
    body:JSON.stringify(body||{})
  });
  const d=await r.json();
  if(!r.ok || d.ok===false) throw new Error(d.error || ('HTTP '+r.status));
  return d;
}

async function loadSession(){
  const d=await getJson('/api/session');
  TOKEN=d.token;
}

async function loadDashboard(){
  const d=await getJson('/api/dashboard');
  const di=d.by_discovery||{};
  const st=d.by_status||{};
  const mi=d.manifest_integrity||{};
  const m=d.manifest||{};

  document.getElementById('dashboard').innerHTML=
    '<div class="metric"><b>Artifacts</b><span>'+esc(d.artifact_count)+'</span></div>'+
    '<div class="metric"><b>New</b><span>'+esc(di.NEW||0)+'</span></div>'+
    '<div class="metric"><b>Hash Changed</b><span>'+esc(di.HASH_CHANGED||0)+'</span></div>'+
    '<div class="metric"><b>Missing</b><span>'+esc(di.MISSING||0)+'</span></div>'+
    '<div class="metric"><b>Last Known Good</b><span>'+esc(st.LAST_KNOWN_GOOD||0)+'</span></div>'+
    '<div class="metric"><b>Training Eligible</b><span>'+esc(d.training_eligible_count||0)+'</span></div>'+
    '<div class="metric"><b>Manifest Files</b><span>'+esc(mi.total||0)+'</span></div>'+
    '<div class="metric"><b>Manifest Matches</b><span>'+esc(mi.match||0)+'</span></div>';

  document.getElementById('manifest').innerHTML=
    '<div class="metric"><b>Build</b><span style="font-size:13px">'+esc(m.build)+'</span></div>'+
    '<div class="metric"><b>Architecture</b><span>'+esc(m.architecture)+'</span></div>'+
    '<div class="metric"><b>Schema</b><span>'+esc(m.schema_version)+'</span></div>'+
    '<div class="metric"><b>Baseline</b><span style="font-size:13px">'+esc(m.baseline)+'</span></div>'+
    '<div class="metric"><b>Provider</b><span>'+esc(m.default_provider)+'</span></div>'+
    '<div class="metric"><b>Fast Model</b><span style="font-size:12px">'+esc(m.fast_model)+'</span></div>'+
    '<div class="metric"><b>Project Model</b><span style="font-size:12px">'+esc(m.project_model)+'</span></div>'+
    '<div class="metric"><b>Features</b><span>'+esc(m.feature_count)+'</span></div>';

  let text=
    '<b>Source integrity:</b> '+
    '<span class="good-text">MATCH '+esc(mi.match||0)+'</span> | '+
    '<span class="warn-text">UNEXPECTED CHANGED '+esc(mi.changed||0)+'</span> | '+
    '<span class="bad-text">MISSING '+esc(mi.missing||0)+'</span>';

  if((mi.expected_integration_changes||[]).length){
    text += '<br><span class="muted">Expected Artifacts integration change: '+
      esc(mi.expected_integration_changes.join(', '))+'</span>';
  }

  if((mi.unexpected_changed_files||[]).length){
    text += '<br><b>Unexpected changed:</b> '+
      esc(mi.unexpected_changed_files.join(', '));
  }

  document.getElementById('integrity').innerHTML=text;
}

async function loadArtifacts(){
  const search=document.getElementById('search').value||'';
  const type=document.getElementById('filterType').value||'';
  const status=document.getElementById('filterStatus').value||'';
  const discovery=document.getElementById('filterDiscovery').value||'';

  const d=await getJson(
    '/api/artifacts?search='+encodeURIComponent(search)+
    '&type='+encodeURIComponent(type)+
    '&status='+encodeURIComponent(status)+
    '&discovery='+encodeURIComponent(discovery)
  );

  const body=document.getElementById('artifactBody');
  body.innerHTML='';

  (d.artifacts||[]).forEach(a=>{
    const tr=document.createElement('tr');
    const size=Number(a.size_bytes||0)>1048576
      ? (Number(a.size_bytes)/1048576).toFixed(2)+' MB'
      : Math.round(Number(a.size_bytes||0)/1024)+' KB';

    const git=[
      a.git_branch||'',
      a.git_commit ? String(a.git_commit).substring(0,10) : ''
    ].filter(Boolean).join(' / ');

    tr.innerHTML=
      '<td>'+esc(a.id)+'</td>'+
      '<td>'+esc(a.artifact_type)+'</td>'+
      '<td>'+esc(a.name)+'</td>'+
      '<td>'+esc(a.status)+'</td>'+
      '<td>'+esc(a.discovery_status)+'</td>'+
      '<td>'+esc(a.test_status)+'</td>'+
      '<td>'+esc(a.version)+'</td>'+
      '<td>'+esc(a.path_kind)+'</td>'+
      '<td>'+esc(a.source_origin)+'</td>'+
      '<td>'+esc(size)+'</td>'+
      '<td>'+esc(git)+'</td>'+
      '<td class="hash" title="'+esc(a.sha256)+'">'+esc(String(a.sha256||'').substring(0,12))+'</td>'+
      '<td class="path">'+esc(a.path)+'</td>'+
      '<td>'+
        '<button onclick="verifyOne('+Number(a.id)+')">Verify</button> '+
        '<button onclick="openOne('+Number(a.id)+')">Open</button> '+
        '<button class="good" onclick="setStatus('+Number(a.id)+',\'LAST_KNOWN_GOOD\')">Last Good</button> '+
        '<button onclick="setStatus('+Number(a.id)+',\'ARCHIVED\')">Archive</button>'+
      '</td>';

    body.appendChild(tr);
  });
}

async function runScan(){
  try{
    msg('Scanning...');
    const d=await postJson('/api/scan',{});
    msg('Discovery complete: '+d.observations+' kept, '+d.auto_records_pruned+' noisy auto records removed, '+d.manual_records_preserved+' manual preserved');
    await loadAll();
  }catch(e){msg('ERROR: '+e.message);}
}

async function verifyOne(id){
  try{
    const d=await getJson('/api/verify?id='+encodeURIComponent(id));
    alert(d.hash_match ? 'HASH MATCH' : 'HASH CHANGED');
    await loadAll();
  }catch(e){alert(e.message);await loadAll();}
}

async function verifyAll(){
  try{
    msg('Verifying...');
    const d=await postJson('/api/verify-all',{});
    msg('Verify: PASS '+d.pass+', changed '+d.hash_changed+', missing '+d.missing);
    await loadAll();
  }catch(e){msg('ERROR: '+e.message);}
}

async function openOne(id){
  try{await postJson('/api/open',{id:id});}
  catch(e){alert(e.message);}
}

async function setStatus(id,status){
  try{
    await postJson('/api/status',{id:id,status:status});
    await loadAll();
  }catch(e){alert(e.message);}
}

async function manualRegister(){
  try{
    msg('Registering...');
    await postJson('/api/register',{
      project_id:document.getElementById('manualProject').value,
      artifact_type:document.getElementById('manualType').value,
      status:document.getElementById('manualStatus').value,
      test_status:document.getElementById('manualTest').value,
      path:document.getElementById('manualPath').value,
      notes:document.getElementById('manualNotes').value,
      training_eligible:document.getElementById('manualTraining').checked
    });
    msg('Artifact registered');
    await loadAll();
  }catch(e){msg('ERROR: '+e.message);}
}

async function exportIndex(){
  try{
    const d=await postJson('/api/export',{});
    msg('Exported: '+d.json+' | '+d.csv);
    await loadAll();
  }catch(e){msg('ERROR: '+e.message);}
}

async function loadAll(){
  await Promise.all([loadDashboard(),loadArtifacts()]);
}

(async()=>{
  try{
    await loadSession();
    await loadAll();
  }catch(e){msg('STARTUP ERROR: '+e.message);}
})();
</script>
</body>
</html>
"""

def json_response(handler, data, code=200):
    raw = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(raw)))
    handler.end_headers()
    handler.wfile.write(raw)

def html_response(handler):
    raw = HTML.encode("utf-8")
    handler.send_response(200)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(raw)))
    handler.end_headers()
    handler.wfile.write(raw)

def read_json(handler):
    length = int(handler.headers.get("Content-Length", "0") or 0)
    if length <= 0:
        return {}
    raw = handler.rfile.read(length)
    return json.loads(raw.decode("utf-8")) if raw else {}

def protected(handler):
    supplied = handler.headers.get("X-Agape-Artifacts-Token", "")
    return secrets.compare_digest(str(supplied), str(TOKEN))

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        try:
            if path == "/":
                return html_response(self)

            if path == "/favicon.ico":
                self.send_response(204)
                self.end_headers()
                return

            if path == "/api/session":
                return json_response(self, {
                    "ok": True,
                    "module": MODULE,
                    "token": TOKEN,
                })

            if path == "/api/dashboard":
                return json_response(self, dashboard())

            if path == "/api/artifacts":
                return json_response(
                    self,
                    list_artifacts(
                        search=(query.get("search") or [""])[0],
                        artifact_type=(query.get("type") or [""])[0],
                        status=(query.get("status") or [""])[0],
                        discovery=(query.get("discovery") or [""])[0],
                    ),
                )

            if path == "/api/verify":
                return json_response(
                    self,
                    verify_one((query.get("id") or [""])[0]),
                )

            return json_response(
                self, {"ok": False, "error": "NOT_FOUND"}, 404
            )

        except Exception as exc:
            return json_response(
                self, {"ok": False, "error": str(exc)}, 400
            )

    def do_POST(self):
        path = urlparse(self.path).path

        if not protected(self):
            return json_response(
                self,
                {"ok": False, "error": "SESSION_TOKEN_REQUIRED"},
                403,
            )

        try:
            data = read_json(self)

            if path == "/api/scan":
                return json_response(self, scan())

            if path == "/api/verify-all":
                return json_response(self, verify_all())

            if path == "/api/register":
                return json_response(self, manual_register(data))

            if path == "/api/status":
                return json_response(
                    self,
                    set_status(data.get("id"), data.get("status")),
                )

            if path == "/api/open":
                return json_response(self, open_path(data.get("id")))

            if path == "/api/export":
                return json_response(self, export_index())

            return json_response(
                self, {"ok": False, "error": "NOT_FOUND"}, 404
            )

        except Exception as exc:
            return json_response(
                self, {"ok": False, "error": str(exc)}, 400
            )

def main():
    global PROJECT, DATA_ROOT, DATABASE, PORT

    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--data", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--port", required=True, type=int)
    args = parser.parse_args()

    PROJECT = Path(args.project).resolve()
    DATA_ROOT = Path(args.data).resolve()
    DATABASE = Path(args.database).resolve()
    PORT = int(args.port)

    initialize_database()

    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)

    print("AGAPE_ARTIFACTS_R3=READY", flush=True)
    print("PORT=" + str(PORT), flush=True)
    print("DATABASE=" + str(DATABASE), flush=True)

    server.serve_forever()

if __name__ == "__main__":
    main()