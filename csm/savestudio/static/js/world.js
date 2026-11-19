/* Save Studio - Vulture Market Radar & Tournament Hub / Fair-Award Patcher */

function bindWorldEvents() {
  $("radarFilterQ").addEventListener("input", renderMarketRadar);
  $("btnRadarRefresh").addEventListener("click", loadMarketRadar);
  $("btnRadarPurgePolicy").addEventListener("click", () => execMarketRadarAction("purge_policy_violations", 0, 0));

  $("tournSearchQ").addEventListener("input", renderTournamentsList);
  $("btnBatchFairDry").addEventListener("click", () => runBatchFairPatch(true));
  $("btnBatchFairApply").addEventListener("click", () => runBatchFairPatch(false));
}

// ---- Vulture Market Radar ----

async function loadMarketRadar() {
  try {
    state.radarData = await api("/api/studio/market-radar");
    renderMarketRadar();
  } catch (err) {
    toast(`Market Radar error: ${err.message}`, "err");
  }
}

function renderMarketRadar() {
  const rd = state.radarData;
  if (!rd || !rd.loaded) return;
  const sum = rd.summary || {};
  const q = ($("radarFilterQ").value || "").trim().toLowerCase();

  const kpis = [
    ["Total Interest Entries", (sum.totalInterestRows || 0).toLocaleString(), "Live teams[].personInterests rows"],
    ["Distinct Hunted Players", (sum.huntedPlayers || 0).toLocaleString(), "Players currently on club radars"],
    ["Live Active Bids (1..6)", (sum.activeBids || 0).toLocaleString(), "Pending buyouts & contract offers"],
    ["Failed / Cooldown Rows (7..8)", (sum.cooldownRows || 0).toLocaleString(), "Rejected suitors on 93d cooldown"],
    ["Policy-Breaking Targets", (sum.policyViolations || 0).toLocaleString(), "'Only National / Lang' hunting outsiders"],
  ];
  $("radarKpiGrid").innerHTML = kpis
    .map(
      ([l, v, s]) => `<div class="kpi-card"><div class="kpi-label">${escapeHtml(l)}</div><div class="kpi-val">${escapeHtml(v)}</div><div class="kpi-sub">${escapeHtml(s)}</div></div>`
    )
    .join("");

  const swarms = (rd.vultureSwarms || []).filter(
    (s) => !q || s.playerName.toLowerCase().includes(q) || s.teamName.toLowerCase().includes(q) || (s.clubs || []).some((c) => c.teamName.toLowerCase().includes(q))
  );
  $("radarSwarmsBody").innerHTML = `
    <div class="table-wrap" style="max-height:58vh;">
      <table>
        <thead><tr><th>Player</th><th>Cur Club</th><th>Skill / Age</th><th>Clubs Hunting</th><th>Active</th><th>Cooldown</th><th>Policy Viol</th><th>Peak Score</th><th>Top Suitors &amp; Action</th></tr></thead>
        <tbody>${swarms
          .map(
            (s) => `<tr>
            <td><span class="link-cell" onclick="openPlayerStatsModal(${s.playerId})"><strong>${escapeHtml(s.playerName)}</strong></span>${s.benched ? ' <span class="pill pill-warn">Benched</span>' : ""}</td>
            <td>${escapeHtml(s.teamName)}</td>
            <td class="mono">${s.avgSkill.toFixed(2)} · ${s.age}y</td>
            <td><span class="pill ${s.distinctClubs >= 10 ? "pill-bad" : s.distinctClubs >= 4 ? "pill-warn" : "pill-blue"}">${s.distinctClubs} clubs</span></td>
            <td class="mono">${s.activeBids}</td>
            <td class="mono">${s.cooldowns}</td>
            <td class="mono ${s.policyMismatches ? "stat-bad" : "muted"}">${s.policyMismatches}</td>
            <td class="mono"><strong>${s.peakScore.toFixed(2)}</strong></td>
            <td style="font-size:12px;">
              ${escapeHtml((s.clubs || []).slice(0, 4).map((c) => c.teamName).join(", "))}
              ${s.cooldowns ? ` <button class="btn btn-sm radar-clr-pl-cd" data-pid="${s.playerId}">Clear CD</button>` : ""}
            </td>
          </tr>`
          )
          .join("") || `<tr><td colspan="9" class="muted">No hunted players matching filter.</td></tr>`}</tbody>
      </table>
    </div>`;

  const bids = (rd.activeBids || []).filter(
    (b) => !q || b.playerName.toLowerCase().includes(q) || b.bidderName.toLowerCase().includes(q) || b.fromTeamName.toLowerCase().includes(q)
  );
  $("radarActiveBody").innerHTML = `
    <div class="table-wrap" style="max-height:58vh;">
      <table>
        <thead><tr><th>Player</th><th>From</th><th>Bidder</th><th>Status</th><th>Role / Urg</th><th>Score</th><th>Salary / Buyout</th><th>Policy</th><th>Action</th></tr></thead>
        <tbody>${bids
          .map(
            (b) => `<tr>
            <td><span class="link-cell" onclick="openPlayerStatsModal(${b.playerId})"><strong>${escapeHtml(b.playerName)}</strong></span> <span class="mono muted">(${b.playerSkill.toFixed(1)})</span></td>
            <td>${escapeHtml(b.fromTeamName)}</td>
            <td><span class="link-cell" onclick="openTeamStatsModal(${b.bidderId})"><strong>${escapeHtml(b.bidderName)}</strong></span></td>
            <td><span class="pill pill-warn">${escapeHtml(b.statusLabel)}</span></td>
            <td>${escapeHtml(b.role)} · ${escapeHtml(b.urgency)}</td>
            <td class="mono">${b.score.toFixed(2)}</td>
            <td class="mono">${b.salaryYear ? formatMoney(b.salaryYear) : "-"} / ${b.buyoutPrice ? formatMoney(b.buyoutPrice) : "-"}</td>
            <td>${b.violatesPolicy ? `<span class="pill pill-bad">${escapeHtml(b.violationReason)}</span>` : `<span class="muted">OK</span>`}</td>
            <td><button class="btn btn-sm btn-bad radar-cancel-bid" data-pid="${b.playerId}" data-tid="${b.bidderId}">Cancel</button></td>
          </tr>`
          )
          .join("") || `<tr><td colspan="9" class="muted">No live active bids.</td></tr>`}</tbody>
      </table>
    </div>`;

  const clubs = (rd.clubActivity || []).filter((c) => !q || c.teamName.toLowerCase().includes(q));
  $("radarClubsBody").innerHTML = `
    <div class="table-wrap" style="max-height:58vh;">
      <table>
        <thead><tr><th>Club</th><th>Rank</th><th>Total Targets</th><th>Active Bids</th><th>Cooldowns</th><th>Policy Violations</th><th>Action</th></tr></thead>
        <tbody>${clubs
          .map(
            (c) => `<tr>
            <td><span class="link-cell" onclick="openTeamStatsModal(${c.teamId})"><strong>${escapeHtml(c.teamName)}</strong></span></td>
            <td class="mono">${c.worldRank ? `#${c.worldRank}` : "-"}</td>
            <td class="mono">${c.totalInterests}</td>
            <td class="mono">${c.activeBids}</td>
            <td class="mono">${c.cooldowns}</td>
            <td class="mono ${c.policyViolations ? "stat-bad" : "muted"}">${c.policyViolations}</td>
            <td>${c.cooldowns ? `<button class="btn btn-sm radar-clr-tm-cd" data-tid="${c.teamId}">Clear Cooldowns</button>` : "-"}</td>
          </tr>`
          )
          .join("")}</tbody>
      </table>
    </div>`;

  $("radarSwarmsBody").querySelectorAll(".radar-clr-pl-cd").forEach((btn) => {
    btn.addEventListener("click", () => execMarketRadarAction("clear_player_cooldowns", Number(btn.dataset.pid), 0));
  });
  $("radarActiveBody").querySelectorAll(".radar-cancel-bid").forEach((btn) => {
    btn.addEventListener("click", () => execMarketRadarAction("cancel_bid", Number(btn.dataset.pid), Number(btn.dataset.tid)));
  });
  $("radarClubsBody").querySelectorAll(".radar-clr-tm-cd").forEach((btn) => {
    btn.addEventListener("click", () => execMarketRadarAction("clear_team_cooldowns", 0, Number(btn.dataset.tid)));
  });
}

