---
name: dependency-audit
description: 모노레포의 외부 의존성에 대해 보안 취약점 스캔, 라이선스 감사, outdated 감지를 수행합니다.
argument-hint: "[패키지명]"
user-invocable: true
---

# Dependency Audit — 의존성 감사

모노레포의 외부 의존성을 보안, 라이선스, 최신성 관점에서 감사한다. 문제가 발견되면 `/update-dependencies`로 연결한다.

> **관련 스킬**: 의존성 업그레이드 실행은 → `/update-dependencies`

## 사용법

```
/dependency-audit
/dependency-audit spakky-sqlalchemy
```

- 인자 없음: 전체 모노레포 감사
- 패키지명: 해당 패키지만 감사

---

## Phase 1: 의존성 수집

### 1-1. 외부 의존성 목록 추출

```bash
uv run python -c "
import tomllib
from pathlib import Path
root = tomllib.loads(Path('pyproject.toml').read_text())
members = root.get('tool', {}).get('uv', {}).get('workspace', {}).get('members', [])
workspace_pkgs = set()
for m in members:
    for p in Path('.').glob(m):
        pkg = tomllib.loads((p / 'pyproject.toml').read_text())
        workspace_pkgs.add(pkg['project']['name'])
for m in members:
    for p in Path('.').glob(m):
        pkg = tomllib.loads((p / 'pyproject.toml').read_text())
        name = pkg['project']['name']
        deps = pkg['project'].get('dependencies', [])
        for d in deps:
            dep_name = d.split('>')[0].split('<')[0].split('=')[0].split('!')[0].split('[')[0].strip()
            if dep_name not in workspace_pkgs:
                print(f'{name}\t{d}')
"
```

인자로 패키지명이 주어진 경우 해당 패키지만 필터링한다.

### 1-2. 락파일에서 실제 설치 버전 확인

```bash
uv pip list --format json
```

## Phase 2: 보안 취약점 스캔

### 2-1. pip-audit 실행

```bash
uv run pip-audit --format json
```

`pip-audit`이 설치되어 있지 않으면:

```bash
uv tool run pip-audit --format json
```

### 2-2. 취약점 분류

| 심각도 | CVSS | 조치 |
|--------|------|------|
| **Critical** | 9.0+ | 즉시 업데이트 권장 |
| **High** | 7.0-8.9 | 빠른 업데이트 권장 |
| **Medium** | 4.0-6.9 | 다음 릴리즈에 포함 |
| **Low** | 0.1-3.9 | 인지만 |

각 취약점에 대해:
- CVE ID
- 영향받는 패키지와 버전
- 수정된 버전 (있으면)
- 이 모노레포에서 해당 패키지를 사용하는 패키지 목록

## Phase 3: 최신성 검사

### 3-1. outdated 패키지 확인

```bash
uv pip list --outdated --format json
```

### 3-2. 버전 격차 분류

| 분류 | 기준 | 우선순위 |
|------|------|---------|
| **Major behind** | 현재 major < 최신 major | 높음 (breaking changes 가능) |
| **Minor behind** | 같은 major, minor 차이 2+ | 중간 |
| **Patch behind** | 같은 major.minor, patch만 다름 | 낮음 |

## Phase 4: 라이선스 감사

### 4-1. 라이선스 수집

```bash
uv run python -c "
import importlib.metadata
for dist in importlib.metadata.distributions():
    meta = dist.metadata
    name = meta['Name']
    license = meta.get('License') or meta.get('Classifier', '')
    print(f'{name}\t{license}')
" | sort
```

### 4-2. 호환성 검사

Spakky Framework는 MIT 라이선스이므로, 아래 라이선스는 **비호환 경고** 대상:

| 라이선스 | 호환성 |
|---------|--------|
| MIT, BSD, Apache 2.0, ISC | 호환 |
| LGPL | 주의 (동적 링크만 허용) |
| GPL, AGPL | 비호환 |
| Unknown | 확인 필요 |

## Phase 5: 결과 보고

```
## 의존성 감사 결과

### 보안 취약점

| 심각도 | 패키지 | 현재 버전 | CVE | 수정 버전 | 사용처 |
|--------|--------|----------|-----|----------|--------|
| 🔴 Critical | {패키지} | {버전} | {CVE} | {수정 버전} | {패키지 목록} |
| 🟡 High | ... | ... | ... | ... | ... |

### outdated 패키지

| 패키지 | 현재 | 최신 | 격차 | 사용처 |
|--------|------|------|------|--------|
| {패키지} | {현재} | {최신} | Major | {패키지 목록} |

### 라이선스

| 패키지 | 라이선스 | 호환성 |
|--------|---------|--------|
| {패키지} | {라이선스} | 🔴 비호환 / 🟡 주의 |

### 요약

- 취약점: Critical {N}, High {M}, Medium {K}
- Outdated: Major {N}, Minor {M}, Patch {K}
- 라이선스 경고: {N}건
```

### 다음 액션

`AskUserQuestion`으로 다음 행동을 묻는다:

```yaml
question: "어떻게 진행할까요?"
header: "의존성 감사 완료"
options:
  - label: "전체 업데이트"
    description: "/update-dependencies를 실행하여 전체 의존성을 업데이트합니다"
  - label: "보안 패치만"
    description: "취약점이 있는 패키지만 선택적으로 업데이트합니다"
  - label: "이슈 생성"
    description: "감사 결과를 GitHub Issue로 생성합니다"
  - label: "종료"
    description: "감사 결과만 확인하고 종료합니다"
```

- "전체 업데이트" 선택 시 `/update-dependencies`를 실행한다.
- "보안 패치만" 선택 시 취약점 패키지만 수동으로 `uv add`하여 업데이트한다.

---

## 규칙

- **보안 취약점은 항상 보고한다** — 심각도와 무관하게 발견된 모든 취약점을 목록에 포함.
- 취약점이 Critical/High이면 보고 시 **강조 표시**한다.
- 의존성 업그레이드 실행은 이 스킬이 아닌 `/update-dependencies`에 위임한다.
- `uv run` 접두사 필수.

$ARGUMENTS
