# Changelog

All notable changes to spakky-vllm are documented in this file.

## Unreleased

- Implemented vLLM OpenAI-compatible streaming over chat completions SSE chunks.
- Added typed streaming error events for timeout, transport, invalid chunk,
  provider error, refusal, and non-success finish reasons.
- Added token delta, tool-call candidate, usage, and cancellation-close coverage.
