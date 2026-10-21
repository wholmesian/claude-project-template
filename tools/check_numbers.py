#!/usr/bin/env python3
"""check_numbers.py - 보고서의 "A. 수치 대조" 표를 원시 산출물(JSON/CSV)과 다시 대조한다.

Python 3.9+ 표준 라이브러리만 사용한다. Windows/Linux에서 같게 동작한다.
기본 root는 이 파일이 있는 tools/ 의 부모 폴더이며 --root로 바꾼다.

    python tools/check_numbers.py [REPORT.md ...] [--root DIR] [--require-all] [--no-coverage] [--json]

표 형식(reports/TEMPLATE.md): `보고서 수치 | 원시 산출물(경로, 키) | 대조 결과`
원시 산출물 칸: `경로#키 [*k]`
  .json  키는 점 경로와 [i], 점이 든 키는 ["a.b"]      예) stages/s3/outputs/summary.json#main.beta[0].t
  .csv/.tsv  `열[행]` 행은 0부터 센 번호 또는 `다른열=값`  예) x.csv#mean[group=KW], x.csv#t[3]
  끝의 ` *100` ` /100` 은 원천 값에 곱하거나 나눈다.
종료코드: 0 모두 통과, 1 불일치/원천 오류(--require-all이면 미검증·파싱 불가·표 없음 포함), 2 사용법 오류.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional, Tuple

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

OK, BAD, SRC, UNV, PARSE = "일치", "불일치", "원천 오류", "미검증", "파싱 불가"
REPORT_NAME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}_.+\.md$")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)")
NUM_RE = re.compile(
    r"(?<![A-Za-z0-9_.])(?:([+\-−])(?=\d))?(\d{1,3}(?:,\d{3})+(?!\d)|\d+)(\.\d+)?(?:[eE]([+\-−]?\d+))?(%)?")
FILE_TOKEN_RE = re.compile(r"[\w./\\-]+\.(?:md|json|csv|tsv|py|ipynb|parquet|txt|png|svg|pdf|ya?ml|xlsx?)\b", re.I)
DATE_TOKEN_RE = re.compile(r"\d{4}[-.]\d{2}[-.]\d{2}")
MULT_RE = re.compile(r"^(.*?\S)\s+([*×/])\s*(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\s*$")


class Num(NamedTuple):
    value: float      # 보고서에 적힌 값(% 칸이면 % 단위 그대로)
    tol: float        # 적힌 자릿수의 반올림 허용 오차 0.5*10^-d
    pct: bool
    text: str


# ---------------------------------------------------------------- 파싱 도우미

def read_lines(p: Path) -> List[str]:
    return p.read_text(encoding="utf-8-sig", errors="replace").splitlines()


def split_row(line: str) -> Optional[List[str]]:
    s = line.strip()
    if not s.startswith("|"):
        return None
    cells = re.split(r"(?<!\\)\|", s)[1:]
    if s.endswith("|") and not s.endswith("\\|") and cells:
        cells = cells[:-1]
    return [c.strip().replace("\\|", "|") for c in cells]


def is_sep_row(cells: List[str]) -> bool:
    return bool(cells) and any(cells) and all(re.fullmatch(r":?-+:?", c) for c in cells if c)


def clean_cell(s: str) -> str:
    """마크다운 링크는 글자만, 백틱·굵게 표시는 제거."""
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)
    s = s.replace("`", "").replace("**", "").replace("<br>", " ")
    return s.strip()


def match_to_num(m: "re.Match[str]") -> Num:
    sign = -1.0 if m.group(1) in ("-", "−") else 1.0
    ip, frac = m.group(2).replace(",", ""), (m.group(3) or "")
    exp = int((m.group(4) or "0").replace("−", "-"))
    val = sign * float("%s%s" % (ip, frac) + "e%d" % exp)
    d = len(frac) - 1 if frac else 0
    return Num(val, 0.5 * 10 ** (exp - d), bool(m.group(5)), m.group(0))


def parse_report_number(cell: str) -> Optional[Num]:
    """셀의 첫 숫자. 유니코드 마이너스, 천단위 쉼표, 앞의 +, 뒤의 %, 과학 표기를 받는다."""
    m = NUM_RE.search(cell)
    return match_to_num(m) if m else None


def close(a: float, b: float, tol: float) -> bool:
    return abs(a - b) <= tol * (1 + 1e-9) + 1e-15 * max(abs(a), abs(b))


def fmt(v: float) -> str:
    return "%.10g" % v


def parse_source(cell: str) -> Tuple[str, str, Optional[Tuple[str, float]]]:
    """`경로#키 [*k]` -> (경로, 키, (연산자, k) 또는 None). 형식이 틀리면 ValueError."""
    s = cell.strip().replace("−", "-")
    mult = None
    m = MULT_RE.match(s)
    if m and "#" in m.group(1):
        s, mult = m.group(1), (m.group(2), float(m.group(3)))
    if "#" not in s:
        raise ValueError("'경로#키' 형식이 아님")
    path, key = s.split("#", 1)
    path, key = path.strip().replace("\\", "/"), key.strip()
    if not path or not key:
        raise ValueError("경로 또는 키가 비어 있음")
    if mult and mult[0] in ("/", ) and mult[1] == 0:
        raise ValueError("0으로 나눌 수 없음")
    return path, key, mult


def parse_json_key(key: str) -> List[Any]:
    """`a.b[0]["x.y"]` -> ['a','b',0,'x.y']"""
    segs: List[Any] = []
    buf, i, n = "", 0, len(key)
    while i < n:
        c = key[i]
        if c == ".":
            if buf:
                segs.append(buf)
            buf, i = "", i + 1
        elif c == "[":
            if buf:
                segs.append(buf)
                buf = ""
            if i + 1 < n and key[i + 1] in "\"'":
                q = key[i + 1]
                j = key.find(q + "]", i + 2)
                if j < 0:
                    raise ValueError("따옴표 키가 닫히지 않음")
                segs.append(key[i + 2:j])
                i = j + 2
            else:
                j = key.find("]", i)
                if j < 0:
                    raise ValueError("']' 없음")
                try:
                    segs.append(int(key[i + 1:j].strip()))
                except ValueError:
                    raise ValueError("배열 인덱스가 정수가 아님: [%s]" % key[i + 1:j])
                i = j + 1
        else:
            buf, i = buf + c, i + 1
    if buf:
        segs.append(buf)
    if not segs:
        raise ValueError("키가 비어 있음")
    return segs


def to_float(v: Any) -> float:
    if isinstance(v, bool) or v is None:
        raise ValueError("숫자가 아님: %r" % (v,))
    if isinstance(v, (int, float)):
        f = float(v)
    elif isinstance(v, str):
        try:
            f = float(v.strip().replace("−", "-"))
        except ValueError:
            raise ValueError("숫자가 아님: %r" % v[:30])
    else:
        raise ValueError("숫자가 아님(%s)" % type(v).__name__)
    if not math.isfinite(f):
        raise ValueError("유한한 숫자가 아님")
    return f


def json_lookup(obj: Any, key: str) -> float:
    cur = obj
    for seg in parse_json_key(key):
        if isinstance(seg, int):
            if not isinstance(cur, list):
                raise ValueError("[%d]: 배열이 아님" % seg)
            if not -len(cur) <= seg < len(cur):
                raise ValueError("[%d]: 범위 밖(길이 %d)" % (seg, len(cur)))
            cur = cur[seg]
        else:
            if not isinstance(cur, dict) or seg not in cur:
                raise ValueError("키 없음: %s" % seg)
            cur = cur[seg]
    return to_float(cur)


def csv_lookup(table: Tuple[List[str], List[List[str]]], key: str) -> float:
    header, rows = table
    m = re.match(r"^(.*?)\[([^\[\]]*)\]$", key)
    col, sel = (m.group(1).strip(), m.group(2).strip()) if m else (key.strip(), None)
    if col not in header:
        raise ValueError("열 없음: %s (열: %s)" % (col, ", ".join(header[:8])))
    ci = header.index(col)
    if sel is None:
        if len(rows) != 1:
            raise ValueError("행 지정 필요: 열[행] (데이터 %d행)" % len(rows))
        picked = [rows[0]]
    elif re.fullmatch(r"-?\d+", sel):
        idx = int(sel)
        if not -len(rows) <= idx < len(rows):
            raise ValueError("행 번호 범위 밖: %d (데이터 %d행)" % (idx, len(rows)))
        picked = [rows[idx]]
    elif "=" in sel:
        kc, kv = [x.strip().strip("'\"") for x in sel.split("=", 1)]
        if kc not in header:
            raise ValueError("행 조건 열 없음: %s" % kc)
        ki = header.index(kc)

        def same(a: str) -> bool:
            a = a.strip()
            try:
                return a == kv or float(a) == float(kv)
            except ValueError:
                return False
        picked = [r for r in rows if ki < len(r) and same(r[ki])]
        if not picked:
            raise ValueError("조건에 맞는 행 없음: %s=%s" % (kc, kv))
        if len(picked) > 1:
            raise ValueError("조건에 맞는 행이 %d개(하나여야 함): %s=%s" % (len(picked), kc, kv))
    else:
        raise ValueError("행 지정 형식 오류: [%s]" % sel)
    row = picked[0]
    if ci >= len(row):
        raise ValueError("해당 행에 열이 없음")
    return to_float(row[ci])


class Loader:
    """원시 파일을 한 번만 읽는다."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.cache: Dict[Path, Any] = {}

    def value(self, path: str, key: str) -> float:
        p = (self.root / path).resolve()
        try:
            p.relative_to(self.root)
        except ValueError:
            raise ValueError("root 밖의 경로: %s" % path)
        if not p.is_file():
            raise ValueError("파일 없음: %s" % path)
        ext = p.suffix.lower()
        if ext not in (".json", ".csv", ".tsv"):
            raise ValueError("지원하지 않는 형식: %s" % ext)
        if p not in self.cache:
            try:
                if ext == ".json":
                    self.cache[p] = json.loads(p.read_text(encoding="utf-8-sig"))
                else:
                    with p.open(encoding="utf-8-sig", newline="") as fh:
                        data = list(csv.reader(fh, delimiter="\t" if ext == ".tsv" else ","))
                    self.cache[p] = ([h.strip() for h in data[0]], data[1:]) if data else ([], [])
            except (ValueError, csv.Error, UnicodeDecodeError) as e:
                raise ValueError("파일을 읽을 수 없음(%s): %s" % (path, str(e)[:60]))
        return json_lookup(self.cache[p], key) if ext == ".json" else csv_lookup(self.cache[p], key)


