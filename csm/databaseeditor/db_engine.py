"""Core CS Manager Database, Tournament Scheduler/Validator, Balance & Weapons Engine."""

from __future__ import annotations

import base64
import copy
import datetime as dt
import json
import math
import os
import platform
import random
import shutil
from pathlib import Path
from typing import Any

import gamedata as gd


# 7 reference years whose Jan 1 covers Mon..Sun (2029=Mon..2034=Sun, 2028=Leap Sat)
ANCHOR_SCENARIO_YEARS = [2029, 2030, 2031, 2026, 2027, 2028, 2034]
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


DATABASE_JSON_FILES = [
    "teams.json",
    "players.json",
    "playerContracts.json",
    "playerRelationships.json",
    "staffers.json",
    "staffContracts.json",
    "sponsors.json",
    "tournaments.json",
    "tournamentStages.json",
    "workshop_manifest.json",
]

DEFAULT_SKILL_KEYS = [s["key"] for s in gd.PLAYER_SKILLS]
CORE_16_SKILL_KEYS = [
    s["key"] for s in gd.PLAYER_SKILLS if s["key"] not in ("pistols", "smgs")
]
STAFF_SKILL_KEYS = [s["key"] for s in gd.STAFF_SKILLS]

# Exact dev GameBalance baseline from CS Manager's test/gameBalance.json
DEV_GAMEBALANCE_BASELINE = {
    "greatRegensOnNewCareer": 3, "goodRegensOnNewCareer": 77,
    "averageRegensOnNewCareer": 140, "badRegensOnNewCareer": 100,
    "practiceFacilitiesCostLevel0": 0, "practiceFacilitiesCostLevel1": 1500,
    "practiceFacilitiesCostLevel2": 4000, "practiceFacilitiesCostLevel3": 7000, "practiceFacilitiesCostLevel4": 20000,
    "academyCostLevel0": 0, "academyCostLevel1": 5000,
    "academyCostLevel2": 15000, "academyCostLevel3": 30000, "academyCostLevel4": 110000,
    "brandingCenterCostLevel0": 0, "brandingCenterCostLevel1": 3000,
    "brandingCenterCostLevel2": 5000, "brandingCenterCostLevel3": 10000,
    "brandingCenterCostLevel4": 20000, "brandingCenterCostLevel5": 30000,
    "brandingCenterCostLevel6": 50000, "brandingCenterCostLevel7": 80500,
    "brandingCenterCostLevel8": 120000, "brandingCenterCostLevel9": 260000,
    "ownerContributionTier1": 2500, "ownerContributionTier2": 5000, "ownerContributionTier3": 9000,
    "ownerContributionTier4": 13500, "ownerContributionTier5": 18000, "ownerContributionTier6": 27000,
    "ownerContributionTier7": 38000, "ownerContributionTier8": 55000, "ownerContributionTier9": 72000,
    "ownerContributionTier10": 92000, "ownerContributionTier11": 113000, "ownerContributionTier12": 140000,
    "ownerContributionTier13": 165000, "ownerContributionTier14": 180000, "ownerContributionTier15": 215000,
    "ownerContributionTier16": 240000, "ownerContributionTier17": 265000, "ownerContributionTier18": 295000,
    "ownerContributionTier19": 330000, "ownerContributionTier20": 365000,
    "merchContributionTier1": 100, "merchContributionTier2": 250, "merchContributionTier3": 450,
    "merchContributionTier4": 650, "merchContributionTier5": 1000, "merchContributionTier6": 1650,
    "merchContributionTier7": 2500, "merchContributionTier8": 3850, "merchContributionTier9": 5500,
    "merchContributionTier10": 8800, "merchContributionTier11": 13200, "merchContributionTier12": 19800,
    "merchContributionTier13": 27500, "merchContributionTier14": 38500, "merchContributionTier15": 51000,
    "merchContributionTier16": 66000, "merchContributionTier17": 88000, "merchContributionTier18": 110000,
    "merchContributionTier19": 135000, "merchContributionTier20": 160000,
}


def _balance_param_groups(gb: dict[str, Any]) -> list[dict[str, Any]]:
    """Group and naturally sort all GameBalance parameters for modding UI."""
    def _num_tail(k: str) -> tuple[int, str]:
        digits = ""
        for ch in reversed(k):
            if ch.isdigit():
                digits = ch + digits
            else:
                break
        return (int(digits) if digits else -1, k.lower())

    regen_order = ["greatRegensOnNewCareer", "goodRegensOnNewCareer", "averageRegensOnNewCareer", "badRegensOnNewCareer"]
    groups_map: list[tuple[str, str, list[str]]] = [
        ("regens", "1. Regen Intake Pool (New Career Draft)", [k for k in regen_order if k in gb]),
        ("practice", "2. Practice Facility Upgrades (Lv 0-4)", sorted([k for k in gb if k.startswith("practiceFacilitiesCostLevel")], key=_num_tail)),
        ("academy", "3. Youth Academy Upgrades (Lv 0-4)", sorted([k for k in gb if k.startswith("academyCostLevel")], key=_num_tail)),
        ("branding", "4. Branding Center Upgrades (Lv 0-9)", sorted([k for k in gb if k.startswith("brandingCenterCostLevel")], key=_num_tail)),
        ("owner", "5. Owner Monthly Contribution (Tiers 1-20)", sorted([k for k in gb if k.startswith("ownerContributionTier")], key=_num_tail)),
        ("merch", "6. Merch Monthly Contribution (Tiers 1-20)", sorted([k for k in gb if k.startswith("merchContributionTier")], key=_num_tail)),
    ]
    used = {k for _, _, ks in groups_map for k in ks}
    others = sorted([k for k in gb if k not in used], key=_num_tail)
    if others:
        groups_map.append(("other", "7. Other Custom Parameters", others))
    return [{"id": gid, "title": title, "keys": ks} for gid, title, ks in groups_map if ks]


def discover_csm_appdata_dirs() -> dict[str, list[str]]:
    """Auto-discover CS Manager Databases, GameBalances, and Weapons directories."""
    system = platform.system()
    home = Path.home()
    roots: list[Path] = []
    if system == "Windows":
        local_low = home / "AppData" / "LocalLow" / "Crumana" / "CS Manager"
        if os.environ.get("USERPROFILE"):
            roots.append(Path(os.environ["USERPROFILE"]) / "AppData" / "LocalLow" / "Crumana" / "CS Manager")
        roots.append(local_low)
    elif system == "Darwin":
        roots.append(home / "Library" / "Application Support" / "Crumana" / "CS Manager")
        roots.append(home / "Library" / "Application Support" / "com.Crumana.CSManager")
    else:
        roots.append(home / ".config" / "unity3d" / "Crumana" / "CS Manager")
        steam_compat = (
            home / ".local" / "share" / "Steam" / "steamapps" / "compatdata"
        )
        if steam_compat.exists():
            for child in steam_compat.iterdir():
                cand = (
                    child / "pfx" / "drive_c" / "users" / "steamuser"
                    / "AppData" / "LocalLow" / "Crumana" / "CS Manager"
                )
                if cand.exists():
                    roots.append(cand)

    unique_roots: list[Path] = []
    seen = set()
    for r in roots:
        try:
            rp = r.resolve()
        except OSError:
            rp = r
        if rp not in seen and r.exists():
            seen.add(rp)
            unique_roots.append(r)

    out = {"roots": [str(r) for r in unique_roots], "databases": [], "gameBalances": [], "weapons": []}
    for r in unique_roots:
        for cat, key in [("Databases", "databases"), ("GameBalances", "gameBalances"), ("Weapons", "weapons")]:
            cdir = r / cat
            if cdir.exists() and cdir.is_dir():
                out[key].append(str(cdir))
    return out


def list_all_packs() -> dict[str, list[dict[str, Any]]]:
    """List installed Database, GameBalance, and Weapons packs."""
    dirs = discover_csm_appdata_dirs()
    result: dict[str, list[dict[str, Any]]] = {"databases": [], "gameBalances": [], "weapons": []}

    for d in dirs["databases"]:
        for child in sorted(Path(d).iterdir(), key=lambda p: p.name.lower()):
            if child.is_dir() and (child / "teams.json").exists():
                wm = child / "workshop_manifest.json"
                title = child.name
                if wm.exists():
                    try:
                        title = json.loads(wm.read_text(encoding="utf-8")).get("databaseName") or child.name
                    except Exception:
                        pass
                result["databases"].append({
                    "name": child.name,
                    "displayName": title,
                    "path": str(child),
                    "mtime": child.stat().st_mtime,
                })

    for d in dirs["gameBalances"]:
        for child in sorted(Path(d).iterdir(), key=lambda p: p.name.lower()):
            if child.is_dir() and (child / "gameBalance.json").exists():
                result["gameBalances"].append({
                    "name": child.name,
                    "path": str(child / "gameBalance.json"),
                    "dir": str(child),
                    "mtime": (child / "gameBalance.json").stat().st_mtime,
                })

    for d in dirs["weapons"]:
        for child in sorted(Path(d).iterdir(), key=lambda p: p.name.lower()):
            if child.is_dir() and (child / "weapons.json").exists():
                result["weapons"].append({
                    "name": child.name,
                    "path": str(child / "weapons.json"),
                    "dir": str(child),
                    "mtime": (child / "weapons.json").stat().st_mtime,
                })
    return result


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return copy.deepcopy(default)
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _avg(vals: list[float]) -> float:
    return sum(vals) / len(vals) if vals else 0.0


def _gini(vals: list[float]) -> float:
    clean = sorted(max(0.0, float(v)) for v in vals)
    n = len(clean)
    tot = sum(clean)
    if n == 0 or tot <= 1e-12:
        return 0.0
    weighted = sum((2 * (i + 1) - n - 1) * v for i, v in enumerate(clean))
    return round(weighted / (n * tot), 3)


def _percentiles(vals: list[float]) -> dict[str, Any]:
    if not vals:
        return {"count": 0, "min": 0, "p10": 0, "p25": 0, "p50": 0, "p75": 0, "p90": 0, "max": 0}
    s = sorted(float(v) for v in vals)
    n = len(s)

    def _q(p: float) -> float:
        idx = p * (n - 1)
        lo = int(math.floor(idx))
        hi = int(math.ceil(idx))
        if lo == hi:
            return round(s[lo], 2)
        return round(s[lo] + (s[hi] - s[lo]) * (idx - lo), 2)

    return {
        "count": n,
        "min": round(s[0], 2),
        "p10": _q(0.10),
        "p25": _q(0.25),
        "p50": _q(0.50),
        "p75": _q(0.75),
        "p90": _q(0.90),
        "max": round(s[-1], 2),
    }


