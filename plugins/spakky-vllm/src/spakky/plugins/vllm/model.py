"""IAgentModel implementation backed by vLLM."""

from collections.abc import AsyncGenerator, AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, field
from json import JSONDecodeError, loads
from typing import override

from spakky.agent import (
    IAgentModel,
    JsonObject,
    JsonSchemaConstraint,
    JsonValue,
    ModelError,
    ModelMessage,
    ModelMessageRole,
    ModelRequest,
    ModelResponse,
    ModelStreamEvent,
    ModelStreamEventKind,
    ModelToolCall,
    ModelToolChoice,
    ModelUsage,
    StructuredOutputSpec,
    ToolCallingSpec,
)
from spakky.core.pod.annotations.pod import Pod

from spakky.plugins.vllm.client import IVllmChatClient
from spakky.plugins.vllm.config import VllmConfig
from spakky.plugins.vllm.error import (
    AbstractVllmError,
    VllmConstrainedDecodingUnsupportedError,
    VllmModelRefusalError,
    VllmResponseError,
    VllmStreamingDisabledError,
    VllmTimeoutError,
    VllmTransportError,
)


@dataclass(slots=True)
class _ToolCallBuffer:
    index: int
    call_id: str | None = None
    name: str | None = None
    arguments_fragments: list[str] = field(default_factory=list)

    def extend_arguments(self, fragment: str | None) -> None:
        if fragment is not None:
            self.arguments_fragments.append(fragment)

    def to_tool_call(self, adapter: "VllmAgentModel") -> ModelToolCall:
        if self.name is None:
            raise VllmResponseError
        constraint = adapter._tool_constraint_for(self.name)
        provider_arguments = "".join(self.arguments_fragments)
        return ModelToolCall(
            name=self.name,
            arguments=adapter._to_tool_arguments(provider_arguments, constraint),
            call_id=self.call_id,
            metadata={"provider_arguments": provider_arguments},
        )


