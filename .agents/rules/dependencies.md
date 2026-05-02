---
paths:
  - "**/pyproject.toml"
---

# 의존성 관리 규칙

## 버전 지정

- 의존성 추가 시 **PyPI에서 최신 안정 버전을 조회**하여 지정한다
- 기억이나 추정에 의한 버전 지정 금지 — 반드시 `uv add` 또는 PyPI 조회로 확인
- `>=` 하한 지정 필수, 상한(`<`)은 breaking change가 알려진 경우에만

## 추가 절차

1. `uv add <패키지>` 로 추가 (버전 자동 해석)
2. `uv sync --all-extras --all-packages` 로 lock 파일 갱신
3. 추가된 의존성이 기존 패키지와 호환되는지 테스트 실행으로 확인

## 내부 의존성

- 코어/플러그인 간 의존 방향은 `monorepo.md` 참조
- 내부 패키지 의존은 `{ workspace = true }` 형태 사용
