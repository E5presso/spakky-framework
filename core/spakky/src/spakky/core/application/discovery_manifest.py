"""Discovery manifest storage for reusable scan discovery results."""

import json
import sys
from enum import StrEnum
from pathlib import Path
from types import FunctionType, ModuleType
from typing import Self

from spakky.core.common.importing import Module, is_package, resolve_module
from spakky.core.common.mutability import immutable

DISCOVERY_MANIFEST_SCHEMA_VERSION = 1
DISCOVERY_MANIFEST_DETAIL_KEY = "discovery_manifest_decision"
DEFAULT_DISCOVERY_MANIFEST_PATH = Path(".spakky") / "cache" / "discovery-manifest.json"

JsonObject = dict[str, object]


class DiscoveryManifestDecision(StrEnum):
    """Decision made while loading a discovery manifest."""

    MISS = "miss"
    HIT = "hit"
    STALE_SCHEMA = "stale_schema"
    STALE_INPUT = "stale_input"


@immutable
class DiscoveryManifestSourceFingerprint:
    """Fingerprint for one Python source file involved in scan discovery."""

    path: str
    """Absolute source file path."""

    mtime_ns: int
    """Source file modification time in nanoseconds."""

    size: int
    """Source file size in bytes."""

    def to_json(self) -> JsonObject:
        """Serialize the source fingerprint.

        Returns:
            JSON-compatible object.
        """
        return {
            "path": self.path,
            "mtime_ns": self.mtime_ns,
            "size": self.size,
        }


@immutable
class DiscoveryManifestFingerprint:
    """Input fingerprint used to decide whether a manifest is fresh."""

    schema_version: int
    """Manifest schema version used by the current runtime."""

    python_version: str
    """Major/minor Python version."""

    module_name: str
    """Scan target module name."""

    is_package: bool
    """Whether the target is a package scan."""

    exclude: tuple[str, ...]
    """Normalized exclude module patterns."""

    sources: tuple[DiscoveryManifestSourceFingerprint, ...]
    """Source files that affect scan discovery."""

    @classmethod
    def from_scan_input(
        cls,
        path: Module,
        exclude: set[Module],
    ) -> Self:
        """Build a fingerprint from scan inputs.

        Args:
            path: Scan target module or module name.
            exclude: Exclude module patterns.

        Returns:
            Fingerprint for the current scan input.
        """
        module = resolve_module(path)
        source_files = _source_files_for(module)
        return cls(
            schema_version=DISCOVERY_MANIFEST_SCHEMA_VERSION,
            python_version=f"{sys.version_info.major}.{sys.version_info.minor}",
            module_name=module.__name__,
            is_package=is_package(module),
            exclude=tuple(sorted(_normalize_module_name(item) for item in exclude)),
            sources=tuple(_source_fingerprint(source) for source in source_files),
        )

    def to_json(self) -> JsonObject:
        """Serialize the fingerprint.

        Returns:
            JSON-compatible object.
        """
        return {
            "schema_version": self.schema_version,
            "python_version": self.python_version,
            "module_name": self.module_name,
            "is_package": self.is_package,
            "exclude": list(self.exclude),
            "sources": [source.to_json() for source in self.sources],
        }


@immutable
class DiscoveryManifestCandidate:
    """Pod or Tag candidate discovered during scan."""

    module_name: str
    """Module containing the candidate object."""

    qualname: str
    """Qualified object name inside the module."""

    @classmethod
    def from_object(cls, obj: type | FunctionType) -> Self:
        """Build a candidate identity from a discovered object.

        Args:
            obj: Discovered class or function.

        Returns:
            Candidate identity.
        """
        return cls(module_name=obj.__module__, qualname=obj.__qualname__)

    def matches(self, obj: object) -> bool:
        """Check whether an object matches this candidate identity.

        Args:
            obj: Candidate object loaded from a module.

        Returns:
            True when the object has the same module and qualified name.
        """
        if isinstance(obj, FunctionType):
            return (
                obj.__module__ == self.module_name and obj.__qualname__ == self.qualname
            )
        if isinstance(obj, type):
            return (
                obj.__module__ == self.module_name and obj.__qualname__ == self.qualname
            )
        return False

    def to_json(self) -> JsonObject:
        """Serialize the candidate.

        Returns:
            JSON-compatible object.
        """
        return {
            "module_name": self.module_name,
            "qualname": self.qualname,
        }


