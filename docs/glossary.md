# Spakky Framework 용어 사전

> Spakky 문서와 코드에서 반복해서 등장하는 용어를 실제 API 이름과 함께 설명합니다.

이 문서는 Spakky Framework에서 사용하는 핵심 용어를 정의합니다.

---

## 코어 개념

### Pod

컨테이너가 관리하는 컴포넌트 단위. `@Pod` 데코레이터로 클래스나 함수를 표시하면 `ApplicationContext`가 인스턴스 생명주기와 의존성 주입을 담당합니다.

```python
from spakky.core.pod.annotations.pod import Pod

@Pod()
class UserService:
    def __init__(self, repository: UserRepository) -> None:
        self.repository = repository
```

**스코프 (Scope)**:

- `SINGLETON` — 애플리케이션 전체에서 하나의 인스턴스 공유 (기본값)
- `PROTOTYPE` — 요청할 때마다 새 인스턴스 생성
- `CONTEXT` — 요청/컨텍스트 범위 내에서 인스턴스 공유

### ApplicationContext

Pod 인스턴스와 생명주기를 관리하는 핵심 컨테이너. 의존성 주입, 서비스 시작/종료, 이벤트 루프 관리를 담당합니다.

```python
from spakky.core.application.application_context import ApplicationContext

context = ApplicationContext()
context.add(UserService)
context.start()
```

### Optional DI (`get_or_none`)

컨테이너에 등록되어 있지 않을 수 있는 Pod를 안전하게 조회하는 패턴입니다. `ApplicationContext.get_or_none(type_)`은 Pod가 등록되어 있으면 인스턴스를 반환하고, 없으면 `None`을 반환합니다. `get()`과 달리 `NoSuchPodError`를 발생시키지 않습니다.

```python
from spakky.core.pod.interfaces.container import IContainer

propagator = container.get_or_none(ITracePropagator)
if propagator is not None:
    propagator.inject(carrier)
```

이 패턴은 플러그인 간 선택적 의존성에 사용됩니다. 예를 들어, `spakky-fastapi`의 `AddBuiltInMiddlewaresPostProcessor`는 `get_or_none(ITracePropagator)`로 propagator를 조회하고, 있으면 `TracingMiddleware`를 등록합니다.

### Collection DI

같은 타입 또는 interface를 구현하는 모든 Pod 후보를 하나의 collection으로
주입하는 패턴입니다. 생성자 파라미터에 `list[T]`, `tuple[T, ...]`,
`dict[str, T]`를 선언하면 `ApplicationContext`가 매칭 후보를 Pod name 기준의
안정적인 순서로 주입합니다. `dict[str, T]`는 Pod name을 key로 사용합니다.

```python
@Pod()
class NotificationFanout:
    def __init__(self, senders: dict[str, IEmailSender]) -> None:
        self.senders = senders
```

지원하지 않는 collection 형태는 `UnsupportedCollectionDependencyTypeError`를
발생시킵니다. 필수 collection 의존성에 매칭 후보가 없으면 Pod 인스턴스화가
실패하므로, 없을 수 있는 후보 집합은 optional 의존성이나 기본값으로 표현합니다.

### SpakkyApplication

애플리케이션 부트스트랩 진입점. 컴포넌트 스캔, 플러그인 로딩, 컨테이너 설정을 위한 fluent API를 제공합니다.

```python
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext

app = SpakkyApplication(ApplicationContext())
app.scan()  # 현재 패키지의 Pod 자동 스캔
```

### DiscoveryManifest

`SpakkyApplication.scan()`의 discovery 결과를 재사용하기 위한 선택형 JSON artifact입니다. `enable_discovery_manifest()`로 활성화하며, schema version, Python version, scan 대상, exclude pattern, source file mtime/size fingerprint가 일치할 때만 hit로 사용됩니다. decision은 `miss`, `hit`, `stale_schema`, `stale_input` 중 하나로 시작 진단에 기록됩니다.

### Actuator

애플리케이션의 `health`, `readiness`, `liveness`, `info` 상태를 전송 방식과
독립적인 모델로 집계하는 상태 확인 표면입니다. `spakky-actuator`는 probe와 info
contributor를 `ActuatorExtensionRegistry`에 모으고,
`ActuatorAggregationService`가 endpoint별 결과를 평가합니다.

```python
from spakky.actuator import AbstractHealthProbe
from spakky.core.pod.annotations.pod import Pod


@Pod()
class DatabaseProbe(AbstractHealthProbe):
    ...
```

### Redis Cache Backend

`spakky-cache`의 backend-neutral `ICache[T]` 계약을 Redis 저장소로 구현하는
플러그인입니다. `spakky-redis`는 `RedisCache[T]`, `RedisCacheConfig`,
Actuator health/info contributor를 제공합니다.

```python
from spakky.cache import cacheable
from spakky.core.stereotype.usecase import UseCase


@UseCase()
class ProfileService:
    @cacheable(key="profile:{0}")
    def load_profile(self, user_id: str) -> str:
        return f"profile:{user_id}"
```

### AuthContext

`spakky-auth`가 정의하는 request/context-scoped 인증 상태입니다. Inbound adapter나
snapshot verifier가 `ApplicationContext` context value에 저장하며, 보호된 boundary는
사용자 메서드 인자 대신 이 context를 읽어 인증 주체, tenant, role, scope, safe claim을
평가합니다.

```python
from spakky.auth import AuthContext, AuthSubject

auth_context = AuthContext(
    subject=AuthSubject(id="user:alice"),
    issuer="issuer:local",
    scopes=("documents:read",),
)
```

### Auth Requirement Decorator

클래스나 메서드 boundary에 provider에 묶이지 않는 auth metadata를 붙이는 decorator입니다.
`@protected`, `@require_scope`, `@require_role`, `@require_permission`,
`@require_policy`, `@require_relation`은 AND semantics로 결합되며, 실제 decision은
등록된 provider port가 수행합니다.

```python
from spakky.auth import protected, require_scope

@protected
@require_scope("documents:read")
def read_document(document_id: str) -> str:
    ...
```

### Auth Provider Capability

provider plugin이 `spakky.contributions.spakky.auth` entry point로 선언하는 기능
단위입니다. `spakky-auth` startup validation은 보호된 boundary와 snapshot propagation이
요구하는 `AUTHENTICATION`, `POLICY_EVALUATION`, `PERMISSION_CHECK`, `ROLE_CHECK`,
`SCOPE_CHECK`, `RELATION_CHECK`, `SNAPSHOT_SIGN`, `SNAPSHOT_VERIFY` capability가
정확히 하나의 provider에 의해 충족되는지 확인합니다. `PASSWORD_HASH`와
`PASSWORD_VERIFY`는 provider가 선언하고 사용할 수 있는 capability지만, 현재 startup
validation은 password-only provider의 고유성을 startup requirement로 계산하지 않습니다.

### AuthContextSnapshot

task, broker, event, saga 같은 비동기 경계에서 raw bearer token 대신 전파하는
provider에 묶이지 않는 인증 snapshot입니다. `spakky-cryptography`는 HMAC 기반
`SNAPSHOT_SIGN`/`SNAPSHOT_VERIFY` provider를 제공하고, consumer boundary는 snapshot을
검증한 뒤 `AuthContext`를 seed합니다.

### OIDC Provider

`spakky-oidc`가 제공하는 bearer JWT 인증 provider입니다. Discovery document와 JWKS를
읽고 issuer, audience, signature, time claim을 검증한 뒤 선택된 safe claim만
`AuthContext`로 옮깁니다. Browser login, callback, session route는 애플리케이션이나
별도 서비스가 담당합니다.

### OpenFGA Provider

`spakky-openfga`가 제공하는 관계 기반 인가 provider입니다. `@require_relation` 같은
요구사항을 OpenFGA check 요청으로 변환해 `ALLOW`/`DENY`/`ERROR` 결정을 반환합니다.
Tuple write, authorization model migration, list resources 같은 관리 기능은 제공하지
않습니다.

