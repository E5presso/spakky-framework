# spakky-llm

> `spakky-llm`은 `spakky-agent`의 `IAgentModel`을 OpenAI Chat Completions,
> Anthropic Messages, Google GenerateContent API에 연결하는 다중 provider 플러그인입니다.

애플리케이션은 provider 연결 정보를 요청 metadata로 넘기지 않고 운영자가 등록한
`LlmProfile` allowlist에서 profile을 선택합니다. 기본 profile은 공식 OpenAI Python
SDK가 `http://127.0.0.1:8000/v1`의 로컬 vLLM OpenAI-compatible API를 호출하도록
구성됩니다.

## 설치와 로드

```bash
pip install spakky-llm
```

```python
import spakky.agent
import spakky.plugins.llm
from spakky.agent import IAgentModel
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext

app = (
    SpakkyApplication(ApplicationContext())
    .load_plugins(
        include={
            spakky.agent.PLUGIN_NAME,
            spakky.plugins.llm.PLUGIN_NAME,
        }
    )
    .start()
)
model = app.container.get(type_=IAgentModel)
```

플러그인은 `LlmConfig`, `OpenAIChatProvider`, `AnthropicMessagesProvider`,
`GoogleGenerateContentProvider`, `LlmAgentModel`을 등록하고
`IAgentModel -> LlmAgentModel` binding을 설정합니다. Adapter가 도구를 실행하지는
않습니다. 모델이 낸 `ModelToolCall` 후보를 검증해 반환하고, `spakky-agent` runner가
한 provider stream 안에서 candidate를 승인·dispatch한 뒤 result/evidence/terminal을
방출합니다. 표준 runner는 tool result를 model에 재주입하거나 같은 invocation에서
model을 다시 호출하지 않습니다.

## Profile 설정 { #llm-profile-configuration }

`LlmConfig`는 `SPAKKY_LLM__` 접두사와 `__` 중첩 구분자를 사용합니다.
`default_profile`은 trim 이후 비어 있을 수 없고 반드시 `profiles`에 존재해야 합니다.
Profile 이름도 trim 이후 비어 있거나 중복될 수 없으며 profile 목록은 하나 이상이어야
합니다. `LlmConfig`와 `LlmProfile` 모두 알 수 없는 필드를 `extra="forbid"`로
거부하므로 연결 설정 오타가 SDK 기본 host로 우회되지 않습니다.

### `LlmConfig`

| 필드 | 타입 | 기본값 | 의미 |
| --- | --- | --- | --- |
| `default_profile` | `str` | `"default"` | 요청이 profile을 지정하지 않을 때 쓸 allowlist key |
| `profiles` | `dict[str, LlmProfile]` | 로컬 vLLM profile | 운영자가 허용한 provider 연결 목록 |

기본 `default` profile은 `provider="vllm"`,
`api="openai-chat-completions"`, `model="default"`,
`base_url="http://127.0.0.1:8000/v1"`, `api_key="EMPTY"`,
`openai_dialect="vllm"`입니다.

### `LlmProfile`

| 필드 | 타입 | 기본값 | 의미 |
| --- | --- | --- | --- |
| `provider` | `str` | 필수 | `ModelSelection.provider`와 대조할 운영자 소유 식별자 |
| `api` | `LlmProviderApi` | 필수 | 사용할 공식 SDK API family |
| `model` | `str` | 필수 | profile의 기본 model id |
| `base_url` | `str \| None` | `None` | SDK endpoint override |
| `api_key` | `SecretStr \| None` | `None` | SDK client 생성 경계에서만 꺼내는 secret |
| `headers` | `dict[str, str]` | `{}` | SDK client의 default headers |
| `request_timeout_seconds` | `float` | `30.0` | non-streaming 요청 timeout, `0`보다 커야 함 |
| `stream_timeout_seconds` | `float` | `300.0` | streaming 요청 timeout, `0`보다 커야 함 |
| `max_retries` | `int` | `0` | 공식 SDK retry 횟수, 음수 불가 |
| `stream_enabled` | `bool` | `true` | 해당 profile의 streaming 허용 여부 |
| `context_window_tokens` | `int \| None` | `None` | `ModelCapability`로 노출할 context window |
| `supports_reasoning` | `bool` | `false` | reasoning channel 지원 선언 |
| `supports_token_counting` | `bool` | `false` | 호출 전 token counting 지원 선언 |
| `openai_dialect` | `OpenAICompatibleDialect` | `"standard"` | OpenAI 표준 또는 vLLM extension 선택 |
| `chat_template_kwargs` | `dict[str, LlmScalar]` | `{}` | vLLM `chat_template_kwargs`; 문자열 boolean은 정규화 |
| `include_thoughts` | `bool` | `false` | Google thinking part를 reasoning event로 포함 |
| `anthropic_max_tokens` | `int` | `4096` | Anthropic 요청의 기본 `max_tokens` |

