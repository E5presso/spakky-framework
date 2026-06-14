"""FastAPI actuator 노출 문서 계약 테스트."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_fastapi_actuator_docs_expect_security_hardening_warning() -> None:
    """문서는 FastAPI actuator route에 명시적 보호가 필요하다고 경고해야 한다."""
    guide = (REPO_ROOT / "docs/guides/actuator.md").read_text(encoding="utf-8")
    readme = (REPO_ROOT / "plugins/spakky-fastapi/README.md").read_text(
        encoding="utf-8"
    )

    for doc in (guide, readme):
        assert "인증을 자동 적용하지 않습니다" in doc
        assert "내부망" in doc
        assert "리버스 프록시 허용 목록" in doc
        assert "접근 제어 계층" in doc
        assert "SPAKKY_ACTUATOR_INCLUDE_DETAILS=false" in doc
