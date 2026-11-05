// The lab's OpenTelemetry exporter, with the portal's recommended token claims (the template's default). azd doesn't
// deploy it with main.bicep: the postprovision hook in azure.yaml runs connect-telemetry.sh, which deploys it once
// the component reports its OTLP endpoints and the gateway can publish to them. The values come from the outputs of
// main.bicep, which azd passes to the hook as environment variables.
using 'otel-exporter.bicep'

param gatewayName = readEnvironmentVariable('AI_GATEWAY_NAME')
param appInsightsName = readEnvironmentVariable('APP_INSIGHTS_NAME')
