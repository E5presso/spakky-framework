from dataclasses import dataclass

from spakky.core.pod.annotations.pod import Pod
from spakky.core.pod.annotations.tag import Tag


@dataclass(eq=False)
class CustomTag(Tag):
    """Custom tag for testing scan."""

    category: str = ""


@CustomTag(category="test")
@Pod()
class TaggedPod: ...


@CustomTag(category="tag-only")
class TagOnlyClass:
    """Tag만 있고 Pod은 없는 클래스 - 136->138 분기 커버용."""

    ...
