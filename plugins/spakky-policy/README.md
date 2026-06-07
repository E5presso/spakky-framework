# spakky-policy

`spakky-policy` loads YAML, TOML, and JSON policy documents into typed canonical
models and evaluates RBAC, PBAC, and ABAC-style authorization rules for
`spakky-auth`.

## Installation

```bash
pip install spakky-policy
```

## Usage

```python
from spakky.auth import AuthContext, AuthSubject
from spakky.plugins.policy import PolicyDocumentEvaluator, PolicyEvaluationInput
from spakky.plugins.policy.loader import policy_document_from_mapping

document = policy_document_from_mapping(
    {
        "version": "2026-06",
        "metadata": {"name": "article-policy"},
        "roles": [{"ref": "role:editor", "permissions": ["permission:article-read"]}],
        "policies": [
            {
                "ref": "policy:article-read",
                "statements": [
                    {
                        "ref": "allow-editor-read",
                        "effect": "allow",
                        "roles": ["role:editor"],
                        "permissions": ["permission:article-read"],
                        "resources": ["article:1"],
                        "actions": ["article:read"],
                    }
                ],
            }
        ],
    }
)

auth_context = AuthContext(
    subject=AuthSubject(id="user:alice"),
    issuer="issuer:test",
    roles=("role:editor",),
)
result = PolicyDocumentEvaluator(document).evaluate(
    PolicyEvaluationInput(
        auth_context=auth_context,
        resource="article:1",
        action="article:read",
        policy="policy:article-read",
    )
)
assert result.allowed is True
```

## Policy Semantics

- Explicit deny statements take precedence over matching allow statements.
- No matching allow statement returns default deny evidence.
- Conditions support `all`, `any`, and `not` composition plus `equals`,
  `not_equals`, `in`, `contains`, and `exists` atomic operators.
- Resource, action, and tenant refs are canonical strings supplied by
  `AuthorizationRequest`, decorator metadata, `AuthContext`, or resolver output.
- Named policies are the OR/ANY user-facing surface; MCP/tool authorization,
  generic policy APIs, policy UI, and authorized data filtering are out of scope.

## License

MIT License
