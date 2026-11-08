#!/usr/bin/env bash
# Start the backend and a Cloudflare quick tunnel together, then print the
# HTTPS URL phones open. Safari needs an HTTPS origin for camera, microphone
# and speech recognition; the quick tunnel gives one on any Wi-Fi without
# installing a certificate on the phone. Ctrl-C stops both.
#
# Needs: the .venv from README, and `brew install cloudflared`
# (`brew install qrencode` adds a scannable QR code).
set -euo pipefail
cd "$(dirname "$0")/.."
PORT="${PORT:-8000}"

command -v cloudflared >/dev/null || { echo "cloudflared missing: brew install cloudflared" >&2; exit 1; }
[ -f .env ] || { echo ".env missing: run python scripts/configure.py first" >&2; exit 1; }
[ -f .venv/bin/activate ] && source .venv/bin/activate
if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Port $PORT is already in use. Stop that process or run PORT=8001 $0" >&2; exit 1
fi

log="$(mktemp -t ahead-tunnel)"
cleanup() { kill "${tunnel_pid:-}" "${backend_pid:-}" 2>/dev/null || true; rm -f "$log"; }
trap cleanup EXIT INT TERM

python -m uvicorn backend.app:create_app --factory --host 127.0.0.1 --port "$PORT" &
backend_pid=$!
cloudflared tunnel --url "http://127.0.0.1:$PORT" --no-autoupdate >"$log" 2>&1 &
tunnel_pid=$!

url=""
for _ in $(seq 1 60); do
  url="$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$log" | head -1 || true)"
  [ -n "$url" ] && break
  kill -0 "$tunnel_pid" 2>/dev/null || { cat "$log" >&2; exit 1; }
  sleep 0.5
done
[ -n "$url" ] || { echo "Tunnel gave no URL in 30 s:" >&2; cat "$log" >&2; exit 1; }

echo
echo "Phones open:  $url"
echo "Mac opens:    http://127.0.0.1:$PORT"
echo "API key:      TV_API_KEY in .env"
command -v qrencode >/dev/null && qrencode -t ANSIUTF8 "$url"
echo "Ctrl-C stops the backend and the tunnel."
wait "$backend_pid"
