# spakky-fastapi

FastAPI 통합 — 라우트 데코레이터, 자동 엔드포인트 등록, 인증 경계 통합

`spakky-fastapi`는 HTTP `Authorization: Bearer <token>`과 WebSocket
`Authorization: Bearer <token>` 또는 `access_token=<token>` connection query를
`CredentialCarrier`로 추출하고, 사용자 handler 호출 전에 `AuthContext`를
request/context scope에 seed합니다. 보호된 handler는 인증만을 위해 FastAPI
`Request` 또는 `WebSocket` 파라미터를 선언할 필요가 없습니다. HTTP auth failure는
CHALLENGE=401, DENY=403, ERROR=500으로 매핑되고, WebSocket auth failure는
connection close로 처리됩니다.

## 스테레오타입

::: spakky.plugins.fastapi.stereotypes.api_controller
options:
show_root_heading: false

## 라우트

::: spakky.plugins.fastapi.routes.route
options:
show_root_heading: false

::: spakky.plugins.fastapi.routes.get
options:
show_root_heading: false

::: spakky.plugins.fastapi.routes.post
options:
show_root_heading: false

::: spakky.plugins.fastapi.routes.put
options:
show_root_heading: false

::: spakky.plugins.fastapi.routes.patch
options:
show_root_heading: false

::: spakky.plugins.fastapi.routes.delete
options:
show_root_heading: false

::: spakky.plugins.fastapi.routes.head
options:
show_root_heading: false

::: spakky.plugins.fastapi.routes.options
options:
show_root_heading: false

::: spakky.plugins.fastapi.routes.websocket
options:
show_root_heading: false

## 미들웨어

::: spakky.plugins.fastapi.middlewares.error_handling
options:
show_root_heading: false

::: spakky.plugins.fastapi.middlewares.tracing
options:
show_root_heading: false

## 후처리기s

::: spakky.plugins.fastapi.post_processors.bind_lifespan
options:
show_root_heading: false

::: spakky.plugins.fastapi.post_processors.add_builtin_middlewares
options:
show_root_heading: false

::: spakky.plugins.fastapi.post_processors.register_routes
options:
show_root_heading: false

::: spakky.plugins.fastapi.post_processors.register_actuator
options:
show_root_heading: false

## Actuator

::: spakky.plugins.fastapi.actuator
options:
show_root_heading: false

## 에러

::: spakky.plugins.fastapi.error
options:
show_root_heading: false

## 플러그인 진입점

::: spakky.plugins.fastapi.main
options:
show_root_heading: false

## 추가 모듈

::: spakky.plugins.fastapi.auth
    options:
      show_root_heading: false
