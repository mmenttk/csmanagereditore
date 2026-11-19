/* Save Studio - Stats Hub, Event Fair Compare, Bug Showcase & All-Team God Mode */

function bindAnalyticsEvents() {
  $("btnStatsRefresh").addEventListener("click", () => {
    loadStatsHub();
    if ($("subtab-events").classList.contains("active") || state.eventStatsData) loadEventStatsStudio(state.selectedEventId);
  });
  $("statsFilterYear").addEventListener("change", loadStatsHub);
  $("statsFilterTeam").addEventListener("change", () => { loadStatsHub(); if (state.eventStatsData) renderEventStatsStudio(); });
  $("statsFilterMinMaps").addEventListener("change", loadStatsHub);
  $("statsFilterQ").addEventListener("input", renderStatsHub);
  $("statsEventSelect").addEventListener("change", () => {
    state.selectedEventId = Number($("statsEventSelect").value || 0) || null;
    loadEventStatsStudio(state.selectedEventId);
  });

  $("btnShowcaseRefresh").addEventListener("click", loadBugShowcaseStudio);
  $("showcaseFilterQ").addEventListener("input", renderBugShowcaseStudio);
}

// ---- Stats Hub ----

async function loadStatsHub() {
  try {
    const params = new URLSearchParams({
      year: $("statsFilterYear").value || "",
      team_id: $("statsFilterTeam").value || "",
      min_maps: $("statsFilterMinMaps").value || "0",
    });
    state.statsData = await api(`/api/stats/overview?${params.toString()}`);
    const yrs = state.statsData.years || [];
    const curY = $("statsFilterYear").value;
    $("statsFilterYear").innerHTML = [`<option value="">All Years</option>`]
      .concat(yrs.map((y) => `<option value="${y}" ${String(y) === curY ? "selected" : ""}>${y}</option>`))
      .join("");
    renderStatsHub();
    if ($("subtab-events")?.classList.contains("active")) loadEventStatsStudio(state.selectedEventId);
  } catch (err) {
    toast(`Stats error: ${err.message}`, "err");
  }
}

function renderStatsHub() {
  const d = state.statsData;
  if (!d) return;
  const t = d.totals || {};
  $("statsKpiGrid").innerHTML = [
    ["Matches", (t.matchesPlayed || 0).toLocaleString(), `${t.mapsPlayed || 0} maps`],
    ["Kills / Rounds", (t.kills || 0).toLocaleString(), `${(t.roundsPlayed || 0).toLocaleString()} rounds`],
    ["MVP / EVP", `${t.mvps || 0} / ${t.evps || 0}`, `${t.wins || 0} player event wins`],
    ["Titles", (t.titlesAwarded || 0).toLocaleString(), formatMoney(t.totalPrizePool || 0)],
  ]
    .map(([l, v, s]) => `<div class="kpi-card"><div class="kpi-label">${l}</div><div class="kpi-val">${v}</div><div class="kpi-sub">${escapeHtml(s)}</div></div>`)
    .join("");

  const q = ($("statsFilterQ").value || "").trim().toLowerCase();
  const ps = (d.players || []).filter((p) => !q || p.name.toLowerCase().includes(q) || p.teamName.toLowerCase().includes(q)).slice(0, 180);
  $("statsPlayersBody").innerHTML = ps
    .map(
      (p, i) => `<tr>
      <td class="muted">${i + 1}</td>
      <td><span class="link-cell" onclick="openPlayerStatsModal(${p.playerId})"><strong>${escapeHtml(p.name)}</strong></span></td>
      <td>${escapeHtml(p.teamName)}</td>
      <td class="mono ${p.rating >= 1.1 ? "stat-good" : ""}">${p.rating.toFixed(2)}</td>
      <td class="mono">${p.matches} (${p.matchesWon}-${p.matchesLost})</td>
      <td class="mono">${p.mapsPlayed}</td>
      <td class="mono">${p.kd.toFixed(2)}</td>
      <td class="mono">${p.adr.toFixed(1)}</td>
      <td>${p.mvps ? `<span class="pill pill-warn">${p.mvps} MVP</span> ` : ""}${p.evps ? `<span class="pill pill-blue">${p.evps} EVP</span>` : ""}</td>
    </tr>`
    )
    .join("");

  const ts = (d.teams || []).filter((tm) => !q || tm.name.toLowerCase().includes(q)).slice(0, 120);
  $("statsTeamsBody").innerHTML = ts
    .map(
      (tm) => `<tr>
      <td class="mono">#${tm.worldRank || "-"}</td>
      <td><span class="link-cell" onclick="openTeamStatsModal(${tm.teamId})"><strong>${escapeHtml(tm.name)}</strong></span></td>
      <td class="mono">${tm.rankingPoints}</td>
      <td class="mono">${tm.avgSkill}</td>
      <td class="mono">${tm.matchesWon}-${tm.matchesLost}</td>
      <td class="mono">${tm.mapsWon}-${tm.mapsLost}</td>
      <td class="mono">${tm.titles}</td>
      <td class="mono">${formatMoney(tm.balance)}</td>
    </tr>`
    )
    .join("");

  const t20 = d.top20Prediction?.candidates || [];
  $("top20Title").textContent = `HLTV / CSTV Top 20 Prediction (${d.top20Prediction?.year || ""})`;
  $("top20Note").textContent = "vs Top 10 Rating × Awards Multiplier × Sample";
  $("statsTop20Body").innerHTML = t20
    .slice(0, 30)
    .map(
      (c, i) => `<tr>
      <td><strong>#${i + 1}</strong></td>
      <td><span class="link-cell" onclick="openPlayerStatsModal(${c.playerId})"><strong>${escapeHtml(c.name)}</strong></span></td>
      <td>${escapeHtml(c.teamName)}</td>
      <td class="mono">${c.t10Rating.toFixed(3)}</td>
      <td class="mono">${c.overallRating.toFixed(3)}</td>
      <td class="mono">${c.t10Matches}</td>
      <td>${c.mvps} MVP / ${c.evps} EVP</td>
      <td class="mono"><strong>${c.baseScore.toFixed(3)}</strong></td>
    </tr>`
    )
    .join("");

  if (state.eventStatsData) renderEventStatsStudio();
}

