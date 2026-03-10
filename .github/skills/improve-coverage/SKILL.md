---
name: improve-coverage
description: Improve test coverage for a Spakky Framework package. Use this skill when asked to raise, fix, or measure coverage for any package under core/ or plugins/.
---

# 커버리지 개선 워크플로우

아래 단계를 **반드시 순서대로** 수행하세요.

## Step 1: 기존 테스트 구조 확인

```bash
ls -la tests/
# unit/, integration/ 디렉토리 존재 여부 확인
```

많은 패키지가 `unit/`과 `integration/` 디렉토리로 분리되어 있습니다.
**기존 통합 테스트가 이미 해당 라인을 커버하고 있을 수 있습니다.**

## Step 2: 전체 테스트로 커버리지 측정

커버리지는 **run_coverage.py 스크립트**를 사용하여 측정합니다:

```bash
# 단일 패키지 커버리지 측정
uv run python scripts/run_coverage.py --package <package-name>

# 예시: spakky-sqlalchemy 패키지
uv run python scripts/run_coverage.py --package spakky-sqlalchemy

# 전체 패키지 커버리지 측정 (병렬 실행)
uv run python scripts/run_coverage.py
```

> ❌ **금지**: `cd <dir> && uv run pytest` 직접 실행
> ❌ **금지**: `--cov` 옵션 직접 지정
> 스크립트가 pyproject.toml 설정과 커버리지 XML 생성을 자동 처리합니다.

## Step 3: 미커버 라인 분류

100% 미달성 시 각 라인을 아래 기준으로 분류합니다:

| 분류 | 예시 | 조치 |
|------|------|------|
| `pragma: no cover` | 에러 핸들링, `TYPE_CHECKING` 블록 | 의도적 제외 — 추가 테스트 불필요 |
| 통합 테스트 필요 | 외부 시스템 콜백, 런타임 전용 브로커 경로 | 통합 테스트 추가/확장 |
| 테스트 누락 | 일반 분기, 조건문 | 단위 테스트 추가 |
| 동기/비동기 분리 | `KafkaEventConsumer` vs `AsyncKafkaEventConsumer` | **양쪽 모두** 테스트 필요 |

### `pragma: no cover` 사용 기준

**Mock 가득 찬 테스트보다 no cover가 낫습니다.** 아래 경우에만 사용:
- 외부 시스템 콜백 (Kafka/RabbitMQ)
- 비동기 런타임 루프 (별도 스레드 실행)
- 방어적 분기 (정상 흐름 불가)
- 에러 로깅 (`except Exception`)

**사유 작성**: def 라인 끝에 `# pragma: no cover - 사유` 형태로 작성.

> **원칙**: 테스트 코드가 프로덕션보다 복잡하거나 mock이 무의미하면 → no cover

## Step 4: 파일별 100% 달성

각 파일마다:

1. 단위 테스트로 커버 가능한 라인 → 단위 테스트 추가
2. 통합 테스트 필요 라인 → 기존 통합 테스트 확장 고려
3. 커버 불가 라인 → `# pragma: no cover` 표시 (사유 명시)

**100% 달성 확인 후** 다음 파일로 이동하세요.

## Step 5: 테스트 스타일 규칙

테스트 규칙은 `test-writing.instructions.md`가 자동 적용됩니다 (함수 기반, 네이밍 규칙, docstring 등).

### Parametrized Fixture 주의사항

`@pytest.fixture(params=[...])` 사용 시, `None` 파라미터가 포함되면 이전 값이 남아있을 수 있습니다:

```python
# ❌ 잘못된 예: 이전 파라미터 값이 환경변수에 남음
@pytest.fixture(params=["value", None])
def config_fixture(request):
    if request.param is not None:
        environ["KEY"] = request.param
    yield
    # None 케이스에서 이전 "value"가 여전히 남아있음

# ✅ 올바른 예: 명시적으로 정리
@pytest.fixture(params=["value", None])
def config_fixture(request):
    key = "KEY"
    if request.param is not None:
        environ[key] = request.param
    else:
        environ.pop(key, None)  # 명시적 제거
    yield
```

## Step 6: 최종 검증

```bash
# 단일 패키지
uv run python scripts/run_coverage.py --package <package-name>

# 전체 패키지
uv run python scripts/run_coverage.py
```

100% 미달성 이유를 명시적으로 보고하세요.
