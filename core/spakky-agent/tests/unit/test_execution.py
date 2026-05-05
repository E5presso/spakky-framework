"""Tests for agent execution contracts."""

from collections.abc import AsyncGenerator, Generator

import pytest
import tests.fixtures.future_agent_app as future_agent_app
import spakky.agent.execution as execution_module

from spakky.core.pod.annotations.pod import Pod

from spakky.agent import (
    Agent,
    AgentDefinitionError,
    AgentExecutionLimits,
    AgentExecutionSpec,
    AgentYield,
    AgentYieldKind,
    Final,
    AgentSignalKind,
    RecoveryStrategy,
    StreamingExposureMode,
)


def test_agent_execution_spec_expect_defaults_are_non_durable_and_balanced() -> None:
    """기본 실행 spec은 production persistence fallback을 암시하지 않는다."""
    spec = AgentExecutionSpec()

    assert spec.accepted_signals == ()
    assert spec.name is None
    assert spec.objective is None
    assert spec.recovery == RecoveryStrategy.NONE
    assert spec.streaming_exposure_mode == StreamingExposureMode.BALANCED
    assert spec.timeout_seconds is None
    assert spec.limits == AgentExecutionLimits()
    assert spec.delegation_allowed is False
    assert spec.metadata == {}


def test_agent_execution_spec_expect_declares_business_semantics() -> None:
    """실행 spec이 DI로 정해지는 infra capability가 아닌 보조 의미를 담는다."""
    spec = AgentExecutionSpec(
        name="support_agent",
        objective="resolve support tickets",
        limits=AgentExecutionLimits(timeout_seconds=30),
    )

    assert spec.name == "support_agent"
    assert spec.objective == "resolve support tickets"
    assert spec.limits.timeout_seconds == 30


def test_agent_execution_spec_expect_accepts_adr_signal_vocabulary() -> None:
    """ADR-0009의 signal vocabulary를 tuple 계약으로 표현한다."""
    spec = AgentExecutionSpec(
        accepted_signals=(
            AgentSignalKind.USER_MESSAGE,
            AgentSignalKind.APPROVAL_DECISION,
            AgentSignalKind.CANCEL,
        ),
        recovery=RecoveryStrategy.ACTION_BOUNDARY,
    )

    assert spec.accepted_signals == (
        AgentSignalKind.USER_MESSAGE,
        AgentSignalKind.APPROVAL_DECISION,
        AgentSignalKind.CANCEL,
    )
    assert spec.recovery == RecoveryStrategy.ACTION_BOUNDARY


def test_agent_execution_spec_expect_rejects_non_positive_timeout() -> None:
    """bootstrap 전 definition 단계에서 잘못된 timeout을 custom error로 거부한다."""
    with pytest.raises(AgentDefinitionError):
        AgentExecutionSpec(timeout_seconds=0)


def test_agent_execution_limits_expect_rejects_non_positive_timeout() -> None:
    """limits가 잘못된 실행 경계를 custom error로 거부한다."""
    with pytest.raises(AgentDefinitionError):
        AgentExecutionLimits(timeout_seconds=0)


def test_agent_expect_is_pod_stereotype_with_execution_spec_metadata() -> None:
    """Agent stereotype이 Pod metadata와 execution spec을 함께 보존한다."""
    spec = AgentExecutionSpec(delegation_allowed=True)

    @Agent(spec=spec)
    class SampleAgent:
        async def execute(
            self,
            command: str,
        ) -> AsyncGenerator[AgentYield[Final[str]], None]:
            yield AgentYield(
                kind=AgentYieldKind.FINAL,
                payload=Final(output=command, metadata={}),
            )

    agent = Agent.get(SampleAgent)

    assert agent.spec is spec
    assert agent.type_ is SampleAgent
    assert agent.name == "sample_agent"


def test_agent_expect_accepts_sync_generator_execute_contract() -> None:
    """execute가 sync Generator[AgentYield[T], None, None] 계약도 표현한다."""

    @Agent()
    class SyncGeneratorAgent:
        def execute(
            self,
            command: str,
        ) -> Generator[AgentYield[Final[str]], None, None]:
            yield AgentYield(
                kind=AgentYieldKind.FINAL,
                payload=Final(output=command, metadata={}),
            )

    agent = Agent.get(SyncGeneratorAgent)

    assert agent.type_ is SyncGeneratorAgent


