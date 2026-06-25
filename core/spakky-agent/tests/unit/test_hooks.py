"""Tests for declarative @on_signal signal-hook discovery (ADR-0013 §1)."""

from collections.abc import AsyncGenerator
import typing
from typing import override

import pytest

from spakky.agent import (
    AgentSignal,
    AgentSignalKind,
    AgentYield,
    AgentYieldKind,
    Progress,
    on_signal,
)
from spakky.agent.error import AgentDefinitionError
from spakky.agent.hooks import (
    AGENT_SIGNAL_HOOK_DEFINITION_KEY,
    AgentSignalHookCatalog,
    AgentSignalHookDescriptor,
    AgentSignalHookIdentity,
    discover_agent_signal_hooks,
)


def _progress_yield(text: str) -> AgentYield[object]:
    return AgentYield(
        kind=AgentYieldKind.PROGRESS,
        payload=Progress(text, current_step="steering"),
    )


def test_discover_agent_signal_hooks_expect_valid_hook_bound_to_kind() -> None:
    """async-generator @on_signal 메서드는 kind와 함께 descriptor로 발견된다."""

    class Owner:
        @on_signal(AgentSignalKind.STEERING_INSTRUCTION)
        async def react(
            self,
            signal: AgentSignal,
        ) -> AsyncGenerator[AgentYield[object], None]:
            yield _progress_yield(signal.id)

    catalog = discover_agent_signal_hooks(Owner)

    assert len(catalog.descriptors) == 1
    descriptor = catalog.descriptors[0]
    assert descriptor.kind is AgentSignalKind.STEERING_INSTRUCTION
    assert descriptor.identity.member_name == "react"
    assert descriptor.owner is Owner


def test_discover_agent_signal_hooks_expect_non_async_generator_rejected() -> None:
    """@on_signal가 async generator가 아니면 정의 에러로 거부된다."""

    class Owner:
        @on_signal(AgentSignalKind.STEERING_INSTRUCTION)
        def react(self, signal: AgentSignal) -> None:
            return None

    with pytest.raises(AgentDefinitionError):
        discover_agent_signal_hooks(Owner)


def test_discover_agent_signal_hooks_expect_missing_self_rejected() -> None:
    """@on_signal 메서드의 첫 인자가 self가 아니면 인스턴스 메서드 아님으로 거부된다."""

    class Owner:
        @on_signal(AgentSignalKind.STEERING_INSTRUCTION)
        # pyrefly: ignore - 첫 인자 self 누락 거부 검증 (의도적 위반)
        async def react(
            signal: AgentSignal,
        ) -> AsyncGenerator[AgentYield[object], None]:
            yield _progress_yield(signal.id)

    with pytest.raises(AgentDefinitionError):
        discover_agent_signal_hooks(Owner)


def test_discover_agent_signal_hooks_expect_extra_argument_rejected() -> None:
    """signal 외 인자를 받는 @on_signal 메서드는 거부된다."""

    class Owner:
        @on_signal(AgentSignalKind.STEERING_INSTRUCTION)
        async def react(
            self,
            signal: AgentSignal,
            extra: str,
        ) -> AsyncGenerator[AgentYield[object], None]:
            yield _progress_yield(signal.id + extra)

    with pytest.raises(AgentDefinitionError):
        discover_agent_signal_hooks(Owner)


def test_discover_agent_signal_hooks_expect_variadic_argument_rejected() -> None:
    """가변 인자를 쓰는 @on_signal 메서드는 거부된다."""

    class Owner:
        @on_signal(AgentSignalKind.STEERING_INSTRUCTION)
        async def react(
            self,
            *signal: AgentSignal,
        ) -> AsyncGenerator[AgentYield[object], None]:
            yield _progress_yield(signal[0].id)

    with pytest.raises(AgentDefinitionError):
        discover_agent_signal_hooks(Owner)


def test_discover_agent_signal_hooks_expect_missing_annotation_rejected() -> None:
    """signal 인자에 타입 주석이 없으면 거부된다."""

    class Owner:
        @on_signal(AgentSignalKind.STEERING_INSTRUCTION)
        async def react(self, signal) -> AsyncGenerator[AgentYield[object], None]:  # type: ignore[no-untyped-def] - 의도적 미주석 거부 검증
            yield _progress_yield(signal.id)

    with pytest.raises(AgentDefinitionError):
        discover_agent_signal_hooks(Owner)


