"""Tests for agent execution contracts."""

from collections.abc import AsyncGenerator, Callable, Generator
from dataclasses import fields
from decimal import Decimal

import pytest
import tests.fixtures.future_agent_app as future_agent_app
import spakky.agent.execution as execution_module

from pydantic import BaseModel

from spakky.core.pod.annotations.pod import Pod


from spakky.agent import (
    Agent,
    AgentCompactionPolicy,
    AgentDefinitionError,
    AgentExecutionLimits,
    AgentExecutionSpec,
    AgentTeammate,
    AgentYield,
    AgentYieldKind,
    Final,
    AgentSignalKind,
    KeepRecentMessagesCompactionStrategy,
    ProviderManagedCompactionStrategy,
    TrimToolResultsCompactionStrategy,
    RecoveryStrategy,
    StreamingExposureMode,
)


def test_agent_execution_spec_expect_defaults_are_non_durable_and_balanced() -> None:
    """기본 실행 spec은 production persistence fallback을 암시하지 않는다."""
    spec = AgentExecutionSpec()

    assert spec.accepted_signals == ()
    assert spec.name is None
    assert spec.objective is None
    assert spec.instructions is None
    assert spec.output_type is None
    assert spec.recovery == RecoveryStrategy.NONE
    assert spec.streaming_exposure_mode == StreamingExposureMode.BALANCED
    assert spec.limits == AgentExecutionLimits()
    assert spec.limits.max_steps == 8
    assert spec.limits.max_tool_calls == 32
    assert spec.limits.max_tokens is None
    assert spec.limits.timeout_seconds is None
    assert spec.teammates == ()
    assert spec.compaction is None
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


def test_agent_execution_spec_expect_has_no_legacy_timeout_alias() -> None:
    """실행 timeout은 limits 한 곳에만 있고 spec alias는 존재하지 않는다."""
    assert "timeout_seconds" not in {
        descriptor.name for descriptor in fields(AgentExecutionSpec)
    }


def test_agent_execution_limits_expect_rejects_non_positive_timeout() -> None:
    """limits가 잘못된 실행 경계를 custom error로 거부한다."""
    with pytest.raises(AgentDefinitionError):
        AgentExecutionLimits(timeout_seconds=0)


@pytest.mark.parametrize(
    "limits",
    [
        AgentExecutionLimits(max_steps=1),
        AgentExecutionLimits(max_tool_calls=1),
        AgentExecutionLimits(max_tokens=1),
        AgentExecutionLimits(max_cost=Decimal("0.01")),
    ],
)
def test_agent_execution_limits_expect_accepts_positive_bounds(
    limits: AgentExecutionLimits,
) -> None:
    """모델 step, 실제 tool dispatch, provider usage 예산을 선언한다."""
    assert limits.max_steps > 0
    assert limits.max_tool_calls > 0


@pytest.mark.parametrize(
    "factory",
    [
        lambda: AgentExecutionLimits(max_steps=0),
        lambda: AgentExecutionLimits(max_tool_calls=0),
        lambda: AgentExecutionLimits(max_tokens=0),
    ],
)
def test_agent_execution_limits_expect_rejects_non_positive_counts(
    factory: Callable[[], AgentExecutionLimits],
) -> None:
    """모든 count/token limit은 양수여야 한다."""
    with pytest.raises(AgentDefinitionError):
        factory()


@pytest.mark.parametrize(
    "max_cost",
    [Decimal("0"), Decimal("-0.01"), Decimal("NaN"), Decimal("Infinity")],
)
def test_agent_execution_limits_expect_rejects_invalid_cost(
    max_cost: Decimal,
) -> None:
    """Cost limits must be positive finite decimals."""
    with pytest.raises(AgentDefinitionError):
        AgentExecutionLimits(max_cost=max_cost)


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


def test_agent_expect_auto_provides_execute_when_absent() -> None:
    """execute 본문이 없으면 프레임워크 runner-backed execute가 자동 제공된다."""
    from spakky.agent.runner import runner_backed_execute

    @Agent()
    class DeclarationOnlyAgent: ...

    assert Agent.get(DeclarationOnlyAgent) is not None
    assert vars(DeclarationOnlyAgent)["execute"] is runner_backed_execute


