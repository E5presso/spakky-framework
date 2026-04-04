---
name: check-coverage
description: Spakky Framework 패키지의 테스트 커버리지를 측정합니다
argument-hint: "[package-name]"
user-invocable: true
---

# 커버리지 확인 워크플로우

패키지의 테스트 커버리지를 측정합니다.

> **관련 스킬**: 커버리지 개선이 필요하면 → `/improve-coverage`

## 커버리지 측정 명령어

**반드시 `scripts/run_coverage.py`를 사용하세요.**

```bash
# 단일 패키지 커버리지 측정
uv run python scripts/run_coverage.py --package <package-name>

# 전체 패키지 커버리지 측정 (병렬 실행)
uv run python scripts/run_coverage.py

# 순차 실행 (디버깅용)
uv run python scripts/run_coverage.py --sequential
```

## 금지 사항

| 금지 | 이유 |
|------|------|
| `cd <dir> && uv run pytest --cov` | pyproject.toml 설정 무시 |
| `pytest --cov` 직접 실행 | 경로 설정 오류 가능 |

## 출력

스크립트가 자동으로:
- 각 패키지 `coverage.xml` 생성
- 커버리지 요약 테이블 출력
- 라인/브랜치 커버리지 % 표시

$ARGUMENTS