### Policy Document Evaluator

`spakky-policy`가 제공하는 policy document 평가기입니다. YAML, TOML, JSON으로 작성한
정책 문서를 typed model로 바꾼 뒤 `PolicyDocumentEvaluator`가 resource/action,
permission, role, scope 요구사항을 평가합니다. 명시적인 `deny`가 우선하고, 일치하는
`allow`가 없으면 기본적으로 거부합니다.

### Kafka Transport

`spakky-kafka`가 제공하는 Integration Event 전송 플러그인입니다. Event system의
`IAsyncEventTransport` 구현으로 동작하며, 비즈니스 코드는 Kafka client가 아니라
`IAsyncEventPublisher` 또는 `IAsyncEventBus`에 의존합니다.

### RabbitMQ Transport

`spakky-rabbitmq`가 제공하는 Integration Event 전송 플러그인입니다. RabbitMQ consumer는
메시지 header에서 trace/auth snapshot을 복원하고, 등록된 event handler를 호출합니다.
보호된 handler의 ack/nack 정책은 RabbitMQ auth 설정으로 조정할 수 있습니다.

---

## Stereotype 데코레이터

Pod의 역할을 명시하는 특화된 데코레이터입니다. 기능적으로 `@Pod`와 동일하지만 의도를 명확히 합니다.

### @Configuration

설정 값을 담는 클래스 자체를 Pod로 등록하는 `@Pod` 특화 stereotype입니다.
환경변수 기반 설정은 보통 `BaseSettings`를 상속한 `@Configuration` 클래스로 선언합니다.
다른 Pod를 만드는 factory는 클래스 내부 메서드가 아니라 모듈 수준 `@Pod()` 함수로 둡니다.

```python
from spakky.core.stereotype.configuration import Configuration
from pydantic_settings import BaseSettings

@Configuration()
class DatabaseConfig(BaseSettings):
    pool_size: int = 10
    connection_url: str = "postgresql://localhost/app"
```

### @Controller

외부 요청을 처리하는 클래스 (HTTP, CLI 등).

```python
from spakky.core.stereotype.controller import Controller

@Controller()
class UserController:
    def __init__(self, service: UserService) -> None:
        self.service = service
```

### @UseCase

비즈니스 로직을 캡슐화하는 애플리케이션 서비스.

```python
from spakky.core.stereotype.usecase import UseCase

@UseCase()
class CreateUserUseCase:
    def execute(self, command: CreateUserCommand) -> User:
        ...
```

### @Agent

LLM 기반 orchestration을 수행하는 application workflow component입니다. `@UseCase`와
동격인 `@Pod` 계열 stereotype이며, inbound adapter에서 호출되고 constructor DI로
model/workspace/shell/git/repository 같은 outbound port를 주입받습니다.

`@Agent`가 `execute()`를 직접 선언하면 `AgentYield` stream 계약을 검증합니다.
`execute()`를 생략하면 framework runner가 `RunAgentInput`을 받는 runner-backed
`execute()`를 합성하고 bounded model/tool loop를 소유합니다. FastAPI WebSocket, CLI, SSE 같은 Spakky-native inbound
adapter는 `AgentYield`를 transport별 payload로 변환하고, protocol adapter는
`AgentRunner.run_events()`의 `AgentEvent`를 사용합니다.

### RunAgentInput

`spakky.agent.inbound.RunAgentInput`은 runner-backed Agent 실행을 시작하거나 재개하는
inbound contract입니다. `state_id`는 run/state id, `instruction`은 이번 model request의
사용자 지시, `conversation_id`는 멀티턴 thread id, `parent_run_id`는 delegation parent를
나타냅니다. `resume=True`는 durable signal queue에 들어온 승인 결정 같은 외부 입력을
반영해 paused run을 재개할 때 사용합니다.

`message_history`가 있으면 caller가 history를 직접 제공하는 stateless 경로이고, 없으면
runner가 optional `ITaskStore`에서 `effective_conversation_id`로 persisted history를 읽습니다.
`context`는 static `AgentContext`이며 기본값은 empty envelope입니다.

### AgentExecutionLimits

`AgentExecutionSpec.limits`에 들어가는 bounded runner 계약입니다. 기본 model step은 8,
실제 tool call은 32이며 token/cost/time budget은 opt-in입니다. Step limit은 다음 model request
전에, tool limit은 whole batch dispatch 전에, token limit은 provider total usage를 누적한
뒤, cost limit은 operator pricing으로 terminal step cost를 누적한 뒤, timeout은
model/async-tool await에 집행됩니다. `max_cost`는 positive finite `Decimal`이며 pricing이
없거나 usage/ref를 exact하게 계산할 수 없으면 fail closed합니다. Deadline이 있는 in-process sync tool은
preempt할 수 없어 batch 전체가 실행 전에 `agent_sync_tool_timeout_unenforceable`로
거부됩니다. `AgentExecutionSpec.timeout_seconds` direct field나 alias는 없습니다.

### Typed structured output

`AgentExecutionSpec.output_type`으로 선언하는 final result 계약입니다. 지원 class는 Pydantic
`BaseModel`, dataclass, `TypedDict`이며 runner가 strict closed JSON Schema를 model에 보내고
provider JSON을 실제 declared type으로 materialize합니다. Native `run()`은 typed value,
`run_events()`와 AG-UI/A2A는 JSON-safe value를 사용합니다. Text JSON fallback, coercion,
extra key와 silent key loss는 허용하지 않습니다.

### AgentContext

`RunAgentInput.context`와 `IAgentContextProvider`가 공유하는 typed model-input envelope입니다.
`packs`, optional `manifest`, optional `digest`를 가지며 static pack이 dynamic pack보다 먼저
결합됩니다. Manifest와 digest는 pack 전체 provenance를 정확히 덮어야 합니다.

### ContextPack

ID, content, source, semantic role, freshness/relevance, token budget, sensitivity를 가진 한 context
단위입니다. Runner는 raw prompt concatenation 대신 `ModelRequest.context`에 pack을 전달하고
guarded evidence message로 조립합니다. Token budget truncation과 redaction은 caller object를
mutate하지 않는 prepared copy에 적용됩니다.

### IAgentContextProvider

Agent constructor에 주입하는 optional async context port입니다.
`provide(run_input, model_step)`에서 `AgentContext`를 반환합니다.
`refresh_context_each_step=False`면 invocation 첫 결과를 재사용하고 `True`면 model step마다
호출합니다. Raw provider context는 checkpoint하지 않으므로 fresh resume에서는 provider를
다시 호출합니다.

Durable resume은 raw static context도 저장하지 않고 prepared static context fingerprint만
checkpoint합니다. Static context를 사용했던 caller는 resume에 동일 context를 다시 보내야
하며 model-bound prepared fingerprint가 다른 missing/different/additive context는
`agent_checkpoint_invalid`입니다.

### RAG

RAG (Retrieval-Augmented Generation)는 model request 전에 관련 정보를 검색해
`AgentContext`에 evidence로 넣는 실행 형태입니다. Spakky에서는 application-owned
`IRetriever`가 `RetrievalHit`를 반환하고 constructor-injected `RetrievalContext`가 이를
JSON source frame, 총 token budget, manifest를 가진 context pack으로 바꿉니다. 기본값은
`limit=5`, `max_context_tokens=2048`, `allow_empty=False`입니다.

### Agentic RAG

같은 `IRetriever`를 constructor-injected `RetrievalTool`로 제공해 model이 필요할 때
`search(query=...)`를 선택하는 실행 형태입니다. Model에는 query만 보이고 tenant,
namespace, filters는 adapter에 고정됩니다. Result content는 일반 `TOOL` history/evidence
의미를 따르므로 classic context budget이나 redaction이 자동 적용되지 않습니다.

### IRetriever / RetrievalHit

`IRetriever.retrieve(query, *, limit, tenant_id, namespace, filters)`는 classic RAG와
agentic RAG가 공유하는 async 검색 port입니다. `RetrievalHit`는 ID, model-facing content,
source, optional score/rerank score, digest/revision, scope와 span을 담습니다. Bound scope와
반환 hit가 exact match해야 하며 duplicate ID나 malformed provenance는
`AgentRetrievalError`입니다.