def test_agent_expect_keeps_user_supplied_execute() -> None:
    """개발자가 execute를 직접 작성하면 자동 제공이 그것을 덮어쓰지 않는다."""
    from spakky.agent.runner import runner_backed_execute

    @Agent()
    class CustomExecuteAgent:
        async def execute(
            self,
            command: str,
        ) -> AsyncGenerator[AgentYield[Final[str]], None]:
            yield AgentYield(
                kind=AgentYieldKind.FINAL,
                payload=Final(output=command, metadata={}),
            )

    assert CustomExecuteAgent.execute is not runner_backed_execute


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


class _SupportTicketResolution(BaseModel):
    """Structured output a support agent declares for resolved tickets."""

    ticket_id: str
    resolved: bool


def test_agent_execution_spec_expect_declares_instructions_and_output_type() -> None:
    """선언형 spec이 시스템 지시와 구조화 출력 타입을 단일 선언점에 담는다."""
    spec = AgentExecutionSpec(
        instructions="Resolve support tickets within policy.",
        output_type=_SupportTicketResolution,
    )

    assert spec.instructions == "Resolve support tickets within policy."
    assert spec.output_type is _SupportTicketResolution


def test_agent_execution_spec_expect_rejects_blank_instructions() -> None:
    """instructions는 공백 문자열일 수 없다."""
    with pytest.raises(AgentDefinitionError):
        AgentExecutionSpec(instructions="   ")


def test_agent_execution_spec_expect_rejects_non_class_output_type() -> None:
    """output_type은 구조화 출력 타입(class)이어야 한다."""
    instance_not_class = _SupportTicketResolution(ticket_id="T-1", resolved=True)
    with pytest.raises(AgentDefinitionError):
        # pyrefly: ignore - 의도적으로 class가 아닌 instance를 전달해 런타임 가드 검증
        AgentExecutionSpec(output_type=instance_not_class)


def test_agent_execution_spec_expect_declares_local_pod_teammate() -> None:
    """teammate를 로컬 @Agent Pod 타입으로 선언해 in-process 위임을 표현한다."""

    @Agent()
    class ResearcherAgent:
        async def execute(
            self,
            command: str,
        ) -> AsyncGenerator[AgentYield[Final[str]], None]:
            yield AgentYield(
                kind=AgentYieldKind.FINAL,
                payload=Final(output=command, metadata={}),
            )

    teammate = AgentTeammate(name="researcher", pod=ResearcherAgent)
    spec = AgentExecutionSpec(teammates=(teammate,))

    assert spec.teammates == (teammate,)
    assert spec.teammates[0].pod is ResearcherAgent
    assert spec.teammates[0].card_url is None


def test_agent_teammate_expect_declares_remote_agent_card_url() -> None:
    """teammate를 원격 AgentCard URL로 선언해 cross-process 위임을 표현한다."""
    teammate = AgentTeammate(
        name="billing",
        card_url="https://billing.internal/.well-known/agent-card.json",
    )

    assert teammate.pod is None
    assert teammate.card_url == "https://billing.internal/.well-known/agent-card.json"


def test_agent_teammate_expect_rejects_blank_name() -> None:
    """teammate name은 공백 문자열일 수 없다."""
    with pytest.raises(AgentDefinitionError):
        AgentTeammate(name=" ", card_url="https://billing.internal/card")


def test_agent_teammate_expect_rejects_declaring_neither_binding() -> None:
    """teammate는 로컬 pod·원격 url 중 하나를 반드시 선언해야 한다."""
    with pytest.raises(AgentDefinitionError):
        AgentTeammate(name="orphan")


def test_agent_teammate_expect_rejects_declaring_both_bindings() -> None:
    """teammate는 로컬 pod와 원격 url을 동시에 선언할 수 없다."""

    @Agent()
    class LocalAgent:
        async def execute(
            self,
            command: str,
        ) -> AsyncGenerator[AgentYield[Final[str]], None]:
            yield AgentYield(
                kind=AgentYieldKind.FINAL,
                payload=Final(output=command, metadata={}),
            )

    with pytest.raises(AgentDefinitionError):
        AgentTeammate(
            name="ambiguous",
            pod=LocalAgent,
            card_url="https://peer.internal/card",
        )


