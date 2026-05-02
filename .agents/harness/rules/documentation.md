---
paths:
  - "**/*.py"
  - "**/*.md"
---

# 문서 동기화 규칙

코드(`*.py`)와 문서(`*.md`)가 변경되면 커밋 전에 `/sync-docs`로 문서를 코드와 일치시킨다.

## 원칙

- **Code-first**: 모든 문서 사실은 실제 코드로 검증한다. 환각 금지.
- **변경과 동시 반영**: 코드 변경을 포함한 PR에 문서 갱신을 함께 포함한다. "문서는 나중에"는 금지.
- **Priority**: Code > `CONTRIBUTING.md` > `CLAUDE.md` > 패키지 `README.md` > `docs/`. 불일치 시 상위 우선순위에 맞춰 하위를 수정한다.

## 실행 방법

- **기본**: 코드 변경을 완료하면 `/sync-docs`를 호출한다. 스킬이 `git diff`로 변경 범위를 감지해 `sync-dev-docs`(개발 문서) / `sync-user-docs`(사용자 문서)로 자동 라우팅한다.
- **범위 지정**: `/sync-docs dev|user|all [패키지명]`으로 대상을 좁힐 수 있다.
- **호출 시점**: 변경이 커밋되기 전, Phase 4(`/check`) 직후. PR 생성 전에 반드시 한 번은 실행한다.
- **동작 방식**: 스킬은 Write→Review 수렴 루프를 백그라운드 서브에이전트로 실행한다. 메인 에이전트는 오케스트레이터 역할만 맡는다.

## 동기화 대상 매핑 (참고)

| 코드 변경 | 라우팅 | 대표 문서 |
|----------|-------|---------|
| `core/*/src/**`, `plugins/*/src/**` | dev+user | 패키지 `README.md`, `docs/guides/`, `docs/api/` |
| `*/pyproject.toml` | dev+user | 패키지 `README.md`, `docs/plugin-api.md` |
| 공개 API·인터페이스 시그니처 | dev+user | 관련 가이드·API 레퍼런스 |
| 레이어·의존 방향·빌딩 블록 | dev | `ARCHITECTURE.md`, `docs/adr/` |
| 워크플로·도구 설정 | dev | `CONTRIBUTING.md`, `CLAUDE.md` |
| `docs/**`, `mkdocs.yml` 단독 수정 | user | 변경된 파일 자체 |

정확한 라우팅 규칙은 `sync-docs` 스킬이 결정한다. 라우팅을 수동으로 덮어쓰지 않는다.

## 금지 사항

- 코드를 수정한 PR에서 `/sync-docs` 호출을 건너뛰는 것
- 존재하지 않는 API/경로를 문서에 기재하는 것
- `CHANGELOG.md`를 수동 편집하는 것 (commitizen이 자동 생성)

## 예외

- 내부 구현 세부사항만 변경(공개 API 불변): 동기화 불필요
- 오탈자/포맷팅만 수정하는 문서 전용 PR: `/sync-docs` 생략 가능
