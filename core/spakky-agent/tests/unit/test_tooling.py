"""Tests for agent tool descriptor discovery."""

from collections.abc import AsyncGenerator, Mapping
import typing
from dataclasses import dataclass
from enum import Enum, StrEnum
from typing import Annotated

import pytest

from spakky.agent import (
    Agent,
    AgentDefinitionError,
    AgentToolCatalog,
    AgentToolDescriptor,
    AgentToolIdentity,
    AgentToolSchemaHandle,
    AgentYield,
    AgentYieldKind,
    DataAccess,
    EvidenceCapture,
    Externality,
    Final,
    Idempotency,
    ResultBudget,
    TimeoutPolicy,
    ToolApprovalRequirement,
    ToolEffects,
    ToolPermission,
    ToolResumeAction,
    ToolRisk,
    ToolRiskAxis,
    agent_tool,
    discover_agent_tools,
)
from spakky.agent.tooling import AGENT_TOOL_DEFINITION_KEY, get_agent_tool_definition


class SearchMode(StrEnum):
    """검색 도구 입력 enum fixture."""

    EXACT = "exact"
    FUZZY = "fuzzy"


class ExitCode(Enum):
    """정수 enum fixture."""

    OK = 0
    FAIL = 1


class MixedJsonEnum(Enum):
    """Mixed JSON primitive enum fixture."""

    ENABLED = True
    SCORE = 0.5
    EMPTY = None


@dataclass(frozen=True, slots=True)
class SearchFilter:
    """Nested dataclass fixture for schema generation."""

    tags: list[str]
    limit: int = 10


@dataclass(frozen=True, slots=True)
class SearchResult:
    """Dataclass output fixture for schema generation."""

    title: str
    scores: Mapping[str, float]
    filter_: SearchFilter | None = None


@dataclass(frozen=True, slots=True)
class DefaultedFilter:
    """Dataclass fixture whose fields are all optional by default."""

    enabled: bool = False


def test_agent_tool_expect_attaches_typed_descriptor_metadata_to_method() -> None:
    """decorator가 method object에 typed descriptor metadata를 남긴다."""

    @agent_tool(
        name="search_docs",
        schema_name="docs.search",
        permissions=(ToolPermission("docs.read"),),
        effects=ToolEffects.read_only(),
        idempotency=Idempotency.IDEMPOTENT,
        evidence=EvidenceCapture.STRUCTURED,
        approval=ToolApprovalRequirement.NOT_REQUIRED,
    )
    def search_docs(query: str) -> str:
        return query

    definition = get_agent_tool_definition(search_docs)

    assert definition is not None
    assert definition.name == "search_docs"
    assert definition.schema_name == "docs.search"
    assert definition.metadata.permissions == (ToolPermission("docs.read"),)
    assert definition.metadata.effects == ToolEffects.read_only()
    assert definition.metadata.idempotency == Idempotency.IDEMPOTENT
    assert definition.metadata.evidence == EvidenceCapture.STRUCTURED
    assert definition.metadata.approval == ToolApprovalRequirement.NOT_REQUIRED
    assert definition.metadata.risk == ToolRisk(axes=(ToolRiskAxis.READ,))
    assert definition.metadata.requires_approval_candidate is False


def test_agent_expect_discovers_decorated_methods_as_deterministic_catalog() -> None:
    """Agent metadata가 decorated method catalog를 deterministic order로 보존한다."""

    @Agent()
    class WorkspaceAgent:
        @agent_tool(schema_name="workspace.write")
        def write_file(self, path: str, content: str) -> str:
            return f"{path}:{content}"

        @agent_tool(schema_name="workspace.read")
        def read_file(self, path: str) -> str:
            return path

        async def execute(
            self,
            command: str,
        ) -> AsyncGenerator[AgentYield[Final[str]], None]:
            yield AgentYield(
                kind=AgentYieldKind.FINAL,
                payload=Final(output=command, metadata={}),
            )

    catalog = Agent.get(WorkspaceAgent).tool_catalog

    assert [descriptor.schema.name for descriptor in catalog.descriptors] == [
        "workspace.read",
        "workspace.write",
    ]
    assert [descriptor.name for descriptor in catalog.descriptors] == [
        "read_file",
        "write_file",
    ]


