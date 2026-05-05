# spakky-sqlalchemy

SQLAlchemy 통합 - ORM, Repository, Transaction, Outbox Contribution

`spakky-sqlalchemy`는 `spakky-data`의 Repository/Transaction 계약을 SQLAlchemy engine과
session으로 구현하는 플러그인입니다. 처음 사용하는 경우에는
[데이터베이스 가이드](../../guides/sqlalchemy.md)에서 도메인 Aggregate, ORM table,
Repository, `@Transactional()` UseCase를 한 흐름으로 확인하세요.

Outbox storage/table은 base plugin 본체가 아니라
`spakky.contributions.spakky.outbox` contribution으로 등록됩니다. `load_plugins(include=...)`
사용 시 `spakky-outbox`와 `spakky-sqlalchemy`가 모두 include set에 있어야 이
contribution이 로드됩니다. 설치 시에는 `spakky-outbox`를 별도로 추가하거나
`spakky-sqlalchemy[outbox]` extra를 사용하세요.

## 메인

::: spakky.plugins.sqlalchemy.main
options:
show_root_heading: false

## 설정

::: spakky.plugins.sqlalchemy.common.config
options:
show_root_heading: false

## ORM

::: spakky.plugins.sqlalchemy.orm.table
options:
show_root_heading: false

::: spakky.plugins.sqlalchemy.orm.schema_registry
options:
show_root_heading: false

::: spakky.plugins.sqlalchemy.orm.error
options:
show_root_heading: false

## 영속성

::: spakky.plugins.sqlalchemy.persistency.repository
options:
show_root_heading: false

::: spakky.plugins.sqlalchemy.persistency.transaction
options:
show_root_heading: false

::: spakky.plugins.sqlalchemy.persistency.session_manager
options:
show_root_heading: false

::: spakky.plugins.sqlalchemy.persistency.connection_manager
options:
show_root_heading: false

::: spakky.plugins.sqlalchemy.persistency.error
options:
show_root_heading: false

## Outbox

::: spakky.plugins.sqlalchemy.contributions.outbox
options:
show_root_heading: false

::: spakky.plugins.sqlalchemy.outbox.storage
options:
show_root_heading: false

::: spakky.plugins.sqlalchemy.outbox.table
options:
show_root_heading: false

## 에러

::: spakky.plugins.sqlalchemy.error
options:
show_root_heading: false
