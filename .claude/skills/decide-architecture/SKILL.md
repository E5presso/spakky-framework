---
name: decide-architecture
description: 아키텍처 의사결정 시 기존 ADR을 참조하고 새 ADR을 작성합니다
argument-hint: "[주제]"
user-invocable: true
---

# 아키텍처 의사결정 워크플로우

## Step 1: 기존 ADR 확인

`docs/adr/README.md`를 읽어 기존 의사결정 목록 파악.
관련 ADR이 있으면 해당 ADR을 읽고 맥락 파악.

## Step 2: ARCHITECTURE.md 참조

`ARCHITECTURE.md`에서 관련 섹션을 읽어 현재 아키텍처 이해.

## Step 3: 논의 및 대안 탐색

- 기존 ADR과 충돌하는 부분이 있으면 명시적으로 알림
- 대안 제시 시 각각의 장단점을 구체적으로 비교

## Step 4: ADR 작성

의사결정 확정 시:

1. `docs/adr/TEMPLATE.md`로 ADR 구조 확인
2. `docs/adr/README.md`에서 다음 번호 확인
3. `docs/adr/NNNN-<slug>.md` 파일 생성
4. `docs/adr/README.md` 목록에 항목 추가
5. `ARCHITECTURE.md`의 ADR 테이블에 항목 추가
6. 기존 ADR 대체 시 이전 ADR 상태를 `Superseded`로 변경

### ADR 필수 섹션

- **맥락 (Context)**: 문제 상황과 배경
- **결정 동인 (Decision Drivers)**: 판단 기준
- **고려한 대안 (Considered Options)**: 최소 2개 이상 대안 비교
- **결정 (Decision)**: 선택과 근거
- **결과 (Consequences)**: 긍정/부정/중립적 영향

### ADR 작성 원칙

- **Code-first**: 모든 주장은 실제 코드로 검증 가능
- **대안 비교**: "왜 선택했는가"뿐 아니라 "왜 다른 것을 선택하지 않았는가"도 기술

## Step 5: 관련 문서 동기화

- `ARCHITECTURE.md` — 최신 목표 아키텍처 반영
- `docs/adr/README.md` — ADR 목록 테이블
- 관련 패키지 `README.md` — API 변경 반영
- `CONTRIBUTING.md` — 개발 가이드 변경 반영

CHANGELOG.md는 자동 생성이므로 수정하지 않습니다.

$ARGUMENTS