`RetrievalHit.metadata`의 arbitrary 값은 model context, tool result, durable context
evidence에 전달되지 않습니다. Context preparation이 보존할 수 있는 metadata는 framework의
strictly validated `retrieval` block뿐이며 unknown key나 malformed field가 있으면 block
전체를 제거합니다. 별도 RAG plugin은 없습니다. Vector 확장은 `ITextEmbedding`,
`IVectorSearch`, `VectorRetriever`와 optional `IReranker`/`RerankedRetriever`를 조합하지만,
framework는 vector backend나 index write API를 제공하지 않습니다.

### ContextManifest / ContextDigest

`ContextManifest`는 pack ID/source/role과 origin/evidence/digest reference를 순서대로
기록하는 provenance envelope입니다. `ContextDigest`는 정확히 그 manifest와 전체 pack ID
순서에서 파생된 digest입니다. Incomplete coverage, conflicting entry, duplicate pack ID,
static/dynamic 일부만 덮는 partial digest는 fail closed합니다. Evidence에는 raw context나
digest summary가 아니라 이 provenance와 digest value만 남깁니다. Combined context
fingerprint는 evidence의 correlation digest로서 같은 step의 동일 context를 deduplicate하고
변경된 context를 구분합니다. `CONTEXT`/`CONTEXT_MANIFEST` evidence의 digest는 이
fingerprint이고, `CONTEXT_DIGEST` evidence는 declared digest를 유지하면서 payload의
`context_fingerprint`로 결속됩니다.

Runner가 검증하는 것은 manifest reference와 pack coverage이며 declared digest value를 raw
content에서 재계산하지는 않습니다.

### Approval fingerprint

승인 재사용을 exact tool payload에 묶는
`approval:{state_id}:{call_id}:{digest}` identifier입니다. `digest`는 canonical JSON
arguments의 full SHA-256입니다. Checkpoint는 `approved_call_fingerprints`를 보존하며
pending argument가 달라지면 기존 승인을 재사용하지 않습니다. `MODIFY`는 새 payload로
fingerprint와 assistant tool-call history를 함께 갱신합니다.

### Tool continuation group

Tool calls를 가진 하나의 `ASSISTANT` message와 그 call ID 각각에 대응하는 연속 `TOOL`
result message 전체입니다. Compaction은 이 group을 분리할 수 없습니다. Runner는 custom
strategy를 포함해 각 compaction 단계 뒤 correlation을 검증하고 orphan/missing result를
provider request 전에 fail closed합니다.

### ITaskStore

`spakky.agent.interfaces.task_store.ITaskStore`는 core Agent transcript를
`conversation_id`로 저장하는 server-side session port입니다. `ConversationTurn`은 user
또는 assistant 발화만 담고, 다음 run의 model request history로 재생됩니다. A2A protocol
`Task` snapshot 저장은 `spakky-a2a`의 `IA2ATaskRepository`/`SpakkyA2ATaskStore`가 담당하므로
core transcript store와 섞지 않습니다. TTL, correction과 tenant/user scope를 가진
long-term memory는 `ITaskStore`가 아니라 `IMemoryStore`를 사용합니다.

### MemoryEntry / IMemoryStore / MemoryRetriever

`MemoryEntry`는 kind, content/provenance, exact tenant/user/namespace, timezone-aware creation과
optional expiry, previous entry를 가리키는 `supersedes`를 가진 immutable long-term memory
revision입니다. `IMemoryStore`는 `save()`, scoped `search()`, explicit `delete()`를 정의하는
backend port이며 core production 구현은 없습니다.

`MemoryRetriever`는 store와 tenant/user/namespace, allowed `MemoryKind` tuple을 bind해
`IRetriever`로 노출합니다. Expired entry와 superseded target을 제거하고 cross-scope,
duplicate, conflicting correction과 active correction cycle을 `AgentMemoryError`로 거부합니다. 기존
`RetrievalContext` 또는 `RetrievalTool`로 감싸 model context/tool에 연결합니다.

### AgentEvaluationSuite

Explicit `AgentEvaluationDataset`의 각 `AgentEvaluationCase`를 정확히 하나의
`AgentEvaluationSample`과 짝지어 evaluator tuple 순서로 offline 채점하는 aggregate입니다.
Built-in evaluator는 ordered tool trace, strict structured output, reference precision/recall,
retrieval reference groundedness를 제공합니다. `ModelJudgeEvaluator`는 application-owned
`IModelJudge`만 사용하며 default judge가 없습니다.

`AgentEvaluationReport.evidence_candidates()`가 만드는 `AgentEvidenceKind.EVALUATION`은
metric/pass/score/case/sample correlation 전용입니다. `AgentEvidenceKind.SIGNAL`은 runner가
소비한 non-terminal inbound signal audit이며 offline evaluation과 다른 kind입니다.
Evaluation case/sample의 structured JSON과 tool arguments/metadata는 construction 시 deep
snapshot됩니다.

### ModelPricingCatalog / ModelCost

Opaque logical model ref를 per-million-token `ModelPrice`에 연결하는 immutable versioned
operator snapshot과 그 exact `Decimal` 계산 결과입니다. Cached/generic cache-write rate는
없으면 input rate를, TTL-specific write rate는 없으면 generic write rate를 사용합니다.
Built-in price는 없으며 `AgentExecutionLimits.max_cost`를
사용할 때 pricing이 없거나 usage/ref가 불완전하면 fail closed합니다. Durable checkpoint는
pricing fingerprint와 cumulative cost를 함께 보존하고, resume은 `MODEL` evidence의 exact
route/full usage로 completed step cost를 재계산해 checkpoint total과 대조합니다.

### ModelUsage cache fields

`ModelUsage.cached_input_tokens`, total `cache_write_input_tokens`, TTL별
`cache_write_5m_input_tokens`/`cache_write_1h_input_tokens`는 provider가 보고한 cache read와
write input을 보존합니다. OpenAI, Anthropic, Google adapter가 official SDK usage를
provider-neutral field로 매핑하고, pricing은 inclusive `input_tokens`에서 cached/total write를
빼 regular input을 계산합니다. TTL breakdown이 있으면 5-minute + 1-hour 합이 total
cache-write usage와 정확히 같아야 합니다. Distinct TTL price가 설정됐는데 nonzero write
usage가 TTL별로 분류되지 않은 경우도 fail closed합니다.

### IAgentTelemetry / AgentSpanRecord

Runner가 완료한 `RUN`, `MODEL`, `TOOL`, `RETRIEVAL` interval을 관측 adapter에 전달하는 sync
outbound port와 immutable record입니다. Record는 nanosecond timestamps, scalar correlation,
OK/ERROR와 optional error code만 허용하며 prompt/context/completion, retrieval query/content,
tool arguments/result를 포함하지 않습니다. Sink failure는 `AgentTelemetryError`입니다.

### AgentEvent

`spakky.agent.event.AgentEvent`는 AG-UI, A2A 같은 protocol adapter가 소비하는
protocol-neutral event union입니다. `MessageDeltaEvent`, `ReasoningDeltaEvent`,
`ToolCallStartEvent`, `ToolCallArgsDeltaEvent`, `ToolCallEndEvent`, `ToolCallResultEvent`,
`RunStartedEvent`, `RunPausedEvent`, `RunFinishedEvent`, `StepStartedEvent`,
`StepFinishedEvent`, `StateSnapshotEvent`, `StateDeltaEvent`, `ArtifactEvent`가 포함됩니다.

모든 event는 `AgentEventAttribution(agent_id, run_id, conversation_id, parent_run_id)`를
통해 어떤 agent/run/conversation에서 나왔는지 보존합니다. AG-UI는 이를 `runId`와
`threadId`로, A2A는 task id와 context id로 투영합니다.

