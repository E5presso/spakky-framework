---
name: architecture-decision
description: 아키텍처 의사결정 시 기존 ADR을 참조하고 새 ADR을 작성합니다. 설계 논의, 아키텍처 변경, 대안 비교가 필요할 때 사용하세요.
---

# 아키텍처 의사결정 워크플로우

아키텍처 관련 논의나 설계 변경 요청을 받았을 때 이 워크플로우를 따르세요.

## Step 1: 기존 ADR 확인

`docs/adr/README.md`를 읽어 기존 의사결정 목록을 파악합니다.
현재 논의와 관련된 ADR이 있으면 해당 ADR을 읽고 맥락을 파악합니다.

## Step 2: ARCHITECTURE.md 참조

`ARCHITECTURE.md`에서 관련 섹션을 읽어 현재 아키텍처를 이해합니다.
설계 결정이 기존 아키텍처와 어떻게 관계되는지 파악합니다.

## Step 3: 논의 및 대안 탐색

- 기존 ADR과 충돌하는 부분이 있으면 명시적으로 알립니다
- 대안을 제시할 때 각각의 장단점을 구체적으로 비교합니다
- 외부 프레임워크 사례가 필요하면 Context7 또는 웹 검색을 활용합니다

## Step 4: ADR 작성

의사결정이 확정되면 `docs/adr/TEMPLATE.md`를 기반으로 새 ADR을 작성합니다:

1. `docs/adr/README.md`에서 다음 번호 확인
2. `docs/adr/NNNN-<slug>.md` 파일 생성 (TEMPLATE.md 구조 사용)
3. `docs/adr/README.md`의 목록에 항목 추가
4. `ARCHITECTURE.md`의 ADR 테이블에 항목 추가
5. 기존 ADR을 대체하는 경우 이전 ADR 상태를 `Superseded`로 변경

## Step 5: 관련 문서 동기화

ADR 내용에 따라 다음 문서를 업데이트합니다:

- `ARCHITECTURE.md` — 아키텍처 설명 반영
- 관련 패키지 `README.md` — API 변경 반영
- `CONTRIBUTING.md` — 개발 가이드 변경 반영

CHANGELOG.md는 자동 생성이므로 수정하지 않습니다.
