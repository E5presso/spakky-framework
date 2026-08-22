---
title: "ADR-0015: Multi-provider LLM official SDK adapters"
date: '2026-08-22'
status: accepted
---

# ADR-0015: Multi-provider LLM official SDK adapters

> **부분 대체**: §2의 profile-owned model/capability와 §4의 caller profile/provider/raw-model 선택 및 Gemini Developer API 전용 Google backend 결정은 [ADR-0016](0016-operator-owned-model-catalog.md)이 대체합니다. §5의 one-request runner 제한은 [ADR-0017](0017-bounded-iterative-agent-loop.md)이 대체합니다. Package rename, provider 공식 SDK와 transport lifecycle, tool authority, terminal validation, portable schema 결정은 계속 Accepted입니다.
>
> vLLM 전용 adapter package를 provider-neutral `spakky-llm`으로 교체하고, operator가 허용한 profile을 provider 공식 SDK adapter에 연결합니다.
> Core `IAgentModel` 계약과 Agent tool-call 승인·dispatch authority는 유지하며 LangChain이나 Pydantic AI를 runtime dependency로 추가하지 않습니다.

## 맥락 (Context)

[ADR-0009](0009-agentic-hexagonal-architecture.md)는 첫 model implementation으로 local vLLM OpenAI-compatible server에 연결하는 `plugins/spakky-vllm`을 선택했습니다. 이 선택은 `spakky-agent`의 core model contract를 provider-neutral `IAgentModel`로 유지하면서 최초 outbound adapter를 제공하는 데에는 충분했습니다.

그러나 vLLM은 OpenAI-compatible API server 중 하나이며, package 이름이 vLLM에 고정될 이유는 core contract에 없습니다. OpenAI-compatible endpoint 외에 Anthropic Messages와 Google GenerateContent를 연결하려면 provider마다 request/response, streaming, tool call, structured output, usage, refusal/error 의미를 명시적으로 정규화해야 합니다. 하나의 raw HTTP client가 모든 API를 같은 protocol로 취급하면 provider-native 의미를 잃거나 dialect 분기가 늘어납니다.

기존 구현은 `httpx`로 OpenAI-compatible request와 Server-Sent Events(SSE)를 직접 처리했습니다. Provider 수가 늘어나면 auth header, retry, timeout, stream lifecycle, typed response 변화까지 framework가 반복 구현해야 하므로 transport 책임과 semantic mapping 책임을 분리할 필요가 있습니다.

## 결정 (Decision)

### 1. Package를 hard rename합니다

`plugins/spakky-vllm`을 `plugins/spakky-llm`으로 교체합니다. Distribution은 `spakky-llm`, module은 `spakky.plugins.llm`, plugin entry point는 `spakky-llm`, root extra는 `spakky[llm]`, 환경변수 prefix는 `SPAKKY_LLM__`을 사용합니다.

이전 distribution, module, class, 환경변수 이름을 위한 deprecation alias나 compatibility shim은 두지 않습니다. 아직 안정화된 production API가 아니므로 두 이름을 병존시켜 routing과 문서 정본을 흐리지 않습니다.

### 2. Model, Provider, Profile 책임을 분리합니다

- `LlmAgentModel`을 유일한 `IAgentModel` binding으로 두고, 선택된 target을 provider adapter로 routing합니다.
- `ILLMProvider` 구현은 하나 이상의 명시적 provider API family를 Spakky의 `ModelRequest`, `ModelResponse`, `ModelStreamEvent` 의미로 mapping합니다.
- 이 ADR이 처음 채택한 `LlmProfile`은 provider id, API family, model 기본값, base URL, API key, header, timeout/retry, capability와 dialect option을 함께 보관했습니다. **Model 기본값과 capability를 profile에 둔 부분, `ModelSelection`을 profile/provider/raw model로 해석한 부분은 ADR-0016이 대체했습니다.** 현재 profile은 연결·backend·auth만 소유하고, `LlmModelRoute`가 physical model과 capability를 소유하며 caller는 opaque `model_ref`만 전달합니다.

