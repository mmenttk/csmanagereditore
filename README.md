# CS Manager — Save & Database Editor Suite

A zero-dependency local web workbench built in pure Python 3.10+ (`http.server`) and vanilla HTML/CSS/JS for inspecting, editing, auditing, and balancing **CS Manager** save files and custom databases.

## Suite Components

1. **Save Editor** (repository root, `http://127.0.0.1:8765`): Unified save workbench combining full roster/save editing, stats & HLTV-style award modding, anomaly audits, and **Studio Labs**.
2. **Database Studio** ([`csm/databaseeditor/`](csm/databaseeditor/README.md), `http://127.0.0.1:8766`): Author and balance custom databases (`players`, `staff`, `teams`, `tournaments`, `sponsors`, `gameBalance`, `weapons`) with tournament overlap checks, tier-1 invite logic guide, and league parity smoothing.
3. **Standalone Save Studio** ([`csm/savestudio/`](csm/savestudio/README.md), `http://127.0.0.1:8790`): Optional sidebar-layout standalone edition.

## Save Editor Features

- **Core Transfers & Editors**:
  - **Transfers, Players, Staff & Orgs**: Edit attributes, potentials, wellness (`burnout`, `mood`, `startingPotential`), career awards CRUD, player relationships, languages, contracts, org sponsors CRUD, ranking history sparklines, and recalculate AI tactics.
  - **Topbar Safety & Search**: **Undo Time Machine Snapshots** (automatic checkpoints before major edits + manual restore), non-destructive **Backup Copy**, **Save (with Backup)** / **Save As** / **Download `.json`**, and **`Ctrl+K` Global Search** across players, teams, staff, and tournaments.
- **Stats, Tournaments & Award Patching**:
  - **Stats**: Player & Team career stats, Head-to-Head, CSTV Top 20 predictor (with `+10%` vote simulation + **Recalculate & Save Top 20** / **Reset Top 20**), and **Event Stats** comparing the game's `Rating × Mult` score against **Our Fair Score** (`BayesRating(k=25% MaxM) + PlaceBonus (+0.055 / +0.030 / +0.010 / -0.015 / -0.055) + OppRank(±0.040) + PlayoffVol(+0.045 × PO/MaxPO)` with **MVP locked to Grand Finalists 1st or 2nd**).
  - **Tournaments & Awards**: Browse played events (sorted by MVP/EVP-giving by default with **Hide Upcoming** toggle), edit prestige/prize metadata, preview/apply single or batch Fair MVP/EVP patches cleanly across Spring/Fall editions, and repair career awards via **Repair / Sync Player Awards**.
- **Bug Showcase, Data Science & Manager Helper**:
  - Live anomaly audit (13-0 blowouts, undeserved awards, bench crimes, multi-club vulture bidding breakdowns), win-rate regressions & Lorenz/Gini parity metrics, and roster optimization / moneyball replacement scouting.
- **Studio Labs** (7 integrated labs):
  - **Career HQ**: Manager profile, skills, contract, board job security sliders, and one-click club takeover.
  - **Save Diff**: Compare any earlier save or backup against the active save (skill risers/fallers, world rank swings, new transfers, trophies & awards).
  - **God Mode**: League floor booster, **All-Team Superteam Smoother** with optional star protection, AI sabotage fixer, economy rebalancer, and wonderkid injector.
  - **Roster Sandbox & Sim**: Test 5-man fantasy lineups (`skill^2.8` Bo1/Bo3/Bo5 win odds, comms languages, chemistry, role conflicts, 7-map comfort) and commit transfers + tactics.
  - **Growth & Trajectory**: Monthly `playerSkillHistories` SVG curves, wonderkids, risers/decliners, and ceiling gaps.
  - **Market Radar**: Live `personInterests` vulture swarms, active bids, hiring-policy violation purge, and cooldown clearing.
  - **Weapon Meta Lab**: Live `weapons.weapons` tuning plus instant presets (`CS2 Balanced`, `AWP Era`, `Rifle Laser`, `Eco Chaos`).

## Quick Start

### Save Editor
- **Windows**: Double-click `launch.bat`
- **macOS / Linux**:
  ```bash
  ./launch.sh
  ```
  *(or `python3 server.py`)*

Open `http://127.0.0.1:8765`, pick a discovered save or upload a `.json` save file (for example under `%AppData%\..\LocalLow\Crumana\CS Manager`), make your changes, and click **Save (with Backup)** or **Download `.json`**.

### Database Studio
- **Windows**: Double-click [`csm/databaseeditor/launch.bat`](csm/databaseeditor/launch.bat)
- **macOS / Linux**:
  ```bash
  cd csm/databaseeditor && ./launch.sh
  ```

## Safety & Git Hygiene

- Every write creates a timestamped backup inside a local `backups/` folder before modifying files on disk.
- `.gitignore` excludes `*.json` save/database files, `backups/`, `EDITORBACKUP/`, imported custom logo/asset folders, virtual environments, and Python caches so personal game data stays private when pushing to GitHub.
