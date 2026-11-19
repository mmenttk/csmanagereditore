"""Local web server for CS Manager Database, Tournament Schedule, GameBalance & Weapons Editor."""

from __future__ import annotations

import argparse
import json
import mimetypes
import socket
import subprocess
import sys
import urllib.parse
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import gamedata as gd
from db_engine import DatabaseWorkspace, list_all_packs


STATIC_DIR = Path(__file__).resolve().parent / "static"
WORKSPACE = DatabaseWorkspace()


def _browse_folder_native(initial_dir: str = "", title: str = "Select CS Manager Database Folder") -> dict[str, Any]:
    """Open native folder picker in an isolated subprocess (desktop local usage)."""
    script = (
        "import tkinter as tk; from tkinter import filedialog; "
        "r = tk.Tk(); r.withdraw(); r.attributes('-topmost', True); "
        f"p = filedialog.askdirectory(initialdir={initial_dir!r}, title={title!r}); "
        "print(p or '')"
    )
    try:
        proc = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=60)
        path = (proc.stdout or "").strip()
        return {"ok": bool(path), "path": path, "cancelled": not bool(path)}
    except Exception as exc:
        return {"ok": False, "unsupported": True, "error": str(exc)}


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: Any) -> None:
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(raw)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(raw)


def _read_body_json(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length") or 0)
    if length <= 0:
        return {}
    raw = handler.rfile.read(length)
    return json.loads(raw.decode("utf-8"))


class DatabaseRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)

        try:
            if path == "/" or path == "/index.html":
                return self._serve_static("index.html")
            if path in ("/app.js", "/style.css"):
                return self._serve_static(path.lstrip("/"))
            if path == "/api/meta":
                return _json_response(self, HTTPStatus.OK, {
                    "nations": gd.NATIONS,
                    "nationRegions": gd.NATION_REGIONS,
                    "languages": gd.LANGUAGES,
                    "playerSkills": gd.PLAYER_SKILLS,
                    "staffSkills": gd.STAFF_SKILLS,
                    "playerMentalities": gd.PLAYER_MENTALITIES,
                    "staffMentalities": gd.STAFF_MENTALITIES,
                    "playerStatus": gd.PLAYER_STATUS,
                    "roleStatus": gd.ROLE_STATUS,
                    "transferStatus": gd.TRANSFER_STATUS,
                    "contractType": gd.CONTRACT_TYPE,
                    "staffRoles": gd.STAFF_ROLES,
                    "professionalStatus": gd.PROFESSIONAL_STATUS,
                    "hiringBias": gd.HIRING_BIAS,
                    "academyFocus": gd.ACADEMY_FOCUS,
                    "personalityAxes": gd.PERSONALITY_AXES,
                    "playerPositions": gd.PLAYER_POSITIONS,
                    "mapNames": gd.MAP_NAMES,
                    "relationshipTypes": gd.RELATIONSHIP_TYPES,
                    "awardTypes": gd.AWARD_TYPES,
                    "portraitFields": gd.PORTRAIT_FIELDS,
                    "formatTypes": gd.FORMAT_TYPES,
                    "venues": gd.VENUES,
                    "regions": gd.REGIONS,
                    "dynamicLocations": gd.DYNAMIC_LOCATIONS,
                    "progressTypes": gd.PROGRESS_TYPES,
                    "sessionSlots": gd.SESSION_SLOTS,
                    "daysOfWeek": gd.DAYS_OF_WEEK,
                    "stageNameKeys": gd.STAGE_NAME_KEYS,
                    "stageNameLabels": gd.STAGE_NAME_LABELS,
                    "awardBreakdownByRep": gd.AWARD_BREAKDOWN_BY_REP,
                    "weaponTypes": gd.WEAPON_TYPES,
                    "weaponAvailability": gd.WEAPON_AVAILABILITY,
                    "weaponTiers": gd.WEAPON_TIERS,
                })
            if path == "/api/packs":
                return _json_response(self, HTTPStatus.OK, list_all_packs())
            if path == "/api/summary":
                return _json_response(self, HTTPStatus.OK, WORKSPACE.get_summary())
            if path == "/api/teams":
                q = (qs.get("q") or [""])[0]
                reg = int(qs["region"][0]) if qs.get("region") and qs["region"][0] != "" else None
                return _json_response(self, HTTPStatus.OK, WORKSPACE.list_teams(search=q, region=reg))
            if path == "/api/team":
                tid = int(qs["id"][0])
                return _json_response(self, HTTPStatus.OK, WORKSPACE.get_team(tid))
            if path == "/api/players":
                q = (qs.get("q") or [""])[0]
                tid = int(qs["teamId"][0]) if qs.get("teamId") and qs["teamId"][0] != "" else None
                free = (qs.get("freeOnly") or ["false"])[0].lower() == "true"
                role = (qs.get("role") or [""])[0]
                limit = int(qs["limit"][0]) if qs.get("limit") and qs["limit"][0] != "" else 300
                return _json_response(self, HTTPStatus.OK, WORKSPACE.list_players(search=q, team_id=tid, free_only=free, role=role, limit=limit))
            if path == "/api/player":
                pid = int(qs["id"][0])
                return _json_response(self, HTTPStatus.OK, WORKSPACE.get_player(pid))
            if path == "/api/staff":
                q = (qs.get("q") or [""])[0]
                return _json_response(self, HTTPStatus.OK, WORKSPACE.list_staff(search=q))
            if path == "/api/staff/item":
                sid = int(qs["id"][0])
                return _json_response(self, HTTPStatus.OK, WORKSPACE.get_staff(sid))
            if path == "/api/sponsors":
                return _json_response(self, HTTPStatus.OK, WORKSPACE.list_sponsors())
            if path == "/api/tournaments":
                return _json_response(self, HTTPStatus.OK, WORKSPACE.list_tournaments())
            if path == "/api/tournaments/schedule":
                return _json_response(self, HTTPStatus.OK, WORKSPACE.analyze_tournaments_schedule())
            if path == "/api/tournaments/suggest-slots":
                tpl = int(qs["template"][0])
                return _json_response(self, HTTPStatus.OK, WORKSPACE.suggest_tournament_slots(tpl))
            if path == "/api/tournaments/visualize":
                tpl = int(qs["template"][0])
                return _json_response(self, HTTPStatus.OK, WORKSPACE.visualize_tournament_run(tpl))
            if path == "/api/logos":
                kind = (qs.get("kind") or ["team"])[0]
                return _json_response(self, HTTPStatus.OK, WORKSPACE.list_logos(kind))
            if path.startswith("/api/logo-img/"):
                parts = path[len("/api/logo-img/"):].split("/", 1)
                if len(parts) == 2:
                    kind = urllib.parse.unquote(parts[0])
                    name = urllib.parse.unquote(parts[1])
                    fp = WORKSPACE.resolve_logo_path(kind, name)
                    if fp and fp.exists():
                        return self._serve_file(fp)
                return _json_response(self, HTTPStatus.NOT_FOUND, {"error": "Logo image not found"})
            if path == "/api/data-science/balance":
                return _json_response(self, HTTPStatus.OK, WORKSPACE.analyze_db_balance())
            if path == "/api/mod/balance":
                return _json_response(self, HTTPStatus.OK, WORKSPACE.get_balance_and_analysis())
            if path == "/api/mod/weapons":
                return _json_response(self, HTTPStatus.OK, WORKSPACE.get_weapons_and_analysis())
            if path == "/api/god-mode/state":
                return _json_response(self, HTTPStatus.OK, WORKSPACE.get_god_mode_state())

            _json_response(self, HTTPStatus.NOT_FOUND, {"error": f"Unknown GET endpoint: {path}"})
        except Exception as exc:
            _json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(exc)})

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        try:
            body = _read_body_json(self)
            if path == "/api/load-database":
                return _json_response(self, HTTPStatus.OK, WORKSPACE.load_database(body["path"]))
            if path == "/api/save-database":
                return _json_response(self, HTTPStatus.OK, WORKSPACE.save_database(body.get("targetFolder")))
            if path == "/api/clone-database":
                return _json_response(self, HTTPStatus.OK, WORKSPACE.clone_database(body["name"]))
            if path == "/api/browse-folder":
                return _json_response(self, HTTPStatus.OK, _browse_folder_native(WORKSPACE.db_dir or ""))
            if path == "/api/validate-db":
                return _json_response(self, HTTPStatus.OK, WORKSPACE.validate_database(auto_fix=bool(body.get("autoFix"))))

            if path == "/api/team/update":
                return _json_response(self, HTTPStatus.OK, WORKSPACE.update_team(int(body["teamId"]), body.get("patch", {})))
            if path == "/api/team/create":
                return _json_response(self, HTTPStatus.OK, WORKSPACE.create_team(body))
            if path == "/api/team/delete":
                return _json_response(self, HTTPStatus.OK, WORKSPACE.delete_team(int(body["teamId"])))

            if path == "/api/player/update":
                return _json_response(self, HTTPStatus.OK, WORKSPACE.update_player(int(body["playerId"]), body.get("patch", {})))
            if path == "/api/player/create":
                return _json_response(self, HTTPStatus.OK, WORKSPACE.create_player(body))
            if path == "/api/player/delete":
                return _json_response(self, HTTPStatus.OK, WORKSPACE.delete_player(int(body["playerId"])))
            if path == "/api/player/relationship/save":
                return _json_response(
                    self,
                    HTTPStatus.OK,
                    WORKSPACE.save_player_relationship(
                        int(body["player1Id"]),
                        int(body["player2Id"]),
                        int(body.get("type", 1)),
                        int(body.get("duration", 0)),
                    ),
                )
            if path == "/api/player/relationship/delete":
                return _json_response(
                    self,
                    HTTPStatus.OK,
                    WORKSPACE.delete_player_relationship(int(body["player1Id"]), int(body["player2Id"])),
                )

            if path == "/api/staff/update":
                return _json_response(self, HTTPStatus.OK, WORKSPACE.update_staff(int(body["staffId"]), body.get("patch", {})))
            if path == "/api/staff/create":
                return _json_response(self, HTTPStatus.OK, WORKSPACE.create_staff(body))
            if path == "/api/staff/delete":
                return _json_response(self, HTTPStatus.OK, WORKSPACE.delete_staff(int(body["staffId"])))

            if path == "/api/sponsor/save":
                return _json_response(self, HTTPStatus.OK, WORKSPACE.save_sponsor(body))
            if path == "/api/sponsor/delete":
                return _json_response(self, HTTPStatus.OK, WORKSPACE.delete_sponsor(int(body["id"])))

            if path == "/api/tournament/save":
                return _json_response(self, HTTPStatus.OK, WORKSPACE.save_tournament(body))
            if path == "/api/tournament/clone":
                return _json_response(self, HTTPStatus.OK, WORKSPACE.clone_tournament(int(body["template"])))
            if path == "/api/tournament/delete":
                return _json_response(self, HTTPStatus.OK, WORKSPACE.delete_tournament(int(body["template"])))

            if path == "/api/mod/balance/load":
                return _json_response(self, HTTPStatus.OK, WORKSPACE.load_game_balance(body["path"]))
            if path == "/api/mod/balance/update":
                return _json_response(self, HTTPStatus.OK, WORKSPACE.update_game_balance(body.get("patch", {})))
            if path == "/api/mod/balance/scale":
                return _json_response(
                    self,
                    HTTPStatus.OK,
                    WORKSPACE.batch_scale_balance(body["category"], float(body.get("pct", 10.0))),
                )
            if path == "/api/mod/balance/save":
                return _json_response(self, HTTPStatus.OK, WORKSPACE.save_game_balance(body.get("newPackName")))
            if path == "/api/god-mode/run":
                return _json_response(
                    self,
                    HTTPStatus.OK,
                    WORKSPACE.run_god_mode(
                        body["action"],
                        body.get("params", {}),
                        dry_run=bool(body.get("dryRun", False)),
                    ),
                )

            if path == "/api/mod/weapons/load":
                return _json_response(self, HTTPStatus.OK, WORKSPACE.load_weapons(body["path"]))
            if path == "/api/mod/weapons/update":
                return _json_response(self, HTTPStatus.OK, WORKSPACE.update_weapon(int(body["id"]), body.get("patch", {})))
            if path == "/api/mod/weapons/scale":
                wt = int(body["weaponType"]) if body.get("weaponType") not in (None, "") else None
                return _json_response(self, HTTPStatus.OK, WORKSPACE.batch_scale_weapons(body["action"], wt, float(body.get("pct", 10.0))))
            if path == "/api/mod/weapons/save":
                return _json_response(self, HTTPStatus.OK, WORKSPACE.save_weapons(body.get("newPackName")))

            if path == "/api/logos/import-folder":
                kind = str(body.get("kind") or "team")
                sync_global = bool(body.get("syncGlobal", True))
                folder = str(body.get("folder") or "").strip()
                if not folder:
                    pick = _browse_folder_native(WORKSPACE.db_dir or "", title=f"Select {kind.replace('_', ' ').title()} Logos Folder")
                    if not pick.get("ok"):
                        return _json_response(self, HTTPStatus.OK, pick)
                    folder = pick["path"]
                return _json_response(self, HTTPStatus.OK, WORKSPACE.import_logos_from_folder(kind, folder, sync_global=sync_global))

            if path == "/api/logos/upload":
                kind = str(body.get("kind") or "team")
                files = list(body.get("files") or [])
                sync_global = bool(body.get("syncGlobal", True))
                return _json_response(self, HTTPStatus.OK, WORKSPACE.import_logo_uploads(kind, files, sync_global=sync_global))

            _json_response(self, HTTPStatus.NOT_FOUND, {"error": f"Unknown POST endpoint: {path}"})
        except Exception as exc:
            _json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(exc)})

    def _serve_file(self, fp: Path) -> None:
        ctype, _ = mimetypes.guess_type(str(fp))
        data = fp.read_bytes()
        self.send_response(HTTPStatus.OK)
        header_type = ctype or "application/octet-stream"
        if header_type.startswith("text/") or header_type in ("application/javascript", "application/json"):
            header_type = f"{header_type}; charset=utf-8"
        self.send_header("Content-Type", header_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _serve_static(self, rel: str) -> None:
        fp = (STATIC_DIR / rel).resolve()
        if not str(fp).startswith(str(STATIC_DIR.resolve())) or not fp.exists():
            return _json_response(self, HTTPStatus.NOT_FOUND, {"error": "File not found"})
        self._serve_file(fp)


def preload_latest_packs() -> None:
    packs = list_all_packs()
    if packs["databases"] and not WORKSPACE.db_dir:
        latest_db = max(packs["databases"], key=lambda x: x["mtime"])
        try:
            WORKSPACE.load_database(latest_db["path"])
        except Exception:
            pass
    if packs["gameBalances"] and WORKSPACE.balance_data is None:
        latest_gb = max(packs["gameBalances"], key=lambda x: x["mtime"])
        try:
            WORKSPACE.load_game_balance(latest_gb["path"])
        except Exception:
            pass
    if packs["weapons"] and WORKSPACE.weapons_data is None:
        latest_w = max(packs["weapons"], key=lambda x: x["mtime"])
        try:
            WORKSPACE.load_weapons(latest_w["path"])
        except Exception:
            pass


def _lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def main() -> None:
    parser = argparse.ArgumentParser(description="CS Manager Custom Database, Schedule, Balance & Weapons Studio")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--lan", action="store_true", help="Bind 0.0.0.0 so LAN devices can connect")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    preload_latest_packs()
    host = "0.0.0.0" if args.lan else "127.0.0.1"
    httpd = ThreadingHTTPServer((host, args.port), DatabaseRequestHandler)
    local_url = f"http://127.0.0.1:{args.port}/"
    print(f"CS Manager Database Studio running at {local_url}")
    if args.lan:
        print(f"LAN URL: http://{_lan_ip()}:{args.port}/")
    if not args.no_browser:
        try:
            webbrowser.open(local_url)
        except Exception:
            pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