이 구조는 Pydantic AI가 분리한 Model/Provider/Profile 책임과 LangChain의 provider별 integration package에서 유용한 경계를 참고한 것입니다. Spakky는 이미 `IAgentModel`, message/tool/schema/event contract와 framework-owned Agent execution orchestration을 소유하므로 두 framework를 runtime dependency로 추가하지 않고 경계만 적용합니다.

### 3. Transport는 provider 공식 SDK에 위임합니다

- OpenAI와 OpenAI-compatible endpoint는 공식 `openai` async SDK의 Chat Completions API를 사용합니다. vLLM은 `OpenAICompatibleDialect.VLLM` profile에서만 `chat_template_kwargs`와 vLLM structured-output extension을 허용합니다.
- Anthropic은 공식 `anthropic` async SDK의 Messages API를 사용합니다.
- Google Gemini는 공식 `google-genai` async SDK의 GenerateContent API를 사용합니다.

Framework adapter는 SDK의 typed response와 stream을 provider-neutral contract로 mapping하고 provider error를 `AbstractLlmError` 계층으로 정규화합니다. Raw `httpx` request나 수동 SSE parser는 구현하지 않습니다. Google adapter는 `HttpOptions.async_client_args`에 `httpx.AsyncHTTPTransport`를 주입해 공식 SDK의 async backend를 httpx로 고정하고 aiohttp fallback을 허용하지 않지만, request 실행과 transport lifecycle은 계속 SDK가 소유합니다.

OpenAI와 Anthropic async client는 request/stream context가 끝날 때 닫습니다. Google SDK가 async client와 주입된 transport를 닫은 뒤 adapter는 이를 소유한 root sync `Client`도 `finally`에서 닫아 성공, provider error, transport error, stream 종료가 같은 lifecycle 경계를 따르게 합니다. Google complete/stream에서 `httpx.InvalidURL`과 `httpx.UnsupportedProtocol`은 `LlmConfigurationError`, timeout은 `LlmTimeoutError`, 나머지 transport failure는 `LlmTransportError`로 정규화합니다.

HTTP status 200은 그 자체로 성공이 아닙니다. OpenAI, Anthropic, Google adapter는 공식 SDK의 JSON decode, typed response validation, adapter mapping 과정에서 malformed success payload를 발견하면 `LlmResponseError`로 정규화합니다. OpenAI stream에서 usage opt-out을 요청하면 SDK `stream_options`에 usage를 요청하지 않고 unsolicited usage chunk도 무시합니다. Google thought part는 선택된 `LlmModelRoute.capability.supports_reasoning`이 true일 때만 요청하고 reasoning event로 게시합니다.

### 4. 연결 권한은 operator-owned profile에 고정합니다

`LlmConfig.profiles`는 배포 설정으로 등록한 connection allowlist입니다. 이 연결 권한 원칙은 유지하지만, caller가 profile/provider/raw model을 선택하던 초기 규칙은 ADR-0016이 대체합니다. 현재 `LlmConfig.models`가 logical `model_ref`를 profile과 physical model에 연결하고, 외부 `ModelSelection`은 catalog의 opaque `model_ref` 하나만 선택합니다.

Request metadata는 `base_url`, API key, header, profile 또는 physical model을 변경하지 못합니다. 따라서 AG-UI/A2A 같은 inbound adapter가 전달한 metadata가 임의 endpoint 접속이나 credential 치환으로 이어지지 않습니다. Environment가 effective config field를 공급하는 구성에서는 알 수 없는 최상위 `SPAKKY_LLM__...` key, nested profile/model field, API/dialect 조합을 설정 검증 단계에서 거부합니다. 세 config field를 모두 constructor에 명시한 경우에는 같은 prefixed environment source 자체를 effective config에 사용하지 않습니다.

