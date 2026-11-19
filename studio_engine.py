"""Next-generation Save Studio engine extending CS Manager SaveSession."""

from __future__ import annotations

import copy
import datetime as dt
import json
import math
import zlib
from pathlib import Path
from typing import Any

EDITOR_DIR = Path(__file__).resolve().parent

import gamedata as gd
from save_engine import (
    BACKUPS_DIR,
    DEFAULT_SAVES_DIR,
    SaveSession,
    _clamp,
    _player_avg_skill,
    _staff_avg_skill,
    discover_save_files,
)

STUDIO_BACKUPS_DIR = BACKUPS_DIR

_MUTABLE_KEYS = (
    "profile",
    "datetime",
    "teams",
    "players",
    "playerContracts",
    "staffers",
    "staffContracts",
    "playerRelationships",
    "transferHistories",
    "tournaments",
    "emails",
    "weapons",
    "sponsors",
)

_SKILL_BY_ID = {s["id"]: s for s in gd.PLAYER_SKILLS}
_MECH_IDS = (1, 2, 3, 4, 5, 6)
_WEAP_IDS = (7, 8, 9, 10)
_MENTAL_IDS = (11, 12, 13, 14, 15, 16, 17, 18)
_PRACTICAL_IDS = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 17)

_WEAPON_TYPES = {0: "Pistol", 1: "SMG", 2: "Rifle", 3: "Sniper"}
_AWARD_TYPES = {0: "MVP", 1: "Event Win", 2: "EVP", 3: "Top 20"}
_BID_STATUS_LABELS = {
    0: "Shortlisted / Evaluating",
    1: "Bid Made",
    2: "Bid Accepted",
    3: "Bid Sent",
    4: "Contract Offered",
    5: "Contract Accepted",
    6: "Awaiting Final Response",
    7: "Failed Bid / Player Cooldown",
    8: "Team Cooldown",
}
_URGENCY_LABELS = {0: "High", 1: "Medium", 2: "Low", 3: "Backup"}
_ROLE_INTEREST_LABELS = {0: "Any", 1: "IGL", 2: "Sniper", 3: "Rifler"}


def _player_potential_avg(player: dict[str, Any]) -> float:
    pot = player.get("potential") or {}
    vals = pot.get("m_Values") or []
    keys = pot.get("m_Keys") or []
    if not vals:
        return _player_avg_skill(player)
    paired = [float(v) for k, v in zip(keys, vals) if int(k) in _PRACTICAL_IDS]
    if paired:
        return round(sum(paired) / len(paired), 2)
    return round(sum(float(v) for v in vals) / len(vals), 2)


def _player_burnout_total(player: dict[str, Any]) -> float:
    bo = player.get("burnout") or {}
    return round(float(bo.get("burnoutFromPractice", 0.0) or 0.0) + float(bo.get("burnoutFromMatches", 0.0) or 0.0), 4)


def _player_mood_score(player: dict[str, Any]) -> float:
    m = player.get("mood") or {}
    base = (
        float(m.get("moodFromTournamentReputation", 0.0) or 0.0)
        + float(m.get("moodFromBurnout", 0.0) or 0.0)
        + float(m.get("moodFromRelationships", 0.0) or 0.0)
        + float(m.get("moodFromDialog", 0.0) or 0.0)
        + float(m.get("moodFromPersonality", 0.0) or 0.0)
        + float(m.get("moodFromPracticeDialog", 0.0) or 0.0)
    )
    match_sum = 0.0
    match_w = 0.0
    for mm in m.get("moodsFromMatches") or []:
        rel = float(mm.get("relevance", 0.0) or 0.0)
        val = (
            float(mm.get("moodFromResult", 0.0) or 0.0)
            + float(mm.get("moodFromRoles", 0.0) or 0.0)
            + float(mm.get("moodFromPositions", 0.0) or 0.0)
            + float(mm.get("moodFromMaps", 0.0) or 0.0)
        )
        match_sum += val * rel
        match_w += rel
    tourn_sum = sum(float(tm.get("moodEffect", 0.0) or 0.0) * float(tm.get("relevance", 0.0) or 0.0) for tm in (m.get("moodsFromTournaments") or []))
    return round(base + (match_sum / max(match_w, 1.0)) + tourn_sum * 0.1, 2)


