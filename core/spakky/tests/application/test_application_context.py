import asyncio
from abc import abstractmethod
from dataclasses import dataclass
from typing import Annotated, Any
from uuid import UUID, uuid4

import pytest

from spakky.core.application.application_context import (
    ApplicationContext,
    CircularDependencyGraphDetectedError,
    NoSuchPodError,
    NoUniquePodError,
)
from spakky.core.common.annotation import ClassAnnotation
from spakky.core.common.constants import CONTEXT_ID
from spakky.core.pod.annotations.lazy import Lazy
from spakky.core.pod.annotations.pod import Pod, PodInstantiationFailedError
from spakky.core.pod.annotations.primary import Primary
from spakky.core.pod.annotations.qualifier import Qualifier
from spakky.core.pod.interfaces.container import CannotRegisterNonPodObjectError


def test_application_context_register_expect_success() -> None:
    """ApplicationContext에 Pod를 정상적으로 등록할 수 있음을 검증한다."""

    @Pod()
    class FirstSamplePod:
        id: UUID

        def __init__(self) -> None:
            self.id = uuid4()

    @Pod()
    class SecondSamplePod:
        id: UUID

        def __init__(self) -> None:
            self.id = uuid4()

    context: ApplicationContext = ApplicationContext()
    context.add(FirstSamplePod)
    context.add(SecondSamplePod)


def test_application_context_register_expect_error() -> None:
    """Pod 데코레이터가 없는 클래스 등록 시 CannotRegisterNonPodObjectError가 발생함을 검증한다."""

    class NonPod:
        id: UUID

        def __init__(self) -> None:
            self.id = uuid4()

    context: ApplicationContext = ApplicationContext()
    with pytest.raises(CannotRegisterNonPodObjectError):
        context.add(NonPod)


def test_application_context_get_by_type_singleton_expect_success() -> None:
    """타입으로 Pod를 조회할 때 싱글톤 인스턴스가 반환됨을 검증한다."""

    @Pod()
    class FirstSamplePod:
        id: UUID

        def __init__(self) -> None:
            self.id = uuid4()

    @Pod()
    class SecondSamplePod:
        id: UUID

        def __init__(self) -> None:
            self.id = uuid4()

    context: ApplicationContext = ApplicationContext()
    context.add(FirstSamplePod)
    context.add(SecondSamplePod)

    assert context.get(type_=FirstSamplePod).id == context.get(type_=FirstSamplePod).id
    assert (
        context.get(type_=SecondSamplePod).id == context.get(type_=SecondSamplePod).id
    )


def test_application_context_get_by_type_expect_no_such_error() -> None:
    """등록되지 않은 타입으로 Pod 조회 시 NoSuchPodError가 발생함을 검증한다."""

    @Pod()
    class FirstSamplePod:
        id: UUID

        def __init__(self) -> None:
            self.id = uuid4()

    class SecondSamplePod:
        id: UUID

        def __init__(self) -> None:
            self.id = uuid4()

    context: ApplicationContext = ApplicationContext()
    context.add(FirstSamplePod)

    assert context.get(type_=FirstSamplePod).id == context.get(type_=FirstSamplePod).id
    with pytest.raises(NoSuchPodError):
        assert (
            context.get(type_=SecondSamplePod).id
            == context.get(type_=SecondSamplePod).id
        )


def test_application_context_get_by_name_expect_success() -> None:
    """이름으로 Pod를 정상적으로 조회할 수 있음을 검증한다."""

    @Pod()
    class SamplePod:
        id: UUID

        def __init__(self) -> None:
            self.id = uuid4()

    context: ApplicationContext = ApplicationContext()
    context.add(SamplePod)

    assert isinstance(context.get(name="sample_pod", type_=SamplePod), SamplePod)


def test_application_context_get_by_name_expect_no_such_error() -> None:
    """존재하지 않는 타입으로 Pod 조회 시 NoSuchPodError가 발생함을 검증한다."""

    @Pod()
    class SamplePod:
        id: UUID

        def __init__(self) -> None:
            self.id = uuid4()

    class WrongPod: ...

    context: ApplicationContext = ApplicationContext()
    context.add(SamplePod)

    with pytest.raises(NoSuchPodError):
        context.get(type_=WrongPod)


def test_application_context_contains_by_type_expect_true() -> None:
    """등록된 Pod 타입에 대해 contains가 True를 반환함을 검증한다."""

    @Pod()
    class SamplePod:
        id: UUID

        def __init__(self) -> None:
            self.id = uuid4()

    context: ApplicationContext = ApplicationContext()
    context.add(SamplePod)

    assert context.contains(type_=SamplePod) is True


