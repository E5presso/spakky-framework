---
name: improve-coverage
description: Spakky Framework 패키지의 테스트 커버리지를 개선합니다
argument-hint: "[package-name]"
user-invocable: true
---

# 커버리지 개선 워크플로우

아래 단계를 **반드시 순서대로** 수행하세요.

> **관련 스킬**: 단순 커버리지 확인만 필요하면 → `/check-coverage`

## Step 1: 기존 테스트 구조 확인

`tests/` 디렉토리에 `unit/`, `integration/` 존재 여부 확인.
**기존 통합 테스트가 이미 해당 라인을 커버하고 있을 수 있습니다.**

## Step 2: 전체 테스트로 커버리지 측정

```bash
uv run python scripts/run_coverage.py --package <package-name>
```

> **금지**: `cd <dir> && uv run pytest` 직접 실행, `--cov` 옵션 직접 지정

## Step 3: 미커버 라인 분류

| 분류 | 예시 | 조치 |
|------|------|------|
| `pragma: no cover` | 에러 핸들링, `TYPE_CHECKING` 블록 | 의도적 제외 |
| 통합 테스트 필요 | 외부 시스템 콜백, 런타임 전용 경로 | 통합 테스트 추가/확장 |
| 테스트 누락 | 일반 분기, 조건문 | 단위 테스트 추가 |
| 동기/비동기 분리 | `Consumer` vs `AsyncConsumer` | **양쪽 모두** 테스트 |

### `pragma: no cover` 사용 기준

**Mock 가득 찬 테스트보다 no cover가 낫습니다.** 아래 경우에만:
- 외부 시스템 콜백 (Kafka/RabbitMQ)
- 비동기 런타임 루프 (별도 스레드 실행)
- 방어적 분기 (정상 흐름 불가)
- 에러 로깅 (`except Exception`)

**사유 작성**: `# pragma: no cover - 사유` 형태.

> **원칙**: 테스트 코드가 프로덕션보다 복잡하거나 mock이 무의미하면 → no cover

## Step 4: 파일별 100% 달성

각 파일마다:
1. 단위 테스트로 커버 가능한 라인 → 단위 테스트 추가
2. 통합 테스트 필요 라인 → 기존 통합 테스트 확장 고려
3. 커버 불가 라인 → `# pragma: no cover` 표시 (사유 명시)

**100% 달성 확인 후** 다음 파일로 이동.

## Step 5: Parametrized Fixture 주의사항

```python
# ❌ 잘못된 예: 이전 파라미터 값이 환경변수에 남음
@pytest.fixture(params=["value", None])
def config_fixture(request):
    if request.param is not None:
        environ["KEY"] = request.param
    yield

# ✅ 올바른 예: 명시적으로 정리
@pytest.fixture(params=["value", None])
def config_fixture(request):
    if request.param is not None:
        environ["KEY"] = request.param
    else:
        environ.pop("KEY", None)
    yield
```

## Step 6: 최종 검증

```bash
uv run python scripts/run_coverage.py --package <package-name>
```

100% 미달성 이유를 명시적으로 보고하세요.

$ARGUMENTS
