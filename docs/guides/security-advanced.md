# 인증/인가 심화

> `spakky-auth`의 transport별 실패 정책, snapshot 전파, startup validation을 정리한 심화 가이드입니다.

이 문서는 [인증/인가](security.md)를 읽은 뒤 확인하는 운영 상세 문서입니다. 입문 문서에서는 decorator와 provider 선택을 다루고, 여기서는 HTTP, gRPC, CLI, worker, broker, saga 경계에서 실패가 어떻게 매핑되는지 설명합니다.

## FastAPI HTTP와 WebSocket

FastAPI HTTP 라우트는 `Authorization: Bearer <token>`을 읽습니다. WebSocket 핸들러는 같은 헤더를 먼저 확인하고, 없으면 `access_token` 쿼리 파라미터를 사용합니다. 어댑터는 사용자 핸들러를 호출하기 전에 인증을 끝내고 `AuthContext`를 `ApplicationContext`에 저장합니다.

| 상황 | HTTP 결과 | WebSocket 결과 |
| --- | --- | --- |
| 공개 라우트에 credential이 없음 | 핸들러 실행 | 핸들러 실행 |
| 공개 라우트의 credential이 core auth contract에서 거절됨 | 핸들러 실행 | 핸들러 실행 |
| 공개 라우트에서 provider-local 또는 예기치 않은 credential 오류 발생 | framework error handling으로 매핑 | framework error handling으로 매핑 |
| 보호 라우트에 credential이 없음 | 401 | close code 1008 |
| 인증 실패 | 401 | close code 1008 |
| 인가 `DENY` | 403 | close code 1008 |
| provider 비가용 또는 metadata 충돌 | 500 | close code 1011 |

## gRPC

gRPC는 invocation metadata를 읽습니다. `authorization: Bearer <token>`은 bearer credential로 처리됩니다. Bearer metadata가 없으면 `spakky.auth.context_snapshot` 또는 `x-spakky-auth-context-snapshot`을 `AUTH_CONTEXT_SNAPSHOT` credential로 받습니다. 이 credential은 등록된 `IAuthenticationProvider`를 통해 인증되고, 반환된 `AuthContext`가 저장됩니다. Credential은 있는데 provider가 없으면 gRPC `Unavailable`이 발생합니다.

`AuthInvocation`의 boundary 값은 `grpc`이고, operation은 등록된 RPC operation string입니다.

## Typer CLI

Typer command에 기존 `--auth-token` option이 없으면 어댑터가 auth option을 자동으로 붙입니다. 값은 `--auth-token`을 먼저 보고, 없으면 `SPAKKY_AUTH_TOKEN` 환경변수를 읽습니다. stdin은 auth carrier가 아닙니다. 각 command 실행 전에는 이전 command의 context가 섞이지 않도록 context-scoped state를 비우고, bearer token이 있으면 인증한 뒤 `AuthContext`를 저장합니다.

| Decision | Exit code | 출력 |
| --- | --- | --- |
| `CHALLENGE` | 2 | reason code와 선택적 reason |
| `DENY` | 3 | reason code와 선택적 reason |
| `ERROR` | 1 | reason code와 선택적 reason |

Auth decorator가 없는 command는 provider가 없어도 실행됩니다.

## Task와 worker 경계

같은 프로세스에서 직접 task를 실행하면 현재 request/context scope를 그대로 사용합니다. `ApplicationContext`를 비우지 않고, snapshot도 요구하지 않으며, task method에 `AuthContext`를 인자로 넘기지도 않습니다. Auth decorator metadata는 task route로 복사되므로 queue adapter가 worker 실행 시점에 같은 요구사항을 강제할 수 있습니다.

`AuthSnapshotPropagationConfig(enabled=True)`가 등록되어 있고 현재 context에 `AuthContext`가 있으면, Celery dispatch aspect는 task header에 signed snapshot metadata를 넣습니다. Header key는 `spakky.auth.context_snapshot`입니다. 전파가 켜져 있고 context도 있는데 signer가 없으면 dispatch는 조용히 넘어가지 않고 실패합니다.

보호된 worker task는 사용자 코드가 실행되기 전에 snapshot을 검증하고 `AuthContext`를 저장한 뒤 task metadata를 평가합니다. Snapshot이 없거나 잘못되었거나 만료되면 `CHALLENGE`로 처리됩니다. Verifier를 사용할 수 없으면 `ERROR`가 되며, `is_retryable_auth_failure()`로 재시도 가능한 실패인지 확인할 수 있습니다.

