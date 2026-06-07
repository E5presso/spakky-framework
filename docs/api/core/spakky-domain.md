# spakky-domain

> `spakky-domain`은 DDD 모델과 CQRS UseCase 계약을 제공하는 core 패키지입니다.

DDD 빌딩 블록 — Aggregate Root, Entity, Value Object, Domain Event, CQRS

## 플러그인 진입점

::: spakky.domain.main
options:
show_root_heading: false

## 모델

::: spakky.domain.models.base
options:
show_root_heading: false

::: spakky.domain.models.aggregate_root
options:
show_root_heading: false

::: spakky.domain.models.entity
options:
show_root_heading: false

::: spakky.domain.models.value_object
options:
show_root_heading: false

::: spakky.domain.models.event
options:
show_root_heading: false

## 애플리케이션 (CQRS)

::: spakky.domain.application.command
options:
show_root_heading: false

::: spakky.domain.application.query
options:
show_root_heading: false

## 에러

::: spakky.domain.error
options:
show_root_heading: false