def test_tool_schema_expect_generates_input_schema_from_supported_signature() -> None:
    """primitive/enum/dataclass/collection/optional signature를 JSON schema로 만든다."""

    @Agent()
    class SearchAgent:
        @agent_tool(schema_name="docs.search")
        def search(
            self,
            query: Annotated[str, "model-visible"],
            mode: SearchMode,
            filters: list[SearchFilter],
            window: tuple[int, int],
            metadata: Mapping[str, str] | None = None,
        ) -> SearchResult:
            return SearchResult(
                title=f"{mode}:{query}",
                scores={"total": 1.0},
                filter_=filters[0] if filters else None,
            )

        async def execute(
            self,
            command: str,
        ) -> AsyncGenerator[AgentYield[Final[str]], None]:
            yield AgentYield(
                kind=AgentYieldKind.FINAL,
                payload=Final(output=command, metadata={}),
            )

    descriptor = Agent.get(SearchAgent).tool_catalog.by_schema_name("docs.search")

    assert descriptor.schema.input_schema == {
        "type": "object",
        "title": "docs.search.input",
        "properties": {
            "query": {"type": "string"},
            "mode": {"enum": ["exact", "fuzzy"], "type": "string"},
            "filters": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "tags": {"type": "array", "items": {"type": "string"}},
                        "limit": {"type": "integer"},
                    },
                    "additionalProperties": False,
                    "required": ["tags"],
                },
            },
            "window": {
                "type": "array",
                "prefixItems": [{"type": "integer"}, {"type": "integer"}],
                "minItems": 2,
                "maxItems": 2,
            },
            "metadata": {
                "anyOf": [
                    {
                        "type": "object",
                        "additionalProperties": {"type": "string"},
                    },
                    {"type": "null"},
                ],
            },
        },
        "additionalProperties": False,
        "required": ["query", "mode", "filters", "window"],
    }


def test_tool_schema_expect_generates_output_schema_from_return_type() -> None:
    """tool return annotation도 model-facing JSON schema로 검증되고 보존된다."""

    @Agent()
    class SearchAgent:
        @agent_tool(schema_name="docs.result")
        def result(self, status: ExitCode) -> SearchResult | str:
            if status == ExitCode.OK:
                return SearchResult(title="ok", scores={})
            return "failed"

        async def execute(
            self,
            command: str,
        ) -> AsyncGenerator[AgentYield[Final[str]], None]:
            yield AgentYield(
                kind=AgentYieldKind.FINAL,
                payload=Final(output=command, metadata={}),
            )

    descriptor = Agent.get(SearchAgent).tool_catalog.by_schema_name("docs.result")

    assert descriptor.schema.input_schema["properties"] == {
        "status": {"enum": [0, 1], "type": "integer"},
    }
    assert descriptor.schema.output_schema == {
        "title": "docs.result.output",
        "anyOf": [
            {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "scores": {
                        "type": "object",
                        "additionalProperties": {"type": "number"},
                    },
                    "filter_": {
                        "anyOf": [
                            {
                                "type": "object",
                                "properties": {
                                    "tags": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                    },
                                    "limit": {"type": "integer"},
                                },
                                "additionalProperties": False,
                                "required": ["tags"],
                            },
                            {"type": "null"},
                        ],
                    },
                },
                "additionalProperties": False,
                "required": ["title", "scores"],
            },
            {"type": "string"},
        ],
    }


