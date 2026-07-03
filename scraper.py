import os
import sys
import json
import time
import urllib.request
from datetime import datetime, timezone

LEAGUE_ID = "248321"
BASE = "https://play.fifa.com"
RANKING_URL = f"{BASE}/api/en/fantasy/ranking/league/{LEAGUE_ID}?limit=20"
TEAM_HISTORY_URL = BASE + "/api/en/fantasy/team/history/{round}/{team_id}"
PLAYERS_URL = f"{BASE}/json/fantasy/players.json"
SQUADS_URL = f"{BASE}/json/fantasy/squads.json"

DATA_DIR = "data"
HISTORY_FILE = os.path.join(DATA_DIR, "history.json")
PLAYERS_FILE = os.path.join(DATA_DIR, "players.json")
SQUADS_FILE = os.path.join(DATA_DIR, "squads.json")

COOKIE = os.environ.get("FIFA_COOKIE")

if not COOKIE:
    print("ERROR: FIFA_COOKIE secret is not set", file=sys.stderr)
    sys.exit(1)


def http_get_json(url, use_cookie=True, timeout=15):
    headers = {
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    if use_cookie:
        headers["Cookie"] = COOKIE
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default
    return default


def save_json(path, obj):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# 1. League ranking (tells us the current round + which teams are in the league)
# ---------------------------------------------------------------------------
try:
    ranking_data = http_get_json(RANKING_URL)
except Exception as e:
    print(f"ERROR: ranking request failed: {e}", file=sys.stderr)
    sys.exit(1)

ranks = ranking_data.get("success", {}).get("ranks")
if not ranks:
    print(f"ERROR: no ranks in response (cookie may be expired): {ranking_data}", file=sys.stderr)
    sys.exit(1)

current_round = max(r["roundId"] for r in ranks)

# ---------------------------------------------------------------------------
# 2. Public game data: full player database + national squads.
#    These are static assets and do NOT require the session cookie.
# ---------------------------------------------------------------------------
try:
    players = http_get_json(PLAYERS_URL, use_cookie=False)
    save_json(PLAYERS_FILE, players)
    print(f"OK: saved {len(players)} players")
except Exception as e:
    print(f"WARN: could not refresh players.json: {e}", file=sys.stderr)

try:
    squads = http_get_json(SQUADS_URL, use_cookie=False)
    save_json(SQUADS_FILE, squads)
    print(f"OK: saved {len(squads)} squads")
except Exception as e:
    print(f"WARN: could not refresh squads.json: {e}", file=sys.stderr)

# ---------------------------------------------------------------------------
# 3. Per-team, per-round history (squad, captain, chips, transfers).
#    Backfills any round we don't have cached yet; always re-fetches the
#    current round since it can still change until it locks.
# ---------------------------------------------------------------------------
history = load_json(HISTORY_FILE, {"teams": {}})
history.setdefault("teams", {})

TEAM_HISTORY_FIELDS = [
    "captain", "vice", "lineup", "bench", "benchOrder", "substitutions",
    "transfers", "captainChanges", "value", "maxCaptain", "maxCaptainBooster",
    "twelfthMan", "wildCard", "qualification", "cleanSheet",
    "qualificationPlayerIds", "cleanSheetPlayerIds", "roundPoints",
    "overallPoints", "freeTransfers", "negativeTransfers", "locked",
]

fetch_errors = 0

for r in ranks:
    team_id = str(r["userId"])
    team_entry = history["teams"].setdefault(team_id, {"userName": r["userName"], "rounds": {}})
    team_entry["userName"] = r["userName"]
    team_entry["avatar"] = r.get("avatar")
    team_entry["level"] = r.get("level")
    team_entry["overallRank"] = r.get("overallRank")
    team_entry["roundRank"] = r.get("roundRank")
    team_entry["overallPoints"] = r.get("overallPoints")
    team_entry["roundPoints"] = r.get("roundPoints")

    for round_id in range(1, current_round + 1):
        round_key = str(round_id)
        # Skip rounds we already have, except the current (still-open) one.
        if round_key in team_entry["rounds"] and round_id != current_round:
            continue
        try:
            resp = http_get_json(TEAM_HISTORY_URL.format(round=round_id, team_id=team_id))
            success = resp.get("success")
            if not success:
                continue
            team_entry["rounds"][round_key] = {
                k: success.get(k) for k in TEAM_HISTORY_FIELDS
            }
            time.sleep(0.2)  # be polite to the API
        except Exception as e:
            fetch_errors += 1
            print(f"WARN: team {team_id} round {round_id} failed: {e}", file=sys.stderr)

history["current_round"] = current_round
history["league_id"] = LEAGUE_ID
history["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

save_json(HISTORY_FILE, history)

print(
    f"OK: saved history for {len(history['teams'])} teams through round "
    f"{current_round} at {history['updated_at']} ({fetch_errors} fetch errors)"
)