`openai_dialect="vllm"`과 `chat_template_kwargs`는
`api="openai-chat-completions"`에서만 사용할 수 있습니다.
`chat_template_kwargs`는 vLLM dialect에서만 허용됩니다. `include_thoughts=true`는
`api="google-generate-content"`이면서 `supports_reasoning=true`인 profile에서만
유효합니다. `anthropic_max_tokens`를 명시하는 경우 API는
`anthropic-messages`여야 합니다. `provider`, `model`, non-null `base_url`은 trim되고
빈 문자열이면 거부됩니다.

### 연결 설정의 fail-closed 경계 { #llm-connection-boundary }

`SPAKKY_LLM__`로 시작하지만 `default_profile`이나 `profiles`가 아닌 top-level
환경변수는 `LlmConfig` 생성 시 거부됩니다. 따라서
`SPAKKY_LLM__PROFILSE__...` 같은 오타가 기본 연결로 조용히 우회하지 않습니다.
Profile 내부의 알 수 없는 필드도 `extra="forbid"` 검증에 실패합니다.

Standard API profile에서 `base_url=None`이면 adapter가 아래 공식 endpoint를 SDK에
명시적으로 전달합니다. `OPENAI_BASE_URL`과 `ANTHROPIC_BASE_URL` 같은 SDK ambient
환경변수는 이 선택을 바꾸지 못하며, `GOOGLE_GENAI_USE_VERTEXAI`도 Google profile을
Vertex AI로 전환하지 못합니다.

| API family | `base_url=None`일 때 endpoint | 추가 경계 |
| --- | --- | --- |
| OpenAI Chat Completions | `https://api.openai.com/v1` | standard dialect에만 적용; vLLM은 명시 `base_url` 필수 |
| Anthropic Messages | `https://api.anthropic.com` | profile API key 필수 |
| Google GenerateContent | `https://generativelanguage.googleapis.com/` | `vertexai=False`로 Developer API 사용 |

Operator가 추가하는 custom header의 유일한 입력은 `LlmProfile.headers`입니다.
`OPENAI_CUSTOM_HEADERS`나 `ANTHROPIC_CUSTOM_HEADERS`가 process 환경에 존재하면 해당
adapter는 ambient header를 섞지 않고 `LlmConfigurationError`로 거부합니다. 요청의
`ModelSelection.metadata`도 endpoint, credential, header 설정에는 사용되지 않습니다.

## 중첩 환경 변수 예시

다음은 OpenAI 표준 API를 기본 profile로 등록하는 예입니다. 중첩 변수로
`profiles`를 제공하면 기본 factory profile을 대체하므로 `DEFAULT_PROFILE`도 같은
allowlist key를 가리켜야 합니다.

```bash
export SPAKKY_LLM__DEFAULT_PROFILE=openai
export SPAKKY_LLM__PROFILES__OPENAI__PROVIDER=openai
export SPAKKY_LLM__PROFILES__OPENAI__API=openai-chat-completions
export SPAKKY_LLM__PROFILES__OPENAI__MODEL=gpt-5.5
export SPAKKY_LLM__PROFILES__OPENAI__API_KEY="$OPENAI_API_KEY"
export SPAKKY_LLM__PROFILES__OPENAI__MAX_RETRIES=2
```

Anthropic Messages profile은 API family와 `anthropic_max_tokens`를 함께 지정합니다.

