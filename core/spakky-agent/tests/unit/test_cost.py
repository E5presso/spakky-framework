"""Tests for operator-owned model pricing and exact cost accounting."""

from collections.abc import Mapping
from decimal import Decimal
from typing import cast

import pytest

import spakky.agent as public_api
from spakky.agent.cost import (
    AgentPricingError,
    ModelCost,
    ModelPrice,
    ModelPricingCatalog,
)
from spakky.agent.interfaces.model import ModelUsage


def _price() -> ModelPrice:
    return ModelPrice(
        input_per_million=Decimal("2"),
        output_per_million=Decimal("4"),
        cached_input_per_million=Decimal("1"),
        cache_write_input_per_million=Decimal("3"),
        cache_write_5m_input_per_million=Decimal("2.5"),
        cache_write_1h_input_per_million=Decimal("4"),
    )


def _catalog() -> ModelPricingCatalog:
    return ModelPricingCatalog(
        version="prices-2026-08-23",
        prices={"openrouter/kimi": _price()},
        metadata={"source": "operator"},
    )


def test_model_pricing_catalog_calculates_cached_and_written_tokens_exactly() -> None:
    """Inclusive input usage is split across regular, cached, and write rates."""
    cost = _catalog().calculate(
        "openrouter/kimi",
        ModelUsage(
            input_tokens=1_000_000,
            output_tokens=500_000,
            total_tokens=1_500_000,
            cached_input_tokens=200_000,
            cache_write_input_tokens=100_000,
            cache_write_5m_input_tokens=60_000,
            cache_write_1h_input_tokens=40_000,
        ),
    )

    assert cost == ModelCost(
        model_ref="openrouter/kimi",
        amount=Decimal("3.91"),
        currency="USD",
        pricing_version="prices-2026-08-23",
        input_tokens=1_000_000,
        output_tokens=500_000,
        cached_input_tokens=200_000,
        cache_write_input_tokens=100_000,
        cache_write_5m_input_tokens=60_000,
        cache_write_1h_input_tokens=40_000,
    )


def test_model_pricing_catalog_uses_input_rate_for_unspecified_cache_rates() -> None:
    """Absent optional cache rates preserve deterministic input-rate billing."""
    catalog = ModelPricingCatalog(
        version="v1",
        prices={
            "model": ModelPrice(
                input_per_million=Decimal("2"),
                output_per_million=Decimal("4"),
            )
        },
    )

    cost = catalog.calculate(
        "model",
        ModelUsage(
            input_tokens=1_000_000,
            output_tokens=500_000,
            cached_input_tokens=250_000,
            cache_write_input_tokens=250_000,
        ),
    )

    assert cost.amount == Decimal("4")


def test_model_pricing_catalog_prices_cache_write_ttl_categories_exactly() -> None:
    """Provider TTL breakdown uses distinct operator rates without collapsing it."""
    cost = _catalog().calculate(
        "openrouter/kimi",
        ModelUsage(
            input_tokens=1_000_000,
            output_tokens=0,
            cache_write_input_tokens=300_000,
            cache_write_5m_input_tokens=200_000,
            cache_write_1h_input_tokens=100_000,
        ),
    )

    assert cost.amount == Decimal("2.3")
    assert cost.cache_write_input_tokens == 300_000
    assert cost.cache_write_5m_input_tokens == 200_000
    assert cost.cache_write_1h_input_tokens == 100_000


def test_model_pricing_catalog_fingerprint_is_order_independent_and_bound() -> None:
    """Equivalent catalogs hash equally while rate or metadata changes do not."""
    first = ModelPricingCatalog(
        version="v1",
        prices={
            "b": ModelPrice(Decimal("2"), Decimal("4")),
            "a": ModelPrice(Decimal("1"), Decimal("3")),
        },
        metadata={"z": "last", "a": "first"},
    )
    reordered = ModelPricingCatalog(
        version="v1",
        prices={
            "a": ModelPrice(Decimal("1"), Decimal("3")),
            "b": ModelPrice(Decimal("2"), Decimal("4")),
        },
        metadata={"a": "first", "z": "last"},
    )
    changed = ModelPricingCatalog(
        version="v1",
        prices={
            "a": ModelPrice(Decimal("1"), Decimal("3")),
            "b": ModelPrice(Decimal("2.1"), Decimal("4")),
        },
        metadata={"a": "first", "z": "last"},
    )

    assert first.fingerprint == reordered.fingerprint
    assert first.fingerprint != changed.fingerprint


def test_model_pricing_catalog_snapshots_mutable_input_mappings() -> None:
    """Operator configuration cannot mutate an already-validated catalog."""
    prices = {"model": ModelPrice(Decimal("1"), Decimal("2"))}
    metadata = {"source": "operator"}
    catalog = ModelPricingCatalog(version="v1", prices=prices, metadata=metadata)
    fingerprint = catalog.fingerprint

    prices["model"] = ModelPrice(Decimal("9"), Decimal("9"))
    metadata["source"] = "mutated"

    assert catalog.prices["model"].input_per_million == Decimal("1")
    assert catalog.metadata == {"source": "operator"}
    assert catalog.fingerprint == fingerprint


