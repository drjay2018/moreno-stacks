#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")"
source .cf-api

API="https://api.cloudflare.com/client/v4"
AUTH=(-H "Authorization: Bearer $CF_API_TOKEN" -H "Content-Type: application/json")

check() {
  local label="$1" resp="$2"
  if echo "$resp" | jq -e '.success == true' > /dev/null 2>&1; then
    echo "OK: $label"
  else
    echo "FALLO: $label"
    echo "$resp" | jq -c '.errors' 2>/dev/null
  fi
}

echo "== TLS =="
r=$(curl -s -X PATCH "$API/zones/$CF_ZONE_ID/settings/ssl" "${AUTH[@]}" -d '{"value":"full"}')
check "SSL mode (Full)" "$r"
r=$(curl -s -X PATCH "$API/zones/$CF_ZONE_ID/settings/always_use_https" "${AUTH[@]}" -d '{"value":"on"}')
check "Always Use HTTPS" "$r"
r=$(curl -s -X PATCH "$API/zones/$CF_ZONE_ID/settings/min_tls_version" "${AUTH[@]}" -d '{"value":"1.2"}')
check "TLS mínimo 1.2" "$r"

echo "== Bot Fight Mode =="
r=$(curl -s -X GET "$API/zones/$CF_ZONE_ID/bot_management" "${AUTH[@]}" | jq '.result | del(.using_latest_model, .is_robots_txt_managed, .bot_preference_sync_enabled) | .fight_mode = true | .enable_js = true')
r=$(curl -s -X PUT "$API/zones/$CF_ZONE_ID/bot_management" "${AUTH[@]}" -d "$r")
check "Bot Fight Mode" "$r"

echo "== Rate limiting =="
r=$(curl -s -X PUT "$API/zones/$CF_ZONE_ID/rulesets/phases/http_ratelimit/entrypoint" "${AUTH[@]}" -d '{
  "rules": [{
    "action": "block",
    "expression": "true",
    "description": "homelab-rate-limit",
    "ratelimit": {
      "characteristics": ["cf.colo.id","ip.src"],
      "period": 10,
      "requests_per_period": 60,
      "mitigation_timeout": 10
    }
  }]
}')
check "Regla de rate limiting" "$r"

# 0 Hardcoding: una función reutilizable para cualquier app de Access nueva
setup_access_app() {
  local domain="$1" name="$2" emails_csv="$3"
  echo "== Access: $domain =="

  local app_id
  app_id=$(curl -s -X GET "$API/accounts/$CF_ACCOUNT_ID/access/apps" "${AUTH[@]}" | jq -r --arg d "$domain" '.result[] | select(.domain==$d) | .id')

  if [[ -z "$app_id" ]]; then
    r=$(curl -s -X POST "$API/accounts/$CF_ACCOUNT_ID/access/apps" "${AUTH[@]}" -d "{
      \"name\": \"$name\",
      \"domain\": \"$domain\",
      \"type\": \"self_hosted\",
      \"session_duration\": \"24h\"
    }")
    check "Crear app de Access ($name)" "$r"
    app_id=$(echo "$r" | jq -r '.result.id')
  else
    echo "OK: la app de Access ya existe ($app_id), no se duplica"
  fi

  [[ -z "$app_id" || "$app_id" == "null" ]] && return

  local emails_json
  emails_json=$(echo "$emails_csv" | tr ',' '\n' | jq -R '{email:{email: .}}' | jq -s .)

  local policy_id
  policy_id=$(curl -s -X GET "$API/accounts/$CF_ACCOUNT_ID/access/apps/$app_id/policies" "${AUTH[@]}" | jq -r '.result[0].id // empty')

  local body="{\"name\": \"Allow $name\", \"decision\": \"allow\", \"include\": $emails_json}"
  if [[ -n "$policy_id" ]]; then
    r=$(curl -s -X PUT "$API/accounts/$CF_ACCOUNT_ID/access/apps/$app_id/policies/$policy_id" "${AUTH[@]}" -d "$body")
    check "Actualizar política de Access ($name)" "$r"
  else
    r=$(curl -s -X POST "$API/accounts/$CF_ACCOUNT_ID/access/apps/$app_id/policies" "${AUTH[@]}" -d "$body")
    check "Crear política de Access ($name)" "$r"
  fi
}

setup_access_app "files.morenodata.com" "Filebrowser" "$ACCESS_ALLOWED_EMAILS"
setup_access_app "releases.morenodata.com" "Releases" "$RELEASES_ALLOWED_EMAILS"

echo "== Listo =="
