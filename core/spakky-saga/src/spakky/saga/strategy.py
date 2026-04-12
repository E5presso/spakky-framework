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

    def delay_for(self, attempt: int) -> float:
        """attempt(1-indexed) 직전에 대기할 초 단위 지연을 반환한다.

        Args:
            attempt: 시도 번호 (1-indexed). attempt=1 → base, attempt=2 → base*2, ...

        Returns:
            float: base * 2^(attempt-1).
        """
        return self.base * (2 ** (attempt - 1))


@immutable
class Retry:
    """지정 횟수만큼 재시도 후 then 전략을 적용한다."""

    max_attempts: int = 3
    backoff: ExponentialBackoff = field(default_factory=ExponentialBackoff)
    then: Union["Compensate", "Skip"] = field(default_factory=Compensate)


ErrorStrategy: TypeAlias = Compensate | Skip | Retry
"""에러 전략 유니온 타입."""