async function execMarketRadarAction(mode, playerId, teamId) {
  try {
    const res = await api("/api/studio/market-radar/action", {
      method: "POST",
      body: JSON.stringify({ mode, playerId, teamId }),
    });
    state.radarData = res.radar;
    toast(`Removed ${res.removedCount} market interest/cooldown entry(ies)`, "ok");
    await refreshSaveSummary();
    renderMarketRadar();
  } catch (err) {
    toast(err.message, "err");
  }
}

// ---- Tournament Control & Fair-Award Patcher ----

async function loadTournamentsHub() {
  try {
    state.tournamentsData = await api("/api/studio/tournaments");
    renderTournamentsList();
  } catch (err) {
    toast(`Tournaments error: ${err.message}`, "err");
  }
}

function renderTournamentsList() {
  const td = state.tournamentsData;
  if (!td || !td.loaded) return;
  const q = ($("tournSearchQ").value || "").trim().toLowerCase();
  const list = (td.tournaments || []).filter(
    (t) => !q || t.name.toLowerCase().includes(q) || (t.championName || "").toLowerCase().includes(q)
  );
  $("tournHubCount").textContent = `${list.length} events (${td.mvpMismatchCount || 0} MVP mismatches)`;

  const curId = state.selectedTournamentDetail?.meta?.id || 0;
  $("tournPickList").innerHTML = list
    .map(
      (t) => `<div class="pick-item ${t.id === curId ? "active" : ""}" data-tid="${t.id}">
        <div>
          <div><strong>${escapeHtml(t.name)}</strong> ${t.mvpMismatch ? `<span class="pill pill-bad">MVP Snub</span>` : t.hasRecordedAwards ? `<span class="pill pill-ok">${t.awardsCount} Aw</span>` : ""}</div>
          <div class="muted" style="font-size:11.5px;">${escapeHtml(t.date)} · Rep ${t.reputation} · ${escapeHtml(t.championName || "-")}</div>
        </div>
        <span class="mono muted">#${t.id}</span>
      </div>`
    )
    .join("");

  $("tournPickList").querySelectorAll(".pick-item").forEach((el) => {
    el.addEventListener("click", () => openTournamentDetail(Number(el.dataset.tid)));
  });

  if (list.length && !curId) {
    const firstAw = list.find((t) => t.mvpMismatch || t.hasRecordedAwards) || list[0];
    openTournamentDetail(firstAw.id);
  }
}

