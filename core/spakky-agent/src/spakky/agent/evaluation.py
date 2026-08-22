"""Pure offline agent evaluation contracts and deterministic built-ins."""

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from math import isfinite
from types import MappingProxyType
from typing import cast, override

from spakky.agent.error import AgentDefinitionError
from spakky.agent.evidence import AgentEvidenceCandidate
from spakky.agent.interfaces.model import ModelToolCall
from spakky.agent.structured_output import (
    _json_value,
    _structured_output_contract,
)
from spakky.agent.types import JsonObject, JsonValue


@dataclass(frozen=True, slots=True)
class AgentEvaluationCase:
    """One offline case containing only explicit evaluator expectations."""

    id: str
    expected_tool_calls: tuple[ModelToolCall, ...] = ()
    output_type: type[object] | None = None
    expected_output: JsonValue = None
    expected_citations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Validate all case expectations before any sample is scored."""
        _EvaluationValidation.text(
            self.id,
            "Agent evaluation case id must be nonblank single-line text",
        )
        object.__setattr__(
            self,
            "expected_tool_calls",
            _EvaluationValidation.tool_calls(self.expected_tool_calls),
        )
        _EvaluationValidation.references(
            self.expected_citations,
            "Agent evaluation citations must be a tuple",
        )
        if self.output_type is None:
            if self.expected_output is not None:
                raise AgentDefinitionError(
                    "Expected structured output requires an output type"
                )
            return
        if not isinstance(self.output_type, type):
            raise AgentDefinitionError("Agent evaluation output type must be a class")
        contract = _structured_output_contract(self.output_type)
        if self.expected_output is not None:
            expected_output = _json_value(self.expected_output)
            contract.materialize(expected_output)
            object.__setattr__(
                self,
                "expected_output",
                _freeze_json(expected_output),
            )


@dataclass(frozen=True, slots=True)
class AgentEvaluationDataset:
    """Ordered set of unique offline evaluation cases."""

    id: str
    cases: tuple[AgentEvaluationCase, ...]

    def __post_init__(self) -> None:
        """Reject empty, mutable-shaped, or ambiguous datasets."""
        _EvaluationValidation.text(
            self.id,
            "Agent evaluation dataset id must be nonblank single-line text",
        )
        if not isinstance(self.cases, tuple) or not self.cases:
            raise AgentDefinitionError("Agent evaluation dataset cannot be empty")
        if any(not isinstance(case, AgentEvaluationCase) for case in self.cases):
            raise AgentDefinitionError(
                "Agent evaluation dataset contains an invalid case"
            )
        case_ids = tuple(case.id for case in self.cases)
        if len(set(case_ids)) != len(case_ids):
            raise AgentDefinitionError("Agent evaluation case ids must be unique")


@dataclass(frozen=True, slots=True)
class AgentEvaluationSample:
    """Observed output and trace for exactly one offline case."""

    id: str
    case_ref: str
    structured_output: JsonValue = None
    tool_calls: tuple[ModelToolCall, ...] = ()
    citations: tuple[str, ...] = ()
    retrieval_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Validate sample correlations and reference-only grounding inputs."""
        _EvaluationValidation.text(
            self.id,
            "Agent evaluation sample id must be nonblank single-line text",
        )
        _EvaluationValidation.text(
            self.case_ref,
            "Agent evaluation sample case reference must be nonblank single-line text",
        )
        object.__setattr__(
            self,
            "tool_calls",
            _EvaluationValidation.tool_calls(self.tool_calls),
        )
        object.__setattr__(
            self,
            "structured_output",
            _snapshot_json(self.structured_output),
        )
        _EvaluationValidation.references(
            self.citations,
            "Agent evaluation citations must be a tuple",
        )
        _EvaluationValidation.references(
            self.retrieval_refs,
            "Agent evaluation retrieval references must be a tuple",
        )


