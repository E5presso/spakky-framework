---
name: onboarding
description: 새 개발자의 Spakky Framework 개발 환경을 설정합니다. RTK 설치, 의존성 동기화, 도구 검증을 수행합니다.
user-invocable: true
---

# 온보딩 워크플로우

새 개발자의 로컬 환경을 설정합니다. 아래 단계를 **순서대로** 수행하세요.

## Step 1: 필수 도구 확인

아래 도구들이 설치되어 있는지 확인합니다:

```bash
# Python 3.11+
python3 --version

# uv (패키지 매니저)
uv --version

# git
git --version

# gh (GitHub CLI)
gh --version
```

누락된 도구가 있으면 사용자에게 알리고 설치 방법을 안내하세요.

## Step 2: RTK 설치 및 설정

[RTK](https://github.com/rtk-ai/rtk)는 CLI 출력을 압축하여 토큰 소비를 60-90% 줄여주는 프록시입니다.

```bash
# RTK 설치 확인 — 미설치 시 자동 설치
rtk --version || brew install rtk

# RTK 글로벌 초기화 (Claude Code 훅 자동 설정)
rtk init -g

# 설치 확인
rtk init --show
```

이 명령은 `~/.claude/settings.json`에 PreToolUse 훅을 자동 등록하여, Bash 명령어를 RTK가 투명하게 프록시합니다.

> **참고**: RTK 훅은 `~/.claude/settings.json` (글로벌)에 설정됩니다.
> 프로젝트 `.claude/settings.json`에는 포함하지 않습니다 — 개인 환경 설정이므로.

## Step 3: 의존성 동기화

```bash
uv sync --all-packages --all-extras
```

## Step 4: Pre-commit 훅 설치

```bash
uv run pre-commit install
```

## Step 5: 린터/타입 체커 검증

각 패키지에서 도구가 정상 동작하는지 확인합니다:

```bash
# 코어 패키지 예시
cd core/spakky && uv run ruff check . && uv run pyrefly check
```

## Step 6: 테스트 실행

```bash
# 전체 유닛 테스트 (빠른 검증)
uv run python scripts/run_coverage.py
```

## Step 7: 완료 보고

설정 결과를 요약합니다:

```
## 온보딩 완료

| 항목 | 상태 |
|------|------|
| Python | ✅ 3.x.x |
| uv | ✅ x.x.x |
| RTK | ✅ / ❌ (선택) |
| 의존성 | ✅ 동기화 완료 |
| Pre-commit | ✅ 설치 완료 |
| 린터 | ✅ 통과 |
| 테스트 | ✅ 통과 |
```
