import pytest

from spakky.auth import (
    AUTHENTICATED_REQUIREMENT_REF,
    AuthRequirementKind,
    ConflictingAuthMetadataError,
    get_effective_auth_metadata,
    has_auth_boundary_metadata,
    protected,
    public_access,
    require_role,
    require_scope,
)


def test_missing_decorator_metadata_allows_all_boundaries() -> None:
    def boundary() -> str:
        return "ok"

    metadata = get_effective_auth_metadata(boundary)

    assert not metadata.public_access
    assert not metadata.protected
    assert metadata.requirements == ()
    assert not has_auth_boundary_metadata(boundary)


def test_public_access_marker_declares_explicit_public_boundary() -> None:
    @public_access
    def boundary() -> str:
        return "ok"

    metadata = get_effective_auth_metadata(boundary)

    assert metadata.public_access
    assert metadata.requirements == ()
    assert has_auth_boundary_metadata(boundary)


def test_protected_marker_requires_authenticated_context() -> None:
    @protected
    def boundary() -> str:
        return "ok"

    metadata = get_effective_auth_metadata(boundary)

    assert metadata.requirements[0].kind is AuthRequirementKind.AUTHENTICATED
    assert metadata.requirements[0].ref == AUTHENTICATED_REQUIREMENT_REF


def test_stacked_requirements_keep_order_and_deduplicate_exact_matches() -> None:
    @require_scope("documents:read")
    @require_role("role:admin")
    @require_scope("documents:read")
    def boundary() -> str:
        return "ok"

    metadata = get_effective_auth_metadata(boundary)

    assert [(item.kind, item.ref) for item in metadata.requirements] == [
        (AuthRequirementKind.SCOPE, "documents:read"),
        (AuthRequirementKind.ROLE, "role:admin"),
    ]


def test_class_and_method_requirements_are_combined_with_and_semantics() -> None:
    @require_role("role:admin")
    class DocumentController:
        @require_scope("documents:read")
        def read(self) -> str:
            return "ok"

    controller = DocumentController()
    metadata = get_effective_auth_metadata(controller.read)

    assert [(item.kind, item.ref) for item in metadata.requirements] == [
        (AuthRequirementKind.ROLE, "role:admin"),
        (AuthRequirementKind.SCOPE, "documents:read"),
    ]
    assert has_auth_boundary_metadata(controller)
    assert has_auth_boundary_metadata(DocumentController)


def test_public_access_conflicts_with_effective_protected_metadata() -> None:
    @public_access
    class DocumentController:
        @require_scope("documents:read")
        def read(self) -> str:
            return "ok"

    controller = DocumentController()

    with pytest.raises(ConflictingAuthMetadataError):
        get_effective_auth_metadata(controller.read)


def test_owner_type_parameter_supports_unbound_method_metadata_aggregation() -> None:
    @require_role("role:admin")
    class DocumentController:
        @require_scope("documents:read")
        def read(self) -> str:
            return "ok"

    metadata = get_effective_auth_metadata(
        DocumentController.read,
        owner_type=DocumentController,
    )

    assert [(item.kind, item.ref) for item in metadata.requirements] == [
        (AuthRequirementKind.ROLE, "role:admin"),
        (AuthRequirementKind.SCOPE, "documents:read"),
    ]


def test_method_only_metadata_is_discovered_from_class_and_bound_method() -> None:
    class DocumentController:
        @require_scope("documents:read")
        def read(self) -> str:
            return "ok"

    controller = DocumentController()

    assert has_auth_boundary_metadata(DocumentController)
    assert has_auth_boundary_metadata(controller)
    assert has_auth_boundary_metadata(controller.read)


def test_class_only_metadata_is_discovered_from_bound_method_owner() -> None:
    @require_role("role:admin")
    class DocumentController:
        def read(self) -> str:
            return "ok"

    controller = DocumentController()

    assert has_auth_boundary_metadata(controller.read)


def test_class_without_auth_metadata_is_not_an_auth_boundary() -> None:
    class DocumentController:
        def read(self) -> str:
            return "ok"

    assert not has_auth_boundary_metadata(DocumentController)


def test_classmethod_owner_type_is_resolved_from_bound_class() -> None:
    class DocumentController:
        @classmethod
        @require_scope("documents:read")
        def read(cls) -> str:
            return "ok"

    metadata = get_effective_auth_metadata(DocumentController.read)

    assert [(item.kind, item.ref) for item in metadata.requirements] == [
        (AuthRequirementKind.SCOPE, "documents:read"),
    ]
