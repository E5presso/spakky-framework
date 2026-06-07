# ADR-0005: Outbox SQLAlchemy 구현체를 spakky-sqlalchemy에 통합

- **상태**: Accepted
- **날짜**: 2026-03-15
- **대체**: [ADR-0002](0002-outbox-plugin-architecture.md) 일부 (패키지 분리 전략)

## 맥락 (Context)

[ADR-0002](0002-outbox-plugin-architecture.md)에서 `spakky-outbox`(추상화)와 `spakky-outbox-sqlalchemy`(구현체)를 별도 패키지로 분리하기로 했다. 근거는 MongoDB, DynamoDB 등 다른 DB 백엔드 확장 시 조합 폭발(N×M 브릿지 패키지)을 방지하기 위함이었다.

그러나 실제로 구현해보니 다음 문제가 드러났다:

1. **조합 폭발은 브릿지 분리로 해결되지 않는다**: DB 백엔드 N개 × 추상화 M개 = N×M 브릿지 패키지. 오히려 패키지 수가 선형 이상으로 증가한다.
2. **Outbox 저장은 본질적으로 DB 작업이다**: `OutboxMessageTable`, `SqlAlchemyOutboxStorage`의 모든 코드가 SQLAlchemy API를 사용한다. 개념적으로 SQLAlchemy 플러그인에 속하는 코드다.
3. **명시적 feature contribution이 런타임 감지를 대체한다**: ADR-0010 이후 `spakky-sqlalchemy`는 `spakky-outbox` 설치 여부를 `_HAS_OUTBOX` 같은 import guard로 감지하지 않는다. 대신 Python entry point metadata의 `spakky.contributions.spakky.outbox` group으로 outbox 구현을 선언하고, framework loader가 active feature/provider 조합에 따라 호출한다.

### 현재 구조 vs 제안 구조

| 구조 | 패키지 |
|------|--------|
| 현재 (ADR-0002) | `spakky-outbox` (추상화) |
| 현재 (ADR-0002) | `spakky-outbox-sqlalchemy` (브릿지) -> `spakky-outbox` + `spakky-sqlalchemy` |
| 현재 (ADR-0002) | `spakky-outbox-mongodb` (향후 브릿지) -> `spakky-outbox` + `motor` |
| 현재 (ADR-0002) | `spakky-outbox-dynamodb` (향후 브릿지) -> `spakky-outbox` + `boto3` |
| 제안 (ADR-0010 이후 구현 형태) | `spakky-outbox` (추상화) |
| 제안 (ADR-0010 이후 구현 형태) | `spakky-sqlalchemy` (기존 + `spakky-outbox` contribution) |
| 제안 (ADR-0010 이후 구현 형태) | `spakky-mongodb` (향후, 기존 + `spakky-outbox` contribution) |
| 제안 (ADR-0010 이후 구현 형태) | `spakky-dynamodb` (향후, 기존 + `spakky-outbox` contribution) |

**DB 백엔드 하나를 추가하면 그 DB로 할 수 있는 모든 것이 하나의 플러그인에서 제공된다.** 브릿지 패키지 0개.

## 결정 동인 (Decision Drivers)

- **패키지 수 최소화**: 사용자가 설치할 패키지 수 감소 (`spakky-outbox` + `spakky-sqlalchemy[outbox]` 또는 `spakky-outbox` + `spakky-sqlalchemy` 조합으로 충분)
- **DB 백엔드 = 단일 플러그인 원칙**: 하나의 DB 기술에 대한 모든 구현이 하나의 플러그인에 위치
- **명시적 metadata 기반 활성화**: optional import guard 대신 ADR-0010의 feature contribution entry point 모델 사용
- **관리 비용 감소**: 버전 호환성 관리 대상 패키지 1개 감소

## 고려한 대안 (Considered Options)

### 대안 A: 현행 유지 (별도 패키지)

ADR-0002 그대로. `spakky-outbox-sqlalchemy`를 독립 패키지로 유지.

- **장점**: 기존 사용자 코드 변경 없음
- **단점**: 브릿지 패키지 수 선형 증가, 사용자 설치 불편, DB 백엔드 추가 시 항상 2개 패키지 생성

### 대안 B: spakky-sqlalchemy에 통합 + feature contribution ✅

`spakky-outbox-sqlalchemy`의 코드를 `spakky-sqlalchemy`로 이동. `spakky-sqlalchemy` base plugin은 SQLAlchemy substrate만 등록하고, outbox 관련 Pod는 `spakky.contributions.spakky.outbox` entry point가 별도 contribution으로 등록한다.

- **장점**: 패키지 1개 감소, DB 백엔드 = 단일 플러그인 원칙, ADR-0010 contribution policy와 일관성
- **단점**: `spakky-sqlalchemy`의 코드 약간 증가 (파일 3개 추가), breaking change

### 대안 C: spakky-outbox에 통합

모든 DB 구현체를 `spakky-outbox`에 넣고 선택적 의존으로 관리.