```bash
export SPAKKY_LLM__DEFAULT_PROFILE=claude
export SPAKKY_LLM__PROFILES__CLAUDE__PROVIDER=anthropic
export SPAKKY_LLM__PROFILES__CLAUDE__API=anthropic-messages
export SPAKKY_LLM__PROFILES__CLAUDE__MODEL=claude-opus-4-1
export SPAKKY_LLM__PROFILES__CLAUDE__API_KEY="$ANTHROPIC_API_KEY"
export SPAKKY_LLM__PROFILES__CLAUDE__ANTHROPIC_MAX_TOKENS=4096
```

Google GenerateContent에서 thought stream을 쓰려면 두 capability flag를 함께
설정합니다.

```bash
export SPAKKY_LLM__DEFAULT_PROFILE=gemini
export SPAKKY_LLM__PROFILES__GEMINI__PROVIDER=google
export SPAKKY_LLM__PROFILES__GEMINI__API=google-generate-content
export SPAKKY_LLM__PROFILES__GEMINI__MODEL=gemini-2.5-pro
export SPAKKY_LLM__PROFILES__GEMINI__API_KEY="$GOOGLE_API_KEY"
export SPAKKY_LLM__PROFILES__GEMINI__SUPPORTS_REASONING=true
export SPAKKY_LLM__PROFILES__GEMINI__INCLUDE_THOUGHTS=true
```

로컬 vLLM의 model과 chat template만 바꾸는 경우에도 완전한 profile을 등록합니다.

```bash
export SPAKKY_LLM__DEFAULT_PROFILE=local
export SPAKKY_LLM__PROFILES__LOCAL__PROVIDER=vllm
export SPAKKY_LLM__PROFILES__LOCAL__API=openai-chat-completions
export SPAKKY_LLM__PROFILES__LOCAL__MODEL=Qwen/Qwen3-8B
export SPAKKY_LLM__PROFILES__LOCAL__BASE_URL=http://127.0.0.1:8000/v1
export SPAKKY_LLM__PROFILES__LOCAL__API_KEY=EMPTY
export SPAKKY_LLM__PROFILES__LOCAL__OPENAI_DIALECT=vllm
export SPAKKY_LLM__PROFILES__LOCAL__CHAT_TEMPLATE_KWARGS__ENABLE_THINKING=false
```

## 요청별 모델 선택

`ModelSelection`은 profile, provider, model만 고릅니다. `metadata`에 `base_url`,
API key, headers를 넣어도 `LlmAgentModel`은 연결 설정으로 사용하지 않습니다.

```python
from spakky.agent import ModelSelection, RunAgentInput

run_input = RunAgentInput(
    state_id="run-42",
    instruction="변경 사항을 요약해 주세요.",
    model_selection=ModelSelection(
        profile="claude",
        provider="anthropic",
        model="claude-opus-4-1",
    ),
)
```

`profile`이 있으면 정확한 allowlist entry를 선택합니다. `profile` 없이
`provider`만 주면 그 provider 이름을 가진 profile이 정확히 하나일 때만 선택됩니다.
`provider`가 선택된 profile의 값과 다르거나 profile이 없거나 모호하면
`LlmModelSelectionError`입니다. `model`은 선택한 profile의 연결 정보를 유지한 채
요청 model id만 덮어씁니다.

## Provider 경계와 기능

| API family | 공식 SDK adapter | dialect 또는 특징 |
| --- | --- | --- |
| `openai-chat-completions` | `AsyncOpenAI` | OpenAI standard와 vLLM extension |
| `anthropic-messages` | `AsyncAnthropic` | native Messages, tool-use block, JSON output format |
| `google-generate-content` | `google.genai.Client` | native GenerateContent, function calling, thinking part |

공식 SDK가 인증, retry, typed response, provider stream parsing을 소유합니다. Spakky는
`ModelRequest` mapping, `ModelResponse`와 `ModelStreamEvent` 정규화, portable JSON
Schema 검증, 오류 분류를 소유합니다. 이 패키지는 raw HTTP request나 SSE parser를
`httpx`로 만들지 않습니다. `httpx` 직접 사용 범위는 Google 공식 SDK에 async
transport를 주입하고, 그 transport가 노출하는 configuration/timeout/transport 예외를
공통 LLM error로 정규화하는 경계로 제한됩니다.