def test_tool_schema_expect_accepts_variadic_tuple_as_array_items() -> None:
    """tuple[T, ...]는 동일 item type의 배열 schema로 표현한다."""

    @Agent()
    class PathAgent:
        @agent_tool(schema_name="path.parts")
        def join(self, parts: tuple[str, ...]) -> str:
            return "/".join(parts)

        async def execute(
            self,
            command: str,
        ) -> AsyncGenerator[AgentYield[Final[str]], None]:
            yield AgentYield(
                kind=AgentYieldKind.FINAL,
                payload=Final(output=command, metadata={}),
            )

    descriptor = Agent.get(PathAgent).tool_catalog.by_schema_name("path.parts")

    assert descriptor.schema.input_schema["properties"] == {
        "parts": {"type": "array", "items": {"type": "string"}},
    }


def test_tool_schema_expect_omits_required_for_defaulted_parameters() -> None:
    """default가 있는 parameter는 required 목록에 넣지 않는다."""

    @Agent()
    class PingAgent:
        @agent_tool(schema_name="agent.ping")
        def ping(self, verbose: bool = False) -> None:
            return None

        async def execute(
            self,
            command: str,
        ) -> AsyncGenerator[AgentYield[Final[str]], None]:
            yield AgentYield(
                kind=AgentYieldKind.FINAL,
                payload=Final(output=command, metadata={}),
            )

    descriptor = Agent.get(PingAgent).tool_catalog.by_schema_name("agent.ping")

    assert descriptor.schema.input_schema == {
        "type": "object",
        "title": "agent.ping.input",
        "properties": {"verbose": {"type": "boolean"}},
        "additionalProperties": False,
    }
    assert descriptor.schema.output_schema == {
        "title": "agent.ping.output",
        "type": "null",
    }


def test_tool_schema_expect_omits_dataclass_required_when_fields_have_defaults() -> (
    None
):
    """dataclass field default도 nested required 목록에서 제외한다."""

    @Agent()
    class DefaultedDataclassAgent:
        @agent_tool(schema_name="agent.defaulted")
        def inspect(self, filter_: DefaultedFilter) -> str:
            return str(filter_.enabled)

        async def execute(
            self,
            command: str,
        ) -> AsyncGenerator[AgentYield[Final[str]], None]:
            yield AgentYield(
                kind=AgentYieldKind.FINAL,
                payload=Final(output=command, metadata={}),
            )

    descriptor = Agent.get(DefaultedDataclassAgent).tool_catalog.by_schema_name(
        "agent.defaulted"
    )

    assert descriptor.schema.input_schema["properties"] == {
        "filter_": {
            "type": "object",
            "properties": {"enabled": {"type": "boolean"}},
            "additionalProperties": False,
        },
    }


def test_tool_schema_expect_preserves_mixed_json_primitive_enum_values() -> None:
    """mixed primitive enum은 enum 값만 보존하고 단일 type을 강제하지 않는다."""

    @Agent()
    class MixedEnumAgent:
        @agent_tool(schema_name="agent.mixed")
        def inspect(self, value: MixedJsonEnum) -> str:
            return value.name

        async def execute(
            self,
            command: str,
        ) -> AsyncGenerator[AgentYield[Final[str]], None]:
            yield AgentYield(
                kind=AgentYieldKind.FINAL,
                payload=Final(output=command, metadata={}),
            )

    descriptor = Agent.get(MixedEnumAgent).tool_catalog.by_schema_name("agent.mixed")

    assert descriptor.schema.input_schema["properties"] == {
        "value": {"enum": [True, 0.5, None]},
    }


def test_tool_schema_expect_rejects_untyped_and_unsupported_signatures() -> None:
    """Any/untyped/unsupported 타입은 Agent definition 단계에서 custom error로 실패한다."""
    with pytest.raises(AgentDefinitionError):

        @Agent()
        class UntypedToolAgent:
            @agent_tool(schema_name="invalid.untyped")
            def invalid(self, value) -> str:
                return value

            async def execute(
                self,
                command: str,
            ) -> AsyncGenerator[AgentYield[Final[str]], None]:
                yield AgentYield(
                    kind=AgentYieldKind.FINAL,
                    payload=Final(output=command, metadata={}),
                )

    with pytest.raises(AgentDefinitionError):

        @Agent()
        class AnyToolAgent:
            @agent_tool(schema_name="invalid.any")
            def invalid(self, value: typing.Any) -> str:
                return value

            async def execute(
                self,
                command: str,
            ) -> AsyncGenerator[AgentYield[Final[str]], None]:
                yield AgentYield(
                    kind=AgentYieldKind.FINAL,
                    payload=Final(output=command, metadata={}),
                )

    with pytest.raises(AgentDefinitionError):

        @Agent()
        class ObjectToolAgent:
            @agent_tool(schema_name="invalid.object")
            def invalid(self, value: object) -> object:
                return value

            async def execute(
                self,
                command: str,
            ) -> AsyncGenerator[AgentYield[Final[str]], None]:
                yield AgentYield(
                    kind=AgentYieldKind.FINAL,
                    payload=Final(output=command, metadata={}),
                )


