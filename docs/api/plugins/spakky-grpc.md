# spakky-grpc

gRPC 서비스 컨트롤러 통합 — code-first, 타입 안전 프로토콜 생성

## 스테레오타입

::: spakky.plugins.grpc.stereotypes.grpc_controller
    options:
      show_root_heading: false

## 데코레이터

::: spakky.plugins.grpc.decorators.rpc
    options:
      show_root_heading: false

## 어노테이션

::: spakky.plugins.grpc.annotations.field
    options:
      show_root_heading: false

## Handler

::: spakky.plugins.grpc.handler
    options:
      show_root_heading: false

## 인증 경계

::: spakky.plugins.grpc.auth
    options:
      show_root_heading: false

## 서버 명세

::: spakky.plugins.grpc.server_spec
    options:
      show_root_heading: false

## 스키마

### Registry

::: spakky.plugins.grpc.schema.registry
    options:
      show_root_heading: false

### Descriptor Builder

::: spakky.plugins.grpc.schema.descriptor_builder
    options:
      show_root_heading: false

### 타입 맵

::: spakky.plugins.grpc.schema.type_map
    options:
      show_root_heading: false

## 인터셉터

::: spakky.plugins.grpc.interceptors.tracing
    options:
      show_root_heading: false

::: spakky.plugins.grpc.interceptors.error_handling
    options:
      show_root_heading: false

## 후처리기s

::: spakky.plugins.grpc.post_processors.register_services
    options:
      show_root_heading: false

::: spakky.plugins.grpc.post_processors.add_interceptors
    options:
      show_root_heading: false

::: spakky.plugins.grpc.post_processors.bind_server
    options:
      show_root_heading: false

## 에러

::: spakky.plugins.grpc.error
    options:
      show_root_heading: false

## 추가 모듈

::: spakky.plugins.grpc.main
    options:
      show_root_heading: false
