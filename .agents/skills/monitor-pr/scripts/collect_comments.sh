#!/usr/bin/env bash
# 미처리 코멘트 수집. 3채널 REST API.
# 사용법: REPO=E5presso/spakky-framework PR_NUMBER=123 bash collect_comments.sh
#
# 채널:
#   CH1: 인라인 리뷰 코멘트 (`pulls/{N}/comments`)
#   CH2: 일반 PR 코멘트    (`issues/{N}/comments`)
#   CH3: 리뷰 본문         (`pulls/{N}/reviews`)
#
# ── 처리 판정: ID 태그 마커 ──
# 에이전트는 응답 본문 끝에 `<!-- claude-agent-reply to=<id> -->` 마커를 부착한다.
# `<id>`는 응답이 겨냥하는 대상 코멘트/리뷰의 숫자 GitHub ID. 이 마커 집합으로부터
# "처리된 ID 집합"을 구성하고, 각 채널에서 해당 ID에 속하지 않은 항목만 반환한다.
# - login 기반 식별 포기: 에이전트/사용자 동일 GitHub 계정(개인 PAT) 혼용 가능.
# - timestamp / thread 기반 휴리스틱 포기: 교차 thread에 낀 non-agent 코멘트 누락
#   사례(claude[bot] 리뷰) 재현 실패.
#
# SINCE_TS 설정 시 해당 시점 이후만 수집(이벤트 핸들러용 narrowing).
# LAST_SEEN_CH1, LAST_SEEN_CH2, LAST_SEEN_CH3 설정 시 해당 ID 이후만 수집(재시작용).
# STALE_HANDLED_IDS 설정 시 (콤마 구분) 해당 id의 기존 reply 마커를 무시하고 미처리로 재분류.
#   in-place 갱신 감지(watch.sh)에서 updatedAt이 증가한 id를 전달받아 본문이 바뀐 코멘트/리뷰를
#   재수집·재triage 대상으로 되돌린다.
set -euo pipefail

# Claude Code Bash tool spawns non-login shells that miss /opt/homebrew/bin.
case ":$PATH:" in
  *:/opt/homebrew/bin:*) ;;
  *) export PATH="$PATH:/opt/homebrew/bin" ;;
esac

if ! command -v gh >/dev/null 2>&1; then
  echo "FATAL: gh CLI not found in PATH ($PATH)" >&2
  exit 1
fi

REPO="${REPO:-E5presso/spakky-framework}"
: "${PR_NUMBER:?PR_NUMBER env required}"

# REVIEW_NOISE_FILTER: APPROVED는 ceremonial. 본문 비어있는 COMMENTED/REQUESTED_CHANGES는
# 개별 인라인 코멘트의 container 역할만 하므로 CH1에서 이미 집계됨 — CH3에서 중복 제외.
REVIEW_NOISE_FILTER='select(.state != "APPROVED") | select((.body // "") | length > 0)'
COMMENT_NOISE_FILTER='select(.user.login != "linear[bot]") | select(((.user.login == "codecov[bot]") and ((.body // "") | test("^## \\[Codecov\\]"; "i"))) | not)'

# ── RAW fetch ──
# silent-failure 금지: gh 오류는 `set -e`로 스크립트를 중단시켜 표면화한다.
CH1_RAW=$(gh api "repos/$REPO/pulls/$PR_NUMBER/comments" --paginate)
CH2_RAW=$(gh api "repos/$REPO/issues/$PR_NUMBER/comments" --paginate)
CH3_RAW=$(gh api "repos/$REPO/pulls/$PR_NUMBER/reviews" --paginate)