def test_tool_schema_expect_rejects_untyped_mapping_and_non_string_keys() -> None:
    """mapping은 string key와 typed value를 명시해야 model schema가 안전하다."""
    with pytest.raises(AgentDefinitionError):

        @Agent()
        class UntypedMappingAgent:
            @agent_tool(schema_name="invalid.dict")
            def invalid(self, value: dict) -> str:
                return str(value)

            async def execute(
                self,
                command: str,
            ) -> AsyncGenerator[AgentYield[Final[str]], None]:
                yield AgentYield(
                    kind=AgentYieldKind.FINAL,
                    payload=Final(output=command, metadata={}),
                )

    with pytest.raises(AgentDefinitionError):

        @Agent()
        class NumericKeyMappingAgent:
            @agent_tool(schema_name="invalid.keys")
            def invalid(self, value: dict[int, str]) -> str:
                return str(value)

            async def execute(
                self,
                command: str,
            ) -> AsyncGenerator[AgentYield[Final[str]], None]:
                yield AgentYield(
                    kind=AgentYieldKind.FINAL,
                    payload=Final(output=command, metadata={}),
                )


def test_tool_schema_expect_rejects_parameters_without_object_schema() -> None:
    """positional-only/varargs/varkw는 object argument schema로 표현하지 않는다."""
    with pytest.raises(AgentDefinitionError):

        @Agent()
        class PositionalOnlyToolAgent:
            @agent_tool(schema_name="invalid.positional")
            def invalid(self, value: str, /) -> str:
                return value

            async def execute(
                self,
                command: str,
            ) -> AsyncGenerator[AgentYield[Final[str]], None]:
                yield AgentYield(
                    kind=AgentYieldKind.FINAL,
                    payload=Final(output=command, metadata={}),
                )

    with pytest.raises(AgentDefinitionError):

        @Agent()
        class VarargsToolAgent:
            @agent_tool(schema_name="invalid.varargs")
            def invalid(self, *values: str) -> str:
                return ",".join(values)

            async def execute(
                self,
                command: str,
            ) -> AsyncGenerator[AgentYield[Final[str]], None]:
                yield AgentYield(
                    kind=AgentYieldKind.FINAL,
                    payload=Final(output=command, metadata={}),
                )

    with pytest.raises(AgentDefinitionError):

        @Agent()
        class VarkwToolAgent:
            @agent_tool(schema_name="invalid.varkw")
            def invalid(self, **values: str) -> str:
                return str(values)

            async def execute(
                self,
                command: str,
            ) -> AsyncGenerator[AgentYield[Final[str]], None]:
                yield AgentYield(
                    kind=AgentYieldKind.FINAL,
                    payload=Final(output=command, metadata={}),
                )


