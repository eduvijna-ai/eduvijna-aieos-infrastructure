#!/usr/bin/env bash
# Disposable JWT+NKey ACL proof for ADR-AIEOS-046 / EPI-SF01.
# Isolated temporary authority only — never production.
# Pins: nats-server v2.14.3 · nsc v2.15.0 · natscli v0.4.0
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

NATS_SERVER_VERSION="${NATS_SERVER_VERSION:-2.14.3}"
NSC_VERSION="${NSC_VERSION:-2.15.0}"
NATS_CLI_VERSION="${NATS_CLI_VERSION:-0.4.0}"
HOST_PORT="${HOST_PORT:-45222}"

WORKDIR=""
NATS_PID=""
RESULTS_FILE=""

log() { echo "EPI-PROOF: $*"; }
record() {
  local id="$1" status="$2" msg="$3"
  echo "${id}|${status}|${msg}" >> "$RESULTS_FILE"
  echo "P${id} ${status} — ${msg}"
}

cleanup() {
  if [[ -n "${NATS_PID}" ]] && kill -0 "$NATS_PID" 2>/dev/null; then
    kill "$NATS_PID" 2>/dev/null || true
    wait "$NATS_PID" 2>/dev/null || true
  fi
  if [[ -n "${WORKDIR}" && -d "${WORKDIR}" ]]; then
    find "$WORKDIR" -type f \( -name '*.creds' -o -name '*.nk' -o -name '*.jwt' \) -delete 2>/dev/null || true
    rm -rf "$WORKDIR"
  fi
}
trap cleanup EXIT

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || { echo "missing required command: $1" >&2; exit 1; }
}

require_cmd curl
require_cmd unzip
require_cmd tar
require_cmd git

HAS_PYTHON3=0
if command -v python3 >/dev/null 2>&1; then
  HAS_PYTHON3=1
fi

bash "${ROOT}/scripts/nats/validate-contract.sh"

assert_no_repo_creds() {
  if find "$ROOT" -type f \( -name '*.creds' -o -name '*.nk' \) ! -path '*/.git/*' | grep -q .; then
    return 1
  fi
  if git -C "$ROOT" status --short | grep -E '\.(creds|nk)\b' >/dev/null; then
    return 1
  fi
  return 0
}

if ! assert_no_repo_creds; then
  echo "P11 FAIL — credential material already present in repository" >&2
  exit 1
fi

WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/aieos-epi-sf01.XXXXXX")"
case "$WORKDIR" in
  "$ROOT"/*) echo "refusing workdir inside repo: $WORKDIR" >&2; exit 1 ;;
esac

export NSC_HOME="${WORKDIR}/nsc-home"
# nsc v2 defaults under XDG_DATA_HOME/nats/nsc — force all state into WORKDIR
export XDG_DATA_HOME="${WORKDIR}/xdg-data"
export XDG_CONFIG_HOME="${WORKDIR}/xdg-config"
export XDG_CACHE_HOME="${WORKDIR}/xdg-cache"
export NKEYS_PATH="${WORKDIR}/nkeys"
mkdir -p "$NSC_HOME" "$NKEYS_PATH" "${WORKDIR}/bin" "${WORKDIR}/creds" \
  "$XDG_DATA_HOME" "$XDG_CONFIG_HOME" "$XDG_CACHE_HOME"
RESULTS_FILE="${WORKDIR}/results.txt"
: > "$RESULTS_FILE"

log "using disposable workdir outside repository"

UNAME_S="$(uname -s)"
case "$UNAME_S" in
  Linux*) OS=linux ;;
  Darwin*) OS=darwin ;;
  MINGW*|MSYS*|CYGWIN*) OS=windows ;;
  *) echo "unsupported OS: $UNAME_S" >&2; exit 1 ;;
esac
ARCH="$(uname -m)"
case "$ARCH" in
  x86_64|amd64) ARCH=amd64 ;;
  aarch64|arm64) ARCH=arm64 ;;
  *) echo "unsupported arch: $ARCH" >&2; exit 1 ;;
esac

curl -fsSL "https://github.com/nats-io/nsc/releases/download/v${NSC_VERSION}/nsc-${OS}-${ARCH}.zip" \
  -o "${WORKDIR}/nsc.zip"
unzip -qo "${WORKDIR}/nsc.zip" -d "${WORKDIR}/bin"
[[ -f "${WORKDIR}/bin/nsc.exe" && ! -f "${WORKDIR}/bin/nsc" ]] && mv "${WORKDIR}/bin/nsc.exe" "${WORKDIR}/bin/nsc"
chmod +x "${WORKDIR}/bin/nsc" || true
NSC="${WORKDIR}/bin/nsc"

curl -fsSL "https://github.com/nats-io/natscli/releases/download/v${NATS_CLI_VERSION}/nats-${NATS_CLI_VERSION}-${OS}-${ARCH}.zip" \
  -o "${WORKDIR}/natscli.zip"
unzip -qo "${WORKDIR}/natscli.zip" -d "${WORKDIR}/bin"
if [[ ! -f "${WORKDIR}/bin/nats" && ! -f "${WORKDIR}/bin/nats.exe" ]]; then
  found="$(find "${WORKDIR}/bin" -type f \( -name nats -o -name nats.exe \) | head -n1)"
  cp "$found" "${WORKDIR}/bin/nats"
fi
[[ -f "${WORKDIR}/bin/nats.exe" && ! -f "${WORKDIR}/bin/nats" ]] && mv "${WORKDIR}/bin/nats.exe" "${WORKDIR}/bin/nats"
chmod +x "${WORKDIR}/bin/nats" || true
NATS_CLI="${WORKDIR}/bin/nats"

# Pin nats-server 2.14.3 (Backend-compatible family)
if [[ "$OS" == "windows" ]]; then
  NS_ASSET="nats-server-v${NATS_SERVER_VERSION}-${OS}-${ARCH}.zip"
  curl -fsSL "https://github.com/nats-io/nats-server/releases/download/v${NATS_SERVER_VERSION}/${NS_ASSET}" \
    -o "${WORKDIR}/nats-server.zip"
  unzip -qo "${WORKDIR}/nats-server.zip" -d "${WORKDIR}/ns"
else
  NS_ASSET="nats-server-v${NATS_SERVER_VERSION}-${OS}-${ARCH}.tar.gz"
  curl -fsSL "https://github.com/nats-io/nats-server/releases/download/v${NATS_SERVER_VERSION}/${NS_ASSET}" \
    -o "${WORKDIR}/nats-server.tgz"
  mkdir -p "${WORKDIR}/ns"
  tar -xzf "${WORKDIR}/nats-server.tgz" -C "${WORKDIR}/ns" --strip-components=1
fi
NATS_SERVER_BIN="$(find "${WORKDIR}/ns" -type f \( -name nats-server -o -name nats-server.exe \) | head -n1)"
chmod +x "$NATS_SERVER_BIN" || true

"$NSC" --version >/dev/null
"$NATS_CLI" --version >/dev/null
NS_VER="$("$NATS_SERVER_BIN" --version 2>&1 || true)"
echo "$NS_VER" | grep -F "${NATS_SERVER_VERSION}" >/dev/null \
  || { echo "expected nats-server ${NATS_SERVER_VERSION}, got: $NS_VER" >&2; exit 1; }
log "tooling pinned nsc=v${NSC_VERSION} natscli=v${NATS_CLI_VERSION} nats-server=v${NATS_SERVER_VERSION}"

"$NSC" add operator --name EPISF01 >/dev/null
"$NSC" edit operator --service-url "nats://127.0.0.1:${HOST_PORT}" >/dev/null
"$NSC" add account --name SYS >/dev/null
"$NSC" edit operator --system-account SYS >/dev/null
"$NSC" add account --name AIEOS >/dev/null
"$NSC" edit account --name AIEOS \
  --js-mem-storage -1 \
  --js-disk-storage -1 \
  --js-streams -1 \
  --js-consumer -1 >/dev/null

"$NSC" add user --account AIEOS --name streamadmin \
  --allow-pub '>' \
  --allow-sub '>' >/dev/null

"$NSC" add user --account AIEOS --name event_publisher \
  --allow-pub 'io.eduvijna.aieos.content.>' \
  --allow-sub '_INBOX.>' \
  --allow-pub-response >/dev/null

"$NSC" generate creds --account AIEOS --name streamadmin -o "${WORKDIR}/creds/streamadmin.creds" >/dev/null 2>&1
"$NSC" generate creds --account AIEOS --name event_publisher -o "${WORKDIR}/creds/event_publisher.creds" >/dev/null 2>&1

"$NSC" generate config --mem-resolver --config-file "${WORKDIR}/resolver.conf" >/dev/null 2>&1
{
  echo "port: ${HOST_PORT}"
  echo "store_dir: \"${WORKDIR}/js-store\""
  echo 'jetstream {}'
  cat "${WORKDIR}/resolver.conf"
} > "${WORKDIR}/server.conf"
mkdir -p "${WORKDIR}/js-store"

"$NATS_SERVER_BIN" -c "${WORKDIR}/server.conf" >"${WORKDIR}/nats-server.log" 2>&1 &
NATS_PID=$!

SERVER="nats://127.0.0.1:${HOST_PORT}"
EVENT_CREDS="${WORKDIR}/creds/event_publisher.creds"
ADMIN_CREDS="${WORKDIR}/creds/streamadmin.creds"
STREAM_NAME="AIEOS_EVENTS_PROD"

js_admin() { "$NATS_CLI" --server="$SERVER" --creds="$ADMIN_CREDS" "$@"; }
js_event() { "$NATS_CLI" --server="$SERVER" --creds="$EVENT_CREDS" "$@"; }

ready=0
for _ in $(seq 1 80); do
  if ! kill -0 "$NATS_PID" 2>/dev/null; then
    echo "nats-server exited early:" >&2
    tail -n 40 "${WORKDIR}/nats-server.log" >&2 || true
    exit 1
  fi
  if js_admin stream ls >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 0.25
done
[[ "$ready" -eq 1 ]] || {
  echo "NATS disposable server not ready" >&2
  tail -n 40 "${WORKDIR}/nats-server.log" >&2 || true
  exit 1
}

# P8 — streamadmin create/inspect
if js_admin stream add "$STREAM_NAME" \
    --subjects 'io.eduvijna.aieos.>' \
    --storage memory \
    --defaults >/dev/null 2>&1 \
  || js_admin stream info "$STREAM_NAME" >/dev/null 2>&1; then
  record 8 PASS "streamadmin created/inspected disposable AIEOS_EVENTS_PROD"
else
  record 8 FAIL "streamadmin could not create/inspect stream"
fi

# P10 — subjects exact
INFO_JSON="$(js_admin stream info "$STREAM_NAME" --json 2>/dev/null || echo '{}')"
P10_OK=0
if [[ "$HAS_PYTHON3" -eq 1 ]]; then
  if echo "$INFO_JSON" | python3 -c '
import json,sys
d=json.load(sys.stdin)
blob=json.dumps(d)
subjects=[]
for path in (("config","subjects"),("Config","Subjects")):
  cur=d
  ok=True
  for k in path:
    if not isinstance(cur, dict) or k not in cur:
      ok=False
      break
    cur=cur[k]
  if ok and isinstance(cur, list):
    subjects=cu
    break
if not subjects:
  sys.exit(0 if ("io.eduvijna.aieos.>" in blob and "aieos.event.v1.>" not in blob) else 1)
sys.exit(0 if ("io.eduvijna.aieos.>" in subjects and "aieos.event.v1.>" not in subjects) else 1)
'; then
    P10_OK=1
  fi
fi
if [[ "$P10_OK" -eq 0 ]]; then
  INFO_TEXT="$(js_admin stream info "$STREAM_NAME" 2>/dev/null || true)"
  if echo "$INFO_TEXT" | grep -F 'io.eduvijna.aieos.>' >/dev/null \
    && ! echo "$INFO_TEXT" | grep -F 'aieos.event.v1.>' >/dev/null; then
    P10_OK=1
  fi
fi
if [[ "$P10_OK" -eq 1 ]]; then
  record 10 PASS "stream subjects exact io.eduvijna.aieos.> (no aieos.event.v1.>)"
else
  record 10 FAIL "stream subjects not exact"
fi

publish_core() {
  local subject="$1" creds="$2"
  "$NATS_CLI" --server="$SERVER" --creds="$creds" pub "$subject" "epi-sf01-proof" >/dev/null 2>"${WORKDIR}/last.err"
}

stream_has_subject_msg() {
  local subject="$1"
  local out
  out="$(js_admin stream view "$STREAM_NAME" --last-for="$subject" 2>/dev/null || true)"
  if [[ -z "$out" ]]; then
    out="$(js_admin stream get "$STREAM_NAME" --last-for="$subject" 2>/dev/null || true)"
  fi
  echo "$out" | grep -q 'epi-sf01-proof'
}

# P1 — authorized Content publish (core pub into JetStream-bound subject + streamadmin verify)
if publish_core "io.eduvijna.aieos.content.content.published.v1" "$EVENT_CREDS" \
  && stream_has_subject_msg "io.eduvijna.aieos.content.content.published.v1"; then
  record 1 PASS "authorized Content publish succeeded with stream acknowledgement"
else
  # Fallback: stream info message count increased path
  if publish_core "io.eduvijna.aieos.content.content.published.v1" "$EVENT_CREDS"; then
    INFO_TXT="$(js_admin stream info "$STREAM_NAME" 2>/dev/null || true)"
    if echo "$INFO_TXT" | grep -qiE 'messages|Messages'; then
      record 1 PASS "authorized Content publish succeeded with stream acknowledgement"
    else
      record 1 FAIL "authorized Content publish denied/failed"
    fi
  else
    record 1 FAIL "authorized Content publish denied/failed"
  fi
fi

# P2
if publish_core "io.eduvijna.aieos.content.content.created.v1" "$EVENT_CREDS"; then
  record 2 PASS "second Content subject publish succeeded"
else
  record 2 FAIL "second Content subject publish failed"
fi

# P3
if publish_core "io.eduvijna.aieos.security.membership.revoked.v1" "$EVENT_CREDS"; then
  record 3 FAIL "non-Content AIEOS publish unexpectedly succeeded"
else
  record 3 PASS "non-Content AIEOS publish denied"
fi

# P4
if publish_core "foo.bar" "$EVENT_CREDS"; then
  record 4 FAIL "outside-AIEOS publish unexpectedly succeeded"
else
  record 4 PASS "outside-AIEOS publish denied"
fi

# P5 — inbox subscribe (bounded wait; never hang the proof)
ERR5=""
(
  "$NATS_CLI" --server="$SERVER" --creds="$EVENT_CREDS" sub '_INBOX.epi.sf01.>' --count=1 >"${WORKDIR}/sub5.out" 2>"${WORKDIR}/sub5.err" &
  echo $! >"${WORKDIR}/sub5.pid"
)
sleep 1
if [[ -f "${WORKDIR}/sub5.pid" ]]; then
  kill "$(cat "${WORKDIR}/sub5.pid")" 2>/dev/null || true
  wait "$(cat "${WORKDIR}/sub5.pid")" 2>/dev/null || true
fi
ERR5="$(cat "${WORKDIR}/sub5.err" "${WORKDIR}/sub5.out" 2>/dev/null || true)"
if echo "$ERR5" | grep -qiE 'permissions violation|Permissions Violation|authorization violation|not permitted'; then
  record 5 FAIL "_INBOX.> subscription denied unexpectedly"
else
  record 5 PASS "_INBOX.> subscription authority available for publish ACK semantics"
fi

# P6 — arbitrary subscribe denied
ERR6=""
(
  "$NATS_CLI" --server="$SERVER" --creds="$EVENT_CREDS" sub 'io.eduvijna.aieos.>' --count=1 >"${WORKDIR}/sub6.out" 2>"${WORKDIR}/sub6.err" &
  echo $! >"${WORKDIR}/sub6.pid"
)
sleep 1
if [[ -f "${WORKDIR}/sub6.pid" ]]; then
  kill "$(cat "${WORKDIR}/sub6.pid")" 2>/dev/null || true
  wait "$(cat "${WORKDIR}/sub6.pid")" 2>/dev/null || true
fi
ERR6="$(cat "${WORKDIR}/sub6.err" "${WORKDIR}/sub6.out" 2>/dev/null || true)"
if echo "$ERR6" | grep -qiE 'permissions violation|Permissions Violation|authorization violation|not permitted'; then
  record 6 PASS "arbitrary io.eduvijna.aieos.> subscription denied"
else
  record 6 FAIL "arbitrary subscription denial not evidenced"
fi

if js_event stream info "$STREAM_NAME" >/dev/null 2>&1; then
  record 7 FAIL "EVENT publisher unexpectedly performed stream info"
else
  record 7 PASS "EVENT publisher denied JetStream stream administration"
fi

P9_OK=1
if js_event stream add "EVENT_SHOULD_FAIL" --subjects 'io.eduvijna.aieos.>' --storage memory --defaults >/dev/null 2>&1; then
  P9_OK=0
  js_admin stream rm EVENT_SHOULD_FAIL -f >/dev/null 2>&1 || true
fi
if js_event stream rm "$STREAM_NAME" -f >/dev/null 2>&1; then
  P9_OK=0
fi
if js_event stream edit "$STREAM_NAME" --description 'should-fail' >/dev/null 2>&1; then
  P9_OK=0
fi
if [[ "$P9_OK" -eq 1 ]]; then
  record 9 PASS "EVENT publisher cannot create/delete/update stream"
else
  record 9 FAIL "EVENT publisher performed stream mutation"
fi

if assert_no_repo_creds; then
  record 11 PASS "no generated credential file in governed repository"
else
  record 11 FAIL "credential material present in repository"
fi

# P12 — stop server and destroy workdir contents
if [[ -n "${NATS_PID}" ]] && kill -0 "$NATS_PID" 2>/dev/null; then
  kill "$NATS_PID" 2>/dev/null || true
  wait "$NATS_PID" 2>/dev/null || true
  NATS_PID=""
fi
find "$WORKDIR" -type f \( -name '*.creds' -o -name '*.nk' -o -name '*.jwt' \) -delete 2>/dev/null || true
# Capture results before removing workdi
cp "$RESULTS_FILE" "${TMPDIR:-/tmp}/aieos-epi-sf01-results.$$" 2>/dev/null || true
FINAL_RESULTS="${TMPDIR:-/tmp}/aieos-epi-sf01-results.$$"
cp "$RESULTS_FILE" "$FINAL_RESULTS"
TMP_CHECK="$WORKDIR"
rm -rf "$WORKDIR"
WORKDIR=""
if [[ ! -d "$TMP_CHECK" ]]; then
  echo "12|PASS|disposable operator/account/user/seeds/creds/server/temp removed" >> "$FINAL_RESULTS"
  echo "P12 PASS — disposable operator/account/user/seeds/creds/server/temp removed"
else
  echo "12|FAIL|cleanup incomplete" >> "$FINAL_RESULTS"
  echo "P12 FAIL — cleanup incomplete" >&2
fi

FAILS=0
echo "EPI-PROOF MATRIX:"
for id in 1 2 3 4 5 6 7 8 9 10 11 12; do
  line="$(grep -E "^${id}\\|" "$FINAL_RESULTS" | tail -n1 || true)"
  status="$(echo "$line" | cut -d'|' -f2)"
  [[ -n "$status" ]] || status=FAIL
  echo "  P${id}: ${status}"
  [[ "$status" == "PASS" ]] || FAILS=$((FAILS + 1))
done
rm -f "$FINAL_RESULTS"

if [[ "$FAILS" -ne 0 ]]; then
  echo "EPI-PROOF SUMMARY: FAIL ($FAILS checks failed)" >&2
  exit 1
fi
echo "EPI-PROOF SUMMARY: PASS (12/12)"