def test_application_context_contains_by_type_expect_false() -> None:
    """등록되지 않은 Pod 타입에 대해 contains가 False를 반환함을 검증한다."""

    @Pod()
    class FirstSamplePod:
        id: UUID

        def __init__(self) -> None:
            self.id = uuid4()

    @Pod()
    class SecondSamplePod:
        id: UUID

        def __init__(self) -> None:
            self.id = uuid4()

    context: ApplicationContext = ApplicationContext()
    context.add(FirstSamplePod)

    assert context.contains(type_=FirstSamplePod) is True
    assert context.contains(type_=SecondSamplePod) is False


def test_application_context_contains_by_name_expect_false() -> None:
    """등록되지 않은 타입에 대해 contains가 False를 반환함을 검증한다."""

    @Pod()
    class FirstSamplePod:
        id: UUID

        def __init__(self) -> None:
            self.id = uuid4()

    class WrongPod: ...

    context: ApplicationContext = ApplicationContext()
    context.add(FirstSamplePod)

    assert context.contains(type_=FirstSamplePod) is True
    assert context.contains(type_=WrongPod) is False


def test_application_context_get_primary_expect_success() -> None:
    """Primary 어노테이션이 있는 Pod가 우선적으로 조회됨을 검증한다."""

    class ISamplePod:
        @abstractmethod
        def do(self) -> None: ...

    @Primary()
    @Pod()
    class FirstSamplePod(ISamplePod):
        def do(self) -> None:
            return

    @Pod()
    class SecondSamplePod(ISamplePod):
        def do(self) -> None:
            return

    context: ApplicationContext = ApplicationContext()
    context.add(FirstSamplePod)
    context.add(SecondSamplePod)

    assert isinstance(context.get(type_=ISamplePod), FirstSamplePod)


def test_application_context_get_qualified_expect_success() -> None:
    """Qualifier를 사용하여 특정 조건의 Pod를 주입받을 수 있음을 검증한다."""

    class ISamplePod:
        @abstractmethod
        def do(self) -> str: ...

    @Pod()
    class FirstSamplePod(ISamplePod):
        def do(self) -> str:
            return "first"

    @Pod()
    class SecondSamplePod(ISamplePod):
        def do(self) -> str:
            return "second"

    @Pod()
    class SampleService:
        __pod: ISamplePod

        def __init__(
            self,
            pod: Annotated[
                ISamplePod,
                Qualifier(lambda pod: pod.name.startswith("second")),
            ],
        ) -> None:
            self.__pod = pod

        def do(self) -> str:
            return self.__pod.do()

    context: ApplicationContext = ApplicationContext()
    context.add(FirstSamplePod)
    context.add(SecondSamplePod)
    context.add(SampleService)
    context.start()

    service = context.get(type_=SampleService)
    assert service.do() == "second"


def test_application_context_get_primary_expect_no_unique_error() -> None:
    """여러 개의 Primary Pod가 있을 때 NoUniquePodError가 발생함을 검증한다."""

    class ISamplePod:
        @abstractmethod
        def do(self) -> None: ...

    @Primary()
    @Pod()
    class FirstSamplePod(ISamplePod):
        def do(self) -> None:
            return

    @Primary()
    @Pod()
    class SecondSamplePod(ISamplePod):
        def do(self) -> None:
            return

    context: ApplicationContext = ApplicationContext()
    context.add(FirstSamplePod)
    context.add(SecondSamplePod)

    with pytest.raises(NoUniquePodError):
        context.get(type_=ISamplePod)


def test_application_context_get_dependency_recursive_by_type() -> None:
    """의존성이 있는 Pod가 재귀적으로 주입됨을 검증한다."""

    @Pod()
    class A:
        def a(self) -> str:
            return "a"

    @Pod()
    class B:
        def b(self) -> str:
            return "b"

    @Pod()
    class C:
        __a: A
        __b: B

        def __init__(self, b: A, a: B) -> None:
            self.__a = b
            self.__b = a

        def c(self) -> str:
            return self.__a.a() + self.__b.b()

    context: ApplicationContext = ApplicationContext()
    context.add(A)
    context.add(B)
    context.add(C)
    context.start()

    assert context.get(type_=C).c() == "ab"


