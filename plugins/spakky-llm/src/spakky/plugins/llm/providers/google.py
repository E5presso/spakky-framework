"""Google Gemini provider implemented with the official Google Gen AI SDK."""

from base64 import b64decode, b64encode
from binascii import Error as Base64Error
from collections.abc import AsyncGenerator, AsyncIterator, Mapping, Sequence
from contextlib import aclosing
from json import JSONDecodeError
from typing import Never, override

import httpx
from google import genai
from google.genai import errors, types
from pydantic import ValidationError
from spakky.agent import (
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
    ToolCallingSpec,
)
from spakky.core.pod.annotations.pod import Pod

from spakky.plugins.llm.codec import LlmJsonCodec
from spakky.plugins.llm.config import LlmProviderApi
from spakky.plugins.llm.constants import OFFICIAL_GOOGLE_BASE_URL
from spakky.plugins.llm.error import (
    LlmConfigurationError,
    LlmModelRefusalError,
    LlmProviderUnavailableError,
    LlmResponseError,
    LlmTimeoutError,
    LlmTransportError,
)
from spakky.plugins.llm.provider import (
    ILLMProvider,
    LlmModelTarget,
    done_event,
    ensure_terminal_tool_choice,
    ensure_tool_call_allowed,
)

_MILLISECONDS_PER_SECOND = 1_000
_SUCCESS_FINISH_REASONS = frozenset({"STOP", "MAX_TOKENS"})
_REFUSAL_FINISH_REASONS = frozenset(
    {
        "SAFETY",
        "RECITATION",
        "LANGUAGE",
        "BLOCKLIST",
        "PROHIBITED_CONTENT",
        "SPII",
        "IMAGE_SAFETY",
        "IMAGE_PROHIBITED_CONTENT",
        "NO_IMAGE",
        "IMAGE_RECITATION",
    }
)