@Pod()
class VllmAgentModel(IAgentModel):
    """Spakky Agent model adapter for a local OpenAI-compatible vLLM server."""

    __config: VllmConfig
    __client: IVllmChatClient
    __tool_schema_by_name: Mapping[str, JsonSchemaConstraint] | None

    def __init__(self, config: VllmConfig, client: IVllmChatClient) -> None:
        self.__config = config
        self.__client = client
        self.__tool_schema_by_name = None

    @override
    async def complete(self, request: ModelRequest) -> ModelResponse:
        """Return a provider-neutral model response from vLLM chat completions."""
        payload = self._to_chat_completion_payload(request, stream=False)
        self.__tool_schema_by_name = self._tool_constraints_by_name(
            request.tool_calling
        )
        response = await self.__client.complete(payload, self.__config)
        return self._to_model_response(response, request)

    @override
    def stream(self, request: ModelRequest) -> AsyncGenerator[ModelStreamEvent, None]:
        """Return provider-neutral stream events from vLLM chat completions."""
        return self._stream(request)

    async def _stream(
        self,
        request: ModelRequest,
    ) -> AsyncGenerator[ModelStreamEvent, None]:
        if not self.__config.stream_enabled:
            yield self._to_error_event(VllmStreamingDisabledError())
            yield self._done_event(None, None)
            return

        try:
            payload = self._to_chat_completion_payload(request, stream=True)
        except AbstractVllmError as e:
            yield self._to_error_event(e)
            yield self._done_event(None, None)
            return
        self.__tool_schema_by_name = self._tool_constraints_by_name(
            request.tool_calling
        )
        structured_fragments: list[str] = []
        tool_buffers: dict[int, _ToolCallBuffer] = {}
        finish_reason: str | None = None
        usage: ModelUsage | None = None
        terminal_error: ModelError | None = None
        try:
            stream = self.__client.stream(payload, self.__config)
        except AbstractVllmError as e:
            yield self._to_error_event(e)
            yield self._done_event(None, None)
            return
        try:
            async for chunk in stream:
                provider_error = self._to_provider_error(chunk.get("error"))
                if provider_error is not None:
                    terminal_error = provider_error
                    break
                usage_value = chunk.get("usage")
                if usage_value is not None:
                    usage = self._to_usage(usage_value)
                choices = self._expect_sequence(chunk.get("choices"))
                if len(choices) == 0:
                    continue
                for raw_choice in choices:
                    choice = self._expect_mapping(raw_choice)
                    async for event in self._stream_choice_events(
                        choice,
                        request.structured_output,
                        structured_fragments,
                        tool_buffers,
                    ):
                        yield event
                    choice_finish_reason = self._optional_string(
                        choice.get("finish_reason")
                    )
                    if choice_finish_reason is not None:
                        finish_reason = choice_finish_reason
                        if finish_reason == "tool_calls":
                            for event in self._tool_call_events(tool_buffers):
                                yield event
                        if (
                            finish_reason == "stop"
                            and request.structured_output is not None
                        ):
                            yield self._to_structured_output_event(
                                structured_fragments,
                                request.structured_output,
                            )
                        terminal_error = self._finish_reason_error(finish_reason)
        except AbstractVllmError as e:
            yield self._to_error_event(e)
            yield self._done_event(None, None)
            return
        finally:
            await stream.aclose()

        if terminal_error is not None:
            yield ModelStreamEvent(
                kind=ModelStreamEventKind.ERROR,
                error=terminal_error,
            )
        yield self._done_event(finish_reason, usage)

    def _to_chat_completion_payload(
        self,
        request: ModelRequest,
        *,
        stream: bool,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "model": self.__config.model,
            "messages": [
                self._to_openai_message(message)
                for message in request.assemble_messages()
            ],
            "stream": stream,
        }
        if request.sampling.temperature is not None:
            payload["temperature"] = request.sampling.temperature
        if request.sampling.top_p is not None:
            payload["top_p"] = request.sampling.top_p
        if request.sampling.max_tokens is not None:
            payload["max_tokens"] = request.sampling.max_tokens
        if request.structured_output is not None:
            structured_schema = request.structured_output.constraint.schema
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": (
                        request.structured_output.output_type_name
                        or "structured_output"
                    ),
                    "schema": structured_schema,
                    "strict": request.structured_output.constraint.strict,
                },
            }
            payload["structured_outputs"] = {"json": structured_schema}
        if request.tool_calling is not None:
            self._ensure_tool_constraints_supported(request.tool_calling)
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description or "",
                        "parameters": tool.parameters.schema,
                        "strict": tool.parameters.strict,
                    },
                }
                for tool in request.tool_calling.tools
            ]
            payload["tool_choice"] = self._to_tool_choice(request.tool_calling.choice)
        if stream and request.streaming.include_usage:
            payload["stream_options"] = {"include_usage": True}
        return payload

    def _to_openai_message(self, message: ModelMessage) -> dict[str, object]:
        role = message.role.value
        if message.role == ModelMessageRole.EVIDENCE:
            role = ModelMessageRole.USER.value
        return {"role": role, "content": message.content}

    def _to_tool_choice(self, choice: ModelToolChoice) -> str:
        return {
            ModelToolChoice.AUTO: "auto",
            ModelToolChoice.NONE: "none",
            ModelToolChoice.REQUIRED: "required",
        }[choice]

    def _to_model_response(
        self,
        response: Mapping[str, object],
        request: ModelRequest,
    ) -> ModelResponse:
        choices = self._expect_sequence(response.get("choices"))
        if len(choices) == 0:
            raise VllmResponseError
        first_choice = self._expect_mapping(choices[0])
        finish_reason = self._optional_string(first_choice.get("finish_reason"))
        message = self._expect_mapping(first_choice.get("message"))
        refusal = self._optional_string(message.get("refusal"))
        if refusal is not None and refusal != "":
            raise VllmModelRefusalError
        if finish_reason == "content_filter":
            raise VllmModelRefusalError
        tool_calls = tuple(self._to_tool_calls(message.get("tool_calls")))
        if (
            request.tool_calling is not None
            and request.tool_calling.choice == ModelToolChoice.NONE
            and len(tool_calls) > 0
        ):
            raise VllmResponseError
        content = self._to_message_content(message.get("content"), tool_calls)
        structured_output = None
        if request.structured_output is not None:
            structured_output = self._to_structured_output(
                content,
                request.structured_output.constraint,
            )
        return ModelResponse(
            content=content,
            structured_output=structured_output,
            tool_calls=tool_calls,
            usage=self._to_usage(response.get("usage")),
            metadata={"provider": "vllm", "finish_reason": finish_reason},
        )

    async def _stream_choice_events(
        self,
        choice: Mapping[str, object],
        structured_output: StructuredOutputSpec | None,
        structured_fragments: list[str],
        tool_buffers: dict[int, _ToolCallBuffer],
    ) -> AsyncIterator[ModelStreamEvent]:
        delta_value = choice.get("delta")
        if delta_value is None:
            return
        delta = self._expect_mapping(delta_value)
        content = self._optional_string(delta.get("content"))
        if content is not None and content != "":
            if structured_output is not None:
                structured_fragments.append(content)
            yield ModelStreamEvent(
                kind=ModelStreamEventKind.TOKEN_DELTA,
                token_delta=content,
                metadata={"provider": "vllm"},
            )
        refusal = self._optional_string(delta.get("refusal"))
        if refusal is not None and refusal != "":
            yield ModelStreamEvent(
                kind=ModelStreamEventKind.ERROR,
                error=ModelError(
                    code="model_refusal",
                    message=refusal,
                    retryable=False,
                    metadata={"provider": "vllm"},
                ),
            )
        tool_call_chunks = delta.get("tool_calls")
        if tool_call_chunks is not None:
            self._accumulate_tool_call_chunks(tool_call_chunks, tool_buffers)

    def _accumulate_tool_call_chunks(
        self,
        value: object,
        tool_buffers: dict[int, _ToolCallBuffer],
    ) -> None:
        raw_calls = self._expect_sequence(value)
        for position, raw_call in enumerate(raw_calls):
            item = self._expect_mapping(raw_call)
            index = self._optional_int(item.get("index"))
            if index is None:
                index = position
            buffer = tool_buffers.setdefault(index, _ToolCallBuffer(index=index))
            call_id = self._optional_string(item.get("id"))
            if call_id is not None:
                buffer.call_id = call_id
            function_value = item.get("function")
            if function_value is None:
                continue
            function = self._expect_mapping(function_value)
            name = self._optional_string(function.get("name"))
            if name is not None:
                buffer.name = name
            buffer.extend_arguments(self._optional_string(function.get("arguments")))

    def _tool_call_events(
        self,
        tool_buffers: dict[int, _ToolCallBuffer],
    ) -> tuple[ModelStreamEvent, ...]:
        events = tuple(
            ModelStreamEvent(
                kind=ModelStreamEventKind.TOOL_CALL_CANDIDATE,
                tool_call=tool_buffers[index].to_tool_call(self),
                metadata={"provider": "vllm"},
            )
            for index in sorted(tool_buffers)
        )
        tool_buffers.clear()
        return events

    def _to_structured_output_event(
        self,
        structured_fragments: Sequence[str],
        structured_output: StructuredOutputSpec,
    ) -> ModelStreamEvent:
        return ModelStreamEvent(
            kind=ModelStreamEventKind.STRUCTURED_OUTPUT,
            structured_output=self._to_structured_output(
                "".join(structured_fragments),
                structured_output.constraint,
            ),
            metadata={"provider": "vllm"},
        )

    def _to_provider_error(self, value: object) -> ModelError | None:
        if value is None:
            return None
        error = self._expect_mapping(value)
        code = self._optional_string(error.get("code")) or "provider_error"
        message = self._optional_string(error.get("message")) or "vLLM stream error"
        return ModelError(
            code=code,
            message=message,
            retryable=False,
            metadata={"provider": "vllm"},
        )

    def _finish_reason_error(self, finish_reason: str) -> ModelError | None:
        if finish_reason in ("stop", "tool_calls"):
            return None
        code = (
            "model_refusal"
            if finish_reason == "content_filter"
            else "model_finish_reason"
        )
        return ModelError(
            code=code,
            message=f"vLLM stream finished with reason: {finish_reason}",
            retryable=False,
            metadata={"provider": "vllm", "finish_reason": finish_reason},
        )

    def _to_error_event(self, error: AbstractVllmError) -> ModelStreamEvent:
        return ModelStreamEvent(
            kind=ModelStreamEventKind.ERROR,
            error=self._to_model_error(error),
        )

    def _to_model_error(self, error: AbstractVllmError) -> ModelError:
        if isinstance(error, VllmTimeoutError):
            return ModelError(
                code="vllm_timeout",
                message=VllmTimeoutError.message,
                retryable=True,
                metadata={"provider": "vllm"},
            )
        if isinstance(error, VllmTransportError):
            return ModelError(
                code="vllm_transport_error",
                message=VllmTransportError.message,
                retryable=True,
                metadata={"provider": "vllm"},
            )
        if isinstance(error, VllmStreamingDisabledError):
            return ModelError(
                code="vllm_streaming_disabled",
                message=VllmStreamingDisabledError.message,
                retryable=False,
                metadata={"provider": "vllm"},
            )
        if isinstance(error, VllmConstrainedDecodingUnsupportedError):
            return ModelError(
                code="vllm_constrained_decoding_unsupported",
                message=VllmConstrainedDecodingUnsupportedError.message,
                retryable=False,
                metadata={"provider": "vllm"},
            )
        return ModelError(
            code="vllm_response_error",
            message=VllmResponseError.message,
            retryable=False,
            metadata={"provider": "vllm"},
        )

    def _done_event(
        self,
        finish_reason: str | None,
        usage: ModelUsage | None,
    ) -> ModelStreamEvent:
        return ModelStreamEvent(
            kind=ModelStreamEventKind.DONE,
            usage=usage,
            metadata={"provider": "vllm", "finish_reason": finish_reason},
        )

    def _to_message_content(
        self,
        value: object,
        tool_calls: tuple[ModelToolCall, ...],
    ) -> str:
        if isinstance(value, str):
            return value
        if value is None and len(tool_calls) > 0:
            return ""
        raise VllmResponseError

    def _to_tool_calls(self, value: object) -> tuple[ModelToolCall, ...]:
        if value is None:
            return ()
        raw_calls = self._expect_sequence(value)
        calls: list[ModelToolCall] = []
        for raw_call in raw_calls:
            item = self._expect_mapping(raw_call)
            function = self._expect_mapping(item.get("function"))
            name = function.get("name")
            if not isinstance(name, str):
                raise VllmResponseError
            constraint = self._tool_constraint_for(name)
            calls.append(
                ModelToolCall(
                    name=name,
                    arguments=self._to_tool_arguments(
                        function.get("arguments"),
                        constraint,
                    ),
                    call_id=self._optional_string(item.get("id")),
                    metadata={
                        "provider_arguments": self._optional_string(
                            function.get("arguments")
                        )
                        or "",
                    },
                )
            )
        return tuple(calls)

    def _to_tool_arguments(
        self,
        value: object,
        constraint: JsonSchemaConstraint | None = None,
    ) -> JsonObject:
        raw_arguments = self._optional_string(value)
        if raw_arguments is None or raw_arguments == "":
            arguments: JsonObject = {}
            if constraint is not None:
                self._validate_json_value(arguments, constraint.schema)
            return arguments
        try:
            decoded: object = loads(raw_arguments)
        except JSONDecodeError as e:
            raise VllmResponseError from e
        arguments = self._to_json_object(decoded)
        if constraint is not None:
            self._validate_json_value(arguments, constraint.schema)
        return arguments

    def _to_structured_output(
        self,
        value: object,
        constraint: JsonSchemaConstraint,
    ) -> JsonValue:
        raw_content = self._optional_string(value)
        if raw_content is None or raw_content == "":
            raise VllmResponseError
        try:
            decoded: object = loads(raw_content)
        except JSONDecodeError as e:
            raise VllmResponseError from e
        structured_output = self._to_json_value(decoded)
        self._validate_json_value(structured_output, constraint.schema)
        return structured_output

    def _to_json_object(self, value: object) -> JsonObject:
        if not isinstance(value, Mapping):
            raise VllmResponseError
        result: dict[str, JsonValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise VllmResponseError
            result[key] = self._to_json_value(item)
        return result

    def _to_json_value(self, value: object) -> JsonValue:
        if value is None or isinstance(value, str | int | float | bool):
            return value
        if isinstance(value, Mapping):
            return self._to_json_object(value)
        if isinstance(value, Sequence):
            return tuple(self._to_json_value(item) for item in value)
        raise VllmResponseError

    def _tool_constraints_by_name(
        self,
        tool_calling: ToolCallingSpec | None,
    ) -> Mapping[str, JsonSchemaConstraint] | None:
        if tool_calling is None:
            return None
        constraints: dict[str, JsonSchemaConstraint] = {}
        for tool in tool_calling.tools:
            if tool.name in constraints:
                raise VllmResponseError
            constraints[tool.name] = tool.parameters
        return constraints

    def _tool_constraint_for(self, name: str) -> JsonSchemaConstraint | None:
        if self.__tool_schema_by_name is None:
            return None
        constraint = self.__tool_schema_by_name.get(name)
        if constraint is None:
            raise VllmResponseError
        return constraint

    def _ensure_tool_constraints_supported(
        self,
        tool_calling: ToolCallingSpec,
    ) -> None:
        if tool_calling.choice != ModelToolChoice.AUTO:
            return
        for tool in tool_calling.tools:
            if tool.parameters.strict:
                raise VllmConstrainedDecodingUnsupportedError

    def _validate_json_value(
        self,
        value: JsonValue,
        schema: Mapping[str, JsonValue],
    ) -> None:
        alternatives = schema.get("anyOf")
        if alternatives is not None:
            self._validate_any_of(value, alternatives)
            return
        enum_values = schema.get("enum")
        if enum_values is not None:
            self._validate_enum(value, enum_values)
        schema_type = self._optional_string(schema.get("type"))
        if schema_type is None:
            return
        if schema_type == "object":
            self._validate_object(value, schema)
            return
        if schema_type == "array":
            self._validate_array(value, schema)
            return
        if schema_type == "string" and not isinstance(value, str):
            raise VllmResponseError
        if schema_type == "integer" and (
            not isinstance(value, int) or isinstance(value, bool)
        ):
            raise VllmResponseError
        if schema_type == "number" and (
            not isinstance(value, int | float) or isinstance(value, bool)
        ):
            raise VllmResponseError
        if schema_type == "boolean" and not isinstance(value, bool):
            raise VllmResponseError
        if schema_type == "null" and value is not None:
            raise VllmResponseError

    def _validate_any_of(self, value: JsonValue, alternatives: JsonValue) -> None:
        if not isinstance(alternatives, Sequence) or isinstance(alternatives, str):
            raise VllmResponseError
        for alternative in alternatives:
            if not isinstance(alternative, Mapping):
                raise VllmResponseError
            try:
                self._validate_json_value(value, alternative)
                return
            except VllmResponseError:
                continue
        raise VllmResponseError

    def _validate_enum(self, value: JsonValue, enum_values: JsonValue) -> None:
        if not isinstance(enum_values, Sequence) or isinstance(enum_values, str):
            raise VllmResponseError
        if value not in enum_values:
            raise VllmResponseError

    def _validate_object(
        self,
        value: JsonValue,
        schema: Mapping[str, JsonValue],
    ) -> None:
        if not isinstance(value, Mapping):
            raise VllmResponseError
        required = schema.get("required", ())
        if not isinstance(required, Sequence) or isinstance(required, str):
            raise VllmResponseError
        for required_key in required:
            if not isinstance(required_key, str) or required_key not in value:
                raise VllmResponseError
        properties = schema.get("properties", {})
        if not isinstance(properties, Mapping):
            raise VllmResponseError
        additional_properties = schema.get("additionalProperties", True)
        for key, item in value.items():
            property_schema = properties.get(key)
            if property_schema is None:
                self._validate_additional_property(item, additional_properties)
                continue
            if not isinstance(property_schema, Mapping):
                raise VllmResponseError
            self._validate_json_value(item, property_schema)

    def _validate_additional_property(
        self,
        value: JsonValue,
        additional_properties: JsonValue,
    ) -> None:
        if additional_properties is False:
            raise VllmResponseError
        if additional_properties is True:
            return
        if not isinstance(additional_properties, Mapping):
            raise VllmResponseError
        self._validate_json_value(value, additional_properties)

    def _validate_array(
        self,
        value: JsonValue,
        schema: Mapping[str, JsonValue],
    ) -> None:
        if not isinstance(value, Sequence) or isinstance(value, str):
            raise VllmResponseError
        min_items = self._optional_int(schema.get("minItems"))
        if min_items is not None and len(value) < min_items:
            raise VllmResponseError
        max_items = self._optional_int(schema.get("maxItems"))
        if max_items is not None and len(value) > max_items:
            raise VllmResponseError
        prefix_items = schema.get("prefixItems")
        if prefix_items is not None:
            self._validate_prefix_items(value, prefix_items)
            return
        item_schema = schema.get("items")
        if item_schema is None:
            return
        if not isinstance(item_schema, Mapping):
            raise VllmResponseError
        for item in value:
            self._validate_json_value(item, item_schema)

    def _validate_prefix_items(
        self,
        value: Sequence[JsonValue],
        prefix_items: JsonValue,
    ) -> None:
        if not isinstance(prefix_items, Sequence) or isinstance(prefix_items, str):
            raise VllmResponseError
        if len(value) < len(prefix_items):
            raise VllmResponseError
        for index, item_schema in enumerate(prefix_items):
            if not isinstance(item_schema, Mapping):
                raise VllmResponseError
            self._validate_json_value(value[index], item_schema)

    def _to_usage(self, value: object) -> ModelUsage:
        if value is None:
            return ModelUsage()
        usage = self._expect_mapping(value)
        return ModelUsage(
            input_tokens=self._optional_int(usage.get("prompt_tokens")),
            output_tokens=self._optional_int(usage.get("completion_tokens")),
            total_tokens=self._optional_int(usage.get("total_tokens")),
        )

    def _expect_mapping(self, value: object) -> Mapping[str, object]:
        if not isinstance(value, Mapping):
            raise VllmResponseError
        return value

    def _expect_sequence(self, value: object) -> tuple[object, ...]:
        if not isinstance(value, list):
            raise VllmResponseError
        return tuple(value)

    def _optional_string(self, value: object) -> str | None:
        if value is None or isinstance(value, str):
            return value
        raise VllmResponseError

    def _optional_int(self, value: object) -> int | None:
        if value is None or isinstance(value, int):
            return value
        raise VllmResponseError