Provider가 `TOOL_CALL_CANDIDATE`만 보내면 runner는 없는 START/END frame만 합성합니다.
`run_events()`에서 signal hook의 `Progress`는 `signal_progress` `ArtifactEvent`가 되며,
지원하지 않는 hook yield shape는 `agent_signal_projection_unsupported` terminal입니다.

### IAgentModel { #iagentmodel }

`spakky-agent`가 소유하는 model outbound port입니다. `spakky-llm`은 이 port를
구현하는 공식 provider plugin으로, operator-owned logical model catalog를 OpenAI Chat
Completions, Anthropic Messages, Gemini Developer API, Vertex AI SDK adapter에
라우팅합니다. OpenRouter는 standard OpenAI-compatible connection으로, vLLM은 명시적
vLLM dialect로 지원됩니다. Provider 응답과 stream은 공통
`ModelResponse`와 `ModelStreamEvent`로 정규화됩니다.

표준 Agent runner는 `IAgentModel.stream()` 또는 guarded `complete()`에서 whole tool
batch를 받은 뒤 검증·승인·순차 dispatch합니다. Assistant tool-call 및 `TOOL` result
history를 다음 model request에 넣어 반복하고, tool call이 없는 step에서 final을 한 번
만듭니다. 사용법은
[AI Agent 개발](guides/agents.md), catalog 사용법은
[LLM 모델 라우팅](guides/llm-routing.md)을 확인하세요.

### Logical model ref { #logical-model-ref }

`support/primary`처럼 caller가 선택하는 operator-owned opaque key입니다. Case-sensitive이며
앞뒤 공백 외에는 canonicalization하지 않고 `/`도 provider 구분자로 해석하지 않습니다.
실제 provider, connection profile, physical model ID를 caller 계약에서 분리해 route 교체
시 Agent 코드를 유지합니다.

### ModelSelection

한 run에서 logical model ref를 지목하는 core frozen dataclass입니다. 공개 필드는 필수
`model_ref: str` 하나뿐입니다. Provider, profile, raw model, endpoint, credential,
selection metadata는 이 계약에 속하지 않습니다. Blank ref는 core에서, unknown ref는
catalog-aware router에서 fail closed합니다.

### LlmProfile

`spakky-llm` 운영자가 소유하는 connection/backend/auth 설정입니다. Provider 진단 표식,
API family, base URL, API key 또는 Google credential strategy, headers, timeout, retry,
stream 허용 여부를 담습니다. 실제 model ID와 `ModelCapability`은 담지 않습니다.

### LlmModelRoute

Logical model ref를 `LlmProfile`, physical provider model ID, `ModelCapability`에 연결하는
strict catalog entry입니다. vLLM의 model별 `chat_template_kwargs`도 route가 소유합니다.
Route와 profile을 교체해도 caller의 logical ref는 유지할 수 있습니다.

### Gemini Developer API

API key로 인증하는 Google의 공식 Gemini API 제품명입니다. “Developer”는 개발 환경이나
무료·비상용 endpoint라는 뜻이 아닙니다. `spakky-llm`에서는
`LlmProviderApi.GOOGLE_GEMINI_DEVELOPER`와 explicit `API_KEY` credential strategy로
선택합니다.

### Vertex AI

Google Cloud project/location과 ADC (Application Default Credentials) 또는 명시적인
service-account 파일을 사용하는 별도 Google backend입니다. 설치된 Google Gen AI SDK의
enterprise mode로 연결하며, profile 이름이 아니라 credential identity와 IAM이 실제 접근
권한을 결정합니다.

### Agent Persistence Contribution

Durable Agent 실행에 필요한 `IAgentStateRepository`, `IAgentSignalRepository`,
`IAgentEvidenceRepository` 구현을 provider plugin이 기여하는 방식입니다.
SQLAlchemy 구현은 `spakky.contributions.spakky.agent` entry point로 제공되며,
운영용 in-memory fallback은 없습니다.

### AgentTeammate

`AgentExecutionSpec.teammates`에 들어가는 delegation 선언입니다. `AgentTeammate`는
`name`과 정확히 하나의 binding을 갖습니다. 로컬 teammate는 `pod=SomeAgent`, 원격
teammate는 `card_url="https://.../.well-known/agent-card.json"`로 선언합니다.
둘 다 없거나 둘 다 있으면 `AgentDefinitionError`입니다.

### AG-UI Adapter

`spakky-agui`가 제공하는 UI streaming protocol adapter입니다. `AgentRunner.run_events()`의
`AgentEvent`를 AG-UI `BaseEvent`로 투영하고, FastAPI SSE endpoint(`add_agui_endpoint`),
HTTP streaming endpoint(`add_agui_http_stream_endpoint`), WebSocket endpoint
(`add_agui_websocket_endpoint`), stdio helper를 제공합니다. AG-UI에는 전용 approval
event가 없으므로 non-null approval ID가 있는 approval-required `RunPausedEvent`만
`hitl_approval` deferred tool call로 표현됩니다. Authentication/user-input pause처럼
`approval_id=None`인 event는 현재 `AgUiPendingApprovalError`입니다.

### A2A Adapter

`spakky-a2a`가 제공하는 Agent-to-Agent protocol adapter입니다. `@A2ACompatible` marker와
post-processors는 `@Agent` spec/tool/teammate에서 AgentCard를 파생하고, JSON-RPC,
HTTP+JSON REST, gRPC transport에 선언형으로 연결합니다. `A2AAgentDelegate`는 원격 AgentCard를
사용해 teammate call을 보내고 remote stream을 child `AgentEvent`로 parent run에 합류시킵니다.

### MCP Adapter

`spakky-mcp`가 제공하는 Model Context Protocol adapter입니다.
`MCPClient.open_runner()`는 run마다 선택된 외부 MCP server tools를 lazy
`mcp_search_tools`/`mcp_call_tool` 경로로 `AgentToolCatalog`에 합류시킨
`AgentRunner`를 엽니다. MCP server는 agent가 아니라 외부 도구 카탈로그를 표준 MCP
프로토콜로 제공하는 별도 tool host입니다.

### @Repository

데이터 접근 계층. 영속성 저장소와의 상호작용을 추상화합니다.

```python
from spakky.data.stereotype.repository import Repository

@Repository()
class UserRepository:
    def find_by_id(self, id: UUID) -> User | None:
        ...
```

### @EventHandler

이벤트를 처리하는 클래스. `@on_event` 데코레이터와 함께 사용합니다.

```python
from spakky.event.stereotype.event_handler import EventHandler, on_event

@EventHandler()
class UserEventHandler:
    @on_event(UserCreatedEvent)
    async def handle(self, event: UserCreatedEvent) -> None:
        ...
```

---

## AOP (관점 지향 프로그래밍)

### Aspect

횡단 관심사 (로깅, 트랜잭션 등)를 모듈화하는 컴포넌트. `IAspect` 또는 `IAsyncAspect` 인터페이스를 구현합니다.

```python
from spakky.core.aop.aspect import Aspect
from spakky.core.aop.interfaces.aspect import IAspect

@Aspect()
class LoggingAspect(IAspect):
    def before(self, *args, **kwargs) -> None:
        print("Method called")
```

### Advice

Aspect가 특정 시점에 실행하는 액션:

- **Before** — 메서드 실행 전
- **AfterReturning** — 메서드 정상 반환 후
- **AfterRaising** — 메서드 예외 발생 후
- **After** — 메서드 실행 후 (결과와 무관)
- **Around** — 메서드 실행을 감싸서 제어

### Pointcut

Advice가 적용될 메서드를 선택하는 조건자 함수.

```python
from spakky.core.aop.pointcut import Around

def is_service_method(method) -> bool:
    return hasattr(method, "__service__")

@Around(pointcut=is_service_method)
def around(self, joinpoint, *args, **kwargs):
    return joinpoint(*args, **kwargs)
```

### JoinPoint

Aspect가 개입할 수 있는 프로그램 실행 지점. Around advice에서 다음 호출을 제어할 때 사용합니다.

---

## 도메인 모델 (spakky-domain)