def test_tool_schema_expect_rejects_missing_return_and_bad_enum_values() -> None:
    """return type과 enum 값도 schema-compatible 계약을 가져야 한다."""
    with pytest.raises(AgentDefinitionError):

        @Agent()
        class MissingReturnToolAgent:
            @agent_tool(schema_name="invalid.return")
            def invalid(self, value: str):
                return value

            async def execute(
                self,
                command: str,
            ) -> AsyncGenerator[AgentYield[Final[str]], None]:
                yield AgentYield(
                    kind=AgentYieldKind.FINAL,
                    payload=Final(output=command, metadata={}),
                )

    class BadEnum(Enum):
        VALUE = ("not", "json", "primitive")

    with pytest.raises(AgentDefinitionError):

        @Agent()
        class BadEnumToolAgent:
            @agent_tool(schema_name="invalid.enum")
            def invalid(self, value: BadEnum) -> str:
                return value.name

            async def execute(
                self,
                command: str,
            ) -> AsyncGenerator[AgentYield[Final[str]], None]:
                yield AgentYield(
                    kind=AgentYieldKind.FINAL,
                    payload=Final(output=command, metadata={}),
                )


def test_tool_schema_expect_rejects_unresolved_annotations() -> None:
    """forward reference를 해소할 수 없으면 bootstrap 전 custom error로 실패한다."""
    scope = _agent_definition_exec_scope()
    with pytest.raises(AgentDefinitionError):
        exec(
            """
@Agent()
class UnresolvedToolAgent:
    @agent_tool(schema_name="invalid.forward")
    def invalid(self, value: "MissingToolType") -> str:
        return value

    async def execute(
        self,
        command: str,
    ) -> AsyncGenerator[AgentYield[Final[str]], None]:
        yield AgentYield(
            kind=AgentYieldKind.FINAL,
            payload=Final(output=command, metadata={}),
        )
""",
            scope,
            scope,
        )


def test_tool_schema_expect_rejects_unresolved_dataclass_fields() -> None:
    """dataclass field annotation도 schema generation 전에 해소되어야 한다."""
    scope = _agent_definition_exec_scope()
    with pytest.raises(AgentDefinitionError):
        exec(
            """
@dataclass(frozen=True, slots=True)
class BrokenDataclass:
    value: "MissingFieldType"


@Agent()
class BrokenDataclassToolAgent:
    @agent_tool(schema_name="invalid.dataclass")
    def invalid(self, value: BrokenDataclass) -> str:
        return str(value)

    async def execute(
        self,
        command: str,
    ) -> AsyncGenerator[AgentYield[Final[str]], None]:
        yield AgentYield(
            kind=AgentYieldKind.FINAL,
            payload=Final(output=command, metadata={}),
        )
""",
            scope,
            scope,
        )


def _agent_definition_exec_scope() -> dict[str, object]:
    return {
        "Agent": Agent,
        "agent_tool": agent_tool,
        "dataclass": dataclass,
        "AsyncGenerator": AsyncGenerator,
        "AgentYield": AgentYield,
        "AgentYieldKind": AgentYieldKind,
        "Final": Final,
    }


def test_tool_catalog_expect_preserves_owner_callable_schema_and_metadata() -> None:
    """descriptor가 owner, callable, schema handle, approval metadata를 보존한다."""

    @Agent()
    class ShellAgent:
        @agent_tool(
            schema_name="shell.run",
            effects=ToolEffects.external_side_effect(),
            idempotency=Idempotency.NON_IDEMPOTENT,
            approval=ToolApprovalRequirement.REQUIRED,
        )
        def run_shell(self, command: str) -> str:
            return command

        async def execute(
            self,
            command: str,
        ) -> AsyncGenerator[AgentYield[Final[str]], None]:
            yield AgentYield(
                kind=AgentYieldKind.FINAL,
                payload=Final(output=command, metadata={}),
            )

    descriptor = Agent.get(ShellAgent).tool_catalog.by_schema_name("shell.run")

    assert descriptor.owner is ShellAgent
    assert descriptor.callable is ShellAgent.run_shell
    assert descriptor.identity == AgentToolIdentity(
        owner_module=__name__,
        owner_qualname="test_tool_catalog_expect_preserves_owner_callable_schema_and_metadata.<locals>.ShellAgent",
        name="run_shell",
    )
    assert descriptor.schema.input_schema_name == "shell.run.input"
    assert descriptor.schema.output_schema_name == "shell.run.output"
    assert descriptor.metadata.effects == ToolEffects.external_side_effect()
    assert descriptor.metadata.idempotency == Idempotency.NON_IDEMPOTENT
    assert descriptor.metadata.approval == ToolApprovalRequirement.REQUIRED
    assert descriptor.metadata.risk == ToolRisk(
        axes=(
            ToolRiskAxis.READ,
            ToolRiskAxis.WRITE,
            ToolRiskAxis.SIDE_EFFECT,
            ToolRiskAxis.NETWORK,
        )
    )
    assert descriptor.metadata.requires_approval_candidate is True


