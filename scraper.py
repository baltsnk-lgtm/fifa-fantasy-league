import os
import sys
import json
import urllib.request
from datetime import datetime, timezone

LEAGUE_ID = "248321"
URL = f"https://play.fifa.com/api/en/fantasy/ranking/league/{LEAGUE_ID}?limit=20"

COOKIE = os.environ.get("FIFA_COOKIE")

if not COOKIE:
    print("ERROR: FIFA_COOKIE secret is not set", file=sys.stderr)
    sys.exit(1)

req = urllib.request.Request(
    URL,
    headers={
        "Cookie": COOKIE,
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    },
)

try:
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read().decode("utf-8")
        data = json.loads(raw)
except Exception as e:
    print(f"ERROR: request failed: {e}", file=sys.stderr)
    sys.exit(1)

ranks = data.get("success", {}).get("ranks")

if not ranks:
    # Cookie most likely expired -> API returns {"success":{}, "errors":[...]}
    print(f"ERROR: no ranks in response (cookie may be expired): {data}", file=sys.stderr)
    sys.exit(1)

standings = sorted(
    (
        {
            "rank": r["overallRank"],
            "name": r["userName"],
            "points": r["overallPoints"],
            "round_points": r["roundPoints"],
            "round_rank": r["roundRank"],
            "level": r["level"],
            "avatar": r["avatar"],
        }
        for r in ranks
    ),
    key=lambda x: x["rank"],
)

output = {
    "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
    "league_id": LEAGUE_ID,
    "standings": standings,
}

with open("standings.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"OK: saved {len(standings)} standings at {output['updated_at']}")