# ---------------------------------------------------------------- 표 찾기와 행 검증

def find_table(lines: List[str]) -> Optional[Tuple[int, List[Tuple[int, List[str]]]]]:
    """'수치 대조'가 든 제목 뒤의 첫 표 -> (제목 줄번호, [(줄번호, 셀들)]) (헤더·구분선 제외)."""
    for h, ln in enumerate(lines):
        hm = HEADING_RE.match(ln)
        if not hm or "수치 대조" not in hm.group(2):
            continue
        level, i = len(hm.group(1)), h + 1
        while i < len(lines):
            m2 = HEADING_RE.match(lines[i])
            if m2 and len(m2.group(1)) <= level:
                break
            if split_row(lines[i]) is not None:
                tbl = []
                while i < len(lines) and split_row(lines[i]) is not None:
                    tbl.append((i + 1, split_row(lines[i])))  # type: ignore[arg-type]
                    i += 1
                body = tbl[1:]
                if body and is_sep_row(body[0][1]):
                    body = body[1:]
                return h + 1, body  # type: ignore[return-value]
            i += 1
    return None


def claim_of(result: str) -> Optional[str]:
    """사람이 적은 대조 결과. 템플릿 그대로('일치 / 불일치 / 미검증')면 주장 없음."""
    has_bad, has_unv = "불일치" in result, "미검증" in result
    has_ok = "일치" in result.replace("불일치", "")
    found = [name for name, on in ((OK, has_ok), (BAD, has_bad), (UNV, has_unv)) if on]
    return found[0] if len(found) == 1 else None


