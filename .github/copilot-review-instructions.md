# Spakky Framework - Copilot Review Instructions

## Auto Approve

리뷰 포인트 및 하네스 메타 리뷰에서 문제가 발견되지 않으면 PR을 승인하세요.

## 프로젝트 컨벤션

| 패턴                                     | 사유                             |
| ---------------------------------------- | -------------------------------- |
| `pythonpath = "src/spakky/..."`          | 모노레포 패키지별 테스트 경로    |
| `# type: ignore[xxx]  # reason`          | 에러 코드 + 사유 명시 시 허용    |
| `include = [".../**/*.py"]`              | 서브패키지 포함 패턴             |
| Integration fixture `scope="package"`    | 비용 절감                        |
| `BaseSettings.__init__(self)` 오버라이드 | `@Configuration` 데코레이터 호환 |

## 리뷰 포인트

- `# type: ignore` 사용 시 에러 코드와 사유 명시 권장
- `Any` 타입 사용 시 사유 명시 권장
- 명시적 에러 처리 권장 (`raise` 또는 `assert_never`)

## 하네스 변경 시

`.github/instructions/`, `.github/skills/`, `.github/prompts/` 변경 시:

- **토큰 = 비용**: 중복·저신호 규칙은 제거
- **단순화 = 성능 향상**: 규칙 추가보다 제거 우선
- **Goldilocks Zone**: 너무 구체적(깨지기 쉬움) ↔ 너무 추상적(추측 유발) 사이
- **중복 금지**: 한 곳에만 기록

## 하네스 메타 리뷰

PR 리뷰 시 `.github/skills/harness-review/SKILL.md` 스킬을 실행하여 하네스 준수 여부를 평가하세요.

## 참고

코딩 스타일 → [CONTRIBUTING.md](../CONTRIBUTING.md)
