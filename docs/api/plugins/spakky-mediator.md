# spakky-mediator

명시적으로 설치·선택하는 로컬 domain event consumer·dispatcher입니다.
`spakky-event`의 계약·발행과 Kafka/RabbitMQ의 외부 소비를 독립적으로 조합합니다.

## 플러그인 진입점

::: spakky.plugins.mediator.main
    options:
      show_root_heading: false

## Consumer와 Dispatcher

::: spakky.plugins.mediator.mediator
    options:
      show_root_heading: false

## Domain Handler 등록

::: spakky.plugins.mediator.post_processor
    options:
      show_root_heading: false

## 이전

로컬 dispatch를 사용하는 앱은 `spakky-mediator` 또는 `spakky[mediator]`를 설치하고
`Plugin(name="spakky-mediator")`를 명시적으로 선택합니다. 구체 구현 import는
`spakky.plugins.mediator.mediator`와 `spakky.plugins.mediator.post_processor`로 옮깁니다.
`spakky.event`의 consumer·dispatcher 인터페이스와 handler stereotype은 유지됩니다.
