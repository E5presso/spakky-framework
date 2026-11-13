"""OpenAI SDK adapter for Responses API profiles, including ChatGPT sign-in."""

from base64 import b64encode
from collections.abc import AsyncIterator, Iterator, Mapping, Sequence
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from json import JSONDecodeError, dumps
from math import isfinite
from os import environ
from typing import Literal, override

from httpx2 import TimeoutException, TransportError
from openai import (
    APIConnectionError,
    APIError,
    APIResponseValidationError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    AsyncStream,
    AuthenticationError,
    Omit,
    omit,
)
from openai.types.responses import (
    EasyInputMessageParam,
    FunctionToolParam,
    NamespaceToolParam,
    Response,
    ResponseCompletedEvent,
    ResponseErrorEvent,
    ResponseFailedEvent,
    ResponseFunctionCallArgumentsDeltaEvent,
    ResponseFunctionToolCall,
    ResponseFunctionToolCallParam,
    ResponseIncompleteEvent,
    ResponseInputContentParam,
    ResponseInputItemParam,
    ResponseOutputItem,
    ResponseOutputItemAddedEvent,
    ResponseOutputItemDoneEvent,
    ResponseOutputMessage,
    ResponseReasoningItem,
    ResponseReasoningSummaryTextDeltaEvent,
    ResponseReasoningTextDeltaEvent,
    ResponseRefusalDeltaEvent,
    ResponseStreamEvent,
    ResponseTextConfigParam,
    ResponseTextDeltaEvent,
    ResponseUsage,
    ToolParam,
)
from openai.types.responses.response_input_item_param import FunctionCallOutput
from openai.types.shared_params import Reasoning
from spakky.agent import (
    AudioPart,
    DocumentPart,
    ImagePart,
    JsonObject,
    JsonSchemaConstraint,
    JsonValue,
    ModelMessage,
    ModelMessageRole,
    ModelRequest,
    ModelResponse,
    ModelStreamEvent,
    ModelStreamEventKind,
    ModelToolCall,
    ModelToolChoice,
    ModelUsage,
    TextPart,
    VideoPart,
)
from spakky.agent.content import (
    ModelContentPart,
    model_content_parts,
    model_content_text,
)
from spakky.core.pod.annotations.pod import Pod

from spakky.plugins.llm.codec import LlmJsonCodec
from spakky.plugins.llm.config import (
    LlmProviderApi,
    LlmReasoningEffort,
    OpenAICompatibleDialect,
)
from spakky.plugins.llm.constants import OFFICIAL_OPENAI_BASE_URL
from spakky.plugins.llm.error import (
    AbstractLlmError,
    LlmAuthenticationError,
    LlmConfigurationError,
    LlmModelRefusalError,
    LlmQuotaExhaustedError,
    LlmRateLimitError,
    LlmResponseError,
    LlmStreamInterruptedError,
    LlmTimeoutError,
    LlmTransportError,
    LlmUnsupportedFeatureError,
)
from spakky.plugins.llm.provider import (
    ILLMCredentialProvider,
    ILLMProvider,
    LlmAccessToken,
    LlmCredentialRequest,
    LlmModelTarget,
    done_event,
    ensure_terminal_tool_choice,
    ensure_tool_call_allowed,
    routing_metadata,
)

_QUOTA_ERROR_CODES = frozenset(
    {
        "insufficient_quota",
        "subscription_sharing_usage_limit_exceeded",
        "subscription_sharing_usage_unavailable",
    }
)
_RATE_LIMIT_ERROR_CODES = frozenset({"rate_limit_exceeded"})
_SERVER_ERROR_CODES = frozenset({"server_error"})
_UNAUTHORIZED_STATUS = 401
_RATE_LIMIT_STATUS = 429
_TIMEOUT_STATUSES = frozenset({408, 504})
_SERVER_ERROR_STATUS_FLOOR = 500
_CHATGPT_TOOL_NAMESPACE = "functions"
_CHATGPT_TOOL_NAMESPACE_DESCRIPTION = "Function tools provided by the application."
_FINISH_STOP = "stop"
_FINISH_LENGTH = "length"
_FINISH_TOOL_CALLS = "tool_calls"
_OPENAI_IMAGE_MIME_TYPES = frozenset(
    {"image/gif", "image/jpeg", "image/png", "image/webp"}
)
_REASONING_EFFORTS: dict[
    LlmReasoningEffort,
    Literal["none", "minimal", "low", "medium", "high", "xhigh", "max"],
] = {
    LlmReasoningEffort.NONE: "none",
    LlmReasoningEffort.MINIMAL: "minimal",
    LlmReasoningEffort.LOW: "low",
    LlmReasoningEffort.MEDIUM: "medium",
    LlmReasoningEffort.HIGH: "high",
    LlmReasoningEffort.XHIGH: "xhigh",
    LlmReasoningEffort.MAX: "max",
}
_OPENAI_DOCUMENT_MIME_TYPES = frozenset({"application/pdf", "text/plain"})