def test_discover_agent_signal_hooks_expect_wrong_annotation_rejected() -> None:
    """signal 인자가 AgentSignal이 아니면 거부된다."""

    class Owner:
        @on_signal(AgentSignalKind.STEERING_INSTRUCTION)
        async def react(
            self,
            signal: str,
        ) -> AsyncGenerator[AgentYield[object], None]:
            yield _progress_yield(signal)

    with pytest.raises(AgentDefinitionError):
        discover_agent_signal_hooks(Owner)


def test_discover_agent_signal_hooks_expect_missing_return_annotation_rejected() -> (
    None
):
    """반환 타입 주석이 없으면 거부된다."""

    class Owner:
        @on_signal(AgentSignalKind.STEERING_INSTRUCTION)
        async def react(self, signal: AgentSignal):  # type: ignore[no-untyped-def] - 의도적 미주석 거부 검증
            yield _progress_yield(signal.id)

    with pytest.raises(AgentDefinitionError):
        discover_agent_signal_hooks(Owner)


def test_discover_agent_signal_hooks_expect_non_async_generator_return_rejected() -> (
    None
):
    """반환 타입이 AsyncGenerator가 아니면 거부된다."""

    class Owner:
        @on_signal(AgentSignalKind.STEERING_INSTRUCTION)
        # pyrefly: ignore - AsyncGenerator 아닌 반환 타입 거부 검증 (의도적 위반)
        async def react(self, signal: AgentSignal) -> "list[AgentYield[object]]":
            yield _progress_yield(signal.id)

    with pytest.raises(AgentDefinitionError):
        discover_agent_signal_hooks(Owner)


def test_discover_agent_signal_hooks_expect_non_agent_yield_type_rejected() -> None:
    """AsyncGenerator의 yield 타입이 AgentYield가 아니면 거부된다."""

    class Owner:
        @on_signal(AgentSignalKind.STEERING_INSTRUCTION)
        async def react(
            self,
            signal: AgentSignal,
        ) -> AsyncGenerator[str, None]:
            yield signal.id

    with pytest.raises(AgentDefinitionError):
        discover_agent_signal_hooks(Owner)


def test_discover_agent_signal_hooks_expect_unresolvable_annotation_rejected() -> None:
    """해석할 수 없는 주석은 거부된다."""

    class Owner:
        @on_signal(AgentSignalKind.STEERING_INSTRUCTION)
        async def react(
            self,
            # pyrefly: ignore - 미해석 주석 거부 검증 (의도적 위반)
            signal: "MissingType",  # noqa: F821 - 미해석 주석 거부 검증
        ) -> AsyncGenerator[AgentYield[object], None]:
            yield _progress_yield(signal.id)

    with pytest.raises(AgentDefinitionError):
        discover_agent_signal_hooks(Owner)


def test_agent_signal_hook_catalog_expect_duplicate_identity_rejected() -> None:
    """중복 identity를 가진 descriptor는 catalog 생성 시 거부된다."""

    async def react(
        target: object,
        signal: AgentSignal,
    ) -> AsyncGenerator[AgentYield[object], None]:
        yield _progress_yield(signal.id)

    identity = AgentSignalHookIdentity(
        owner_module="m",
        owner_qualname="Owner",
        member_name="react",
    )
    descriptor = AgentSignalHookDescriptor(
        identity=identity,
        owner=object,
        callable=react,
        kind=AgentSignalKind.STEERING_INSTRUCTION,
    )

    with pytest.raises(AgentDefinitionError):
        AgentSignalHookCatalog(descriptors=(descriptor, descriptor))


