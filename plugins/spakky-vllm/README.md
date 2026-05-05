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

Streaming chunk mapping is intentionally reserved for the follow-up vLLM streaming
ticket. Until then, `stream()` exposes the contract and fails clearly instead of
silently falling back to fake streaming.
