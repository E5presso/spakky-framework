import asyncio
from abc import abstractmethod
from dataclasses import dataclass
from typing import Annotated, Any, Protocol, runtime_checkable
from uuid import UUID, uuid4

import pytest

from spakky.application.application_context import (
    ApplicationContext,
    CircularDependencyGraphDetectedError,
    NoSuchPodError,
    NoUniquePodError,
)
from spakky.core.annotation import ClassAnnotation
from spakky.core.mutability import immutable
from spakky.domain.usecases.command import AbstractCommand, ICommandUseCase
from spakky.pod.annotations.lazy import Lazy
from spakky.pod.annotations.pod import Pod, PodInstantiationFailedError
from spakky.pod.annotations.primary import Primary
from spakky.pod.annotations.qualifier import Qualifier
from spakky.pod.interfaces.container import CannotRegisterNonPodObjectError


def test_application_context_register_expect_success() -> None:
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
    class NonPod:
        id: UUID

        def __init__(self) -> None:
            self.id = uuid4()

    context: ApplicationContext = ApplicationContext()
    with pytest.raises(CannotRegisterNonPodObjectError):
        context.add(NonPod)


def test_application_context_get_by_type_singleton_expect_success() -> None:
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
    @Pod()
    class SamplePod:
        id: UUID

        def __init__(self) -> None:
            self.id = uuid4()

    context: ApplicationContext = ApplicationContext()
    context.add(SamplePod)

    assert isinstance(context.get(name="sample_pod", type_=SamplePod), SamplePod)


def test_application_context_get_by_name_expect_no_such_error() -> None:
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
    @Pod()
    class SamplePod:
        id: UUID

        def __init__(self) -> None:
            self.id = uuid4()

    context: ApplicationContext = ApplicationContext()
    context.add(SamplePod)

    assert context.contains(type_=SamplePod) is True


def test_application_context_contains_by_type_expect_false() -> None:
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
    class ISamplePod(Protocol):
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
    class ISamplePod(Protocol):
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
    class ISamplePod(Protocol):
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
    class A:
        def a(self) -> str:
            return "A"

    def get_a() -> A:
        return A()

    context: ApplicationContext = ApplicationContext()
    with pytest.raises(CannotRegisterNonPodObjectError):
        context.add(get_a)


def test_application_lazy_loading() -> None:
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
    @runtime_checkable
    class IA(Protocol):
        def a(self) -> str: ...

    @runtime_checkable
    class IB(Protocol):
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


def test_application_context_with_generic_interface() -> None:
    @immutable
    class SignupCommand(AbstractCommand):
        username: str
        password: str

    class ISignupCommandUseCase(ICommandUseCase[SignupCommand, None], Protocol):
        pass

    @immutable
    class SigninCommand(AbstractCommand):
        username: str
        password: str

    class ISigninCommandUseCase(ICommandUseCase[SigninCommand, None], Protocol):
        pass

    @Pod()
    class SignupCommandUseCase(ISignupCommandUseCase):
        users: dict[str, SignupCommand]

        def __init__(self) -> None:
            self.users = {}

        def execute(self, command: SignupCommand) -> None:
            self.users[command.username] = command

    @Pod()
    class SigninCommandUseCase(ISigninCommandUseCase):
        logs: list[SigninCommand]

        def __init__(self) -> None:
            self.logs = []

        def execute(self, command: SigninCommand) -> None:
            self.logs.append(command)

    context: ApplicationContext = ApplicationContext()
    context.add(SignupCommandUseCase)
    context.add(SigninCommandUseCase)
    context.start()

    signup = context.get(type_=ICommandUseCase[SignupCommand, None])
    signup.execute(SignupCommand(username="user", password="password"))
    signup = context.get(type_=SignupCommandUseCase)
    assert "user" in signup.users

    signin = context.get(type_=ICommandUseCase[SigninCommand, None])
    signin.execute(SigninCommand(username="user", password="password"))
    signin = context.get(type_=SigninCommandUseCase)
    assert len(signin.logs) == 1


def test_application_context_with_multiple_children_list_not_exists() -> None:
    @runtime_checkable
    class IRepository(Protocol):
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
    @runtime_checkable
    class IRepository(Protocol):
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
    @runtime_checkable
    class IRepository(Protocol):
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
    @runtime_checkable
    class IDependency(Protocol):
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
    @runtime_checkable
    class IRepository(Protocol):
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
    """Test that lazy pods are not initialized during start."""

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
    """Test that initializing missing pod raises error."""
    from spakky.pod.annotations.pod import UnexpectedDependencyTypeInjectedError

    class NonExistentPod:  # noqa: F841
        """Dummy class for type annotation."""

        pass

    @Pod(name="test_missing_pod")
    class TestPod:
        def __init__(self, missing_dep: NonExistentPod) -> None:  # pyrefly: ignore
            pass

    context = ApplicationContext()
    context.add(TestPod)

    # This should raise UnexpectedDependencyTypeInjectedError during initialization
    # since the missing_dep cannot be resolved and is not optional
    with pytest.raises(UnexpectedDependencyTypeInjectedError):
        context.start()


def test_set_singleton_cache_with_non_singleton_pod() -> None:
    """Test that __set_singleton_cache only caches SINGLETON scoped pods."""

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
    """Test context cache behavior with cache miss and then hit."""

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
    """Test that prototype scope branch is executed (match case)."""

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
    """Test that adding the same pod twice (same ID) returns early."""

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
    """Test get_context_id when context already has an ID."""

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
    """Test contains method with name qualifier when pod exists."""

    @Pod(name="test_pod")
    class TestPod:
        pass

    context = ApplicationContext()
    context.add(TestPod)

    # Test with name - should use "name in self.__pods" branch
    assert context.contains(TestPod, name="test_pod")
    assert not context.contains(TestPod, name="nonexistent")


def test_context_cache_multiple_pods() -> None:
    """Test context cache with multiple context-scoped pods."""

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