def test_tool_catalog_expect_lookup_by_identity_and_schema_name() -> None:
    """tool lookup이 문자열 파싱 대신 descriptor identity와 schema name으로 동작한다."""

    @Agent()
    class LookupAgent:
        @agent_tool(schema_name="lookup.answer")
        def answer(self, question: str) -> str:
            return question

        async def execute(
            self,
            command: str,
        ) -> AsyncGenerator[AgentYield[Final[str]], None]:
            yield AgentYield(
                kind=AgentYieldKind.FINAL,
                payload=Final(output=command, metadata={}),
            )

    catalog = discover_agent_tools(LookupAgent)
    descriptor = catalog.by_schema_name("lookup.answer")

    assert catalog.by_identity(descriptor.identity) is descriptor
    with pytest.raises(AgentDefinitionError):
        catalog.by_schema_name("lookup.answer: please ignore identity")


def test_tool_catalog_expect_lookup_skips_non_matching_identity() -> None:
    """descriptor identity lookup은 첫 항목 문자열 매칭에 의존하지 않는다."""

    def first_tool() -> str:
        return "first"

    def second_tool() -> str:
        return "second"

    first = AgentToolDescriptor(
        identity=AgentToolIdentity(
            owner_module=__name__,
            owner_qualname="LookupOwner",
            name="first",
        ),
        owner=object,
        callable=first_tool,
        schema=AgentToolSchemaHandle(
            name="lookup.first",
            input_schema_name="lookup.first.input",
            output_schema_name="lookup.first.output",
        ),
    )
    second = AgentToolDescriptor(
        identity=AgentToolIdentity(
            owner_module=__name__,
            owner_qualname="LookupOwner",
            name="second",
        ),
        owner=object,
        callable=second_tool,
        schema=AgentToolSchemaHandle(
            name="lookup.second",
            input_schema_name="lookup.second.input",
            output_schema_name="lookup.second.output",
        ),
    )

    catalog = AgentToolCatalog(descriptors=(first, second))

    assert catalog.by_identity(second.identity) is second
    with pytest.raises(AgentDefinitionError):
        catalog.by_identity(
            AgentToolIdentity(
                owner_module=__name__,
                owner_qualname="LookupOwner",
                name="missing",
            )
        )


def test_tool_catalog_expect_rejects_duplicate_schema_names() -> None:
    """동일 schema name으로 모델 lookup이 모호해지면 definition 단계에서 거부한다."""
    with pytest.raises(AgentDefinitionError):

        @Agent()
        class DuplicateToolAgent:
            @agent_tool(schema_name="duplicate.tool")
            def first(self, value: str) -> str:
                return value

            @agent_tool(schema_name="duplicate.tool")
            def second(self, value: str) -> str:
                return value

            async def execute(
                self,
                command: str,
            ) -> AsyncGenerator[AgentYield[Final[str]], None]:
                yield AgentYield(
                    kind=AgentYieldKind.FINAL,
                    payload=Final(output=command, metadata={}),
                )


