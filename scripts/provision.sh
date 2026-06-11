#!/usr/bin/env bash
set -euo pipefail

RESOURCE_GROUP="${RESOURCE_GROUP:-rg-voice-live-acs-demo}"
LOCATION="${LOCATION:-eastus2}"
SUFFIX="${SUFFIX:-$(date +%s | tail -c 7)}"
ACS_NAME="${ACS_NAME:-vlacs${SUFFIX}}"
AI_NAME="${AI_NAME:-vlai${SUFFIX}}"

az group create \
  --name "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --tags purpose=voice-live-acs-demo createdBy=copilot \
  --only-show-errors \
  --output none

az communication create \
  --resource-group "$RESOURCE_GROUP" \
  --name "$ACS_NAME" \
  --location global \
  --data-location "United States" \
  --tags purpose=voice-live-acs-demo createdBy=copilot \
  --only-show-errors \
  --output none

az cognitiveservices account create \
  --resource-group "$RESOURCE_GROUP" \
  --name "$AI_NAME" \
  --location "$LOCATION" \
  --kind AIServices \
  --sku S0 \
  --custom-domain "$AI_NAME" \
  --yes \
  --tags purpose=voice-live-acs-demo createdBy=copilot \
  --only-show-errors \
  --output none

ACS_HOST="$(az communication show -g "$RESOURCE_GROUP" -n "$ACS_NAME" --query hostName -o tsv --only-show-errors)"
AI_ENDPOINT="$(az cognitiveservices account show -g "$RESOURCE_GROUP" -n "$AI_NAME" --query properties.endpoint -o tsv --only-show-errors)"

cat <<EOF
RESOURCE_GROUP=$RESOURCE_GROUP
ACS_NAME=$ACS_NAME
ACS_ENDPOINT=https://$ACS_HOST
AI_NAME=$AI_NAME
VOICE_LIVE_ENDPOINT=$AI_ENDPOINT
EOF
