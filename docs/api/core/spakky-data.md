# spakky-data

Repository, Transaction 추상화 — 데이터 접근 계층

`spakky-data`는 core 레이어의 추상 계약만 제공합니다. 애플리케이션에서 SQLAlchemy로
영속화를 구현하려면 `spakky-sqlalchemy`를 함께 설치하고, `AbstractMappableTable` /
`AbstractAsyncGenericRepository` 또는 `AbstractGenericRepository`를 사용하세요.

사용자 흐름은 [데이터베이스 가이드](../../guides/sqlalchemy.md)를 먼저 보는 편이 좋습니다.
이 페이지는 실제 API 표면을 확인하기 위한 레퍼런스입니다.

## 스테레오타입

::: spakky.data.stereotype.repository
options:
show_root_heading: false

## 영속성

::: spakky.data.persistency.repository
options:
show_root_heading: false

::: spakky.data.persistency.transaction
options:
show_root_heading: false

::: spakky.data.persistency.aggregate_collector
options:
show_root_heading: false

::: spakky.data.persistency.error
options:
show_root_heading: false

## 외부 Proxy

::: spakky.data.external.proxy
options:
show_root_heading: false

::: spakky.data.external.error
options:
show_root_heading: false

## Aspect

::: spakky.data.aspects.transactional
options:
show_root_heading: false