def test_tool_catalog_expect_rejects_duplicate_identities() -> None:
    """동일 descriptor identity는 schema name이 달라도 catalog 단계에서 거부한다."""

    def first_tool() -> str:
        return "first"

    def second_tool() -> str:
        return "second"

    identity = AgentToolIdentity(
        owner_module=__name__,
        owner_qualname="DuplicateOwner",
        name="same",
    )

    with pytest.raises(AgentDefinitionError):
        AgentToolCatalog(
            descriptors=(
                AgentToolDescriptor(
                    identity=identity,
                    owner=object,
                    callable=first_tool,
                    schema=AgentToolSchemaHandle(
                        name="duplicate.first",
                        input_schema_name="duplicate.first.input",
                        output_schema_name="duplicate.first.output",
                    ),
                ),
                AgentToolDescriptor(
                    identity=identity,
                    owner=object,
                    callable=second_tool,
                    schema=AgentToolSchemaHandle(
                        name="duplicate.second",
                        input_schema_name="duplicate.second.input",
                        output_schema_name="duplicate.second.output",
                    ),
                ),
            )
        )


def test_agent_tool_expect_rejects_blank_names() -> None:
    """tool identity와 schema handle은 blank 문자열을 허용하지 않는다."""
    with pytest.raises(AgentDefinitionError):

        @agent_tool(name=" ")
        def invalid_tool(value: str) -> str:
            return value


def test_agent_tool_expect_rejects_invalid_metadata_values() -> None:
    """risk/approval metadata value object는 정의 시점에 잘못된 값을 거부한다."""
    with pytest.raises(AgentDefinitionError):
        ToolPermission(" ")
    with pytest.raises(AgentDefinitionError):
        TimeoutPolicy(seconds=0)
    with pytest.raises(AgentDefinitionError):
        ResultBudget(max_bytes=0)
    with pytest.raises(AgentDefinitionError):

        @agent_tool(description=" ")
        def blank_description(value: str) -> str:
            return value


def test_agent_tool_expect_derives_effect_defaults_and_overrides() -> None:
    """effects shortcut과 explicit data boundary override를 metadata에 반영한다."""

    @agent_tool(
        effects=ToolEffects.write_state(),
        data_access=DataAccess.READ_WRITE,
        externality=Externality.EXTERNAL,
    )
    def mutate_workspace(value: str) -> str:
        return value

    definition = get_agent_tool_definition(mutate_workspace)

    assert definition is not None
    assert definition.metadata.effects == ToolEffects.write_state()
    assert definition.metadata.data_access == DataAccess.READ_WRITE
    assert definition.metadata.externality == Externality.EXTERNAL
    assert definition.metadata.risk == ToolRisk(
        axes=(
            ToolRiskAxis.READ,
            ToolRiskAxis.WRITE,
            ToolRiskAxis.SIDE_EFFECT,
            ToolRiskAxis.NETWORK,
        )
    )


def test_agent_tool_expect_represents_destructive_network_risk_axes() -> None:
    """ToolRisk가 read/write/side-effect/destructive/network 축을 표현한다."""

    @agent_tool(
        effects=ToolEffects.destructive_action(),
        data_access=DataAccess.READ_WRITE,
    )
    def delete_workspace(value: str) -> str:
        return value

    definition = get_agent_tool_definition(delete_workspace)

    assert definition is not None
    assert definition.metadata.risk == ToolRisk(
        axes=(
            ToolRiskAxis.READ,
            ToolRiskAxis.WRITE,
            ToolRiskAxis.SIDE_EFFECT,
            ToolRiskAxis.DESTRUCTIVE,
            ToolRiskAxis.NETWORK,
        )
    )
    assert definition.metadata.requires_approval_candidate is True


def test_agent_tool_expect_rejects_duplicate_risk_axes() -> None:
    """ToolRisk 직접 생성 시 중복 축은 정의 오류로 거부한다."""
    with pytest.raises(AgentDefinitionError):
        ToolRisk(axes=(ToolRiskAxis.READ, ToolRiskAxis.READ))


def test_agent_tool_expect_approval_is_candidate_not_global_requirement() -> None:
    """approval metadata는 위험 후보를 표현하지만 모든 tool에 강제되지 않는다."""

    @agent_tool(effects=ToolEffects.read_only())
    def read_workspace(value: str) -> str:
        return value

    @agent_tool(
        effects=ToolEffects.write_state(),
        approval=ToolApprovalRequirement.NOT_REQUIRED,
    )
    def trusted_write(value: str) -> str:
        return value

    read_definition = get_agent_tool_definition(read_workspace)
    write_definition = get_agent_tool_definition(trusted_write)

    assert read_definition is not None
    assert write_definition is not None
    assert read_definition.metadata.requires_approval_candidate is False
    assert write_definition.metadata.risk.includes(ToolRiskAxis.SIDE_EFFECT) is True
    assert write_definition.metadata.requires_approval_candidate is False


