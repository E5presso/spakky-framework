---
title: "ADR-0021: Multimodal model content와 explicit LLM execution policy"
date: '2026-08-23'
status: accepted
---

# ADR-0021: Multimodal model content와 explicit LLM execution policy

> Text-only caller를 깨지 않고 portable multimodal input을 추가하고, media URI network authority를 provider-bound policy로 분리합니다.
> Fallback, cache, retry/concurrency/rate/circuit와 durable retry identity는 모두 operator가 명시하며 이미 성공한 billable model call을 후속 실패 때문에 재실행하지 않습니다.

## 맥락 (Context)

ADR-0016의 logical model catalog와 ADR-0017의 bounded iterative loop는 provider topology와 tool authority를 caller에게서 분리했지만 model message는 plain text에 한정됐습니다. 이미지·오디오·비디오·문서를 받으려면 protocol adapter 또는 provider SDK object를 application contract에 직접 노출해야 했고, checkpoint·compaction·capability·cache가 같은 content identity를 공유하지 못했습니다.

Remote media URI는 값 생성 시 DNS/fetch를 수행하면 synchronous constructor가 network side effect를 갖고 event loop를 막습니다. 반대로 syntax validation만 하고 provider로 넘기면 DNS rebinding/private-address 접근을 model/cache 직전에 통제할 authority가 없습니다. Application이 소유하는 private media gateway, custom scheme와 deterministic `.test` fixture도 public-Internet default와 구분해야 합니다.

Provider 장애 처리도 hidden global fallback이나 ambient retry로 추가하면 operator가 선택한 route, 비용, cache partition과 stream replay 의미가 흐려집니다. Exact/semantic response cache는 model input identity를 가져야 하지만 application data용 `spakky-cache`를 자동 재사용하거나 request metadata를 tenant authority로 믿을 수 없습니다. 특히 provider 성공 뒤 cache store가 실패한 경우 일반 retry/fallback을 적용하면 같은 billable request를 중복 실행합니다.

Durable resume은 JSON checkpoint를 typed decode한 뒤에만 검증하면 대형 inline media나 변조된 shape를 먼저 복원할 수 있습니다. Repository가 evidence를 순서대로 반환한다는 가정, 이전 checkpoint replay, resume marker가 original conversation turn을 덮는 문제도 fail-closed identity와 맞지 않습니다.

## 결정 (Decision)

### 1. Core model input은 portable ordered content part를 사용합니다

`ModelMessage.content`는 기존 `str` 또는 다음 ordered sequence입니다.

| Part | 입력 의미 |
|------|-----------|
| `TextPart` | ordered text segment |
| `ImagePart` | `image/*` URI 또는 bytes |
| `AudioPart` | `audio/*` URI 또는 bytes |
| `VideoPart` | `video/*` URI 또는 bytes |
| `DocumentPart` | `application/*`/`text/*` URI 또는 bytes + optional filename |

Media part는 URI와 bytes 중 정확히 하나만 갖고 optional `source`/`content_digest` provenance를 보존합니다. `ModelMessage.user(content, metadata=...)`가 lower-level canonical constructor입니다. `RunAgentInput.attachments`는 기존 positional field 순서 뒤에 append하고 instruction을 첫 `TextPart`로 유지합니다. Attachment가 없으면 `user_message()`는 기존 plain-string message를 그대로 만듭니다.

`MediaSafetyLimits` default는 `allowed_uri_schemes=frozenset({"https"})`, `allowed_uri_hosts=None`, media 16개, inline bytes aggregate 20 MiB입니다. Part별 custom limit가 섞이면 request는 가장 작은 count/byte limit를 적용합니다. `ModelMessage`와 `ModelRequest` 모두 media budget을 검증하며, `ModelRequest`는 complete request의 모든 message를 다시 aggregate합니다.