async function loadEventStatsStudio(tid = null) {
  try {
    const url = tid ? `/api/stats/event?tournament_id=${encodeURIComponent(tid)}` : "/api/stats/event";
    state.eventStatsData = await api(url);
    if (state.eventStatsData.event?.id) state.selectedEventId = state.eventStatsData.event.id;
    renderEventStatsStudio();
  } catch (err) {
    toast(err.message, "err");
  }
}

function renderEventStatsStudio() {
  const data = state.eventStatsData;
  if (!data) return;
  const ev = data.event;
  $("statsEventSelect").innerHTML = (data.events || [])
    .map((e) => `<option value="${e.id}" ${e.id === (ev?.id || 0) ? "selected" : ""}>${escapeHtml(e.date)} — ${escapeHtml(e.name)} (Rep ${e.reputation})</option>`)
    .join("");
  if (!ev) return;

  const q = ($("statsFilterQ").value || "").trim().toLowerCase();
  const rows = (data.players || []).filter((p) => !q || p.playerName.toLowerCase().includes(q) || p.teamName.toLowerCase().includes(q));
  $("statsEventKpiGrid").innerHTML = [
    ["Champion / 2nd", ev.championName || "—", `2nd: ${ev.runnerUpName || "—"}`],
    ["Game MVP", ev.gameMvp ? `${ev.gameMvp.playerName} (${ev.gameMvp.score.toFixed(3)})` : "None", `Saved: ${ev.recordedMvp?.playerName || "—"}`],
    ["HLTV Fair MVP", ev.fairMvp ? `${ev.fairMvp.playerName} (${ev.fairMvp.score.toFixed(3)})` : "None", "Grand Finalist locked (1st/2nd)"],
    ["Biggest Snub", ev.biggestSnub ? ev.biggestSnub.playerName : "None", ev.biggestSnub ? `Fair #${ev.biggestSnub.fairRank} vs Game ${ev.biggestSnub.gameRank ? "#" + ev.biggestSnub.gameRank : "Inelig"}` : "—"],
  ]
    .map(([l, v, s]) => `<div class="kpi-card"><div class="kpi-label">${escapeHtml(l)}</div><div class="kpi-val" style="font-size:15.5px;">${escapeHtml(v)}</div><div class="kpi-sub">${escapeHtml(s)}</div></div>`)
    .join("");

  $("statsEventBody").innerHTML = rows
    .map(
      (p) => `<tr>
      <td><strong>#${p.fairRank}</strong></td>
      <td>${p.gameRank ? `#${p.gameRank}` : "—"}</td>
      <td class="${(p.rankDelta || 0) > 0 ? "stat-good" : (p.rankDelta || 0) < 0 ? "stat-bad" : "muted"}">${p.rankDelta === null ? "Inelig" : (p.rankDelta > 0 ? `+${p.rankDelta}` : p.rankDelta)}</td>
      <td><span class="link-cell" onclick="openPlayerStatsModal(${p.playerId})"><strong>${escapeHtml(p.playerName)}</strong></span></td>
      <td>${escapeHtml(p.teamName)}</td>
      <td>${escapeHtml(p.placement)}</td>
      <td class="mono">${p.matches}</td>
      <td class="mono">${p.maps} (${p.poMaps})</td>
      <td class="mono">${p.rating.toFixed(3)}</td>
      <td class="mono">${p.kd.toFixed(2)}</td>
      <td class="mono">${p.adr.toFixed(1)}</td>
      <td class="mono">${p.gameEligible ? p.gameScore.toFixed(3) : "Inelig"} ${p.gameProjectedAward ? `<span class="pill pill-blue">${p.gameProjectedAward}</span>` : ""}</td>
      <td class="mono"><strong>${p.fairScore.toFixed(3)}</strong> ${p.fairProjectedAward ? `<span class="pill pill-warn">${p.fairProjectedAward}</span>` : ""}</td>
      <td>${p.actualAward ? `<span class="pill pill-purple">${p.actualAward}</span>` : "—"}</td>
    </tr>`
    )
    .join("");
}

// ---- Deep Modals ----

async function openPlayerStatsModal(pid) {
  try {
    const d = await api(`/api/stats/player/${pid}`);
    const c = d.career || {};
    $("psModalTitle").textContent = `${d.player?.name || pid} — Career Stats`;
    $("psModalBody").innerHTML = `
      <div class="kpi-grid">
        <div class="kpi-card"><div class="kpi-label">Rating</div><div class="kpi-val">${(c.rating || 0).toFixed(2)}</div><div class="kpi-sub">${c.matches || 0}m (${c.matchesWon || 0}W-${c.matchesLost || 0}L)</div></div>
        <div class="kpi-card"><div class="kpi-label">K/D</div><div class="kpi-val">${(c.kd || 0).toFixed(2)}</div><div class="kpi-sub">${c.kills || 0}K / ${c.deaths || 0}D</div></div>
        <div class="kpi-card"><div class="kpi-label">ADR / HS%</div><div class="kpi-val">${(c.adr || 0).toFixed(1)}</div><div class="kpi-sub">${c.hsPct || 0}% HS</div></div>
        <div class="kpi-card"><div class="kpi-label">Quick Action</div><div class="kpi-val"><button class="btn btn-sm btn-cyan" onclick="$('playerStatsModal').classList.remove('open');activateTab('players');openPlayerPro(${pid});">Edit in Pro</button></div><div class="kpi-sub">Open full editor</div></div>
      </div>`;
    $("playerStatsModal").classList.add("open");
  } catch (err) {
    toast(err.message, "err");
  }
}

async function openTeamStatsModal(tid) {
  try {
    const d = await api(`/api/stats/team/${tid}`);
    const t = d.team || {};
    $("tsModalTitle").textContent = `${t.name || tid} — Org Telemetry`;
    const mpRows = (d.mapPool || [])
      .map(
        (m) => `<tr><td><strong>${escapeHtml(m.mapName)}</strong></td><td class="mono">${m.played}</td><td class="mono">${m.won}-${m.lost} (${m.winPct}%)</td><td class="mono">${m.pistolWinPct}%</td><td class="mono">${m.clutchesWon}</td></tr>`
      )
      .join("");
    $("tsModalBody").innerHTML = `
      <div class="kpi-grid">
        <div class="kpi-card"><div class="kpi-label">World Rank</div><div class="kpi-val">#${t.worldRank || "-"}</div><div class="kpi-sub">${t.rankingPoints || 0} pts &middot; ${escapeHtml(t.nationName || "")}</div></div>
        <div class="kpi-card"><div class="kpi-label">Matches / Maps</div><div class="kpi-val">${t.matchesWon || 0}-${t.matchesLost || 0}</div><div class="kpi-sub">Maps: ${t.mapsWon || 0}-${t.mapsLost || 0} &middot; Pistol ${t.pistolWinPct || 0}%</div></div>
        <div class="kpi-card"><div class="kpi-label">Prize Won / Clutches</div><div class="kpi-val">${formatMoney(t.prizeWon || 0)}</div><div class="kpi-sub">${t.clutchesWon || 0} clutches won</div></div>
        <div class="kpi-card"><div class="kpi-label">Quick Action</div><div class="kpi-val"><button class="btn btn-sm btn-cyan" onclick="$('teamStatsModal').classList.remove('open');activateTab('teams');openTeamPro(${tid});">Edit Org &amp; Sponsors</button></div><div class="kpi-sub">Open org editor</div></div>
      </div>
      ${mpRows ? `<div class="table-wrap" style="max-height:280px;"><table><thead><tr><th>Map</th><th>Played</th><th>W-L</th><th>Pistol %</th><th>Clutches</th></tr></thead><tbody>${mpRows}</tbody></table></div>` : ""}`;
    $("teamStatsModal").classList.add("open");
  } catch (err) {
    toast(err.message, "err");
  }
}

// ---- Bug Showcase & Vulture Transfer Modal ----

async function loadBugShowcaseStudio() {
  try {
    state.showcaseData = await api("/api/bug-showcase");
    renderBugShowcaseStudio();
  } catch (err) {
    toast(`Showcase error: ${err.message}`, "err");
  }
}

function renderBugShowcaseStudio() {
  const sc = state.showcaseData;
  if (!sc) return;
  const bl = sc.blowouts || {};
  const aw = sc.awards || {};
  const tx = sc.transfers || {};
  const st = sc.stability || {};
  const q = ($("showcaseFilterQ").value || "").trim().toLowerCase();

  $("scKpiGrid").innerHTML = [
    ["Blowouts (<=3 Rds Lost)", `${bl.blowoutLe3Pct || 0}% vs ${bl.proLe3Baseline || 9}% pro`, `${bl.shutouts13_0 || 0} shutouts (${bl.shutoutPct || 0}%) across ${bl.totalMaps || 0} maps`],
    ["Flagged MVP / EVP Awards", `${aw.flaggedCount || 0} / ${aw.totalEvaluated || 0}`, `${aw.outrankedMvps || 0} outranked MVPs`],
    ["Flagged AI Transfers", `${tx.flaggedTransfersCount || 0} / ${tx.totalPlayerTransfers || 0}`, `${tx.benchedOverStarterCount || 0} bench-over-starter crimes`],
    ["Post-Transfer Avg Stint", `${st.avgStintMonths || 0} months`, `Pro low end: 6.0m (${st.sub6MonthsPct || 0}% <6m)`],
  ]
    .map(([l, v, s]) => `<div class="kpi-card"><div class="kpi-label">${escapeHtml(l)}</div><div class="kpi-val" style="font-size:16px;">${escapeHtml(v)}</div><div class="kpi-sub">${escapeHtml(s)}</div></div>`)
    .join("");

  const ftxs = (tx.flaggedTransfers || []).filter((r) => !q || `${r.playerName} ${r.fromTeamName} ${r.toTeamName}`.toLowerCase().includes(q));
  state.showcaseTxShown = ftxs;
  $("scTransfersBody").innerHTML = ftxs
    .map((r, idx) => {
      const bCnt = r.bidderCount || 0;
      return `<tr class="tx-bidders-row" data-txidx="${idx}" style="cursor:pointer;">
        <td class="mono muted">${escapeHtml(r.date)}</td>
        <td><strong>${escapeHtml(r.playerName)}</strong> <span class="muted">(${r.skill.toFixed(2)} sk)</span></td>
        <td>${escapeHtml(r.fromTeamName)} &rarr; <strong>${escapeHtml(r.toTeamName)}</strong></td>
        <td class="mono">${r.purchasePrice > 0 ? formatMoney(r.purchasePrice) : "Free"}</td>
        <td><span class="pill ${bCnt >= 8 ? "pill-bad" : bCnt >= 3 ? "pill-warn" : "pill-blue"}">${bCnt} clubs</span></td>
        <td style="font-size:12px;">${(r.reasons || []).map((x) => escapeHtml(x)).join(" &bull; ")}</td>
      </tr>`;
    })
    .join("");

  $("scTransfersBody").querySelectorAll(".tx-bidders-row").forEach((tr) => {
    tr.addEventListener("click", () => {
      const row = state.showcaseTxShown?.[Number(tr.dataset.txidx)];
      if (row) openTransferBiddersModal(row);
    });
  });

  const awRows = (aw.flagged || []).filter((a) => !q || `${a.playerName} ${a.event}`.toLowerCase().includes(q));
  $("scAwardsBody").innerHTML = awRows
    .map(
      (a) => `<tr><td>${escapeHtml(a.event)} <span class="muted">(${escapeHtml(a.date)})</span></td><td><span class="pill ${a.role === "MVP" ? "pill-warn" : "pill-blue"}">${escapeHtml(a.role)}</span></td><td><strong>${escapeHtml(a.playerName)}</strong></td><td class="mono">${Number(a.rating || 0).toFixed(2)}</td><td>${escapeHtml(a.placement)}</td><td style="font-size:12px;">${escapeHtml((a.reasons || []).join(" · "))}</td></tr>`
    )
    .join("") || `<tr><td colspan="6" class="muted">No flagged award anomalies found in this save.</td></tr>`;

  const blEx = (bl.examples || []).filter((e) => !q || `${e.winner} ${e.loser} ${e.map}`.toLowerCase().includes(q)).slice(0, 40);
  $("scBlowoutsBody").innerHTML = `
    <div class="info-banner" style="margin-bottom:10px;">
      13-0 Shutouts: <strong>${bl.shutouts13_0 || 0} (${bl.shutoutPct || 0}%)</strong> vs Pro <strong>${bl.pro13_0Baseline || 1.2}%</strong> (${bl.shutoutMultiplier || 0}&times;) &bull;
      &le;3 Round Losses: <strong>${bl.blowoutsLe3 || 0} (${bl.blowoutLe3Pct || 0}%)</strong> vs Pro <strong>${bl.proLe3Baseline || 9}%</strong> &bull;
      12-0 Halves: <strong>${bl.halves12_0 || 0} (${bl.half12_0Pct || 0}%)</strong> vs Pro <strong>${bl.pro12_0Baseline || 0.8}%</strong>
    </div>
    ${blEx.length ? `<div class="table-wrap" style="max-height:46vh;"><table><thead><tr><th>Date</th><th>Tournament</th><th>Map</th><th>Score</th><th>Teams</th></tr></thead><tbody>${blEx
      .map((e) => `<tr><td class="mono muted">${escapeHtml(e.date)}</td><td>${escapeHtml(e.tournament)}</td><td>${escapeHtml(e.map)}</td><td class="mono"><strong>${escapeHtml(e.score)}</strong></td><td><strong>${escapeHtml(e.winner)}</strong> def. ${escapeHtml(e.loser)}</td></tr>`)
      .join("")}</tbody></table></div>` : `<div class="muted">No extreme blowout examples logged yet.</div>`}`;
}

function openTransferBiddersModal(tx) {
  const bidders = tx.bidders || [];
  $("tbModalTitle").textContent = `${tx.playerName} — Vulture Suitors & Bidders`;
  $("tbModalSubtitle").textContent = `${tx.fromTeamName} → ${tx.toTeamName} on ${tx.date} (${tx.purchasePrice > 0 ? formatMoney(tx.purchasePrice) : "Free"})`;
  $("tbModalBody").innerHTML = bidders.length
    ? `<div class="table-wrap" style="max-height:58vh;"><table>
        <thead><tr><th>#</th><th>Club</th><th>Rank &amp; Policy</th><th>Status</th><th>Roles</th><th>AI Score</th><th>Cooldown</th><th>Offer Limits</th></tr></thead>
        <tbody>${bidders
          .map(
            (b, i) => `<tr>
            <td class="muted">${i + 1}</td>
            <td><strong>${escapeHtml(b.teamName)}</strong>${b.teamId === tx.toTeamId ? ' <span class="pill pill-ok">Winner</span>' : ""}</td>
            <td>#${b.worldRank || "-"} · ${b.violatesPolicy ? `<span class="pill pill-bad">${escapeHtml(b.policyDetail)}</span>` : escapeHtml(b.hiringBiasLabel)}</td>
            <td><span class="pill ${b.isActiveBid ? "pill-warn" : b.isCooldownBid ? "pill-bad" : "pill-blue"}">${escapeHtml(b.bestStatusLabel)}</span></td>
            <td>${escapeHtml(b.rolesText || "Any")}</td>
            <td class="mono"><strong>${Number(b.peakScore || 0).toFixed(2)}</strong></td>
            <td class="mono">${b.maxCooldown ? `${b.maxCooldown}d` : "—"}</td>
            <td class="mono">${b.maxAbsoluteOffer ? `Max ${formatMoney(b.maxAbsoluteOffer)}` : b.offerSalary ? `Sal ${formatMoney(b.offerSalary)}` : "—"}</td>
          </tr>`
          )
          .join("")}</tbody>
      </table></div>`
    : `<div class="info-banner">No active/cooldown bidder records remain in <code>teams[].personInterests</code> for this transfer (93-day cooldown already expired).</div>`;
  $("transferBiddersModal").classList.add("open");
}

// ---- God Mode Balancer (All Teams + Blank Protected Star Box) ----

async function loadGodModeStudio() {
  try {
    state.godMode = await api("/api/god-mode/state");
    renderGodModeStudio();
  } catch (err) {
    toast(`God Mode error: ${err.message}`, "err");
  }
}

function filterGodModeTeamsStudio() {
  const sel = $("gmNerfTeam");
  if (!sel || !state.godMode) return;
  const q = ($("gmNerfTeamSearch")?.value || "").trim().toLowerCase();
  const curId = Number(state.godNerfSelectedTeamId || sel.value || 0);
  const teams = (state.godMode.teams || []).filter((t) => !q || `${t.worldRank} ${t.name}`.toLowerCase().includes(q));
  sel.innerHTML = teams.length
    ? teams.map((t) => `<option value="${t.teamId}" ${t.teamId === curId ? "selected" : ""}>#${t.worldRank || "-"} ${escapeHtml(t.name)} (Avg ${t.avgSkill})</option>`).join("")
    : `<option value="">No match</option>`;
  if (sel.value) state.godNerfSelectedTeamId = Number(sel.value);
}

function renderGodModeStudio() {
  const gm = state.godMode;
  if (!gm || !gm.loaded) {
    $("godModeBody").innerHTML = `<div class="card muted">Load a save first to use God Mode.</div>`;
    return;
  }
  const prev = {
    search: $("gmNerfTeamSearch")?.value || "",
    team: $("gmNerfTeam")?.value || state.godNerfSelectedTeamId || "",
    nerfProt: $("gmNerfProtect")?.value ?? "",
    floorProt: $("gmFloorProtect")?.value ?? "",
  };
  const sn = gm.snapshot || {};
  const teams = gm.teams || [];
  const res = state.godModeResult;

  const teamOpts = teams
    .map((t) => `<option value="${t.teamId}" ${String(t.teamId) === String(prev.team) ? "selected" : ""}>#${t.worldRank || "-"} ${escapeHtml(t.name)} (Avg ${t.avgSkill})</option>`)
    .join("");

  const resHtml = res
    ? `<div class="card" style="border-color:${res.dryRun ? "var(--amber)" : "var(--green)"};">
        <div class="card-header">
          <h3 class="card-title">${res.dryRun ? "DRY-RUN PREVIEW" : "APPLIED"} — ${escapeHtml(res.action)} (${res.changeCount} edits)</h3>
          <span class="pill ${res.dryRun ? "pill-warn" : "pill-ok"}">${res.dryRun ? "Preview" : "Applied (Undo saved)"}</span>
        </div>
        <div class="muted" style="font-size:12px;margin-bottom:8px;">${escapeHtml(res.summary)}</div>
        <div class="table-wrap" style="max-height:240px;"><table>
          <thead><tr><th>Target</th><th>Team</th><th>Detail</th></tr></thead>
          <tbody>${(res.changes || []).map((c) => `<tr><td><strong>${escapeHtml(c.target)}</strong></td><td>${escapeHtml(c.team)}</td><td>${escapeHtml(c.detail)}</td></tr>`).join("") || `<tr><td colspan="3" class="muted">No changes needed.</td></tr>`}</tbody>
        </table></div>
      </div>`
    : "";

  $("godModeBody").innerHTML = `
    <div class="kpi-grid">
      <div class="kpi-card"><div class="kpi-label">Managed Team Avg</div><div class="kpi-val">${sn.userAvgSkill || 0}</div><div class="kpi-sub">${escapeHtml(sn.userTeamName || "-")}</div></div>
      <div class="kpi-card"><div class="kpi-label">Top-10 / Top-20 Avg</div><div class="kpi-val">${sn.top10AvgSkill || 0} / ${sn.top20AvgSkill || 0}</div><div class="kpi-sub">Spread ${sn.top10Spread || 0} · Gini ${sn.top10Gini || 0}</div></div>
      <div class="kpi-card"><div class="kpi-label">AI Bench Crimes</div><div class="kpi-val">${sn.aiBenchSabotagesTop20 || 0}</div><div class="kpi-sub">Top-20 teams benching better players</div></div>
      <div class="kpi-card"><div class="kpi-label">Teams Available</div><div class="kpi-val">${teams.length}</div><div class="kpi-sub">Every active roster in save</div></div>
    </div>

    <div class="two-col">
      <div class="card">
        <div class="card-header"><h3 class="card-title">1. League Skill Floor &amp; Parity Smoother</h3></div>
        <div class="form-grid">
          <div class="field"><label>Scope</label><select id="gmFloorScope"><option value="top10">Top 10</option><option value="top20" selected>Top 20</option><option value="top30">Top 30</option><option value="all">All Teams</option></select></div>
          <div class="field"><label>Mode</label><select id="gmFloorMode"><option value="floor" selected>Raise Below Floor</option><option value="smooth_target">Smooth Toward Target</option><option value="weakest_slot_boost">Boost Weakest 2</option></select></div>
          <div class="field"><label>Target Skill</label><input id="gmFloorTarget" type="number" step="0.1" value="15.8" /></div>
          <div class="field"><label>Strength (%)</label><input id="gmFloorStrength" type="number" value="75" /></div>
          <div class="field"><label>Weakest +Delta</label><input id="gmFloorDelta" type="number" step="0.1" value="1.2" /></div>
          <div class="field"><label>Protect Stars (csv)</label><input id="gmFloorProtect" type="text" value="${escapeHtml(prev.floorProt)}" /></div>
        </div>
        <div class="inline-actions" style="justify-content:space-between;margin-top:10px;">
          <label class="checkbox-row"><input id="gmProtectUser" type="checkbox" checked /><span>Protect User Club</span></label>
          <div class="inline-actions">
            <button class="btn btn-sm" onclick="execGodModeStudio('boost_floor_parity', true)">Preview</button>
            <button class="btn btn-sm btn-ok" onclick="execGodModeStudio('boost_floor_parity', false)">Apply</button>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-header"><h3 class="card-title">2. Team Smoother (All ${teams.length} Teams)</h3></div>
        <div class="form-grid">
          <div class="field"><label>Filter Any Team</label><input id="gmNerfTeamSearch" type="text" value="${escapeHtml(prev.search)}" oninput="filterGodModeTeamsStudio()" /></div>
          <div class="field"><label>Target Team</label><select id="gmNerfTeam" onchange="state.godNerfSelectedTeamId=Number(this.value)">${teamOpts}</select></div>
          <div class="field"><label>Protect Star(s) (csv)</label><input id="gmNerfProtect" type="text" value="${escapeHtml(prev.nerfProt)}" /></div>
          <div class="field"><label>Target Avg</label><input id="gmNerfTargetAvg" type="number" step="0.1" value="16.2" /></div>
          <div class="field"><label>Cap Teammates</label><input id="gmNerfCap" type="number" step="0.1" value="17.0" /></div>
        </div>
        <div class="inline-actions" style="justify-content:flex-end;margin-top:10px;">
          <button class="btn btn-sm" onclick="execGodModeStudio('nerf_superteam_keep_stars', true)">Preview</button>
          <button class="btn btn-sm btn-warn" onclick="execGodModeStudio('nerf_superteam_keep_stars', false)">Smooth Team</button>
        </div>
      </div>
    </div>

    <div class="two-col">
      <div class="card">
        <div class="card-header"><h3 class="card-title">3. AI Bench, Language &amp; Economy Fixer</h3></div>
        <div class="inline-actions" style="margin-bottom:8px;">
          <select id="gmAiScope" style="width:150px;"><option value="top20" selected>Top 20</option><option value="all">All Teams</option></select>
          <button class="btn btn-sm" onclick="execGodModeStudio('fix_ai_sabotage', true)">Preview AI Fix</button>
          <button class="btn btn-sm btn-ok" onclick="execGodModeStudio('fix_ai_sabotage', false)">Fix AI Sabotages</button>
        </div>
        <div class="inline-actions">
          <input id="gmEconMinBal" type="number" step="100000" value="1000000" style="width:160px;" />
          <button class="btn btn-sm" onclick="execGodModeStudio('rebalance_economy', true)">Preview Econ</button>
          <button class="btn btn-sm btn-ok" onclick="execGodModeStudio('rebalance_economy', false)">Rebalance Cash</button>
        </div>
      </div>

      <div class="card">
        <div class="card-header"><h3 class="card-title">4. Wonderkid Injector</h3></div>
        <div class="inline-actions">
          <input id="gmWkCount" type="number" min="1" max="25" value="8" style="width:80px;" title="Count" />
          <input id="gmWkSkill" type="number" step="0.5" value="13.5" style="width:90px;" title="Base skill" />
          <button class="btn btn-sm" onclick="execGodModeStudio('inject_wonderkids', true)">Preview Spawn</button>
          <button class="btn btn-sm btn-cyan" onclick="execGodModeStudio('inject_wonderkids', false)">Spawn Wonderkids</button>
        </div>
      </div>
    </div>
    ${resHtml}`;

  if (prev.search) filterGodModeTeamsStudio();
}

async function execGodModeStudio(action, dryRun) {
  let params = {};
  if (action === "boost_floor_parity") {
    params = {
      scope: $("gmFloorScope").value,
      mode: $("gmFloorMode").value,
      targetFloor: Number($("gmFloorTarget").value),
      smoothTarget: Number($("gmFloorTarget").value),
      strengthPct: Number($("gmFloorStrength").value),
      boostDelta: Number($("gmFloorDelta").value),
      protectedNames: $("gmFloorProtect").value,
      protectUserTeam: $("gmProtectUser").checked,
    };
  } else if (action === "nerf_superteam_keep_stars") {
    params = {
      teamId: Number($("gmNerfTeam").value),
      protectedNames: $("gmNerfProtect").value,
      targetAvg: Number($("gmNerfTargetAvg").value),
      capNonProtected: Number($("gmNerfCap").value),
    };
  } else if (action === "fix_ai_sabotage") {
    params = { scope: $("gmAiScope").value, fixBench: true, syncLanguages: true, minStaffSkill: 15.0 };
  } else if (action === "rebalance_economy") {
    params = { scope: $("gmAiScope").value, minBalance: Number($("gmEconMinBal").value), maxBalanceCap: 0, minOwnerTier: 12 };
  } else if (action === "inject_wonderkids") {
    params = { count: Number($("gmWkCount").value), minAge: 16, maxAge: 18, baseSkill: Number($("gmWkSkill").value), potTarget: 19, useStartingPotential: true, startingPotential: 255, assignMode: "free_agents", nationMode: "diverse_pro" };
  }
  try {
    state.godModeResult = await api("/api/god-mode/run", { method: "POST", body: JSON.stringify({ action, params, dryRun }) });
    if (!dryRun) {
      state.godMode = await api("/api/god-mode/state");
      await refreshSaveSummary();
      toast(`Applied ${action} (${state.godModeResult.changeCount} edits)`, "ok");
    } else {
      toast(`Preview ready (${state.godModeResult.changeCount} edits)`, "ok");
    }
    renderGodModeStudio();
  } catch (err) {
    toast(err.message, "err");
  }
}
