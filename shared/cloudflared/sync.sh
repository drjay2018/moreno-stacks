#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
set -a; source .env; set +a

TUNNEL_ID=$(cloudflared tunnel list -o json | jq -r --arg n "$TUNNEL_NAME" '.[]|select(.name==$n).id')
[[ -n "$TUNNEL_ID" ]] || { echo "Tunnel '$TUNNEL_NAME' no existe" >&2; exit 1; }

docker network inspect "$EDGE_NETWORK" >/dev/null 2>&1 || docker network create "$EDGE_NETWORK"

{
  echo "tunnel: $TUNNEL_ID"
  echo "credentials-file: /etc/cloudflared/creds.json"
  echo "ingress:"
  grep -vE '^\s*(#|$)' routes.conf | while read -r sub svc; do
    fqdn="${sub}.${DOMAIN}"
    echo "  - hostname: $fqdn"
    echo "    service: $svc"
    cloudflared tunnel route dns --overwrite-dns "$TUNNEL_NAME" "$fqdn" >&2
  done
  echo "  - service: http_status:404"
} > config.yml.tmp

cloudflared tunnel --config config.yml.tmp ingress validate
mv config.yml.tmp config.yml
docker compose up -d --force-recreate cloudflared
