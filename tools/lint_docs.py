#!/usr/bin/env python3
"""lint_docs.py - 문서 일관성 린트 (ADR 목록, 보고서 목록, 물결표, 플레이스홀더, 낡음, 비밀 위생).

Python 3.9+ 표준 라이브러리만 사용한다. Windows/Linux에서 같게 동작한다.
기본 root는 이 파일이 있는 tools/ 의 부모 폴더이며 --root로 바꾼다.

    python tools/lint_docs.py [--root DIR] [--strict] [--stale-days N] [--only CODE[,CODE]] [--json]

출력: `[ERROR|WARN|INFO] CODE path:line 메시지`. ERROR가 있으면 종료코드 1
(--strict면 WARN도), 사용법 오류는 2.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, Iterator, List, NamedTuple, Optional, Tuple
from urllib.parse import unquote

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

SKIP_DIRS = {".git", ".changelog", "venv", ".venv", "node_modules", "__pycache__", ".ipynb_checkpoints"}
PLACEHOLDER_SKIP_TOP = {".claude", "dot-claude", "optional", ".changelog"}  # 템플릿 원본/모듈은 {{ }}가 정상
ALL_CODES = [
    "TILDE", "PLACEHOLDER", "ADR-INDEX", "ADR-DUP", "ADR-GAP", "ADR-STATUS", "ADR-SUPERSEDE", "ADR-LONG",
    "RPT-NAME", "RPT-INDEX", "STALE-STATUS", "STALE-CHANGELOG", "CLAUDE-LEN", "CLAUDE-DATE",
    "ENV-IGNORE", "ENV-EXAMPLE",
]

ADR_FILE_RE = re.compile(r"^(\d{4})-.+\.md$")
STATUS_LINE_RE = re.compile(r"^- 상태: \*\*(.+?)\*\*")
RPT_NAME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}_.+\.md$")
RUN_TS_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})T(\d{2})-(\d{2})-(\d{2})Z")
DATE_RE = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")
FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")
URL_RE = re.compile(r"https?://[^\s)>\]]+")
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


class Finding(NamedTuple):
    sev: str
    code: str
    path: str
    line: Optional[int]
    msg: str

    def text(self) -> str:
        loc = self.path + (":%d" % self.line if self.line else "")
        return "[%s] %s %s %s" % (self.sev, self.code, loc, self.msg)

    def as_dict(self) -> Dict[str, object]:
        return {"severity": self.sev, "code": self.code, "path": self.path, "line": self.line, "message": self.msg}


# ---------------------------------------------------------------- 공통 도우미

def rel(root: Path, p: Path) -> str:
    return p.relative_to(root).as_posix()


def read_lines(p: Path) -> List[str]:
    return p.read_text(encoding="utf-8-sig", errors="replace").splitlines()


def walk_md(root: Path) -> Iterator[Path]:
    for dirpath, dirnames, filenames in os.walk(str(root)):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for f in sorted(filenames):
            if f.lower().endswith(".md"):
                yield Path(dirpath) / f


def split_row(line: str) -> Optional[List[str]]:
    """마크다운 표의 한 줄을 셀 목록으로. 표 줄이 아니면 None. 이스케이프된 \\| 는 셀 구분이 아니다."""
    s = line.strip()
    if not s.startswith("|"):
        return None
    cells = re.split(r"(?<!\\)\|", s)[1:]
    if s.endswith("|") and not s.endswith("\\|") and cells:
        cells = cells[:-1]
    return [c.strip().replace("\\|", "|") for c in cells]


def is_sep_row(cells: List[str]) -> bool:
    return bool(cells) and all(re.fullmatch(r":?-+:?", c) for c in cells if c) and any(cells)


def parse_date(s: str) -> Optional[dt.date]:
    m = DATE_RE.search(s)
    if not m:
        return None
    try:
        return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def iter_text_lines(lines: List[str]) -> Iterator[Tuple[int, str]]:
    """코드 펜스(``` 또는 ~~~) 밖의 (줄번호, 텍스트). 같은 문자의 펜스만 닫는다."""
    fence: Optional[str] = None
    for no, ln in enumerate(lines, 1):
        m = FENCE_RE.match(ln)
        if m:
            ch = m.group(1)[0]
            if fence is None:
                fence = ch
            elif fence == ch:
                fence = None
            continue
        if fence is None:
            yield no, ln


# ---------------------------------------------------------------- 1. TILDE

def mask_code(line: str) -> str:
    """인라인 코드 스팬, 백슬래시 이스케이프(\\~), URL을 같은 길이의 공백으로 가린 줄."""
    out = list(line)
    i, n = 0, len(line)
    while i < n:
        c = line[i]
        if c == "\\":
            out[i:i + 2] = " " * len(out[i:i + 2])
            i += 2
        elif c == "`":
            j = i
            while j < n and line[j] == "`":
                j += 1
            run, k, close = j - i, j, -1
            while k < n:
                if line[k] == "`":
                    m = k
                    while m < n and line[m] == "`":
                        m += 1
                    if m - k == run:
                        close = m
                        break
                    k = m
                else:
                    k += 1
            end = close if close >= 0 else j  # 짝 없는 백틱은 그 글자만 가린다
            out[i:end] = " " * (end - i)
            i = end
        elif c == "h" and URL_RE.match(line, i):
            end = URL_RE.match(line, i).end()  # type: ignore[union-attr]
            out[i:end] = " " * (end - i)
            i = end
        else:
            i += 1
    return "".join(out)


def bare_tilde_columns(line: str) -> List[int]:
    return [m.start() for m in re.finditer("~", mask_code(line))]


def check_tilde(root: Path) -> List[Finding]:
    res: List[Finding] = []
    for p in walk_md(root):
        for no, ln in iter_text_lines(read_lines(p)):
            if bare_tilde_columns(ln):
                res.append(Finding("ERROR", "TILDE", rel(root, p), no,
                                   "이스케이프 안 한 `~` (범위는 ' - ', 날짜 기간은 ' \\~ ')"))
    return res


# ---------------------------------------------------------------- 2. PLACEHOLDER

def check_placeholder(root: Path) -> List[Finding]:
    res: List[Finding] = []
    for p in walk_md(root):
        parts = p.relative_to(root).parts
        if parts[0] in PLACEHOLDER_SKIP_TOP or "TEMPLATE" in p.name:
            continue
        for no, ln in enumerate(read_lines(p), 1):
            # 코드 스팬 안과 설명용 `{{...}}` 표기는 미기입 자리가 아니다
            masked = mask_code(ln.replace("{{...}}", "       "))
            for m in re.finditer(r"\{\{.*?(?:\}\}|$)", masked):
                snippet = ln[m.start():m.end()]
                sev = "INFO" if snippet.startswith("{{미정") else "WARN"
                res.append(Finding(sev, "PLACEHOLDER", rel(root, p), no, snippet[:100]))
    return res


# ---------------------------------------------------------------- 3. ADR

def norm_status(text: str) -> Tuple[Optional[str], Optional[str], bool]:
    """상태 문자열 -> (토큰, 대체 대상 번호, 다른 저장소 참조 여부). 알 수 없으면 토큰 None."""
    t = re.sub(r"[*`]", "", text).strip()
    if t.startswith("대체됨"):
        m = re.match(r"대체됨\s*\(\s*→\s*((?:[^\s:)]+:)?)(\d{1,4})", t)
        if m:
            num = m.group(2).zfill(4)
            return "대체됨(→ %s)" % num, num, bool(m.group(1))
        return "대체됨", None, False
    if re.match(r"확정\s*\(임시\)", t):
        return "확정(임시)", None, False
    if t.startswith("확정"):
        return "확정", None, False
    if t.startswith("제안"):
        return "제안", None, False
    return None, None, False


def adr_files(d: Path) -> List[Path]:
    return sorted(f for f in d.iterdir()
                  if f.is_file() and ADR_FILE_RE.match(f.name) and not f.name.startswith("0000-"))


def adr_readme_rows(lines: List[str]) -> List[Tuple[int, str, str, str]]:
    """README 표에서 첫 셀에 링크가 있는 행 -> (줄, 링크 대상, 상태 셀, 원문)."""
    rows = []
    for no, ln in enumerate(lines, 1):
        cells = split_row(ln)
        if not cells or len(cells) < 3 or is_sep_row(cells):
            continue
        m = LINK_RE.search(cells[0])
        if not m:
            continue
        target = unquote(m.group(1).strip().split("#")[0]).replace("\\", "/")
        if target.startswith("./"):
            target = target[2:]
        if target.lower().endswith(".md"):
            rows.append((no, target, cells[2], ln))
    return rows


def check_adr(root: Path) -> List[Finding]:
    d = root / "docs" / "decisions"
    if not d.is_dir():
        return []
    res: List[Finding] = []
    base = "docs/decisions/"
    files = adr_files(d)
    by_num: Dict[str, List[Path]] = {}
    for f in files:
        by_num.setdefault(ADR_FILE_RE.match(f.name).group(1), []).append(f)  # type: ignore[union-attr]
    nums = sorted(by_num)

    # ADR-DUP / ADR-GAP
    for n in nums:
        if len(by_num[n]) > 1:
            res.append(Finding("ERROR", "ADR-DUP", base + by_num[n][1].name, None,
                               "번호 %s 중복: %s" % (n, ", ".join(f.name for f in by_num[n]))))
    if nums:
        have = set(int(n) for n in nums)
        missing = ["%04d" % k for k in range(1, max(have) + 1) if k not in have]
        if missing:
            res.append(Finding("WARN", "ADR-GAP", base.rstrip("/"), None, "번호 빠짐: " + ", ".join(missing)))

    # README 표
    readme = d / "README.md"
    rows: List[Tuple[int, str, str, str]] = []
    if readme.is_file():
        rows = adr_readme_rows(read_lines(readme))
    elif files:
        res.append(Finding("ERROR", "ADR-INDEX", base + "README.md", None, "README.md 없음(ADR 목록 없음)"))
    row_by_name: Dict[str, Tuple[int, str]] = {}
    for no, target, status, raw in rows:
        row_by_name.setdefault(target, (no, status))
        if not (d / target).is_file():
            res.append(Finding("ERROR", "ADR-INDEX", base + "README.md", no, "목록의 파일 없음: " + target))
        if len(raw.rstrip()) > 220:
            res.append(Finding("WARN", "ADR-LONG", base + "README.md", no,
                               "목록 한 줄이 %d자(220자 초과). 한 문장으로 줄이고 근거는 본문으로" % len(raw.rstrip())))
    if readme.is_file():
        for f in files:
            if f.name not in row_by_name:
                res.append(Finding("ERROR", "ADR-INDEX", base + f.name, None, "README.md 목록에 없음"))

    # ADR-STATUS / ADR-SUPERSEDE
    def supersede(path: str, line: Optional[int], target: Optional[str], foreign: bool) -> None:
        if target and not foreign and target not in by_num:
            res.append(Finding("ERROR", "ADR-SUPERSEDE", path, line, "대체 대상 ADR %s 파일이 없음" % target))

    for f in files:
        lines = read_lines(f)
        sl = next(((i, m.group(1)) for i, ln in enumerate(lines, 1) for m in [STATUS_LINE_RE.match(ln)] if m), None)
        row = row_by_name.get(f.name)
        if sl is None:
            res.append(Finding("WARN", "ADR-STATUS", base + f.name, None, "'- 상태: **...**' 줄이 없음"))
            continue
        ftok, ftarget, fforeign = norm_status(sl[1])
        if ftok is None:
            res.append(Finding("WARN", "ADR-STATUS", base + f.name, sl[0], "알 수 없는 상태 값: " + sl[1]))
        supersede(base + f.name, sl[0], ftarget, fforeign)
        if ftok == "대체됨":
            res.append(Finding("WARN", "ADR-SUPERSEDE", base + f.name, sl[0], "대체됨인데 '→ NNNN' 대상이 없음"))
        if row:
            rtok, rtarget, rforeign = norm_status(row[1])
            if rtok is None:
                res.append(Finding("WARN", "ADR-STATUS", base + "README.md", row[0], "알 수 없는 상태 값: " + row[1]))
            elif ftok is not None and rtok != ftok:
                res.append(Finding("ERROR", "ADR-STATUS", base + f.name, sl[0],
                                   "파일 상태 '%s' 와 README 상태 '%s' 가 다름(README:%d)" % (ftok, rtok, row[0])))
            if rtarget != ftarget:
                supersede(base + "README.md", row[0], rtarget, rforeign)
    return res


def adr_dates(root: Path) -> List[Tuple[dt.date, str]]:
    d = root / "docs" / "decisions"
    out: List[Tuple[dt.date, str]] = []
    if d.is_dir():
        for f in adr_files(d):
            for ln in read_lines(f):
                m = re.match(r"^- 날짜:\s*(.*)", ln)
                if m and parse_date(m.group(1)):
                    out.append((parse_date(m.group(1)), "ADR " + f.name))  # type: ignore[arg-type]
                    break
    return out


# ---------------------------------------------------------------- 4. RPT

def report_files(root: Path) -> List[Path]:
    d = root / "reports"
    if not d.is_dir():
        return []
    return sorted(f for f in d.iterdir()
                  if f.is_file() and f.suffix.lower() == ".md" and f.name not in ("README.md", "TEMPLATE.md"))


def cell_md_names(cell: str) -> List[str]:
    """표 셀에서 .md 파일명(링크 대상, 백틱, 맨 토큰 순) 추출."""
    found = [m.group(1) for m in re.finditer(r"\]\(([^)]+?\.md)\)", cell)]
    found += [m.group(1) for m in re.finditer(r"`([^`]+?\.md)`", cell)]
    if not found:
        found = re.findall(r"[^\s`\[\]()|<>]+\.md", cell)
    names = []
    for x in found:
        x = unquote(x).strip().replace("\\", "/")
        x = x[2:] if x.startswith("./") else x
        x = x[len("reports/"):] if x.startswith("reports/") else x
        names.append(x)
    return names


def check_reports(root: Path) -> List[Finding]:
    d = root / "reports"
    if not d.is_dir():
        return []
    res: List[Finding] = []
    files = report_files(root)
    for f in files:
        if not RPT_NAME_RE.match(f.name):
            res.append(Finding("WARN", "RPT-NAME", "reports/" + f.name, None, "파일명이 YYYY-MM-DD_<제목>.md 형식이 아님"))
    readme = d / "README.md"
    if not readme.is_file():
        if files:
            res.append(Finding("ERROR", "RPT-INDEX", "reports/README.md", None, "README.md 없음(보고서 목록 없음)"))
        return res
    mentioned: Dict[str, int] = {}
    for no, ln in enumerate(read_lines(readme), 1):
        cells = split_row(ln)
        if not cells or len(cells) < 3 or is_sep_row(cells) or "{{" in cells[2]:
            continue
        for name in cell_md_names(cells[2]):
            mentioned.setdefault(name, no)
            if not (d / name).is_file():
                res.append(Finding("ERROR", "RPT-INDEX", "reports/README.md", no, "목록의 파일 없음: " + name))
    for f in files:
        if f.name not in mentioned:
            res.append(Finding("ERROR", "RPT-INDEX", "reports/" + f.name, None, "reports/README.md 목록에 없음"))
    return res


# ---------------------------------------------------------------- 5. 낡음

def list_runs(root: Path) -> List[Tuple[dt.datetime, str, bool]]:
    """.changelog/runs 의 (UTC 시각, 파일명, claim 여부). 시각을 못 읽는 파일은 제외."""
    d = root / ".changelog" / "runs"
    out = []
    if d.is_dir():
        for f in sorted(d.iterdir()):
            m = RUN_TS_RE.match(f.name)
            if f.is_file() and m and f.name.endswith(".json"):
                try:
                    t = dt.datetime(*[int(x) for x in m.groups()])
                except ValueError:
                    continue
                out.append((t, f.name, f.name.endswith(".claim.json")))
    return out


def check_stale_status(root: Path, stale_days: int) -> List[Finding]:
    sp = root / "docs" / "STATUS.md"
    if not sp.is_file():
        return []
    path = "docs/STATUS.md"
    sline, stoken = None, ""
    for no, ln in enumerate(read_lines(sp), 1):
        m = re.search(r"최종 갱신\s*(\S+)", ln)
        if m:
            sline, stoken = no, m.group(1)
            break
    if sline is None:
        return [Finding("WARN", "STALE-STATUS", path, None, "'최종 갱신 YYYY-MM-DD' 줄이 없음")]
    sdate = parse_date(stoken)
    if sdate is None:
        if "{{" in stoken:
            return [Finding("INFO", "STALE-STATUS", path, sline, "최종 갱신 날짜가 아직 미기입(플레이스홀더)")]
        return [Finding("WARN", "STALE-STATUS", path, sline, "최종 갱신 날짜를 읽을 수 없음: " + stoken)]
    cands: List[Tuple[dt.date, str]] = []
    for f in report_files(root):
        m = RPT_NAME_RE.match(f.name)
        if m and parse_date(f.name[:10]):
            cands.append((parse_date(f.name[:10]), "보고서 " + f.name))  # type: ignore[arg-type]
    cands += adr_dates(root)
    cands += [(t.date(), "changelog " + n) for t, n, _ in list_runs(root)]
    if not cands:
        return []
    newest = max(cands, key=lambda x: x[0])
    gap = (newest[0] - sdate).days
    if gap > stale_days:
        return [Finding("WARN", "STALE-STATUS", path, sline,
                        "STATUS 최종 갱신 %s, 최신 활동 %s(%s)로 %d일 앞섬(허용 %d일)"
                        % (sdate, newest[0], newest[1], gap, stale_days))]
    return []


def check_stale_changelog(root: Path, stale_days: int) -> List[Finding]:
    if not (root / ".changelog" / "runs").is_dir():
        return []
    runs = list_runs(root)
    claims = [t for t, _, c in runs if c]
    verified = [t for t, _, c in runs if not c]
    path = ".changelog/runs"
    if not claims:
        return []
    if not verified:
        return [Finding("WARN", "STALE-CHANGELOG", path, None,
                        "claim %d건, 검증 기록 0건 - diff --commit 누락 의심" % len(claims))]
    gap = (max(claims).date() - max(verified).date()).days
    if gap > stale_days:
        return [Finding("WARN", "STALE-CHANGELOG", path, None,
                        "claim 최신 %s, 검증 기록 최신 %s로 %d일 앞섬 - diff --commit 누락 의심"
                        % (max(claims).date(), max(verified).date(), gap))]
    return []


# ---------------------------------------------------------------- 6. CLAUDE.md

def check_claude_md(root: Path) -> List[Finding]:
    p = root / "CLAUDE.md"
    if not p.is_file():
        return []
    lines = read_lines(p)
    res: List[Finding] = []
    if len(lines) > 150:
        res.append(Finding("WARN", "CLAUDE-LEN", "CLAUDE.md", None, "%d줄(150줄 초과). 길면 규칙이 묻힌다" % len(lines)))
    date_re = re.compile(r"(?<!\d)(?:20\d\d-\d\d-\d\d|20\d\d\.\d\d\.\d\d)(?!\d)")
    skip_level = 0
    hits: List[int] = []
    for no, ln in enumerate(lines, 1):
        m = re.match(r"^(#{1,6})\s+(.*)", ln)
        if m:
            if "Compact instructions" in m.group(2):
                skip_level = len(m.group(1))
                continue
            if skip_level and len(m.group(1)) <= skip_level:
                skip_level = 0
        if not skip_level and date_re.search(ln):
            hits.append(no)
    if hits:
        res.append(Finding("WARN", "CLAUDE-DATE", "CLAUDE.md", hits[0],
                           "날짜가 있는 줄 %d개(앞 3개: %s). 상태·날짜는 docs/STATUS.md로"
                           % (len(hits), ", ".join(str(h) for h in hits[:3]))))
    return res


# ---------------------------------------------------------------- 7. 비밀 위생

def check_secrets(root: Path) -> List[Finding]:
    res: List[Finding] = []
    gi = root / ".gitignore"
    if not gi.is_file():
        res.append(Finding("ERROR", "ENV-IGNORE", ".gitignore", None, ".gitignore 없음(.env가 커밋될 수 있음)"))
    elif not any(ln.strip() in (".env", "/.env") for ln in read_lines(gi)):
        res.append(Finding("ERROR", "ENV-IGNORE", ".gitignore", None, ".gitignore에 `.env` 줄이 없음"))
    ex = root / ".env.example"
    if ex.is_file():
        for no, ln in enumerate(read_lines(ex), 1):
            s = ln.strip()
            if not s or s.startswith("#"):
                continue
            m = re.match(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", s)
            if m and m.group(2).strip().strip("'\"").strip():
                # 값은 출력하지 않는다(비밀 노출 방지). 키 이름만.
                res.append(Finding("WARN", "ENV-EXAMPLE", ".env.example", no,
                                   "%s 에 값이 들어 있음(키 이름만 남긴다)" % m.group(1)))
    return res


# ---------------------------------------------------------------- 실행

def run_all(root: Path, stale_days: int) -> List[Finding]:
    return (check_tilde(root) + check_placeholder(root) + check_adr(root) + check_reports(root)
            + check_stale_status(root, stale_days) + check_stale_changelog(root, stale_days)
            + check_claude_md(root) + check_secrets(root))


def main(argv: Optional[List[str]] = None) -> int:
    default_root = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser(description="문서 일관성 린트")
    ap.add_argument("--root", default=str(default_root), help="저장소 루트(기본: tools/ 의 부모)")
    ap.add_argument("--strict", action="store_true", help="WARN도 실패로 본다")
    ap.add_argument("--stale-days", type=int, default=3, help="낡음 허용 일수(기본 3)")
    ap.add_argument("--only", default="", help="검사할 코드만(쉼표 구분). 예: TILDE,ADR-INDEX")
    ap.add_argument("--json", action="store_true", help="JSON 목록으로 출력")
    args = ap.parse_args(argv)

    root = Path(args.root).resolve()
    if not root.is_dir():
        ap.error("root 폴더가 없음: %s" % root)
    only = [c.strip().upper() for c in args.only.split(",") if c.strip()]
    bad = [c for c in only if c not in ALL_CODES]
    if bad:
        ap.error("알 수 없는 코드: %s (가능: %s)" % (", ".join(bad), ", ".join(ALL_CODES)))

    findings = run_all(root, args.stale_days)
    if only:
        findings = [f for f in findings if f.code in only]
    counts = {s: sum(1 for f in findings if f.sev == s) for s in ("ERROR", "WARN", "INFO")}
    if args.json:
        print(json.dumps([f.as_dict() for f in findings], ensure_ascii=False, indent=2))
    else:
        for f in findings:
            print(f.text())
        print("요약: ERROR %d, WARN %d, INFO %d" % (counts["ERROR"], counts["WARN"], counts["INFO"]))
    return 1 if counts["ERROR"] or (args.strict and counts["WARN"]) else 0


if __name__ == "__main__":
    sys.exit(main())