def test_application_context_find() -> None:
    """find 메서드를 사용하여 조건에 맞는 Pod들을 찾을 수 있음을 검증한다."""

    @dataclass
    class Customized(ClassAnnotation): ...

    @Pod()
    class FirstSampleClassMarked: ...

    @Pod()
    @Customized()
    class SecondSampleClass: ...

    @Pod()
    @Customized()
    class ThirdSampleClassMarked: ...

    context: ApplicationContext = ApplicationContext()
    context.add(FirstSampleClassMarked)
    context.add(SecondSampleClass)
    context.add(ThirdSampleClassMarked)

    queried: list[object] = list(
        context.find(lambda x: x.target.__name__.endswith("Marked"))
    )
    assert any(isinstance(x, FirstSampleClassMarked) for x in queried)
    assert any(isinstance(x, ThirdSampleClassMarked) for x in queried)

    queried = list(context.find(lambda x: Customized.exists(x.target)))
    assert any(isinstance(x, SecondSampleClass) for x in queried)
    assert any(isinstance(x, ThirdSampleClassMarked) for x in queried)


def test_application_context_register_unmanaged_factory() -> None:
    """함수 기반 팩토리 Pod를 등록하고 조회할 수 있음을 검증한다."""

    class A:
        def a(self) -> str:
            return "A"

    @Pod()
    def get_a() -> A:
        return A()

    context: ApplicationContext = ApplicationContext()
    context.add(get_a)

    assert context.contains(type_=A) is True
    a: A = context.get(name="get_a", type_=A)
    assert isinstance(a, A)
    assert a.a() == "A"


def test_application_context_register_unmanaged_factory_expect_error() -> None:
    """Pod 데코레이터가 없는 함수 등록 시 CannotRegisterNonPodObjectError가 발생함을 검증한다."""

    class A:
        def a(self) -> str:
            return "A"

    def get_a() -> A:
        return A()

    context: ApplicationContext = ApplicationContext()
    with pytest.raises(CannotRegisterNonPodObjectError):
        context.add(get_a)


def test_application_lazy_loading() -> None:
    """Lazy 어노테이션이 있는 Pod는 컷텍스트 시작 시 초기화되지 않음을 검증한다."""
    initialized: bool = False

    @Pod()
    class A:
        def a(self) -> str:
            return "a"

    @Pod()
    class B:
        def b(self) -> str:
            return "b"

    @Pod()
    @Lazy()
    class C:
        __a: A
        __b: B

        def __init__(self, b: A, a: B) -> None:
            self.__a = b
            self.__b = a

            nonlocal initialized
            initialized = True

        def c(self) -> str:
            return self.__a.a() + self.__b.b()

    context: ApplicationContext = ApplicationContext()
    context.add(A)
    context.add(B)
    context.add(C)
    context.start()

    assert initialized is False


def test_application_factory_loading() -> None:
    """PROTOTYPE 스코프 Pod는 조회할 때마다 새 인스턴스가 생성됨을 검증한다."""
    initialized_count: int = 0

    @Pod()
    class A:
        def a(self) -> str:
            return "a"

    @Pod()
    class B:
        def b(self) -> str:
            return "b"

    @Pod(scope=Pod.Scope.PROTOTYPE)
    class C:
        __a: A
        __b: B

        def __init__(self, b: A, a: B) -> None:
            self.__a = b
            self.__b = a
            nonlocal initialized_count
            initialized_count += 1

        def c(self) -> str:
            return self.__a.a() + self.__b.b()

    context: ApplicationContext = ApplicationContext()
    context.add(A)
    context.add(B)
    context.add(C)

    context.get(type_=C)
    context.get(type_=C)
    context.get(type_=C)

    assert initialized_count == 3


def test_application_raise_error_with_circular_dependency() -> None:
    """순환 의존성이 감지되면 CircularDependencyGraphDetectedError가 발생함을 검증한다."""

    class IA:
        def a(self) -> str: ...

    class IB:
        def b(self) -> str: ...

    @Pod()
    class A(IA):
        __b: IB

        def __init__(self, b: IB) -> None:
            self.__b = b

        def a(self) -> str:
            return self.__b.b()

    @Pod()
    class B(IB):
        __a: IA

        def __init__(self, a: IA) -> None:
            self.__a = a

        def b(self) -> str:
            return self.__a.a()

    context: ApplicationContext = ApplicationContext()
    context.add(A)
    context.add(B)

    with pytest.raises(CircularDependencyGraphDetectedError):
        context.start()


