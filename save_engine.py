"""Core save loading, saving, validation, AI tactics rebuilding, and transfer logic."""

from __future__ import annotations

import copy
import datetime as dt
import json
import math
import os
import random
import shutil
import sys
from pathlib import Path
from typing import Any

from gamedata import (
    HIRING_BIAS,
    LANGUAGES,
    MAP_POS_TO_PLAYER_ATTR,
    MAP_TACTIC_POSITIONS,
    NATIONS,
    PLAYER_POSITIONS,
    PLAYER_SKILLS,
    RELATIONSHIP_TYPES,
    STAFF_ROLES,
    STAFF_SKILLS,
)

EDITOR_DIR = Path(__file__).resolve().parent
BACKUPS_DIR = EDITOR_DIR / "backups"


def discover_save_dirs() -> list[tuple[str, Path]]:
    """Return candidate CS Manager SavedGames folders across Windows, macOS, and Linux/Proton."""
    home = Path.home()
    candidates: list[tuple[str, Path]] = []

    if os.name == "nt":
        user_profile = Path(os.environ.get("USERPROFILE", str(home)))
        candidates.append(("SavedGames", user_profile / "AppData" / "LocalLow" / "Crumana" / "CS Manager" / "SavedGames"))
        if user_profile != home:
            candidates.append(("SavedGames", home / "AppData" / "LocalLow" / "Crumana" / "CS Manager" / "SavedGames"))
    elif sys.platform == "darwin":
        app_sup = home / "Library" / "Application Support"
        candidates.append(("SavedGames", app_sup / "Crumana" / "CS Manager" / "SavedGames"))
        candidates.append(("SavedGames", app_sup / "unity.Crumana.CS Manager" / "SavedGames"))
    else:
        candidates.append(("SavedGames", home / ".config" / "unity3d" / "Crumana" / "CS Manager" / "SavedGames"))
        for steam_root in (
            home / ".steam" / "steam" / "steamapps" / "compatdata",
            home / ".local" / "share" / "Steam" / "steamapps" / "compatdata",
            home / ".var" / "app" / "com.valvesoftware.Steam" / ".local" / "share" / "Steam" / "steamapps" / "compatdata",
        ):
            if steam_root.exists():
                for pfx_sg in steam_root.glob("*/pfx/drive_c/users/steamuser/AppData/LocalLow/Crumana/CS Manager/SavedGames"):
                    candidates.append(("Steam Proton SavedGames", pfx_sg))

    candidates.append(("Editor Folder", EDITOR_DIR))
    return candidates


def get_default_saves_dir() -> Path:
    for source, folder in discover_save_dirs():
        if source != "Editor Folder" and folder.exists():
            return folder
    return discover_save_dirs()[0][1]


DEFAULT_SAVES_DIR = get_default_saves_dir()


def discover_save_files() -> list[dict[str, Any]]:
    """Return available .json save files from CS Manager's SavedGames and the editor folder."""
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source, folder in discover_save_dirs():
        if not folder.exists():
            continue
        for p in sorted(folder.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
            resolved = str(p.resolve())
            if resolved in seen:
                continue
            seen.add(resolved)
            stat = p.stat()
            results.append(
                {
                    "name": p.name,
                    "source": source,
                    "path": resolved,
                    "size_mb": round(stat.st_size / (1024 * 1024), 2),
                    "modified": dt.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                }
            )
    return results


def _clamp(val: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, val))


def _wants_role(desire: int, role_status: int) -> bool:
    if role_status == 0:
        return desire >= 15
    if role_status == 1:
        return 6 < desire < 15
    if role_status == 2:
        return desire <= 6
    return False


def _role_comfort_norm(role_comfort: float) -> float:
    # Matches MapPositionAttribute::GetRoleComfortNormalized: Lerp(0, 1, (comfort - 1) / 8) -> wait:
    # IL: Mathf.Lerp(0, 1, roleComfort / 9) or (roleComfort-1)/9; clamping [0, 1].
    return _clamp((float(role_comfort) - 1.0) / 9.0, 0.0, 1.0)


def _lane_protection_score(pos_type: int, lane: int) -> float:
    # Matches MapPosition::GetLaneProtectionScore(lane): 0=A, 1=B, 2=Mid
    if lane == 0:  # A
        if pos_type == 5:
            return 3.0
        if pos_type == 6:
            return 2.0
        if pos_type in (9, 10):
            return 0.5
        return 0.0
    if lane == 2:  # Mid
        if pos_type == 9:
            return 4.0
        if pos_type in (6, 8, 10):
            return 2.0
        return 0.0
    if lane == 1:  # B
        if pos_type == 7:
            return 3.0
        if pos_type == 8:
            return 2.0
        if pos_type == 10:
            return 0.5
        return 0.0
    return 0.0


def _player_avg_skill(player: dict[str, Any]) -> float:
    skills = player.get("skills", {})
    if not skills:
        return 0.0
    return round(sum(skills.values()) / len(skills), 2)


def _staff_avg_skill(staff: dict[str, Any]) -> float:
    skills = staff.get("skills", {})
    if not skills:
        return 0.0
    return round(sum(skills.values()) / len(skills), 2)


class SaveSession:
    """In-memory representation of a loaded CS Manager save file."""

    def __init__(self) -> None:
        self.path: Path | None = None
        self.virtual_name: str = ""
        self.data: dict[str, Any] | None = None
        self.dirty: bool = False
        self.players_by_id: dict[int, dict[str, Any]] = {}
        self.staff_by_id: dict[int, dict[str, Any]] = {}
        self.teams_by_id: dict[int, dict[str, Any]] = {}
        self.maps_by_id: dict[int, dict[str, Any]] = {}
        self.player_contract_by_pid: dict[int, dict[str, Any]] = {}
        self.staff_contract_by_sid: dict[int, dict[str, Any]] = {}

    def _validate_loaded_root(self, data: Any) -> dict[str, Any]:
        if not isinstance(data, dict):
            raise ValueError("Invalid CS Manager save file (root JSON must be an object).")
        for req_key in ("players", "playerContracts", "teams", "staffers", "staffContracts"):
            if req_key not in data:
                raise ValueError(f"Invalid CS Manager save file (missing '{req_key}').")
        return data

    def load(self, file_path: str | Path) -> dict[str, Any]:
        p = Path(file_path).resolve()
        if not p.exists():
            raise FileNotFoundError(f"Save file not found: {p}")
        with p.open("r", encoding="utf-8") as f:
            data = self._validate_loaded_root(json.load(f))
        self.path = p
        self.virtual_name = p.name
        self.data = data
        self.dirty = False
        self.rebuild_indices()
        return self.summary()

    def load_upload(self, filename: str, raw_text: str) -> dict[str, Any]:
        """Load a save file uploaded via browser from any device."""
        clean_name = Path(filename or "uploaded_save.json").name
        if not clean_name.lower().endswith(".json"):
            clean_name += ".json"
        data = self._validate_loaded_root(json.loads(raw_text))
        self.path = None
        self.virtual_name = clean_name
        self.data = data
        self.dirty = False
        self.rebuild_indices()
        return self.summary()

    def export_json_bytes(self) -> tuple[str, bytes]:
        """Serialize the current save into Unity-compact JSON bytes for browser download."""
        if self.data is None:
            raise RuntimeError("No save file is currently loaded.")
        filename = self.path.name if self.path else (self.virtual_name or "cs_manager_save.json")
        raw = json.dumps(self.data, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        return filename, raw

    def rebuild_indices(self) -> None:
        assert self.data is not None
        self.players_by_id = {p["id"]: p for p in self.data["players"]["players"]}
        self.staff_by_id = {s["id"]: s for s in self.data["staffers"]["staffers"]}
        self.teams_by_id = {t["id"]: t for t in self.data["teams"]["teams"]}
        self.maps_by_id = {m["id"]: m for m in self.data.get("maps", {}).get("maps", [])}
        self.player_contract_by_pid = {}
        for c in self.data["playerContracts"]["playerContracts"]:
            self.player_contract_by_pid[c["playerId"]] = c
        self.staff_contract_by_sid = {}
        for c in self.data["staffContracts"]["staffContracts"]:
            self.staff_contract_by_sid[c["staffId"]] = c

    def save(self, target_path: str | Path | None = None) -> dict[str, Any]:
        if self.data is None:
            raise RuntimeError("No save file is currently loaded.")
        if target_path is None and self.path is None:
            raise ValueError("Uploaded browser save has no local file path yet — use 'Save As...' or 'Download .json'.")
        dest = Path(target_path).resolve() if target_path else self.path
        assert dest is not None
        backup_path: str | None = None
        if dest.exists():
            BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
            stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
            bpath = BACKUPS_DIR / f"{dest.stem}_{stamp}{dest.suffix}"
            shutil.copy2(dest, bpath)
            backup_path = str(bpath)

        tmp_path = dest.with_suffix(".json.tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            # Match UnityEngine.JsonUtility.ToJson(..., false) compact formatting
            json.dump(self.data, f, separators=(",", ":"), ensure_ascii=False)
        tmp_path.replace(dest)
        self.path = dest
        self.virtual_name = dest.name
        self.dirty = False
        return {
            "saved_path": str(dest),
            "backup_path": backup_path,
            "summary": self.summary(),
        }

    def summary(self) -> dict[str, Any]:
        if self.data is None:
            return {"path": "", "filename": "", "dirty": False, "counts": {}, "maps": []}
        profile = self.data.get("profile", {})
        user_team_id = profile.get("team", 0)
        user_team = self.teams_by_id.get(user_team_id)
        fname = self.path.name if self.path else (self.virtual_name or "uploaded_save.json")
        return {
            "path": str(self.path) if self.path else f"browser://{fname}",
            "isBrowserUpload": self.path is None,
            "filename": fname,
            "dirty": self.dirty,
            "gameVersion": self.data.get("gameVersion", ""),
            "datetime": self.data.get("datetime", {}),
            "managerName": profile.get("name", ""),
            "userTeamId": user_team_id,
            "userTeamName": user_team["name"] if user_team else "Unemployed",
            "counts": {
                "players": len(self.players_by_id),
                "staffers": len(self.staff_by_id),
                "teams": len(self.teams_by_id),
                "playerContracts": len(self.data["playerContracts"]["playerContracts"]),
                "staffContracts": len(self.data["staffContracts"]["staffContracts"]),
                "transferHistories": len(self.data.get("transferHistories", {}).get("transferHistories", [])),
                "relationships": len(self.data.get("playerRelationships", {}).get("playerRelationships", [])),
            },
            "maps": [
                {"id": m["id"], "name": m["name"], "active": bool(m.get("active", True))}
                for m in self.data.get("maps", {}).get("maps", [])
            ],
        }

    # ------------------------------------------------------------------
    # Team Roster & AI Tactics Helpers (faithful to Assembly-CSharp.dll)
    # ------------------------------------------------------------------

    def get_team_player_contracts(self, team_id: int) -> list[dict[str, Any]]:
        assert self.data is not None
        return [c for c in self.data["playerContracts"]["playerContracts"] if c.get("teamId") == team_id]

    def get_team_staff_contracts(self, team_id: int) -> list[dict[str, Any]]:
        assert self.data is not None
        return [c for c in self.data["staffContracts"]["staffContracts"] if c.get("teamId") == team_id]

    def remove_player_from_tactics(self, team: dict[str, Any], player_id: int) -> None:
        """Matches Team::RemovePlayerFromTactics across all generalTactics and mapTactics."""
        for gt in team.get("generalTactics", []):
            for field in ("iglId", "secondIglId", "sniperId", "secondSniperId"):
                if gt.get(field) == player_id:
                    gt[field] = 0
        for mt in team.get("mapTactics", []):
            mt["mapPositions"] = [
                mp for mp in mt.get("mapPositions", []) if mp.get("roleOccupantId") != player_id
            ]

    def _pick_igl_roles(self, active_pairs: list[tuple[dict[str, Any], dict[str, Any]]]) -> tuple[int, int]:
        if not active_pairs:
            return 0, 0
        status_bonus = {0: 30.0, 1: 20.0, 2: 10.0, 3: 0.0}

        def score_primary(p: dict[str, Any], c: dict[str, Any]) -> float:
            desire = p.get("personality", {}).get("desireToIgl", 10)
            s = 100.0 if c.get("igl") == 0 else (30.0 if c.get("igl") == 1 else 0.0)
            if _wants_role(desire, 0):
                s += status_bonus.get(c.get("status", 3), 0.0)
            s += desire + p.get("skills", {}).get("leadership", 0.0) * 0.5
            return s

        primary_p, _ = max(active_pairs, key=lambda pc: score_primary(*pc))
        primary_id = primary_p["id"]

        others = [pc for pc in active_pairs if pc[0]["id"] != primary_id]
        if not others:
            return primary_id, 0

        def score_secondary(p: dict[str, Any], c: dict[str, Any]) -> float:
            desire = p.get("personality", {}).get("desireToIgl", 10)
            s = 100.0 if c.get("igl") == 1 else 15.0
            if _wants_role(desire, 1):
                s += status_bonus.get(c.get("status", 3), 0.0)
            s += desire * 0.5 + p.get("skills", {}).get("leadership", 0.0) * 0.25
            return s

        sec_p, _ = max(others, key=lambda pc: score_secondary(*pc))
        return primary_id, sec_p["id"]

    def _pick_sniper_roles(self, active_pairs: list[tuple[dict[str, Any], dict[str, Any]]]) -> tuple[int, int]:
        if not active_pairs:
            return 0, 0
        status_bonus = {0: 30.0, 1: 20.0, 2: 10.0, 3: 0.0}

        def score_primary(p: dict[str, Any], c: dict[str, Any]) -> float:
            desire = p.get("personality", {}).get("desireToAwp", 10)
            s = 100.0 if c.get("sniper") == 0 else (30.0 if c.get("sniper") == 1 else 0.0)
            if _wants_role(desire, 0):
                s += status_bonus.get(c.get("status", 3), 0.0)
            s += desire + p.get("skills", {}).get("snipers", 0.0) * 0.5
            return s

        primary_p, primary_c = max(active_pairs, key=lambda pc: score_primary(*pc))
        primary_id = primary_p["id"] if (primary_c.get("sniper") in (0, 1) or primary_p.get("skills", {}).get("snipers", 0) >= 12) else primary_p["id"]

        others = [pc for pc in active_pairs if pc[0]["id"] != primary_id]
        if not others:
            return primary_id, 0

        def score_secondary(p: dict[str, Any], c: dict[str, Any]) -> float:
            desire = p.get("personality", {}).get("desireToAwp", 10)
            s = 100.0 if c.get("sniper") == 1 else 15.0
            if _wants_role(desire, 1):
                s += status_bonus.get(c.get("status", 3), 0.0)
            s += desire * 0.5 + p.get("skills", {}).get("snipers", 0.0) * 0.25
            return s

        sec_p, sec_c = max(others, key=lambda pc: score_secondary(*pc))
        sec_id = sec_p["id"] if (sec_c.get("sniper") == 1 or sec_p.get("skills", {}).get("snipers", 0) >= 11) else 0
        return primary_id, sec_id

    def recalculate_ai_tactics(self, team_id: int) -> dict[str, Any]:
        """Rebuild generalTactics & mapTactics for team_id using CS Manager's AI tactics rules."""
        assert self.data is not None
        team = self.teams_by_id.get(team_id)
        if not team:
            raise ValueError(f"Team {team_id} not found.")

        active_contracts = [c for c in self.get_team_player_contracts(team_id) if not c.get("benched", False)]
        active_pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for c in active_contracts:
            p = self.players_by_id.get(c["playerId"])
            if p:
                active_pairs.append((p, c))

        # 1. General Tactics
        igl_id, sec_igl_id = self._pick_igl_roles(active_pairs)
        sniper_id, sec_sniper_id = self._pick_sniper_roles(active_pairs)

        head_coach = None
        for sc in self.get_team_staff_contracts(team_id):
            if sc.get("role") == 0:
                head_coach = self.staff_by_id.get(sc["staffId"])
                break

        igl_player = self.players_by_id.get(igl_id)
        coach_m = head_coach.get("preferredMentality", 1) if head_coach else None
        igl_m = igl_player.get("preferredMentality", 1) if igl_player else None
        if coach_m in (0, 1, 2) and igl_m in (0, 1, 2):
            if (coach_m == 2 and igl_m == 0) or (coach_m == 0 and igl_m == 2):
                mentality = 1
            else:
                mentality = igl_m
        elif igl_m in (0, 1, 2):
            mentality = igl_m
        elif coach_m in (0, 1, 2):
            mentality = coach_m
        else:
            mentality = 1

        if mentality == 2:
            lo, hi = 0.4, 1.0
        elif mentality == 1:
            lo, hi = 0.3, 0.7
        else:
            lo, hi = 0.0, 0.6

        gen_list = team.setdefault("generalTactics", [])
        active_gt = next((g for g in gen_list if g.get("active")), None)
        if active_gt is None:
            if gen_list:
                active_gt = gen_list[0]
                active_gt["active"] = True
            else:
                active_gt = {
                    "iglId": 0,
                    "secondIglId": 0,
                    "sniperId": 0,
                    "secondSniperId": 0,
                    "attackPace": round(random.uniform(lo, hi), 4),
                    "attackPack": round(random.uniform(lo, hi), 4),
                    "attackForceBuy": round(random.uniform(lo, hi), 4),
                    "defenseForceBuy": round(random.uniform(lo, hi), 4),
                    "defenseStack": round(random.uniform(lo, hi), 4),
                    "defensePush": round(random.uniform(lo, hi), 4),
                    "defenseUtilityUsageTiming": 0.0,
                    "active": True,
                    "knowledge": 20.0,
                }
                gen_list.append(active_gt)

        active_gt["iglId"] = igl_id
        active_gt["secondIglId"] = sec_igl_id
        active_gt["sniperId"] = sniper_id
        active_gt["secondSniperId"] = sec_sniper_id

        # Also sanitize any inactive generalTactic presets so no stale departed player IDs linger
        active_id_set = {p["id"] for p, _ in active_pairs}
        for gt in gen_list:
            if not gt.get("active"):
                for f in ("iglId", "secondIglId", "sniperId", "secondSniperId"):
                    if gt.get(f, 0) not in active_id_set:
                        gt[f] = 0

        # 2. Map Tactics (rebuild active mapTactic for every map in save)
        status_weight = {0: 10.0, 1: 6.0, 2: 3.5, 3: 1.0}
        maps_list = self.data.get("maps", {}).get("maps", [])
        existing_by_map = {mt["mapId"]: mt for mt in team.get("mapTactics", [])}
        new_map_tactics: list[dict[str, Any]] = []

        for m in maps_list:
            mid = m["id"]
            old_mt = existing_by_map.get(mid, {})
            map_positions: list[dict[str, Any]] = []

            if active_pairs:
                # Defense positions: 5..10, Attack positions: 0..4
                lane_diff = {
                    0: float(m.get("aLaneDefendDifficulty", 5.0)),
                    1: float(m.get("bLaneDefendDifficulty", 5.0)),
                    2: float(m.get("midLaneDefendDifficulty", 5.0)),
                }

                for side in (0, 1):  # 0 = defense (5..10), 1 = attack (0..4)
                    pos_range = list(range(5, 11)) if side == 0 else list(range(0, 5))
                    # Build candidate position pool up to len(active_pairs)
                    pool: list[tuple[int, float]] = []
                    cur_lanes = dict(lane_diff)
                    while len(pool) < len(active_pairs):
                        if side == 0:
                            best_pos = None
                            best_lane_score = -1e9
                            used_pos = {p_id for p_id, _ in pool}
                            for pt in pos_range:
                                sc = 0.0
                                for ln in (0, 1, 2):
                                    sc += _lane_protection_score(pt, ln) * abs(cur_lanes[ln]) / 10.0
                                if pt in used_pos:
                                    sc -= 0.3
                                if sc > best_lane_score:
                                    best_lane_score = sc
                                    best_pos = pt
                            assert best_pos is not None
                            pool.append((best_pos, max(best_lane_score, 0.5)))
                            for ln in (0, 1, 2):
                                cur_lanes[ln] -= _lane_protection_score(best_pos, ln)
                        else:
                            for pt in pos_range:
                                if len(pool) < len(active_pairs):
                                    pool.append((pt, 3.0))

                    remaining_players = list(active_pairs)
                    remaining_pool = list(pool)
                    max_pool_score = max((s for _, s in remaining_pool), default=1.0) or 1.0
                    used_pos_counts: dict[int, int] = {}

                    while remaining_players:
                        best_pair = None
                        best_pos_type = pos_range[0]
                        best_total = -1e9
                        for p, c in remaining_players:
                            attr_by_type = {a["positionType"]: a["roleComfort"] for a in p.get("mapPositionAttributes", [])}
                            st_w = status_weight.get(c.get("status", 3), 1.0)
                            for pt in pos_range:
                                attr_type = MAP_POS_TO_PLAYER_ATTR[pt]
                                comfort = _role_comfort_norm(attr_by_type.get(attr_type, 5))
                                matching_pool = sorted([s for ppt, s in remaining_pool if ppt == pt], reverse=True)
                                if matching_pool:
                                    team_want = matching_pool[0] / max_pool_score
                                else:
                                    team_want = -1.0 * (len(remaining_players) / max(len(active_pairs), 1))
                                total = comfort * 0.8 * st_w + team_want * 2.0 + random.uniform(0.0, 0.05)
                                if total > best_total:
                                    best_total = total
                                    best_pair = (p, c)
                                    best_pos_type = pt
                        assert best_pair is not None
                        chosen_p, _ = best_pair
                        ui_pos = used_pos_counts.get(best_pos_type, 0) + 1
                        used_pos_counts[best_pos_type] = ui_pos
                        map_positions.append(
                            {
                                "positionType": best_pos_type,
                                "roleOccupantId": chosen_p["id"],
                                "uiPosition": ui_pos,
                                "individualInstructionUtilityUsage": 0,
                                "individualInstructionUtilityPriority": 0,
                            }
                        )
                        remaining_players.remove(best_pair)
                        for idx, (ppt, _) in enumerate(remaining_pool):
                            if ppt == best_pos_type:
                                remaining_pool.pop(idx)
                                break

            new_map_tactics.append(
                {
                    "mapId": mid,
                    "equilibriumFromTraining": old_mt.get("equilibriumFromTraining", 0),
                    "knowledgeFromTraining": old_mt.get("knowledgeFromTraining", 15),
                    "knowledgeFromPlayers": old_mt.get("knowledgeFromPlayers", 25),
                    "mapPositions": map_positions,
                    "active": True,
                    "aFocus": old_mt.get("aFocus", False),
                    "midFocus": old_mt.get("midFocus", False),
                    "bFocus": old_mt.get("bFocus", False),
                }
            )

        # Keep any inactive tactics sanitized, replace active ones
        inactive_mts = [mt for mt in team.get("mapTactics", []) if not mt.get("active")]
        for mt in inactive_mts:
            mt["mapPositions"] = [
                mp for mp in mt.get("mapPositions", []) if mp.get("roleOccupantId") in active_id_set
            ]
        team["mapTactics"] = new_map_tactics + inactive_mts
        self.dirty = True
        return {
            "teamId": team_id,
            "activePlayerIds": sorted(active_id_set),
            "iglId": igl_id,
            "secondIglId": sec_igl_id,
            "sniperId": sniper_id,
            "secondSniperId": sec_sniper_id,
            "mapsUpdated": len(new_map_tactics),
        }

    # ------------------------------------------------------------------
    # Bench / Promote & Transfer Operations
    # ------------------------------------------------------------------

    def set_player_benched(self, player_id: int, benched: bool, auto_tactics: bool = True) -> dict[str, Any]:
        c = self.player_contract_by_pid.get(player_id)
        if not c:
            raise ValueError(f"Player {player_id} does not have an active contract.")
        c["benched"] = bool(benched)
        team_id = c["teamId"]
        team = self.teams_by_id.get(team_id)
        if team and benched:
            self.remove_player_from_tactics(team, player_id)
        tactics_res = None
        if team and auto_tactics:
            tactics_res = self.recalculate_ai_tactics(team_id)
        self.dirty = True
        return {"playerId": player_id, "teamId": team_id, "benched": bool(benched), "tactics": tactics_res}

    def transfer_player(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Execute a complete, game-consistent player transfer."""
        assert self.data is not None
        player_id = int(payload["playerId"])
        target_team_id = int(payload["targetTeamId"])  # 0 = release to Free Agency
        bench_player_id = int(payload.get("benchPlayerId") or 0)
        join_benched = bool(payload.get("joinBenched", False))
        auto_promote_old = bool(payload.get("autoPromoteOldTeam", True))
        buyout_price = int(payload.get("buyoutPrice") or 0)
        apply_finances = bool(payload.get("applyFinances", False))

        player = self.players_by_id.get(player_id)
        if not player:
            raise ValueError(f"Player {player_id} not found.")
        if target_team_id != 0 and target_team_id not in self.teams_by_id:
            raise ValueError(f"Target team {target_team_id} not found.")

        old_contract = self.player_contract_by_pid.get(player_id)
        old_team_id = old_contract["teamId"] if old_contract else 0
        profile = self.data.get("profile", {})
        user_team_id = profile.get("team", 0)

        # 1. Remove player from academy if needed
        if player.get("academyPlayer"):
            player["academyPlayer"] = False
            for t in self.data["teams"]["teams"]:
                if player_id in t.get("academyPlayers", []):
                    t["academyPlayers"] = [x for x in t["academyPlayers"] if x != player_id]

        # 2. Clean up old team if leaving a different team
        old_team_updated = None
        if old_team_id and old_team_id != target_team_id:
            old_team = self.teams_by_id.get(old_team_id)
            if old_team:
                old_team["playerDilemmas"] = [
                    d for d in old_team.get("playerDilemmas", []) if d.get("playerId") != player_id
                ]
                if "playersToBenchAfterMatch" in old_team:
                    old_team["playersToBenchAfterMatch"] = [
                        x for x in old_team["playersToBenchAfterMatch"] if x != player_id
                    ]
                if old_team_id == user_team_id:
                    for em in self.data.get("emails", {}).get("emails", []):
                        if em.get("player1Id") == player_id or em.get("player2Id") == player_id:
                            em["mustRespond"] = False
                self.remove_player_from_tactics(old_team, player_id)

        # Remove any existing contract(s) for this player
        self.data["playerContracts"]["playerContracts"] = [
            c for c in self.data["playerContracts"]["playerContracts"] if c.get("playerId") != player_id
        ]

        # If old team dropped below 5 active players and has a benched player, optionally promote
        if old_team_id and old_team_id != target_team_id:
            old_team = self.teams_by_id.get(old_team_id)
            if old_team:
                rem_contracts = self.get_team_player_contracts(old_team_id)
                rem_active = [c for c in rem_contracts if not c.get("benched")]
                rem_benched = [c for c in rem_contracts if c.get("benched")]
                if auto_promote_old and len(rem_active) < 5 and rem_benched:
                    rem_benched.sort(
                        key=lambda c: _player_avg_skill(self.players_by_id.get(c["playerId"], {})),
                        reverse=True,
                    )
                    rem_benched[0]["benched"] = False
                old_team_updated = self.recalculate_ai_tactics(old_team_id)

        # 3. Release to free agency if target_team_id == 0
        if target_team_id == 0:
            player["monthsBenchedOrWithoutContract"] = 0
            player["monthsSinceNewContract"] = 6
            self.rebuild_indices()
            self.dirty = True
            return {
                "status": "released",
                "playerId": player_id,
                "fromTeamId": old_team_id,
                "targetTeamId": 0,
                "oldTeamTactics": old_team_updated,
            }

        target_team = self.teams_by_id[target_team_id]

        # 4. If user selected an active player to bench on target team, bench them first
        if bench_player_id and bench_player_id != player_id:
            for c in self.data["playerContracts"]["playerContracts"]:
                if c.get("teamId") == target_team_id and c.get("playerId") == bench_player_id:
                    c["benched"] = True
                    self.remove_player_from_tactics(target_team, bench_player_id)
                    break

        # 5. Create new contract
        cur_dt = self.data.get("datetime", {"hour": 0, "day": 1, "month": 7, "year": 2026})
        default_end = {
            "hour": 0,
            "day": 1,
            "month": 7,
            "year": int(cur_dt.get("year", 2026)) + 2,
        }
        end_date = payload.get("endDate") or (old_contract.get("endDate") if old_contract else None) or default_end
        new_contract = {
            "salaryYear": int(payload.get("salaryYear") if payload.get("salaryYear") is not None else (old_contract.get("salaryYear", 250000) if old_contract else 250000)),
            "endDate": {
                "hour": int(end_date.get("hour", 0)),
                "day": int(end_date.get("day", 1)),
                "month": int(end_date.get("month", 7)),
                "year": int(end_date.get("year", int(cur_dt.get("year", 2026)) + 2)),
            },
            "teamId": target_team_id,
            "playerId": player_id,
            "status": int(payload.get("status", old_contract.get("status", 1) if old_contract else 1)),
            "sniper": int(payload.get("sniper", old_contract.get("sniper", 2) if old_contract else 2)),
            "igl": int(payload.get("igl", old_contract.get("igl", 2) if old_contract else 2)),
            "benched": bool(join_benched),
            "signingOnFee": int(payload.get("signingOnFee", 0)),
            "transferStatus": int(payload.get("transferStatus", 0)),
            "askingPrice": int(payload.get("askingPrice", 0)),
            "contractType": int(payload.get("contractType", 0)),
        }
        self.data["playerContracts"]["playerContracts"].append(new_contract)

        # 6. Update player state & clean interests/shortlist/mood (matches SignPlayer)
        player["monthsBenchedOrWithoutContract"] = 0
        player["monthsSinceNewContract"] = 0
        mood = player.setdefault("mood", {})
        mood["moodFromDialog"] = 0.0
        mood["moodFromTournamentReputation"] = 0.0
        mood["moodsFromMatches"] = []

        for t in self.data["teams"]["teams"]:
            if "personInterests" in t:
                t["personInterests"] = [
                    pi for pi in t["personInterests"] if pi.get("playerId") != player_id
                ]
        if "playerShortlist" in profile:
            profile["playerShortlist"] = [x for x in profile["playerShortlist"] if x != player_id]

        # Adjust team cohesion training & clear cached mainLanguage
        cohesion = target_team.setdefault("teamCohesion", {})
        if "cohesionFromTraining" in cohesion:
            cohesion["cohesionFromTraining"] = min(float(cohesion["cohesionFromTraining"]), 0.3)

        # 7. Log TransferHistory
        if old_team_id != target_team_id:
            th_list = self.data.setdefault("transferHistories", {}).setdefault("transferHistories", [])
            th_list.append(
                {
                    "personId": player_id,
                    "personType": 0,
                    "transferType": 0,
                    "datetime": copy.deepcopy(cur_dt),
                    "purchasePrice": buyout_price,
                    "fromTeamId": old_team_id,
                    "otherTeamId": target_team_id,
                }
            )

        # 8. Optional buyout finances
        if apply_finances and buyout_price > 0 and old_team_id != target_team_id:
            tf_new = target_team.setdefault("teamFinances", {})
            tf_new["currentBalance"] = int(tf_new.get("currentBalance", 0)) - buyout_price
            tf_new["buyoutAndSignOnExpenses"] = int(tf_new.get("buyoutAndSignOnExpenses", 0)) + buyout_price
            if old_team_id and old_team_id in self.teams_by_id:
                tf_old = self.teams_by_id[old_team_id].setdefault("teamFinances", {})
                tf_old["currentBalance"] = int(tf_old.get("currentBalance", 0)) + buyout_price
                tf_old["buyoutIncome"] = int(tf_old.get("buyoutIncome", 0)) + buyout_price

        self.rebuild_indices()
        new_team_tactics = self.recalculate_ai_tactics(target_team_id)
        self.dirty = True

        return {
            "status": "transferred",
            "playerId": player_id,
            "fromTeamId": old_team_id,
            "targetTeamId": target_team_id,
            "benchedPlayerId": bench_player_id or None,
            "newTeamTactics": new_team_tactics,
            "oldTeamTactics": old_team_updated,
        }

    def transfer_staff(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Transfer a staff member to a target team (or release to Free Agency)."""
        assert self.data is not None
        staff_id = int(payload["staffId"])
        target_team_id = int(payload["targetTeamId"])  # 0 = release
        role = int(payload.get("role", 0))
        replace_existing = bool(payload.get("replaceExisting", True))
        buyout_price = int(payload.get("buyoutPrice") or 0)
        apply_finances = bool(payload.get("applyFinances", False))

        staff = self.staff_by_id.get(staff_id)
        if not staff:
            raise ValueError(f"Staff {staff_id} not found.")
        if target_team_id != 0 and target_team_id not in self.teams_by_id:
            raise ValueError(f"Target team {target_team_id} not found.")

        old_contract = self.staff_contract_by_sid.get(staff_id)
        old_team_id = old_contract["teamId"] if old_contract else 0

        # Remove old contract for this staffer
        self.data["staffContracts"]["staffContracts"] = [
            c for c in self.data["staffContracts"]["staffContracts"] if c.get("staffId") != staff_id
        ]

        if target_team_id == 0:
            staff["monthsSinceNewContract"] = 6
            self.rebuild_indices()
            self.dirty = True
            return {"status": "released", "staffId": staff_id, "fromTeamId": old_team_id}

        # Optionally release existing staffer occupying this role on target team
        displaced_staff_id = None
        if replace_existing:
            kept = []
            for c in self.data["staffContracts"]["staffContracts"]:
                if c.get("teamId") == target_team_id and c.get("role") == role:
                    displaced_staff_id = c["staffId"]
                    if displaced_staff_id in self.staff_by_id:
                        self.staff_by_id[displaced_staff_id]["monthsSinceNewContract"] = 6
                else:
                    kept.append(c)
            self.data["staffContracts"]["staffContracts"] = kept

        cur_dt = self.data.get("datetime", {"hour": 0, "day": 1, "month": 7, "year": 2026})
        default_end = {"hour": 0, "day": 1, "month": 7, "year": int(cur_dt.get("year", 2026)) + 2}
        end_date = payload.get("endDate") or (old_contract.get("endDate") if old_contract else None) or default_end

        new_contract = {
            "salaryYear": int(payload.get("salaryYear") if payload.get("salaryYear") is not None else (old_contract.get("salaryYear", 180000) if old_contract else 180000)),
            "endDate": {
                "hour": int(end_date.get("hour", 0)),
                "day": int(end_date.get("day", 1)),
                "month": int(end_date.get("month", 7)),
                "year": int(end_date.get("year", int(cur_dt.get("year", 2026)) + 2)),
            },
            "teamId": target_team_id,
            "staffId": staff_id,
            "role": role,
            "rejectAllStaffOffers": bool(payload.get("rejectAllStaffOffers", False)),
        }
        self.data["staffContracts"]["staffContracts"].append(new_contract)

        staff["monthsBenchedOrWithoutContract"] = 0
        staff["monthsSinceNewContract"] = 0

        for t in self.data["teams"]["teams"]:
            if "personInterests" in t:
                t["personInterests"] = [
                    pi for pi in t["personInterests"] if pi.get("staffId") != staff_id
                ]

        if old_team_id != target_team_id:
            th_list = self.data.setdefault("transferHistories", {}).setdefault("transferHistories", [])
            th_list.append(
                {
                    "personId": staff_id,
                    "personType": 1,
                    "transferType": 0,
                    "datetime": copy.deepcopy(cur_dt),
                    "purchasePrice": buyout_price,
                    "fromTeamId": old_team_id,
                    "otherTeamId": target_team_id,
                }
            )

        if apply_finances and buyout_price > 0 and old_team_id != target_team_id:
            target_team = self.teams_by_id[target_team_id]
            tf_new = target_team.setdefault("teamFinances", {})
            tf_new["currentBalance"] = int(tf_new.get("currentBalance", 0)) - buyout_price
            tf_new["buyoutAndSignOnExpenses"] = int(tf_new.get("buyoutAndSignOnExpenses", 0)) + buyout_price
            if old_team_id and old_team_id in self.teams_by_id:
                tf_old = self.teams_by_id[old_team_id].setdefault("teamFinances", {})
                tf_old["currentBalance"] = int(tf_old.get("currentBalance", 0)) + buyout_price
                tf_old["buyoutIncome"] = int(tf_old.get("buyoutIncome", 0)) + buyout_price

        self.rebuild_indices()
        self.dirty = True
        return {
            "status": "transferred",
            "staffId": staff_id,
            "fromTeamId": old_team_id,
            "targetTeamId": target_team_id,
            "role": role,
            "displacedStaffId": displaced_staff_id,
        }

    # ------------------------------------------------------------------
    # Save Validator & Auto-Repair
    # ------------------------------------------------------------------

    def validate_and_fix(self, fix: bool = False) -> dict[str, Any]:
        if self.data is None:
            return {"loaded": False, "issueCount": 0, "issues": [], "fixedTeamCount": 0, "fixedTeamIds": []}
        issues: list[dict[str, Any]] = []
        fixed_teams: set[int] = set()

        # Check duplicate player contracts
        seen_pids: set[int] = set()
        dup_pids: set[int] = set()
        for c in self.data["playerContracts"]["playerContracts"]:
            pid = c["playerId"]
            if pid in seen_pids:
                dup_pids.add(pid)
            seen_pids.add(pid)
        if dup_pids:
            issues.append({"type": "duplicate_player_contracts", "playerIds": sorted(dup_pids)})
            if fix:
                kept = {}
                for c in self.data["playerContracts"]["playerContracts"]:
                    kept[c["playerId"]] = c
                self.data["playerContracts"]["playerContracts"] = list(kept.values())
                self.rebuild_indices()

        # Check every team's tactics vs active roster
        for team in self.data["teams"]["teams"]:
            tid = team["id"]
            contracts = self.get_team_player_contracts(tid)
            active_ids = {c["playerId"] for c in contracts if not c.get("benched", False)}
            benched_ids = {c["playerId"] for c in contracts if c.get("benched", False)}

            team_problems: list[str] = []
            for gt in team.get("generalTactics", []):
                for f in ("iglId", "secondIglId", "sniperId", "secondSniperId"):
                    val = gt.get(f, 0)
                    if val != 0 and val not in active_ids:
                        team_problems.append(f"generalTactics.{f}={val} not active")

            for mt in team.get("mapTactics", []):
                if mt.get("active"):
                    occ = {mp["roleOccupantId"] for mp in mt.get("mapPositions", []) if mp.get("roleOccupantId", 0) != 0}
                    stale = occ - active_ids
                    missing = active_ids - occ
                    if stale:
                        team_problems.append(f"mapId={mt['mapId']} has non-active occupants {sorted(stale)}")
                    if missing and active_ids:
                        team_problems.append(f"mapId={mt['mapId']} missing active players {sorted(missing)}")

            if len(active_ids) > 5:
                team_problems.append(f"active count is {len(active_ids)} (> 5)")
            elif len(active_ids) < 5 and len(benched_ids) > 0:
                team_problems.append(f"active count is {len(active_ids)} with {len(benched_ids)} benched player(s) available")

            if team_problems:
                issues.append({"type": "team_tactics_mismatch", "teamId": tid, "teamName": team["name"], "details": team_problems})
                if fix:
                    if len(active_ids) > 5:
                        starters = [c for c in contracts if not c.get("benched", False)]
                        starters.sort(key=lambda c: _player_avg_skill(self.players_by_id.get(c["playerId"], {})))
                        for c in starters[: len(starters) - 5]:
                            c["benched"] = True
                    elif len(active_ids) < 5 and len(benched_ids) > 0:
                        benched = [c for c in contracts if c.get("benched", False)]
                        benched.sort(
                            key=lambda c: _player_avg_skill(self.players_by_id.get(c["playerId"], {})),
                            reverse=True,
                        )
                        for c in benched[: 5 - len(active_ids)]:
                            c["benched"] = False
                    if active_ids or len(benched_ids) > 0:
                        self.recalculate_ai_tactics(tid)
                        fixed_teams.add(tid)

        return {
            "issueCount": len(issues),
            "issues": issues,
            "fixed": fix,
            "fixedTeamCount": len(fixed_teams),
            "fixedTeamIds": sorted(fixed_teams),
        }

    # ------------------------------------------------------------------
    # Query & Update Endpoints
    # ------------------------------------------------------------------

    def list_players(self, q: str = "", team_id: str = "", nation: str = "", free_only: bool = False, offset: int = 0, limit: int = 100) -> dict[str, Any]:
        if self.data is None:
            return {"total": 0, "offset": offset, "limit": limit, "items": []}
        ql = q.strip().lower()
        rows = []
        for p in self.data["players"]["players"]:
            pid = p["id"]
            c = self.player_contract_by_pid.get(pid)
            tid = c["teamId"] if c else 0
            if free_only and c is not None:
                continue
            if team_id != "" and str(tid) != str(team_id):
                continue
            if nation != "" and str(p.get("nation")) != str(nation):
                continue
            if ql:
                tname = self.teams_by_id[tid]["name"].lower() if tid in self.teams_by_id else "free agent"
                if ql not in p.get("name", "").lower() and ql not in tname and ql != str(pid):
                    continue
            tname = self.teams_by_id[tid]["name"] if tid in self.teams_by_id else "Free Agent"
            rows.append(
                {
                    "id": pid,
                    "name": p.get("name", ""),
                    "age": p.get("age", 0),
                    "nation": p.get("nation", 0),
                    "nationName": NATIONS.get(p.get("nation", 0), f"Nation {p.get('nation')}"),
                    "reputation": p.get("reputation", 1),
                    "preferredMentality": p.get("preferredMentality", 1),
                    "teamId": tid,
                    "teamName": tname,
                    "benched": bool(c.get("benched")) if c else False,
                    "status": c.get("status") if c else None,
                    "igl": c.get("igl", 2) if c else 2,
                    "sniper": c.get("sniper", 2) if c else 2,
                    "salaryYear": c.get("salaryYear", 0) if c else 0,
                    "avgSkill": _player_avg_skill(p),
                }
            )
        rows.sort(key=lambda r: (-r["avgSkill"], r["name"].lower()))
        total = len(rows)
        return {"total": total, "items": rows[offset : offset + limit]}

    def _relationship_row(self, rel: dict[str, Any], focus_player_id: int | None = None) -> dict[str, Any]:
        p1 = int(rel.get("player1Id", 0) or 0)
        p2 = int(rel.get("player2Id", 0) or 0)
        p1_obj = self.players_by_id.get(p1)
        p2_obj = self.players_by_id.get(p2)
        c1 = self.player_contract_by_pid.get(p1)
        c2 = self.player_contract_by_pid.get(p2)
        t1 = self.teams_by_id.get(c1["teamId"])["name"] if c1 and c1["teamId"] in self.teams_by_id else ("Free Agent" if p1_obj else "Missing")
        t2 = self.teams_by_id.get(c2["teamId"])["name"] if c2 and c2["teamId"] in self.teams_by_id else ("Free Agent" if p2_obj else "Missing")
        rtype = int(rel.get("type", 1) if rel.get("type") is not None else 1)
        p1_res = bool(rel.get("player1Resolved", False))
        p2_res = bool(rel.get("player2Resolved", False))

        other_id = p2 if (focus_player_id is None or p1 == focus_player_id) else p1
        other_obj = p2_obj if other_id == p2 else p1_obj
        other_team = t2 if other_id == p2 else t1
        self_is_p1 = focus_player_id is None or p1 == focus_player_id
        return {
            "player1Id": p1,
            "player2Id": p2,
            "player1Name": p1_obj.get("name", f"Player #{p1}") if p1_obj else f"Missing Player #{p1}",
            "player2Name": p2_obj.get("name", f"Player #{p2}") if p2_obj else f"Missing Player #{p2}",
            "player1TeamName": t1,
            "player2TeamName": t2,
            "player1TeamId": c1["teamId"] if c1 else 0,
            "player2TeamId": c2["teamId"] if c2 else 0,
            "otherPlayerId": other_id,
            "otherPlayerName": other_obj.get("name", f"Player #{other_id}") if other_obj else f"Missing Player #{other_id}",
            "otherExists": other_obj is not None,
            "otherTeamName": other_team,
            "otherAvgSkill": round(_player_avg_skill(other_obj), 2) if other_obj else 0.0,
            "type": rtype,
            "typeLabel": RELATIONSHIP_TYPES.get(rtype, f"Type {rtype}"),
            "duration": int(rel.get("duration", 0) or 0),
            "player1Resolved": p1_res,
            "player2Resolved": p2_res,
            "selfIsPlayer1": self_is_p1,
            "selfResolved": p1_res if self_is_p1 else p2_res,
            "otherResolved": p2_res if self_is_p1 else p1_res,
        }

    def _build_player_relationships_list(self, player_id: int) -> list[dict[str, Any]]:
        assert self.data is not None
        rels = self.data.get("playerRelationships", {}).get("playerRelationships", [])
        rows = [
            self._relationship_row(r, focus_player_id=player_id)
            for r in rels
            if int(r.get("player1Id", 0) or 0) == player_id or int(r.get("player2Id", 0) or 0) == player_id
        ]
        rows.sort(key=lambda item: (item["type"], item["otherPlayerName"].lower()))
        return rows

    def get_player(self, player_id: int) -> dict[str, Any]:
        p = self.players_by_id.get(player_id)
        if not p:
            raise ValueError(f"Player {player_id} not found.")
        c = self.player_contract_by_pid.get(player_id)
        tid = c["teamId"] if c else 0
        return {
            "player": copy.deepcopy(p),
            "contract": copy.deepcopy(c) if c else None,
            "teamId": tid,
            "teamName": self.teams_by_id[tid]["name"] if tid in self.teams_by_id else "Free Agent",
            "relationships": self._build_player_relationships_list(player_id),
        }

    def update_player(self, player_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        assert self.data is not None
        p = self.players_by_id.get(player_id)
        if not p:
            raise ValueError(f"Player {player_id} not found.")
        pdata = payload.get("player", {})
        for k in (
            "name", "age", "nation", "reputation", "preferredMentality",
            "setForRetirement", "monthsBenchedOrWithoutContract", "monthsSinceNewContract",
            "longevity", "temporaryStandIn", "dontReplaceOnRetire", "academyPlayer",
        ):
            if k in pdata:
                p[k] = pdata[k]

        if "skills" in pdata:
            p["skills"].update({k: float(v) for k, v in pdata["skills"].items()})
        if "potential" in pdata:
            p["potential"] = pdata["potential"]
        if "languagesSpoken" in pdata:
            p["languagesSpoken"] = pdata["languagesSpoken"]
        if "mapPositionAttributes" in pdata:
            p["mapPositionAttributes"] = pdata["mapPositionAttributes"]
        if "mapOpinions" in pdata:
            p["mapOpinions"] = pdata["mapOpinions"]
        if "personality" in pdata:
            p["personality"].update({k: int(v) for k, v in pdata["personality"].items()})

        if "contract" in payload and payload["contract"] is not None:
            cdata = payload["contract"]
            existing = self.player_contract_by_pid.get(player_id)
            if existing:
                for k in (
                    "salaryYear", "endDate", "status", "sniper", "igl", "benched",
                    "signingOnFee", "transferStatus", "askingPrice", "contractType",
                ):
                    if k in cdata:
                        existing[k] = cdata[k]
                if "teamId" in cdata and int(cdata["teamId"]) != existing["teamId"]:
                    # Route teamId change through transfer logic so tactics stay valid!
                    self.transfer_player(
                        {
                            "playerId": player_id,
                            "targetTeamId": int(cdata["teamId"]),
                            "salaryYear": existing["salaryYear"],
                            "endDate": existing["endDate"],
                            "status": existing["status"],
                            "sniper": existing["sniper"],
                            "igl": existing["igl"],
                            "joinBenched": existing["benched"],
                            "signingOnFee": existing["signingOnFee"],
                            "transferStatus": existing["transferStatus"],
                            "askingPrice": existing["askingPrice"],
                            "contractType": existing["contractType"],
                        }
                    )
            elif int(cdata.get("teamId", 0)) > 0:
                self.transfer_player(
                    {
                        "playerId": player_id,
                        "targetTeamId": int(cdata["teamId"]),
                        "salaryYear": cdata.get("salaryYear", 250000),
                        "endDate": cdata.get("endDate"),
                        "status": cdata.get("status", 1),
                        "sniper": cdata.get("sniper", 2),
                        "igl": cdata.get("igl", 2),
                        "joinBenched": cdata.get("benched", False),
                        "signingOnFee": cdata.get("signingOnFee", 0),
                        "transferStatus": cdata.get("transferStatus", 0),
                        "askingPrice": cdata.get("askingPrice", 0),
                        "contractType": cdata.get("contractType", 0),
                    }
                )
        self.dirty = True
        return self.get_player(player_id)

    def list_player_relationships(
        self, q: str = "", rel_type: str = "", team_id: str = "", unresolved_only: bool = False
    ) -> dict[str, Any]:
        """List and filter all player-to-player relationships in the loaded save."""
        if self.data is None:
            return {"total": 0, "items": [], "counts": {}}
        ql = q.strip().lower()
        rels = self.data.get("playerRelationships", {}).get("playerRelationships", [])
        rows = []
        for rel in rels:
            row = self._relationship_row(rel)
            if rel_type != "" and str(row["type"]) != str(rel_type):
                continue
            if team_id != "" and str(row["player1TeamId"]) != str(team_id) and str(row["player2TeamId"]) != str(team_id):
                continue
            if unresolved_only and (row["player1Resolved"] and row["player2Resolved"]):
                continue
            if ql:
                hay = f"{row['player1Name']} {row['player2Name']} {row['player1TeamName']} {row['player2TeamName']} {row['player1Id']} {row['player2Id']}".lower()
                if ql not in hay:
                    continue
            rows.append(row)
        rows.sort(key=lambda item: (item["type"], item["player1Name"].lower(), item["player2Name"].lower()))
        return {"total": len(rows), "items": rows}

    def save_player_relationship(
        self,
        player1_id: int,
        player2_id: int,
        rel_type: int = 1,
        duration: int = 0,
        player1_resolved: bool | None = None,
        player2_resolved: bool | None = None,
    ) -> dict[str, Any]:
        """Create or update a bidirectional relationship between two players in the save."""
        assert self.data is not None
        if player1_id == player2_id:
            raise ValueError("A player cannot have a relationship with themselves.")
        if player1_id not in self.players_by_id or player2_id not in self.players_by_id:
            raise ValueError(f"Both players must exist in the save (#{player1_id}, #{player2_id}).")

        rtype = max(0, min(4, int(rel_type)))
        dur = max(0, int(duration))
        rels_wrap = self.data.setdefault("playerRelationships", {"playerRelationships": []})
        if not isinstance(rels_wrap, dict):
            rels_wrap = {"playerRelationships": []}
            self.data["playerRelationships"] = rels_wrap
        rels = rels_wrap.setdefault("playerRelationships", [])

        existing = next(
            (
                r for r in rels
                if {int(r.get("player1Id", 0) or 0), int(r.get("player2Id", 0) or 0)} == {player1_id, player2_id}
            ),
            None,
        )
        if existing is not None:
            existing["type"] = rtype
            existing["duration"] = dur
            stored_p1 = int(existing.get("player1Id", player1_id) or player1_id)
            if stored_p1 == player1_id:
                if player1_resolved is not None:
                    existing["player1Resolved"] = bool(player1_resolved)
                if player2_resolved is not None:
                    existing["player2Resolved"] = bool(player2_resolved)
            else:
                # Caller provided flags aligned to (player1_id, player2_id); align back onto stored pair order.
                if player2_resolved is not None:
                    existing["player1Resolved"] = bool(player2_resolved)
                if player1_resolved is not None:
                    existing["player2Resolved"] = bool(player1_resolved)
        else:
            rels.append({
                "player1Id": int(player1_id),
                "player2Id": int(player2_id),
                "type": rtype,
                "duration": dur,
                "player1Resolved": bool(player1_resolved) if player1_resolved is not None else False,
                "player2Resolved": bool(player2_resolved) if player2_resolved is not None else False,
            })

        self.dirty = True
        return self.get_player(player1_id)

    def delete_player_relationship(self, player1_id: int, player2_id: int) -> dict[str, Any]:
        """Delete the relationship between two players from the save."""
        assert self.data is not None
        rels_wrap = self.data.get("playerRelationships") or {}
        rels = rels_wrap.get("playerRelationships", [])
        before = len(rels)
        kept = [
            r for r in rels
            if {int(r.get("player1Id", 0) or 0), int(r.get("player2Id", 0) or 0)} != {player1_id, player2_id}
        ]
        if len(kept) == before:
            raise ValueError("Relationship not found.")
        rels_wrap["playerRelationships"] = kept
        self.dirty = True
        return self.get_player(player1_id)

    def list_staff(self, q: str = "", team_id: str = "", role: str = "", free_only: bool = False, offset: int = 0, limit: int = 100) -> dict[str, Any]:
        if self.data is None:
            return {"total": 0, "offset": offset, "limit": limit, "items": []}
        ql = q.strip().lower()
        rows = []
        for s in self.data["staffers"]["staffers"]:
            sid = s["id"]
            c = self.staff_contract_by_sid.get(sid)
            tid = c["teamId"] if c else 0
            srole = c.get("role") if c else None
            if free_only and c is not None:
                continue
            if team_id != "" and str(tid) != str(team_id):
                continue
            if role != "" and str(srole) != str(role):
                continue
            if ql:
                tname = self.teams_by_id[tid]["name"].lower() if tid in self.teams_by_id else "free agent"
                if ql not in s.get("name", "").lower() and ql not in tname and ql != str(sid):
                    continue
            tname = self.teams_by_id[tid]["name"] if tid in self.teams_by_id else "Free Agent"
            rows.append(
                {
                    "id": sid,
                    "name": s.get("name", ""),
                    "age": s.get("age", 0),
                    "nation": s.get("nation", 0),
                    "nationName": NATIONS.get(s.get("nation", 0), f"Nation {s.get('nation')}"),
                    "reputation": s.get("reputation", 1),
                    "preferredMentality": s.get("preferredMentality", 1),
                    "teamId": tid,
                    "teamName": tname,
                    "role": srole,
                    "roleName": STAFF_ROLES.get(srole, "Free Agent") if srole is not None else "Free Agent",
                    "salaryYear": c.get("salaryYear", 0) if c else 0,
                    "avgSkill": _staff_avg_skill(s),
                }
            )
        rows.sort(key=lambda r: (-r["avgSkill"], r["name"].lower()))
        total = len(rows)
        return {"total": total, "items": rows[offset : offset + limit]}

    def get_staff(self, staff_id: int) -> dict[str, Any]:
        s = self.staff_by_id.get(staff_id)
        if not s:
            raise ValueError(f"Staff {staff_id} not found.")
        c = self.staff_contract_by_sid.get(staff_id)
        tid = c["teamId"] if c else 0
        return {
            "staff": copy.deepcopy(s),
            "contract": copy.deepcopy(c) if c else None,
            "teamId": tid,
            "teamName": self.teams_by_id[tid]["name"] if tid in self.teams_by_id else "Free Agent",
        }

    def update_staff(self, staff_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        assert self.data is not None
        s = self.staff_by_id.get(staff_id)
        if not s:
            raise ValueError(f"Staff {staff_id} not found.")
        sdata = payload.get("staff", {})
        for k in (
            "name", "age", "nation", "reputation", "preferredMentality",
            "setForRetirement", "retirementConsiderationAge",
            "monthsBenchedOrWithoutContract", "monthsSinceNewContract",
        ):
            if k in sdata:
                s[k] = sdata[k]
        if "skills" in sdata:
            s["skills"].update({k: float(v) for k, v in sdata["skills"].items()})
        if "potential" in sdata:
            s["potential"] = sdata["potential"]
        if "languagesSpoken" in sdata:
            s["languagesSpoken"] = sdata["languagesSpoken"]
        if "careerInterests" in sdata:
            s["careerInterests"] = sdata["careerInterests"]

        if "contract" in payload and payload["contract"] is not None:
            cdata = payload["contract"]
            existing = self.staff_contract_by_sid.get(staff_id)
            if existing:
                for k in ("salaryYear", "endDate", "role", "rejectAllStaffOffers"):
                    if k in cdata:
                        existing[k] = cdata[k]
                if "teamId" in cdata and int(cdata["teamId"]) != existing["teamId"]:
                    self.transfer_staff(
                        {
                            "staffId": staff_id,
                            "targetTeamId": int(cdata["teamId"]),
                            "role": existing["role"],
                            "salaryYear": existing["salaryYear"],
                            "endDate": existing["endDate"],
                            "rejectAllStaffOffers": existing["rejectAllStaffOffers"],
                        }
                    )
            elif int(cdata.get("teamId", 0)) > 0:
                self.transfer_staff(
                    {
                        "staffId": staff_id,
                        "targetTeamId": int(cdata["teamId"]),
                        "role": cdata.get("role", 0),
                        "salaryYear": cdata.get("salaryYear", 180000),
                        "endDate": cdata.get("endDate"),
                        "rejectAllStaffOffers": cdata.get("rejectAllStaffOffers", False),
                    }
                )
        self.dirty = True
        return self.get_staff(staff_id)

    def list_teams(self, q: str = "") -> list[dict[str, Any]]:
        if self.data is None:
            return []
        ql = q.strip().lower()
        user_tid = self.data.get("profile", {}).get("team", 0)
        rows = []
        for t in self.data["teams"]["teams"]:
            tid = t["id"]
            if ql and ql not in t.get("name", "").lower() and ql != str(tid):
                continue
            pcs = self.get_team_player_contracts(tid)
            scs = self.get_team_staff_contracts(tid)
            active_cnt = sum(1 for c in pcs if not c.get("benched"))
            rows.append(
                {
                    "id": tid,
                    "name": t.get("name", ""),
                    "nation": t.get("nation", 0),
                    "nationName": NATIONS.get(t.get("nation", 0), ""),
                    "reputation": t.get("reputation", 1),
                    "professionalStatus": t.get("professionalStatus", 0),
                    "financialStrength": t.get("financialStrength", 1),
                    "balance": t.get("teamFinances", {}).get("currentBalance", 0),
                    "activeCount": active_cnt,
                    "benchedCount": len(pcs) - active_cnt,
                    "staffCount": len(scs),
                    "isUserTeam": tid == user_tid,
                }
            )
        rows.sort(key=lambda r: (not r["isUserTeam"], -r["reputation"], r["name"].lower()))
        return rows

    def get_team(self, team_id: int) -> dict[str, Any]:
        t = self.teams_by_id.get(team_id)
        if not t:
            raise ValueError(f"Team {team_id} not found.")
        pcs = self.get_team_player_contracts(team_id)
        roster = []
        for c in pcs:
            p = self.players_by_id.get(c["playerId"])
            if p:
                roster.append(
                    {
                        "playerId": p["id"],
                        "name": p["name"],
                        "age": p["age"],
                        "nationName": NATIONS.get(p.get("nation", 0), ""),
                        "avgSkill": _player_avg_skill(p),
                        "benched": bool(c.get("benched")),
                        "status": c.get("status", 1),
                        "igl": c.get("igl", 2),
                        "sniper": c.get("sniper", 2),
                        "salaryYear": c.get("salaryYear", 0),
                        "endDate": c.get("endDate", {}),
                    }
                )
        roster.sort(key=lambda r: (r["benched"], -r["avgSkill"]))

        scs = self.get_team_staff_contracts(team_id)
        staff_roster = []
        for c in scs:
            s = self.staff_by_id.get(c["staffId"])
            if s:
                staff_roster.append(
                    {
                        "staffId": s["id"],
                        "name": s["name"],
                        "age": s["age"],
                        "role": c.get("role", 0),
                        "roleName": STAFF_ROLES.get(c.get("role", 0), "Staff"),
                        "avgSkill": _staff_avg_skill(s),
                        "salaryYear": c.get("salaryYear", 0),
                        "endDate": c.get("endDate", {}),
                    }
                )
        staff_roster.sort(key=lambda r: r["role"])

        team_copy = copy.deepcopy(t)
        # Keep payload snappy by trimming massive historical arrays not edited in org stats
        for heavy in ("rankingPoints", "rankingHistory", "mapStats", "playbooks"):
            team_copy.pop(heavy, None)

        return {
            "team": team_copy,
            "roster": roster,
            "staff": staff_roster,
            "isUserTeam": team_id == self.data.get("profile", {}).get("team", 0),
        }

    def update_team(self, team_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        t = self.teams_by_id.get(team_id)
        if not t:
            raise ValueError(f"Team {team_id} not found.")
        tdata = payload.get("team", {})
        for k in (
            "name", "nation", "reputation", "reputationProgress", "professionalStatus",
            "financialStrength", "coffeeMachine", "cable", "ventilation", "recreation",
            "branding", "academy", "academyFocus",
        ):
            if k in tdata:
                t[k] = tdata[k]
        if "owner" in tdata:
            t.setdefault("owner", {}).update(tdata["owner"])
        if "teamFinances" in tdata:
            t.setdefault("teamFinances", {}).update(tdata["teamFinances"])
        if "teamCohesion" in tdata:
            t.setdefault("teamCohesion", {}).update(tdata["teamCohesion"])
        if "jobSecurity" in tdata:
            t.setdefault("jobSecurity", {}).update(tdata["jobSecurity"])
        self.dirty = True
        return self.get_team(team_id)

    def list_transfers(self, limit: int = 80) -> list[dict[str, Any]]:
        if self.data is None:
            return []
        items = self.data.get("transferHistories", {}).get("transferHistories", [])
        out = []
        for th in reversed(items[-limit:]):
            ptype = th.get("personType", 0)
            pid = th.get("personId", 0)
            if ptype == 0:
                name = self.players_by_id.get(pid, {}).get("name", f"Player #{pid}")
            else:
                name = self.staff_by_id.get(pid, {}).get("name", f"Staff #{pid}")
            from_id = th.get("fromTeamId", 0)
            to_id = th.get("otherTeamId", 0)
            out.append(
                {
                    "personId": pid,
                    "personName": name,
                    "personType": "Player" if ptype == 0 else "Staff",
                    "fromTeamName": self.teams_by_id.get(from_id, {}).get("name", "Free Agent") if from_id else "Free Agent",
                    "toTeamName": self.teams_by_id.get(to_id, {}).get("name", "Free Agent") if to_id else "Free Agent",
                    "purchasePrice": th.get("purchasePrice", 0),
                    "datetime": th.get("datetime", {}),
                }
            )
        return out

    def _default_portrait(self, age: int = 20) -> dict[str, int]:
        assert self.data is not None
        pool = self.data["players"]["players"] + self.data["staffers"]["staffers"]
        if pool:
            p = copy.deepcopy(random.choice(pool).get("portrait", {}))
            if p:
                if age < 28:
                    p["wrinkes"] = 0
                return p
        return {
            "face": random.randint(1, 3),
            "nose": random.randint(1, 11),
            "mouth": random.randint(1, 13),
            "mouthColor": random.randint(1, 6),
            "eyes": random.randint(1, 12),
            "eyeballsColor": random.randint(1, 7),
            "eyebrows": random.randint(0, 11),
            "eyebrowsColor": random.randint(1, 9),
            "hair": random.randint(1, 44),
            "hairColor": random.randint(1, 9),
            "beard": 0 if age < 20 else random.randint(0, 15),
            "beardColor": random.randint(1, 9),
            "accessory": 0,
            "accessoryColor": 1,
            "wrinkes": 0 if age < 28 else random.randint(0, 3),
            "skinColor": random.randint(1, 5),
            "neck": random.randint(1, 2),
        }

    def create_player(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create a brand-new player and optionally sign them to a team."""
        assert self.data is not None
        pdata = payload.get("player", payload)
        name = str(pdata.get("name", "")).strip()
        if not name:
            raise ValueError("Player name / alias cannot be empty.")

        age = int(_clamp(int(pdata.get("age", 19)), 15, 55))
        nation = int(pdata.get("nation", 1))
        reputation = int(_clamp(int(pdata.get("reputation", 10)), 1, 20))
        mentality = int(_clamp(int(pdata.get("preferredMentality", 1)), 0, 2))
        longevity = int(pdata.get("longevity", 30))
        base_skill = float(_clamp(float(pdata.get("baseSkill", 12.0)), 1.0, 20.0))
        base_pot = int(_clamp(int(pdata.get("basePotential", max(int(round(base_skill)) + 3, 15))), 1, 20))

        raw_skills = pdata.get("skills", {})
        skills: dict[str, float] = {}
        for sk in PLAYER_SKILLS:
            key = sk["key"]
            skills[key] = float(_clamp(float(raw_skills.get(key, base_skill)), 1.0, 20.0))

        raw_pot = pdata.get("potential", {})
        if isinstance(raw_pot, dict) and "m_Keys" in raw_pot and "m_Values" in raw_pot:
            pot_map = {int(k): int(_clamp(int(v), 1, 20)) for k, v in zip(raw_pot["m_Keys"], raw_pot["m_Values"])}
        else:
            pot_map = {}
        pot_keys = [sk["id"] for sk in PLAYER_SKILLS]
        pot_vals = [
            int(_clamp(max(pot_map.get(sk["id"], base_pot), int(skills[sk["key"]])), 1, 20))
            for sk in PLAYER_SKILLS
        ]

        langs = pdata.get("languagesSpoken")
        if not langs:
            langs = [{"languageId": 13, "languageSkill": 20, "limit": 20, "progress": 0.0}]

        raw_roles = pdata.get("mapPositionAttributes")
        if raw_roles:
            role_attrs = raw_roles
        else:
            role_comforts = pdata.get("roleComforts", {})
            role_attrs = [
                {
                    "positionType": pos_id,
                    "roleComfort": int(_clamp(int(role_comforts.get(str(pos_id), 6)), 1, 10)),
                    "progress": 30.0,
                }
                for pos_id in sorted(PLAYER_POSITIONS.keys())
            ]

        raw_maps = pdata.get("mapOpinions")
        if raw_maps is not None:
            map_opinions = raw_maps
        else:
            map_opinions = [
                {"mapId": m["id"], "like": True}
                for m in self.data.get("maps", {}).get("maps", [])
            ]

        raw_pers = pdata.get("personality", {})
        personality = {
            "quietPassion": int(_clamp(int(raw_pers.get("quietPassion", 10)), 1, 20)),
            "kindMean": int(_clamp(int(raw_pers.get("kindMean", 10)), 1, 20)),
            "loyalMercenary": int(_clamp(int(raw_pers.get("loyalMercenary", 10)), 1, 20)),
            "contentAmbition": int(_clamp(int(raw_pers.get("contentAmbition", 10)), 1, 20)),
            "stressproneResillient": int(_clamp(int(raw_pers.get("stressproneResillient", 10)), 1, 20)),
            "desireToIgl": int(_clamp(int(raw_pers.get("desireToIgl", 8)), 1, 20)),
            "desireToAwp": int(_clamp(int(raw_pers.get("desireToAwp", 8)), 1, 20)),
        }

        new_id = max((p["id"] for p in self.data["players"]["players"]), default=0) + 1
        new_player: dict[str, Any] = {
            "id": new_id,
            "name": name,
            "age": age,
            "nation": nation,
            "reputation": reputation,
            "portrait": self._default_portrait(age),
            "preferredMentality": mentality,
            "languagesSpoken": langs,
            "setForRetirement": bool(pdata.get("setForRetirement", False)),
            "monthsBenchedOrWithoutContract": 0,
            "monthsSinceNewContract": 6,
            "reputationProgress": 0.0,
            "potential": {"m_Keys": pot_keys, "m_Values": pot_vals},
            "playerAwards": [],
            "recentlyAgreedToResolveDilemmaScore": 0.0,
            "skills": skills,
            "mapPositionAttributes": role_attrs,
            "mapOpinions": map_opinions,
            "mood": {
                "moodFromTournamentReputation": 0.0,
                "moodFromBurnout": 0.0,
                "moodFromRelationships": 0.0,
                "moodFromDialog": 0.0,
                "moodFromPersonality": 0.25,
                "moodFromPracticeDialog": 0.0,
                "moodsFromMatches": [],
                "moodsFromTournaments": [],
            },
            "personality": personality,
            "burnout": {"burnoutFromPractice": 0.0, "burnoutFromMatches": 0.0},
            "longevity": longevity,
            "dialogCooldown": 0,
            "preliminaryDialogCooldown": 0,
            "temporaryStandIn": False,
            "dontReplaceOnRetire": False,
            "academyPlayer": False,
            "skillOffset": -1,
            "dialogStage": 0,
            "dialogConsideration": 0,
            "dialogKey": 0,
            "practiceRatings": [],
            "useStartingPotential": False,
            "startingPotential": 0,
        }

        self.data["players"]["players"].append(new_player)
        self.rebuild_indices()
        self.dirty = True

        contract_cfg = payload.get("contract") or {}
        target_team_id = int(contract_cfg.get("teamId") or payload.get("targetTeamId") or 0)
        if target_team_id > 0:
            self.transfer_player(
                {
                    "playerId": new_id,
                    "targetTeamId": target_team_id,
                    "benchPlayerId": int(contract_cfg.get("benchPlayerId") or payload.get("benchPlayerId") or 0),
                    "joinBenched": bool(contract_cfg.get("benched", False)),
                    "autoPromoteOldTeam": False,
                    "buyoutPrice": 0,
                    "applyFinances": False,
                    "salaryYear": int(contract_cfg.get("salaryYear", 250000)),
                    "endDate": contract_cfg.get("endDate"),
                    "status": int(contract_cfg.get("status", 1)),
                    "igl": int(contract_cfg.get("igl", 2)),
                    "sniper": int(contract_cfg.get("sniper", 2)),
                    "contractType": int(contract_cfg.get("contractType", 0)),
                    "signingOnFee": int(contract_cfg.get("signingOnFee", 0)),
                }
            )

        return self.get_player(new_id)

    def create_staff(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create a brand-new staff member and optionally sign them to a team."""
        assert self.data is not None
        sdata = payload.get("staff", payload)
        name = str(sdata.get("name", "")).strip()
        if not name:
            raise ValueError("Staff name / alias cannot be empty.")

        age = int(_clamp(int(sdata.get("age", 34)), 20, 85))
        nation = int(sdata.get("nation", 1))
        reputation = int(_clamp(int(sdata.get("reputation", 10)), 1, 20))
        mentality = int(_clamp(int(sdata.get("preferredMentality", 1)), 0, 3))
        retire_age = int(sdata.get("retirementConsiderationAge", 65))
        base_skill = float(_clamp(float(sdata.get("baseSkill", 12.0)), 1.0, 20.0))
        base_pot = int(_clamp(int(sdata.get("basePotential", max(int(round(base_skill)) + 3, 15))), 1, 20))

        raw_skills = sdata.get("skills", {})
        skills: dict[str, float] = {}
        for sk in STAFF_SKILLS:
            key = sk["key"]
            skills[key] = float(_clamp(float(raw_skills.get(key, base_skill)), 1.0, 20.0))

        raw_pot = sdata.get("potential", {})
        if isinstance(raw_pot, dict) and "m_Keys" in raw_pot and "m_Values" in raw_pot:
            pot_map = {int(k): int(_clamp(int(v), 1, 20)) for k, v in zip(raw_pot["m_Keys"], raw_pot["m_Values"])}
        else:
            pot_map = {}
        pot_keys = [sk["id"] for sk in STAFF_SKILLS]
        pot_vals = [
            int(_clamp(max(pot_map.get(sk["id"], base_pot), int(skills[sk["key"]])), 1, 20))
            for sk in STAFF_SKILLS
        ]

        langs = sdata.get("languagesSpoken")
        if not langs:
            langs = [{"languageId": 13, "languageSkill": 20, "limit": 20, "progress": 0.0}]

        contract_cfg = payload.get("contract") or {}
        preferred_role = int(contract_cfg.get("role", 0))
        raw_ci = sdata.get("careerInterests")
        if raw_ci:
            career_interests = raw_ci
        else:
            career_interests = [
                {
                    "roleType": r_id,
                    "roleInterest": 20 if r_id == preferred_role else 10,
                }
                for r_id in sorted(STAFF_ROLES.keys())
            ]

        new_id = max((s["id"] for s in self.data["staffers"]["staffers"]), default=0) + 1
        new_staff: dict[str, Any] = {
            "id": new_id,
            "name": name,
            "age": age,
            "nation": nation,
            "reputation": reputation,
            "portrait": self._default_portrait(age),
            "preferredMentality": mentality,
            "languagesSpoken": langs,
            "setForRetirement": bool(sdata.get("setForRetirement", False)),
            "monthsBenchedOrWithoutContract": 0,
            "monthsSinceNewContract": 6,
            "reputationProgress": 0.0,
            "potential": {"m_Keys": pot_keys, "m_Values": pot_vals},
            "playerAwards": [],
            "recentlyAgreedToResolveDilemmaScore": 0.0,
            "skills": skills,
            "careerInterests": career_interests,
            "retirementConsiderationAge": retire_age,
            "careerStats": [],
        }

        self.data["staffers"]["staffers"].append(new_staff)
        self.rebuild_indices()
        self.dirty = True

        target_team_id = int(contract_cfg.get("teamId") or payload.get("targetTeamId") or 0)
        if target_team_id > 0:
            self.transfer_staff(
                {
                    "staffId": new_id,
                    "targetTeamId": target_team_id,
                    "role": preferred_role,
                    "replaceExisting": bool(contract_cfg.get("replaceExisting", True)),
                    "buyoutPrice": 0,
                    "applyFinances": False,
                    "salaryYear": int(contract_cfg.get("salaryYear", 180000)),
                    "endDate": contract_cfg.get("endDate"),
                    "rejectAllStaffOffers": bool(contract_cfg.get("rejectAllStaffOffers", False)),
                }
            )

        return self.get_staff(new_id)

    # ------------------------------------------------------------------
    # Detailed Statistics & Match Analytics
    # ------------------------------------------------------------------

    def _stats_lookups(self) -> tuple[dict[int, str], dict[int, dict[str, Any]], dict[int, str]]:
        assert self.data is not None
        tmpl_names: dict[int, str] = {}
        tourn_by_id: dict[int, dict[str, Any]] = {}
        raw_tourns: dict[int, dict[str, Any]] = {}
        for t in self.data.get("tournaments", {}).get("tournaments", []):
            raw_tourns[t["id"]] = t
            if "template" in t:
                tmpl_names.setdefault(t["template"], t.get("name", f"Tournament #{t['template']}"))
        # Match.tournamentId always references tournamentStages[].id (never tournaments[].id directly,
        # which has an overlapping 1..N ID space and would mislabel matches like Major Playoffs #30 as Stake Pulse #30).
        for s in self.data.get("tournamentStages", {}).get("tournamentStages", []):
            sid = s.get("id")
            if sid is None:
                continue
            parent = raw_tourns.get(s.get("parentId"), {})
            base_name = parent.get("name") or tmpl_names.get(s.get("parentTemplate")) or f"Tournament #{sid}"
            raw_stage = s.get("name", "")
            stage_label = raw_stage.split("__", 1)[0].replace("_", " ").strip().title() if raw_stage else ""
            full_name = f"{base_name} ({stage_label})" if stage_label else base_name
            tourn_by_id[sid] = {
                "id": sid,
                "name": full_name,
                "parentId": s.get("parentId"),
                "reputation": parent.get("reputation", 1),
            }
        map_names = {m["id"]: m.get("name", f"Map {m['id']}") for m in self.data.get("maps", {}).get("maps", [])}
        return tmpl_names, tourn_by_id, map_names

    @staticmethod
    def _match_date_key(dt_obj: dict[str, Any]) -> tuple[int, int, int, int]:
        return (
            int(dt_obj.get("year", 0)),
            int(dt_obj.get("month", 0)),
            int(dt_obj.get("day", 0)),
            int(dt_obj.get("hour", 0)),
        )

    @staticmethod
    def _parse_map_player_stat(ps: dict[str, Any]) -> dict[str, int]:
        d = ps.get("data", [])
        pid = int(d[0]) if len(d) > 0 else 0
        assists = int(d[1]) if len(d) > 1 else 0
        flash_assists = int(d[2]) if len(d) > 2 else 0
        deaths = int(d[3]) if len(d) > 3 else 0
        damage = int(d[4]) if len(d) > 4 else 0
        hs_kills = int(d[5]) if len(d) > 5 else 0
        k2 = int(d[6]) if len(d) > 6 else 0
        k3 = int(d[7]) if len(d) > 7 else 0
        k4 = int(d[8]) if len(d) > 8 else 0
        k5 = int(d[9]) if len(d) > 9 else 0
        opening_deaths = int(d[10]) if len(d) > 10 else 0

        kills = 0
        opening_kills = 0
        sniper_kills = 0
        clutch_kills = 0
        for mk in ps.get("matrixKills", []):
            md = mk.get("data", [])
            if len(md) >= 5:
                kills += int(md[1])
                opening_kills += int(md[2])
                sniper_kills += int(md[3])
                clutch_kills += int(md[4])

        return {
            "playerId": pid,
            "kills": kills,
            "assists": assists,
            "flashAssists": flash_assists,
            "deaths": deaths,
            "damage": damage,
            "hsKills": hs_kills,
            "k2": k2,
            "k3": k3,
            "k4": k4,
            "k5": k5,
            "openingKills": opening_kills,
            "openingDeaths": opening_deaths,
            "sniperKills": sniper_kills,
            "clutchKills": clutch_kills,
        }

    def _compute_top20_prediction(self, pred_year: int) -> dict[str, Any]:
        """Replicate DashboardManager::CheckForPlayerOfTheYearEvents Top 20 formula."""
        assert self.data is not None
        cur_dt = self.data.get("datetime", {}) or {}
        cur_save_year = int(cur_dt.get("year", 0) or 0)

        # Aggregate year-level overall & vs-Top-10 career stats (opponentRank == 3)
        stats_by_pid: dict[int, dict[str, Any]] = {}
        for row in self.data.get("playerCareerStats", {}).get("playerCareerStats", []):
            if int(row.get("year", 0) or 0) != pred_year:
                continue
            mw = int(row.get("matchesWon", 0) or 0)
            ml = int(row.get("matchesLost", 0) or 0)
            matches_cnt = mw + ml
            if matches_cnt <= 0:
                continue
            pid = int(row.get("playerId", 0) or 0)
            if not pid:
                continue
            acc_r = float(row.get("accumulativeRating", 0.0) or 0.0)
            agg = stats_by_pid.setdefault(
                pid,
                {"allMatches": 0, "allAcc": 0.0, "t10Matches": 0, "t10Acc": 0.0},
            )
            agg["allMatches"] += matches_cnt
            agg["allAcc"] += acc_r
            if int(row.get("opponentRank", 0) or 0) == 3:
                agg["t10Matches"] += matches_cnt
                agg["t10Acc"] += acc_r

        # Check Dec 23 game snapshot if predicting the current in-game year
        save_poty_by_pid: dict[int, dict[str, Any]] = {}
        save_vote_pid = 0
        if pred_year == cur_save_year:
            for srow in self.data.get("profile", {}).get("playerOfTheYearScores", []) or []:
                spid = int(srow.get("playerId", 0) or 0)
                if spid:
                    voted = bool(srow.get("profileVote", False))
                    if voted:
                        save_vote_pid = spid
                    save_poty_by_pid[spid] = {
                        "rating": round(float(srow.get("rating", 0.0) or 0.0), 4),
                        "score": round(float(srow.get("score", 0.0) or 0.0), 4),
                        "voted": voted,
                    }

        candidates: list[dict[str, Any]] = []
        snubbed_pool: list[dict[str, Any]] = []
        finalized = False

        for p in self.data["players"]["players"]:
            pid = p["id"]
            st = stats_by_pid.get(pid)
            if not st:
                continue
            all_m = st["allMatches"]
            all_r = (st["allAcc"] / all_m) if all_m > 0 else 0.0
            t10_m = st["t10Matches"]
            t10_r = (st["t10Acc"] / t10_m) if t10_m > 0 else 0.0

            mvps = 0
            evps = 0
            actual_top20 = 0
            for a in p.get("playerAwards", []) or []:
                if int(a.get("year", 0) or 0) != pred_year:
                    continue
                atype = int(a.get("type", -1))
                if atype == 0:
                    mvps += 1
                elif atype == 2:
                    evps += 1
                elif atype == 3:
                    place = int(a.get("top20Placement", 0) or 0)
                    if place > 0:
                        actual_top20 = place
                        finalized = True

            c = self.player_contract_by_pid.get(pid)
            cur_tid = c["teamId"] if c else 0
            cur_tname = self.teams_by_id[cur_tid]["name"] if cur_tid in self.teams_by_id else "Free Agent"

            if (mvps + evps) > 0 and t10_m > 0:
                award_mult = (1.05 ** mvps) * (1.01 ** evps)
                sample_w = min(t10_m / 50.0, 1.0)
                base_score = t10_r * award_mult * sample_w
                sp = save_poty_by_pid.get(pid)
                candidates.append(
                    {
                        "playerId": pid,
                        "name": p.get("name", ""),
                        "teamId": cur_tid,
                        "teamName": cur_tname,
                        "age": p.get("age", 0),
                        "nationName": NATIONS.get(p.get("nation", 0), ""),
                        "avgSkill": _player_avg_skill(p),
                        "t10Rating": round(t10_r, 4),
                        "t10Matches": t10_m,
                        "sampleWeight": round(sample_w, 4),
                        "overallRating": round(all_r, 4),
                        "overallMatches": all_m,
                        "mvps": mvps,
                        "evps": evps,
                        "awardMult": round(award_mult, 4),
                        "baseScore": round(base_score, 6),
                        "votedScore": round(base_score * 1.1, 6),
                        "actualTop20": actual_top20,
                        "saveRating": sp["rating"] if sp else None,
                        "saveScore": sp["score"] if sp else None,
                        "saveVoted": sp["voted"] if sp else False,
                    }
                )
            elif all_m >= 10:
                reason = "0 MVPs/EVPs this year (fails award gate)" if (mvps + evps) == 0 else "0 matches vs Top 10 teams (fails opponent gate)"
                snubbed_pool.append(
                    {
                        "playerId": pid,
                        "name": p.get("name", ""),
                        "teamId": cur_tid,
                        "teamName": cur_tname,
                        "overallRating": round(all_r, 4),
                        "overallMatches": all_m,
                        "t10Rating": round(t10_r, 4),
                        "t10Matches": t10_m,
                        "mvps": mvps,
                        "evps": evps,
                        "baseScore": 0.0,
                        "reason": reason,
                    }
                )

        # Sort eligible candidates exactly like CheckForPlayerOfTheYearEvents (descending score)
        candidates.sort(key=lambda r: (-r["baseScore"], -r["t10Rating"], r["playerId"]))
        for idx, cand in enumerate(candidates, start=1):
            cand["baseRank"] = idx
            cand["inGameTop20"] = idx <= 20
            cand["cstvBallotRank"] = None

        # CSTV voting UI (ShowCstvVoting) takes the Top 20 by score, sorts by vs-Top-10 rating, and lists top 13
        top20_by_rating = sorted(candidates[:20], key=lambda r: (-r["t10Rating"], r["baseRank"]))
        for v_idx, cand in enumerate(top20_by_rating[:13], start=1):
            cand["cstvBallotRank"] = v_idx

        # Also add #21+ high-rated candidates hurt by <50 Top-10 match penalty or low awards into snubbed watchlist
        for cand in candidates[20:]:
            if cand["overallMatches"] < 10:
                continue
            if cand["t10Matches"] < 50:
                reason = f"Sample penalty: {cand['t10Matches']}/50 vs Top 10 ({cand['sampleWeight']:.2f}x)"
            else:
                reason = f"Outside Top 20 cut (base rank #{cand['baseRank']})"
            snubbed_pool.append(
                {
                    "playerId": cand["playerId"],
                    "name": cand["name"],
                    "teamId": cand["teamId"],
                    "teamName": cand["teamName"],
                    "overallRating": cand["overallRating"],
                    "overallMatches": cand["overallMatches"],
                    "t10Rating": cand["t10Rating"],
                    "t10Matches": cand["t10Matches"],
                    "mvps": cand["mvps"],
                    "evps": cand["evps"],
                    "baseScore": cand["baseScore"],
                    "reason": reason,
                }
            )

        snubbed_pool.sort(key=lambda r: (-r["overallRating"], -r["overallMatches"], r["playerId"]))

        return {
            "year": pred_year,
            "saveDate": cur_dt,
            "hasDec23Snapshot": bool(save_poty_by_pid),
            "saveVotePlayerId": save_vote_pid,
            "finalized": finalized,
            "eligibleCount": len(candidates),
            "candidates": candidates[:40],
            "snubbed": snubbed_pool[:15],
        }

    def get_stats_overview(self, year: int | None = None, team_id: int | None = None, min_maps: int = 0) -> dict[str, Any]:
        """Compute comprehensive player, team, map, award, and match statistics."""
        if self.data is None:
            return {"loaded": False}

        tmpl_names, tourn_by_id, map_names = self._stats_lookups()
        years_set: set[int] = set()

        # 1. Career stats aggregation (rating, official matches W/L)
        pcs_agg: dict[int, dict[str, Any]] = {}
        for row in self.data.get("playerCareerStats", {}).get("playerCareerStats", []):
            ryear = int(row.get("year", 0))
            if ryear:
                years_set.add(ryear)
            if year is not None and ryear != year:
                continue
            if team_id is not None and row.get("teamId") != team_id:
                continue
            rp = int(row.get("roundsPlayed", 0))
            mw = int(row.get("matchesWon", 0))
            ml = int(row.get("matchesLost", 0))
            if rp == 0 and mw == 0 and ml == 0:
                continue
            pid = int(row.get("playerId", 0))
            entry = pcs_agg.setdefault(
                pid,
                {
                    "matchesWon": 0,
                    "matchesLost": 0,
                    "accRating": 0.0,
                    "rounds": 0,
                    "kills": 0,
                    "assists": 0,
                    "deaths": 0,
                    "damage": 0,
                    "ok": 0,
                    "od": 0,
                },
            )
            entry["matchesWon"] += mw
            entry["matchesLost"] += ml
            entry["accRating"] += float(row.get("accumulativeRating", 0.0))
            entry["rounds"] += rp
            entry["kills"] += int(row.get("accumulatedKills", 0))
            entry["assists"] += int(row.get("accumulatedAssists", 0))
            entry["deaths"] += int(row.get("accumulateDeaths", 0))
            entry["damage"] += int(row.get("accumulatedDamage", 0))
            entry["ok"] += int(row.get("accumulatedOpeningKills", 0))
            entry["od"] += int(row.get("accumulatedOpeningDeaths", 0))

        # 2. Played matches & map-level micro-stats
        p_map_agg: dict[int, dict[str, int]] = {}
        t_agg: dict[int, dict[str, int]] = {}
        m_agg: dict[int, dict[str, int]] = {
            mid: {"mapId": mid, "name": mname, "played": 0, "rounds": 0, "otMaps": 0, "picks": 0, "bans": 0, "kills": 0, "aces": 0}
            for mid, mname in map_names.items()
        }
        recent_matches: list[dict[str, Any]] = []
        total_matches = 0
        total_maps = 0
        total_rounds = 0
        total_kills = 0
        total_k2 = total_k3 = total_k4 = total_k5 = 0
        total_clutches = 0

        for m in self.data.get("matches", {}).get("matches", []):
            match_maps = [mm for mm in m.get("matchMaps", []) if mm.get("baseMatchRounds")]
            if not match_maps:
                continue
            dt_obj = m.get("datetime", {})
            myear = int(dt_obj.get("year", 0))
            if myear:
                years_set.add(myear)
            if year is not None and myear != year:
                continue

            t1 = int(m.get("team1Id", 0))
            t2 = int(m.get("team2Id", 0))
            if team_id is not None and team_id not in (t1, t2):
                continue

            total_matches += 1
            for mp in m.get("mapPicks", []):
                mid = int(mp.get("mapId", 0))
                if mid in m_agg:
                    if mp.get("picked"):
                        m_agg[mid]["picks"] += 1
                    else:
                        m_agg[mid]["bans"] += 1

            t1_maps = 0
            t2_maps = 0
            t1_pids = set(m.get("team1PlayerIds", []))
            t2_pids = set(m.get("team2PlayerIds", []))
            map_score_strs: list[str] = []

            for mm in match_maps:
                rounds = mm.get("baseMatchRounds", [])
                r_cnt = len(rounds)
                if r_cnt == 0:
                    continue
                total_maps += 1
                total_rounds += r_cnt
                mid = int(mm.get("mapId", 0))

                t1_r = sum(1 for r in rounds if r.get("winner") == t1)
                t2_r = sum(1 for r in rounds if r.get("winner") == t2)
                if t1_r > t2_r:
                    t1_maps += 1
                    t1_won_map = True
                else:
                    t2_maps += 1
                    t1_won_map = False
                map_score_strs.append(f"{map_names.get(mid, f'Map {mid}')} {t1_r}-{t2_r}")

                # Pistol rounds (1 and 13 in MR12)
                t1_pistols_w = sum(1 for r in rounds if r.get("number") in (1, 13) and r.get("winner") == t1)
                t2_pistols_w = sum(1 for r in rounds if r.get("number") in (1, 13) and r.get("winner") == t2)
                pistols_cnt = sum(1 for r in rounds if r.get("number") in (1, 13))

                t1_cw = int(mm.get("team1ClutchesWon", 0))
                t2_cw = int(mm.get("team2ClutchesWon", 0))
                total_clutches += t1_cw + t2_cw

                for tid_x, mw_x, ml_x, pw_x, cw_x, sv_x, fb_x in (
                    (t1, 1 if t1_won_map else 0, 0 if t1_won_map else 1, t1_pistols_w, t1_cw, int(mm.get("team1Saves", 0)), int(mm.get("team1Fullbuys", 0))),
                    (t2, 0 if t1_won_map else 1, 1 if t1_won_map else 0, t2_pistols_w, t2_cw, int(mm.get("team2Saves", 0)), int(mm.get("team2Fullbuys", 0))),
                ):
                    if tid_x:
                        ta = t_agg.setdefault(
                            tid_x,
                            {"matchesWon": 0, "matchesLost": 0, "mapsWon": 0, "mapsLost": 0, "roundsPlayed": 0, "pistolsWon": 0, "pistolsPlayed": 0, "clutchesWon": 0, "saves": 0, "fullbuys": 0},
                        )
                        ta["mapsWon"] += mw_x
                        ta["mapsLost"] += ml_x
                        ta["roundsPlayed"] += r_cnt
                        ta["pistolsWon"] += pw_x
                        ta["pistolsPlayed"] += pistols_cnt
                        ta["clutchesWon"] += cw_x
                        ta["saves"] += sv_x
                        ta["fullbuys"] += fb_x

                if mid in m_agg:
                    m_agg[mid]["played"] += 1
                    m_agg[mid]["rounds"] += r_cnt
                    if r_cnt > 24:
                        m_agg[mid]["otMaps"] += 1

                for ps_raw in mm.get("playerStats", []):
                    ps = self._parse_map_player_stat(ps_raw)
                    pid = ps["playerId"]
                    if not pid:
                        continue
                    if team_id is not None:
                        if team_id == t1 and pid not in t1_pids:
                            continue
                        if team_id == t2 and pid not in t2_pids:
                            continue
                    pa = p_map_agg.setdefault(
                        pid,
                        {
                            "mapsPlayed": 0,
                            "mapsWon": 0,
                            "rounds": 0,
                            "kills": 0,
                            "assists": 0,
                            "flashAssists": 0,
                            "deaths": 0,
                            "damage": 0,
                            "hsKills": 0,
                            "k2": 0,
                            "k3": 0,
                            "k4": 0,
                            "k5": 0,
                            "openingKills": 0,
                            "openingDeaths": 0,
                            "sniperKills": 0,
                            "clutchKills": 0,
                        },
                    )
                    pa["mapsPlayed"] += 1
                    won_this_map = (pid in t1_pids and t1_won_map) or (pid in t2_pids and not t1_won_map)
                    if won_this_map:
                        pa["mapsWon"] += 1
                    pa["rounds"] += r_cnt
                    for k_stat in ("kills", "assists", "flashAssists", "deaths", "damage", "hsKills", "k2", "k3", "k4", "k5", "openingKills", "openingDeaths", "sniperKills", "clutchKills"):
                        pa[k_stat] += ps[k_stat]
                    total_kills += ps["kills"]
                    total_k2 += ps["k2"]
                    total_k3 += ps["k3"]
                    total_k4 += ps["k4"]
                    total_k5 += ps["k5"]
                    if mid in m_agg:
                        m_agg[mid]["kills"] += ps["kills"]
                        m_agg[mid]["aces"] += ps["k5"]

            if t1:
                t1a = t_agg.setdefault(t1, {"matchesWon": 0, "matchesLost": 0, "mapsWon": 0, "mapsLost": 0, "roundsPlayed": 0, "pistolsWon": 0, "pistolsPlayed": 0, "clutchesWon": 0, "saves": 0, "fullbuys": 0})
                if t1_maps > t2_maps:
                    t1a["matchesWon"] += 1
                else:
                    t1a["matchesLost"] += 1
            if t2:
                t2a = t_agg.setdefault(t2, {"matchesWon": 0, "matchesLost": 0, "mapsWon": 0, "mapsLost": 0, "roundsPlayed": 0, "pistolsWon": 0, "pistolsPlayed": 0, "clutchesWon": 0, "saves": 0, "fullbuys": 0})
                if t2_maps > t1_maps:
                    t2a["matchesWon"] += 1
                else:
                    t2a["matchesLost"] += 1

            tourn_obj = tourn_by_id.get(m.get("tournamentId"), {})
            recent_matches.append(
                {
                    "id": m["id"],
                    "datetime": dt_obj,
                    "sortKey": self._match_date_key(dt_obj),
                    "tournamentName": tourn_obj.get("name", f"Tournament #{m.get('tournamentId')}"),
                    "team1Id": t1,
                    "team1Name": self.teams_by_id.get(t1, {}).get("name", f"Team {t1}"),
                    "team2Id": t2,
                    "team2Name": self.teams_by_id.get(t2, {}).get("name", f"Team {t2}"),
                    "team1Maps": t1_maps,
                    "team2Maps": t2_maps,
                    "winnerTeamId": t1 if t1_maps > t2_maps else t2,
                    "bo": m.get("numberOfMaps", len(match_maps)),
                    "scoresSummary": ", ".join(map_score_strs),
                    "team1RankBefore": m.get("team1RankBefore", 0),
                    "team2RankBefore": m.get("team2RankBefore", 0),
                }
            )

        recent_matches.sort(key=lambda x: x["sortKey"], reverse=True)
        for rm in recent_matches:
            rm.pop("sortKey", None)

        # 3. Awards & Tournament Hall of Fame
        # PlayerAward.Type enum from game assembly: 0=mvp, 1=win (event trophy), 2=evp, 3=top20
        total_mvps = total_wins = total_evps = 0
        player_awards_summary: dict[int, dict[str, int]] = {}
        awards_feed: list[dict[str, Any]] = []
        for p in self.data["players"]["players"]:
            pid = p["id"]
            aws = p.get("playerAwards", [])
            if not aws:
                continue
            mv = wn = ev = t20 = 0
            for a in aws:
                ayear = int(a.get("year", 0))
                tmpl_id = int(a.get("tournamentTemplate", -1))
                # Skip pre-career mock/dev awards (year=7, tournamentTemplate=-1)
                if ayear < 2000 or (tmpl_id < 0 and a.get("type") != 3):
                    continue
                if year is not None and ayear != year:
                    continue
                atype = int(a.get("type", 0))
                if atype == 0:
                    mv += 1
                    total_mvps += 1
                elif atype == 1:
                    wn += 1
                    total_wins += 1
                elif atype == 2:
                    ev += 1
                    total_evps += 1
                elif atype == 3:
                    t20 = int(a.get("top20Placement", 0)) or t20
                tid_a = a.get("teamId", 0)
                awards_feed.append(
                    {
                        "playerId": pid,
                        "playerName": p.get("name", ""),
                        "teamName": self.teams_by_id.get(tid_a, {}).get("name", ""),
                        "type": atype,
                        "typeLabel": {0: "MVP", 1: "Event Win", 2: "EVP", 3: f"Top 20 (#{a.get('top20Placement', '')})"}.get(atype, f"Award {atype}"),
                        "tournamentName": tmpl_names.get(tmpl_id, f"Event #{tmpl_id}") if atype != 3 else "HLTV Yearly Top 20",
                        "year": ayear,
                        "month": int(a.get("month", 0)),
                    }
                )
            player_awards_summary[pid] = {"mvps": mv, "wins": wn, "evps": ev, "top20": t20}
        awards_feed.sort(key=lambda x: (-x["year"], -x["month"], x["type"], x["playerName"]))

        # 4. Build Player Leaderboard
        all_pids = set(pcs_agg.keys()) | set(p_map_agg.keys())
        player_rows: list[dict[str, Any]] = []
        for pid in all_pids:
            p = self.players_by_id.get(pid)
            if not p:
                continue
            c = self.player_contract_by_pid.get(pid)
            cur_tid = c["teamId"] if c else 0
            cur_tname = self.teams_by_id[cur_tid]["name"] if cur_tid in self.teams_by_id else "Free Agent"

            pcs = pcs_agg.get(pid, {})
            pm = p_map_agg.get(pid, {})
            maps_played = pm.get("mapsPlayed", 0)
            if maps_played < min_maps:
                continue

            mw = pcs.get("matchesWon", 0)
            ml = pcs.get("matchesLost", 0)
            matches_cnt = mw + ml
            rating = round(pcs["accRating"] / matches_cnt, 3) if matches_cnt > 0 else 0.0

            # Use map_agg for rounds/K/A/D/dmg (exact & includes flash/HS/clutches/AWP/multikills), fallback to pcs
            rounds = pm.get("rounds") or pcs.get("rounds", 0)
            kills = pm.get("kills") if pm else pcs.get("kills", 0)
            deaths = pm.get("deaths") if pm else pcs.get("deaths", 0)
            assists = pm.get("assists") if pm else pcs.get("assists", 0)
            damage = pm.get("damage") if pm else pcs.get("damage", 0)
            ok = pm.get("openingKills") if pm else pcs.get("ok", 0)
            od = pm.get("openingDeaths") if pm else pcs.get("od", 0)
            hs = pm.get("hsKills", 0)
            awp_k = pm.get("sniperKills", 0)
            clutches = pm.get("clutchKills", 0)
            flash_a = pm.get("flashAssists", 0)
            k2 = pm.get("k2", 0)
            k3 = pm.get("k3", 0)
            k4 = pm.get("k4", 0)
            k5 = pm.get("k5", 0)
            aw = player_awards_summary.get(pid, {})

            player_rows.append(
                {
                    "playerId": pid,
                    "name": p.get("name", ""),
                    "age": p.get("age", 0),
                    "nationName": NATIONS.get(p.get("nation", 0), ""),
                    "teamId": cur_tid,
                    "teamName": cur_tname,
                    "avgSkill": _player_avg_skill(p),
                    "reputation": p.get("reputation", 1),
                    "rating": rating,
                    "matches": matches_cnt,
                    "matchesWon": mw,
                    "matchesLost": ml,
                    "winPct": round(mw * 100.0 / matches_cnt, 1) if matches_cnt else 0.0,
                    "mapsPlayed": maps_played,
                    "mapsWon": pm.get("mapsWon", 0),
                    "rounds": rounds,
                    "kills": kills,
                    "assists": assists,
                    "flashAssists": flash_a,
                    "deaths": deaths,
                    "kd": round(kills / max(deaths, 1), 2),
                    "kDiff": kills - deaths,
                    "kpr": round(kills / rounds, 2) if rounds else 0.0,
                    "dpr": round(deaths / rounds, 2) if rounds else 0.0,
                    "adr": round(damage / rounds, 1) if rounds else 0.0,
                    "hsPct": round(hs * 100.0 / kills, 1) if kills else 0.0,
                    "openingKills": ok,
                    "openingDeaths": od,
                    "openingDiff": ok - od,
                    "openingPct": round(ok * 100.0 / (ok + od), 1) if (ok + od) else 0.0,
                    "sniperKills": awp_k,
                    "clutchKills": clutches,
                    "k2": k2,
                    "k3": k3,
                    "k4": k4,
                    "k5": k5,
                    "mvps": aw.get("mvps", 0),
                    "evps": aw.get("evps", 0),
                    "wins": aw.get("wins", 0),
                    "top20": aw.get("top20", 0),
                }
            )

        player_rows.sort(key=lambda r: (-r["rating"], -r["kd"], -r["kills"]))

        # 5. Team Standings & Tournament Hall of Fame
        team_rows: list[dict[str, Any]] = []
        hall_of_fame: list[dict[str, Any]] = []
        total_prize_pool = 0
        for t in self.data["teams"]["teams"]:
            tid = t["id"]
            if team_id is not None and tid != team_id:
                continue
            rank_pts = 0
            titles = 0
            top4 = 0
            prize_won = 0
            for rp in t.get("rankingPoints", []):
                r_yr = int(rp.get("dateGranted", {}).get("year", 0))
                rank_pts += int(rp.get("currentPoints", 0))
                if year is not None and r_yr != year:
                    continue
                pmoney = int(rp.get("prizeMoney", 0))
                prize_won += pmoney
                total_prize_pool += pmoney
                place = int(rp.get("tournamentPlacement", 0))
                if place == 1:
                    titles += 1
                    hall_of_fame.append(
                        {
                            "teamId": tid,
                            "teamName": t.get("name", ""),
                            "tournamentName": tmpl_names.get(rp.get("tournamentTemplate"), f"Event #{rp.get('tournamentTemplate')}"),
                            "prizeMoney": pmoney,
                            "points": int(rp.get("originalPoints", 0)),
                            "datetime": rp.get("dateGranted", {}),
                            "sortKey": self._match_date_key(rp.get("dateGranted", {})),
                        }
                    )
                if 1 <= place <= 4:
                    top4 += 1

            pcs_t = self.get_team_player_contracts(tid)
            active_players = [self.players_by_id[c["playerId"]] for c in pcs_t if not c.get("benched") and c["playerId"] in self.players_by_id]
            avg_roster_skill = round(sum(_player_avg_skill(p) for p in active_players) / len(active_players), 2) if active_players else 0.0
            avg_roster_age = round(sum(p.get("age", 20) for p in active_players) / len(active_players), 1) if active_players else 0.0

            ta = t_agg.get(tid, {})
            mw_t = ta.get("matchesWon", 0)
            ml_t = ta.get("matchesLost", 0)
            m_tot = mw_t + ml_t
            map_w = ta.get("mapsWon", 0)
            map_l = ta.get("mapsLost", 0)
            map_tot = map_w + map_l
            pw_t = ta.get("pistolsWon", 0)
            pp_t = ta.get("pistolsPlayed", 0)

            rhist = t.get("rankingHistory", [])
            cur_rank = rhist[-1] if rhist else 0
            rank_delta = (rhist[-2] - cur_rank) if len(rhist) >= 2 and rhist[-2] > 0 and cur_rank > 0 else 0

            team_rows.append(
                {
                    "teamId": tid,
                    "name": t.get("name", ""),
                    "nationName": NATIONS.get(t.get("nation", 0), ""),
                    "reputation": t.get("reputation", 1),
                    "worldRank": cur_rank,
                    "rankDelta": rank_delta,
                    "rankingPoints": rank_pts,
                    "avgSkill": avg_roster_skill,
                    "avgAge": avg_roster_age,
                    "matches": m_tot,
                    "matchesWon": mw_t,
                    "matchesLost": ml_t,
                    "matchWinPct": round(mw_t * 100.0 / m_tot, 1) if m_tot else 0.0,
                    "maps": map_tot,
                    "mapsWon": map_w,
                    "mapsLost": map_l,
                    "mapWinPct": round(map_w * 100.0 / map_tot, 1) if map_tot else 0.0,
                    "pistolWinPct": round(pw_t * 100.0 / pp_t, 1) if pp_t else 0.0,
                    "clutchesWon": ta.get("clutchesWon", 0),
                    "titles": titles,
                    "top4": top4,
                    "prizeWon": prize_won,
                    "balance": t.get("teamFinances", {}).get("currentBalance", 0),
                }
            )

        team_rows.sort(key=lambda r: (r["worldRank"] == 0, r["worldRank"] if r["worldRank"] > 0 else 9999, -r["rankingPoints"]))
        hall_of_fame.sort(key=lambda x: x["sortKey"], reverse=True)
        for h in hall_of_fame:
            h.pop("sortKey", None)

        map_rows = []
        for mr in m_agg.values():
            played = mr["played"]
            map_rows.append(
                {
                    **mr,
                    "avgRounds": round(mr["rounds"] / played, 1) if played else 0.0,
                    "otPct": round(mr["otMaps"] * 100.0 / played, 1) if played else 0.0,
                }
            )
        map_rows.sort(key=lambda r: -r["played"])

        cur_save_year = int((self.data.get("datetime", {}) or {}).get("year", 0) or 0)
        pred_year = year if year is not None else (cur_save_year or (max(years_set) if years_set else 0))
        top20_prediction = self._compute_top20_prediction(pred_year) if pred_year else {"year": 0, "candidates": [], "snubbed": []}
        if year is None and not top20_prediction.get("candidates") and years_set:
            latest_data_year = max(years_set)
            if latest_data_year != pred_year:
                top20_prediction = self._compute_top20_prediction(latest_data_year)

        return {
            "loaded": True,
            "years": sorted(years_set, reverse=True),
            "totals": {
                "matchesPlayed": total_matches,
                "mapsPlayed": total_maps,
                "roundsPlayed": total_rounds,
                "kills": total_kills,
                "aces": total_k5,
                "quads": total_k4,
                "triples": total_k3,
                "doubles": total_k2,
                "clutches": total_clutches,
                "mvps": total_mvps,
                "evps": total_evps,
                "wins": total_wins,
                "titlesAwarded": len(hall_of_fame),
                "totalPrizePool": total_prize_pool,
            },
            "players": player_rows,
            "teams": team_rows,
            "maps": map_rows,
            "recentMatches": recent_matches[:120],
            "hallOfFame": hall_of_fame[:80],
            "awardsFeed": awards_feed[:120],
            "top20Prediction": top20_prediction,
        }

    def get_player_stats_detail(self, player_id: int) -> dict[str, Any]:
        """Deep career, map, event, skill-growth, victim, and match breakdown for a player."""
        assert self.data is not None
        p = self.players_by_id.get(player_id)
        if not p:
            raise ValueError(f"Player {player_id} not found.")
        tmpl_names, tourn_by_id, map_names = self._stats_lookups()
        c = self.player_contract_by_pid.get(player_id)
        cur_tid = c["teamId"] if c else 0

        # 1. Career rows by team + event + year
        event_rows = []
        tot = {"mw": 0, "ml": 0, "accRating": 0.0, "rounds": 0, "kills": 0, "assists": 0, "deaths": 0, "damage": 0, "ok": 0, "od": 0}
        for row in self.data.get("playerCareerStats", {}).get("playerCareerStats", []):
            if row.get("playerId") != player_id:
                continue
            rp = int(row.get("roundsPlayed", 0))
            mw = int(row.get("matchesWon", 0))
            ml = int(row.get("matchesLost", 0))
            if rp == 0 and mw == 0 and ml == 0:
                continue
            cnt = mw + ml
            tid_r = int(row.get("teamId", 0))
            tmpl = int(row.get("tournamentTemplate", 0))
            event_rows.append(
                {
                    "year": row.get("year", 0),
                    "month": row.get("month", 0),
                    "teamName": self.teams_by_id.get(tid_r, {}).get("name", f"Team {tid_r}"),
                    "tournamentName": tmpl_names.get(tmpl, f"Event #{tmpl}"),
                    "matchesWon": mw,
                    "matchesLost": ml,
                    "rating": round(float(row.get("accumulativeRating", 0.0)) / cnt, 2) if cnt else 0.0,
                    "rounds": rp,
                    "kills": int(row.get("accumulatedKills", 0)),
                    "assists": int(row.get("accumulatedAssists", 0)),
                    "deaths": int(row.get("accumulateDeaths", 0)),
                    "adr": round(int(row.get("accumulatedDamage", 0)) / rp, 1) if rp else 0.0,
                    "openingDiff": int(row.get("accumulatedOpeningKills", 0)) - int(row.get("accumulatedOpeningDeaths", 0)),
                }
            )
            tot["mw"] += mw
            tot["ml"] += ml
            tot["accRating"] += float(row.get("accumulativeRating", 0.0))
            tot["rounds"] += rp
            tot["kills"] += int(row.get("accumulatedKills", 0))
            tot["assists"] += int(row.get("accumulatedAssists", 0))
            tot["deaths"] += int(row.get("accumulateDeaths", 0))
            tot["damage"] += int(row.get("accumulatedDamage", 0))
            tot["ok"] += int(row.get("accumulatedOpeningKills", 0))
            tot["od"] += int(row.get("accumulatedOpeningDeaths", 0))
        event_rows.sort(key=lambda r: (r["year"], r["month"]), reverse=True)

        # 2. Match & Map breakdown + Victims matrix
        by_map: dict[int, dict[str, int]] = {}
        victims: dict[int, int] = {}
        recent_maps: list[dict[str, Any]] = []
        micro_tot = {"maps": 0, "mapsWon": 0, "rounds": 0, "kills": 0, "assists": 0, "flashAssists": 0, "deaths": 0, "damage": 0, "hsKills": 0, "k2": 0, "k3": 0, "k4": 0, "k5": 0, "openingKills": 0, "openingDeaths": 0, "sniperKills": 0, "clutchKills": 0}

        for m in self.data.get("matches", {}).get("matches", []):
            t1_pids = set(m.get("team1PlayerIds", []))
            t2_pids = set(m.get("team2PlayerIds", []))
            if player_id not in t1_pids and player_id not in t2_pids:
                continue
            t1 = int(m.get("team1Id", 0))
            t2 = int(m.get("team2Id", 0))
            is_t1 = player_id in t1_pids
            opp_tid = t2 if is_t1 else t1
            opp_name = self.teams_by_id.get(opp_tid, {}).get("name", f"Team {opp_tid}")
            tourn_name = tourn_by_id.get(m.get("tournamentId"), {}).get("name", "")
            dt_obj = m.get("datetime", {})

            for mm in m.get("matchMaps", []):
                rounds = mm.get("baseMatchRounds", [])
                r_cnt = len(rounds)
                if r_cnt == 0:
                    continue
                ps_raw = next((x for x in mm.get("playerStats", []) if x.get("data") and x["data"][0] == player_id), None)
                if not ps_raw:
                    continue
                ps = self._parse_map_player_stat(ps_raw)
                t1_r = sum(1 for r in rounds if r.get("winner") == t1)
                t2_r = sum(1 for r in rounds if r.get("winner") == t2)
                won = (t1_r > t2_r) if is_t1 else (t2_r > t1_r)
                mid = int(mm.get("mapId", 0))

                for mk in ps_raw.get("matrixKills", []):
                    md = mk.get("data", [])
                    if len(md) >= 2 and int(md[1]) > 0:
                        opp_pid = int(md[0])
                        victims[opp_pid] = victims.get(opp_pid, 0) + int(md[1])

                micro_tot["maps"] += 1
                if won:
                    micro_tot["mapsWon"] += 1
                micro_tot["rounds"] += r_cnt
                for k_stat in ("kills", "assists", "flashAssists", "deaths", "damage", "hsKills", "k2", "k3", "k4", "k5", "openingKills", "openingDeaths", "sniperKills", "clutchKills"):
                    micro_tot[k_stat] += ps[k_stat]

                bm = by_map.setdefault(mid, {"mapId": mid, "mapName": map_names.get(mid, f"Map {mid}"), "maps": 0, "wins": 0, "rounds": 0, "kills": 0, "deaths": 0, "damage": 0, "hsKills": 0, "sniperKills": 0, "clutchKills": 0, "aces": 0})
                bm["maps"] += 1
                if won:
                    bm["wins"] += 1
                bm["rounds"] += r_cnt
                bm["kills"] += ps["kills"]
                bm["deaths"] += ps["deaths"]
                bm["damage"] += ps["damage"]
                bm["hsKills"] += ps["hsKills"]
                bm["sniperKills"] += ps["sniperKills"]
                bm["clutchKills"] += ps["clutchKills"]
                bm["aces"] += ps["k5"]

                recent_maps.append(
                    {
                        "matchId": m["id"],
                        "datetime": dt_obj,
                        "sortKey": self._match_date_key(dt_obj),
                        "tournamentName": tourn_name,
                        "opponentName": opp_name,
                        "mapName": map_names.get(mid, f"Map {mid}"),
                        "score": f"{t1_r if is_t1 else t2_r}-{t2_r if is_t1 else t1_r}",
                        "won": won,
                        "kills": ps["kills"],
                        "assists": ps["assists"],
                        "deaths": ps["deaths"],
                        "adr": round(ps["damage"] / r_cnt, 1),
                        "hsPct": round(ps["hsKills"] * 100.0 / ps["kills"], 1) if ps["kills"] else 0.0,
                        "sniperKills": ps["sniperKills"],
                        "clutchKills": ps["clutchKills"],
                        "k2": ps["k2"],
                        "k3": ps["k3"],
                        "k4": ps["k4"],
                        "k5": ps["k5"],
                    }
                )

        recent_maps.sort(key=lambda x: x["sortKey"], reverse=True)
        for rm in recent_maps:
            rm.pop("sortKey", None)

        map_breakdown = []
        for bm in by_map.values():
            map_breakdown.append(
                {
                    **bm,
                    "winPct": round(bm["wins"] * 100.0 / bm["maps"], 1) if bm["maps"] else 0.0,
                    "kd": round(bm["kills"] / max(bm["deaths"], 1), 2),
                    "adr": round(bm["damage"] / bm["rounds"], 1) if bm["rounds"] else 0.0,
                    "hsPct": round(bm["hsKills"] * 100.0 / bm["kills"], 1) if bm["kills"] else 0.0,
                }
            )
        map_breakdown.sort(key=lambda x: -x["maps"])

        # 3. Skill progression from playerSkillHistories
        hist_by_skill: dict[int, list[tuple[int, int, float]]] = {}
        for h in self.data.get("playerSkillHistories", {}).get("playerSkillHistories", []):
            if h.get("playerId") == player_id:
                sid = int(h.get("skillId", 0))
                hist_by_skill.setdefault(sid, []).append((int(h.get("year", 0)), int(h.get("month", 0)), float(h.get("skillLevel", 0.0))))

        skill_progression = []
        for sk in PLAYER_SKILLS:
            cur_val = float(p.get("skills", {}).get(sk["key"], 0.0))
            pts = sorted(hist_by_skill.get(sk["id"], []))
            first_val = pts[0][2] if pts else cur_val
            skill_progression.append(
                {
                    "id": sk["id"],
                    "label": sk["label"],
                    "group": sk["group"],
                    "start": round(first_val, 2),
                    "current": round(cur_val, 2),
                    "delta": round(cur_val - first_val, 2),
                }
            )

        top_victims = [
            {"playerId": vid, "name": self.players_by_id.get(vid, {}).get("name", f"Player #{vid}"), "kills": kcnt}
            for vid, kcnt in sorted(victims.items(), key=lambda x: -x[1])[:10]
        ]

        awards = []
        for a in p.get("playerAwards", []):
            ayear = int(a.get("year", 0))
            tmpl_id = int(a.get("tournamentTemplate", -1))
            if ayear < 2000 or (tmpl_id < 0 and a.get("type") != 3):
                continue
            atype = int(a.get("type", 0))
            awards.append(
                {
                    "type": atype,
                    "typeLabel": {0: "MVP", 1: "Event Win", 2: "EVP", 3: f"Top 20 (#{a.get('top20Placement', '')})"}.get(atype, "Award"),
                    "tournamentName": tmpl_names.get(tmpl_id, f"Event #{tmpl_id}") if atype != 3 else "HLTV Yearly Top 20",
                    "teamName": self.teams_by_id.get(a.get("teamId", 0), {}).get("name", ""),
                    "year": ayear,
                    "month": int(a.get("month", 0)),
                }
            )
        awards.sort(key=lambda x: (-x["year"], -x["month"], x["type"]))

        m_tot = tot["mw"] + tot["ml"]
        return {
            "player": {
                "id": player_id,
                "name": p.get("name", ""),
                "age": p.get("age", 0),
                "nationName": NATIONS.get(p.get("nation", 0), ""),
                "teamName": self.teams_by_id[cur_tid]["name"] if cur_tid in self.teams_by_id else "Free Agent",
                "avgSkill": _player_avg_skill(p),
                "reputation": p.get("reputation", 1),
            },
            "career": {
                "rating": round(tot["accRating"] / m_tot, 3) if m_tot else 0.0,
                "matches": m_tot,
                "matchesWon": tot["mw"],
                "matchesLost": tot["ml"],
                **micro_tot,
                "kd": round(micro_tot["kills"] / max(micro_tot["deaths"], 1), 2) if micro_tot["maps"] else round(tot["kills"] / max(tot["deaths"], 1), 2),
                "adr": round(micro_tot["damage"] / micro_tot["rounds"], 1) if micro_tot["rounds"] else (round(tot["damage"] / tot["rounds"], 1) if tot["rounds"] else 0.0),
                "hsPct": round(micro_tot["hsKills"] * 100.0 / micro_tot["kills"], 1) if micro_tot["kills"] else 0.0,
            },
            "mapBreakdown": map_breakdown,
            "eventBreakdown": event_rows,
            "skillProgression": skill_progression,
            "topVictims": top_victims,
            "awards": awards,
            "recentMaps": recent_maps[:25],
        }

    def get_team_stats_detail(self, team_id: int) -> dict[str, Any]:
        """Detailed team performance, map pool, tournament history, and match history."""
        assert self.data is not None
        t = self.teams_by_id.get(team_id)
        if not t:
            raise ValueError(f"Team {team_id} not found.")
        tmpl_names, tourn_by_id, map_names = self._stats_lookups()

        map_pool: dict[int, dict[str, int]] = {
            mid: {"mapId": mid, "mapName": mname, "played": 0, "won": 0, "lost": 0, "picked": 0, "banned": 0}
            for mid, mname in map_names.items()
        }
        matches_list: list[dict[str, Any]] = []
        mw = ml = map_w = map_l = pw = pp = cw = sv = fb = 0

        for m in self.data.get("matches", {}).get("matches", []):
            t1 = int(m.get("team1Id", 0))
            t2 = int(m.get("team2Id", 0))
            if team_id not in (t1, t2):
                continue
            match_maps = [mm for mm in m.get("matchMaps", []) if mm.get("baseMatchRounds")]
            if not match_maps:
                continue
            is_t1 = team_id == t1
            opp_id = t2 if is_t1 else t1
            for mp in m.get("mapPicks", []):
                if mp.get("choiceBy") == team_id and mp.get("mapId") in map_pool:
                    if mp.get("picked"):
                        map_pool[mp["mapId"]]["picked"] += 1
                    else:
                        map_pool[mp["mapId"]]["banned"] += 1

            my_maps = 0
            opp_maps = 0
            score_strs = []
            for mm in match_maps:
                rounds = mm.get("baseMatchRounds", [])
                r_cnt = len(rounds)
                if not r_cnt:
                    continue
                t1_r = sum(1 for r in rounds if r.get("winner") == t1)
                t2_r = sum(1 for r in rounds if r.get("winner") == t2)
                my_r, opp_r = (t1_r, t2_r) if is_t1 else (t2_r, t1_r)
                won_m = my_r > opp_r
                if won_m:
                    my_maps += 1
                    map_w += 1
                else:
                    opp_maps += 1
                    map_l += 1
                mid = int(mm.get("mapId", 0))
                score_strs.append(f"{map_names.get(mid, f'Map {mid}')} {my_r}-{opp_r}")
                if mid in map_pool:
                    map_pool[mid]["played"] += 1
                    if won_m:
                        map_pool[mid]["won"] += 1
                    else:
                        map_pool[mid]["lost"] += 1
                pw += sum(1 for r in rounds if r.get("number") in (1, 13) and r.get("winner") == team_id)
                pp += sum(1 for r in rounds if r.get("number") in (1, 13))
                cw += int(mm.get("team1ClutchesWon" if is_t1 else "team2ClutchesWon", 0))
                sv += int(mm.get("team1Saves" if is_t1 else "team2Saves", 0))
                fb += int(mm.get("team1Fullbuys" if is_t1 else "team2Fullbuys", 0))

            if my_maps > opp_maps:
                mw += 1
            else:
                ml += 1

            dt_obj = m.get("datetime", {})
            matches_list.append(
                {
                    "id": m["id"],
                    "datetime": dt_obj,
                    "sortKey": self._match_date_key(dt_obj),
                    "tournamentName": tourn_by_id.get(m.get("tournamentId"), {}).get("name", ""),
                    "opponentId": opp_id,
                    "opponentName": self.teams_by_id.get(opp_id, {}).get("name", f"Team {opp_id}"),
                    "won": my_maps > opp_maps,
                    "seriesScore": f"{my_maps}-{opp_maps}",
                    "mapScores": ", ".join(score_strs),
                    "pointsDelta": m.get("team1PointsDelta" if is_t1 else "team2PointsDelta", 0),
                }
            )

        matches_list.sort(key=lambda x: x["sortKey"], reverse=True)
        for ml_item in matches_list:
            ml_item.pop("sortKey", None)

        tourn_results = []
        for rp in t.get("rankingPoints", []):
            place = int(rp.get("tournamentPlacement", 0))
            if place > 0:
                tourn_results.append(
                    {
                        "tournamentName": tmpl_names.get(rp.get("tournamentTemplate"), f"Event #{rp.get('tournamentTemplate')}"),
                        "placement": place,
                        "prizeMoney": int(rp.get("prizeMoney", 0)),
                        "points": int(rp.get("originalPoints", 0)),
                        "datetime": rp.get("dateGranted", {}),
                        "sortKey": self._match_date_key(rp.get("dateGranted", {})),
                    }
                )
        tourn_results.sort(key=lambda x: x["sortKey"], reverse=True)
        for tr in tourn_results:
            tr.pop("sortKey", None)

        map_pool_rows = [
            {
                **mp,
                "winPct": round(mp["won"] * 100.0 / mp["played"], 1) if mp["played"] else 0.0,
            }
            for mp in map_pool.values()
        ]
        map_pool_rows.sort(key=lambda x: (-x["played"], -x["winPct"]))

        return {
            "team": {
                "id": team_id,
                "name": t.get("name", ""),
                "nationName": NATIONS.get(t.get("nation", 0), ""),
                "rankingHistory": t.get("rankingHistory", []),
                "worldRank": (t.get("rankingHistory") or [0])[-1],
                "rankingPoints": sum(int(rp.get("currentPoints", 0)) for rp in t.get("rankingPoints", [])),
                "matchesWon": mw,
                "matchesLost": ml,
                "mapsWon": map_w,
                "mapsLost": map_l,
                "pistolWinPct": round(pw * 100.0 / pp, 1) if pp else 0.0,
                "clutchesWon": cw,
                "saves": sv,
                "fullbuys": fb,
                "prizeWon": sum(int(rp.get("prizeMoney", 0)) for rp in t.get("rankingPoints", [])),
            },
            "mapPool": map_pool_rows,
            "tournaments": tourn_results[:30],
            "recentMatches": matches_list[:35],
        }

    def get_match_stats_detail(self, match_id: int) -> dict[str, Any]:
        """Return full veto and map-by-map 10-player scoreboards for a played match."""
        assert self.data is not None
        m = next((x for x in self.data.get("matches", {}).get("matches", []) if x.get("id") == match_id), None)
        if not m:
            raise ValueError(f"Match {match_id} not found.")
        _, tourn_by_id, map_names = self._stats_lookups()

        t1 = int(m.get("team1Id", 0))
        t2 = int(m.get("team2Id", 0))
        t1_name = self.teams_by_id.get(t1, {}).get("name", f"Team {t1}")
        t2_name = self.teams_by_id.get(t2, {}).get("name", f"Team {t2}")
        t1_pids = set(m.get("team1PlayerIds", []))
        t2_pids = set(m.get("team2PlayerIds", []))

        veto = [
            {
                "order": mp.get("order", 0),
                "mapName": map_names.get(mp.get("mapId"), f"Map {mp.get('mapId')}"),
                "picked": bool(mp.get("picked")),
                "by": self.teams_by_id.get(mp.get("choiceBy", 0), {}).get("name", "Decider") if mp.get("choiceBy") else "Decider",
            }
            for mp in sorted(m.get("mapPicks", []), key=lambda x: x.get("order", 0))
        ]

        maps_out = []
        t1_maps = t2_maps = 0
        for mm in m.get("matchMaps", []):
            rounds = mm.get("baseMatchRounds", [])
            r_cnt = len(rounds)
            if r_cnt == 0:
                continue
            t1_r = sum(1 for r in rounds if r.get("winner") == t1)
            t2_r = sum(1 for r in rounds if r.get("winner") == t2)
            if t1_r > t2_r:
                t1_maps += 1
            else:
                t2_maps += 1

            t1_rows = []
            t2_rows = []
            for ps_raw in mm.get("playerStats", []):
                ps = self._parse_map_player_stat(ps_raw)
                pid = ps["playerId"]
                row = {
                    **ps,
                    "name": self.players_by_id.get(pid, {}).get("name", f"Player #{pid}"),
                    "kd": round(ps["kills"] / max(ps["deaths"], 1), 2),
                    "adr": round(ps["damage"] / r_cnt, 1),
                    "hsPct": round(ps["hsKills"] * 100.0 / ps["kills"], 1) if ps["kills"] else 0.0,
                }
                if pid in t1_pids:
                    t1_rows.append(row)
                else:
                    t2_rows.append(row)
            t1_rows.sort(key=lambda r: (-r["kills"], r["deaths"]))
            t2_rows.sort(key=lambda r: (-r["kills"], r["deaths"]))

            maps_out.append(
                {
                    "mapName": map_names.get(mm.get("mapId"), f"Map {mm.get('mapId')}"),
                    "rounds": r_cnt,
                    "team1Score": t1_r,
                    "team2Score": t2_r,
                    "team1ClutchesWon": mm.get("team1ClutchesWon", 0),
                    "team2ClutchesWon": mm.get("team2ClutchesWon", 0),
                    "team1Players": t1_rows,
                    "team2Players": t2_rows,
                }
            )

        return {
            "id": match_id,
            "datetime": m.get("datetime", {}),
            "tournamentName": tourn_by_id.get(m.get("tournamentId"), {}).get("name", f"Tournament #{m.get('tournamentId')}"),
            "team1Name": t1_name,
            "team2Name": t2_name,
            "team1Maps": t1_maps,
            "team2Maps": t2_maps,
            "team1RankBefore": m.get("team1RankBefore", 0),
            "team2RankBefore": m.get("team2RankBefore", 0),
            "team1PointsDelta": m.get("team1PointsDelta", 0),
            "team2PointsDelta": m.get("team2PointsDelta", 0),
            "veto": veto,
            "maps": maps_out,
        }

    # ---------------------------------------------------------------------
    # Event Stats & Fair Score vs Real Game MVP/EVP Scoring
    # ---------------------------------------------------------------------

    @staticmethod
    def _awards_for_reputation(reputation: int) -> dict[str, Any]:
        """Return exact engine MVP/EVP/HM slot counts and tier label for tournament reputation."""
        r = max(1, min(20, int(reputation or 1)))
        mvp = 1 if r >= 13 else 0
        if r == 20:
            evp = 7
        elif r == 19:
            evp = 6
        elif r >= 17:
            evp = 5
        elif r >= 14:
            evp = 4
        elif r >= 11:
            evp = 3
        elif r >= 9:
            evp = 2
        elif r == 8:
            evp = 1
        else:
            evp = 0

        if r >= 13:
            hm = 0
        elif r >= 11:
            hm = 2
        elif r >= 9:
            hm = 3
        elif r == 8:
            hm = 4
        else:
            hm = 5

        if r >= 19:
            tier_lbl = "Major (Tier 5)"
        elif r >= 13:
            tier_lbl = "S-Tier (Tier 4)"
        elif r >= 9:
            tier_lbl = "A-Tier (Tier 3)"
        elif r >= 5:
            tier_lbl = "B-Tier (Tier 2)"
        else:
            tier_lbl = "C-Tier (Tier 1)"

        return {
            "reputation": r,
            "tierLabel": tier_lbl,
            "mvp": mvp,
            "evp": evp,
            "hm": hm,
            "total": mvp + evp + hm,
        }

    @staticmethod
    def _match_winner_loser(m: dict[str, Any]) -> tuple[int, int]:
        t1 = int(m.get("team1Id", 0) or 0)
        t2 = int(m.get("team2Id", 0) or 0)
        s1 = s2 = 0
        for mm in m.get("matchMaps", []):
            r1 = sum(1 for r in mm.get("baseMatchRounds", []) if r.get("winner") == t1)
            r2 = sum(1 for r in mm.get("baseMatchRounds", []) if r.get("winner") == t2)
            if r1 > r2:
                s1 += 1
            elif r2 > r1:
                s2 += 1
        return (t1, t2) if s1 >= s2 else (t2, t1)

    def _compute_event_placements(
        self,
        tid: int,
        champions_by_tid: dict[int, int],
        stages_by_tid: dict[int, list[dict[str, Any]]],
        matches_by_stage: dict[int, list[dict[str, Any]]],
    ) -> dict[str, Any]:
        """Resolve tournament placements, final stage ID, and decompiled Game Score multipliers."""
        placements: dict[int, str] = {}
        final_stage_teams: set[int] = set()
        final_stage_id = 0

        if tid in champions_by_tid:
            placements[champions_by_tid[tid]] = "1st"

        cand = [
            s
            for s in stages_by_tid.get(tid, [])
            if "QUALIFIER" not in (s.get("name") or "").upper() and matches_by_stage.get(int(s.get("id", 0) or 0))
        ]
        if not cand:
            cand = [s for s in stages_by_tid.get(tid, []) if matches_by_stage.get(int(s.get("id", 0) or 0))]

        all_event_teams: set[int] = set()
        for s in cand:
            for m in matches_by_stage.get(int(s.get("id", 0) or 0), []):
                if m.get("team1Id"):
                    all_event_teams.add(int(m["team1Id"]))
                if m.get("team2Id"):
                    all_event_teams.add(int(m["team2Id"]))

        if cand:
            final_stage = max(cand, key=lambda s: (int(s.get("stage", 0) or 0), int(s.get("id", 0) or 0)))
            final_stage_id = int(final_stage.get("id", 0) or 0)
            ms = matches_by_stage.get(final_stage_id, [])
            for m in ms:
                if m.get("team1Id"):
                    final_stage_teams.add(int(m["team1Id"]))
                if m.get("team2Id"):
                    final_stage_teams.add(int(m["team2Id"]))
            for p_entry in final_stage.get("participants", []) or []:
                pt = int(p_entry.get("teamId", 0) or 0) if isinstance(p_entry, dict) else int(p_entry or 0)
                if pt:
                    final_stage_teams.add(pt)

            is_playoff = "PLAYOFF" in (final_stage.get("name") or "").upper() or int(final_stage.get("formatType", -1)) == 0
            if is_playoff and ms:
                upper = [m for m in ms if not m.get("lowerBracket")]
                if upper:
                    max_r = max(int(m.get("round", 0) or 0) for m in upper)
                    finals = [m for m in upper if int(m.get("round", 0) or 0) == max_r]
                    if len(finals) == 1:
                        w, l = self._match_winner_loser(finals[0])
                        placements.setdefault(w, "1st")
                        placements.setdefault(l, "2nd")
                        for m in upper:
                            r = int(m.get("round", 0) or 0)
                            mw_t, ml_t = self._match_winner_loser(m)
                            if r == max_r - 1:
                                placements.setdefault(ml_t, "3rd-4th")
                            elif r == max_r - 2:
                                placements.setdefault(ml_t, "5th-8th")
                    for ftid in final_stage_teams:
                        placements.setdefault(ftid, "5th-8th" if len(final_stage_teams) <= 8 else "Final Stage")
            else:
                # League / Swiss final stage: rank by final stage W-L to infer Top 8 cutoff
                wl_rec: dict[int, list[int]] = {}
                for m in ms:
                    mw_t, ml_t = self._match_winner_loser(m)
                    wl_rec.setdefault(mw_t, [0, 0])[0] += 1
                    wl_rec.setdefault(ml_t, [0, 0])[1] += 1
                ranked_fs = sorted(wl_rec.items(), key=lambda kv: (-kv[1][0], kv[1][1], kv[0]))
                for idx, (rtid, _) in enumerate(ranked_fs, start=1):
                    if idx == 1:
                        placements.setdefault(rtid, "1st")
                    elif idx == 2:
                        placements.setdefault(rtid, "2nd")
                    elif idx <= 4:
                        placements.setdefault(rtid, "3rd-4th")
                    elif idx <= 8:
                        placements.setdefault(rtid, "5th-8th")

        # Determine exact Top 8 teams (for Tournament.GetFinalTotalPositionOfTeam <= 8 game award eligibility)
        top8_teams: set[int] = {tid_k for tid_k, lbl in placements.items() if lbl in ("1st", "2nd", "3rd-4th", "5th-8th")}
        if len(top8_teams) < 8 and all_event_teams:
            # Fill remaining top-8 spots by overall event match wins when brackets aren't full 8-team playoffs
            ev_wl: dict[int, list[int]] = {x: [0, 0] for x in all_event_teams}
            for s in cand:
                for m in matches_by_stage.get(int(s.get("id", 0) or 0), []):
                    mw_t, ml_t = self._match_winner_loser(m)
                    if mw_t in ev_wl:
                        ev_wl[mw_t][0] += 1
                    if ml_t in ev_wl:
                        ev_wl[ml_t][1] += 1
            for rtid, _ in sorted(ev_wl.items(), key=lambda kv: (-kv[1][0], kv[1][1], kv[0])):
                if len(top8_teams) >= 8:
                    break
                top8_teams.add(rtid)

        # Decompiled Tournament.CalculateAndGetAwardsList multipliers:
        # Must finish Top 8; 1st -> 1.2x, 2nd -> 1.1x, Final Stage -> 1.0x, Non-Final Top 8 -> 0.9x, 9th+ -> Ineligible (0.0x)
        game_mults: dict[int, float] = {}
        for xtid in all_event_teams | set(placements.keys()):
            if xtid not in top8_teams:
                game_mults[xtid] = 0.0
                continue
            lbl = placements.get(xtid, "5th-8th")
            if lbl == "1st":
                game_mults[xtid] = 1.20
            elif lbl == "2nd":
                game_mults[xtid] = 1.10
            elif xtid in final_stage_teams:
                game_mults[xtid] = 1.00
            else:
                game_mults[xtid] = 0.90

        return {
            "placements": placements,
            "finalStageId": final_stage_id,
            "finalStageTeams": final_stage_teams,
            "top8Teams": top8_teams,
            "gameMults": game_mults,
            "stageIds": [int(s.get("id", 0) or 0) for s in cand],
        }

    def get_event_stats(self, tournament_id: int | None = None) -> dict[str, Any]:
        """Compute per-event player ratings, Real Game MVP/EVP scores, and Fair Scoring comparison."""
        if self.data is None:
            return {"loaded": False}

        tmpl_names, _, _ = self._stats_lookups()
        tournaments = self.data.get("tournaments", {}).get("tournaments", [])
        stages = self.data.get("tournamentStages", {}).get("tournamentStages", [])
        pcs = self.data.get("playerCareerStats", {}).get("playerCareerStats", [])
        matches = self.data.get("matches", {}).get("matches", [])

        champions_by_tid: dict[int, int] = {}
        for tid_k, t_obj in self.teams_by_id.items():
            for th in t_obj.get("trophyHistories", []):
                ch_tid = int(th.get("tournamentId", 0) or 0)
                if ch_tid:
                    champions_by_tid[ch_tid] = int(tid_k)

        stage_by_id: dict[int, dict[str, Any]] = {}
        stages_by_tid: dict[int, list[dict[str, Any]]] = {}
        t_end: dict[int, tuple[int, int, int]] = {}
        t_start: dict[int, tuple[int, int, int]] = {}
        for s in stages:
            sid = int(s.get("id", 0) or 0)
            pid = int(s.get("parentId", 0) or 0)
            stage_by_id[sid] = s
            stages_by_tid.setdefault(pid, []).append(s)
            for key, store in (("endDatetime", t_end), ("startDatetime", t_start)):
                dt = s.get(key) or {}
                y, mo, da = int(dt.get("year", 0) or 0), int(dt.get("month", 0) or 0), int(dt.get("day", 0) or 0)
                if pid and y > 10:
                    prev = store.get(pid)
                    if prev is None or (key == "endDatetime" and (y, mo, da) > prev) or (key == "startDatetime" and (y, mo, da) < prev):
                        store[pid] = (y, mo, da)

        matches_by_stage: dict[int, list[dict[str, Any]]] = {}
        t_months: dict[int, set[tuple[int, int]]] = {}
        t_match_counts: dict[int, int] = {}
        for m in matches:
            if not m.get("processingCompleted") and not m.get("matchMaps"):
                continue
            sid = int(m.get("tournamentId", 0) or 0)
            matches_by_stage.setdefault(sid, []).append(m)
            st = stage_by_id.get(sid)
            if st:
                tid = int(st.get("parentId", 0) or 0)
                if tid:
                    t_match_counts[tid] = t_match_counts.get(tid, 0) + 1
                    if "QUALIFIER" not in (st.get("name") or "").upper():
                        dt = m.get("datetime", {})
                        y, mo = int(dt.get("year", 0) or 0), int(dt.get("month", 0) or 0)
                        if y > 10:
                            t_months.setdefault(tid, set()).add((y, mo))

        tourn_by_id = {int(t.get("id", 0) or 0): t for t in tournaments}
        events_list: list[dict[str, Any]] = []
        for t in tournaments:
            tid = int(t.get("id", 0) or 0)
            mc = t_match_counts.get(tid, 0)
            pa = [int(x or 0) for x in (t.get("playersAwarded") or []) if int(x or 0) > 0]
            champ_id = champions_by_tid.get(tid, 0)
            if mc == 0 and not pa and not champ_id:
                continue
            end_dt = t_end.get(tid) or t_start.get(tid)
            months = set(t_months.get(tid, set()))
            if end_dt:
                months.add((end_dt[0], end_dt[1]))
            yy, mm = (end_dt[0], end_dt[1]) if end_dt else (max(months) if months else (0, 0))
            rep = int(t.get("reputation", 1) or 1)
            slots = self._awards_for_reputation(rep)
            events_list.append(
                {
                    "id": tid,
                    "name": t.get("name") or tmpl_names.get(t.get("template"), f"Tournament #{tid}"),
                    "template": int(t.get("template", 0) or 0),
                    "reputation": rep,
                    "tierLabel": slots["tierLabel"],
                    "year": yy,
                    "month": mm,
                    "date": f"{yy}-{mm:02d}" if yy else "-",
                    "sortKey": (end_dt or (yy, mm, 0), rep, tid),
                    "matchCount": mc,
                    "championTeamId": champ_id,
                    "championName": self.teams_by_id.get(champ_id, {}).get("name", "—") if champ_id else "—",
                    "awardsCount": len(pa),
                    "hasRecordedAwards": len(pa) > 0,
                }
            )

        events_list.sort(key=lambda e: (-e["sortKey"][0][0], -e["sortKey"][0][1], -e["sortKey"][0][2], -e["reputation"], -e["id"]))
        for ev in events_list:
            ev.pop("sortKey", None)

        if not events_list:
            return {"loaded": True, "events": [], "event": None, "players": []}

        sel_id = int(tournament_id) if tournament_id is not None else 0
        if sel_id not in {e["id"] for e in events_list}:
            # Default to latest event with recorded awards, or newest played event
            with_aw = [e for e in events_list if e["hasRecordedAwards"]]
            sel_id = with_aw[0]["id"] if with_aw else events_list[0]["id"]

        t_sel = tourn_by_id[sel_id]
        tpl_sel = int(t_sel.get("template", 0) or 0)
        rep_sel = int(t_sel.get("reputation", 1) or 1)
        slots = self._awards_for_reputation(rep_sel)
        pl_info = self._compute_event_placements(sel_id, champions_by_tid, stages_by_tid, matches_by_stage)

        # Aggregate match-level and map-level performance strictly for this event's stages
        event_ms: list[dict[str, Any]] = []
        for sid in pl_info["stageIds"]:
            event_ms.extend(matches_by_stage.get(sid, []))

        p_map: dict[int, dict[str, Any]] = {}
        event_months: set[tuple[int, int]] = set(t_months.get(sel_id, set()))
        if sel_id in t_end:
            event_months.add((t_end[sel_id][0], t_end[sel_id][1]))
        elif sel_id in t_start:
            event_months.add((t_start[sel_id][0], t_start[sel_id][1]))

        final_stage_id = pl_info["finalStageId"]
        for m in event_ms:
            dt = m.get("datetime") or {}
            if int(dt.get("year", 0) or 0) > 10:
                event_months.add((int(dt["year"]), int(dt["month"])))
            is_po = int(m.get("tournamentId", 0) or 0) == final_stage_id
            t1 = int(m.get("team1Id", 0) or 0)
            t2 = int(m.get("team2Id", 0) or 0)
            r1 = int(m.get("team1RankBefore", 0) or 0) or 25
            r2 = int(m.get("team2RankBefore", 0) or 0) or 25
            t1_pids = {int(x or 0) for x in (m.get("team1PlayerIds") or []) if int(x or 0) > 0}
            t2_pids = {int(x or 0) for x in (m.get("team2PlayerIds") or []) if int(x or 0) > 0}
            mw_tid, _ = self._match_winner_loser(m)

            for pid in t1_pids | t2_pids:
                agg = p_map.setdefault(
                    pid,
                    {
                        "teamId": t1 if pid in t1_pids else t2,
                        "matches": 0,
                        "wins": 0,
                        "losses": 0,
                        "maps": 0,
                        "poMaps": 0,
                        "rounds": 0,
                        "kills": 0,
                        "assists": 0,
                        "deaths": 0,
                        "damage": 0,
                        "hsKills": 0,
                        "openingKills": 0,
                        "openingDeaths": 0,
                        "sniperKills": 0,
                        "clutchKills": 0,
                        "oppRanks": [],
                    },
                )
                agg["teamId"] = t1 if pid in t1_pids else t2
                agg["matches"] += 1
                won_m = (pid in t1_pids and mw_tid == t1) or (pid in t2_pids and mw_tid == t2)
                agg["wins" if won_m else "losses"] += 1
                agg["oppRanks"].append(r2 if pid in t1_pids else r1)

            for mm in m.get("matchMaps", []):
                rc = len(mm.get("baseMatchRounds") or [])
                for ps_raw in mm.get("playerStats", []):
                    ps = self._parse_map_player_stat(ps_raw)
                    pid = ps["playerId"]
                    if not pid:
                        continue
                    inferred_tid = t1 if pid in t1_pids else (t2 if pid in t2_pids else 0)
                    agg = p_map.setdefault(
                        pid,
                        {
                            "teamId": inferred_tid,
                            "matches": 0,
                            "wins": 0,
                            "losses": 0,
                            "maps": 0,
                            "poMaps": 0,
                            "rounds": 0,
                            "kills": 0,
                            "assists": 0,
                            "deaths": 0,
                            "damage": 0,
                            "hsKills": 0,
                            "openingKills": 0,
                            "openingDeaths": 0,
                            "sniperKills": 0,
                            "clutchKills": 0,
                            "oppRanks": [],
                        },
                    )
                    if not agg["teamId"] and inferred_tid:
                        agg["teamId"] = inferred_tid
                    agg["maps"] += 1
                    if is_po:
                        agg["poMaps"] += 1
                    agg["rounds"] += rc
                    for sk in ("kills", "assists", "deaths", "damage", "hsKills", "openingKills", "openingDeaths", "sniperKills", "clutchKills"):
                        agg[sk] += ps[sk]

        # Match exact saved playerCareerStats for rating (filter by template + event months + event participants if known)
        event_teams = {agg["teamId"] for agg in p_map.values() if agg["teamId"]} | set(pl_info["placements"].keys())
        pcs_by_pid: dict[int, dict[str, Any]] = {}
        for row in pcs:
            if int(row.get("tournamentTemplate", -1)) != tpl_sel:
                continue
            ym = (int(row.get("year", 0) or 0), int(row.get("month", 0) or 0))
            if event_months and ym not in event_months:
                continue
            mw = int(row.get("matchesWon", 0) or 0)
            ml = int(row.get("matchesLost", 0) or 0)
            if mw + ml == 0:
                continue
            pid = int(row.get("playerId", 0) or 0)
            rtid = int(row.get("teamId", 0) or 0)
            if p_map and pid not in p_map and rtid not in event_teams:
                continue
            cur = pcs_by_pid.setdefault(
                pid,
                {"m": 0, "mw": 0, "ml": 0, "acc": 0.0, "rp": 0, "k": 0, "a": 0, "d": 0, "dmg": 0, "ok": 0, "od": 0, "tid": 0},
            )
            cur["m"] += mw + ml
            cur["mw"] += mw
            cur["ml"] += ml
            cur["acc"] += float(row.get("accumulativeRating", 0.0) or 0.0)
            cur["rp"] += int(row.get("roundsPlayed", 0) or 0)
            cur["k"] += int(row.get("accumulatedKills", 0) or 0)
            cur["a"] += int(row.get("accumulatedAssists", 0) or 0)
            cur["d"] += int(row.get("accumulateDeaths", 0) or 0)
            cur["dmg"] += int(row.get("accumulatedDamage", 0) or 0)
            cur["ok"] += int(row.get("accumulatedOpeningKills", 0) or 0)
            cur["od"] += int(row.get("accumulatedOpeningDeaths", 0) or 0)
            if rtid:
                cur["tid"] = rtid

        all_pids = set(p_map.keys()) | set(pcs_by_pid.keys())
        if not all_pids:
            sel_meta = next((e for e in events_list if e["id"] == sel_id), None)
            return {"loaded": True, "events": events_list, "event": sel_meta, "players": []}

        # Recorded awards on tournament object
        pa_raw = [int(x or 0) for x in (t_sel.get("playersAwarded") or []) if int(x or 0) > 0]
        recorded_role_by_pid: dict[int, str] = {}
        for idx, apid in enumerate(pa_raw):
            if idx < slots["mvp"]:
                recorded_role_by_pid[apid] = "MVP"
            elif idx < slots["mvp"] + slots["evp"]:
                recorded_role_by_pid[apid] = "EVP"
            else:
                recorded_role_by_pid[apid] = "HM"

        # Determine event max matches & max playoff maps for sample stabilization & deep-run scaling
        sample_counts = [
            pcs_by_pid[p]["m"] if p in pcs_by_pid else max(1, p_map.get(p, {}).get("matches", 0))
            for p in all_pids
        ]
        max_m = max(sample_counts, default=1)
        k_prior = max(1.5, max_m * 0.25)
        max_po_maps = max((p_map.get(p, {}).get("poMaps", 0) for p in all_pids), default=0)

        fair_place_bonus_map = {
            "1st": 0.055,
            "2nd": 0.030,
            "3rd-4th": 0.010,
            "5th-8th": -0.015,
        }

        players_out: list[dict[str, Any]] = []
        for pid in all_pids:
            mp = p_map.get(pid, {})
            pc = pcs_by_pid.get(pid, {})
            m_cnt = pc["m"] if pc else mp.get("matches", 0)
            if m_cnt == 0 and mp.get("maps", 0) == 0:
                continue
            m_eff = max(1, m_cnt)

            rp = mp.get("rounds", 0) or pc.get("rp", 0)
            kills = mp.get("kills", 0) or pc.get("k", 0)
            deaths = mp.get("deaths", 0) or pc.get("d", 0)
            assists = mp.get("assists", 0) or pc.get("a", 0)
            damage = mp.get("damage", 0) or pc.get("dmg", 0)
            ok = mp.get("openingKills", 0) or pc.get("ok", 0)
            od = mp.get("openingDeaths", 0) or pc.get("od", 0)
            maps_cnt = mp.get("maps", 0) or m_cnt
            po_maps = mp.get("poMaps", 0)
            wins = mp.get("wins", 0) if mp else pc.get("mw", 0)
            losses = mp.get("losses", 0) if mp else pc.get("ml", 0)
            tid = mp.get("teamId", 0) or pc.get("tid", 0)

            rp_safe = max(rp, 1)
            kpr = kills / rp_safe
            dpr = deaths / rp_safe
            adr = damage / rp_safe
            kd = kills / max(deaths, 1)
            hs_pct = (mp.get("hsKills", 0) * 100.0 / kills) if (mp and kills > 0) else 0.0

            if pc and pc["m"] > 0:
                rating = pc["acc"] / pc["m"]
                rating_src = "save"
            else:
                # Transparent HLTV-style fallback rating when event has no finished PCS row yet
                impact = 2.13 * kpr + 0.42 * (assists / rp_safe) - 0.41
                surv = max(0.0, 1.0 - dpr)
                rating = max(0.35, 0.0073 * (surv * 100.0) + 0.3591 * kpr - 0.5329 * dpr + 0.2372 * impact + 0.0032 * adr + 0.1587)
                rating_src = "estimated"

            pl_lbl = pl_info["placements"].get(tid, "9th+" if tid not in pl_info["top8Teams"] else "5th-8th")
            g_mult = pl_info["gameMults"].get(tid, 0.0)
            game_eligible = g_mult > 0.0
            game_score = rating * g_mult if game_eligible else 0.0

            # Fair Score components
            bayes_rating = (rating * m_eff + 1.00 * k_prior) / (m_eff + k_prior)
            place_bonus = fair_place_bonus_map.get(pl_lbl, -0.055)
            opp_ranks = mp.get("oppRanks", []) if mp else []
            avg_opp = (sum(opp_ranks) / len(opp_ranks)) if opp_ranks else 15.0
            opp_bonus = max(-0.040, min(0.040, (15.0 - avg_opp) * 0.004)) if opp_ranks else 0.0
            po_bonus = (0.045 * (po_maps / max_po_maps)) if (max_po_maps > 0 and po_maps > 0) else 0.0
            fair_score = bayes_rating + place_bonus + opp_bonus + po_bonus

            p_obj = self.players_by_id.get(pid, {})
            t_obj = self.teams_by_id.get(tid, {})
            players_out.append(
                {
                    "playerId": pid,
                    "playerName": p_obj.get("name", f"Player #{pid}"),
                    "teamId": tid,
                    "teamName": t_obj.get("name", f"Team #{tid}" if tid else "—"),
                    "placement": pl_lbl,
                    "matches": m_cnt,
                    "wins": wins,
                    "losses": losses,
                    "maps": maps_cnt,
                    "poMaps": po_maps,
                    "rounds": rp,
                    "kills": kills,
                    "deaths": deaths,
                    "assists": assists,
                    "kd": round(kd, 2),
                    "kpr": round(kpr, 2),
                    "adr": round(adr, 1),
                    "hsPct": round(hs_pct, 1),
                    "openingDiff": ok - od,
                    "sniperKills": mp.get("sniperKills", 0) if mp else 0,
                    "clutchKills": mp.get("clutchKills", 0) if mp else 0,
                    "avgOppRank": round(avg_opp, 1) if opp_ranks else None,
                    "rating": round(rating, 3),
                    "ratingSource": rating_src,
                    "gameMult": round(g_mult, 2),
                    "gameEligible": game_eligible,
                    "gameScore": round(game_score, 3),
                    "fairScore": round(fair_score, 3),
                    "bayesRating": round(bayes_rating, 3),
                    "fairPlaceBonus": round(place_bonus, 3),
                    "fairOppBonus": round(opp_bonus, 3),
                    "fairPoBonus": round(po_bonus, 3),
                    "actualAward": recorded_role_by_pid.get(pid, ""),
                    "gameRank": None,
                    "fairRank": 0,
                    "rankDelta": None,
                    "gameProjectedAward": "",
                    "fairProjectedAward": "",
                }
            )

        # Rank by Game Score (eligible Top-8 teams first)
        eligible_rows = sorted(
            [r for r in players_out if r["gameEligible"]],
            key=lambda r: (-r["gameScore"], -r["rating"], r["playerId"]),
        )
        for idx, row in enumerate(eligible_rows, start=1):
            row["gameRank"] = idx
            if idx <= slots["mvp"]:
                row["gameProjectedAward"] = "MVP"
            elif idx <= slots["mvp"] + slots["evp"]:
                row["gameProjectedAward"] = "EVP"
            elif idx <= slots["total"]:
                row["gameProjectedAward"] = "HM"

        # Rank all players by Fair Score; lock MVP slot(s) to Grand Finalists (1st or 2nd) when present
        fair_rows = sorted(players_out, key=lambda r: (-r["fairScore"], -r["rating"], r["playerId"]))
        gf_candidates = [r for r in fair_rows if r["placement"] in ("1st", "2nd")]
        mvp_pool = gf_candidates if gf_candidates else fair_rows
        fair_mvp_ids = {r["playerId"] for r in mvp_pool[: slots["mvp"]]}
        rem_evp = slots["evp"]
        rem_hm = slots["hm"]
        for idx, row in enumerate(fair_rows, start=1):
            row["fairRank"] = idx
            if row["playerId"] in fair_mvp_ids:
                row["fairProjectedAward"] = "MVP"
            elif rem_evp > 0:
                row["fairProjectedAward"] = "EVP"
                rem_evp -= 1
            elif rem_hm > 0:
                row["fairProjectedAward"] = "HM"
                rem_hm -= 1
            if row["gameRank"] is not None:
                row["rankDelta"] = row["gameRank"] - row["fairRank"]

        sel_meta = next((e for e in events_list if e["id"] == sel_id), {})
        game_mvp_row = next((r for r in eligible_rows if r["gameProjectedAward"] == "MVP"), None)
        fair_mvp_row = next((r for r in fair_rows if r["fairProjectedAward"] == "MVP"), None)
        rec_mvp_pid = pa_raw[0] if (pa_raw and slots["mvp"] > 0) else 0
        rec_mvp_row = next((r for r in players_out if r["playerId"] == rec_mvp_pid), None)

        snubs = [r for r in fair_rows[: max(10, slots["total"] + 4)] if (r["rankDelta"] or 0) > 0 or not r["gameEligible"]]
        biggest_snub = max(snubs, key=lambda r: (r["rankDelta"] if r["rankDelta"] is not None else 99, r["rating"]), default=None)
        overrated = [r for r in eligible_rows[: max(10, slots["total"] + 4)] if (r["rankDelta"] or 0) < 0]
        biggest_over = min(overrated, key=lambda r: (r["rankDelta"] or 0, r["rating"]), default=None)

        runner_up_tid = next((tk for tk, lbl in pl_info["placements"].items() if lbl == "2nd"), 0)
        event_detail = {
            **sel_meta,
            "runnerUpName": self.teams_by_id.get(runner_up_tid, {}).get("name", "—") if runner_up_tid else "—",
            "awardSlots": slots,
            "matchCount": len(event_ms),
            "playerCount": len(players_out),
            "kPrior": round(k_prior, 2),
            "recordedMvp": (
                {"playerId": rec_mvp_row["playerId"], "playerName": rec_mvp_row["playerName"], "rating": rec_mvp_row["rating"], "placement": rec_mvp_row["placement"]}
                if rec_mvp_row
                else None
            ),
            "gameMvp": (
                {"playerId": game_mvp_row["playerId"], "playerName": game_mvp_row["playerName"], "rating": game_mvp_row["rating"], "score": game_mvp_row["gameScore"], "placement": game_mvp_row["placement"]}
                if game_mvp_row
                else None
            ),
            "fairMvp": (
                {"playerId": fair_mvp_row["playerId"], "playerName": fair_mvp_row["playerName"], "rating": fair_mvp_row["rating"], "score": fair_mvp_row["fairScore"], "placement": fair_mvp_row["placement"]}
                if fair_mvp_row
                else None
            ),
            "biggestSnub": (
                {"playerId": biggest_snub["playerId"], "playerName": biggest_snub["playerName"], "rating": biggest_snub["rating"], "fairRank": biggest_snub["fairRank"], "gameRank": biggest_snub["gameRank"], "placement": biggest_snub["placement"]}
                if biggest_snub
                else None
            ),
            "biggestOverreward": (
                {"playerId": biggest_over["playerId"], "playerName": biggest_over["playerName"], "rating": biggest_over["rating"], "fairRank": biggest_over["fairRank"], "gameRank": biggest_over["gameRank"], "placement": biggest_over["placement"]}
                if biggest_over
                else None
            ),
        }

        return {
            "loaded": True,
            "events": events_list,
            "event": event_detail,
            "players": fair_rows,
        }

    # ---------------------------------------------------------------------
    # Bug Showcase Analytics
    # ---------------------------------------------------------------------

    def get_bug_showcase(self) -> dict[str, Any]:
        """Analyze blowout rates vs CS2 pro baselines, undeserved MVPs/EVPs, and irrational AI transfers."""
        if not self.data:
            raise ValueError("No save loaded.")

        blowouts = self._showcase_blowouts()
        awards = self._showcase_awards()
        transfers = self._showcase_transfers()
        stability = self._showcase_stability()
        findings = self._showcase_findings(blowouts, awards, transfers, stability)

        return {
            "loaded": True,
            "blowouts": blowouts,
            "awards": awards,
            "transfers": transfers,
            "stability": stability,
            "findings": findings,
        }

    def _showcase_findings(
        self,
        blowouts: dict[str, Any],
        awards: dict[str, Any],
        transfers: dict[str, Any],
        stability: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Assemble unified decompiled-engine + empirical-save root causes dossier."""
        b = blowouts
        a = awards
        t = transfers
        s = stability
        return [
            {
                "category": "Match & Round Simulation (Blowouts & Snowballs)",
                "tag": "Combat / Economy / Odds",
                "items": [
                    {
                        "id": "combat-helmet",
                        "severity": "critical",
                        "title": "1. Broken Helmet Damage Overwrite",
                        "symbol": "Weapon::CalculateDamage (Assembly-CSharp.dll)",
                        "liveImpact": f"{b.get('shutouts13_0', 0)} shutout 13-0 maps ({b.get('shutoutPct', 0)}%, {b.get('shutoutMultiplier', 0)}x pro avg) & {b.get('halves12_0', 0)} 12-0 halves.",
                        "rootCause": "When a target has a helmet, damage is overwritten directly with `damage * armorMultiplier` — wiping out the headshot multiplier and distance dropoff. Armored winners take ~27 dmg from an AK headshot while unhelmeted broke defenders take ~144.",
                        "devFix": "Apply `damage *= armorMultiplier` *after* headshot and range multipliers while keeping helmet penetration realistic instead of resetting the base scalar.",
                    },
                    {
                        "id": "post-plant-copypaste",
                        "severity": "critical",
                        "title": "2. Post-Plant Retake Probability Copy-Paste Bug",
                        "symbol": "SimulationManager::CheckForRoundOverAndPostPlantInitiation",
                        "liveImpact": f"Even-odds T-side rounds win {b.get('closeTWinPct', 0)}% (Pistol R1: {b.get('closeR1TWinPct', 0)}%).",
                        "rootCause": "Stage 5 computes `atkStrength` into a local variable and never references it — BOTH numerator and denominator use `(1 + defStrength)` so defender strength cancels out completely. T-side always gets >=50% (often 61%+) post-plant odds even in 1v5 retakes.",
                        "devFix": "Use `atkStrength / (atkStrength + defStrength)` weighted by alive player counts and remaining bomb timer instead of cancelling `defStrength`.",
                    },
                    {
                        "id": "inverted-armor-reserve",
                        "severity": "high",
                        "title": "3. Inverted Armor Reserve Budget",
                        "symbol": "MatchPurchaseFunctions::SetPlayerPurchaseBudget",
                        "liveImpact": f"Round-2+ streak win rate snowballs across {b.get('blowoutsLe3', 0)} 13-<=3 blowouts ({b.get('blowoutLe3Pct', 0)}%).",
                        "rootCause": "Reserves $650 using `hasArmor ? 650 : 0` — subtracting $650 from players who *already have* armor instead of unarmored eco/force players, starving losing defenders of full rifles and utility.",
                        "devFix": "Invert condition to `!hasArmor ? 650 : 0` (and reserve $350 for helmet upgrade when kevlar < 100%).",
                    },
                    {
                        "id": "force-buy-loop",
                        "severity": "high",
                        "title": "4. Chaotic Force-Buy Loop & Missing $800 Plant Bonus",
                        "symbol": "BaseMatchTeam::SetPurchaseStrategy & ApplyRoundMoney",
                        "liveImpact": f"{b.get('top20_13_0', 0)} Top-20 vs Top-20 13-0s; {b.get('upset_13_0', 0)} underdog 13-0s.",
                        "rootCause": "A team `Save` decision randomly flips to `FullSpend` on `Random.value <= forceBuy * 0.6f`, trapping losing squads on SMG/Deagle half-buys every round, compounded by omitting the CS2 +$800 T bomb-plant team loss bonus.",
                        "devFix": "Enforce team-wide synchronized eco/full-buy coordination based on projected next-round loss bonus and award +$800 per planted T bomb loss.",
                    },
                    {
                        "id": "skill-pow-28",
                        "severity": "warn",
                        "title": "5. Pre-Match `skill^2.8` Snowball Across BO3/BO5",
                        "symbol": "MiscFunctions::GetOddsOfWinning & Team::GetTotalMapComfort",
                        "liveImpact": "Even +1.2 skill gaps produce 76-90% actual series win rates vs ~61-70% nominal pre-match odds.",
                        "rootCause": "Power scales as `pow(GetActivePlayersSkillAverage(), 2.8) * GetComfortMultiplier(comfort)`. Compounded over 24+ rounds per map and BO3 formats, weak 5th-player floors or unpracticed maps snowball into near-unbeatable multi-trophy streaks.",
                        "devFix": "Soften exponent (`~1.8-2.1`) or add per-map variance / tactical counterplay + meaningful fatigue penalties on packed calendars.",
                    },
                ],
            },
            {
                "category": "Awards, MVPs/EVPs & Year-End Top 20 Rankings",
                "tag": "HLTV / CSTV Scoring",
                "items": [
                    {
                        "id": "mvp-placement",
                        "severity": "high",
                        "title": "6. MVP / EVP Selection Ignores Placement & Trophy Context",
                        "symbol": "TournamentAwardEvaluator / PlayerAwards",
                        "liveImpact": f"{a.get('flaggedCount', 0)} flagged awards out of {a.get('totalEvaluated', 0)} evaluated ({a.get('outrankedMvps', 0)} outranked MVPs, {a.get('sub110Evps', 0)} sub-1.10 EVPs, {a.get('duplicateMvpEvps', 0)} dupes).",
                        "rootCause": "MVPs can be awarded to early-eliminated group-stage rating farmers or lower-tier outliers without placement-adjusted weighting (`#1` champion bonus vs finalist/SF carry threshold), while weak winners slip in ahead of higher-impact teammates or duplicate MVP+EVP entries.",
                        "devFix": "Filter out low-reputation events without awards, weight deep playoff/final maps heavier than groups, and only give MVP to a runner-up/SF star if they massively clear the champion's best player.",
                    },
                    {
                        "id": "top20-cliff",
                        "severity": "warn",
                        "title": "7. Year-End Top 20 Linear 50-Match Cliff & Exponential MVP Boost",
                        "symbol": "YearEndTop20Ranking (`AvgRating_vsTop10 * 1.05^MVP * 1.01^EVP * min(Matches/50, 1)`)",
                        "liveImpact": "Bubble stars with Elite Ratings vs Top-10 are severely punished if their team played <50 Top-10 maps, while dominant teams stack 1.05^MVP compounding.",
                        "rootCause": "A strict linear `Matches_vsTop10 / 50` multiplier cuts a 1.25-rated star with 25 Top-10 maps down by 50%, whereas every MVP gives an uncapped exponential `1.05x` multiplier alongside a strict `#1-#13` CSTV ballot tier.",
                        "devFix": "Replace linear `<50` cutoff with a softer diminishing-returns curve (e.g. `sqrt(min(n, 50) / 50)`), and cap exponential MVP stacking.",
                    },
                    {
                        "id": "burnout-snowball",
                        "severity": "info",
                        "title": "8. Negligible Tournament Burnout & Wealth Compounding",
                        "symbol": "TeamCohesion.cohesionFromBurnout & TeamFinances",
                        "liveImpact": "Top teams maintain near-100% burnout health across heavy tournament schedules and hoard multi-million balances.",
                        "rootCause": "Traveling and playing deep in 10+ Tier-1 events per year barely lowers `cohesionFromBurnout`, letting #1 superteams attend every Big Event fresh while prize money locks down top contracts forever.",
                        "devFix": "Accumulate real travel/series fatigue on consecutive weeks without breaks so skipping minor events becomes strategically necessary.",
                    },
                ],
            },
            {
                "category": "AI Transfers, Bench Sabotage & Squad Stability",
                "tag": "AI GM Logic",
                "items": [
                    {
                        "id": "ai-vulture-bench",
                        "severity": "critical",
                        "title": "9. AI Vultures Hunt Benched Players Regardless of Fit",
                        "symbol": "TeamAI Transfer Evaluation",
                        "liveImpact": f"{t.get('flaggedTxCount', 0)} questionable AI transfers totaling ${int(t.get('totalWastedSpend', 0) or 0):,}.",
                        "rootCause": "AI transfer scoring heavily discounts players sitting on another team's bench (`benched == true`) without checking if the target actually beats the buyer's existing starters or fits role needs.",
                        "devFix": "Require minimum skill upgrade over weakest starter on matching role (`Entry`/`AWP`/`IGL`) and evaluate full active roster strength rather than bench status discounts.",
                    },
                    {
                        "id": "ai-bench-better",
                        "severity": "critical",
                        "title": "10. AI Benches Stronger Starters Behind Worse Signings",
                        "symbol": "Lineup Auto-Select / Contract Priority",
                        "liveImpact": f"{t.get('benchedOverStarterCount', 0)} teams currently leave a higher-skilled player on the bench behind a weaker starter.",
                        "rootCause": "Recent signings, wage tiers, or role/nationality flags cause manager AI to demote higher-skilled starters onto the bench (`benched = true`), hurting match win% and triggering endless poaching loops.",
                        "devFix": "Pick active 5 primarily by role-weighted practical skill total and only bench a better player if deliberately resting/injured/unhappy.",
                    },
                    {
                        "id": "ai-policy-breach",
                        "severity": "high",
                        "title": "11. 'Only National' & 'Only National Language' Policy Breaches",
                        "symbol": "owner.hiringBias == 0 / 1 vs TeamAI Signings",
                        "liveImpact": f"{t.get('policyHb0Players', 0)} National + {t.get('policyHb1Players', 0)} Language player breaches (+{t.get('policyTxStaff', 0)} staff), ${int(t.get('policySpend', 0) or 0):,} spent.",
                        "rootCause": "Strict national clubs (`hiringBias == 0`) and language-locked clubs (`hiringBias == 1`) sign foreign or non-fluent players and staff anyway — breaking club identity and slashing `cohesionFromLanguage`.",
                        "devFix": "Enforce hard pre-bid eligibility filter on `player.nation == team.nation` (`hiringBias == 0`) and fluent shared national language (`>=10` skill for `hiringBias == 1`).",
                    },
                    {
                        "id": "zero-patience-stints",
                        "severity": "high",
                        "title": "12. Zero Post-Signing Protection & Revolving-Door Churn",
                        "symbol": "TeamAI Bench / Transfer Trigger",
                        "liveImpact": f"Ended/benched stints average {s.get('avgStintMonths', 0)}m ({s.get('sub6MonthsPct', 0)}% below 6.0m CS2 pro low end); {s.get('carouselTeamsCount', 0)} high-churn orgs.",
                        "rootCause": "After spending heavy buyouts, AI orgs have zero post-signing patience/sunk-cost grace period — immediately benching or selling new players within weeks and turning rosters over 4-8+ times a season.",
                        "devFix": "Add a minimum ~3-6 month post-transfer protection window (unless terrible form/chemistry breakdown) before AI can bench or transfer-list a paid signing.",
                    },
                ],
            },
            {
                "category": "Save Integrity & Match Freeze Prevention",
                "tag": "Serialization / Tactics",
                "items": [
                    {
                        "id": "tactics-freeze",
                        "severity": "warn",
                        "title": "13. Stale `generalTactics` / Missing `mapPositions` Match Freeze",
                        "symbol": "Team.generalTactics (iglId, sniperId) & Team.mapTactics[].mapPositions",
                        "liveImpact": "Directly editing or transferring players without rebuilding tactics leaves invalid player IDs in lane slots and freezes simulated matches.",
                        "rootCause": "The match engine expects all 5 active `mapPositions` across every map and valid `iglId`/`sniperId` references in active `generalTactics` to correspond to unbenched players under contract.",
                        "devFix": "Ensure game-side fallback validation before match start; inside this editor, Transfers and Validate & Fix automatically call `recalculate_ai_tactics` to prevent corruption.",
                    },
                ],
            },
        ]

    def _showcase_blowouts(self) -> dict[str, Any]:
        assert self.data is not None
        _, tourn_by_id, map_names = self._stats_lookups()

        total_maps = 0
        shutouts_13_0 = 0
        blowouts_le3 = 0
        halves_12_0 = 0
        halves_12_0_t = 0
        halves_12_0_ct = 0
        halves_12_0_unk = 0
        r13_after_12_0_total = 0
        r13_after_12_0_held = 0
        top20_13_0 = 0
        upset_13_0 = 0

        close_t_wins = 0
        close_ct_wins = 0
        close_r1_t_wins = 0
        close_r1_total = 0

        # Intra-half win-streak snowball tracker (rounds 2..12)
        streak_stats: dict[int, list[int]] = {}  # streak_len -> [wins, total]

        examples: list[dict[str, Any]] = []

        for m in self.data.get("matches", {}).get("matches", []):
            if not m.get("processingCompleted"):
                continue
            t1_id = int(m.get("team1Id", 0))
            t2_id = int(m.get("team2Id", 0))
            t1_name = self.teams_by_id.get(t1_id, {}).get("name", f"Team #{t1_id}")
            t2_name = self.teams_by_id.get(t2_id, {}).get("name", f"Team #{t2_id}")
            t1_rank = int(m.get("team1RankBefore", 0) or 0)
            t2_rank = int(m.get("team2RankBefore", 0) or 0)
            t1_odds = float(m.get("team1PreMatchOdds", 0.5) or 0.5)
            t2_odds = float(m.get("team2PreMatchOdds", 0.5) or 0.5)
            is_close_match = 0.45 <= t1_odds <= 0.55
            is_top20_pair = 0 < t1_rank <= 20 and 0 < t2_rank <= 20
            ev_name = tourn_by_id.get(m.get("tournamentId"), {}).get("name", f"Event #{m.get('tournamentId')}")
            dt = m.get("datetime", {})
            date_str = f"{dt.get('year', 0)}-{int(dt.get('month', 0)):02d}-{int(dt.get('day', 0)):02d}"

            for mm in m.get("matchMaps", []):
                rounds = sorted(mm.get("baseMatchRounds", []), key=lambda r: int(r.get("number", 0)))
                if not rounds:
                    continue
                total_maps += 1

                t1_r = sum(1 for r in rounds if r.get("winner") == t1_id)
                t2_r = sum(1 for r in rounds if r.get("winner") == t2_id)
                win_r = max(t1_r, t2_r)
                lose_r = min(t1_r, t2_r)
                winner_id = t1_id if t1_r > t2_r else t2_id
                winner_odds = t1_odds if winner_id == t1_id else t2_odds
                is_upset = winner_odds < 0.50

                # Infer Half 1 T-side team from winningType (2 = Bomb detonated => T; 3 = Defuse/Time => CT)
                h1_t_team = 0
                for r in rounds:
                    num = int(r.get("number", 0))
                    wt = int(r.get("winningType", 0))
                    w = int(r.get("winner", 0))
                    if num <= 12:
                        if wt == 2:
                            h1_t_team = w
                            break
                        if wt == 3:
                            h1_t_team = t2_id if w == t1_id else t1_id
                            break
                    elif 13 <= num <= 24:
                        if wt == 2:
                            h1_t_team = t2_id if w == t1_id else t1_id
                            break
                        if wt == 3:
                            h1_t_team = w
                            break

                # Half 1 12-0 + streak snowball
                h1 = [r for r in rounds if 1 <= int(r.get("number", 0)) <= 12]
                if len(h1) == 12:
                    h1_winners = {int(r.get("winner", 0)) for r in h1}
                    if len(h1_winners) == 1:
                        halves_12_0 += 1
                        sweep_team = next(iter(h1_winners))
                        if h1_t_team:
                            if sweep_team == h1_t_team:
                                halves_12_0_t += 1
                            else:
                                halves_12_0_ct += 1
                        else:
                            halves_12_0_unk += 1
                        r13 = next((r for r in rounds if int(r.get("number", 0)) == 13), None)
                        if r13:
                            r13_after_12_0_total += 1
                            if int(r13.get("winner", 0)) == sweep_team:
                                r13_after_12_0_held += 1

                    # Track active H1 streak before round i (rounds 2..12)
                    cur_team = int(h1[0].get("winner", 0))
                    cur_streak = 1
                    for r in h1[1:]:
                        key = min(cur_streak, 8)
                        bucket = streak_stats.setdefault(key, [0, 0])
                        bucket[1] += 1
                        rw = int(r.get("winner", 0))
                        if rw == cur_team:
                            bucket[0] += 1
                            cur_streak += 1
                        else:
                            cur_team = rw
                            cur_streak = 1

                # Close-match T vs CT skew (reg rounds 1..24)
                if is_close_match and h1_t_team:
                    for r in rounds:
                        num = int(r.get("number", 0))
                        if num > 24:
                            continue
                        rw = int(r.get("winner", 0))
                        t_on_round = h1_t_team if num <= 12 else (t2_id if h1_t_team == t1_id else t1_id)
                        if rw == t_on_round:
                            close_t_wins += 1
                            if num == 1:
                                close_r1_t_wins += 1
                        else:
                            close_ct_wins += 1
                        if num == 1:
                            close_r1_total += 1

                if win_r == 13 and lose_r == 0:
                    shutouts_13_0 += 1
                    if is_top20_pair:
                        top20_13_0 += 1
                    if is_upset:
                        upset_13_0 += 1

                if win_r == 13 and lose_r <= 3:
                    blowouts_le3 += 1
                    tags = []
                    if lose_r == 0:
                        tags.append("13-0")
                    else:
                        tags.append(f"13-{lose_r}")
                    if is_top20_pair:
                        tags.append("Top 20 vs Top 20")
                    if is_upset:
                        tags.append(f"Upset ({round(winner_odds * 100)}% odds)")
                    if len(examples) < 250:
                        examples.append(
                            {
                                "matchId": int(m.get("id", 0)),
                                "date": date_str,
                                "dateKey": self._match_date_key(dt),
                                "event": ev_name,
                                "mapName": map_names.get(mm.get("mapId"), f"Map {mm.get('mapId')}"),
                                "team1Id": t1_id,
                                "team1Name": t1_name,
                                "team1Rank": t1_rank,
                                "team2Id": t2_id,
                                "team2Name": t2_name,
                                "team2Rank": t2_rank,
                                "team1Score": t1_r,
                                "team2Score": t2_r,
                                "loseScore": lose_r,
                                "winnerOdds": round(winner_odds * 100, 1),
                                "isTop20": is_top20_pair,
                                "isUpset": is_upset,
                                "tags": tags,
                            }
                        )

        examples.sort(key=lambda e: (e["loseScore"], -(1 if e["isTop20"] else 0), -(1 if e["isUpset"] else 0), -e["dateKey"][0], -e["dateKey"][1], -e["dateKey"][2]))

        shutout_pct = round(shutouts_13_0 * 100.0 / total_maps, 2) if total_maps else 0.0
        blowout_le3_pct = round(blowouts_le3 * 100.0 / total_maps, 2) if total_maps else 0.0
        half_12_0_pct = round(halves_12_0 * 100.0 / total_maps, 2) if total_maps else 0.0
        close_tot = close_t_wins + close_ct_wins

        streak_curve = []
        for s_len in sorted(streak_stats.keys()):
            w_cnt, tot_cnt = streak_stats[s_len]
            streak_curve.append(
                {
                    "streakLabel": f"{s_len}+" if s_len == 8 else str(s_len),
                    "wins": w_cnt,
                    "total": tot_cnt,
                    "holdPct": round(w_cnt * 100.0 / tot_cnt, 1) if tot_cnt else 0.0,
                }
            )

        pro_13_0_mid = 1.1  # HLTV CS2 MR12 tier-1/pro shutout rate (~0.8% - 1.5%)
        pro_le3_mid = 13.5  # HLTV CS2 MR12 pro <=3 rounds blowout rate (~12% - 15%)
        pro_12_0_mid = 0.45

        return {
            "totalMaps": total_maps,
            "shutouts13_0": shutouts_13_0,
            "shutoutPct": shutout_pct,
            "pro13_0Range": "0.8% - 1.5%",
            "pro13_0Baseline": pro_13_0_mid,
            "shutoutMultiplier": round(shutout_pct / pro_13_0_mid, 2) if pro_13_0_mid else 0.0,
            "blowoutsLe3": blowouts_le3,
            "blowoutLe3Pct": blowout_le3_pct,
            "proLe3Range": "12% - 15%",
            "proLe3Baseline": pro_le3_mid,
            "blowoutMultiplier": round(blowout_le3_pct / pro_le3_mid, 2) if pro_le3_mid else 0.0,
            "halves12_0": halves_12_0,
            "half12_0Pct": half_12_0_pct,
            "pro12_0Baseline": pro_12_0_mid,
            "halves12_0T": halves_12_0_t,
            "halves12_0Ct": halves_12_0_ct,
            "halves12_0Unk": halves_12_0_unk,
            "r13After12_0Total": r13_after_12_0_total,
            "r13After12_0HeldPct": round(r13_after_12_0_held * 100.0 / r13_after_12_0_total, 1) if r13_after_12_0_total else 0.0,
            "top20_13_0": top20_13_0,
            "upset_13_0": upset_13_0,
            "upset_13_0Pct": round(upset_13_0 * 100.0 / shutouts_13_0, 1) if shutouts_13_0 else 0.0,
            "closeTWinPct": round(close_t_wins * 100.0 / close_tot, 1) if close_tot else 50.0,
            "closeR1TWinPct": round(close_r1_t_wins * 100.0 / close_r1_total, 1) if close_r1_total else 50.0,
            "streakCurve": streak_curve,
            "examples": examples[:120],
            "rootCauses": [
                {
                    "title": "1. Broken Helmet Damage Overwrite",
                    "symbol": "Weapon::CalculateDamage",
                    "summary": "When a target has a helmet, damage is overwritten with `damage * armorMultiplier` — wiping out the headshot multiplier and distance dropoff. Winners with helmets take ~27 dmg from an AK headshot while unhelmeted broke defenders take ~144.",
                },
                {
                    "title": "2. Post-Plant Probabilities Copy-Paste Bug",
                    "symbol": "SimulationManager::CheckForRoundOverAndPostPlantInitiation",
                    "summary": "Stage 5 computes `atkStrength` into a local variable and then never uses it — BOTH numerator and denominator use `(1 + defStrength)` so defense cancels out. T-side always gets >=50% (often 61%+) post-plant odds even in 1v5 retakes.",
                },
                {
                    "title": "3. Inverted Armor Reserve Budget",
                    "symbol": "MatchPurchaseFunctions::SetPlayerPurchaseBudget",
                    "summary": "Reserves $650 with `hasArmor ? 650 : 0` — charging players who ALREADY have armor instead of unarmored eco/force players, starving losing defenders of full utility and rifles.",
                },
                {
                    "title": "4. Chaotic Force-Buy Loop & No Bomb Plant Bonus",
                    "symbol": "BaseMatchTeam::SetPurchaseStrategy & ApplyRoundMoney",
                    "summary": "A `Save` decision flips to `FullSpend` on `Random.value <= forceBuy * 0.6f`, trapping losing teams on SMG/Deagle half-buys every round, compounded by missing the CS2 +$800 T bomb-plant team bonus.",
                },
            ],
        }

    def _showcase_awards(self) -> dict[str, Any]:
        assert self.data is not None
        tmpl_names, _, _ = self._stats_lookups()
        tournaments = self.data.get("tournaments", {}).get("tournaments", [])
        stages = self.data.get("tournamentStages", {}).get("tournamentStages", [])
        pcs = self.data.get("playerCareerStats", {}).get("playerCareerStats", [])
        matches = self.data.get("matches", {}).get("matches", [])

        # Map champion team_id from teams[].trophyHistories
        champions_by_tid: dict[int, int] = {}
        for tid_k, t_obj in self.teams_by_id.items():
            for th in t_obj.get("trophyHistories", []):
                ch_tid = int(th.get("tournamentId", 0) or 0)
                if ch_tid:
                    champions_by_tid[ch_tid] = int(tid_k)

        t_end: dict[int, tuple[int, int, int]] = {}
        stage_by_id: dict[int, dict[str, Any]] = {}
        stages_by_tid: dict[int, list[dict[str, Any]]] = {}
        for s in stages:
            sid = int(s.get("id", 0) or 0)
            pid = int(s.get("parentId", 0) or 0)
            stage_by_id[sid] = s
            stages_by_tid.setdefault(pid, []).append(s)
            dt = s.get("endDatetime") or {}
            y, m, d = int(dt.get("year", 0) or 0), int(dt.get("month", 0) or 0), int(dt.get("day", 0) or 0)
            if pid and y > 10:
                prev = t_end.get(pid)
                if prev is None or (y, m, d) > prev:
                    t_end[pid] = (y, m, d)

        t_months: dict[int, set[tuple[int, int]]] = {}
        matches_by_stage: dict[int, list[dict[str, Any]]] = {}
        for m in matches:
            if not m.get("processingCompleted"):
                continue
            sid = int(m.get("tournamentId", 0) or 0)
            matches_by_stage.setdefault(sid, []).append(m)
            st = stage_by_id.get(sid)
            if st and "QUALIFIER" not in (st.get("name") or "").upper():
                tid = int(st.get("parentId", 0) or 0)
                dt = m.get("datetime", {})
                y, mo = int(dt.get("year", 0) or 0), int(dt.get("month", 0) or 0)
                if tid and y > 10:
                    t_months.setdefault(tid, set()).add((y, mo))

        def _match_wl(m: dict[str, Any]) -> tuple[int, int]:
            t1 = int(m.get("team1Id", 0) or 0)
            t2 = int(m.get("team2Id", 0) or 0)
            s1 = s2 = 0
            for mm in m.get("matchMaps", []):
                r1 = sum(1 for r in mm.get("baseMatchRounds", []) if r.get("winner") == t1)
                r2 = sum(1 for r in mm.get("baseMatchRounds", []) if r.get("winner") == t2)
                if r1 > r2:
                    s1 += 1
                elif r2 > r1:
                    s2 += 1
            return (t1, t2) if s1 >= s2 else (t2, t1)

        def _team_placements(tid: int) -> dict[int, tuple[str, float]]:
            # Placement multipliers: 1st=1.10x, 2nd=1.08x, 3rd-4th=1.04x, 5th-8th=1.02x, Other=1.00x
            placements: dict[int, tuple[str, float]] = {}
            if tid in champions_by_tid:
                placements[champions_by_tid[tid]] = ("1st", 1.10)
            cand = [
                s
                for s in stages_by_tid.get(tid, [])
                if "QUALIFIER" not in (s.get("name") or "").upper() and matches_by_stage.get(int(s.get("id", 0)))
            ]
            if not cand:
                return placements
            final_stage = max(cand, key=lambda s: (int(s.get("stage", 0) or 0), int(s.get("id", 0) or 0)))
            ms = matches_by_stage.get(int(final_stage.get("id", 0)), [])
            is_playoff = "PLAYOFF" in (final_stage.get("name") or "").upper() or int(final_stage.get("formatType", -1)) == 0
            if is_playoff and ms:
                upper = [m for m in ms if not m.get("lowerBracket")]
                if upper:
                    max_r = max(int(m.get("round", 0) or 0) for m in upper)
                    finals = [m for m in upper if int(m.get("round", 0) or 0) == max_r]
                    if len(finals) == 1:
                        w, l = _match_wl(finals[0])
                        placements.setdefault(w, ("1st", 1.10))
                        placements.setdefault(l, ("2nd", 1.08))
                        for m in upper:
                            r = int(m.get("round", 0) or 0)
                            _, ml = _match_wl(m)
                            if r == max_r - 1:
                                placements.setdefault(ml, ("3rd-4th", 1.04))
                            elif r == max_r - 2:
                                placements.setdefault(ml, ("5th-8th", 1.02))
            return placements

        pcs_by_tpl_ym: dict[tuple[int, int, int], list[dict[str, Any]]] = {}
        for r in pcs:
            mw = int(r.get("matchesWon", 0) or 0)
            ml = int(r.get("matchesLost", 0) or 0)
            if mw + ml <= 0:
                continue
            key = (int(r.get("tournamentTemplate", 0)), int(r.get("year", 0)), int(r.get("month", 0)))
            pcs_by_tpl_ym.setdefault(key, []).append(r)

        # Also detect duplicate (MVP + EVP) in playerAwards and collect real MVP/EVP events (excluding mock year <= 10)
        dup_awards: list[dict[str, Any]] = []
        mock_awards_hidden = 0
        real_award_events: set[tuple[int, int, int]] = set()
        for pid, p in self.players_by_id.items():
            seen_ev: dict[tuple[int, int, int], set[int]] = {}
            for a in p.get("playerAwards", []):
                y = int(a.get("year", 0) or 0)
                if y <= 10:
                    mock_awards_hidden += 1
                    continue
                atype = int(a.get("type", -1))
                tpl = int(a.get("tournamentTemplate", 0) or 0)
                mo = int(a.get("month", 0) or 0)
                if atype in (0, 2):
                    real_award_events.add((tpl, y, mo))
                    seen_ev.setdefault((tpl, y, mo), set()).add(atype)
            for (tpl, y, mo), types in seen_ev.items():
                if 0 in types and 2 in types:
                    dup_awards.append(
                        {
                            "severity": 85,
                            "role": "MVP + EVP",
                            "playerId": pid,
                            "playerName": p.get("name", f"Player #{pid}"),
                            "teamId": 0,
                            "teamName": "—",
                            "event": tmpl_names.get(tpl, f"Event #{tpl}"),
                            "date": f"{y}-{mo:02d}",
                            "rating": 0.0,
                            "weightedScore": 0.0,
                            "placement": "—",
                            "placementMult": 1.0,
                            "matches": 0,
                            "wins": 0,
                            "losses": 0,
                            "kpr": 0.0,
                            "adr": 0.0,
                            "eventRank": 0,
                            "fieldSize": 0,
                            "bestPlayerId": 0,
                            "bestPlayerName": "—",
                            "bestPlayerRating": 0.0,
                            "bestPlacement": "—",
                            "bestWeightedScore": 0.0,
                            "ratingGap": 0.0,
                            "reasons": ["Player received BOTH MVP and EVP for the same tournament"],
                        }
                    )

        total_evaluated = 0
        total_mvps = 0
        total_evps = 0
        sub110_evps = 0
        outranked_mvps = 0
        flagged: list[dict[str, Any]] = list(dup_awards)

        for t in tournaments:
            tid = int(t.get("id", 0))
            pa = t.get("playersAwarded") or []
            if not pa:
                continue
            tpl = int(t.get("template", 0))
            months = set(t_months.get(tid, set()))
            end_dt = t_end.get(tid)
            if end_dt:
                months.add((end_dt[0], end_dt[1]))
            if not months:
                continue
            # Only evaluate tournaments that actually grant MVP/EVP awards (not low-reputation tournaments)
            if real_award_events:
                if not any((tpl, yy, mm) in real_award_events for yy, mm in months):
                    continue
            elif int(t.get("reputation", 0) or 0) < 15:
                continue

            placements = _team_placements(tid)
            pstats: dict[int, dict[str, Any]] = {}
            for yy, mm in months:
                for r in pcs_by_tpl_ym.get((tpl, yy, mm), []):
                    pid = int(r.get("playerId", 0))
                    st = pstats.setdefault(
                        pid,
                        {"m": 0, "mw": 0, "ml": 0, "rat_sum": 0.0, "rp": 0, "k": 0, "d": 0, "dmg": 0, "team_id": 0},
                    )
                    mw = int(r.get("matchesWon", 0) or 0)
                    ml = int(r.get("matchesLost", 0) or 0)
                    st["m"] += mw + ml
                    st["mw"] += mw
                    st["ml"] += ml
                    st["rat_sum"] += float(r.get("accumulativeRating", 0.0) or 0.0)
                    st["rp"] += int(r.get("roundsPlayed", 0) or 0)
                    st["k"] += int(r.get("accumulatedKills", 0) or 0)
                    st["d"] += int(r.get("accumulateDeaths", 0) or 0)
                    st["dmg"] += int(r.get("accumulatedDamage", 0) or 0)
                    st["team_id"] = int(r.get("teamId", 0) or 0)

            max_m = max((st["m"] for st in pstats.values()), default=0)
            min_q = max(2, int(round(max_m * 0.45))) if max_m >= 4 else 1

            weighted_pool = []
            for pid, st in pstats.items():
                if st["m"] < min_q:
                    continue
                rat = st["rat_sum"] / st["m"]
                pl_lbl, mult = placements.get(st["team_id"], ("Other", 1.00))
                w_score = rat * mult
                weighted_pool.append((w_score, rat, pl_lbl, mult, st["m"], pid, st))
            weighted_pool.sort(reverse=True)
            if not weighted_pool:
                continue

            w_rank = {x[5]: idx + 1 for idx, x in enumerate(weighted_pool)}
            best_w, best_rat, best_pl, _, _, best_pid, _ = weighted_pool[0]
            best_name = self.players_by_id.get(best_pid, {}).get("name", f"Player #{best_pid}")
            date_str = f"{end_dt[0]}-{end_dt[1]:02d}" if end_dt else f"{max(months)[0]}-{max(months)[1]:02d}"
            ev_name = t.get("name") or tmpl_names.get(tpl, f"Tournament #{tid}")

            for idx, raw_pid in enumerate(pa):
                pid = int(raw_pid or 0)
                role = "MVP" if idx == 0 else "EVP"
                total_evaluated += 1
                if role == "MVP":
                    total_mvps += 1
                else:
                    total_evps += 1

                if pid <= 0 or pid not in self.players_by_id:
                    flagged.append(
                        {
                            "severity": 95,
                            "role": role,
                            "playerId": pid,
                            "playerName": f"Invalid Player (#{pid})",
                            "teamId": 0,
                            "teamName": "—",
                            "event": ev_name,
                            "date": date_str,
                            "rating": 0.0,
                            "weightedScore": 0.0,
                            "placement": "—",
                            "placementMult": 1.0,
                            "matches": 0,
                            "wins": 0,
                            "losses": 0,
                            "kpr": 0.0,
                            "adr": 0.0,
                            "eventRank": 0,
                            "fieldSize": len(weighted_pool),
                            "bestPlayerId": best_pid,
                            "bestPlayerName": best_name,
                            "bestPlayerRating": round(best_rat, 2),
                            "bestPlacement": best_pl,
                            "bestWeightedScore": round(best_w, 2),
                            "ratingGap": round(best_w, 2),
                            "reasons": [f"Broken award slot (ID {pid}) written into tournament playersAwarded"],
                        }
                    )
                    continue

                st = pstats.get(pid)
                if not st or st["m"] == 0:
                    continue
                rat = st["rat_sum"] / st["m"]
                rp = max(st["rp"], 1)
                kpr = st["k"] / rp
                adr = st["dmg"] / rp
                team_id = st["team_id"]
                team_name = self.teams_by_id.get(team_id, {}).get("name", "—")
                pl_lbl, mult = placements.get(team_id, ("Other", 1.00))
                w_score = rat * mult
                rk = w_rank.get(pid, len(weighted_pool) + 1)
                w_gap = best_w - w_score

                # HLTV-realistic MVP/EVP evaluation:
                # Winning trophy carries huge weight; non-champions need an overwhelming rating + deep run to steal MVP.
                mvp_req = {
                    "1st": (0.05, 0.0),
                    "2nd": (0.18, 1.42),
                    "3rd-4th": (0.25, 1.48),
                    "5th-8th": (0.28, 1.50),
                    "Other": (0.30, 1.50),
                }
                awarded_set = {int(x or 0) for x in pa if int(x or 0) > 0}
                reasons = []
                severity = 0.0
                disp_best_id = best_pid
                disp_best_name = best_name
                disp_best_rat = best_rat
                disp_best_pl = best_pl
                disp_best_w = best_w

                if role == "MVP":
                    mvp_m = st["m"]
                    if rat < 1.18:
                        outranked_mvps += 1
                        reasons.append(f"Carried champion MVP ({rat:.2f} rating < 1.18 HLTV baseline)")
                        severity += 40 + (1.20 - rat) * 200
                    # Check if a teammate outperformed the MVP
                    best_mate = None
                    for o_pid, o_st in pstats.items():
                        if o_pid != pid and int(o_st["team_id"]) == team_id and o_st["m"] >= max(2, int(round(mvp_m * 0.75))):
                            o_rat = o_st["rat_sum"] / o_st["m"]
                            if o_rat > rat + 0.05 and (best_mate is None or o_rat > best_mate[0]):
                                best_mate = (o_rat, o_pid)
                    if best_mate:
                        outranked_mvps += 1
                        m_rat, m_pid = best_mate
                        m_name = self.players_by_id.get(m_pid, {}).get("name", f"Player #{m_pid}")
                        reasons.append(f"Teammate {m_name} posted {m_rat:.2f} vs MVP's {rat:.2f} (+{m_rat - rat:.2f})")
                        severity += 45 + (m_rat - rat) * 180
                        disp_best_id, disp_best_name, disp_best_rat, disp_best_pl, disp_best_w = (
                            m_pid, m_name, m_rat, pl_lbl, m_rat * mult
                        )
                    # Check if a non-champion superstar overwhelmingly outcarried the MVP
                    best_other = None
                    for o_pid, o_st in pstats.items():
                        if o_pid == pid or o_st["m"] < max(2, int(round(mvp_m * 0.60))):
                            continue
                        o_rat = o_st["rat_sum"] / o_st["m"]
                        o_pl, o_mult = placements.get(int(o_st["team_id"]), ("Other", 1.00))
                        min_gap, min_floor = mvp_req.get(o_pl, (0.30, 1.50))
                        if o_rat >= min_floor and (o_rat - rat) >= min_gap:
                            if best_other is None or o_rat > best_other[0]:
                                best_other = (o_rat, o_pid, o_pl, o_mult, o_st["m"])
                    if best_other:
                        outranked_mvps += 1
                        o_rat, o_pid, o_pl, o_mult, o_m = best_other
                        o_name = self.players_by_id.get(o_pid, {}).get("name", f"Player #{o_pid}")
                        reasons.append(
                            f"Outcarried by {o_name} ({o_rat:.2f} in {o_pl}, {o_m}m, +{o_rat - rat:.2f} over MVP)"
                        )
                        severity += 40 + (o_rat - rat) * 150
                        disp_best_id, disp_best_name, disp_best_rat, disp_best_pl, disp_best_w = (
                            o_pid, o_name, o_rat, o_pl, o_rat * o_mult
                        )

                if role == "EVP":
                    # Find best snubbed non-awarded player with real sample size
                    best_snub = None
                    for o_pid, o_st in pstats.items():
                        if o_pid in awarded_set or o_st["m"] < min_q:
                            continue
                        o_rat = o_st["rat_sum"] / o_st["m"]
                        o_pl, o_mult = placements.get(int(o_st["team_id"]), ("Other", 1.00))
                        if o_pl in ("1st", "2nd", "3rd-4th") or o_st["m"] >= max(3, int(round(max_m * 0.70))):
                            if best_snub is None or (o_rat * o_mult) > (best_snub[0] * best_snub[3]):
                                best_snub = (o_rat, o_pid, o_pl, o_mult)

                    if rat < 1.10:
                        sub110_evps += 1
                        reasons.append(f"Sub-1.10 EVP ({rat:.2f}, KPR {kpr:.2f}, ADR {adr:.0f})")
                        severity += (1.15 - rat) * 260
                    elif rat < 1.15 and best_snub and (best_snub[0] - rat) >= 0.16:
                        s_rat, s_pid, s_pl, s_mult = best_snub
                        s_name = self.players_by_id.get(s_pid, {}).get("name", f"Player #{s_pid}")
                        reasons.append(
                            f"Low {rat:.2f} EVP ({pl_lbl} quota) while {s_name} ({s_rat:.2f}, {s_pl}) got no award"
                        )
                        severity += 20 + (s_rat - rat) * 100
                        disp_best_id, disp_best_name, disp_best_rat, disp_best_pl, disp_best_w = (
                            s_pid, s_name, s_rat, s_pl, s_rat * s_mult
                        )

                    if rat < 1.13 and adr < 76.0 and kpr < 0.72:
                        reasons.append(f"Low fragging impact ({kpr:.2f} KPR, {adr:.1f} ADR)")
                        severity += 15

                if reasons:
                    flagged.append(
                        {
                            "severity": round(severity, 1),
                            "role": role,
                            "playerId": pid,
                            "playerName": self.players_by_id[pid].get("name", f"Player #{pid}"),
                            "teamId": team_id,
                            "teamName": team_name,
                            "event": ev_name,
                            "date": date_str,
                            "rating": round(rat, 2),
                            "weightedScore": round(w_score, 2),
                            "placement": pl_lbl,
                            "placementMult": mult,
                            "matches": st["m"],
                            "wins": st["mw"],
                            "losses": st["ml"],
                            "kpr": round(kpr, 2),
                            "adr": round(adr, 1),
                            "eventRank": rk,
                            "fieldSize": len(weighted_pool),
                            "bestPlayerId": disp_best_id,
                            "bestPlayerName": disp_best_name,
                            "bestPlayerRating": round(disp_best_rat, 2),
                            "bestPlacement": disp_best_pl,
                            "bestWeightedScore": round(disp_best_w, 2),
                            "ratingGap": round(disp_best_rat - rat, 2),
                            "reasons": reasons,
                        }
                    )

        flagged.sort(key=lambda r: (-r["severity"], r["rating"]))

        return {
            "totalEvaluated": total_evaluated,
            "totalMvps": total_mvps,
            "totalEvps": total_evps,
            "flaggedCount": len(flagged),
            "sub110Evps": sub110_evps,
            "outrankedMvps": outranked_mvps,
            "duplicateMvpEvps": len(dup_awards),
            "mockAwardsHidden": mock_awards_hidden,
            "flagged": flagged[:150],
        }

    def _showcase_transfers(self) -> dict[str, Any]:
        assert self.data is not None

        team_starters: dict[int, list[tuple[float, dict[str, Any], dict[str, Any]]]] = {}
        team_benched: dict[int, list[tuple[float, dict[str, Any], dict[str, Any]]]] = {}
        for pid, c in self.player_contract_by_pid.items():
            p = self.players_by_id.get(pid)
            if not p:
                continue
            tid = int(c.get("teamId", 0) or 0)
            sk = _player_avg_skill(p)
            if c.get("benched"):
                team_benched.setdefault(tid, []).append((sk, p, c))
            else:
                team_starters.setdefault(tid, []).append((sk, p, c))

        for lst in team_starters.values():
            lst.sort(key=lambda x: -x[0])
        for lst in team_benched.values():
            lst.sort(key=lambda x: -x[0])

        # 1. Teams currently benching a strictly stronger player than an active starter
        benched_crimes: list[dict[str, Any]] = []
        for tid, b_list in team_benched.items():
            s_list = team_starters.get(tid, [])
            if not s_list:
                continue
            worst_sk, worst_p, _ = s_list[-1]
            tname = self.teams_by_id.get(tid, {}).get("name", f"Team #{tid}")
            for b_sk, bp, _ in b_list:
                diff = round(b_sk - worst_sk, 2)
                if diff >= 0.25:
                    benched_crimes.append(
                        {
                            "teamId": tid,
                            "teamName": tname,
                            "benchedId": int(bp["id"]),
                            "benchedName": bp.get("name", "?"),
                            "benchedSkill": round(b_sk, 2),
                            "benchedAge": int(bp.get("age", 0)),
                            "starterId": int(worst_p["id"]),
                            "starterName": worst_p.get("name", "?"),
                            "starterSkill": round(worst_sk, 2),
                            "starterAge": int(worst_p.get("age", 0)),
                            "skillDiff": diff,
                        }
                    )
        benched_crimes.sort(key=lambda r: -r["skillDiff"])

        # 2. Historical AI player transfers
        raw_transfers = [
            x for x in self.data.get("transferHistories", {}).get("transferHistories", []) if int(x.get("personType", -1)) == 0
        ]
        transfers_by_pid: dict[int, int] = {}
        for x in raw_transfers:
            pid = int(x.get("personId", 0))
            transfers_by_pid[pid] = transfers_by_pid.get(pid, 0) + 1

        # Infer each nation's official/dominant national language(s) from native players' fluent languages (>=15)
        nat_lang_counts: dict[int, dict[int, int]] = {}
        for p_obj in self.players_by_id.values():
            p_n = int(p_obj.get("nation", 0) or 0)
            if not p_n:
                continue
            for lg in p_obj.get("languagesSpoken", []):
                if int(lg.get("languageSkill", 0) or 0) >= 15:
                    lid = int(lg.get("languageId", 0) or 0)
                    if lid:
                        bucket = nat_lang_counts.setdefault(p_n, {})
                        bucket[lid] = bucket.get(lid, 0) + 1
        nation_req_langs: dict[int, set[int]] = {}
        for p_n, cnts in nat_lang_counts.items():
            ranked = sorted(cnts.items(), key=lambda z: -z[1])
            allowed = {ranked[0][0]}
            if len(ranked) > 1 and ranked[1][1] >= ranked[0][1] * 0.40:
                allowed.add(ranked[1][0])
            nation_req_langs[p_n] = allowed

        def _person_lang_ids(person: dict[str, Any]) -> set[int]:
            return {
                int(lg.get("languageId", 0) or 0)
                for lg in person.get("languagesSpoken", [])
                if int(lg.get("languageSkill", 0) or 0) >= 10
            }

        def _fmt_langs(lids: set[int]) -> str:
            if not lids:
                return "None"
            return ", ".join(sorted(LANGUAGES.get(lid, f"#{lid}") for lid in lids))

        def _check_policy(t_obj: dict[str, Any], hb: int, person: dict[str, Any]) -> tuple[bool, str, str]:
            t_nat = int(t_obj.get("nation", 0) or 0)
            p_nat = int(person.get("nation", 0) or 0)
            if hb == 0 and t_nat and p_nat and t_nat != p_nat:
                return True, "hb0", f"Only National ({NATIONS.get(t_nat, f'#{t_nat}')})"
            if hb == 1 and t_nat:
                req_langs = nation_req_langs.get(t_nat, set())
                p_langs = _person_lang_ids(person)
                if req_langs and not (p_langs & req_langs):
                    return True, "hb1", f"Only {_fmt_langs(req_langs)} (Speaks: {_fmt_langs(p_langs)})"
            return False, "", ""

        # Collect per-player suitors/bidders from teams[].personInterests (+ bid/transfer emails)
        bid_status_labels = {
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
        urgency_labels = {0: "High", 1: "Medium", 2: "Low", 3: "Backup"}
        role_labels = {0: "Any", 1: "IGL", 2: "Sniper", 3: "Rifler"}
        hb_labels = {0: "Only National", 1: "Only National Lang", 2: "Anyone"}

        # Precompute rank per teamId from points descending
        ranked_tids = [
            int(t_id)
            for t_id, _ in sorted(
                self.teams_by_id.items(),
                key=lambda kv: (-float(kv[1].get("worldRankingPoints", 0.0) or 0.0), int(kv[0])),
            )
        ]
        team_rank_map = {t_id: idx for idx, t_id in enumerate(ranked_tids, start=1)}

        bidders_raw: dict[int, dict[int, dict[str, Any]]] = {}
        for tid_k, t_obj in self.teams_by_id.items():
            t_id = int(tid_k)
            for pi in t_obj.get("personInterests", []) or []:
                pid_i = int(pi.get("playerId", 0) or 0)
                if pid_i <= 0:
                    continue
                bs = int(pi.get("bidStatus", 0) or 0)
                urg = int(pi.get("urgency", 3) or 0)
                role = int(pi.get("roleInterest", 0) or 0)
                sc = float(pi.get("score", 0.0) or 0.0)
                cd = int(pi.get("cooldown", 0) or 0)
                buyout = int(pi.get("buyoutPrice", 0) or 0)
                max_non = int(pi.get("maxNonNegotiationOffer", 0) or 0)
                max_abs = int(pi.get("maxAbsoluteOffer", 0) or 0)
                co = pi.get("playerContractOffer") or {}
                sal = int(co.get("salaryYear", 0) or 0)
                ask = int(co.get("askingPrice", 0) or 0)
                fee = int(co.get("signingOnFee", 0) or 0)
                benched_off = bool(co.get("benched", False))

                bucket = bidders_raw.setdefault(pid_i, {}).get(t_id)
                if bucket is None:
                    hb_v = int((t_obj.get("owner") or {}).get("hiringBias", 2))
                    p_obj = self.players_by_id.get(pid_i)
                    viol, _, pdetail = _check_policy(t_obj, hb_v, p_obj) if (p_obj and hb_v in (0, 1)) else (False, "", "")
                    bucket = {
                        "teamId": t_id,
                        "teamName": t_obj.get("name", f"Team #{t_id}"),
                        "worldRank": team_rank_map.get(t_id, 0),
                        "teamNation": NATIONS.get(int(t_obj.get("nation", 0) or 0), "—"),
                        "hiringBiasLabel": hb_labels.get(hb_v, "Anyone"),
                        "violatesPolicy": viol,
                        "policyDetail": pdetail,
                        "entriesCount": 0,
                        "roles": [],
                        "bestStatus": bs,
                        "bestStatusLabel": bid_status_labels.get(bs, f"Status #{bs}"),
                        "isActiveBid": bs in (1, 2, 3, 4, 5, 6),
                        "isCooldownBid": bs in (7, 8),
                        "urgency": urg,
                        "urgencyLabel": urgency_labels.get(urg, f"U{urg}"),
                        "peakScore": round(sc, 2),
                        "maxCooldown": cd,
                        "buyoutPrice": buyout,
                        "maxNonNegotiationOffer": max_non,
                        "maxAbsoluteOffer": max_abs,
                        "offerSalary": sal,
                        "offerAskingPrice": ask,
                        "offerSigningFee": fee,
                        "offerBenched": benched_off,
                        "source": "personInterests",
                    }
                    bidders_raw[pid_i][t_id] = bucket

                bucket["entriesCount"] += 1
                rl = role_labels.get(role, f"R{role}")
                if rl not in bucket["roles"]:
                    bucket["roles"].append(rl)
                # Status priority: Active (1..6) > Cooldown (7..8) > Shortlisted (0)
                prio_new = 2 if bs in (1, 2, 3, 4, 5, 6) else (1 if bs in (7, 8) else 0)
                prio_old = 2 if bucket["bestStatus"] in (1, 2, 3, 4, 5, 6) else (1 if bucket["bestStatus"] in (7, 8) else 0)
                if prio_new > prio_old or (prio_new == prio_old and bs > bucket["bestStatus"]):
                    bucket["bestStatus"] = bs
                    bucket["bestStatusLabel"] = bid_status_labels.get(bs, f"Status #{bs}")
                bucket["isActiveBid"] = bucket["isActiveBid"] or (bs in (1, 2, 3, 4, 5, 6))
                bucket["isCooldownBid"] = bucket["isCooldownBid"] or (bs in (7, 8))
                if urg < bucket["urgency"]:
                    bucket["urgency"] = urg
                    bucket["urgencyLabel"] = urgency_labels.get(urg, f"U{urg}")
                if sc > bucket["peakScore"]:
                    bucket["peakScore"] = round(sc, 2)
                bucket["maxCooldown"] = max(bucket["maxCooldown"], cd)
                bucket["buyoutPrice"] = max(bucket["buyoutPrice"], buyout)
                bucket["maxNonNegotiationOffer"] = max(bucket["maxNonNegotiationOffer"], max_non)
                bucket["maxAbsoluteOffer"] = max(bucket["maxAbsoluteOffer"], max_abs)
                bucket["offerSalary"] = max(bucket["offerSalary"], sal)
                bucket["offerAskingPrice"] = max(bucket["offerAskingPrice"], ask)
                bucket["offerSigningFee"] = max(bucket["offerSigningFee"], fee)
                bucket["offerBenched"] = bucket["offerBenched"] or benched_off

        # Supplement from emails for bid/buyout emails involving the player
        for em in self.data.get("emails", {}).get("emails", []) or []:
            etype = int(em.get("type", -1))
            if etype not in (2, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25):
                continue
            epids = [int(em.get("player1Id", 0) or 0), int(em.get("player2Id", 0) or 0)]
            etid = int(em.get("teamId", 0) or 0)
            if etid <= 0 or etid not in self.teams_by_id:
                continue
            for epid in epids:
                if epid <= 0:
                    continue
                if etid not in bidders_raw.get(epid, {}):
                    t_obj = self.teams_by_id[etid]
                    hb_v = int((t_obj.get("owner") or {}).get("hiringBias", 2))
                    p_obj = self.players_by_id.get(epid)
                    viol, _, pdetail = _check_policy(t_obj, hb_v, p_obj) if (p_obj and hb_v in (0, 1)) else (False, "", "")
                    co = em.get("contractOffer") or {}
                    bidders_raw.setdefault(epid, {})[etid] = {
                        "teamId": etid,
                        "teamName": t_obj.get("name", f"Team #{etid}"),
                        "worldRank": team_rank_map.get(etid, 0),
                        "teamNation": NATIONS.get(int(t_obj.get("nation", 0) or 0), "—"),
                        "hiringBiasLabel": hb_labels.get(hb_v, "Anyone"),
                        "violatesPolicy": viol,
                        "policyDetail": pdetail,
                        "entriesCount": 1,
                        "roles": ["Offer"],
                        "bestStatus": 1,
                        "bestStatusLabel": "Bid / Offer Email",
                        "isActiveBid": True,
                        "isCooldownBid": False,
                        "urgency": 1,
                        "urgencyLabel": "Medium",
                        "peakScore": 0.0,
                        "maxCooldown": 0,
                        "buyoutPrice": int((em.get("personInterest") or {}).get("buyoutPrice", 0) or 0),
                        "maxNonNegotiationOffer": 0,
                        "maxAbsoluteOffer": 0,
                        "offerSalary": int(co.get("salaryYear", 0) or 0),
                        "offerAskingPrice": int(co.get("askingPrice", 0) or 0),
                        "offerSigningFee": int(co.get("signingOnFee", 0) or 0),
                        "offerBenched": bool(co.get("benched", False)),
                        "source": "email",
                    }

        def _bidders_for_pid(pid_i: int) -> list[dict[str, Any]]:
            lst = list(bidders_raw.get(pid_i, {}).values())
            for b in lst:
                b["rolesText"] = " / ".join(b["roles"]) if b["roles"] else "Any"
            lst.sort(
                key=lambda b: (
                    0 if b["isActiveBid"] else (1 if b["isCooldownBid"] else 2),
                    -b["peakScore"],
                    b["worldRank"] or 9999,
                    b["teamName"],
                )
            )
            return lst

        flagged_transfers: list[dict[str, Any]] = []
        total_spend_wasted = 0
        signed_over_better_bench = 0
        signed_then_benched = 0
        multi_moved_count = 0

        for x in raw_transfers:
            pid = int(x.get("personId", 0))
            p = self.players_by_id.get(pid)
            if not p:
                continue
            sk = _player_avg_skill(p)
            age = int(p.get("age", 0) or 0)
            from_id = int(x.get("fromTeamId", 0) or 0)
            to_id = int(x.get("otherTeamId", 0) or 0)
            price = int(x.get("purchasePrice", 0) or 0)
            dt = x.get("datetime", {})
            date_str = f"{dt.get('year', 0)}-{int(dt.get('month', 0)):02d}-{int(dt.get('day', 0)):02d}"

            c = self.player_contract_by_pid.get(pid)
            b_list = team_benched.get(to_id, [])
            s_list = team_starters.get(to_id, [])
            best_b = b_list[0] if b_list else None
            worst_s = s_list[-1] if s_list else None

            reasons = []
            severity = 0.0
            compare_name = "—"
            compare_skill = 0.0

            if c and int(c.get("teamId", 0)) == to_id and c.get("benched"):
                signed_then_benched += 1
                reasons.append(f"Signed to {self.teams_by_id.get(to_id, {}).get('name', '?')} (${price:,}) and currently BENCHED")
                severity += 45 + (price / 25000.0)

            if best_b and best_b[1]["id"] != pid and best_b[0] > sk + 0.30:
                signed_over_better_bench += 1
                gap = round(best_b[0] - sk, 2)
                compare_name = f"{best_b[1].get('name')} (Benched)"
                compare_skill = round(best_b[0], 2)
                reasons.append(f"Team benches superior {best_b[1].get('name')} ({best_b[0]:.2f}, +{gap:.2f}) while fielding/signing {sk:.2f}")
                severity += 35 + gap * 18 + (price / 35000.0)

            if worst_s and worst_s[1]["id"] != pid and len(s_list) >= 5 and sk < worst_s[0] - 0.50:
                gap = round(worst_s[0] - sk, 2)
                if compare_name == "—":
                    compare_name = f"{worst_s[1].get('name')} (Worst Starter)"
                    compare_skill = round(worst_s[0], 2)
                reasons.append(f"Weaker than team's worst starter {worst_s[1].get('name')} ({worst_s[0]:.2f} vs {sk:.2f})")
                severity += 20 + gap * 14

            if age >= 30 and price >= 100000:
                reasons.append(f"Paid ${price:,} for age-{age} veteran ({sk:.2f} avg skill)")
                severity += 18 + (age - 29) * 5 + (price / 50000.0)

            move_cnt = transfers_by_pid.get(pid, 1)
            if move_cnt >= 2:
                multi_moved_count += 1
                reasons.append(f"Transferred {move_cnt}x in carousel")
                severity += 14 * move_cnt

            to_team = self.teams_by_id.get(to_id, {})
            hiring_bias = int((to_team.get("owner") or {}).get("hiringBias", -1))
            t_nat = int(to_team.get("nation", 0) or 0)
            p_nat = int(p.get("nation", 0) or 0)
            if hiring_bias == 0 and t_nat and p_nat and t_nat != p_nat:
                t_nat_name = NATIONS.get(t_nat, f"Nation #{t_nat}")
                p_nat_name = NATIONS.get(p_nat, f"Nation #{p_nat}")
                reasons.append(f"'Only National' ({t_nat_name}) club signed foreign player ({p_nat_name})")
                severity += 42 + (price / 25000.0)
            elif hiring_bias == 1 and t_nat:
                req_langs = nation_req_langs.get(t_nat, set())
                p_langs = _person_lang_ids(p)
                if req_langs and not (p_langs & req_langs):
                    reasons.append(
                        f"'Only National Language' ({_fmt_langs(req_langs)}) club signed player speaking {_fmt_langs(p_langs)}"
                    )
                    severity += 38 + (price / 25000.0)

            if reasons:
                total_spend_wasted += price
                b_list_pid = _bidders_for_pid(pid)
                flagged_transfers.append(
                    {
                        "severity": round(severity, 1),
                        "date": date_str,
                        "dateKey": self._match_date_key(dt),
                        "playerId": pid,
                        "playerName": p.get("name", f"Player #{pid}"),
                        "playerNation": NATIONS.get(p_nat, f"#{p_nat}"),
                        "skill": round(sk, 2),
                        "age": age,
                        "fromTeamId": from_id,
                        "fromTeamName": "Free Agent" if from_id == 0 else self.teams_by_id.get(from_id, {}).get("name", f"#{from_id}"),
                        "toTeamId": to_id,
                        "toTeamName": self.teams_by_id.get(to_id, {}).get("name", f"#{to_id}"),
                        "purchasePrice": price,
                        "compareName": compare_name,
                        "compareSkill": compare_skill,
                        "reasons": reasons,
                        "bidderCount": len(b_list_pid),
                        "bidderEntries": sum(b["entriesCount"] for b in b_list_pid),
                        "cooldownBidCount": sum(1 for b in b_list_pid if b["isCooldownBid"]),
                        "activeBidCount": sum(1 for b in b_list_pid if b["isActiveBid"]),
                        "policyMismatchBidders": sum(1 for b in b_list_pid if b["violatesPolicy"]),
                        "bidders": b_list_pid,
                    }
                )

        flagged_transfers.sort(key=lambda r: (-r["severity"], -r["purchasePrice"], -r["dateKey"][0], -r["dateKey"][1]))

        # 3. "Only National" (hiringBias == 0) & "Only National Language" (hiringBias == 1) Policy Violations
        strict_teams = {
            int(tid): (t, int((t.get("owner") or {}).get("hiringBias", -1)))
            for tid, t in self.teams_by_id.items()
            if int((t.get("owner") or {}).get("hiringBias", -1)) in (0, 1)
        }
        only_national_count = sum(1 for _, hb in strict_teams.values() if hb == 0)
        only_lang_count = sum(1 for _, hb in strict_teams.values() if hb == 1)

        policy_map: dict[tuple[int, int, int, str], dict[str, Any]] = {}
        policy_tx_players = 0
        policy_tx_staff = 0
        policy_hb0_players = 0
        policy_hb0_staff = 0
        policy_hb1_players = 0
        policy_hb1_staff = 0
        policy_spend = 0

        for x in self.data.get("transferHistories", {}).get("transferHistories", []):
            to_id = int(x.get("otherTeamId", 0) or 0)
            if to_id not in strict_teams:
                continue
            t, hb = strict_teams[to_id]
            ptype = int(x.get("personType", -1))
            pid = int(x.get("personId", 0))
            person = self.players_by_id.get(pid) if ptype == 0 else (self.staff_by_id.get(pid) if ptype == 1 else None)
            if not person:
                continue
            viol, pcode, pdetail = _check_policy(t, hb, person)
            if not viol:
                continue
            t_nat = int(t.get("nation", 0) or 0)
            p_nat = int(person.get("nation", 0) or 0)
            price = int(x.get("purchasePrice", 0) or 0)
            dt_obj = x.get("datetime", {})
            date_str = f"{dt_obj.get('year', 0)}-{int(dt_obj.get('month', 0)):02d}-{int(dt_obj.get('day', 0)):02d}"
            from_id = int(x.get("fromTeamId", 0) or 0)
            from_name = "Free Agent" if from_id == 0 else self.teams_by_id.get(from_id, {}).get("name", f"#{from_id}")
            if ptype == 0:
                policy_tx_players += 1
                if pcode == "hb0":
                    policy_hb0_players += 1
                else:
                    policy_hb1_players += 1
            else:
                policy_tx_staff += 1
                if pcode == "hb0":
                    policy_hb0_staff += 1
                else:
                    policy_hb1_staff += 1
            policy_spend += price
            key = (to_id, ptype, pid, pcode)
            existing = policy_map.get(key)
            if existing is None or price > existing["purchasePrice"]:
                policy_map[key] = {
                    "teamId": to_id,
                    "teamName": t.get("name", f"Team #{to_id}"),
                    "teamNation": NATIONS.get(t_nat, f"#{t_nat}"),
                    "policyCode": pcode,
                    "policyLabel": "Only National" if pcode == "hb0" else "Only National Lang",
                    "policyDetail": pdetail,
                    "personType": "Player" if ptype == 0 else "Staff",
                    "personId": pid,
                    "personName": person.get("name", f"#{pid}"),
                    "personNation": NATIONS.get(p_nat, f"#{p_nat}"),
                    "age": int(person.get("age", 0) or 0),
                    "skill": _player_avg_skill(person) if ptype == 0 else _staff_avg_skill(person),
                    "date": date_str,
                    "route": f"{from_name} -> {t.get('name', '?')}",
                    "purchasePrice": price,
                    "activeOnTeam": False,
                    "source": "Transfer",
                }

        active_staff_contracts = {int(c.get("staffId", 0)): c for c in self.data.get("staffContracts", {}).get("staffContracts", [])}
        policy_active_players = 0
        policy_active_staff = 0

        for pid, c in self.player_contract_by_pid.items():
            to_id = int(c.get("teamId", 0) or 0)
            if to_id not in strict_teams:
                continue
            p = self.players_by_id.get(pid)
            if not p:
                continue
            t, hb = strict_teams[to_id]
            viol, pcode, pdetail = _check_policy(t, hb, p)
            if not viol:
                continue
            t_nat, p_nat = int(t.get("nation", 0) or 0), int(p.get("nation", 0) or 0)
            policy_active_players += 1
            key = (to_id, 0, pid, pcode)
            if key in policy_map:
                policy_map[key]["activeOnTeam"] = True
                policy_map[key]["source"] = "Signed + Active" + (" (Benched)" if c.get("benched") else "")
            else:
                policy_map[key] = {
                    "teamId": to_id,
                    "teamName": t.get("name", f"Team #{to_id}"),
                    "teamNation": NATIONS.get(t_nat, f"#{t_nat}"),
                    "policyCode": pcode,
                    "policyLabel": "Only National" if pcode == "hb0" else "Only National Lang",
                    "policyDetail": pdetail,
                    "personType": "Player",
                    "personId": pid,
                    "personName": p.get("name", f"#{pid}"),
                    "personNation": NATIONS.get(p_nat, f"#{p_nat}"),
                    "age": int(p.get("age", 0) or 0),
                    "skill": _player_avg_skill(p),
                    "date": "Roster",
                    "route": "Current Roster" + (" (Benched)" if c.get("benched") else ""),
                    "purchasePrice": 0,
                    "activeOnTeam": True,
                    "source": "Active Contract",
                }

        for sid, c in active_staff_contracts.items():
            to_id = int(c.get("teamId", 0) or 0)
            if to_id not in strict_teams:
                continue
            s = self.staff_by_id.get(sid)
            if not s:
                continue
            t, hb = strict_teams[to_id]
            viol, pcode, pdetail = _check_policy(t, hb, s)
            if not viol:
                continue
            t_nat, s_nat = int(t.get("nation", 0) or 0), int(s.get("nation", 0) or 0)
            policy_active_staff += 1
            key = (to_id, 1, sid, pcode)
            if key in policy_map:
                policy_map[key]["activeOnTeam"] = True
                policy_map[key]["source"] = "Hired + Active"
            else:
                policy_map[key] = {
                    "teamId": to_id,
                    "teamName": t.get("name", f"Team #{to_id}"),
                    "teamNation": NATIONS.get(t_nat, f"#{t_nat}"),
                    "policyCode": pcode,
                    "policyLabel": "Only National" if pcode == "hb0" else "Only National Lang",
                    "policyDetail": pdetail,
                    "personType": "Staff",
                    "personId": sid,
                    "personName": s.get("name", f"#{sid}"),
                    "personNation": NATIONS.get(s_nat, f"#{s_nat}"),
                    "age": int(s.get("age", 0) or 0),
                    "skill": _staff_avg_skill(s),
                    "date": "Roster",
                    "route": "Current Staff",
                    "purchasePrice": 0,
                    "activeOnTeam": True,
                    "source": "Active Staff",
                }

        policy_violations = sorted(
            policy_map.values(),
            key=lambda r: (
                0 if r["personType"] == "Player" else 1,
                -r["purchasePrice"],
                0 if r["activeOnTeam"] else 1,
                r["teamName"],
            ),
        )

        return {
            "totalPlayerTransfers": len(raw_transfers),
            "flaggedTransfersCount": len(flagged_transfers),
            "benchedOverStarterCount": len(benched_crimes),
            "signedOverBetterBench": signed_over_better_bench,
            "signedThenBenched": signed_then_benched,
            "multiMovedEvents": multi_moved_count,
            "totalWastedSpend": total_spend_wasted,
            "benchedCrimes": benched_crimes,
            "flaggedTransfers": flagged_transfers[:150],
            "onlyNationalTeamCount": only_national_count,
            "onlyLangTeamCount": only_lang_count,
            "policyTxPlayers": policy_tx_players,
            "policyTxStaff": policy_tx_staff,
            "policyHb0Players": policy_hb0_players,
            "policyHb0Staff": policy_hb0_staff,
            "policyHb1Players": policy_hb1_players,
            "policyHb1Staff": policy_hb1_staff,
            "policyActivePlayers": policy_active_players,
            "policyActiveStaff": policy_active_staff,
            "policySpend": policy_spend,
            "policyViolations": policy_violations[:280],
            "rootCauses": [
                {
                    "title": "1. AI Hunts Transfer-Listed / Benched Vulture Targets",
                    "symbol": "TeamAI Transfer Evaluation",
                    "summary": "AI transfer scoring heavily discounts players sitting on another team's bench (`benched == true`) regardless of whether they actually upgrade the buyer's weakest role.",
                },
                {
                    "title": "2. AI Benches Its Own Better Starter for Worse New Signing",
                    "symbol": "Lineup Auto-Select / Contract Priority",
                    "summary": "Recent signings or specific role/nationality/salary flags cause the manager AI to drop higher-skilled starters onto the bench, leaving them stranded until another vulture signs them.",
                },
                {
                    "title": "3. 'Only National' & 'Only National Language' Ignored by AI",
                    "symbol": "owner.hiringBias == 0 / 1",
                    "summary": "Both strict national clubs (`hiringBias == 0`) and language-locked clubs (`hiringBias == 1`) ignore their own transfer policy and sign ineligible or non-fluent players.",
                },
            ],
        }

    def _showcase_stability(self) -> dict[str, Any]:
        """Measure post-transfer stint durations vs CS2 pro baselines (6-14 months avg, 6m low end) and team churn."""
        assert self.data is not None

        def _to_date(dt_obj: dict[str, Any]) -> dt.date | None:
            y = int(dt_obj.get("year", 0) or 0)
            m = int(dt_obj.get("month", 0) or 0)
            d = int(dt_obj.get("day", 0) or 0)
            if y <= 10 or m < 1 or m > 12:
                return None
            return dt.date(y, m, max(1, min(28, d)))

        all_dates: list[dt.date] = []
        team_player_dates: dict[tuple[int, int], list[dt.date]] = {}
        for m in self.data.get("matches", {}).get("matches", []):
            if not m.get("processingCompleted"):
                continue
            d = _to_date(m.get("datetime", {}))
            if not d:
                continue
            all_dates.append(d)
            t1, t2 = int(m.get("team1Id", 0) or 0), int(m.get("team2Id", 0) or 0)
            for pid in m.get("team1PlayerIds", []):
                team_player_dates.setdefault((int(pid), t1), []).append(d)
            for pid in m.get("team2PlayerIds", []):
                team_player_dates.setdefault((int(pid), t2), []).append(d)

        raw_th = self.data.get("transferHistories", {}).get("transferHistories", [])
        for x in raw_th:
            d = _to_date(x.get("datetime", {}))
            if d:
                all_dates.append(d)

        cur_date = max(all_dates) if all_dates else dt.date(2026, 12, 1)

        p_tx = [x for x in raw_th if int(x.get("personType", -1)) == 0 and _to_date(x.get("datetime", {})) is not None]
        p_tx.sort(key=lambda x: _to_date(x["datetime"]) or cur_date)

        tx_by_pid: dict[int, list[dict[str, Any]]] = {}
        churn: dict[int, dict[str, Any]] = {}

        def _ch_bucket(tid: int) -> dict[str, Any]:
            return churn.setdefault(tid, {"inP": 0, "outP": 0, "inS": 0, "spend": 0})

        for x in p_tx:
            pid = int(x.get("personId", 0))
            tx_by_pid.setdefault(pid, []).append(x)
            to_id = int(x.get("otherTeamId", 0) or 0)
            from_id = int(x.get("fromTeamId", 0) or 0)
            if to_id:
                b = _ch_bucket(to_id)
                b["inP"] += 1
                b["spend"] += int(x.get("purchasePrice", 0) or 0)
            if from_id:
                _ch_bucket(from_id)["outP"] += 1

        for x in raw_th:
            if int(x.get("personType", -1)) == 1:
                to_id = int(x.get("otherTeamId", 0) or 0)
                if to_id:
                    _ch_bucket(to_id)["inS"] += 1

        stints: list[dict[str, Any]] = []
        for pid, txs in tx_by_pid.items():
            p = self.players_by_id.get(pid)
            if not p:
                continue
            sk = _player_avg_skill(p)
            c = self.player_contract_by_pid.get(pid)
            for i, x in enumerate(txs):
                d_in = _to_date(x["datetime"])
                if not d_in:
                    continue
                to_id = int(x.get("otherTeamId", 0) or 0)
                to_name = self.teams_by_id.get(to_id, {}).get("name", f"Team #{to_id}")
                price = int(x.get("purchasePrice", 0) or 0)
                played = sorted(team_player_dates.get((pid, to_id), []))
                outcome = ""
                d_end = d_in
                active_days = 0
                held_days = 0

                if i + 1 < len(txs) and int(txs[i + 1].get("fromTeamId", 0) or 0) == to_id:
                    d_end = _to_date(txs[i + 1]["datetime"]) or d_in
                    active_days = max(0, (d_end - d_in).days)
                    held_days = active_days
                    next_name = self.teams_by_id.get(int(txs[i + 1].get("otherTeamId", 0) or 0), {}).get("name", "Next Club")
                    outcome = f"Sold/Moved -> {next_name}"
                elif c and int(c.get("teamId", 0) or 0) == to_id and c.get("benched"):
                    d_end = max(played) if played else d_in
                    active_days = max(0, (d_end - d_in).days)
                    held_days = max(0, (cur_date - d_in).days)
                    outcome = "Signed & Benched"
                elif not c or int(c.get("teamId", 0) or 0) != to_id:
                    d_end = max(played) if played else d_in
                    active_days = max(0, (d_end - d_in).days)
                    held_days = active_days
                    outcome = "Dropped / Left Roster"
                else:
                    # Still an active starter — check if < 180d open ongoing only? Skip ended metrics unless ended
                    continue

                active_months = round(active_days / 30.44, 1)
                pro_low_days = 180  # ~6 months (low end of 6-14 month CS2 pro average stint)
                stints.append(
                    {
                        "playerId": pid,
                        "playerName": p.get("name", f"Player #{pid}"),
                        "skill": round(sk, 2),
                        "teamId": to_id,
                        "teamName": to_name,
                        "fee": price,
                        "signDate": d_in.isoformat(),
                        "endDate": d_end.isoformat(),
                        "activeDays": active_days,
                        "activeMonths": active_months,
                        "heldDays": held_days,
                        "matchesPlayed": len(played),
                        "outcome": outcome,
                        "belowProLowEnd": active_days < pro_low_days,
                        "proLowDiffMonths": round(6.0 - active_months, 1),
                    }
                )

        stints.sort(key=lambda s: (s["activeDays"], -s["fee"]))

        completed_cnt = len(stints)
        sub6m_cnt = sum(1 for s in stints if s["activeDays"] < 180)
        sub3m_cnt = sum(1 for s in stints if s["activeDays"] < 90)
        days_list = sorted(s["activeDays"] for s in stints)
        avg_days = round(sum(days_list) / completed_cnt, 1) if completed_cnt else 0.0
        med_days = float(days_list[completed_cnt // 2]) if completed_cnt else 0.0
        avg_months = round(avg_days / 30.44, 1) if completed_cnt else 0.0
        med_months = round(med_days / 30.44, 1) if completed_cnt else 0.0

        # Active bench counts per team for churn table
        benched_by_tid: dict[int, int] = {}
        active_by_tid: dict[int, int] = {}
        for c in self.player_contract_by_pid.values():
            tid = int(c.get("teamId", 0) or 0)
            if c.get("benched"):
                benched_by_tid[tid] = benched_by_tid.get(tid, 0) + 1
            else:
                active_by_tid[tid] = active_by_tid.get(tid, 0) + 1

        team_churn_rows = []
        carousel_teams = 0
        for tid, st in churn.items():
            tot_p = st["inP"] + st["outP"]
            if tot_p >= 4:
                carousel_teams += 1
            if tot_p >= 2 or st["inS"] >= 4:
                team_churn_rows.append(
                    {
                        "teamId": tid,
                        "teamName": self.teams_by_id.get(tid, {}).get("name", f"Team #{tid}"),
                        "playersIn": st["inP"],
                        "playersOut": st["outP"],
                        "totalPlayerMoves": tot_p,
                        "staffIn": st["inS"],
                        "spend": st["spend"],
                        "startersNow": active_by_tid.get(tid, 0),
                        "benchedNow": benched_by_tid.get(tid, 0),
                    }
                )
        team_churn_rows.sort(key=lambda r: (-r["totalPlayerMoves"], -r["spend"], -r["staffIn"]))

        return {
            "completedStintsCount": completed_cnt,
            "sub6MonthsCount": sub6m_cnt,
            "sub6MonthsPct": round(sub6m_cnt * 100.0 / completed_cnt, 1) if completed_cnt else 0.0,
            "sub3MonthsCount": sub3m_cnt,
            "avgStintDays": avg_days,
            "avgStintMonths": avg_months,
            "medianStintDays": med_days,
            "medianStintMonths": med_months,
            "proLowEndMonths": 6.0,
            "proMedianRange": "8 - 10 months",
            "proFullRange": "6 - 14 months",
            "carouselTeamsCount": carousel_teams,
            "stints": stints[:150],
            "teamChurn": team_churn_rows[:120],
            "rootCauses": [
                {
                    "title": "1. Zero Post-Signing Protection / Sunk-Cost Memory",
                    "symbol": "TeamAI Bench / Transfer Trigger",
                    "summary": "After paying steep buyout fees ($125k-$400k+) for a player, AI immediately forgets the investment and benches or drops them weeks later with almost no matches played.",
                },
                {
                    "title": "2. Bench-Poaching Chain Reaction",
                    "symbol": "Revolving-Door Orgs (4-8+ moves/yr)",
                    "summary": "Because every team dumps decent starters onto the bench and vultures prioritize benched players, single teams burn through 5-8 player moves and 5-14 staff changes in one season, crushing average tenure well below the 6-month CS2 pro low end.",
                },
            ],
        }

    # ------------------------------------------------------------------
    # Team Strength Diff, Trophy Realism Audit, Matchup Lab & Market Radar
    # ------------------------------------------------------------------

    _PRACTICAL_KEYS = (
        "tracking", "sprayControl", "reactions", "crosshairPlacement", "flicks", "movement",
        "overview", "decisions", "composure", "teamwork", "consistency",
        "pistols", "smgs", "utility", "rifles", "snipers",
    )
    _PRACTICAL_IDS = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 17)
    _MECH_KEYS = ("tracking", "sprayControl", "reactions", "crosshairPlacement", "flicks", "movement")
    _MENTAL_KEYS = ("overview", "decisions", "composure", "consistency")
    _WEAPON_KEYS = ("pistols", "smgs", "rifles", "snipers", "utility")

    @staticmethod
    def _pearson_r(xs: list[float], ys: list[float]) -> float:
        n = len(xs)
        if n < 3 or n != len(ys):
            return 0.0
        mx = sum(xs) / n
        my = sum(ys) / n
        num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
        dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
        dy = math.sqrt(sum((y - my) ** 2 for y in ys))
        if dx <= 1e-12 or dy <= 1e-12:
            return 0.0
        return round(num / (dx * dy), 3)

    @staticmethod
    def _ols_fit(xs: list[float], ys: list[float]) -> tuple[float, float, float]:
        n = len(xs)
        if n < 3 or n != len(ys):
            return 0.0, 1.0, 0.0
        mx = sum(xs) / n
        my = sum(ys) / n
        sxx = sum((x - mx) ** 2 for x in xs)
        if sxx <= 1e-12:
            return 0.0, round(my, 4), 0.0
        slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
        intercept = my - slope * mx
        r = SaveSession._pearson_r(xs, ys)
        return round(slope, 4), round(intercept, 4), round(r * r, 3)

    @staticmethod
    def _gini(vals: list[float]) -> float:
        clean = sorted(max(0.0, float(v)) for v in vals)
        n = len(clean)
        tot = sum(clean)
        if n == 0 or tot <= 1e-12:
            return 0.0
        weighted = sum((2 * (i + 1) - n - 1) * v for i, v in enumerate(clean))
        return round(weighted / (n * tot), 3)

    @staticmethod
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

    def _player_practical_avg(self, p: dict[str, Any]) -> float:
        sk = p.get("skills") or {}
        return sum(float(sk.get(k, 0) or 0) for k in self._PRACTICAL_KEYS) / 16.0

    def _player_avg_pot(self, p: dict[str, Any]) -> float:
        pot = p.get("potential") or {}
        if isinstance(pot, dict) and "m_Keys" in pot and "m_Values" in pot:
            pmap = {int(k): float(v) for k, v in zip(pot["m_Keys"], pot["m_Values"])}
            vals = [pmap[sid] for sid in self._PRACTICAL_IDS if sid in pmap]
            if vals:
                return sum(vals) / len(vals)
        return self._player_practical_avg(p)

    @staticmethod
    def _person_fluent_langs(person: dict[str, Any]) -> set[int]:
        return {
            int(lg.get("languageId", 0) or 0)
            for lg in person.get("languagesSpoken", [])
            if int(lg.get("languageSkill", 0) or 0) >= 10
        }

    @staticmethod
    def _fmt_lang_set(lids: set[int]) -> str:
        if not lids:
            return "None"
        return ", ".join(sorted(LANGUAGES.get(lid, f"#{lid}") for lid in lids))

    def _infer_nation_req_langs(self) -> dict[int, set[int]]:
        """Infer each nation's dominant language(s) from native fluent players."""
        nat_counts: dict[int, dict[int, int]] = {}
        for p_obj in self.players_by_id.values():
            p_n = int(p_obj.get("nation", 0) or 0)
            if not p_n:
                continue
            for lg in p_obj.get("languagesSpoken", []):
                if int(lg.get("languageSkill", 0) or 0) >= 15:
                    lid = int(lg.get("languageId", 0) or 0)
                    if lid:
                        b = nat_counts.setdefault(p_n, {})
                        b[lid] = b.get(lid, 0) + 1
        req: dict[int, set[int]] = {}
        for p_n, cnts in nat_counts.items():
            ranked = sorted(cnts.items(), key=lambda z: -z[1])
            allowed = {ranked[0][0]}
            if len(ranked) > 1 and ranked[1][1] >= ranked[0][1] * 0.40:
                allowed.add(ranked[1][0])
            req[p_n] = allowed
        return req

    @staticmethod
    def _team_facility_score(team: dict[str, Any]) -> float:
        """Exact Team::GetFacilityGradeBackgroundScore average across all 6 facility tracks (0..100)."""
        std_keys = ("coffeeMachine", "recreation", "branding", "cable", "ventilation")
        total = 0.0
        for fk in std_keys:
            lvl = int(team.get(fk, 0) or 0)
            total += min(100.0, max(0.0, lvl * 25.0))
        acad_lvl = int(team.get("academy", 0) or 0)
        acad_map = {0: 0.0, 1: 25.0, 2: 25.0, 3: 50.0, 4: 50.0, 5: 75.0, 6: 75.0}
        total += acad_map.get(acad_lvl, 100.0 if acad_lvl >= 7 else 0.0)
        return round(total / 6.0, 1)

    @staticmethod
    def _team_cohesion_metrics(team: dict[str, Any]) -> tuple[float, float, float]:
        """Return (cohesionAvgPct, burnoutHealthPct, languageCohesionPct)."""
        coh = team.get("teamCohesion") or {}
        if not isinstance(coh, dict):
            return 0.0, 0.0, 0.0
        parts = [
            float(coh.get("cohesionFromTraining", 0.0) or 0.0),
            float(coh.get("cohesionFromBurnout", 0.0) or 0.0),
            float(coh.get("cohesionFromMentality", 0.0) or 0.0),
            float(coh.get("cohesionFromLanguage", 0.0) or 0.0),
            float(coh.get("cohesionFromLeadership", 0.0) or 0.0),
            float(coh.get("cohesionFromRelationships", 0.0) or 0.0),
        ]
        avg_pct = round((sum(parts) / len(parts)) * 100.0, 1)
        burnout_pct = round(parts[1] * 100.0, 1)
        lang_pct = round(parts[3] * 100.0, 1)
        return avg_pct, burnout_pct, lang_pct

    @staticmethod
    def _team_map_comforts(team: dict[str, Any], map_ids: list[int]) -> tuple[float, dict[int, int]]:
        """Replicate Team::GetTotalMapComfort(mapId) = clamp(genKnowledge + kPlayers + kTraining, 1, 100)."""
        gts = team.get("generalTactics") or []
        active_gt = next((g for g in gts if g.get("active")), gts[0] if gts else {})
        gen_k = float(active_gt.get("knowledge", 0.0) or 0.0)
        mt_by_id = {}
        for mt in team.get("mapTactics") or []:
            mid = int(mt.get("mapId", 0) or 0)
            if mid and (mid not in mt_by_id or mt.get("active")):
                mt_by_id[mid] = mt
        comforts: dict[int, int] = {}
        for mid in map_ids:
            mt = mt_by_id.get(mid)
            if mt:
                raw = int(gen_k) + int(mt.get("knowledgeFromPlayers", 0) or 0) + int(mt.get("knowledgeFromTraining", 0) or 0)
                comforts[mid] = max(1, min(100, raw))
            else:
                comforts[mid] = max(1, min(100, int(gen_k) or 50))
        avg_c = round(sum(comforts.values()) / len(comforts), 1) if comforts else 50.0
        return avg_c, comforts

    def get_strength_realism(self, year: int | None = None, focus_team_id: int | None = None) -> dict[str, Any]:
        """Compute Team Strength Diff, Multi-Trophy Realism Audit, Odds Calibration, and Data Science stats."""
        if self.data is None:
            return {"loaded": False}

        tmpl_names, _, map_names = self._stats_lookups()
        map_ids = sorted(map_names.keys())
        cur_dt = self.data.get("datetime", {}) or {}
        cur_year = int(cur_dt.get("year", 0) or 0)
        cur_month = int(cur_dt.get("month", 1) or 1)
        cur_day = int(cur_dt.get("day", 1) or 1)

        # Collect years with played matches or trophies
        years_set: set[int] = set()
        for m in self.data.get("matches", {}).get("matches", []):
            if any(mm.get("baseMatchRounds") for mm in m.get("matchMaps", [])):
                my = int((m.get("datetime") or {}).get("year", 0) or 0)
                if my:
                    years_set.add(my)
        for t in self.data["teams"]["teams"]:
            for th in t.get("trophyHistories") or []:
                ty = int(th.get("year", 0) or 0)
                if ty:
                    years_set.add(ty)

        target_year = year if year is not None else (cur_year if cur_year in years_set else (max(years_set) if years_set else cur_year))

        # 1. Per-player season rating from playerCareerStats for target_year
        p_rating_agg: dict[int, tuple[float, int]] = {}
        for row in self.data.get("playerCareerStats", {}).get("playerCareerStats", []):
            if int(row.get("year", 0) or 0) != target_year:
                continue
            mw = int(row.get("matchesWon", 0) or 0)
            ml = int(row.get("matchesLost", 0) or 0)
            mc = mw + ml
            if mc <= 0:
                continue
            pid = int(row.get("playerId", 0) or 0)
            prev_acc, prev_m = p_rating_agg.get(pid, (0.0, 0))
            p_rating_agg[pid] = (prev_acc + float(row.get("accumulativeRating", 0.0) or 0.0), prev_m + mc)

        def _p_year_rating(pid: int) -> float:
            acc, mc = p_rating_agg.get(pid, (0.0, 0))
            return round(acc / mc, 3) if mc > 0 else 0.0

        # 2. Match records, streaks, pre-match odds vs actual calibration in target_year
        team_match_rec: dict[int, dict[str, Any]] = {}
        buckets = [
            {"label": "50-55%", "lo": 0.50, "hi": 0.55, "wins": 0, "total": 0, "oddsSum": 0.0},
            {"label": "55-60%", "lo": 0.55, "hi": 0.60, "wins": 0, "total": 0, "oddsSum": 0.0},
            {"label": "60-65%", "lo": 0.60, "hi": 0.65, "wins": 0, "total": 0, "oddsSum": 0.0},
            {"label": "65-70%", "lo": 0.65, "hi": 0.70, "wins": 0, "total": 0, "oddsSum": 0.0},
            {"label": "70-80%", "lo": 0.70, "hi": 0.80, "wins": 0, "total": 0, "oddsSum": 0.0},
            {"label": "80-100%", "lo": 0.80, "hi": 1.01, "wins": 0, "total": 0, "oddsSum": 0.0},
        ]
        format_cal = {
            "BO1": {"wins": 0, "total": 0, "oddsSum": 0.0},
            "BO3": {"wins": 0, "total": 0, "oddsSum": 0.0},
            "BO5": {"wins": 0, "total": 0, "oddsSum": 0.0},
        }
        completed_matches: list[tuple[tuple[int, int, int, int], int, int, int, float, float, int, int]] = []
        for m in self.data.get("matches", {}).get("matches", []):
            match_maps = [mm for mm in m.get("matchMaps", []) if mm.get("baseMatchRounds")]
            if not match_maps:
                continue
            dt_obj = m.get("datetime") or {}
            if int(dt_obj.get("year", 0) or 0) != target_year:
                continue
            t1 = int(m.get("team1Id", 0) or 0)
            t2 = int(m.get("team2Id", 0) or 0)
            if not t1 or not t2:
                continue
            t1_maps = t2_maps = 0
            for mm in match_maps:
                rds = mm.get("baseMatchRounds", [])
                r1 = sum(1 for r in rds if r.get("winner") == t1)
                r2 = sum(1 for r in rds if r.get("winner") == t2)
                if r1 > r2:
                    t1_maps += 1
                else:
                    t2_maps += 1
            win_id = t1 if t1_maps > t2_maps else t2
            o1 = float(m.get("team1PreMatchOdds", 0.5) or 0.5)
            o2 = float(m.get("team2PreMatchOdds", 0.5) or 0.5)
            bo = int(m.get("numberOfMaps", len(match_maps)) or len(match_maps))
            completed_matches.append((self._match_date_key(dt_obj), t1, t2, win_id, o1, o2, t1_maps, t2_maps))

            if abs(o1 - o2) > 1e-6:
                fav_id = t1 if o1 > o2 else t2
                fav_o = max(o1, o2)
                fav_won = 1 if win_id == fav_id else 0
                for b in buckets:
                    if b["lo"] <= fav_o < b["hi"]:
                        b["wins"] += fav_won
                        b["total"] += 1
                        b["oddsSum"] += fav_o
                        break
                fmt = "BO5" if bo >= 5 else ("BO3" if bo == 3 else "BO1")
                format_cal[fmt]["wins"] += fav_won
                format_cal[fmt]["total"] += 1
                format_cal[fmt]["oddsSum"] += fav_o

        completed_matches.sort(key=lambda x: x[0])
        for _, t1, t2, win_id, o1, o2, m1, m2 in completed_matches:
            for tid_x, won_x, mw_x, ml_x, o_x in (
                (t1, win_id == t1, m1, m2, o1),
                (t2, win_id == t2, m2, m1, o2),
            ):
                rec = team_match_rec.setdefault(
                    tid_x,
                    {"wins": 0, "losses": 0, "mapsWon": 0, "mapsLost": 0, "oddsSum": 0.0, "curStreak": 0, "maxStreak": 0},
                )
                rec["mapsWon"] += mw_x
                rec["mapsLost"] += ml_x
                rec["oddsSum"] += o_x
                if won_x:
                    rec["wins"] += 1
                    rec["curStreak"] += 1
                    if rec["curStreak"] > rec["maxStreak"]:
                        rec["maxStreak"] = rec["curStreak"]
                else:
                    rec["losses"] += 1
                    rec["curStreak"] = 0

        # 3. Completed tournaments & trophies in target_year
        tourn_by_id_raw = {t["id"]: t for t in self.data.get("tournaments", {}).get("tournaments", [])}

        # Build full trophy haul per team (from trophyHistories, falling back to rankingPoints if needed)
        trophies_by_team: dict[int, list[dict[str, Any]]] = {}
        for t in self.data["teams"]["teams"]:
            tid = t["id"]
            t_list: list[dict[str, Any]] = []
            for th in t.get("trophyHistories") or []:
                if int(th.get("year", 0) or 0) != target_year:
                    continue
                th_tid = int(th.get("tournamentId", 0) or 0)
                t_obj = tourn_by_id_raw.get(th_tid, {})
                tmpl = int(th.get("tournamentTemplate", t_obj.get("template", -1)))
                rep = int(t_obj.get("reputation", 1) or 1)
                win_names = [self.players_by_id[pid]["name"] for pid in (th.get("winningPlayerIds") or []) if pid in self.players_by_id]
                t_list.append(
                    {
                        "tournamentId": th_tid,
                        "tournamentName": t_obj.get("name") or tmpl_names.get(tmpl, f"Event #{tmpl}"),
                        "reputation": rep,
                        "isTier1": rep >= 16,
                        "seasonPart": "Spring" if th.get("spring") else "Fall",
                        "winningRoster": win_names,
                    }
                )
            if not t_list:
                # Fallback to rankingPoints place==1 for saves where trophyHistories weren't stored
                for rp in t.get("rankingPoints") or []:
                    dg = rp.get("dateGranted") or {}
                    if int(dg.get("year", 0) or 0) == target_year and int(rp.get("tournamentPlacement", 0) or 0) == 1:
                        tmpl = int(rp.get("tournamentTemplate", -1))
                        t_list.append(
                            {
                                "tournamentId": 0,
                                "tournamentName": tmpl_names.get(tmpl, f"Event #{tmpl}"),
                                "reputation": 16 if int(rp.get("originalPoints", 0) or 0) >= 400 else 10,
                                "isTier1": int(rp.get("originalPoints", 0) or 0) >= 400,
                                "seasonPart": "Spring" if int(dg.get("month", 7) or 7) <= 6 else "Fall",
                                "winningRoster": [],
                            }
                        )
            if t_list:
                trophies_by_team[tid] = t_list

        total_tier1_completed = sum(
            1 for tlist in trophies_by_team.values() for tr in tlist if tr["isTier1"]
        )

        # 4. Compute Team Strength metrics for every team with active starters
        user_team_id = int((self.data.get("profile") or {}).get("team", 0) or 0)
        team_strengths: list[dict[str, Any]] = []
        for t in self.data["teams"]["teams"]:
            tid = t["id"]
            contracts = self.get_team_player_contracts(tid)
            starters = [self.players_by_id[c["playerId"]] for c in contracts if not c.get("benched") and c["playerId"] in self.players_by_id]
            benched = [self.players_by_id[c["playerId"]] for c in contracts if c.get("benched") and c["playerId"] in self.players_by_id]
            if not starters:
                continue

            starter_profiles = []
            prac_totals = []
            mech_vals = []
            mental_vals = []
            wpn_vals = []
            awp_scores = []
            igl_scores = []
            for p in starters:
                sk = p.get("skills") or {}
                ptot = sum(float(sk.get(k, 0) or 0) for k in self._PRACTICAL_KEYS)
                pavg = ptot / 16.0
                mech = sum(float(sk.get(k, 0) or 0) for k in self._MECH_KEYS) / len(self._MECH_KEYS)
                ment = sum(float(sk.get(k, 0) or 0) for k in self._MENTAL_KEYS) / len(self._MENTAL_KEYS)
                wpn = sum(float(sk.get(k, 0) or 0) for k in self._WEAPON_KEYS) / len(self._WEAPON_KEYS)
                awp_s = float(sk.get("snipers", 0) or 0) * 0.70 + float(sk.get("reactions", 0) or 0) * 0.15 + float(sk.get("composure", 0) or 0) * 0.15
                igl_s = float(sk.get("overview", 0) or 0) * 0.35 + float(sk.get("decisions", 0) or 0) * 0.35 + float(sk.get("leadership", 0) or 0) * 0.30
                prac_totals.append(ptot)
                mech_vals.append(mech)
                mental_vals.append(ment)
                wpn_vals.append(wpn)
                awp_scores.append(awp_s)
                igl_scores.append(igl_s)
                starter_profiles.append(
                    {
                        "playerId": p["id"],
                        "name": p.get("name", ""),
                        "age": p.get("age", 0),
                        "avgSkill": round(pavg, 2),
                        "practicalTotal": round(ptot, 1),
                        "mechanics": round(mech, 2),
                        "mental": round(ment, 2),
                        "weapons": round(wpn, 2),
                        "awpScore": round(awp_s, 2),
                        "iglScore": round(igl_s, 2),
                        "yearRating": _p_year_rating(p["id"]),
                    }
                )
            starter_profiles.sort(key=lambda r: -r["avgSkill"])

            team_prac_total = sum(prac_totals) / len(prac_totals)
            avg_skill = team_prac_total / 16.0
            power_index = max(1.0, team_prac_total) ** 2.8
            best_star = starter_profiles[0]
            weakest_link = starter_profiles[-1]

            best_bench_p = max(
                benched,
                key=lambda bp: sum(float((bp.get("skills") or {}).get(k, 0) or 0) for k in self._PRACTICAL_KEYS) / 16.0,
                default=None,
            )
            best_bench_skill = (
                round(sum(float((best_bench_p.get("skills") or {}).get(k, 0) or 0) for k in self._PRACTICAL_KEYS) / 16.0, 2)
                if best_bench_p else 0.0
            )
            bench_waste = round(max(0.0, best_bench_skill - weakest_link["avgSkill"]), 2)

            staff_cs = self.get_team_staff_contracts(tid)
            staff_objs = [self.staff_by_id[sc["staffId"]] for sc in staff_cs if sc["staffId"] in self.staff_by_id]
            staff_avg = round(sum(_staff_avg_skill(so) for so in staff_objs) / len(staff_objs), 2) if staff_objs else 0.0

            coh_avg, burnout_pct, lang_pct = self._team_cohesion_metrics(t)
            map_avg, map_comforts = self._team_map_comforts(t, map_ids)
            fac_score = self._team_facility_score(t)
            wages = sum(int(c.get("salaryYear", 0) or 0) for c in contracts) + sum(int(sc.get("salaryYear", 0) or 0) for sc in staff_cs)

            rhist = t.get("rankingHistory") or []
            world_rank = int(rhist[-1]) if rhist else 0
            rec = team_match_rec.get(tid, {})
            mw = rec.get("wins", 0)
            ml = rec.get("losses", 0)
            mtot = mw + ml
            win_pct = round(mw * 100.0 / mtot, 1) if mtot else 0.0
            avg_odds = round((rec.get("oddsSum", 0.0) / mtot) * 100.0, 1) if mtot else 0.0
            map_w = rec.get("mapsWon", 0)
            map_l = rec.get("mapsLost", 0)
            map_tot = map_w + map_l

            trophies = trophies_by_team.get(tid, [])
            tier1_trophies = sum(1 for tr in trophies if tr["isTier1"])

            team_strengths.append(
                {
                    "teamId": tid,
                    "name": t.get("name", ""),
                    "nationName": NATIONS.get(t.get("nation", 0), ""),
                    "worldRank": world_rank,
                    "reputation": int(t.get("reputation", 1) or 1),
                    "isUserTeam": tid == user_team_id,
                    "starterCount": len(starters),
                    "avgSkill": round(avg_skill, 2),
                    "practicalSkillTotal": round(team_prac_total, 1),
                    "powerIndex": power_index,
                    "mechanicsAvg": round(sum(mech_vals) / len(mech_vals), 2),
                    "mentalAvg": round(sum(mental_vals) / len(mental_vals), 2),
                    "weaponsAvg": round(sum(wpn_vals) / len(wpn_vals), 2),
                    "bestAwp": round(max(awp_scores), 2),
                    "bestIgl": round(max(igl_scores), 2),
                    "bestStarSkill": best_star["avgSkill"],
                    "bestStarName": best_star["name"],
                    "weakestLinkSkill": weakest_link["avgSkill"],
                    "weakestLinkName": weakest_link["name"],
                    "spread": round(best_star["avgSkill"] - weakest_link["avgSkill"], 2),
                    "benchedCount": len(benched),
                    "bestBenchedSkill": best_bench_skill,
                    "bestBenchedName": best_bench_p.get("name", "") if best_bench_p else "",
                    "benchWasteGap": bench_waste,
                    "staffCount": len(staff_objs),
                    "staffAvgSkill": staff_avg,
                    "cohesionAvg": coh_avg,
                    "burnoutHealth": burnout_pct,
                    "languageCohesion": lang_pct,
                    "mapReadinessAvg": map_avg,
                    "mapComforts": map_comforts,
                    "facilityScore": fac_score,
                    "balance": int((t.get("teamFinances") or {}).get("currentBalance", 0) or 0),
                    "annualWages": wages,
                    "matches": mtot,
                    "wins": mw,
                    "losses": ml,
                    "winPct": win_pct,
                    "mapsWon": map_w,
                    "mapsLost": map_l,
                    "mapWinPct": round(map_w * 100.0 / map_tot, 1) if map_tot else 0.0,
                    "avgPreMatchOdds": avg_odds,
                    "oddsDefiancePp": round(win_pct - avg_odds, 1) if mtot else 0.0,
                    "maxWinStreak": rec.get("maxStreak", 0),
                    "trophiesCount": len(trophies),
                    "tier1TrophiesCount": tier1_trophies,
                    "trophySharePct": round(tier1_trophies * 100.0 / total_tier1_completed, 1) if total_tier1_completed else 0.0,
                    "trophies": trophies,
                    "starters": starter_profiles,
                }
            )

        team_strengths.sort(key=lambda r: (r["worldRank"] == 0, r["worldRank"] if r["worldRank"] > 0 else 9999, -r["avgSkill"]))

        ranked_teams = [r for r in team_strengths if r["worldRank"] > 0]
        rank1 = ranked_teams[0] if ranked_teams else (max(team_strengths, key=lambda r: r["avgSkill"]) if team_strengths else None)
        top10 = ranked_teams[:10] if ranked_teams else team_strengths[:10]
        top10_avg_skill = sum(r["avgSkill"] for r in top10) / len(top10) if top10 else 0.0

        for r in team_strengths:
            r["gapVsRank1"] = round(r["avgSkill"] - rank1["avgSkill"], 2) if rank1 else 0.0
            r["gapVsTop10Avg"] = round(r["avgSkill"] - top10_avg_skill, 2)
            r["gameOddsVsRank1"] = round(r["powerIndex"] * 100.0 / (r["powerIndex"] + rank1["powerIndex"]), 1) if rank1 else 50.0

        # 5. Odds Calibration output
        cal_rows = []
        for b in buckets:
            tot = b["total"]
            exp_pct = round((b["oddsSum"] / tot) * 100.0, 1) if tot else 0.0
            act_pct = round((b["wins"] / tot) * 100.0, 1) if tot else 0.0
            cal_rows.append(
                {
                    "bucket": b["label"],
                    "matches": tot,
                    "wins": b["wins"],
                    "expectedPct": exp_pct,
                    "actualPct": act_pct,
                    "diffPp": round(act_pct - exp_pct, 1) if tot else 0.0,
                }
            )
        fmt_rows = []
        for fmt_name in ("BO1", "BO3", "BO5"):
            fd = format_cal[fmt_name]
            tot = fd["total"]
            exp_pct = round((fd["oddsSum"] / tot) * 100.0, 1) if tot else 0.0
            act_pct = round((fd["wins"] / tot) * 100.0, 1) if tot else 0.0
            fmt_rows.append({"format": fmt_name, "matches": tot, "expectedPct": exp_pct, "actualPct": act_pct, "diffPp": round(act_pct - exp_pct, 1) if tot else 0.0})

        # 6. Trophy Realism Audit for focus team (specified focus_team_id, or top trophy winner, or rank #1)
        by_tid = {r["teamId"]: r for r in team_strengths}
        top_trophy_team = max(team_strengths, key=lambda r: (r["trophiesCount"], r["winPct"], r["avgSkill"]), default=None)
        focus_team = by_tid.get(focus_team_id or 0) or top_trophy_team or rank1

        realism_audit: dict[str, Any] = {}
        if focus_team:
            rivals = [r for r in ranked_teams[:10] if r["teamId"] != focus_team["teamId"]]
            rival_avg_skill = round(sum(r["avgSkill"] for r in rivals) / len(rivals), 2) if rivals else 0.0
            rival_coh_avg = round(sum(r["cohesionAvg"] for r in rivals) / len(rivals), 1) if rivals else 0.0
            rival_map_avg = round(sum(r["mapReadinessAvg"] for r in rivals) / len(rivals), 1) if rivals else 0.0
            rival_staff_avg = round(sum(r["staffAvgSkill"] for r in rivals) / len(rivals), 2) if rivals else 0.0
            rival_bal_med = sorted(r["balance"] for r in rivals)[len(rivals) // 2] if rivals else 0
            rivals_benching_better = sum(1 for r in rivals if r["benchWasteGap"] > 0.2)
            rivals_below_floor = sum(1 for r in rivals if r["weakestLinkSkill"] < focus_team["weakestLinkSkill"])

            tr_cnt = focus_team["trophiesCount"]
            win_pct = focus_team["winPct"]
            share_pct = focus_team["trophySharePct"]
            if tr_cnt >= 10 or win_pct >= 88.0 or share_pct >= 55.0:
                verdict = "UNREALISTIC — Engine Snowball Artifact"
                verdict_level = "bad"
            elif tr_cnt >= 7 or win_pct >= 82.0:
                verdict = "BORDERLINE — Historic Superteam Era"
                verdict_level = "warn"
            else:
                verdict = "REALISTIC — Pro Tier-1 Parity"
                verdict_level = "ok"

            realism_audit = {
                "focusTeamId": focus_team["teamId"],
                "focusTeamName": focus_team["name"],
                "verdict": verdict,
                "verdictLevel": verdict_level,
                "trophiesWon": tr_cnt,
                "tier1TrophiesWon": focus_team["tier1TrophiesCount"],
                "totalTier1Completed": total_tier1_completed,
                "trophySharePct": share_pct,
                "wins": focus_team["wins"],
                "losses": focus_team["losses"],
                "winPct": win_pct,
                "avgPreMatchOdds": focus_team["avgPreMatchOdds"],
                "oddsDefiancePp": focus_team["oddsDefiancePp"],
                "maxWinStreak": focus_team["maxWinStreak"],
                "avgSkill": focus_team["avgSkill"],
                "rivalTop10AvgSkill": rival_avg_skill,
                "skillEdgeVsTop10": round(focus_team["avgSkill"] - rival_avg_skill, 2),
                "proBenchmarks": {
                    "proPeakTitlesYr": "4 - 7 Big Events",
                    "proPeakMatchWinPct": "72% - 82%",
                    "proPeakSweepShare": "25% - 40%",
                    "proBestExamples": "2018 Astralis / 2024 Spirit / 2025 Vitality",
                },
                "factors": [
                    {
                        "title": "1. Round -> Map -> BO3 Probability Compounding",
                        "summary": f"{focus_team['name']} averages {focus_team['avgPreMatchOdds']}% pre-match odds (MiscFunctions::GetOddsOfWinning skill^2.8), yet wins {win_pct}% of matches (+{focus_team['oddsDefiancePp']}pp defiance). Across the whole save, 60-65% favorites actually win {cal_rows[2]['actualPct']}% and 70-80% favorites win {cal_rows[4]['actualPct']}%.",
                    },
                    {
                        "title": "2. Weakest-Link Floor & Superteam Stacking",
                        "summary": f"{focus_team['name']}'s weakest starter ({focus_team['weakestLinkName']} {focus_team['weakestLinkSkill']}) beats the weakest starter on {rivals_below_floor}/{len(rivals)} Top-10 rivals, and even beats several Top-10 team averages ({rival_avg_skill}).",
                    },
                    {
                        "title": "3. AI Bench Sabotage & Transfer Mistakes",
                        "summary": f"{rivals_benching_better}/{len(rivals)} Top-10 AI rivals are leaving a stronger player on the bench or churning rosters mid-season, gifting free series consistency to a stable 5-man core.",
                    },
                    {
                        "title": "4. Off-Server Edge (Cohesion, Map Prep & Staff)",
                        "summary": f"{focus_team['name']} holds {focus_team['cohesionAvg']}% cohesion (rivals avg {rival_coh_avg}%), {focus_team['mapReadinessAvg']} map comfort (rivals {rival_map_avg}), and {focus_team['staffAvgSkill']} staff avg (rivals {rival_staff_avg}).",
                    },
                    {
                        "title": "5. Near-Zero Tournament Burnout & Wealth Snowball",
                        "summary": f"Even after {focus_team['matches']} matches and {tr_cnt} trophy runs, {focus_team['name']} sits at {focus_team['burnoutHealth']}% burnout health with ${focus_team['balance']:,} cash (Top-10 rival median ${rival_bal_med:,}) to retain 18+ skill superstars.",
                    },
                ],
                "leagueTrophyTable": sorted(
                    [
                        {
                            "teamId": r["teamId"],
                            "name": r["name"],
                            "worldRank": r["worldRank"],
                            "avgSkill": r["avgSkill"],
                            "trophiesCount": r["trophiesCount"],
                            "tier1TrophiesCount": r["tier1TrophiesCount"],
                            "trophySharePct": r["trophySharePct"],
                            "winPct": r["winPct"],
                            "maxWinStreak": r["maxWinStreak"],
                        }
                        for r in team_strengths if r["trophiesCount"] > 0 or (r["worldRank"] and r["worldRank"] <= 10)
                    ],
                    key=lambda x: (-x["trophiesCount"], -x["winPct"], x["worldRank"] or 9999),
                )[:20],
            }

        # 7. Data Science Lab: Skill -> Rating Regression, Age Curve, Parity/Gini & Nation Meta
        rated_pool: list[dict[str, Any]] = []
        rank_by_tid = {r["teamId"]: (r["worldRank"] if r["worldRank"] > 0 else 200) for r in team_strengths}
        for pid, (acc, mc) in p_rating_agg.items():
            p = self.players_by_id.get(pid)
            if not p or mc < 6:
                continue
            avg_sk = self._player_practical_avg(p)
            c = self.player_contract_by_pid.get(pid)
            tid = int(c["teamId"]) if c else 0
            rated_pool.append(
                {
                    "playerId": pid,
                    "name": p.get("name", ""),
                    "age": int(p.get("age", 0) or 0),
                    "teamId": tid,
                    "teamName": self.teams_by_id[tid]["name"] if tid in self.teams_by_id else "Free Agent",
                    "teamRank": rank_by_tid.get(tid, 200),
                    "avgSkill": round(avg_sk, 2),
                    "matches": mc,
                    "actualRating": round(acc / mc, 3),
                    "skills": p.get("skills") or {},
                }
            )
        if len(rated_pool) < 15:
            # Early-season fallback to >=1 match if save just rolled over year
            rated_pool = []
            for pid, (acc, mc) in p_rating_agg.items():
                p = self.players_by_id.get(pid)
                if not p or mc < 1:
                    continue
                avg_sk = self._player_practical_avg(p)
                c = self.player_contract_by_pid.get(pid)
                tid = int(c["teamId"]) if c else 0
                rated_pool.append(
                    {
                        "playerId": pid,
                        "name": p.get("name", ""),
                        "age": int(p.get("age", 0) or 0),
                        "teamId": tid,
                        "teamName": self.teams_by_id[tid]["name"] if tid in self.teams_by_id else "Free Agent",
                        "teamRank": rank_by_tid.get(tid, 200),
                        "avgSkill": round(avg_sk, 2),
                        "matches": mc,
                        "actualRating": round(acc / mc, 3),
                        "skills": p.get("skills") or {},
                    }
                )

        ys_rat = [r["actualRating"] for r in rated_pool]
        skill_correlations: list[dict[str, Any]] = []
        if len(rated_pool) >= 5:
            skill_correlations.append(
                {
                    "key": "avgSkill",
                    "label": "Practical Avg Skill (16)",
                    "group": "Composite",
                    "r": self._pearson_r([r["avgSkill"] for r in rated_pool], ys_rat),
                }
            )
            for sk_meta in PLAYER_SKILLS:
                skey = sk_meta["key"]
                xs = [float(r["skills"].get(skey, 0) or 0) for r in rated_pool]
                skill_correlations.append(
                    {
                        "key": skey,
                        "label": sk_meta["label"],
                        "group": sk_meta["group"],
                        "r": self._pearson_r(xs, ys_rat),
                    }
                )
            skill_correlations.append(
                {
                    "key": "age",
                    "label": "Player Age",
                    "group": "Meta",
                    "r": self._pearson_r([float(r["age"]) for r in rated_pool], ys_rat),
                }
            )
            skill_correlations.append(
                {
                    "key": "teamRank",
                    "label": "Team World Rank #",
                    "group": "Meta",
                    "r": self._pearson_r([float(r["teamRank"]) for r in rated_pool], ys_rat),
                }
            )
            skill_correlations.sort(key=lambda c: -abs(c["r"]))

        ols_slope, ols_intercept, ols_r2 = self._ols_fit([r["avgSkill"] for r in rated_pool], ys_rat)
        residuals_list = []
        for r in rated_pool:
            exp_rat = round(ols_slope * r["avgSkill"] + ols_intercept, 3)
            resid = round(r["actualRating"] - exp_rat, 3)
            residuals_list.append(
                {
                    "playerId": r["playerId"],
                    "name": r["name"],
                    "age": r["age"],
                    "teamId": r["teamId"],
                    "teamName": r["teamName"],
                    "avgSkill": r["avgSkill"],
                    "matches": r["matches"],
                    "actualRating": r["actualRating"],
                    "expectedRating": exp_rat,
                    "residual": resid,
                }
            )
        overperformers = sorted(residuals_list, key=lambda x: (-x["residual"], -x["actualRating"]))[:15]
        underperformers = sorted(residuals_list, key=lambda x: (x["residual"], x["actualRating"]))[:15]

        # Empirical Age Curve across all players + ratings from p_rating_agg
        age_brackets = [
            ("<=18", 0, 18),
            ("19-20", 19, 20),
            ("21-22", 21, 22),
            ("23-24", 23, 24),
            ("25-26", 25, 26),
            ("27-28", 27, 28),
            ("29+", 29, 99),
        ]
        age_curve: list[dict[str, Any]] = []
        for b_lbl, alo, ahi in age_brackets:
            grp_ps = [p for p in self.players_by_id.values() if alo <= int(p.get("age", 0) or 0) <= ahi]
            if not grp_ps:
                continue
            sk_vals = [self._player_practical_avg(p) for p in grp_ps]
            pot_vals = [self._player_avg_pot(p) for p in grp_ps]
            r_vals = [_p_year_rating(p["id"]) for p in grp_ps if p_rating_agg.get(p["id"], (0.0, 0))[1] >= 6]
            mean_sk = round(sum(sk_vals) / len(sk_vals), 2)
            mean_pot = round(sum(pot_vals) / len(pot_vals), 2)
            age_curve.append(
                {
                    "bracket": b_lbl,
                    "count": len(grp_ps),
                    "avgSkill": mean_sk,
                    "avgPot": mean_pot,
                    "headroom": round(mean_pot - mean_sk, 2),
                    "ratedCount": len(r_vals),
                    "avgRating": round(sum(r_vals) / len(r_vals), 3) if r_vals else 0.0,
                }
            )

        # Parity, Gini & Distributions + Team Factor Correlations + Nation Talent Meta
        team_skills_all = [r["avgSkill"] for r in team_strengths]
        player_skills_all = [self._player_practical_avg(p) for p in self.players_by_id.values()]
        team_wages_all = [float(r["annualWages"]) for r in team_strengths if r["annualWages"] > 0]
        team_bal_all = [max(0.0, float(r["balance"])) for r in team_strengths]
        distributions = {
            "teamSkill": {"gini": self._gini(team_skills_all), **self._percentiles(team_skills_all)},
            "playerSkill": {"gini": self._gini(player_skills_all), **self._percentiles(player_skills_all)},
            "teamWages": {"gini": self._gini(team_wages_all), **self._percentiles(team_wages_all)},
            "teamBalance": {"gini": self._gini(team_bal_all), **self._percentiles(team_bal_all)},
        }

        active_teams = [r for r in team_strengths if r["matches"] >= 8]
        ys_win = [float(r["winPct"]) for r in active_teams]
        team_factor_corrs = []
        for fkey, flbl in (
            ("avgSkill", "Roster Avg Skill"),
            ("weakestLinkSkill", "Weakest-Link Floor"),
            ("bestStarSkill", "Best Star Peak"),
            ("mapReadinessAvg", "Map Comfort Avg"),
            ("cohesionAvg", "Team Cohesion %"),
            ("staffAvgSkill", "Coaching Staff Avg"),
            ("facilityScore", "Facility Score"),
            ("annualWages", "Annual Payroll ($)"),
        ):
            team_factor_corrs.append(
                {
                    "key": fkey,
                    "label": flbl,
                    "r": self._pearson_r([float(r[fkey]) for r in active_teams], ys_win),
                }
            )
        team_factor_corrs.sort(key=lambda x: -abs(x["r"]))

        nation_acc: dict[int, dict[str, Any]] = {}
        for p in self.players_by_id.values():
            nid = int(p.get("nation", 0) or 0)
            if not nid:
                continue
            sk = self._player_practical_avg(p)
            pot = self._player_avg_pot(p)
            entry = nation_acc.setdefault(nid, {"skills": [], "pots": [], "ratings": [], "elite": 0})
            entry["skills"].append(sk)
            entry["pots"].append(pot)
            if sk >= 16.0:
                entry["elite"] += 1
            if p_rating_agg.get(p["id"], (0.0, 0))[1] >= 6:
                entry["ratings"].append(_p_year_rating(p["id"]))
        nation_meta = []
        for nid, info in nation_acc.items():
            cnt = len(info["skills"])
            if cnt < 10:
                continue
            nation_meta.append(
                {
                    "nationId": nid,
                    "nationName": NATIONS.get(nid, f"Nation #{nid}"),
                    "playerCount": cnt,
                    "elite16Plus": info["elite"],
                    "avgSkill": round(sum(info["skills"]) / cnt, 2),
                    "avgPot": round(sum(info["pots"]) / cnt, 2),
                    "avgRating": round(sum(info["ratings"]) / len(info["ratings"]), 3) if info["ratings"] else 0.0,
                }
            )
        nation_meta.sort(key=lambda x: (-x["elite16Plus"], -x["avgSkill"], -x["playerCount"]))

        cur_days_approx = cur_year * 365 + (cur_month - 1) * 30 + cur_day
        market_radar = self._build_market_radar(p_rating_agg, cur_days_approx)

        return {
            "loaded": True,
            "year": target_year,
            "years": sorted(years_set, reverse=True),
            "mapsMeta": [{"mapId": mid, "name": map_names[mid]} for mid in map_ids],
            "rank1Skill": rank1["avgSkill"] if rank1 else 0.0,
            "top10AvgSkill": round(top10_avg_skill, 2),
            "teamStrengths": team_strengths,
            "oddsCalibration": cal_rows,
            "formatCalibration": fmt_rows,
            "trophyRealism": realism_audit,
            "regression": {
                "sampleSize": len(rated_pool),
                "olsModel": {"slope": ols_slope, "intercept": ols_intercept, "r2": ols_r2},
                "skillCorrelations": skill_correlations,
                "overperformers": overperformers,
                "underperformers": underperformers,
                "ageCurve": age_curve,
            },
            "parity": {
                "teamSampleSize": len(active_teams),
                "distributions": distributions,
                "teamFactorCorrelations": team_factor_corrs,
                "nationMeta": nation_meta[:20],
            },
            "marketRadar": market_radar,
        }

    # ------------------------------------------------------------------
    # Manager Helper Lab: Market Radar, Roster Optimizer, Replacement Finder, Wonderkids
    # ------------------------------------------------------------------

    @staticmethod
    def _classify_player_role(sk: dict[str, Any]) -> tuple[str, float, float, float]:
        """Return (bestRoleLabel, awpScore, iglScore, entryScore)."""
        awp_s = float(sk.get("snipers", 0) or 0) * 0.68 + float(sk.get("reactions", 0) or 0) * 0.16 + float(sk.get("composure", 0) or 0) * 0.16
        igl_s = float(sk.get("overview", 0) or 0) * 0.35 + float(sk.get("decisions", 0) or 0) * 0.35 + float(sk.get("leadership", 0) or 0) * 0.30
        entry_s = float(sk.get("aggression", 0) or 0) * 0.35 + float(sk.get("reactions", 0) or 0) * 0.25 + float(sk.get("flicks", 0) or 0) * 0.20 + float(sk.get("movement", 0) or 0) * 0.20
        sup_s = float(sk.get("utility", 0) or 0) * 0.40 + float(sk.get("teamwork", 0) or 0) * 0.35 + float(sk.get("consistency", 0) or 0) * 0.25
        rif_s = float(sk.get("rifles", 0) or 0) * 0.45 + float(sk.get("sprayControl", 0) or 0) * 0.30 + float(sk.get("crosshairPlacement", 0) or 0) * 0.25
        if float(sk.get("snipers", 0) or 0) >= 15.0 and awp_s >= rif_s:
            role = "AWPer"
        elif igl_s >= 14.5 and float(sk.get("leadership", 0) or 0) >= 13.0 and igl_s >= max(entry_s, rif_s) - 1.5:
            role = "IGL"
        elif entry_s >= max(rif_s, sup_s) and float(sk.get("aggression", 0) or 0) >= 14.0:
            role = "Entry"
        elif sup_s >= rif_s:
            role = "Support"
        else:
            role = "Rifler"
        return role, round(awp_s, 2), round(igl_s, 2), round(entry_s, 2)

    def _build_market_radar(
        self,
        p_rating_agg: dict[int, tuple[float, int]],
        cur_days_approx: int,
    ) -> dict[str, list[dict[str, Any]]]:
        """Build Bargains, Overpaid, Expiring, and Free Agent radar lists."""
        def _yr_rat(pid: int) -> float:
            acc, mc = p_rating_agg.get(pid, (0.0, 0))
            return round(acc / mc, 3) if mc > 0 else 0.0

        all_contracted_rows = []
        tier_buckets: dict[int, list[int]] = {}
        for c in self.data["playerContracts"]["playerContracts"]:
            pid = int(c.get("playerId", 0) or 0)
            p = self.players_by_id.get(pid)
            if not p:
                continue
            p_avg = self._player_practical_avg(p)
            sal = int(c.get("salaryYear", 0) or 0)
            tier_key = int(p_avg // 2)
            if sal > 0:
                tier_buckets.setdefault(tier_key, []).append(sal)
            all_contracted_rows.append((c, p, round(p_avg, 2)))

        tier_median: dict[int, int] = {}
        for tk, sals in tier_buckets.items():
            s_sorted = sorted(sals)
            tier_median[tk] = s_sorted[len(s_sorted) // 2] if s_sorted else 0

        bargains: list[dict[str, Any]] = []
        overpaid: list[dict[str, Any]] = []
        expiring: list[dict[str, Any]] = []
        for c, p, p_avg in all_contracted_rows:
            pid = p["id"]
            tid = int(c.get("teamId", 0) or 0)
            tname = self.teams_by_id.get(tid, {}).get("name", f"Team #{tid}")
            sal = int(c.get("salaryYear", 0) or 0)
            med_sal = tier_median.get(int(p_avg // 2), sal) or max(sal, 1)
            yr_rat = _yr_rat(pid)
            benched = bool(c.get("benched", False))
            ed = c.get("endDate") or {}
            ed_yr = int(ed.get("year", 0) or 0)
            ed_mo = int(ed.get("month", 1) or 1)
            ed_day = int(ed.get("day", 1) or 1)
            months_left = round(((ed_yr * 365 + (ed_mo - 1) * 30 + ed_day) - cur_days_approx) / 30.4375, 1) if ed_yr else 99.0
            role, _, _, _ = self._classify_player_role(p.get("skills") or {})
            row = {
                "playerId": pid,
                "name": p.get("name", ""),
                "age": p.get("age", 0),
                "nationName": NATIONS.get(p.get("nation", 0), ""),
                "teamId": tid,
                "teamName": tname,
                "bestRole": role,
                "avgSkill": p_avg,
                "avgPot": round(self._player_avg_pot(p), 2),
                "yearRating": yr_rat,
                "salaryYear": sal,
                "peerMedianSalary": med_sal,
                "ratio": round(sal / max(med_sal, 1), 2),
                "benched": benched,
                "monthsLeft": months_left,
                "endDate": f"{ed_yr}-{ed_mo:02d}-{ed_day:02d}" if ed_yr else "-",
                "languages": self._fmt_lang_set(self._person_fluent_langs(p)),
                "isFreeAgent": False,
            }
            if p_avg >= 12.0 and sal > 0 and not benched and row["ratio"] <= 0.72:
                bargains.append(row)
            if sal >= 200000 and (benched or row["ratio"] >= 1.55 or (p_avg < 12.0 and sal >= 300000)):
                overpaid.append(row)
            if 0 <= months_left <= 12.5 and p_avg >= 11.0:
                expiring.append(row)

        free_agents: list[dict[str, Any]] = []
        for pid, p in self.players_by_id.items():
            if pid in self.player_contract_by_pid or p.get("setForRetirement"):
                continue
            p_avg = round(self._player_practical_avg(p), 2)
            p_pot = round(self._player_avg_pot(p), 2)
            role, _, _, _ = self._classify_player_role(p.get("skills") or {})
            med_sal = tier_median.get(int(p_avg // 2), 0)
            free_agents.append(
                {
                    "playerId": pid,
                    "name": p.get("name", ""),
                    "age": p.get("age", 0),
                    "nationName": NATIONS.get(p.get("nation", 0), ""),
                    "teamId": 0,
                    "teamName": "Free Agent",
                    "bestRole": role,
                    "avgSkill": p_avg,
                    "avgPot": p_pot,
                    "yearRating": _yr_rat(pid),
                    "salaryYear": 0,
                    "peerMedianSalary": med_sal,
                    "ratio": 0.0,
                    "benched": False,
                    "monthsLeft": 0.0,
                    "endDate": "Free Agent",
                    "languages": self._fmt_lang_set(self._person_fluent_langs(p)),
                    "isFreeAgent": True,
                }
            )

        bargains.sort(key=lambda r: (r["ratio"], -r["avgSkill"], -r["yearRating"]))
        overpaid.sort(key=lambda r: (-int(r["benched"]), -r["salaryYear"], r["avgSkill"]))
        expiring.sort(key=lambda r: (-r["avgSkill"], r["monthsLeft"]))
        free_agents.sort(key=lambda r: (-r["avgSkill"], -r["avgPot"], r["age"]))
        return {
            "bargains": bargains[:50],
            "overpaid": overpaid[:50],
            "expiring": expiring[:60],
            "freeAgents": free_agents[:80],
        }

    def get_manager_helper(
        self,
        team_id: int | None = None,
        target_player_id: int | None = None,
        role_preset: str = "match",
    ) -> dict[str, Any]:
        """Compute Market Radar, Roster Optimizer, Moneyball Replacement Finder, and Wonderkid Scout."""
        if self.data is None:
            return {"loaded": False}

        _, _, map_names = self._stats_lookups()
        map_ids = sorted(map_names.keys())
        cur_dt = self.data.get("datetime", {}) or {}
        cur_year = int(cur_dt.get("year", 0) or 0)
        cur_month = int(cur_dt.get("month", 1) or 1)
        cur_day = int(cur_dt.get("day", 1) or 1)
        cur_days_approx = cur_year * 365 + (cur_month - 1) * 30 + cur_day

        p_rating_agg: dict[int, tuple[float, int]] = {}
        for row in self.data.get("playerCareerStats", {}).get("playerCareerStats", []):
            if int(row.get("year", 0) or 0) != cur_year:
                continue
            mc = int(row.get("matchesWon", 0) or 0) + int(row.get("matchesLost", 0) or 0)
            if mc > 0:
                pid = int(row.get("playerId", 0) or 0)
                pa, pm = p_rating_agg.get(pid, (0.0, 0))
                p_rating_agg[pid] = (pa + float(row.get("accumulativeRating", 0.0) or 0.0), pm + mc)

        market_radar = self._build_market_radar(p_rating_agg, cur_days_approx)
        nation_req_langs = self._infer_nation_req_langs()

        user_team_id = int((self.data.get("profile") or {}).get("team", 0) or 0)
        teams_selector = []
        for t in self.data["teams"]["teams"]:
            tid = t["id"]
            cs = self.get_team_player_contracts(tid)
            if not cs:
                continue
            starters = [self.players_by_id[c["playerId"]] for c in cs if not c.get("benched") and c["playerId"] in self.players_by_id]
            avg_s = round(sum(self._player_practical_avg(p) for p in starters) / len(starters), 2) if starters else 0.0
            rh = t.get("rankingHistory") or []
            wr = int(rh[-1]) if rh else 0
            teams_selector.append(
                {
                    "teamId": tid,
                    "name": t.get("name", ""),
                    "worldRank": wr,
                    "isUserTeam": tid == user_team_id,
                    "avgSkill": avg_s,
                }
            )
        teams_selector.sort(key=lambda r: (r["worldRank"] == 0, r["worldRank"] if r["worldRank"] > 0 else 9999, -r["avgSkill"]))

        sel_tid = team_id if (team_id and team_id in self.teams_by_id) else (user_team_id if user_team_id in self.teams_by_id else (teams_selector[0]["teamId"] if teams_selector else 0))
        sel_team = self.teams_by_id.get(sel_tid, {})
        team_nation = int(sel_team.get("nation", 0) or 0)
        main_lang_id = int((sel_team.get("teamCohesion") or {}).get("mainLanguage", 13) or 13)
        main_lang_name = LANGUAGES.get(main_lang_id, f"Lang #{main_lang_id}")
        hiring_bias = int((sel_team.get("owner") or {}).get("hiringBias", -1))
        hiring_bias_label = HIRING_BIAS.get(hiring_bias, "Open / Any")
        req_nat_langs = nation_req_langs.get(team_nation, set())

        def _is_policy_ok(p_obj: dict[str, Any]) -> bool:
            if hiring_bias == 0:
                return int(p_obj.get("nation", 0) or 0) == team_nation
            if hiring_bias == 1 and req_nat_langs:
                return bool(self._person_fluent_langs(p_obj) & req_nat_langs)
            return True

        # Roster Optimizer for sel_tid
        team_cs = self.get_team_player_contracts(sel_tid)
        gts = sel_team.get("generalTactics") or []
        active_gt = next((g for g in gts if g.get("active")), gts[0] if gts else {})
        cur_igl_id = int(active_gt.get("iglId", 0) or 0)
        cur_awp_id = int(active_gt.get("sniperId", 0) or 0)

        starters_opt: list[dict[str, Any]] = []
        benched_opt: list[dict[str, Any]] = []
        for c in team_cs:
            pid = c["playerId"]
            p = self.players_by_id.get(pid)
            if not p:
                continue
            sk = p.get("skills") or {}
            avg_s = round(self._player_practical_avg(p), 2)
            avg_pot = round(self._player_avg_pot(p), 2)
            role, awp_s, igl_s, entry_s = self._classify_player_role(sk)
            fl = self._person_fluent_langs(p)
            row = {
                "playerId": pid,
                "name": p.get("name", ""),
                "age": int(p.get("age", 0) or 0),
                "nationName": NATIONS.get(p.get("nation", 0), ""),
                "avgSkill": avg_s,
                "avgPot": avg_pot,
                "bestRole": role,
                "awpScore": awp_s,
                "iglScore": igl_s,
                "entryScore": entry_s,
                "salaryYear": int(c.get("salaryYear", 0) or 0),
                "languages": self._fmt_lang_set(fl),
                "speaksMainLang": main_lang_id in fl,
                "policyOk": _is_policy_ok(p),
                "isCurrentIgl": pid == cur_igl_id,
                "isCurrentAwp": pid == cur_awp_id,
            }
            if c.get("benched"):
                benched_opt.append(row)
            else:
                starters_opt.append(row)

        starters_opt.sort(key=lambda r: -r["avgSkill"])
        benched_opt.sort(key=lambda r: -r["avgSkill"])
        worst_starter = starters_opt[-1] if starters_opt else None
        for b in benched_opt:
            b["upgradeVsWorstStarter"] = round(b["avgSkill"] - worst_starter["avgSkill"], 2) if worst_starter else 0.0

        _, map_comfort_dict = self._team_map_comforts(sel_team, map_ids)
        map_comforts_sorted = sorted(
            [{"mapId": mid, "name": map_names[mid], "comfort": map_comfort_dict.get(mid, 50)} for mid in map_ids],
            key=lambda x: x["comfort"],
        )

        best_igl = max(starters_opt, key=lambda r: r["iglScore"], default=None)
        best_awp = max(starters_opt, key=lambda r: r["awpScore"], default=None)
        alerts: list[dict[str, str]] = []
        if worst_starter and benched_opt and benched_opt[0]["avgSkill"] > worst_starter["avgSkill"] + 0.1:
            b0 = benched_opt[0]
            alerts.append(
                {
                    "severity": "warn",
                    "title": f"Bench Upgrade Available: {b0['name']} ({b0['avgSkill']}) > {worst_starter['name']} ({worst_starter['avgSkill']})",
                    "detail": f"Promoting {b0['name']} off the bench immediately boosts active floor by +{round(b0['avgSkill'] - worst_starter['avgSkill'], 2)}.",
                }
            )
        if best_igl and cur_igl_id and best_igl["playerId"] != cur_igl_id:
            cur_igl_row = next((s for s in starters_opt if s["playerId"] == cur_igl_id), None)
            if cur_igl_row and best_igl["iglScore"] > cur_igl_row["iglScore"] + 0.8:
                alerts.append(
                    {
                        "severity": "info",
                        "title": f"IGL Role Optimization: {best_igl['name']} ({best_igl['iglScore']}) vs {cur_igl_row['name']} ({cur_igl_row['iglScore']})",
                        "detail": "Highest Overview/Decisions/Leadership specialist is not assigned primary IGL in active generalTactics.",
                    }
                )
        if best_awp and cur_awp_id and best_awp["playerId"] != cur_awp_id:
            cur_awp_row = next((s for s in starters_opt if s["playerId"] == cur_awp_id), None)
            if cur_awp_row and best_awp["awpScore"] > cur_awp_row["awpScore"] + 0.8:
                alerts.append(
                    {
                        "severity": "info",
                        "title": f"AWP Role Optimization: {best_awp['name']} ({best_awp['awpScore']}) vs {cur_awp_row['name']} ({cur_awp_row['awpScore']})",
                        "detail": "Another starter scores notably higher on Snipers/Reactions/Composure than your current assigned AWPer.",
                    }
                )
        non_fluent = [s["name"] for s in starters_opt if not s["speaksMainLang"]]
        if non_fluent:
            alerts.append(
                {
                    "severity": "warn",
                    "title": f"{len(non_fluent)} starter(s) do not speak {main_lang_name}: {', '.join(non_fluent)}",
                    "detail": f"Language barrier lowers cohesionFromLanguage; club policy is '{hiring_bias_label}'.",
                }
            )
        policy_bad = [r["name"] for r in starters_opt + benched_opt if not r["policyOk"]]
        if policy_bad:
            alerts.append(
                {
                    "severity": "bad",
                    "title": f"Policy Breach Warning ({hiring_bias_label}): {', '.join(policy_bad)}",
                    "detail": "These contracted players violate this team's owner hiring bias.",
                }
            )
        if map_comforts_sorted and map_comforts_sorted[0]["comfort"] < 65:
            weak_maps = ", ".join(f"{m['name']} ({m['comfort']})" for m in map_comforts_sorted[:3])
            alerts.append(
                {
                    "severity": "info",
                    "title": f"Lowest Map Pool Comfort: {weak_maps}",
                    "detail": "Each 10 points below 50 reduces GetComfortMultiplier and cuts single-map win odds.",
                }
            )
        if not alerts:
            alerts.append(
                {
                    "severity": "ok",
                    "title": "Optimal Roster & Tactic Alignment",
                    "detail": f"All 5 starters speak {main_lang_name}, outrate the bench, match owner policy, and align with IGL/AWP specialists.",
                }
            )

        team_rh = sel_team.get("rankingHistory") or []
        team_wages = sum(int(c.get("salaryYear", 0) or 0) for c in team_cs) + sum(int(sc.get("salaryYear", 0) or 0) for sc in self.get_team_staff_contracts(sel_tid))
        roster_optimizer = {
            "teamId": sel_tid,
            "name": sel_team.get("name", ""),
            "worldRank": int(team_rh[-1]) if team_rh else 0,
            "avgSkill": round(sum(s["avgSkill"] for s in starters_opt) / len(starters_opt), 2) if starters_opt else 0.0,
            "mainLanguageId": main_lang_id,
            "mainLanguageName": main_lang_name,
            "hiringBias": hiring_bias,
            "hiringBiasLabel": hiring_bias_label,
            "balance": int((sel_team.get("teamFinances") or {}).get("currentBalance", 0) or 0),
            "annualWages": team_wages,
            "starters": starters_opt,
            "benched": benched_opt,
            "alerts": alerts,
            "mapComforts": map_comforts_sorted,
            "recommendedRoles": {
                "bestIglName": best_igl["name"] if best_igl else "-",
                "bestIglId": best_igl["playerId"] if best_igl else 0,
                "bestAwpName": best_awp["name"] if best_awp else "-",
                "bestAwpId": best_awp["playerId"] if best_awp else 0,
            },
        }

        # Moneyball Replacement Finder
        all_skill_keys = [sk["key"] for sk in PLAYER_SKILLS]
        ref_pid = target_player_id if (target_player_id and target_player_id in self.players_by_id) else (worst_starter["playerId"] if worst_starter else 0)
        role_templates: dict[str, list[float]] = {
            "awper": [18 if k in ("snipers", "reactions", "composure", "flicks") else (15 if k in ("crosshairPlacement", "decisions", "consistency") else 12) for k in all_skill_keys],
            "igl": [18 if k in ("overview", "decisions", "leadership", "teamwork") else (15 if k in ("composure", "utility", "consistency") else 12) for k in all_skill_keys],
            "entry": [18 if k in ("aggression", "reactions", "flicks", "movement", "rifles") else (15 if k in ("sprayControl", "crosshairPlacement") else 12) for k in all_skill_keys],
            "support": [18 if k in ("utility", "teamwork", "consistency", "pistols") else (15 if k in ("rifles", "overview", "decisions") else 12) for k in all_skill_keys],
            "rifler": [18 if k in ("rifles", "sprayControl", "crosshairPlacement", "tracking", "composure") else 12 for k in all_skill_keys],
        }
        ref_p = self.players_by_id.get(ref_pid)
        if role_preset in role_templates:
            ref_vec = role_templates[role_preset]
            ref_avg = round(sum(ref_vec[i] for i, k in enumerate(all_skill_keys) if k in self._PRACTICAL_KEYS) / 16.0, 2)
            ref_info = {"mode": role_preset, "playerId": 0, "name": f"{role_preset.upper()} Role Template", "avgSkill": ref_avg, "bestRole": role_preset.upper()}
        elif ref_p:
            rsk = ref_p.get("skills") or {}
            ref_vec = [float(rsk.get(k, 10) or 10) for k in all_skill_keys]
            ref_role, _, _, _ = self._classify_player_role(rsk)
            ref_avg = round(self._player_practical_avg(ref_p), 2)
            ref_info = {"mode": "player", "playerId": ref_pid, "name": ref_p.get("name", ""), "avgSkill": ref_avg, "bestRole": ref_role}
        else:
            ref_vec = [15.0] * len(all_skill_keys)
            ref_avg = 15.0
            ref_info = {"mode": "default", "playerId": 0, "name": "Balanced Pro", "avgSkill": 15.0, "bestRole": "Rifler"}

        ref_norm = math.sqrt(sum(v * v for v in ref_vec)) or 1.0
        candidates: list[dict[str, Any]] = []
        for pid, p in self.players_by_id.items():
            if pid == ref_pid or p.get("setForRetirement"):
                continue
            c = self.player_contract_by_pid.get(pid)
            cand_tid = int(c["teamId"]) if c else 0
            if cand_tid == sel_tid and c and not c.get("benched"):
                continue
            sk = p.get("skills") or {}
            cand_avg = round(self._player_practical_avg(p), 2)
            if cand_avg < max(10.0, ref_avg - 2.5):
                continue
            vec = [float(sk.get(k, 10) or 10) for k in all_skill_keys]
            c_norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            cos_sim = sum(a * b for a, b in zip(ref_vec, vec)) / (ref_norm * c_norm)
            sim_pct = round(max(0.0, min(100.0, cos_sim * 100.0)), 1)
            cand_pot = round(self._player_avg_pot(p), 2)
            role, _, _, _ = self._classify_player_role(sk)
            fl = self._person_fluent_langs(p)
            sal = int(c.get("salaryYear", 0) or 0) if c else 0
            benched = bool(c.get("benched", False)) if c else False
            if c and c.get("endDate"):
                ed = c["endDate"]
                ed_yr = int(ed.get("year", 0) or 0)
                ed_mo = int(ed.get("month", 1) or 1)
                ed_day = int(ed.get("day", 1) or 1)
                m_left = round(((ed_yr * 365 + (ed_mo - 1) * 30 + ed_day) - cur_days_approx) / 30.4375, 1) if ed_yr else 99.0
                ed_str = f"{ed_yr}-{ed_mo:02d}-{ed_day:02d}"
            else:
                m_left = 0.0
                ed_str = "Free Agent"
            score = cand_avg * 2.5 + (sim_pct - 90.0) * 0.25 + (1.5 if not c else (0.8 if benched or m_left <= 6 else 0.0)) + (1.0 if main_lang_id in fl else 0.0)
            candidates.append(
                {
                    "playerId": pid,
                    "name": p.get("name", ""),
                    "age": int(p.get("age", 0) or 0),
                    "nationName": NATIONS.get(p.get("nation", 0), ""),
                    "teamId": cand_tid,
                    "teamName": self.teams_by_id[cand_tid]["name"] if cand_tid in self.teams_by_id else "Free Agent",
                    "isFreeAgent": cand_tid == 0,
                    "benched": benched,
                    "avgSkill": cand_avg,
                    "avgPot": cand_pot,
                    "skillDelta": round(cand_avg - ref_avg, 2),
                    "similarityPct": sim_pct,
                    "bestRole": role,
                    "salaryYear": sal,
                    "monthsLeft": m_left,
                    "endDate": ed_str,
                    "speaksMainLang": main_lang_id in fl,
                    "policyOk": _is_policy_ok(p),
                    "languages": self._fmt_lang_set(fl),
                    "fitScore": round(score, 2),
                }
            )
        candidates.sort(key=lambda r: (-r["fitScore"], -r["avgSkill"], -r["similarityPct"]))

        # Wonderkid & Hidden Gem Scout (U21)
        wonderkids: list[dict[str, Any]] = []
        for pid, p in self.players_by_id.items():
            age = int(p.get("age", 0) or 0)
            if age <= 0 or age > 21 or p.get("setForRetirement"):
                continue
            avg_s = round(self._player_practical_avg(p), 2)
            avg_pot = round(self._player_avg_pot(p), 2)
            if avg_pot < 13.5:
                continue
            c = self.player_contract_by_pid.get(pid)
            tid = int(c["teamId"]) if c else 0
            ed = (c.get("endDate") or {}) if c else {}
            ed_yr = int(ed.get("year", 0) or 0)
            m_left = round(((ed_yr * 365 + (int(ed.get("month", 1) or 1) - 1) * 30 + int(ed.get("day", 1) or 1)) - cur_days_approx) / 30.4375, 1) if ed_yr else 0.0
            role, _, _, _ = self._classify_player_role(p.get("skills") or {})
            fl = self._person_fluent_langs(p)
            wonderkids.append(
                {
                    "playerId": pid,
                    "name": p.get("name", ""),
                    "age": age,
                    "nationName": NATIONS.get(p.get("nation", 0), ""),
                    "teamId": tid,
                    "teamName": self.teams_by_id[tid]["name"] if tid in self.teams_by_id else "Free Agent",
                    "isFreeAgent": tid == 0,
                    "benched": bool(c.get("benched", False)) if c else False,
                    "bestRole": role,
                    "avgSkill": avg_s,
                    "avgPot": avg_pot,
                    "headroom": round(avg_pot - avg_s, 2),
                    "salaryYear": int(c.get("salaryYear", 0) or 0) if c else 0,
                    "monthsLeft": m_left,
                    "speaksMainLang": main_lang_id in fl,
                    "languages": self._fmt_lang_set(fl),
                }
            )
        wonderkids.sort(key=lambda r: (-r["avgPot"], -r["avgSkill"], r["age"]))

        return {
            "loaded": True,
            "teams": teams_selector,
            "marketRadar": market_radar,
            "rosterOptimizer": roster_optimizer,
            "replacementFinder": {
                "reference": ref_info,
                "candidates": candidates[:120],
            },
            "wonderkids": wonderkids[:60],
        }

    # ------------------------------------------------------------------
    # God Mode Lab: League Balancing, Skill Smoothing, Floor Boost, AI Fixer
    # ------------------------------------------------------------------

    def _god_sync_potential_caps(self, player: dict[str, Any]) -> None:
        """Ensure every skill's potential limit >= ceil(current skill)."""
        sk = player.get("skills") or {}
        pot = player.get("potential")
        if not isinstance(pot, dict) or "m_Keys" not in pot or "m_Values" not in pot:
            pot = {"m_Keys": [m["id"] for m in PLAYER_SKILLS], "m_Values": [20 for _ in PLAYER_SKILLS]}
            player["potential"] = pot
        pmap = {int(k): int(v) for k, v in zip(pot["m_Keys"], pot["m_Values"])}
        keys = [m["id"] for m in PLAYER_SKILLS]
        vals = [
            int(_clamp(max(pmap.get(m["id"], 15), int(math.ceil(float(sk.get(m["key"], 10) or 10)))), 1, 20))
            for m in PLAYER_SKILLS
        ]
        pot["m_Keys"] = keys
        pot["m_Values"] = vals

    def _god_set_player_target_avg(
        self,
        player: dict[str, Any],
        target_avg: float,
        max_skill_cap: float = 20.0,
    ) -> tuple[float, float]:
        """Shift a player's skills cleanly so their 16-skill practical avg reaches target_avg (respecting 1..max_skill_cap)."""
        sk = player.get("skills") or {}
        old_avg = round(self._player_practical_avg(player), 2)
        target_avg = float(_clamp(target_avg, 1.0, max_skill_cap))
        for _ in range(5):
            cur_avg = self._player_practical_avg(player)
            diff = target_avg - cur_avg
            if abs(diff) < 0.015:
                break
            for m in PLAYER_SKILLS:
                k = m["key"]
                v = float(sk.get(k, 10.0) or 10.0)
                cap = max_skill_cap if k in self._PRACTICAL_KEYS else 20.0
                sk[k] = round(float(_clamp(v + diff, 1.0, cap)), 2)
        if max_skill_cap < 20.0:
            for k in self._PRACTICAL_KEYS:
                sk[k] = round(min(max_skill_cap, float(sk.get(k, 10.0) or 10.0)), 2)
        self._god_sync_potential_caps(player)
        new_avg = round(self._player_practical_avg(player), 2)
        return old_avg, new_avg

    def _god_parity_snapshot(self) -> dict[str, Any]:
        """Compute lightweight Before/After league parity telemetry across Top-20 teams."""
        assert self.data is not None
        user_tid = int((self.data.get("profile") or {}).get("team", 0) or 0)
        rows = []
        for t in self.data["teams"]["teams"]:
            tid = t["id"]
            pcs = self.get_team_player_contracts(tid)
            starters = [self.players_by_id[c["playerId"]] for c in pcs if not c.get("benched") and c["playerId"] in self.players_by_id]
            if not starters:
                continue
            avgs = [self._player_practical_avg(p) for p in starters]
            rh = t.get("rankingHistory") or []
            wr = int(rh[-1]) if rh else 0
            benched = [self.players_by_id[c["playerId"]] for c in pcs if c.get("benched") and c["playerId"] in self.players_by_id]
            best_bench = max((self._player_practical_avg(bp) for bp in benched), default=0.0)
            floor_s = min(avgs)
            rows.append(
                {
                    "teamId": tid,
                    "name": t.get("name", ""),
                    "worldRank": wr,
                    "isUserTeam": tid == user_tid,
                    "avgSkill": round(sum(avgs) / len(avgs), 2),
                    "weakestFloor": round(floor_s, 2),
                    "benchWaste": round(max(0.0, best_bench - floor_s), 2),
                    "balance": int((t.get("teamFinances") or {}).get("currentBalance", 0) or 0),
                }
            )
        rows.sort(key=lambda r: (r["worldRank"] == 0, r["worldRank"] if r["worldRank"] > 0 else 9999, -r["avgSkill"]))
        top10 = [r for r in rows if r["worldRank"] > 0][:10] or rows[:10]
        top20 = [r for r in rows if r["worldRank"] > 0][:20] or rows[:20]
        user_row = next((r for r in rows if r["isUserTeam"]), rows[0] if rows else None)
        t10_avg = round(sum(r["avgSkill"] for r in top10) / len(top10), 2) if top10 else 0.0
        t20_avg = round(sum(r["avgSkill"] for r in top20) / len(top20), 2) if top20 else 0.0
        max_row = max(top20, key=lambda r: r["avgSkill"], default=None)
        min_t10 = min(top10, key=lambda r: r["avgSkill"], default=None)
        return {
            "userTeamName": user_row["name"] if user_row else "-",
            "userAvgSkill": user_row["avgSkill"] if user_row else 0.0,
            "userFloor": user_row["weakestFloor"] if user_row else 0.0,
            "top10AvgSkill": t10_avg,
            "top20AvgSkill": t20_avg,
            "top10Spread": round((max_row["avgSkill"] - min_t10["avgSkill"]), 2) if (max_row and min_t10) else 0.0,
            "top10Gini": self._gini([r["avgSkill"] for r in top10]),
            "aiBenchSabotagesTop20": sum(1 for r in top20 if not r["isUserTeam"] and r["benchWaste"] >= 0.25),
            "teamsList": rows,
        }

    def _god_scoped_teams(self, scope: str, include_user: bool) -> list[tuple[dict[str, Any], int]]:
        """Return [(team_dict, world_rank), ...] ordered by world rank matching scope."""
        assert self.data is not None
        user_tid = int((self.data.get("profile") or {}).get("team", 0) or 0)
        ranked = []
        for t in self.data["teams"]["teams"]:
            tid = t["id"]
            if not include_user and tid == user_tid:
                continue
            pcs = self.get_team_player_contracts(tid)
            if not any(not c.get("benched") for c in pcs):
                continue
            rh = t.get("rankingHistory") or []
            wr = int(rh[-1]) if rh else 0
            ranked.append((t, wr))
        ranked.sort(key=lambda x: (x[1] == 0, x[1] if x[1] > 0 else 9999, -int(x[0].get("reputation", 1) or 1)))
        limit = {"top10": 10, "top20": 20, "top30": 30}.get(scope, 9999)
        return ranked[:limit]

    def get_god_mode_state(self) -> dict[str, Any]:
        """Return lightweight overview + team list + suggested star protection for God Mode."""
        if self.data is None:
            return {"loaded": False}
        snap = self._god_parity_snapshot()
        user_tid = int((self.data.get("profile") or {}).get("team", 0) or 0)
        top_user_star = ""
        if user_tid in self.teams_by_id:
            pcs = self.get_team_player_contracts(user_tid)
            stars = [self.players_by_id[c["playerId"]] for c in pcs if not c.get("benched") and c["playerId"] in self.players_by_id]
            if stars:
                best_p = max(stars, key=self._player_practical_avg)
                top_user_star = best_p.get("name", "")
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
                for r in snap["teamsList"][:40]
            ],
            "defaultProtectedStar": top_user_star,
        }

    def run_god_mode(self, action: str, params: dict[str, Any], dry_run: bool = False) -> dict[str, Any]:
        """Execute (or preview) a God Mode league-balancing / smoothing / AI-fixer action."""
        if self.data is None:
            raise RuntimeError("No save file is currently loaded.")
        if dry_run:
            clone = SaveSession()
            clone.data = copy.deepcopy(self.data)
            clone.rebuild_indices()
            res = clone.run_god_mode(action, params, dry_run=False)
            res["dryRun"] = True
            return res

        before_snap = self._god_parity_snapshot()
        protected_raw = str(params.get("protectedNames") or "")
        protected_set = {x.strip().lower() for x in protected_raw.split(",") if x.strip()}
        changes: list[dict[str, Any]] = []
        summary_lines: list[str] = []

        if action == "boost_floor_parity":
            scope = str(params.get("scope", "top20"))
            mode = str(params.get("mode", "floor"))
            target_floor = float(params.get("targetFloor", 15.8))
            smooth_target = float(params.get("smoothTarget", 16.2))
            strength_pct = float(_clamp(float(params.get("strengthPct", 75.0)), 5.0, 100.0)) / 100.0
            boost_delta = float(_clamp(float(params.get("boostDelta", 1.2)), 0.1, 6.0))
            protect_user = bool(params.get("protectUserTeam", True))

            targets = self._god_scoped_teams(scope, include_user=not protect_user)
            for t, wr in targets:
                pcs = self.get_team_player_contracts(t["id"])
                starters = [self.players_by_id[c["playerId"]] for c in pcs if not c.get("benched") and c["playerId"] in self.players_by_id]
                if not starters:
                    continue
                starters.sort(key=self._player_practical_avg)
                if mode == "weakest_slot_boost":
                    to_edit = starters[:2]
                    for p in to_edit:
                        if p.get("name", "").lower() in protected_set:
                            continue
                        cur = self._player_practical_avg(p)
                        old_a, new_a = self._god_set_player_target_avg(p, min(19.5, cur + boost_delta))
                        if abs(new_a - old_a) >= 0.02:
                            changes.append({"target": p["name"], "team": t["name"], "detail": f"Weakest-slot floor {old_a} -> {new_a}"})
                else:
                    team_avg = sum(self._player_practical_avg(p) for p in starters) / len(starters)
                    for p in starters:
                        if p.get("name", "").lower() in protected_set:
                            continue
                        cur = self._player_practical_avg(p)
                        if mode == "floor":
                            if cur >= target_floor:
                                continue
                            desired = cur + (target_floor - cur) * strength_pct
                        else:
                            # smooth_toward_target shifts players relative to team avg -> smooth_target
                            team_shift = (smooth_target - team_avg) * strength_pct
                            desired = cur + team_shift
                        old_a, new_a = self._god_set_player_target_avg(p, desired)
                        if abs(new_a - old_a) >= 0.02:
                            changes.append({"target": p["name"], "team": t["name"], "detail": f"Avg skill {old_a} -> {new_a}"})
            summary_lines.append(f"Adjusted {len(changes)} starter(s) across {len(targets)} teams ({scope}, mode={mode}).")

        elif action == "nerf_superteam_keep_stars":
            tid = int(params.get("teamId") or (self.data.get("profile") or {}).get("team", 0) or 0)
            team = self.teams_by_id.get(tid)
            if not team:
                raise ValueError(f"Team {tid} not found.")
            target_avg = float(_clamp(float(params.get("targetAvg", 16.2)), 10.0, 19.5))
            cap_non = float(_clamp(float(params.get("capNonProtected", 17.2)), 10.0, 20.0))
            pcs = self.get_team_player_contracts(tid)
            starters = [self.players_by_id[c["playerId"]] for c in pcs if not c.get("benched") and c["playerId"] in self.players_by_id]
            prot_players = [p for p in starters if p.get("name", "").lower() in protected_set]
            edit_players = [p for p in starters if p.get("name", "").lower() not in protected_set]
            if not edit_players:
                raise ValueError("No unprotected starters left on this team to adjust.")
            prot_sum = sum(self._player_practical_avg(p) for p in prot_players)
            desired_edit_mean = (target_avg * len(starters) - prot_sum) / len(edit_players)
            cur_edit_mean = sum(self._player_practical_avg(p) for p in edit_players) / len(edit_players)
            shift = desired_edit_mean - cur_edit_mean
            for p in edit_players:
                cur = self._player_practical_avg(p)
                old_a, new_a = self._god_set_player_target_avg(p, cur + shift, max_skill_cap=cap_non)
                changes.append({"target": p["name"], "team": team["name"], "detail": f"Teammate smoothed {old_a} -> {new_a}"})
            for pp in prot_players:
                changes.append({"target": pp["name"], "team": team["name"], "detail": f"PROTECTED ({round(self._player_practical_avg(pp), 2)} avg untouched)"})
            summary_lines.append(f"Smoothed {team['name']} teammates around protected star(s): {', '.join(p['name'] for p in prot_players) or 'None'}.")

        elif action == "fix_ai_sabotage":
            scope = str(params.get("scope", "top20"))
            fix_bench = bool(params.get("fixBench", True))
            min_map_c = int(params.get("minMapComfort", 65) or 0)
            sync_langs = bool(params.get("syncLanguages", True))
            min_staff = float(params.get("minStaffSkill", 15.5) or 0)
            burnout_top = bool(params.get("applyBurnoutToTopTeams", False))

            targets = self._god_scoped_teams(scope, include_user=False)
            for t, wr in targets:
                tid = t["id"]
                if fix_bench:
                    pcs = self.get_team_player_contracts(tid)
                    act = [self.players_by_id[c["playerId"]] for c in pcs if not c.get("benched") and c["playerId"] in self.players_by_id]
                    ben = [self.players_by_id[c["playerId"]] for c in pcs if c.get("benched") and c["playerId"] in self.players_by_id]
                    act.sort(key=self._player_practical_avg)
                    ben.sort(key=lambda bp: -self._player_practical_avg(bp))
                    swapped = False
                    while act and ben and self._player_practical_avg(ben[0]) > self._player_practical_avg(act[0]) + 0.25:
                        up = ben.pop(0)
                        dn = act.pop(0)
                        c_up = self.player_contract_by_pid[up["id"]]
                        c_dn = self.player_contract_by_pid[dn["id"]]
                        c_up["benched"] = False
                        c_dn["benched"] = True
                        self.remove_player_from_tactics(t, dn["id"])
                        swapped = True
                        changes.append({"target": f"{up['name']} <-> {dn['name']}", "team": t["name"], "detail": "Promoted stronger bench player"})
                    if swapped:
                        self.recalculate_ai_tactics(tid)

                if min_map_c > 0:
                    gts = t.get("generalTactics") or []
                    active_gt = next((g for g in gts if g.get("active")), gts[0] if gts else {})
                    gen_k = int(float(active_gt.get("knowledge", 0.0) or 0.0))
                    boosted_maps = 0
                    for mt in t.get("mapTactics") or []:
                        cur_c = gen_k + int(mt.get("knowledgeFromPlayers", 0) or 0) + int(mt.get("knowledgeFromTraining", 0) or 0)
                        if cur_c < min_map_c:
                            mt["knowledgeFromTraining"] = int(mt.get("knowledgeFromTraining", 0) or 0) + (min_map_c - cur_c)
                            boosted_maps += 1
                    if boosted_maps:
                        changes.append({"target": "Map Prep", "team": t["name"], "detail": f"Raised {boosted_maps} maps to >= {min_map_c} comfort"})

                if sync_langs:
                    main_lid = int((t.get("teamCohesion") or {}).get("mainLanguage", 13) or 13)
                    pcs = self.get_team_player_contracts(tid)
                    for c in pcs:
                        if c.get("benched"):
                            continue
                        p = self.players_by_id.get(c["playerId"])
                        if not p:
                            continue
                        langs = p.get("languagesSpoken") or []
                        entry = next((lg for lg in langs if int(lg.get("languageId", 0) or 0) == main_lid), None)
                        if entry and int(entry.get("languageSkill", 0) or 0) < 15:
                            entry["languageSkill"] = 16
                            entry["limit"] = max(16, int(entry.get("limit", 16) or 16))
                            changes.append({"target": p["name"], "team": t["name"], "detail": f"Added fluent {LANGUAGES.get(main_lid, 'Main Lang')}"})
                        elif not entry:
                            langs.append({"languageId": main_lid, "languageSkill": 16, "limit": 20, "progress": 0.0})
                            p["languagesSpoken"] = langs
                            changes.append({"target": p["name"], "team": t["name"], "detail": f"Added fluent {LANGUAGES.get(main_lid, 'Main Lang')}"})

                if min_staff > 0:
                    for sc in self.get_team_staff_contracts(tid):
                        so = self.staff_by_id.get(sc["staffId"])
                        if not so:
                            continue
                        ss = so.get("skills") or {}
                        cur_s = _staff_avg_skill(so)
                        if cur_s < min_staff:
                            delta_s = min_staff - cur_s
                            for sk_m in STAFF_SKILLS:
                                k = sk_m["key"]
                                ss[k] = round(float(_clamp(float(ss.get(k, 10) or 10) + delta_s, 1.0, 20.0)), 2)
                            changes.append({"target": so.get("name", "Staff"), "team": t["name"], "detail": f"Staff avg {cur_s} -> {round(_staff_avg_skill(so), 2)}"})

            if burnout_top:
                for t, wr in self._god_scoped_teams("top10", include_user=True)[:3]:
                    coh = t.setdefault("teamCohesion", {})
                    old_b = float(coh.get("cohesionFromBurnout", 1.0) or 1.0)
                    coh["cohesionFromBurnout"] = min(old_b, 0.78)
                    changes.append({"target": "Schedule Burnout", "team": t["name"], "detail": f"cohesionFromBurnout {round(old_b, 2)} -> {round(coh['cohesionFromBurnout'], 2)}"})

            summary_lines.append(f"Applied {len(changes)} AI/prep/burnout adjustments across {scope}.")

        elif action == "rebalance_economy":
            scope = str(params.get("scope", "top20"))
            min_bal = int(params.get("minBalance", 1500000) or 0)
            max_cap = int(params.get("maxBalanceCap", 0) or 0)
            min_fac = int(_clamp(int(params.get("minFacilityLevel", 3) or 0), 0, 4))
            targets = self._god_scoped_teams(scope, include_user=False)
            for t, wr in targets:
                fin = t.setdefault("teamFinances", {})
                bal = int(fin.get("currentBalance", 0) or 0)
                if min_bal > 0 and bal < min_bal:
                    fin["currentBalance"] = min_bal
                    changes.append({"target": "Cash Grant", "team": t["name"], "detail": f"${bal:,} -> ${min_bal:,}"})
                if min_fac > 0:
                    upgraded = []
                    for fk in ("coffeeMachine", "recreation", "cable", "ventilation", "academy"):
                        if int(t.get(fk, 0) or 0) < min_fac:
                            t[fk] = min_fac
                            upgraded.append(fk)
                    if upgraded:
                        changes.append({"target": "Facilities", "team": t["name"], "detail": f"Upgraded {', '.join(upgraded)} >= Lv{min_fac}"})
            if max_cap > 0:
                for t, wr in self._god_scoped_teams("top30", include_user=True):
                    fin = t.setdefault("teamFinances", {})
                    bal = int(fin.get("currentBalance", 0) or 0)
                    if bal > max_cap:
                        fin["currentBalance"] = max_cap
                        changes.append({"target": "Wealth Cap", "team": t["name"], "detail": f"Capped ${bal:,} -> ${max_cap:,}"})
            summary_lines.append(f"Rebalanced finances & facilities ({len(changes)} updates).")

        elif action == "inject_wonderkids":
            cnt = int(_clamp(int(params.get("count", 10)), 1, 25))
            age_lo = int(_clamp(int(params.get("minAge", 16)), 15, 21))
            age_hi = int(_clamp(int(params.get("maxAge", 18)), age_lo, 22))
            sk_lo = float(_clamp(float(params.get("skillMin", 12.0)), 8.0, 18.0))
            sk_hi = float(_clamp(float(params.get("skillMax", 14.5)), sk_lo, 19.0))
            pot_lo = float(_clamp(float(params.get("potMin", 17.5)), 14.0, 20.0))
            pot_hi = float(_clamp(float(params.get("potMax", 19.5)), pot_lo, 20.0))
            assign_mode = str(params.get("assignMode", "free_agents"))
            nation_mode = str(params.get("nationMode", "diverse_pro"))

            nation_pools = {
                "eu": [27, 93, 34, 36, 78, 33, 70, 66, 91, 79, 26],
                "cis": [82, 99, 51, 12, 35, 53, 55, 31],
                "americas": [16, 102, 18, 5, 19, 103],
                "asia": [62, 20, 90, 98, 7, 67, 43],
            }
            nat_choices = nation_pools.get(nation_mode) or (nation_pools["eu"] + nation_pools["cis"] + nation_pools["americas"] + nation_pools["asia"])
            handles_a = ["kaze", "nyx", "r0nin", "vex", "z3n", "koda", "orion", "mizu", "falk", "draco", "lyra", "tarkov", "volt", "haze", "flint", "nexaR", "solis", "kr1s", "axel", "bastian", "vortex", "juno", "skye", "torin", "rexx"]
            roles = ["AWPer", "Entry", "Rifler", "IGL", "Support"]
            existing_names = {p.get("name", "").lower() for p in self.players_by_id.values()}
            ai_teams = [t for t, _ in self._god_scoped_teams("top20", include_user=False)]

            for idx in range(cnt):
                base_h = handles_a[idx % len(handles_a)]
                cand_name = base_h if base_h.lower() not in existing_names else f"{base_h}{random.randint(10, 99)}"
                existing_names.add(cand_name.lower())
                role = roles[idx % len(roles)]
                age_val = random.randint(age_lo, age_hi)
                nid = random.choice(nat_choices)
                base_sk = round(random.uniform(sk_lo, sk_hi), 1)
                base_pot = int(round(random.uniform(pot_lo, pot_hi)))

                role_bumps = {
                    "AWPer": {"snipers": 3.5, "reactions": 2.0, "composure": 1.5, "flicks": 1.5},
                    "Entry": {"aggression": 3.0, "reactions": 2.0, "flicks": 2.0, "movement": 1.5, "rifles": 2.0},
                    "IGL": {"overview": 3.0, "decisions": 3.0, "leadership": 3.5, "teamwork": 2.5},
                    "Support": {"utility": 3.0, "teamwork": 3.0, "consistency": 2.0, "pistols": 1.5},
                    "Rifler": {"rifles": 3.0, "sprayControl": 2.5, "crosshairPlacement": 2.0, "tracking": 1.5},
                }[role]
                sk_dict = {
                    m["key"]: round(float(_clamp(base_sk + role_bumps.get(m["key"], random.uniform(-0.8, 0.8)), 5.0, 19.5)), 1)
                    for m in PLAYER_SKILLS
                }
                pot_keys = [m["id"] for m in PLAYER_SKILLS]
                pot_vals = [int(_clamp(max(base_pot, math.ceil(sk_dict[m["key"]])), 10, 20)) for m in PLAYER_SKILLS]

                target_tid = 0
                if assign_mode == "top20_bench" and ai_teams:
                    target_tid = ai_teams[idx % len(ai_teams)]["id"]

                created = self.create_player(
                    {
                        "player": {
                            "name": cand_name,
                            "age": age_val,
                            "nation": nid,
                            "reputation": 10,
                            "preferredMentality": 1,
                            "skills": sk_dict,
                            "potential": {"m_Keys": pot_keys, "m_Values": pot_vals},
                            "academyPlayer": False,
                        },
                        "targetTeamId": target_tid,
                        "joinBenched": True if target_tid > 0 else False,
                        "salaryYear": 120000 if target_tid > 0 else 0,
                    }
                )
                p_new = created["player"]
                tname = self.teams_by_id[target_tid]["name"] if target_tid in self.teams_by_id else "Free Agent"
                changes.append({"target": f"{p_new['name']} ({age_val}y {role})", "team": tname, "detail": f"Avg {round(self._player_practical_avg(p_new), 2)} / Pot {base_pot}"})
            summary_lines.append(f"Spawned {cnt} U21 {nation_mode} wonderkids ({assign_mode}).")

        else:
            raise ValueError(f"Unknown God Mode action: {action}")

        self.dirty = True
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