@dataclass(frozen=True, slots=True)
class AgentEvaluationResult:
    """One bounded metric result for one explicit case/sample pair."""

    evaluator: str
    metric: str
    passed: bool
    score: float
    case_ref: str
    sample_ref: str

    def __post_init__(self) -> None:
        """Reject results that cannot be compared or safely evidenced."""
        for value, message in (
            (
                self.evaluator,
                "Agent evaluator name must be nonblank single-line text",
            ),
            (
                self.metric,
                "Agent evaluation metric must be nonblank single-line text",
            ),
            (
                self.case_ref,
                "Agent evaluation case reference must be nonblank single-line text",
            ),
            (
                self.sample_ref,
                "Agent evaluation sample reference must be nonblank single-line text",
            ),
        ):
            _EvaluationValidation.text(value, message)
        if not isinstance(self.passed, bool):
            raise AgentDefinitionError("Agent evaluation pass value must be boolean")
        _EvaluationValidation.score(self.score)

    def to_evidence_candidate(self) -> AgentEvidenceCandidate:
        """Project the metric to privacy-safe append-only evaluation evidence."""
        return AgentEvidenceCandidate.evaluation(
            evaluator=self.evaluator,
            metric=self.metric,
            passed=self.passed,
            score=self.score,
            case_ref=self.case_ref,
            sample_ref=self.sample_ref,
        )


@dataclass(frozen=True, slots=True)
class AgentEvaluationReport:
    """Deterministically ordered results for one dataset evaluation."""

    dataset_ref: str
    results: tuple[AgentEvaluationResult, ...]

    def __post_init__(self) -> None:
        """Reject reports without an attributable metric result."""
        _EvaluationValidation.text(
            self.dataset_ref,
            "Agent evaluation dataset reference must be nonblank single-line text",
        )
        if not isinstance(self.results, tuple) or not self.results:
            raise AgentDefinitionError("Agent evaluation report cannot be empty")
        if any(
            not isinstance(result, AgentEvaluationResult) for result in self.results
        ):
            raise AgentDefinitionError(
                "Agent evaluation report contains an invalid result"
            )

    @property
    def passed(self) -> bool:
        """Return whether every metric passed."""
        return all(result.passed for result in self.results)

    @property
    def score(self) -> float:
        """Return the unweighted mean across the explicit metric results."""
        return sum(result.score for result in self.results) / len(self.results)

    def evidence_candidates(self) -> tuple[AgentEvidenceCandidate, ...]:
        """Return privacy-safe evidence without raw outputs, prompts, or context."""
        return tuple(result.to_evidence_candidate() for result in self.results)


class IAgentEvaluator(ABC):
    """Replaceable offline evaluator over an explicit case/sample pair."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the stable evaluator identity used in reports and evidence."""
        ...

    @abstractmethod
    async def evaluate(
        self,
        case: AgentEvaluationCase,
        sample: AgentEvaluationSample,
    ) -> Sequence[AgentEvaluationResult]:
        """Evaluate exactly one already-correlated case/sample pair."""
        ...


class IModelJudge(ABC):
    """Optional externally supplied model-judge port with no default backend."""

    @abstractmethod
    async def judge(
        self,
        case: AgentEvaluationCase,
        sample: AgentEvaluationSample,
    ) -> float:
        """Return a bounded score without implying a network or model fallback."""
        ...