### Entity

고유 식별자로 구분되는 도메인 객체. `AbstractEntity`를 상속합니다.

```python
from spakky.domain.models.entity import AbstractEntity

@mutable
class User(AbstractEntity[UUID]):
    name: str
    email: str
```

### ValueObject

식별자 없이 속성값으로만 동등성을 판단하는 불변 객체. `AbstractValueObject`를 상속합니다.

```python
from spakky.domain.models.value_object import AbstractValueObject

@immutable
class Email(AbstractValueObject):
    value: str
```

### AggregateRoot

일관성 경계를 관리하는 엔터티의 진입점. 도메인 이벤트를 수집하며, 발행은 `AggregateCollector`와 `TransactionalEventPublishingAspect`가 트랜잭션 커밋 후 수행합니다. `AbstractAggregateRoot`를 상속합니다.

```python
from spakky.domain.models.aggregate_root import AbstractAggregateRoot

@mutable
class Order(AbstractAggregateRoot[UUID]):
    items: list[OrderItem]

    def add_item(self, item: OrderItem) -> None:
        self.items.append(item)
        self.add_event(ItemAddedEvent(order_id=self.uid, item=item))
```

---

## 이벤트 시스템 (spakky-event)

> 설계 배경 및 대안 분석은 [ADR-0001](adr/0001-event-system-redesign.md)을 참조하세요.

### DomainEvent

하나의 바운디드 컨텍스트 내에서 발생하는 도메인 상태 변경. `AbstractDomainEvent`를 상속합니다.

```python
from spakky.domain.models.event import AbstractDomainEvent

@immutable
class UserCreatedEvent(AbstractDomainEvent):
    user_id: UUID
    email: str
```

### IntegrationEvent

바운디드 컨텍스트 간 또는 서비스 간 통신에 사용되는 이벤트. `AbstractIntegrationEvent`를 상속합니다.

```python
from spakky.domain.models.event import AbstractIntegrationEvent

@immutable
class OrderPlacedEvent(AbstractIntegrationEvent):
    order_id: UUID
    total_amount: Decimal
```

### 동사 규칙 {#동사-규칙-verb-convention}

이벤트 시스템 전체에서 동사를 다음과 같이 구분합니다:

| 동사 | 의미 | 사용 레이어 |
|------|------|------------|
| `publish` | 이벤트를 시스템에 발행 (호출자가 경로를 모름) | EventPublisher |
| `send` | Integration Event를 외부로 전송 | EventBus, EventTransport |
| `dispatch` | 등록된 핸들러에 인프로세스 전달 | Dispatcher, Mediator |
| `register` | 이벤트 타입에 핸들러 콜백 등록 | Consumer |

### 이벤트 인터페이스

> 설계 배경은 [ADR-0001](adr/0001-event-system-redesign.md) 참조.

| 역할 | 인터페이스 (sync / async) | 설명 |
|------|--------------------------|------|
| 발행 진입점 | `IEventPublisher` / `IAsyncEventPublisher` | 타입 기반 라우팅 |
| 인프로세스 전달 | `IEventDispatcher` / `IAsyncEventDispatcher` | 핸들러에 dispatch |
| 핸들러 등록 | `IEventConsumer` / `IAsyncEventConsumer` | 콜백 등록 |
| 외부 전송 진입점 | `IEventBus` / `IAsyncEventBus` | Outbox seam |
| 실제 메시지 전송 | `IEventTransport` / `IAsyncEventTransport` | Kafka/RabbitMQ |

주요 구현체:

| 구현체 | 역할 |
|--------|------|
| `EventMediator` | Consumer + Dispatcher 통합 (인프로세스) |
| `EventPublisher` | `match event:` 타입 라우터 |
| `DirectEventBus` | 기본 EventBus → Transport 위임 |
| `KafkaEventTransport` | Kafka Transport 구현 |
| `RabbitMQEventTransport` | RabbitMQ Transport 구현 |

### Consumer와 EventHandler

- **Consumer** — 핸들러를 **등록**하는 인터페이스 (`register(event_type, callback)`)
- **EventHandler** — 이벤트를 **처리**하는 클래스 스테레오타입 (`@EventHandler` + `@on_event`)

`EventHandlerRegistrationPostProcessor`가 `@EventHandler` Pod를 스캔하여 `AbstractDomainEvent`를 받는 `@on_event` 메서드를 in-process Consumer에 자동 등록합니다. `AbstractIntegrationEvent`는 broker transport consumer 경로에서 처리합니다.

### EventPublisher

이벤트를 발행하는 단일 진입점:

- `IEventPublisher` / `IAsyncEventPublisher` — `publish(event: AbstractEvent)` → 타입 기반 라우팅
  - `AbstractDomainEvent` → `EventMediator` (인프로세스 dispatch)
  - `AbstractIntegrationEvent` → `IEventBus` (외부 전송)

### EventBus와 EventTransport

Integration Event 전송을 2단 인터페이스로 분리:

- **EventBus** (`IEventBus`) — Integration Event 발행 진입점. Outbox seam 역할
- **EventTransport** (`IEventTransport`) — 실제 메시지 브로커 전송 (Kafka/RabbitMQ 구현)

### 파티션 키 (partition key)

Integration Event가 어느 브로커 파티션으로 갈지 결정하는 값입니다. `AbstractIntegrationEvent.partition_key` property로 노출되며, 기본값 `None`은 "키 없음"을 의미하여 브로커가 라운드로빈으로 분산합니다.

같은 파티션 키를 가진 이벤트는 항상 같은 파티션으로 갑니다 — Kafka가 보장하는 순서는 파티션 안에서만 성립하므로, 파티션 키는 순서 보장의 **전제 조건**입니다. 보통 aggregate id를 키로 사용합니다.

Outbox를 경유하는 경로에서는 릴레이가 키 단위 순서를 함께 지킵니다. Transport가 영구적이고 특정 레코드에 귀속 가능한 거부를 `EventDeliveryRejectedError`로 확정하면 그 키의 후속 메시지를 보류하고 retry 예산을 쓰지만, 연결·timeout·queue·그 밖의 transport 장애는 원래 예외 타입을 유지하며 그 장애 자체로 예산을 소모하지 않습니다. `fetch_pending`은 키를 통째로 claim하여 여러 릴레이 인스턴스가 같은 키를 병렬 발행하지 않으며, 영구 레코드 귀속 거부로 retry를 소진한 메시지는 발행 포기(abandoned) 처리되어 키를 다시 열어 줍니다 — 상세와 그 대가는 [Kafka 가이드](guides/kafka.md)의 파티션 키 절 참조.

전달 경로: 이벤트 → `IEventBus` → (`OutboxMessage.partition_key` 컬럼 경유) → `IEventTransport.send(..., partition_key=...)` → Kafka `produce(key=...)`. RabbitMQ transport는 파티션 개념이 없어 이 값을 라우팅에 사용하지 않습니다.

---

## 태스크 시스템 (spakky-task)

> 설계 배경은 [ADR-0003](adr/0003-task-schedule-decorator-split.md) 참조.

### @TaskHandler

태스크 핸들러 클래스를 마크하는 스테레오타입. `@task` 및 `@schedule` 메서드를 그룹화합니다.

```python
from spakky.task import TaskHandler, task, schedule
from datetime import timedelta

@TaskHandler()
class EmailTaskHandler:
    @task
    def send_email(self, to: str) -> None: ...

    @schedule(interval=timedelta(hours=1))
    def cleanup(self) -> None: ...
```

### @task

메서드를 온디맨드 디스패치 대상으로 마크하는 데코레이터. 플러그인의 AOP Aspect가 호출을 가로채 태스크 큐로 전달합니다.

### @schedule

메서드를 정기 실행 대상으로 마크하는 데코레이터. `interval`, `at`, `crontab` 중 정확히 하나를 지정해야 합니다.

| 파라미터 | 타입 | 설명 |
|-----------|------|------|
| `interval` | `timedelta` | 고정 간격 실행 |
| `at` | `time` | 매일 특정 시각 실행 |
| `crontab` | `Crontab` | Cron 기반 스케줄 |

