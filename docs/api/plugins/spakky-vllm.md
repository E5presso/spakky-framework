# spakky-vllm

`spakky-vllm`은 ADR-0009 Agent workflow를 위한 로컬 OpenAI-compatible
`IAgentModel` 구현체입니다. 이 패키지는 의도적으로 outbound model adapter 역할만
담당합니다. Agent core 계약은 `spakky-agent`에 남기고, vLLM HTTP 설정, completion
mapping, streaming event, tool-call argument 검증은 이 플러그인이 소유합니다.

## 검증 전략

`spakky-vllm` 테스트는 실제 vLLM 서버나 로컬 모델을 호출하지 않습니다. CI와 로컬 커밋
시간을 예측 가능하게 유지하기 위해 `IVllmChatClient` fake로 request mapping,
streaming event 변환, structured output, required tool calling, error mapping을
검증합니다.

::: spakky.plugins.vllm
