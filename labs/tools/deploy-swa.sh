#!/usr/bin/env bash
# Builds the labs site for Azure Static Web Apps (served from /) and deploys it.
#   npm run deploy:swa -- [app-name] [resource-group]
# Requires: az login, and an existing Static Web App.
set -euo pipefail

APP="${1:-swa-ai-gateway-labs}"
RG="${2:-rg-ai-gateway-labs}"
cd "$(dirname "$0")/.."

HOST=$(az staticwebapp show -n "$APP" -g "$RG" --query defaultHostname -o tsv)
rm -rf .swa
LABS_OUT=.swa LABS_SITE_URL="https://$HOST/" node build.mjs --strict
cp tools/staticwebapp.config.json .swa/

SWA_CLI_DEPLOYMENT_TOKEN=$(az staticwebapp secrets list -n "$APP" -g "$RG" --query properties.apiKey -o tsv)
export SWA_CLI_DEPLOYMENT_TOKEN
if command -v swa >/dev/null; then SWA=(swa); else SWA=(npx --yes @azure/static-web-apps-cli); fi
"${SWA[@]}" deploy .swa --env production

echo "Deployed: https://$HOST/"
