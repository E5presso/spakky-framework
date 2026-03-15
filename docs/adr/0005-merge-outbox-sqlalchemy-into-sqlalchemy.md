# ADR-0005: Outbox SQLAlchemy 구현체를 spakky-sqlalchemy에 통합

- **상태**: Accepted
- **날짜**: 2026-03-15
- **대체**: [ADR-0002](0002-outbox-plugin-architecture.md) 일부 (패키지 분리 전략)

## 맥락 (Context)

[ADR-0002](0002-outbox-plugin-architecture.md)에서 `spakky-outbox`(추상화)와 `spakky-outbox-sqlalchemy`(구현체)를 별도 패키지로 분리하기로 했다. 근거는 MongoDB, DynamoDB 등 다른 DB 백엔드 확장 시 조합 폭발(N×M 브릿지 패키지)을 방지하기 위함이었다.

그러나 실제로 구현해보니 다음 문제가 드러났다:

1. **조합 폭발은 브릿지 분리로 해결되지 않는다**: DB 백엔드 N개 × 추상화 M개 = N×M 브릿지 패키지. 오히려 패키지 수가 선형 이상으로 증가한다.
2. **Outbox 저장은 본질적으로 DB 작업이다**: `OutboxMessageTable`, `SqlAlchemyOutboxStorage`의 모든 코드가 SQLAlchemy API를 사용한다. 개념적으로 SQLAlchemy 플러그인에 속하는 코드다.
3. **런타임 감지 패턴이 이미 프레임워크에 존재한다**: `spakky-opentelemetry`가 `spakky-logging` 설치 여부를 런타임에 감지하여 브릿지하는 패턴(ADR-0004)이 확립되었다. 동일한 패턴으로 `spakky-sqlalchemy`가 `spakky-outbox` 설치 여부를 감지할 수 있다.

### 현재 구조 vs 제안 구조

```
# 현재 (ADR-0002)
spakky-outbox (추상화)
spakky-outbox-sqlalchemy (브릿지) → spakky-outbox + spakky-sqlalchemy
spakky-outbox-mongodb (향후 브릿지) → spakky-outbox + motor
spakky-outbox-dynamodb (향후 브릿지) → spakky-outbox + boto3

# 제안
spakky-outbox (추상화)
spakky-sqlalchemy (기존 + outbox 설치 시 자동 확장)
spakky-mongodb (향후, 기존 + outbox 설치 시 자동 확장)
spakky-dynamodb (향후, 기존 + outbox 설치 시 자동 확장)
```

**DB 백엔드 하나를 추가하면 그 DB로 할 수 있는 모든 것이 하나의 플러그인에서 제공된다.** 브릿지 패키지 0개.

## 결정 동인 (Decision Drivers)

- **패키지 수 최소화**: 사용자가 설치할 패키지 수 감소 (`spakky-outbox` + `spakky-sqlalchemy`만으로 충분)
- **DB 백엔드 = 단일 플러그인 원칙**: 하나의 DB 기술에 대한 모든 구현이 하나의 플러그인에 위치
- **런타임 감지 패턴 일관성**: ADR-0004에서 확립된 선택적 의존 패턴 재사용
- **관리 비용 감소**: 버전 호환성 관리 대상 패키지 1개 감소

## 고려한 대안 (Considered Options)

### 대안 A: 현행 유지 (별도 패키지)

ADR-0002 그대로. `spakky-outbox-sqlalchemy`를 독립 패키지로 유지.

- **장점**: 기존 사용자 코드 변경 없음
- **단점**: 브릿지 패키지 수 선형 증가, 사용자 설치 불편, DB 백엔드 추가 시 항상 2개 패키지 생성

### 대안 B: spakky-sqlalchemy에 통합 + 런타임 감지 ✅

`spakky-outbox-sqlalchemy`의 코드를 `spakky-sqlalchemy`로 이동. `spakky-outbox` 설치 여부를 런타임에 감지하여 outbox 관련 Pod를 조건부 등록.

