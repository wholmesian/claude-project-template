---
name: init-project
description: One-time initialization of a new project copied from claude-project-template -- interview the user, fill CLAUDE.md placeholders, replace the template README, date ADR 0001 and STATUS.md, take the first fileaudit baseline. Use when the user asks to initialize or set up a project from this template.
---

# 새 프로젝트 초기화 (1회)

이 템플릿을 복사한 폴더에서 처음 한 번만 쓴다. 이미 초기화된 프로젝트(`CLAUDE.md`에 `{{PROJECT_NAME}}`이 없다)에서는 **덮어쓰지 않고** 멈춰서 사용자에게 알린다.

## 0. 사전 확인

1. `CLAUDE.md`에 `{{PROJECT_NAME}}`이 있는지 본다. 없으면 이미 초기화된 것이다. 멈춘다.
   채울 자리 목록은 `grep -rn "{{" . --exclude-dir=.git --exclude-dir=.claude --exclude-dir=optional --exclude="*TEMPLATE*"`로 센다(스킬·양식 파일의 `{{...}}`는 양식 자리표시라 채우지 않는다).
2. 사용자가 프롬프트에 준 값(프로젝트 이름·목적·성공 기준·비목표·원천 데이터·고유 규칙·연구형 여부·역할 분담 여부)을 정리한다.
3. 비어 있는 항목은 **추측하지 말고** AskUserQuestion으로 묻는다(한 번에 묻는다). 프로젝트 목적과 성공 기준이 비어 있으면 다른 것을 채우기 전에 먼저 묻는다.

## 1. 채우기

1. `CLAUDE.md`
   - 개요(이름·목적·성공 기준·비목표)를 채운다. 사용자 말을 그대로 쓰고 보태지 않는다.
   - 구조 표의 `{{프로젝트 고유 경로}}` 행과 절대 규칙 2·13의 자리를 채운다. 사용자가 모르는 항목은 줄을 지우지 말고 `{{미정 - 사용자 확인 필요}}`로 남기고 마지막 보고에 올린다.
   - 설계/실행 세션을 나누지 않는 프로젝트면 "역할 분담" 절을 줄인다(규칙 5는 유지).
   - 길이 점검: 150줄을 넘기면 줄인다. 상태·날짜가 들어가면 `docs/STATUS.md`로 옮긴다.
2. `README.md`는 템플릿 안내문이므로 **프로젝트용 README로 교체**한다(이름, 목적 한 문단, "작업 방식은 `CLAUDE.md`와 `docs/`" 링크, 시작 방법). 템플릿 안내가 필요하면 템플릿 저장소를 가리킨다.
3. `docs/STATUS.md`의 `{{YYYY-MM-DD}}`를 오늘 날짜로, 첫 실제 단계 행을 사용자와 정한 값으로 채운다(모르면 "대기"로 두고 보고).
4. `docs/decisions/0001-작업-방식-채택.md`와 `docs/decisions/README.md`의 날짜를 오늘로 바꾼다. 사용자가 이 방식 일부를 쓰지 않기로 했다면 ADR 0001의 "결정"을 그 범위로 고치고, 줄인 부분을 "영향"에 적는다.
5. `.env.example`을 프로젝트의 실제 키 이름으로 바꾼다(값은 쓰지 않는다). `.gitignore`의 `{{프로젝트 고유 제외 항목}}`을 채우거나 지운다.
6. `.claude/settings.json`은 그대로 두되, 사용자가 Claude의 `git push`를 허용하려 하면 해당 줄을 뺀다(사용자에게 확인 후).
7. `optional/`: 연구형이면 `optional/research-prereg/README.md`를 읽고 사용자와 필요한 부분(`trial_registry.csv`, 사전등록 ADR 양식)만 `docs/decisions/`·`stages/`로 옮기고, `CLAUDE.md` 절대 규칙에 한 줄을 추가한다. 아니면 `optional/`을 지운다.
8. 안 쓰는 스킬은 지우지 말고 사용자에게 묻는다. `init-project` 자체는 초기화가 끝나면 지워도 되고 두어도 된다(다시 돌려도 0단계에서 멈춘다).

## 2. 마무리

1. 위 `grep` 명령을 다시 돌려 남은 자리를 목록으로 만든다. 의도적으로 남긴 것(`{{미정 ...}}`)과 빠뜨린 것을 구분한다.
2. `python tools/fileaudit.py snapshot`으로 첫 baseline을 만든다(설계 세션 역할).
3. 사용자에게 보고한다: 채운 것, 남긴 것(이유), 지운 것, 사용자가 결정해야 할 것. **커밋·`git init`·푸시는 사용자가 요청할 때만 한다.**

## 하지 않는 것

- 프로젝트 내용(데이터 설명, 실험 설계)을 초기화 단계에서 만들어 채우지 않는다. 그건 첫 단계 지시서의 일이다.
- 사용자가 주지 않은 규칙을 "있을 법해서" 추가하지 않는다.
- `{{...}}`를 그럴듯한 값으로 메우지 않는다.