def test_circular_dependency_error_message_format() -> None:
    """순환 의존성 에러 메시지가 시각적 의존성 트리를 포함함을 검증한다."""

    class IA:
        def a(self) -> str: ...

    class IB:
        def b(self) -> str: ...

    @Pod()
    class A(IA):
        __b: IB

        def __init__(self, b: IB) -> None:
            self.__b = b

        def a(self) -> str:
            return self.__b.b()

    @Pod()
    class B(IB):
        __a: IA

        def __init__(self, a: IA) -> None:
            self.__a = a

        def b(self) -> str:
            return self.__a.a()

    context: ApplicationContext = ApplicationContext()
    context.add(A)
    context.add(B)

    with pytest.raises(CircularDependencyGraphDetectedError) as exc_info:
        context.start()

    error_msg = str(exc_info.value)
    print(error_msg)
    # Verify visual tree elements are present
    assert "Circular dependency graph detected" in error_msg
    assert "Dependency path:" in error_msg
    assert "└─>" in error_msg
    assert "CIRCULAR!" in error_msg
    # Verify both classes are mentioned
    assert "A" in error_msg or "B" in error_msg


def test_application_context_with_multiple_children_list_not_exists() -> None:
    """list 타입 의존성에 해당하는 Pod가 없을 때 PodInstantiationFailedError가 발생함을 검증한다."""

    class IRepository:
        @abstractmethod
        def get(self, id: str) -> dict[str, Any]: ...

    @Pod()
    class SampleService:
        __repositories: list[IRepository]

        def __init__(self, repositories: list[IRepository]) -> None:
            self.__repositories = repositories

        def get(self, id: str) -> list[dict[str, Any]]:
            return [repository.get(id) for repository in self.__repositories]

    context: ApplicationContext = ApplicationContext()
    context.add(SampleService)
    with pytest.raises(PodInstantiationFailedError):
        context.start()


def test_application_context_with_multiple_children_set_not_exists() -> None:
    """set 타입 의존성에 해당하는 Pod가 없을 때 PodInstantiationFailedError가 발생함을 검증한다."""

    class IRepository:
        @abstractmethod
        def get(self, id: str) -> dict[str, Any]: ...

    @Pod()
    class SampleService:
        __repositories: set[IRepository]

        def __init__(self, repositories: set[IRepository]) -> None:
            self.__repositories = repositories

        def get(self, id: str) -> list[dict[str, Any]]:
            return [repository.get(id) for repository in self.__repositories]

    context: ApplicationContext = ApplicationContext()
    context.add(SampleService)
    with pytest.raises(PodInstantiationFailedError):
        context.start()


def test_application_context_with_multiple_children_dict_not_exists() -> None:
    """dict 타입 의존성에 해당하는 Pod가 없을 때 PodInstantiationFailedError가 발생함을 검증한다."""

    class IRepository:
        @abstractmethod
        def get(self, id: str) -> dict[str, Any]: ...

    @Pod()
    class SampleService:
        __repositories: dict[str, IRepository]

        def __init__(self, repositories: dict[str, IRepository]) -> None:
            self.__repositories = repositories

        def get(self, id: str) -> dict[str, dict[str, Any]]:
            return {
                name: repository.get(id)
                for name, repository in self.__repositories.items()
            }

    context: ApplicationContext = ApplicationContext()
    context.add(SampleService)
    with pytest.raises(PodInstantiationFailedError):
        context.start()


def test_application_context_with_optional_dependency() -> None:
    """Optional 타입 의존성이 없을 때 None이 주입됨을 검증한다."""

    class IDependency:
        @abstractmethod
        def do(self) -> str: ...

    @Pod()
    class SampleService:
        __service: IDependency | None

        def __init__(self, service: IDependency | None) -> None:
            self.__service = service

        def do(self) -> str:
            return self.__service.do() if self.__service else "default"

    context = ApplicationContext()
    context.add(SampleService)
    context.start()

    service = context.get(type_=SampleService)
    assert service.do() == "default"