async function openTournamentDetail(tid) {
  try {
    state.selectedTournamentDetail = await api(`/api/studio/tournament/${tid}`);
    renderTournamentsList();
    renderTournamentDetail();
  } catch (err) {
    toast(err.message, "err");
  }
}

function renderTournamentDetail() {
  const d = state.selectedTournamentDetail;
  if (!d || !d.meta) return;
  const m = d.meta;
  const ev = d.event || {};
  const players = d.players || [];
  const slots = ev.awardSlots || {};

  const kpis = [
    ["Champion / 2nd", ev.championName || "—", `2nd: ${ev.runnerUpName || "—"}`],
    ["Saved MVP", ev.recordedMvp ? `${ev.recordedMvp.playerName} (${ev.recordedMvp.rating.toFixed(2)})` : "None", ev.recordedMvp?.placement || "—"],
    ["HLTV Fair MVP", ev.fairMvp ? `${ev.fairMvp.playerName} (${ev.fairMvp.rating.toFixed(2)})` : "None", `Slots: ${slots.mvp || 0} MVP / ${slots.evp || 0} EVP`],
    ["Sticker Pool", m.stickerMoneyGranted ? formatMoney(m.stickerMoneyGranted) : `${formatMoney(m.stickerMoneyLow)}–${formatMoney(m.stickerMoneyHigh)}`, m.bestOfFiveGrandFinals ? "BO5 Grand Final" : "BO3 Grand Final"],
  ];

  $("tournDetailBody").innerHTML = `
    <div class="card-header">
      <div>
        <h3 class="card-title">${escapeHtml(m.name)} <span class="muted">(#${m.id} · ${escapeHtml(ev.date || "")})</span></h3>
        <div class="muted" style="font-size:12px;">${(d.stages || []).map((s) => `${s.name} (${s.matchCount}m)`).join(" -> ") || "No stage records yet"}</div>
      </div>
      <div class="inline-actions">
        <button id="btnTournSaveMeta" class="btn btn-sm btn-blue">Save Meta</button>
        <button id="btnTournPatchDry" class="btn btn-sm btn-cyan">Preview Fair Awards</button>
        <button id="btnTournPatchApply" class="btn btn-sm btn-warn">Apply Fair Awards</button>
      </div>
    </div>

    <div class="kpi-grid">${kpis
      .map(
        ([l, v, s]) => `<div class="kpi-card"><div class="kpi-label">${escapeHtml(l)}</div><div class="kpi-val" style="font-size:15.5px;">${escapeHtml(v)}</div><div class="kpi-sub">${escapeHtml(s)}</div></div>`
      )
      .join("")}</div>

    <div class="form-grid" style="margin-bottom:12px;">
      <div class="field"><label>Reputation (1-20)</label><input id="tmRepInput" type="number" min="1" max="20" value="${m.reputation}" /></div>
      <div class="field"><label>Sticker Low ($)</label><input id="tmStickLo" type="number" step="50000" value="${m.stickerMoneyLow}" /></div>
      <div class="field"><label>Sticker High ($)</label><input id="tmStickHi" type="number" step="50000" value="${m.stickerMoneyHigh}" /></div>
      <div class="field" style="justify-content:end;"><label class="checkbox-row"><input id="tmBo5Check" type="checkbox" ${m.bestOfFiveGrandFinals ? "checked" : ""} /><span>BO5 Grand Final</span></label></div>
    </div>

    <div id="tournPatchPreviewBox"></div>

    <div class="table-wrap" style="max-height:52vh;">
      <table>
        <thead><tr><th>Fair #</th><th>Game #</th><th>Player</th><th>Team</th><th>Place</th><th>M (PO Maps)</th><th>Rating</th><th>Game Score</th><th>Fair Score</th><th>Saved</th></tr></thead>
        <tbody>${players
          .slice(0, 60)
          .map(
            (p) => `<tr>
            <td><strong>#${p.fairRank}</strong></td>
            <td>${p.gameRank ? `#${p.gameRank}` : "—"}</td>
            <td><span class="link-cell" onclick="openPlayerStatsModal(${p.playerId})"><strong>${escapeHtml(p.playerName)}</strong></span></td>
            <td>${escapeHtml(p.teamName)}</td>
            <td>${escapeHtml(p.placement)}</td>
            <td class="mono">${p.matches} (${p.poMaps})</td>
            <td class="mono ${p.rating >= 1.15 ? "stat-good" : ""}">${p.rating.toFixed(3)}</td>
            <td class="mono">${p.gameEligible ? p.gameScore.toFixed(3) : "Inelig"} ${p.gameProjectedAward ? `<span class="pill pill-blue">${p.gameProjectedAward}</span>` : ""}</td>
            <td class="mono"><strong>${p.fairScore.toFixed(3)}</strong> ${p.fairProjectedAward ? `<span class="pill ${p.fairProjectedAward === "MVP" ? "pill-warn" : "pill-ok"}">${p.fairProjectedAward}</span>` : ""}</td>
            <td>${p.actualAward ? `<span class="pill pill-purple">${p.actualAward}</span>` : "—"}</td>
          </tr>`
          )
          .join("") || `<tr><td colspan="10" class="muted">No played matches for this tournament yet.</td></tr>`}</tbody>
      </table>
    </div>`;

  $("btnTournSaveMeta").addEventListener("click", () => saveTournamentMeta(m.id));
  $("btnTournPatchDry").addEventListener("click", () => runTournamentAwardPatch(m.id, "fair", true));
  $("btnTournPatchApply").addEventListener("click", () => runTournamentAwardPatch(m.id, "fair", false));
}

