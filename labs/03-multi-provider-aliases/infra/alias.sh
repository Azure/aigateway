#!/usr/bin/env bash
# Lists, creates, retargets, and deletes AI Gateway model aliases with the `az aigateway model-alias` commands.
#
# Usage:
#   export RG="<resource-group>" GATEWAY="<gateway>"
#   ./alias.sh list
#   ./alias.sh show     <alias>
#   ./alias.sh put      <alias> <provider-name> <backend-model> [tokens-per-minute]
#   ./alias.sh retarget <alias> <provider-name> <backend-model>
#   ./alias.sh delete   <alias>
#
# "put" creates the alias, or updates the existing one, with this backend model and these policies. With
# tokens-per-minute it sets a per-caller token limit on the alias; without it, it removes the alias policies.
# "retarget" updates only the backend model, so the alias name, description, and policies stay as they are.
# Requires the Azure CLI 2.75 or later (signed in), the aigateway extension, and jq.
set -euo pipefail

: "${RG:?Set RG to the gateway resource group}"
: "${GATEWAY:?Set GATEWAY to the gateway name}"

ACTION="${1:-list}"
GATEWAY_ID="$(az aigateway show -g "$RG" -n "$GATEWAY" --query id -o tsv)"
ALIAS_ARGS=(-g "$RG" --gateway-name "$GATEWAY")

list_json() { az aigateway model-alias list "${ALIAS_ARGS[@]}" -o json; }
show_json() { az aigateway model-alias show "${ALIAS_ARGS[@]}" -n "$1" -o json; }

# The callable alias lives in properties.aliasName and can contain "/". The resource name can't, so look
# up an existing alias by its callable name first, and otherwise derive a resource name from it.
existing_name() {
  list_json | jq -r --arg a "$1" '.[] | select((.properties.aliasName // .name) == $a) | .name' | head -n1
}
new_name() { echo "$1" | tr '[:upper:]' '[:lower:]' | sed -E 's#[^a-z0-9_.-]+#-#g; s#^[-.]+##; s#[-.]+$##'; }
resource_name() {
  local found
  found="$(existing_name "$1")"
  if [ -n "$found" ]; then echo "$found"; else new_name "$1"; fi
}

model_id() { echo "$GATEWAY_ID/workspaces/default/modelProviders/$1/models/$2"; }

print_table() {
  jq -r '(if type == "array" then .[] else . end)
    | [ (.properties.aliasName // .name),
        (.properties.backendModels[0].resourceId // "-" | split("/") | if length > 2 then "\(.[-3])/\(.[-1])" else .[0] end),
        ((.properties.policies // []) | map(if .type == "tokenLimit" then "tokenLimit \(.count)/\(.period)" else .type end) | join(", ") | if . == "" then "-" else . end) ]
    | @tsv' | { printf 'ALIAS\tPROVIDER/BACKEND MODEL\tALIAS POLICIES\n'; cat; } | column -t -s $'\t'
}

case "$ACTION" in
  list)
    list_json | print_table
    ;;
  show)
    ALIAS="${2:?Pass the alias}"
    show_json "$(resource_name "$ALIAS")"
    ;;
  put)
    ALIAS="${2:?Pass the alias}"
    PROVIDER="${3:?Pass the model provider name}"
    MODEL="${4:?Pass the backend model name}"
    TPM="${5:-}"
    POLICIES="$(jq -cn --arg tpm "$TPM" '
      if $tpm == "" then [] else
        [{type: "tokenLimit", count: ($tpm | tonumber), period: "minute", counterKey: ["identity"]}] end')"
    NAME="$(resource_name "$ALIAS")"
    az aigateway model-alias set "${ALIAS_ARGS[@]}" -n "$NAME" --routing-name "$ALIAS" \
      --backend-model resource-id="$(model_id "$PROVIDER" "$MODEL")" --policies "$POLICIES" \
      --only-show-errors -o none
    show_json "$NAME" | print_table
    ;;
  retarget)
    ALIAS="${2:?Pass the alias}"
    PROVIDER="${3:?Pass the model provider name}"
    MODEL="${4:?Pass the backend model name}"
    NAME="$(resource_name "$ALIAS")"
    az aigateway model-alias update "${ALIAS_ARGS[@]}" -n "$NAME" \
      --backend-model resource-id="$(model_id "$PROVIDER" "$MODEL")" --only-show-errors -o none
    show_json "$NAME" | print_table
    ;;
  delete)
    ALIAS="${2:?Pass the alias}"
    az aigateway model-alias delete "${ALIAS_ARGS[@]}" -n "$(resource_name "$ALIAS")" --yes
    echo "Deleted alias $ALIAS"
    ;;
  *)
    echo "Unknown action '$ACTION'. Use list, show, put, retarget, or delete." >&2
    exit 2
    ;;
esac
