# Spakky Framework - AI Coding Instructions

> 코딩 스타일 → [CONTRIBUTING.md](../CONTRIBUTING.md) | 아키텍처 → [ARCHITECTURE.md](../ARCHITECTURE.md) | ADR → [docs/adr/](../docs/adr/README.md) | 예제 → [README.md](../README.md)

## Overview

- **Framework**: Spring-inspired DI/IoC for Python 3.11+, AOP, plugin system (`uv` monorepo)
- **Core** (`core/`): `spakky`, `spakky-domain`, `spakky-data`, `spakky-event`, `spakky-task`, `spakky-outbox`
- **Plugins** (`plugins/`): `spakky-logging`, `spakky-fastapi`, `spakky-rabbitmq`, `spakky-kafka`, `spakky-security`, `spakky-typer`, `spakky-sqlalchemy`, `spakky-celery`

## Documentation Maintenance Rules

- **Preservation**: 이 섹션은 모든 버전에서 보존 필수
- **Code-first**: 모든 기술은 실제 코드 기반. 환각 금지
- **Cross-reference**: 문서화 전 정확한 코드 라인 확인 필수
- **Sync all docs**: 코드 변경 시 관련 마크다운 업데이트 (`CHANGELOG.md` 자동 생성 제외)
- **Sub-package READMEs**: `core/*/README.md`, `plugins/*/README.md` 항상 확인/업데이트
- **Priority**: Code > `CONTRIBUTING.md` > this file > `README.md`. 불일치 시 문서 수정
- **Verification**: 파일 경로, 클래스/함수명, 시그니처, import 경로, 환경변수 — 실제 코드로 검증
