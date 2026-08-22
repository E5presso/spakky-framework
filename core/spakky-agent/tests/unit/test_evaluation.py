"""Tests for pure offline agent evaluation contracts and built-in evaluators."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from math import inf
from typing import TypedDict, cast, override

import pytest
from pydantic import BaseModel

import spakky.agent as agent_api
from spakky.agent.error import AgentDefinitionError
from spakky.agent.evaluation import (
    AgentEvaluationCase,
    AgentEvaluationDataset,
    AgentEvaluationReport,
    AgentEvaluationResult,
    AgentEvaluationSample,
    AgentEvaluationSuite,
    CitationEvaluator,
    IAgentEvaluator,
    IModelJudge,
    ModelJudgeEvaluator,
    RetrievalGroundednessEvaluator,
    StructuredOutputEvaluator,
    ToolTraceEvaluator,
    _thaw_json,
)
from spakky.agent.evidence import AgentEvidenceCandidate, AgentEvidenceKind
from spakky.agent.interfaces.model import ModelToolCall
from spakky.agent.types import JsonObject, JsonValue


class ModelAnswer(BaseModel):
    answer: str


@dataclass
class DataclassAnswer:
    answer: str


class TypedAnswer(TypedDict):
    answer: str


class RecordingEvaluator(IAgentEvaluator):
    """Evaluator fake recording deterministic case/sample ordering."""

    def __init__(self, name: str) -> None:
        self._name = name
        self.calls: list[tuple[str, str]] = []

    @property
    @override
    def name(self) -> str:
        return self._name

    @override
    async def evaluate(
        self,
        case: AgentEvaluationCase,
        sample: AgentEvaluationSample,
    ) -> Sequence[AgentEvaluationResult]:
        self.calls.append((case.id, sample.id))
        return (
            AgentEvaluationResult(
                evaluator=self.name,
                metric=f"{self.name}_metric",
                passed=True,
                score=1.0,
                case_ref=case.id,
                sample_ref=sample.id,
            ),
        )


class FixedModelJudge(IModelJudge):
    """Offline model-judge fake returning one configured score."""

    def __init__(self, score: object) -> None:
        self.score = score
        self.calls: list[tuple[str, str]] = []

    @override
    async def judge(
        self,
        case: AgentEvaluationCase,
        sample: AgentEvaluationSample,
    ) -> float:
        self.calls.append((case.id, sample.id))
        # The fake deliberately violates its return annotation for boundary tests.
        return cast(float, self.score)


class InvalidResultEvaluator(IAgentEvaluator):
    """Evaluator fake returning a deliberately malformed result boundary."""

    def __init__(self, result: object, name: str = "invalid") -> None:
        self.result = result
        self._name = name

    @property
    @override
    def name(self) -> str:
        return self._name

    @override
    async def evaluate(
        self,
        case: AgentEvaluationCase,
        sample: AgentEvaluationSample,
    ) -> Sequence[AgentEvaluationResult]:
        _ = (case, sample)
        # The fake deliberately violates the port to probe suite validation.
        return cast(Sequence[AgentEvaluationResult], self.result)


def _case(identifier: str = "case-1") -> AgentEvaluationCase:
    return AgentEvaluationCase(
        id=identifier,
        output_type=ModelAnswer,
        expected_output={"answer": identifier},
    )


def _sample(
    identifier: str = "sample-1", case_ref: str = "case-1"
) -> AgentEvaluationSample:
    return AgentEvaluationSample(
        id=identifier,
        case_ref=case_ref,
        structured_output={"answer": case_ref},
    )


async def test_evaluation_suite_explicit_pairs_expect_deterministic_order() -> None:
    """Dataset order and evaluator order fully determine the report order."""
    first = RecordingEvaluator("first")
    second = RecordingEvaluator("second")
    dataset = AgentEvaluationDataset("dataset-1", (_case("case-1"), _case("case-2")))
    samples = (
        _sample("sample-2", "case-2"),
        _sample("sample-1", "case-1"),
    )

    report = await AgentEvaluationSuite((first, second)).evaluate(dataset, samples)

    assert [(result.case_ref, result.evaluator) for result in report.results] == [
        ("case-1", "first"),
        ("case-1", "second"),
        ("case-2", "first"),
        ("case-2", "second"),
    ]
    assert first.calls == [("case-1", "sample-1"), ("case-2", "sample-2")]
    assert report.dataset_ref == "dataset-1"
    assert report.passed is True
    assert report.score == 1.0


async def test_evaluation_case_and_sample_snapshot_nested_json() -> None:
    """Validated expectations and observations cannot mutate after construction."""
    expected_arguments: dict[str, JsonValue] = {
        "value": "original",
        "nested": {"items": [1, 2]},
    }
    sample_arguments: dict[str, JsonValue] = {
        "value": "original",
        "nested": {"items": [1, 2]},
    }
    expected_output: dict[str, JsonValue] = {"answer": "original"}
    sample_output: dict[str, JsonValue] = {"answer": "original"}
    case = AgentEvaluationCase(
        "case-snapshot",
        expected_tool_calls=(ModelToolCall("lookup", expected_arguments),),
        output_type=ModelAnswer,
        expected_output=expected_output,
    )
    sample = AgentEvaluationSample(
        "sample-snapshot",
        "case-snapshot",
        structured_output=sample_output,
        tool_calls=(ModelToolCall("lookup", sample_arguments),),
    )

    expected_arguments["value"] = "tampered"
    sample_arguments["value"] = "tampered"
    expected_output["answer"] = "tampered"
    sample_output["answer"] = "tampered"

    report = await AgentEvaluationSuite(
        (ToolTraceEvaluator(), StructuredOutputEvaluator())
    ).evaluate(AgentEvaluationDataset("dataset-snapshot", (case,)), (sample,))

    assert report.passed is True
    assert case.expected_tool_calls[0].arguments["value"] == "original"
    assert sample.tool_calls[0].arguments["value"] == "original"
    assert case.expected_output == {"answer": "original"}
    assert sample.structured_output == {"answer": "original"}
    assert _thaw_json((1, {"nested": (2,)})) == (1, {"nested": (2,)})


async def test_tool_trace_evaluator_exact_trace_expect_ids_ignored() -> None:
    """Tool name/arguments/order are scored while provider correlation ids are not."""
    expected = (
        ModelToolCall("search", {"query": "one"}, "expected-1"),
        ModelToolCall("fetch", {"id": "doc-1"}, "expected-2"),
    )
    case = AgentEvaluationCase("case-tools", expected_tool_calls=expected)
    exact = AgentEvaluationSample(
        "sample-exact",
        "case-tools",
        tool_calls=(
            replace(expected[0], call_id="actual-1"),
            replace(expected[1], call_id="actual-2"),
        ),
    )
    partial = replace(exact, id="sample-partial", tool_calls=exact.tool_calls[:1])

    exact_result = (await ToolTraceEvaluator().evaluate(case, exact))[0]
    partial_result = (await ToolTraceEvaluator().evaluate(case, partial))[0]
    empty_result = (
        await ToolTraceEvaluator().evaluate(
            AgentEvaluationCase("case-empty"),
            AgentEvaluationSample("sample-empty", "case-empty"),
        )
    )[0]

    assert (exact_result.passed, exact_result.score) == (True, 1.0)
    assert (partial_result.passed, partial_result.score) == (False, 0.5)
    assert (empty_result.passed, empty_result.score) == (True, 1.0)


@pytest.mark.parametrize("output_type", [ModelAnswer, DataclassAnswer, TypedAnswer])
async def test_structured_output_evaluator_supported_types_expect_strict_score(
    output_type: type[object],
) -> None:
    """BaseModel, dataclass, and TypedDict share the strict materializer."""
    case = AgentEvaluationCase(
        "case-structured",
        output_type=output_type,
        expected_output={"answer": "yes"},
    )
    evaluator = StructuredOutputEvaluator()

    passed = (
        await evaluator.evaluate(
            case,
            AgentEvaluationSample(
                "sample-valid",
                case.id,
                structured_output={"answer": "yes"},
            ),
        )
    )[0]
    mismatch = (
        await evaluator.evaluate(
            case,
            AgentEvaluationSample(
                "sample-mismatch",
                case.id,
                structured_output={"answer": "no"},
            ),
        )
    )[0]
    invalid = (
        await evaluator.evaluate(
            case,
            AgentEvaluationSample(
                "sample-invalid",
                case.id,
                structured_output={"answer": 1},
            ),
        )
    )[0]

    assert (passed.passed, passed.score) == (True, 1.0)
    assert (mismatch.passed, mismatch.score) == (False, 0.0)
    assert (invalid.passed, invalid.score) == (False, 0.0)


async def test_structured_output_evaluator_schema_only_expect_validity_score() -> None:
    """Omitting an expected payload evaluates schema validity without text fallback."""
    case = AgentEvaluationCase("case-schema", output_type=ModelAnswer)
    result = (
        await StructuredOutputEvaluator().evaluate(
            case,
            AgentEvaluationSample(
                "sample-schema",
                case.id,
                structured_output={"answer": "valid"},
            ),
        )
    )[0]

    assert result.passed is True
    with pytest.raises(AgentDefinitionError):
        await StructuredOutputEvaluator().evaluate(
            AgentEvaluationCase("case-untyped"),
            AgentEvaluationSample("sample-untyped", "case-untyped"),
        )


async def test_citation_evaluator_expect_precision_and_recall() -> None:
    """Citation precision and recall are emitted as separate bounded metrics."""
    case = AgentEvaluationCase("case-citations", expected_citations=("a", "b"))
    sample = AgentEvaluationSample(
        "sample-citations",
        case.id,
        citations=("a", "extra"),
    )

    results = await CitationEvaluator(0.5, 0.5).evaluate(case, sample)
    empty = await CitationEvaluator().evaluate(
        AgentEvaluationCase("case-empty"),
        AgentEvaluationSample("sample-empty", "case-empty"),
    )
    missing = await CitationEvaluator().evaluate(
        case,
        AgentEvaluationSample("sample-missing", case.id),
    )

    assert [(result.metric, result.score, result.passed) for result in results] == [
        ("citation_precision", 0.5, True),
        ("citation_recall", 0.5, True),
    ]
    assert [result.score for result in empty] == [1.0, 1.0]
    assert [result.score for result in missing] == [0.0, 0.0]


async def test_retrieval_groundedness_expect_reference_only_score() -> None:
    """Groundedness uses cited/retrieved references without raw context inspection."""
    evaluator = RetrievalGroundednessEvaluator(0.5)
    case = AgentEvaluationCase("case-grounded")

    partial = (
        await evaluator.evaluate(
            case,
            AgentEvaluationSample(
                "sample-partial",
                case.id,
                citations=("hit-1", "missing"),
                retrieval_refs=("hit-1",),
            ),
        )
    )[0]
    empty = (
        await evaluator.evaluate(
            case,
            AgentEvaluationSample("sample-empty", case.id),
        )
    )[0]
    unsupported = (
        await evaluator.evaluate(
            case,
            AgentEvaluationSample(
                "sample-unsupported",
                case.id,
                retrieval_refs=("hit-1",),
            ),
        )
    )[0]

    assert (partial.score, partial.passed) == (0.5, True)
    assert (empty.score, empty.passed) == (1.0, True)
    assert (unsupported.score, unsupported.passed) == (0.0, False)


async def test_model_judge_evaluator_explicit_port_expect_bounded_result() -> None:
    """The wrapper calls only its injected judge and applies the explicit threshold."""
    judge = FixedModelJudge(0.75)
    evaluator = ModelJudgeEvaluator(
        judge,
        metric="quality",
        minimum_score=0.7,
        evaluator_name="quality_judge",
    )
    case = AgentEvaluationCase("case-judge")
    sample = AgentEvaluationSample("sample-judge", case.id)

    result = (await evaluator.evaluate(case, sample))[0]

    assert judge.calls == [(case.id, sample.id)]
    assert result == AgentEvaluationResult(
        evaluator="quality_judge",
        metric="quality",
        passed=True,
        score=0.75,
        case_ref=case.id,
        sample_ref=sample.id,
    )


def test_evaluation_result_evidence_expect_privacy_safe_metric_only() -> None:
    """Evidence contains correlation and scores but no sample output or context."""
    result = AgentEvaluationResult(
        evaluator="structured_output",
        metric="structured_output",
        passed=True,
        score=1.0,
        case_ref="case-secret",
        sample_ref="sample-secret",
    )
    report = AgentEvaluationReport("dataset-secret", (result,))

    candidate = report.evidence_candidates()[0]

    assert candidate == AgentEvidenceCandidate.evaluation(
        evaluator=result.evaluator,
        metric=result.metric,
        passed=result.passed,
        score=result.score,
        case_ref=result.case_ref,
        sample_ref=result.sample_ref,
    )
    assert candidate.kind is AgentEvidenceKind.EVALUATION
    assert candidate.payload == {
        "evaluator": "structured_output",
        "metric": "structured_output",
        "passed": True,
        "score": 1.0,
        "case_ref": "case-secret",
        "sample_ref": "sample-secret",
    }
    assert "prompt" not in repr(candidate)
    assert "context" not in repr(candidate)
    assert AgentEvidenceKind.SIGNAL.value == "signal"

    failed_report = AgentEvaluationReport(
        "dataset-mixed",
        (
            result,
            replace(result, metric="failed_metric", passed=False, score=0.0),
        ),
    )
    assert failed_report.passed is False
    assert failed_report.score == 0.5


def test_evaluation_public_exports_expect_canonical_identity() -> None:
    """All Wave 5 evaluation additions resolve from the package root."""
    assert agent_api.AgentEvaluationCase is AgentEvaluationCase
    assert agent_api.AgentEvaluationSuite is AgentEvaluationSuite
    assert agent_api.ToolTraceEvaluator is ToolTraceEvaluator
    assert agent_api.IModelJudge is IModelJudge


def test_evaluation_definition_boundaries_expect_agent_definition_error() -> None:
    """Invalid datasets, samples, results, reports, and evaluator config fail early."""
    # Runtime-boundary probes intentionally violate static annotations.
    factories = (
        lambda: AgentEvaluationCase(" "),
        lambda: AgentEvaluationCase("case", expected_output={"value": 1}),
        lambda: AgentEvaluationCase(
            "case",
            output_type=cast(type[object], "invalid"),
        ),
        lambda: AgentEvaluationCase(
            "case",
            output_type=ModelAnswer,
            expected_output={"answer": 1},
        ),
        lambda: AgentEvaluationCase(
            "case",
            expected_tool_calls=cast(tuple[ModelToolCall, ...], []),
        ),
        lambda: AgentEvaluationCase(
            "case",
            expected_tool_calls=(cast(ModelToolCall, object()),),
        ),
        lambda: AgentEvaluationCase(
            "case",
            expected_tool_calls=(ModelToolCall(" ", {}),),
        ),
        lambda: AgentEvaluationCase(
            "case",
            expected_tool_calls=(
                ModelToolCall(
                    "tool",
                    {},
                    metadata=cast(JsonObject, []),
                ),
            ),
        ),
        lambda: AgentEvaluationCase(
            "case",
            expected_tool_calls=(
                ModelToolCall("tool", cast(agent_api.JsonObject, [])),
            ),
        ),
        lambda: AgentEvaluationDataset("dataset", ()),
        lambda: AgentEvaluationDataset(
            "dataset",
            cast(tuple[AgentEvaluationCase, ...], [_case()]),
        ),
        lambda: AgentEvaluationDataset(
            "dataset",
            (cast(AgentEvaluationCase, object()),),
        ),
        lambda: AgentEvaluationDataset("dataset", (_case(), _case())),
        lambda: AgentEvaluationSample("sample", "case", citations=("a", "a")),
        lambda: AgentEvaluationSample("sample", "case", citations=(" ",)),
        lambda: AgentEvaluationSample(
            "sample",
            "case",
            retrieval_refs=cast(tuple[str, ...], ["a"]),
        ),
        lambda: AgentEvaluationResult(
            "evaluator", "metric", cast(bool, 1), 1.0, "case", "sample"
        ),
        lambda: AgentEvaluationResult(
            "evaluator", "metric", True, inf, "case", "sample"
        ),
        lambda: AgentEvaluationReport("dataset", ()),
        lambda: AgentEvaluationReport(
            "dataset",
            (cast(AgentEvaluationResult, object()),),
        ),
        lambda: AgentEvaluationSuite(()),
        lambda: AgentEvaluationSuite(
            cast(tuple[IAgentEvaluator, ...], [RecordingEvaluator("one")]),
        ),
        lambda: AgentEvaluationSuite((cast(IAgentEvaluator, object()),)),
        lambda: AgentEvaluationSuite(
            (RecordingEvaluator("same"), RecordingEvaluator("same"))
        ),
        lambda: AgentEvaluationSuite((RecordingEvaluator(" "),)),
        lambda: CitationEvaluator(-0.1, 1.0),
        lambda: RetrievalGroundednessEvaluator(1.1),
        lambda: ModelJudgeEvaluator(cast(IModelJudge, object())),
        lambda: ModelJudgeEvaluator(FixedModelJudge(1.0), metric=" "),
    )
    for factory in factories:
        with pytest.raises(AgentDefinitionError):
            factory()


@pytest.mark.parametrize(
    "factory",
    [
        lambda: AgentEvidenceCandidate.evaluation(
            evaluator=" ",
            metric="metric",
            passed=True,
            score=1.0,
            case_ref="case",
            sample_ref="sample",
        ),
        lambda: AgentEvidenceCandidate.evaluation(
            evaluator="evaluator",
            metric="metric",
            passed=cast(bool, 1),
            score=1.0,
            case_ref="case",
            sample_ref="sample",
        ),
        lambda: AgentEvidenceCandidate.evaluation(
            evaluator="evaluator",
            metric="metric",
            passed=True,
            score=cast(float, "invalid"),
            case_ref="case",
            sample_ref="sample",
        ),
        lambda: AgentEvidenceCandidate.evaluation(
            evaluator="evaluator",
            metric="metric",
            passed=True,
            score=inf,
            case_ref="case",
            sample_ref="sample",
        ),
        lambda: AgentEvidenceCandidate.evaluation(
            evaluator="evaluator",
            metric="metric",
            passed=True,
            score=-0.1,
            case_ref="case",
            sample_ref="sample",
        ),
    ],
)
def test_evaluation_evidence_invalid_metric_expect_definition_error(
    factory: Callable[[], AgentEvidenceCandidate],
) -> None:
    """Evidence cannot encode uncorrelated, nonboolean, or unbounded metrics."""
    with pytest.raises(AgentDefinitionError):
        factory()


@pytest.mark.parametrize("score", [True, "bad", inf, -0.1, 1.1])
async def test_model_judge_invalid_score_expect_agent_definition_error(
    score: object,
) -> None:
    """A judge cannot return bool, nonnumeric, nonfinite, or unbounded scores."""
    evaluator = ModelJudgeEvaluator(FixedModelJudge(score))
    with pytest.raises(AgentDefinitionError):
        await evaluator.evaluate(
            AgentEvaluationCase("case"),
            AgentEvaluationSample("sample", "case"),
        )


@pytest.mark.parametrize(
    "samples",
    [
        cast(tuple[AgentEvaluationSample, ...], []),
        (),
        (_sample("sample-1"), _sample("sample-2")),
        (_sample("sample-other", "other"),),
    ],
)
async def test_evaluation_suite_invalid_pairing_expect_agent_definition_error(
    samples: tuple[AgentEvaluationSample, ...],
) -> None:
    """Samples must be immutable, unique by case, and exactly cover the dataset."""
    with pytest.raises(AgentDefinitionError):
        await AgentEvaluationSuite((RecordingEvaluator("evaluator"),)).evaluate(
            AgentEvaluationDataset("dataset", (_case(),)),
            samples,
        )


async def test_evaluation_suite_invalid_runtime_inputs_expect_definition_error() -> (
    None
):
    """Runtime callers cannot substitute an invalid dataset or sample item."""
    suite = AgentEvaluationSuite((RecordingEvaluator("evaluator"),))
    dataset = AgentEvaluationDataset("dataset", (_case(),))
    with pytest.raises(AgentDefinitionError):
        await suite.evaluate(
            cast(AgentEvaluationDataset, object()),
            (_sample(),),
        )
    with pytest.raises(AgentDefinitionError):
        await suite.evaluate(
            dataset,
            (cast(AgentEvaluationSample, object()),),
        )


@pytest.mark.parametrize(
    "result",
    [
        object(),
        "invalid",
        (),
        ("invalid",),
        (
            AgentEvaluationResult(
                "wrong",
                "metric",
                True,
                1.0,
                "case-1",
                "sample-1",
            ),
        ),
        (
            AgentEvaluationResult(
                "invalid",
                "metric",
                True,
                1.0,
                "other",
                "sample-1",
            ),
        ),
        (
            AgentEvaluationResult(
                "invalid",
                "metric",
                True,
                1.0,
                "case-1",
                "other-sample",
            ),
        ),
        (
            AgentEvaluationResult(
                "invalid",
                "metric",
                True,
                1.0,
                "case-1",
                "sample-1",
            ),
            AgentEvaluationResult(
                "invalid",
                "metric",
                True,
                1.0,
                "case-1",
                "sample-1",
            ),
        ),
    ],
)
async def test_evaluation_suite_invalid_evaluator_result_expect_definition_error(
    result: object,
) -> None:
    """Evaluator output shape, correlation, and metric identity are validated."""
    suite = AgentEvaluationSuite((InvalidResultEvaluator(result),))
    with pytest.raises(AgentDefinitionError):
        await suite.evaluate(
            AgentEvaluationDataset("dataset", (_case(),)),
            (_sample(),),
        )
