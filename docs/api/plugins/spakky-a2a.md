# spakky-a2a

> `spakky-a2a`는 `@Agent`를 A2A AgentCard와 task transport로 노출하고, 원격 A2A teammate를 `spakky-agent` delegation stream으로 합류시키는 어댑터입니다.

서버 경로는 공식 `a2a-sdk` request handler와 task store를 사용하며, 실행은 `AgentRunner.run_events()`에서 나온 `AgentEvent`를 A2A task/message/artifact update로 투영합니다.

## Public API

::: spakky.plugins.a2a
    options:
      show_root_heading: false

## 설정

::: spakky.plugins.a2a.config
    options:
      show_root_heading: false

## AgentCard

::: spakky.plugins.a2a.card.derivation
    options:
      show_root_heading: false

## 서버 등록

::: spakky.plugins.a2a.stereotypes.a2a_agent_server
    options:
      show_root_heading: false

::: spakky.plugins.a2a.server.registry
    options:
      show_root_heading: false

::: spakky.plugins.a2a.server.builder
    options:
      show_root_heading: false

::: spakky.plugins.a2a.server.request_handler
    options:
      show_root_heading: false

## Executor

::: spakky.plugins.a2a.executor.adapter
    options:
      show_root_heading: false

::: spakky.plugins.a2a.executor.event_mapping
    options:
      show_root_heading: false

## Transports

::: spakky.plugins.a2a.rest_transport
    options:
      show_root_heading: false

::: spakky.plugins.a2a.rest_transport.builder
    options:
      show_root_heading: false

::: spakky.plugins.a2a.grpc_transport
    options:
      show_root_heading: false

::: spakky.plugins.a2a.grpc_transport.builder
    options:
      show_root_heading: false

::: spakky.plugins.a2a.grpc_transport.handler
    options:
      show_root_heading: false

## Client와 Delegation

::: spakky.plugins.a2a.client
    options:
      show_root_heading: false

::: spakky.plugins.a2a.delegation
    options:
      show_root_heading: false

## Task Store

::: spakky.plugins.a2a.store.interfaces
    options:
      show_root_heading: false

::: spakky.plugins.a2a.store.task_store
    options:
      show_root_heading: false

## Plugin

::: spakky.plugins.a2a.post_processors.register_agent_servers
    options:
      show_root_heading: false

::: spakky.plugins.a2a.main
    options:
      show_root_heading: false

## 에러

::: spakky.plugins.a2a.error
    options:
      show_root_heading: false
