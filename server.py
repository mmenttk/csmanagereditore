"""Local HTTP server for CS Manager Save Editor (stdlib-only)."""

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

import gamedata
from save_engine import DEFAULT_SAVES_DIR, SaveSession, discover_save_files

APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"

SESSION = SaveSession()
SESSION_LOCK = threading.Lock()


def _open_native_file_dialog(mode: str, initial_dir: Path, initial_file: str = "") -> str:
    """Spawn a short-lived Python subprocess to show a native OS file dialog (Windows/macOS/Linux desktop)."""
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


class EditorRequestHandler(SimpleHTTPRequestHandler):
    """Serves static UI files and /api/* JSON endpoints."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def log_message(self, format: str, *args: Any) -> None:
        # Suppress noisy static asset logs; keep errors visible.
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
                        return self._send_json(HTTPStatus.OK, SESSION.get_player(int(m.group(1))))

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
                        return self._send_json(HTTPStatus.OK, SESSION.get_team(int(m.group(1))))

                    if path == "/api/transfers":
                        limit = _qs_int(qs, "limit", 80)
                        return self._send_json(HTTPStatus.OK, {"transfers": SESSION.list_transfers(limit=limit)})

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

                    if path == "/api/download":
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

                    if path == "/api/validate":
                        fix = bool(body.get("fix", False))
                        return self._send_json(HTTPStatus.OK, SESSION.validate_and_fix(fix=fix))

                    if path == "/api/players":
                        return self._send_json(HTTPStatus.CREATED, SESSION.create_player(body))

                    if path == "/api/staff":
                        return self._send_json(HTTPStatus.CREATED, SESSION.create_staff(body))

                    if path == "/api/transfer/player":
                        return self._send_json(HTTPStatus.OK, SESSION.transfer_player(body))

                    if path == "/api/transfer/staff":
                        return self._send_json(HTTPStatus.OK, SESSION.transfer_staff(body))

                    m = re.fullmatch(r"/api/player/(\d+)/bench", path)
                    if m:
                        benched = bool(body.get("benched", True))
                        auto_tactics = bool(body.get("autoTactics", True))
                        return self._send_json(
                            HTTPStatus.OK,
                            SESSION.set_player_benched(int(m.group(1)), benched=benched, auto_tactics=auto_tactics),
                        )

                    m = re.fullmatch(r"/api/team/(\d+)/recalculate-tactics", path)
                    if m:
                        return self._send_json(
                            HTTPStatus.OK, SESSION.recalculate_ai_tactics(int(m.group(1)))
                        )

                    if path == "/api/god-mode/apply":
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
                        return self._send_json(HTTPStatus.OK, SESSION.update_player(int(m.group(1)), body))

                    m = re.fullmatch(r"/api/staff/(\d+)", path)
                    if m:
                        return self._send_json(HTTPStatus.OK, SESSION.update_staff(int(m.group(1)), body))

                    m = re.fullmatch(r"/api/team/(\d+)", path)
                    if m:
                        return self._send_json(HTTPStatus.OK, SESSION.update_team(int(m.group(1)), body))

            return self._send_error_json(HTTPStatus.NOT_FOUND, f"Unknown API endpoint: {method} {path}")

        except FileNotFoundError as exc:
            return self._send_error_json(HTTPStatus.NOT_FOUND, str(exc))
        except (KeyError, ValueError, json.JSONDecodeError) as exc:
            return self._send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
        except Exception as exc:
            return self._send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, f"{type(exc).__name__}: {exc}")

    def do_GET(self) -> None:
        if self.path.startswith("/api/"):
            self._handle_api("GET")
            return
        if self.path in ("", "/"):
            self.path = "/index.html"
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
    parser = argparse.ArgumentParser(description="CS Manager Save Editor Server")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default 127.0.0.1)")
    parser.add_argument("--lan", action="store_true", help="Listen on all interfaces (0.0.0.0) so phones/tablets/other PCs on LAN can connect")
    parser.add_argument("--port", type=int, default=8765, help="Port to listen on (default 8765)")
    parser.add_argument("--no-browser", action="store_true", help="Do not auto-open the web browser")
    parser.add_argument("--load", default="", help="Optional save file path to pre-load on startup")
    args = parser.parse_args()
    bind_host = "0.0.0.0" if args.lan else args.host

    if args.load:
        SESSION.load(args.load)
    else:
        saves = discover_save_files()
        if saves:
            # Prefer a non-reference save from SavedGames if available, otherwise first discovered
            preferred = next((s for s in saves if s.get("source") == "SavedGames"), saves[0])
            try:
                SESSION.load(preferred["path"])
            except Exception as exc:
                print(f"Warning: could not preload {preferred['path']}: {exc}")

    os.chdir(APP_DIR)
    try:
        server = ThreadingHTTPServer((bind_host, args.port), EditorRequestHandler)
    except OSError as exc:
        print(f"\nERROR: Could not bind {bind_host}:{args.port} ({exc}).")
        print("An older CS Manager Save Editor window is probably still running on this port.")
        print("Close that old terminal window and launch again.")
        sys.exit(1)
    actual_port = server.server_address[1]
    local_host = "127.0.0.1" if bind_host == "0.0.0.0" else bind_host
    url = f"http://{local_host}:{actual_port}/"
    print(f"CS Manager Save Editor running at {url}")
    if bind_host == "0.0.0.0":
        lan_ip = _detect_lan_ip()
        if lan_ip:
            print(f"LAN / Mobile access URL: http://{lan_ip}:{actual_port}/")
    print("Press Ctrl+C to stop.")

    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
