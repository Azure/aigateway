#!/usr/bin/env bash
# Connects an AI Gateway to its Application Insights component over OpenTelemetry, in the order Azure needs:
#   1. Waits until the component reports its OTLP endpoints and its Data Collection Rule. Azure creates them a few
#      minutes after OTLP ingestion turns on, so they can still be empty when the deployment ends.
#   2. Grants the gateway's managed identity Monitoring Metrics Publisher on the rule. Bicep can't: the rule lives in a
#      managed resource group whose deny assignment blocks deployments.
#   3. Deploys the OpenTelemetry exporter from a .bicepparam file, and retries while the role assignment propagates.
# azd runs it after each deployment (see azure.yaml), with the deployment's outputs as environment variables. When
# "azd provision" finds no changes to deploy, it skips the hook: run "azd hooks run postprovision" instead. Running it
# again is harmless.
#
# Usage:
#   export AZURE_RESOURCE_GROUP="<gateway-resource-group>"
#   export APP_INSIGHTS_ID="<component-resource-id>"
#   export AI_GATEWAY_PRINCIPAL_ID="<gateway-managed-identity-object-id>"
#   ./connect-telemetry.sh <exporter.bicepparam>
#
# The .bicepparam file can read more environment variables, such as AI_GATEWAY_NAME and APP_INSIGHTS_NAME.
set -euo pipefail

PARAMS_FILE="${1:?Pass the .bicepparam file of the exporter}"
: "${AZURE_RESOURCE_GROUP:?Set AZURE_RESOURCE_GROUP to the gateway resource group}"
: "${APP_INSIGHTS_ID:?Set APP_INSIGHTS_ID to the resource ID of the Application Insights component}"
: "${AI_GATEWAY_PRINCIPAL_ID:?Set AI_GATEWAY_PRINCIPAL_ID to the object ID of the gateway managed identity}"
SUBSCRIPTION_ID="$(cut -d/ -f3 <<<"$APP_INSIGHTS_ID")"

# The managed Azure Monitor workspace behind OTLP ingestion needs the Microsoft.Monitor resource provider
if [ "$(az provider show -n Microsoft.Monitor --subscription "$SUBSCRIPTION_ID" --query registrationState -o tsv)" != "Registered" ]; then
  echo "📝 Registering the Microsoft.Monitor resource provider"
  az provider register -n Microsoft.Monitor --subscription "$SUBSCRIPTION_ID" --wait
fi

# 1. Wait up to 10 minutes for the three OTLP endpoints and the Data Collection Rule
echo "⏳ Waiting for the OTLP endpoints of ${APP_INSIGHTS_ID##*/}"
READY="(properties.OTLPMetricsEndpoint && properties.OTLPLogsEndpoint && properties.OTLPTracesEndpoint)"
for attempt in $(seq 1 60); do
  DCR_ID="$(az resource show --ids "$APP_INSIGHTS_ID" --api-version 2020-02-02 \
    --query "$READY && properties.DataCollectionRuleResourceId || ''" -o tsv 2>/dev/null || true)"
  [ -n "$DCR_ID" ] && break
  [ "$attempt" -lt 60 ] || { echo "🚨 ${APP_INSIGHTS_ID##*/} has no OTLP endpoints after 10 minutes" >&2; exit 1; }
  sleep 10
done
echo "🆔 Data Collection Rule: ${DCR_ID##*/}"

# 2. Let the gateway's identity publish to the Data Collection Rule
az role assignment create --assignee-object-id "$AI_GATEWAY_PRINCIPAL_ID" --assignee-principal-type ServicePrincipal \
  --role "Monitoring Metrics Publisher" --scope "$DCR_ID" -o none
echo "🔐 The gateway can publish to the Data Collection Rule"

# 3. Create or update the exporter, retrying for up to 5 minutes while the role assignment propagates
for attempt in $(seq 1 10); do
  if az deployment group create --subscription "$SUBSCRIPTION_ID" -g "$AZURE_RESOURCE_GROUP" -n aigw-telemetry \
    -p "$PARAMS_FILE" -o none; then
    echo "📊 The gateway sends metrics, logs, and traces to ${APP_INSIGHTS_ID##*/}"
    exit 0
  fi
  [ "$attempt" -lt 10 ] || break
  echo "⏳ The role assignment may still be propagating. Retrying in 30 seconds."
  sleep 30
done
echo "🚨 The telemetry exporter deployment failed. In a few minutes, run 'azd hooks run postprovision' or this script again." >&2
exit 1