def test_agent_teammate_expect_rejects_non_class_pod() -> None:
    """teammate의 로컬 binding은 class여야 한다."""
    instance_not_class = object()
    with pytest.raises(AgentDefinitionError):
        # pyrefly: ignore - 의도적으로 class가 아닌 instance를 전달해 런타임 가드 검증
        AgentTeammate(name="bad_pod", pod=instance_not_class)


def test_agent_teammate_expect_rejects_non_http_card_url_scheme() -> None:
    """원격 AgentCard URL은 http(s) 스킴이어야 한다."""
    with pytest.raises(AgentDefinitionError):
        AgentTeammate(name="ftp_peer", card_url="ftp://peer.internal/card")


def test_agent_teammate_expect_rejects_card_url_without_host() -> None:
    """원격 AgentCard URL은 호스트(netloc)를 포함해야 한다."""
    with pytest.raises(AgentDefinitionError):
        AgentTeammate(name="hostless", card_url="https:///card")


def test_agent_execution_spec_expect_rejects_duplicate_teammate_names() -> None:
    """teammate roster에 같은 이름이 중복되면 거부한다."""
    with pytest.raises(AgentDefinitionError):
        AgentExecutionSpec(
            teammates=(
                AgentTeammate(name="peer", card_url="https://a.internal/card"),
                AgentTeammate(name="peer", card_url="https://b.internal/card"),
            )
        )


def test_agent_execution_spec_expect_declares_compaction_policy() -> None:
    """spec이 pluggable 전략 체인과 임계치 정책을 선언적으로 보유한다."""
    sliding = KeepRecentMessagesCompactionStrategy(max_messages=10)
    trimming = TrimToolResultsCompactionStrategy(max_characters=2000)
    policy = AgentCompactionPolicy(
        strategies=(trimming, sliding),
        trigger_token_threshold=8000,
    )
    spec = AgentExecutionSpec(compaction=policy)

    assert spec.compaction is policy
    assert spec.compaction.strategies == (trimming, sliding)
    assert spec.compaction.trigger_token_threshold == 8000


def test_agent_compaction_policy_expect_rejects_empty_strategy_chain() -> None:
    """compaction 정책은 최소 하나의 전략을 요구한다."""
    with pytest.raises(AgentDefinitionError):
        AgentCompactionPolicy(strategies=(), trigger_token_threshold=1000)


def test_agent_compaction_policy_expect_rejects_non_positive_threshold() -> None:
    """compaction trigger 임계치는 양수여야 한다."""
    with pytest.raises(AgentDefinitionError):
        AgentCompactionPolicy(
            strategies=(ProviderManagedCompactionStrategy(),),
            trigger_token_threshold=0,
        )


def test_agent_expect_consumes_full_declarative_spec_at_definition() -> None:
    """@Agent(spec=...)가 instructions·output_type·teammates·compaction을 함께 보존한다."""

    @Agent()
    class PlannerAgent:
        async def execute(
            self,
            command: str,
        ) -> AsyncGenerator[AgentYield[Final[str]], None]:
            yield AgentYield(
                kind=AgentYieldKind.FINAL,
                payload=Final(output=command, metadata={}),
            )

    provider_managed = ProviderManagedCompactionStrategy()
    spec = AgentExecutionSpec(
        name="support_agent",
        instructions="Resolve support tickets within policy.",
        output_type=_SupportTicketResolution,
        teammates=(
            AgentTeammate(name="planner", pod=PlannerAgent),
            AgentTeammate(name="billing", card_url="https://billing.internal/card"),
        ),
        compaction=AgentCompactionPolicy(
            strategies=(provider_managed,),
            trigger_token_threshold=16000,
        ),
    )

    @Agent(spec=spec)
    class SupportAgent:
        async def execute(
            self,
            command: str,
        ) -> AsyncGenerator[AgentYield[Final[str]], None]:
            yield AgentYield(
                kind=AgentYieldKind.FINAL,
                payload=Final(output=command, metadata={}),
            )

    agent = Agent.get(SupportAgent)

    assert agent.spec is spec
    assert agent.spec.instructions == "Resolve support tickets within policy."
    assert agent.spec.output_type is _SupportTicketResolution
    assert tuple(teammate.name for teammate in agent.spec.teammates) == (
        "planner",
        "billing",
    )
    assert agent.spec.compaction is not None
    assert agent.spec.compaction.strategies == (provider_managed,)