class StudioSession(SaveSession):
    """SaveSession extended with Snapshots, Career HQ, Growth Lab, Sandbox, Award Patcher, Market Radar, Weapons & Save Diff."""

    def __init__(self) -> None:
        super().__init__()
        self._snapshots: list[dict[str, Any]] = []
        self._snap_seq: int = 0
        self._growth_cache: dict[str, Any] | None = None

    def rebuild_indices(self) -> None:
        super().rebuild_indices()
        self._growth_cache = None

    def summary(self) -> dict[str, Any]:
        res = super().summary()
        res["loaded"] = self.data is not None
        res["fileName"] = res.get("filename", "")
        res["snapshotCount"] = len(self._snapshots)
        return res

    def list_teams(self, q: str = "") -> list[dict[str, Any]]:
        rows = super().list_teams(q=q)
        if self.data is None:
            return rows
        starters_by_tid: dict[int, list[float]] = {}
        for c in self.data.get("playerContracts", {}).get("playerContracts", []):
            if c.get("benched"):
                continue
            tid = int(c.get("teamId", 0) or 0)
            p = self.players_by_id.get(int(c.get("playerId", 0) or 0))
            if tid and p:
                starters_by_tid.setdefault(tid, []).append(self._player_practical_avg(p))
        for r in rows:
            tid = r["id"]
            t_obj = self.teams_by_id.get(tid, {})
            rh = t_obj.get("rankingHistory") or []
            r["worldRank"] = int(rh[-1]) if rh else 0
            avgs = starters_by_tid.get(tid, [])
            r["avgSkill"] = round(sum(avgs) / len(avgs), 2) if avgs else 0.0
        rows.sort(key=lambda r: (r["worldRank"] == 0, r["worldRank"] if r["worldRank"] > 0 else 9999, -r["avgSkill"], r["name"].lower()))
        return rows

    # ------------------------------------------------------------------
    # Save Load / Undo Time Machine Snapshots
    # ------------------------------------------------------------------

    def load(self, file_path: str | Path) -> dict[str, Any]:
        super().load(file_path)
        self._reset_snapshots("Initial Load")
        return self.summary()

    def load_upload(self, filename: str, raw_text: str) -> dict[str, Any]:
        super().load_upload(filename, raw_text)
        self._reset_snapshots("Initial Upload Load")
        return self.summary()

    def _reset_snapshots(self, label: str) -> None:
        self._snapshots = []
        self._snap_seq = 0
        if self.data is not None:
            self.create_snapshot(label)

    def create_snapshot(self, label: str = "Manual Checkpoint") -> dict[str, Any]:
        if self.data is None:
            raise RuntimeError("No save file is currently loaded.")
        subset = {k: self.data[k] for k in _MUTABLE_KEYS if k in self.data}
        raw = json.dumps(subset, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        blob = zlib.compress(raw, level=1)
        self._snap_seq += 1
        meta = {
            "id": self._snap_seq,
            "label": str(label or f"Checkpoint #{self._snap_seq}").strip()[:90],
            "createdAt": dt.datetime.now().strftime("%H:%M:%S"),
            "sizeKb": round(len(blob) / 1024.0, 1),
            "dirty": bool(self.dirty),
        }
        self._snapshots.append({**meta, "blob": blob})
        if len(self._snapshots) > 15:
            self._snapshots.pop(0)
        return meta

    def list_snapshots(self) -> list[dict[str, Any]]:
        return [
            {k: v for k, v in s.items() if k != "blob"}
            for s in reversed(self._snapshots)
        ]

    def restore_snapshot(self, snap_id: int) -> dict[str, Any]:
        if self.data is None:
            raise RuntimeError("No save file is currently loaded.")
        target = next((s for s in self._snapshots if s["id"] == int(snap_id)), None)
        if not target:
            raise ValueError(f"Snapshot #{snap_id} not found.")
        restored = json.loads(zlib.decompress(target["blob"]).decode("utf-8"))
        for k, v in restored.items():
            self.data[k] = v
        self.rebuild_indices()
        self.dirty = True
        return {"restored": {k: v for k, v in target.items() if k != "blob"}, "summary": self.summary()}

    def create_disk_backup(self) -> dict[str, Any]:
        if self.data is None:
            raise RuntimeError("No save file is currently loaded.")
        STUDIO_BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
        stem = self.path.stem if self.path else Path(self.virtual_name or "save").stem
        stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        bpath = STUDIO_BACKUPS_DIR / f"{stem}_{stamp}.json"
        raw = json.dumps(self.data, separators=(",", ":"), ensure_ascii=False)
        bpath.write_text(raw, encoding="utf-8")
        return {"backupPath": str(bpath), "sizeMb": round(bpath.stat().st_size / (1024 * 1024), 2)}

    # ------------------------------------------------------------------
    # God Mode: Fast Selective Dry-Run + All-Team Support + Blank Star Box
    # ------------------------------------------------------------------

    def get_god_mode_state(self) -> dict[str, Any]:
        if self.data is None:
            return {"loaded": False}
        snap = self._god_parity_snapshot()
        return {
            "loaded": True,
            "snapshot": {k: v for k, v in snap.items() if k != "teamsList"},
            "teams": [
                {
                    "teamId": r["teamId"],
                    "name": r["name"],
                    "worldRank": r["worldRank"],
                    "isUserTeam": r["isUserTeam"],
                    "avgSkill": r["avgSkill"],
                    "weakestFloor": r["weakestFloor"],
                }
                for r in snap["teamsList"]
            ],
            "defaultProtectedStar": "",
        }

    def run_god_mode(self, action: str, params: dict[str, Any], dry_run: bool = False) -> dict[str, Any]:
        if self.data is None:
            raise RuntimeError("No save file is currently loaded.")
        if dry_run:
            # Share immutable massive tables (matches, playerSkillHistories, playerCareerStats, etc.)
            # and deep-copy only mutable keys for <0.5s dry-runs even on 75MB saves.
            clone = StudioSession()
            clone_data: dict[str, Any] = {}
            mutable_set = set(_MUTABLE_KEYS)
            for k, v in self.data.items():
                clone_data[k] = copy.deepcopy(v) if k in mutable_set else v
            clone.data = clone_data
            clone.path = self.path
            clone.virtual_name = self.virtual_name
            clone.rebuild_indices()
            res = SaveSession.run_god_mode(clone, action, params, dry_run=False)
            res["dryRun"] = True
            return res

        self.create_snapshot(f"Before God Mode ({action})")
        return SaveSession.run_god_mode(self, action, params, dry_run=False)

    # ------------------------------------------------------------------
    # Global Command Palette Search
    # ------------------------------------------------------------------

    def global_search(self, q: str, limit: int = 8) -> dict[str, Any]:
        if self.data is None:
            return {"players": [], "teams": [], "staff": [], "tournaments": []}
        ql = q.strip().lower()
        lim = max(3, min(25, int(limit or 8)))

        p_hits = []
        for p in self.data["players"]["players"]:
            name = p.get("name", "")
            pid = int(p["id"])
            if not ql or ql in name.lower() or ql == str(pid):
                c = self.player_contract_by_pid.get(pid)
                tid = c["teamId"] if c else 0
                tname = self.teams_by_id.get(tid, {}).get("name", "Free Agent") if tid else "Free Agent"
                p_hits.append({
                    "id": pid,
                    "name": name,
                    "subtitle": f"{tname} · {_player_avg_skill(p):.2f} sk · {p.get('age', 0)}y",
                    "avgSkill": _player_avg_skill(p),
                })
        p_hits.sort(key=lambda r: (-r["avgSkill"], r["name"].lower()))

        t_hits = []
        for t in self.data["teams"]["teams"]:
            name = t.get("name", "")
            tid = int(t["id"])
            if not ql or ql in name.lower() or ql == str(tid):
                rh = t.get("rankingHistory") or []
                wr = int(rh[-1]) if rh else 0
                bal = int((t.get("teamFinances") or {}).get("currentBalance", 0) or 0)
                t_hits.append({
                    "id": tid,
                    "name": name,
                    "worldRank": wr,
                    "subtitle": f"{'#' + str(wr) if wr else 'Unranked'} · Rep {t.get('reputation', 1)} · ${bal:,}",
                })
        t_hits.sort(key=lambda r: (r["worldRank"] == 0, r["worldRank"] or 9999, r["name"].lower()))

        s_hits = []
        for s in self.data["staffers"]["staffers"]:
            name = s.get("name", "")
            sid = int(s["id"])
            if not ql or ql in name.lower() or ql == str(sid):
                c = self.staff_contract_by_sid.get(sid)
                tid = c["teamId"] if c else 0
                tname = self.teams_by_id.get(tid, {}).get("name", "Free Agent") if tid else "Free Agent"
                rname = gd.STAFF_ROLES.get(c.get("role", 0), "Staff") if c else "Free Agent"
                s_hits.append({
                    "id": sid,
                    "name": name,
                    "subtitle": f"{tname} · {rname} · {_staff_avg_skill(s):.2f} sk",
                    "avgSkill": _staff_avg_skill(s),
                })
        s_hits.sort(key=lambda r: (-r["avgSkill"], r["name"].lower()))

        tr_hits = []
        for t in reversed(self.data.get("tournaments", {}).get("tournaments", [])):
            name = t.get("name", "")
            tid = int(t["id"])
            if not ql or ql in name.lower() or ql == str(tid):
                pa_len = len([x for x in (t.get("playersAwarded") or []) if int(x or 0) > 0])
                tr_hits.append({
                    "id": tid,
                    "name": name,
                    "subtitle": f"Rep {t.get('reputation', 1)} · {pa_len} saved awards",
                    "rep": int(t.get("reputation", 1) or 1),
                })
        tr_hits.sort(key=lambda r: (-r["rep"], -r["id"]))

        return {
            "players": p_hits[:lim],
            "teams": t_hits[:lim],
            "staff": s_hits[:lim],
            "tournaments": tr_hits[:lim],
        }

    # ------------------------------------------------------------------
    # Career HQ & Manager Console
    # ------------------------------------------------------------------

    def get_career_hq(self) -> dict[str, Any]:
        if self.data is None:
            return {"loaded": False}
        prof = self.data.get("profile") or {}
        msid = int(prof.get("staffId", 0) or 0)
        mtid = int(prof.get("team", 0) or 0)
        mstaff = self.staff_by_id.get(msid)
        mcon = self.staff_contract_by_sid.get(msid)
        team = self.teams_by_id.get(mtid)

        team_detail = None
        if team:
            pcs = self.get_team_player_contracts(mtid)
            starters = [self.players_by_id[c["playerId"]] for c in pcs if not c.get("benched") and c["playerId"] in self.players_by_id]
            benched = [self.players_by_id[c["playerId"]] for c in pcs if c.get("benched") and c["playerId"] in self.players_by_id]
            rh = team.get("rankingHistory") or []
            cur_rank = int(rh[-1]) if rh else 0
            all_p = starters + benched
            team_detail = {
                "id": mtid,
                "name": team.get("name", ""),
                "nation": team.get("nation", 0),
                "nationName": gd.NATIONS.get(team.get("nation", 0), ""),
                "reputation": team.get("reputation", 1),
                "professionalStatus": team.get("professionalStatus", 2),
                "balance": int((team.get("teamFinances") or {}).get("currentBalance", 0) or 0),
                "worldRank": cur_rank,
                "rankingHistory": [int(x) for x in rh[-36:]],
                "avgSkill": round(sum(self._player_practical_avg(p) for p in starters) / max(len(starters), 1), 2) if starters else 0.0,
                "avgBurnout": round(sum(_player_burnout_total(p) for p in all_p) / max(len(all_p), 1), 3) if all_p else 0.0,
                "avgMood": round(sum(_player_mood_score(p) for p in all_p) / max(len(all_p), 1), 2) if all_p else 0.0,
                "starterCount": len(starters),
                "benchedCount": len(benched),
                "sponsors": copy.deepcopy(team.get("sponsors") or []),
                "jobSecurity": copy.deepcopy(team.get("jobSecurity") or {}),
                "facilities": {
                    k: int(team.get(k, 0) or 0)
                    for k in ("coffeeMachine", "cable", "ventilation", "recreation", "branding", "academy", "academyFocus")
                },
                "trophiesCount": len(team.get("trophyHistories") or []),
                "recentTrophies": list(reversed((team.get("trophyHistories") or [])[-8:])),
                "roster": [
                    {
                        "playerId": p["id"],
                        "name": p.get("name", ""),
                        "age": p.get("age", 0),
                        "avgSkill": _player_avg_skill(p),
                        "burnout": _player_burnout_total(p),
                        "mood": _player_mood_score(p),
                        "benched": bool(self.player_contract_by_pid.get(p["id"], {}).get("benched")),
                        "salaryYear": int(self.player_contract_by_pid.get(p["id"], {}).get("salaryYear", 0) or 0),
                    }
                    for p in starters + benched
                ],
            }

        all_teams = self.list_teams()
        return {
            "loaded": True,
            "datetime": copy.deepcopy(self.data.get("datetime", {})),
            "profile": {
                "staffId": msid,
                "name": prof.get("name", mstaff.get("name", "") if mstaff else ""),
                "age": int(prof.get("age", mstaff.get("age", 30) if mstaff else 30) or 30),
                "nation": int(prof.get("nation", mstaff.get("nation", 1) if mstaff else 1) or 1),
                "teamId": mtid,
            },
            "managerStaff": copy.deepcopy(mstaff) if mstaff else None,
            "managerContract": copy.deepcopy(mcon) if mcon else None,
            "team": team_detail,
            "allTeams": all_teams,
            "recentTransfers": self.list_transfers(limit=15),
        }

    def update_career_hq(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.data is None:
            raise RuntimeError("No save file is currently loaded.")
        self.create_snapshot("Before Career HQ Update")
        prof = self.data.setdefault("profile", {})
        msid = int(prof.get("staffId", 0) or 0)
        mtid = int(prof.get("team", 0) or 0)

        p_in = payload.get("profile") or {}
        if "name" in p_in and str(p_in["name"]).strip():
            prof["name"] = str(p_in["name"]).strip()
        if "age" in p_in:
            prof["age"] = int(_clamp(int(p_in["age"]), 18, 90))
        if "nation" in p_in:
            prof["nation"] = int(p_in["nation"])

        mstaff = self.staff_by_id.get(msid)
        if mstaff:
            for k in ("name", "age", "nation"):
                if k in prof:
                    mstaff[k] = prof[k]
            ms_in = payload.get("managerSkills") or {}
            if isinstance(ms_in, dict) and ms_in:
                skills_src = ms_in.get("skills") if isinstance(ms_in.get("skills"), dict) else ms_in
                mstaff.setdefault("skills", {}).update(
                    {
                        k: round(float(_clamp(float(v), 1.0, 20.0)), 2)
                        for k, v in skills_src.items()
                        if isinstance(v, (int, float, str))
                    }
                )

        mc_in = payload.get("managerContract") or {}
        mcon = self.staff_contract_by_sid.get(msid)
        if mcon and mc_in:
            if "salaryYear" in mc_in:
                mcon["salaryYear"] = max(0, int(mc_in["salaryYear"]))
            if "endDate" in mc_in and isinstance(mc_in["endDate"], dict):
                mcon["endDate"].update({k: int(v) for k, v in mc_in["endDate"].items() if k in ("year", "month", "day", "hour")})

        js_in = payload.get("jobSecurity") or {}
        team = self.teams_by_id.get(mtid)
        if team and js_in:
            js = team.setdefault("jobSecurity", {})
            for fk in (
                "securityFromLeague", "securityFromChampionship", "securityFromRanking",
                "securityFromBudget", "securityFromLongevity", "securityFromSquadComposition",
                "securityFromPreviousSeason",
            ):
                if fk in js_in:
                    js[fk] = float(_clamp(float(js_in[fk]), 0.0, 1.0))
            for ik in ("gracePeriod", "leagueGoal", "championshipGoal", "rankingGoal"):
                if ik in js_in:
                    js[ik] = int(js_in[ik])

        self.dirty = True
        return self.get_career_hq()

    def switch_managed_team(self, target_team_id: int, swap_coach: bool = False) -> dict[str, Any]:
        if self.data is None:
            raise RuntimeError("No save file is currently loaded.")
        tid = int(target_team_id)
        if tid not in self.teams_by_id:
            raise ValueError(f"Target team #{tid} not found.")
        self.create_snapshot(f"Before Switch Club -> {self.teams_by_id[tid].get('name', tid)}")

        prof = self.data.setdefault("profile", {})
        old_tid = int(prof.get("team", 0) or 0)
        msid = int(prof.get("staffId", 0) or 0)
        if old_tid == tid:
            return self.get_career_hq()

        scs = self.data["staffContracts"]["staffContracts"]
        new_scs = []
        displaced_coaches: list[dict[str, Any]] = []
        mgr_contract: dict[str, Any] | None = None

        for c in scs:
            csid = int(c.get("staffId", 0) or 0)
            ctid = int(c.get("teamId", 0) or 0)
            crole = int(c.get("role", -1))
            if csid == msid and msid > 0:
                mgr_contract = c
                continue
            if ctid == tid and crole == 0:
                displaced_coaches.append(c)
                continue
            new_scs.append(c)

        if swap_coach and old_tid > 0:
            for dc in displaced_coaches:
                dc["teamId"] = old_tid
                new_scs.append(dc)

        cur_dt = self.data.get("datetime", {"year": 2026, "month": 7, "day": 1, "hour": 0})
        if mgr_contract is None and msid > 0:
            mgr_contract = {
                "salaryYear": 500000,
                "endDate": {"hour": 0, "day": 1, "month": 1, "year": int(cur_dt.get("year", 2026)) + 3},
                "teamId": tid,
                "staffId": msid,
                "role": 0,
                "rejectAllStaffOffers": False,
            }
        if mgr_contract is not None:
            mgr_contract["teamId"] = tid
            mgr_contract["role"] = 0
            new_scs.append(mgr_contract)

        self.data["staffContracts"]["staffContracts"] = new_scs
        prof["team"] = tid
        prof["nextMatchId"] = 0
        self.rebuild_indices()
        self.dirty = True
        return self.get_career_hq()

    # ------------------------------------------------------------------
    # Enhanced Player Pro & Team Pro Operations
    # ------------------------------------------------------------------

    def get_player_pro(self, player_id: int) -> dict[str, Any]:
        base = self.get_player(player_id)
        p = self.players_by_id[player_id]
        tmpl_names, _, _ = self._stats_lookups()
        awards_out = []
        for idx, aw in enumerate(p.get("playerAwards") or []):
            tpl = int(aw.get("tournamentTemplate", 0) or 0)
            tid_a = int(aw.get("teamId", 0) or 0)
            atype = int(aw.get("type", 0) or 0)
            awards_out.append({
                "index": idx,
                "type": atype,
                "typeLabel": _AWARD_TYPES.get(atype, f"Type {atype}"),
                "tournamentTemplate": tpl,
                "tournamentName": tmpl_names.get(tpl, f"Template #{tpl}"),
                "year": int(aw.get("year", 0) or 0),
                "month": int(aw.get("month", 0) or 0),
                "teamId": tid_a,
                "teamName": self.teams_by_id.get(tid_a, {}).get("name", "—") if tid_a else "—",
                "top20Placement": int(aw.get("top20Placement", 0) or 0),
            })

        base["pro"] = {
            "useStartingPotential": bool(p.get("useStartingPotential", False)),
            "startingPotential": int(p.get("startingPotential", 150) or 150),
            "potentialAvg": _player_potential_avg(p),
            "practicalAvg": self._player_practical_avg(p),
            "burnout": copy.deepcopy(p.get("burnout") or {"burnoutFromPractice": 0.0, "burnoutFromMatches": 0.0}),
            "totalBurnout": _player_burnout_total(p),
            "moodScore": _player_mood_score(p),
            "mood": {
                k: round(float((p.get("mood") or {}).get(k, 0.0) or 0.0), 3)
                for k in (
                    "moodFromTournamentReputation", "moodFromBurnout", "moodFromRelationships",
                    "moodFromDialog", "moodFromPersonality", "moodFromPracticeDialog",
                )
            },
            "awards": awards_out,
            "skillHistory": self.get_player_trajectory(player_id)["series"],
            "tournamentTemplates": [{"id": k, "name": v} for k, v in sorted(tmpl_names.items(), key=lambda x: x[1].lower())],
        }
        return base

    def update_player_pro(self, player_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        if self.data is None:
            raise RuntimeError("No save file is currently loaded.")
        p = self.players_by_id.get(player_id)
        if not p:
            raise ValueError(f"Player {player_id} not found.")
        self.create_snapshot(f"Before Player Edit: {p.get('name', player_id)}")
        pdata = payload.get("player") or {}
        if "useStartingPotential" in pdata:
            p["useStartingPotential"] = bool(pdata["useStartingPotential"])
        if "startingPotential" in pdata:
            p["startingPotential"] = int(_clamp(int(pdata["startingPotential"]), 50, 275))
        if "burnout" in pdata and isinstance(pdata["burnout"], dict):
            bo = p.setdefault("burnout", {"burnoutFromPractice": 0.0, "burnoutFromMatches": 0.0})
            for bk in ("burnoutFromPractice", "burnoutFromMatches"):
                if bk in pdata["burnout"]:
                    bo[bk] = float(_clamp(float(pdata["burnout"][bk]), 0.0, 1.0))
        self.update_player(player_id, payload)
        return self.get_player_pro(player_id)

    def _apply_player_wellness(self, p: dict[str, Any], reset_burnout: bool = True, max_mood: bool = True) -> None:
        if reset_burnout:
            p["burnout"] = {"burnoutFromPractice": 0.0, "burnoutFromMatches": 0.0}
            m = p.setdefault("mood", {})
            m["moodFromBurnout"] = 0.0
        if max_mood:
            m = p.setdefault("mood", {})
            m["moodFromBurnout"] = 0.0
            m["moodFromDialog"] = max(float(m.get("moodFromDialog", 0.0) or 0.0), 0.5)
            m["moodFromPracticeDialog"] = max(float(m.get("moodFromPracticeDialog", 0.0) or 0.0), 0.5)
            m["moodFromRelationships"] = max(float(m.get("moodFromRelationships", 0.0) or 0.0), 0.25)
            for mm in m.get("moodsFromMatches") or []:
                if float(mm.get("moodFromResult", 0.0) or 0.0) < 0:
                    mm["moodFromResult"] = 1.0

    def heal_player_state(self, player_id: int, reset_burnout: bool = True, max_mood: bool = True) -> dict[str, Any]:
        p = self.players_by_id.get(player_id)
        if not p:
            raise ValueError(f"Player {player_id} not found.")
        self.create_snapshot(f"Before Heal {p.get('name', player_id)}")
        self._apply_player_wellness(p, reset_burnout=reset_burnout, max_mood=max_mood)
        self.dirty = True
        return self.get_player_pro(player_id)

    def add_player_award(self, player_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        p = self.players_by_id.get(player_id)
        if not p:
            raise ValueError(f"Player {player_id} not found.")
        self.create_snapshot(f"Before Add Award: {p.get('name', player_id)}")
        c = self.player_contract_by_pid.get(player_id)
        cur_dt = self.data.get("datetime", {"year": 2026, "month": 1}) if self.data else {}
        atype = int(_clamp(int(payload.get("type", 0)), 0, 3))
        p.setdefault("playerAwards", []).append({
            "type": atype,
            "tournamentTemplate": int(payload.get("tournamentTemplate", 0) or 0),
            "year": int(payload.get("year", cur_dt.get("year", 2026)) or 2026),
            "month": int(_clamp(int(payload.get("month", cur_dt.get("month", 1)) or 1), 1, 12)),
            "teamId": int(payload.get("teamId", c["teamId"] if c else 0) or 0),
            "top20Placement": int(_clamp(int(payload.get("top20Placement", 0) or 0), 0, 20)) if atype == 3 else 0,
        })
        self.dirty = True
        return self.get_player_pro(player_id)

    def delete_player_award(self, player_id: int, award_index: int) -> dict[str, Any]:
        p = self.players_by_id.get(player_id)
        if not p:
            raise ValueError(f"Player {player_id} not found.")
        aws = p.get("playerAwards") or []
        if award_index < 0 or award_index >= len(aws):
            raise ValueError(f"Award index {award_index} out of range.")
        self.create_snapshot(f"Before Delete Award: {p.get('name', player_id)}")
        aws.pop(award_index)
        self.dirty = True
        return self.get_player_pro(player_id)

    def get_team_pro(self, team_id: int) -> dict[str, Any]:
        base = self.get_team(team_id)
        t = self.teams_by_id[team_id]
        tmpl_names, tourn_by_id, _ = self._stats_lookups()
        raw_tourns = {x["id"]: x for x in self.data.get("tournaments", {}).get("tournaments", [])}

        pcs = self.get_team_player_contracts(team_id)
        all_p = [self.players_by_id[c["playerId"]] for c in pcs if c["playerId"] in self.players_by_id]
        cooldowns = sum(1 for pi in (t.get("personInterests") or []) if int(pi.get("bidStatus", 0) or 0) in (7, 8))
        active_bids = sum(1 for pi in (t.get("personInterests") or []) if 1 <= int(pi.get("bidStatus", 0) or 0) <= 6)

        trophies = []
        for th in reversed(t.get("trophyHistories") or []):
            tid_t = int(th.get("tournamentId", 0) or 0)
            tpl_t = int(th.get("tournamentTemplate", 0) or 0)
            t_name = raw_tourns.get(tid_t, {}).get("name") or tmpl_names.get(tpl_t) or f"Tournament #{tid_t}"
            trophies.append({
                "tournamentId": tid_t,
                "name": t_name,
                "year": int(th.get("year", 0) or 0),
                "spring": bool(th.get("spring", True)),
                "players": [self.players_by_id.get(pid, {}).get("name", f"#{pid}") for pid in (th.get("winningPlayerIds") or [])],
            })

        catalog = [
            {
                "id": int(sp.get("id", 0)),
                "name": sp.get("name", ""),
                "reputation": int(sp.get("reputation", 1) or 1),
                "fixedMonthlyContribution": int(sp.get("fixedMonthlyContribution", 0) or 0),
                "bonusPayout": int(sp.get("bonusPayout", 0) or 0),
                "bonusPositionRequirement": int(sp.get("bonusPositionRequirement", 4) or 4),
            }
            for sp in self.data.get("sponsors", {}).get("sponsors", [])
        ]
        catalog.sort(key=lambda x: (-x["reputation"], -x["fixedMonthlyContribution"], x["name"]))

        base["pro"] = {
            "rankingHistory": [int(x) for x in (t.get("rankingHistory") or [])[-36:]],
            "sponsors": copy.deepcopy(t.get("sponsors") or []),
            "sponsorCatalog": catalog,
            "trophies": trophies,
            "squadHealth": {
                "avgBurnout": round(sum(_player_burnout_total(p) for p in all_p) / max(len(all_p), 1), 3) if all_p else 0.0,
                "avgMood": round(sum(_player_mood_score(p) for p in all_p) / max(len(all_p), 1), 2) if all_p else 0.0,
                "cooldowns": cooldowns,
                "activeBids": active_bids,
            },
        }
        return base

    def manage_team_sponsor(self, team_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        t = self.teams_by_id.get(team_id)
        if not t:
            raise ValueError(f"Team {team_id} not found.")
        mode = str(payload.get("mode", "update")).lower()
        sponsors = t.setdefault("sponsors", [])
        self.create_snapshot(f"Before Sponsor {mode}: {t.get('name', team_id)}")
        cur_dt = self.data.get("datetime", {"hour": 0, "day": 15, "month": 1, "year": 2027}) if self.data else {}

        if mode == "delete":
            idx = int(payload.get("index", -1))
            if idx < 0 or idx >= len(sponsors):
                raise ValueError(f"Sponsor index {idx} out of range.")
            sponsors.pop(idx)
        elif mode == "add":
            cat_id = int(payload.get("sponsorId", 0) or 0)
            template_sp = next((copy.deepcopy(s) for s in self.data.get("sponsors", {}).get("sponsors", []) if int(s.get("id", 0)) == cat_id), None)
            if not template_sp:
                template_sp = {
                    "id": cat_id or 1,
                    "reputation": int(payload.get("reputation", 5) or 5),
                    "name": str(payload.get("name", "Custom Sponsor")).strip() or "Custom Sponsor",
                    "logo": str(payload.get("logo", "custom")),
                    "expiry": {"hour": 0, "day": 1, "month": 1, "year": 2026},
                    "dealLength": {"hour": 0, "day": 15, "month": 6, "year": int(cur_dt.get("year", 2026)) + 1},
                    "fixedMonthlyContribution": 50000,
                    "potentialBonusTournamentTemplate": 9,
                    "bonusTournamentId": 0,
                    "bonusPositionRequirement": 4,
                    "bonusPayout": 100000,
                    "slot": len(sponsors) + 1,
                    "accepted": True,
                }
            if "fixedMonthlyContribution" in payload:
                template_sp["fixedMonthlyContribution"] = max(0, int(payload["fixedMonthlyContribution"]))
            if "bonusPayout" in payload:
                template_sp["bonusPayout"] = max(0, int(payload["bonusPayout"]))
            if "bonusPositionRequirement" in payload:
                template_sp["bonusPositionRequirement"] = max(1, int(payload["bonusPositionRequirement"]))
            if "endYear" in payload:
                template_sp.setdefault("dealLength", {})["year"] = int(payload["endYear"])
            template_sp["accepted"] = True
            template_sp["slot"] = int(payload.get("slot", len(sponsors) + 1))
            sponsors.append(template_sp)
        elif mode == "update":
            idx = int(payload.get("index", -1))
            if idx < 0 or idx >= len(sponsors):
                raise ValueError(f"Sponsor index {idx} out of range.")
            sp = sponsors[idx]
            for fk in ("fixedMonthlyContribution", "bonusPayout", "bonusPositionRequirement", "reputation", "slot"):
                if fk in payload:
                    sp[fk] = max(0, int(payload[fk]))
            if "accepted" in payload:
                sp["accepted"] = bool(payload["accepted"])
            if "endYear" in payload:
                sp.setdefault("dealLength", {"hour": 0, "day": 15, "month": 6, "year": int(payload["endYear"])})["year"] = int(payload["endYear"])
        else:
            raise ValueError(f"Unknown sponsor mode: {mode}")

        self.dirty = True
        return self.get_team_pro(team_id)

    def heal_team_squad(
        self, team_id: int, reset_burnout: bool = True, max_mood: bool = True, clear_cooldowns: bool = False
    ) -> dict[str, Any]:
        t = self.teams_by_id.get(team_id)
        if not t:
            raise ValueError(f"Team {team_id} not found.")
        self.create_snapshot(f"Before Heal Squad: {t.get('name', team_id)}")
        healed = 0
        for c in self.get_team_player_contracts(team_id):
            p = self.players_by_id.get(c["playerId"])
            if p:
                self._apply_player_wellness(p, reset_burnout=reset_burnout, max_mood=max_mood)
                healed += 1
        cd_cleared = 0
        if clear_cooldowns and "personInterests" in t:
            before = len(t["personInterests"])
            t["personInterests"] = [pi for pi in t["personInterests"] if int(pi.get("bidStatus", 0) or 0) not in (7, 8)]
            cd_cleared = before - len(t["personInterests"])
        self.dirty = True
        return {"healedPlayers": healed, "cooldownsCleared": cd_cleared, "team": self.get_team_pro(team_id)}

    # ------------------------------------------------------------------
    # Player Growth & Trajectory Lab
    # ------------------------------------------------------------------

    def _ensure_growth_index(self) -> dict[int, list[dict[str, Any]]]:
        if self._growth_cache is not None:
            return self._growth_cache
        assert self.data is not None
        by_pid_ym: dict[int, dict[tuple[int, int], dict[int, float]]] = {}
        for row in self.data.get("playerSkillHistories", {}).get("playerSkillHistories", []) or []:
            pid = int(row.get("playerId", 0) or 0)
            sid = int(row.get("skillId", 0) or 0)
            yy = int(row.get("year", 0) or 0)
            mm = int(row.get("month", 0) or 0)
            val = float(row.get("skillLevel", 0.0) or 0.0)
            if pid and sid and yy:
                by_pid_ym.setdefault(pid, {}).setdefault((yy, mm), {})[sid] = val

        series_by_pid: dict[int, list[dict[str, Any]]] = {}
        for pid, ym_map in by_pid_ym.items():
            pts = []
            for (yy, mm), sdict in sorted(ym_map.items()):
                mech = [sdict[k] for k in _MECH_IDS if k in sdict]
                weap = [sdict[k] for k in _WEAP_IDS if k in sdict]
                ment = [sdict[k] for k in _MENTAL_IDS if k in sdict]
                prac = [sdict[k] for k in _PRACTICAL_IDS if k in sdict]
                all_v = prac or list(sdict.values())
                if not all_v:
                    continue
                pts.append({
                    "year": yy,
                    "month": mm,
                    "label": f"{yy}-{mm:02d}",
                    "overall": round(sum(all_v) / len(all_v), 2),
                    "mechanics": round(sum(mech) / len(mech), 2) if mech else 0.0,
                    "weapons": round(sum(weap) / len(weap), 2) if weap else 0.0,
                    "mental": round(sum(ment) / len(ment), 2) if ment else 0.0,
                    "skills": {str(k): round(v, 2) for k, v in sdict.items()},
                })
            if pts:
                series_by_pid[pid] = pts
        self._growth_cache = series_by_pid
        return series_by_pid

    def get_growth_lab(self, min_months: int = 2) -> dict[str, Any]:
        if self.data is None:
            return {"loaded": False}
        series_map = self._ensure_growth_index()
        min_m = max(1, int(min_months or 2))
        rows = []
        all_labels: set[str] = set()

        for pid, p in self.players_by_id.items():
            c = self.player_contract_by_pid.get(pid)
            tid = c["teamId"] if c else 0
            tname = self.teams_by_id.get(tid, {}).get("name", "Free Agent") if tid else "Free Agent"
            cur_avg = _player_avg_skill(p)
            pot_avg = _player_potential_avg(p)
            pts = series_map.get(pid, [])
            for pt in pts:
                all_labels.add(pt["label"])
            if len(pts) >= min_m:
                start_pt, end_pt = pts[0], pts[-1]
                delta = round(end_pt["overall"] - start_pt["overall"], 2)
                mech_d = round(end_pt["mechanics"] - start_pt["mechanics"], 2)
                weap_d = round(end_pt["weapons"] - start_pt["weapons"], 2)
                ment_d = round(end_pt["mental"] - start_pt["mental"], 2)
                start_ovr = start_pt["overall"]
                end_ovr = end_pt["overall"]
                span = f"{start_pt['label']} → {end_pt['label']}"
            else:
                delta = mech_d = weap_d = ment_d = 0.0
                start_ovr = end_ovr = cur_avg
                span = "-"

            rows.append({
                "playerId": pid,
                "name": p.get("name", ""),
                "age": int(p.get("age", 0) or 0),
                "nationName": gd.NATIONS.get(p.get("nation", 0), ""),
                "teamId": tid,
                "teamName": tname,
                "monthsTracked": len(pts),
                "span": span,
                "startOverall": start_ovr,
                "endOverall": end_ovr,
                "currentAvg": cur_avg,
                "potentialAvg": pot_avg,
                "ceilingGap": round(max(0.0, pot_avg - cur_avg), 2),
                "overallDelta": delta,
                "mechDelta": mech_d,
                "weapDelta": weap_d,
                "mentDelta": ment_d,
                "useStartingPotential": bool(p.get("useStartingPotential", False)),
                "startingPotential": int(p.get("startingPotential", 0) or 0),
            })

        tracked = [r for r in rows if r["monthsTracked"] >= min_m]
        risers = sorted(tracked, key=lambda r: (-r["overallDelta"], -r["endOverall"]))[:60]
        decliners = sorted(tracked, key=lambda r: (r["overallDelta"], r["endOverall"]))[:60]
        wonderkids = sorted([r for r in rows if r["age"] <= 20], key=lambda r: (-r["overallDelta"], -r["currentAvg"], -r["potentialAvg"]))[:60]
        untapped = sorted(rows, key=lambda r: (-r["ceilingGap"], -r["potentialAvg"], r["age"]))[:60]

        return {
            "loaded": True,
            "monthsSpan": sorted(all_labels),
            "trackedCount": len(tracked),
            "totalPlayers": len(rows),
            "risers": risers,
            "decliners": decliners,
            "wonderkids": wonderkids,
            "untappedCeiling": untapped,
        }

    def get_player_trajectory(self, player_id: int) -> dict[str, Any]:
        p = self.players_by_id.get(player_id)
        if not p:
            raise ValueError(f"Player {player_id} not found.")
        series_map = self._ensure_growth_index()
        pts = series_map.get(player_id, [])
        c = self.player_contract_by_pid.get(player_id)
        tid = c["teamId"] if c else 0
        return {
            "playerId": player_id,
            "name": p.get("name", ""),
            "age": int(p.get("age", 0) or 0),
            "teamName": self.teams_by_id.get(tid, {}).get("name", "Free Agent") if tid else "Free Agent",
            "currentAvg": _player_avg_skill(p),
            "potentialAvg": _player_potential_avg(p),
            "series": pts,
        }

    # ------------------------------------------------------------------
    # What-If Roster Sandbox & Matchup Simulator
    # ------------------------------------------------------------------

    def _sandbox_player_metrics(self, pids: list[int]) -> dict[str, Any]:
        players = [self.players_by_id[pid] for pid in pids if pid in self.players_by_id]
        if not players:
            return {
                "avgSkill": 0.0, "mechAvg": 0.0, "weaponAvg": 0.0, "mentalAvg": 0.0,
                "avgAge": 0.0, "totalSalary": 0, "power28": 0.0, "players": [],
            }
        prac = [self._player_practical_avg(p) for p in players]
        mechs = []
        weaps = []
        ments = []
        salaries = []
        p_rows = []
        for p in players:
            sk = p.get("skills", {})
            c = self.player_contract_by_pid.get(p["id"])
            sal = int(c.get("salaryYear", 0) or 0) if c else 0
            salaries.append(sal)
            mechs.append(sum(float(sk.get(k, 10.0) or 10.0) for k in self._MECH_KEYS) / len(self._MECH_KEYS))
            weaps.append(sum(float(sk.get(k, 10.0) or 10.0) for k in self._WEAPON_KEYS) / len(self._WEAPON_KEYS))
            ments.append(sum(float(sk.get(k, 10.0) or 10.0) for k in self._MENTAL_KEYS) / len(self._MENTAL_KEYS))
            pers = p.get("personality", {})
            langs = [
                f"{gd.LANGUAGES.get(int(lg.get('languageId', 0)), '?')} ({int(lg.get('languageSkill', 0))})"
                for lg in (p.get("languagesSpoken") or []) if int(lg.get("languageSkill", 0) or 0) >= 8
            ]
            p_rows.append({
                "playerId": p["id"],
                "name": p.get("name", ""),
                "age": int(p.get("age", 0) or 0),
                "teamName": self.teams_by_id.get(c["teamId"], {}).get("name", "Free Agent") if c and c.get("teamId") in self.teams_by_id else "Free Agent",
                "practicalAvg": round(self._player_practical_avg(p), 2),
                "avgSkill": _player_avg_skill(p),
                "salaryYear": sal,
                "desireToIgl": int(pers.get("desireToIgl", 0) or 0),
                "desireToAwp": int(pers.get("desireToAwp", 0) or 0),
                "leadership": round(float(sk.get("leadership", 10.0) or 10.0), 1),
                "snipers": round(float(sk.get("snipers", 10.0) or 10.0), 1),
                "languages": langs,
            })

        avg_s = sum(prac) / len(prac)
        return {
            "avgSkill": round(avg_s, 2),
            "mechAvg": round(sum(mechs) / len(mechs), 2),
            "weaponAvg": round(sum(weaps) / len(weaps), 2),
            "mentalAvg": round(sum(ments) / len(ments), 2),
            "avgAge": round(sum(float(p.get("age", 0) or 0) for p in players) / len(players), 1),
            "totalSalary": sum(salaries),
            "power28": round(avg_s ** 2.8, 2),
            "players": p_rows,
        }

    def simulate_roster(self, team_id: int, player_ids: list[int], vs_team_id: int = 0) -> dict[str, Any]:
        if self.data is None:
            raise RuntimeError("No save file is currently loaded.")
        team = self.teams_by_id.get(int(team_id))
        if not team:
            raise ValueError(f"Team #{team_id} not found.")
        seen: set[int] = set()
        pids: list[int] = []
        for raw_id in player_ids:
            pid = int(raw_id)
            if pid not in self.players_by_id:
                raise ValueError(f"Player #{pid} not found.")
            if pid not in seen:
                seen.add(pid)
                pids.append(pid)
        if not (1 <= len(pids) <= 5):
            raise ValueError("Sandbox requires between 1 and 5 unique players.")

        cur_pcs = self.get_team_player_contracts(int(team_id))
        cur_pids = [c["playerId"] for c in cur_pcs if not c.get("benched") and c["playerId"] in self.players_by_id][:5]
        baseline = self._sandbox_player_metrics(cur_pids)
        sim = self._sandbox_player_metrics(pids)

        # Compute Bo3 odds vs current Top-10 ranked teams (excluding this team)
        ranked_teams = []
        for t in self.data["teams"]["teams"]:
            tid_o = t["id"]
            if tid_o == int(team_id):
                continue
            pcs_o = self.get_team_player_contracts(tid_o)
            st_o = [c["playerId"] for c in pcs_o if not c.get("benched") and c["playerId"] in self.players_by_id][:5]
            if len(st_o) < 5:
                continue
            rh = t.get("rankingHistory") or []
            wr = int(rh[-1]) if rh else 0
            met = self._sandbox_player_metrics(st_o)
            ranked_teams.append((wr == 0, wr or 9999, -met["avgSkill"], tid_o, t.get("name", ""), met, st_o))
        ranked_teams.sort()
        top10 = ranked_teams[:10]

        def _series_odds(p_a: float, p_b: float) -> tuple[float, float, float]:
            tot = p_a + p_b
            bo1 = (p_a / tot) if tot > 0 else 0.5
            bo3 = (bo1 ** 2) * (3.0 - 2.0 * bo1)
            bo5 = (bo1 ** 3) * (10.0 - 15.0 * bo1 + 6.0 * (bo1 ** 2))
            return round(bo1 * 100.0, 1), round(bo3 * 100.0, 1), round(bo5 * 100.0, 1)

        base_t10_bo3 = []
        sim_t10_bo3 = []
        for _, _, _, _, _, om, _ in top10:
            if baseline["power28"] > 0:
                base_t10_bo3.append(_series_odds(baseline["power28"], om["power28"])[1])
            sim_t10_bo3.append(_series_odds(sim["power28"], om["power28"])[1])

        # Specific opponent head-to-head
        opp_entry = next((r for r in ranked_teams if r[3] == int(vs_team_id)), ranked_teams[0] if ranked_teams else None)
        vs_opp = None
        if opp_entry:
            _, wr_o, _, oid, oname, om, opids = opp_entry
            bo1, bo3, bo5 = _series_odds(sim["power28"], om["power28"])
            vs_opp = {
                "teamId": oid,
                "teamName": oname,
                "worldRank": wr_o if wr_o < 9999 else 0,
                "avgSkill": om["avgSkill"],
                "bo1Pct": bo1,
                "bo3Pct": bo3,
                "bo5Pct": bo5,
                "skillDelta": round(sim["avgSkill"] - om["avgSkill"], 2),
            }

        # Language comms check (>= 12 fluency)
        lang_counts: dict[int, int] = {}
        player_lang_sets: dict[int, set[int]] = {}
        for pid in pids:
            p = self.players_by_id[pid]
            fset = {int(lg.get("languageId", 0)) for lg in (p.get("languagesSpoken") or []) if int(lg.get("languageSkill", 0) or 0) >= 12}
            player_lang_sets[pid] = fset
            for lid in fset:
                lang_counts[lid] = lang_counts.get(lid, 0) + 1
        shared_langs = [gd.LANGUAGES.get(lid, f"#{lid}") for lid, cnt in sorted(lang_counts.items()) if cnt == len(pids)]
        best_lang_id = max(lang_counts.items(), key=lambda kv: (kv[1], 1 if kv[0] == 13 else 0))[0] if lang_counts else 0
        best_lang_name = gd.LANGUAGES.get(best_lang_id, "None") if best_lang_id else "None"
        non_fluent = [
            self.players_by_id[pid].get("name", f"#{pid}")
            for pid in pids if best_lang_id and best_lang_id not in player_lang_sets.get(pid, set())
        ]

        # Relationships inside lineup
        friends = []
        rivals = []
        for rel in self.data.get("playerRelationships", {}).get("playerRelationships", []):
            p1 = int(rel.get("player1Id", 0) or 0)
            p2 = int(rel.get("player2Id", 0) or 0)
            if p1 in seen and p2 in seen:
                rtype = int(rel.get("type", 1) or 0)
                pair_lbl = f"{self.players_by_id[p1].get('name')} ↔ {self.players_by_id[p2].get('name')}"
                if rtype == 0:
                    rivals.append(pair_lbl)
                else:
                    friends.append(f"{pair_lbl} ({gd.RELATIONSHIP_TYPES.get(rtype, 'Bond')})")

        # Roles check
        primary_igls = [r["name"] for r in sim["players"] if r["desireToIgl"] >= 15]
        primary_awps = [r["name"] for r in sim["players"] if r["desireToAwp"] >= 15]
        role_warnings = []
        if not primary_igls and not any(r["desireToIgl"] >= 10 for r in sim["players"]):
            role_warnings.append("No natural IGL (nobody has Desire to IGL >= 10)")
        if not primary_awps and not any(r["desireToAwp"] >= 10 for r in sim["players"]):
            role_warnings.append("No dedicated AWPer (nobody has Desire to AWP >= 10)")
        if len(primary_awps) > 1:
            role_warnings.append(f"AWP overlap: {', '.join(primary_awps)} all want Primary AWP")
        if rivals:
            role_warnings.append(f"{len(rivals)} Rivalry inside starting 5")

        # 7-map pool comfort + preference vs opponent
        def _map_scores(mp_pids: list[int]) -> dict[int, tuple[float, int]]:
            out = {}
            for mid_m in self.maps_by_id:
                vals = []
                likes = 0
                for pid_x in mp_pids:
                    px = self.players_by_id.get(pid_x, {})
                    atts = [float(a.get("roleComfort", 5)) for a in (px.get("mapPositionAttributes") or []) if int(a.get("mapId", 0) or 0) == mid_m]
                    if atts:
                        vals.append(max(atts))
                    for op in px.get("mapOpinions") or []:
                        if int(op.get("mapId", 0) or 0) == mid_m and op.get("like"):
                            likes += 1
                out[mid_m] = (round(sum(vals) / len(vals), 2) if vals else 5.0, likes)
            return out

        sim_maps = _map_scores(pids)
        opp_maps = _map_scores(opp_entry[6]) if opp_entry else {}
        map_pool = [
            {
                "mapId": mid_m,
                "mapName": m_obj.get("name", f"Map {mid_m}"),
                "comfort": sim_maps[mid_m][0],
                "likes": sim_maps[mid_m][1],
                "oppComfort": opp_maps.get(mid_m, (5.0, 0))[0] if opp_maps else None,
            }
            for mid_m, m_obj in self.maps_by_id.items()
        ]

        return {
            "teamId": int(team_id),
            "teamName": team.get("name", ""),
            "baseline": baseline,
            "simulated": sim,
            "skillDiff": round(sim["avgSkill"] - baseline["avgSkill"], 2),
            "salaryDiff": sim["totalSalary"] - baseline["totalSalary"],
            "baseTop10Bo3Pct": round(sum(base_t10_bo3) / len(base_t10_bo3), 1) if base_t10_bo3 else 0.0,
            "simTop10Bo3Pct": round(sum(sim_t10_bo3) / len(sim_t10_bo3), 1) if sim_t10_bo3 else 0.0,
            "vsOpponent": vs_opp,
            "comms": {
                "sharedLanguages": shared_langs,
                "bestLanguage": best_lang_name,
                "bestLanguageCoverage": lang_counts.get(best_lang_id, 0) if best_lang_id else 0,
                "missingFluency": non_fluent,
            },
            "chemistry": {"friends": friends, "rivals": rivals},
            "roles": {
                "primaryIgls": primary_igls,
                "primaryAwps": primary_awps,
                "warnings": role_warnings,
            },
            "mapPool": map_pool,
        }

    def commit_roster_sandbox(self, team_id: int, player_ids: list[int]) -> dict[str, Any]:
        if self.data is None:
            raise RuntimeError("No save file is currently loaded.")
        tid = int(team_id)
        if tid not in self.teams_by_id:
            raise ValueError(f"Team #{tid} not found.")
        seen: set[int] = set()
        pids: list[int] = []
        for raw_id in player_ids:
            pid = int(raw_id)
            if pid not in self.players_by_id:
                raise ValueError(f"Player #{pid} not found.")
            if pid not in seen:
                seen.add(pid)
                pids.append(pid)
        if not (1 <= len(pids) <= 5):
            raise ValueError("Commit requires 1 to 5 unique players.")

        self.create_snapshot(f"Before Roster Sandbox Commit -> {self.teams_by_id[tid].get('name', tid)}")
        team = self.teams_by_id[tid]

        # Bench existing starters of target team not in desired 5
        for c in self.get_team_player_contracts(tid):
            if not c.get("benched") and c["playerId"] not in seen:
                c["benched"] = True
                self.remove_player_from_tactics(team, c["playerId"])

        # Sign / unbench the desired starters
        for pid in pids:
            existing = self.player_contract_by_pid.get(pid)
            if existing and int(existing.get("teamId", 0)) == tid:
                existing["benched"] = False
            else:
                self.transfer_player({"playerId": pid, "targetTeamId": tid, "joinBenched": False})

        self.rebuild_indices()
        tactics_res = self.recalculate_ai_tactics(tid)
        self.dirty = True
        return {
            "committed": True,
            "tactics": tactics_res,
            "simulation": self.simulate_roster(tid, pids),
        }

    # ------------------------------------------------------------------
    # Tournament Hub & Fair-Award Retroactive Patcher
    # ------------------------------------------------------------------

    def list_tournaments_hub(self) -> dict[str, Any]:
        if self.data is None:
            return {"loaded": False}
        base_ev = self.get_event_stats()
        ev_map = {e["id"]: e for e in base_ev.get("events", [])}
        tournaments = self.data.get("tournaments", {}).get("tournaments", [])

        rows = []
        mismatches = 0
        # Evaluate MVP mismatches on awarded MVP events (reputation >= 13)
        for ev in base_ev.get("events", []):
            t_raw = next((x for x in tournaments if int(x.get("id", 0)) == ev["id"]), {})
            rec_mvp = ""
            fair_mvp = ""
            mismatch = False
            if ev["hasRecordedAwards"] and ev["reputation"] >= 13:
                det = self.get_event_stats(ev["id"])
                rm = (det.get("event") or {}).get("recordedMvp")
                fm = (det.get("event") or {}).get("fairMvp")
                rec_mvp = rm["playerName"] if rm else ""
                fair_mvp = fm["playerName"] if fm else ""
                if rm and fm and rm["playerId"] != fm["playerId"]:
                    mismatch = True
                    mismatches += 1
            rows.append({
                **ev,
                "awardSlots": self._awards_for_reputation(ev["reputation"]),
                "bestOfFiveGrandFinals": bool(t_raw.get("bestOfFiveGrandFinals", False)),
                "stickerMoneyLow": int(t_raw.get("stickerMoneyLow", 0) or 0),
                "stickerMoneyHigh": int(t_raw.get("stickerMoneyHigh", 0) or 0),
                "stickerMoneyGranted": int(t_raw.get("stickerMoneyGranted", 0) or 0),
                "recordedMvpName": rec_mvp,
                "fairMvpName": fair_mvp,
                "mvpMismatch": mismatch,
            })

        # Also include unplayed/upcoming tournaments at end
        for t in tournaments:
            tid = int(t.get("id", 0) or 0)
            if tid in ev_map:
                continue
            rep = int(t.get("reputation", 1) or 1)
            slots = self._awards_for_reputation(rep)
            rows.append({
                "id": tid,
                "name": t.get("name") or f"Tournament #{tid}",
                "template": int(t.get("template", 0) or 0),
                "reputation": rep,
                "tierLabel": slots["tierLabel"],
                "awardSlots": slots,
                "year": 0,
                "month": 0,
                "date": "Upcoming",
                "matchCount": 0,
                "championTeamId": 0,
                "championName": "—",
                "awardsCount": 0,
                "hasRecordedAwards": False,
                "bestOfFiveGrandFinals": bool(t.get("bestOfFiveGrandFinals", False)),
                "stickerMoneyLow": int(t.get("stickerMoneyLow", 0) or 0),
                "stickerMoneyHigh": int(t.get("stickerMoneyHigh", 0) or 0),
                "stickerMoneyGranted": int(t.get("stickerMoneyGranted", 0) or 0),
                "recordedMvpName": "",
                "fairMvpName": "",
                "mvpMismatch": False,
            })

        years_found = {
            int(a.get("year", 0) or 0)
            for p in self.data.get("players", {}).get("players", [])
            for a in (p.get("playerAwards") or [])
            if int(a.get("type", -1)) in (0, 2, 3) and int(a.get("year", 0) or 0) >= 2000
        }
        years_found.update(
            int(cs.get("year", 0) or 0)
            for cs in self.data.get("playerCareerStats", {}).get("playerCareerStats", [])
            if int(cs.get("year", 0) or 0) >= 2000
        )
        cur_yr = int((self.data.get("datetime") or {}).get("year", 2026) or 2026)
        if not years_found:
            years_found.add(cur_yr)

        return {
            "loaded": True,
            "total": len(rows),
            "playedCount": len(ev_map),
            "mvpMismatchCount": mismatches,
            "awardYears": sorted(years_found, reverse=True),
            "tournaments": rows,
        }

    def get_tournament_hub_detail(self, tournament_id: int) -> dict[str, Any]:
        if self.data is None:
            raise RuntimeError("No save file is currently loaded.")
        t_raw = next((t for t in self.data.get("tournaments", {}).get("tournaments", []) if int(t.get("id", 0)) == int(tournament_id)), None)
        if not t_raw:
            raise ValueError(f"Tournament #{tournament_id} not found.")

        ev_stats = self.get_event_stats(int(tournament_id))
        if (ev_stats.get("event") or {}).get("id") != int(tournament_id):
            rep = int(t_raw.get("reputation", 1) or 1)
            slots = self._awards_for_reputation(rep)
            ev_stats = {
                "loaded": True,
                "events": ev_stats.get("events", []),
                "event": {
                    "id": int(t_raw["id"]),
                    "name": t_raw.get("name", f"Tournament #{tournament_id}"),
                    "template": int(t_raw.get("template", 0) or 0),
                    "reputation": rep,
                    "tierLabel": slots["tierLabel"],
                    "year": 0,
                    "month": 0,
                    "date": "Upcoming",
                    "matchCount": 0,
                    "championTeamId": 0,
                    "championName": "—",
                    "runnerUpName": "—",
                    "awardsCount": 0,
                    "hasRecordedAwards": False,
                    "awardSlots": slots,
                    "playerCount": 0,
                    "recordedMvp": None,
                    "gameMvp": None,
                    "fairMvp": None,
                },
                "players": [],
            }
        stages_raw = [s for s in self.data.get("tournamentStages", {}).get("tournamentStages", []) if int(s.get("parentId", 0) or 0) == int(tournament_id)]
        stages_raw.sort(key=lambda s: int(s.get("stage", 0) or 0))
        stage_ids = {int(s["id"]) for s in stages_raw if s.get("id") is not None}

        ms_by_stage: dict[int, list[dict[str, Any]]] = {}
        for m in self.data.get("matches", {}).get("matches", []):
            sid = int(m.get("tournamentId", 0) or 0)
            if sid in stage_ids:
                ms_by_stage.setdefault(sid, []).append(m)

        stages_out = []
        for s in stages_raw:
            sid = int(s["id"])
            raw_s = s.get("name", "")
            lbl = raw_s.split("__", 1)[0].replace("_", " ").strip().title() if raw_s else f"Stage {s.get('stage', 1)}"
            sdt = s.get("startDatetime") or {}
            edt = s.get("endDatetime") or {}
            stages_out.append({
                "id": sid,
                "stage": int(s.get("stage", 0) or 0),
                "name": lbl,
                "participants": int(s.get("numberOfParticipants", 0) or 0),
                "matchCount": len(ms_by_stage.get(sid, [])),
                "startDate": f"{sdt.get('year', 0)}-{int(sdt.get('month', 0)):02d}-{int(sdt.get('day', 0)):02d}" if sdt.get("year") else "-",
                "endDate": f"{edt.get('year', 0)}-{int(edt.get('month', 0)):02d}-{int(edt.get('day', 0)):02d}" if edt.get("year") else "-",
            })

        return {
            **ev_stats,
            "meta": {
                "id": int(t_raw["id"]),
                "name": t_raw.get("name", ""),
                "template": int(t_raw.get("template", 0) or 0),
                "reputation": int(t_raw.get("reputation", 1) or 1),
                "bestOfFiveGrandFinals": bool(t_raw.get("bestOfFiveGrandFinals", False)),
                "stickerMoneyLow": int(t_raw.get("stickerMoneyLow", 0) or 0),
                "stickerMoneyHigh": int(t_raw.get("stickerMoneyHigh", 0) or 0),
                "stickerMoneyGranted": int(t_raw.get("stickerMoneyGranted", 0) or 0),
                "playersAwarded": [int(x or 0) for x in (t_raw.get("playersAwarded") or []) if int(x or 0) > 0],
            },
            "stages": stages_out,
        }

    def update_tournament_meta(self, tournament_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        if self.data is None:
            raise RuntimeError("No save file is currently loaded.")
        t_raw = next((t for t in self.data.get("tournaments", {}).get("tournaments", []) if int(t.get("id", 0)) == int(tournament_id)), None)
        if not t_raw:
            raise ValueError(f"Tournament #{tournament_id} not found.")
        self.create_snapshot(f"Before Tournament Edit: {t_raw.get('name', tournament_id)}")
        if "reputation" in payload:
            t_raw["reputation"] = int(_clamp(int(payload["reputation"]), 1, 20))
        if "bestOfFiveGrandFinals" in payload:
            t_raw["bestOfFiveGrandFinals"] = bool(payload["bestOfFiveGrandFinals"])
        if "stickerMoneyLow" in payload:
            t_raw["stickerMoneyLow"] = max(0, int(payload["stickerMoneyLow"]))
        if "stickerMoneyHigh" in payload:
            t_raw["stickerMoneyHigh"] = max(0, int(payload["stickerMoneyHigh"]))
        self.dirty = True
        return self.get_tournament_hub_detail(tournament_id)

    def _compute_award_patch(self, tournament_id: int, mode: str, custom_ids: list[int] | None) -> dict[str, Any]:
        t_raw = next((t for t in self.data.get("tournaments", {}).get("tournaments", []) if int(t.get("id", 0)) == int(tournament_id)), None)
        if not t_raw:
            raise ValueError(f"Tournament #{tournament_id} not found.")
        ev_stats = self.get_event_stats(int(tournament_id))
        ev = ev_stats.get("event") or {}
        if ev.get("id") != int(tournament_id):
            raise ValueError(f"Tournament #{tournament_id} has no played match stats yet.")
        players = ev_stats.get("players") or []
        slots = self._awards_for_reputation(int(t_raw.get("reputation", 1) or 1))
        total_slots = slots["total"]

        old_ids = [int(x or 0) for x in (t_raw.get("playersAwarded") or []) if int(x or 0) > 0]
        if mode == "fair":
            ordered: list[int] = []
            for role in ("MVP", "EVP", "HM"):
                for row in players:
                    if row.get("fairProjectedAward") == role and row["playerId"] not in ordered:
                        ordered.append(int(row["playerId"]))
            new_ids = ordered[:total_slots]
        elif mode == "custom":
            seen: set[int] = set()
            new_ids = []
            for raw_id in (custom_ids or []):
                pid = int(raw_id)
                if pid in self.players_by_id and pid not in seen:
                    seen.add(pid)
                    new_ids.append(pid)
            new_ids = new_ids[:total_slots]
        else:
            raise ValueError(f"Unknown award patch mode: {mode}")

        ev_team_by_pid = {int(r["playerId"]): int(r["teamId"] or 0) for r in players}
        return {
            "tournament": t_raw,
            "event": ev,
            "slots": slots,
            "oldIds": old_ids,
            "newIds": new_ids,
            "evTeamByPid": ev_team_by_pid,
            "changed": old_ids != new_ids,
        }

    def patch_tournament_awards(
        self,
        tournament_id: int,
        mode: str = "fair",
        custom_player_ids: list[int] | None = None,
        dry_run: bool = False,
        _skip_snapshot: bool = False,
    ) -> dict[str, Any]:
        if self.data is None:
            raise RuntimeError("No save file is currently loaded.")
        plan = self._compute_award_patch(tournament_id, mode, custom_player_ids)
        t_raw = plan["tournament"]
        ev = plan["event"]
        slots = plan["slots"]
        old_ids = plan["oldIds"]
        new_ids = plan["newIds"]

        def _fmt_list(pids: list[int]) -> list[dict[str, Any]]:
            out = []
            for idx, pid in enumerate(pids):
                role = "MVP" if idx < slots["mvp"] else ("EVP" if idx < slots["mvp"] + slots["evp"] else "HM")
                out.append({"playerId": pid, "playerName": self.players_by_id.get(pid, {}).get("name", f"#{pid}"), "role": role})
            return out

        tpl = int(t_raw.get("template", 0) or 0)
        end_y, end_m = self._tournament_end_ym(int(tournament_id))
        ev_year = end_y if end_y >= 2000 else int(ev.get("year", 0) or 0)
        ev_month = end_m if end_m > 0 else int(ev.get("month", 0) or 0)
        if not ev_year:
            cur_dt = self.data.get("datetime", {})
            ev_year = int(cur_dt.get("year", 2026) or 2026)
            ev_month = int(cur_dt.get("month", 1) or 1)

        # Only adopt an adjacent existing PlayerAward month (+/-1) if no other tournament of this template ends in that month
        other_tpl_months = {
            self._tournament_end_ym(int(t["id"]))
            for t in self.data.get("tournaments", {}).get("tournaments", [])
            if int(t.get("id", 0)) != int(tournament_id) and int(t.get("template", 0) or 0) == tpl
        }
        if old_ids and ev_month > 0:
            for pid_o in old_ids:
                po = self.players_by_id.get(pid_o)
                if not po:
                    continue
                hit = next(
                    (
                        a for a in po.get("playerAwards", [])
                        if int(a.get("tournamentTemplate", -1)) == tpl
                        and int(a.get("year", 0)) == ev_year
                        and int(a.get("type", -1)) in (0, 2)
                        and abs(int(a.get("month", 0) or 0) - ev_month) <= 1
                        and (ev_year, int(a.get("month", 0) or 0)) not in other_tpl_months
                    ),
                    None,
                )
                if hit:
                    ev_month = int(hit.get("month", ev_month) or ev_month)
                    break

        if not dry_run:
            if not _skip_snapshot:
                self.create_snapshot(f"Before Fair Award Patch: {t_raw.get('name', tournament_id)}")
            t_raw["playersAwarded"] = list(new_ids)

            # Remove ONLY MVP (type 0) & EVP (type 2) matching this exact event; preserve Event Win (1) & Top 20 (3)
            for p_obj in self.players_by_id.values():
                aws = p_obj.get("playerAwards")
                if not aws:
                    continue
                p_obj["playerAwards"] = [
                    a for a in aws
                    if not (
                        int(a.get("type", -1)) in (0, 2)
                        and int(a.get("tournamentTemplate", -1)) == tpl
                        and int(a.get("year", 0)) == ev_year
                        and (ev_month == 0 or int(a.get("month", 0)) == ev_month)
                    )
                ]

            give_count = slots["mvp"] + slots["evp"]
            for idx, pid_n in enumerate(new_ids[:give_count]):
                po = self.players_by_id.get(pid_n)
                if not po:
                    continue
                atype = 0 if idx < slots["mvp"] else 2
                c_n = self.player_contract_by_pid.get(pid_n)
                tid_a = plan["evTeamByPid"].get(pid_n) or (c_n["teamId"] if c_n else 0)
                po.setdefault("playerAwards", []).append({
                    "type": atype,
                    "tournamentTemplate": tpl,
                    "year": ev_year,
                    "month": ev_month or 1,
                    "teamId": int(tid_a),
                    "top20Placement": 0,
                })
            self.dirty = True

        return {
            "dryRun": dry_run,
            "tournamentId": int(tournament_id),
            "tournamentName": t_raw.get("name", ""),
            "year": ev_year,
            "month": ev_month,
            "changed": plan["changed"],
            "oldAwards": _fmt_list(old_ids),
            "newAwards": _fmt_list(new_ids),
        }

    def batch_patch_fair_awards(self, min_reputation: int = 13, dry_run: bool = True) -> dict[str, Any]:
        if self.data is None:
            raise RuntimeError("No save file is currently loaded.")
        min_rep = max(1, min(20, int(min_reputation or 13)))
        targets = [
            t for t in self.data.get("tournaments", {}).get("tournaments", [])
            if int(t.get("reputation", 0) or 0) >= min_rep and any(int(x or 0) > 0 for x in (t.get("playersAwarded") or []))
        ]
        if not dry_run and targets:
            self.create_snapshot(f"Before Batch Fair Award Patch (Rep >= {min_rep})")

        diffs = []
        changed_events = 0
        mvp_changes = 0
        for t in targets:
            res = self.patch_tournament_awards(int(t["id"]), mode="fair", dry_run=dry_run, _skip_snapshot=True)
            if res["changed"]:
                changed_events += 1
                old_m = res["oldAwards"][0]["playerName"] if res["oldAwards"] else "—"
                new_m = res["newAwards"][0]["playerName"] if res["newAwards"] else "—"
                if old_m != new_m:
                    mvp_changes += 1
                diffs.append({
                    "tournamentId": res["tournamentId"],
                    "name": res["tournamentName"],
                    "date": f"{res['year']}-{res['month']:02d}",
                    "oldMvp": old_m,
                    "newMvp": new_m,
                    "mvpChanged": old_m != new_m,
                    "oldList": ", ".join(f"{x['playerName']} ({x['role']})" for x in res["oldAwards"]),
                    "newList": ", ".join(f"{x['playerName']} ({x['role']})" for x in res["newAwards"]),
                })
        return {
            "dryRun": dry_run,
            "minReputation": min_rep,
            "scannedEvents": len(targets),
            "changedEvents": changed_events,
            "mvpChanges": mvp_changes,
            "diffs": diffs,
        }

    def _tournament_end_ym(self, tournament_id: int) -> tuple[int, int]:
        if self.data is None:
            return (0, 0)
        best = (0, 0, 0)
        for s in self.data.get("tournamentStages", {}).get("tournamentStages", []):
            if int(s.get("parentId", 0) or 0) != int(tournament_id):
                continue
            for key in ("endDatetime", "startDatetime"):
                dt_s = s.get(key) or {}
                y = int(dt_s.get("year", 0) or 0)
                m = int(dt_s.get("month", 0) or 0)
                d = int(dt_s.get("day", 0) or 0)
                if y >= 2000 and m > 0:
                    cand = (y, m, d)
                    if cand > best:
                        best = cand
                    break
        return (best[0], best[1])

    def sync_player_awards_from_tournaments(self, dry_run: bool = False) -> dict[str, Any]:
        """Rebuild all MVP/EVP career playerAwards strictly from played Tier-1+ tournaments' saved winners and true end months."""
        if self.data is None:
            raise RuntimeError("No save file is currently loaded.")

        pcs_team: dict[tuple[int, int, int, int], int] = {}
        for row in self.data.get("playerCareerStats", {}).get("playerCareerStats", []):
            pid = int(row.get("playerId", 0) or 0)
            tpl = int(row.get("tournamentTemplate", 0) or 0)
            yr = int(row.get("year", 0) or 0)
            mo = int(row.get("month", 0) or 0)
            tid = int(row.get("teamId", 0) or 0)
            if pid and tpl and yr >= 2000 and mo > 0 and tid:
                pcs_team[(pid, tpl, yr, mo)] = tid

        expected_by_event: list[dict[str, Any]] = []
        covered_tpl_years: set[tuple[int, int]] = set()
        expected_sigs: set[tuple[int, int, int, int, int]] = set()
        for t in self.data.get("tournaments", {}).get("tournaments", []):
            pa = [int(x or 0) for x in (t.get("playersAwarded") or []) if int(x or 0) > 0]
            if not pa:
                continue
            rep = int(t.get("reputation", 1) or 1)
            slots = self._awards_for_reputation(rep)
            if slots["mvp"] <= 0:
                continue
            end_y, end_m = self._tournament_end_ym(int(t["id"]))
            if end_y < 2000 or end_m <= 0:
                continue
            tpl = int(t.get("template", 0) or 0)
            covered_tpl_years.add((tpl, end_y))
            give_count = slots["mvp"] + slots["evp"]
            entries = []
            for idx, pid_n in enumerate(pa[:give_count]):
                if pid_n not in self.players_by_id:
                    continue
                atype = 0 if idx < slots["mvp"] else 2
                c_n = self.player_contract_by_pid.get(pid_n)
                tid_a = (
                    pcs_team.get((pid_n, tpl, end_y, end_m))
                    or pcs_team.get((pid_n, tpl, end_y, end_m - 1))
                    or (c_n["teamId"] if c_n else 0)
                )
                expected_sigs.add((pid_n, atype, tpl, end_y, end_m))
                entries.append({
                    "playerId": pid_n,
                    "type": atype,
                    "tournamentTemplate": tpl,
                    "year": end_y,
                    "month": end_m,
                    "teamId": int(tid_a or 0),
                })
            expected_by_event.append({
                "tournamentId": int(t["id"]),
                "name": t.get("name", ""),
                "tpl": tpl,
                "year": end_y,
                "month": end_m,
                "entries": entries,
            })

        existing_sigs: set[tuple[int, int, int, int, int]] = set()
        existing_in_scope = 0
        for pid, p_obj in self.players_by_id.items():
            for a in (p_obj.get("playerAwards") or []):
                at = int(a.get("type", -1))
                tpl_a = int(a.get("tournamentTemplate", -1))
                yr_a = int(a.get("year", 0) or 0)
                mo_a = int(a.get("month", 0) or 0)
                if at in (0, 2) and (tpl_a, yr_a) in covered_tpl_years:
                    existing_in_scope += 1
                    existing_sigs.add((pid, at, tpl_a, yr_a, mo_a))

        mismatched_events = 0
        for ev_e in expected_by_event:
            ev_sigs = {(e["playerId"], e["type"], e["tournamentTemplate"], e["year"], e["month"]) for e in ev_e["entries"]}
            cur_ev_sigs = {s for s in existing_sigs if s[2] == ev_e["tpl"] and s[3] == ev_e["year"] and s[4] == ev_e["month"]}
            if ev_sigs != cur_ev_sigs:
                mismatched_events += 1

        if not dry_run and expected_by_event:
            self.create_snapshot("Before Repair/Sync Player Awards from Tournaments")
            for p_obj in self.players_by_id.values():
                aws = p_obj.get("playerAwards")
                if not aws:
                    continue
                p_obj["playerAwards"] = [
                    a for a in aws
                    if not (
                        int(a.get("type", -1)) in (0, 2)
                        and (int(a.get("tournamentTemplate", -1)), int(a.get("year", 0) or 0)) in covered_tpl_years
                    )
                ]
            for ev_e in expected_by_event:
                for e in ev_e["entries"]:
                    po = self.players_by_id.get(e["playerId"])
                    if po is not None:
                        po.setdefault("playerAwards", []).append({
                            "type": e["type"],
                            "tournamentTemplate": e["tournamentTemplate"],
                            "year": e["year"],
                            "month": e["month"],
                            "teamId": e["teamId"],
                            "top20Placement": 0,
                        })
            self.dirty = True

        return {
            "dryRun": dry_run,
            "eventsSynced": len(expected_by_event),
            "mismatchedEventsBefore": mismatched_events,
            "removedCount": len(existing_sigs - expected_sigs) + max(0, existing_in_scope - len(existing_sigs)),
            "addedCount": len(expected_sigs - existing_sigs),
            "totalExpectedAwards": len(expected_sigs),
        }

    def reset_or_recalc_top20(
        self,
        year: int,
        mode: str = "recalculate",
        vote_player_id: int = 0,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        if self.data is None:
            raise RuntimeError("No save file is currently loaded.")
        yr = int(year)
        if yr < 2000 or yr > 2200:
            raise ValueError(f"Invalid Top 20 year: {yr}")
        mode_n = str(mode or "recalculate").strip().lower()
        if mode_n not in ("recalculate", "clear"):
            raise ValueError(f"Unknown Top 20 mode: {mode_n}")

        old_top20: list[dict[str, Any]] = []
        old_rank_by_pid: dict[int, int] = {}
        for p in self.data.get("players", {}).get("players", []):
            pid = int(p.get("id", 0) or 0)
            for aw in (p.get("playerAwards") or []):
                if int(aw.get("type", -1)) == 3 and int(aw.get("year", 0) or 0) == yr:
                    pl = int(aw.get("top20Placement", 0) or 0)
                    if pl > 0:
                        old_top20.append({"playerId": pid, "name": p.get("name", f"#{pid}"), "rank": pl})
                        old_rank_by_pid[pid] = pl
        old_top20.sort(key=lambda r: (r["rank"], r["playerId"]))

        pred = self._compute_top20_prediction(yr)
        vpid = int(vote_player_id or 0)
        new_top20: list[dict[str, Any]] = []

        if mode_n == "recalculate":
            ranked = []
            for c in pred.get("candidates", []):
                sc = float(c["votedScore"] if (vpid and int(c["playerId"]) == vpid) else c["baseScore"])
                ranked.append((sc, float(c["t10Rating"]), -int(c["playerId"]), c))
            ranked.sort(key=lambda x: (-x[0], -x[1], x[2]))
            for idx, (sc, _, _, c) in enumerate(ranked[:20], start=1):
                pid_c = int(c["playerId"])
                new_top20.append({
                    "rank": idx,
                    "playerId": pid_c,
                    "name": c.get("name", f"#{pid_c}"),
                    "teamId": int(c.get("teamId", 0) or 0),
                    "teamName": c.get("teamName", "Free Agent"),
                    "score": round(sc, 4),
                    "mvps": int(c.get("mvps", 0) or 0),
                    "evps": int(c.get("evps", 0) or 0),
                    "oldRank": old_rank_by_pid.get(pid_c, 0),
                })

        emails_updated = 0
        emails_removed = 0
        cur_dt = self.data.get("datetime") or {}
        cur_save_year = int(cur_dt.get("year", 0) or 0)

        if not dry_run:
            snap_lbl = f"Before {'Recalculate' if mode_n == 'recalculate' else 'Clear'} {yr} Top 20"
            self.create_snapshot(snap_lbl)

            for p in self.data.get("players", {}).get("players", []):
                aws = p.get("playerAwards")
                if aws:
                    p["playerAwards"] = [
                        a for a in aws
                        if not (int(a.get("type", -1)) == 3 and int(a.get("year", 0) or 0) == yr)
                    ]

            if mode_n == "recalculate":
                for row in new_top20:
                    po = self.players_by_id.get(row["playerId"])
                    if po is not None:
                        po.setdefault("playerAwards", []).append({
                            "type": 3,
                            "tournamentTemplate": 0,
                            "year": yr,
                            "month": 0,
                            "teamId": int(row["teamId"]),
                            "top20Placement": int(row["rank"]),
                        })
                new_ids = [r["playerId"] for r in new_top20]
                for em in self.data.get("emails", {}).get("emails", []):
                    em_yr = int((em.get("datetime") or {}).get("year", 0) or 0)
                    if em.get("topicKey") == "PLAYER_OF_THE_YEAR_RESULT_TOPIC" and em_yr == yr:
                        em["top20PlayerIds"] = list(new_ids)
                        emails_updated += 1
            else:
                emails_root = self.data.get("emails") or {}
                emails_list = emails_root.get("emails")
                if isinstance(emails_list, list):
                    kept_emails = []
                    for em in emails_list:
                        em_yr = int((em.get("datetime") or {}).get("year", 0) or 0)
                        if em.get("topicKey") == "PLAYER_OF_THE_YEAR_RESULT_TOPIC" and em_yr == yr:
                            emails_removed += 1
                        else:
                            kept_emails.append(em)
                    emails_root["emails"] = kept_emails

            if yr == cur_save_year:
                self.data.setdefault("profile", {})["playerOfTheYearScores"] = []

            self.dirty = True

        return {
            "dryRun": dry_run,
            "mode": mode_n,
            "year": yr,
            "votePlayerId": vpid,
            "oldCount": len(old_top20),
            "newCount": len(new_top20),
            "oldTop20": old_top20,
            "newTop20": new_top20,
            "changed": [x["playerId"] for x in old_top20] != [x["playerId"] for x in new_top20] or (mode_n == "clear" and len(old_top20) > 0),
            "emailsUpdated": emails_updated,
            "emailsRemoved": emails_removed,
        }

    # ------------------------------------------------------------------
    # Live Vulture & Transfer Market Radar
    # ------------------------------------------------------------------

    def _market_nation_lang_rules(self) -> tuple[dict[int, set[int]], Any]:
        nat_counts: dict[int, dict[int, int]] = {}
        for p in self.players_by_id.values():
            pn = int(p.get("nation", 0) or 0)
            if not pn:
                continue
            for lg in p.get("languagesSpoken") or []:
                if int(lg.get("languageSkill", 0) or 0) >= 15:
                    lid = int(lg.get("languageId", 0) or 0)
                    if lid:
                        b = nat_counts.setdefault(pn, {})
                        b[lid] = b.get(lid, 0) + 1
        req_langs: dict[int, set[int]] = {}
        for pn, cnts in nat_counts.items():
            ranked = sorted(cnts.items(), key=lambda x: -x[1])
            allowed = {ranked[0][0]}
            if len(ranked) > 1 and ranked[1][1] >= ranked[0][1] * 0.40:
                allowed.add(ranked[1][0])
            req_langs[pn] = allowed

        def _violates(t_obj: dict[str, Any], p_obj: dict[str, Any]) -> tuple[bool, str]:
            hb = int((t_obj.get("owner") or {}).get("hiringBias", 2))
            tn = int(t_obj.get("nation", 0) or 0)
            pn = int(p_obj.get("nation", 0) or 0)
            if hb == 0 and tn and pn and tn != pn:
                return True, f"Only National ({gd.NATIONS.get(tn, f'#{tn}')})"
            if hb == 1 and tn:
                req = req_langs.get(tn, set())
                p_l = {int(lg.get("languageId", 0)) for lg in (p_obj.get("languagesSpoken") or []) if int(lg.get("languageSkill", 0) or 0) >= 10}
                if req and not (p_l & req):
                    return True, f"Only {gd.NATIONS.get(tn, '')} Language"
            return False, ""

        return req_langs, _violates

    def get_market_radar(self) -> dict[str, Any]:
        if self.data is None:
            return {"loaded": False}
        _, _violates = self._market_nation_lang_rules()

        swarms_by_pid: dict[int, dict[int, dict[str, Any]]] = {}
        active_bids: list[dict[str, Any]] = []
        club_rows: list[dict[str, Any]] = []

        total_rows = 0
        total_active = 0
        total_cd = 0
        total_policy_bad = 0

        for t in self.data["teams"]["teams"]:
            tid = int(t["id"])
            tname = t.get("name", f"Team #{tid}")
            pis = t.get("personInterests") or []
            c_tot = 0
            c_act = 0
            c_cd = 0
            c_viol = 0
            for pi in pis:
                pid = int(pi.get("playerId", 0) or 0)
                if pid <= 0 or pid not in self.players_by_id:
                    continue
                p_obj = self.players_by_id[pid]
                total_rows += 1
                c_tot += 1
                bs = int(pi.get("bidStatus", 0) or 0)
                sc = float(pi.get("score", 0.0) or 0.0)
                cd = int(pi.get("cooldown", 0) or 0)
                urg = int(pi.get("urgency", 3) or 0)
                role = int(pi.get("roleInterest", 0) or 0)
                viol, vreason = _violates(t, p_obj)
                if 1 <= bs <= 6:
                    total_active += 1
                    c_act += 1
                    co = pi.get("playerContractOffer") or {}
                    c_cur = self.player_contract_by_pid.get(pid)
                    active_bids.append({
                        "playerId": pid,
                        "playerName": p_obj.get("name", f"#{pid}"),
                        "playerSkill": _player_avg_skill(p_obj),
                        "fromTeamName": self.teams_by_id.get(c_cur["teamId"], {}).get("name", "Free Agent") if c_cur and c_cur.get("teamId") in self.teams_by_id else "Free Agent",
                        "bidderId": tid,
                        "bidderName": tname,
                        "status": bs,
                        "statusLabel": _BID_STATUS_LABELS.get(bs, f"Status {bs}"),
                        "role": _ROLE_INTEREST_LABELS.get(role, "Any"),
                        "urgency": _URGENCY_LABELS.get(urg, "Med"),
                        "score": round(sc, 2),
                        "salaryYear": int(co.get("salaryYear", 0) or 0),
                        "buyoutPrice": int(pi.get("buyoutPrice", 0) or 0),
                        "violatesPolicy": viol,
                        "violationReason": vreason,
                    })
                elif bs in (7, 8):
                    total_cd += 1
                    c_cd += 1
                if viol:
                    total_policy_bad += 1
                    c_viol += 1

                tb = swarms_by_pid.setdefault(pid, {}).get(tid)
                if tb is None:
                    tb = {
                        "teamId": tid,
                        "teamName": tname,
                        "bestStatus": bs,
                        "bestStatusLabel": _BID_STATUS_LABELS.get(bs, f"#{bs}"),
                        "isActive": 1 <= bs <= 6,
                        "isCooldown": bs in (7, 8),
                        "peakScore": round(sc, 2),
                        "maxCooldown": cd,
                        "entries": 0,
                        "violatesPolicy": viol,
                        "violationReason": vreason,
                    }
                    swarms_by_pid[pid][tid] = tb
                tb["entries"] += 1
                if sc > tb["peakScore"]:
                    tb["peakScore"] = round(sc, 2)
                tb["maxCooldown"] = max(tb["maxCooldown"], cd)
                if (1 <= bs <= 6) and not tb["isActive"]:
                    tb["bestStatus"] = bs
                    tb["bestStatusLabel"] = _BID_STATUS_LABELS.get(bs, f"#{bs}")
                    tb["isActive"] = True

            if c_tot > 0:
                rh = t.get("rankingHistory") or []
                club_rows.append({
                    "teamId": tid,
                    "teamName": tname,
                    "worldRank": int(rh[-1]) if rh else 0,
                    "totalInterests": c_tot,
                    "activeBids": c_act,
                    "cooldowns": c_cd,
                    "policyViolations": c_viol,
                })

        vulture_swarms = []
        for pid, tmap in swarms_by_pid.items():
            p_obj = self.players_by_id[pid]
            c_cur = self.player_contract_by_pid.get(pid)
            cur_tid = c_cur["teamId"] if c_cur else 0
            clubs = sorted(tmap.values(), key=lambda x: (-int(x["isActive"]), -int(x["isCooldown"]), -x["peakScore"]))
            vulture_swarms.append({
                "playerId": pid,
                "playerName": p_obj.get("name", f"#{pid}"),
                "age": int(p_obj.get("age", 0) or 0),
                "avgSkill": _player_avg_skill(p_obj),
                "teamName": self.teams_by_id.get(cur_tid, {}).get("name", "Free Agent") if cur_tid else "Free Agent",
                "benched": bool(c_cur.get("benched")) if c_cur else False,
                "distinctClubs": len(clubs),
                "totalRows": sum(c["entries"] for c in clubs),
                "activeBids": sum(1 for c in clubs if c["isActive"]),
                "cooldowns": sum(1 for c in clubs if c["isCooldown"]),
                "policyMismatches": sum(1 for c in clubs if c["violatesPolicy"]),
                "peakScore": max(c["peakScore"] for c in clubs),
                "clubs": clubs,
            })

        vulture_swarms.sort(key=lambda r: (-r["distinctClubs"], -r["activeBids"], -r["avgSkill"]))
        active_bids.sort(key=lambda r: (-r["score"], -r["playerSkill"]))
        club_rows.sort(key=lambda r: (-r["totalInterests"], -r["activeBids"]))

        return {
            "loaded": True,
            "summary": {
                "totalInterestRows": total_rows,
                "huntedPlayers": len(swarms_by_pid),
                "activeBids": total_active,
                "cooldownRows": total_cd,
                "policyViolations": total_policy_bad,
            },
            "vultureSwarms": vulture_swarms[:80],
            "activeBids": active_bids[:120],
            "clubActivity": club_rows[:60],
        }

    def clear_market_bids(self, mode: str, player_id: int = 0, team_id: int = 0) -> dict[str, Any]:
        if self.data is None:
            raise RuntimeError("No save file is currently loaded.")
        _, _violates = self._market_nation_lang_rules()
        self.create_snapshot(f"Before Market Cleanup ({mode})")
        removed = 0

        for t in self.data["teams"]["teams"]:
            tid = int(t["id"])
            if mode == "clear_team_cooldowns" and tid != int(team_id):
                continue
            if mode == "cancel_bid" and tid != int(team_id):
                continue
            pis = t.get("personInterests") or []
            if not pis:
                continue
            kept = []
            for pi in pis:
                pid = int(pi.get("playerId", 0) or 0)
                bs = int(pi.get("bidStatus", 0) or 0)
                drop = False
                if mode == "purge_policy_violations" and pid in self.players_by_id:
                    drop = _violates(t, self.players_by_id[pid])[0]
                elif mode == "clear_player_cooldowns" and pid == int(player_id) and bs in (7, 8):
                    drop = True
                elif mode == "clear_team_cooldowns" and tid == int(team_id) and bs in (7, 8):
                    drop = True
                elif mode == "cancel_bid" and tid == int(team_id) and pid == int(player_id):
                    drop = True
                if drop:
                    removed += 1
                else:
                    kept.append(pi)
            t["personInterests"] = kept

        if removed > 0:
            self.dirty = True
        return {"removedCount": removed, "radar": self.get_market_radar()}

    # ------------------------------------------------------------------
    # Live Weapon Meta Lab
    # ------------------------------------------------------------------

    def _enrich_weapon(self, w: dict[str, Any]) -> dict[str, Any]:
        dmg = float(w.get("damage", 0) or 0)
        armor_m = float(w.get("armorMultiplier", 1.0) or 1.0)
        hs_m = float(w.get("hsMultiplier", 1.0) or 1.0)
        si = float(w.get("shotInterval", 0.1) or 0.1)
        arm_body = round(dmg * armor_m, 1)
        arm_hs = round(dmg * hs_m * armor_m, 1)
        rpm = round(60.0 / max(si, 0.02))
        stk = math.ceil(100.0 / max(arm_body, 1.0))
        return {
            "id": int(w.get("id", 0)),
            "name": w.get("customName") or w.get("iconName") or f"Weapon #{w.get('id')}",
            "type": int(w.get("type", 0) or 0),
            "typeLabel": _WEAPON_TYPES.get(int(w.get("type", 0) or 0), "Other"),
            "price": int(w.get("price", 0) or 0),
            "damage": int(w.get("damage", 0) or 0),
            "hsMultiplier": round(hs_m, 3),
            "armorMultiplier": round(armor_m, 3),
            "accuracy": round(float(w.get("accuracy", 0) or 0), 2),
            "movingAccuracyPenalty": round(float(w.get("movingAccuracyPenalty", 0) or 0), 3),
            "recoilIncreasePerShot": round(float(w.get("recoilIncreasePerShot", 0) or 0), 3),
            "recoilResetTime": round(float(w.get("recoilResetTime", 0) or 0), 3),
            "shotInterval": round(si, 3),
            "damageDropOffPerUnitOfDistance": round(float(w.get("damageDropOffPerUnitOfDistance", 0) or 0), 4),
            "ammo": int(w.get("ammo", 0) or 0),
            "killReward": int(w.get("killReward", 0) or 0),
            "reloadTime": int(w.get("reloadTime", 0) or 0),
            "tier": int(w.get("tier", 1) or 1),
            "armoredBodyDmg": arm_body,
            "armoredHsDmg": arm_hs,
            "rpm": rpm,
            "shotsToKillBody": stk,
        }

    def get_weapons_meta(self) -> dict[str, Any]:
        if self.data is None:
            return {"loaded": False}
        raw = self.data.get("weapons", {}).get("weapons", [])
        items = [self._enrich_weapon(w) for w in raw]
        items.sort(key=lambda w: (w["type"], -w["price"], w["name"]))
        return {"loaded": True, "count": len(items), "weapons": items}

    def update_weapon(self, weapon_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        if self.data is None:
            raise RuntimeError("No save file is currently loaded.")
        raw = self.data.get("weapons", {}).get("weapons", [])
        w = next((x for x in raw if int(x.get("id", 0)) == int(weapon_id)), None)
        if not w:
            raise ValueError(f"Weapon #{weapon_id} not found.")
        self.create_snapshot(f"Before Weapon Edit: {w.get('customName', weapon_id)}")

        int_bounds = {
            "price": (0, 16000), "damage": (1, 500), "ammo": (1, 200),
            "killReward": (0, 2500), "reloadTime": (1, 12), "tier": (1, 10),
        }
        flt_bounds = {
            "hsMultiplier": (1.0, 10.0), "armorMultiplier": (0.1, 2.0), "accuracy": (1.0, 100.0),
            "movingAccuracyPenalty": (0.0, 2.0), "recoilIncreasePerShot": (0.0, 3.0),
            "recoilResetTime": (0.01, 2.0), "shotInterval": (0.02, 5.0),
            "damageDropOffPerUnitOfDistance": (0.0, 0.2),
        }
        for k, (lo, hi) in int_bounds.items():
            if k in payload:
                w[k] = int(_clamp(int(payload[k]), lo, hi))
        for k, (lo, hi) in flt_bounds.items():
            if k in payload:
                w[k] = float(_clamp(float(payload[k]), lo, hi))
        self.dirty = True
        return {"weapon": self._enrich_weapon(w), "weapons": self.get_weapons_meta()["weapons"]}

    def apply_weapon_preset(self, preset_name: str) -> dict[str, Any]:
        if self.data is None:
            raise RuntimeError("No save file is currently loaded.")
        raw = self.data.get("weapons", {}).get("weapons", [])
        self.create_snapshot(f"Before Weapon Preset: {preset_name}")
        updated = 0
        for w in raw:
            nm = str(w.get("customName") or "").upper()
            wtype = int(w.get("type", 0) or 0)
            if preset_name == "awp_era":
                if "AWP" in nm:
                    w["price"] = 4500
                    w["ammo"] = 10
                    w["killReward"] = 300
                    w["shotInterval"] = 1.25
                    updated += 1
            elif preset_name == "rifle_laser":
                if wtype == 2:
                    w["accuracy"] = min(98.0, float(w.get("accuracy", 25.0) or 25.0) * 1.15)
                    w["recoilIncreasePerShot"] = max(0.05, float(w.get("recoilIncreasePerShot", 0.5) or 0.5) * 0.8)
                    updated += 1
            elif preset_name == "eco_chaos":
                if wtype in (0, 1):
                    w["armorMultiplier"] = min(1.0, float(w.get("armorMultiplier", 0.6) or 0.6) + 0.12)
                    w["killReward"] = min(1200, int(w.get("killReward", 300) or 300) + 150)
                    updated += 1
            elif preset_name == "cs2_balanced":
                if "AWP" in nm:
                    w["price"] = 4750
                    w["ammo"] = 5
                    w["killReward"] = 100
                    w["shotInterval"] = 1.455
                    updated += 1
                elif "M4A1" in nm or "M4A4" in nm:
                    w["price"] = 2900
                    updated += 1
            else:
                raise ValueError(f"Unknown weapon preset: {preset_name}")
        self.dirty = True
        return {"preset": preset_name, "updatedCount": updated, "weapons": self.get_weapons_meta()["weapons"]}

    # ------------------------------------------------------------------
    # Save Diff & Time Machine
    # ------------------------------------------------------------------

    def list_comparable_saves(self) -> list[dict[str, Any]]:
        results = list(discover_save_files())
        seen = {r["path"] for r in results}
        cur_res = str(self.path.resolve()) if self.path else ""
        for folder, src in ((BACKUPS_DIR, "Save Editor Backups"), (EDITOR_DIR / "csm" / "savestudio" / "backups", "Save Studio Backups")):
            if not folder.exists():
                continue
            for p in sorted(folder.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:25]:
                rp = str(p.resolve())
                if rp in seen:
                    continue
                seen.add(rp)
                st = p.stat()
                results.append({
                    "name": p.name,
                    "source": src,
                    "path": rp,
                    "size_mb": round(st.st_size / (1024 * 1024), 2),
                    "modified": dt.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M"),
                })
        for r in results:
            r["isCurrent"] = bool(cur_res and r["path"] == cur_res)
        return results

    def compare_saves(self, baseline_path: str) -> dict[str, Any]:
        if self.data is None:
            raise RuntimeError("No save file is currently loaded.")
        bp = Path(baseline_path).resolve()
        if not bp.exists():
            raise FileNotFoundError(f"Baseline save not found: {bp}")
        with bp.open("r", encoding="utf-8") as f:
            base = self._validate_loaded_root(json.load(f))

        b_dt = base.get("datetime") or {}
        c_dt = self.data.get("datetime") or {}
        fmt_dt = lambda d: f"{d.get('year', 0)}-{int(d.get('month', 0)):02d}-{int(d.get('day', 0)):02d}" if d.get("year") else "-"

        b_players = {p["id"]: p for p in base.get("players", {}).get("players", [])}
        skill_diffs = []
        for pid, cp in self.players_by_id.items():
            bp_obj = b_players.get(pid)
            if not bp_obj:
                continue
            c_avg = round(self._player_practical_avg(cp), 2)
            b_avg = round(self._player_practical_avg(bp_obj), 2)
            diff = round(c_avg - b_avg, 2)
            if abs(diff) >= 0.05:
                con = self.player_contract_by_pid.get(pid)
                tid = con["teamId"] if con else 0
                skill_diffs.append({
                    "playerId": pid,
                    "name": cp.get("name", f"#{pid}"),
                    "age": int(cp.get("age", 0) or 0),
                    "teamName": self.teams_by_id.get(tid, {}).get("name", "Free Agent") if tid else "Free Agent",
                    "beforeAvg": b_avg,
                    "afterAvg": c_avg,
                    "delta": diff,
                })
        skill_risers = sorted([x for x in skill_diffs if x["delta"] > 0], key=lambda x: (-x["delta"], -x["afterAvg"]))[:30]
        skill_fallers = sorted([x for x in skill_diffs if x["delta"] < 0], key=lambda x: (x["delta"], x["afterAvg"]))[:30]

        b_teams = {t["id"]: t for t in base.get("teams", {}).get("teams", [])}
        rank_diffs = []
        bal_swings = []
        for tid, ct in self.teams_by_id.items():
            bt = b_teams.get(tid)
            if not bt:
                continue
            c_rh = ct.get("rankingHistory") or []
            b_rh = bt.get("rankingHistory") or []
            c_r = int(c_rh[-1]) if c_rh else 0
            b_r = int(b_rh[-1]) if b_rh else 0
            if c_r > 0 and b_r > 0 and c_r != b_r:
                # Positive climb means moved UP (lower rank number)
                rank_diffs.append({
                    "teamId": tid,
                    "name": ct.get("name", ""),
                    "beforeRank": b_r,
                    "afterRank": c_r,
                    "climb": b_r - c_r,
                })
            c_bal = int((ct.get("teamFinances") or {}).get("currentBalance", 0) or 0)
            b_bal = int((bt.get("teamFinances") or {}).get("currentBalance", 0) or 0)
            if c_bal != b_bal:
                bal_swings.append({
                    "teamId": tid,
                    "name": ct.get("name", ""),
                    "beforeBalance": b_bal,
                    "afterBalance": c_bal,
                    "delta": c_bal - b_bal,
                })
        rank_climbers = sorted([x for x in rank_diffs if x["climb"] > 0], key=lambda x: (-x["climb"], x["afterRank"]))[:30]
        rank_fallers = sorted([x for x in rank_diffs if x["climb"] < 0], key=lambda x: (x["climb"], -x["afterRank"]))[:30]
        bal_swings.sort(key=lambda x: -abs(x["delta"]))

        def _tx_sig(th: dict[str, Any]) -> tuple[int, int, int, int, int, int]:
            d = th.get("datetime") or {}
            return (
                int(th.get("personType", 0)),
                int(th.get("personId", 0)),
                int(th.get("fromTeamId", 0)),
                int(th.get("otherTeamId", 0)),
                int(d.get("year", 0)),
                int(d.get("month", 0)) * 100 + int(d.get("day", 0)),
            )

        base_tx_sigs = {_tx_sig(th) for th in (base.get("transferHistories", {}).get("transferHistories", []) or [])}
        new_transfers = []
        for th in reversed(self.data.get("transferHistories", {}).get("transferHistories", []) or []):
            if _tx_sig(th) not in base_tx_sigs:
                ptype = int(th.get("personType", 0) or 0)
                pid = int(th.get("personId", 0) or 0)
                pname = self.players_by_id.get(pid, {}).get("name") if ptype == 0 else self.staff_by_id.get(pid, {}).get("name")
                fid = int(th.get("fromTeamId", 0) or 0)
                tid_n = int(th.get("otherTeamId", 0) or 0)
                d = th.get("datetime") or {}
                new_transfers.append({
                    "personType": "Player" if ptype == 0 else "Staff",
                    "personId": pid,
                    "personName": pname or f"#{pid}",
                    "fromTeamName": self.teams_by_id.get(fid, {}).get("name", "Free Agent") if fid else "Free Agent",
                    "toTeamName": self.teams_by_id.get(tid_n, {}).get("name", "Free Agent") if tid_n else "Free Agent",
                    "purchasePrice": int(th.get("purchasePrice", 0) or 0),
                    "date": fmt_dt(d),
                })

        tmpl_names, _, _ = self._stats_lookups()
        raw_tourns = {x["id"]: x for x in self.data.get("tournaments", {}).get("tournaments", [])}
        base_trophies = {
            (tid_b, int(th.get("tournamentId", 0)), int(th.get("year", 0)))
            for tid_b, bt in b_teams.items()
            for th in (bt.get("trophyHistories") or [])
        }
        new_trophies = []
        for tid, ct in self.teams_by_id.items():
            for th in (ct.get("trophyHistories") or []):
                sig = (tid, int(th.get("tournamentId", 0)), int(th.get("year", 0)))
                if sig not in base_trophies:
                    new_trophies.append({
                        "teamId": tid,
                        "teamName": ct.get("name", f"#{tid}"),
                        "tournamentName": raw_tourns.get(sig[1], {}).get("name") or tmpl_names.get(int(th.get("tournamentTemplate", 0) or 0)) or f"Event #{sig[1]}",
                        "year": sig[2],
                    })

        base_awards = {
            (pid_b, int(aw.get("type", 0)), int(aw.get("tournamentTemplate", 0)), int(aw.get("year", 0)), int(aw.get("month", 0)))
            for pid_b, bp_obj in b_players.items()
            for aw in (bp_obj.get("playerAwards") or [])
        }
        new_awards = []
        for pid, cp in self.players_by_id.items():
            for aw in (cp.get("playerAwards") or []):
                sig = (pid, int(aw.get("type", 0)), int(aw.get("tournamentTemplate", 0)), int(aw.get("year", 0)), int(aw.get("month", 0)))
                if sig not in base_awards and sig[1] in (0, 2, 3):
                    new_awards.append({
                        "playerId": pid,
                        "playerName": cp.get("name", f"#{pid}"),
                        "typeLabel": _AWARD_TYPES.get(sig[1], f"Type {sig[1]}"),
                        "tournamentName": tmpl_names.get(sig[2], f"Template #{sig[2]}"),
                        "date": f"{sig[3]}-{sig[4]:02d}",
                        "top20Placement": int(aw.get("top20Placement", 0) or 0),
                    })

        return {
            "baselineMeta": {
                "name": bp.name,
                "path": str(bp),
                "date": fmt_dt(b_dt),
                "players": len(b_players),
                "teams": len(b_teams),
                "matches": len([m for m in base.get("matches", {}).get("matches", []) if m.get("processingCompleted")]),
            },
            "currentMeta": {
                "name": self.path.name if self.path else (self.virtual_name or "Current Save"),
                "date": fmt_dt(c_dt),
                "players": len(self.players_by_id),
                "teams": len(self.teams_by_id),
                "matches": len([m for m in self.data.get("matches", {}).get("matches", []) if m.get("processingCompleted")]),
            },
            "skillRisers": skill_risers,
            "skillFallers": skill_fallers,
            "rankClimbers": rank_climbers,
            "rankFallers": rank_fallers,
            "balanceSwings": bal_swings[:25],
            "newTransfers": new_transfers[:100],
            "newTrophies": new_trophies[:60],
            "newAwards": new_awards[:60],
        }