def check_row(lineno: int, cells: List[str], loader: Loader) -> Optional[Dict[str, Any]]:
    cells = [clean_cell(c) for c in cells] + ["", "", ""]
    rcell, scell, result = cells[0], cells[1], cells[2]
    if not rcell and not scell:
        return None  # 빈 행(템플릿 자리)
    row: Dict[str, Any] = {"line": lineno, "report_cell": rcell, "source_cell": scell, "status": "",
                           "report_value": None, "source_value": None, "note": "", "claim": claim_of(result),
                           "claim_conflict": False}
    if row["claim"] == UNV or scell in ("", "-", "—", "–"):
        row["status"] = UNV
        return row
    num = parse_report_number(rcell)
    if num is None:
        row.update(status=PARSE, note="보고서 칸에서 숫자를 찾지 못함")
        return row
    row["report_value"] = num.value
    try:
        path, key, mult = parse_source(scell)
        raw = loader.value(path, key)
    except ValueError as e:
        row.update(status=SRC, note=str(e))
        return row
    val = raw
    if mult:
        val = raw * mult[1] if mult[0] in ("*", "×") else raw / mult[1]
    cands = [(val, "")]
    if num.pct and not mult:
        cands = [(val, "원값 일치"), (val * 100, "x100 일치")]
    row["source_value"] = val
    for v, note in cands:
        if close(num.value, v, num.tol):
            row.update(status=OK, source_value=v, note=note)
            break
    else:
        row["status"] = BAD
        row["note"] = "허용 오차 %s" % fmt(num.tol)
        if len(cands) > 1:
            row["note"] += ", x100 값 %s" % fmt(cands[1][0])
    if row["status"] == BAD and row["claim"] == OK:
        row["claim_conflict"] = True
        row["note"] += " / 보고서의 대조 결과 주장과 다름"
    elif row["status"] == OK and row["claim"] == BAD:
        row["note"] = (row["note"] + " / 보고서는 불일치로 적었으나 일치함").strip(" /")
    return row


