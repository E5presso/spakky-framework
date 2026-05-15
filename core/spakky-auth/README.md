# Spakky Auth

[Spakky Framework](https://github.com/E5presso/spakky-framework)를 위한 provider-neutral authentication and authorization core package입니다.

## 설치

```bash
pip install spakky-auth
```

## 현재 범위

`spakky-auth`는 인증/인가 마일스톤의 core package import root와 feature entry point를 먼저 안정화합니다. Provider plugin과 boundary integration이 의존할 수 있는 `spakky.auth` import root, package metadata, workspace registration, documentation API path를 제공합니다.

이 등록 티켓은 `AuthContext`, decision model, ABC port, decorator metadata, AOP enforcement, startup validation을 구현하지 않습니다. 해당 semantic model은 후속 이슈 #280 이후에서 추가됩니다.

## Plugin Entry Point

패키지는 Spakky plugin discovery를 위해 다음 entry point를 등록합니다.

```toml
[project.entry-points."spakky.plugins"]
spakky-auth = "spakky.auth.main:initialize"
```

현재 `initialize()`는 등록용 no-op입니다. 후속 auth semantic model과 enforcement component가 추가되면 이 entry point를 통해 feature-local component를 등록합니다.

## 개발 검증

패키지 단위 검증은 패키지 디렉토리에서 실행합니다.

```bash
cd core/spakky-auth
uv run ruff format .
uv run ruff check .
uv run pyrefly check
uv run pytest
```

`pytest`는 `pyproject.toml`의 coverage 설정을 사용하며 `src/spakky/auth/**/*.py`에 대해 100% coverage를 요구합니다.

## 라이선스

MIT License
