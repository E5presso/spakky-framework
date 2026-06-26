# spakky-a2a

> `spakky-a2a`는 `@Agent`를 A2A AgentCard와 task transport로 노출하고, 원격 A2A teammate를 `spakky-agent` delegation stream으로 합류시키는 어댑터입니다.

서버 경로는 공식 `a2a-sdk` request handler와 task store를 사용하며, 실행은 `IAgentRunnerFactory`가 여는 runner의 `AgentEvent` stream을 A2A task/message/artifact update로 투영합니다. `@A2ACompatible @Agent`는 registry에 등록되고 ASGI host Pod가 있으면 JSON-RPC/REST endpoint가 자동 mount됩니다. `spakky-grpc`의 `GrpcServerSpec`가 있으면 gRPC handler도 선언형으로 등록됩니다.

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

::: spakky.plugins.a2a.stereotypes.a2a_compatible
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

::: spakky.plugins.a2a.post_processors.mount_asgi
    options:
      show_root_heading: false

::: spakky.plugins.a2a.post_processors.register_grpc
    options:
      show_root_heading: false

::: spakky.plugins.a2a.main
    options:
      show_root_heading: false

## 에러

::: spakky.plugins.a2a.error
    options:
      show_root_heading: false
