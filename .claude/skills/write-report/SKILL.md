---
name: write-report
description: Write a human-readable stage report under reports/ following this repo's filename, tone, and template conventions. Use when a stage or a distinct conversation's work finishes and the context must survive for readers with no prior context.
---

# 보고서 작성 워크플로

`reports/`에는 **사람이 읽는 보고서**만 쌓는다. 기술 산출물(JSON·parquet·코드·그림 원본)은 `stages/<단계>/outputs/`에 두고 여기 오지 않는다. 목적: 이 프로젝트의 맥락을 전혀 모르는 사람(몇 달 뒤의 나, 새 동료, 공저자)이 읽고 이해하게 하는 것. 뼈대는 `reports/TEMPLATE.md`를 복사해서 쓴다.

## 언제 쓰나

**별도 대화에서 작업이 끝날 때마다 1건.** 단계 하나가 여러 대화로 쪼개지면 각각 1건. 재실행·수정도 유의미한 결과가 나왔으면 별도 1건. 지시서가 보고서 파일명을 지정하면 그것을 따른다.

## 파일명

```
YYYY-MM-DD_<단계>_<제목>.md
예) 2026-10-21_s1_데이터-이해.md
    2026-10-25_종합_중간-점검.md     ← 설계 세션의 종합은 단계 자리에 "종합"
```

## 말투

- 직관적이고 쉬운 말. 논문체 금지.
- 전문 용어는 처음 나올 때 한 문장으로 푼다. 비유를 적극 쓴다.
- 수식보다 말로 먼저 설명하고, 필요하면 LaTeX 수식을 덧붙인다.
- 표와 구체적 예시를 적극 쓴다.
- 숫자는 반드시 **무엇과 비교해서 크고 작은지**를 함께 쓴다.
- 단순 범위는 " - ", 날짜 기간은 " \~ ". 이스케이프하지 않은 물결표(`~`) 금지(`CLAUDE.md` 문서 표기 규칙). 기존 보고서를 고칠 때는 그 안의 물결표도 바꾼다.

## 쓰는 순서

1. 지시서의 §6 산출물 표와 핵심 표 지정을 확인한다.
2. `reports/TEMPLATE.md`를 복사해 헤더 표와 한 줄 요약부터 채운다.
3. 본문 §1 - §6을 쓴다. **짧게 쓰려고 배경 설명(§1, §2)을 빼지 않는다** — 그게 이 보고서의 존재 이유다. 본문 2 - 5쪽, 상세 수치는 부록이나 산출물로.
4. **수치 대조**: 본문과 핵심 표의 수치를 원시 산출물(`summary.json` 등)에서 다시 읽어 부록 A에 적는다. 못 한 것은 "미검증". `python tools/check_numbers.py reports/<이 보고서>.md`가 통과해야 한다.
5. §5 "판단이 필요한 것"은 목록과 선택지만. 결론은 설계 세션 몫이다(실행 세션이 쓸 때).
6. §6에 실패하거나 건너뛴 작업과 이유를 반드시 적는다.
7. `reports/README.md` 목록 맨 아래에 한 줄 append한다.

## 주의

- 비밀·접속 정보를 쓰지 않는다.
- 이미 쓴 보고서는 고치지 않는다. 정정은 새 보고서 + 옛 보고서 맨 위 한 줄.
- 결정이 필요한 내용이 나오면 보고서에 결론을 쓰지 말고 `write-adr` 스킬(설계 세션)로 넘긴다.
