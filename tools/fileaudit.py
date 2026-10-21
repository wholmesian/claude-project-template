#!/usr/bin/env python3
"""fileaudit.py -- verified filesystem-change auditor for orchestrated agent work.

Python 3.9+, standard library only. Runs identically on Windows and Linux.

Subcommands:
    snapshot                     take a current inventory snapshot (baseline)
    diff --label L [--commit]    compare current disk state to the baseline
    record --label L             let a working agent log its own (unverified) claim

See tools/README.md for the intended workflow.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCRIPT_PATH = Path(__file__).resolve()
TOOLS_DIR = SCRIPT_PATH.parent
REPO_ROOT = TOOLS_DIR.parent
CHANGELOG_DIR = REPO_ROOT / ".changelog"
RUNS_DIR = CHANGELOG_DIR / "runs"
INVENTORY_PATH = CHANGELOG_DIR / "inventory.tsv"
INVENTORY_PREV_PATH = CHANGELOG_DIR / "inventory.prev.tsv"
CHANGELOG_MD_PATH = REPO_ROOT / "CHANGELOG.md"

EXCLUDED_DIR_NAMES = {
    "venv",
    ".git",
    ".changelog",
    "__pycache__",
    "node_modules",
    ".ipynb_checkpoints",
}
EXCLUDED_FILE_SUFFIXES = (".pyc",)
EXCLUDED_FILE_NAMES = {".DS_Store", "Thumbs.db"}
EXCLUDED_EXACT_FILENAME = ".env"  # never hash/record the .env file itself

LARGE_FILE_THRESHOLD = 8 * 1024 * 1024  # 8 MB
CHUNK_SIZE = 1024 * 1024  # 1 MB

INVENTORY_HEADER_RE = re.compile(r"^# fileaudit v1 ")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_now_for_filename() -> str:
    # ISO-ish timestamp, colons replaced with '-' so it is filesystem-safe on Windows.
    return utc_now_iso().replace(":", "-")


def sanitize_label(label: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", label)


# ---------------------------------------------------------------------------
# Path classification / walking
# ---------------------------------------------------------------------------

def to_posix_rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def is_excluded(rel_posix: str, filename: str) -> bool:
    parts = rel_posix.split("/")
    # any path component (except the last, the filename itself) matching an excluded dir
    for part in parts[:-1]:
        if part in EXCLUDED_DIR_NAMES:
            return True
    # also allow exclusion if the top-level segment itself is the excluded dir
    # (covers e.g. "venv" as a bare top-level match too, already handled above)
    if filename in EXCLUDED_FILE_NAMES:
        return True
    if any(filename.endswith(suf) for suf in EXCLUDED_FILE_SUFFIXES):
        return True
    if filename == EXCLUDED_EXACT_FILENAME:
        return True
    return False


def iter_repo_files(root: Path):
    """Yield (abs_path, rel_posix) for every non-excluded file under root."""
    for dirpath, dirnames, filenames in _walk(root):
        # prune excluded directories in-place so os.walk-style traversal skips them
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIR_NAMES]
        for filename in filenames:
            abs_path = dirpath / filename
            try:
                rel_posix = to_posix_rel(abs_path, root)
            except ValueError:
                continue
            if is_excluded(rel_posix, filename):
                continue
            yield abs_path, rel_posix


def _walk(root: Path):
    """os.walk wrapper using pathlib-friendly Path objects."""
    import os

    for dirpath_str, dirnames, filenames in os.walk(root):
        dirpath = Path(dirpath_str)
        yield dirpath, dirnames, filenames


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------

def digest_for_file(abs_path: Path) -> tuple[int, str]:
    """Return (size, digest). Streams in 1 MB chunks; never loads large files fully."""
    try:
        size = abs_path.stat().st_size
    except OSError:
        return -1, "ERROR-stat-failed"

    if size <= LARGE_FILE_THRESHOLD:
        h = hashlib.sha256()
        try:
            with abs_path.open("rb") as f:
                while True:
                    chunk = f.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    h.update(chunk)
            return size, h.hexdigest()
        except OSError:
            return size, "ERROR-read-failed"
    else:
        try:
            mtime = int(abs_path.stat().st_mtime)
        except OSError:
            mtime = 0
        return size, f"LARGE-size-mtime:{size}:{mtime}"


# ---------------------------------------------------------------------------
# Inventory (TSV) read/write
# ---------------------------------------------------------------------------

def build_inventory() -> dict:
    """Walk the repo and build {relpath: (size, digest)}."""
    inventory = {}
    for abs_path, rel_posix in iter_repo_files(REPO_ROOT):
        size, digest = digest_for_file(abs_path)
        inventory[rel_posix] = (size, digest)
    return inventory


def write_inventory_tsv(inventory: dict, path: Path, timestamp: str) -> None:
    lines = [f"# fileaudit v1 {timestamp}"]
    for relpath in sorted(inventory.keys()):
        size, digest = inventory[relpath]
        lines.append(f"{relpath}\t{size}\t{digest}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_inventory_tsv(path: Path) -> dict:
    """Return {relpath: (size, digest)}. Returns {} if the file does not exist."""
    if not path.exists():
        return {}
    inventory = {}
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f):
            line = line.rstrip("\n")
            if not line:
                continue
            if line_no == 0 and INVENTORY_HEADER_RE.match(line):
                continue
            parts = line.split("\t")
            if len(parts) != 3:
                continue
            relpath, size_str, digest = parts
            try:
                size = int(size_str)
            except ValueError:
                size = -1
            inventory[relpath] = (size, digest)
    return inventory


def ensure_changelog_dirs() -> None:
    CHANGELOG_DIR.mkdir(parents=True, exist_ok=True)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# snapshot
# ---------------------------------------------------------------------------

def cmd_snapshot(args: argparse.Namespace) -> int:
    ensure_changelog_dirs()

    if INVENTORY_PATH.exists():
        INVENTORY_PATH.replace(INVENTORY_PREV_PATH)

    inventory = build_inventory()
    timestamp = utc_now_iso()
    write_inventory_tsv(inventory, INVENTORY_PATH, timestamp)

    if not args.quiet:
        total_bytes = sum(size for size, _ in inventory.values() if size >= 0)
        print(f"snapshot: {len(inventory)} files, {total_bytes:,} bytes -> {INVENTORY_PATH}")
    return 0


# ---------------------------------------------------------------------------
# diff
# ---------------------------------------------------------------------------

def short_digest(digest: str, n: int = 12) -> str:
    return digest[:n]


def format_size(size: int) -> str:
    if size < 0:
        return "?"
    return f"{size:,}"


def compute_diff(baseline: dict, current: dict):
    added = []
    modified = []
    deleted = []

    baseline_keys = set(baseline.keys())
    current_keys = set(current.keys())

    for relpath in sorted(current_keys - baseline_keys):
        size, digest = current[relpath]
        added.append({"path": relpath, "size": size, "digest": digest})

    for relpath in sorted(baseline_keys - current_keys):
        size_old, digest_old = baseline[relpath]
        deleted.append({"path": relpath, "size_old": size_old, "digest_old": digest_old})

    for relpath in sorted(baseline_keys & current_keys):
        size_old, digest_old = baseline[relpath]
        size_new, digest_new = current[relpath]
        if digest_old != digest_new:
            modified.append(
                {
                    "path": relpath,
                    "size": size_new,
                    "digest_old": digest_old,
                    "digest_new": digest_new,
                }
            )

    return added, modified, deleted


def print_diff_report(added, modified, deleted) -> None:
    print(f"added: {len(added)}  modified: {len(modified)}  deleted: {len(deleted)}")
    print()

    if added:
        print(f"-- added ({len(added)}) --")
        for item in added:
            print(f"  + {item['path']}  {format_size(item['size'])} B  {short_digest(item['digest'])}")
        print()

    if modified:
        print(f"-- modified ({len(modified)}) --")
        for item in modified:
            print(
                f"  ~ {item['path']}  {format_size(item['size'])} B  "
                f"{short_digest(item['digest_old'])} -> {short_digest(item['digest_new'])}"
            )
        print()

    if deleted:
        print(f"-- deleted ({len(deleted)}) --")
        for item in deleted:
            print(f"  - {item['path']}  {format_size(item['size_old'])} B  {short_digest(item['digest_old'])}")
        print()

    if not (added or modified or deleted):
        print("no changes detected")


def write_run_record(payload: dict, timestamp_for_filename: str, label: str, suffix: str) -> Path:
    ensure_changelog_dirs()
    filename = f"{timestamp_for_filename}_{label}{suffix}.json"
    run_path = RUNS_DIR / filename
    run_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return run_path


def append_changelog_md(timestamp_display: str, label: str, actor: str, reason: str,
                         added, modified, deleted) -> None:
    is_new = not CHANGELOG_MD_PATH.exists()

    lines = []
    if is_new:
        lines.append("# 변경 이력")
        lines.append("")
        lines.append("이 파일은 `tools/fileaudit.py`가 자동으로 append한다. 직접 편집하지 말 것.")
        lines.append("각 항목은 실행 전후 파일 스냅샷을 비교해 **실제로 디스크에서 바뀐 것**만 기록한다.")
        lines.append("작업 세션이 스스로 주장한 내용은 `.changelog/runs/*.claim.json`에 따로 남는다.")
        lines.append("")

    lines.append(f"## {timestamp_display} — {label}")
    lines.append(f"**실행**: {actor}")
    lines.append(f"**이유**: {reason if reason else '(no reason given)'}")
    lines.append("")

    if not (added or modified or deleted):
        lines.append("변경 사항 없음.")
    else:
        lines.append("| | 파일 | 크기 | digest |")
        lines.append("|---|---|---|---|")
        for item in added:
            lines.append(
                f"| + | `{item['path']}` | {format_size(item['size'])} B | `{short_digest(item['digest'])}` |"
            )
        for item in modified:
            lines.append(
                f"| ~ | `{item['path']}` | {format_size(item['size'])} B | "
                f"`{short_digest(item['digest_old'])}` → `{short_digest(item['digest_new'])}` |"
            )
        for item in deleted:
            lines.append(f"| − | `{item['path']}` | — | — |")

    lines.append("")

    with CHANGELOG_MD_PATH.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def cmd_diff(args: argparse.Namespace) -> int:
    label = sanitize_label(args.label)
    actor = args.actor
    reason = args.reason

    baseline = read_inventory_tsv(INVENTORY_PATH)
    current = build_inventory()

    added, modified, deleted = compute_diff(baseline, current)

    print_diff_report(added, modified, deleted)

    if args.commit:
        timestamp_iso = utc_now_iso()
        timestamp_for_filename = utc_now_for_filename()
        timestamp_display = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        payload = {
            "kind": "verified",
            "timestamp_utc": timestamp_iso,
            "label": label,
            "actor": actor,
            "reason": reason,
            "summary": {"added": len(added), "modified": len(modified), "deleted": len(deleted)},
            "added": added,
            "modified": modified,
            "deleted": deleted,
        }
        run_path = write_run_record(payload, timestamp_for_filename, label, "")
        print(f"run record written: {run_path}")

        append_changelog_md(timestamp_display, label, actor, reason, added, modified, deleted)
        print(f"CHANGELOG.md updated: {CHANGELOG_MD_PATH}")

        # Re-snapshot so inventory.tsv becomes the new baseline.
        if INVENTORY_PATH.exists():
            INVENTORY_PATH.replace(INVENTORY_PREV_PATH)
        write_inventory_tsv(current, INVENTORY_PATH, timestamp_iso)
        print(f"baseline re-snapshotted: {INVENTORY_PATH}")

    return 0


# ---------------------------------------------------------------------------
# record
# ---------------------------------------------------------------------------

def cmd_record(args: argparse.Namespace) -> int:
    label = sanitize_label(args.label)
    actor = args.actor
    reason = args.reason
    files = [p.strip() for p in args.files.split(",") if p.strip()] if args.files else []
    note = args.note or ""

    timestamp_iso = utc_now_iso()
    timestamp_for_filename = utc_now_for_filename()

    payload = {
        "kind": "claim",
        "timestamp_utc": timestamp_iso,
        "label": label,
        "actor": actor,
        "reason": reason,
        "claimed_files": files,
        "note": note,
    }

    run_path = write_run_record(payload, timestamp_for_filename, label, ".claim")
    print(str(run_path))
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fileaudit.py",
        description="Verified filesystem-change auditor for orchestrated agent work.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_snapshot = subparsers.add_parser("snapshot", help="Take a current inventory snapshot (baseline).")
    p_snapshot.add_argument("--quiet", action="store_true", help="Suppress the summary line.")
    p_snapshot.set_defaults(func=cmd_snapshot)

    p_diff = subparsers.add_parser("diff", help="Compare current disk state to inventory.tsv.")
    p_diff.add_argument("--label", required=True, help="Short slug used in the run filename.")
    p_diff.add_argument("--actor", default="unknown", help='Who did the work, e.g. "Cowork subagent (Sonnet)".')
    p_diff.add_argument("--reason", default="", help="One-line reason for the change.")
    p_diff.add_argument(
        "--commit",
        action="store_true",
        help="Write the run record, append CHANGELOG.md, and re-snapshot the baseline.",
    )
    p_diff.set_defaults(func=cmd_diff)

    p_record = subparsers.add_parser("record", help="Let the working agent declare its own (unverified) intent.")
    p_record.add_argument("--label", required=True, help="Short slug used in the run filename.")
    p_record.add_argument("--actor", default="unknown", help="Who is making this claim.")
    p_record.add_argument("--reason", default="", help="One-line reason.")
    p_record.add_argument("--files", default="", help='Comma-separated claimed paths, e.g. "a.py,b.md".')
    p_record.add_argument("--note", default="", help="Free-text note.")
    p_record.set_defaults(func=cmd_record)

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
