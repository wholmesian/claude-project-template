---
name: run-stage-instructions
description: Execute one stage from a self-contained instruction doc written by the design session (stages/*_INSTRUCTIONS.md) -- pre-flight checks, stop-and-report points, no design decisions, closing checklist (outputs, report, STATUS note, fileaudit record). Use when the user hands this session an instruction file to run.
---

# 실행 지시서로 단계 한 개 실행하기

이 저장소에서 실행 세션은 **실행 담당**이다. 설계·해석·판정은 설계 세션이 한다. 지시서는 자기완결적으로 쓰여 있으므로 **지시서가 1순위 근거**이고, 지시서와 `CLAUDE.md` 요약이 다르면 지시서를 따른다(단 `CLAUDE.md` 절대 규칙은 어떤 경우에도 우선).

## 1. 시작 전 점검

1. 지시서 전체를 읽고 §"멈추고 보고할 지점"과 §"실행 조건"을 먼저 뽑아 둔다.
2. 실행 조건을 하나씩 실제로 확인한다(선행 ADR이 커밋돼 있나, 입력 파일이 지정 경로에 있나, 이전 단계 검수가 통과인가). 하나라도 아니면 **아무것도 만들지 말고** 보고한다.
3. 변경 이력: 끝날 때 `record`만 한다. `snapshot`은 돌리지 않는다(`fileaudit` 스킬). git 커밋도 사용자가 요청할 때만 한다.
4. 기존 코드를 재사용하면, 판정에 쓰는 결과를 만들기 전에 **구현 검수**(기존 결과 재현)부터 한다. 지시서에 허용 오차가 있으면 그 값을 쓴다.

## 2. 실행 중

- 지시서의 정의·임계값·기간·시드를 **바꾸지 않는다.** 결과가 이상해 보여도 규칙을 고쳐 다시 돌리지 말고, 그대로의 결과와 "판단 필요" 항목으로 남긴다.
- 지시서에 없는 분석·실험을 덧붙이지 않는다. 유용해 보이면 보고서 §5 "새로 생긴 선택지"에 제안으로만 적는다(사용자 동의 전 실행 금지).
- 도메인 사실(컬럼 의미, 생성 규칙)을 2 - 3회 확인해도 모르면 추정으로 밀지 말고 멈춘다.
- 멈춤 지점에 걸리면: 그때까지의 산출물을 저장하고, 무엇이 걸렸는지 수치와 함께 보고한 뒤 종료한다. 다음 단계로 넘어가지 않는다.
- 중간 결과는 파일로 캐시해 재계산을 줄인다. 파일은 지시서가 지정한 경로에만 둔다.

## 3. 마무리 체크리스트

- [ ] 지시서 "산출물" 표의 파일이 전부 지정 경로에 있다(없는 것은 이유를 보고서에).
- [ ] 보고서를 `write-report` 스킬 규칙대로 `reports/`에 썼고 `reports/README.md` 목록에 한 줄 추가했다.
- [ ] 보고서의 수치를 원시 산출물과 대조해 부록 A에 적었다(못 한 것은 "미검증").
- [ ] 비밀·접속 정보가 stdout·로그·산출물·보고서 어디에도 없다.
- [ ] `fileaudit record`를 실행했다(`--actor "Claude Code (<모델>)"`). `CHANGELOG.md`·`.changelog/`는 직접 건드리지 않았다. `snapshot`·`diff --commit`은 하지 않았다.
- [ ] 보고서 맨 위에 완료 여부와 "판단이 필요한 것"을 적어, 설계 세션이 `docs/STATUS.md`를 갱신하고 `diff --commit`을 돌릴 수 있게 했다.
- [ ] `python tools/check_numbers.py와 python tools/lint_docs.py`가 불일치·ERROR 없이 통과했다.
- [ ] 이 세션에서 다음 단계로 이어가지 않았다(다음 단계는 새 세션).