## Event, RabbitMQ, Kafka

`AuthContextSnapshotHeaderInjector`는 snapshot 전파가 꺼져 있어도 outbound event header에서 raw bearer `Authorization` header를 제거합니다. 전파가 켜져 있고 `AuthContext`가 있으면 snapshot을 서명해 `spakky.auth.context_snapshot`에 기록합니다. Application context가 없거나 context 값이 잘못되었거나 signer가 없으면 명시적으로 실패합니다. 공개 흐름에서 `AuthContext`가 없는 경우에는 snapshot만 생략합니다.

RabbitMQ consumer는 AMQP header를 문자열 값으로 변환하고 message-local context에 저장합니다. 그런 다음 `ApplicationContext`를 비우고 signed snapshot을 검증한 뒤, integration event handler가 실행되기 전에 `AuthContext`를 저장합니다. 지원하는 key는 `spakky.auth.context_snapshot`과 `x-spakky-auth-context-snapshot`입니다. 둘 다 있으면 metadata key가 우선합니다.

| RabbitMQ decision state | 기본 action |
| --- | --- |
| `CHALLENGE` | `ack` |
| `DENY` | `ack` |
| `ERROR` | `nack_requeue` |

이 action은 RabbitMQ 설정 `auth_challenge_action`, `auth_deny_action`, `auth_error_action`으로 바꿀 수 있습니다.

Kafka consumer는 message header를 decode하고 `ApplicationContext`를 비운 뒤, auth-aware handler wrapper에만 header를 전달합니다. 보호된 handler는 `x-spakky-auth-context-snapshot`을 먼저 확인하고, 없으면 `spakky.auth.context_snapshot`을 fallback으로 사용합니다. Header 이름은 대소문자를 구분하지 않습니다. Snapshot이 없거나 잘못되었거나 만료되면 non-ALLOW decision을 반환하고 handler는 실행되지 않습니다. Snapshot verifier를 사용할 수 없으면 consumer가 재시도 가능한 인프라 장애로 다룰 수 있도록 error를 전파합니다.

## Saga

`AbstractSagaData`는 `auth_context_snapshot`을 담습니다. 보호된 saga step과 보호된 compensation callback은 실행 전에 이 snapshot을 검증하고, 일반 auth boundary와 같은 decorator requirement를 평가합니다. Step이 snapshot 없는 replacement saga data를 반환하면 엔진은 현재 snapshot을 유지합니다. 반환된 data에 새 snapshot이 있으면 새 값을 사용합니다.

Snapshot이 없거나 잘못되었거나 만료되면 보호된 step은 `CHALLENGE`로 실패합니다. Provider를 사용할 수 없거나 requirement provider가 없으면 `ERROR`로 실패합니다. Saga history에는 step 실패가 기록되고, 이후 처리는 일반 saga error strategy를 따릅니다.

## R03 최종 적합성 매트릭스

R03는 R04 뒤에 실행되는 인증/인가 마일스톤의 최종 기술 gate입니다. 아래 매트릭스는 구현된 boundary 동작을 package 간 기준으로 정리한 reference입니다.

