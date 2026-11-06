#!/usr/bin/env bash
# Regenerates one value (primary or secondary) of an AI Gateway runtime API key, reads the new value, and
# optionally stores it in Azure Key Vault. Only the last four characters of the key are printed.
#
# Zero-downtime rotation for clients that use the primary value today:
#   ./rotate-key.sh support-bot secondary   # 1. issue a fresh secondary value that no client uses yet
#                                           # 2. move every client to the secondary value
#   ./rotate-key.sh support-bot primary     # 3. retire the old primary value
# Next time, swap the roles: regenerate primary first, move clients, then regenerate secondary.
#
# Usage:
#   export RG="<resource-group>" GATEWAY="<gateway>"
#   export KEY_VAULT="<key-vault-name>"     # optional: store the new value as secret <key-name>-api-key
#   ./rotate-key.sh <key-name> <primary|secondary>
# Requires the Azure CLI 2.75 or later with the aigateway extension.
set -euo pipefail

NAME="${1:?Usage: rotate-key.sh <key-name> <primary|secondary>}"
TYPE="${2:?Usage: rotate-key.sh <key-name> <primary|secondary>}"
case "$TYPE" in
  primary|secondary) ;;
  *) echo "error: the second argument must be primary or secondary" >&2; exit 2 ;;
esac
: "${RG:?Set RG to the gateway resource group}"
: "${GATEWAY:?Set GATEWAY to the gateway name}"

az aigateway api-key regenerate -g "$RG" --gateway-name "$GATEWAY" -n "$NAME" --key-type "$TYPE" -o none

VALUE="$(az aigateway api-key list-secrets -g "$RG" --gateway-name "$GATEWAY" -n "$NAME" --query "${TYPE}Key" -o tsv)"
if [[ -z "$VALUE" ]]; then
  echo "error: couldn't read the new $TYPE value. You need the apiKeys/listSecrets/action permission." >&2
  exit 1
fi
echo "Regenerated the $TYPE value of '$NAME' (ends in ...${VALUE: -4})."

if [[ -n "${KEY_VAULT:-}" ]]; then
  SECRET="${NAME}-api-key"
  az keyvault secret set --vault-name "$KEY_VAULT" --name "$SECRET" --value "$VALUE" \
    --tags "aigateway-key=$NAME" "key-type=$TYPE" -o none
  echo "Stored it in Key Vault '$KEY_VAULT' as secret '$SECRET'."
else
  echo "Read it with: az aigateway api-key list-secrets -g $RG --gateway-name $GATEWAY -n $NAME --query ${TYPE}Key -o tsv"
fi