@immutable
class DiscoveryManifest:
    """Reusable scan discovery manifest."""

    fingerprint: DiscoveryManifestFingerprint
    """Input fingerprint that produced this manifest."""

    module_names: tuple[str, ...]
    """Modules scanned during fresh discovery."""

    candidates: tuple[DiscoveryManifestCandidate, ...]
    """Pod and Tag candidates discovered during fresh discovery."""

    def to_json(self) -> JsonObject:
        """Serialize the manifest.

        Returns:
            JSON-compatible object.
        """
        return {
            "schema_version": DISCOVERY_MANIFEST_SCHEMA_VERSION,
            "fingerprint": self.fingerprint.to_json(),
            "module_names": list(self.module_names),
            "candidates": [candidate.to_json() for candidate in self.candidates],
        }


@immutable
class DiscoveryManifestLoadResult:
    """Result of attempting to load a discovery manifest."""

    decision: DiscoveryManifestDecision
    """Manifest reuse decision."""

    manifest: DiscoveryManifest | None = None
    """Loaded manifest when the decision is hit."""


class DiscoveryManifestStore:
    """File-backed DiscoveryManifest store."""

    _path: Path

    def __init__(self, path: Path) -> None:
        """Initialize the store.

        Args:
            path: Manifest JSON file path.
        """
        self._path = path

    def load(
        self,
        fingerprint: DiscoveryManifestFingerprint,
    ) -> DiscoveryManifestLoadResult:
        """Load a manifest and compare it to the current fingerprint.

        Args:
            fingerprint: Current scan input fingerprint.

        Returns:
            Manifest load decision and loaded manifest on hit.
        """
        if not self._path.exists():
            return DiscoveryManifestLoadResult(
                decision=DiscoveryManifestDecision.MISS,
            )

        try:
            payload: object = json.loads(self._path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return DiscoveryManifestLoadResult(
                decision=DiscoveryManifestDecision.MISS,
            )

        manifest = _manifest_from_json(payload)
        if manifest is None:
            return DiscoveryManifestLoadResult(
                decision=DiscoveryManifestDecision.MISS,
            )
        if manifest.fingerprint.schema_version != DISCOVERY_MANIFEST_SCHEMA_VERSION:
            return DiscoveryManifestLoadResult(
                decision=DiscoveryManifestDecision.STALE_SCHEMA,
            )
        if manifest.fingerprint.to_json() != fingerprint.to_json():
            return DiscoveryManifestLoadResult(
                decision=DiscoveryManifestDecision.STALE_INPUT,
            )
        return DiscoveryManifestLoadResult(
            decision=DiscoveryManifestDecision.HIT,
            manifest=manifest,
        )

    def save(self, manifest: DiscoveryManifest) -> None:
        """Persist a manifest.

        Args:
            manifest: Manifest generated from fresh discovery.
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(manifest.to_json(), indent=2, sort_keys=True),
            encoding="utf-8",
        )


def default_discovery_manifest_path() -> Path:
    """Return the deterministic project-local manifest path.

    Returns:
        Default DiscoveryManifest path under the project cache directory.
    """
    return Path.cwd() / DEFAULT_DISCOVERY_MANIFEST_PATH


def _normalize_module_name(module: Module) -> str:
    if isinstance(module, ModuleType):
        return module.__name__
    return module


def _source_files_for(module: ModuleType) -> tuple[Path, ...]:
    spec = module.__spec__
    search_locations = spec.submodule_search_locations if spec is not None else None
    if search_locations is not None:
        source_paths = {
            source.resolve()
            for location in search_locations
            for source in Path(location).rglob("*.py")
        }
        return tuple(sorted(source_paths))

    module_file = module.__dict__.get("__file__")
    if not isinstance(module_file, str):
        return ()
    return (Path(module_file).resolve(),)


def _source_fingerprint(path: Path) -> DiscoveryManifestSourceFingerprint:
    stat = path.stat()
    return DiscoveryManifestSourceFingerprint(
        path=str(path),
        mtime_ns=stat.st_mtime_ns,
        size=stat.st_size,
    )


def _manifest_from_json(payload: object) -> DiscoveryManifest | None:
    if not isinstance(payload, dict):
        return None
    schema_version = payload.get("schema_version")
    if not isinstance(schema_version, int):
        return None
    if schema_version != DISCOVERY_MANIFEST_SCHEMA_VERSION:
        stale_fingerprint = DiscoveryManifestFingerprint(
            schema_version=schema_version,
            python_version="",
            module_name="",
            is_package=False,
            exclude=(),
            sources=(),
        )
        return DiscoveryManifest(
            fingerprint=stale_fingerprint,
            module_names=(),
            candidates=(),
        )

    fingerprint_payload = payload.get("fingerprint")
    module_names_payload = payload.get("module_names")
    candidates_payload = payload.get("candidates")
    fingerprint = _fingerprint_from_json(fingerprint_payload)
    module_names = _module_names_from_json(module_names_payload)
    candidates = _candidates_from_json(candidates_payload)
    if fingerprint is None or module_names is None or candidates is None:
        return None
    return DiscoveryManifest(
        fingerprint=fingerprint,
        module_names=module_names,
        candidates=candidates,
    )


def _fingerprint_from_json(payload: object) -> DiscoveryManifestFingerprint | None:
    if not isinstance(payload, dict):
        return None
    schema_version = payload.get("schema_version")
    python_version = payload.get("python_version")
    module_name = payload.get("module_name")
    target_is_package = payload.get("is_package")
    exclude_payload = payload.get("exclude")
    sources_payload = payload.get("sources")
    exclude = _strings_from_json(exclude_payload)
    sources = _sources_from_json(sources_payload)
    if not isinstance(schema_version, int):
        return None
    if not isinstance(python_version, str):
        return None
    if not isinstance(module_name, str):
        return None
    if not isinstance(target_is_package, bool):
        return None
    if exclude is None or sources is None:
        return None
    return DiscoveryManifestFingerprint(
        schema_version=schema_version,
        python_version=python_version,
        module_name=module_name,
        is_package=target_is_package,
        exclude=exclude,
        sources=sources,
    )


def _sources_from_json(
    payload: object,
) -> tuple[DiscoveryManifestSourceFingerprint, ...] | None:
    if not isinstance(payload, list):
        return None
    sources: list[DiscoveryManifestSourceFingerprint] = []
    for item in payload:
        if not isinstance(item, dict):
            return None
        path = item.get("path")
        mtime_ns = item.get("mtime_ns")
        size = item.get("size")
        if not isinstance(path, str):
            return None
        if not isinstance(mtime_ns, int):
            return None
        if not isinstance(size, int):
            return None
        sources.append(
            DiscoveryManifestSourceFingerprint(
                path=path,
                mtime_ns=mtime_ns,
                size=size,
            )
        )
    return tuple(sources)


def _strings_from_json(payload: object) -> tuple[str, ...] | None:
    if not isinstance(payload, list):
        return None
    values: list[str] = []
    for item in payload:
        if not isinstance(item, str):
            return None
        values.append(item)
    return tuple(values)


def _module_names_from_json(payload: object) -> tuple[str, ...] | None:
    return _strings_from_json(payload)


def _candidates_from_json(
    payload: object,
) -> tuple[DiscoveryManifestCandidate, ...] | None:
    if not isinstance(payload, list):
        return None
    candidates: list[DiscoveryManifestCandidate] = []
    for item in payload:
        if not isinstance(item, dict):
            return None
        module_name = item.get("module_name")
        qualname = item.get("qualname")
        if not isinstance(module_name, str):
            return None
        if not isinstance(qualname, str):
            return None
        candidates.append(
            DiscoveryManifestCandidate(module_name=module_name, qualname=qualname)
        )
    return tuple(candidates)