def _pearson_r(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 3 or len(ys) != n:
        return 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = sum((x - mx) ** 2 for x in xs)
    dy = sum((y - my) ** 2 for y in ys)
    den = math.sqrt(dx * dy)
    return round(num / den, 4) if den > 1e-12 else 0.0


def _player_skill_avg(player: dict[str, Any], keys: list[str] | None = None) -> float:
    sk = player.get("skills") or {}
    ks = keys or CORE_16_SKILL_KEYS
    vals = [_safe_float(sk.get(k), 10.0) for k in ks]
    return sum(vals) / len(vals) if vals else 10.0


def _player_potential_avg(player: dict[str, Any]) -> float:
    pot = (player.get("potential") or {}).get("m_Values") or []
    # In DB files, potential values may store 1 when unset unless > 1 or startingPotential is set
    vals = [_safe_float(v, 0.0) for v in pot if _safe_float(v, 0.0) > 1.0]
    if vals:
        return sum(vals) / len(vals)
    sk = _player_skill_avg(player, DEFAULT_SKILL_KEYS)
    return max(sk, _safe_float(player.get("startingPotential"), sk))


def _staff_skill_avg(staff: dict[str, Any]) -> float:
    sk = staff.get("skills") or {}
    vals = [_safe_float(sk.get(k), 10.0) for k in STAFF_SKILL_KEYS]
    return sum(vals) / len(vals) if vals else 10.0


def _tournament_linked_stages(tourn: dict[str, Any], all_stages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tid = _safe_int(tourn.get("id"))
    tpl = _safe_int(tourn.get("template"))
    out = [
        s for s in all_stages
        if (tpl and _safe_int(s.get("parentTemplate")) == tpl)
        or (tid and _safe_int(s.get("parentId")) == tid)
    ]
    return sorted(out, key=lambda s: (_safe_int(s.get("stage")), _safe_int(s.get("regionEligibility"))))


def _stage_count_rounds(stage: dict[str, Any]) -> int:
    """Exact replica of TournamentStage.CountRounds() from Assembly-CSharp.dll."""
    fmt = _safe_int(stage.get("formatType"), 0)
    parts = max(2, _safe_int(stage.get("numberOfParticipants"), 2))
    groups = max(1, _safe_int(stage.get("groups"), 1))
    per_group = max(2, parts // groups)

    if fmt == 1:  # League / Round-robin
        return max(1, per_group - 1)
    if fmt == 2:  # Swiss
        rw = _safe_int(stage.get("requiredWins"), 3)
        ml = _safe_int(stage.get("maxLosses"), 3)
        return max(1, rw + ml)
    # Single Bracket (0) or Double Bracket (3)
    rounds = 0
    cur = per_group
    while cur > 1:
        rounds += 1
        cur = max(1, cur // 2)
    if fmt == 3:
        rounds += 3
    return max(1, rounds)


def _csm_dow(d: dt.date) -> int:
    """CS Manager uses 1=Mon .. 7=Sun (matching Python isoweekday)."""
    return d.isoweekday()


def _advance_to_dow(start: dt.date, target_dow: int) -> dt.date:
    target = max(1, min(7, int(target_dow)))
    diff = (target - _csm_dow(start)) % 7
    return start + dt.timedelta(days=diff)


def _simulate_tournament_dates(
    tourn: dict[str, Any],
    stages: list[dict[str, Any]],
    ref_year: int = 2026,
    half: str = "spring",
) -> dict[str, Any]:
    """
    Simulate CS Manager's Tournament.GenerateAndSetDates() + TournamentStage.GetDatetimeForRound().
    half='spring' uses startMonthRange (1..6); half='fall' shifts by +6 months (7..12).
    """
    raw_m = max(1, min(12, _safe_int(tourn.get("startMonthRange"), 1)))
    month = raw_m if half == "spring" else (((raw_m - 1 + 6) % 12) + 1)
    raw_d = max(1, min(28 if month == 2 else 30 if month in (4, 6, 9, 11) else 31, _safe_int(tourn.get("startDayRange"), 1)))
    anchor = dt.date(ref_year, month, raw_d)

    sorted_stages = sorted(stages, key=lambda s: (_safe_int(s.get("stage"), 1), _safe_int(s.get("regionEligibility"), 3)))
    cursor_by_stage: dict[int, dt.date] = {}
    stage_windows: list[dict[str, Any]] = []
    errors: list[str] = []

    # Group by stage number (note: e.g. Major stage 1 can have 3 regional stages running in parallel!)
    stage_nums = sorted({_safe_int(s.get("stage"), 1) for s in sorted_stages})
    prev_end: dt.date | None = None

    for s_num in stage_nums:
        group_stages = [s for s in sorted_stages if _safe_int(s.get("stage"), 1) == s_num]
        stage_max_end: dt.date | None = None
        for idx_in_num, st in enumerate(group_stages):
            dows = sorted({int(x) for x in (st.get("daysOfWeekPlayed") or []) if 1 <= int(x) <= 7})
            if not dows:
                errors.append(f"Stage {s_num} has empty daysOfWeekPlayed (throws engine exception)")
                dows = [1, 2, 3]
            min_start = anchor if prev_end is None else (prev_end + dt.timedelta(days=1))
            st_start = _advance_to_dow(min_start, dows[0])
            rounds = _stage_count_rounds(st)
            k = len(dows)
            round_dates: list[dt.date] = []
            for r_idx in range(rounds):
                week_off = r_idx // k
                slot_idx = r_idx % k
                dow = dows[slot_idx]
                delta_dow = dow - _csm_dow(st_start)
                if delta_dow < 0:
                    delta_dow += 7
                r_date = st_start + dt.timedelta(days=week_off * 7 + delta_dow)
                round_dates.append(r_date)
            st_end = round_dates[-1] if round_dates else st_start
            if stage_max_end is None or st_end > stage_max_end:
                stage_max_end = st_end
            cursor_by_stage[s_num] = st_end

            stage_windows.append({
                "stageNum": s_num,
                "name": st.get("name") or f"Stage {s_num}",
                "nameLabel": gd.format_stage_name(st.get("name")),
                "formatType": _safe_int(st.get("formatType")),
                "formatName": gd.FORMAT_TYPES.get(_safe_int(st.get("formatType")), "Unknown"),
                "participants": _safe_int(st.get("numberOfParticipants")),
                "groups": _safe_int(st.get("groups"), 1),
                "mapsPerMatch": _safe_int(st.get("mapsPerMatch"), 3),
                "requiredWins": _safe_int(st.get("requiredWins"), 3),
                "maxLosses": _safe_int(st.get("maxLosses"), 2),
                "openSignup": bool(st.get("openSignup", False)),
                "venue": _safe_int(st.get("venue")),
                "venueName": gd.VENUES.get(_safe_int(st.get("venue")), "Online"),
                "region": _safe_int(st.get("regionEligibility"), 3),
                "regionName": gd.REGIONS.get(_safe_int(st.get("regionEligibility"), 3), "World"),
                "slot": _safe_int(st.get("matchSessionSlot"), 3),
                "slotLabel": gd.SESSION_SLOTS.get(_safe_int(st.get("matchSessionSlot"), 3), "Slot 3"),
                "daysOfWeek": dows,
                "rounds": rounds,
                "invitationDate": (st_start - dt.timedelta(days=5 + s_num)).isoformat(),
                "startDate": st_start.isoformat(),
                "endDate": st_end.isoformat(),
                "roundDates": [d.isoformat() for d in round_dates],
                "isLan": _safe_int(st.get("venue"), 0) != 0,
            })
        if stage_max_end is not None:
            prev_end = stage_max_end

    if stage_windows:
        all_starts = [w["startDate"] for w in stage_windows]
        all_ends = [w["endDate"] for w in stage_windows]
        lan_wins = [w for w in stage_windows if w["isLan"]]
        t_start = min(all_starts)
        t_end = max(all_ends)
        lan_start = min((w["startDate"] for w in lan_wins), default=None)
        lan_end = max((w["endDate"] for w in lan_wins), default=None)
    else:
        t_start = anchor.isoformat()
        t_end = anchor.isoformat()
        lan_start = None
        lan_end = None
        errors.append("Tournament has 0 linked stages")

    # Overall tournament region eligibility = union of stages (World if any stage is World or multiple regions)
    regions_set = {w["region"] for w in stage_windows}
    if not regions_set or 3 in regions_set or len(regions_set) > 1:
        eff_region = 3
    else:
        eff_region = next(iter(regions_set))

    tier_info = gd.classify_tournament_tier(_safe_int(tourn.get("reputation")))
    awards_info = gd.awards_for_reputation(_safe_int(tourn.get("reputation")))
    prize_total = sum(
        _safe_int(p.get("money"))
        for st in sorted_stages
        for p in (st.get("prizes") or [])
    )

    return {
        "template": _safe_int(tourn.get("template")),
        "id": _safe_int(tourn.get("id")),
        "name": tourn.get("name") or f"Tournament #{tourn.get('template')}",
        "reputation": _safe_int(tourn.get("reputation")),
        "tier": tier_info,
        "awards": awards_info,
        "outdated": bool(tourn.get("outdated", False)),
        "startMonthRange": raw_m,
        "startDayRange": raw_d,
        "anchorDate": anchor.isoformat(),
        "anchorDow": gd.DAYS_OF_WEEK.get(_csm_dow(anchor), "Mon"),
        "simMonth": month,
        "half": half,
        "startDate": t_start,
        "endDate": t_end,
        "durationDays": (dt.date.fromisoformat(t_end) - dt.date.fromisoformat(t_start)).days + 1,
        "hasLan": lan_start is not None,
        "lanStart": lan_start,
        "lanEnd": lan_end,
        "effectiveRegion": eff_region,
        "effectiveRegionName": gd.REGIONS.get(eff_region, "World"),
        "prizePool": prize_total,
        "stages": stage_windows,
        "errors": errors,
    }


def _dates_overlap(a0: str | None, a1: str | None, b0: str | None, b1: str | None) -> tuple[bool, int]:
    if not (a0 and a1 and b0 and b1):
        return False, 0
    s0, e0 = dt.date.fromisoformat(a0), dt.date.fromisoformat(a1)
    s1, e1 = dt.date.fromisoformat(b0), dt.date.fromisoformat(b1)
    lo = max(s0, s1)
    hi = min(e0, e1)
    if lo <= hi:
        return True, (hi - lo).days + 1
    return False, 0


def _regions_overlap(r1: int, r2: int) -> bool:
    return r1 == 3 or r2 == 3 or r1 == r2


class DatabaseWorkspace:
    """In-memory workspace managing Database, GameBalance, and Weapons packs."""

    def __init__(self) -> None:
        # Database pack state
        self.db_dir: str | None = None
        self.db_name: str | None = None
        self.db: dict[str, Any] = {}
        self.dirty_db: bool = False

        # GameBalance pack state
        self.balance_path: str | None = None
        self.balance_name: str | None = None
        self.balance_data: dict[str, Any] | None = None
        self.dirty_balance: bool = False

        # Weapons pack state
        self.weapons_path: str | None = None
        self.weapons_name: str | None = None
        self.weapons_data: dict[str, Any] | None = None
        self.dirty_weapons: bool = False

    # ------------------------------------------------------------------
    # Pack loading & saving
    # ------------------------------------------------------------------

    def load_database(self, folder: str) -> dict[str, Any]:
        p = Path(folder)
        if not p.exists() or not (p / "teams.json").exists():
            raise FileNotFoundError(f"Valid CS Manager database folder not found (missing teams.json): {folder}")

        self.db_dir = str(p)
        self.db_name = p.name
        self.db = {
            "teams": _read_json(p / "teams.json", {"teams": []}).get("teams", []),
            "players": _read_json(p / "players.json", {"players": []}).get("players", []),
            "playerContracts": _read_json(p / "playerContracts.json", {"playerContracts": []}).get("playerContracts", []),
            "playerRelationships": _read_json(p / "playerRelationships.json", {"playerRelationships": []}).get("playerRelationships", []),
            "staffers": _read_json(p / "staffers.json", {"staffers": []}).get("staffers", []),
            "staffContracts": _read_json(p / "staffContracts.json", {"staffContracts": []}).get("staffContracts", []),
            "sponsors": _read_json(p / "sponsors.json", {"sponsors": []}).get("sponsors", []),
            "tournaments": _read_json(p / "tournaments.json", {"tournaments": []}).get("tournaments", []),
            "tournamentStages": _read_json(p / "tournamentStages.json", {"tournamentStages": []}).get("tournamentStages", []),
            "workshop_manifest": _read_json(p / "workshop_manifest.json", {"databaseName": p.name}),
        }
        self.dirty_db = False
        return self.get_summary()

    def save_database(self, target_folder: str | None = None, create_backup: bool = True) -> dict[str, Any]:
        if not self.db_dir:
            raise ValueError("No database loaded.")
        dest = Path(target_folder or self.db_dir)
        dest.mkdir(parents=True, exist_ok=True)

        if create_backup and dest.exists() and (dest / "teams.json").exists():
            stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
            bkp = Path(__file__).resolve().parent / "backups" / "databases" / f"{dest.name}_{stamp}"
            bkp.mkdir(parents=True, exist_ok=True)
            for fname in DATABASE_JSON_FILES:
                src = dest / fname
                if src.exists():
                    shutil.copy2(src, bkp / fname)

        # Preserve logo assets if saving to a new directory
        if target_folder and Path(target_folder).resolve() != Path(self.db_dir).resolve():
            src_dir = Path(self.db_dir)
            for asset_dir in ["TeamLogos", "TournamentLogos", "SponsorLogos"]:
                s_sub = src_dir / asset_dir
                d_sub = dest / asset_dir
                if s_sub.exists() and not d_sub.exists():
                    shutil.copytree(s_sub, d_sub)

        manifest = dict(self.db.get("workshop_manifest") or {})
        manifest["databaseName"] = dest.name

        _write_json(dest / "teams.json", {"teams": self.db["teams"]})
        _write_json(dest / "players.json", {"players": self.db["players"]})
        _write_json(dest / "playerContracts.json", {"playerContracts": self.db["playerContracts"]})
        _write_json(dest / "playerRelationships.json", {"playerRelationships": self.db["playerRelationships"]})
        _write_json(dest / "staffers.json", {"staffers": self.db["staffers"]})
        _write_json(dest / "staffContracts.json", {"staffContracts": self.db["staffContracts"]})
        _write_json(dest / "sponsors.json", {"sponsors": self.db["sponsors"]})
        _write_json(dest / "tournaments.json", {"tournaments": self.db["tournaments"]})
        _write_json(dest / "tournamentStages.json", {"tournamentStages": self.db["tournamentStages"]})
        _write_json(dest / "workshop_manifest.json", manifest)

        self.db_dir = str(dest)
        self.db_name = dest.name
        self.dirty_db = False
        return {"ok": True, "path": str(dest), "name": dest.name}

    def clone_database(self, new_name: str) -> dict[str, Any]:
        if not self.db_dir:
            raise ValueError("No database loaded.")
        clean_name = "".join(c for c in new_name.strip() if c not in r'\/:*?"<>|')
        if not clean_name:
            raise ValueError("Invalid database name.")
        dest = Path(self.db_dir).parent / clean_name
        if dest.exists():
            raise ValueError(f"Database '{clean_name}' already exists.")
        res = self.save_database(str(dest), create_backup=False)
        return {"ok": True, **res, "summary": self.get_summary()}

    def load_game_balance(self, path_str: str) -> dict[str, Any]:
        p = Path(path_str)
        if p.is_dir():
            p = p / "gameBalance.json"
        if not p.exists():
            raise FileNotFoundError(f"gameBalance.json not found: {path_str}")
        self.balance_path = str(p)
        self.balance_name = p.parent.name
        self.balance_data = json.loads(p.read_text(encoding="utf-8"))
        self.dirty_balance = False
        return self.get_balance_and_analysis()

    def save_game_balance(self, new_pack_name: str | None = None) -> dict[str, Any]:
        if not self.balance_data or not self.balance_path:
            raise ValueError("No GameBalance pack loaded.")
        dest = Path(self.balance_path)
        if new_pack_name:
            clean = "".join(c for c in new_pack_name.strip() if c not in r'\/:*?"<>|')
            if not clean:
                raise ValueError("Invalid GameBalance pack name.")
            pack_dir = dest.parent.parent / clean
            pack_dir.mkdir(parents=True, exist_ok=True)
            _write_json(pack_dir / "workshop_manifest.json", {"databaseName": clean})
            dest = pack_dir / "gameBalance.json"
        elif dest.exists():
            stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
            bkp = Path(__file__).resolve().parent / "backups" / "balances"
            bkp.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dest, bkp / f"{dest.parent.name}_{stamp}_gameBalance.json")

        _write_json(dest, self.balance_data)
        self.balance_path = str(dest)
        self.balance_name = dest.parent.name
        self.dirty_balance = False
        return {"ok": True, "path": str(dest), "name": dest.parent.name}

    def load_weapons(self, path_str: str) -> dict[str, Any]:
        p = Path(path_str)
        if p.is_dir():
            p = p / "weapons.json"
        if not p.exists():
            raise FileNotFoundError(f"weapons.json not found: {path_str}")
        self.weapons_path = str(p)
        self.weapons_name = p.parent.name
        self.weapons_data = json.loads(p.read_text(encoding="utf-8"))
        self.dirty_weapons = False
        return self.get_weapons_and_analysis()

    def save_weapons(self, new_pack_name: str | None = None) -> dict[str, Any]:
        if not self.weapons_data or not self.weapons_path:
            raise ValueError("No Weapons pack loaded.")
        dest = Path(self.weapons_path)
        if new_pack_name:
            clean = "".join(c for c in new_pack_name.strip() if c not in r'\/:*?"<>|')
            if not clean:
                raise ValueError("Invalid Weapons pack name.")
            pack_dir = dest.parent.parent / clean
            if (dest.parent / "CustomWeaponSkins").exists() and not (pack_dir / "CustomWeaponSkins").exists():
                shutil.copytree(dest.parent / "CustomWeaponSkins", pack_dir / "CustomWeaponSkins")
            pack_dir.mkdir(parents=True, exist_ok=True)
            _write_json(pack_dir / "workshop_manifest.json", {"databaseName": clean})
            dest = pack_dir / "weapons.json"
        elif dest.exists():
            stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
            bkp = Path(__file__).resolve().parent / "backups" / "weapons"
            bkp.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dest, bkp / f"{dest.parent.name}_{stamp}_weapons.json")

        _write_json(dest, self.weapons_data)
        self.weapons_path = str(dest)
        self.weapons_name = dest.parent.name
        self.dirty_weapons = False
        return {"ok": True, "path": str(dest), "name": dest.parent.name}

    # ------------------------------------------------------------------
    # Summary & Helpers
    # ------------------------------------------------------------------

    def _contract_maps(self) -> tuple[dict[int, dict[str, Any]], dict[int, list[dict[str, Any]]], dict[int, dict[str, Any]], dict[int, list[dict[str, Any]]]]:
        p_by_player: dict[int, dict[str, Any]] = {}
        p_by_team: dict[int, list[dict[str, Any]]] = {}
        for c in self.db.get("playerContracts", []):
            pid = _safe_int(c.get("playerId"))
            tid = _safe_int(c.get("teamId"))
            if pid:
                p_by_player[pid] = c
            if tid:
                p_by_team.setdefault(tid, []).append(c)

        s_by_staff: dict[int, dict[str, Any]] = {}
        s_by_team: dict[int, list[dict[str, Any]]] = {}
        for c in self.db.get("staffContracts", []):
            sid = _safe_int(c.get("staffId"))
            tid = _safe_int(c.get("teamId"))
            if sid:
                s_by_staff[sid] = c
            if tid:
                s_by_team.setdefault(tid, []).append(c)
        return p_by_player, p_by_team, s_by_staff, s_by_team

    def _team_lookup(self) -> dict[int, dict[str, Any]]:
        return {_safe_int(t.get("id")): t for t in self.db.get("teams", []) if _safe_int(t.get("id"))}

    def _player_lookup(self) -> dict[int, dict[str, Any]]:
        return {_safe_int(p.get("id")): p for p in self.db.get("players", []) if _safe_int(p.get("id"))}

    def _staff_lookup(self) -> dict[int, dict[str, Any]]:
        return {_safe_int(s.get("id")): s for s in self.db.get("staffers", []) if _safe_int(s.get("id"))}

    def _next_id(self, rows: list[dict[str, Any]]) -> int:
        return max((_safe_int(r.get("id")) for r in rows), default=0) + 1

    def get_summary(self) -> dict[str, Any]:
        packs = list_all_packs()
        if not self.db_dir:
            return {
                "loaded": False,
                "packs": packs,
                "balanceLoaded": self.balance_data is not None,
                "balanceName": self.balance_name,
                "weaponsLoaded": self.weapons_data is not None,
                "weaponsName": self.weapons_name,
            }

        teams = self.db.get("teams", [])
        players = self.db.get("players", [])
        p_contracts = self.db.get("playerContracts", [])
        staffers = self.db.get("staffers", [])
        tournaments = self.db.get("tournaments", [])
        stages = self.db.get("tournamentStages", [])
        sponsors = self.db.get("sponsors", [])

        tier_counts = {"Major (T5)": 0, "S-Tier (T4)": 0, "A-Tier (T3)": 0, "B-Tier (T2)": 0, "C-Tier (T1)": 0}
        for t in tournaments:
            if t.get("outdated"):
                continue
            tier = gd.classify_tournament_tier(_safe_int(t.get("reputation")))
            if tier["engineTier"] == 5:
                tier_counts["Major (T5)"] += 1
            elif tier["engineTier"] == 4:
                tier_counts["S-Tier (T4)"] += 1
            elif tier["engineTier"] == 3:
                tier_counts["A-Tier (T3)"] += 1
            elif tier["engineTier"] == 2:
                tier_counts["B-Tier (T2)"] += 1
            else:
                tier_counts["C-Tier (T1)"] += 1

        validation = self.validate_database(auto_fix=False)
        sched = self.analyze_tournaments_schedule()

        return {
            "loaded": True,
            "dbDir": self.db_dir,
            "dbName": self.db_name,
            "dirtyDb": self.dirty_db,
            "dirtyBalance": self.dirty_balance,
            "dirtyWeapons": self.dirty_weapons,
            "balanceLoaded": self.balance_data is not None,
            "balanceName": self.balance_name,
            "weaponsLoaded": self.weapons_data is not None,
            "weaponsName": self.weapons_name,
            "packs": packs,
            "counts": {
                "teams": len(teams),
                "players": len(players),
                "freeAgents": max(0, len(players) - len({ _safe_int(c.get("playerId")) for c in p_contracts })),
                "playerContracts": len(p_contracts),
                "relationships": len(self.db.get("playerRelationships", [])),
                "staffers": len(staffers),
                "staffContracts": len(self.db.get("staffContracts", [])),
                "sponsors": len(sponsors),
                "tournaments": len(tournaments),
                "activeTournaments": sum(1 for t in tournaments if not t.get("outdated")),
                "stages": len(stages),
                "tournamentTiers": tier_counts,
            },
            "validationSummary": {
                "errorCount": validation["errorCount"],
                "warningCount": validation["warningCount"],
                "issueCount": validation["issueCount"],
            },
            "overlapSummary": sched["summary"],
        }

    # ------------------------------------------------------------------
    # Teams CRUD & Queries
    # ------------------------------------------------------------------

    def list_teams(self, search: str = "", nation: int | None = None, region: int | None = None) -> list[dict[str, Any]]:
        _, p_by_team, _, s_by_team = self._contract_maps()
        p_lookup = self._player_lookup()
        q = search.strip().lower()
        rows = []
        for t in self.db.get("teams", []):
            tid = _safe_int(t.get("id"))
            nat = _safe_int(t.get("nation"))
            reg = gd.NATION_REGIONS.get(nat, 0)
            if nation is not None and nat != nation:
                continue
            if region is not None and reg != region:
                continue
            name = t.get("name") or ""
            if q and q not in name.lower() and q not in str(tid) and q not in gd.NATIONS.get(nat, "").lower():
                continue

            t_pcs = p_by_team.get(tid, [])
            starters = []
            bench = []
            payroll = 0
            for c in t_pcs:
                payroll += _safe_int(c.get("salaryYear"))
                pl = p_lookup.get(_safe_int(c.get("playerId")))
                if not pl:
                    continue
                if c.get("benched"):
                    bench.append(pl)
                else:
                    starters.append(pl)
            active = starters[:5] if len(starters) >= 5 else starters
            avg_sk = _avg([_player_skill_avg(pl) for pl in active]) if active else 0.0
            pts = sum(_safe_float(rp.get("currentPoints")) for rp in (t.get("rankingPoints") or []))
            rows.append({
                "id": tid,
                "name": name,
                "nation": nat,
                "nationName": gd.NATIONS.get(nat, "Unknown"),
                "regionName": gd.REGIONS.get(reg, "EU"),
                "reputation": _safe_int(t.get("reputation")),
                "professionalStatus": _safe_int(t.get("professionalStatus")),
                "professionalStatusName": gd.PROFESSIONAL_STATUS.get(_safe_int(t.get("professionalStatus")), "Pro"),
                "hiringBias": _safe_int((t.get("owner") or {}).get("hiringBias"), 7),
                "hiringBiasName": gd.HIRING_BIAS.get(_safe_int((t.get("owner") or {}).get("hiringBias"), 7), "International"),
                "rosterCount": len(starters),
                "benchCount": len(bench),
                "staffCount": len(s_by_team.get(tid, [])),
                "avgSkill": round(avg_sk, 2),
                "payroll": payroll,
                "rankingPoints": round(pts),
                "logo": t.get("logo") or "",
            })
        rows.sort(key=lambda r: (-r["rankingPoints"], -r["avgSkill"], r["name"].lower()))
        return rows

    def get_team(self, team_id: int) -> dict[str, Any]:
        team = self._team_lookup().get(team_id)
        if not team:
            raise ValueError(f"Team {team_id} not found.")
        _, p_by_team, _, s_by_team = self._contract_maps()
        p_lookup = self._player_lookup()
        s_lookup = self._staff_lookup()

        players = []
        for c in p_by_team.get(team_id, []):
            pl = p_lookup.get(_safe_int(c.get("playerId")))
            if not pl:
                continue
            players.append({
                "id": _safe_int(pl["id"]),
                "name": pl.get("name"),
                "age": _safe_int(pl.get("age")),
                "nation": _safe_int(pl.get("nation")),
                "nationName": gd.NATIONS.get(_safe_int(pl.get("nation")), "Unknown"),
                "avgSkill": round(_player_skill_avg(pl), 2),
                "potentialAvg": round(_player_potential_avg(pl), 2),
                "benched": bool(c.get("benched", False)),
                "igl": _safe_int(c.get("igl"), 2),
                "sniper": _safe_int(c.get("sniper"), 2),
                "status": _safe_int(c.get("status"), 1),
                "salaryYear": _safe_int(c.get("salaryYear")),
                "endYear": _safe_int((c.get("endDate") or {}).get("year"), 2028),
            })
        players.sort(key=lambda r: (r["benched"], -r["avgSkill"]))

        staff = []
        for c in s_by_team.get(team_id, []):
            st = s_lookup.get(_safe_int(c.get("staffId")))
            if not st:
                continue
            staff.append({
                "id": _safe_int(st["id"]),
                "name": st.get("name"),
                "age": _safe_int(st.get("age")),
                "nationName": gd.NATIONS.get(_safe_int(st.get("nation")), "Unknown"),
                "role": _safe_int(c.get("role")),
                "roleName": gd.STAFF_ROLES.get(_safe_int(c.get("role")), "Staff"),
                "avgSkill": round(_staff_skill_avg(st), 2),
                "salaryYear": _safe_int(c.get("salaryYear")),
            })
        return {"team": copy.deepcopy(team), "players": players, "staff": staff}

    def update_team(self, team_id: int, patch: dict[str, Any]) -> dict[str, Any]:
        team = self._team_lookup().get(team_id)
        if not team:
            raise ValueError(f"Team {team_id} not found.")
        for k in ["name", "logo"]:
            if k in patch:
                team[k] = str(patch[k])
        for k in ["nation", "reputation", "professionalStatus", "financialStrength",
                  "coffeeMachine", "cable", "ventilation", "recreation", "branding", "academy", "academyFocus"]:
            if k in patch:
                team[k] = _safe_int(patch[k], _safe_int(team.get(k)))
        if "owner" in patch and isinstance(patch["owner"], dict):
            owner = team.setdefault("owner", {"name": "Owner", "hiringBias": 7, "dialogCountdown": 0})
            if "name" in patch["owner"]:
                owner["name"] = str(patch["owner"]["name"])
            if "hiringBias" in patch["owner"]:
                owner["hiringBias"] = _safe_int(patch["owner"]["hiringBias"], 7)
        if "teamFinances" in patch and isinstance(patch["teamFinances"], dict):
            tf = team.setdefault("teamFinances", {})
            for fk in ["currentBalance", "ownerContribution", "merchandiseContribution", "ownerContributionMultipler"]:
                if fk in patch["teamFinances"]:
                    tf[fk] = _safe_float(patch["teamFinances"][fk]) if "Contribution" in fk or "Multipler" in fk else _safe_int(patch["teamFinances"][fk])
        if "mainLanguage" in patch:
            team.setdefault("teamCohesion", {})["mainLanguage"] = _safe_int(patch["mainLanguage"])
        if "rankingPointsTotal" in patch:
            pts = max(0, _safe_int(patch["rankingPointsTotal"]))
            if team.get("rankingPoints"):
                team["rankingPoints"][0]["originalPoints"] = pts
                team["rankingPoints"][0]["currentPoints"] = pts
            else:
                team["rankingPoints"] = [{
                    "type": 3, "tournamentTemplate": 0, "opponentTeamId": 0,
                    "prizeMoney": 0, "tournamentPlacement": 0, "venue": 0,
                    "dateGranted": {"hour": 0, "day": 1, "month": 1, "year": 2026},
                    "originalPoints": pts, "currentPoints": pts, "currentRelevance": 1.0,
                    "startingPoints": True, "win": False,
                }]
        self.dirty_db = True
        return self.get_team(team_id)

    def create_team(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.db_dir:
            raise ValueError("No database loaded.")
        teams = self.db["teams"]
        new_id = self._next_id(teams)
        name = str(payload.get("name") or f"Custom Team {new_id}").strip()
        nat = _safe_int(payload.get("nation"), 102)
        rep = max(1, min(20, _safe_int(payload.get("reputation"), 10)))
        pts = max(0, _safe_int(payload.get("rankingPointsTotal"), 500))
        lang = _safe_int(payload.get("mainLanguage"), 13)
        hiring_bias = _safe_int(payload.get("hiringBias"), 7)
        prof_status = _safe_int(payload.get("professionalStatus"), 2)

        sample_portrait = (teams[0].get("owner") or {}).get("portrait") if teams else None
        portrait = copy.deepcopy(sample_portrait) if isinstance(sample_portrait, dict) else {
            "face": 3, "nose": 5, "mouth": 4, "mouthColor": 2, "eyes": 3,
            "eyeballsColor": 2, "eyebrows": 3, "eyebrowsColor": 2, "hair": 12,
            "hairColor": 2, "beard": 0, "beardColor": 2, "accessory": 0,
            "accessoryColor": 0, "wrinkes": 0, "skinColor": 2, "neck": 1,
        }

        new_team = {
            "id": new_id,
            "name": name,
            "nation": nat,
            "reputation": rep,
            "owner": {
                "name": str(payload.get("ownerName") or "Owner"),
                "portrait": portrait,
                "hiringBias": hiring_bias,
                "dialogCountdown": 0,
            },
            "generalTactics": [],
            "mapTactics": [],
            "trainingScheme": {"trainingWeek": [], "mapsBeingPracticed": [], "trainingIntensity": 0, "focus": 0},
            "professionalStatus": prof_status,
            "teamFinances": {
                "currentBalance": _safe_int(payload.get("currentBalance"), 500000),
                "ownerContribution": _safe_float(payload.get("ownerContribution"), 10.0),
                "merchandiseContribution": _safe_float(payload.get("merchandiseContribution"), 10.0),
                "ownerContributionMultipler": 1.0,
                "travelCosts": 0, "participationFees": 0, "prizeMoney": 0, "sponsorBonus": 0,
                "buyoutAndSignOnExpenses": 0, "facilitiesUpgradeExpenses": 0, "buyoutIncome": 0,
            },
            "financialStrength": _safe_int(payload.get("financialStrength"), 0),
            "rankingPoints": [{
                "type": 3, "tournamentTemplate": 0, "opponentTeamId": 0,
                "prizeMoney": 0, "tournamentPlacement": 0, "venue": 0,
                "dateGranted": {"hour": 0, "day": 1, "month": 1, "year": 2026},
                "originalPoints": pts, "currentPoints": pts, "currentRelevance": 1.0,
                "startingPoints": True, "win": False,
            }],
            "teamCohesion": {
                "cohesionFromTraining": 0.0, "cohesionFromBurnout": 0.0, "cohesionFromMentality": 0.0,
                "cohesionFromLanguage": 0.0, "cohesionFromLeadership": 0.0, "cohesionFromRelationships": 0.0,
                "cohesionFromDilemmas": 0.0, "cohesionFromIgl": 0.0, "mainLanguage": lang,
            },
            "logo": str(payload.get("logo") or name),
            "colorData": {"r": 0.15, "g": 0.45, "b": 0.85},
            "jobSecurity": {
                "securityFromLeague": 0.0, "securityFromChampionship": 0.0, "securityFromRanking": 0.0,
                "securityFromBudget": 0.0, "securityFromLongevity": 0.0, "securityFromSquad": 0.0,
                "securityFromPreviousSeason": 0.0,
            },
            "reputationProgress": 0.0,
            "travellingDays": 0,
            "sponsors": [],
            "coffeeMachine": _safe_int(payload.get("coffeeMachine"), 2),
            "cable": _safe_int(payload.get("cable"), 2),
            "ventilation": _safe_int(payload.get("ventilation"), 2),
            "recreation": _safe_int(payload.get("recreation"), 2),
            "branding": _safe_int(payload.get("branding"), 3),
            "academy": _safe_int(payload.get("academy"), 1),
            "academyFocus": _safe_int(payload.get("academyFocus"), 0),
            "academyPlayers": [], "facilityProgresses": [], "personInterests": [],
            "playerDilemmas": [], "trainingReport": [], "trophies": [],
            "tournamentTrackers": [], "rankingHistory": [], "mapStats": [],
            "recentSigningsScore": 0.0, "recentBuyoutMoneySpent": 0,
            "seasonStartPosition": 0, "seasonStartReputation": rep, "playbooks": [],
        }
        teams.append(new_team)
        self.dirty_db = True
        return self.get_team(new_id)

    def delete_team(self, team_id: int) -> dict[str, Any]:
        before = len(self.db["teams"])
        self.db["teams"] = [t for t in self.db["teams"] if _safe_int(t.get("id")) != team_id]
        if len(self.db["teams"]) == before:
            raise ValueError(f"Team {team_id} not found.")
        self.db["playerContracts"] = [c for c in self.db["playerContracts"] if _safe_int(c.get("teamId")) != team_id]
        self.db["staffContracts"] = [c for c in self.db["staffContracts"] if _safe_int(c.get("teamId")) != team_id]
        self.dirty_db = True
        return {"ok": True, "deletedTeamId": team_id}

    # ------------------------------------------------------------------
    # Players & Contracts CRUD
    # ------------------------------------------------------------------

    def list_players(
        self,
        search: str = "",
        team_id: int | None = None,
        free_only: bool = False,
        role: str = "",
        limit: int = 300,
    ) -> list[dict[str, Any]]:
        p_by_player, _, _, _ = self._contract_maps()
        t_lookup = self._team_lookup()
        q = search.strip().lower()
        rows = []
        for p in self.db.get("players", []):
            pid = _safe_int(p.get("id"))
            c = p_by_player.get(pid)
            tid = _safe_int(c.get("teamId")) if c else 0
            if free_only and tid != 0:
                continue
            if team_id is not None and tid != team_id:
                continue
            if role == "igl" and (not c or _safe_int(c.get("igl"), 2) == 2):
                continue
            if role == "awp" and (not c or _safe_int(c.get("sniper"), 2) == 2):
                continue

            team_name = (t_lookup.get(tid) or {}).get("name") or ("Free Agent" if tid == 0 else f"Team #{tid}")
            nat = _safe_int(p.get("nation"))
            if q and q not in (p.get("name") or "").lower() and q not in team_name.lower() and q not in str(pid):
                continue
            rows.append({
                "id": pid,
                "name": p.get("name"),
                "age": _safe_int(p.get("age")),
                "nation": nat,
                "nationName": gd.NATIONS.get(nat, "Unknown"),
                "reputation": _safe_int(p.get("reputation")),
                "teamId": tid,
                "teamName": team_name,
                "benched": bool(c.get("benched")) if c else False,
                "igl": _safe_int(c.get("igl"), 2) if c else 2,
                "sniper": _safe_int(c.get("sniper"), 2) if c else 2,
                "salaryYear": _safe_int(c.get("salaryYear")) if c else 0,
                "avgSkill": round(_player_skill_avg(p), 2),
                "potentialAvg": round(_player_potential_avg(p), 2),
                "useStartingPotential": bool(p.get("useStartingPotential", False)),
                "startingPotential": _safe_int(p.get("startingPotential"), 0),
                "snipersSkill": round(_safe_float((p.get("skills") or {}).get("snipers")), 1),
                "leadershipSkill": round(_safe_float((p.get("skills") or {}).get("leadership")), 1),
            })
        rows.sort(key=lambda r: (-r["avgSkill"], r["age"], (r["name"] or "").lower()))
        return rows[:limit]

    def get_player(self, player_id: int) -> dict[str, Any]:
        p_lookup = self._player_lookup()
        pl = p_lookup.get(player_id)
        if not pl:
            raise ValueError(f"Player {player_id} not found.")
        p_by_player, _, _, _ = self._contract_maps()
        t_lookup = self._team_lookup()
        c = p_by_player.get(player_id)
        rels = []
        for r in self.db.get("playerRelationships", []):
            p1 = _safe_int(r.get("player1Id"))
            p2 = _safe_int(r.get("player2Id"))
            if p1 != player_id and p2 != player_id:
                continue
            other_id = p2 if p1 == player_id else p1
            other = p_lookup.get(other_id)
            oc = p_by_player.get(other_id)
            otid = _safe_int(oc.get("teamId")) if oc else 0
            otype = _safe_int(r.get("type"), 1)
            rels.append({
                "player1Id": p1,
                "player2Id": p2,
                "otherPlayerId": other_id,
                "otherPlayerName": other.get("name") if other else f"Missing Player #{other_id}",
                "otherExists": other is not None,
                "otherTeamName": (t_lookup.get(otid) or {}).get("name") or ("Free Agent" if other else "N/A"),
                "otherAvgSkill": round(_player_skill_avg(other), 2) if other else 0.0,
                "type": otype,
                "typeLabel": gd.RELATIONSHIP_TYPES.get(otype, f"Type {otype}"),
                "duration": _safe_int(r.get("duration"), 0),
                "player1Resolved": bool(r.get("player1Resolved", False)),
                "player2Resolved": bool(r.get("player2Resolved", False)),
            })
        rels.sort(key=lambda item: (item["type"], (item["otherPlayerName"] or "").lower()))
        return {
            "player": copy.deepcopy(pl),
            "contract": copy.deepcopy(c) if c else None,
            "relationships": rels,
        }

    def update_player(self, player_id: int, patch: dict[str, Any]) -> dict[str, Any]:
        pl = self._player_lookup().get(player_id)
        if not pl:
            raise ValueError(f"Player {player_id} not found.")
        if "name" in patch:
            pl["name"] = str(patch["name"])
        for k in ["age", "nation", "reputation", "preferredMentality", "longevity", "useStartingPotential", "startingPotential"]:
            if k in patch:
                if k == "useStartingPotential":
                    pl[k] = bool(patch[k])
                elif k == "startingPotential":
                    raw_sp = _safe_int(patch[k], _safe_int(pl.get(k)))
                    pl[k] = 0 if (raw_sp <= 0 and not pl.get("useStartingPotential")) else max(50, min(275, raw_sp))
                else:
                    pl[k] = _safe_int(patch[k], _safe_int(pl.get(k)))
        for bkey in ["academyPlayer", "temporaryStandIn", "dontReplaceOnRetire", "setForRetirement"]:
            if bkey in patch:
                pl[bkey] = bool(patch[bkey])
        if "skills" in patch and isinstance(patch["skills"], dict):
            sk = pl.setdefault("skills", {})
            for k, v in patch["skills"].items():
                if k in DEFAULT_SKILL_KEYS:
                    sk[k] = max(1.0, min(20.0, _safe_float(v, 10.0)))
        if "potential" in patch and isinstance(patch["potential"], dict):
            pot = pl.setdefault("potential", {"m_Keys": list(range(1, 19)), "m_Values": [1] * 18})
            keys = pot.setdefault("m_Keys", list(range(1, 19)))
            vals = pot.setdefault("m_Values", [1] * 18)
            for idx, skill_def in enumerate(gd.PLAYER_SKILLS):
                s_key = skill_def["key"]
                s_id = skill_def["id"]
                if s_key in patch["potential"]:
                    if s_id not in keys:
                        keys.append(s_id)
                        vals.append(1)
                    pos = keys.index(s_id)
                    while len(vals) <= pos:
                        vals.append(1)
                    vals[pos] = max(1, min(20, _safe_int(patch["potential"][s_key], 1)))
        if "personality" in patch and isinstance(patch["personality"], dict):
            pers = pl.setdefault("personality", {})
            for ax in gd.PERSONALITY_AXES:
                k = ax["key"]
                if k in patch["personality"]:
                    pers[k] = max(1, min(20, _safe_int(patch["personality"][k], 10)))
        if "mapPositionAttributes" in patch and isinstance(patch["mapPositionAttributes"], list):
            by_pos = {
                _safe_int(m.get("positionType")): m
                for m in patch["mapPositionAttributes"]
                if isinstance(m, dict) and 0 <= _safe_int(m.get("positionType"), -1) <= 8
            }
            existing_pos = {
                _safe_int(m.get("positionType")): m
                for m in (pl.get("mapPositionAttributes") or [])
                if isinstance(m, dict)
            }
            pl["mapPositionAttributes"] = [
                {
                    "positionType": pos_id,
                    "roleComfort": max(1, min(10, _safe_int((by_pos.get(pos_id) or existing_pos.get(pos_id) or {}).get("roleComfort"), 5))),
                    "progress": max(0.0, min(100.0, _safe_float((by_pos.get(pos_id) or existing_pos.get(pos_id) or {}).get("progress"), 0.0))),
                }
                for pos_id in range(9)
            ]
        if "mapOpinions" in patch and isinstance(patch["mapOpinions"], list):
            cleaned_ops: list[dict[str, Any]] = []
            seen_maps: set[int] = set()
            for item in patch["mapOpinions"]:
                if not isinstance(item, dict):
                    continue
                mid = _safe_int(item.get("mapId"))
                if mid not in gd.MAP_NAMES or mid in seen_maps:
                    continue
                seen_maps.add(mid)
                cleaned_ops.append({"mapId": mid, "like": bool(item.get("like", True))})
            cleaned_ops.sort(key=lambda m: m["mapId"])
            pl["mapOpinions"] = cleaned_ops
        if "portrait" in patch and isinstance(patch["portrait"], dict):
            pt = pl.setdefault("portrait", {})
            for pf in gd.PORTRAIT_FIELDS:
                k = pf["key"]
                if k in patch["portrait"]:
                    pt[k] = max(pf["min"], min(pf["max"], _safe_int(patch["portrait"][k], pf["min"])))
        if "languagesSpoken" in patch and isinstance(patch["languagesSpoken"], list):
            seen_langs: set[int] = set()
            langs_out = []
            for l in patch["languagesSpoken"]:
                lid = _safe_int(l.get("languageId"))
                if lid <= 0 or lid in seen_langs:
                    continue
                seen_langs.add(lid)
                langs_out.append({
                    "languageId": lid,
                    "languageSkill": max(1, min(20, _safe_int(l.get("languageSkill"), 20))),
                    "limit": max(0, min(20, _safe_int(l.get("limit"), 20))),
                    "progress": _safe_float(l.get("progress"), 0.0),
                })
            pl["languagesSpoken"] = langs_out
        for ckey in ["monthsSinceNewContract", "monthsBenchedOrWithoutContract"]:
            if ckey in patch:
                pl[ckey] = max(0, _safe_int(patch[ckey], _safe_int(pl.get(ckey))))
        for fkey in ["reputationProgress", "skillOffset"]:
            if fkey in patch:
                pl[fkey] = _safe_float(patch[fkey], _safe_float(pl.get(fkey)))
        if "playerAwards" in patch and isinstance(patch["playerAwards"], list):
            awards_out = []
            for aw in patch["playerAwards"]:
                if not isinstance(aw, dict):
                    continue
                atype = max(0, min(3, _safe_int(aw.get("type"), 0)))
                awards_out.append({
                    "type": atype,
                    "tournamentTemplate": _safe_int(aw.get("tournamentTemplate"), -1),
                    "year": _safe_int(aw.get("year"), 2025),
                    "month": max(0, min(12, _safe_int(aw.get("month"), 0))),
                    "teamId": max(0, _safe_int(aw.get("teamId"), 0)),
                    "top20Placement": max(0, min(20, _safe_int(aw.get("top20Placement"), 0))) if atype == 3 else 0,
                })
            pl["playerAwards"] = awards_out
        if "contract" in patch:
            self._apply_player_contract(player_id, patch["contract"])
        self.dirty_db = True
        return self.get_player(player_id)

    def save_player_relationship(
        self, player1_id: int, player2_id: int, rel_type: int = 1, duration: int = 0
    ) -> dict[str, Any]:
        if player1_id == player2_id:
            raise ValueError("A player cannot have a relationship with themselves.")
        p_lookup = self._player_lookup()
        if player1_id not in p_lookup or player2_id not in p_lookup:
            raise ValueError(f"Both players must exist in the database (#{player1_id}, #{player2_id}).")
        rtype = max(0, min(4, _safe_int(rel_type, 1)))
        dur = max(0, _safe_int(duration, 0))
        rels = self.db.setdefault("playerRelationships", [])
        existing = next(
            (
                r for r in rels
                if {_safe_int(r.get("player1Id")), _safe_int(r.get("player2Id"))} == {player1_id, player2_id}
            ),
            None,
        )
        if existing:
            existing["type"] = rtype
            existing["duration"] = dur
        else:
            rels.append({
                "player1Id": player1_id,
                "player2Id": player2_id,
                "type": rtype,
                "duration": dur,
                "player1Resolved": False,
                "player2Resolved": False,
            })
        self.dirty_db = True
        return self.get_player(player1_id)

    def delete_player_relationship(self, player1_id: int, player2_id: int) -> dict[str, Any]:
        rels = self.db.get("playerRelationships", [])
        before = len(rels)
        self.db["playerRelationships"] = [
            r for r in rels
            if {_safe_int(r.get("player1Id")), _safe_int(r.get("player2Id"))} != {player1_id, player2_id}
        ]
        if len(self.db["playerRelationships"]) == before:
            raise ValueError("Relationship not found.")
        self.dirty_db = True
        return self.get_player(player1_id)

    def _apply_player_contract(self, player_id: int, cpatch: dict[str, Any] | None) -> None:
        contracts = self.db["playerContracts"]
        if cpatch is None or _safe_int(cpatch.get("teamId")) <= 0:
            self.db["playerContracts"] = [c for c in contracts if _safe_int(c.get("playerId")) != player_id]
            return
        team_id = _safe_int(cpatch["teamId"])
        existing = next((c for c in contracts if _safe_int(c.get("playerId")) == player_id), None)
        if not existing:
            existing = {
                "salaryYear": 120000,
                "endDate": {"hour": 0, "day": 1, "month": 7, "year": 2028},
                "teamId": team_id,
                "playerId": player_id,
                "status": 1,
                "sniper": 2,
                "igl": 2,
                "benched": False,
                "signingOnFee": 0,
                "transferStatus": 0,
                "askingPrice": 0,
                "contractType": 0,
            }
            contracts.append(existing)
        existing["teamId"] = team_id
        for k in ["salaryYear", "status", "sniper", "igl", "transferStatus", "askingPrice", "contractType"]:
            if k in cpatch:
                existing[k] = _safe_int(cpatch[k], existing[k])
        if "benched" in cpatch:
            existing["benched"] = bool(cpatch["benched"])
        if "endYear" in cpatch:
            existing.setdefault("endDate", {"hour": 0, "day": 1, "month": 7, "year": 2028})["year"] = max(2026, _safe_int(cpatch["endYear"], 2028))

    def create_player(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.db_dir:
            raise ValueError("No database loaded.")
        players = self.db["players"]
        new_id = self._next_id(players)
        preset = str(payload.get("preset") or "rifler").lower()
        base = max(6.0, min(19.0, _safe_float(payload.get("baseSkill"), 14.0)))
        pot_target = max(int(round(base)), min(20, _safe_int(payload.get("potentialTarget"), min(20, int(round(base)) + 2))))

        skills = {k: round(base, 1) for k in DEFAULT_SKILL_KEYS}
        if preset == "awper":
            skills.update({"snipers": min(20.0, base + 3.0), "flicks": min(20.0, base + 2.0), "reactions": min(20.0, base + 1.5), "rifles": max(5.0, base - 2.0)})
        elif preset == "igl":
            skills.update({"leadership": min(20.0, base + 3.5), "decisions": min(20.0, base + 2.0), "overview": min(20.0, base + 2.0), "utility": min(20.0, base + 1.5)})
        elif preset == "entry":
            skills.update({"aggression": min(20.0, base + 2.5), "reactions": min(20.0, base + 2.0), "crosshairPlacement": min(20.0, base + 1.5), "movement": min(20.0, base + 1.5)})
        elif preset == "support":
            skills.update({"utility": min(20.0, base + 3.0), "teamwork": min(20.0, base + 2.5), "composure": min(20.0, base + 1.5)})

        pot_keys = [s["id"] for s in gd.PLAYER_SKILLS]
        pot_vals = [max(1, min(20, max(int(round(skills[s["key"]])), pot_target))) for s in gd.PLAYER_SKILLS]
        lang_id = _safe_int(payload.get("languageId"), 13)

        use_custom_pot = bool(payload.get("useStartingPotential", False))
        custom_pot_val = _safe_int(payload.get("startingPotential"), 0)
        if use_custom_pot:
            custom_pot_val = max(50, min(275, custom_pot_val if custom_pot_val >= 50 else min(275, int(round(pot_target * 13.75)))))
        else:
            custom_pot_val = max(50, min(275, custom_pot_val)) if custom_pot_val > 0 else 0

        new_player = {
            "id": new_id,
            "name": str(payload.get("name") or f"Player{new_id}").strip(),
            "age": max(15, min(42, _safe_int(payload.get("age"), 20))),
            "nation": _safe_int(payload.get("nation"), 102),
            "reputation": max(1, min(20, _safe_int(payload.get("reputation"), 10))),
            "portrait": {
                "face": 3, "nose": 6, "mouth": 5, "mouthColor": 3, "eyes": 2, "eyeballsColor": 2,
                "eyebrows": 3, "eyebrowsColor": 2, "hair": 20, "hairColor": 2, "beard": 0, "beardColor": 2,
                "accessory": 0, "accessoryColor": 0, "wrinkes": 0, "skinColor": 2, "neck": 1,
            },
            "preferredMentality": _safe_int(payload.get("preferredMentality"), 1),
            "languagesSpoken": [{"languageId": lang_id, "languageSkill": 20, "limit": 20, "progress": 0.0}],
            "setForRetirement": False,
            "monthsBenchedOrWithoutContract": 0,
            "monthsSinceNewContract": 6,
            "reputationProgress": 0.0,
            "potential": {"m_Keys": pot_keys, "m_Values": pot_vals},
            "playerAwards": [],
            "skills": skills,
            "mapPositionAttributes": [{"positionType": i, "roleComfort": 7, "progress": 0.0} for i in range(9)],
            "mapOpinions": [{"mapId": mid, "like": True} for mid in range(1, 9)],
            "mood": {"base": 0.0, "happinessFromPlaying": 0.0, "happinessFromResults": 0.0, "happinessFromTeamStatus": 0.0, "happinessFromTeamTraining": 0.0, "happinessFromCoaching": 0.0, "happinessFromClubAtmosphere": 0.0, "happinessFromRecentWins": 0.0, "happinessFromTournamentOutcome": 0.0},
            "personality": {
                "quietPassion": 10, "kindMean": 8, "loyalMercenary": 8, "contentAmbition": 14,
                "stressproneResillient": 14, "desireToIgl": 18 if preset == "igl" else 5,
                "desireToAwp": 18 if preset == "awper" else 4,
            },
            "burnout": 0.0, "longevity": 10, "dialogCooldown": 0, "preliminaryDialogCooldown": 0,
            "temporaryStandIn": False, "dontReplaceOnRetire": False, "academyPlayer": False,
            "skillOffset": 0.0, "dialogStage": 0, "dialogConsideration": 0, "dialogKey": "",
            "practiceRatings": [], "useStartingPotential": use_custom_pot, "startingPotential": custom_pot_val,
        }
        players.append(new_player)
        if _safe_int(payload.get("teamId")) > 0:
            self._apply_player_contract(new_id, {
                "teamId": _safe_int(payload["teamId"]),
                "salaryYear": _safe_int(payload.get("salaryYear"), 180000),
                "status": _safe_int(payload.get("status"), 1),
                "igl": 0 if preset == "igl" else 2,
                "sniper": 0 if preset == "awper" else 2,
                "benched": bool(payload.get("benched", False)),
                "endYear": _safe_int(payload.get("endYear"), 2028),
            })
        self.dirty_db = True
        return self.get_player(new_id)

    def delete_player(self, player_id: int) -> dict[str, Any]:
        before = len(self.db["players"])
        self.db["players"] = [p for p in self.db["players"] if _safe_int(p.get("id")) != player_id]
        if len(self.db["players"]) == before:
            raise ValueError(f"Player {player_id} not found.")
        self.db["playerContracts"] = [c for c in self.db["playerContracts"] if _safe_int(c.get("playerId")) != player_id]
        self.db["playerRelationships"] = [
            r for r in self.db.get("playerRelationships", [])
            if _safe_int(r.get("player1Id")) != player_id and _safe_int(r.get("player2Id")) != player_id
        ]
        self.dirty_db = True
        return {"ok": True, "deletedPlayerId": player_id}

    # ------------------------------------------------------------------
    # Staff & Sponsors CRUD
    # ------------------------------------------------------------------

    def list_staff(self, search: str = "", limit: int = 250) -> list[dict[str, Any]]:
        _, _, s_by_staff, _ = self._contract_maps()
        t_lookup = self._team_lookup()
        q = search.strip().lower()
        rows = []
        for s in self.db.get("staffers", []):
            sid = _safe_int(s.get("id"))
            c = s_by_staff.get(sid)
            tid = _safe_int(c.get("teamId")) if c else 0
            team_name = (t_lookup.get(tid) or {}).get("name") or "Free Agent"
            nat = _safe_int(s.get("nation"))
            role_id = _safe_int(c.get("role")) if c else -1
            if q and q not in (s.get("name") or "").lower() and q not in team_name.lower():
                continue
            rows.append({
                "id": sid,
                "name": s.get("name"),
                "age": _safe_int(s.get("age")),
                "nation": nat,
                "nationName": gd.NATIONS.get(nat, "Unknown"),
                "teamId": tid,
                "teamName": team_name,
                "role": role_id,
                "roleName": gd.STAFF_ROLES.get(role_id, "Unemployed" if role_id < 0 else "Staff"),
                "avgSkill": round(_staff_skill_avg(s), 2),
                "salaryYear": _safe_int(c.get("salaryYear")) if c else 0,
            })
        rows.sort(key=lambda r: (-r["avgSkill"], (r["name"] or "").lower()))
        return rows[:limit]

    def get_staff(self, staff_id: int) -> dict[str, Any]:
        st = self._staff_lookup().get(staff_id)
        if not st:
            raise ValueError(f"Staff {staff_id} not found.")
        _, _, s_by_staff, _ = self._contract_maps()
        return {"staff": copy.deepcopy(st), "contract": copy.deepcopy(s_by_staff.get(staff_id))}

    def update_staff(self, staff_id: int, patch: dict[str, Any]) -> dict[str, Any]:
        st = self._staff_lookup().get(staff_id)
        if not st:
            raise ValueError(f"Staff {staff_id} not found.")
        if "name" in patch:
            st["name"] = str(patch["name"])
        for k in ["age", "nation", "reputation", "preferredMentality", "retirementConsiderationAge", "monthsSinceNewContract", "monthsBenchedOrWithoutContract"]:
            if k in patch:
                val = _safe_int(patch[k], _safe_int(st.get(k)))
                if k in ("monthsSinceNewContract", "monthsBenchedOrWithoutContract"):
                    val = max(0, val)
                elif k == "retirementConsiderationAge":
                    val = max(35, min(80, val))
                st[k] = val
        if "setForRetirement" in patch:
            st["setForRetirement"] = bool(patch["setForRetirement"])
        if "skills" in patch and isinstance(patch["skills"], dict):
            sk = st.setdefault("skills", {})
            for k in STAFF_SKILL_KEYS:
                if k in patch["skills"]:
                    sk[k] = max(1.0, min(20.0, _safe_float(patch["skills"][k], 10.0)))
        if "potential" in patch and isinstance(patch["potential"], dict):
            pot = st.setdefault("potential", {"m_Keys": list(range(1, 8)), "m_Values": [1] * 7})
            keys = pot.setdefault("m_Keys", list(range(1, 8)))
            vals = pot.setdefault("m_Values", [1] * 7)
            for sd in gd.STAFF_SKILLS:
                s_key = sd["key"]
                s_id = sd["id"]
                if s_key in patch["potential"]:
                    if s_id not in keys:
                        keys.append(s_id)
                        vals.append(1)
                    pos = keys.index(s_id)
                    while len(vals) <= pos:
                        vals.append(1)
                    vals[pos] = max(1, min(20, _safe_int(patch["potential"][s_key], 1)))
        if "careerInterests" in patch and isinstance(patch["careerInterests"], list):
            by_role = {
                _safe_int(it.get("roleType")): _safe_int(it.get("roleInterest"), 5)
                for it in patch["careerInterests"] if isinstance(it, dict)
            }
            st["careerInterests"] = [
                {"roleType": r, "roleInterest": max(1, min(20, by_role.get(r, 5)))}
                for r in range(6)
            ]
        if "languagesSpoken" in patch and isinstance(patch["languagesSpoken"], list):
            seen_langs: set[int] = set()
            langs_out = []
            for l in patch["languagesSpoken"]:
                lid = _safe_int(l.get("languageId"))
                if lid <= 0 or lid in seen_langs:
                    continue
                seen_langs.add(lid)
                langs_out.append({
                    "languageId": lid,
                    "languageSkill": max(1, min(20, _safe_int(l.get("languageSkill"), 20))),
                    "limit": max(0, min(20, _safe_int(l.get("limit"), 20))),
                    "progress": _safe_float(l.get("progress"), 0.0),
                })
            st["languagesSpoken"] = langs_out
        if "portrait" in patch and isinstance(patch["portrait"], dict):
            pt = st.setdefault("portrait", {})
            for pf in gd.PORTRAIT_FIELDS:
                k = pf["key"]
                if k in patch["portrait"]:
                    pt[k] = max(pf["min"], min(pf["max"], _safe_int(patch["portrait"][k], pf["min"])))
        if "careerStats" in patch and isinstance(patch["careerStats"], list):
            cs_out = []
            for row in patch["careerStats"]:
                if not isinstance(row, dict):
                    continue
                cs_out.append({
                    "teamId": max(0, _safe_int(row.get("teamId"), 0)),
                    "year": _safe_int(row.get("year"), 2025),
                    "matchesWon": max(0, _safe_int(row.get("matchesWon"), 0)),
                    "matchesLost": max(0, _safe_int(row.get("matchesLost"), 0)),
                    "staffRole": max(0, min(5, _safe_int(row.get("staffRole"), 0))),
                })
            st["careerStats"] = cs_out
        if "contract" in patch:
            cpatch = patch["contract"]
            contracts = self.db["staffContracts"]
            if cpatch is None or _safe_int(cpatch.get("teamId")) <= 0:
                self.db["staffContracts"] = [c for c in contracts if _safe_int(c.get("staffId")) != staff_id]
            else:
                tid = _safe_int(cpatch["teamId"])
                ex = next((c for c in contracts if _safe_int(c.get("staffId")) == staff_id), None)
                if not ex:
                    ex = {"salaryYear": 90000, "endDate": {"hour": 0, "day": 1, "month": 1, "year": 2028}, "teamId": tid, "staffId": staff_id, "role": 0, "rejectAllStaffOffers": False}
                    contracts.append(ex)
                ex["teamId"] = tid
                ex["salaryYear"] = _safe_int(cpatch.get("salaryYear"), ex["salaryYear"])
                ex["role"] = _safe_int(cpatch.get("role"), ex["role"])
                if "rejectAllStaffOffers" in cpatch:
                    ex["rejectAllStaffOffers"] = bool(cpatch["rejectAllStaffOffers"])
                ed = ex.setdefault("endDate", {"hour": 0, "day": 1, "month": 1, "year": 2028})
                if "endYear" in cpatch:
                    ed["year"] = max(2026, _safe_int(cpatch["endYear"], ed.get("year", 2028)))
                if "endMonth" in cpatch:
                    ed["month"] = max(1, min(12, _safe_int(cpatch["endMonth"], ed.get("month", 1))))
                if "endDay" in cpatch:
                    ed["day"] = max(1, min(28, _safe_int(cpatch["endDay"], ed.get("day", 1))))
        self.dirty_db = True
        return self.get_staff(staff_id)

    def create_staff(self, payload: dict[str, Any]) -> dict[str, Any]:
        staffers = self.db["staffers"]
        new_id = self._next_id(staffers)
        base = max(5.0, min(19.0, _safe_float(payload.get("baseSkill"), 13.0)))
        role_id = max(0, min(5, _safe_int(payload.get("role"), 0)))
        skills = {k: round(base, 1) for k in STAFF_SKILL_KEYS}
        new_st = {
            "id": new_id,
            "name": str(payload.get("name") or f"Coach{new_id}").strip(),
            "age": _safe_int(payload.get("age"), 34),
            "nation": _safe_int(payload.get("nation"), 102),
            "reputation": _safe_int(payload.get("reputation"), 10),
            "portrait": {
                "face": 3, "nose": 4, "mouth": 4, "mouthColor": 3, "eyes": 2, "eyeballsColor": 2,
                "eyebrows": 4, "eyebrowsColor": 2, "hair": 15, "hairColor": 2, "beard": 0, "beardColor": 2,
                "accessory": 0, "accessoryColor": 0, "wrinkes": 0, "skinColor": 2, "neck": 1,
            },
            "preferredMentality": _safe_int(payload.get("preferredMentality"), 1),
            "languagesSpoken": [{"languageId": _safe_int(payload.get("languageId"), 13), "languageSkill": 20, "limit": 20, "progress": 0.0}],
            "setForRetirement": False, "monthsBenchedOrWithoutContract": 0, "monthsSinceNewContract": 6, "reputationProgress": 0.0,
            "potential": {"m_Keys": list(range(1, 8)), "m_Values": [max(1, min(20, int(round(base)) + 1))] * 7},
            "playerAwards": [], "skills": skills,
            "careerInterests": [{"roleType": r, "roleInterest": 18 if r == role_id else 6} for r in range(6)],
            "retirementConsiderationAge": 55, "careerStats": [],
        }
        staffers.append(new_st)
        if _safe_int(payload.get("teamId")) > 0:
            self.db["staffContracts"].append({
                "salaryYear": _safe_int(payload.get("salaryYear"), 120000),
                "endDate": {"hour": 0, "day": 1, "month": 1, "year": 2028},
                "teamId": _safe_int(payload["teamId"]),
                "staffId": new_id,
                "role": _safe_int(payload.get("role"), 0),
                "rejectAllStaffOffers": False,
            })
        self.dirty_db = True
        return self.get_staff(new_id)

    def delete_staff(self, staff_id: int) -> dict[str, Any]:
        before = len(self.db["staffers"])
        self.db["staffers"] = [s for s in self.db["staffers"] if _safe_int(s.get("id")) != staff_id]
        if len(self.db["staffers"]) == before:
            raise ValueError(f"Staff {staff_id} not found.")
        self.db["staffContracts"] = [c for c in self.db["staffContracts"] if _safe_int(c.get("staffId")) != staff_id]
        self.dirty_db = True
        return {"ok": True, "deletedStaffId": staff_id}

    def list_sponsors(self) -> list[dict[str, Any]]:
        return sorted(copy.deepcopy(self.db.get("sponsors", [])), key=lambda s: (-_safe_int(s.get("reputation")), (s.get("name") or "").lower()))

    def save_sponsor(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        sponsors = self.db["sponsors"]
        sid = _safe_int(payload.get("id"))
        ex = next((s for s in sponsors if _safe_int(s.get("id")) == sid), None) if sid else None
        if not ex:
            sid = self._next_id(sponsors)
            ex = {
                "id": sid, "reputation": 10, "name": "New Sponsor", "logo": "",
                "expiry": {"hour": 0, "day": 0, "month": 0, "year": 0},
                "dealLength": {"hour": 0, "day": 0, "month": 0, "year": 0},
                "fixedMonthlyContribution": 5000, "potentialBonusTournamentTemplate": 4,
                "bonusTournamentId": 0, "bonusPositionRequirement": 8, "bonusPayout": 10000,
                "slot": 0, "accepted": False,
            }
            sponsors.append(ex)
        for k in ["name", "logo"]:
            if k in payload:
                ex[k] = str(payload[k])
        for k in ["reputation", "fixedMonthlyContribution", "potentialBonusTournamentTemplate", "bonusPositionRequirement", "bonusPayout"]:
            if k in payload:
                ex[k] = _safe_int(payload[k], ex[k])
        self.dirty_db = True
        return self.list_sponsors()

    def delete_sponsor(self, sponsor_id: int) -> list[dict[str, Any]]:
        self.db["sponsors"] = [s for s in self.db["sponsors"] if _safe_int(s.get("id")) != sponsor_id]
        self.dirty_db = True
        return self.list_sponsors()

    # ------------------------------------------------------------------
    # Tournaments & Stages CRUD
    # ------------------------------------------------------------------

    def list_tournaments(self) -> list[dict[str, Any]]:
        tournaments = self.db.get("tournaments", [])
        stages = self.db.get("tournamentStages", [])
        out = []
        for idx, t in enumerate(tournaments):
            linked = _tournament_linked_stages(t, stages)
            sim = _simulate_tournament_dates(t, linked, half="spring")
            enriched_stages = []
            for st in copy.deepcopy(linked):
                st["nameLabel"] = gd.format_stage_name(st.get("name"))
                enriched_stages.append(st)
            out.append({
                "index": idx,
                "template": _safe_int(t.get("template")),
                "id": _safe_int(t.get("id")),
                "name": t.get("name"),
                "logo": t.get("logo"),
                "reputation": _safe_int(t.get("reputation")),
                "tier": sim["tier"],
                "awards": sim["awards"],
                "outdated": bool(t.get("outdated", False)),
                "startMonthRange": _safe_int(t.get("startMonthRange"), 1),
                "startDayRange": _safe_int(t.get("startDayRange"), 1),
                "dynamicLocation": _safe_int(t.get("dynamicLocation")),
                "bestOfFiveGrandFinals": bool(t.get("bestOfFiveGrandFinals", False)),
                "stickerMoneyHigh": _safe_int(t.get("stickerMoneyHigh")),
                "stickerMoneyLow": _safe_int(t.get("stickerMoneyLow")),
                "isMajor": _safe_int(t.get("reputation")) >= 19,
                "stickerPctTotal": round(sum(_safe_float(pr.get("stickerMoneyPercentages")) for st in linked for pr in (st.get("prizes") or [])), 3),
                "stageCount": len(linked),
                "prizePool": sim["prizePool"],
                "effectiveRegion": sim["effectiveRegion"],
                "effectiveRegionName": sim["effectiveRegionName"],
                "hasLan": sim["hasLan"],
                "simSpring": {"start": sim["startDate"], "end": sim["endDate"], "days": sim["durationDays"]},
                "stages": enriched_stages,
                "raw": copy.deepcopy(t),
            })
        out.sort(key=lambda r: (-r["reputation"], r["startMonthRange"], r["startDayRange"], (r["name"] or "").lower()))
        return out

    def save_tournament(self, payload: dict[str, Any]) -> dict[str, Any]:
        tournaments = self.db["tournaments"]
        stages = self.db["tournamentStages"]
        orig_tpl = _safe_int(payload.get("origTemplate"))
        tpl = _safe_int(payload.get("template"))
        tourn = next((t for t in tournaments if _safe_int(t.get("template")) == orig_tpl), None) if orig_tpl else None

        if not tourn:
            # Create new tournament
            used = {_safe_int(t.get("template")) for t in tournaments}
            if tpl <= 0 or tpl in used:
                tpl = (max(used, default=50) + 1)
            tourn = {
                "id": 0,
                "template": tpl,
                "name": str(payload.get("name") or f"Custom Event {tpl}"),
                "logo": str(payload.get("logo") or payload.get("name") or ""),
                "reputation": max(1, min(20, _safe_int(payload.get("reputation"), 15))),
                "tournamentStageNames": [
                    "GROUPS__CONTEXT_TOURNAMENT_STAGE_NAME",
                    "PLAYOFFS__CONTEXT_TOURNAMENT_STAGE_NAME",
                ],
                "outdated": bool(payload.get("outdated", False)),
                "startDayRange": max(1, min(31, _safe_int(payload.get("startDayRange"), 1))),
                "startMonthRange": max(1, min(6, _safe_int(payload.get("startMonthRange"), 1))),
                "dynamicLocation": _safe_int(payload.get("dynamicLocation"), 2),
                "playersAwarded": [],
                "bestOfFiveGrandFinals": bool(payload.get("bestOfFiveGrandFinals", True)),
                "stickerMoneyGranted": 0,
                "stickerMoneyHigh": _safe_int(payload.get("stickerMoneyHigh"), 0),
                "stickerMoneyLow": _safe_int(payload.get("stickerMoneyLow"), 0),
            }
            tournaments.append(tourn)

            # Default 2 stages if none supplied
            raw_stages = payload.get("stages")
            if not raw_stages:
                tier_code = payload.get("presetTier") or "S"
                raw_stages = _default_stages_for_tier(tpl, tier_code)
            for st in raw_stages:
                st_copy = copy.deepcopy(st)
                st_copy["parentTemplate"] = tpl
                st_copy["parentId"] = 0
                stages.append(st_copy)
        else:
            if tpl > 0 and tpl != orig_tpl:
                # Re-link existing stages cleanly
                for s in stages:
                    if _safe_int(s.get("parentTemplate")) == orig_tpl:
                        s["parentTemplate"] = tpl
                tourn["template"] = tpl
            else:
                tpl = orig_tpl

            for k in ["name", "logo"]:
                if k in payload:
                    tourn[k] = str(payload[k])
            for k in ["reputation", "startDayRange", "startMonthRange", "dynamicLocation", "stickerMoneyHigh", "stickerMoneyLow"]:
                if k in payload:
                    val = _safe_int(payload[k], tourn.get(k, 0))
                    if k == "startMonthRange":
                        val = max(1, min(6, val))
                    elif k == "startDayRange":
                        val = max(1, min(31, val))
                    elif k == "reputation":
                        val = max(1, min(20, val))
                    tourn[k] = val
            for k in ["outdated", "bestOfFiveGrandFinals"]:
                if k in payload:
                    tourn[k] = bool(payload[k])

            if "stages" in payload and isinstance(payload["stages"], list):
                kept = [s for s in stages if _safe_int(s.get("parentTemplate")) != tpl]
                new_stages = []
                for idx, st in enumerate(payload["stages"]):
                    s_obj = _normalize_stage_dict(st, tpl, idx + 1)
                    new_stages.append(s_obj)
                self.db["tournamentStages"] = kept + new_stages
                tourn["tournamentStageNames"] = sorted(
                    list(dict.fromkeys([s["name"] for s in new_stages])),
                    key=lambda n: next((s["stage"] for s in new_stages if s["name"] == n), 99),
                )

        self.dirty_db = True
        return {"ok": True, "template": tpl, "tournaments": self.list_tournaments()}

    def delete_tournament(self, template: int) -> dict[str, Any]:
        before = len(self.db["tournaments"])
        self.db["tournaments"] = [t for t in self.db["tournaments"] if _safe_int(t.get("template")) != template]
        if len(self.db["tournaments"]) == before:
            raise ValueError(f"Tournament template {template} not found.")
        self.db["tournamentStages"] = [s for s in self.db["tournamentStages"] if _safe_int(s.get("parentTemplate")) != template]
        self.dirty_db = True
        return {"ok": True, "deletedTemplate": template}

    def clone_tournament(self, template: int) -> dict[str, Any]:
        """Duplicate an existing tournament and all its linked stages with a fresh unique template ID."""
        tournaments = self.db["tournaments"]
        stages = self.db["tournamentStages"]
        src = next((t for t in tournaments if _safe_int(t.get("template")) == template), None)
        if not src:
            raise ValueError(f"Tournament template {template} not found.")
        used = {_safe_int(t.get("template")) for t in tournaments}
        new_tpl = max(used, default=50) + 1
        t_copy = copy.deepcopy(src)
        t_copy["id"] = 0
        t_copy["template"] = new_tpl
        t_copy["name"] = f"{src.get('name', 'Tournament')} (Copy)"
        if _safe_int(t_copy.get("reputation")) < 19:
            t_copy["stickerMoneyLow"] = 0
            t_copy["stickerMoneyHigh"] = 0
        tournaments.append(t_copy)
        for st in _tournament_linked_stages(src, stages):
            s_copy = copy.deepcopy(st)
            s_copy["id"] = 0
            s_copy["parentId"] = 0
            s_copy["parentTemplate"] = new_tpl
            stages.append(s_copy)
        self.dirty_db = True
        return {"ok": True, "template": new_tpl, "tournaments": self.list_tournaments()}

    # ------------------------------------------------------------------
    # KEY FEATURE 1: Tournament Overlap & Schedule Validator
    # ------------------------------------------------------------------

    def analyze_tournaments_schedule(self) -> dict[str, Any]:
        """
        Simulate Spring (M1..6) and Fall (M7..12) dates via CS Manager's scheduler
        and detect overlaps split cleanly by Tier (Major T5, S-Tier T4, A-Tier T3, B-Tier T2, C-Tier T1).
        """
        tournaments = self.db.get("tournaments", [])
        stages = self.db.get("tournamentStages", [])
        active = [t for t in tournaments if not t.get("outdated")]

        events_spring: list[dict[str, Any]] = []
        events_fall: list[dict[str, Any]] = []
        stage_chain_issues: list[dict[str, Any]] = []

        for t in active:
            linked = _tournament_linked_stages(t, stages)
            sim_sp = _simulate_tournament_dates(t, linked, ref_year=2026, half="spring")
            sim_fa = _simulate_tournament_dates(t, linked, ref_year=2026, half="fall")
            events_spring.append(sim_sp)
            events_fall.append(sim_fa)

            # Check internal stage chain & bracket math
            tpl = sim_sp["template"]
            for err in sim_sp["errors"]:
                stage_chain_issues.append({"template": tpl, "name": sim_sp["name"], "severity": "error", "message": err})
            by_snum: dict[int, list[dict[str, Any]]] = {}
            for st in linked:
                snum = _safe_int(st.get("stage"), 1)
                by_snum.setdefault(snum, []).append(st)
                parts = _safe_int(st.get("numberOfParticipants"))
                grps = max(1, _safe_int(st.get("groups"), 1))
                fmt = _safe_int(st.get("formatType"))
                if parts < grps or parts % grps != 0:
                    stage_chain_issues.append({
                        "template": tpl, "name": sim_sp["name"], "severity": "error",
                        "message": f"Stage {snum}: {parts} participants cannot divide evenly into {grps} groups.",
                    })
                elif fmt in (0, 3):
                    per_g = parts // grps
                    if per_g & (per_g - 1) != 0:
                        stage_chain_issues.append({
                            "template": tpl, "name": sim_sp["name"], "severity": "warn",
                            "message": f"Stage {snum}: Bracket group size {per_g} is not a power of 2.",
                        })
            s_nums = sorted(by_snum.keys())
            for i in range(len(s_nums) - 1):
                cur_s = by_snum[s_nums[i]]
                nxt_s = by_snum[s_nums[i + 1]]
                adv_spots = sum(
                    1
                    for st in cur_s
                    for pr in (st.get("prizes") or [])
                    if _safe_int(pr.get("progressType")) == 1
                )
                nxt_parts = sum(_safe_int(st.get("numberOfParticipants")) for st in nxt_s)
                if adv_spots > nxt_parts:
                    stage_chain_issues.append({
                        "template": tpl, "name": sim_sp["name"], "severity": "error",
                        "message": f"Stage {s_nums[i]} advances {adv_spots} teams, exceeding Stage {s_nums[i+1]} capacity ({nxt_parts}).",
                    })

        # Pairwise conflict check across ALL 7 weekday orientations (2026..2034 covering Mon..Sun anchors + Fall wrap)
        sims_by_year_sp: dict[int, list[dict[str, Any]]] = {}
        sims_by_year_fa: dict[int, list[dict[str, Any]]] = {}
        for yr in ANCHOR_SCENARIO_YEARS:
            sims_by_year_sp[yr] = [_simulate_tournament_dates(t, _tournament_linked_stages(t, stages), ref_year=yr, half="spring") for t in active]
            sims_by_year_fa[yr] = [_simulate_tournament_dates(t, _tournament_linked_stages(t, stages), ref_year=yr, half="fall") for t in active]

        conflicts: list[dict[str, Any]] = []
        parallel_regionals: list[dict[str, Any]] = []
        conflict_count_by_tpl: dict[int, int] = {}

        n_sp = len(events_spring)
        for i in range(n_sp):
            a_ref = events_spring[i]
            for j in range(i + 1, n_sp):
                b_ref = events_spring[j]
                reg_clash = _regions_overlap(a_ref["effectiveRegion"], b_ref["effectiveRegion"])

                # Evaluate across all 7 weekday alignments (when startDayRange lands on Mon..Sun)
                hit_weekdays: list[str] = []
                weekday_matrix: list[dict[str, Any]] = []
                max_d_all = 0
                min_d_all = 999
                max_d_lan = 0
                max_slot_hits = 0
                any_lan_overlap = False
                sample_a, sample_b = a_ref, b_ref

                for yr in ANCHOR_SCENARIO_YEARS:
                    ay = sims_by_year_sp[yr][i]
                    by = sims_by_year_sp[yr][j]
                    over_all, d_all = _dates_overlap(ay["startDate"], ay["endDate"], by["startDate"], by["endDate"])
                    b_cmp = by
                    if not over_all:
                        fa_by = sims_by_year_fa[yr][j]
                        over_wrap, d_wrap = _dates_overlap(ay["startDate"], ay["endDate"], fa_by["startDate"], fa_by["endDate"])
                        if over_wrap:
                            over_all, d_all, b_cmp = over_wrap, d_wrap, fa_by
                    over_lan, d_lan = _dates_overlap(ay["lanStart"], ay["lanEnd"], b_cmp["lanStart"], b_cmp["lanEnd"]) if over_all else (False, 0)
                    dow_lbl = ay["anchorDow"]
                    weekday_matrix.append({"dow": dow_lbl, "year": yr, "overlaps": over_all, "days": d_all if over_all else 0, "lanOverlap": over_lan})
                    if not over_all:
                        continue

                    slots_a = {(rd, st["slot"]) for st in ay["stages"] for rd in st["roundDates"]}
                    slots_b = {(rd, st["slot"]) for st in b_cmp["stages"] for rd in st["roundDates"]}
                    slot_hits = len(slots_a & slots_b)

                    hit_weekdays.append(dow_lbl)
                    max_d_all = max(max_d_all, d_all)
                    min_d_all = min(min_d_all, d_all)
                    max_slot_hits = max(max_slot_hits, slot_hits)
                    if over_lan:
                        any_lan_overlap = True
                        max_d_lan = max(max_d_lan, d_lan)
                    if yr == 2026 or sample_a is a_ref:
                        sample_a, sample_b = ay, b_cmp

                if not hit_weekdays:
                    continue

                if not reg_clash:
                    parallel_regionals.append({
                        "aName": a_ref["name"], "aTemplate": a_ref["template"], "aRegion": a_ref["effectiveRegionName"],
                        "bName": b_ref["name"], "bTemplate": b_ref["template"], "bRegion": b_ref["effectiveRegionName"],
                        "overlapDays": max_d_all, "window": f"{sample_a['startDate'][5:]} .. {sample_a['endDate'][5:]}",
                        "tierBand": f"{a_ref['tier']['subCode']} / {b_ref['tier']['subCode']}",
                        "yearsHit": len(hit_weekdays),
                    })
                    continue

                ta = a_ref["tier"]["engineTier"]
                tb = b_ref["tier"]["engineTier"]
                top_tier = max(ta, tb)
                same_band = a_ref["tier"]["code"] == b_ref["tier"]["code"]

                if any_lan_overlap and ta >= 4 and tb >= 4:
                    scenario = "s_tier_lan"
                    scenario_label = "S-Tier / Major LAN Collision"
                    severity = "critical"
                elif ta >= 4 and tb >= 4:
                    scenario = "s_tier_all"
                    scenario_label = "S-Tier / Major Overlap"
                    severity = "critical"
                elif any_lan_overlap and (ta >= 3 and tb >= 3):
                    scenario = "high_tier_lan"
                    scenario_label = "A/S-Tier LAN Collision"
                    severity = "high"
                elif top_tier >= 4 and any_lan_overlap:
                    scenario = "s_vs_lower_lan"
                    scenario_label = "S-Tier vs Lower-Tier LAN Clash"
                    severity = "high"
                elif same_band and ta == 3:
                    scenario = "a_tier"
                    scenario_label = "A-Tier vs A-Tier Overlap"
                    severity = "high"
                elif same_band:
                    scenario = f"{a_ref['tier']['code'].lower()}_tier"
                    scenario_label = f"{a_ref['tier']['subCode']} vs {b_ref['tier']['subCode']} Overlap"
                    severity = "warn"
                else:
                    scenario = "cross_tier"
                    scenario_label = f"Cross-Tier ({a_ref['tier']['subCode']} vs {b_ref['tier']['subCode']})"
                    severity = "info" if top_tier < 4 else "warn"

                conflict_count_by_tpl[a_ref["template"]] = conflict_count_by_tpl.get(a_ref["template"], 0) + 1
                conflict_count_by_tpl[b_ref["template"]] = conflict_count_by_tpl.get(b_ref["template"], 0) + 1

                wk_count = len(hit_weekdays)
                conflicts.append({
                    "a": {"template": a_ref["template"], "name": a_ref["name"], "rep": a_ref["reputation"], "tier": a_ref["tier"], "start": sample_a["startDate"], "end": sample_a["endDate"], "region": a_ref["effectiveRegionName"], "hasLan": a_ref["hasLan"]},
                    "b": {"template": b_ref["template"], "name": b_ref["name"], "rep": b_ref["reputation"], "tier": b_ref["tier"], "start": sample_b["startDate"], "end": sample_b["endDate"], "region": b_ref["effectiveRegionName"], "hasLan": b_ref["hasLan"]},
                    "overlapDays": max_d_all,
                    "minOverlapDays": 0 if wk_count < 7 else min_d_all,
                    "lanOverlapDays": max_d_lan if any_lan_overlap else 0,
                    "hasLanOverlap": any_lan_overlap,
                    "exactSlotCollisions": max_slot_hits,
                    "scenario": scenario,
                    "scenarioLabel": scenario_label,
                    "severity": severity,
                    "sameTierBand": same_band,
                    "highestTier": top_tier,
                    "weekdayHits": wk_count,
                    "alwaysOverlaps": wk_count == 7,
                    "triggerWeekdays": hit_weekdays,
                    "weekdayMatrix": weekday_matrix,
                })

        sev_rank = {"critical": 0, "high": 1, "warn": 2, "info": 3}
        conflicts.sort(key=lambda c: (sev_rank.get(c["severity"], 9), -c["highestTier"], -c["weekdayHits"], -c["overlapDays"]))

        for ev in events_spring:
            ev["conflictCount"] = conflict_count_by_tpl.get(ev["template"], 0)

        # Split summaries per tier bucket
        tier_buckets = []
        for code, title, lo, hi in [
            ("T5", "Tier 5: Majors & Flagships (Rep 19-20)", 19, 20),
            ("T4", "Tier 4: S-Tier (Rep 13-18)", 13, 18),
            ("T3", "Tier 3: A-Tier (Rep 9-12)", 9, 12),
            ("T2", "Tier 2: B-Tier (Rep 5-8)", 5, 8),
            ("T1", "Tier 1: C-Tier & Regional (Rep 1-4)", 1, 4),
        ]:
            evs = [e for e in events_spring if lo <= e["reputation"] <= hi]
            within_tier_conflicts = [c for c in conflicts if lo <= c["a"]["rep"] <= hi and lo <= c["b"]["rep"] <= hi]
            touching_conflicts = [c for c in conflicts if (lo <= c["a"]["rep"] <= hi) or (lo <= c["b"]["rep"] <= hi)]
            tier_buckets.append({
                "code": code,
                "title": title,
                "tournamentCount": len(evs),
                "lanCount": sum(1 for e in evs if e["hasLan"]),
                "withinTierConflicts": len(within_tier_conflicts),
                "touchingConflicts": len(touching_conflicts),
                "totalPrizePool": sum(e["prizePool"] for e in evs),
                "tournaments": evs,
            })

        monthly_load = []
        for m in range(1, 7):
            m_start = dt.date(2026, m, 1)
            next_m = dt.date(2026, m + 1, 1)
            m_end = next_m - dt.timedelta(days=1)
            counts_by_code = {"Major": 0, "S-Tier": 0, "A-Tier": 0, "B-Tier": 0, "C-Tier": 0}
            for e in events_spring:
                ov, _ = _dates_overlap(e["startDate"], e["endDate"], m_start.isoformat(), m_end.isoformat())
                if ov:
                    counts_by_code[e["tier"]["subCode"]] = counts_by_code.get(e["tier"]["subCode"], 0) + 1
            monthly_load.append({"month": m, "label": m_start.strftime("%b"), **counts_by_code})

        # Circuit EVP integrity + Hardware Simulation Load Estimation
        est_matches_half = 0
        est_maps_half = 0
        total_active_stages = 0
        max_participants_stage = 0
        stray_evp_events: list[dict[str, Any]] = []
        s_tier_events = 0
        safe_low_events = 0

        for t in active:
            rep = _safe_int(t.get("reputation"))
            tpl = _safe_int(t.get("template"))
            linked = _tournament_linked_stages(t, stages)
            total_active_stages += len(linked)
            if rep >= 13:
                s_tier_events += 1
            elif 8 <= rep <= 12:
                aw = gd.awards_for_reputation(rep)
                stray_evp_events.append({
                    "template": tpl,
                    "name": t.get("name"),
                    "reputation": rep,
                    "evp": aw["evp"],
                    "hm": aw["honorableMentions"],
                })
            else:
                safe_low_events += 1

            for st in linked:
                parts = max(2, _safe_int(st.get("numberOfParticipants"), 8))
                grps = max(1, _safe_int(st.get("groups"), 1))
                max_participants_stage = max(max_participants_stage, parts)
                fmt = _safe_int(st.get("formatType"))
                bo = max(1, _safe_int(st.get("mapsPerMatch"), 3))
                per_g = max(2, parts // grps)
                if fmt == 0:  # Single Elim
                    m_cnt = parts - grps
                elif fmt == 1:  # Round Robin
                    m_cnt = grps * ((per_g * (per_g - 1)) // 2)
                elif fmt == 2:  # Swiss
                    rw = max(1, _safe_int(st.get("requiredWins"), 3))
                    ml = max(1, _safe_int(st.get("maxLosses"), 2))
                    m_cnt = int(round((parts * (rw + ml - 1)) * 0.5))
                elif fmt == 3:  # Double Elim
                    m_cnt = max(parts, 2 * parts - 2 * grps)
                else:
                    m_cnt = parts - 1
                est_matches_half += m_cnt
                # Average maps played per BO3 (~2.42) / BO5 (~3.85) / BO1 (1)
                avg_maps = 1.0 if bo == 1 else (2.42 if bo == 3 else 3.85)
                est_maps_half += int(round(m_cnt * avg_maps))

        active_count = len(events_spring)
        yearly_runs = active_count * 2
        yearly_stage_runs = total_active_stages * 2
        yearly_matches = est_matches_half * 2
        yearly_maps = est_maps_half * 2

        if active_count <= 25 and yearly_maps <= 4500:
            hw_tier, hw_badge = "Lightweight (Laptop / Steam Deck Safe)", "ok"
        elif active_count <= 45 and yearly_maps <= 8500:
            hw_tier, hw_badge = "Balanced Standard (Desktop Sweet Spot)", "ok"
        elif active_count <= 62 and yearly_maps <= 12000:
            hw_tier, hw_badge = "Heavy Load (Fast CPU Recommended)", "warn"
        else:
            hw_tier, hw_badge = "Overcooked / High Save & Tick Lag Risk", "bad"

        circuit_and_hardware = {
            "activeTemplates": active_count,
            "yearlyEventRuns": yearly_runs,
            "activeStages": total_active_stages,
            "yearlyStageRuns": yearly_stage_runs,
            "estMatchesPerYear": yearly_matches,
            "estMapsPerYear": yearly_maps,
            "maxStageParticipants": max_participants_stage,
            "hardwareTier": hw_tier,
            "hardwareBadge": hw_badge,
            "sTierCount": s_tier_events,
            "strayEvpZoneCount": len(stray_evp_events),
            "safeLowTierCount": safe_low_events,
            "strayEvpEvents": stray_evp_events,
        }

        return {
            "summary": {
                "activeTournaments": len(events_spring),
                "totalConflicts": len(conflicts),
                "alwaysOverlaps": sum(1 for c in conflicts if c["alwaysOverlaps"]),
                "conditionalOverlaps": sum(1 for c in conflicts if not c["alwaysOverlaps"]),
                "criticalConflicts": sum(1 for c in conflicts if c["severity"] == "critical"),
                "highConflicts": sum(1 for c in conflicts if c["severity"] == "high"),
                "lanConflicts": sum(1 for c in conflicts if c["hasLanOverlap"]),
                "sTierConflicts": sum(1 for c in conflicts if c["highestTier"] >= 4 and c["a"]["tier"]["engineTier"] >= 4 and c["b"]["tier"]["engineTier"] >= 4),
                "aTierConflicts": sum(1 for c in conflicts if c["a"]["tier"]["engineTier"] == 3 or c["b"]["tier"]["engineTier"] == 3),
                "safeParallelRegionals": len(parallel_regionals),
                "stageChainIssues": len(stage_chain_issues),
            },
            "circuitAndHardware": circuit_and_hardware,
            "tierBuckets": tier_buckets,
            "eventsSpring": events_spring,
            "conflicts": conflicts,
            "parallelRegionals": parallel_regionals,
            "stageChainIssues": stage_chain_issues,
            "monthlyLoad": monthly_load,
        }

    def suggest_tournament_slots(self, template: int) -> dict[str, Any]:
        """Search all (month 1..6, day 1..28) windows across ALL 7 weekday orientations for year-proof slots."""
        tournaments = self.db.get("tournaments", [])
        stages = self.db.get("tournamentStages", [])
        target = next((t for t in tournaments if _safe_int(t.get("template")) == template), None)
        if not target:
            raise ValueError(f"Tournament template {template} not found.")
        t_stages = _tournament_linked_stages(target, stages)
        other_raws = [t for t in tournaments if not t.get("outdated") and _safe_int(t.get("template")) != template]
        others_by_yr = {
            yr: [_simulate_tournament_dates(t, _tournament_linked_stages(t, stages), ref_year=yr, half="spring") for t in other_raws]
            for yr in ANCHOR_SCENARIO_YEARS
        }
        target_tier = gd.classify_tournament_tier(_safe_int(target.get("reputation")))["engineTier"]

        candidates = []
        for m in range(1, 7):
            max_d = 28 if m == 2 else 30 if m in (4, 6) else 31
            for d in range(1, max_d + 1, 2):
                probe = copy.deepcopy(target)
                probe["startMonthRange"] = m
                probe["startDayRange"] = d
                worst_same_hi = 0
                worst_lan = 0
                worst_lower = 0
                clean_wkds = 0
                blocking_set: list[str] = []
                sim_2026 = _simulate_tournament_dates(probe, t_stages, ref_year=2026, half="spring")

                for yr in ANCHOR_SCENARIO_YEARS:
                    sim_y = sim_2026 if yr == 2026 else _simulate_tournament_dates(probe, t_stages, ref_year=yr, half="spring")
                    sh, lh, lw = 0, 0, 0
                    for o in others_by_yr[yr]:
                        if not _regions_overlap(sim_y["effectiveRegion"], o["effectiveRegion"]):
                            continue
                        ov, _ = _dates_overlap(sim_y["startDate"], sim_y["endDate"], o["startDate"], o["endDate"])
                        if not ov:
                            continue
                        ov_lan, _ = _dates_overlap(sim_y["lanStart"], sim_y["lanEnd"], o["lanStart"], o["lanEnd"])
                        if ov_lan:
                            lh += 1
                        if o["tier"]["engineTier"] >= target_tier or (o["tier"]["engineTier"] >= 4 and target_tier >= 3):
                            sh += 1
                            lbl = f"{o['name']} ({o['tier']['subCode']})"
                            if lbl not in blocking_set:
                                blocking_set.append(lbl)
                        else:
                            lw += 1
                    if sh == 0 and lh == 0:
                        clean_wkds += 1
                    worst_same_hi = max(worst_same_hi, sh)
                    worst_lan = max(worst_lan, lh)
                    worst_lower = max(worst_lower, lw)

                score = worst_same_hi * 120 + worst_lan * 40 + (7 - clean_wkds) * 18 + worst_lower * 4
                candidates.append({
                    "startMonthRange": m,
                    "startDayRange": d,
                    "startDate": sim_2026["startDate"],
                    "endDate": sim_2026["endDate"],
                    "sameOrHigherConflicts": worst_same_hi,
                    "lanConflicts": worst_lan,
                    "lowerConflicts": worst_lower,
                    "cleanWeekdays": clean_wkds,
                    "penaltyScore": score,
                    "blockingNames": blocking_set[:4],
                })
        candidates.sort(key=lambda c: (c["penaltyScore"], c["startMonthRange"], c["startDayRange"]))
        return {
            "template": template,
            "name": target.get("name"),
            "current": {"startMonthRange": _safe_int(target.get("startMonthRange")), "startDayRange": _safe_int(target.get("startDayRange"))},
            "suggestions": candidates[:12],
        }

    def visualize_tournament_run(self, template: int) -> dict[str, Any]:
        """Return day-by-day execution visualizer across Spring, Fall, and all 7 start-weekday shifts."""
        tournaments = self.db.get("tournaments", [])
        stages = self.db.get("tournamentStages", [])
        t = next((x for x in tournaments if _safe_int(x.get("template")) == template), None)
        if not t:
            raise ValueError(f"Tournament template {template} not found.")
        linked = _tournament_linked_stages(t, stages)

        def _build_run(half: str) -> dict[str, Any]:
            sim = _simulate_tournament_dates(t, linked, ref_year=2026, half=half)
            timeline_rounds: list[dict[str, Any]] = []
            for st in sim["stages"]:
                fmt = st["formatType"]
                n_r = len(st["roundDates"])
                parts_pg = max(2, st["participants"] // max(1, st["groups"]))
                for r_i, rd_iso in enumerate(st["roundDates"], 1):
                    d_obj = dt.date.fromisoformat(rd_iso)
                    if fmt == 0:  # Single elim labels from end
                        rem = n_r - r_i
                        if rem == 0:
                            r_lbl = "Grand Final"
                        elif rem == 1:
                            r_lbl = "Semifinals"
                        elif rem == 2:
                            r_lbl = "Quarterfinals"
                        else:
                            r_lbl = f"Round {r_i} (Bo{st['mapsPerMatch']})"
                    elif fmt == 2:
                        r_lbl = f"Swiss Round {r_i} ({st['requiredWins']}W / {st['maxLosses']}L)"
                    elif fmt == 3:
                        r_lbl = "Grand Final" if r_i == n_r else f"Double Elim Matchday {r_i}"
                    else:
                        r_lbl = f"Group Matchday {r_i}"
                    timeline_rounds.append({
                        "stageNum": st["stageNum"],
                        "stageLabel": st["nameLabel"],
                        "venueName": st["venueName"],
                        "isLan": st["isLan"],
                        "slotLabel": st["slotLabel"],
                        "date": rd_iso,
                        "dow": gd.DAYS_OF_WEEK.get(_csm_dow(d_obj), "Mon"),
                        "roundIdx": r_i,
                        "roundLabel": r_lbl,
                        "participants": st["participants"],
                        "groups": st["groups"],
                    })
            return {"sim": sim, "rounds": timeline_rounds}

        spring = _build_run("spring")
        fall = _build_run("fall")
        weekday_shifts = []
        for yr in ANCHOR_SCENARIO_YEARS:
            sy = _simulate_tournament_dates(t, linked, ref_year=yr, half="spring")
            weekday_shifts.append({
                "anchorDow": sy["anchorDow"],
                "year": yr,
                "startDate": sy["startDate"],
                "endDate": sy["endDate"],
                "durationDays": sy["durationDays"],
            })

        return {
            "template": template,
            "name": t.get("name"),
            "awards": gd.awards_for_reputation(_safe_int(t.get("reputation"))),
            "spring": spring,
            "fall": fall,
            "weekdayShifts": weekday_shifts,
        }

    # ------------------------------------------------------------------
    # Custom Logos & Icons Folder Importer / Browser
    # ------------------------------------------------------------------

    def _logo_folders(self, kind: str) -> tuple[Path | None, Path | None]:
        """Return (pack_logo_dir, appdata_custom_dir) for kind in team/tournament/sponsor/weapon_icon/weapon_skin."""
        dirs = discover_csm_appdata_dirs()
        app_root = Path(dirs["roots"][0]) if dirs["roots"] else None

        mapping = {
            "team": ("TeamLogos", "CustomTeamLogos", "db"),
            "tournament": ("TournamentLogos", "CustomTournamentLogos", "db"),
            "sponsor": ("SponsorLogos", "CustomSponsorLogos", "db"),
            "weapon_icon": ("CustomWeaponIcons", "CustomWeaponIcons", "weapons"),
            "weapon_skin": ("CustomWeaponSkins", "CustomWeaponSkins", "weapons"),
        }
        if kind not in mapping:
            raise ValueError(f"Unsupported logo kind: {kind}")
        pack_sub, global_sub, owner = mapping[kind]
        pack_dir: Path | None = None
        if owner == "db" and self.db_dir:
            pack_dir = Path(self.db_dir) / pack_sub
        elif owner == "weapons" and self.weapons_path:
            pack_dir = Path(self.weapons_path).parent / pack_sub
        global_dir = (app_root / global_sub) if app_root else None
        return pack_dir, global_dir

    def list_logos(self, kind: str) -> list[dict[str, Any]]:
        pack_dir, global_dir = self._logo_folders(kind)
        found: dict[str, dict[str, Any]] = {}
        for source_lbl, d in [("pack", pack_dir), ("global", global_dir)]:
            if not d or not d.exists():
                continue
            for f in d.iterdir():
                if f.is_file() and f.suffix.lower() in IMAGE_EXTS:
                    key = f.stem
                    if key not in found:
                        found[key] = {
                            "stem": key,
                            "filename": f.name,
                            "source": source_lbl,
                            "url": f"/api/logo-img/{kind}/{f.name}",
                        }
        return sorted(found.values(), key=lambda x: x["stem"].lower())

    def resolve_logo_path(self, kind: str, name_or_file: str) -> Path | None:
        pack_dir, global_dir = self._logo_folders(kind)
        clean = Path(name_or_file).name
        stem_low = Path(clean).stem.lower()
        for d in [pack_dir, global_dir]:
            if not d or not d.exists():
                continue
            exact = d / clean
            if exact.is_file():
                return exact
            for f in d.iterdir():
                if f.is_file() and f.suffix.lower() in IMAGE_EXTS:
                    if f.name.lower() == clean.lower() or f.stem.lower() == stem_low:
                        return f
        return None

    def import_logos_from_folder(self, kind: str, src_folder: str, sync_global: bool = True) -> dict[str, Any]:
        src = Path(src_folder)
        if not src.exists() or not src.is_dir():
            raise ValueError(f"Logo folder does not exist: {src_folder}")
        pack_dir, global_dir = self._logo_folders(kind)
        copied = []
        targets = [d for d in [pack_dir, global_dir if sync_global else None] if d is not None]
        if not targets:
            raise ValueError("No target pack or CS Manager folder available.")
        for tdir in targets:
            tdir.mkdir(parents=True, exist_ok=True)
        for f in sorted(src.iterdir()):
            if f.is_file() and f.suffix.lower() in IMAGE_EXTS:
                for tdir in targets:
                    shutil.copy2(f, tdir / f.name)
                copied.append(f.stem)
        return {"ok": True, "importedCount": len(copied), "stems": copied, "logos": self.list_logos(kind)}

    def import_logo_uploads(self, kind: str, files: list[dict[str, str]], sync_global: bool = True) -> dict[str, Any]:
        pack_dir, global_dir = self._logo_folders(kind)
        targets = [d for d in [pack_dir, global_dir if sync_global else None] if d is not None]
        if not targets:
            raise ValueError("No target pack or CS Manager folder available.")
        for tdir in targets:
            tdir.mkdir(parents=True, exist_ok=True)
        imported = []
        for item in files:
            fname = Path(str(item.get("name") or "")).name
            if not fname or Path(fname).suffix.lower() not in IMAGE_EXTS:
                continue
            b64 = str(item.get("dataBase64") or "")
            if "," in b64:
                b64 = b64.split(",", 1)[1]
            raw = base64.b64decode(b64)
            for tdir in targets:
                (tdir / fname).write_bytes(raw)
            imported.append(Path(fname).stem)
        return {"ok": True, "importedCount": len(imported), "stems": imported, "logos": self.list_logos(kind)}

    # ------------------------------------------------------------------
    # DB Integrity Validator & Auto-Fix
    # ------------------------------------------------------------------

    def validate_database(self, auto_fix: bool = False) -> dict[str, Any]:
        if not self.db_dir:
            raise ValueError("No database loaded.")
        issues: list[dict[str, Any]] = []
        fixes_applied = 0

        teams = self.db["teams"]
        players = self.db["players"]
        staffers = self.db["staffers"]
        p_contracts = self.db["playerContracts"]
        s_contracts = self.db["staffContracts"]
        tournaments = self.db["tournaments"]
        stages = self.db["tournamentStages"]

        t_ids = {_safe_int(t.get("id")) for t in teams}
        p_ids = {_safe_int(p.get("id")) for p in players}
        s_ids = {_safe_int(s.get("id")) for s in staffers}
        p_lookup = self._player_lookup()
        t_lookup = self._team_lookup()

        # 1. Duplicate player/staff contracts or orphan contracts
        seen_p: set[int] = set()
        kept_pc = []
        for c in p_contracts:
            pid = _safe_int(c.get("playerId"))
            tid = _safe_int(c.get("teamId"))
            if pid not in p_ids or (tid != 0 and tid not in t_ids):
                issues.append({"severity": "error", "category": "Orphan Contract", "detail": f"PlayerContract playerId={pid} teamId={tid} points to missing entity."})
                if auto_fix:
                    fixes_applied += 1
                    continue
            elif pid in seen_p:
                issues.append({"severity": "error", "category": "Duplicate Contract", "detail": f"Player #{pid} has multiple contracts."})
                if auto_fix:
                    fixes_applied += 1
                    continue
            seen_p.add(pid)
            kept_pc.append(c)
        if auto_fix:
            self.db["playerContracts"] = kept_pc

        seen_s: set[int] = set()
        kept_sc = []
        for c in s_contracts:
            sid = _safe_int(c.get("staffId"))
            tid = _safe_int(c.get("teamId"))
            if sid not in s_ids or (tid != 0 and tid not in t_ids):
                issues.append({"severity": "error", "category": "Orphan Staff Contract", "detail": f"StaffContract staffId={sid} teamId={tid} points to missing entity."})
                if auto_fix:
                    fixes_applied += 1
                    continue
            elif sid in seen_s:
                issues.append({"severity": "error", "category": "Duplicate Staff Contract", "detail": f"Staff #{sid} has multiple contracts."})
                if auto_fix:
                    fixes_applied += 1
                    continue
            seen_s.add(sid)
            kept_sc.append(c)
        if auto_fix:
            self.db["staffContracts"] = kept_sc

        # 2. Team starter count != 5 & Hiring bias mismatches
        _, p_by_team, _, _ = self._contract_maps()
        for tid, t in t_lookup.items():
            pcs = p_by_team.get(tid, [])
            starters = [c for c in pcs if not c.get("benched")]
            if len(pcs) > 0 and len(starters) != 5:
                issues.append({
                    "severity": "warn", "category": "Starter Count",
                    "detail": f"{t.get('name')} has {len(starters)} non-benched starters ({len(pcs)} total contracted).",
                })
                if auto_fix and len(pcs) >= 5:
                    pcs_sorted = sorted(pcs, key=lambda c: -_player_skill_avg(p_lookup.get(_safe_int(c.get("playerId")), {})))
                    for idx, c in enumerate(pcs_sorted):
                        c["benched"] = idx >= 5
                    fixes_applied += 1

            bias = _safe_int((t.get("owner") or {}).get("hiringBias"), 7)
            t_nat = _safe_int(t.get("nation"))
            t_reg = gd.NATION_REGIONS.get(t_nat, 0)
            t_lang = _safe_int((t.get("teamCohesion") or {}).get("mainLanguage"))
            if bias in (0, 1, 4):
                for c in starters:
                    pl = p_lookup.get(_safe_int(c.get("playerId")))
                    if not pl:
                        continue
                    p_nat = _safe_int(pl.get("nation"))
                    p_reg = gd.NATION_REGIONS.get(p_nat, 0)
                    p_langs = {_safe_int(l.get("languageId")) for l in (pl.get("languagesSpoken") or [])}
                    if bias == 0 and p_nat != t_nat:
                        issues.append({"severity": "warn", "category": "Policy Violation", "detail": f"{t.get('name')} (Only National: {gd.NATIONS.get(t_nat)}) starts {pl.get('name')} ({gd.NATIONS.get(p_nat)})."})
                    elif bias == 1 and t_lang and t_lang not in p_langs:
                        issues.append({"severity": "warn", "category": "Policy Violation", "detail": f"{t.get('name')} (Only National Language: {gd.LANGUAGES.get(t_lang)}) starts {pl.get('name')} without language."})
                    elif bias == 4 and p_reg != t_reg:
                        issues.append({"severity": "warn", "category": "Policy Violation", "detail": f"{t.get('name')} (Only Regional) starts {pl.get('name')} from another region."})

        # 3. Tournament templates & stage crash checks
        used_tpls: set[int] = set()
        for t in tournaments:
            tpl = _safe_int(t.get("template"))
            if tpl <= 0 or tpl in used_tpls:
                issues.append({"severity": "error", "category": "Duplicate/Zero Template", "detail": f"Tournament '{t.get('name')}' has invalid/duplicate template={tpl}."})
                if auto_fix:
                    new_tpl = max(used_tpls | {_safe_int(x.get('template')) for x in tournaments}, default=50) + 1
                    t["template"] = new_tpl
                    used_tpls.add(new_tpl)
                    fixes_applied += 1
            else:
                used_tpls.add(tpl)

        valid_tpls = {_safe_int(t.get("template")) for t in tournaments}
        kept_stages = []
        for st in stages:
            pt = _safe_int(st.get("parentTemplate"))
            if pt not in valid_tpls:
                issues.append({"severity": "error", "category": "Orphan Stage", "detail": f"Stage '{st.get('name')}' references missing parentTemplate={pt}."})
                if auto_fix:
                    fixes_applied += 1
                    continue
            if not (st.get("daysOfWeekPlayed") or []):
                issues.append({"severity": "error", "category": "Empty Match Days", "detail": f"Stage tpl={pt} stage={st.get('stage')} has empty daysOfWeekPlayed (crashes game)."})
                if auto_fix:
                    st["daysOfWeekPlayed"] = [5, 6, 7] if _safe_int(st.get("stage")) >= 2 else [1, 2, 3]
                    fixes_applied += 1
            kept_stages.append(st)
        if auto_fix:
            self.db["tournamentStages"] = kept_stages

        # 4. Sticker money only on Majors (rep >= 19), Stray-EVP circuit zone (rep 8..12), Custom Potential (50..275)
        for t in tournaments:
            if t.get("outdated"):
                continue
            tpl = _safe_int(t.get("template"))
            rep = _safe_int(t.get("reputation"))
            linked = _tournament_linked_stages(t, kept_stages if auto_fix else stages)
            stk_sum = sum(_safe_float(pr.get("stickerMoneyPercentages")) for s in linked for pr in (s.get("prizes") or []))
            has_stk = _safe_int(t.get("stickerMoneyLow")) > 0 or _safe_int(t.get("stickerMoneyHigh")) > 0 or stk_sum > 0
            if rep < 19 and has_stk:
                issues.append({"severity": "warn", "category": "Sticker Money (Major Only)", "detail": f"'{t.get('name')}' (tpl={tpl}, rep={rep}) is not a Major (rep<19) but has Sticker Money / Percentages configured."})
                if auto_fix:
                    t["stickerMoneyLow"] = 0
                    t["stickerMoneyHigh"] = 0
                    for s in linked:
                        for pr in (s.get("prizes") or []):
                            pr["stickerMoneyPercentages"] = 0
                    fixes_applied += 1
            elif rep >= 19 and (_safe_int(t.get("stickerMoneyHigh")) > 0) and abs(stk_sum - 100.0) > 0.5:
                issues.append({"severity": "warn", "category": "Major Sticker % Sum", "detail": f"Major '{t.get('name')}' stage sticker percentages sum to {stk_sum:.2f}% (recommended ~100%)."})
            if 8 <= rep <= 12:
                aw = gd.awards_for_reputation(rep)
                issues.append({"severity": "warn", "category": "Circuit Stray-EVP Zone", "detail": f"'{t.get('name')}' (rep={rep}) awards {aw['evp']} stray EVP(s). Keep Tier 2/3 events <= rep 7 or promote S-tier >= rep 13."})

        for pl in players:
            if pl.get("useStartingPotential"):
                sp = _safe_int(pl.get("startingPotential"))
                if sp < 50 or sp > 275:
                    issues.append({"severity": "warn", "category": "Custom Potential Range", "detail": f"Player '{pl.get('name')}' has useStartingPotential=true with out-of-range startingPotential={sp} (game expects 50-275)."})
                    if auto_fix:
                        pl["startingPotential"] = max(50, min(275, sp if sp > 0 else 180))
                        fixes_applied += 1

        if auto_fix and fixes_applied:
            self.dirty_db = True

        err_c = sum(1 for i in issues if i["severity"] == "error")
        warn_c = sum(1 for i in issues if i["severity"] == "warn")
        return {
            "issueCount": len(issues),
            "errorCount": err_c,
            "warningCount": warn_c,
            "fixesApplied": fixes_applied,
            "issues": issues[:200],
        }

    # ------------------------------------------------------------------
    # KEY FEATURE 2: Database Unbalance & Data Science Audit
    # ------------------------------------------------------------------

    def analyze_db_balance(self) -> dict[str, Any]:
        """Full pre-career unbalance analysis using Gini, percentiles, skill^2.8 projected dominance, and rep residuals."""
        if not self.db_dir:
            raise ValueError("No database loaded.")

        _, p_by_team, _, s_by_team = self._contract_maps()
        p_lookup = self._player_lookup()
        s_lookup = self._staff_lookup()

        team_rows = []
        for t in self.db.get("teams", []):
            tid = _safe_int(t.get("id"))
            pcs = p_by_team.get(tid, [])
            if not pcs:
                continue
            starters = []
            for c in pcs:
                if c.get("benched"):
                    continue
                pl = p_lookup.get(_safe_int(c.get("playerId")))
                if pl:
                    starters.append((pl, c))
            if not starters:
                starters = [(p_lookup[_safe_int(c.get("playerId"))], c) for c in pcs if _safe_int(c.get("playerId")) in p_lookup]
            starters.sort(key=lambda x: -_player_skill_avg(x[0]))
            five = starters[:5]
            if not five:
                continue

            p_objs = [x[0] for x in five]
            sk_list = [_player_skill_avg(pl) for pl in p_objs]
            mech_list = [_player_skill_avg(pl, [s["key"] for s in gd.PLAYER_SKILLS if s["group"] == "Mechanics"]) for pl in p_objs]
            wep_list = [_player_skill_avg(pl, ["rifles", "snipers", "pistols", "smgs"]) for pl in p_objs]
            men_list = [_player_skill_avg(pl, [s["key"] for s in gd.PLAYER_SKILLS if s["group"] == "Mental"]) for pl in p_objs]
            pot_list = [_player_potential_avg(pl) for pl in p_objs]

            avg_sk = _avg(sk_list)
            floor_sk = min(sk_list)
            ceil_sk = max(sk_list)
            payroll = sum(_safe_int(c.get("salaryYear")) for c in pcs)
            pts = sum(_safe_float(rp.get("currentPoints")) for rp in (t.get("rankingPoints") or []))
            nat = _safe_int(t.get("nation"))
            reg = gd.NATION_REGIONS.get(nat, 0)

            coaches = [
                s_lookup[_safe_int(c.get("staffId"))]
                for c in s_by_team.get(tid, [])
                if _safe_int(c.get("staffId")) in s_lookup
            ]
            coach_avg = _avg([_staff_skill_avg(st) for st in coaches]) if coaches else 0.0

            team_rows.append({
                "id": tid,
                "name": t.get("name"),
                "nationName": gd.NATIONS.get(nat, "Unknown"),
                "region": reg,
                "regionName": gd.REGIONS.get(reg, "EU"),
                "reputation": _safe_int(t.get("reputation")),
                "rankingPoints": round(pts),
                "avgSkill": round(avg_sk, 3),
                "floorSkill": round(floor_sk, 2),
                "starSkill": round(ceil_sk, 2),
                "mechAvg": round(_avg(mech_list), 2),
                "wepAvg": round(_avg(wep_list), 2),
                "menAvg": round(_avg(men_list), 2),
                "potAvg": round(_avg(pot_list), 2),
                "coachAvg": round(coach_avg, 2),
                "payroll": payroll,
                "hiringBias": _safe_int((t.get("owner") or {}).get("hiringBias"), 7),
                "hiringBiasName": gd.HIRING_BIAS.get(_safe_int((t.get("owner") or {}).get("hiringBias"), 7), "Intl"),
                "hasIgl": any(_safe_int(c.get("igl"), 2) == 0 for _, c in five),
                "hasAwp": any(_safe_int(c.get("sniper"), 2) == 0 for _, c in five),
                "rosterNames": [pl.get("name") for pl in p_objs],
            })

        # Sort by actual DB strength (avgSkill) AND compare against rankingPoints rank
        team_rows.sort(key=lambda r: (-r["avgSkill"], -r["rankingPoints"]))
        for idx, r in enumerate(team_rows, 1):
            r["skillRank"] = idx
        by_pts = sorted(team_rows, key=lambda r: (-r["rankingPoints"], -r["avgSkill"]))
        for idx, r in enumerate(by_pts, 1):
            r["dbRank"] = idx
            r["rankGap"] = r["dbRank"] - r["skillRank"]  # Positive = underrated in DB points; negative = inflated rank

        # Projected Dominance Model using engine's GetOddsOfWinning: p = sA^2.8 / (sA^2.8 + sB^2.8)
        top10 = team_rows[:10]
        top16 = team_rows[:16]
        t10_skills = [r["avgSkill"] for r in top10]
        t10_med = sorted(t10_skills)[len(t10_skills) // 2] if t10_skills else 15.0

        def _p_map(s1: float, s2: float) -> float:
            a = max(1.0, s1) ** 2.8
            b = max(1.0, s2) ** 2.8
            return a / (a + b)

        def _p_bo3(pm: float) -> float:
            return pm * pm * (3.0 - 2.0 * pm)

        for r in top16:
            opps = [o for o in top10 if o["id"] != r["id"]]
            map_win = _avg([_p_map(r["avgSkill"], o["avgSkill"]) for o in opps]) if opps else 0.5
            bo3_win = _avg([_p_bo3(_p_map(r["avgSkill"], o["avgSkill"])) for o in opps]) if opps else 0.5
            r["projMapWinVsTop10"] = round(map_win * 100.0, 1)
            r["projBo3WinVsTop10"] = round(bo3_win * 100.0, 1)
            # Soft tournament trophy concentration estimate (8-team S-Tier playoff -> ~bo3_win^3 normalized)
            r["_rawTrophyWt"] = max(0.0, bo3_win) ** 3.2

        wt_sum = sum(r["_rawTrophyWt"] for r in top16) or 1.0
        for r in top16:
            share = r["_rawTrophyWt"] / wt_sum
            r["projTrophySharePct"] = round(share * 100.0, 1)
            r["projSTierOutOf10"] = round(share * 10.0, 2)
            del r["_rawTrophyWt"]

        # Unbalance flags
        unbalance_alerts: list[dict[str, Any]] = []
        if len(team_rows) >= 2:
            gap_1_2 = team_rows[0]["avgSkill"] - team_rows[1]["avgSkill"]
            gap_1_t10 = team_rows[0]["avgSkill"] - t10_med
            if gap_1_2 >= 0.8 or team_rows[0].get("projBo3WinVsTop10", 50) >= 78:
                unbalance_alerts.append({
                    "severity": "critical",
                    "title": f"Runaway Superteam Risk: {team_rows[0]['name']}",
                    "detail": f"Avg skill {team_rows[0]['avgSkill']:.2f} sits +{gap_1_2:.2f} above #2 ({team_rows[1]['name']}) and +{gap_1_t10:.2f} above Top-10 median. Under CS Manager's skill^2.8 engine odds, projects {team_rows[0]['projBo3WinVsTop10']}% BO3 winrate and {team_rows[0]['projTrophySharePct']}% of Big-Event trophies.",
                })
        if len(team_rows) >= 10:
            gini_t10 = _gini([r["avgSkill"] for r in top10])
            if gini_t10 > 0.035:
                unbalance_alerts.append({
                    "severity": "warn",
                    "title": f"Steep Top-10 Skill Drop-Off (Gini={gini_t10})",
                    "detail": f"#1 ({team_rows[0]['avgSkill']:.2f}) vs #10 ({team_rows[9]['avgSkill']:.2f}) spread is {team_rows[0]['avgSkill'] - team_rows[9]['avgSkill']:.2f} pts — expect frequent 13-0/blowouts.",
                })

        # OLS Skill -> Reputation & Skill -> RankingPoints Mismatches
        xs_rep = [r["avgSkill"] for r in team_rows]
        ys_rep = [float(r["reputation"]) for r in team_rows]
        r_skill_rep = _pearson_r(xs_rep, ys_rep)
        rep_outliers = []
        if len(xs_rep) >= 5:
            mx, my = _avg(xs_rep), _avg(ys_rep)
            den = sum((x - mx) ** 2 for x in xs_rep) or 1.0
            slope = sum((x - mx) * (y - my) for x, y in zip(xs_rep, ys_rep)) / den
            inter = my - slope * mx
            for r in team_rows:
                pred = slope * r["avgSkill"] + inter
                resid = r["reputation"] - pred
                if abs(resid) >= 3.0 or abs(r["rankGap"]) >= 12:
                    rep_outliers.append({
                        "team": r["name"], "avgSkill": r["avgSkill"],
                        "reputation": r["reputation"], "expectedRep": round(pred, 1),
                        "repResid": round(resid, 1), "skillRank": r["skillRank"],
                        "dbRank": r["dbRank"], "rankGap": r["rankGap"],
                    })
            rep_outliers.sort(key=lambda o: -max(abs(o["repResid"]) * 4, abs(o["rankGap"])))

        # Region Ecosystem Breakdown
        region_meta = []
        all_players = self.db.get("players", [])
        for rcode, rname in [(0, "EU"), (1, "Americas"), (2, "Asia")]:
            r_teams = [r for r in team_rows if r["region"] == rcode]
            r_players = [p for p in all_players if gd.NATION_REGIONS.get(_safe_int(p.get("nation")), 0) == rcode]
            top_r_teams = r_teams[:10]
            region_meta.append({
                "region": rname,
                "teams": len(r_teams),
                "top30Teams": sum(1 for r in team_rows[:30] if r["region"] == rcode),
                "top10AvgSkill": round(_avg([r["avgSkill"] for r in top_r_teams]), 2),
                "players": len(r_players),
                "elitePlayers": sum(1 for p in r_players if _player_skill_avg(p) >= 15.5),
                "awpers14": sum(1 for p in r_players if _safe_float((p.get("skills") or {}).get("snipers")) >= 14.0),
                "igls14": sum(1 for p in r_players if _safe_float((p.get("skills") or {}).get("leadership")) >= 14.0),
                "wonderkidsU20": sum(1 for p in r_players if _safe_int(p.get("age")) <= 20 and _player_potential_avg(p) >= 15.0),
            })

        # Player Distribution, Age Pyramid & Skill Outliers
        p_avgs = [_player_skill_avg(p) for p in all_players]
        p_ages = [_safe_int(p.get("age"), 22) for p in all_players]
        age_buckets = [
            {"label": "U19 (<=19)", "count": sum(1 for a in p_ages if a <= 19)},
            {"label": "20-23", "count": sum(1 for a in p_ages if 20 <= a <= 23)},
            {"label": "24-27", "count": sum(1 for a in p_ages if 24 <= a <= 27)},
            {"label": "28+", "count": sum(1 for a in p_ages if a >= 28)},
        ]
        # Top & Bottom player outliers + inflated 19-20 skills count
        p_by_player, _, _, _ = self._contract_maps()
        t_lookup = self._team_lookup()
        player_outliers = []
        for p in all_players:
            sk = _player_skill_avg(p)
            c = p_by_player.get(_safe_int(p.get("id")))
            tid = _safe_int(c.get("teamId")) if c else 0
            tname = (t_lookup.get(tid) or {}).get("name") or "Free Agent"
            sk_vals = [_safe_float((p.get("skills") or {}).get(k)) for k in CORE_16_SKILL_KEYS]
            maxed_20 = sum(1 for v in sk_vals if v >= 19.5)
            player_outliers.append({
                "id": _safe_int(p.get("id")), "name": p.get("name"), "team": tname,
                "age": _safe_int(p.get("age")), "avgSkill": round(sk, 2),
                "potential": round(_player_potential_avg(p), 2),
                "salary": _safe_int(c.get("salaryYear")) if c else 0,
                "maxedCount": maxed_20,
            })
        player_outliers.sort(key=lambda r: -r["avgSkill"])

        # Overall Database Unbalance Score (0 = perfectly balanced, 100 = severely unbalanced)
        gini_top10 = _gini([r["avgSkill"] for r in top10])
        gini_top30 = _gini([r["avgSkill"] for r in team_rows[:30]])
        top1_gap = (team_rows[0]["avgSkill"] - t10_med) if team_rows else 0.0
        max_bo3 = max((r.get("projBo3WinVsTop10", 50.0) for r in top16), default=50.0)
        unbalance_score = round(min(100.0, max(0.0, (max_bo3 - 55.0) * 1.8 + top1_gap * 14.0 + gini_top30 * 500.0)), 1)

        return {
            "unbalanceScore": unbalance_score,
            "verdict": "Severely Unbalanced / Superteam-Dominated" if unbalance_score >= 65 else "Moderately Skewed" if unbalance_score >= 38 else "Healthy Parity",
            "alerts": unbalance_alerts,
            "parity": {
                "top10Skill": {"gini": gini_top10, **_percentiles([r["avgSkill"] for r in top10])},
                "top30Skill": {"gini": gini_top30, **_percentiles([r["avgSkill"] for r in team_rows[:30]])},
                "allTeamsSkill": {"gini": _gini([r["avgSkill"] for r in team_rows]), **_percentiles([r["avgSkill"] for r in team_rows])},
                "allPlayersSkill": {"gini": _gini(p_avgs), **_percentiles(p_avgs)},
                "payrolls": {"gini": _gini([r["payroll"] for r in team_rows if r["payroll"] > 0]), **_percentiles([r["payroll"] for r in team_rows if r["payroll"] > 0])},
            },
            "correlations": {
                "skillVsReputationR": r_skill_rep,
                "skillVsRankingPointsR": _pearson_r(xs_rep, [float(r["rankingPoints"]) for r in team_rows]),
                "skillVsPayrollR": _pearson_r([r["avgSkill"] for r in team_rows if r["payroll"] > 0], [float(r["payroll"]) for r in team_rows if r["payroll"] > 0]),
            },
            "powerRankings": team_rows[:40],
            "top16Projection": top16,
            "repOutliers": rep_outliers[:20],
            "regionMeta": region_meta,
            "ageBuckets": age_buckets,
            "topPlayerOutliers": player_outliers[:20],
        }

    # ------------------------------------------------------------------
    # KEY FEATURE 3: GameBalance & Weapons Modding + Unbalance Science
    # ------------------------------------------------------------------

    def get_balance_and_analysis(self) -> dict[str, Any]:
        if not self.balance_data:
            return {"loaded": False}
        gb = self.balance_data
        regens = {
            "great": _safe_int(gb.get("greatRegensOnNewCareer")),
            "good": _safe_int(gb.get("goodRegensOnNewCareer")),
            "average": _safe_int(gb.get("averageRegensOnNewCareer")),
            "bad": _safe_int(gb.get("badRegensOnNewCareer")),
        }
        tot_reg = sum(regens.values()) or 1
        regen_pcts = {k: round(v * 100.0 / tot_reg, 1) for k, v in regens.items()}

        practice_costs = [_safe_int(gb.get(f"practiceFacilitiesCostLevel{i}")) for i in range(5)]
        academy_costs = [_safe_int(gb.get(f"academyCostLevel{i}")) for i in range(5)]
        branding_costs = [_safe_int(gb.get(f"brandingCenterCostLevel{i}")) for i in range(10)]
        owner_tiers = [_safe_int(gb.get(f"ownerContributionTier{i}")) for i in range(1, 21)]
        merch_tiers = [_safe_int(gb.get(f"merchContributionTier{i}")) for i in range(1, 21)]

        # Audit tier jump spikes, merch ratio & branding ROI payback
        econ_alerts = []
        tier_curve = []
        for idx in range(20):
            own = owner_tiers[idx]
            mer = merch_tiers[idx]
            comb = own + mer
            prev_own = owner_tiers[idx - 1] if idx > 0 else own
            jump_pct = round(((own - prev_own) / max(1, prev_own)) * 100.0, 1) if idx > 0 else 0.0
            merch_share = round((mer / comb) * 100.0, 1) if comb > 0 else 0.0
            br_lvl = min(len(branding_costs) - 1, max(1, (idx // 2) + 1))
            br_cost = branding_costs[br_lvl] if branding_costs else 0
            merch_delta = max(1, mer - (merch_tiers[idx - 1] if idx > 0 else 0))
            payback_mo = round(br_cost / merch_delta, 1) if br_cost > 0 else 0.0
            if jump_pct >= 50.0 and idx >= 3:
                econ_alerts.append(f"Owner Tier {idx+1} jumps +{jump_pct}% (${prev_own:,} -> ${own:,}/mo).")
            tier_curve.append({
                "tier": idx + 1, "owner": own, "merch": mer,
                "combinedMonthly": comb, "annualCombined": comb * 12,
                "ownerJumpPct": jump_pct, "merchSharePct": merch_share,
                "estPaybackMonths": payback_mo,
            })

        # Facility cliff check
        for label, arr in [("Practice Facility", practice_costs), ("Academy", academy_costs), ("Branding", branding_costs)]:
            if len(arr) >= 2 and arr[-1] > 0 and arr[-2] > 0:
                ratio = round(arr[-1] / arr[-2], 2)
                if ratio >= 3.0:
                    econ_alerts.append(f"{label} final upgrade spikes {ratio}x (${arr[-2]:,} -> ${arr[-1]:,}).")

        if regens["great"] * 100.0 / tot_reg > 5.0:
            econ_alerts.append(f"Regen inflation: {regen_pcts['great']}% Great regens ({regens['great']}/{tot_reg}) will flood future drafts with superstars.")
        elif regens["great"] <= 1:
            econ_alerts.append(f"Elite scarcity: Only {regens['great']} Great regens per career — aging stars won't be replaced.")

        # Compare loaded DB payrolls vs GameBalance tiers
        top10_payrolls: list[int] = []
        deficit_orgs = 0
        total_orgs_checked = 0
        if self.db_dir and self.db.get("teams"):
            _, p_by_team, _, s_by_team = self._contract_maps()
            ranked = sorted(
                self.db["teams"],
                key=lambda t: (-sum(_safe_float(rp.get("currentPoints")) for rp in (t.get("rankingPoints") or [])), -_safe_int(t.get("reputation"))),
            )
            for idx_t, t in enumerate(ranked):
                tid = _safe_int(t.get("id"))
                pcs = p_by_team.get(tid, [])
                if not pcs:
                    continue
                total_orgs_checked += 1
                payroll = sum(_safe_int(c.get("salaryYear")) for c in pcs) + sum(_safe_int(c.get("salaryYear")) for c in s_by_team.get(tid, []))
                if idx_t < 10:
                    top10_payrolls.append(payroll)
                tf = t.get("teamFinances") or {}
                o_t = max(1, min(20, int(round(_safe_float(tf.get("ownerContribution"), 1)))))
                m_t = max(1, min(20, int(round(_safe_float(tf.get("merchandiseContribution"), 1)))))
                base_annual = (owner_tiers[o_t - 1] + merch_tiers[m_t - 1]) * 12
                if payroll > base_annual:
                    deficit_orgs += 1

        avg_t10_payroll = int(round(_avg([float(x) for x in top10_payrolls]))) if top10_payrolls else 0
        t20_annual = (owner_tiers[-1] + merch_tiers[-1]) * 12 if owner_tiers else 0
        t20_cov_pct = round((t20_annual / avg_t10_payroll) * 100.0, 1) if avg_t10_payroll > 0 else 0.0

        dev_reg_sum = sum(DEV_GAMEBALANCE_BASELINE[k] for k in ("greatRegensOnNewCareer", "goodRegensOnNewCareer", "averageRegensOnNewCareer", "badRegensOnNewCareer"))
        dev_fac_sum = sum(DEV_GAMEBALANCE_BASELINE[k] for k in DEV_GAMEBALANCE_BASELINE if "CostLevel" in k)
        dev_t20 = DEV_GAMEBALANCE_BASELINE["ownerContributionTier20"] + DEV_GAMEBALANCE_BASELINE["merchContributionTier20"]
        cur_fac_sum = sum(practice_costs) + sum(academy_costs) + sum(branding_costs)
        cur_t20 = (owner_tiers[-1] if owner_tiers else 0) + (merch_tiers[-1] if merch_tiers else 0)

        return {
            "loaded": True,
            "name": self.balance_name,
            "path": self.balance_path,
            "dirty": self.dirty_balance,
            "data": copy.deepcopy(gb),
            "sortedGroups": _balance_param_groups(gb),
            "analysis": {
                "totalRegens": sum(regens.values()),
                "regens": regens,
                "regenPcts": regen_pcts,
                "practiceSum": sum(practice_costs),
                "academySum": sum(academy_costs),
                "brandingSum": sum(branding_costs),
                "allFacilitySum": cur_fac_sum,
                "ownerTier20": owner_tiers[-1] if owner_tiers else 0,
                "merchTier20": merch_tiers[-1] if merch_tiers else 0,
                "tierCurve": tier_curve,
                "alerts": econ_alerts,
                "regenGini": _gini(list(regens.values())),
                "dbEcon": {
                    "top10AvgPayroll": avg_t10_payroll,
                    "t20PayrollCoveragePct": t20_cov_pct,
                    "deficitOrgsCount": deficit_orgs,
                    "totalOrgsChecked": total_orgs_checked,
                },
                "devBaseline": {
                    "devTotalRegens": dev_reg_sum,
                    "devFacilityTotal": dev_fac_sum,
                    "devTier20Monthly": dev_t20,
                    "regenDiffPct": round(((sum(regens.values()) - dev_reg_sum) / max(1, dev_reg_sum)) * 100.0, 1),
                    "facilityDiffPct": round(((cur_fac_sum - dev_fac_sum) / max(1, dev_fac_sum)) * 100.0, 1),
                    "tier20DiffPct": round(((cur_t20 - dev_t20) / max(1, dev_t20)) * 100.0, 1),
                },
            },
        }

    def batch_scale_balance(self, category: str, pct: float = 10.0) -> dict[str, Any]:
        """Batch scale GameBalance categories or reset to dev baseline (test/gameBalance.json)."""
        if not self.balance_data:
            raise ValueError("No GameBalance pack loaded.")
        gb = self.balance_data
        if category == "reset_dev":
            for k, v in DEV_GAMEBALANCE_BASELINE.items():
                if k in gb:
                    gb[k] = v
            self.dirty_balance = True
            return self.get_balance_and_analysis()
        mult = 1.0 + (pct / 100.0)
        for k, v in list(gb.items()):
            match = (
                (category == "owner" and k.startswith("ownerContributionTier"))
                or (category == "merch" and k.startswith("merchContributionTier"))
                or (category == "facilities" and "CostLevel" in k)
                or (category == "regens" and k.endswith("RegensOnNewCareer"))
                or (category == "all")
            )
            if not match:
                continue
            cur = _safe_int(v)
            if cur <= 0:
                continue
            if category == "regens" or k.endswith("RegensOnNewCareer"):
                gb[k] = max(1, int(round(cur * mult)))
            else:
                gb[k] = max(50, int(round(cur * mult / 50.0) * 50))
        self.dirty_balance = True
        return self.get_balance_and_analysis()

    def update_game_balance(self, patch: dict[str, Any]) -> dict[str, Any]:
        if not self.balance_data:
            raise ValueError("No GameBalance pack loaded.")
        for k, v in patch.items():
            if k in self.balance_data:
                self.balance_data[k] = max(0, _safe_int(v, _safe_int(self.balance_data[k])))
        self.dirty_balance = True
        return self.get_balance_and_analysis()

    def get_weapons_and_analysis(self) -> dict[str, Any]:
        if not self.weapons_data:
            return {"loaded": False}
        weapons = self.weapons_data.get("weapons", [])
        analyzed = []
        for w in weapons:
            dmg = _safe_float(w.get("damage"), 1.0)
            armor_m = _safe_float(w.get("armorMultiplier"), 0.5)
            hs_m = _safe_float(w.get("hsMultiplier"), 4.0)
            rof_int = max(0.02, _safe_float(w.get("shotInterval"), 0.1))
            price = _safe_int(w.get("price"), 0)
            acc = _safe_float(w.get("accuracy"), 1.0)
            drop = _safe_float(w.get("damageDropOffPerUnitOfDistance"), 0.002)
            ammo = _safe_int(w.get("ammo"), 1)
            wtype = _safe_int(w.get("type"), 0)
            avail = _safe_int(w.get("availability"), 2)

            rpm = 60.0 / rof_int
            armored_body = dmg * armor_m
            raw_dps = dmg / rof_int
            armored_dps = armored_body / rof_int
            stk_armor = max(1, math.ceil(100.0 / max(1.0, armored_body)))
            ttk_ms = round((stk_armor - 1) * rof_int * 1000.0)
            intended_hs_armor = dmg * armor_m * hs_m
            # Weapon::CalculateDamage() overwrites dmg = weapon.damage * armorMultiplier when armored/helmeted
            engine_armored_hs = armored_body
            unarmored_hs = dmg * hs_m
            dmg_30u = dmg * max(0.2, 1.0 - drop * 30.0) * armor_m
            eff_per_1k = (armored_dps * (acc / 25.0)) / max(0.3, price / 1000.0)

            analyzed.append({
                "id": _safe_int(w.get("id")),
                "customName": w.get("customName") or f"Weapon #{w.get('id')}",
                "type": wtype,
                "typeName": gd.WEAPON_TYPES.get(wtype, "Other"),
                "availability": avail,
                "availabilityName": "T" if avail == 0 else "CT" if avail == 1 else "Both",
                "tier": _safe_int(w.get("tier"), 1),
                "price": price,
                "damage": dmg,
                "armorMultiplier": round(armor_m, 4),
                "hsMultiplier": round(hs_m, 3),
                "accuracy": round(acc, 2),
                "shotInterval": round(rof_int, 4),
                "rpm": round(rpm, 0),
                "armoredBodyDmg": round(armored_body, 1),
                "rawDps": round(raw_dps, 1),
                "armoredDps": round(armored_dps, 1),
                "stkArmor": stk_armor,
                "ttkArmorMs": ttk_ms,
                "intendedHsArmorDmg": round(intended_hs_armor, 1),
                "engineArmoredHsDmg": round(engine_armored_hs, 1),
                "unarmoredHsDmg": round(unarmored_hs, 1),
                "dmgAt30uArmor": round(dmg_30u, 1),
                "valueIndex": round(eff_per_1k, 1),
                "killReward": _safe_int(w.get("killReward"), 300),
                "ammo": ammo,
                "flags": [],
            })

        # Compute z-scores & outlier flags within each Weapon Type
        by_type: dict[int, list[dict[str, Any]]] = {}
        for row in analyzed:
            by_type.setdefault(row["type"], []).append(row)

        weapon_alerts: list[dict[str, Any]] = []
        for wt, group in by_type.items():
            dpss = [g["armoredDps"] for g in group]
            vals = [g["valueIndex"] for g in group]
            m_dps, m_val = _avg(dpss), _avg(vals)
            sd_dps = math.sqrt(_avg([(x - m_dps) ** 2 for x in dpss])) or 1.0
            sd_val = math.sqrt(_avg([(x - m_val) ** 2 for x in vals])) or 1.0
            for g in group:
                z_d = (g["armoredDps"] - m_dps) / sd_dps
                z_v = (g["valueIndex"] - m_val) / sd_val
                g["typeZScore"] = round((z_d + z_v) * 0.5, 2)
                if g["stkArmor"] == 1 and g["price"] <= 2000:
                    g["flags"].append("1-Shot Bargain")
                if g["damage"] * g["hsMultiplier"] < 100 and wt in (0, 2):
                    g["flags"].append("Weak HS (<100)")
                if g["typeZScore"] >= 1.2:
                    g["flags"].append("OP Outlier")
                elif g["typeZScore"] <= -1.2:
                    g["flags"].append("Underpowered")
                if abs(g["typeZScore"]) >= 1.25:
                    weapon_alerts.append({
                        "severity": "warn" if g["typeZScore"] > 0 else "info",
                        "weapon": g["customName"],
                        "typeName": g["typeName"],
                        "detail": f"Z={g['typeZScore']:+.2f} within {g['typeName']}s | Armored DPS {g['armoredDps']} (TTK {g['ttkArmorMs']}ms), ${g['price']}, Value {g['valueIndex']}.",
                    })

        # Side Parity (T-only vs CT-only)
        side_summary = []
        for av_id, av_lbl in [(0, "T-Side Exclusives"), (1, "CT-Side Exclusives"), (2, "Shared Weapons")]:
            grp = [a for a in analyzed if a["availability"] == av_id]
            side_summary.append({
                "label": av_lbl,
                "count": len(grp),
                "avgPrice": round(_avg([g["price"] for g in grp])),
                "avgArmoredDps": round(_avg([g["armoredDps"] for g in grp]), 1),
                "avgTtkMs": round(_avg([g["ttkArmorMs"] for g in grp])),
                "avgAccuracy": round(_avg([g["accuracy"] for g in grp]), 1),
            })

        analyzed.sort(key=lambda r: (r["type"], r["price"], r["customName"].lower()))
        return {
            "loaded": True,
            "name": self.weapons_name,
            "path": self.weapons_path,
            "dirty": self.dirty_weapons,
            "weapons": copy.deepcopy(weapons),
            "analysis": {
                "rows": analyzed,
                "sideSummary": side_summary,
                "dpsGini": _gini([a["armoredDps"] for a in analyzed]),
                "valueGini": _gini([a["valueIndex"] for a in analyzed]),
                "alerts": weapon_alerts,
            },
        }

    def update_weapon(self, weapon_id: int, patch: dict[str, Any]) -> dict[str, Any]:
        if not self.weapons_data:
            raise ValueError("No Weapons pack loaded.")
        weapons = self.weapons_data.get("weapons", [])
        w = next((x for x in weapons if _safe_int(x.get("id")) == weapon_id), None)
        if not w:
            raise ValueError(f"Weapon {weapon_id} not found.")
        int_fields = ["type", "damage", "price", "ammo", "killReward", "reloadTime", "availability", "tier"]
        flt_fields = ["hsMultiplier", "armorMultiplier", "accuracy", "movingAccuracyPenalty", "recoilIncreasePerShot", "recoilResetTime", "shotInterval", "damageDropOffPerUnitOfDistance"]
        str_fields = ["customName", "weaponSoundKey", "iconName"]
        for k in int_fields:
            if k in patch:
                w[k] = _safe_int(patch[k], _safe_int(w.get(k)))
        for k in flt_fields:
            if k in patch:
                w[k] = _safe_float(patch[k], _safe_float(w.get(k)))
        for k in str_fields:
            if k in patch:
                w[k] = str(patch[k])
        if "skinNames" in patch and isinstance(patch["skinNames"], list):
            w["skinNames"] = [str(s) for s in patch["skinNames"] if str(s).strip()]
        self.dirty_weapons = True
        return self.get_weapons_and_analysis()

    # ------------------------------------------------------------------
    # God Mode DB Balancer: Floor Boost, Superteam Smoother, AI/Econ Fixer
    # ------------------------------------------------------------------

    def _god_sync_potential_caps(self, player: dict[str, Any]) -> None:
        """Ensure per-skill potential caps & custom startingPotential don't undercut current skills."""
        sk = player.get("skills") or {}
        pot = player.get("potential")
        if not isinstance(pot, dict) or "m_Keys" not in pot or "m_Values" not in pot:
            pot = {"m_Keys": [m["id"] for m in gd.PLAYER_SKILLS], "m_Values": [20 for _ in gd.PLAYER_SKILLS]}
            player["potential"] = pot
        pmap = {int(k): int(v) for k, v in zip(pot["m_Keys"], pot["m_Values"])}
        pot["m_Keys"] = [m["id"] for m in gd.PLAYER_SKILLS]
        pot["m_Values"] = [
            int(max(1, min(20, max(pmap.get(m["id"], 15), int(math.ceil(_safe_float(sk.get(m["key"], 10.0), 10.0)))))))
            for m in gd.PLAYER_SKILLS
        ]
        if player.get("useStartingPotential"):
            cur_sum_14 = int(round(_player_skill_avg(player, CORE_16_SKILL_KEYS) * 14.0))
            sp = _safe_int(player.get("startingPotential"), 180)
            player["startingPotential"] = max(50, min(275, max(sp, cur_sum_14)))

    def _god_set_player_target_avg(
        self,
        player: dict[str, Any],
        target_avg: float,
        max_skill_cap: float = 20.0,
    ) -> tuple[float, float]:
        """Shift a player's skills cleanly so CORE_16 avg reaches target_avg (1..max_skill_cap)."""
        sk = player.setdefault("skills", {})
        old_avg = round(_player_skill_avg(player, CORE_16_SKILL_KEYS), 2)
        target_avg = max(1.0, min(max_skill_cap, float(target_avg)))
        for _ in range(5):
            cur_avg = _player_skill_avg(player, CORE_16_SKILL_KEYS)
            diff = target_avg - cur_avg
            if abs(diff) < 0.015:
                break
            for k in DEFAULT_SKILL_KEYS:
                v = _safe_float(sk.get(k, 10.0), 10.0)
                cap = max_skill_cap if k in CORE_16_SKILL_KEYS else 20.0
                sk[k] = round(max(1.0, min(cap, v + diff)), 2)
        if max_skill_cap < 20.0:
            for k in CORE_16_SKILL_KEYS:
                sk[k] = round(min(max_skill_cap, _safe_float(sk.get(k, 10.0), 10.0)), 2)
        self._god_sync_potential_caps(player)
        new_avg = round(_player_skill_avg(player, CORE_16_SKILL_KEYS), 2)
        return old_avg, new_avg

    def _god_parity_snapshot(self) -> dict[str, Any]:
        """Compute Top-10/20/DB parity & skill^2.8 dominance telemetry."""
        _, p_by_team, _, _ = self._contract_maps()
        p_lookup = self._player_lookup()
        rows: list[dict[str, Any]] = []
        for t in self.db.get("teams", []):
            tid = _safe_int(t.get("id"))
            pcs = p_by_team.get(tid, [])
            starters = [p_lookup[_safe_int(c.get("playerId"))] for c in pcs if not c.get("benched") and _safe_int(c.get("playerId")) in p_lookup]
            if not starters:
                continue
            avgs = [_player_skill_avg(p, CORE_16_SKILL_KEYS) for p in starters]
            benched = [p_lookup[_safe_int(c.get("playerId"))] for c in pcs if c.get("benched") and _safe_int(c.get("playerId")) in p_lookup]
            best_bench = max((_player_skill_avg(bp, CORE_16_SKILL_KEYS) for bp in benched), default=0.0)
            pts = sum(_safe_float(rp.get("currentPoints")) for rp in (t.get("rankingPoints") or []))
            floor_s = min(avgs)
            rows.append({
                "teamId": tid,
                "name": t.get("name", ""),
                "reputation": _safe_int(t.get("reputation"), 1),
                "rankingPoints": round(pts),
                "avgSkill": round(_avg(avgs), 2),
                "weakestFloor": round(floor_s, 2),
                "benchWaste": round(max(0.0, best_bench - floor_s), 2),
                "balance": _safe_int((t.get("teamFinances") or {}).get("currentBalance"), 0),
                "power28": round(_avg(avgs) ** 2.8, 1),
            })
        rows.sort(key=lambda r: (-r["rankingPoints"], -r["avgSkill"], -r["reputation"]))
        for idx, r in enumerate(rows, 1):
            r["dbRank"] = idx
        top10 = rows[:10]
        top20 = rows[:20]
        t10_avg = round(_avg([r["avgSkill"] for r in top10]), 2) if top10 else 0.0
        t20_avg = round(_avg([r["avgSkill"] for r in top20]), 2) if top20 else 0.0
        top1_row = max(top20, key=lambda r: r["avgSkill"], default=None)
        min_t10 = min(top10, key=lambda r: r["avgSkill"], default=None)
        top1_bo3 = 0.0
        if top1_row and top10:
            others = [r for r in top10 if r["teamId"] != top1_row["teamId"]] or top10
            m_wins = [top1_row["power28"] / (top1_row["power28"] + o["power28"]) for o in others]
            bo3_wins = [(p * p * (3.0 - 2.0 * p)) * 100.0 for p in m_wins]
            top1_bo3 = round(_avg(bo3_wins), 1)
        return {
            "top1TeamName": top1_row["name"] if top1_row else "-",
            "top1AvgSkill": top1_row["avgSkill"] if top1_row else 0.0,
            "top1Bo3VsTop10": top1_bo3,
            "top10AvgSkill": t10_avg,
            "top20AvgSkill": t20_avg,
            "top10Spread": round((top1_row["avgSkill"] - min_t10["avgSkill"]), 2) if (top1_row and min_t10) else 0.0,
            "top10Gini": _gini([r["avgSkill"] for r in top10]),
            "aiBenchSabotagesTop20": sum(1 for r in top20 if r["benchWaste"] >= 0.25),
            "teamsList": rows,
        }

    def _god_scoped_teams(self, scope: str, excluded_ids: set[int] | None = None) -> list[dict[str, Any]]:
        excluded = excluded_ids or set()
        snap = self._god_parity_snapshot()["teamsList"]
        t_lookup = self._team_lookup()
        limit = {"top10": 10, "top20": 20, "top30": 30}.get(scope, 9999)
        selected = []
        for r in snap[:limit]:
            if r["teamId"] in excluded:
                continue
            t = t_lookup.get(r["teamId"])
            if t:
                selected.append(t)
        return selected

    def get_god_mode_state(self) -> dict[str, Any]:
        if not self.db_dir:
            return {"loaded": False}
        snap = self._god_parity_snapshot()
        return {
            "loaded": True,
            "snapshot": {k: v for k, v in snap.items() if k != "teamsList"},
            "teams": [
                {k: r[k] for k in ("teamId", "name", "dbRank", "avgSkill", "weakestFloor", "benchWaste", "balance")}
                for r in snap["teamsList"]
            ],
            "defaultProtectedStar": "",
        }

    def run_god_mode(self, action: str, params: dict[str, Any], dry_run: bool = False) -> dict[str, Any]:
        """Preview or apply God Mode DB balancing, smoothing, AI-fix, economy, or wonderkid injection."""
        if not self.db_dir:
            raise ValueError("No database loaded.")
        if dry_run:
            clone = DatabaseWorkspace()
            clone.db_dir = self.db_dir
            clone.db_name = self.db_name
            clone.db = copy.deepcopy(self.db)
            res = clone.run_god_mode(action, params, dry_run=False)
            res["dryRun"] = True
            return res

        before_snap = self._god_parity_snapshot()
        protected_raw = str(params.get("protectedNames") or "")
        protected_set = {x.strip().lower() for x in protected_raw.split(",") if x.strip()}
        protect_top1 = bool(params.get("protectTop1Team", False))
        excl = {before_snap["teamsList"][0]["teamId"]} if (protect_top1 and before_snap["teamsList"]) else set()

        _, p_by_team, s_by_team_idx, _ = self._contract_maps()
        p_lookup = self._player_lookup()
        s_lookup = self._staff_lookup()
        changes: list[dict[str, Any]] = []
        summary_lines: list[str] = []

        if action == "boost_floor_parity":
            scope = str(params.get("scope", "top20"))
            mode = str(params.get("mode", "floor"))
            target_floor = float(params.get("targetFloor", 15.8))
            smooth_target = float(params.get("smoothTarget", 16.2))
            strength_pct = max(5.0, min(100.0, float(params.get("strengthPct", 75.0)))) / 100.0
            boost_delta = max(0.1, min(6.0, float(params.get("boostDelta", 1.2))))

            targets = self._god_scoped_teams(scope, excluded_ids=excl)
            for t in targets:
                tid = _safe_int(t.get("id"))
                starters = [p_lookup[_safe_int(c.get("playerId"))] for c in p_by_team.get(tid, []) if not c.get("benched") and _safe_int(c.get("playerId")) in p_lookup]
                if not starters:
                    continue
                starters.sort(key=lambda p: _player_skill_avg(p, CORE_16_SKILL_KEYS))
                if mode == "weakest_slot_boost":
                    for p in starters[:2]:
                        if (p.get("name") or "").lower() in protected_set:
                            continue
                        cur = _player_skill_avg(p, CORE_16_SKILL_KEYS)
                        old_a, new_a = self._god_set_player_target_avg(p, min(19.5, cur + boost_delta))
                        if abs(new_a - old_a) >= 0.02:
                            changes.append({"target": p["name"], "team": t["name"], "detail": f"Weakest-slot floor {old_a} -> {new_a}"})
                else:
                    team_avg = _avg([_player_skill_avg(p, CORE_16_SKILL_KEYS) for p in starters])
                    for p in starters:
                        if (p.get("name") or "").lower() in protected_set:
                            continue
                        cur = _player_skill_avg(p, CORE_16_SKILL_KEYS)
                        if mode == "floor":
                            if cur >= target_floor:
                                continue
                            desired = cur + (target_floor - cur) * strength_pct
                        else:
                            desired = cur + (smooth_target - team_avg) * strength_pct
                        old_a, new_a = self._god_set_player_target_avg(p, desired)
                        if abs(new_a - old_a) >= 0.02:
                            changes.append({"target": p["name"], "team": t["name"], "detail": f"Avg skill {old_a} -> {new_a}"})
            summary_lines.append(f"Adjusted {len(changes)} starter(s) across {len(targets)} teams ({scope}, mode={mode}).")

        elif action == "nerf_superteam_keep_stars":
            tid = _safe_int(params.get("teamId"))
            if not tid and before_snap["teamsList"]:
                tid = before_snap["teamsList"][0]["teamId"]
            team = self._team_lookup().get(tid)
            if not team:
                raise ValueError(f"Team #{tid} not found.")
            target_avg = max(10.0, min(19.5, float(params.get("targetAvg", 16.2))))
            cap_non = max(10.0, min(20.0, float(params.get("capNonProtected", 17.2))))
            starters = [p_lookup[_safe_int(c.get("playerId"))] for c in p_by_team.get(tid, []) if not c.get("benched") and _safe_int(c.get("playerId")) in p_lookup]
            prot_players = [p for p in starters if (p.get("name") or "").lower() in protected_set]
            edit_players = [p for p in starters if (p.get("name") or "").lower() not in protected_set]
            if not edit_players:
                raise ValueError("No unprotected starters left on this team to adjust.")
            prot_sum = sum(_player_skill_avg(p, CORE_16_SKILL_KEYS) for p in prot_players)
            desired_edit_mean = (target_avg * len(starters) - prot_sum) / len(edit_players)
            cur_edit_mean = _avg([_player_skill_avg(p, CORE_16_SKILL_KEYS) for p in edit_players])
            shift = desired_edit_mean - cur_edit_mean
            for p in edit_players:
                cur = _player_skill_avg(p, CORE_16_SKILL_KEYS)
                old_a, new_a = self._god_set_player_target_avg(p, cur + shift, max_skill_cap=cap_non)
                changes.append({"target": p["name"], "team": team["name"], "detail": f"Teammate smoothed {old_a} -> {new_a}"})
            for pp in prot_players:
                changes.append({"target": pp["name"], "team": team["name"], "detail": f"PROTECTED ({round(_player_skill_avg(pp, CORE_16_SKILL_KEYS), 2)} avg untouched)"})
            summary_lines.append(f"Smoothed {team['name']} teammates around protected star(s): {', '.join(p['name'] for p in prot_players) or 'None'}.")

        elif action == "fix_ai_sabotage":
            scope = str(params.get("scope", "top20"))
            fix_bench = bool(params.get("fixBench", True))
            sync_langs = bool(params.get("syncLanguages", True))
            min_staff = float(params.get("minStaffSkill", 15.0) or 0.0)
            targets = self._god_scoped_teams(scope)
            p_by_player, _, _, s_by_team = self._contract_maps()
            for t in targets:
                tid = _safe_int(t.get("id"))
                pcs = p_by_team.get(tid, [])
                if fix_bench and len(pcs) >= 5:
                    pcs_sorted = sorted(pcs, key=lambda c: -_player_skill_avg(p_lookup.get(_safe_int(c.get("playerId")), {}), CORE_16_SKILL_KEYS))
                    swapped = False
                    for idx, c in enumerate(pcs_sorted):
                        should_bench = idx >= 5
                        if bool(c.get("benched")) != should_bench:
                            c["benched"] = should_bench
                            swapped = True
                    if swapped:
                        changes.append({"target": "Starting 5", "team": t["name"], "detail": "Set top-5 highest-skill players as active starters"})
                if sync_langs:
                    main_lid = _safe_int((t.get("teamCohesion") or {}).get("mainLanguage"), 13) or 13
                    for c in pcs:
                        if c.get("benched"):
                            continue
                        p = p_lookup.get(_safe_int(c.get("playerId")))
                        if not p:
                            continue
                        langs = p.setdefault("languagesSpoken", [])
                        entry = next((lg for lg in langs if _safe_int(lg.get("languageId")) == main_lid), None)
                        if entry and _safe_int(entry.get("languageSkill")) < 15:
                            entry["languageSkill"] = 16
                            entry["limit"] = max(16, _safe_int(entry.get("limit"), 16))
                            changes.append({"target": p["name"], "team": t["name"], "detail": f"Boosted {gd.LANGUAGES.get(main_lid, 'Lang')} fluency >=16"})
                        elif not entry:
                            langs.append({"languageId": main_lid, "languageSkill": 16, "limit": 20, "progress": 0.0})
                            changes.append({"target": p["name"], "team": t["name"], "detail": f"Added fluent {gd.LANGUAGES.get(main_lid, 'Lang')}"})
                if min_staff > 0:
                    for sc in s_by_team.get(tid, []):
                        so = s_lookup.get(_safe_int(sc.get("staffId")))
                        if not so:
                            continue
                        cur_s = _staff_skill_avg(so)
                        if cur_s < min_staff:
                            delta_s = min_staff - cur_s
                            ss = so.setdefault("skills", {})
                            for k in STAFF_SKILL_KEYS:
                                ss[k] = round(max(1.0, min(20.0, _safe_float(ss.get(k, 10.0), 10.0) + delta_s)), 2)
                            changes.append({"target": so.get("name", "Staff"), "team": t["name"], "detail": f"Staff avg {round(cur_s, 2)} -> {round(_staff_skill_avg(so), 2)}"})
            summary_lines.append(f"Applied {len(changes)} roster/language/staff fixes across {scope}.")

        elif action == "rebalance_economy":
            scope = str(params.get("scope", "top20"))
            min_bal = _safe_int(params.get("minBalance"), 1500000)
            max_cap = _safe_int(params.get("maxBalanceCap"), 0)
            min_own_tier = max(0, min(20, _safe_int(params.get("minOwnerTier"), 0)))
            targets = self._god_scoped_teams(scope)
            for t in targets:
                fin = t.setdefault("teamFinances", {})
                bal = _safe_int(fin.get("currentBalance"), 0)
                if min_bal > 0 and bal < min_bal:
                    fin["currentBalance"] = min_bal
                    changes.append({"target": "Starting Balance", "team": t["name"], "detail": f"${bal:,} -> ${min_bal:,}"})
                if min_own_tier > 0 and _safe_float(fin.get("ownerContribution"), 1) < min_own_tier:
                    old_t = _safe_float(fin.get("ownerContribution"), 1)
                    fin["ownerContribution"] = min_own_tier
                    changes.append({"target": "Owner Tier", "team": t["name"], "detail": f"Tier {old_t} -> Tier {min_own_tier}"})
            if max_cap > 0:
                for t in self._god_scoped_teams("top30"):
                    fin = t.setdefault("teamFinances", {})
                    bal = _safe_int(fin.get("currentBalance"), 0)
                    if bal > max_cap:
                        fin["currentBalance"] = max_cap
                        changes.append({"target": "Wealth Cap", "team": t["name"], "detail": f"Capped ${bal:,} -> ${max_cap:,}"})
            summary_lines.append(f"Rebalanced DB finances & owner tiers ({len(changes)} updates).")

        elif action == "inject_wonderkids":
            cnt = max(1, min(25, _safe_int(params.get("count"), 10)))
            age_lo = max(15, min(21, _safe_int(params.get("minAge"), 16)))
            age_hi = max(age_lo, min(22, _safe_int(params.get("maxAge"), 18)))
            base_sk = max(6.0, min(18.5, _safe_float(params.get("baseSkill"), 13.5)))
            pot_target = max(int(round(base_sk)), min(20, _safe_int(params.get("potTarget"), 19)))
            use_cp = bool(params.get("useStartingPotential", True))
            cp_val = max(50, min(275, _safe_int(params.get("startingPotential"), 255)))
            assign_mode = str(params.get("assignMode", "free_agents"))
            nation_mode = str(params.get("nationMode", "diverse_pro"))
            nation_pools = {
                "eu": [27, 93, 34, 36, 78, 33, 70, 66, 91, 79, 26],
                "cis": [82, 99, 51, 12, 35, 53, 55, 31],
                "americas": [16, 102, 18, 5, 19, 103],
                "asia": [62, 20, 90, 98, 7, 67, 43],
            }
            nat_choices = nation_pools.get(nation_mode) or (nation_pools["eu"] + nation_pools["cis"] + nation_pools["americas"] + nation_pools["asia"])
            handles = ["kaze", "nyx", "r0nin", "vex", "z3n", "koda", "orion", "mizu", "falk", "draco", "lyra", "tarkov", "volt", "haze", "flint", "nexaR", "solis", "kr1s", "axel", "bastian", "vortex", "juno", "skye", "torin", "rexx"]
            presets = ["awper", "entry", "rifler", "igl", "support"]
            existing_names = {(p.get("name") or "").lower() for p in self.db.get("players", [])}
            top_teams = self._god_scoped_teams("top20")
            for idx in range(cnt):
                bh = handles[idx % len(handles)]
                cand = bh if bh.lower() not in existing_names else f"{bh}{random.randint(10, 99)}"
                existing_names.add(cand.lower())
                preset = presets[idx % len(presets)]
                tid = _safe_int(top_teams[idx % len(top_teams)]["id"]) if (assign_mode == "top20_bench" and top_teams) else 0
                created = self.create_player({
                    "name": cand,
                    "age": random.randint(age_lo, age_hi),
                    "nation": random.choice(nat_choices),
                    "preset": preset,
                    "baseSkill": round(base_sk + random.uniform(-0.4, 0.4), 1),
                    "potentialTarget": pot_target,
                    "useStartingPotential": use_cp,
                    "startingPotential": cp_val if use_cp else 0,
                    "teamId": tid,
                    "benched": tid > 0,
                    "salaryYear": 120000 if tid > 0 else 0,
                })
                tname = self._team_lookup().get(tid, {}).get("name", "Free Agent") if tid else "Free Agent"
                changes.append({"target": f"{created['player']['name']} ({preset})", "team": tname, "detail": f"Age {created['player']['age']}, Pot {cp_val if use_cp else pot_target}"})
            summary_lines.append(f"Spawned {cnt} U21 {nation_mode} wonderkids ({assign_mode}).")

        else:
            raise ValueError(f"Unknown God Mode action: {action}")

        self.dirty_db = True
        after_snap = self._god_parity_snapshot()
        return {
            "ok": True,
            "dryRun": False,
            "action": action,
            "summary": " ".join(summary_lines),
            "changeCount": len(changes),
            "changes": changes[:150],
            "before": {k: v for k, v in before_snap.items() if k != "teamsList"},
            "after": {k: v for k, v in after_snap.items() if k != "teamsList"},
        }

    def batch_scale_weapons(self, action: str, weapon_type: int | None = None, pct: float = 10.0) -> dict[str, Any]:
        """Batch balance utility for Weapons Modding."""
        if not self.weapons_data:
            raise ValueError("No Weapons pack loaded.")
        weapons = self.weapons_data.get("weapons", [])
        mult = 1.0 + (pct / 100.0)
        for w in weapons:
            if weapon_type is not None and _safe_int(w.get("type")) != weapon_type:
                continue
            if action == "scale_price":
                if _safe_int(w.get("price")) > 0:
                    w["price"] = max(50, int(round(_safe_int(w["price"]) * mult / 50.0) * 50))
            elif action == "scale_damage":
                w["damage"] = max(1, int(round(_safe_float(w["damage"]) * mult)))
            elif action == "scale_armor_pen":
                w["armorMultiplier"] = round(max(0.1, min(1.0, _safe_float(w["armorMultiplier"]) * mult)), 4)
            elif action == "scale_accuracy":
                w["accuracy"] = round(max(1.0, min(60.0, _safe_float(w["accuracy"]) * mult)), 2)
        self.dirty_weapons = True
        return self.get_weapons_and_analysis()


def _default_stages_for_tier(template: int, tier_code: str) -> list[dict[str, Any]]:
    tier = (tier_code or "S").upper()
    if tier in ("MAJOR", "T5"):
        p1, p2 = 50000, 500000
        parts1 = 16
        days1 = [1, 2, 3, 4, 5]
        venue1, venue2 = 1, 2
    elif tier in ("S", "T4"):
        p1, p2 = 25000, 250000
        parts1 = 16
        days1 = [3, 4, 5, 6, 7]
        venue1, venue2 = 1, 2
    elif tier in ("A", "T3"):
        p1, p2 = 5000, 50000
        parts1 = 16
        days1 = [1, 2, 3]
        venue1, venue2 = 1, 2
    else:
        p1, p2 = 0, 10000
        parts1 = 16
        days1 = [1, 2, 3]
        venue1, venue2 = 0, 0

    adv_prizes = [{"position": pos, "money": max(0, p1 // pos) if pos <= 4 else 0, "progressType": 1 if pos <= 8 else 0, "stickerMoneyPercentages": 0.0} for pos in range(1, parts1 + 1)]
    playoff_prizes = [{"position": pos, "money": max(1000, p2 // pos), "progressType": 0, "stickerMoneyPercentages": 0.0} for pos in range(1, 9)]
    empty_dt = {"hour": 0, "day": 0, "month": 0, "year": 0}
    return [
        {
            "id": 0, "parentId": 0, "parentTemplate": template, "stage": 1,
            "name": "GROUPS__CONTEXT_TOURNAMENT_STAGE_NAME",
            "numberOfParticipants": parts1, "groups": 1, "formatType": 2,
            "mapsPerMatch": 3, "matchSessionSlot": 3,
            "matchesGenerated": False, "matchesPopulated": False,
            "daysOfWeekPlayed": days1,
            "startDatetime": copy.deepcopy(empty_dt), "endDatetime": copy.deepcopy(empty_dt),
            "participants": [], "venue": venue1, "location": 0, "cityIndex": 0,
            "regionEligibility": 3, "openSignup": tier in ("B", "C", "T2", "T1"),
            "outdated": False, "invitationDate": copy.deepcopy(empty_dt),
            "requiredWins": 3, "maxLosses": 2, "prizes": adv_prizes, "participationFee": 0,
        },
        {
            "id": 0, "parentId": 0, "parentTemplate": template, "stage": 2,
            "name": "PLAYOFFS__CONTEXT_TOURNAMENT_STAGE_NAME",
            "numberOfParticipants": 8, "groups": 1, "formatType": 0,
            "mapsPerMatch": 3, "matchSessionSlot": 3,
            "matchesGenerated": False, "matchesPopulated": False,
            "daysOfWeekPlayed": [5, 6, 7],
            "startDatetime": copy.deepcopy(empty_dt), "endDatetime": copy.deepcopy(empty_dt),
            "participants": [], "venue": venue2, "location": 0, "cityIndex": 0,
            "regionEligibility": 3, "openSignup": False,
            "outdated": False, "invitationDate": copy.deepcopy(empty_dt),
            "requiredWins": 0, "maxLosses": 0, "prizes": playoff_prizes, "participationFee": 0,
        },
    ]


def _normalize_stage_dict(raw: dict[str, Any], template: int, default_stage_num: int) -> dict[str, Any]:
    empty_dt = {"hour": 0, "day": 0, "month": 0, "year": 0}
    dows = sorted({int(d) for d in (raw.get("daysOfWeekPlayed") or [1, 2, 3]) if 1 <= int(d) <= 7}) or [1, 2, 3]
    prizes = raw.get("prizes") or []
    return {
        "id": 0,
        "parentId": 0,
        "parentTemplate": template,
        "stage": max(1, _safe_int(raw.get("stage"), default_stage_num)),
        "name": str(raw.get("name") or "GROUPS__CONTEXT_TOURNAMENT_STAGE_NAME"),
        "numberOfParticipants": max(2, _safe_int(raw.get("numberOfParticipants"), 16)),
        "groups": max(1, _safe_int(raw.get("groups"), 1)),
        "formatType": _safe_int(raw.get("formatType"), 0),
        "mapsPerMatch": _safe_int(raw.get("mapsPerMatch"), 3),
        "matchSessionSlot": _safe_int(raw.get("matchSessionSlot"), 3),
        "matchesGenerated": False,
        "matchesPopulated": False,
        "daysOfWeekPlayed": dows,
        "startDatetime": copy.deepcopy(raw.get("startDatetime") or empty_dt),
        "endDatetime": copy.deepcopy(raw.get("endDatetime") or empty_dt),
        "participants": [],
        "venue": _safe_int(raw.get("venue"), 0),
        "location": _safe_int(raw.get("location"), 0),
        "cityIndex": _safe_int(raw.get("cityIndex"), 0),
        "regionEligibility": _safe_int(raw.get("regionEligibility"), 3),
        "openSignup": bool(raw.get("openSignup", False)),
        "outdated": bool(raw.get("outdated", False)),
        "invitationDate": copy.deepcopy(raw.get("invitationDate") or empty_dt),
        "requiredWins": _safe_int(raw.get("requiredWins"), 3),
        "maxLosses": _safe_int(raw.get("maxLosses"), 2),
        "prizes": [
            {
                "position": _safe_int(p.get("position"), idx + 1),
                "money": _safe_int(p.get("money"), 0),
                "progressType": _safe_int(p.get("progressType"), 0),
                "stickerMoneyPercentages": _safe_float(p.get("stickerMoneyPercentages"), 0.0),
            }
            for idx, p in enumerate(prizes)
        ],
        "participationFee": _safe_int(raw.get("participationFee"), 0),
    }
