"""Tests for separate optional batch, file, and provider-native tool ports."""

from collections.abc import Sequence
from math import inf
from typing import cast, override

import pytest
from spakky.agent import (
    JsonObject,
    JsonValue,
    ModelMessage,
    ModelMessageRole,
    ModelRequest,
    ModelResponse,
)

from spakky.plugins.llm.error import LlmPlatformBoundaryError
from spakky.plugins.llm.provider import (
    ILLMBatchProvider,
    ILLMFileProvider,
    ILLMNativeToolProvider,
    ILLMProvider,
    LlmBatchHandle,
    LlmBatchRequest,
    LlmBatchState,
    LlmFileHandle,
    LlmFileUpload,
    LlmNativeToolKind,
    LlmNativeToolRequest,
    LlmNativeToolResult,
)


class RecordingBatchProvider(ILLMBatchProvider):
    """Minimal batch port proving it is independent of interactive inference."""

    @override
    async def submit_batch(self, request: LlmBatchRequest) -> LlmBatchHandle:
        return LlmBatchHandle(id=request.id, state=LlmBatchState.SUBMITTED)

    @override
    async def batch_status(self, handle: LlmBatchHandle) -> LlmBatchHandle:
        return LlmBatchHandle(id=handle.id, state=LlmBatchState.COMPLETED)

    @override
    async def batch_results(self, handle: LlmBatchHandle) -> Sequence[ModelResponse]:
        return (ModelResponse(content=handle.id),)


class RecordingFileProvider(ILLMFileProvider):
    """Minimal explicit file lifecycle adapter."""

    @override
    async def upload_file(self, upload: LlmFileUpload) -> LlmFileHandle:
        return LlmFileHandle("file-1", upload.name, upload.media_type)

    @override
    async def delete_file(self, handle: LlmFileHandle) -> None:
        _ = handle


class RecordingNativeToolProvider(ILLMNativeToolProvider):
    """Minimal native-tool port with no ModelRequest integration."""

    @property
    @override
    def native_tools(self) -> frozenset[LlmNativeToolKind]:
        return frozenset({LlmNativeToolKind.WEB_SEARCH})

    @override
    async def invoke_native_tool(
        self,
        request: LlmNativeToolRequest,
    ) -> LlmNativeToolResult:
        return LlmNativeToolResult(request.kind, {"items": 1}, {})


def _request() -> ModelRequest:
    return ModelRequest(messages=(ModelMessage(ModelMessageRole.USER, "hello"),))


async def test_batch_port_expect_explicit_lifecycle_outside_interactive_provider() -> (
    None
):
    """Batch submit/status/results works without inheriting ILLMProvider."""
    provider = RecordingBatchProvider()
    request = LlmBatchRequest("batch-1", (_request(),))

    submitted = await provider.submit_batch(request)
    completed = await provider.batch_status(submitted)
    results = await provider.batch_results(completed)

    assert not isinstance(provider, ILLMProvider)
    assert submitted.state is LlmBatchState.SUBMITTED
    assert completed.state is LlmBatchState.COMPLETED
    assert results[0].content == "batch-1"


async def test_file_and_native_tool_ports_expect_explicit_separate_invocation() -> None:
    """File and web-search behavior exists only through their dedicated ports."""
    files = RecordingFileProvider()
    native = RecordingNativeToolProvider()
    handle = await files.upload_file(
        LlmFileUpload("context.pdf", "application/pdf", b"document")
    )
    result = await native.invoke_native_tool(
        LlmNativeToolRequest(LlmNativeToolKind.WEB_SEARCH, {"query": "spakky"})
    )
    await files.delete_file(handle)

    assert handle.id == "file-1"
    assert native.native_tools == frozenset({LlmNativeToolKind.WEB_SEARCH})
    assert result.output == {"items": 1}


def test_optional_platform_payloads_expect_recursive_snapshot() -> None:
    """Frozen batch and native-tool values do not retain caller JSON aliases."""
    metadata: dict[str, JsonValue] = {"nested": {"value": 1}}
    request = ModelRequest(
        messages=(ModelMessage.user("hello"),),
        metadata=metadata,
    )
    requests = [request]
    batch = LlmBatchRequest("batch", requests)
    arguments: dict[str, JsonValue] = {"query": {"terms": ["one"]}}
    native_request = LlmNativeToolRequest(
        LlmNativeToolKind.WEB_SEARCH,
        arguments,
    )
    output: dict[str, JsonValue] = {"items": [1]}
    result_metadata: dict[str, JsonValue] = {"provider": {"page": 1}}
    result = LlmNativeToolResult(
        LlmNativeToolKind.WEB_SEARCH,
        output,
        result_metadata,
    )

    requests.clear()
    cast(dict[str, JsonValue], metadata["nested"])["value"] = 2
    cast(dict[str, JsonValue], arguments["query"])["terms"] = ["two"]
    output["items"] = [2]
    cast(dict[str, JsonValue], result_metadata["provider"])["page"] = 2

    assert len(batch.requests) == 1
    assert batch.requests[0].metadata == {"nested": {"value": 1}}
    assert native_request.arguments == {"query": {"terms": ("one",)}}
    assert result.output == {"items": (1,)}
    assert result.metadata == {"provider": {"page": 1}}


@pytest.mark.parametrize(
    "invalid",
    (
        lambda: LlmBatchRequest("", (_request(),)),
        lambda: LlmBatchRequest("batch", ()),
        lambda: LlmBatchHandle("", LlmBatchState.RUNNING),
        lambda: LlmFileUpload("", "application/pdf", b"document"),
        lambda: LlmFileUpload("file", "", b"document"),
        lambda: LlmFileUpload("file", "application/pdf", b""),
        lambda: LlmFileHandle("", "file", "application/pdf"),
        lambda: LlmFileHandle("id", "", "application/pdf"),
        lambda: LlmFileHandle("id", "file", ""),
        lambda: LlmBatchRequest(cast(str, 1), (_request(),)),
        lambda: LlmBatchRequest("batch", cast(Sequence[ModelRequest], "bad")),
        lambda: LlmBatchRequest(
            "batch",
            (cast(ModelRequest, object()),),
        ),
        lambda: LlmBatchHandle(
            "id",
            cast(LlmBatchState, "running"),
        ),
        lambda: LlmFileUpload(cast(str, 1), "application/pdf", b"document"),
        lambda: LlmFileUpload("file", cast(str, 1), b"document"),
        lambda: LlmFileUpload("file", "application/pdf", cast(bytes, "bad")),
        lambda: LlmFileHandle(cast(str, 1), "file", "application/pdf"),
        lambda: LlmNativeToolRequest(
            cast(LlmNativeToolKind, "web_search"),
            {},
        ),
        lambda: LlmNativeToolRequest(
            LlmNativeToolKind.WEB_SEARCH,
            cast(JsonObject, []),
        ),
        lambda: LlmNativeToolResult(
            cast(LlmNativeToolKind, "web_search"),
            None,
            {},
        ),
        lambda: LlmNativeToolResult(
            LlmNativeToolKind.WEB_SEARCH,
            cast(JsonValue, inf),
            {},
        ),
        lambda: LlmNativeToolResult(
            LlmNativeToolKind.WEB_SEARCH,
            None,
            cast(JsonObject, []),
        ),
    ),
)
def test_optional_platform_types_expect_invalid_boundaries_rejected(invalid) -> None:
    """Malformed optional platform requests fail before any backend is required."""
    with pytest.raises(LlmPlatformBoundaryError):
        invalid()