세 adapter 모두 complete/stream, portable sampling, function tools,
structured JSON output, usage mapping을 지원합니다. `supports_reasoning`은 provider가
반환한 reasoning channel의 노출을 선언하는 capability이며 모든 SDK에 reasoning 요청을
켜는 공통 switch가 아닙니다. vLLM dialect만
`chat_template_kwargs`와 `structured_outputs.json`을 `extra_body`에 추가하며,
OpenAI standard에는 표준 `response_format`만 사용합니다.

| API family | complete / stream | tools | structured output |
| --- | --- | --- | --- |
| OpenAI Chat Completions | 지원 / 지원 | function tool과 choice; stream delta framing | 표준 `response_format`; vLLM은 `structured_outputs.json`도 추가 |
| Anthropic Messages | 지원 / 지원 | native tool-use block과 choice; stream delta framing | native JSON output format |
| Google GenerateContent | 지원 / 지원 | native function declaration과 choice; stream candidate | `response_json_schema`와 JSON MIME type |

| API family | reasoning | usage | stream tool event |
| --- | --- | --- | --- |
| OpenAI Chat Completions | capability가 켜지면 complete metadata와 stream delta | complete 및 요청 시 stream terminal usage | start, args delta, end, candidate |
| Anthropic Messages | 반환된 thinking event를 capability가 켜진 경우에만 stream delta로 전달 | complete 및 요청 시 final-message usage | start, args delta, end, candidate |
| Google GenerateContent | `include_thoughts`가 켜지면 thought stream delta | complete 및 요청 시 chunk usage | 완성된 candidate |

Google adapter는 SDK의 automatic function calling을 명시적으로 끕니다. 따라서
세 adapter 모두 tool을 실행하지 않고 검증된 후보만 runner에 전달합니다.

Anthropic adapter는 `messages.create()`나 `messages.stream()`에 SDK `thinking` 요청
파라미터를 보내지 않습니다. Provider stream에 `thinking` event가 들어온 경우에만
`supports_reasoning=true`인 profile에서 `REASONING_DELTA`로 통과시키며,
non-streaming response의 thinking/redacted-thinking block은 visible content에 포함하지
않습니다. Google의 `include_thoughts=true`는 이와 달리 SDK
`ThinkingConfig(include_thoughts=True)`를 전송합니다.

### Tool 호출 권한과 원자적 stream 경계

`ModelRequest.tool_calling`의 tool catalog가 provider tool call의 유일한 권한
목록입니다. 요청에 catalog가 없거나 `choice=NONE`인데 provider가 tool call을
반환하면 `LlmResponseError`입니다. 반환된 tool 이름이 `ToolCallingSpec.tools`에 없거나
arguments가 그 tool의 portable JSON Schema를 통과하지 못해도 같은 오류로
거부합니다. `choice=REQUIRED`는 terminal response에 하나 이상의 유효한 tool call을
요구합니다. `AUTO`는 catalog 안에서 0개 이상을 허용하고, `NONE`이나 catalog가 없는
요청은 0개만 허용합니다. Native SDK에 전달한 `tool_choice`만 신뢰하지 않고 adapter가
response를 다시 검증합니다.

| API family | terminal reason과 tool batch의 일관성 |
| --- | --- |
| OpenAI Chat Completions | tool call 존재 여부와 `finish_reason="tool_calls"` 여부가 정확히 같아야 함 |
| Anthropic Messages | tool call 존재 여부와 `stop_reason="tool_use"` 여부가 정확히 같아야 함 |
| Google GenerateContent | 허용된 terminal finish reason을 먼저 확인한 뒤 catalog/schema와 `NONE`/`REQUIRED`를 검증 |

Streaming에서는 text/reasoning delta와 provider별 tool framing event가 먼저 보일 수
있습니다. 특히 OpenAI는 `TOOL_CALL_START`와 `TOOL_CALL_ARGS_DELTA`를 terminal보다 먼저
내보낼 수 있지만, 이 event들은 tool 실행 권한이 아닙니다. 세 adapter 모두
`TOOL_CALL_CANDIDATE`는 다음 검증이 전부 끝날 때까지 보류합니다.