### Crontab

Python 네이티브 타입 기반 cron 명세 값 객체. 문자열 대신 `Weekday`/`Month` IntEnum을 사용합니다.

```python
from spakky.task import Crontab, Weekday, Month

# 매주 월요일 09:00
Crontab(weekday=Weekday.MONDAY, hour=9)

# 매년 1월 1일 자정
Crontab(month=Month.JANUARY, day=1)
```

필드 순서: `month` → `day` → `weekday` → `hour` → `minute` (내림차순 시간 척도)

---

## 서비스 생명주기

### IService

시작/종료 생명주기를 가진 동기 서비스 인터페이스.

```python
import threading
from spakky.core.service.interfaces.service import IService

class BackgroundWorker(IService):
    def set_stop_event(self, stop_event: threading.Event) -> None: ...
    def start(self) -> None: ...
    def stop(self) -> None: ...
```

### IAsyncService

시작/종료 생명주기를 가진 비동기 서비스 인터페이스.

```python
from asyncio import locks
from spakky.core.service.interfaces.service import IAsyncService

class AsyncWorker(IAsyncService):
    def set_stop_event(self, stop_event: locks.Event) -> None: ...
    async def start_async(self) -> None: ...
    async def stop_async(self) -> None: ...
```

---

## 플러그인 시스템

### Plugin

프레임워크 확장을 식별하는 불변 객체. 이름으로 구분됩니다.

```python
from spakky.core.application.plugin import Plugin

FASTAPI_PLUGIN = Plugin(name="spakky-fastapi")
```

플러그인 로딩:

```python
app.load_plugins(include={FASTAPI_PLUGIN})
```

---

## 데이터 계층 (spakky-data)

### @Transactional

메서드에 트랜잭션 경계를 적용하는 Aspect.

### AggregateCollector

Repository 저장 경로에서 AggregateRoot 참조를 수집하는 컴포넌트. 트랜잭션 커밋 후 `TransactionalEventPublishingAspect`가 collector에 모인 AggregateRoot의 이벤트를 발행합니다.

---

## 트랜잭셔널 Outbox (spakky-outbox)

> 설계 배경은 [ADR-0002](adr/0002-outbox-plugin-architecture.md), [ADR-0006](adr/0006-move-outbox-to-core.md) 참조.

### OutboxEventBus

`@Primary`로 기본 `IEventBus`를 대체하여, Integration Event를 브로커 대신 Outbox 테이블에 저장합니다. 비즈니스 데이터와 같은 트랜잭션 내에서 원자적으로 기록하고, 브로커가 수락 가능한 레코드는 확인될 때까지 재전송하므로 성공 전달 경로는 중복 가능한 at-least-once 의미를 갖습니다. 영구 레코드 귀속 거부는 retry 소진 후 abandoned 처리되어 성공 전달이 0회일 수 있습니다.

```python
from spakky.outbox.bus.outbox_event_bus import OutboxEventBus, AsyncOutboxEventBus
```

### OutboxMessage

영속성에 독립적인 Outbox 메시지 모델. `id`, `event_name`, `payload`, `headers`, `partition_key`, `created_at`, `published_at`, `retry_count`, `claimed_at`, `abandoned_at` 필드를 가집니다.

```python
from spakky.outbox.common.message import OutboxMessage
```

### IOutboxStorage

Outbox 메시지의 CRUD를 담당하는 포트 인터페이스. `spakky-sqlalchemy`는
`spakky.contributions.spakky.outbox` contribution으로 SQLAlchemy 구현체와 Outbox
table을 제공합니다.

```python
from spakky.outbox.ports.storage import IOutboxStorage, IAsyncOutboxStorage
```

### OutboxRelayBackgroundService

백그라운드 서비스로 Outbox 테이블을 폴링하여 미전송 메시지를 `IEventTransport`로 전송합니다.

---

## 구조화 로깅 (spakky-logging)

### @logged

메서드에 자동 로깅을 적용하는 어노테이션. 인자, 반환값, 실행 시간을 자동 기록합니다. `enable_masking`, `masking_keys`, `slow_threshold_ms`, `max_result_length`, `log_args`, `log_result` 파라미터를 지원합니다.

```python
from spakky.plugins.logging import logged

@logged()
def create_user(self, name: str) -> str: ...
```

### LogContext

`contextvars` 기반 컨텍스트 전파. `bind()`, `unbind()`, `clear()`, `get()`, `scope()` 메서드로 요청 ID 등 공통 정보를 모든 로그에 자동 주입합니다.

```python
from spakky.plugins.logging import LogContext

LogContext.bind(request_id="abc-123")
```

### LoggingConfig

로깅 설정 `@Configuration` Pod. 환경변수 접두사 `SPAKKY_LOGGING__`로 구성합니다. `level`, `format` (`TEXT`/`JSON`/`PRETTY`), `mask_keys`, `slow_threshold_ms` 등을 설정합니다.

---

## 암호화 유틸리티 (spakky-cryptography)

### HMAC

공유 `Key`로 문자열을 서명하고 검증하는 유틸리티. `HMACType`은 `HS224`, `HS256`, `HS384`, `HS512` 알고리즘을 표현합니다.

```python
from spakky.plugins.cryptography.hmac_signer import HMAC, HMACType
from spakky.plugins.cryptography.key import Key

key = Key(size=32)
signature = HMAC.sign_text(key, HMACType.HS256, "message")
is_valid = HMAC.verify(key, HMACType.HS256, "message", signature)
```

### Password Encoder

패스워드 해시를 생성하고 입력 패스워드를 검증하는 인코더 계열. `Argon2PasswordEncoder`, `BcryptPasswordEncoder`, `ScryptPasswordEncoder`, `Pbkdf2PasswordEncoder`가 `encode()`와 `challenge(password)` 계약을 제공합니다.

```python
from spakky.plugins.cryptography.password.argon2 import Argon2PasswordEncoder

hashed = Argon2PasswordEncoder(password="secret").encode()
is_valid = Argon2PasswordEncoder(password_hash=hashed).challenge("secret")
```

---

## CLI 통합 (spakky-typer)

### @CliController

Typer 하위 명령 그룹으로 등록되는 CLI 컨트롤러 스테레오타입. `group_name`을 생략하면 클래스명을 kebab-case로 변환한 그룹명이 사용됩니다.

```python
from spakky.plugins.typer.stereotypes.cli_controller import CliController

@CliController("users")
class UserCliController:
    ...
```

### @command

`@CliController` 메서드를 Typer 명령으로 표시하는 데코레이터. `name`, `help`, `short_help`, `hidden`, `deprecated` 등 Typer 명령 옵션을 보존하고 `TyperCLIPostProcessor`가 컨테이너 초기화 중 등록합니다.

```python
from spakky.plugins.typer.stereotypes.cli_controller import command

@command("create")
def create_user(self, name: str, email: str) -> None:
    ...
```

### TyperCLIPostProcessor

`@CliController` Pod에서 `@command` 메서드를 스캔해 `Typer` 앱에 하위 명령 그룹을 추가하는 후처리기. 명령 실행 시 컨텍스트 스코프를 비우고 컨테이너에서 컨트롤러 인스턴스를 다시 조회합니다.

---

## Celery 통합 (spakky-celery)

### Celery 태스크 디스패치

`@task` 메서드 호출을 AOP로 가로채 Celery `send_task()` 호출로 변환하는 디스패치 패턴. 워커 컨텍스트 내부에서는 재디스패치하지 않고 원래 메서드를 직접 실행합니다.

```python
from spakky.task.stereotype.task_handler import TaskHandler, task

@TaskHandler()
class EmailTaskHandler:
    @task
    def send_email(self, to: str) -> None: ...
```

### CeleryTaskResult

Celery의 `AsyncResult`를 `spakky-task`의 태스크 결과 계약에 맞게 감싸는 결과 객체. 디스패치된 태스크의 `task_id`, 블로킹 `get()`, 비동기 `get_async()` 조회를 제공합니다.