Standard OpenAI, Anthropic과 Gemini Developer API profile의 `base_url=None`은 SDK ambient endpoint 선택에 위임하지 않습니다. Adapter가 각 공식 endpoint를 명시적으로 전달합니다. Google backend를 Developer API로만 고정한 부분은 ADR-0016이 대체하며, 현재 `google-gemini-developer`는 explicit API key와 `enterprise=False`, `google-vertex`는 explicit project/location 및 ADC 또는 service-account strategy와 `enterprise=True`를 사용합니다. Vertex profile `base_url`이 없으면 adapter가 global, `us`/`eu` multi-region, 또는 일반 regional endpoint를 설치 SDK의 endpoint 규칙과 동일하게 `HttpOptions`에 explicit 전달해 `GOOGLE_VERTEX_BASE_URL` inference를 차단하고, profile `base_url`이 있으면 그 값이 우선합니다. OpenAI client의 organization, project, admin key, webhook secret은 explicit empty value로 전달합니다. `OPENAI_CUSTOM_HEADERS`와 `ANTHROPIC_CUSTOM_HEADERS`가 환경에 존재하면 client 생성을 거부하고, 추가 header는 profile만 권한을 갖습니다.

### 5. Tool-call approval과 dispatch authority를 provider SDK에 넘기지 않습니다

Provider adapter는 tool schema를 전달하고 tool-call candidate를 반환하지만 tool을 실행하지 않습니다. Google SDK automatic function calling은 tool이 있는 요청에서 명시적으로 비활성화합니다. Tool candidate의 승인과 dispatch, result/evidence 방출은 [ADR-0013](0013-declarative-agent-loop-ownership.md)에 따라 `AgentRunner`가 소유합니다.

Provider response에 tool call이 있어도 request가 `ToolCallingSpec.tools` catalog로 name/schema를 선언하지 않았다면 권한이 없습니다. Empty catalog와 unknown tool을 거부하고, `ModelToolChoice.NONE`은 call 1개 이상을, `ModelToolChoice.REQUIRED`는 call 0개를 contract violation으로 처리합니다. OpenAI는 call 유무와 `finish_reason=tool_calls`, Anthropic은 call 유무와 `stop_reason=tool_use`가 서로 일치해야 합니다. 모든 provider의 성공 stream은 terminal reason을 가져야 하며 reason 없는 EOF는 partial success가 아닙니다.

`TOOL_CALL_CANDIDATE`를 side-effect authority gate로 취급합니다. Adapter는 terminal/refusal, 전체 tool batch, tool choice와 terminal reason consistency, structured output validation을 모두 마친 뒤에만 candidate를 게시합니다. 한 batch의 call 하나가 invalid하면 앞선 valid call도 candidate로 공개하지 않습니다. OpenAI는 terminal 전 informational `TOOL_CALL_START`/`TOOL_CALL_ARGS_DELTA`를 허용하되 `TOOL_CALL_END`와 candidate는 보류합니다. Anthropic은 모든 tool lifecycle event를, Google은 candidate를 terminal 검증까지 buffer합니다.

Provider가 candidate-only lifecycle을 내면 ADR-0017 runner가 missing neutral START/END만 합성하고 이미 관찰한 frame side는 중복하지 않습니다. 이는 provider authority를 넓히지 않고 AG-UI/A2A에 stable call lifecycle을 제공하는 projection 규칙입니다.

Terminal reason은 provider SDK의 literal type이 아니라 adapter의 explicit allowlist로 판정합니다.

- OpenAI success는 `stop`, `length`, `tool_calls`입니다. `content_filter`와 non-empty message/delta refusal은 model refusal이고, `null`, legacy `function_call`, unknown reason은 malformed response입니다.
- Anthropic success는 `end_turn`, `max_tokens`, `stop_sequence`, `tool_use`, `model_context_window_exceeded`입니다. `refusal` 또는 non-null `stop_details`는 model refusal이고, `null`, `pause_turn`, unknown reason은 malformed response입니다.
- Google success는 `STOP`, `MAX_TOKENS`입니다. `SAFETY`, `RECITATION`, `LANGUAGE`, `BLOCKLIST`, `PROHIBITED_CONTENT`, `SPII`, `IMAGE_SAFETY`, `IMAGE_PROHIBITED_CONTENT`, `NO_IMAGE`, `IMAGE_RECITATION`은 model refusal이고, 그 밖의 unknown/other reason은 malformed response입니다.

