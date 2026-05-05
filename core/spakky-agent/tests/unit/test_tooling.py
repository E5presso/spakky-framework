"""Tests for agent tool descriptor discovery."""

from collections.abc import AsyncGenerator

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
    agent_tool,
    discover_agent_tools,
)
from spakky.agent.tooling import AGENT_TOOL_DEFINITION_KEY, get_agent_tool_definition


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
