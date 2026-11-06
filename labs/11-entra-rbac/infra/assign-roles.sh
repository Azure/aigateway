#!/usr/bin/env bash
# Grants an AI Gateway data-plane role to a Microsoft Entra identity at the gateway, a model alias, or an MCP server.
#
# Usage: ./assign-roles.sh <role> [scope] [principal-object-id] [principal-type]
#   role                 user | models | tools
#                          user   = AI Gateway User        (models and tools)
#                          models = AI Gateway Models User (models only)
#                          tools  = AI Gateway Tools User  (tools only)
#   scope                gateway (default) | alias:<alias-name> | mcp:<mcp-server-name>
#   principal-object-id  defaults to the signed-in user
#   principal-type       User (default) | Group | ServicePrincipal
#
# Requires RG and GATEWAY, the Azure CLI with the aigateway extension, and permission to create role assignments
# (Owner, User Access Administrator, or Role Based Access Control Administrator). Contributor isn't enough.
set -euo pipefail

: "${RG:?Set RG to the resource group of the gateway}"
: "${GATEWAY:?Set GATEWAY to the gateway name}"

ROLE="${1:?Usage: ./assign-roles.sh <user|models|tools> [gateway|alias:<name>|mcp:<name>] [principal-object-id] [principal-type]}"
TARGET="${2:-gateway}"
PRINCIPAL_ID="${3:-}"
PRINCIPAL_TYPE="${4:-User}"

case "$ROLE" in
  user)   ROLE_ID="caad7a21-134e-43f4-a550-c5ffc17e051c"; ROLE_NAME="AI Gateway User" ;;
  models) ROLE_ID="a6b68e3d-a1f0-4c60-8678-237c050cf4ea"; ROLE_NAME="AI Gateway Models User" ;;
  tools)  ROLE_ID="dce03f8d-857f-4e40-a90d-67770fa6ecd2"; ROLE_NAME="AI Gateway Tools User" ;;
  *) echo "Unknown role '$ROLE'. Use user, models, or tools." >&2; exit 2 ;;
esac

GATEWAY_ID="$(az aigateway show -g "$RG" -n "$GATEWAY" --query id -o tsv)"

case "$TARGET" in
  gateway) SCOPE="$GATEWAY_ID" ;;
  alias:?*)
    [[ "$ROLE" != "tools" ]] || { echo "AI Gateway Tools User can't be assigned on a model alias." >&2; exit 2; }
    SCOPE="$GATEWAY_ID/workspaces/default/aliases/${TARGET#alias:}" ;;
  mcp:?*)
    [[ "$ROLE" != "models" ]] || { echo "AI Gateway Models User can't be assigned on an MCP server." >&2; exit 2; }
    SCOPE="$GATEWAY_ID/workspaces/default/toolServers/${TARGET#mcp:}" ;;
  *) echo "Unknown scope '$TARGET'. Use gateway, alias:<name>, or mcp:<name>." >&2; exit 2 ;;
esac

if [[ -z "$PRINCIPAL_ID" ]]; then
  PRINCIPAL_ID="$(az ad signed-in-user show --query id -o tsv)"
  PRINCIPAL_TYPE="User"
fi

echo "Role:      $ROLE_NAME ($ROLE_ID)"
echo "Principal: $PRINCIPAL_ID ($PRINCIPAL_TYPE)"
echo "Scope:     $SCOPE"

az role assignment create \
  --assignee-object-id "$PRINCIPAL_ID" \
  --assignee-principal-type "$PRINCIPAL_TYPE" \
  --role "$ROLE_ID" \
  --scope "$SCOPE" \
  --output none

az role assignment list --scope "$SCOPE" \
  --query "[?principalId=='$PRINCIPAL_ID'].{Role:roleDefinitionName, PrincipalType:principalType, Scope:scope}" \
  --output table

echo "Role assignments can take several minutes to apply. Until then, calls return 403."
