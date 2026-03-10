from abc import abstractmethod

from spakky.core.application.application_context import ApplicationContext
from spakky.core.pod.annotations.pod import Pod
from spakky.core.pod.inject import inject


def test_inject_to_function_by_type() -> None:
    """inject 함수가 타입을 기반으로 함수에 의존성을 주입함을 검증한다."""

    class IA:
        @abstractmethod
        def a(self) -> str: ...

    class IB:
        @abstractmethod
        def b(self) -> str: ...

    class IC:
        @abstractmethod
        def c(self) -> str: ...

    @Pod()
    class A(IA):
        def a(self) -> str:
            return "a"

    @Pod()
    class B(IB):
        def b(self) -> str:
            return "b"

    @Pod()
    class C(IC):
        __a: IA
        __b: IB

        def __init__(self, a: IA, b: IB) -> None:
            self.__a = a
            self.__b = b

        def c(self) -> str:
            return self.__a.a() + self.__b.b()

    context: ApplicationContext = ApplicationContext()
    context.add(A)
    context.add(B)
    context.add(C)

    def execute_c(c: IC = inject(context, type_=IC)) -> str:
        return c.c()

    assert execute_c() == "ab"


def test_inject_with_name() -> None:
    """inject 함수가 name 파라미터를 사용하여 특정 이름의 Pod을 주입함을 검증한다."""

    class IService:
        @abstractmethod
        def get_value(self) -> str: ...

    @Pod(name="service_a")
    class ServiceA(IService):
        def get_value(self) -> str:
            return "service_a"

    @Pod(name="service_b")
    class ServiceB(IService):
        def get_value(self) -> str:
            return "service_b"

    context: ApplicationContext = ApplicationContext()
    context.add(ServiceA)
    context.add(ServiceB)

    # Inject by name
    service_a = inject(context, type_=IService, name="service_a")
    service_b = inject(context, type_=IService, name="service_b")

    assert service_a.get_value() == "service_a"
    assert service_b.get_value() == "service_b"
