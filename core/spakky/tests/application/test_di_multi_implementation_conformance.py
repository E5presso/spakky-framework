from abc import abstractmethod
from typing import Annotated

import pytest

from spakky.core.application.application_context import (
    ApplicationContext,
    NoUniquePodError,
)
from spakky.core.pod.annotations.pod import Pod
from spakky.core.pod.annotations.primary import Primary
from spakky.core.pod.annotations.qualifier import Qualifier


class IConformanceEngine:
    @abstractmethod
    def name(self) -> str: ...


@Pod(name="alpha_engine")
class AlphaConformanceEngine(IConformanceEngine):
    def name(self) -> str:
        return "alpha"


@Pod(name="beta_engine")
class BetaConformanceEngine(IConformanceEngine):
    def name(self) -> str:
        return "beta"


@Primary()
@Pod(name="primary_engine")
class PrimaryConformanceEngine(IConformanceEngine):
    def name(self) -> str:
        return "primary"


@Pod(name="bound_engine")
class BoundConformanceEngine(IConformanceEngine):
    def name(self) -> str:
        return "bound"


@Pod(name="qualified_engine")
class QualifiedConformanceEngine(IConformanceEngine):
    def name(self) -> str:
        return "qualified"


def test_di_multi_implementation_single_ambiguity_expect_candidates_and_hints() -> None:
    context = ApplicationContext()
    context.add(AlphaConformanceEngine)
    context.add(BetaConformanceEngine)

    with pytest.raises(NoUniquePodError) as error:
        context.get(type_=IConformanceEngine)

    assert [candidate.pod_name for candidate in error.value.candidates] == [
        "alpha_engine",
        "beta_engine",
    ]
    assert any(
        "Annotated[T, Qualifier(...)]" in hint for hint in error.value.resolution_hints
    )
    assert any(
        "ApplicationContext.bind" in hint for hint in error.value.resolution_hints
    )
    assert any("@Primary" in hint for hint in error.value.resolution_hints)
    assert any("get(type_, name=...)" in hint for hint in error.value.resolution_hints)


def test_di_multi_implementation_primary_expect_selected_when_unique() -> None:
    context = ApplicationContext()
    context.add(AlphaConformanceEngine)
    context.add(PrimaryConformanceEngine)

    assert context.get(type_=IConformanceEngine).name() == "primary"


def test_di_multi_implementation_multiple_primary_expect_primary_ambiguity() -> None:
    @Primary()
    @Pod(name="secondary_primary_engine")
    class SecondaryPrimaryConformanceEngine(IConformanceEngine):
        def name(self) -> str:
            return "secondary-primary"

    context = ApplicationContext()
    context.add(PrimaryConformanceEngine)
    context.add(SecondaryPrimaryConformanceEngine)
    context.add(AlphaConformanceEngine)

    with pytest.raises(NoUniquePodError) as error:
        context.get(type_=IConformanceEngine)

    assert [candidate.pod_name for candidate in error.value.candidates] == [
        "primary_engine",
        "secondary_primary_engine",
    ]
    assert all(candidate.is_primary for candidate in error.value.candidates)


def test_di_multi_implementation_selection_priority_expect_explicit_before_binding() -> (
    None
):
    context = ApplicationContext()
    context.bind_to_name(IConformanceEngine, "bound_engine")
    context.add(BoundConformanceEngine)
    context.add(QualifiedConformanceEngine)

    selected = context.get(type_=IConformanceEngine, name="qualified_engine")

    assert selected.name() == "qualified"


def test_di_multi_implementation_selection_priority_expect_binding_before_primary_and_legacy() -> (
    None
):
    @Pod()
    class BindingPriorityRunner:
        __engine: IConformanceEngine

        def __init__(self, primary_engine: IConformanceEngine) -> None:
            self.__engine = primary_engine

        def run(self) -> str:
            return self.__engine.name()

    context = ApplicationContext()
    context.bind_to_name(IConformanceEngine, "bound_engine")
    context.add(PrimaryConformanceEngine)
    context.add(BoundConformanceEngine)
    context.add(BindingPriorityRunner)
    context.start()

    assert context.get(type_=BindingPriorityRunner).run() == "bound"


def test_di_multi_implementation_selection_priority_expect_qualifier_before_binding() -> (
    None
):
    @Pod()
    class QualifiedPriorityRunner:
        __engine: IConformanceEngine

        def __init__(
            self,
            engine: Annotated[
                IConformanceEngine,
                Qualifier(lambda pod: pod.name == "qualified_engine"),
            ],
        ) -> None:
            self.__engine = engine

        def run(self) -> str:
            return self.__engine.name()

    context = ApplicationContext()
    context.bind_to_name(IConformanceEngine, "bound_engine")
    context.add(BoundConformanceEngine)
    context.add(QualifiedConformanceEngine)
    context.add(QualifiedPriorityRunner)
    context.start()

    assert context.get(type_=QualifiedPriorityRunner).run() == "qualified"