@dataclass(slots=True)
class _FunctionCallBuffer:
    """Accumulate one streamed function call keyed by its output index."""

    name: str
    call_id: str
    argument_fragments: list[str] = field(default_factory=list)
    # None until the provider sends the authoritative completed arguments.
    final_arguments: str | None = None

    def arguments(self) -> str:
        """Return completed arguments, preferring the provider's final value."""
        if self.final_arguments is not None:
            return self.final_arguments
        return "".join(self.argument_fragments)


@dataclass(slots=True)
class _ResponseTurn:
    """Mutable accumulation of one streamed Responses API turn."""

    text_fragments: list[str] = field(default_factory=list)
    reasoning_fragments: list[str] = field(default_factory=list)
    buffers: dict[int, _FunctionCallBuffer] = field(default_factory=dict)
    tool_calls: tuple[ModelToolCall, ...] = ()
    structured_output: JsonValue = None
    usage: ModelUsage = field(default_factory=ModelUsage)
    # None until a terminal response event arrives; absence means interruption.
    finish_reason: str | None = None
    response_metadata: dict[str, JsonValue] = field(default_factory=dict)


@Pod()
class OpenAIResponsesProvider(ILLMProvider):
    """Map OpenAI Responses SSE streams onto the Spakky model contract."""

    __codec: LlmJsonCodec
    __credential_providers: dict[str, ILLMCredentialProvider]

    def __init__(
        self,
        credential_providers: tuple[ILLMCredentialProvider, ...] = (),
    ) -> None:
        self.__codec = LlmJsonCodec()
        registry: dict[str, ILLMCredentialProvider] = {}
        for credential_provider in credential_providers:
            if credential_provider.name in registry:
                raise LlmConfigurationError
            registry[credential_provider.name] = credential_provider
        self.__credential_providers = registry

    @property
    @override
    def apis(self) -> frozenset[LlmProviderApi]:
        """Return the OpenAI Responses API family."""
        return frozenset({LlmProviderApi.OPENAI_RESPONSES})

    @property
    @override
    def is_default(self) -> bool:
        """Mark the first-party Responses adapter as replaceable default."""
        return True

    @override
    async def complete(
        self,
        target: LlmModelTarget,
        request: ModelRequest,
    ) -> ModelResponse:
        """Return one completion aggregated from the Responses SSE stream."""
        turn = _ResponseTurn()
        async for _ in self._events(
            target,
            request,
            turn,
            target.profile.request_timeout_seconds,
        ):
            continue
        metadata: dict[str, JsonValue] = self._metadata(target)
        metadata.update(turn.response_metadata)
        metadata["finish_reason"] = turn.finish_reason
        if len(turn.reasoning_fragments) > 0:
            metadata["reasoning"] = "".join(turn.reasoning_fragments)
        return ModelResponse(
            content="".join(turn.text_fragments),
            structured_output=turn.structured_output,
            tool_calls=turn.tool_calls,
            usage=turn.usage,
            metadata=metadata,
        )

    @override
    def stream(
        self,
        target: LlmModelTarget,
        request: ModelRequest,
    ) -> AsyncIterator[ModelStreamEvent]:
        """Return normalized events from the Responses SSE stream."""
        return self._stream(target, request)

    async def _stream(
        self,
        target: LlmModelTarget,
        request: ModelRequest,
    ) -> AsyncIterator[ModelStreamEvent]:
        turn = _ResponseTurn()
        async for event in self._events(
            target,
            request,
            turn,
            target.profile.stream_timeout_seconds,
        ):
            yield event
        for tool_call in turn.tool_calls:
            yield ModelStreamEvent(
                kind=ModelStreamEventKind.TOOL_CALL_END,
                tool_call=tool_call,
                metadata=self._metadata(target),
            )
            yield ModelStreamEvent(
                kind=ModelStreamEventKind.TOOL_CALL_CANDIDATE,
                tool_call=tool_call,
                metadata=self._metadata(target),
            )
        if request.structured_output is not None:
            yield ModelStreamEvent(
                kind=ModelStreamEventKind.STRUCTURED_OUTPUT,
                structured_output=turn.structured_output,
                metadata=self._metadata(target),
            )
        yield done_event(
            target,
            turn.finish_reason,
            turn.usage if request.streaming.include_usage else None,
            turn.response_metadata,
        )

    async def _events(
        self,
        target: LlmModelTarget,
        request: ModelRequest,
        turn: _ResponseTurn,
        timeout: float | None,
    ) -> AsyncIterator[ModelStreamEvent]:
        self._ensure_supported_request(target, request)
        input_items = self._input(target, request)
        constraints = self.__codec.tool_constraints(request.tool_calling)
        try:
            async with AsyncExitStack() as stack:
                stream = await self._open(stack, target, request, input_items, timeout)
                async for event in stream:
                    for model_event in self._event(target, request, event, turn):
                        yield model_event
        except APIError as error:
            raise self._normalized_sdk_error(error) from error
        except TimeoutException as error:
            raise LlmTimeoutError from error
        except TransportError as error:
            raise LlmStreamInterruptedError from error
        except (JSONDecodeError, AttributeError, TypeError) as error:
            raise LlmResponseError from error

        if turn.finish_reason is None:
            raise LlmStreamInterruptedError
        turn.tool_calls = tuple(
            self._tool_call(target, turn.buffers[index], constraints)
            for index in sorted(turn.buffers)
        )
        ensure_terminal_tool_choice(request, len(turn.tool_calls))
        if len(turn.tool_calls) > 0:
            turn.finish_reason = _FINISH_TOOL_CALLS
        if request.structured_output is not None:
            turn.structured_output = self.__codec.decode_value(
                "".join(turn.text_fragments),
                request.structured_output.constraint,
            )

    async def _open(
        self,
        stack: AsyncExitStack,
        target: LlmModelTarget,
        request: ModelRequest,
        input_items: list[ResponseInputItemParam],
        timeout: float | None,
    ) -> AsyncStream[ResponseStreamEvent]:
        """Open the SSE stream, replacing a rejected dynamic credential once."""
        credential_provider = self._credential_provider(target)
        token = await self._access_token(target, request, credential_provider, None)
        client = await stack.enter_async_context(self._client(target, token))
        try:
            stream = await self._create(client, target, request, input_items, timeout)
        except AuthenticationError:
            if credential_provider is None:
                raise
            token = await self._access_token(
                target,
                request,
                credential_provider,
                token,
            )
            client = await stack.enter_async_context(self._client(target, token))
            stream = await self._create(client, target, request, input_items, timeout)
        return await stack.enter_async_context(stream)

    async def _create(
        self,
        client: AsyncOpenAI,
        target: LlmModelTarget,
        request: ModelRequest,
        input_items: list[ResponseInputItemParam],
        timeout: float | None,
    ) -> AsyncStream[ResponseStreamEvent]:
        sampling = request.sampling
        return await client.responses.create(
            model=target.model,
            input=input_items,
            stream=True,
            store=False,
            temperature=self._sampling_number(target, sampling.temperature),
            top_p=self._sampling_number(target, sampling.top_p),
            max_output_tokens=self._max_output_tokens(target, request),
            tools=self._tools(target, request),
            tool_choice=self._tool_choice(request),
            text=self._text(request),
            reasoning=self._reasoning(target),
            timeout=timeout,
        )

    def _credential_provider(
        self,
        target: LlmModelTarget,
    ) -> ILLMCredentialProvider | None:
        name = target.profile.credential_provider
        if name is None:
            return None
        credential_provider = self.__credential_providers.get(name)
        if credential_provider is None:
            raise LlmConfigurationError
        return credential_provider

    async def _access_token(
        self,
        target: LlmModelTarget,
        request: ModelRequest,
        credential_provider: ILLMCredentialProvider | None,
        rejected_token: LlmAccessToken | None,
    ) -> LlmAccessToken:
        if credential_provider is None:
            api_key = target.profile.api_key_value()
            if api_key is None:
                raise LlmConfigurationError
            return api_key
        token = await credential_provider.access_token(
            LlmCredentialRequest(
                profile_name=target.profile_name,
                request=request,
                rejected_token=rejected_token,
            )
        )
        if token.strip() == "":
            raise LlmConfigurationError
        return token

    def _client(self, target: LlmModelTarget, token: LlmAccessToken) -> AsyncOpenAI:
        profile = target.profile
        if profile.api not in self.apis:
            raise LlmUnsupportedFeatureError
        if "OPENAI_CUSTOM_HEADERS" in environ:
            raise LlmConfigurationError
        return AsyncOpenAI(
            api_key=token,
            admin_api_key="",
            base_url=profile.base_url or OFFICIAL_OPENAI_BASE_URL,
            organization="",
            project="",
            webhook_secret="",
            timeout=profile.request_timeout_seconds,
            max_retries=profile.max_retries,
            default_headers=dict(profile.headers),
        )

    def _event(
        self,
        target: LlmModelTarget,
        request: ModelRequest,
        event: ResponseStreamEvent,
        turn: _ResponseTurn,
    ) -> Iterator[ModelStreamEvent]:
        if isinstance(event, ResponseTextDeltaEvent):
            if event.delta != "":
                turn.text_fragments.append(event.delta)
                yield ModelStreamEvent(
                    kind=ModelStreamEventKind.TOKEN_DELTA,
                    token_delta=event.delta,
                    metadata=self._metadata(target),
                )
        elif isinstance(event, ResponseRefusalDeltaEvent):
            raise LlmModelRefusalError
        elif isinstance(
            event,
            ResponseReasoningSummaryTextDeltaEvent | ResponseReasoningTextDeltaEvent,
        ):
            if target.route.capability.supports_reasoning and event.delta != "":
                turn.reasoning_fragments.append(event.delta)
                yield ModelStreamEvent(
                    kind=ModelStreamEventKind.REASONING_DELTA,
                    reasoning_delta=event.delta,
                    metadata=self._metadata(target),
                )
        elif isinstance(event, ResponseOutputItemAddedEvent):
            yield from self._function_call_started(
                target,
                request,
                turn,
                event.output_index,
                event.item,
            )
        elif isinstance(event, ResponseFunctionCallArgumentsDeltaEvent):
            buffer = turn.buffers.get(event.output_index)
            if buffer is None:
                raise LlmResponseError
            buffer.argument_fragments.append(event.delta)
            yield ModelStreamEvent(
                kind=ModelStreamEventKind.TOOL_CALL_ARGS_DELTA,
                tool_call=self._partial_tool_call(target, buffer),
                tool_call_args_delta=event.delta,
                metadata=self._metadata(target),
            )
        elif isinstance(event, ResponseOutputItemDoneEvent):
            yield from self._function_call_started(
                target,
                request,
                turn,
                event.output_index,
                event.item,
            )
            if isinstance(event.item, ResponseFunctionToolCall):
                turn.buffers[event.output_index].final_arguments = event.item.arguments
        elif isinstance(event, ResponseCompletedEvent):
            if event.response.status != "completed":
                raise LlmResponseError
            self._finish(turn, event.response, _FINISH_STOP)
        elif isinstance(event, ResponseIncompleteEvent):
            details = event.response.incomplete_details
            if details is None or details.reason != "max_output_tokens":
                raise LlmModelRefusalError
            self._finish(turn, event.response, _FINISH_LENGTH)
        elif isinstance(event, ResponseFailedEvent):
            failure = event.response.error
            raise self._coded_error(failure.code if failure is not None else None)
        elif isinstance(event, ResponseErrorEvent):
            raise self._coded_error(event.code)

    def _function_call_started(
        self,
        target: LlmModelTarget,
        request: ModelRequest,
        turn: _ResponseTurn,
        output_index: int,
        item: ResponseOutputItem,
    ) -> Iterator[ModelStreamEvent]:
        if isinstance(item, ResponseOutputMessage | ResponseReasoningItem):
            return
        if not isinstance(item, ResponseFunctionToolCall):
            raise LlmUnsupportedFeatureError
        if output_index in turn.buffers:
            return
        ensure_tool_call_allowed(request)
        buffer = _FunctionCallBuffer(name=item.name, call_id=item.call_id)
        turn.buffers[output_index] = buffer
        yield ModelStreamEvent(
            kind=ModelStreamEventKind.TOOL_CALL_START,
            tool_call=self._partial_tool_call(target, buffer),
            metadata=self._metadata(target),
        )

    def _finish(
        self,
        turn: _ResponseTurn,
        response: Response,
        finish_reason: str,
    ) -> None:
        turn.finish_reason = finish_reason
        turn.usage = self._usage(response.usage)
        turn.response_metadata = {
            "response_id": response.id,
            "response_model": response.model,
        }

    def _input(
        self,
        target: LlmModelTarget,
        request: ModelRequest,
    ) -> list[ResponseInputItemParam]:
        items: list[ResponseInputItemParam] = []
        for message in request.assemble_messages():
            items.extend(self._message_items(target, message))
        return items

    def _ensure_supported_request(
        self,
        target: LlmModelTarget,
        request: ModelRequest,
    ) -> None:
        required = request.required_input_modalities()
        if not required <= target.route.capability.input_modalities:
            raise LlmUnsupportedFeatureError

    def _message_items(
        self,
        target: LlmModelTarget,
        message: ModelMessage,
    ) -> list[ResponseInputItemParam]:
        if message.role == ModelMessageRole.SYSTEM:
            system: EasyInputMessageParam = {
                "role": self._system_role(target),
                "content": self._non_media_text(message),
            }
            return [system]
        if message.role in (ModelMessageRole.USER, ModelMessageRole.EVIDENCE):
            user: EasyInputMessageParam = {
                "role": "user",
                "content": self._user_content(message),
            }
            return [user]
        if message.role == ModelMessageRole.ASSISTANT:
            items: list[ResponseInputItemParam] = []
            text = self._non_media_text(message)
            if text != "":
                assistant: EasyInputMessageParam = {
                    "role": "assistant",
                    "content": text,
                }
                items.append(assistant)
            items.extend(self._history_function_calls(target, message.metadata))
            return items
        call_id = message.metadata.get("call_id")
        if not isinstance(call_id, str) or call_id.strip() == "":
            raise LlmResponseError
        output: FunctionCallOutput = {
            "type": "function_call_output",
            "call_id": call_id,
            "output": self._non_media_text(message),
        }
        return [output]

    def _system_role(self, target: LlmModelTarget) -> Literal["system", "developer"]:
        if target.profile.openai_dialect == OpenAICompatibleDialect.CHATGPT:
            return "developer"
        return "system"

    def _user_content(
        self,
        message: ModelMessage,
    ) -> str | list[ResponseInputContentParam]:
        if isinstance(message.content, str):
            return message.content
        return [
            self._content_part(part) for part in model_content_parts(message.content)
        ]

    def _non_media_text(self, message: ModelMessage) -> str:
        if not isinstance(message.content, str) and any(
            not isinstance(part, TextPart)
            for part in model_content_parts(message.content)
        ):
            raise LlmUnsupportedFeatureError
        return model_content_text(message.content)

    def _content_part(self, part: ModelContentPart) -> ResponseInputContentParam:
        if isinstance(part, TextPart):
            return {"type": "input_text", "text": part.text}
        if isinstance(part, ImagePart):
            if part.media_type not in _OPENAI_IMAGE_MIME_TYPES:
                raise LlmUnsupportedFeatureError
            image_url = part.uri
            if image_url is None:
                image_url = self._data_url(part.media_type, part.data)
            return {"type": "input_image", "image_url": image_url, "detail": "auto"}
        if isinstance(part, DocumentPart):
            if (
                part.uri is not None
                or part.media_type not in _OPENAI_DOCUMENT_MIME_TYPES
                or part.filename is None
            ):
                raise LlmUnsupportedFeatureError
            return {
                "type": "input_file",
                "file_data": self._data_url(part.media_type, part.data),
                "filename": part.filename,
            }
        if isinstance(part, AudioPart | VideoPart):
            raise LlmUnsupportedFeatureError
        raise LlmResponseError

    def _data_url(self, media_type: str, data: bytes | None) -> str:
        if data is None:
            raise LlmResponseError
        encoded = b64encode(data).decode("ascii")
        return f"data:{media_type};base64,{encoded}"

    def _history_function_calls(
        self,
        target: LlmModelTarget,
        metadata: JsonObject,
    ) -> list[ResponseFunctionToolCallParam]:
        value = metadata.get("tool_calls")
        if value is None:
            return []
        if not isinstance(value, Sequence) or isinstance(value, str):
            raise LlmResponseError
        calls: list[ResponseFunctionToolCallParam] = []
        for raw_call in value:
            if not isinstance(raw_call, Mapping):
                raise LlmResponseError
            call_id = raw_call.get("id")
            name = raw_call.get("name")
            arguments = raw_call.get("arguments")
            if not isinstance(call_id, str) or not isinstance(name, str):
                raise LlmResponseError
            if isinstance(arguments, str):
                encoded_arguments = arguments
            elif isinstance(arguments, Mapping):
                encoded_arguments = dumps(arguments, separators=(",", ":"))
            else:
                raise LlmResponseError
            call: ResponseFunctionToolCallParam = {
                "type": "function_call",
                "call_id": call_id,
                "name": name,
                "arguments": encoded_arguments,
            }
            if target.profile.openai_dialect == OpenAICompatibleDialect.CHATGPT:
                call["namespace"] = _CHATGPT_TOOL_NAMESPACE
            calls.append(call)
        return calls

    def _tools(
        self,
        target: LlmModelTarget,
        request: ModelRequest,
    ) -> list[ToolParam] | Omit:
        if request.tool_calling is None:
            return omit
        if len(request.tool_calling.tools) == 0:
            raise LlmResponseError
        functions: list[FunctionToolParam] = [
            {
                "type": "function",
                "name": tool.name,
                "description": tool.description or "",
                "parameters": self._schema(tool.parameters.schema),
                "strict": tool.parameters.strict,
            }
            for tool in request.tool_calling.tools
        ]
        if target.profile.openai_dialect != OpenAICompatibleDialect.CHATGPT:
            return [*functions]
        namespace: NamespaceToolParam = {
            "type": "namespace",
            "name": _CHATGPT_TOOL_NAMESPACE,
            "description": _CHATGPT_TOOL_NAMESPACE_DESCRIPTION,
            "tools": [
                {
                    "type": "function",
                    "name": function["name"],
                    "description": function.get("description"),
                    "parameters": function["parameters"],
                    "strict": function["strict"],
                }
                for function in functions
            ],
        }
        return [namespace]

    def _tool_choice(
        self,
        request: ModelRequest,
    ) -> Literal["auto", "none", "required"] | Omit:
        if request.tool_calling is None:
            return omit
        if request.tool_calling.choice == ModelToolChoice.AUTO:
            return "auto"
        if request.tool_calling.choice == ModelToolChoice.NONE:
            return "none"
        return "required"

    def _text(self, request: ModelRequest) -> ResponseTextConfigParam | Omit:
        if request.structured_output is None:
            return omit
        constraint = request.structured_output.constraint
        schema = (
            self._strict_response_schema(constraint.schema)
            if constraint.strict
            else constraint.schema
        )
        return {
            "format": {
                "type": "json_schema",
                "name": request.structured_output.output_type_name
                or "structured_output",
                "schema": self._schema(schema),
                "strict": constraint.strict,
            }
        }

    def _reasoning(self, target: LlmModelTarget) -> Reasoning | Omit:
        effort = target.route.reasoning_effort
        supports_reasoning = target.route.capability.supports_reasoning
        if effort is None and not supports_reasoning:
            return omit
        reasoning: Reasoning = {}
        if effort is not None:
            reasoning["effort"] = _REASONING_EFFORTS[effort]
        if supports_reasoning:
            reasoning["summary"] = "auto"
        return reasoning

    def _sampling_number(
        self,
        target: LlmModelTarget,
        value: float | None,
    ) -> float | Omit:
        if (
            value is None
            or target.profile.openai_dialect == OpenAICompatibleDialect.CHATGPT
        ):
            return omit
        return value

    def _max_output_tokens(
        self,
        target: LlmModelTarget,
        request: ModelRequest,
    ) -> int | Omit:
        max_tokens = request.sampling.max_tokens
        if (
            max_tokens is None
            or target.profile.openai_dialect == OpenAICompatibleDialect.CHATGPT
        ):
            return omit
        return max_tokens

    def _tool_call(
        self,
        target: LlmModelTarget,
        buffer: _FunctionCallBuffer,
        constraints: Mapping[str, JsonSchemaConstraint] | None,
    ) -> ModelToolCall:
        arguments = buffer.arguments()
        constraint = self.__codec.tool_constraint(buffer.name, constraints)
        return ModelToolCall(
            name=buffer.name,
            arguments=self.__codec.decode_object(arguments, constraint),
            call_id=buffer.call_id,
            metadata={
                **self._metadata(target),
                "provider_arguments": arguments,
            },
        )

    def _partial_tool_call(
        self,
        target: LlmModelTarget,
        buffer: _FunctionCallBuffer,
    ) -> ModelToolCall:
        return ModelToolCall(
            name=buffer.name,
            arguments={},
            call_id=buffer.call_id,
            metadata=self._metadata(target),
        )

    def _usage(self, usage: ResponseUsage | None) -> ModelUsage:
        if usage is None:
            return ModelUsage()
        return ModelUsage(
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            total_tokens=usage.total_tokens,
            cached_input_tokens=usage.input_tokens_details.cached_tokens,
            cache_write_input_tokens=usage.input_tokens_details.cache_write_tokens,
        )

    def _schema(self, schema: Mapping[str, JsonValue]) -> dict[str, object]:
        return {key: value for key, value in schema.items()}

    def _strict_response_schema(
        self,
        schema: Mapping[str, JsonValue],
    ) -> JsonObject:
        result: dict[str, JsonValue] = {}
        for key, value in schema.items():
            if key == "properties" and isinstance(value, Mapping):
                result[key] = {
                    name: self._strict_response_schema(property_schema)
                    if isinstance(property_schema, Mapping)
                    else property_schema
                    for name, property_schema in value.items()
                }
            elif key in ("anyOf", "prefixItems") and isinstance(value, Sequence):
                result[key] = tuple(
                    self._strict_response_schema(item)
                    if isinstance(item, Mapping)
                    else item
                    for item in value
                )
            elif key in ("items", "additionalProperties") and isinstance(
                value, Mapping
            ):
                result[key] = self._strict_response_schema(value)
            else:
                result[key] = value
        if result.get("type") == "object":
            properties = result.get("properties", {})
            if not isinstance(properties, Mapping):
                raise LlmResponseError
            if isinstance(result.get("additionalProperties"), Mapping):
                raise LlmUnsupportedFeatureError
            result["required"] = tuple(properties)
            result["additionalProperties"] = False
        return result

    def _metadata(self, target: LlmModelTarget) -> dict[str, JsonValue]:
        return dict(routing_metadata(target))

    def _coded_error(self, code: str | None) -> AbstractLlmError:
        """Classify a provider error code carried by an SSE event or HTTP body."""
        details: JsonObject = {} if code is None else {"provider_code": code}
        if code in _QUOTA_ERROR_CODES:
            return LlmQuotaExhaustedError(details=details)
        if code in _RATE_LIMIT_ERROR_CODES:
            return LlmRateLimitError(details=details)
        if code in _SERVER_ERROR_CODES:
            return LlmTransportError(details=details)
        return LlmResponseError(details=details)

    def _normalized_sdk_error(self, error: APIError) -> AbstractLlmError:
        if isinstance(error, APITimeoutError):
            return LlmTimeoutError()
        if isinstance(error, APIConnectionError):
            return LlmTransportError()
        if isinstance(error, APIResponseValidationError):
            return LlmResponseError()
        if error.code in _QUOTA_ERROR_CODES:
            return self._coded_error(error.code)
        if not isinstance(error, APIStatusError):
            return self._coded_error(error.code)
        if error.status_code == _UNAUTHORIZED_STATUS:
            return LlmAuthenticationError()
        if error.status_code in _TIMEOUT_STATUSES:
            return LlmTimeoutError()
        if error.status_code == _RATE_LIMIT_STATUS:
            return LlmRateLimitError(
                retry_after_seconds=self._retry_after_seconds(
                    error.response.headers.get("retry-after")
                )
            )
        if error.status_code >= _SERVER_ERROR_STATUS_FLOOR:
            return LlmTransportError()
        return LlmResponseError()

    def _retry_after_seconds(self, value: str | None) -> float | None:
        if value is None:
            return None
        try:
            seconds = float(value)
        except ValueError:
            return None
        if not isfinite(seconds) or seconds < 0:
            return None
        return seconds