- terminal reason이 존재하고 허용된 값인지 확인합니다. OpenAI와 Anthropic은 위
  표의 reason-tool 일관성도 확인합니다.
- 전체 tool batch의 이름, arguments, catalog 등록 여부를 검증하고
  `NONE`/`REQUIRED` 제약을 확인합니다.
- Structured output 요청이 있으면 누적된 terminal JSON의 decode와 schema 검증까지
  완료합니다.

모든 검증을 통과한 뒤에만 이미 전체가 검증된 batch의 candidate event를 순서대로
방출합니다. 따라서 side effect 권한은 candidate 경계에서 검증 전 0개, 검증 후
유효한 batch로 열립니다. 앞선 token이나 framing delta가 있었더라도 terminal 검증이
실패하면 candidate는 하나도 방출되지 않습니다. 표준 `AgentRunner`는 이 candidate를
승인·dispatch하지만 tool result를 같은 invocation의 model에 재주입하거나 model을
다시 호출하지 않는 single-pass 실행이라는 제한은 그대로입니다.

### OpenAI와 Anthropic terminal reason

OpenAI와 Anthropic SDK의 response type이 표현할 수 있는 terminal 값 전체를 성공으로
간주하지 않습니다. Adapter가 아래 allowlist와 refusal 조건을 complete와 stream에
동일하게 적용하고, nullable·legacy·미인식 terminal 값은 fail closed합니다.

| API family | 성공 allowlist | 모델 거부 | `LlmResponseError` |
| --- | --- | --- | --- |
| OpenAI Chat Completions | `stop`, `length`, `tool_calls` | `content_filter` 또는 non-empty refusal field | terminal `null`, legacy `function_call`, 그 밖의 미인식 값 |
| Anthropic Messages | `end_turn`, `max_tokens`, `stop_sequence`, `tool_use`, `model_context_window_exceeded` | `refusal` 또는 non-null `stop_details` | terminal `null`, `pause_turn`, 그 밖의 미인식 값 |

성공 allowlist를 통과한 뒤에도 앞 절의 reason-tool 일관성, tool batch, structured
output 검증이 이어집니다. 따라서 SDK가 HTTP 200 payload를 loose terminal 값으로
decode했더라도 이 표의 성공 조건과 후속 검증을 모두 통과하기 전에는 candidate나
terminal success를 방출하지 않습니다.

### Google finish reason과 thought opt-in

Google adapter는 typed candidate의 terminal finish reason을 명시적인 allowlist로
분류합니다. HTTP 성공이나 candidate 존재만으로 성공 처리하지 않습니다.

| 분류 | Google finish reason 또는 조건 | 결과 |
| --- | --- | --- |
| 성공 | `STOP`, `MAX_TOKENS` | terminal reason 수용 후 tool/structured output 검증 계속 |
| 모델 거부 | `SAFETY`, `RECITATION`, `LANGUAGE`, `BLOCKLIST`, `PROHIBITED_CONTENT`, `SPII`, `IMAGE_SAFETY`, `IMAGE_PROHIBITED_CONTENT`, `NO_IMAGE`, `IMAGE_RECITATION`, prompt feedback block | `LlmModelRefusalError` |
| 잘못된 response | reason 누락·미지정, `OTHER`, `IMAGE_OTHER`, `MALFORMED_FUNCTION_CALL`, `UNEXPECTED_TOOL_CALL`, 그 밖의 미인식 값 | `LlmResponseError` |

`MAX_TOKENS`는 terminal reason 분류만 통과시킵니다. Structured output JSON이 잘려
decode 또는 schema 검증에 실패하면 최종 결과는 여전히 `LlmResponseError`이고
`STRUCTURED_OUTPUT`이나 tool candidate를 방출하지 않습니다.