`ModelRequest.__post_init__()`은 outer messages/context sequence를 tuple로 고정하고 request-level metadata를 snapshot하며 nested value type과 request-wide media aggregate를 검증합니다. Nested message/context/manifest/digest/tool/schema deep copy는 `ModelRequest.snapshot()`이 수행합니다. `LlmAgentModel.complete()`/`stream()`은 진입 시 이 snapshot 하나를 만들고 capability, URI policy, cache lookup/key, provider request와 cache store가 그 동일한 값을 관찰하게 합니다.

`ModelCapability.input_modalities`는 `TEXT`/`IMAGE`/`AUDIO`/`VIDEO`/`DOCUMENT`를 route별로 선언합니다. Core `IAgentModel.validate_request()`와 fallback-aware router는 request의 actual modality가 selected/reachable capability에 포함되는지 provider I/O 전에 검사합니다. Provider 이름으로 capability를 추론하지 않고 provider별 MIME/source wire 제한은 adapter가 더 좁게 검증합니다.

이 결정은 input만 확장합니다. Common `ModelResponse`, `ModelStreamEvent`와 Agent final은 text, strict structured value와 tool call을 유지하며 generated image/audio/video/file output contract를 추가하지 않습니다.

### 2. URI value construction과 network authority를 분리합니다

`ImagePart.from_uri()` 등 value constructor는 network에 접근하지 않습니다. Absolute remote URI, allowed scheme, credential/control-character 부재와 host를 검증하고, default authority에서는 localhost/local resolver suffix와 non-public literal address를 거부합니다. `data:`/`file:`은 허용 scheme으로도 선택할 수 없습니다.

Application은 `MediaSafetyLimits.allowed_uri_hosts`로 exact host authority를 부여하거나 `allowed_uri_schemes`로 custom remote scheme을 명시할 수 있습니다. 이 값은 part에 immutable policy snapshot으로 남습니다.

`spakky-llm`은 replaceable `ILLMMediaUriPolicy.validate(target, request)`를 provider/cache 앞에 둡니다. Default `PublicLlmMediaUriPolicy(timeout_seconds=2.0)`는 ordinary HTTP(S) hostname을 `asyncio.to_thread(getaddrinfo)`와 async timeout으로 resolve하고 모든 address가 public인지 검사합니다. 다음 경우는 framework DNS를 생략합니다.

- explicit `allowed_uri_hosts`: application이 host 접근 authority를 인수합니다.
- `.test`: local/CI SDK fake가 실제 DNS에 의존하지 않습니다.
- custom allowed scheme: framework가 resolver 의미를 추론하지 않습니다.
- literal IP: core static literal-address guard를 이미 통과했습니다.

DNS failure·timeout·invalid/private resolution은 `LlmConfigurationError`와 `LlmFailureClass.CONFIGURATION`으로 정규화합니다. Fallback은 현재 route가 이 class를 명시한 경우만 가능합니다. Framework는 URI body를 fetch하거나 cache input body로 변환하지 않습니다.

### 3. First-party provider는 portable input을 native wire로만 변환합니다

OpenAI-compatible adapter는 supported image URI/inline, inline MP3/WAV audio, filename이 있는 inline PDF/plain-text document를 매핑하고 video를 거부합니다. Anthropic adapter는 supported image URI/inline, PDF URI/inline, inline UTF-8 plain-text document를 매핑하고 audio/video를 거부합니다. Google adapter는 operator가 capability에 선언한 URI/bytes를 `types.Part.from_uri()`/`from_bytes()`로 보냅니다.

Assistant/tool correlation history와 system/evidence framing은 기존 text semantics를 유지합니다. Provider가 지원하지 않는 role/media, MIME/source 조합을 text description으로 바꾸거나 drop하지 않고 `LlmUnsupportedFeatureError`로 fail closed합니다. Provider-native generated-media response를 common output처럼 노출하지 않습니다.

### 4. Fallback은 route-owned ordered failure edge입니다

`LlmModelRoute`는 `fallbacks: tuple[str, ...]`와 `fallback_on: frozenset[LlmFailureClass]`를 함께 선언합니다. 둘 중 하나만 설정하거나 blank/duplicate/missing/self ref, catalog 전체 cycle은 `LlmConfig` 생성에서 거부합니다.