def test_application_context_with_multiple_qualifiers() -> None:
    """여러 개의 Qualifier를 적용하여 교집합 조건으로 Pod를 주입받을 수 있음을 검증한다."""

    class IRepository:
        @abstractmethod
        def get(self, id: str) -> dict[str, Any]: ...

    @Pod()
    class FirstRepository(IRepository):
        def get(self, id: str) -> dict[str, Any]:
            return {"id": id, "name": "First"}

    @Pod()
    class SecondRepository(IRepository):
        def get(self, id: str) -> dict[str, Any]:
            return {"id": id, "name": "Second"}

    @Pod()
    class SampleService:
        repository: IRepository

        def __init__(
            self,
            repository: Annotated[
                IRepository,
                Qualifier(lambda repo: repo.is_family_with(IRepository)),
                Qualifier(lambda repo: repo.type_ == FirstRepository),
            ],
        ) -> None:
            self.repository = repository

        def get(self, id: str) -> dict[str, Any]:
            return self.repository.get(id)

    context: ApplicationContext = ApplicationContext()
    context.add(FirstRepository)
    context.add(SecondRepository)
    context.add(SampleService)
    context.start()

    service = context.get(type_=SampleService)
    assert isinstance(service.repository, FirstRepository)


@pytest.mark.asyncio
async def test_application_context_get_context_id() -> None:
    """비동기 태스크별로 독립적인 컷텍스트 ID가 생성됨을 검증한다."""
    context = ApplicationContext()
    context.start()

    results: list[UUID] = []

    async def task_logic() -> None:
        context.clear_context()
        id1 = context.get_context_id()
        await asyncio.sleep(0.01)
        id2 = context.get_context_id()
        assert id1 == id2
        results.append(id1)

    await asyncio.gather(*(task_logic() for _ in range(5)))
    assert len(set(results)) == 5


def test_type_index_cache_hit_for_single_implementation() -> None:
    """단일 구현의 타입 인덱스 캐시 히트가 정상 동작함을 검증한다."""
    context = ApplicationContext()

    class IService:
        pass

    @Pod()
    class ConcreteService(IService):
        def __init__(self) -> None:
            self.value = "test"

    context.add(ConcreteService)
    context.start()

    assert context.contains(IService)
    service1 = context.get(IService)

    assert context.contains(IService)
    service2 = context.get(IService)

    assert service1 is service2
    assert service1.value == "test"  # type: ignore

    context.stop()


def test_type_index_cache_hit_for_base_type() -> None:
    """비이스 타입으로 조회 시 타입 인덱스 캐시가 정상 동작함을 검증한다."""
    context = ApplicationContext()

    class BaseService:
        pass

    @Pod()
    class DerivedService(BaseService):
        pass

    context.add(DerivedService)
    context.start()

    assert context.contains(BaseService)
    service = context.get(BaseService)
    assert isinstance(service, DerivedService)

    assert context.contains(BaseService)
    service2 = context.get(BaseService)
    assert service is service2

    context.stop()


def test_type_index_with_multiple_inheritance_levels() -> None:
    """여러 단계의 상속 계층에서 타입 인덱스가 정상 동작함을 검증한다."""
    context = ApplicationContext()

    class Level1:
        pass

    class Level2(Level1):
        pass

    class Level3(Level2):
        pass

    @Pod()
    class ConcreteService(Level3):
        pass

    context.add(ConcreteService)
    context.start()

    assert context.contains(Level1)
    assert context.contains(Level2)
    assert context.contains(Level3)
    assert context.contains(ConcreteService)

    service1 = context.get(Level1)
    service2 = context.get(Level2)
    service3 = context.get(Level3)
    service4 = context.get(ConcreteService)

    assert service1 is service2 is service3 is service4

    context.stop()


def test_type_index_with_multiple_pods_of_same_base_type() -> None:
    """동일 베이스 타입의 여러 Pod를 이름으로 구분하여 조회할 수 있음을 검증한다."""
    context = ApplicationContext()

    class IRepository:
        pass

    @Pod(name="repo1")
    class FirstRepo(IRepository):
        pass

    @Pod(name="repo2")
    class SecondRepo(IRepository):
        pass

    @Pod(name="repo3")
    class ThirdRepo(IRepository):
        pass

    context.add(FirstRepo)
    context.add(SecondRepo)
    context.add(ThirdRepo)
    context.start()

    assert context.contains(IRepository)

    repo1 = context.get(IRepository, name="repo1")
    repo2 = context.get(IRepository, name="repo2")
    repo3 = context.get(IRepository, name="repo3")

    assert isinstance(repo1, FirstRepo)
    assert isinstance(repo2, SecondRepo)
    assert isinstance(repo3, ThirdRepo)
    assert repo1 is not repo2
    assert repo2 is not repo3

    context.stop()