@dataclass(frozen=True, slots=True)
class AgentEvaluationSuite:
    """Sequentially evaluate explicit samples in dataset and evaluator order."""

    evaluators: tuple[IAgentEvaluator, ...]

    def __post_init__(self) -> None:
        """Reject suites whose evaluator order or identity is ambiguous."""
        if not isinstance(self.evaluators, tuple) or not self.evaluators:
            raise AgentDefinitionError("Agent evaluation suite cannot be empty")
        if any(
            not isinstance(evaluator, IAgentEvaluator) for evaluator in self.evaluators
        ):
            raise AgentDefinitionError(
                "Agent evaluation suite contains an invalid evaluator"
            )
        names = tuple(evaluator.name for evaluator in self.evaluators)
        for name in names:
            _EvaluationValidation.text(
                name,
                "Agent evaluator name must be nonblank single-line text",
            )
        if len(set(names)) != len(names):
            raise AgentDefinitionError("Agent evaluator names must be unique")

    async def evaluate(
        self,
        dataset: AgentEvaluationDataset,
        samples: tuple[AgentEvaluationSample, ...],
    ) -> AgentEvaluationReport:
        """Pair one explicit sample per case and preserve deterministic ordering."""
        if not isinstance(dataset, AgentEvaluationDataset):
            raise AgentDefinitionError("Agent evaluation dataset is invalid")
        if not isinstance(samples, tuple) or any(
            not isinstance(sample, AgentEvaluationSample) for sample in samples
        ):
            raise AgentDefinitionError("Agent evaluation samples must be a tuple")
        sample_by_case = {sample.case_ref: sample for sample in samples}
        if len(sample_by_case) != len(samples):
            raise AgentDefinitionError(
                "Agent evaluation samples must be unique per case"
            )
        case_ids = tuple(case.id for case in dataset.cases)
        if set(sample_by_case) != set(case_ids):
            raise AgentDefinitionError(
                "Agent evaluation samples must exactly cover the dataset"
            )
        results: list[AgentEvaluationResult] = []
        for case in dataset.cases:
            sample = sample_by_case[case.id]
            for evaluator in self.evaluators:
                evaluated = await evaluator.evaluate(case, sample)
                self._append_validated_results(
                    results,
                    evaluated,
                    evaluator=evaluator,
                    case=case,
                    sample=sample,
                )
        return AgentEvaluationReport(dataset_ref=dataset.id, results=tuple(results))

    def _append_validated_results(
        self,
        destination: list[AgentEvaluationResult],
        evaluated: object,
        *,
        evaluator: IAgentEvaluator,
        case: AgentEvaluationCase,
        sample: AgentEvaluationSample,
    ) -> None:
        """Validate evaluator output before it enters the aggregate report."""
        if not isinstance(evaluated, Sequence) or isinstance(evaluated, str | bytes):
            raise AgentDefinitionError("Agent evaluator result must be a sequence")
        batch = tuple(evaluated)
        if not batch or any(
            not isinstance(result, AgentEvaluationResult) for result in batch
        ):
            raise AgentDefinitionError("Agent evaluator returned an invalid result")
        metrics: set[str] = set()
        for result in batch:
            if (
                result.evaluator != evaluator.name
                or result.case_ref != case.id
                or result.sample_ref != sample.id
            ):
                raise AgentDefinitionError(
                    "Agent evaluator result correlation does not match its pair"
                )
            if result.metric in metrics:
                raise AgentDefinitionError(
                    "Agent evaluator metrics must be unique per pair"
                )
            metrics.add(result.metric)
            destination.append(result)


@dataclass(frozen=True, slots=True)
class ToolTraceEvaluator(IAgentEvaluator):
    """Score exact ordered tool names and arguments while ignoring call ids."""

    @property
    @override
    def name(self) -> str:
        return "tool_trace"

    @override
    async def evaluate(
        self,
        case: AgentEvaluationCase,
        sample: AgentEvaluationSample,
    ) -> Sequence[AgentEvaluationResult]:
        expected = tuple(
            (call.name, call.arguments) for call in case.expected_tool_calls
        )
        actual = tuple((call.name, call.arguments) for call in sample.tool_calls)
        denominator = max(len(expected), len(actual))
        score = (
            1.0
            if denominator == 0
            else sum(
                expected_item == actual_item
                for expected_item, actual_item in zip(expected, actual)
            )
            / denominator
        )
        return (
            AgentEvaluationResult(
                evaluator=self.name,
                metric="tool_trace",
                passed=expected == actual,
                score=score,
                case_ref=case.id,
                sample_ref=sample.id,
            ),
        )