현재 설치된 OpenAI·Anthropic SDK는 response model을 loose-construct하여 schema에 없는 future terminal literal도 typed object에 보존할 수 있습니다. 따라서 SDK decode/validation 성공을 terminal success로 간주하지 않고, 새 reason은 의미를 검토해 allowlist에 명시하기 전까지 `LlmResponseError`로 fail closed합니다. Token/context limit 계열 success terminal도 structured output terminal validation을 생략하지 않습니다.

Provider adapter는 assistant tool-call와 TOOL result history를 native SDK message로 복원하는 책임을 유지합니다. Runner가 이 history를 이용해 bounded iterative model/tool loop를 수행하는 현재 의미는 ADR-0017이 정본입니다.

### 6. Structured JSON은 portable schema subset에서 fail closed합니다

Provider가 반환한 structured output과 tool argument는 `LlmJsonCodec`이 검증합니다. Codec은 value를 검사하기 전에 schema shape 전체를 재귀 순회하므로 선택되지 않은 `anyOf` alternative나 value에 사용되지 않은 nested branch에 unsupported validation keyword가 있어도 거부합니다. 알 수 없는 schema type은 허용하지 않고, `anyOf`가 일치해도 같은 schema object에서 codec이 지원하는 sibling constraint를 계속 적용합니다. `prefixItems`가 선언된 array는 나머지 tail을 `items`로 검사하며 `items: false`이면 추가 tail을 거부합니다.

JSON text와 SDK object의 non-finite number는 거부합니다. Enum equality는 boolean과 number를 구분하고 nested JSON에 재귀 적용하되 JSON number인 integer와 같은 값의 float는 동일하게 취급합니다. Structured stream은 provider finish reason이 truncation이어도 terminal에 누적된 JSON을 항상 decode·validate하여 partial structured value를 게시하지 않습니다. 지원하지 않거나 malformed인 schema를 느슨하게 통과시키지 않습니다.

## 대안 (Alternatives)

### 대안 A: raw `httpx` client를 확장합니다

직접 HTTP를 사용하면 dependency 수와 SDK별 client 차이를 줄일 수 있습니다. 반면 provider별 인증, retry, timeout, SSE/event parsing, typed response 변화와 protocol error를 framework가 모두 추적해야 합니다. OpenAI-compatible dialect와 native Anthropic/Google API의 차이도 결국 하나의 큰 조건 분기로 모이므로 채택하지 않았습니다.

### 대안 B: LangChain과 provider integration package를 사용합니다

LangChain은 provider별 integration package와 공통 model interface를 제공하므로 지원 provider를 빠르게 늘리기 쉽습니다. 그러나 Spakky의 `IAgentModel`, message/tool/schema/event 계약 위에 LangChain contract를 다시 mapping해야 하고, provider integration과 transitive dependency가 Agent core architecture의 두 번째 정본이 됩니다. Official SDK adapter를 직접 두는 것보다 책임이 줄지 않아 채택하지 않았습니다.

### 대안 C: Pydantic AI의 Model API를 사용합니다

Pydantic AI의 Model/Provider/Profile 분리와 provider normalization은 목표에 잘 맞습니다. 하지만 Spakky는 이미 Agent loop, model request/response, tool, structured output, stream event를 정의합니다. Pydantic AI를 runtime foundation으로 사용하면 이 계약들이 중복되고 Pydantic AI API 변화가 Spakky public contract까지 전파됩니다. 구조적 경계는 참고하되 dependency는 추가하지 않기로 했습니다.

