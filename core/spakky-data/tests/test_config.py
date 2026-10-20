"""Data 공통 환경 설정과 이전 SQLAlchemy 설정의 소유권 분리를 검증한다."""

import pytest
from pydantic import ValidationError

from spakky.data.config import DataConfig


def test_data_config_without_override_expect_async_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """공통 환경변수가 없으면 기존 기본값인 비동기 지원을 유지한다."""
    monkeypatch.delenv("SPAKKY_DATA__SUPPORT_ASYNC_MODE", raising=False)
    assert DataConfig().support_async_mode is True


@pytest.mark.parametrize("value, expected", [("false", False), ("true", True)])
def test_data_config_common_variable_expect_selected_mode(
    monkeypatch: pytest.MonkeyPatch, value: str, expected: bool
) -> None:
    """Data 환경변수만으로 비동기 지원 모드를 선택한다."""
    monkeypatch.setenv("SPAKKY_DATA__SUPPORT_ASYNC_MODE", value)
    assert DataConfig().support_async_mode is expected


def test_data_config_old_plugin_variable_expect_no_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """이전 플러그인 전용 변수는 공통 설정의 별칭이나 두 번째 정본이 아니다."""
    monkeypatch.delenv("SPAKKY_DATA__SUPPORT_ASYNC_MODE", raising=False)
    monkeypatch.setenv("SPAKKY_SQLALCHEMY__SUPPORT_ASYNC_MODE", "false")
    assert DataConfig().support_async_mode is True


def test_data_config_invalid_value_expect_validation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """잘못된 모드 값은 임의 기본값으로 바꾸지 않고 설정 오류로 거절한다."""
    monkeypatch.setenv("SPAKKY_DATA__SUPPORT_ASYNC_MODE", "invalid")
    with pytest.raises(ValidationError):
        DataConfig()
