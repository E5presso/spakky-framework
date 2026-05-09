# spakky-vllm

`spakky-vllm`은 `spakky-agent`를 위한 첫 공식 `IAgentModel` 어댑터
패키지입니다. 코어에 모델 SDK 의존성을 넣지 않고, Spakky Agent workflow를
로컬 vLLM OpenAI-compatible HTTP 엔드포인트에 연결합니다.

## 언제 필요한가

애플리케이션이 로컬 vLLM 서버를 대상으로 `@Agent` workflow를 실행하고,
코어 `IAgentModel` 포트를 통해 모델 구현체를 주입해야 할 때 사용합니다.

## 설치

```bash
pip install spakky-vllm
```

durable Agent 실행에는 `spakky-agent`와 `spakky-sqlalchemy[agent]` 같은
persistence provider도 필요합니다. `spakky-vllm`은 모델 어댑터만 제공합니다.
state, signal, evidence repository, inbound HTTP/CLI 어댑터, 운영용 in-memory
persistence fallback은 제공하지 않습니다.

## 설정

설정은 `SPAKKY_VLLM__` 환경변수 접두사를 사용하는 `VllmConfig`로 읽습니다.

| 설정 | 기본값 | 목적 |
|------|--------|------|
| `SPAKKY_VLLM__ENDPOINT_URL` | `http://127.0.0.1:8000/v1` | OpenAI-compatible API 기본 URL |
| `SPAKKY_VLLM__MODEL` | `default` | chat completion 요청에 전달할 model id |
| `SPAKKY_VLLM__REQUEST_TIMEOUT_SECONDS` | `30.0` | 비스트리밍 요청 timeout |
| `SPAKKY_VLLM__STREAM_TIMEOUT_SECONDS` | `300.0` | 스트리밍 요청 timeout |
| `SPAKKY_VLLM__STREAM_ENABLED` | `true` | public streaming surface 활성화 여부 |
| `SPAKKY_VLLM__CHAT_TEMPLATE_KWARGS__ENABLE_THINKING` | 미설정 | vLLM chat template에 전달할 모델별 옵션 예시 |

`chat_template_kwargs`는 vLLM의 모델별 chat template 옵션을 요청 payload에 그대로
전달합니다. 예를 들어 일부 reasoning/thinking 계열 모델은 `enable_thinking=false`
같은 template switch를 지원하며, 짧은 검증 요청에서는 이런 옵션을 통해 응답 토큰 예산을
더 예측 가능하게 만들 수 있습니다.

## 플러그인 표면

플러그인을 로드하면 다음 항목을 등록합니다.

- `VllmConfig`
- `HttpxVllmChatClient`
- `VllmAgentModel`
- 명시적 `IAgentModel -> VllmAgentModel` binding

`VllmAgentModel.complete()`는 OpenAI-compatible chat completion 요청을 보내고,
provider 응답을 `ModelResponse`로 변환합니다. structured output 요청에는
OpenAI-compatible `response_format`과 vLLM `structured_outputs.json` 제약을 함께
실어 보낸 뒤, 반환된 JSON을 파싱하고 검증해 `ModelResponse.structured_output`으로
노출합니다.

tool calling은 `@agent_tool` descriptor에서 생성된
`ModelToolSpec.parameters.schema` 객체를 vLLM function parameter schema로 사용합니다.
required tool choice는 constrained decoding으로 취급합니다. `auto`와 strict tool
schema를 함께 쓰는 요청은 capability error로 실패합니다. vLLM이 auto tool arguments의
schema-constrained decoding을 보장하지 않기 때문입니다. 반환된 tool arguments는 같은
schema로 파싱·검증한 뒤에만 `ModelToolCall`로 노출됩니다.

`VllmAgentModel.stream()`은 같은 요청에 `stream=true`를 붙여 전송하고, server-sent
event chunk를 디코딩해 provider-neutral `ModelStreamEvent` 값을 내보냅니다.

- token delta는 `ModelStreamEventKind.TOKEN_DELTA`
- streamed function-call fragment는 `tool_calls` finish boundary에서 `TOOL_CALL_CANDIDATE`
- structured JSON content는 terminal validation 이후 `STRUCTURED_OUTPUT`
- `StreamingOptions.include_usage`가 켜진 경우 usage chunk는 마지막 `DONE` event에 첨부
- timeout, transport, invalid chunk, invalid structured output, provider error,
  refusal, unsupported constrained decoding mode, non-success finish reason은 typed
  `ERROR` event 뒤 `DONE`으로 종료

Agent 구현체는 token event를 `AgentYieldKind.TOKEN` payload로 전달할 수 있습니다.
취소 lifecycle이 모델 호출 중단을 요구하면 async stream을 닫으면 됩니다. HTTP stream은
async generator가 소유하므로 `aclose()`가 underlying client stream을 해제하고,
background request를 남기지 않습니다.

## 검증 전략

이 패키지의 테스트는 실제 vLLM 서버나 로컬 모델을 호출하지 않습니다. CI와 로컬 커밋
시간을 예측 가능하게 유지하기 위해 `IVllmChatClient` fake를 사용해 adapter 계약을
검증합니다.

주요 검증 범위:

- OpenAI-compatible request payload 변환
- structured output 요청과 JSON schema 검증
- required tool calling payload와 반환 argument 검증
- server-sent event chunk를 `ModelStreamEvent`로 변환하는 streaming adapter 동작
- timeout, transport, provider error, refusal, unsupported constrained decoding mode,
  non-success finish reason의 typed error mapping