| 경계 | Decorator 없는 공개 호출 | 보호된 호출 성공 | `CHALLENGE` 경로 | `DENY` 경로 | `ERROR` / provider 비가용 | Context 순서 | Snapshot 경로 | Startup validation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| FastAPI HTTP | Credential 없이 handler 실행 | Bearer credential로 `AuthContext`를 저장하고 handler 전 requirement decorator 평가 | inbound bearer credential 없음, 오류, 만료 시 401 | authorization denial 시 403 | auth provider 비가용 또는 metadata 충돌 시 500 | 기존 request scope를 비운 뒤 `AuthContext` 저장 | HTTP로는 전파하지 않음. Bearer는 inbound 전용 | 보호 route는 일치하는 provider capability가 정확히 하나 필요 |
| FastAPI WebSocket | Credential 없이 handler 실행 | Header bearer 또는 `access_token` query token으로 handler 전 `AuthContext` 저장 | credential 없음, 오류, 만료 시 close code 1008 | close code 1008 | close code 1011 | WebSocket wrapper가 seed 전에 scope 정리 | WebSocket으로는 전파하지 않음. Bearer는 inbound 전용 | 보호 socket handler는 일치하는 provider capability가 정확히 하나 필요 |
| gRPC unary | Auth metadata가 없으면 허용 | Metadata bearer 또는 snapshot credential을 `IAuthenticationProvider`로 인증하고 unary handler 전 `AuthContext` 저장 | credential/snapshot 없음, 오류, 만료 시 gRPC unauthenticated | gRPC permission denied | provider 비가용 또는 metadata 충돌 시 gRPC unavailable/internal | Interceptor가 seed 전에 request scope 정리 | `spakky.auth.context_snapshot`, `x-spakky-auth-context-snapshot`을 auth credential로 허용 | 보호 RPC는 일치하는 provider capability가 정확히 하나 필요 |
| gRPC stream | Auth metadata가 없으면 허용 | Stream interceptor가 bearer 또는 snapshot metadata를 인증하고 stream handler 전 `AuthContext` 저장 | credential/snapshot 없음, 오류, 만료 시 gRPC unauthenticated | gRPC permission denied | provider 비가용 또는 metadata 충돌 시 gRPC unavailable/internal | Interceptor가 seed 전에 request scope 정리 | Metadata/header snapshot credential을 `IAuthenticationProvider`로 허용 | 보호 stream은 일치하는 provider capability가 정확히 하나 필요 |
| Typer | Provider나 token이 없어도 허용 | `--auth-token` 또는 `SPAKKY_AUTH_TOKEN`으로 command 전 `AuthContext` 저장 | bearer credential 없음, 오류, 만료 시 exit 2 | exit 3 | exit 1 | CLI command가 seed 전에 context 정리 | Snapshot 전파 없음. stdin은 auth carrier가 아님 | 보호 command는 일치하는 provider capability가 정확히 하나 필요 |
| spakky-task direct | 현재 request/context scope에서 허용 | 기존 `AuthContext`를 기준으로 task metadata 평가 | 보호된 direct call에 context가 없으면 `CHALLENGE` | Requirement denial은 `DENY` | Provider 비가용 또는 requirement provider 없음은 `ERROR` | Direct execution은 현재 scope를 비우지 않음 | Queue adapter는 복사된 metadata를 받음. Direct execution은 snapshot 불필요 | 보호 task metadata는 일치하는 provider capability가 정확히 하나 필요 |
| Celery | Public task는 snapshot 없이 실행 | Worker가 signed snapshot을 검증하고 `AuthContext`를 저장한 뒤 task metadata 평가 | snapshot 없음, 오류, 만료 시 `CHALLENGE` | Requirement denial은 `DENY` | Verifier 비가용은 재시도 가능한 `ERROR` | Worker가 snapshot seed 전에 scope 정리 | Dispatch가 `spakky.auth.context_snapshot`을 쓰고 worker가 검증 | Enabled propagation은 signer와 verifier provider가 각각 정확히 하나 필요 |
| spakky-event propagation | `AuthContext`가 없으면 public event send에서 snapshot 생략 가능 | 전파가 켜져 있으면 outbound event에 signed `AuthContextSnapshot` metadata 포함 | downstream protected consumer가 snapshot 없음, 오류, 만료를 `CHALLENGE`로 매핑 | downstream handler denial은 `DENY` | enabled propagation에서 signer 없음 또는 invalid context는 `ERROR` | Outbound injector가 raw bearer를 제거한 뒤 snapshot 기록 | `spakky.auth.context_snapshot` 사용. Raw bearer는 전파하지 않음 | Enabled propagation은 snapshot signer와 verifier가 정확히 하나 필요 |
| RabbitMQ | Public handler는 기존 no-auth 동작 유지 | Consumer가 snapshot을 검증하고 handler 전 `AuthContext` 저장 | snapshot 없음, 오류, 만료 시 configured challenge action, 기본 `ack` | 기본 `ack` | 기본 `nack_requeue` | Message-local context와 application context를 seed 전에 정리 | 둘 다 있으면 metadata key가 `x-spakky-auth-context-snapshot`보다 우선 | 보호 handler와 enabled propagation은 capability별 provider가 정확히 하나 필요 |
| Kafka | Public handler는 기존 no-auth 동작 유지 | Consumer가 snapshot을 검증하고 handler 전 `AuthContext` 저장 | snapshot 없음, 오류, 만료 시 non-ALLOW decision으로 보호 handler skip | 보호 handler skip | Provider 비가용은 재시도 가능한 인프라 오류로 전파 | Consumer가 auth-aware wrapper 실행 전에 application context 정리 | `x-spakky-auth-context-snapshot` 우선, `spakky.auth.context_snapshot` fallback | 보호 handler와 enabled propagation은 capability별 provider가 정확히 하나 필요 |
| Saga | Public step/compensation은 일반 saga flow를 따름 | Step이 snapshot을 검증하고 `AuthContext`를 저장한 뒤 decorator 평가 | snapshot 없음, 오류, 만료 시 보호 step이 `CHALLENGE`로 실패 | Requirement denial은 `DENY` | Provider 비가용 또는 requirement provider 없음은 `ERROR` | Step wrapper가 action 또는 compensation callback 전에 seed | `AbstractSagaData.auth_context_snapshot`은 replacement data에 명시 값이 없으면 보존 | 보호 step과 snapshot propagation은 provider가 정확히 하나 필요 |