# ── 처리된 ID 집합 ──
# 모든 채널의 본문에서 `<!-- claude-agent-reply to=<id> -->` 패턴을 스캔하여 id를 수집한다.
# 이 id 집합에 속한 CH1/CH2/CH3 항목은 이미 응답된 것으로 간주한다.
# jq `scan`은 정규식 캡처 그룹 전체를 반환하므로 숫자 부분만 재추출.
HANDLED_IDS=$(jq -r -s '
  (.[0] + .[1] + .[2])
  | map(.body // "")
  | join("\n")
  | [scan("<!-- claude-agent-reply to=([0-9]+) -->")]
  | flatten
  | unique
  | .[]
' <(echo "$CH1_RAW") <(echo "$CH2_RAW") <(echo "$CH3_RAW") 2>/dev/null | tr '\n' ' ' || echo "")

# jq array literal로 변환: "123 456" → [123,456]
HANDLED_JSON=$(printf '%s' "$HANDLED_IDS" | tr -s ' ' '\n' | jq -R 'select(length>0) | tonumber' | jq -s . 2>/dev/null || echo "[]")

# STALE_HANDLED_IDS: in-place 갱신 감지된 id는 HANDLED_JSON에서 제거하여 미처리로 되돌린다.
if [ -n "${STALE_HANDLED_IDS:-}" ]; then
  STALE_JSON=$(printf '%s' "$STALE_HANDLED_IDS" | tr ',' '\n' | jq -R 'select(length>0) | tonumber' | jq -s . 2>/dev/null || echo "[]")
  HANDLED_JSON=$(jq -n --argjson handled "$HANDLED_JSON" --argjson stale "$STALE_JSON" '$handled - $stale')
fi

# ── CH1: 인라인 리뷰 코멘트 ──
# 에이전트 자기 응답 제외: 본문에 마커가 포함된 경우(답변 본체).
# 처리된 대상 제외: .id가 HANDLED_JSON에 포함된 경우(답변 받은 코멘트).
if [ -n "${SINCE_TS:-}" ]; then
  CH1=$(echo "$CH1_RAW" | jq --argjson handled "$HANDLED_JSON" --arg since "$SINCE_TS" '
    [ .[]
      | '"$COMMENT_NOISE_FILTER"'
      | select((.body // "") | contains("<!-- claude-agent-reply") | not)
      | select(.id as $id | ($handled | index($id)) == null)
      | select(.created_at > $since)
      | {id: .id, author: .user.login, body: .body, path: .path, line: .original_line, created: .created_at}
    ]
  ' 2>/dev/null || echo "[]")
elif [ -n "${LAST_SEEN_CH1:-}" ]; then
  CH1=$(echo "$CH1_RAW" | jq --argjson handled "$HANDLED_JSON" --argjson last "$LAST_SEEN_CH1" '
    [ .[]
      | '"$COMMENT_NOISE_FILTER"'
      | select((.body // "") | contains("<!-- claude-agent-reply") | not)
      | select(.id as $id | ($handled | index($id)) == null)
      | select(.id > $last)
      | {id: .id, author: .user.login, body: .body, path: .path, line: .original_line, created: .created_at}
    ]
  ' 2>/dev/null || echo "[]")
else
  CH1=$(echo "$CH1_RAW" | jq --argjson handled "$HANDLED_JSON" '
    [ .[]
      | '"$COMMENT_NOISE_FILTER"'
      | select((.body // "") | contains("<!-- claude-agent-reply") | not)
      | select(.id as $id | ($handled | index($id)) == null)
      | {id: .id, author: .user.login, body: .body, path: .path, line: .original_line, created: .created_at}
    ]
  ' 2>/dev/null || echo "[]")
fi

# ── CH2: 일반 PR 코멘트 ──
if [ -n "${SINCE_TS:-}" ]; then
  CH2=$(echo "$CH2_RAW" | jq --argjson handled "$HANDLED_JSON" --arg since "$SINCE_TS" '
    [ .[]
      | '"$COMMENT_NOISE_FILTER"'
      | select((.body // "") | contains("<!-- claude-agent-reply") | not)
      | select(.id as $id | ($handled | index($id)) == null)
      | select(.created_at > $since)
      | {id: .id, author: .user.login, body: .body, created: .created_at}
    ]
  ' 2>/dev/null || echo "[]")
elif [ -n "${LAST_SEEN_CH2:-}" ]; then
  CH2=$(echo "$CH2_RAW" | jq --argjson handled "$HANDLED_JSON" --argjson last "$LAST_SEEN_CH2" '
    [ .[]
      | '"$COMMENT_NOISE_FILTER"'
      | select((.body // "") | contains("<!-- claude-agent-reply") | not)
      | select(.id as $id | ($handled | index($id)) == null)
      | select(.id > $last)
      | {id: .id, author: .user.login, body: .body, created: .created_at}
    ]
  ' 2>/dev/null || echo "[]")
else
  CH2=$(echo "$CH2_RAW" | jq --argjson handled "$HANDLED_JSON" '
    [ .[]
      | '"$COMMENT_NOISE_FILTER"'
      | select((.body // "") | contains("<!-- claude-agent-reply") | not)
      | select(.id as $id | ($handled | index($id)) == null)
      | {id: .id, author: .user.login, body: .body, created: .created_at}
    ]
  ' 2>/dev/null || echo "[]")
fi

# ── CH3: 리뷰 본문 ──
# REVIEW_NOISE_FILTER: state=APPROVED는 ceremonial이므로 제외.
# 리뷰 본문도 .id가 HANDLED_JSON에 포함되면 응답된 것으로 간주.
if [ -n "${SINCE_TS:-}" ]; then
  CH3=$(echo "$CH3_RAW" | jq --argjson handled "$HANDLED_JSON" --arg since "$SINCE_TS" "
    [ .[] | ${COMMENT_NOISE_FILTER} | ${REVIEW_NOISE_FILTER}
      | select(.id as \$id | (\$handled | index(\$id)) == null)
      | select(.submitted_at > \$since)
      | {id: .id, author: .user.login, body: .body, state: .state, created: .submitted_at}
    ]
  " 2>/dev/null || echo "[]")
elif [ -n "${LAST_SEEN_CH3:-}" ]; then
  CH3=$(echo "$CH3_RAW" | jq --argjson handled "$HANDLED_JSON" --argjson last "$LAST_SEEN_CH3" "
    [ .[] | ${COMMENT_NOISE_FILTER} | ${REVIEW_NOISE_FILTER}
      | select(.id as \$id | (\$handled | index(\$id)) == null)
      | select(.id > \$last)
      | {id: .id, author: .user.login, body: .body, state: .state, created: .submitted_at}
    ]
  " 2>/dev/null || echo "[]")
else
  CH3=$(echo "$CH3_RAW" | jq --argjson handled "$HANDLED_JSON" "
    [ .[] | ${COMMENT_NOISE_FILTER} | ${REVIEW_NOISE_FILTER}
      | select(.id as \$id | (\$handled | index(\$id)) == null)
      | {id: .id, author: .user.login, body: .body, state: .state, created: .submitted_at}
    ]
  " 2>/dev/null || echo "[]")
fi

# ── 결과 출력 ──
CH1_LEN=$(echo "$CH1" | jq 'length' 2>/dev/null || echo 0)
CH2_LEN=$(echo "$CH2" | jq 'length' 2>/dev/null || echo 0)
CH3_LEN=$(echo "$CH3" | jq 'length' 2>/dev/null || echo 0)
TOTAL=$((CH1_LEN + CH2_LEN + CH3_LEN))

echo "CH1_COUNT=$CH1_LEN"
echo "CH2_COUNT=$CH2_LEN"
echo "CH3_COUNT=$CH3_LEN"
echo "TOTAL=$TOTAL"
if [ "$CH1_LEN" -gt 0 ]; then echo "CH1_DATA=$CH1"; fi
if [ "$CH2_LEN" -gt 0 ]; then echo "CH2_DATA=$CH2"; fi
if [ "$CH3_LEN" -gt 0 ]; then echo "CH3_DATA=$CH3"; fi