# ---------------------------------------------------------------- 요약 구간 커버리지

def meaningful(m: "re.Match[str]") -> bool:
    ip, frac, pct = m.group(2).replace(",", ""), m.group(3), m.group(5)
    if frac or pct or m.group(4):
        return True
    if re.fullmatch(r"(?:19|20)\d\d", ip):
        return False  # 연도
    if ip.startswith("0") and len(ip) >= 4:
        return False  # ADR 번호(0042)
    return len(ip) >= 4


def summary_numbers(lines: List[str]) -> List[Tuple[int, Num]]:
    """'한 줄 요약' 제목부터 다음 `## ` 제목 전까지의 의미 있는 수치 -> [(줄번호, Num)]."""
    start = next((i for i, ln in enumerate(lines) if HEADING_RE.match(ln) and "한 줄 요약" in ln), None)
    if start is None:
        return []
    out: List[Tuple[int, Num]] = []
    fence: Optional[str] = None
    for i in range(start + 1, len(lines)):
        ln = lines[i]
        if re.match(r"^##\s", ln):
            break
        fm = re.match(r"^\s*(`{3,}|~{3,})", ln)
        if fm:
            fence = None if fence == fm.group(1)[0] else (fence or fm.group(1)[0])
            continue
        if fence:
            continue
        s = re.sub(r"`+[^`]*`+", " ", ln)
        s = re.sub(r"\]\([^)]*\)", "] ", s)
        s = re.sub(r"https?://\S+", " ", s)
        s = FILE_TOKEN_RE.sub(" ", s)
        s = DATE_TOKEN_RE.sub(" ", s)
        for m in NUM_RE.finditer(s):
            if meaningful(m):
                out.append((i + 1, match_to_num(m)))
    return out


def covered(x: Num, table: List[Num]) -> bool:
    def variants(n: Num) -> List[Tuple[float, float]]:
        v = [(n.value, n.tol)]
        return v + [(n.value / 100, n.tol / 100)] if n.pct else v
    for t in table:
        for a, ta in variants(x):  # 허용 오차는 요약에 적힌 값 자신의 자릿수 기준
            for b, _ in variants(t):
                if close(a, b, ta):
                    return True
    return False


# ---------------------------------------------------------------- 보고서 하나