`include_thoughts`의 기본값은 `false`이며 이때 Google 요청에 `thinking_config`를
보내지 않습니다. `supports_reasoning=true`인 Google profile에서
`include_thoughts=true`를 함께 설정한 경우에만
`ThinkingConfig(include_thoughts=True)`를 보내고 반환된 thought part를
`REASONING_DELTA`로 노출합니다. Automatic function calling은 이 설정과 무관하게
항상 꺼져 있으며 adapter가 tool을 직접 실행하지 않습니다.

### SDK success payload와 OpenAI usage opt-out

세 공식 SDK가 HTTP 200을 반환해도 payload가 typed response 계약을 충족하지 않으면
semantic success로 취급하지 않습니다. SDK decode/mapping 실패뿐 아니라 adapter가
요구하는 candidate, terminal reason, content shape가 빠진 경우도
`LlmResponseError`로 정규화합니다.

| SDK adapter | 잘못된 success payload의 예 |
| --- | --- |
| OpenAI | `APIResponseValidationError`, JSON/typed mapping 실패, choice 누락, null·legacy·unknown terminal reason |
| Anthropic | `APIResponseValidationError`, JSON/content block mapping 실패, null·`pause_turn`·unknown `stop_reason` |
| Google | `UnknownApiResponseError`, JSON/typed model decode 실패, candidate 누락, missing·other·malformed finish reason |

OpenAI stream에서 `StreamingOptions(include_usage=False)`를 선택하면 adapter는 SDK
method에 `omit` sentinel을 전달해 serialized 요청의 `stream_options`를 생략하고,
response에 usage chunk가 들어와도 사용하지 않습니다. 따라서 terminal `DONE`에도
usage를 싣지 않습니다. `include_usage=True`일 때만
`stream_options={"include_usage": True}`를 보내고 terminal usage를 매핑합니다.

### Google async transport와 오류 경계

`spakky-llm`은 `google-genai>=2.19.0`을 사용하며 현재 lock과 검증 runtime은
2.19.0입니다. 이 runtime에서 환경에 따라 선택될 수 있는 aiohttp async backend의
예외가 provider-neutral 경계 밖으로 노출되지 않도록,
`types.HttpOptions.async_client_args`에 `httpx.AsyncHTTPTransport`를 명시합니다.
`google.genai.Client`가 이 transport로 request, retry, typed response와 stream parsing을
계속 소유하며 Spakky가 raw request나 SSE parsing을 수행하는 것은 아닙니다.

Complete와 stream setup/iteration은 같은 오류 경계를 사용합니다.

| SDK/transport 실패 | 공통 오류 | 의미 |
| --- | --- | --- |
| `httpx.InvalidURL`, `httpx.UnsupportedProtocol` | `LlmConfigurationError` | allowlisted endpoint 형식 또는 protocol 오류 |
| `httpx.TimeoutException`, Google API 408/504 | `LlmTimeoutError` | 요청 또는 stream timeout |
| `httpx.TransportError`, Google API 429 또는 5xx(504 제외) | `LlmTransportError` | 연결 또는 재시도 가능한 provider 실패 |
| 그 밖의 Google API 오류 | `LlmResponseError` | provider가 요청이나 response를 수용하지 못함 |

### Portable JSON Schema 검증

Tool argument와 structured output은 provider가 JSON을 생성한 뒤에도
`LlmJsonCodec`의 portable subset으로 다시 검증됩니다. 전체 JSON Schema 구현을
표방하지 않으며, 지원하지 않거나 모호한 shape는 `LlmResponseError`로 fail closed합니다.

- 지원 keyword allowlist에 없는 validation keyword와 알려지지 않은 `type`은 허용하지
  않습니다. Schema shape를 value보다 먼저 재귀 검증하므로 실제 value에 사용되지 않은
  `properties`, `anyOf`, `prefixItems`, `additionalProperties` 내부의 unsupported
  keyword도 거부합니다.
- `anyOf` alternative 하나가 맞더라도 같은 schema의 `type`이나 `enum` sibling 조건을
  계속 검증합니다.
- `prefixItems`는 tuple prefix를 검증하고, 남은 tail은 `items` schema로 검증합니다.
- `items: false`이면 `prefixItems` 뒤의 tail을 허용하지 않습니다. `prefixItems`가
  없으면 array element 자체를 허용하지 않습니다.
