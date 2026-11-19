"""Local HTTP server for CS Manager Save Studio (stdlib-only)."""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import threading
import webbrowser
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

APP_DIR = Path(__file__).resolve().parent
ROOT_DIR = APP_DIR.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import gamedata  # noqa: E402
from save_engine import DEFAULT_SAVES_DIR, discover_save_files  # noqa: E402
from studio_engine import StudioSession  # noqa: E402

STATIC_DIR = APP_DIR / "static"

SESSION = StudioSession()
SESSION_LOCK = threading.Lock()


def _open_native_file_dialog(mode: str, initial_dir: Path, initial_file: str = "") -> str:
    script = (
        "import json, sys, tkinter as tk\n"
        "from tkinter import filedialog\n"
        "cfg = json.loads(sys.argv[1])\n"
        "root = tk.Tk()\n"
        "root.withdraw()\n"
        "try:\n"
        "    root.attributes('-topmost', True)\n"
        "except Exception:\n"
        "    pass\n"
        "root.update()\n"
        "ft = [('CS Manager Save (*.json)', '*.json'), ('All Files (*.*)', '*.*')]\n"
        "if cfg['mode'] == 'open':\n"
        "    path = filedialog.askopenfilename(parent=root, title='Open CS Manager Save', initialdir=cfg['dir'], filetypes=ft)\n"
        "else:\n"
        "    path = filedialog.asksaveasfilename(parent=root, title='Save CS Manager Save As', initialdir=cfg['dir'], initialfile=cfg['file'], defaultextension='.json', filetypes=ft)\n"
        "root.destroy()\n"
        "print(path or '')\n"
    )
    cfg = json.dumps({
        "mode": mode,
        "dir": str(initial_dir if initial_dir.exists() else APP_DIR),
        "file": initial_file,
    })
    res = subprocess.run([sys.executable, "-c", script, cfg], capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(res.stderr.strip() or "Native file dialog unavailable on this system.")
    return res.stdout.strip()


def _open_os_folder(folder: Path) -> None:
    target = folder if folder.exists() else APP_DIR
    if os.name == "nt":
        os.startfile(str(target))
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(target)])
    else:
        subprocess.Popen(["xdg-open", str(target)])


def _detect_lan_ip() -> str | None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except Exception:
        return None


def _meta_payload() -> dict[str, Any]:
    return {
        "nations": gamedata.NATIONS,
        "languages": gamedata.LANGUAGES,
        "playerSkills": gamedata.PLAYER_SKILLS,
        "staffSkills": gamedata.STAFF_SKILLS,
        "playerMentalities": gamedata.PLAYER_MENTALITIES,
        "staffMentalities": gamedata.STAFF_MENTALITIES,
        "playerStatus": gamedata.PLAYER_STATUS,
        "roleStatus": gamedata.ROLE_STATUS,
        "transferStatus": gamedata.TRANSFER_STATUS,
        "contractType": gamedata.CONTRACT_TYPE,
        "staffRoles": gamedata.STAFF_ROLES,
        "playerPositions": gamedata.PLAYER_POSITIONS,
        "mapTacticPositions": gamedata.MAP_TACTIC_POSITIONS,
        "professionalStatus": gamedata.PROFESSIONAL_STATUS,
        "hiringBias": gamedata.HIRING_BIAS,
        "academyFocus": gamedata.ACADEMY_FOCUS,
        "personalityAxes": gamedata.PERSONALITY_AXES,
        "relationshipTypes": gamedata.RELATIONSHIP_TYPES,
        "weaponTypes": {0: "Pistol", 1: "SMG", 2: "Rifle", 3: "Sniper"},
        "awardTypes": {0: "MVP", 1: "Event Win", 2: "EVP", 3: "Top 20"},
    }


def _qs_str(qs: dict[str, list[str]], key: str, default: str = "") -> str:
    vals = qs.get(key)
    return vals[0] if vals else default


