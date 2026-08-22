---
title: "ADR-0016: Operator-owned model catalog와 opaque model routing"
date: '2026-08-22'
status: accepted
---

# ADR-0016: Operator-owned model catalog와 opaque model routing

> 호출자는 제품 의미의 `model_ref`만 선택하고, operator가 profile과 model catalog로 실제 provider topology를 소유합니다.
> Spring Boot식 externalized configuration과 교체 가능한 port를 따르되, 모호한 자동 추론은 하지 않고 누락·중복·미등록 선택을 시작 또는 요청 경계에서 fail closed합니다.

## 맥락 (Context)

[ADR-0015](0015-multi-provider-llm-official-sdk-adapters.md)는 `spakky-llm`과 provider 공식 SDK adapter를 도입했지만, 초기 선택 계약은 caller가 profile/provider/raw model id를 직접 지정할 수 있게 했습니다. 이 방식에서는 배포 topology와 provider model 이름이 application·AG-UI·A2A 요청에 노출됩니다. Operator가 endpoint를 옮기거나 provider model을 교체하면 caller 계약도 함께 바뀌고, catalog 밖 raw model id가 allowlisted 연결 안에서 실행될 수 있었습니다.

Profile도 model 기본값과 capability를 함께 소유해 연결 수명과 model 특성이 결합되어 있었습니다. 같은 endpoint에서 서로 다른 context window·reasoning·tool·modality 특성을 가진 여러 모델을 노출하거나, 같은 논리 모델을 다른 provider로 재배치하기 어려운 구조였습니다.

Google Gen AI SDK는 같은 GenerateContent surface에서 Gemini Developer API와 Vertex AI를 지원하지만 인증과 deployment 좌표가 다릅니다. 여기서 **Gemini Developer API는 Google의 제품명**이며 개발 환경을 뜻하지 않습니다. 상용 애플리케이션도 명시적으로 선택해 사용할 수 있지만, Vertex AI의 project/location과 ADC (Application Default Credentials) 또는 service-account 인증을 Developer API key와 섞어 추론해서는 안 됩니다. 로컬·CI acceptance test는 상용 credential에 접근하지 않고 injected SDK/credential test double로 mapping contract를 검증하며 live service/IAM access를 증명하지 않습니다.

## 결정 (Decision)

### 1. Profile과 model route를 분리합니다

`LlmConfig`는 다음 세 축을 operator configuration으로 소유합니다.

- `profiles: dict[str, LlmProfile]`: provider id, `LlmProviderApi`, endpoint, credential, header, timeout/retry, stream policy와 backend dialect 같은 **연결·backend·auth** 설정
- `models: dict[str, LlmModelRoute]`: profile 이름, 실제 provider model id, `ModelCapability`, model별 vLLM `chat_template_kwargs`
- `default_model: str`: caller가 selection을 생략했을 때 사용할 logical model ref

`LlmProfile`에는 model id나 capability alias를 두지 않습니다. `LlmModelRoute`에는 endpoint, API key, header 같은 연결 권한을 두지 않습니다. Operator용 profile 이름은 `google-vertex`, `openrouter`, `anthropic`, `vllm-local`처럼 backend 또는 연결 역할을 설명하는 중립 이름을 사용합니다. 환경을 이름에 박은 `*-prod` 관례는 요구하지 않습니다. 배포 환경 차이는 외부 설정 source가 같은 중립 key에 주입하는 값으로 표현합니다.

예를 들어 operator는 다음처럼 topology를 구성할 수 있습니다.

