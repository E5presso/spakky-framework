from spakky.core.common.annotation import ClassAnnotation
from spakky.core.pod.annotations.pod import Pod


@ClassAnnotation()
class SecondDummyB: ...


@Pod()
class SecondPodB: ...


class SecondUnmanagedB: ...


@Pod()
def unmanaged_b() -> SecondUnmanagedB:
    return SecondUnmanagedB()


def hello_world() -> str:
    return "Hello World"
