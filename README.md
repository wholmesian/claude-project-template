# claude-project-template

Claude로 프로젝트를 할 때 쓰는 **작업 방식 템플릿**이다. 설계 세션(Cowork)과 실행 세션(Claude Code)을 나누고, 결정(ADR)·보고서·변경 검증(fileaudit)을 일정한 구조로 남긴다.
`kg-experiment-ripple`에서 쓰던 방식을 프로젝트에 종속되지 않게 일반화한 초안(v0.1, 2026-10-21)이다.

> 이 README는 **템플릿 안내문**이다. 새 프로젝트로 복사한 뒤 `init-project` 스킬이 프로젝트용 README로 바꾼다.

## 들어 있는 것

```
claude-project-template/
├── README.md                          이 문서
├── CLAUDE.md                          Claude가 매 세션 읽는 규칙과 지도 ({{...}} 자리를 채운다)
├── .claude/
│   ├── settings.json                  권한 초안: .env 읽기 거부, git push 거부
│   └── skills/
│       ├── init-project/              새 프로젝트 초기화 절차 (1회)
│       ├── run-stage-instructions/    지시서 실행: 시작 점검, 멈춤 지점, 마무리 체크리스트
│       ├── write-report/              보고서 작성 규칙
│       ├── write-adr/                 ADR 작성 절차
│       └── fileaudit/                 변경 검증 도구 사용 절차
├── docs/
│   ├── STATUS.md                      단계별 진행 현황 (상태의 유일한 기준)
│   └── decisions/                     ADR: README(규칙·목록), 0000-TEMPLATE, 0001(이 작업 방식 채택)
├── reports/                           사람이 읽는 보고서: README(목록), TEMPLATE
├── stages/                            단계 지시서와 단계별 코드·산출물: README, TEMPLATE_INSTRUCTIONS
├── tools/
│   ├── fileaudit.py                   파일 변경 검증 (참조 저장소에서 그대로 복사)
│   ├── lint_docs.py                   문서 정합성 린터: ADR·보고서 목록, STATUS 낡음, 물결표, 플레이스홀더
│   ├── check_numbers.py               보고서 수치를 원시 산출물(JSON·CSV)과 자동 대조
│   └── README.md
├── optional/research-prereg/          연구형 프로젝트용 사전등록 모듈 (필요 없으면 삭제)
├── .gitignore, .env.example
```

## 새 프로젝트 시작하기

### 1. 폴더를 만들고 템플릿을 복사한다

PowerShell에서 (`<새프로젝트>`를 바꾼다. `robocopy`는 종료 코드 1이 "복사 성공"이다). `.claude/`(스킬, 권한 설정)도 함께 복사된다.

```
mkdir C:\Users\user\Desktop\<새프로젝트>
robocopy C:\Users\user\Desktop\claude-project-template C:\Users\user\Desktop\<새프로젝트> /E /XD .git .changelog
```

### 2. Claude에게 할 말

Cowork이면 새 폴더를 연결한 세션에서, Claude Code이면 새 폴더에서 `claude`를 실행한 뒤 아래를 붙여넣는다. 알고 있는 항목만 채우고, 나머지는 비워 두면 Claude가 묻는다.

```
이 폴더는 claude-project-template을 복사한 새 프로젝트야.
.claude/skills/init-project/SKILL.md를 읽고 그 절차대로 초기화해줘.

- 프로젝트 이름:
- 목적(한 - 두 문장):
- 성공 기준:
- 비목표(하지 않을 것):
- 읽기 전용으로만 다룰 원천 데이터·시스템(없으면 "없음"):
- 이 프로젝트 고유의 절대 규칙(알고 있는 것만):
- 연구형인가(사전등록·holdout이 필요한가): 예 / 아니오
- 설계 세션과 실행 세션을 나눌 건가: 예 / 아니오

비어 있는 항목은 추측하지 말고 물어봐. 커밋과 git init은 내가 시킬 때만 해줘.
끝나면 채운 것, 일부러 비워 둔 것, 내가 결정해야 할 것을 보고해줘.
```

더 짧게 말해도 된다: "claude-project-template 방식으로 이 폴더를 초기화해줘(init-project 스킬). 프로젝트 목적은 ○○야. 나머지는 물어봐."

### 3. 초기화 뒤 직접 확인할 것

- `CLAUDE.md`를 읽는다. 개요·절대 규칙이 내 말과 맞는지, 150줄 안팎인지 본다. 이 파일이 길어지면 매 세션 비용이 커진다.
- 린터를 돌린다: `python tools/lint_docs.py`. 남은 `{{...}}`가 PLACEHOLDER 경고로 나온다(`{{미정 ...}}`은 Claude가 일부러 남긴 것이라 INFO). ERROR가 있으면 고친다.
- `.claude/settings.json`을 열어 본다. `git push` 거부가 싫으면 그 두 줄을 지운다.
- 그 뒤 `git init`과 첫 커밋은 직접 하거나 "첫 커밋 만들어줘"라고 시킨다.

