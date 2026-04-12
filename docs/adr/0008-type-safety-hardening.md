# ADR-0008: 타입 안전성 강화 — pyrefly ignore 박멸과 구조적 개선

- **상태**: Accepted
- **날짜**: 2026-04-13
- **관련**: Issue #116

## 맥락 (Context)

Spakky Framework 코드베이스에 `# pyrefly: ignore` 주석이 53개 산재해 있었다. 이 중 2개(의도된 ABC 인스턴스화, optional dependency lazy import)만 정당한 사유를 가졌고, 나머지 **44개는 타입 시스템 설계 결함이나 테스트 설계 결함을 회피하는 용도**로 사용되고 있었다.

집계 (스코프: `core/`, `plugins/`):

| 카테고리 | 개수 | 위치 |
|---------|------|------|
| protobuf 동적 속성 접근 (테스트) | 32 | `plugins/spakky-grpc/tests/unit/test_handler.py`, `tests/integration/_client.py` |
| name-mangled private attr 테스트 접근 | 4 | `plugins/spakky-grpc/tests/unit/test_bind_server.py`, `test_register_services.py` |
| grpc handler callable narrowing | 4 | `plugins/spakky-grpc/tests/unit/test_handler.py` |
| protobuf stub ValueType 한계 | 1 | `plugins/spakky-grpc/src/spakky/plugins/grpc/schema/descriptor_builder.py` |
| `UnsupportedFieldTypeError(list)` 시그니처 부정합 | 1 | `plugins/spakky-grpc/src/spakky/plugins/grpc/schema/type_map.py` |
| SchemaRegistry cross-package TypeVar narrowing | 4 | `plugins/spakky-sqlalchemy/src/spakky/plugins/sqlalchemy/persistency/repository.py` |
| async abstractmethod covariance | 2 | `core/spakky-domain/src/spakky/domain/application/{command,query}.py` |

`# pyrefly: ignore`를 회피 수단으로 계속 쓰면 타입 안전성이 점진적으로 썩는다. 문제를 표면에서 지우는 대신 **근본 원인을 제거**해야 한다.

## 결정 동인 (Decision Drivers)

- **타입 안전성 우선**: Spakky는 `Any` 금지, `Protocol` 금지, `cast` 최소화 같은 엄격한 타입 규율을 원칙으로 한다. `# pyrefly: ignore`는 그 원칙의 합법적 탈출구여야 하지 (의도된 소수), 상시 회피 수단이 되어선 안 된다.
- **야매 회피 금지**: 사용자 명시 — "야매로 때우지 말고 정당하고 proper한 해결책을 적용". 헬퍼 함수로 ignore를 압축하는 패턴, 테스트용 property로 내부 상태를 노출하는 패턴, `cast`로 타입 에러를 덮는 패턴은 모두 제외.
- **DRY, 단 현실적으로**: 이미 있는 3rd-party가 적합하면 쓰고, 없으면 만든다. 무거운 의존성 bloat는 피한다.
- **Breaking 허용**: 아직 널리 배포되지 않은 프레임워크이므로, 올바른 설계를 위해 breaking change 허용.

## 고려한 대안 (Considered Options)

### 문제 1: protobuf 동적 속성 ignore 34개 (spakky-grpc)

#### 대안 A-1: `mypy-protobuf`로 `.pyi` stub 생성

protobuf 표준 생태계 해법. `.proto` 파일로부터 `_pb2.pyi`를 생성하여 pyrefly가 동적 속성을 인식하게 한다.

- **장점**: 표준적, 검증됨.
- **단점**: **spakky-grpc에는 `.proto` 파일이 없다.** 런타임에 Python `@dataclass`로부터 `FileDescriptorProto`를 합성하는 구조이므로 `mypy-protobuf`가 적용되지 않는다.

#### 대안 A-2: spakky-grpc를 PydanticRPC/FastGRPC 기반으로 재구현 (DRY)

이미 존재하는 pydantic 기반 gRPC 라이브러리를 wrapping하여 spakky-fastapi 패턴 적용.

- 조사 결과:
  - **PydanticRPC** (i2y/pydantic-rpc): `.proto` 디스크 쓰기 + `grpcio-tools` subprocess. `grpc.aio.Server` 외부 주입 불가 (내부 소유).
  - **FastGRPC** (taogeyt/fast-grpc): `.proto` 디스크 쓰기 + `protoc` subprocess. `grpc.aio.Server` 외부 주입은 가능.
  - 둘 다 실사용 가능한 수준이지만, 현재 spakky-grpc DX (`@GrpcController`, `@Rpc`, `@ProtoField(n)`, 인메모리 descriptor 합성)를 그대로 유지하기에는 프로그래밍 모델이 너무 다르다. wrapping 레이어 자체가 크다.