### Celery Beat 스케줄

`@schedule` 메서드를 Celery Beat `beat_schedule` 항목으로 등록하는 스케줄 통합. `interval`, `at`, `Crontab` 라우트를 Celery schedule 또는 crontab 객체로 변환합니다.

```python
from datetime import timedelta

from spakky.task.stereotype.schedule import schedule

@schedule(interval=timedelta(minutes=30))
def health_check(self) -> None: ...
```

---

## 사가 시스템 (spakky-saga)

### @Saga

사가 오케스트레이터 클래스를 마크하는 스테레오타입. `@Pod`의 서브클래스이므로 패키지 스캔만으로 DI 컨테이너에 자동 등록됩니다.

```python
from spakky.saga import AbstractSaga, Saga, SagaFlow, saga_flow, saga_step

@Saga()
class OrderSaga(AbstractSaga[OrderSagaData]):
    @saga_step
    async def create_order(self, data: OrderSagaData) -> OrderSagaData: ...

    def flow(self) -> SagaFlow[OrderSagaData]:
        return saga_flow(self.create_order)
```

### AbstractSaga

사가의 기본 추상 클래스. `flow()`를 구현하여 사가 흐름을 선언하고, `execute(data)`로 실행합니다. 내부적으로 `run_saga_flow`에 클래스명을 `saga_name`으로 전달하여 구조화 로그에 포함합니다.

### @saga_step

사가 step 메서드를 `_SagaStepDescriptor`로 감싸는 데코레이터. 인스턴스 접근 시 bound 메서드가 `SagaStep`으로 승격되어 `>>`, `&`, `|` 연산자가 타입 안전하게 동작합니다.

```python
from spakky.saga import saga_step

@saga_step
async def create_order(self, data: OrderSagaData) -> OrderSagaData: ...
```

### SagaStep, Transaction, Parallel

DSL의 기본 빌딩 블록.

| 타입 | 역할 | 생성 방법 |
|------|------|---------|
| `SagaStep[T]` | 단일 action (compensate 없음) | `step(action)`, `@saga_step` 메서드 |
| `Transaction[T]` | action + compensate 쌍 | `step(action, compensate=...)`, `action >> compensate` |
| `Parallel[T]` | 동시 실행 그룹 (최소 2개) | `parallel(...)`, `a & b` |

### SagaFlow

최상위 흐름 정의. `saga_flow(*items)`로 생성하며, `.timeout(duration)`·`.on_compensation_failure(handler)`로 실행 옵션을 덧붙입니다. `>>` (action + compensate 쌍), `&` (병렬), `|` (에러 전략) 연산자를 지원합니다.

```python
from datetime import timedelta

from spakky.saga import parallel, saga_flow, step

flow = saga_flow(
    step(saga.create_order, compensate=saga.cancel_order),
    parallel(
        step(saga.reserve_stock, compensate=saga.release_stock),
        step(saga.process_payment, compensate=saga.refund_payment),
    ),
).timeout(timedelta(seconds=30))
```

### ErrorStrategy

사가 step 실패 시 적용할 전략:

| 전략 | 설명 |
|------|------|
| `Compensate()` | 역순 보상 후 FAILED 반환 (기본값) |
| `Skip()` | 실패를 무시하고 다음 step으로 진행 |
| `Retry(max_attempts, backoff, then)` | 재시도 후 `then` 전략 적용 |
| `ExponentialBackoff(base=1.0)` | `Retry.backoff`용 지수 백오프 (`base * 2^(attempt-1)`) |

`parallel()` 그룹 내부의 step은 v1에서 기본 `Compensate` 외 `on_error`를 지정할 수 없습니다.

### 타임아웃

| 수준 | 지정 방법 | 동작 |
|------|---------|------|
| step | `step(..., timeout=timedelta(...))` | 초과 시 `SagaStepTimeoutError`가 `on_error` 전략을 거침 |
| saga | `SagaFlow.timeout(duration)` | 초과 시 `SagaStatus.TIMED_OUT`으로 종료하고 commit된 step을 역순 보상 |

v1 제약상 전체 timeout이 `parallel()` 그룹 실행 도중 만료되면, 이미 성공했지만 compensable 등록 전인 side effect는 보상되지 않을 수 있습니다. 순차 step이나 이미 완료된 parallel 그룹의 commit된 step은 정상 보상됩니다.

### run_saga_flow

`SagaFlow`를 실행하는 얇은 엔트리. `AbstractSaga.execute`가 내부적으로 호출합니다.

```python
from spakky.saga import run_saga_flow

result = await run_saga_flow(flow, data, saga_name="OrderSaga")
```

### SagaResult

사가 실행 결과. `status` (`SagaStatus`), `data`, `failed_step`, `error`, `history` (`tuple[StepRecord, ...]`), `elapsed` 필드를 가집니다. 예외는 발생시키지 않습니다 (보상 실패 시 `SagaCompensationFailedError`는 예외).

### StepRecord / StepStatus

각 step의 실행 기록. `status`는 `COMMITTED` / `FAILED` / `COMPENSATED` 중 하나입니다.

### SagaStatus

사가 전체 상태 열거형: `STARTED`, `RUNNING`, `COMPENSATING`, `COMPLETED`, `FAILED`, `TIMED_OUT`.

### AbstractSagaData

사가 비즈니스 데이터 모델의 기본 클래스. `@immutable` + `AbstractDomainModel`을 확장하며, `saga_id: UUID` 필드가 기본 제공됩니다. 엔진 상태는 포함하지 않습니다.

---

## gRPC 시스템 (spakky-grpc)

### @GrpcController

gRPC 서비스 컨트롤러 클래스를 마크하는 스테레오타입. `@Controller`의 서브클래스입니다.

```python
from spakky.plugins.grpc.stereotypes.grpc_controller import GrpcController

@GrpcController(package="example.user", service_name="UserService")
class UserServiceController:
    ...
```

### @rpc

메서드를 gRPC RPC 엔드포인트로 마크하는 데코레이터. `RpcMethodType`을 지정하여 스트리밍 모드를 선택할 수 있습니다.

```python
from spakky.plugins.grpc.decorators.rpc import rpc, RpcMethodType

@rpc(method_type=RpcMethodType.UNARY)
async def get_user(self, request: GetUserRequest) -> GetUserResponse:
    ...
```

### RpcMethodType

gRPC 메서드 유형을 나타내는 열거형:

| 값 | 설명 |
|----|------|
| `UNARY` | 단일 요청, 단일 응답 |
| `SERVER_STREAMING` | 단일 요청, 스트림 응답 |
| `CLIENT_STREAMING` | 스트림 요청, 단일 응답 |
| `BIDI_STREAMING` | 양방향 스트리밍 |

### ProtoField

Pydantic `BaseModel` 필드에 protobuf 필드 번호를 명시적으로 지정할 때 사용하는 **선택적** 어노테이션입니다. `ProtoField`를 생략하면 `DescriptorBuilder`가 필드 이름의 SHA-256 해시에서 번호를 자동 부여합니다. 이름 기반이므로 필드 순서를 바꿔도 기존 번호는 변하지 않고, 필드를 추가해도 기존 번호가 보존됩니다(새 이름의 salt-0 해시가 기존 번호와 충돌하는 약 5.4억분의 1 확률의 경우만 예외). 예약 구간 19000–19999는 자동으로 건너뜁니다. 기존 `.proto` 계약과 번호를 맞추거나 특정 필드 번호를 무조건 고정해야 할 때 `ProtoField(number=N)`으로 번호를 직접 지정합니다.

```python
from typing import Annotated

from pydantic import BaseModel
from spakky.plugins.grpc.annotations.field import ProtoField


# 자동 번호 부여 (기본)
class GetUserRequest(BaseModel):
    user_id: str

# 번호 명시 (기존 계약 유지가 필요한 경우)
class GetUserRequestPinned(BaseModel):
    user_id: Annotated[str, ProtoField(number=1)]
```

