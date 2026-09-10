#!/usr/bin/env bash
# Check what we can actually do on dCache InfiniteSpace.
#
# Answers three questions that decide whether the public data repository works:
#   1. Which access model are we on (Simple = root-owned 770, self-managed = we own it)?
#   2. Can we chmod a directory ourselves?
#   3. Do permissions INHERIT to files created afterwards?  <- the one that bites later
#
# Non-destructive: everything happens in a throwaway subdirectory that is removed
# at the end, even on failure.
#
# Usage:  ./check_dcache_access.sh [VO]        (default VO: FZJ-ICE2)
# Needs:  oidc-agent configured with a profile named HIFIS  (oidc-token HIFIS)

set -uo pipefail

VO="${1:-FZJ-ICE2}"
API="https://hifis-storage-web.desy.de/api/v1/namespace"
DOOR="https://hifis-storage-ht.desy.de:2880"
BASE="Helmholtz/${VO}"
PROBE="_access-check-$$"

pass() { printf '  \033[32mPASS\033[0m  %s\n' "$1"; }
fail() { printf '  \033[31mFAIL\033[0m  %s\n' "$1"; }
info() { printf '        %s\n' "$1"; }

mode_owner() {  # $1 = path -> "mode owner group", read anonymously
  curl -s -m 25 "${API}/${1}?optional=true" \
    | python3 -c "import sys,json;d=json.load(sys.stdin);print(oct(d['mode']),d.get('owner','?'),d.get('group','?'))" 2>/dev/null
}

echo
echo "dCache access check for /${BASE}"
echo "======================================================================"

# --- 1. access model -------------------------------------------------------
read -r MODE OWNER GROUP <<<"$(mode_owner "$BASE")"
if [ -z "${MODE:-}" ]; then
  fail "cannot read /${BASE} - does the VO exist?"; exit 1
fi
info "mode=${MODE} owner=${OWNER} group=${GROUP}"
if [ "$OWNER" = "0" ]; then
  fail "Simple access model (root-owned). You cannot chmod; HIFIS support must."
  MODEL=simple
else
  pass "Self-managed access model (owner ${OWNER}). You can chmod yourself."
  MODEL=selfmanaged
fi

# --- token -----------------------------------------------------------------
TOKEN="$(oidc-token HIFIS 2>/dev/null)"
if [ -z "$TOKEN" ]; then
  fail "no token from 'oidc-token HIFIS' - run: eval \$(oidc-agent-service use)"
  echo; exit 1
fi
pass "got an OIDC token"
AUTH=(-H "Authorization: Bearer ${TOKEN}")
JSON=(-H "Content-Type: application/json")

cleanup() {
  # The probe file (if step 3 got that far) must go before its directory --
  # DELETE on a non-empty directory fails instead of recursing.
  curl -s -m 25 -X DELETE "${AUTH[@]}" "${API}/${BASE}/${PROBE}/probe.txt" >/dev/null 2>&1
  curl -s -m 25 -X DELETE "${AUTH[@]}" "${API}/${BASE}/${PROBE}" >/dev/null 2>&1
}
trap cleanup EXIT

# --- 2. can we create and chmod? -------------------------------------------
code=$(curl -s -m 30 -o /dev/null -w '%{http_code}' -X POST "${AUTH[@]}" "${JSON[@]}" \
        -d "{\"action\":\"mkdir\",\"name\":\"${PROBE}\"}" "${API}/${BASE}")
case "$code" in
  200|201) pass "created /${BASE}/${PROBE}" ;;
  *)       fail "mkdir returned HTTP ${code}"; exit 1 ;;
esac

code=$(curl -s -m 30 -o /dev/null -w '%{http_code}' -X POST "${AUTH[@]}" "${JSON[@]}" \
        -d '{"action":"chmod","mode":493}' "${API}/${BASE}/${PROBE}")   # 493 = 0755
read -r PMODE _ _ <<<"$(mode_owner "${BASE}/${PROBE}")"
if [ "$PMODE" = "0o755" ]; then
  pass "chmod to 0755 worked (HTTP ${code})"
else
  fail "chmod returned HTTP ${code}; mode is ${PMODE:-unknown}, wanted 0o755"
  [ "$MODEL" = simple ] && info "expected on the Simple model - this is what the ticket is for"
fi

# --- 3. does a NEW file inherit the permissions? ----------------------------
# The high-throughput door redirects both PUT and GET to a pool host (HTTP
# 307/302) -- that's normal, not a failure, so both requests below must
# follow it. The PUT also needs --location-trusted: plain -L strips the
# Authorization header on a host change, which the pool redirect always is.
echo "hello from check_dcache_access.sh" > /tmp/${PROBE}.txt
code=$(curl -s -m 60 -o /dev/null -w '%{http_code}' -L --location-trusted -T /tmp/${PROBE}.txt \
        "${AUTH[@]}" "${DOOR}/${BASE}/${PROBE}/probe.txt")
rm -f /tmp/${PROBE}.txt
if [ "$code" = "201" ] || [ "$code" = "204" ] || [ "$code" = "200" ]; then  # dCache uses 201 for a new file
  pass "uploaded a test file (HTTP ${code})"
  read -r FMODE _ _ <<<"$(mode_owner "${BASE}/${PROBE}/probe.txt")"
  info "new file mode: ${FMODE:-unknown}"
  anon=$(curl -sL -o /dev/null -w '%{http_code}' -m 30 "${DOOR}/${BASE}/${PROBE}/probe.txt")
  if [ "$anon" = "200" ]; then
    pass "ANONYMOUS read of the new file works - inheritance is fine"
  else
    fail "anonymous read returned HTTP ${anon} - permissions did NOT inherit"
    info "every upload would need a chmod afterwards; raise this with HIFIS"
  fi
else
  fail "upload returned HTTP ${code}"
fi

echo "======================================================================"
echo