- **장점**: outbox 관련 코드가 한 곳에
- **단점**: outbox가 모든 DB 기술을 알아야 함, 단일 책임 위반, DB 백엔드 추가 시 outbox 패키지 비대화

## 결정 (Decision)

**대안 B를 채택한다.**

### 변경 내용

1. **코드 이동**: `spakky-outbox-sqlalchemy`의 소스 파일을 `spakky-sqlalchemy`로 이동

   | 경로 | 설명 |
   |------|------|
   | `plugins/spakky-sqlalchemy/src/spakky/plugins/sqlalchemy/` | 기존 SQLAlchemy 플러그인 루트 |
   | `plugins/spakky-sqlalchemy/src/spakky/plugins/sqlalchemy/contributions/outbox.py` | `spakky-outbox` contribution `initialize()` |
   | `plugins/spakky-sqlalchemy/src/spakky/plugins/sqlalchemy/outbox/__init__.py` | Outbox 구현 패키지 |
   | `plugins/spakky-sqlalchemy/src/spakky/plugins/sqlalchemy/outbox/storage.py` | `SqlAlchemyOutboxStorage`, `AsyncSqlAlchemyOutboxStorage` |
   | `plugins/spakky-sqlalchemy/src/spakky/plugins/sqlalchemy/outbox/table.py` | `OutboxMessageTable` |

2. **Contribution 등록**: `spakky-sqlalchemy`의 base plugin은 outbox를 감지하지 않는다. 패키지 metadata가 `spakky.contributions.spakky.outbox` group을 선언하고, loader가 `spakky-outbox` feature와 `spakky-sqlalchemy` provider가 모두 active일 때 contribution을 호출한다.

   ```toml
   [project.entry-points."spakky.plugins"]
   spakky-sqlalchemy = "spakky.plugins.sqlalchemy.main:initialize"

   [project.entry-points."spakky.contributions.spakky.outbox"]
   spakky-sqlalchemy = "spakky.plugins.sqlalchemy.contributions.outbox:initialize"
   ```

   `spakky-outbox`의 plugin name은 Python entry point group segment에서 `spakky.outbox`로 정규화되므로 canonical contribution group은 `spakky.contributions.spakky.outbox`다.

3. **Contribution initialize**: outbox Pod 등록은 contribution module에만 위치한다.

```python
def initialize(app: SpakkyApplication) -> None:
    config = SQLAlchemyConnectionConfig()

    app.add(OutboxMessageTable)
    app.add(SqlAlchemyOutboxStorage)

    if config.support_async_mode:
        app.add(AsyncSqlAlchemyOutboxStorage)
```

4. **패키지 제거**: `spakky-outbox-sqlalchemy` 패키지 삭제, 워크스페이스에서 제거

5. **에러 계층**: `AbstractSpakkyOutboxSqlAlchemyError` → `AbstractSpakkySqlAlchemyError`를 상속하도록 변경 (outbox 에러도 SQLAlchemy 에러로 통합)

### ADR-0002와의 관계

ADR-0002의 핵심 결정(추상화/구현체 분리)은 유효하다. `IOutboxStorage` 인터페이스와 `spakky-outbox` 패키지는 그대로 유지된다. 변경된 것은 **구현체의 물리적 위치**뿐이다 — 별도 패키지에서 DB 플러그인 내부로 이동.

## 결과 (Consequences)

### 긍정적

- **패키지 수 감소**: `spakky-outbox-sqlalchemy` 제거 (모노레포 패키지 -1)
- **사용자 설치 단순화**: `spakky-outbox`와 `spakky-sqlalchemy` provider 조합으로 outbox contribution이 feature/provider 활성 조합에서 로드됨. 배포 편의를 위해 `spakky-sqlalchemy[outbox]` extra가 feature contract 의존성을 함께 설치한다.
- **DB 백엔드 확장 시**: 새 DB 플러그인 하나만 만들면 data + outbox 모두 지원
- **ADR-0010 패턴과 일관성**: entry point metadata → contribution loading 패턴 재사용

### 부정적

- **Breaking change**: `spakky.plugins.outbox_sqlalchemy` import 경로가 `spakky.plugins.sqlalchemy.outbox`로 변경
- **ADR-0002 부분 대체**: 기존 패키지 분리 전략 변경

### 중립적

- `spakky-outbox`의 추상화(`IOutboxStorage`, `OutboxMessage`, Bus, Relay)는 변경 없음
- `spakky-sqlalchemy` base plugin은 `spakky-outbox`를 기본 의존성으로 끌어오지 않는다. outbox contribution module은 feature core contract를 import하므로 `spakky-sqlalchemy[outbox]` extra 또는 별도 `spakky-outbox` 설치가 필요하다. 활성화 여부는 import guard가 아니라 base plugin과 contribution provider가 모두 active인지, 그리고 `load_plugins(include=...)` 필터가 양쪽을 포함하는지로 결정된다.

## 참고 자료

- [ADR-0002: Outbox 플러그인 아키텍처](0002-outbox-plugin-architecture.md)
- [ADR-0010: Feature Contribution Policy](0010-feature-contribution-policy.md) — contribution entry point 활성화 정책