async function saveTournamentMeta(tid) {
  try {
    state.selectedTournamentDetail = await api(`/api/studio/tournament/${tid}/meta`, {
      method: "POST",
      body: JSON.stringify({
        reputation: Number($("tmRepInput").value),
        stickerMoneyLow: Number($("tmStickLo").value),
        stickerMoneyHigh: Number($("tmStickHi").value),
        bestOfFiveGrandFinals: $("tmBo5Check").checked,
      }),
    });
    toast("Saved tournament metadata", "ok");
    await refreshSaveSummary();
    loadTournamentsHub();
    renderTournamentDetail();
  } catch (err) {
    toast(err.message, "err");
  }
}

async function runTournamentAwardPatch(tid, mode, dryRun) {
  try {
    const res = await api(`/api/studio/tournament/${tid}/patch-awards`, {
      method: "POST",
      body: JSON.stringify({ mode, dryRun }),
    });
    const fmt = (arr) => (arr || []).map((x) => `${x.playerName} (${x.role})`).join(", ") || "None";
    $("tournPatchPreviewBox").innerHTML = `
      <div class="${dryRun ? "warn-banner" : "info-banner"}" style="margin-bottom:10px;">
        <strong>${dryRun ? "DRY-RUN PREVIEW" : "PATCH APPLIED"}:</strong> ${escapeHtml(res.tournamentName)} (${res.year}-${String(res.month).padStart(2, "0")})<br>
        <strong>Before:</strong> ${escapeHtml(fmt(res.oldAwards))}<br>
        <strong>After (Fair Score):</strong> ${escapeHtml(fmt(res.newAwards))}
      </div>`;
    if (!dryRun) {
      toast("Patched tournament & player awards!", "ok");
      await refreshSaveSummary();
      state.tournamentsData = await api("/api/studio/tournaments");
      state.selectedTournamentDetail = await api(`/api/studio/tournament/${tid}`);
      renderTournamentsList();
      renderTournamentDetail();
    }
  } catch (err) {
    toast(err.message, "err");
  }
}