## 일상 운영 루프

한 단계는 한 세션에서 끝낸다. 단계를 마친 세션에서 다음 단계를 이어서 하지 않는다.

| 순서 | 어디서 | 할 말 (예) |
|---|---|---|
| 1 | 설계 세션 | "다음 단계(○○) 지시서를 `stages/TEMPLATE_INSTRUCTIONS.md` 양식으로 써줘. 멈춤 지점과 사전 정의값을 꼭 넣어줘." 그다음 `python tools/fileaudit.py snapshot` |
| 2 | 새 실행 세션 | "`stages/S1_..._INSTRUCTIONS.md`를 `run-stage-instructions` 스킬 절차로 실행해줘." |
| 3 | 같은 실행 세션 | "끝났으면 `write-report`로 보고서를 쓰고(부록 A 대조 표에 원천 `경로#키`까지 적어), `python tools/check_numbers.py reports/<새 보고서>.md`와 `python tools/lint_docs.py`를 돌려 통과시키고, `fileaudit record`까지 해줘." |
| 4 | 설계 세션 | "S1 결과를 검증해줘: `fileaudit diff`(dry run) 결과와 보고서의 산출물 주장을 맞춰 보고, `check_numbers.py`를 다시 돌리고, 대조 표에 없는 수치가 있는지(COVERAGE 경고) 보고, '판단이 필요한 것'을 정리해줘." |
| 5 | 설계 세션 | "이 결정을 `write-adr`로 기록해줘." 그리고 "STATUS.md를 갱신하고 `lint_docs.py --strict`가 통과하는지 확인한 뒤 `diff --commit`을 돌려줘." |
| 6 | 사용자 | 필요하면 "지금까지 변경을 커밋해줘." (커밋·푸시는 시킬 때만 한다) |

## 이 템플릿의 원칙

1. **사실마다 정본은 하나**: 결정 = ADR, 결과 = 보고서, 상태 = STATUS.md, 변경 = `.changelog/`. `CLAUDE.md`에는 바뀌는 상태를 적지 않는다.
2. **설계와 실행을 분리**: 실행 세션은 설계 판단을 하지 않고 "판단 필요"로 멈춘다. 결론은 설계 세션과 사용자 몫이다.
3. **주장보다 증거**: 에이전트의 보고는 주장이다. 파일 변경은 fileaudit으로, 보고서 수치는 원시 산출물과 대조로, 재사용 코드는 기존 결과 재현으로 확인한다.
4. **불변 구역**: 원천 데이터는 읽기만, 종결된 단계의 산출물과 보고서는 고치지 않고 새 파일로 정정한다.
5. **비밀은 규칙이 아니라 설정으로 막는다**: `.env`는 git 제외 + 읽기 거부 권한. (한계: Bash로 파일을 읽는 우회까지 막지는 못한다. 규칙 1과 함께 쓴다.)
6. **한 단계 = 한 세션 + 자기완결 지시서 + compact 지침**: 대화 기록이 토큰을 먹는 것을 막고, 인수인계를 문서로 한다.
7. **결정은 지우지 않고 대체한다**: ADR은 상태만 바꾸고 새 번호로 쓴다.
8. **기준은 결과를 보기 전에 고정한다**(연구형): `optional/research-prereg`.

## 점검 도구

세 도구 모두 Python 3.9+ 표준 라이브러리만 쓰고 Windows/Linux에서 같게 동작한다. 자세한 옵션은 `tools/README.md`.

| 도구 | 무엇을 확인하나 | 못 하는 것 |
|---|---|---|
| `fileaudit.py` | 에이전트가 바꿨다고 한 파일과 실제로 바뀐 파일 | 내용이 옳은지 |
| `lint_docs.py` | ADR·보고서 목록이 실제 파일과 맞는지, ADR 상태 불일치, STATUS.md가 새 보고서·ADR·변경 기록보다 낡았는지, `diff --commit` 누락 의심, 물결표 규칙, 남은 `{{...}}`, CLAUDE.md 길이·날짜, `.env` 보호 | 문서 내용이 옳은지, STATUS.md의 상태 값이 사실인지 |
| `check_numbers.py` | 보고서 부록 A 표에 적은 수치를 원시 산출물(JSON·CSV)에서 다시 읽어 대조, 요약·핵심 표의 수치가 그 표에 빠졌는지(COVERAGE) | 표에 올리지 않은 수치, 해석이 맞는지, JSON·CSV 외 형식(parquet·xlsx는 먼저 CSV·JSON으로 내보내야 한다) |