```python
from pydantic import SecretStr
from spakky.agent import ModelCapability
from spakky.plugins.llm.config import (
    GoogleCredentialStrategy,
    LlmConfig,
    LlmModelRoute,
    LlmProfile,
    LlmProviderApi,
    OpenAICompatibleDialect,
)

config = LlmConfig(
    default_model="support/primary",
    profiles={
        "google-vertex": LlmProfile(
            provider="google",
            api=LlmProviderApi.GOOGLE_VERTEX,
            google_credential_strategy=GoogleCredentialStrategy.ADC,
            google_project="project-id",
            google_location="us-central1",
        ),
        "openrouter": LlmProfile(
            provider="openrouter",
            api=LlmProviderApi.OPENAI_CHAT_COMPLETIONS,
            base_url="https://openrouter.ai/api/v1",
            api_key=SecretStr("operator-managed-secret"),
        ),
        "anthropic": LlmProfile(
            provider="anthropic",
            api=LlmProviderApi.ANTHROPIC_MESSAGES,
            api_key=SecretStr("operator-managed-secret"),
        ),
        "vllm-local": LlmProfile(
            provider="vllm",
            api=LlmProviderApi.OPENAI_CHAT_COMPLETIONS,
            base_url="http://127.0.0.1:8000/v1",
            openai_dialect=OpenAICompatibleDialect.VLLM,
        ),
    },
    models={
        "support/primary": LlmModelRoute(
            profile="google-vertex",
            model="publishers/google/models/gemini-2.5-pro",
            capability=ModelCapability(
                supports_tools=True,
                supports_structured_output=True,
            ),
        ),
        "coding/primary": LlmModelRoute(
            profile="openrouter",
            model="moonshotai/kimi-k2",
        ),
        "analysis/primary": LlmModelRoute(
            profile="anthropic",
            model="claude-opus-4-1",
            capability=ModelCapability(supports_reasoning=True),
        ),
        "local/primary": LlmModelRoute(
            profile="vllm-local",
            model="Qwen/Qwen3-8B",
            chat_template_kwargs={"enable_thinking": False},
        ),
    },
)
```

Environment와 dotenv의 `PROFILES`/`MODELS` JSON은 duplicate object key를 nested depth까지 거부합니다. Standard JSON decoder의 last-key-wins 의미를 routing/auth 설정에 허용하지 않습니다. Direct constructor에서 명시한 `default_model`, `profiles`, `models` field는 같은 ambient field를 complex JSON parsing 전에 mask하고, 명시하지 않은 env field만 계속 parsing·validation합니다. 세 field를 모두 직접 제공한 full-explicit 구성은 ambient `SPAKKY_LLM__...` source를 effective config에서 사용하지 않습니다.

### 2. Caller는 opaque `model_ref`만 전달합니다

Core `ModelSelection`은 `model_ref: str` 하나만 갖습니다. Application service, AG-UI, A2A 같은 caller는 다음 논리 선택만 전달합니다.

```python
from spakky.agent import ModelSelection, RunAgentInput

run_input = RunAgentInput(
    state_id="run-1",
    instruction="고객 문의를 분류하고 답변하세요.",
    model_selection=ModelSelection(model_ref="support/primary"),
)
```

Core `ModelSelection`은 whitespace-only 값을 거부하되 nonblank 원문을 그대로 운반합니다. `spakky-llm`의 catalog/routing 경계만 key 전체의 앞뒤 공백을 제거한 뒤 case-sensitive exact lookup을 수행합니다. `/`를 provider와 model 구분자로 해석하거나 분해하지 않습니다. 실제 provider model id에도 `moonshotai/kimi-k2`, `Qwen/Qwen3-8B`, `publishers/google/models/...`처럼 slash가 들어갈 수 있으므로 logical ref와 physical model id는 서로 추론하지 않습니다.

Blank key, 공백 제거 뒤 duplicate key, catalog에 없는 `default_model`, 존재하지 않는 route profile, 알 수 없는 request `model_ref`는 모두 거부합니다. `Support/Primary`와 `support/primary`는 서로 다른 key이며, case folding이나 provider/raw-model fallback을 하지 않습니다. Request metadata는 `base_url`, credential, header, profile 또는 physical model을 바꾸는 routing authority가 아닙니다.