def check_report(path: Path, loader: Loader, coverage: bool) -> Dict[str, Any]:
    lines = read_lines(path)
    res: Dict[str, Any] = {"report": str(path), "table_line": None, "rows": [], "uncovered": [],
                           "counts": {k: 0 for k in (OK, BAD, SRC, UNV, PARSE)}}
    found = find_table(lines)
    if found is None:
        return res
    res["table_line"] = found[0]
    table_nums: List[Num] = []
    for lineno, cells in found[1]:
        row = check_row(lineno, cells, loader)
        if row is None:
            continue
        res["rows"].append(row)
        res["counts"][row["status"]] += 1
        n = parse_report_number(clean_cell(cells[0])) if cells else None
        if n:
            table_nums.append(n)
    if coverage:
        res["uncovered"] = [{"line": ln, "text": n.text} for ln, n in summary_numbers(lines)
                            if not covered(n, table_nums)]
    return res


def render(res: Dict[str, Any]) -> str:
    out = ["== %s" % res["report"]]
    if res["table_line"] is None:
        out.append("  수치 대조 표를 찾지 못함('수치 대조' 제목 뒤의 표)")
        return "\n".join(out)
    for r in res["rows"]:
        src = r["source_cell"] or "(원천 없음)"
        val = "" if r["source_value"] is None else " 원천 %s" % fmt(r["source_value"])
        note = (" - " + r["note"]) if r["note"] else ""
        out.append("  [%s] %s <- %s (줄 %d%s%s)" % (r["status"], r["report_cell"] or "(빈 칸)", src, r["line"], val, note))
    if not res["rows"]:
        out.append("  (대조 행 없음)")
    if res["uncovered"]:
        items = ", ".join("%s(줄 %d)" % (u["text"], u["line"]) for u in res["uncovered"][:12])
        more = len(res["uncovered"]) - 12
        out.append("  WARN COVERAGE 요약·핵심 표의 수치 %d개가 대조 표에 없음: %s%s"
                   % (len(res["uncovered"]), items, " 외 %d개" % more if more > 0 else ""))
    c = res["counts"]
    out.append("  요약: " + ", ".join("%s %d" % (k, c[k]) for k in (OK, BAD, SRC, UNV, PARSE)))
    return "\n".join(out)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="보고서 수치를 원시 산출물과 대조")
    ap.add_argument("reports", nargs="*", help="대조할 보고서(없으면 reports/ 의 날짜 붙은 *.md 전부)")
    ap.add_argument("--root", default=str(Path(__file__).resolve().parent.parent), help="저장소 루트(기본: tools/ 의 부모)")
    ap.add_argument("--require-all", action="store_true", help="미검증·파싱 불가·표 없음도 실패로 본다")
    ap.add_argument("--no-coverage", action="store_true", help="요약 구간 수치 누락 검사(COVERAGE)를 끈다")
    ap.add_argument("--json", action="store_true", help="JSON으로 출력")
    args = ap.parse_args(argv)

    root = Path(args.root).resolve()
    if not root.is_dir():
        ap.error("root 폴더가 없음: %s" % root)
    targets: List[Path] = []
    if args.reports:
        for a in args.reports:
            p = Path(a)
            if not p.is_file() and not p.is_absolute() and (root / a).is_file():
                p = root / a
            if not p.is_file():
                ap.error("보고서 파일이 없음: %s" % a)
            targets.append(p.resolve())
    else:
        d = root / "reports"
        if d.is_dir():
            targets = sorted(f for f in d.iterdir() if f.is_file() and REPORT_NAME_RE.match(f.name))

    loader = Loader(root)
    results = []
    for t in targets:
        r = check_report(t, loader, not args.no_coverage)
        try:
            r["report"] = t.relative_to(root).as_posix()
        except ValueError:
            r["report"] = str(t)
        results.append(r)

    failed = False
    for r in results:
        c = r["counts"]
        r["ok"] = not (c[BAD] or c[SRC] or (args.require_all and (c[UNV] or c[PARSE] or r["table_line"] is None)))
        failed = failed or not r["ok"]
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        if not results:
            print("대조할 보고서가 없음")
        for r in results:
            print(render(r))
        total = {k: sum(r["counts"][k] for r in results) for k in (OK, BAD, SRC, UNV, PARSE)}
        if results:
            print("전체 %d건: %s" % (len(results), ", ".join("%s %d" % (k, v) for k, v in total.items())))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
