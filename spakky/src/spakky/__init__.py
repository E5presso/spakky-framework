"""Spakky - A Spring-inspired dependency injection framework for Python.

Spakky provides a comprehensive DI/IoC container with aspect-oriented programming
support, designed for building maintainable and testable Python applications.

Key Features:
    - Dependency Injection via @Pod decorator and constructor injection
    - Aspect-Oriented Programming with @Aspect, @Before, @After, @Around
    - Stereotype annotations (@Controller, @UseCase) for semantic clarity
    - Plugin system for framework extensions
    - Full async/await support

Example:
    >>> from spakky.application.application import SpakkyApplication
    >>> from spakky.pod.annotations.pod import Pod
    >>>
    >>> @Pod()
    ... class UserService:
    ...     def __init__(self, repository: UserRepository) -> None:
    ...         self.repository = repository
    >>>
    >>> app = SpakkyApplication(context).scan(my_package).start()
    >>> service = app.container.get(UserService)
"""
