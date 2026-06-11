#!/usr/bin/env bash
set -euo pipefail

: "${RESOURCE_GROUP:?Set RESOURCE_GROUP}"
: "${ACS_NAME:?Set ACS_NAME}"
: "${PUBLIC_HOST:?Set PUBLIC_HOST, for example https://example.devtunnels.ms}"

ACS_ID="$(az communication show -g "$RESOURCE_GROUP" -n "$ACS_NAME" --query id -o tsv --only-show-errors)"

az eventgrid event-subscription create \
  --name voice-live-acs-incoming \
  --source-resource-id "$ACS_ID" \
  --endpoint "${PUBLIC_HOST%/}/api/incoming-call" \
  --included-event-types Microsoft.Communication.IncomingCall \
  --event-delivery-schema EventGridSchema \
  --only-show-errors \
  --output table