def _qs_int(qs: dict[str, list[str]], key: str, default: int) -> int:
    vals = qs.get(key)
    if not vals or vals[0] == "":
        return default
    return int(vals[0])


def _qs_bool(qs: dict[str, list[str]], key: str, default: bool = False) -> bool:
    vals = qs.get(key)
    if not vals:
        return default
    return vals[0].lower() in ("1", "true", "yes", "on")


class StudioRequestHandler(SimpleHTTPRequestHandler):
    """Serves Save Studio static assets and /api/* JSON endpoints."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def log_message(self, format: str, *args: Any) -> None:
        if args and len(args) >= 2 and str(args[1]).startswith(("4", "5")):
            super().log_message(format, *args)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def _send_json(self, status: int, data: Any) -> None:
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _send_error_json(self, status: int, message: str) -> None:
        self._send_json(status, {"error": message})

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        if not raw:
            return {}
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("JSON body must be an object.")
        return data

    def _handle_api(self, method: str) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        try:
            if method == "GET":
                if path == "/api/meta":
                    return self._send_json(HTTPStatus.OK, _meta_payload())

                if path == "/api/saves":
                    return self._send_json(HTTPStatus.OK, {"saves": discover_save_files()})

                with SESSION_LOCK:
                    if path == "/api/summary":
                        return self._send_json(HTTPStatus.OK, SESSION.summary())

                    # ---- Studio Snapshots / Search / Career HQ ----
                    if path == "/api/studio/snapshots":
                        return self._send_json(HTTPStatus.OK, {"snapshots": SESSION.list_snapshots()})

                    if path == "/api/studio/search":
                        return self._send_json(HTTPStatus.OK, SESSION.global_search(_qs_str(qs, "q"), _qs_int(qs, "limit", 8)))

                    if path == "/api/studio/career-hq":
                        return self._send_json(HTTPStatus.OK, SESSION.get_career_hq())

                    # ---- Studio Pro Player & Team Details ----
                    m = re.fullmatch(r"/api/studio/player/(\d+)", path)
                    if m:
                        return self._send_json(HTTPStatus.OK, SESSION.get_player_pro(int(m.group(1))))

                    m = re.fullmatch(r"/api/studio/team/(\d+)", path)
                    if m:
                        return self._send_json(HTTPStatus.OK, SESSION.get_team_pro(int(m.group(1))))

                    # ---- Studio Growth Lab ----
                    if path == "/api/studio/growth":
                        return self._send_json(HTTPStatus.OK, SESSION.get_growth_lab(min_months=_qs_int(qs, "min_months", 2)))

                    m = re.fullmatch(r"/api/studio/growth/player/(\d+)", path)
                    if m:
                        return self._send_json(HTTPStatus.OK, SESSION.get_player_trajectory(int(m.group(1))))

                    # ---- Studio Tournaments Hub & Award Patcher ----
                    if path == "/api/studio/tournaments":
                        return self._send_json(HTTPStatus.OK, SESSION.list_tournaments_hub())

                    m = re.fullmatch(r"/api/studio/tournament/(\d+)", path)
                    if m:
                        return self._send_json(HTTPStatus.OK, SESSION.get_tournament_hub_detail(int(m.group(1))))

                    # ---- Studio Market Radar / Weapons / Save Diff ----
                    if path == "/api/studio/market-radar":
                        return self._send_json(HTTPStatus.OK, SESSION.get_market_radar())

                    if path == "/api/studio/weapons":
                        return self._send_json(HTTPStatus.OK, SESSION.get_weapons_meta())

                    if path == "/api/studio/diff/saves":
                        return self._send_json(HTTPStatus.OK, {"saves": SESSION.list_comparable_saves()})

                    # ---- Base Save Editor Read Routes ----
                    if path == "/api/players":
                        res = SESSION.list_players(
                            q=_qs_str(qs, "q"),
                            team_id=_qs_str(qs, "team_id"),
                            nation=_qs_str(qs, "nation"),
                            free_only=_qs_bool(qs, "free_only"),
                            offset=_qs_int(qs, "offset", 0),
                            limit=_qs_int(qs, "limit", 100),
                        )
                        return self._send_json(HTTPStatus.OK, res)

                    m = re.fullmatch(r"/api/player/(\d+)", path)
                    if m:
                        return self._send_json(HTTPStatus.OK, SESSION.get_player_pro(int(m.group(1))))

                    if path == "/api/player-relationships":
                        return self._send_json(
                            HTTPStatus.OK,
                            SESSION.list_player_relationships(
                                q=_qs_str(qs, "q"),
                                rel_type=_qs_str(qs, "type"),
                                team_id=_qs_str(qs, "team_id"),
                                unresolved_only=_qs_bool(qs, "unresolved_only"),
                            ),
                        )

                    if path == "/api/staff":
                        res = SESSION.list_staff(
                            q=_qs_str(qs, "q"),
                            team_id=_qs_str(qs, "team_id"),
                            role=_qs_str(qs, "role"),
                            free_only=_qs_bool(qs, "free_only"),
                            offset=_qs_int(qs, "offset", 0),
                            limit=_qs_int(qs, "limit", 100),
                        )
                        return self._send_json(HTTPStatus.OK, res)

                    m = re.fullmatch(r"/api/staff/(\d+)", path)
                    if m:
                        return self._send_json(HTTPStatus.OK, SESSION.get_staff(int(m.group(1))))

                    if path == "/api/teams":
                        return self._send_json(HTTPStatus.OK, {"teams": SESSION.list_teams(q=_qs_str(qs, "q"))})

                    m = re.fullmatch(r"/api/team/(\d+)", path)
                    if m:
                        return self._send_json(HTTPStatus.OK, SESSION.get_team_pro(int(m.group(1))))

                    if path == "/api/transfers":
                        return self._send_json(HTTPStatus.OK, {"transfers": SESSION.list_transfers(limit=_qs_int(qs, "limit", 80))})

                    if path == "/api/validate":
                        return self._send_json(HTTPStatus.OK, SESSION.validate_and_fix(fix=False))

                    if path == "/api/stats/overview":
                        yr_s = _qs_str(qs, "year")
                        tid_s = _qs_str(qs, "team_id")
                        min_m = _qs_int(qs, "min_maps", 0)
                        return self._send_json(
                            HTTPStatus.OK,
                            SESSION.get_stats_overview(
                                year=int(yr_s) if yr_s else None,
                                team_id=int(tid_s) if tid_s else None,
                                min_maps=min_m,
                            ),
                        )

                    m = re.fullmatch(r"/api/stats/player/(\d+)", path)
                    if m:
                        return self._send_json(HTTPStatus.OK, SESSION.get_player_stats_detail(int(m.group(1))))

                    m = re.fullmatch(r"/api/stats/team/(\d+)", path)
                    if m:
                        return self._send_json(HTTPStatus.OK, SESSION.get_team_stats_detail(int(m.group(1))))

                    m = re.fullmatch(r"/api/stats/match/(\d+)", path)
                    if m:
                        return self._send_json(HTTPStatus.OK, SESSION.get_match_stats_detail(int(m.group(1))))

                    if path == "/api/stats/event":
                        tid_s = _qs_str(qs, "tournament_id")
                        return self._send_json(
                            HTTPStatus.OK,
                            SESSION.get_event_stats(tournament_id=int(tid_s) if tid_s else None),
                        )

                    if path == "/api/bug-showcase":
                        return self._send_json(HTTPStatus.OK, SESSION.get_bug_showcase())

                    if path in ("/api/strength-realism", "/api/data-science"):
                        yr_s = _qs_str(qs, "year")
                        ft_s = _qs_str(qs, "focus_team_id")
                        return self._send_json(
                            HTTPStatus.OK,
                            SESSION.get_strength_realism(
                                year=int(yr_s) if yr_s else None,
                                focus_team_id=int(ft_s) if ft_s else None,
                            ),
                        )

                    if path == "/api/manager-helper":
                        tid_s = _qs_str(qs, "team_id")
                        pid_s = _qs_str(qs, "target_player_id")
                        role_s = _qs_str(qs, "role_preset", "match")
                        return self._send_json(
                            HTTPStatus.OK,
                            SESSION.get_manager_helper(
                                team_id=int(tid_s) if tid_s else None,
                                target_player_id=int(pid_s) if pid_s else None,
                                role_preset=role_s,
                            ),
                        )

                    if path == "/api/god-mode/state":
                        return self._send_json(HTTPStatus.OK, SESSION.get_god_mode_state())

                    if path in ("/api/download", "/api/export"):
                        fname, raw = SESSION.export_json_bytes()
                        safe_name = fname.replace('"', "").replace("\r", "").replace("\n", "")
                        self.send_response(HTTPStatus.OK)
                        self.send_header("Content-Type", "application/json; charset=utf-8")
                        self.send_header("Content-Disposition", f'attachment; filename="{safe_name}"')
                        self.send_header("Content-Length", str(len(raw)))
                        self.end_headers()
                        self.wfile.write(raw)
                        return

            elif method == "POST":
                body = self._read_json_body()
                is_local_client = self.client_address[0] in ("127.0.0.1", "::1")

                if path == "/api/dialog/open-save":
                    if not is_local_client:
                        return self._send_json(HTTPStatus.OK, {"unsupported": True, "remote": True})
                    init_dir = SESSION.path.parent if SESSION.path else (DEFAULT_SAVES_DIR if DEFAULT_SAVES_DIR.exists() else APP_DIR)
                    try:
                        chosen = _open_native_file_dialog("open", init_dir)
                    except Exception as exc:
                        return self._send_json(HTTPStatus.OK, {"unsupported": True, "error": str(exc)})
                    return self._send_json(HTTPStatus.OK, {"path": chosen, "cancelled": not chosen})

                if path == "/api/dialog/save-as":
                    if not is_local_client:
                        return self._send_json(HTTPStatus.OK, {"unsupported": True, "remote": True})
                    init_dir = SESSION.path.parent if SESSION.path else (DEFAULT_SAVES_DIR if DEFAULT_SAVES_DIR.exists() else APP_DIR)
                    init_file = SESSION.path.name if SESSION.path else (SESSION.virtual_name or "custom_save.json")
                    try:
                        chosen = _open_native_file_dialog("save", init_dir, init_file)
                    except Exception as exc:
                        return self._send_json(HTTPStatus.OK, {"unsupported": True, "error": str(exc)})
                    return self._send_json(HTTPStatus.OK, {"path": chosen, "cancelled": not chosen})

                if path == "/api/dialog/open-folder":
                    if not is_local_client:
                        return self._send_error_json(HTTPStatus.BAD_REQUEST, "Open Folder only works when running directly on the host desktop.")
                    folder = SESSION.path.parent if SESSION.path else (DEFAULT_SAVES_DIR if DEFAULT_SAVES_DIR.exists() else APP_DIR)
                    _open_os_folder(folder)
                    return self._send_json(HTTPStatus.OK, {"opened": str(folder)})

                with SESSION_LOCK:
                    if path == "/api/load":
                        file_path = str(body.get("path", "")).strip()
                        if not file_path:
                            raise ValueError("Missing 'path' in request body.")
                        return self._send_json(HTTPStatus.OK, SESSION.load(file_path))

                    if path == "/api/load-upload":
                        filename = str(body.get("filename", "uploaded_save.json")).strip()
                        content = body.get("content", "")
                        if not isinstance(content, str) or not content.strip():
                            raise ValueError("Uploaded file content is empty.")
                        return self._send_json(HTTPStatus.OK, SESSION.load_upload(filename, content))

                    if path == "/api/save":
                        target_path = body.get("path")
                        if target_path is not None:
                            target_path = str(target_path).strip() or None
                        return self._send_json(HTTPStatus.OK, SESSION.save(target_path=target_path))

                    if path == "/api/backup":
                        return self._send_json(HTTPStatus.OK, SESSION.create_disk_backup())

                    if path == "/api/validate":
                        return self._send_json(HTTPStatus.OK, SESSION.validate_and_fix(fix=bool(body.get("fix", False))))

                    # ---- Studio Undo Snapshots ----
                    if path == "/api/studio/snapshot/create":
                        return self._send_json(HTTPStatus.OK, SESSION.create_snapshot(str(body.get("label", "Manual Checkpoint"))))

                    if path == "/api/studio/snapshot/restore":
                        return self._send_json(HTTPStatus.OK, SESSION.restore_snapshot(int(body["id"])))

                    # ---- Studio Career HQ ----
                    if path == "/api/studio/career-hq/update":
                        return self._send_json(HTTPStatus.OK, SESSION.update_career_hq(body))

                    if path == "/api/studio/career-hq/switch-team":
                        return self._send_json(
                            HTTPStatus.OK,
                            SESSION.switch_managed_team(int(body["teamId"]), swap_coach=bool(body.get("swapCoach", False))),
                        )

                    # ---- Studio Player Pro & Team Pro ----
                    m = re.fullmatch(r"/api/studio/player/(\d+)", path)
                    if m:
                        return self._send_json(HTTPStatus.OK, SESSION.update_player_pro(int(m.group(1)), body))

                    m = re.fullmatch(r"/api/studio/player/(\d+)/heal", path)
                    if m:
                        return self._send_json(
                            HTTPStatus.OK,
                            SESSION.heal_player_state(
                                int(m.group(1)),
                                reset_burnout=bool(body.get("resetBurnout", True)),
                                max_mood=bool(body.get("maxMood", True)),
                            ),
                        )

                    m = re.fullmatch(r"/api/studio/player/(\d+)/award/add", path)
                    if m:
                        return self._send_json(HTTPStatus.OK, SESSION.add_player_award(int(m.group(1)), body))

                    m = re.fullmatch(r"/api/studio/player/(\d+)/award/delete", path)
                    if m:
                        return self._send_json(HTTPStatus.OK, SESSION.delete_player_award(int(m.group(1)), int(body["index"])))

                    m = re.fullmatch(r"/api/studio/team/(\d+)/sponsor", path)
                    if m:
                        return self._send_json(HTTPStatus.OK, SESSION.manage_team_sponsor(int(m.group(1)), body))

                    m = re.fullmatch(r"/api/studio/team/(\d+)/heal", path)
                    if m:
                        return self._send_json(
                            HTTPStatus.OK,
                            SESSION.heal_team_squad(
                                int(m.group(1)),
                                reset_burnout=bool(body.get("resetBurnout", True)),
                                max_mood=bool(body.get("maxMood", True)),
                                clear_cooldowns=bool(body.get("clearCooldowns", False)),
                            ),
                        )

                    # ---- Studio Sandbox ----
                    if path == "/api/studio/sandbox/simulate":
                        return self._send_json(
                            HTTPStatus.OK,
                            SESSION.simulate_roster(
                                int(body["teamId"]),
                                [int(x) for x in (body.get("playerIds") or [])],
                                vs_team_id=int(body.get("vsTeamId", 0) or 0),
                            ),
                        )

                    if path == "/api/studio/sandbox/commit":
                        return self._send_json(
                            HTTPStatus.OK,
                            SESSION.commit_roster_sandbox(
                                int(body["teamId"]),
                                [int(x) for x in (body.get("playerIds") or [])],
                            ),
                        )

                    # ---- Studio Tournament Hub & Award Patcher ----
                    m = re.fullmatch(r"/api/studio/tournament/(\d+)/meta", path)
                    if m:
                        return self._send_json(HTTPStatus.OK, SESSION.update_tournament_meta(int(m.group(1)), body))

                    m = re.fullmatch(r"/api/studio/tournament/(\d+)/patch-awards", path)
                    if m:
                        return self._send_json(
                            HTTPStatus.OK,
                            SESSION.patch_tournament_awards(
                                int(m.group(1)),
                                mode=str(body.get("mode", "fair")),
                                custom_player_ids=body.get("customPlayerIds"),
                                dry_run=bool(body.get("dryRun", False)),
                            ),
                        )

                    if path == "/api/studio/tournaments/batch-fair-awards":
                        return self._send_json(
                            HTTPStatus.OK,
                            SESSION.batch_patch_fair_awards(
                                min_reputation=int(body.get("minReputation", 13) or 13),
                                dry_run=bool(body.get("dryRun", True)),
                            ),
                        )

                    # ---- Studio Market Radar Actions ----
                    if path == "/api/studio/market-radar/action":
                        return self._send_json(
                            HTTPStatus.OK,
                            SESSION.clear_market_bids(
                                mode=str(body.get("mode", "")),
                                player_id=int(body.get("playerId", 0) or 0),
                                team_id=int(body.get("teamId", 0) or 0),
                            ),
                        )

                    # ---- Studio Weapon Meta Lab ----
                    m = re.fullmatch(r"/api/studio/weapon/(\d+)", path)
                    if m:
                        return self._send_json(HTTPStatus.OK, SESSION.update_weapon(int(m.group(1)), body))

                    if path == "/api/studio/weapons/preset":
                        return self._send_json(HTTPStatus.OK, SESSION.apply_weapon_preset(str(body.get("preset", ""))))

                    # ---- Studio Save Diff ----
                    if path == "/api/studio/diff/compare":
                        bpath = str(body.get("baselinePath", "")).strip()
                        if not bpath:
                            raise ValueError("Missing 'baselinePath' in request body.")
                        return self._send_json(HTTPStatus.OK, SESSION.compare_saves(bpath))

                    # ---- Base Save Editor Mutation Routes ----
                    if path == "/api/players":
                        return self._send_json(HTTPStatus.CREATED, SESSION.create_player(body))

                    if path == "/api/staff":
                        return self._send_json(HTTPStatus.CREATED, SESSION.create_staff(body))

                    if path == "/api/transfer/player":
                        SESSION.create_snapshot("Before Player Transfer")
                        return self._send_json(HTTPStatus.OK, SESSION.transfer_player(body))

                    if path == "/api/transfer/staff":
                        SESSION.create_snapshot("Before Staff Transfer")
                        return self._send_json(HTTPStatus.OK, SESSION.transfer_staff(body))

                    m = re.fullmatch(r"/api/player/(\d+)/bench", path)
                    if m:
                        return self._send_json(
                            HTTPStatus.OK,
                            SESSION.set_player_benched(
                                int(m.group(1)),
                                benched=bool(body.get("benched", True)),
                                auto_tactics=bool(body.get("autoTactics", True)),
                            ),
                        )

                    if path == "/api/player/relationship/save":
                        return self._send_json(
                            HTTPStatus.OK,
                            SESSION.save_player_relationship(
                                player1_id=int(body["player1Id"]),
                                player2_id=int(body["player2Id"]),
                                rel_type=int(body.get("type", 1)),
                                duration=int(body.get("duration", 0)),
                                player1_resolved=body.get("player1Resolved"),
                                player2_resolved=body.get("player2Resolved"),
                            ),
                        )

                    if path == "/api/player/relationship/delete":
                        return self._send_json(
                            HTTPStatus.OK,
                            SESSION.delete_player_relationship(
                                player1_id=int(body["player1Id"]),
                                player2_id=int(body["player2Id"]),
                            ),
                        )

                    m = re.fullmatch(r"/api/team/(\d+)/recalculate-tactics", path)
                    if m:
                        return self._send_json(HTTPStatus.OK, SESSION.recalculate_ai_tactics(int(m.group(1))))

                    if path in ("/api/god-mode/apply", "/api/god-mode/run"):
                        res = SESSION.run_god_mode(
                            action=str(body.get("action", "")),
                            params=body.get("params") or {},
                            dry_run=bool(body.get("dryRun", False)),
                        )
                        return self._send_json(HTTPStatus.OK, res)

            elif method == "PUT":
                body = self._read_json_body()
                with SESSION_LOCK:
                    m = re.fullmatch(r"/api/player/(\d+)", path)
                    if m:
                        return self._send_json(HTTPStatus.OK, SESSION.update_player_pro(int(m.group(1)), body))

                    m = re.fullmatch(r"/api/staff/(\d+)", path)
                    if m:
                        return self._send_json(HTTPStatus.OK, SESSION.update_staff(int(m.group(1)), body))

                    m = re.fullmatch(r"/api/team/(\d+)", path)
                    if m:
                        SESSION.create_snapshot(f"Before Team Edit #{m.group(1)}")
                        return self._send_json(HTTPStatus.OK, SESSION.update_team(int(m.group(1)), body))

            return self._send_error_json(HTTPStatus.NOT_FOUND, f"Unknown API endpoint: {method} {path}")

        except FileNotFoundError as exc:
            return self._send_error_json(HTTPStatus.NOT_FOUND, str(exc))
        except (KeyError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
            return self._send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
        except Exception as exc:
            return self._send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, f"{type(exc).__name__}: {exc}")

    def do_GET(self) -> None:
        if self.path.startswith("/api/"):
            self._handle_api("GET")
            return
        clean = urlparse(self.path).path
        if clean in ("", "/"):
            self.path = "/index.html"
        else:
            # Guard against directory traversal
            rel = clean.lstrip("/")
            candidate = (STATIC_DIR / rel).resolve()
            if not str(candidate).startswith(str(STATIC_DIR.resolve())):
                self.send_error(HTTPStatus.FORBIDDEN, "Access denied")
                return
        super().do_GET()

    def do_POST(self) -> None:
        if self.path.startswith("/api/"):
            self._handle_api("POST")
            return
        self._send_error_json(HTTPStatus.METHOD_NOT_ALLOWED, "POST only supported on /api/*")

    def do_PUT(self) -> None:
        if self.path.startswith("/api/"):
            self._handle_api("PUT")
            return
        self._send_error_json(HTTPStatus.METHOD_NOT_ALLOWED, "PUT only supported on /api/*")


def main() -> None:
    parser = argparse.ArgumentParser(description="CS Manager Save Studio Server")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default 127.0.0.1)")
    parser.add_argument("--lan", action="store_true", help="Listen on 0.0.0.0 for LAN clients")
    parser.add_argument("--port", type=int, default=8790, help="Port to listen on (default 8790)")
    parser.add_argument("--no-browser", action="store_true", help="Do not auto-open the web browser")
    parser.add_argument("--load", default="", help="Optional save file path to pre-load on startup")
    args = parser.parse_args()
    bind_host = "0.0.0.0" if args.lan else args.host

    if args.load:
        SESSION.load(args.load)
    else:
        saves = discover_save_files()
        if saves:
            preferred = next((s for s in saves if s.get("source") == "SavedGames"), saves[0])
            try:
                SESSION.load(preferred["path"])
            except Exception as exc:
                print(f"Warning: could not preload {preferred['path']}: {exc}")

    os.chdir(APP_DIR)
    try:
        server = ThreadingHTTPServer((bind_host, args.port), StudioRequestHandler)
    except OSError as exc:
        print(f"\nERROR: Could not bind {bind_host}:{args.port} ({exc}).")
        sys.exit(1)
    actual_port = server.server_address[1]
    local_host = "127.0.0.1" if bind_host == "0.0.0.0" else bind_host
    url = f"http://{local_host}:{actual_port}/"
    print(f"CS Manager Save Studio running at {url}")
    if bind_host == "0.0.0.0":
        lan_ip = _detect_lan_ip()
        if lan_ip:
            print(f"LAN URL: http://{lan_ip}:{actual_port}/")
    print("Press Ctrl+C to stop.")

    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down Save Studio...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