async function runBatchFairPatch(dryRun) {
  if (!dryRun && !window.confirm("Retroactively patch ALL completed S-Tier & Major tournaments (Rep 13+) with Fair-Score MVPs/EVPs? (Event Win & Top-20 awards stay intact, and an Undo checkpoint is saved.)")) return;
  try {
    const res = await api("/api/studio/tournaments/batch-fair-awards", {
      method: "POST",
      body: JSON.stringify({ minReputation: 13, dryRun }),
    });
    $("tournBatchResult").innerHTML = `
      <div class="${dryRun ? "warn-banner" : "info-banner"}" style="margin-top:8px;">
        <strong>${dryRun ? "BATCH PREVIEW" : "BATCH APPLIED"}:</strong> Scanned ${res.scannedEvents} tournaments (Rep &ge; ${res.minReputation}) &rarr; <strong>${res.changedEvents} events updated</strong> (${res.mvpChanges} MVP winner flips).
        ${(res.diffs || []).length
          ? `<div class="table-wrap" style="max-height:220px;margin-top:8px;"><table><thead><tr><th>Date</th><th>Event</th><th>Old MVP</th><th>New Fair MVP</th></tr></thead><tbody>${res.diffs
              .map((d) => `<tr><td class="mono">${escapeHtml(d.date)}</td><td>${escapeHtml(d.name)}</td><td class="${d.mvpChanged ? "stat-bad" : ""}">${escapeHtml(d.oldMvp)}</td><td class="${d.mvpChanged ? "stat-good" : ""}">${escapeHtml(d.newMvp)}</td></tr>`)
              .join("")}</tbody></table></div>`
          : ""}
      </div>`;
    if (!dryRun) {
      toast(`Patched ${res.changedEvents} tournaments (${res.mvpChanges} MVP changes)!`, "ok");
      await refreshSaveSummary();
      loadTournamentsHub();
    }
  } catch (err) {
    toast(err.message, "err");
  }
}