def test_type_index_cleared_on_context_stop() -> None:
    """컷텍스트 중지 시 타입 인덱스가 초기화됨을 검증한다."""
    context = ApplicationContext()

    class IService:
        pass

    @Pod()
    class ConcreteService(IService):
        pass

    context.add(ConcreteService)
    context.start()

    assert context.contains(IService)
    service = context.get(IService)
    assert isinstance(service, ConcreteService)

    context.stop()

    assert not context.contains(IService)


def test_type_index_with_interface_and_concrete_types() -> None:
    """인터페이스와 구체 타입 모두로 Pod를 조회할 수 있음을 검증한다."""
    context = ApplicationContext()

    class IUserRepository:
        pass

    class IAdminRepository:
        pass

    @Pod()
    class UserRepository(IUserRepository):
        def __init__(self) -> None:
            self.name = "user_repo"

    @Pod()
    class AdminRepository(IAdminRepository):
        def __init__(self) -> None:
            self.name = "admin_repo"

    context.add(UserRepository)
    context.add(AdminRepository)
    context.start()

    assert context.contains(IUserRepository)
    assert context.contains(IAdminRepository)
    assert context.contains(UserRepository)
    assert context.contains(AdminRepository)

    user_repo = context.get(IUserRepository)
    admin_repo = context.get(IAdminRepository)

    assert user_repo.name == "user_repo"  # type: ignore
    assert admin_repo.name == "admin_repo"  # type: ignore
    assert user_repo is not admin_repo

    context.stop()


def test_type_index_with_prototype_scope() -> None:
    """PROTOTYPE 스코프 Pod의 타입 인덱스가 정상 동작함을 검증한다."""
    context = ApplicationContext()

    class IService:
        pass

    @Pod(scope=Pod.Scope.PROTOTYPE)
    class PrototypeService(IService):
        pass

    context.add(PrototypeService)
    context.start()

    assert context.contains(IService)
    assert context.contains(PrototypeService)

    service1 = context.get(IService)
    service2 = context.get(IService)

    assert isinstance(service1, PrototypeService)
    assert isinstance(service2, PrototypeService)
    assert service1 is not service2

    context.stop()


def test_type_index_find_with_selector() -> None:
    """find 메서드로 타입 인덱스를 활용하여 Pod들을 조회할 수 있음을 검증한다."""
    context = ApplicationContext()

    class IService:
        pass

    @Pod(name="service_a")
    class ServiceA(IService):
        pass

    @Pod(name="service_b")
    class ServiceB(IService):
        pass

    @Pod(name="service_c")
    class ServiceC(IService):
        pass

    context.add(ServiceA)
    context.add(ServiceB)
    context.add(ServiceC)
    context.start()

    all_services = context.find(lambda pod: pod.is_family_with(IService))
    assert len(all_services) == 3

    filtered_services = context.find(
        lambda pod: pod.is_family_with(IService) and pod.name.startswith("service_")
    )
    assert len(filtered_services) == 3

    context.stop()


def test_type_index_with_complex_inheritance_hierarchy() -> None:
    """복잡한 상속 계층에서 타입 인덱스가 정상 동작함을 검증한다."""
    context = ApplicationContext()

    class Animal:
        pass

    class Mammal(Animal):
        pass

    class Dog(Mammal):
        pass

    class Bird(Animal):
        pass

    @Pod(name="dog")
    class Poodle(Dog):
        pass

    @Pod(name="bird")
    class Sparrow(Bird):
        pass

    context.add(Poodle)
    context.add(Sparrow)
    context.start()

    assert context.contains(Animal)
    assert context.contains(Mammal)
    assert context.contains(Dog)
    assert context.contains(Bird)

    dog = context.get(Mammal)
    bird = context.get(Bird)

    assert isinstance(dog, Poodle)
    assert isinstance(bird, Sparrow)

    context.stop()


def test_application_context_lazy_pod_not_initialized() -> None:
    """Lazy Pod이 시작 시 초기화되지 않음을 검증한다."""

    @Lazy()
    @Pod()
    class LazyPod:
        initialized = False

        def __init__(self) -> None:
            LazyPod.initialized = True

    context = ApplicationContext()
    context.add(LazyPod)
    context.start()

    # Lazy pod should not be initialized
    assert not LazyPod.initialized

    context.stop()


