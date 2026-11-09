#!/bin/sh
# The owner's view of the phones that use the cloud, and the block list: ./devices.sh [list | block <id> | unblock <id>].
# Phones are approved automatically within the daily limits (README); block turns one off.
# Reads OWNER_TOKEN from .dev.vars beside this script (the same value as the Worker's secret).
set -e
cd "$(dirname "$0")"
url=${AHEAD_ASK_URL:-https://ahead-ask.jonasneves.workers.dev}
token=$(sed -n 's/^OWNER_TOKEN=//p' .dev.vars 2>/dev/null)
[ -n "$token" ] || { echo "no OWNER_TOKEN in .dev.vars"; exit 1; }
case "${1:-list}" in
  list) curl -s "$url/devices" -H "Authorization: Bearer $token" | python3 -c '
import json,sys,datetime
d=json.load(sys.stdin)
print("today: %s asks, %s phones enrolled" % (d["today"], d["enrolled"]))
print("approved:" if d["approved"] else "approved: none")
for x in d["approved"]:
    since=datetime.datetime.fromtimestamp((x.get("since") or 0)/1000).strftime("%m-%d %H:%M")
    name = "".join(c for c in str(x.get("name")) if c.isprintable())
    print("  %s  %s  %s  since %s  today=%s" % (x["id"], x.get("fp"), name, since, x["today"]))
print("blocked: " + (", ".join(d["blocked"]) if d["blocked"] else "none"))' ;;
  block) [ -n "$2" ] || { echo "usage: $0 block <id>"; exit 1; }; curl -s -X DELETE "$url/devices/$2" -H "Authorization: Bearer $token"; echo ;;
  unblock) [ -n "$2" ] || { echo "usage: $0 unblock <id>"; exit 1; }; curl -s -X POST "$url/devices/$2" -H "Authorization: Bearer $token"; echo ;;
  *) echo "usage: $0 [list | block <id> | unblock <id>]"; exit 1 ;;
esac