- **장점**: 3rd-party DRY, 넓은 생태계.
- **단점**: 현 spakky-grpc DX(런타임 인메모리 합성, 클래스 기반 컨트롤러)를 포기하거나 두꺼운 어댑터 레이어 필요. spakky-grpc의 DX는 이미 준수하다는 평가.

#### 대안 A-3: BaseModel ↔ Message 전용 변환 라이브러리 사용

DTO를 `@dataclass`에서 `pydantic.BaseModel`로 교체하고, Message ↔ BaseModel 변환만 3rd-party에 맡긴다. spakky-grpc의 DX는 그대로 유지.

조사한 후보:

| 라이브러리 | 판정 | 사유 |
|-----------|------|------|
| `protobuf-to-pydantic` | ❌ | 스키마 코드생성만 지원. 인스턴스 변환 API 없음 |
| `pydanticprotobuf` | ❌ | `protobuf<4.0.0` 고정 (현대 grpcio와 충돌), pydantic v1 API, 2022년 이후 방치 |
| `pydantic-protobuf-gen` | ⚠️ | 변환 로직은 정확히 적합. 하지만 하드 의존성에 FastAPI + granian + hypercorn + SQLModel + peewee + jinja2 포함 (코어만 쓰려 해도 불가) |

#### 대안 A-4: `google.protobuf.json_format` 브릿지 인라인 ✅ **채택**

protobuf 공식 라이브러리에 이미 포함된 `json_format.Parse` / `MessageToJson`을 사용하여 BaseModel ↔ Message를 JSON 중간 표현으로 변환. pydantic v2의 `model_dump_json` / `model_validate_json`와 조합하면 수십 줄.

- **장점**:
  - 외부 3rd-party 의존성 추가 없음 (protobuf 표준)
  - BaseModel이 정적으로 타입 인식되어 테스트/프로덕션 모두 ignore 불필요
  - pydantic v2 네이티브
  - wire-format edge case(repeated, optional, nested, oneof, well-known types)를 protobuf 공식 구현이 처리
- **단점**:
  - JSON 중간 표현 오버헤드 (gRPC 자체 오버헤드 대비 미미)
  - 모든 필드가 JSON-representable 해야 함 (bytes→base64는 `json_format`이 자동 처리)

### 문제 2: name-mangled private attr 테스트 접근 (4개)

`BindServerPostProcessor._BindServerPostProcessor__application_context` 등을 테스트가 직접 참조.

#### 대안 B-1: 테스트용 property로 내부 상태 노출

- **장점**: 변경 최소
- **단점**: **야매 회피 해법.** 캡슐화 파괴를 감춘 채 문제를 없앰. 사용자 명시적 거부.

#### 대안 B-2: 테스트를 behavior-based로 재작성 ✅ **채택**

내부 상태(`__application_context`, `__container`) 검증을 제거하고 관찰 가능한 동작으로 검증.

- **장점**: 진짜 해법. 내부 구조 변경에 덜 취약한 테스트.
- **단점**: 테스트 재작성 분량 존재.

### 문제 3: SchemaRegistry cross-package TypeVar (4개)

`SchemaRegistry.get_type` / `from_domain`의 `ObjectT` TypeVar가 unbounded이고 caller의 `AggregateRootT` (bounded `AbstractAggregateRoot`)와 cross-package narrowing 실패.

#### 대안 C-1: 메서드 레벨 `AggregateRootT` bound ✅ **채택**

`SchemaRegistry.get_type` / `from_domain` 메서드에 `AggregateRootT = TypeVar("AggregateRootT", bound=AbstractAggregateRoot[Any])` 도입.

- **장점**: Registry는 여전히 singleton으로 공유. 메서드 시그니처만 정교화.
- **단점**: 메서드 시그니처 breaking (단, caller는 이미 aggregate type을 넘기고 있어 실제 영향 없음).

#### 대안 C-2: 클래스 레벨 제네릭 `SchemaRegistry[AggregateRootT]`

Registry 자체를 제네릭으로. Aggregate별 Registry 인스턴스가 필요해짐.

