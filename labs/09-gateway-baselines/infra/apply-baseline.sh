#!/usr/bin/env bash
# Applies the policy baseline in baseline-policies.json at Gateway scope (the gateway's default
# workspace). It reads the current Gateway scope policies, replaces the entries whose type is in
# the baseline, keeps every other policy, and patches the workspace.
#
# Usage:
#   export RG="<resource-group>" GATEWAY="<gateway>"
#   export ALLOWED_CIDRS="198.51.100.7/32"   # comma-separated CIDR ranges for the IP filter
#   ./apply-baseline.sh              # apply the baseline
#   ./apply-baseline.sh --dry-run    # print the merged policies without changing anything
#   ./apply-baseline.sh --remove     # remove the baseline policy types from Gateway scope
#
# Set BASELINE_FILE to use a different policy file. Requires the Azure CLI (az login) with the
# aigateway extension, and jq.
set -euo pipefail

MODE="apply"
case "${1:-}" in
  "") ;;
  --dry-run) MODE="dry-run" ;;
  --remove) MODE="remove" ;;
  *) echo "Unknown option: $1. Use --dry-run or --remove." >&2; exit 2 ;;
esac

: "${RG:?Set RG to your resource group}"
: "${GATEWAY:?Set GATEWAY to your gateway name}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASELINE_FILE="${BASELINE_FILE:-$SCRIPT_DIR/baseline-policies.json}"
BASELINE="$(jq -c '.' "$BASELINE_FILE")"

# The file holds a placeholder address for the IP filter. Never apply it: replace it with ALLOWED_CIDRS.
if [ "$MODE" != "remove" ] && jq -e 'any(.[]; .type == "ipFilter")' >/dev/null <<<"$BASELINE"; then
  : "${ALLOWED_CIDRS:?Set ALLOWED_CIDRS to the comma-separated CIDR ranges to allow, for example \"\$(curl -s https://api.ipify.org)/32\"}"
  BASELINE="$(jq -c --arg cidrs "$ALLOWED_CIDRS" '
    map(if .type == "ipFilter"
        then .cidrRanges = ($cidrs | split(",") | map(gsub("\\s"; "")) | map(select(length > 0)))
        else . end)' <<<"$BASELINE")"
  if ! jq -e 'all(.[] | select(.type == "ipFilter"); (.cidrRanges | length) > 0)' >/dev/null <<<"$BASELINE"; then
    echo "ALLOWED_CIDRS doesn't contain any CIDR ranges." >&2
    exit 2
  fi
  INVALID="$(jq -r '[.[] | select(.type == "ipFilter") | .cidrRanges[] | select(contains("/") | not)] | join(", ")' <<<"$BASELINE")"
  if [ -n "$INVALID" ]; then
    echo "Use CIDR notation with a prefix length, for example $INVALID/32 for a single address." >&2
    exit 2
  fi
fi

# The az aigateway policy commands set policies from flags, so to apply the whole file the script calls the
# management API with az rest.
GATEWAY_ID="$(az aigateway show -g "$RG" -n "$GATEWAY" --query id -o tsv)"
URL="https://management.azure.com$GATEWAY_ID/workspaces/default?api-version=2025-09-01-preview"

# A PATCH replaces the whole properties.policies array, so always merge with the current array.
CURRENT="$(az rest --method get --url "$URL")"
KEEP='[(.properties.policies // [])[] | select(.type | IN($baseline[].type) | not)]'
if [ "$MODE" = "remove" ]; then
  POLICIES="$(jq -c --argjson baseline "$BASELINE" "$KEEP" <<<"$CURRENT")"
else
  POLICIES="$(jq -c --argjson baseline "$BASELINE" "$KEEP + \$baseline" <<<"$CURRENT")"
fi

if [ "$MODE" = "dry-run" ]; then
  echo "Gateway scope policies after the change (nothing was applied):"
  jq '.' <<<"$POLICIES"
  exit 0
fi

if [ "$MODE" = "apply" ] && jq -e 'any(.[]; .type == "ipFilter")' >/dev/null <<<"$BASELINE"; then
  echo "The IP filter allows runtime calls only from: $(jq -r '[.[] | select(.type == "ipFilter") | .cidrRanges[]] | join(", ")' <<<"$BASELINE")"
fi

az rest --method patch --url "$URL" --body "{\"properties\":{\"policies\":$POLICIES}}" --output none

echo "Gateway scope policies on $GATEWAY:"
az rest --method get --url "$URL" | jq -r '
  (.properties.policies // []) as $p
  | if ($p | length) == 0 then "  (none)" else $p[] | "  \(.type)  \(del(.type) | tojson)" end'
