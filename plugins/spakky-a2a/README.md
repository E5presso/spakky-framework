# spakky-a2a

A2A (Agent2Agent) protocol server plugin for the Spakky framework.

## gRPC transport

`build_a2a_grpc_handler()` builds a `grpc.GenericRpcHandler` for the official
`lf.a2a.v1.A2AService` descriptor. The transport exposes:

- `SendMessage`
- `SendStreamingMessage`
- `GetTask`
- `CancelTask`

The gRPC handler reuses the same AgentCard derivation, `TaskStore`,
`SpakkyAgentExecutor`, and neutral agent-event projection used by the JSON-RPC
transport. Add the handler to a `spakky-grpc` `GrpcServerSpec` or another
`grpc.aio.Server`, then call `/lf.a2a.v1.A2AService/<Method>` with the protobuf
message classes provided by `a2a-sdk`.