이 경계 덕분에 operator는 `support/primary`가 가리키는 profile이나 physical model을 바꾸면서 caller API를 유지할 수 있습니다. Logical model rename은 공개 제품 계약 변경으로 취급하지만, provider 교체는 operator catalog 변경으로 한정할 수 있습니다.

Catalog membership은 connection/routing allowlist이지 caller authorization이 아닙니다. `model_ref`를 아는 caller별·tenant별 접근 제어는 상위 application/auth policy가 담당해야 합니다. Profile 이름에 `-prod`를 붙이는 것으로 접근 권한이나 환경 격리가 생기지 않습니다.

### 3. Capability는 route별로 선언하고 그대로 조회합니다

`LlmModelRoute.capability`는 `supports_reasoning`, `context_window_tokens`, `supports_token_counting`, `input_modalities`, `output_modalities`, `supports_tools`, `supports_structured_output`을 보존합니다. Context window는 양수여야 하고 input/output modality set은 비어 있을 수 없습니다. 기본 `assistant/default` vLLM route는 text-in/text-out과 tools·structured output support를 선언하고 나머지는 base capability 기본값을 유지합니다.

`LlmAgentModel.capability`는 default route의 값을, `capability_for(ModelSelection(...))`는 선택된 route의 값을 재구성 없이 반환합니다. Google은 `supports_reasoning=true`일 때 thought part를 SDK에 요청합니다. OpenAI-compatible·Anthropic adapter는 provider가 반환한 reasoning/thinking extension의 노출만 이 capability로 gate합니다. Provider adapter의 vLLM model별 extension도 profile-level 추정이 아니라 selected route option을 사용합니다. Capability는 실제 지원을 operator가 선언하는 queryable 계약이며, adapter가 provider 이름으로 임의 추론하지 않습니다. 이 결정만으로 모든 capability에 대한 runner preflight enforcement가 추가되는 것은 아닙니다. 현재 core `ModelMessage.content`가 `str`이므로 non-text content part는 아직 표현하지 못합니다.

### 4. Google backend와 credential source를 명시합니다

`GoogleGenerateContentProvider` 하나가 `google-gemini-developer`와 `google-vertex` API family를 구현하지만, profile은 둘 중 하나를 명시해야 합니다.

| API family | SDK mode | 필수 auth/좌표 | 금지 조합 |
|------------|----------|----------------|-----------|
| `google-gemini-developer` | `enterprise=False` | `google_credential_strategy=api-key`, explicit `api_key` | project, location, service-account file |
| `google-vertex` | `enterprise=True` | explicit project/location와 `adc` 또는 `service-account-file` | API key, 누락·혼합된 strategy/file |

ADC를 선택하면 adapter가 cloud-platform scope로 `google.auth.default()`를 호출합니다. Service account를 선택하면 operator가 지정한 mounted file을 같은 scope로 읽습니다. ADC 자체는 ambient credential chain이지만 **그 chain을 사용한다는 결정은 profile의 explicit strategy**입니다. ADC가 개발자 workstation identity를 발견해도 Vertex project 접근 권한을 새로 만들지는 않으며, 실제 접근은 그 identity의 Google IAM 권한이 결정합니다. ADC가 반환한 ambient project 값도 사용하지 않고 profile의 project/location을 전달합니다. Backend, project/location 또는 credential strategy를 SDK 환경변수나 request metadata에서 추론하지 않습니다.

Gemini Developer API는 base URL을 생략하면 Google의 공식 Developer API endpoint를 명시적으로 사용합니다. Vertex AI는 profile `base_url`이 있으면 이를 우선합니다. 없으면 location `global`을 `https://aiplatform.googleapis.com/`, multi-region `us`와 `eu`를 각각 `https://aiplatform.us.rep.googleapis.com/`와 `https://aiplatform.eu.rep.googleapis.com/`, 그 밖의 lowercase endpoint-safe region을 `https://{location}-aiplatform.googleapis.com/`로 변환해 SDK `HttpOptions.base_url`에 explicit 전달합니다. 따라서 `GOOGLE_VERTEX_BASE_URL` 같은 SDK ambient endpoint 설정이 profile routing을 바꾸지 못합니다. Project/location과 credential도 SDK client에 명시하며 caller가 주입하지 않습니다.

