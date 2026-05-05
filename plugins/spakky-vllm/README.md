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

## Local vLLM Smoke Path

The package includes an opt-in smoke path for adopters who want to verify the
adapter against a real local vLLM server without using a paid SaaS key. The
default test suite skips this path unless `SPAKKY_VLLM_SMOKE=1` is set, and the
smoke tests also skip when the local `/models` endpoint is unavailable.

Minimum server capability:

- OpenAI-compatible vLLM chat completions endpoint at `/v1/chat/completions`
- streaming chat completion support
- tool calling support for `tool_choice="required"`; vLLM documents this for
  `vllm>=0.8.3` with a tool parser configured
- a chat/instruct model whose template is compatible with the selected tool
  parser; `Qwen/Qwen2.5-7B-Instruct` with the `hermes` parser is a practical
  local smoke target

Start the server in a separate shell:

```bash
vllm serve Qwen/Qwen2.5-7B-Instruct \
  --host 127.0.0.1 \
  --port 8000 \
  --enable-auto-tool-choice \
  --tool-call-parser hermes
```

Run the package-local smoke tests from this package directory:

```bash
export SPAKKY_VLLM__ENDPOINT_URL=http://127.0.0.1:8000/v1
export SPAKKY_VLLM__MODEL=Qwen/Qwen2.5-7B-Instruct
export SPAKKY_VLLM_SMOKE=1

uv run pytest tests/smoke/test_local_vllm.py -q
```

The smoke tests cover three paths:

- `complete()` returns a non-empty response from the local endpoint
- `stream()` yields at least one `TOKEN_DELTA` and a terminal `DONE` event
- required tool calling emits a `lookup_weather` tool call whose arguments pass
  the provided JSON schema

For a visible command-line trace, run the example:

```bash
uv run python examples/local_smoke.py
```

Expected output shape:

```text
COMPLETE ...spakky-vllm-smoke...
TOKEN_DELTA ...
TOKEN_DELTA ...
DONE usage=...
TOOL_CALL lookup_weather {'city': 'Seoul', 'unit': 'celsius'}
```

Exact token boundaries and wording are model-dependent; the adapter-level
contract is the event shape, terminal `DONE`, and schema-validated tool call.
