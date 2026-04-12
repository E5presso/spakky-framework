"""Plugin initialization entry point."""

from spakky.core.application.application import SpakkyApplication


def initialize(app: SpakkyApplication) -> None:
    """Initialize the spakky-saga plugin.

    `@Saga()` 스테레오타입은 `Pod` 하위 클래스이므로, 패키지 스캔만으로
    DI 컨테이너가 사가 클래스를 자동 관리한다. 사가 실행은
    `AbstractSaga.execute(data)` 또는 `run_saga_flow(flow, data)`를 통해
    이루어지며, 별도 post-processor 등록이 필요하지 않다.

    Args:
        app: The SpakkyApplication instance.
    """
