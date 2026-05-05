# spakky-vllm

`spakky-vllm` is the local, OpenAI-compatible `IAgentModel` implementation for
ADR-0009 agent workflows. It is intentionally an outbound model adapter: core
agent contracts stay in `spakky-agent`, while this plugin owns vLLM HTTP
configuration, completion mapping, streaming events, and tool-call argument
validation.

## Local Smoke

Use the package-local smoke path when you want to prove complete, stream, and
tool schema behavior against a real local vLLM server without a paid SaaS key.
The smoke tests are opt-in and skip by default, so CI does not fail when no local
model is present.

Minimum local target:

- vLLM OpenAI-compatible chat server exposing `/v1/chat/completions`
- streaming enabled on the server and in `SPAKKY_VLLM__STREAM_ENABLED`
- tool calling support for `tool_choice="required"` with a configured tool-call
  parser; vLLM documents required tool choice for `vllm>=0.8.3`
- a chat/instruct model compatible with that parser, such as
  `Qwen/Qwen2.5-7B-Instruct` with `--tool-call-parser hermes`

```bash
vllm serve Qwen/Qwen2.5-7B-Instruct \
  --host 127.0.0.1 \
  --port 8000 \
  --enable-auto-tool-choice \
  --tool-call-parser hermes

export SPAKKY_VLLM__ENDPOINT_URL=http://127.0.0.1:8000/v1
export SPAKKY_VLLM__MODEL=Qwen/Qwen2.5-7B-Instruct
export SPAKKY_VLLM_SMOKE=1

cd plugins/spakky-vllm
uv run pytest tests/smoke/test_local_vllm.py -q
uv run python examples/local_smoke.py
```

Expected stream trace shape:

```text
COMPLETE ...
TOKEN_DELTA ...
DONE usage=...
TOOL_CALL lookup_weather {'city': 'Seoul', 'unit': 'celsius'}
```

The exact token text is model-dependent. The stable contract is that stream
chunks map to `ModelStreamEventKind.TOKEN_DELTA`, stream termination maps to
`DONE`, and required tool calls become schema-validated `ModelToolCall` values.

::: spakky.plugins.vllm
