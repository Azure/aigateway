#!/usr/bin/env bash
# Applies the gateway-wide baseline policies in infra/baselines.json to an AI Gateway.
#
# Gateway-scope policies live in the policies array of the gateway's default workspace. A PATCH replaces the whole
# array, so the script reads the current array, merges the baselines into it, and writes it back:
#   - A baseline whose type already exists updates that policy in place and keeps its id, overrides, and any other
#     fields you set in the portal. Updating a costLimit this way keeps its accumulated spend.
#   - A baseline whose type doesn't exist is appended. A new costLimit gets a fresh, stable id.
#   - Policies of other types (for example ones you added in the portal) are left untouched.
# Running it twice gives the same result. The az aigateway policy commands set one policy at a time from flags, so
# to write the whole array from a file, the script calls the management API with az rest.
#
# Usage:
#   export RG="<gateway-resource-group>" GATEWAY="<gateway-name>"
#   ./apply-baselines.sh [baselines.json]
#   DRY_RUN=1 ./apply-baselines.sh          # print the merged array without changing anything
#
# Requires Azure CLI and jq.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASELINES="${1:-$SCRIPT_DIR/../baselines.json}"
API_VERSION="2025-09-01-preview"
: "${RG:?Set RG to the gateway resource group}"
: "${GATEWAY:?Set GATEWAY to the gateway name}"
command -v jq >/dev/null || { echo "This script needs jq." >&2; exit 1; }
jq -e 'type == "array" and all(.[]; has("type"))' "$BASELINES" >/dev/null \
  || { echo "$BASELINES must be a JSON array of policy objects." >&2; exit 1; }

SUB="$(az account show --query id -o tsv)"
URL="https://management.azure.com/subscriptions/$SUB/resourceGroups/$RG/providers/Microsoft.ApiManagement/aigateways/$GATEWAY/workspaces/default?api-version=$API_VERSION"
NEW_ID="$( (uuidgen 2>/dev/null || cat /proc/sys/kernel/random/uuid) | tr 'A-Z' 'a-z')"

CURRENT="$(az rest --method get --url "$URL")"
POLICIES="$(printf '%s' "$CURRENT" | jq -c --slurpfile base "$BASELINES" --arg id "$NEW_ID" '
  reduce $base[0][] as $b (.properties.policies // [];
    if any(.[]; .type == $b.type)
    then map(if .type == $b.type then . + $b else . end)
    else . + [if $b.type == "costLimit" and ($b.id // "") == "" then $b + {id: $id} else $b end]
    end)')"

echo "Gateway-scope policies after merge:"
printf '%s' "$POLICIES" | jq .

if [ "${DRY_RUN:-0}" = "1" ]; then
  echo "DRY_RUN=1: nothing was changed."
  exit 0
fi

az rest --method patch --url "$URL" --body "{\"properties\":{\"policies\":$POLICIES}}" --output none
echo "Applied. Current gateway-scope policy types:"
az rest --method get --url "$URL" --query "properties.policies[].type" -o tsv
