"""Error strategy types for saga step failure handling."""

from dataclasses import field
from typing import TypeAlias, Union

from spakky.core.common.mutability import immutable


@immutable
class Compensate:
    """역순 보상을 트리거한다 (기본 전략)."""


@immutable
class Skip:
    """실패를 무시하고 다음 step으로 진행한다."""


@immutable
class ExponentialBackoff:
    """지수 백오프 전략."""

    base: float = 1.0


@immutable
class Retry:
    """지정 횟수만큼 재시도 후 then 전략을 적용한다."""

    max_attempts: int = 3
    backoff: ExponentialBackoff = field(default_factory=ExponentialBackoff)
    then: Union["Compensate", "Skip"] = field(default_factory=Compensate)


ErrorStrategy: TypeAlias = Compensate | Skip | Retry
"""에러 전략 유니온 타입."""