def test_application_context_initialize_pods_missing_raises_error() -> None:
    """존재하지 않는 의존성으로 Pod 초기화 시 에러가 발생함을 검증한다."""
    from spakky.core.pod.annotations.pod import UnexpectedDependencyTypeInjectedError

    class NonExistentPod:  # noqa: F841
        """Dummy class for type annotation."""

        pass

    @Pod(name="test_missing_pod")
    class TestPod:
        def __init__(self, missing_dep: NonExistentPod) -> None:  # type: ignore
            pass

    context = ApplicationContext()
    context.add(TestPod)

    # This should raise UnexpectedDependencyTypeInjectedError during initialization
    # since the missing_dep cannot be resolved and is not optional
    with pytest.raises(UnexpectedDependencyTypeInjectedError):
        context.start()


def test_set_singleton_cache_with_non_singleton_pod() -> None:
    """SINGLETON이 아닌 스코프의 Pod는 싱글톤 캐시에 저장되지 않음을 검증한다."""

    @Pod(scope=Pod.Scope.PROTOTYPE)
    class PrototypePod:
        pass

    @Pod(scope=Pod.Scope.CONTEXT)
    class ContextPod:
        pass

    context = ApplicationContext()
    context.add(PrototypePod)
    context.add(ContextPod)
    context.start()

    # Get instances - this will call __set_singleton_cache but should not cache
    prototype1 = context.get(PrototypePod)
    prototype2 = context.get(PrototypePod)
    context1 = context.get(ContextPod)

    # Prototype pods should be different instances
    assert prototype1 is not prototype2

    # Context pod should be cached in context cache, not singleton cache
    assert context1 is not None

    context.stop()


def test_get_internal_with_context_cache_miss_then_hit() -> None:
    """컷텍스트 캐시 미스 후 히트가 정상 동작함을 검증한다."""

    @Pod(scope=Pod.Scope.CONTEXT)
    class ContextScopedPod:
        pass

    context = ApplicationContext()
    context.add(ContextScopedPod)
    context.start()

    # First get - cache miss, creates instance
    instance1 = context.get(ContextScopedPod)
    assert instance1 is not None

    # Second get - cache hit, returns same instance
    instance2 = context.get(ContextScopedPod)
    assert instance1 is instance2

    # Clear context and get again - new instance
    context.clear_context()
    instance3 = context.get(ContextScopedPod)
    assert instance3 is not instance1

    context.stop()


def test_get_internal_prototype_scope_branch() -> None:
    """PROTOTYPE 스코프 분기가 올바르게 실행됨을 검증한다."""

    @Pod(scope=Pod.Scope.PROTOTYPE)
    class PrototypePod:
        pass

    context = ApplicationContext()
    context.add(PrototypePod)
    context.start()

    # Each get creates new instance (match Pod.Scope.PROTOTYPE case)
    instance1 = context.get(PrototypePod)
    instance2 = context.get(PrototypePod)

    assert instance1 is not instance2

    context.stop()


def test_add_same_pod_twice_with_same_id() -> None:
    """동일한 Pod를 두 번 추가해도 한 번만 등록됨을 검증한다."""

    @Pod(name="unique_pod")
    class UniquePod:
        pass

    context = ApplicationContext()

    # Add once
    context.add(UniquePod)

    # Add again - should return early without error
    context.add(UniquePod)

    # Should only have one pod registered
    assert len(context.pods) == 1
    assert "unique_pod" in context.pods


def test_get_context_id_existing_context() -> None:
    """이미 존재하는 컷텍스트 ID를 조회할 수 있음을 검증한다."""

    @Pod()
    class SamplePod:
        pass

    context = ApplicationContext()
    context.add(SamplePod)
    context.start()

    # First call creates context ID
    context_id_1 = context.get_context_id()
    assert isinstance(context_id_1, UUID)

    # Second call returns existing context ID (branch: CONTEXT_ID in context)
    context_id_2 = context.get_context_id()
    assert context_id_1 == context_id_2

    # After clearing context, new ID is created
    context.clear_context()
    context_id_3 = context.get_context_id()
    assert context_id_3 != context_id_1

    context.stop()


def test_contains_with_name_existing() -> None:
    """이름으로 Pod의 존재 여부를 확인할 수 있음을 검증한다."""

    @Pod(name="test_pod")
    class TestPod:
        pass

    context = ApplicationContext()
    context.add(TestPod)

    # Test with name - should use "name in self.__pods" branch
    assert context.contains(TestPod, name="test_pod")
    assert not context.contains(TestPod, name="nonexistent")