@Pod()
class GoogleGenerateContentProvider(ILLMProvider):
    """Adapt Gemini GenerateContent responses to provider-neutral contracts."""

    __codec: LlmJsonCodec

    def __init__(self) -> None:
        self.__codec = LlmJsonCodec()

    @property
    @override
    def api(self) -> LlmProviderApi:
        """Return the native Google GenerateContent API family."""
        return LlmProviderApi.GOOGLE_GENERATE_CONTENT

    @override
    async def complete(
        self,
        target: LlmModelTarget,
        request: ModelRequest,
    ) -> ModelResponse:
        """Return one Gemini response through the official async SDK client."""
        constraints = self.__codec.tool_constraints(request.tool_calling)
        contents = self._contents(request)
        config = self._generate_config(target, request)
        client = self._client(
            target,
            timeout_seconds=target.profile.request_timeout_seconds,
        )
        try:
            async with client.aio as async_client:
                response = await async_client.models.generate_content(
                    model=target.model,
                    contents=contents,
                    config=config,
                )
        except errors.APIError as error:
            self._raise_api_error(error)
        except (
            errors.UnknownApiResponseError,
            JSONDecodeError,
            TypeError,
            ValidationError,
            httpx.DecodingError,
        ) as error:
            raise LlmResponseError from error
        except (httpx.InvalidURL, httpx.UnsupportedProtocol) as error:
            raise LlmConfigurationError from error
        except httpx.TimeoutException as error:
            raise LlmTimeoutError from error
        except httpx.RequestError as error:
            raise LlmTransportError from error
        finally:
            client.close()
        return self._response(target, request, response, constraints)

    @override
    def stream(
        self,
        target: LlmModelTarget,
        request: ModelRequest,
    ) -> AsyncIterator[ModelStreamEvent]:
        """Stream Gemini parts through provider-neutral event kinds."""
        return self._stream(target, request)

    async def _stream(
        self,
        target: LlmModelTarget,
        request: ModelRequest,
    ) -> AsyncIterator[ModelStreamEvent]:
        constraints = self.__codec.tool_constraints(request.tool_calling)
        contents = self._contents(request)
        config = self._generate_config(target, request)
        structured_fragments: list[str] = []
        finish_reason: str | None = None
        usage: ModelUsage | None = None
        tool_call_count = 0
        pending_tool_events: list[ModelStreamEvent] = []
        client = self._client(
            target,
            timeout_seconds=target.profile.stream_timeout_seconds,
        )
        try:
            async with aclosing(
                self._sdk_stream(client, target, contents, config)
            ) as chunks:
                async for chunk in chunks:
                    self._ensure_not_blocked(chunk)
                    if (
                        request.streaming.include_usage
                        and chunk.usage_metadata is not None
                    ):
                        usage = self._usage(chunk.usage_metadata)
                    candidate = self._optional_candidate(chunk)
                    if candidate is None:
                        continue
                    candidate_finish_reason = self._finish_reason(candidate)
                    if candidate_finish_reason is not None:
                        self._ensure_finish_reason(candidate_finish_reason)
                        finish_reason = candidate_finish_reason
                    async for event in self._part_events(
                        target,
                        request,
                        candidate,
                        constraints,
                        structured_fragments,
                    ):
                        if event.kind is ModelStreamEventKind.TOOL_CALL_CANDIDATE:
                            tool_call_count += 1
                            pending_tool_events.append(event)
                        else:
                            yield event
        finally:
            client.close()
        if finish_reason is None:
            raise LlmResponseError
        ensure_terminal_tool_choice(request, tool_call_count)
        structured_output: JsonValue = None
        if request.structured_output is not None:
            structured_output = self.__codec.decode_value(
                "".join(structured_fragments),
                request.structured_output.constraint,
            )
        for pending_tool_event in pending_tool_events:
            yield pending_tool_event
        if request.structured_output is not None:
            yield ModelStreamEvent(
                kind=ModelStreamEventKind.STRUCTURED_OUTPUT,
                structured_output=structured_output,
                metadata=self._metadata(target),
            )
        yield done_event(target, finish_reason, usage)

    async def _sdk_stream(
        self,
        client: genai.Client,
        target: LlmModelTarget,
        contents: types.ContentListUnion | types.ContentListUnionDict,
        config: types.GenerateContentConfig,
    ) -> AsyncGenerator[types.GenerateContentResponse, None]:
        """Yield only SDK-decoded chunks through the typed provider boundary."""
        try:
            async with client.aio as async_client:
                stream = await async_client.models.generate_content_stream(
                    model=target.model,
                    contents=contents,
                    config=config,
                )
                async for chunk in stream:
                    yield chunk
        except errors.APIError as error:
            self._raise_api_error(error)
        except (
            errors.UnknownApiResponseError,
            JSONDecodeError,
            TypeError,
            ValidationError,
            httpx.DecodingError,
        ) as error:
            raise LlmResponseError from error
        except (httpx.InvalidURL, httpx.UnsupportedProtocol) as error:
            raise LlmConfigurationError from error
        except httpx.TimeoutException as error:
            raise LlmTimeoutError from error
        except httpx.RequestError as error:
            raise LlmTransportError from error

    async def _part_events(
        self,
        target: LlmModelTarget,
        request: ModelRequest,
        candidate: types.Candidate,
        constraints: Mapping[str, JsonSchemaConstraint] | None,
        structured_fragments: list[str],
    ) -> AsyncIterator[ModelStreamEvent]:
        if candidate.content is None or candidate.content.parts is None:
            return
        for part in candidate.content.parts:
            metadata = self._part_metadata(target, part)
            if part.text is not None and part.text != "":
                if part.thought is True:
                    if target.profile.include_thoughts:
                        yield ModelStreamEvent(
                            kind=ModelStreamEventKind.REASONING_DELTA,
                            reasoning_delta=part.text,
                            metadata=metadata,
                        )
                else:
                    if request.structured_output is not None:
                        structured_fragments.append(part.text)
                    yield ModelStreamEvent(
                        kind=ModelStreamEventKind.TOKEN_DELTA,
                        token_delta=part.text,
                        metadata=metadata,
                    )
            tool_call = self._tool_call(target, part, constraints)
            if tool_call is not None:
                ensure_tool_call_allowed(request)
                yield ModelStreamEvent(
                    kind=ModelStreamEventKind.TOOL_CALL_CANDIDATE,
                    tool_call=tool_call,
                    metadata=self._metadata(target),
                )

    def _client(
        self,
        target: LlmModelTarget,
        *,
        timeout_seconds: float,
    ) -> genai.Client:
        if target.profile.api is not self.api:
            raise LlmProviderUnavailableError
        api_key = target.profile.api_key_value()
        if api_key is None:
            raise LlmConfigurationError
        try:
            return genai.Client(
                api_key=api_key,
                vertexai=False,
                http_options=types.HttpOptions(
                    base_url=target.profile.base_url or OFFICIAL_GOOGLE_BASE_URL,
                    headers=dict(target.profile.headers),
                    timeout=int(timeout_seconds * _MILLISECONDS_PER_SECOND),
                    async_client_args={"transport": httpx.AsyncHTTPTransport()},
                    retry_options=types.HttpRetryOptions(
                        attempts=target.profile.max_retries + 1,
                    ),
                ),
            )
        except ValueError as error:
            raise LlmConfigurationError from error

    def _generate_config(
        self,
        target: LlmModelTarget,
        request: ModelRequest,
    ) -> types.GenerateContentConfig:
        system_parts = [
            types.Part.from_text(text=message.content)
            for message in request.assemble_messages()
            if message.role is ModelMessageRole.SYSTEM
        ]
        tool_calling = request.tool_calling
        structured_output = request.structured_output
        return types.GenerateContentConfig(
            system_instruction=(
                types.Content(parts=system_parts) if len(system_parts) > 0 else None
            ),
            temperature=request.sampling.temperature,
            top_p=request.sampling.top_p,
            max_output_tokens=request.sampling.max_tokens,
            response_mime_type=(
                "application/json" if structured_output is not None else None
            ),
            response_json_schema=(
                dict(structured_output.constraint.schema)
                if structured_output is not None
                else None
            ),
            tools=self._tools(tool_calling),
            tool_config=self._tool_config(tool_calling),
            automatic_function_calling=(
                types.AutomaticFunctionCallingConfig(disable=True)
                if tool_calling is not None
                else None
            ),
            thinking_config=(
                types.ThinkingConfig(include_thoughts=True)
                if target.profile.include_thoughts
                else None
            ),
        )

    def _contents(self, request: ModelRequest) -> list[types.Content]:
        contents: list[types.Content] = []
        for message in request.assemble_messages():
            if message.role is ModelMessageRole.SYSTEM:
                continue
            contents.append(self._content(message))
        return contents

    def _content(self, message: ModelMessage) -> types.Content:
        if message.role is ModelMessageRole.ASSISTANT:
            parts = self._assistant_parts(message)
            return types.Content(role="model", parts=parts)
        if message.role is ModelMessageRole.TOOL:
            tool_name = self._optional_metadata_text(message.metadata, "tool_name")
            if tool_name is None:
                raise LlmResponseError
            call_id = self._optional_metadata_text(message.metadata, "call_id")
            response = types.FunctionResponse(
                id=call_id,
                name=tool_name,
                response={"output": message.content},
            )
            return types.Content(
                role="user",
                parts=[types.Part(function_response=response)],
            )
        return types.Content(
            role="user",
            parts=[types.Part.from_text(text=message.content)],
        )

    def _assistant_parts(self, message: ModelMessage) -> list[types.Part]:
        parts: list[types.Part] = []
        raw_tool_calls = message.metadata.get("tool_calls")
        if message.content != "" or raw_tool_calls is None:
            parts.append(
                types.Part(
                    text=message.content,
                    thought_signature=self._thought_signature(
                        message.metadata.get("thought_signature")
                    ),
                )
            )
        if raw_tool_calls is None:
            return parts
        if not isinstance(raw_tool_calls, Sequence) or isinstance(raw_tool_calls, str):
            raise LlmResponseError
        for raw_tool_call in raw_tool_calls:
            if not isinstance(raw_tool_call, Mapping):
                raise LlmResponseError
            name = self._required_mapping_text(raw_tool_call, "name")
            call_id = self._optional_mapping_text(raw_tool_call, "id")
            raw_arguments = raw_tool_call.get("arguments", {})
            arguments = self.__codec.to_object(raw_arguments)
            parts.append(
                types.Part(
                    function_call=types.FunctionCall(
                        id=call_id,
                        name=name,
                        args=dict(arguments),
                    ),
                    thought_signature=self._thought_signature(
                        raw_tool_call.get("thought_signature")
                    ),
                )
            )
        return parts

    def _tools(self, tool_calling: ToolCallingSpec | None) -> list[types.Tool] | None:
        if tool_calling is None:
            return None
        if len(tool_calling.tools) == 0:
            raise LlmResponseError
        declarations = [
            types.FunctionDeclaration(
                name=tool.name,
                description=tool.description,
                parameters_json_schema=dict(tool.parameters.schema),
            )
            for tool in tool_calling.tools
        ]
        return [types.Tool(function_declarations=declarations)]

    def _tool_config(
        self, tool_calling: ToolCallingSpec | None
    ) -> types.ToolConfig | None:
        if tool_calling is None:
            return None
        modes = {
            ModelToolChoice.AUTO: types.FunctionCallingConfigMode.AUTO,
            ModelToolChoice.NONE: types.FunctionCallingConfigMode.NONE,
            ModelToolChoice.REQUIRED: types.FunctionCallingConfigMode.ANY,
        }
        return types.ToolConfig(
            function_calling_config=types.FunctionCallingConfig(
                mode=modes[tool_calling.choice],
            )
        )

    def _response(
        self,
        target: LlmModelTarget,
        request: ModelRequest,
        response: types.GenerateContentResponse,
        constraints: Mapping[str, JsonSchemaConstraint] | None,
    ) -> ModelResponse:
        self._ensure_not_blocked(response)
        candidate = self._candidate(response)
        finish_reason = self._finish_reason(candidate)
        if finish_reason is None:
            raise LlmResponseError
        self._ensure_finish_reason(finish_reason)
        tool_calls = self._tool_calls(target, candidate, constraints)
        ensure_terminal_tool_choice(request, len(tool_calls))
        content = self._visible_text(candidate)
        if content == "" and len(tool_calls) == 0:
            raise LlmResponseError
        structured_output: JsonValue = None
        if request.structured_output is not None:
            structured_output = self.__codec.decode_value(
                content,
                request.structured_output.constraint,
            )
        return ModelResponse(
            content=content,
            structured_output=structured_output,
            tool_calls=tool_calls,
            usage=self._usage(response.usage_metadata),
            metadata={
                **self._metadata(target),
                "finish_reason": finish_reason,
            },
        )

    def _candidate(self, response: types.GenerateContentResponse) -> types.Candidate:
        candidate = self._optional_candidate(response)
        if candidate is None:
            raise LlmResponseError
        return candidate

    def _optional_candidate(
        self,
        response: types.GenerateContentResponse,
    ) -> types.Candidate | None:
        if response.candidates is None or len(response.candidates) == 0:
            return None
        return response.candidates[0]

    def _visible_text(self, candidate: types.Candidate) -> str:
        if candidate.content is None or candidate.content.parts is None:
            return ""
        return "".join(
            part.text
            for part in candidate.content.parts
            if part.text is not None and part.thought is not True
        )

    def _tool_calls(
        self,
        target: LlmModelTarget,
        candidate: types.Candidate,
        constraints: Mapping[str, JsonSchemaConstraint] | None,
    ) -> tuple[ModelToolCall, ...]:
        if candidate.content is None or candidate.content.parts is None:
            return ()
        calls: list[ModelToolCall] = []
        for part in candidate.content.parts:
            call = self._tool_call(target, part, constraints)
            if call is not None:
                calls.append(call)
        return tuple(calls)

    def _tool_call(
        self,
        target: LlmModelTarget,
        part: types.Part,
        constraints: Mapping[str, JsonSchemaConstraint] | None,
    ) -> ModelToolCall | None:
        function_call = part.function_call
        if function_call is None:
            return None
        name = function_call.name
        if name is None or name == "":
            raise LlmResponseError
        arguments = self.__codec.to_object(function_call.args or {})
        constraint = self.__codec.tool_constraint(name, constraints)
        self.__codec.validate(arguments, constraint.schema)
        return ModelToolCall(
            name=name,
            arguments=arguments,
            call_id=function_call.id,
            metadata=self._part_metadata(target, part),
        )

    def _ensure_not_blocked(self, response: types.GenerateContentResponse) -> None:
        if (
            response.prompt_feedback is not None
            and response.prompt_feedback.block_reason is not None
        ):
            raise LlmModelRefusalError

    def _finish_reason(self, candidate: types.Candidate) -> str | None:
        if candidate.finish_reason is None:
            return None
        return candidate.finish_reason.value

    def _ensure_finish_reason(self, finish_reason: str) -> None:
        if finish_reason in _SUCCESS_FINISH_REASONS:
            return
        if finish_reason in _REFUSAL_FINISH_REASONS:
            raise LlmModelRefusalError
        raise LlmResponseError

    def _usage(
        self,
        usage: types.GenerateContentResponseUsageMetadata | None,
    ) -> ModelUsage:
        if usage is None:
            return ModelUsage()
        return ModelUsage(
            input_tokens=usage.prompt_token_count,
            output_tokens=usage.candidates_token_count,
            total_tokens=usage.total_token_count,
        )

    def _metadata(self, target: LlmModelTarget) -> JsonObject:
        return {
            "provider": target.profile.provider,
            "profile": target.profile_name,
        }

    def _part_metadata(
        self,
        target: LlmModelTarget,
        part: types.Part,
    ) -> JsonObject:
        metadata = dict(self._metadata(target))
        if part.thought_signature is not None:
            metadata["thought_signature"] = b64encode(part.thought_signature).decode(
                "ascii"
            )
        return metadata

    def _thought_signature(self, value: JsonValue | None) -> bytes | None:
        if value is None:
            return None
        if not isinstance(value, str) or value == "":
            raise LlmResponseError
        try:
            return b64decode(value, validate=True)
        except Base64Error as error:
            raise LlmResponseError from error

    def _optional_metadata_text(
        self,
        metadata: Mapping[str, JsonValue],
        key: str,
    ) -> str | None:
        return self._optional_mapping_text(metadata, key)

    def _optional_mapping_text(
        self,
        mapping: Mapping[str, JsonValue],
        key: str,
    ) -> str | None:
        value = mapping.get(key)
        if value is None:
            return None
        if not isinstance(value, str) or value == "":
            raise LlmResponseError
        return value

    def _required_mapping_text(
        self,
        mapping: Mapping[str, JsonValue],
        key: str,
    ) -> str:
        value = self._optional_mapping_text(mapping, key)
        if value is None:
            raise LlmResponseError
        return value

    def _raise_api_error(self, error: errors.APIError) -> Never:
        if error.code in (408, 504):
            raise LlmTimeoutError from error
        if error.code == 429 or error.code >= 500:
            raise LlmTransportError from error
        raise LlmResponseError from error
