# spakky-vllm

`spakky-vllm` is the first official `IAgentModel` adapter package for `spakky-agent`.
It connects Spakky Agent workflows to a local vLLM OpenAI-compatible HTTP endpoint
without adding model SDK dependencies to core.

## When To Use

Use this package when an application wants to run `@Agent` workflows against a
local vLLM server and inject the model through the core `IAgentModel` port.

## Configuration

Settings are loaded through `VllmConfig` with the `SPAKKY_VLLM__` environment
prefix.

| Setting | Default | Purpose |
|---------|---------|---------|
| `SPAKKY_VLLM__ENDPOINT_URL` | `http://127.0.0.1:8000/v1` | Base OpenAI-compatible API URL |
| `SPAKKY_VLLM__MODEL` | `default` | Model id sent in chat completion requests |
| `SPAKKY_VLLM__REQUEST_TIMEOUT_SECONDS` | `30.0` | Non-streaming request timeout |
| `SPAKKY_VLLM__STREAM_TIMEOUT_SECONDS` | `300.0` | Timeout reserved for streaming requests |
| `SPAKKY_VLLM__STREAM_ENABLED` | `true` | Enables the public streaming surface |

## Plugin Surface

Loading the plugin registers:

- `VllmConfig`
- `HttpxVllmChatClient`
- `VllmAgentModel`
- an explicit `IAgentModel -> VllmAgentModel` binding

`VllmAgentModel.complete()` sends OpenAI-compatible chat completion requests and
maps provider responses into `ModelResponse`. Structured output requests include
both OpenAI-compatible `response_format` and vLLM `structured_outputs.json`
constraints, then parse and validate the returned JSON before exposing
`ModelResponse.structured_output`.

Tool calling uses the `ModelToolSpec.parameters.schema` object generated from
`@agent_tool` descriptors as the vLLM function parameter schema. Required tool
choice is treated as constrained decoding; `auto` plus strict tool schemas fails
with a capability error because vLLM does not guarantee schema-constrained auto
tool arguments. Returned tool arguments are parsed and validated against the same
schema before a `ModelToolCall` can be emitted.

`VllmAgentModel.stream()` sends the same request with `stream=true`, decodes
server-sent event chunks, and emits provider-neutral `ModelStreamEvent` values:

- token deltas become `ModelStreamEventKind.TOKEN_DELTA`
- streamed function-call fragments become `TOOL_CALL_CANDIDATE` at the
  `tool_calls` finish boundary
- structured JSON content becomes `STRUCTURED_OUTPUT` after terminal validation
- usage chunks are attached to the final `DONE` event when requested by
  `StreamingOptions.include_usage`
- timeout, transport, invalid chunk, invalid structured output, provider error,
  refusal, unsupported constrained decoding mode, and non-success finish reasons
  become typed `ERROR` events followed by `DONE`

Agent implementations can forward token events as `AgentYieldKind.TOKEN` payloads
and close the async stream when their cancellation lifecycle asks the model call
to stop. The HTTP stream is owned by the async generator, so `aclose()` releases
the underlying client stream instead of leaving a background request running.
