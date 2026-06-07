# spakky-openfga

`spakky-openfga` provides a check-only OpenFGA authorization provider for
Spakky Auth relationship enforcement.

## Auth Provider Capabilities

The plugin registers `OpenFgaAuthProvider`, which implements:

- `AuthCapability.RELATION_CHECK`
- `AuthCapability.POLICY_EVALUATION`

`RelationCheckRequest.relation` and `AuthorizationRequest.action` are mapped to
the OpenFGA relation. `AuthContext.subject.id` is mapped to the OpenFGA user,
and resource/tenant canonical refs are mapped into the OpenFGA object string.

## Configuration

`OpenFgaConfig` is registered as a settings Pod and reads `SPAKKY_OPENFGA_*`
environment variables. It contains the OpenFGA API URL, store id, optional
authorization model id, principal type, and tenant/object mapping controls. By
default a subject id without a type prefix is mapped as `user:<subject>`, and
tenant refs are prefixed into object refs as `<tenant>/<resource>`.

Common settings:

- `SPAKKY_OPENFGA_API_URL`
- `SPAKKY_OPENFGA_STORE_ID`
- `SPAKKY_OPENFGA_AUTHORIZATION_MODEL_ID`
- `SPAKKY_OPENFGA_PRINCIPAL_TYPE`
- `SPAKKY_OPENFGA_INCLUDE_TENANT_IN_OBJECT`

## Non-goals

This package intentionally does not implement tuple writes, authorization model
migration, admin CLI/API, list resources, data/query filtering, or tuple/model
management surfaces.

Provider-unavailable conditions map to an `ERROR` authorization decision with
`AuthorizationReasonCode.VERIFICATION_PROVIDER_UNAVAILABLE`.