### DescriptorRegistry

protobuf descriptor를 캐싱하고 관리하는 레지스트리. `DescriptorBuilder`가 Python 타입에서 descriptor를 자동 생성합니다. `spakky-grpc` 플러그인이 기본 Pod로 등록하므로 사용자는 listener 주소 같은 애플리케이션 설정만 제공합니다. 등록된 서비스의 전체 이름 목록(`service_names`)은 서버 리플렉션이 광고할 대상이 됩니다.

### GrpcServerSpec

`grpc.aio.Server`를 만들기 전까지 필요한 구성(핸들러, 인터셉터, bind 대상, 채널 옵션, 표준 서비스 등록 콜백)을 누적하는 명세. `grpc.aio.server()`가 호출 시점의 이벤트 루프에 묶이기 때문에, 실제 서버 생성은 서버를 구동할 루프에서 `build()`로 미뤄집니다. bind 대상은 주소와 TLS 자격증명을 함께 담으므로 평문 포트와 TLS 포트를 같은 목록에서 표현합니다.

### GrpcClient

`@GrpcController` 선언 하나에서 호출 가능한 gRPC callable을 만들어 주는 클라이언트. 호출자가 메시지 모델을 복제하면 필드 이름 한 글자 차이로 필드 번호가 갈라지므로, 서버가 등록하는 것과 같은 컨트롤러 클래스에서 descriptor를 만들고 호출 대상도 메서드 참조로 지정합니다.

```python
from spakky.plugins.grpc.client import GrpcClient

client = GrpcClient(channel, UserServiceController)
response = await client.unary_unary(UserServiceController.get_user)(
    GetUserRequest(user_id="1")
)
```

### 표준 서비스 (health·reflection)

애플리케이션 서비스와 함께 노출되는 gRPC 생태계 표준 서비스. `grpc.health.v1.Health`는 Kubernetes의 gRPC 네이티브 프로브가 호출하는 대상이고, 서버 리플렉션은 `.proto` 산출물이 없는 code-first 서비스를 외부 도구에서 조회하는 유일한 경로입니다. 둘 다 `SPAKKY_GRPC_HEALTH_SERVICE_ENABLED`·`SPAKKY_GRPC_REFLECTION_SERVICE_ENABLED`로 끌 수 있습니다.

### descriptor 스냅샷

컨트롤러에서 생성되는 와이어 배치(메시지 → 필드 이름 → 번호·타입)를 결정론적 JSON으로 렌더링한 결과. `spakky-grpc-descriptor-snapshot` 명령으로 출력하며, 저장소에 커밋해 두고 CI에서 diff하면 필드 이름 변경이 만드는 와이어 파손을 배포 전에 잡습니다.

---

## 분산 트레이싱 (spakky-tracing)

> 설계 배경은 [ADR-0004](adr/0004-distributed-tracing-architecture.md) 참조.

### TraceContext

W3C Trace Context Level 2 호환 컨텍스트 객체. `trace_id`, `span_id`, `parent_span_id`, `trace_flags`를 보유합니다. Python `contextvars`를 사용하여 asyncio 태스크 간 격리됩니다.

```python
from spakky.tracing.context import TraceContext

ctx = TraceContext.new_root()    # 새 트레이스 시작
child = ctx.child()              # 자식 span 생성
TraceContext.set(child)          # 현재 컨텍스트에 설정
TraceContext.get()               # 현재 컨텍스트 조회
TraceContext.clear()             # 컨텍스트 초기화
```

### ITracePropagator

서비스 경계에서 TraceContext를 헤더(carrier)에 주입/추출하는 인터페이스.

| 메서드 | 설명 |
|--------|------|
| `inject(carrier)` | 현재 TraceContext를 carrier에 기록 |
| `extract(carrier)` | carrier에서 TraceContext를 복원 (실패 시 `None`) |
| `fields()` | 사용하는 헤더 필드명 목록 |

### W3CTracePropagator

`ITracePropagator`의 기본 구현체. `traceparent` 헤더를 사용합니다.

### OTelTracePropagator

`ITracePropagator`의 OpenTelemetry 구현체. `spakky-opentelemetry` 플러그인이 로드되면 `OTelSetupPostProcessor`가 기본 `W3CTracePropagator`를 이 구현체로 교체합니다. OpenTelemetry SDK의 `TraceContextTextMapPropagator`에 위임합니다.

```python
from spakky.plugins.opentelemetry.propagator import OTelTracePropagator
```

### OpenTelemetryConfig

`spakky-opentelemetry` 플러그인의 설정 클래스. 환경변수 접두사 `SPAKKY_OTEL_`로 구성합니다.

| 필드 | 환경변수 | 기본값 |
|------|---------|--------|
| `service_name` | `SPAKKY_OTEL_SERVICE_NAME` | `"spakky-service"` |
| `exporter_type` | `SPAKKY_OTEL_EXPORTER_TYPE` | `ExporterType.OTLP` |
| `exporter_endpoint` | `SPAKKY_OTEL_EXPORTER_ENDPOINT` | `"http://localhost:4317"` |
| `sample_rate` | `SPAKKY_OTEL_SAMPLE_RATE` | `1.0` |

### OpenTelemetryAgentTelemetry

`spakky-opentelemetry`가 자동 등록하고 `IAgentTelemetry`에 bind하는 Agent span adapter입니다.
Spakky `TraceContext` parent와 exact nanosecond interval을 보존하고 operation kind를
`gen_ai.operation.name`과 OTel `SpanKind`로 매핑합니다. Raw-body denylist를 적용한 뒤 기존
`OpenTelemetryConfig` exporter pipeline을 사용합니다.

```python
from spakky.plugins.opentelemetry.telemetry import OpenTelemetryAgentTelemetry
```

### LogContextBridge

`spakky-opentelemetry`의 로깅 통합 컴포넌트. 생성자에서 `ILogContextBinder | None`을 Optional DI로 주입받아, `spakky-logging`이 등록된 경우 `TraceContext`의 trace/span ID를 `LogContext`에 동기화합니다. `ILogContextBinder`가 컨테이너에 없으면 no-op으로 동작합니다.

```python
from spakky.plugins.opentelemetry.bridge import LogContextBridge
```

### traceparent

W3C 표준 분산 트레이싱 헤더. 형식: `{version:2}-{trace_id:32}-{span_id:16}-{flags:2}`

예시: `00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01`

---

## 어노테이션

### @Primary

동일 타입의 여러 Pod 중 기본 선택 대상으로 지정.

```python
@Pod()
@Primary()
class DefaultUserRepository(IUserRepository):
    ...
```

### @Qualifier

의존성 주입 시 특정 Pod를 이름으로 지정.

```python
@Pod(name="cache")
class CacheUserRepository(IUserRepository):
    ...

@Pod()
class UserService:
    def __init__(self, repository: Annotated[IUserRepository, Qualifier(lambda p: p.name == "cache")]) -> None:
        ...
```

### PodBinding

같은 interface를 구현하는 Pod 후보가 여러 개일 때 application config가
선택할 구현체를 명시하는 binding policy 값입니다. `ApplicationContext.bind()`,
`bind_to_name()`, `bind_to_type()`으로 등록하며, Qualifier/name보다 낮고
`@Primary`보다 높은 우선순위로 단수 의존성을 선택합니다.

```python
from spakky.core.pod.binding import PodBinding

context.bind(PodBinding(interface=IRepository, implementation_name="postgres"))
```

### @Lazy

Pod 인스턴스화를 첫 사용 시점까지 지연.

### @Order

Pod 처리 순서를 지정 (숫자가 낮을수록 우선).

### @Tag

Pod를 태그로 그룹화하여 일괄 조회 가능.

---

## 에러 계층

### AbstractSpakkyFrameworkError

모든 Spakky 프레임워크 예외의 기반 클래스.

### PodAnnotationFailedError

Pod 어노테이션 처리 중 발생하는 예외.

### PodInstantiationFailedError

Pod 인스턴스 생성 중 발생하는 예외.