### 5. OpenRouter와 vLLM은 explicit OpenAI-compatible mode입니다

OpenRouter는 우선 별도 provider-specific dialect 없이 `openai-chat-completions` + `openai_dialect=standard`로 연결합니다. Operator는 `provider="openrouter"`, OpenRouter base URL과 credential을 profile에 등록하고, route가 provider model id를 선택합니다. OpenRouter 고유 semantics가 실제로 필요해질 때만 별도 `ILLMProvider` 또는 명시적 dialect를 추가합니다.

vLLM도 같은 OpenAI SDK adapter를 사용하지만 `openai_dialect=vllm`과 explicit `base_url`을 요구합니다. `chat_template_kwargs`와 vLLM structured-output extension은 이 dialect에서만 허용하며, model별 `chat_template_kwargs`는 route에 둡니다. Standard OpenAI-compatible route로 vLLM extension이 새는 구성은 검증 단계에서 거부합니다.

### 6. Provider 구현은 교체 가능하되 자동 resolution은 엄격합니다

`ILLMProvider.apis`는 구현이 담당하는 `LlmProviderApi` 집합이고 `is_default`는 replaceable default 여부입니다. First-party OpenAI, Anthropic, Google adapter는 `is_default=True`이며 custom 구현은 기본 false입니다.

`LlmAgentModel`은 주입된 복수 provider를 API family별 registry로 구성하고 `profile.api`로 구현을 선택합니다. API마다 non-default custom 구현이 정확히 하나면 first-party default와 함께 등록되어 있어도 custom을 선택합니다. Non-default가 둘 이상이면 ambiguity error이고, custom이 없을 때는 default가 정확히 하나여야 합니다. 빈 `apis`와 configured profile API 구현 누락도 bootstrap construction에서 `LlmConfigurationError`로 실패합니다. 한 구현이 여러 family를 명시하는 것은 허용하므로 Google adapter는 Developer API와 Vertex AI를 함께 담당할 수 있습니다. `LlmProfile.provider`는 operator label과 routing evidence일 뿐 registry key가 아닙니다. 이 resolution은 hardcoded class identity, credential 종류, 등록 순서나 provider 이름을 사용하지 않습니다.

### 7. Routing evidence는 고정된 metadata로 남깁니다

Route가 성공적으로 해석되면 first-party adapter의 `ModelResponse`, `ModelStreamEvent`, `ModelToolCall`, normalized `ModelError`는 다음 네 field를 공통 metadata로 보존합니다. 이 범위는 core `AgentEvent` 전체나 AG-UI/A2A wire metadata 전체를 포함하지 않습니다.

| Field | 의미 |
|-------|------|
| `model_ref` | caller가 선택했거나 default로 해석된 logical ref |
| `profile` | operator catalog에서 resolve된 profile key |
| `provider` | profile에 선언된 provider id |
| `model` | provider SDK에 전달한 physical model id |

Terminal event/response는 여기에 `finish_reason`을 추가할 수 있고, provider가 보존하는 `response_id`, `response_model`, reasoning 또는 thought signature 같은 정보도 추가될 수 있습니다. 알 수 없는 `model_ref`는 default route를 사용한 것처럼 꾸미지 않고 요청된 `model_ref`만 error metadata에 남깁니다. Credential과 header 값은 routing evidence에 넣지 않습니다.

## 대안 (Alternatives)

### 대안 A: Caller가 profile/provider/raw model을 계속 선택합니다

