# tools — 검증 도구

세 도구 모두 Python 3.9+ 표준 라이브러리만 쓰며 Windows/Linux에서 같게 동작한다. 저장소 루트는 `tools/`의 부모이고 `--root`로 바꿀 수 있다. (Windows에서 `python`이 없으면 `py` 또는 `venv\Scripts\python.exe`.)
**전부 점검 도구이고 강제 장치가 아니다.** 단계 마무리 체크리스트(`stages/TEMPLATE_INSTRUCTIONS.md`)에 넣어 두었지만 돌리는 것은 사람 또는 세션이다.

| 도구 | 한 줄 | 담당 |
|---|---|---|
| `fileaudit.py` | 에이전트가 바꿨다고 한 파일 vs 실제로 바뀐 파일 | 설계 세션 snapshot·diff, 실행 세션 record |
| `lint_docs.py` | 문서 목록·상태·표기의 정합성 | 단계 마무리 때 아무 세션 |
| `check_numbers.py` | 보고서 수치 vs 원시 산출물 | 보고서를 쓴 세션이 통과시키고, 설계 세션이 다시 돌린다 |

---

## fileaudit.py — 파일 변경 검증

여러 세션·서브에이전트에 작업을 맡긴 뒤, 실제로 디스크에서 무엇이 바뀌었는지를 **검증된 사실**로 남긴다. 에이전트가 "이 파일을 고쳤다"고 말하는 것과 실제로 파일 해시가 바뀐 것은 다르다. 이 도구는 후자만 "검증됨"으로 기록한다. 담당과 절차는 `.claude/skills/fileaudit`.

```
python tools/fileaudit.py snapshot
python tools/fileaudit.py diff --label "<라벨>" --actor "<누가>" --reason "<왜>"            # dry run
python tools/fileaudit.py diff --label "<라벨>" --actor "<누가>" --reason "<왜>" --commit   # 기록
python tools/fileaudit.py record --label "<라벨>" --actor "<누가>" --reason "<왜>" --files "a,b" --note "<메모>"
```

상태 파일(`.changelog/`)과 `CHANGELOG.md`는 이 도구가 쓴다. 직접 편집하지 않는다.

```
.changelog/
├── inventory.tsv         현재 baseline
├── inventory.prev.tsv    직전 baseline
└── runs/
    ├── <UTC>_<label>.json         diff --commit 결과 (kind: verified)
    └── <UTC>_<label>.claim.json   record 결과 (kind: claim, 에이전트 본인의 주장)
```

- 스캔 제외: `venv/`, `.git/`, `.changelog/`, `__pycache__/`, `node_modules/`, `.ipynb_checkpoints/`, `*.pyc`, `.DS_Store`, `Thumbs.db`, `.env`(`.env.example`은 포함).
- 8MB 이하 파일은 sha256, 초과 파일은 크기와 mtime만 기록한다.
- **한계**: 파일이 바뀌었는지만 확인한다. 내용이 옳은지는 확인하지 않는다(그건 `check_numbers.py`와 구현 검수 몫). 8MB 이하 파일은 전부 해시하므로 데이터 파일이 많은 폴더가 저장소 안에 있으면 스캔이 느려질 수 있다. 큰 데이터는 저장소 밖에 두거나 `EXCLUDED_DIR_NAMES`에 추가한다.

---

## lint_docs.py — 문서 정합성 린터

```
python tools/lint_docs.py [--root DIR] [--strict] [--stale-days N] [--only CODE[,CODE...]] [--json]
```

한 건당 한 줄 `[ERROR|WARN|INFO] 코드 경로:줄 메시지`로 나오고 마지막에 요약이 붙는다. 종료 코드: ERROR가 있으면 1(`--strict`이면 WARN도 1), 정상 0, 사용법 오류 2. `--stale-days`는 낡음 허용 일수(기본 3).

| 코드 | 수준 | 무엇을 잡나 |
|---|---|---|
| `TILDE` | ERROR | 이스케이프하지 않은 물결표(`~`). 코드 블록·코드 스팬·`\~`는 제외 |
| `PLACEHOLDER` | WARN (`{{미정 ...}}`은 INFO) | 채우지 않은 `{{...}}`. `.claude/`, `optional/`, 파일명에 `TEMPLATE`가 든 파일은 제외 |
| `ADR-INDEX` | ERROR | ADR 파일이 `docs/decisions/README.md` 목록에 없거나, 목록 행의 파일이 없음 |
| `ADR-DUP` / `ADR-GAP` | ERROR / WARN | ADR 번호 중복 / 번호 빠짐 |
| `ADR-STATUS` | ERROR | 파일의 `- 상태:`와 목록의 상태가 다름(앞 토큰 기준. `대체됨(→ NNNN)`은 번호까지) |
| `ADR-SUPERSEDE` | ERROR | `대체됨(→ NNNN)`의 대상 ADR이 없음(`저장소명:NNNN`은 제외) |
| `ADR-LONG` | WARN | 목록 한 줄이 220자 초과(목록은 결정 한 문장) |
| `RPT-NAME` / `RPT-INDEX` | WARN / ERROR | 보고서 파일명 규칙 위반 / `reports/README.md` 목록과 실제 파일 불일치(양방향) |
| `STALE-STATUS` | WARN | `docs/STATUS.md`의 "최종 갱신"이 가장 새로운 보고서 파일명 날짜·ADR 날짜·`.changelog` 기록 시각보다 `--stale-days` 넘게 이전 |
| `STALE-CHANGELOG` | WARN | `.changelog/runs`에서 claim(`record`)이 검증 기록(`diff --commit`)보다 `--stale-days` 넘게 새롭거나 검증 기록이 0건 |
| `CLAUDE-LEN` / `CLAUDE-DATE` | WARN | CLAUDE.md가 150줄 초과 / 날짜가 적힌 줄이 있음("# Compact instructions" 절 제외) |
| `ENV-IGNORE` | ERROR | `.gitignore`가 없거나 `.env` 줄이 없음 |
| `ENV-EXAMPLE` | WARN | `.env.example`에 값이 든 줄(출력에는 키 이름만 나온다) |