Execution은 caller가 선택한 primary ref에서 시작합니다. Retry는 current candidate 안에서 먼저 수행하고, 그 candidate route의 `fallback_on`이 발생한 failure class를 허용한 경우에만 그 route의 declared fallback order를 depth-first로 탐색합니다. Global provider scan, default route 복귀, profile/provider/raw-model inference는 없습니다. Capability preflight도 `CAPABILITY` edge만 따라갑니다.

Stream은 caller에게 어떤 event도 emit하기 전까지만 retry/fallback할 수 있습니다. 첫 event 뒤 error는 current stream의 `ERROR`와 `DONE`으로 닫고 다른 candidate에서 prefix를 replay하지 않습니다. Actual provider attempt가 없던 capability/media/cache selection은 evidence에서 `actual_attempt=false`로 구분합니다.

### 5. Resilience는 profile-scoped이고 기본으로 비활성입니다

`LlmProfile.resilience`의 default는 다음과 같습니다.

| Policy | Disabled default | Enable contract |
|--------|------------------|-----------------|
| Retry | `max_attempts=1` | max 10 + explicit failure classes |
| Concurrency | `max_in_flight=None` | positive in-flight + optional queue timeout |
| Rate | `requests_per_period=None` | positive period rate + bounded wait |
| Circuit | `failure_threshold=None` | positive threshold + counted classes |

Retry delay는 provider `Retry-After`가 있으면 그 값을, 아니면 configured bounded deterministic exponential backoff를 사용합니다. Circuit default counted classes는 timeout, transport, provider-unavailable입니다. State는 `LlmAgentModel` instance의 profile key별로 분리하고 clock은 `ILLMClock`으로 교체할 수 있습니다. Provider SDK `max_retries>0`와 orchestration `max_attempts>1`을 함께 켜지 않습니다.

Concurrency/rate/circuit rejection은 각각 typed failure class로 routing evidence에 남습니다. Default configuration은 hidden queue, retry, local rate limit나 circuit state를 만들지 않습니다.

### 6. Response cache는 explicit route policy와 trusted scope를 요구합니다

`LlmCachePolicy` default는 `mode=disabled`, `ttl_seconds=300.0`, `namespace="spakky-llm:v1"`입니다. Exact/semantic mode를 선택하면 `LlmAgentModel` construction은 mode별 `ILLMResponseCache` exactly one과 `ILLMCacheScopeResolver`를 요구합니다. Core/plugin은 production in-memory response cache를 자동 등록하지 않습니다.

Scope resolver는 arbitrary `ModelRequest.metadata`를 tenant authority로 쓰지 않고 `LlmCacheScope(tenant_scope, safety_scope)`를 반환합니다. Exact key는 namespace/scope, resolved logical/physical route와 connection hash, ordered guarded content fingerprint, context manifest/digest reference, tool/schema/structured output와 sampling을 SHA-256에 결속합니다. Raw text/bytes/URI는 exact key surface에 넣지 않습니다. Semantic mode만 backend에 ordered text와 media MIME+digest descriptor를 별도 `semantic_input`으로 제공하므로 semantic cache는 model input을 읽는 explicit trust boundary입니다.

Cache는 `complete()`의 complete, tool-free response만 저장하고 streaming은 항상 bypass합니다. Hit의 current usage는 zero이고 saved usage는 metadata evidence로 보존합니다. Lookup failure가 fallback하려면 route가 `CACHE` class를 허용해야 합니다.

Provider가 성공한 뒤 cache store가 실패하면 retry/fallback을 금지하고 `fallback_suppressed="provider_success"`로 기록합니다. Error는 provider usage와 route metadata를 `AbstractAgentModelError` receipt로 운반합니다. Agent runner는 receipt의 usage/cost/counters, MODEL evidence와 durable checkpoint를 저장한 뒤 terminalize하므로 billable call을 다시 실행하지 않습니다.

### 7. Durable checkpoint는 raw identity를 decode 전에 검증합니다