- 둘 다 **점검이지 강제가 아니다.** 돌려야 효과가 있다. 지시서 마무리 체크리스트와 위 운영 루프에 넣어 두었다.
- `check_numbers.py`는 사람이 대조 표에 쓴 만큼만 본다. 중요한 수치를 표에 안 올리면 모른다. COVERAGE 경고는 요약·핵심 표에 한해서 그 누락을 잡아 준다.
- `lint_docs.py`의 STALE-STATUS는 보고서 파일명 날짜, ADR 날짜, `.changelog` 기록 시각 중 가장 새것을 STATUS.md의 "최종 갱신"과 비교한다. 참조 저장소의 낡음(STATUS 10-08, CHANGELOG 09-28 이후 정지)이 이 방식으로 잡힌다.

## 참조 저장소에서 확인한 약점과 이 템플릿의 대응

`kg-experiment-ripple`을 읽으면서 확인한 것이다. 템플릿이 그대로 따라 하지 않은 부분이기도 하다.

| 확인한 것 | 대응 |
|---|---|
| `docs/STATUS.md`는 2026-10-08 이후, `CHANGELOG.md`는 2026-09-28 이후 갱신이 없다. 같은 기간 ADR(0058까지)과 커밋은 계속됐다. "유일한 기준"이라는 표가 손으로 갱신하는 절차에 의존해서 먼저 낡았다 | 지시서 마무리 체크리스트에 STATUS 갱신 요청과 `diff --commit`을 넣었다. `lint_docs.py`가 STATUS.md 낡음(STALE-STATUS)과 `diff --commit` 누락 의심(STALE-CHANGELOG)을 경고한다. 그래도 돌리는 것은 사람(또는 지시서 체크리스트)이므로 안 돌리면 낡는다 |
| `CLAUDE.md`가 14.6KB이고 날짜가 박힌 "현재 단계" 문단과 줄 하나가 수백 자인 구조 표가 들어 있다. 상태는 적지 않는다는 규칙을 스스로 어겼다 | 개요에서 상태를 빼고 STATUS.md로 보냈다. `init-project`에 150줄 점검을 넣었다 |
| 보고서 폴더가 `reports-1`부터 `reports-4`까지 단계마다 갈라져 "ADR의 `reports/`는 `reports-1/`을 뜻한다" 같은 설명과 규칙 예외가 쌓였다 | `reports/` 하나로 합치고 목록의 `단계` 열로 구분한다 |
| ADR이 0058까지(56건) 쌓였고 상당수가 "결과 판정"이다. 목록 한 줄이 문단 길이라 목록이 본문과 중복된다 | "결과 판정은 보고서에" 기준과 "목록은 한 줄" 규칙을 `docs/decisions/README.md`에 넣었다 |
| ADR 번호가 두 저장소에 걸쳐 이어 쓰여(0053은 다른 저장소) 이 저장소 목록에 빈 번호가 있다 | 번호는 저장소별, 타 저장소는 `저장소명:NNNN`으로 가리키게 했다 |
| 비밀 보호가 규칙 문장뿐이고 `.claude/settings.json`이 없다 | 권한 초안을 넣었다 |
| 보고서 목록 위치 규칙이 서로 달랐다(스킬은 맨 아래 append, 실제 목록은 최신이 위) | 맨 아래 append로 통일했다 |

## 복사하지 않은 것

- `.env`와 값이 든 설정, 데이터, `venv/`, 단계 폴더, 도메인 ADR 56건, 보고서, `.changelog/`·`CHANGELOG.md`(자동 생성이라 새 프로젝트에서 새로 시작한다).
- `query-thinkpool-db` 스킬: 사내 DB 전용이라 일반화하지 않았다. 새 프로젝트에 외부 DB가 있으면 같은 틀(연결 헬퍼 재사용, 읽기 전용 가드, 대형 테이블 필터, 서버별 주의)로 프로젝트용 스킬을 새로 만든다.
- 설계 세션이 쓰는 "Cowork 프로젝트 문서" 쪽 자료. 이 저장소 밖에 있다.

## 아직 없는 것 (필요하면 추가)

- 점검 도구를 자동으로 돌리는 장치(git pre-commit 훅 등). 지금은 사람이나 체크리스트가 돌린다. 훅을 넣으면 `lint_docs.py --strict`를 커밋 전에 강제할 수 있다.
- parquet·xlsx 원천을 직접 읽는 `check_numbers.py` 확장(표준 라이브러리만 쓰는 제약 때문에 뺐다).
- 이 템플릿 자체의 버전 관리: 새 프로젝트에서 개선한 규칙을 어디로 되돌릴지. 지금은 이 폴더를 직접 고치는 것이 전부다.

## 이 템플릿을 고칠 때

개선은 이 폴더에서 한다. 참고: Cowork 세션에서 파일을 내려 쓰는 도구는 `.claude/` 폴더에 쓰지 못한다. `.claude/` 안의 스킬과 `settings.json`은 직접 편집하거나 Claude Code 세션에서 고친다. 이미 만든 프로젝트에는 자동 반영되지 않으므로, 바뀐 파일(주로 `.claude/skills/`와 `docs/decisions/README.md`)을 프로젝트에 복사하고 그 프로젝트에 ADR 한 건으로 기록한다.
