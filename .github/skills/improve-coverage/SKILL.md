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

커버리지는 **모든 테스트(unit + integration)**를 실행해서 측정해야 합니다:

```bash
# 올바른 방법: 패키지 전체 테스트
cd <package-dir> && uv run pytest
```

> ❌ **금지**: `tests/unit/` 또는 `tests/integration/`만 실행하는 것
> pyproject.toml 설정에 의존하세요. 직접 `--cov` 옵션 지정 금지.

## Step 3: 미커버 라인 분류

100% 미달성 시 각 라인을 아래 기준으로 분류합니다:

| 분류 | 예시 | 조치 |
|------|------|------|
| `pragma: no cover` | 에러 핸들링, `TYPE_CHECKING` 블록 | 의도적 제외 — 추가 테스트 불필요 |
| 통합 테스트 필요 | 외부 시스템 콜백, 런타임 전용 브로커 경로 | 통합 테스트 추가/확장 |
| 테스트 누락 | 일반 분기, 조건문 | 단위 테스트 추가 |
| 동기/비동기 분리 | `KafkaEventConsumer` vs `AsyncKafkaEventConsumer` | **양쪽 모두** 테스트 필요 |

### `pragma: no cover` 사용 기준

**Mock 가득 찬 테스트보다 no cover가 낫습니다.** 아래 경우에만 `# pragma: no cover` 사용:

| 케이스 | 사유 예시 |
|--------|----------|
| 외부 시스템 콜백 | Kafka 메시지 배달 콜백 — 실제 브로커 없이 테스트 불가 |
| 비동기 런타임 루프 | `run_async` 메서드 — 통합 테스트에서 별도 스레드로 실행되어 커버리지 수집 불가 |
| 방어적 분기 | `if topic is None` — 정상 흐름에서 발생 불가하지만 타입 안전성 위해 존재 |
| 에러 로깅 | `except Exception` 블록 — 의도적으로 발생시키기 어려운 예외 |

**사유 작성 규칙:**
```python
# ✅ 올바른 예: 구체적 사유 명시
if message is None:  # pragma: no cover - Kafka 브로커가 null 메시지 반환 시 방어 코드
    return

# ❌ 금지: 사유 없음
if message is None:  # pragma: no cover
    return
```

> **원칙**: 테스트 코드가 프로덕션 코드보다 복잡하거나, mock이 실제 동작을 검증하지 못하면 → no cover 처리

## Step 4: 파일별 100% 달성

각 파일마다:

1. 단위 테스트로 커버 가능한 라인 → 단위 테스트 추가
2. 통합 테스트 필요 라인 → 기존 통합 테스트 확장 고려
3. 커버 불가 라인 → `# pragma: no cover` 표시 (사유 명시)

**100% 달성 확인 후** 다음 파일로 이동하세요.

## Step 5: 테스트 스타일 규칙

- **함수 기반만** 허용 (`class TestXxx` 금지)
- 네이밍: `test_<대상함수>_<시나리오>_expect_<기대결과>`
- 각 테스트 함수에 **docstring 필수**
- `scope="function"` fixture 기본

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
cd <package-dir> && uv run pytest
```

100% 미달성 이유를 명시적으로 보고하세요.