- **장점**: 패키지 1개 감소, DB 백엔드 = 단일 플러그인 원칙, ADR-0004 패턴과 일관성
- **단점**: `spakky-sqlalchemy`의 코드 약간 증가 (파일 3개 추가), breaking change

### 대안 C: spakky-outbox에 통합

모든 DB 구현체를 `spakky-outbox`에 넣고 선택적 의존으로 관리.

- **장점**: outbox 관련 코드가 한 곳에
- **단점**: outbox가 모든 DB 기술을 알아야 함, 단일 책임 위반, DB 백엔드 추가 시 outbox 패키지 비대화

## 결정 (Decision)

**대안 B를 채택한다.**

### 변경 내용

1. **코드 이동**: `spakky-outbox-sqlalchemy`의 소스 파일을 `spakky-sqlalchemy`로 이동

   ```
   plugins/spakky-sqlalchemy/src/spakky/plugins/sqlalchemy/
   ├── ... (기존)
   └── outbox/                    # 신규 (outbox 설치 시에만 활성화)
       ├── __init__.py
       ├── storage.py             # SqlAlchemyOutboxStorage, AsyncSqlAlchemyOutboxStorage
       └── table.py               # OutboxMessageTable
   ```

2. **조건부 등록**: `spakky-sqlalchemy`의 `main.py`에서 런타임 감지

   ```python
   try:
       from spakky.plugins.outbox import PLUGIN_NAME as _OUTBOX_PLUGIN  # noqa: F401

       from spakky.plugins.sqlalchemy.outbox.storage import (
           AsyncSqlAlchemyOutboxStorage,
           SqlAlchemyOutboxStorage,
       )
       from spakky.plugins.sqlalchemy.outbox.table import OutboxMessageTable

       _HAS_OUTBOX = True
   except ImportError:
       _HAS_OUTBOX = False

   def initialize(app: SpakkyApplication) -> None:
       # ... 기존 코드 ...
       if _HAS_OUTBOX:
           app.add(SqlAlchemyOutboxStorage)
           app.add(AsyncSqlAlchemyOutboxStorage)
           app.add(OutboxMessageTable)
   ```

3. **패키지 제거**: `spakky-outbox-sqlalchemy` 패키지 삭제, 워크스페이스에서 제거

4. **에러 계층**: `AbstractSpakkyOutboxSqlAlchemyError` → `AbstractSpakkySqlAlchemyError`를 상속하도록 변경 (outbox 에러도 SQLAlchemy 에러로 통합)

### ADR-0002와의 관계

ADR-0002의 핵심 결정(추상화/구현체 분리)은 유효하다. `IOutboxStorage` 인터페이스와 `spakky-outbox` 패키지는 그대로 유지된다. 변경된 것은 **구현체의 물리적 위치**뿐이다 — 별도 패키지에서 DB 플러그인 내부로 이동.

## 결과 (Consequences)

### 긍정적

- **패키지 수 감소**: `spakky-outbox-sqlalchemy` 제거 (모노레포 패키지 -1)
- **사용자 설치 단순화**: `spakky-outbox` + `spakky-sqlalchemy`만 설치하면 outbox 자동 활성화
- **DB 백엔드 확장 시**: 새 DB 플러그인 하나만 만들면 data + outbox 모두 지원
- **ADR-0004 패턴과 일관성**: 런타임 감지 → 조건부 등록 패턴 재사용

### 부정적

- **Breaking change**: `spakky.plugins.outbox_sqlalchemy` import 경로가 `spakky.plugins.sqlalchemy.outbox`로 변경
- **ADR-0002 부분 대체**: 기존 패키지 분리 전략 변경

### 중립적

- `spakky-outbox`의 추상화(`IOutboxStorage`, `OutboxMessage`, Bus, Relay)는 변경 없음
- `spakky-sqlalchemy`에 `spakky-outbox` 의존성이 **추가되지 않음** — 런타임 감지이므로 pyproject.toml 변경 없음

## 참고 자료

- [ADR-0002: Outbox 플러그인 아키텍처](0002-outbox-plugin-architecture.md)
- [ADR-0004: 분산 트레이싱 아키텍처](0004-distributed-tracing-architecture.md) — 런타임 감지 패턴 선례