def test_agent_tool_expect_idempotency_drives_resume_decision() -> None:
    """idempotency metadata가 resume 중복 실행 판단에 쓰이는 형태로 저장된다."""

    @agent_tool(idempotency=Idempotency.IDEMPOTENT)
    def read_file(value: str) -> str:
        return value

    @agent_tool(idempotency=Idempotency.NON_IDEMPOTENT)
    def write_file(value: str) -> str:
        return value

    read_definition = get_agent_tool_definition(read_file)
    write_definition = get_agent_tool_definition(write_file)

    assert read_definition is not None
    assert write_definition is not None
    assert read_definition.metadata.resume.action_for_completed_boundary() == (
        ToolResumeAction.SKIP_COMPLETED
    )
    assert read_definition.metadata.resume.action_for_incomplete_boundary() == (
        ToolResumeAction.RETRY
    )
    assert write_definition.metadata.resume.action_for_incomplete_boundary() == (
        ToolResumeAction.REQUIRE_APPROVAL
    )


def test_agent_tool_expect_rejects_corrupt_attached_metadata() -> None:
    """decorator metadata slot이 오염되면 discovery 전에 custom error로 중단한다."""

    def corrupt_tool(value: str) -> str:
        return value

    corrupt_tool.__dict__[AGENT_TOOL_DEFINITION_KEY] = object()

    with pytest.raises(AgentDefinitionError):
        get_agent_tool_definition(corrupt_tool)


def test_agent_tool_expect_discovers_static_and_class_methods() -> None:
    """staticmethod/classmethod wrapper 안의 decorated function도 discovery한다."""

    @Agent()
    class WrappedToolAgent:
        @staticmethod
        @agent_tool(schema_name="wrapped.static")
        def static_tool(value: str) -> str:
            return value

        @classmethod
        @agent_tool(schema_name="wrapped.class")
        def class_tool(cls, value: str) -> str:
            return value

        async def execute(
            self,
            command: str,
        ) -> AsyncGenerator[AgentYield[Final[str]], None]:
            yield AgentYield(
                kind=AgentYieldKind.FINAL,
                payload=Final(output=command, metadata={}),
            )

    catalog = Agent.get(WrappedToolAgent).tool_catalog

    assert [descriptor.schema.name for descriptor in catalog.descriptors] == [
        "wrapped.class",
        "wrapped.static",
    ]


def test_agent_tool_expect_subclass_override_hides_base_tool() -> None:
    """subclass override는 상위 tool descriptor를 다시 노출하지 않는다."""

    class BaseTools:
        @agent_tool(schema_name="base.secret")
        def read_secret(self, value: str) -> str:
            return value

    def read_secret(self: object, value: str) -> str:
        return value

    restricted_agent = type(
        "RestrictedAgent",
        (BaseTools,),
        {"read_secret": read_secret},
    )

    assert discover_agent_tools(restricted_agent).descriptors == ()


def test_agent_tool_expect_subclass_tool_override_replaces_base_tool() -> None:
    """subclass의 decorated override만 catalog에 남고 base descriptor는 제거된다."""

    class BaseTools:
        @agent_tool(schema_name="workspace.read")
        def read(self, value: str) -> str:
            return value

    @agent_tool(schema_name="workspace.read.custom")
    def read(self: object, value: str) -> str:
        return value

    custom_agent = type("CustomAgent", (BaseTools,), {"read": read})
    catalog = discover_agent_tools(custom_agent)

    assert [descriptor.schema.name for descriptor in catalog.descriptors] == [
        "workspace.read.custom",
    ]