### 대안 D: Provider마다 별도 Spakky plugin을 만듭니다

`spakky-openai`, `spakky-anthropic`, `spakky-google`로 나누면 deployment별 dependency를 최소화할 수 있습니다. 반면 여러 provider를 사용하는 app에서 `IAgentModel` binding과 request별 routing authority가 분산되고 package/문서 surface가 늘어납니다. 현재 범위에서는 하나의 `spakky-llm` router 아래 provider adapter를 모으는 편이 core selection contract와 더 잘 맞습니다.

## 결과 (Consequences)

### 긍정적

- vLLM을 계속 local 기본 profile로 사용할 수 있으면서 package 책임은 특정 server에 고정되지 않습니다.
- Provider SDK가 HTTP lifecycle과 typed API surface를 담당하고 Spakky adapter는 semantic normalization에 집중합니다.
- 하나의 allowlisted router가 request별 opaque `model_ref` 선택과 route capability 조회를 일관되게 처리합니다.
- Connection authority와 tool-call 승인·dispatch authority가 외부 request 및 provider SDK로 새지 않습니다.
- SDK ambient endpoint, connection metadata, custom header가 operator-owned profile을 우회하지 못합니다.
- Provider client와 structured JSON validation이 성공·실패 모두에서 fail-closed lifecycle을 유지합니다.
- Google async transport 구현은 httpx로 결정적이며 SDK default backend 선택에 따라 error taxonomy가 달라지지 않습니다.
- Tool batch가 atomic validation을 통과하기 전에는 Agent side-effect authority가 열리지 않습니다.
- SDK가 unknown terminal literal을 보존해도 명시적 allowlist 밖의 reason은 성공으로 승격되지 않습니다.

### 부정적

- Package 설치 시 OpenAI, Anthropic, Google SDK를 모두 의존성으로 가져옵니다.
- Provider SDK API와 provider response 차이를 각 adapter가 계속 추적해야 합니다.
- Profile의 API family와 dialect, model route의 capability를 operator가 정확히 선언해야 합니다.
- Portable JSON Schema subset 밖의 schema는 provider가 수용하더라도 Spakky validation에서 거부될 수 있습니다.
- Google SDK의 `HttpOptions.async_client_args` transport injection contract를 추적해야 합니다.
- Stream tool event 일부가 terminal validation까지 buffer되므로 즉시 event forwarding보다 지연과 메모리 사용이 늘어날 수 있습니다.
- Provider가 새 success terminal reason을 추가하면 adapter allowlist와 regression test를 함께 갱신해야 합니다.
- Alias가 없으므로 기존 `spakky-vllm`, `spakky.plugins.vllm`, `SPAKKY_VLLM__*` 사용자는 한 번에 새 이름으로 변경해야 합니다.

### 중립적

- ADR-0009의 Agentic Hexagonal Architecture 전체는 계속 Accepted입니다. 그중 `plugins/spakky-vllm` package와 vLLM 전용 adapter로 한정한 결정만 이 ADR이 대체합니다.
- vLLM in-process Python engine은 여전히 범위 밖이며 OpenAI-compatible server로 연결합니다.
- 새로운 provider API family는 `ILLMProvider` 구현과 `LlmProviderApi` entry를 추가해 확장합니다.
- Profile/provider/raw-model caller selection, profile-owned model/capability와 Developer-API-only Google backend는 ADR-0016이 대체합니다.

## 참고 자료

- [ADR-0009: Agentic Hexagonal Architecture](0009-agentic-hexagonal-architecture.md)
- [ADR-0013: 선언형 Agent loop ownership](0013-declarative-agent-loop-ownership.md)
- [ADR-0016: Operator-owned model catalog와 opaque model routing](0016-operator-owned-model-catalog.md)
- [ADR-0017: Bounded iterative model/tool loop](0017-bounded-iterative-agent-loop.md)
- [`spakky-llm` API](../api/plugins/spakky-llm.md)