각 durable save는 positive monotonic `checkpoint_revision`을 올리고 `AgentEvidenceKind.CHECKPOINT`에 revision, step, history length, raw JSON shape size와 SHA-256 checkpoint fingerprint를 append합니다. Resume은 repository order 대신 최대 revision을 latest로 선택하고 state revision과 evidence가 일치하는지 확인합니다.

Shape, fingerprint, history length와 step을 multipart base64 decode·remote URI policy 실행 전에 검증합니다. Initial history fingerprint는 ordered content, inline bytes/URI, MIME/provenance와 per-part safety limits를 포함하고 every MODEL evidence의 initial-history identity와 대조합니다. Older valid checkpoint replay, duplicate revision, raw shape/body tamper와 inconsistent input evidence는 `agent_checkpoint_invalid`입니다. Compaction은 restored history에도 기존 assistant/tool correlation validation을 적용합니다.

Checkpoint는 original `conversation_id`, `user_turn`, `persist_session_turn`도 bind합니다. Resume caller는 같은 effective conversation을 사용해야 하고 resume marker instruction은 original question을 덮지 않습니다. Server-owned session이 실패 후 resume에서 성공하면 `ITaskStore`에는 original user turn과 validated assistant text, 또는 text가 없는 typed final의 deterministic JSON serialization이 기록됩니다. `ConversationTurn.content`는 의도적으로 text이므로 same-run checkpoint는 media를 복원하지만 이후 server-session turn에는 attachment를 자동 replay하지 않습니다. Client-injected multimodal `message_history` 경로의 no-write-back 의미도 유지합니다.

Provider step의 assistant text와 `seen_call_ids`는 full candidate validation과 batch tool-limit gate가 성공한 뒤에만 context에 commit합니다. Invalid descriptor/binding 또는 oversized batch의 partial text/call id가 checkpoint나 TaskStore를 오염시키지 않습니다. Billable terminal failure도 saved counter를 보존하므로 resume은 이미 소진한 step/token/cost budget을 이어받습니다.

### 8. Provider-native batch/file/search는 separate optional port입니다

Batch inference는 `ILLMBatchProvider`, provider file lifecycle은 `ILLMFileProvider`, native web/file search는 `ILLMNativeToolProvider`로 분리합니다. 이 포트는 interactive `ModelRequest`, `AgentRunner` tool catalog와 다른 application-invoked boundary입니다. Plugin entry point는 구현을 auto-register하지 않고 file을 prompt에 주입하거나 native search를 자동 실행하지 않습니다.

### 9. AG-UI/A2A는 protocol media를 core attachment로 정규화합니다

AG-UI는 가장 최근 user message의 text fragments와 typed image/audio/video/document URL/data source를 instruction+attachments로 변환합니다. URL은 MIME이 필수이고 data는 strict base64이며 deprecated binary, media-only input과 invalid source를 runner 전에 거부합니다. Provenance는 `ag-ui:{message.id}`입니다.

A2A는 text와 raw/URL media part를 변환하고 document filename을 보존하지만 data part를 attachment로 해석하지 않습니다. Provenance는 `a2a:{message_id}`입니다. 두 adapter 모두 16 parts/20 MiB aggregate를 inbound 경계에서 적용합니다.

A2A executor는 approval payload, task/conversation id, instruction, attachments, 모든 data part의 canonical model selector와 metadata, 최종 `RunAgentInput`을 전부 검증한 뒤에만 Task enqueue/working transition/approval signal append를 수행합니다. 뒤쪽 invalid media나 duplicate selector가 있어도 앞의 valid 값을 사용해 protocol state를 mutate하지 않습니다.

## 대안 (Alternatives)

### 대안 A: Provider SDK content type을 core에 직접 노출합니다

Provider별 rich content를 즉시 쓸 수 있지만 Agent/application/protocol/checkpoint/cache가 특정 SDK wire type에 결합됩니다. Portable input part와 adapter-owned mapping을 선택합니다.

### 대안 B: URI constructor가 DNS 또는 body fetch를 수행합니다

한 지점에서 검사할 수 있지만 value construction이 blocking network side effect를 갖고 cache/provider candidate와 다른 시점의 DNS 결과를 신뢰하게 됩니다. Static value guard와 async provider-bound policy를 분리합니다.