def test_agent_expect_accepts_non_generator_direct_result_contract() -> None:
    """non-generator execute는 streaming이 아닌 직접 결과 계약으로 허용한다."""

    @Agent()
    class DirectResultAgent:
        def execute(self, command: str) -> str:
            return command

    agent = Agent.get(DirectResultAgent)

    assert agent.type_ is DirectResultAgent


def test_agent_expect_wraps_pod_constructor_di_metadata() -> None:
    """Agent가 UseCase처럼 constructor DI dependency metadata를 가진다."""

    @Pod()
    class AgentTools: ...

    @Agent()
    class SampleAgent:
        def __init__(self, tools: AgentTools) -> None:
            self.tools = tools

        async def execute(
            self,
            command: str,
        ) -> AsyncGenerator[AgentYield[Final[str]], None]:
            yield AgentYield(
                kind=AgentYieldKind.FINAL,
                payload=Final(output=command, metadata={}),
            )

    agent = Agent.get(SampleAgent)

    assert agent.dependencies["tools"].type_ is AgentTools


def test_agent_expect_rejects_missing_execute_contract() -> None:
    """execute가 없는 class는 definition 단계에서 custom error로 거부한다."""
    with pytest.raises(AgentDefinitionError):

        @Agent()
        class MissingExecute: ...


def test_agent_expect_rejects_non_agent_yield_return_type() -> None:
    """execute stream이 AgentYield를 내지 않으면 custom error로 거부한다."""
    with pytest.raises(AgentDefinitionError):

        @Agent()
        class InvalidReturnAgent:
            async def execute(self, command: str) -> AsyncGenerator[str, None]:
                yield command


def test_agent_execution_spec_expect_rejects_blank_name() -> None:
    """name은 공백 문자열일 수 없다."""
    with pytest.raises(AgentDefinitionError):
        AgentExecutionSpec(name=" ")


def test_agent_execution_spec_expect_rejects_blank_objective() -> None:
    """objective는 공백 문자열일 수 없다."""
    with pytest.raises(AgentDefinitionError):
        AgentExecutionSpec(objective=" ")


def test_agent_execution_spec_expect_rejects_conflicting_timeout_declarations() -> None:
    """legacy timeout과 limits timeout이 동시에 다르면 거부한다."""
    with pytest.raises(AgentDefinitionError):
        AgentExecutionSpec(
            timeout_seconds=10,
            limits=AgentExecutionLimits(timeout_seconds=20),
        )


def test_agent_expect_rejects_non_class_target() -> None:
    """Agent stereotype은 class target에만 적용된다."""

    def factory() -> str:
        return "agent"

    with pytest.raises(AgentDefinitionError):
        Agent()(factory)


def test_agent_expect_wraps_invalid_pod_metadata_as_definition_error() -> None:
    """Pod metadata 분석 실패도 agent definition custom error로 감싼다."""
    with pytest.raises(AgentDefinitionError):

        @Agent()
        class UntypedConstructorAgent:
            def __init__(self, dependency) -> None:
                self.dependency = dependency

            async def execute(
                self,
                command: str,
            ) -> AsyncGenerator[AgentYield[Final[str]], None]:
                yield AgentYield(
                    kind=AgentYieldKind.FINAL,
                    payload=Final(output=command, metadata={}),
                )


def test_agent_expect_rejects_static_execute() -> None:
    """execute는 self를 받는 instance method여야 한다."""
    with pytest.raises(AgentDefinitionError):

        @Agent()
        class StaticExecuteAgent:
            @staticmethod
            async def execute(
                command: str,
            ) -> AsyncGenerator[AgentYield[Final[str]], None]:
                yield AgentYield(
                    kind=AgentYieldKind.FINAL,
                    payload=Final(output=command, metadata={}),
                )


