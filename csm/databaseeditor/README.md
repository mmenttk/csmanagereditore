# CS Manager — Database Studio & Balance Validator

Standalone local web studio (`http://127.0.0.1:8766`) for authoring, auditing, and balancing **CS Manager** custom databases (`players`, `staff`, `teams`, `tournaments`, `sponsors`, `gameBalance`, `weapons`), built with pure Python 3.10+ (`http.server`) and vanilla HTML/CSS/JS with zero external dependencies.

## Features

- **Core Database Authoring & Search**:
  - **Players (8 subtabs)**: `Basics` (bio, reputation, mentality, personality traits, IGL/sniper preference, longevity, custom potential), `Skills`, `Maps & Positions`, `Languages`, `Career & Awards` (trophies, career awards, honors, yearly history), `Relations` (friends & rivals), `Portrait` (parametric portrait DNA modder), and `Contract` (team, salary, expiration, completed contracts).
  - **Staff (6 subtabs)**: `Basics`, `Skills`, `Mentality & Interests` (preferred/disliked teams, mentality, role), `Languages`, `Contract` (team, salary, expiration, completed contracts), and `Portrait`.
  - **Teams**: Roster & staff management (inspect/edit/assign/promote), team finances, reputation, region, academy links, and quick logo picker.
  - **Tournaments**: Full event & stage authoring, location, reputation, start window, BO5 Grand Final, prize pool allotment & verification, Major sticker money ranges, and per-event day-by-day run timeline visualizer.
  - **Sponsors**: Payouts, requirements, reputation, duration, and custom logo picker.
- **Tournaments Validator & Meta Guides**:
  - Worst-case calendar overlap solver testing all start-day / day-of-week permutations, split by S-Tier / A-Tier / other tiers.
  - Meta Tournament Circuit guide (how prestige brackets interact with MVP / EVP / honorable mention awards), **Decompiled AI Tournament Selection & Invite Logic** (why Tier-1 teams never skip for rest and ignore colliding second events), and Tournament Count per Hardware Load Ratio guidance.
- **Data Science & Database Audit**:
  - Gini & Lorenz inequality diagnostics, skill/potential/age distributions, team power spread, economy balance, and hardware load alerts.
- **Game Balance & Weapons Modding**:
  - Categorized & sorted `gameBalance` parameters with dev `test.json` baseline analytics comparison and batch adjustment controls, plus weapon stats/price/accuracy editor and batch scaler.
- **God Mode DB Balancer**:
  - Non-destructive preset & batch rebalancing toolkit (floor boost, superteam smoother, youth/wonderkid generator, AI/economy fixer) with automatic pre-write backups (`backups/`).
- **Custom Logo Folder Importer**:
  - Scan local logo/icon folders for teams, tournaments, sponsors, and weapons directly into the editor.

## Quick Start

- **Windows**: Double-click `launch.bat`
- **macOS / Linux**: Run `./launch.sh` (or `python3 server.py`)

Then open `http://127.0.0.1:8766` in your browser and select or browse to a CS Manager database folder containing `.json` files.

## Sharing / Git Hygiene

`.gitignore` excludes personal `*.json` database files, `backups/`, `EDITORBACKUP/`, custom logo/asset folders, and Python caches so your private databases and artwork are not committed to Git.
