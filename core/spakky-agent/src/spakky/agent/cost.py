"""Operator-owned model pricing and deterministic token-cost calculation."""

from dataclasses import dataclass, field
from decimal import Decimal
from hashlib import sha256
from json import dumps
from types import MappingProxyType
from typing import Mapping

from spakky.agent.error import AbstractSpakkyAgentError
from spakky.agent.interfaces.model import ModelUsage

_TOKENS_PER_MILLION = Decimal(1_000_000)


class AgentPricingError(AbstractSpakkyAgentError):
    """Raised when model cost cannot be calculated from trusted inputs."""

    message = "Agent model pricing is invalid or unavailable"


@dataclass(frozen=True, slots=True)
class ModelPrice:
    """Per-million-token rates for one operator catalog model reference."""

    input_per_million: Decimal
    output_per_million: Decimal
    cached_input_per_million: Decimal | None = None
    cache_write_input_per_million: Decimal | None = None
    cache_write_5m_input_per_million: Decimal | None = None
    cache_write_1h_input_per_million: Decimal | None = None

    def __post_init__(self) -> None:
        for value in (
            self.input_per_million,
            self.output_per_million,
            self.cached_input_per_million,
            self.cache_write_input_per_million,
            self.cache_write_5m_input_per_million,
            self.cache_write_1h_input_per_million,
        ):
            if value is not None and (
                not isinstance(value, Decimal) or not value.is_finite() or value < 0
            ):
                raise AgentPricingError


@dataclass(frozen=True, slots=True)
class ModelCost:
    """Exact cost calculated for one model step."""

    model_ref: str
    amount: Decimal
    currency: str
    pricing_version: str
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int = 0
    cache_write_input_tokens: int = 0
    cache_write_5m_input_tokens: int = 0
    cache_write_1h_input_tokens: int = 0

    def __post_init__(self) -> None:
        _require_text(self.model_ref)
        _require_text(self.currency)
        _require_text(self.pricing_version)
        if (
            not isinstance(self.amount, Decimal)
            or not self.amount.is_finite()
            or self.amount < 0
        ):
            raise AgentPricingError
        for value in (
            self.input_tokens,
            self.output_tokens,
            self.cached_input_tokens,
            self.cache_write_input_tokens,
            self.cache_write_5m_input_tokens,
            self.cache_write_1h_input_tokens,
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise AgentPricingError


@dataclass(frozen=True, slots=True)
class ModelPricingCatalog:
    """Versioned operator pricing keyed by opaque logical model reference."""

    version: str
    prices: Mapping[str, ModelPrice]
    currency: str = "USD"
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_text(self.version)
        _require_text(self.currency)
        if not self.prices:
            raise AgentPricingError
        for model_ref, price in self.prices.items():
            _require_text(model_ref)
            if not isinstance(price, ModelPrice):
                raise AgentPricingError
        for key, value in self.metadata.items():
            _require_text(key)
            _require_text(value)
        object.__setattr__(self, "prices", MappingProxyType(dict(self.prices)))
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    @property
    def fingerprint(self) -> str:
        """Return a stable digest binding version, currency, and every rate."""
        payload = {
            "version": self.version,
            "currency": self.currency,
            "prices": {
                model_ref: {
                    "input": str(price.input_per_million),
                    "output": str(price.output_per_million),
                    "cached_input": (
                        None
                        if price.cached_input_per_million is None
                        else str(price.cached_input_per_million)
                    ),
                    "cache_write_input": (
                        None
                        if price.cache_write_input_per_million is None
                        else str(price.cache_write_input_per_million)
                    ),
                    "cache_write_5m_input": (
                        None
                        if price.cache_write_5m_input_per_million is None
                        else str(price.cache_write_5m_input_per_million)
                    ),
                    "cache_write_1h_input": (
                        None
                        if price.cache_write_1h_input_per_million is None
                        else str(price.cache_write_1h_input_per_million)
                    ),
                }
                for model_ref, price in sorted(self.prices.items())
            },
            "metadata": dict(sorted(self.metadata.items())),
        }
        encoded = dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return sha256(encoded).hexdigest()

    def calculate(self, model_ref: str, usage: ModelUsage) -> ModelCost:
        """Calculate exact step cost or fail when required usage is unavailable."""
        _require_text(model_ref)
        price = self.prices.get(model_ref)
        if price is None:
            raise AgentPricingError
        input_tokens = _usage_tokens(usage.input_tokens)
        output_tokens = _usage_tokens(usage.output_tokens)
        cached_input_tokens = _usage_tokens(usage.cached_input_tokens, default=0)
        cache_write_input_tokens = _usage_tokens(
            usage.cache_write_input_tokens,
            default=0,
        )
        cache_write_5m_input_tokens = _usage_tokens(
            usage.cache_write_5m_input_tokens,
            default=0,
        )
        cache_write_1h_input_tokens = _usage_tokens(
            usage.cache_write_1h_input_tokens,
            default=0,
        )
        categorized_cache_write = (
            usage.cache_write_5m_input_tokens is not None
            or usage.cache_write_1h_input_tokens is not None
        )
        if (
            cache_write_input_tokens > 0
            and not categorized_cache_write
            and (
                price.cache_write_5m_input_per_million is not None
                or price.cache_write_1h_input_per_million is not None
            )
        ):
            raise AgentPricingError
        if cached_input_tokens + cache_write_input_tokens > input_tokens:
            raise AgentPricingError
        if categorized_cache_write and (
            cache_write_5m_input_tokens + cache_write_1h_input_tokens
            != cache_write_input_tokens
        ):
            raise AgentPricingError
        regular_input_tokens = (
            input_tokens - cached_input_tokens - cache_write_input_tokens
        )
        cached_rate = (
            price.cached_input_per_million
            if price.cached_input_per_million is not None
            else price.input_per_million
        )
        cache_write_rate = (
            price.cache_write_input_per_million
            if price.cache_write_input_per_million is not None
            else price.input_per_million
        )
        cache_write_5m_rate = (
            price.cache_write_5m_input_per_million
            if price.cache_write_5m_input_per_million is not None
            else cache_write_rate
        )
        cache_write_1h_rate = (
            price.cache_write_1h_input_per_million
            if price.cache_write_1h_input_per_million is not None
            else cache_write_rate
        )
        cache_write_amount = (
            Decimal(cache_write_5m_input_tokens) * cache_write_5m_rate
            + Decimal(cache_write_1h_input_tokens) * cache_write_1h_rate
            if categorized_cache_write
            else Decimal(cache_write_input_tokens) * cache_write_rate
        )
        amount = (
            Decimal(regular_input_tokens) * price.input_per_million
            + Decimal(cached_input_tokens) * cached_rate
            + cache_write_amount
            + Decimal(output_tokens) * price.output_per_million
        ) / _TOKENS_PER_MILLION
        return ModelCost(
            model_ref=model_ref,
            amount=amount,
            currency=self.currency,
            pricing_version=self.version,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_input_tokens=cached_input_tokens,
            cache_write_input_tokens=cache_write_input_tokens,
            cache_write_5m_input_tokens=cache_write_5m_input_tokens,
            cache_write_1h_input_tokens=cache_write_1h_input_tokens,
        )


def _usage_tokens(value: int | None, *, default: int | None = None) -> int:
    if value is None:
        if default is None:
            raise AgentPricingError
        return default
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise AgentPricingError
    return value


def _require_text(value: object) -> None:
    if (
        not isinstance(value, str)
        or not value.strip()
        or "\n" in value
        or "\r" in value
    ):
        raise AgentPricingError
