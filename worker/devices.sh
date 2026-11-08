#!/bin/sh
# The owner's switch for phones that asked to use the cloud: ./devices.sh [list | approve <id> | revoke <id>].
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
for kind in ("pending","approved"):
    print(kind + ":" if d[kind] else kind + ": none")
    for x in d[kind]:
        since=datetime.datetime.fromtimestamp((x.get("since") or 0)/1000).strftime("%m-%d %H:%M")
        extra = "  today=%s" % x["today"] if x.get("today") is not None else ""
        name = "".join(c for c in str(x.get("name")) if c.isprintable())
        print("  %s  %s  %s  since %s%s" % (x["id"], x.get("fp"), name, since, extra))' ;;
  approve) [ -n "$2" ] || { echo "usage: $0 approve <id>"; exit 1; }; curl -s -X POST "$url/devices/$2" -H "Authorization: Bearer $token"; echo ;;
  revoke) [ -n "$2" ] || { echo "usage: $0 revoke <id>"; exit 1; }; curl -s -X DELETE "$url/devices/$2" -H "Authorization: Bearer $token"; echo ;;
  *) echo "usage: $0 [list | approve <id> | revoke <id>]"; exit 1 ;;
esac