def test_agent_expect_rejects_positional_only_execute_parameter() -> None:
    """execute 인자는 positional-only를 사용할 수 없다."""
    with pytest.raises(AgentDefinitionError):

        @Agent()
        class PositionalOnlyAgent:
            async def execute(
                self,
                command: str,
                /,
            ) -> AsyncGenerator[AgentYield[Final[str]], None]:
                yield AgentYield(
                    kind=AgentYieldKind.FINAL,
                    payload=Final(output=command, metadata={}),
                )


def test_agent_expect_rejects_varargs_execute_parameter() -> None:
    """execute는 variable arguments를 사용할 수 없다."""
    with pytest.raises(AgentDefinitionError):

        @Agent()
        class VarargsAgent:
            async def execute(
                self,
                *commands: str,
            ) -> AsyncGenerator[AgentYield[Final[str]], None]:
                yield AgentYield(
                    kind=AgentYieldKind.FINAL,
                    payload=Final(output=commands[0], metadata={}),
                )


def test_agent_expect_rejects_untyped_execute_parameter() -> None:
    """execute 인자는 타입 어노테이션을 가져야 한다."""
    with pytest.raises(AgentDefinitionError):

        @Agent()
        class UntypedExecuteParameterAgent:
            async def execute(
                self,
                command,
            ) -> AsyncGenerator[AgentYield[Final[str]], None]:
                yield AgentYield(
                    kind=AgentYieldKind.FINAL,
                    payload=Final(output=command, metadata={}),
                )


def test_agent_expect_rejects_missing_execute_return_type() -> None:
    """execute return annotation은 필수다."""
    with pytest.raises(AgentDefinitionError):

        @Agent()
        class MissingReturnTypeAgent:
            async def execute(self, command: str):
                yield command


def test_agent_expect_rejects_generator_with_non_none_send_type() -> None:
    """execute generator는 inbound adapter가 send 값을 주입하지 않는 계약이다."""
    with pytest.raises(AgentDefinitionError):

        @Agent()
        class GeneratorSendAgent:
            def execute(
                self,
                command: str,
            ) -> Generator[AgentYield[Final[str]], str, None]:
                yielded = AgentYield(
                    kind=AgentYieldKind.FINAL,
                    payload=Final(output=command, metadata={}),
                )
                yield yielded


def test_agent_expect_rejects_sync_generator_with_return_value_type() -> None:
    """sync execute generator는 StopIteration value를 public output으로 쓰지 않는다."""
    with pytest.raises(AgentDefinitionError):

        @Agent()
        class GeneratorReturnAgent:
            def execute(
                self,
                command: str,
            ) -> Generator[AgentYield[Final[str]], None, str]:
                yield AgentYield(
                    kind=AgentYieldKind.FINAL,
                    payload=Final(output=command, metadata={}),
                )
                return command


def test_agent_expect_rejects_unparameterized_generator_return_type() -> None:
    """execute stream은 yield type을 명시해야 한다."""
    with pytest.raises(AgentDefinitionError):

        @Agent()
        class UnparameterizedGeneratorAgent:
            async def execute(self, command: str) -> AsyncGenerator:
                yield command


def test_agent_expect_resolves_postponed_execute_return_annotation() -> None:
    """future annotations 스타일의 execute 반환 타입도 해석해 검증한다."""
    agent = Agent.get(future_agent_app.FutureAnnotatedAgent)

    assert agent.type_ is future_agent_app.FutureAnnotatedAgent


def test_agent_expect_rejects_unresolvable_execute_return_annotation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """해석 불가능한 지연 반환 타입은 custom definition error로 드러난다."""

    def unresolved_type_hints(
        target: object,
        include_extras: bool = False,
    ) -> dict[str, object]:
        raise NameError(target, include_extras)

    monkeypatch.setattr(execution_module, "get_type_hints", unresolved_type_hints)

    with pytest.raises(AgentDefinitionError):

        @Agent()
        class UnknownReturnAnnotationAgent:
            async def execute(
                self,
                command: str,
            ) -> AsyncGenerator[AgentYield[Final[str]], None]:
                yield AgentYield(
                    kind=AgentYieldKind.FINAL,
                    payload=Final(output=command, metadata={}),
                )