@dataclass(frozen=True, slots=True)
class StructuredOutputEvaluator(IAgentEvaluator):
    """Validate strict structured output and optional exact expected content."""

    @property
    @override
    def name(self) -> str:
        return "structured_output"

    @override
    async def evaluate(
        self,
        case: AgentEvaluationCase,
        sample: AgentEvaluationSample,
    ) -> Sequence[AgentEvaluationResult]:
        if case.output_type is None:
            raise AgentDefinitionError(
                "Structured output evaluator requires a case output type"
            )
        contract = _structured_output_contract(case.output_type)
        try:
            materialized = contract.materialize(_thaw_json(sample.structured_output))
            actual = contract.dump(materialized)
        except AgentDefinitionError:
            passed = False
        else:
            if case.expected_output is None:
                passed = True
            else:
                expected = contract.dump(
                    contract.materialize(_thaw_json(case.expected_output))
                )
                passed = actual == expected
        return (
            AgentEvaluationResult(
                evaluator=self.name,
                metric="structured_output",
                passed=passed,
                score=1.0 if passed else 0.0,
                case_ref=case.id,
                sample_ref=sample.id,
            ),
        )


@dataclass(frozen=True, slots=True)
class CitationEvaluator(IAgentEvaluator):
    """Calculate exact reference precision and recall."""

    minimum_precision: float = 1.0
    minimum_recall: float = 1.0

    def __post_init__(self) -> None:
        """Validate both configured metric thresholds."""
        _EvaluationValidation.threshold(self.minimum_precision)
        _EvaluationValidation.threshold(self.minimum_recall)

    @property
    @override
    def name(self) -> str:
        return "citation"

    @override
    async def evaluate(
        self,
        case: AgentEvaluationCase,
        sample: AgentEvaluationSample,
    ) -> Sequence[AgentEvaluationResult]:
        expected = set(case.expected_citations)
        actual = set(sample.citations)
        relevant = len(expected & actual)
        precision = relevant / len(actual) if actual else float(not expected)
        recall = relevant / len(expected) if expected else 1.0
        return (
            AgentEvaluationResult(
                evaluator=self.name,
                metric="citation_precision",
                passed=precision >= self.minimum_precision,
                score=precision,
                case_ref=case.id,
                sample_ref=sample.id,
            ),
            AgentEvaluationResult(
                evaluator=self.name,
                metric="citation_recall",
                passed=recall >= self.minimum_recall,
                score=recall,
                case_ref=case.id,
                sample_ref=sample.id,
            ),
        )


@dataclass(frozen=True, slots=True)
class RetrievalGroundednessEvaluator(IAgentEvaluator):
    """Score the fraction of cited references present in retrieved evidence."""

    minimum_score: float = 1.0

    def __post_init__(self) -> None:
        """Validate the configured groundedness threshold."""
        _EvaluationValidation.threshold(self.minimum_score)

    @property
    @override
    def name(self) -> str:
        return "retrieval_groundedness"

    @override
    async def evaluate(
        self,
        case: AgentEvaluationCase,
        sample: AgentEvaluationSample,
    ) -> Sequence[AgentEvaluationResult]:
        citations = set(sample.citations)
        retrieved = set(sample.retrieval_refs)
        score = (
            len(citations & retrieved) / len(citations)
            if citations
            else float(not retrieved)
        )
        return (
            AgentEvaluationResult(
                evaluator=self.name,
                metric="retrieval_groundedness",
                passed=score >= self.minimum_score,
                score=score,
                case_ref=case.id,
                sample_ref=sample.id,
            ),
        )


