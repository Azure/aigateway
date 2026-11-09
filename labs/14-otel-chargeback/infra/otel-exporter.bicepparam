// Lab 13's OpenTelemetry exporter, with the token claims to export and the signals that carry each one: the
// recommended preset, plus metrics for the client app claims. azd doesn't deploy it with main.bicep: the postprovision
// hook in azure.yaml runs lab 13's connect-telemetry.sh, which deploys it once the component reports its OTLP
// endpoints and the gateway can publish to them. azd passes the outputs of main.bicep, and the azd environment's
// values such as CLIENT_APP_METRICS, to the hook as environment variables.
using '../../13-monitoring/infra/otel-exporter.bicep'

param gatewayName = readEnvironmentVariable('AI_GATEWAY_NAME')
param appInsightsName = readEnvironmentVariable('APP_INSIGHTS_NAME')

// Set CLIENT_APP_METRICS to false with azd env set to export appid and azp to logs and traces only.
var allSignals = ['logs', 'traces', 'metrics']
var clientAppSignals = bool(readEnvironmentVariable('CLIENT_APP_METRICS', 'true')) ? allSignals : ['logs', 'traces']

param claimAttributes = [
  {
    source: { kind: 'claims', value: 'tid' }
    signals: allSignals
  }
  {
    source: { kind: 'claims', value: 'oid' }
    signals: allSignals
  }
  {
    source: { kind: 'claims', value: 'appid' }
    signals: clientAppSignals
  }
  {
    source: { kind: 'claims', value: 'azp' }
    signals: clientAppSignals
  }
]
