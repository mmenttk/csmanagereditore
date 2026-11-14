# CS Manager Save Editor

Cross-platform web save editor for **CS Manager** (Windows, macOS, Linux/Steam Deck, and LAN/mobile browsers via Python 3.10+ standard library — zero `pip` installs required).

## Features

- **Working Player & Staff Transfers**:
  - Transfers update contracts, clear old team tactics & dilemmas, optionally promote a replacement on the departing team, optionally bench a chosen starter on the destination team, rebuild both teams' `generalTactics` (`IGL`, `2nd IGL`, `AWP`, `2nd AWP`) and active `mapTactics` (`mapPositions`) using the game's AI lane/comfort algorithm so matches do not freeze, reset player match mood/dilemmas, record `transferHistories`, and optionally deduct/credit buyout fees in `teamFinances`.
  - Release players or staff to Free Agency (`0`).
- **Create New Players & Staff**:
  - Add custom players (`+ New Player`) or staff (`+ New Staff`) as free agents or sign them directly onto any team with automatic tactics recalculation.
- **Save Integrity Validator & Auto-Fix**:
  - Detects duplicate contracts, active roster mismatches, stale `generalTactics` IDs, and missing/benched players inside `mapTactics`, repairing them in one click.
- **Full Editors**:
  - **Players**: Name, Age, Nation, Reputation, Mentality, Retirement/Longevity, all 18 Skills + 18 Potential caps, Languages Spoken, Contracts, 9 Map Role Comforts & Progress, Map Likes/Dislikes, and 7 Personality sliders.
  - **Staff**: Name, Age, Nation, Reputation, Mentality, Retirement settings, 7 Staff Skills + Potential caps, Languages Spoken, Contracts & Role, and 6 Career Role Interests.
  - **Orgs / Teams**: Org Name, Nation, Reputation, Professional Status, Financial Strength, Owner Name & Hiring Bias, Team Finances, Facilities & Academy, Team Cohesion & Main Language, Board Goals, plus live Starter/Bench toggles (`AWP` / `2nd AWP` / `IGL` / `2nd IGL` badges) and AI Tactics recalculation.
- **Detailed Stats Hub**:
  - **Player Leaderboard**: Matches, Maps, Win%, Rating, K/D, K/R, ADR, HS%, KAST / Entry Impact (Opening K/D & Diff), Multi-kills (2K/3K/4K/5K), AWP kills, Clutches, MVPs, EVPs, and Yearly Top 20 badges — filterable by Season Year, Team, Min Maps Played, and Search, with clickable deep-dive Player Stats modals (map pool breakdown, event history, top victims matrix, skill progression over time, recent maps).
  - **Team Standings & Analytics**: Ranking points, Match/Map/Pistol W-L%, Clutches, Economy (`Fullbuys`/`Saves`), plus clickable Team Analytics modals (World Rank SVG trend chart, map pool stats, tournament placements & prize money, match log).
  - **Map Pool Meta**: Map pick/ban veto rates, play counts, average rounds, overtime rate, total kills & aces.
  - **Match History & Match Box-Scores**: Full veto sequence (`Ban`/`Pick`/`Decider`), map-by-map CT/T & pistol stats, clutches, and dual-team box scores (`Rating` / `K` / `A (FA)` / `D` / `ADR` / `HS%` / `FK/FD` / `AWP` / `2K–5K`).
  - **Trophies & Awards**: Tournament Champions Hall of Fame, Career Player Awards (`MVP`, `EVP`, `Event Win`, `Top 20`), and Awards Timeline.
  - **Top 20 Prediction**: Replicates the game's exact year-end formula (`AvgRating_vsTop10 * 1.05^MVP * 1.01^EVP * min(Matches_vsTop10 / 50, 1)`), CSTV Ballot `#1–#13` status, high-rated snubs watchlist, and live click-to-vote (`+10%`) rank shift simulator.
- **Bug Showcase & Save Anomaly Audit**:
  - **13-0s & Blowout Audit**: Compares save shutout (`13-0`) and blowout (`<=3` rounds) rates vs the CS2 Tier-1 pro baseline, complete with streak curves and clickable match scoreboards.
  - **Undeserved MVPs & EVPs**: Evaluates real MVP/EVP tournaments against trophy-first and HLTV-style placement-gap rules.
  - **AI Transfers & Policy Breaches**: Flags benching better starters, multi-team carousels, and breaches of `"Only National"` / `"Only National Language"` club hiring policies.
  - **Squad Stability**: Tracks post-transfer stint lengths against the `6–14` month pro baseline and ranks high-churn orgs.
- **Works Across All Devices**:
  - Auto-discovers `SavedGames` folders on Windows (`%USERPROFILE%\AppData\LocalLow\Crumana\CS Manager\SavedGames`), macOS (`~/Library/Application Support/Crumana/CS Manager/SavedGames`), and Linux / Steam Deck (native `~/.config/unity3d/...` + Steam Proton `compatdata`).
  - Supports native desktop Open/Save dialogs (`Browse File...` / `Save As...` / `Open Folder`) **and** browser file upload/download (`Upload .json` / `Download .json`), which also activate automatically on phones, tablets, or remote browsers.

## How to Run

### Windows
- Double-click `launch.bat` (requires Python 3.10+ installed from [python.org](https://www.python.org/downloads/)).

### macOS / Linux / Steam Deck
```bash
chmod +x launch.sh
./launch.sh
```
(Or run `python3 server.py` directly in this folder.)

### Using from a Phone, Tablet, or Another Device on Your Wi-Fi / LAN
Start the server with `--lan` (for example `launch.bat --lan` or `python3 server.py --lan`). The terminal will print a LAN URL (such as `http://192.168.1.42:8765/`) that any device on your network can open in its browser, then use **Upload .json** and **Download .json**.

## virustotal result

https://www.virustotal.com/gui/file-analysis/ZjU2ZWNhZjMxMDg3MDJjNDMwNjcwNDJmZTk5OTIxNzQ6MTc5NDY4MTc1OA==

## Note Before Sharing With Others
Keep your personal save files (e.g. `*.json`), `backups/`, and `__pycache__/` out of the zip when sharing this folder with other people—only `server.py`, `save_engine.py`, `gamedata.py`, `launch.bat`, `launch.sh`, `README.md`, and the `static/` folder are needed.
