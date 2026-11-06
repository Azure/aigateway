#!/usr/bin/env bash
# Connects an AI Gateway to its Application Insights component over OpenTelemetry, in the order Azure needs:
#   1. Waits until the component reports its OTLP endpoints and its Data Collection Rule. Azure creates them a few
#      minutes after OTLP ingestion turns on, so they can still be empty when the deployment ends.
#   2. Grants the gateway's managed identity Monitoring Metrics Publisher on the rule. Bicep can't: the rule lives in a
#      managed resource group whose deny assignment blocks deployments.
#   3. Deletes an earlier exporter of the legacy applicationInsights kind, because an exporter's kind can't change.
#      Then deploys modules/telemetry.bicep, and retries while the role assignment propagates.
# Running it twice gives the same result.
#
# Usage:
#   export RG="<gateway-resource-group>" GATEWAY="<gateway-name>"
#   export APP_INSIGHTS_NAME="<component-name>"   # optional, main.bicep names it <gateway>-insights
#   ./connect-telemetry.sh
#
# Requires Azure CLI with the aigateway extension.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE="$SCRIPT_DIR/../modules/telemetry.bicep"
EXPORTER="appinsights"
: "${RG:?Set RG to the gateway resource group}"
: "${GATEWAY:?Set GATEWAY to the gateway name}"
APP_INSIGHTS_NAME="${APP_INSIGHTS_NAME:-$(cut -c1-64 <<<"$GATEWAY-insights")}"

# The managed Azure Monitor workspace behind OTLP ingestion needs the Microsoft.Monitor resource provider
if [ "$(az provider show -n Microsoft.Monitor --query registrationState -o tsv)" != "Registered" ]; then
  echo "📝 Registering the Microsoft.Monitor resource provider"
  az provider register -n Microsoft.Monitor --wait
fi

# 1. Wait up to 10 minutes for the three OTLP endpoints and the Data Collection Rule
echo "⏳ Waiting for the OTLP endpoints of $APP_INSIGHTS_NAME"
READY="(properties.OTLPMetricsEndpoint && properties.OTLPLogsEndpoint && properties.OTLPTracesEndpoint)"
for attempt in $(seq 1 60); do
  DCR_ID="$(az resource show -g "$RG" -n "$APP_INSIGHTS_NAME" --resource-type Microsoft.Insights/components \
    --api-version 2020-02-02 --query "$READY && properties.DataCollectionRuleResourceId || ''" -o tsv 2>/dev/null || true)"
  [ -n "$DCR_ID" ] && break
  [ "$attempt" -lt 60 ] || { echo "🚨 $APP_INSIGHTS_NAME has no OTLP endpoints after 10 minutes" >&2; exit 1; }
  sleep 10
done
echo "🆔 Data Collection Rule: ${DCR_ID##*/}"

# 2. Let the gateway's identity publish to the Data Collection Rule
PRINCIPAL_ID="$(az aigateway show -g "$RG" -n "$GATEWAY" --query identity.principalId -o tsv)"
az role assignment create --assignee-object-id "$PRINCIPAL_ID" --assignee-principal-type ServicePrincipal \
  --role "Monitoring Metrics Publisher" --scope "$DCR_ID" -o none
echo "🔐 The gateway can publish to the Data Collection Rule"

# 3. Replace a legacy applicationInsights exporter, then create or update the OpenTelemetry exporter, retrying for up
#    to 5 minutes while the role assignment propagates. Azure returns no properties.kind for a legacy exporter, and
#    OpenTelemetry for an OpenTelemetry exporter.
LEGACY="$(az aigateway telemetry-exporter show -g "$RG" --gateway-name "$GATEWAY" -n "$EXPORTER" \
  --query "properties.kind != 'OpenTelemetry'" -o tsv 2>/dev/null || true)"
if [ "$LEGACY" = "true" ]; then
  echo "🧹 Deleting the applicationInsights exporter $EXPORTER, because an exporter's kind can't change"
  az aigateway telemetry-exporter delete -g "$RG" --gateway-name "$GATEWAY" -n "$EXPORTER" --yes -o none
fi
for attempt in $(seq 1 10); do
  if az deployment group create -g "$RG" -n aigw-telemetry -f "$TEMPLATE" \
    -p gatewayName="$GATEWAY" appInsightsName="$APP_INSIGHTS_NAME" exporterName="$EXPORTER" -o none; then
    echo "📊 The gateway sends metrics, logs, and traces to $APP_INSIGHTS_NAME"
    exit 0
  fi
  [ "$attempt" -lt 10 ] || break
  echo "⏳ The role assignment may still be propagating. Retrying in 30 seconds."
  sleep 30
done
echo "🚨 The telemetry exporter deployment failed. Run this script again in a few minutes." >&2
exit 1