**한계**: 마크다운 파서가 아니라 줄 단위 규칙이다. 들여쓴 코드 블록·HTML 주석 안의 `~`·`{{`는 구분하지 못하고, 코드 스팬 안의 `|`는 표 칸을 가른다. 문서 내용이 옳은지, STATUS.md의 상태 값이 사실인지는 확인하지 못한다.

---

## check_numbers.py — 보고서 수치를 원시 산출물과 대조

```
python tools/check_numbers.py [보고서.md ...] [--root DIR] [--require-all] [--no-coverage] [--json]
```

보고서 부록 A("수치 대조") 표를 읽어, 각 행이 가리키는 원시 산출물을 다시 읽고 보고서에 적힌 수와 맞는지 확인한다. 보고서를 지정하지 않으면 `reports/`의 날짜 붙은 `*.md`를 전부 본다. 종료 코드: 불일치·원천 오류가 있으면 1, 정상 0, 사용법 오류 2. `--require-all`이면 미검증·파싱 불가·표 없음도 1.

**표 형식** (`reports/TEMPLATE.md` 부록 A):

| 보고서 수치 | 원시 산출물(경로, 키) | 대조 결과 |
|---|---|---|
| 0.044 | `stages/s1/outputs/summary.json#main.beta[0].t` | |
| 44.4% | `stages/s1/outputs/x.csv#mean[group=KW]` | |

- **보고서 수치**: 첫 숫자 하나만 본다. 유니코드 마이너스(`−`), 천 단위 쉼표, `+`, `%`, 과학 표기(`4.4e-6`)를 읽는다. 소수점 자릿수가 허용 오차를 정한다(0.044는 ±0.0005).
- **원시 산출물**: `경로#키`. JSON은 점과 `[번호]`로(`a.b[0].c`, 점이 든 키는 `["a.b"]`), CSV·TSV는 `열[행]`(행은 0부터 센 번호 또는 `다른열=값`). 경로는 `/`와 `\` 모두 받는다. 단위가 다르면 뒤에 ` *100`(또는 ` /100`). 칸이 비었거나 `-`이거나 대조 결과가 `미검증`이면 미검증이다.
- **`%`가 붙은 수치**에 곱셈 표시가 없으면 원값과 100배 값 중 맞는 쪽을 받고 어느 쪽이 맞았는지 적는다.

**판정**: `일치` / `불일치`(두 값을 함께 표시) / `원천 오류`(파일 없음, 키 없음, 숫자 아님, 루트 밖 경로, 행이 둘 이상 해당) / `미검증` / `파싱 불가`. 사람이 대조 결과 칸에 `일치`라고 썼는데 실제로 불일치면 "보고서의 대조 결과 주장과 다름"으로 따로 표시한다.

**COVERAGE 경고**: "한 줄 요약"부터 다음 `## ` 제목 전까지(핵심 표 포함)에 나온 의미 있는 수치(소수점 또는 `%`가 있거나 4자리 이상)가 대조 표에 없으면 알려 준다. 연도·날짜·ADR 번호(0042 같은 앞자리 0)·코드 스팬·파일명·링크 주소 안의 숫자는 제외한다. `--no-coverage`로 끈다.

**한계**: 표에 올린 수치만 본다(중요한 수치를 표에 안 올리면 COVERAGE는 요약·핵심 표 범위에서만 잡는다). 해석이 맞는지는 모른다. JSON·CSV·TSV만 읽는다(parquet·xlsx는 내보낸 파일을 가리킨다). 한 칸에 수치가 여러 개면 첫 숫자만 본다.

---

## 새 도구를 추가할 때

- 표준 라이브러리만 쓰고 Windows/Linux에서 같게 동작하게 한다.
- 이 파일에 한 단락 추가하고, 누가 언제 돌리는지 단계 마무리 체크리스트(`stages/TEMPLATE_INSTRUCTIONS.md`)나 `.claude/skills/`에 적는다.
- "에이전트의 주장"과 "도구가 확인한 사실"을 출력에서 구분한다.
- 비밀 값은 출력하지 않는다(키 이름만).
