#!/bin/sh
# The owner's view of the beta requests: ./beta.sh [list | flush].
# list shows each request (a failed one with App Store Connect's message); flush sends every request still waiting
# to App Store Connect, for after the three ASC secrets are set. Reads OWNER_TOKEN from .dev.vars beside this script.
set -e
cd "$(dirname "$0")"
url=${AHEAD_ASK_URL:-https://ahead-ask.jonasneves.workers.dev}
token=$(sed -n 's/^OWNER_TOKEN=//p' .dev.vars 2>/dev/null)
[ -n "$token" ] || { echo "no OWNER_TOKEN in .dev.vars"; exit 1; }
case "${1:-list}" in
  list) curl -s "$url/beta/list" -H "Authorization: Bearer $token" | python3 -c '
import json,sys,datetime
d=json.load(sys.stdin)
if "rows" not in d: sys.exit(d)
print("App Store Connect key: " + ("set" if d["asc"] else "not set, requests wait as queued"))
counts={}
for x in d["rows"]:
    counts[x["status"]]=counts.get(x["status"],0)+1
    when=datetime.datetime.fromtimestamp(x["created"]/1000).strftime("%m-%d %H:%M")
    err="  "+x["error"] if x.get("error") else ""
    print("%s  %-8s %-18s %-7s %s%s" % (when,x["status"],x["device"],x["role"],x["email"],err))
print(len(d["rows"]),"requests", counts)' ;;
  flush) curl -s -X POST "$url/beta/flush" -H "Authorization: Bearer $token"; echo ;;
  *) echo "usage: $0 [list | flush]"; exit 1 ;;
esac
