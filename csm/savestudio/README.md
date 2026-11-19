# CS Manager Save Studio

Next-generation save workstation built on top of the root Save Editor engine (`../../save_engine.py` and `../../gamedata.py`), running side-by-side on port **8790**.

## Launch

- Windows: double-click `launch.bat` or run `python server.py`
- macOS/Linux: `./launch.sh` or `python3 server.py`
- Default URL: `http://127.0.0.1:8790/`

## Studio Highlights

- **Undo Time Machine (`Ctrl+K` / Snapshots)** — Automatic compressed checkpoints before major edits so you can revert instantly.
- **Career HQ & Switch Club** — Edit manager identity, Head Coach contract, Job Security sliders & board expectations, or take over any org cleanly.
- **Roster Sandbox & Matchup Sim** — Draft any 5-man lineup, check Bo1/Bo3/Bo5 win odds vs Top 10 or any rival, language comms matrix, friend/rival chemistry, role balance, and commit directly into the save with recalculated tactics.
- **Growth & Trajectory Lab** — Multi-month player progression analytics (`playerSkillHistories`) with interactive SVG skill trajectory charts.
- **Tournament & Fair-Award Patcher** — Reconstruct HLTV-style Fair MVPs/EVPs (Grand Finalist lock + playoff volume) and retroactively patch tournament & `PlayerAward` history (single-event or batch).
- **Vulture Market Radar & Weapon Meta Lab** — Live `personInterests` bidding swarms, policy-breaking bid cleanup, and live weapon tuning/presets.
- **Save Diff & Time Machine** — Diff the active save against any earlier save or backup (skill risers/fallers, rank movers, balance swings, transfers, trophies, awards).
