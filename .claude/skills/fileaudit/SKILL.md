---
name: fileaudit
description: Track verified file changes across a work session with tools/fileaudit.py (snapshot before work, diff --commit after work, record for self-reported claims). Use at the start and end of any delegated session or subagent work in this repo.
---

# fileaudit 워크플로

`tools/fileaudit.py`는 "에이전트가 뭘 고쳤다고 말한 것"과 "실제로 디스크 해시가 바뀐 것"을 구분해 **검증된 사실**로 남기는 도구다. Python 표준 라이브러리만 쓴다. (Windows에서 `python`이 없으면 `py` 또는 `venv\Scripts\python.exe`로 바꿔 읽는다.)

## 누가 무엇을 돌리나

| 시점 | 명령 | 담당 |
|---|---|---|
| 작업 지시 전 | `snapshot` | 설계 세션 — baseline 고정 |
| 실행 중/직후 | `record` | 실행 세션 — 본인이 주장하는 변경 |
| 결과를 받은 뒤 | `diff --commit` | 설계 세션 — 실제 변경 검증 + 기록 |

**실행 세션은 `record`만 한다. `snapshot`과 `diff --commit`은 돌리지 않는다.** `snapshot`은 기존 baseline을 덮어쓰므로, baseline 이후 기록되지 않은 변경이 있으면 그 흔적이 사라진다. 지시서가 실행 세션에 snapshot을 시키면 지시서 오류로 보고 돌리지 말고 보고한다. 변경 여부만 보려면 `diff`를 `--commit` 없이 돌린다(dry run, 아무것도 기록하지 않는다).

## 1. 작업 시작 전 — 스냅샷 (설계 세션)

```
python tools/fileaudit.py snapshot
```

## 2. 결과를 검증할 때 — diff + commit (설계 세션)

```
python tools/fileaudit.py diff --label "<라벨>" --actor "<누가>" --reason "<왜>" --commit
```

`--commit`을 붙이면 한 번에 다음을 한다.
- `.changelog/runs/<UTC>_<label>.json`에 검증된 변경 기록(`kind: verified`)
- `CHANGELOG.md`에 append
- 새 baseline 스냅샷 저장

**diff 결과를 보고서의 "산출물" 주장과 맞춰 본다.** 보고서가 말한 파일이 diff에 없거나, diff에 있는데 보고서에 없는 파일이 있으면 그것이 검증의 요점이다.

## 3. 실행 세션이 의도를 남길 때 — record

```
python tools/fileaudit.py record --label "<라벨>" --actor "Claude Code (<모델>)" --reason "<왜>" --files "<파일1,파일2>" --note "<메모>"
```

이건 검증된 사실이 아니라 에이전트의 주장(claim)이며 `.changelog/runs/<...>.claim.json`에 `"kind": "claim"`으로 저장된다. `CHANGELOG.md`에는 `diff --commit` 결과만 append된다(claim은 append되지 않는다).

## 상태 파일

```
.changelog/
├── inventory.tsv         현재 baseline
├── inventory.prev.tsv    직전 baseline
└── runs/*.json           diff --commit / record 결과
```

`CHANGELOG.md`와 `.changelog/`는 도구가 자동으로 쓴다 — **직접 편집하지 않는다.**

## 주의

- `diff --commit`을 한참 안 돌리면 claim만 쌓이고 검증된 기록은 끊긴다. 단계를 마칠 때 설계 세션이 한 번 돌린다(마무리 체크리스트에 있다).
- 이 도구는 파일이 바뀌었는지만 본다. 내용이 맞는지는 보고서 수치 대조와 구현 검수로 확인한다.
- 스캔 제외: `venv/`, `.git/`, `.changelog/`, `__pycache__/`, `node_modules/`, `.ipynb_checkpoints/`, `*.pyc`, `.DS_Store`, `Thumbs.db`, `.env`(`.env.example`은 포함). 8MB 이하는 sha256, 초과는 크기+mtime만 기록한다.