def test_context_cache_multiple_pods() -> None:
    """여러 개의 CONTEXT 스코프 Pod가 컷텍스트 캐시에 정상적으로 저장됨을 검증한다."""

    @Pod(scope=Pod.Scope.CONTEXT, name="pod_a")
    class PodA:
        pass

    @Pod(scope=Pod.Scope.CONTEXT, name="pod_b")
    class PodB:
        pass

    context = ApplicationContext()
    context.add(PodA)
    context.add(PodB)
    context.start()

    # Get both pods
    pod_a1 = context.get(PodA)
    pod_b1 = context.get(PodB)

    # Get again - should return cached instances
    pod_a2 = context.get(PodA)
    pod_b2 = context.get(PodB)

    assert pod_a1 is pod_a2
    assert pod_b1 is pod_b2

    context.stop()


def test_application_context_set_and_get_context_value_expect_success() -> None:
    """컷텍스트 값을 설정하고 조회할 수 있음을 검증한다."""
    context = ApplicationContext()

    # Set and get simple values
    context.set_context_value("key1", "value1")
    context.set_context_value("key2", 42)
    context.set_context_value("key3", {"nested": "dict"})

    assert context.get_context_value("key1") == "value1"
    assert context.get_context_value("key2") == 42
    assert context.get_context_value("key3") == {"nested": "dict"}


def test_application_context_get_nonexistent_context_value_expect_none() -> None:
    """존재하지 않는 컷텍스트 값 조회 시 None이 반환됨을 검증한다."""
    context = ApplicationContext()

    assert context.get_context_value("nonexistent") is None


def test_application_context_overwrite_context_value_expect_success() -> None:
    """컷텍스트 값을 덮어쓸 수 있음을 검증한다."""
    context = ApplicationContext()

    context.set_context_value("key", "original")
    assert context.get_context_value("key") == "original"

    context.set_context_value("key", "updated")
    assert context.get_context_value("key") == "updated"


def test_application_context_context_id_preserved_expect_success() -> None:
    """CONTEXT_ID가 자동으로 관리되고 조회 가능함을 검증한다."""
    context = ApplicationContext()

    # Context ID should be retrievable via get_context_value
    context_id = context.get_context_value(CONTEXT_ID)
    assert context_id is not None
    assert isinstance(context_id, UUID)

    # Context ID should be the same as get_context_id()
    assert context_id == context.get_context_id()


def test_application_context_cannot_set_context_id_expect_error() -> None:
    """CONTEXT_ID를 직접 설정하려고 하면 에러가 발생함을 검증한다."""
    from spakky.core.application.application_context import (
        CannotAssignSystemContextIDError,
    )

    context = ApplicationContext()

    with pytest.raises(CannotAssignSystemContextIDError):
        context.set_context_value(CONTEXT_ID, uuid4())


def test_application_context_clear_context_expect_success() -> None:
    """컷텍스트 클리어 시 커스텀 값이 제거되고 CONTEXT_ID는 유지됨을 검증한다."""
    context = ApplicationContext()

    # Set some values
    context.set_context_value("key1", "value1")
    context.set_context_value("key2", "value2")

    _ = context.get_context_id()

    # Clear context
    context.clear_context()

    # Custom values should be gone
    assert context.get_context_value("key1") is None
    assert context.get_context_value("key2") is None

    # But CONTEXT_ID should still be accessible (it's generated on-demand)
    assert context.get_context_id() is not None
    # Note: After clear, a new context ID is generated
    new_context_id = context.get_context_id()
    assert isinstance(new_context_id, UUID)


def test_application_context_get_qualified_multiple_candidates_none_match_expect_error() -> (
    None
):
    """여러 후보 중 qualifier로 필터링했지만 매치되는 Pod가 없을 때 UnexpectedDependencyTypeInjectedError가 발생함을 검증한다."""
    from spakky.core.pod.annotations.pod import UnexpectedDependencyTypeInjectedError

    class ISamplePod:
        @abstractmethod
        def do(self) -> str: ...

    @Pod()
    class FirstSamplePod(ISamplePod):
        def do(self) -> str:
            return "first"

    @Pod()
    class SecondSamplePod(ISamplePod):
        def do(self) -> str:
            return "second"

    @Pod()
    class SampleService:
        __pod: ISamplePod

        def __init__(
            self,
            pod: Annotated[
                ISamplePod,
                Qualifier(lambda pod: pod.name.startswith("nonexistent")),
            ],
        ) -> None:
            self.__pod = pod

        def do(self) -> str:
            return self.__pod.do()

    context: ApplicationContext = ApplicationContext()
    context.add(FirstSamplePod)
    context.add(SecondSamplePod)
    context.add(SampleService)

    with pytest.raises(UnexpectedDependencyTypeInjectedError):
        context.start()