- JSON text나 SDK value의 `NaN`, `Infinity`, `-Infinity`는 유효한 portable JSON
  number로 취급하지 않습니다.
- `enum` 비교는 JSON type을 보존합니다. 예를 들어 `true`와 `1`은 다르지만 JSON
  number인 `1`과 `1.0`은 같으며, nested object와 array도 같은 규칙으로 비교합니다.

Structured stream은 provider가 보고한 finish reason이 truncation이어도 누적한 terminal
JSON을 decode하고 schema 검증합니다. 따라서 앞선 `TOKEN_DELTA`가 이미 방출됐더라도
유효한 전체 JSON이 아니면 `STRUCTURED_OUTPUT` event를 내지 않고
`LlmResponseError`로 종료합니다.

## Tool history

이전 tool turn을 직접 `ModelMessage`로 조립한다면 `TOOL` message metadata에는
`call_id`와 `tool_name`을 넣습니다. 앞선 `ASSISTANT` message metadata의
`tool_calls`는 `id`, `name`, `arguments`를 가진 entry 목록입니다.

```python
from spakky.agent import ModelMessage, ModelMessageRole

history = (
    ModelMessage(
        role=ModelMessageRole.ASSISTANT,
        content="",
        metadata={
            "tool_calls": (
                {
                    "id": "call-1",
                    "name": "lookup_weather",
                    "arguments": {"city": "Seoul"},
                },
            )
        },
    ),
    ModelMessage(
        role=ModelMessageRole.TOOL,
        content='{"temperature": 23}',
        metadata={"call_id": "call-1", "tool_name": "lookup_weather"},
    ),
)
```

Gemini가 `thought_signature`를 반환한 tool-call turn은 다음 요청에서 그 signature도
함께 재생해야 할 수 있습니다. Google adapter는 event/tool-call metadata에 제공된
signature를 보존하고 assistant history의 top-level 또는 각 `tool_calls` entry에서
읽지만, provider-neutral text transcript만으로는 이 provider 전용 값이 복원되지
않습니다.

## Streaming과 오류

Streaming adapter는 provider SDK stream을 순회해 text, reasoning, tool-call start,
argument delta, tool candidate, structured output, usage, terminal event를
`ModelStreamEvent`로 변환합니다. Router 단계에서 생긴 `AbstractLlmError`는
`ERROR` 뒤 `DONE`으로 끝나는 public stream으로 정규화됩니다. Non-streaming
`complete()`는 typed `AbstractLlmError`를 호출자에게 그대로 전달합니다.

에러별 stream code는 [에러 계층 구조](../../error-hierarchy.md#spakky-llm-errors)에서
확인할 수 있습니다.

## 함께 보기

- [AI Agent 개발](../../guides/agents.md): single-pass runner와 custom `execute()` 경계를 확인합니다.
- [AI Agent 심화](../../guides/agents-advanced.md): tool dispatch, approval, evidence 흐름을 확인합니다.
- [IAgentModel 용어](../../glossary.md#iagentmodel): core outbound port와 provider plugin 관계를 확인합니다.

## 공개 package

Root package는 플러그인 발견에 필요한 `PLUGIN_NAME`만 공개합니다. 구현 타입을
root alias로 재노출하지 않으므로 아래 실제 모듈에서 import합니다.

::: spakky.plugins.llm

## 설정과 라우터

::: spakky.plugins.llm.config
    options:
      show_root_heading: false

::: spakky.plugins.llm.model
    options:
      show_root_heading: false

::: spakky.plugins.llm.provider
    options:
      show_root_heading: false

## 오류와 상수

::: spakky.plugins.llm.error
    options:
      show_root_heading: false

::: spakky.plugins.llm.constants
    options:
      show_root_heading: false

## Provider adapter

::: spakky.plugins.llm.providers.openai
    options:
      show_root_heading: false

::: spakky.plugins.llm.providers.anthropic
    options:
      show_root_heading: false

::: spakky.plugins.llm.providers.google
    options:
      show_root_heading: false

## Plugin entry point

::: spakky.plugins.llm.main
    options:
      show_root_heading: false