@dataclass(frozen=True, slots=True)
class ModelJudgeEvaluator(IAgentEvaluator):
    """Wrap one explicitly supplied model judge without a default provider."""

    judge: IModelJudge
    metric: str = "model_judge"
    minimum_score: float = 0.5
    evaluator_name: str = "model_judge"

    def __post_init__(self) -> None:
        """Reject an absent judge or ambiguous metric configuration."""
        if not isinstance(self.judge, IModelJudge):
            raise AgentDefinitionError("Model judge evaluator requires an IModelJudge")
        _EvaluationValidation.text(
            self.metric,
            "Model judge metric must be nonblank single-line text",
        )
        _EvaluationValidation.text(
            self.evaluator_name,
            "Model judge evaluator name must be nonblank single-line text",
        )
        _EvaluationValidation.threshold(self.minimum_score)

    @property
    @override
    def name(self) -> str:
        return self.evaluator_name

    @override
    async def evaluate(
        self,
        case: AgentEvaluationCase,
        sample: AgentEvaluationSample,
    ) -> Sequence[AgentEvaluationResult]:
        score = _EvaluationValidation.score(await self.judge.judge(case, sample))
        return (
            AgentEvaluationResult(
                evaluator=self.name,
                metric=self.metric,
                passed=score >= self.minimum_score,
                score=score,
                case_ref=case.id,
                sample_ref=sample.id,
            ),
        )


class _EvaluationValidation:
    """Validate untrusted evaluator and dataset boundaries in one place."""

    @staticmethod
    def text(value: object, message: str) -> None:
        """Validate one stable single-line identifier."""
        if (
            not isinstance(value, str)
            or not value.strip()
            or "\n" in value
            or "\r" in value
        ):
            raise AgentDefinitionError(message)

    @staticmethod
    def score(value: object) -> float:
        """Validate and normalize one externally produced metric score."""
        if (
            isinstance(value, bool)
            or not isinstance(value, int | float)
            or not isfinite(value)
            or not 0 <= value <= 1
        ):
            raise AgentDefinitionError(
                "Agent evaluation score must be between zero and one"
            )
        return float(value)

    @staticmethod
    def threshold(value: object) -> None:
        """Validate one evaluator configuration threshold."""
        _EvaluationValidation.score(value)

    @staticmethod
    def references(value: object, message: str) -> tuple[str, ...]:
        """Validate an immutable unique set of ordered evidence references."""
        if not isinstance(value, tuple):
            raise AgentDefinitionError(message)
        for reference in value:
            _EvaluationValidation.text(
                reference,
                "Agent evaluation reference must be nonblank single-line text",
            )
        if len(set(value)) != len(value):
            raise AgentDefinitionError("Agent evaluation references must be unique")
        return value

    @staticmethod
    def tool_calls(value: object) -> tuple[ModelToolCall, ...]:
        """Validate an immutable ordered tool trace without exposing metadata."""
        if not isinstance(value, tuple):
            raise AgentDefinitionError("Agent evaluation tool trace must be a tuple")
        normalized: list[ModelToolCall] = []
        for call in value:
            if not isinstance(call, ModelToolCall):
                raise AgentDefinitionError(
                    "Agent evaluation tool trace contains an invalid call"
                )
            _EvaluationValidation.text(
                call.name,
                "Agent evaluation tool name must be nonblank single-line text",
            )
            arguments = _json_value(call.arguments)
            if not isinstance(arguments, Mapping):
                raise AgentDefinitionError(
                    "Agent evaluation tool arguments must be an object"
                )
            metadata = _snapshot_json(call.metadata)
            if not isinstance(metadata, Mapping):
                raise AgentDefinitionError(
                    "Agent evaluation tool metadata must be an object"
                )
            normalized.append(
                replace(
                    call,
                    arguments=cast(JsonObject, _freeze_json(arguments)),
                    metadata=cast(JsonObject, _freeze_json(metadata)),
                )
            )
        return tuple(normalized)


def _snapshot_json(value: object) -> JsonValue:
    return _freeze_json(_json_value(value))


def _freeze_json(value: JsonValue) -> JsonValue:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {key: _freeze_json(item) for key, item in value.items()}
        )
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return tuple(_freeze_json(item) for item in value)
    return value


def _thaw_json(value: JsonValue) -> JsonValue:
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return tuple(_thaw_json(item) for item in value)
    return value