@pytest.mark.parametrize(
    "value",
    [cast(Decimal, 1), Decimal("NaN"), Decimal("Infinity"), Decimal("-0.1")],
)
def test_model_price_rejects_invalid_rates(value: Decimal) -> None:
    """Every configured rate must be a non-negative finite Decimal."""
    with pytest.raises(AgentPricingError):
        ModelPrice(input_per_million=value, output_per_million=Decimal("1"))


@pytest.mark.parametrize(
    "price",
    [
        ModelPrice(Decimal("1"), Decimal("2"), cached_input_per_million=Decimal("0")),
        ModelPrice(
            Decimal("1"),
            Decimal("2"),
            cache_write_input_per_million=Decimal("0"),
        ),
    ],
)
def test_model_price_accepts_zero_optional_rates(price: ModelPrice) -> None:
    """Free cache reads or writes remain an explicit operator decision."""
    assert price.input_per_million == Decimal("1")


@pytest.mark.parametrize(
    "value",
    [cast(str, 1), "", " ", "line\nbreak", "line\rbreak"],
)
def test_model_pricing_catalog_rejects_invalid_text(value: str) -> None:
    """Catalog identifiers and metadata remain stable single-line text."""
    with pytest.raises(AgentPricingError):
        ModelPricingCatalog(version=value, prices={"model": _price()})


def test_model_pricing_catalog_rejects_invalid_shapes() -> None:
    """Empty prices, wrong price values, and bad metadata fail closed."""
    with pytest.raises(AgentPricingError):
        ModelPricingCatalog(version="v1", prices={})
    with pytest.raises(AgentPricingError):
        ModelPricingCatalog(
            version="v1",
            prices=cast(Mapping[str, ModelPrice], {"model": "invalid"}),
        )
    with pytest.raises(AgentPricingError):
        ModelPricingCatalog(
            version="v1",
            prices={"model": _price()},
            metadata={"": "value"},
        )
    with pytest.raises(AgentPricingError):
        ModelPricingCatalog(
            version="v1",
            prices={"model": _price()},
            metadata={"source": "line\nvalue"},
        )


@pytest.mark.parametrize(
    "usage",
    [
        ModelUsage(input_tokens=None, output_tokens=1),
        ModelUsage(input_tokens=1, output_tokens=None),
        ModelUsage(input_tokens=True, output_tokens=1),
        ModelUsage(input_tokens=-1, output_tokens=1),
        ModelUsage(input_tokens=1, output_tokens=1, cached_input_tokens=-1),
        ModelUsage(input_tokens=1, output_tokens=1, cache_write_input_tokens=True),
        ModelUsage(input_tokens=1, output_tokens=1, cached_input_tokens=2),
        ModelUsage(
            input_tokens=10,
            output_tokens=1,
            cache_write_input_tokens=5,
            cache_write_5m_input_tokens=2,
            cache_write_1h_input_tokens=2,
        ),
        ModelUsage(
            input_tokens=10,
            output_tokens=1,
            cache_write_input_tokens=5,
        ),
    ],
)
def test_model_pricing_catalog_rejects_unusable_usage(usage: ModelUsage) -> None:
    """Missing, malformed, or internally inconsistent usage cannot be priced."""
    with pytest.raises(AgentPricingError):
        _catalog().calculate("openrouter/kimi", usage)


def test_model_pricing_catalog_rejects_unknown_or_blank_model_ref() -> None:
    """Pricing never falls back to an arbitrary or default route."""
    with pytest.raises(AgentPricingError):
        _catalog().calculate(
            "unknown",
            ModelUsage(input_tokens=1, output_tokens=1),
        )
    with pytest.raises(AgentPricingError):
        _catalog().calculate(" ", ModelUsage(input_tokens=1, output_tokens=1))


def test_model_cost_rejects_invalid_fields() -> None:
    """Directly created cost receipts preserve exact non-negative accounting."""
    valid = {
        "model_ref": "model",
        "amount": Decimal("1"),
        "currency": "USD",
        "pricing_version": "v1",
        "input_tokens": 1,
        "output_tokens": 1,
    }
    with pytest.raises(AgentPricingError):
        ModelCost(**{**valid, "model_ref": ""})
    with pytest.raises(AgentPricingError):
        ModelCost(**{**valid, "amount": Decimal("-1")})
    with pytest.raises(AgentPricingError):
        ModelCost(**{**valid, "amount": Decimal("NaN")})
    with pytest.raises(AgentPricingError):
        ModelCost(**{**valid, "input_tokens": -1})
    with pytest.raises(AgentPricingError):
        ModelCost(**{**valid, "output_tokens": True})


def test_cost_public_exports_are_canonical() -> None:
    """The Spring-style basic pricing surface is available from package root."""
    assert public_api.AgentPricingError is AgentPricingError
    assert public_api.ModelCost is ModelCost
    assert public_api.ModelPrice is ModelPrice
    assert public_api.ModelPricingCatalog is ModelPricingCatalog