- **장점**: 더 엄격
- **단점**: 전역 shared registry 패턴 상실, ergonomics 악화.

### 문제 4: async abstractmethod covariance (2개)

`IAsyncCommandUseCase.run(cmd: CommandT_contra) -> ResultT_co`에서 `async def` 암묵 `Coroutine[Any, Any, ResultT_co]` 반환이 covariance 분석 실패.

#### 대안 D-1: 시그니처를 `def run -> Awaitable[ResultT_co]`로 변경 ✅ **채택**

추상 메서드 선언을 명시적 `Awaitable` 반환으로. 구현체(`async def run`)는 Coroutine이 Awaitable의 subtype이므로 그대로 만족.

- **장점**: 타입 변이 문제 해결. 구현체 코드 변경 불필요.
- **단점**: 인터페이스 시그니처 변경 (breaking).

## 결정 (Decision)

**문제 1**: 대안 A-4 (`google.protobuf.json_format` 브릿지 인라인 + DTO를 `@dataclass` → `pydantic.BaseModel`). spakky-grpc의 외부 API(`@GrpcController`, `@Rpc`, `@ProtoField(n)`)는 그대로 유지. 내부 변환 레이어(`handler._dataclass_to_protobuf`/`_protobuf_to_dataclass`)와 `descriptor_builder`를 BaseModel 기반으로 교체.

**문제 2**: 대안 B-2 (behavior-based 테스트 재작성).

**문제 3**: 대안 C-1 (메서드 레벨 `AggregateRootT` bound).

**문제 4**: 대안 D-1 (`def run -> Awaitable[ResultT_co]`).

### 하네스 규칙 강화

함께 `.claude/rules/python-code.md`에 다음을 추가:

- `cast()` 사용 최소화 — 타입 체커 에러를 `cast`로 치환은 금지. 변수/필드/반환값의 **타입 선언 자체**를 정확하게 바꾼다.
- `# pyrefly: ignore` / `# type: ignore`를 회피 수단으로 사용 금지. 우회 헬퍼, 테스트용 property 노출, 전역 cast 남용은 야매 해결책으로 간주.

## 결과 (Consequences)

### 긍정적

- **ignore 44개 제거**: 2개(정당한 사유)만 남음. 타입 안전성 기본선 회복.
- **spakky-grpc DTO 표준화**: `pydantic.BaseModel` 도입으로 다른 플러그인(spakky-fastapi)과 DTO 계층 통일 가능.
- **테스트 품질 향상**: behavior-based 테스트는 내부 리팩터링에 덜 취약.
- **UseCase 인터페이스 정확성**: `Awaitable` 명시로 타입 변이 정합.
- **Registry 타입 안전**: `AggregateRootT` bound 덕분에 caller 측에서 올바른 aggregate type만 전달 가능.

### 부정적

- **Breaking changes**:
  - `spakky-grpc`: DTO가 `@dataclass` → `pydantic.BaseModel`로 전환. 사용자 코드 수정 필요. pydantic v2 의존성 추가.
  - `spakky-domain`: `IAsyncCommandUseCase.run` / `IAsyncQueryUseCase.run` 시그니처 변경 (실제 `async def` 구현체는 영향 없음, 구조적 subtyping 관점에서만 변경).
  - `spakky-sqlalchemy`: `SchemaRegistry.get_type` / `from_domain` 시그니처 변경 (caller는 이미 aggregate type을 넘기고 있어 실질적 영향 없음).
- **ADR-0008 후속 작업**: 문서(README, guides) 및 예시 코드 동기화 필요.

### 중립적

- JSON 중간 표현 변환 오버헤드: gRPC 자체 비용 대비 미미. 실무 영향 없음.
- `pydantic` 의존이 `spakky-grpc`에 추가 (framework 전반에서 이미 사용).

## 참고 자료

- Issue: [#116](https://github.com/E5presso/spakky-framework/issues/116)
- 검토한 3rd-party 라이브러리:
  - PydanticRPC: https://github.com/i2y/pydantic-rpc
  - FastGRPC: https://github.com/taogeyt/fast-grpc
  - protobuf-to-pydantic: https://github.com/so1n/protobuf_to_pydantic
  - pydanticprotobuf: https://github.com/anthonycorletti/pydanticprotobuf
  - pydantic-protobuf-gen: https://github.com/begonia-org/pydantic-protobuf-gen
- `google.protobuf.json_format`: https://googleapis.dev/python/protobuf/latest/google/protobuf/json_format.html