한 요청에서 자유롭게 backend를 고를 수 있지만 application contract가 deployment topology와 secret-bearing connection 설정에 가까워집니다. Provider 교체와 model rename이 모든 caller에 전파되고 catalog 밖 raw model을 허용하므로 채택하지 않았습니다. 필요한 선택 폭은 operator가 logical ref를 여러 개 공개하는 방식으로 제공합니다.

### 대안 B: `provider/model` 문자열을 slash로 파싱합니다

문자열 하나로 routing할 수 있어 간단해 보이지만 physical model id 자체에 slash가 사용됩니다. Logical namespace와 provider namespace를 결합하면 OpenRouter·vLLM model id에서 모호성이 생기고 provider 교체도 caller-visible rename이 되므로 채택하지 않았습니다.

### 대안 C: Credential과 backend를 SDK 환경에서 자동 감지합니다

설정량은 줄지만 같은 배포가 환경에 따라 Developer API 또는 Vertex AI로 달라질 수 있고, local credential이 예상하지 못한 cloud project로 요청을 보낼 수 있습니다. Spring Boot식 auto-configuration은 조건이 명확할 때만 편의가 되므로, 이 보안·비용 경계에서는 explicit profile과 fail-closed validation을 선택했습니다.

### 대안 D: Provider별 고정 `IAgentModel` bean을 caller가 직접 주입합니다

단일 provider application에는 단순하지만 agent class가 backend topology를 소유하고 run별 선택, protocol adapter 전달, 공통 routing evidence가 분산됩니다. 하나의 router와 교체 가능한 `ILLMProvider` 집합이 더 작은 public surface로 같은 확장성을 제공하므로 채택하지 않았습니다.

## 결과 (Consequences)

### 긍정적

- Caller DX는 `ModelSelection(model_ref=...)` 하나로 축소되고 credential·endpoint·physical model이 application boundary에서 사라집니다.
- Operator는 caller를 바꾸지 않고 model route를 다른 profile/provider로 이동할 수 있습니다.
- 같은 connection profile 아래 여러 model route와 서로 다른 capability를 선언할 수 있습니다.
- Gemini Developer API, Vertex AI, OpenRouter, Anthropic, vLLM이 하나의 catalog 의미로 구성되면서 backend/auth 차이는 명시적으로 유지됩니다.
- First-party adapter는 generic `is_default` semantics로 교체 가능하며, 복수 API family adapter도 표현할 수 있습니다.
- Missing provider, custom ambiguity와 unknown route가 silent fallback 없이 일찍 실패합니다.

### 부정적

- Operator가 profile과 model catalog 두 map의 참조 정합성을 관리해야 합니다.
- Capability는 provider가 자동 발견하지 않으므로 실제 deployment와 맞게 선언하고 acceptance test로 검증해야 합니다.
- 동일 API family의 non-default custom 구현은 하나만 둘 수 있어 custom 간 priority chain은 지원하지 않습니다.
- Logical ref는 제품 계약이므로 rename에는 caller migration이 필요합니다.

### 중립적

- 기본 설정은 `assistant/default` → `vllm-local` → physical `default` route를 제공하지만, production backend를 자동 등록하거나 commercial credential을 요구하지 않습니다.
- Catalog membership은 caller별 route ACL (Access Control List)을 대신하지 않습니다.
- Provider SDK transport ownership, tool-call approval/dispatch authority, terminal reason allowlist와 portable JSON Schema validation은 ADR-0015 결정을 그대로 유지합니다.
- ADR-0015의 profile/provider/raw-model caller selection, profile-owned model/capability, Developer-API-only Google backend 부분만 이 ADR이 대체합니다.

## 참고 자료

- [ADR-0015: Multi-provider LLM official SDK adapters](0015-multi-provider-llm-official-sdk-adapters.md)
- [`spakky-llm` API](../api/plugins/spakky-llm.md)
- [`spakky-agent` API](../api/core/spakky-agent.md)
