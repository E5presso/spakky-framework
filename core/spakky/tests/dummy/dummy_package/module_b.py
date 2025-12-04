from spakky.core.common.annotation import ClassAnnotation
from spakky.core.pod.annotations.pod import Pod


@ClassAnnotation()
class DummyB: ...


@Pod()
class PodB: ...


class UnmanagedB: ...


@Pod()
def unmanaged_b() -> UnmanagedB:
    return UnmanagedB()


def hello_world() -> str:
    return "Hello World"