def test_agent_signal_hook_catalog_expect_hooks_for_filters_by_kind() -> None:
    """hooks_for는 요청 kind에 해당하는 hook만 반환한다."""

    class Owner:
        @on_signal(AgentSignalKind.STEERING_INSTRUCTION)
        async def steer(
            self,
            signal: AgentSignal,
        ) -> AsyncGenerator[AgentYield[object], None]:
            yield _progress_yield(signal.id)

        @on_signal(AgentSignalKind.EXTERNAL_EVENT)
        async def external(
            self,
            signal: AgentSignal,
        ) -> AsyncGenerator[AgentYield[object], None]:
            yield _progress_yield(signal.id)

    catalog = discover_agent_signal_hooks(Owner)

    steering = catalog.hooks_for(AgentSignalKind.STEERING_INSTRUCTION)
    assert [descriptor.identity.member_name for descriptor in steering] == ["steer"]
    assert catalog.hooks_for(AgentSignalKind.USER_MESSAGE) == ()


def test_discover_agent_signal_hooks_expect_subclass_override_wins_over_parent() -> (
    None
):
    """MRO 상에서 동일 멤버명은 가장 파생된 정의가 채택된다."""

    class Parent:
        @on_signal(AgentSignalKind.EXTERNAL_EVENT)
        async def react(
            self,
            signal: AgentSignal,
        ) -> AsyncGenerator[AgentYield[object], None]:
            yield _progress_yield("parent")

    class Child(Parent):
        @override
        @on_signal(AgentSignalKind.STEERING_INSTRUCTION)
        async def react(
            self,
            signal: AgentSignal,
        ) -> AsyncGenerator[AgentYield[object], None]:
            yield _progress_yield("child")

    catalog = discover_agent_signal_hooks(Child)

    assert len(catalog.descriptors) == 1
    assert catalog.descriptors[0].kind is AgentSignalKind.STEERING_INSTRUCTION
    assert catalog.descriptors[0].owner is Child


def test_discover_agent_signal_hooks_expect_inherited_hook_discovered() -> None:
    """부모에 정의된 hook은 자식 클래스 discovery에서도 발견된다."""

    class Parent:
        @on_signal(AgentSignalKind.STEERING_INSTRUCTION)
        async def react(
            self,
            signal: AgentSignal,
        ) -> AsyncGenerator[AgentYield[object], None]:
            yield _progress_yield(signal.id)

    class Child(Parent):
        """Child adds no hook of its own."""

    catalog = discover_agent_signal_hooks(Child)

    assert len(catalog.descriptors) == 1
    assert catalog.descriptors[0].owner is Parent


def test_discover_agent_signal_hooks_expect_invalid_metadata_rejected() -> None:
    """@on_signal 메타데이터 슬롯에 잘못된 값이 박히면 거부된다."""

    class Owner:
        async def react(
            self,
            signal: AgentSignal,
        ) -> AsyncGenerator[AgentYield[object], None]:
            yield _progress_yield(signal.id)

    Owner.react.__dict__[AGENT_SIGNAL_HOOK_DEFINITION_KEY] = "not-a-definition"

    with pytest.raises(AgentDefinitionError):
        discover_agent_signal_hooks(Owner)


def test_discover_agent_signal_hooks_expect_bare_async_generator_rejected() -> None:
    """타입 파라미터 없는 AsyncGenerator 반환 주석은 yield 타입 누락으로 거부된다."""

    class Owner:
        @on_signal(AgentSignalKind.STEERING_INSTRUCTION)
        # pyrefly: ignore - yield 타입 누락 거부 검증 (의도적 위반)
        async def react(self, signal: AgentSignal) -> AsyncGenerator:
            yield _progress_yield(signal.id)

    with pytest.raises(AgentDefinitionError):
        discover_agent_signal_hooks(Owner)


def test_discover_agent_signal_hooks_expect_unparametrized_generic_rejected() -> None:
    """origin은 AsyncGenerator지만 인자가 비면 yield 타입 누락으로 거부된다."""

    class Owner:
        @on_signal(AgentSignalKind.STEERING_INSTRUCTION)
        # pyrefly: ignore - yield 타입 누락 거부 검증 (의도적 위반)
        async def react(self, signal: AgentSignal) -> typing.AsyncGenerator:
            yield _progress_yield(signal.id)

    with pytest.raises(AgentDefinitionError):
        discover_agent_signal_hooks(Owner)
