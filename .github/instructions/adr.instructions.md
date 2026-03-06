---
applyTo: "docs/adr/**/*.md"
---

# ADR 작성 규칙

## 구조

모든 ADR은 `docs/adr/TEMPLATE.md`의 구조를 따릅니다.

## 필수 섹션

- **맥락 (Context)**: 문제 상황과 배경
- **결정 동인 (Decision Drivers)**: 판단 기준
- **고려한 대안 (Considered Options)**: 최소 2개 이상 대안 비교
- **결정 (Decision)**: 선택과 근거
- **결과 (Consequences)**: 긍정/부정/중립적 영향

## 원칙

- **Code-first**: 모든 주장은 실제 코드로 검증 가능해야 합니다
- **대안 비교**: "왜 이것을 선택했는가"뿐 아니라 "왜 다른 것을 선택하지 않았는가"도 기술합니다
- **선행 조사**: 외부 프레임워크(Spring, ASP.NET 등)의 유사 패턴을 조사한 경우 반드시 기록합니다
- **상태 관리**: 새 ADR이 기존 ADR을 대체하면 기존 ADR을 `Superseded`로 변경하고 링크합니다

## 동기화

ADR 작성/수정 시 다음 파일도 함께 업데이트합니다:

- `docs/adr/README.md` — ADR 목록 테이블
- `ARCHITECTURE.md` — Architecture Decision Records 섹션