## Provider 매트릭스

| Provider | 유효한 경로 | 유효하지 않은 경로 | 사용할 수 없는 경로 | 검증 표면 |
| --- | --- | --- | --- | --- |
| OIDC | 유효한 bearer JWT가 선택된 safe claim을 `AuthContext`로 매핑 | malformed token, invalid signature, issuer/audience/`azp`/time claim 실패, JWKS key miss는 `CHALLENGE / INVALID_CREDENTIAL` | discovery 또는 JWKS fetch 실패는 `ERROR / VERIFICATION_PROVIDER_UNAVAILABLE` | `plugins/spakky-oidc` provider test와 FastAPI/gRPC/Typer boundary test |
| Policy | 일치하는 allow rule이 설명 가능한 allow evidence 반환 | explicit deny가 우선하며, matching allow가 없으면 deny evidence 반환 | malformed 또는 unavailable policy document/provider는 auth port를 통해 `ERROR` 반환 | `plugins/spakky-policy` evaluator/provider test |
| OpenFGA | 허용된 check response가 `ALLOW`로 매핑 | 거부된 check response가 `DENY`로 매핑 | OpenFGA client/service 비가용은 `ERROR / VERIFICATION_PROVIDER_UNAVAILABLE` | `plugins/spakky-openfga` provider test |
| Cryptography | Snapshot sign/verify, hash, HMAC, password verify 성공 시 provider-native success 값 반환 | snapshot 없음은 `CHALLENGE / SNAPSHOT_MISSING`, invalid signature 또는 malformed envelope는 `CHALLENGE / SNAPSHOT_INVALID`, expired snapshot은 `CHALLENGE / SNAPSHOT_EXPIRED`, password verification failure는 `CHALLENGE / INVALID_CREDENTIAL` 반환 | signer/verifier/password provider 비가용은 `ERROR / VERIFICATION_PROVIDER_UNAVAILABLE` | `plugins/spakky-cryptography` auth provider test |

## Diagnostics

Startup validation은 plugin loading과 scan 뒤, service start 전에 실행됩니다.

- 보호된 metadata가 있으면 `AUTHENTICATION` provider가 정확히 하나 필요합니다.
- `@require_permission`, `@require_role`, `@require_scope`, `@require_policy`, `@require_relation`은 각각 일치하는 provider capability가 정확히 하나 필요합니다.
- 활성화된 `AuthSnapshotPropagationConfig`에는 `SNAPSHOT_SIGN` provider와 `SNAPSHOT_VERIFY` provider가 각각 정확히 하나 필요합니다.
- 보호된 사용처가 없고 snapshot propagation config도 켜져 있지 않다면 provider가 없어도 fatal하지 않습니다.

Provider가 0개이거나 2개 이상이면 `AuthStartupCapabilityValidationError`가 발생하고 `auth.capability.validation.error` startup diagnostic detail이 기록됩니다. Runtime non-ALLOW decision은 `AuthRequirementDeniedError.decision`에 보존되므로 adapter가 `CHALLENGE`, `DENY`, `ERROR`를 transport별 응답으로 매핑할 수 있습니다.

## Migration

제거된 legacy security package에서 옮기는 방법과 R03 conformance gate에서 사용하는 최종 grep allowlist는 [인증/인가 전환 가이드](auth-migration.md)를 참고하세요.
