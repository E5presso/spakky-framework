"""Shared fixtures for spakky-policy tests."""

import pytest

from spakky.auth import AuthClaim, AuthContext, AuthSubject
from spakky.plugins.policy.loader import policy_document_from_mapping
from spakky.plugins.policy.model import PolicyDocument


@pytest.fixture
def auth_context() -> AuthContext:
    """Authenticated user with RBAC/PBAC/ABAC attributes."""
    return AuthContext(
        subject=AuthSubject(id="user:alice", display_name="Alice"),
        issuer="issuer:test",
        tenant="tenant:acme",
        roles=("role:editor",),
        scopes=("scope:articles",),
        claims=(
            AuthClaim(name="department", value="engineering"),
            AuthClaim(name="region", value="kr"),
            AuthClaim(name="email", value="alice@example.com"),
            AuthClaim(name="mfa", value=True),
        ),
    )


@pytest.fixture
def policy_document() -> PolicyDocument:
    """Canonical policy document covering RBAC, PBAC, and ABAC."""
    return policy_document_from_mapping(
        {
            "version": "2026-06",
            "metadata": {
                "name": "authz",
                "description": "test policy",
                "labels": ["auth", "policy"],
            },
            "subjects": [
                {
                    "ref": "user:alice",
                    "roles": ["role:auditor"],
                    "scopes": ["scope:reports"],
                    "permissions": ["permission:direct"],
                    "claims": {"tier": "gold"},
                    "tenant": "tenant:acme",
                }
            ],
            "resources": [{"ref": "article:1", "tenant": "tenant:acme"}],
            "actions": [{"ref": "article:read"}],
            "permissions": [
                {
                    "ref": "permission:article-read",
                    "resources": ["article:1"],
                    "actions": ["article:read"],
                },
                {"ref": "permission:report-read"},
                {"ref": "permission:direct"},
            ],
            "roles": [
                {
                    "ref": "role:editor",
                    "permissions": ["permission:article-read"],
                },
                {"ref": "role:auditor", "permissions": ["permission:report-read"]},
            ],
            "scopes": [
                {
                    "ref": "scope:articles",
                    "permissions": ["permission:article-read"],
                },
                {"ref": "scope:reports", "permissions": ["permission:report-read"]},
            ],
            "conditions": [
                {
                    "ref": "condition:trusted-region",
                    "operator": "in",
                    "key": "region",
                    "value": ["kr", "jp"],
                }
            ],
            "policies": [
                {
                    "ref": "policy:article-read",
                    "description": "article read policy",
                    "statements": [
                        {
                            "ref": "allow-editor",
                            "effect": "allow",
                            "roles": ["role:editor"],
                            "permissions": ["permission:article-read"],
                            "resources": ["article:1"],
                            "actions": ["article:read"],
                            "tenants": ["tenant:acme"],
                            "condition": {
                                "all": [
                                    {
                                        "operator": "equals",
                                        "key": "department",
                                        "value": "engineering",
                                    },
                                    "condition:trusted-region",
                                    {"operator": "exists", "key": "mfa"},
                                ]
                            },
                        }
                    ],
                },
                {
                    "ref": "policy:deny-email",
                    "statements": [
                        {
                            "ref": "allow-email-domain",
                            "effect": "allow",
                            "resources": ["mail:1"],
                            "condition": {
                                "operator": "contains",
                                "key": "email",
                                "value": "example.com",
                            },
                        },
                        {
                            "ref": "deny-email-domain",
                            "effect": "deny",
                            "resources": ["mail:1"],
                            "condition": {
                                "operator": "not_equals",
                                "key": "email",
                                "value": "blocked@example.com",
                            },
                        },
                    ],
                },
                {
                    "ref": "policy:composed",
                    "statements": [
                        {
                            "ref": "allow-any-not",
                            "effect": "allow",
                            "condition": {
                                "any": [
                                    {
                                        "operator": "equals",
                                        "key": "department",
                                        "value": "finance",
                                    },
                                    {
                                        "not": {
                                            "operator": "equals",
                                            "key": "region",
                                            "value": "us",
                                        }
                                    },
                                ]
                            },
                        }
                    ],
                },
            ],
        }
    )