def test_di_multi_implementation_selection_priority_expect_legacy_after_primary() -> (
    None
):
    @Pod()
    class PrimaryPriorityRunner:
        __engine: IConformanceEngine

        def __init__(self, alpha_engine: IConformanceEngine) -> None:
            self.__engine = alpha_engine

        def run(self) -> str:
            return self.__engine.name()

    context = ApplicationContext()
    context.add(AlphaConformanceEngine)
    context.add(PrimaryConformanceEngine)
    context.add(PrimaryPriorityRunner)
    context.start()

    assert context.get(type_=PrimaryPriorityRunner).run() == "primary"


def test_di_multi_implementation_selection_priority_expect_legacy_when_no_explicit_policy() -> (
    None
):
    @Pod()
    class LegacyPriorityRunner:
        __engine: IConformanceEngine

        def __init__(self, beta_engine: IConformanceEngine) -> None:
            self.__engine = beta_engine

        def run(self) -> str:
            return self.__engine.name()

    context = ApplicationContext()
    context.add(AlphaConformanceEngine)
    context.add(BetaConformanceEngine)
    context.add(LegacyPriorityRunner)
    context.start()

    assert context.get(type_=LegacyPriorityRunner).run() == "beta"


def test_di_multi_implementation_collection_injection_expect_stable_shapes() -> None:
    @Pod()
    class CollectionRunner:
        __engine_list: list[IConformanceEngine]
        __engine_tuple: tuple[IConformanceEngine, ...]
        __engine_dict: dict[str, IConformanceEngine]

        def __init__(
            self,
            engine_list: list[IConformanceEngine],
            engine_tuple: tuple[IConformanceEngine, ...],
            engine_dict: dict[str, IConformanceEngine],
        ) -> None:
            self.__engine_list = engine_list
            self.__engine_tuple = engine_tuple
            self.__engine_dict = engine_dict

        def list_names(self) -> list[str]:
            return [engine.name() for engine in self.__engine_list]

        def tuple_names(self) -> tuple[str, ...]:
            return tuple(engine.name() for engine in self.__engine_tuple)

        def dict_names(self) -> dict[str, str]:
            return {
                pod_name: engine.name()
                for pod_name, engine in self.__engine_dict.items()
            }

    context = ApplicationContext()
    context.add(BetaConformanceEngine)
    context.add(AlphaConformanceEngine)
    context.add(CollectionRunner)
    context.start()

    runner = context.get(type_=CollectionRunner)
    assert runner.list_names() == ["alpha", "beta"]
    assert runner.tuple_names() == ("alpha", "beta")
    assert runner.dict_names() == {
        "alpha_engine": "alpha",
        "beta_engine": "beta",
    }


def test_di_multi_implementation_optional_ambiguity_expect_error() -> None:
    @Pod()
    class OptionalRunner:
        def __init__(self, engine: IConformanceEngine | None) -> None:
            self.engine = engine

    context = ApplicationContext()
    context.add(AlphaConformanceEngine)
    context.add(BetaConformanceEngine)
    context.add(OptionalRunner)

    with pytest.raises(NoUniquePodError):
        context.start()


def test_di_multi_implementation_plugin_adapter_conflict_expect_binding_selection() -> (
    None
):
    class IAgentEngineAdapter:
        @abstractmethod
        def engine(self) -> str: ...

    @Pod(name="langgraph")
    class LangGraphAgentEngineAdapter(IAgentEngineAdapter):
        def engine(self) -> str:
            return "langgraph"

    @Pod(name="pydantic_ai")
    class PydanticAiAgentEngineAdapter(IAgentEngineAdapter):
        def engine(self) -> str:
            return "pydantic-ai"

    @Pod()
    class AgentRuntime:
        __adapter: IAgentEngineAdapter

        def __init__(self, adapter: IAgentEngineAdapter) -> None:
            self.__adapter = adapter

        def engine(self) -> str:
            return self.__adapter.engine()

    context = ApplicationContext()
    context.bind_to_name(IAgentEngineAdapter, "pydantic_ai")
    context.add(LangGraphAgentEngineAdapter)
    context.add(PydanticAiAgentEngineAdapter)
    context.add(AgentRuntime)
    context.start()

    assert context.get(type_=AgentRuntime).engine() == "pydantic-ai"