### 대안 C: 모든 장애에서 global provider fallback과 automatic retry를 수행합니다

가용성은 높아 보이지만 refusal/configuration/capability/cache 오류까지 다른 model로 숨길 수 있고 partial stream·비용을 재생합니다. Route-owned failure allowlist와 profile opt-in retry를 사용합니다.

### 대안 D: `spakky-cache` 또는 process-local cache를 자동 사용합니다

Application data cache와 model-response identity/safety partition 의미가 다르고 tenant authority를 추론하게 됩니다. Dedicated port는 `spakky-llm`에 두되 backend/scope는 application이 명시합니다.

### 대안 E: Cache store failure에서도 provider를 다시 호출합니다

새 backend에 store할 기회는 생기지만 이미 성공한 billable call을 중복 실행합니다. Usage/routing receipt를 durable accounting에 넘기고 terminal failure로 닫습니다.

### 대안 F: Batch/file/native search를 interactive inference에 자동 주입합니다

Provider 기능은 쉽게 보이지만 upload lifecycle, native search authority와 Agent tool approval가 섞입니다. Separate optional port만 제공하고 application이 호출 여부를 결정합니다.

## 결과 (Consequences)

### 긍정적

- 기존 text caller와 positional `RunAgentInput`을 유지하면서 protocol-neutral multimodal input을 사용할 수 있습니다.
- Model capability, cache, provider와 checkpoint가 같은 immutable content snapshot에 결속됩니다.
- Network resolution은 async provider-bound authority이고 private/custom host는 application이 명시적으로 인수합니다.
- Retry/fallback/cache가 hidden inference 없이 route/profile policy와 evidence로 재현됩니다.
- Post-provider failure와 durable resume이 이미 발생한 model usage와 budget을 잊지 않습니다.
- Invalid A2A inbound는 task/signal state를 mutate하기 전에 닫힙니다.

### 부정적

- Operator는 route modality, fallback failure classes, cache backend/scope와 media host authority를 실제 deployment에 맞게 관리해야 합니다.
- Semantic cache backend는 raw semantic text를 읽는 trust boundary이므로 privacy review가 필요합니다.
- Default public DNS policy와 explicit application host authority가 맞지 않으면 custom `ILLMMediaUriPolicy`를 구현해야 합니다.
- Generated-media output과 first-party batch/file/native-search implementation은 제공하지 않습니다.

### 중립적

- RAG는 계속 `spakky-agent`의 `IRetriever`/`RetrievalContext`/`RetrievalTool`이며 별도 RAG plugin이나 `Document`/`Chunk`/ingest/receipt/policy RAG domain taxonomy를 만들지 않습니다. Multimodal `DocumentPart`는 model input value이지 retrieval document abstraction이 아닙니다.
- Knowledge base/index lifecycle, production cache/retrieval backend와 media hosting은 application/vendor 책임입니다.
- ADR-0015의 official SDK/tool authority/schema validation, ADR-0016의 opaque catalog/provider resolution, ADR-0017의 bounded loop/approval/limit와 ADR-0018~0020의 context/retrieval/memory/evaluation/cost/telemetry 결정은 유지됩니다. 이 ADR은 ADR-0016의 text-only capability 제한과 ADR-0017의 text-centric message limitation만 대체합니다.

## 참고 자료

- [ADR-0015: Multi-provider LLM official SDK adapters](0015-multi-provider-llm-official-sdk-adapters.md)
- [ADR-0016: Operator-owned model catalog](0016-operator-owned-model-catalog.md)
- [ADR-0017: Bounded iterative model/tool loop](0017-bounded-iterative-agent-loop.md)
- [ADR-0018: Typed agent output과 composed execution context](0018-typed-agent-output-and-context.md)
- [ADR-0019: Minimal retrieval runtime](0019-minimal-retrieval-runtime.md)
- [ADR-0020: Semantic memory, evaluation, pricing과 Agent telemetry](0020-agent-memory-evaluation-cost-telemetry.md)
