"""Tests for Redis cache configuration."""

from spakky.plugins.redis.common.config import RedisCacheConfig


def _config(*, use_ssl: bool = False) -> RedisCacheConfig:
    return RedisCacheConfig.model_construct(
        host="localhost",
        port=6379,
        db=0,
        username=None,
        password=None,
        use_ssl=use_ssl,
        key_prefix="spakky:cache:",
        socket_timeout=5.0,
    )


def test_config_defaults_expect_local_redis_url() -> None:
    """기본 설정이 local Redis URL과 Spakky key prefix를 제공하는지 검증한다."""
    config = _config()

    assert config.connection_url == "redis://localhost:6379/0"
    assert config.key_prefix == "spakky:cache:"


def test_config_ssl_expect_rediss_url() -> None:
    """SSL 설정이 rediss URL scheme으로 표현되는지 검증한다."""
    config = _config(use_ssl=True)

    assert config.connection_url == "rediss://localhost:6379/0"
