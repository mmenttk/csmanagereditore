/* Save Studio - Career HQ Dashboard & Save Diff Time Machine */

function bindDashboardEvents() {
  $("btnHqSave").addEventListener("click", saveCareerHq);
  $("btnHqSwitchTeam").addEventListener("click", switchManagedTeam);
  $("btnHqHealSquad").addEventListener("click", healManagedSquad);
  $("btnRunDiff").addEventListener("click", runSaveDiff);
}

async function loadCareerHq() {
  try {
    state.hqData = await api("/api/studio/career-hq");
    renderCareerHq();
  } catch (err) {
    toast(`Career HQ error: ${err.message}`, "err");
  }
}

function renderCareerHq() {
  const hq = state.hqData;
  if (!hq || !hq.loaded) return;
  const t = hq.team;
  const prof = hq.profile || {};
  const con = hq.managerContract || {};

  const cards = [
    ["Managed Club", t ? t.name : "Unemployed", t ? `Rank #${t.worldRank || "-"} · Rep ${t.reputation}` : "Pick a club to take over"],
    ["Club Balance", t ? formatMoney(t.balance) : "-", t ? `${t.trophiesCount} titles won` : "—"],
    ["Starting 5 Skill", t ? t.avgSkill.toFixed(2) : "-", t ? `${t.starterCount} active / ${t.benchedCount} bench` : "—"],
    ["Squad Burnout / Mood", t ? `${(t.avgBurnout * 100).toFixed(1)}% / ${t.avgMood.toFixed(1)}` : "-", "Lower burnout & higher mood = peak form"],
    ["Coach Salary", con.salaryYear ? formatMoney(con.salaryYear) : "-", con.endDate ? `Until ${formatDateObj(con.endDate)}` : "—"],
    ["Save Date", formatDateObj(hq.datetime), state.summary?.fileName || ""],
  ];
  $("hqKpiGrid").innerHTML = cards
    .map(
      ([l, v, s]) => `<div class="kpi-card">
      <div class="kpi-label">${escapeHtml(l)}</div>
      <div class="kpi-val" style="font-size:17px;">${escapeHtml(v)}</div>
      <div class="kpi-sub">${escapeHtml(s)}</div>
    </div>`
    )
    .join("");

  $("hqMgrName").value = prof.name || "";
  $("hqMgrAge").value = prof.age || 30;
  if (prof.nation) $("hqMgrNation").value = String(prof.nation);
  $("hqMgrSalary").value = con.salaryYear || 500000;

  const teams = hq.allTeams || [];
  $("hqSwitchTeamSelect").innerHTML = teams
    .map((tm) => `<option value="${tm.id}" ${tm.id === prof.teamId ? "selected" : ""}>#${tm.worldRank || "-"} ${escapeHtml(tm.name)} (${tm.avgSkill} sk · ${formatMoney(tm.balance)})</option>`)
    .join("");

  if (t) {
    $("hqJobSecGrid").style.opacity = "1";
    const js = t.jobSecurity || {};
    $("hqSecLeague").value = Number(js.securityFromLeague ?? 0.5).toFixed(2);
    $("hqSecChamp").value = Number(js.securityFromChampionship ?? 0.5).toFixed(2);
    $("hqSecRank").value = Number(js.securityFromRanking ?? 0.5).toFixed(2);
    $("hqSecBudget").value = Number(js.securityFromBudget ?? 0.5).toFixed(2);
    $("hqSecLong").value = Number(js.securityFromLongevity ?? 0.5).toFixed(2);
    $("hqSecSquad").value = Number(js.securityFromSquadComposition ?? 0.5).toFixed(2);
    $("hqGracePeriod").value = js.gracePeriod ?? 0;
    $("hqRankingGoal").value = js.rankingGoal ?? 0;

    $("hqRankChart").innerHTML = renderSparklineSvg(t.rankingHistory || [], {
      invert: true,
      minVal: 1,
      height: 82,
      color: "#22c55e",
    });

    $("hqRosterBody").innerHTML = (t.roster || []).length
      ? t.roster
          .map(
            (r) => `<tr>
            <td><span class="link-cell" onclick="activateTab('players');openPlayerPro(${r.playerId});">${escapeHtml(r.name)}</span></td>
            <td>${r.age}</td>
            <td class="mono">${r.avgSkill.toFixed(2)}</td>
            <td class="mono ${r.burnout > 0.25 ? "stat-bad" : ""}">${(r.burnout * 100).toFixed(1)}%</td>
            <td class="mono ${r.mood >= 0 ? "stat-good" : "stat-bad"}">${r.mood.toFixed(2)}</td>
            <td>${r.benched ? `<span class="pill pill-warn">Bench</span>` : `<span class="pill pill-ok">Starter</span>`}</td>
          </tr>`
          )
          .join("")
      : `<tr><td colspan="6" class="muted">No contracted players.</td></tr>`;
  } else {
    $("hqJobSecGrid").style.opacity = "0.5";
    $("hqRankChart").innerHTML = `<div class="muted">Unemployed</div>`;
    $("hqRosterBody").innerHTML = "";
  }
}

async function saveCareerHq() {
  try {
    state.hqData = await api("/api/studio/career-hq/update", {
      method: "POST",
      body: JSON.stringify({
        profile: {
          name: $("hqMgrName").value.trim(),
          age: Number($("hqMgrAge").value || 30),
          nation: Number($("hqMgrNation").value || 1),
        },
        managerContract: {
          salaryYear: Number($("hqMgrSalary").value || 0),
        },
        jobSecurity: {
          securityFromLeague: Number($("hqSecLeague").value || 0),
          securityFromChampionship: Number($("hqSecChamp").value || 0),
          securityFromRanking: Number($("hqSecRank").value || 0),
          securityFromBudget: Number($("hqSecBudget").value || 0),
          securityFromLongevity: Number($("hqSecLong").value || 0),
          securityFromSquadComposition: Number($("hqSecSquad").value || 0),
          gracePeriod: Number($("hqGracePeriod").value || 0),
          rankingGoal: Number($("hqRankingGoal").value || 0),
        },
      }),
    });
    toast("Career HQ & Job Security saved", "ok");
    await refreshSaveSummary();
    renderCareerHq();
  } catch (err) {
    toast(err.message, "err");
  }
}

async function switchManagedTeam() {
  const tid = Number($("hqSwitchTeamSelect").value || 0);
  if (!tid) return;
  try {
    state.hqData = await api("/api/studio/career-hq/switch-team", {
      method: "POST",
      body: JSON.stringify({ teamId: tid, swapCoach: $("hqSwapCoach").checked }),
    });
    toast(`Took over ${state.hqData.team?.name || tid}!`, "ok");
    await refreshSaveSummary();
    renderCareerHq();
  } catch (err) {
    toast(err.message, "err");
  }
}

async function healManagedSquad() {
  const tid = state.hqData?.team?.id;
  if (!tid) return toast("No managed team active.", "err");
  try {
    const res = await api(`/api/studio/team/${tid}/heal`, {
      method: "POST",
      body: JSON.stringify({ resetBurnout: true, maxMood: true, clearCooldowns: false }),
    });
    toast(`Healed ${res.healedPlayers} players' burnout & mood!`, "ok");
    await refreshSaveSummary();
    loadCareerHq();
  } catch (err) {
    toast(err.message, "err");
  }
}

// ---- Save Diff & Time Machine ----

async function loadComparableSaves() {
  try {
    const res = await api("/api/studio/diff/saves");
    state.comparableSaves = res.saves || [];
    const others = state.comparableSaves.filter((s) => !s.isCurrent);
    const list = others.length ? others : state.comparableSaves;
    $("diffBaselineSelect").innerHTML = list.length
      ? list.map((s) => `<option value="${escapeHtml(s.path)}">[${escapeHtml(s.source)}] ${escapeHtml(s.name)} (${s.size_mb} MB · ${escapeHtml(s.modified)})</option>`).join("")
      : `<option value="">No comparison saves found</option>`;
  } catch (err) {
    toast(`Save list error: ${err.message}`, "err");
  }
}

async function runSaveDiff() {
  const bpath = $("diffBaselineSelect").value;
  if (!bpath) return toast("Select a baseline save first.", "err");
  $("diffBody").innerHTML = `<div class="card"><div class="muted">Comparing saves...</div></div>`;
  try {
    state.diffData = await api("/api/studio/diff/compare", {
      method: "POST",
      body: JSON.stringify({ baselinePath: bpath }),
    });
    renderDiffResult();
  } catch (err) {
    $("diffBody").innerHTML = `<div class="card stat-bad">${escapeHtml(err.message)}</div>`;
  }
}

function renderDiffResult() {
  const d = state.diffData;
  if (!d) return;
  const bm = d.baselineMeta || {};
  const cm = d.currentMeta || {};

  $("diffBody").innerHTML = `
    <div class="kpi-grid">
      <div class="kpi-card"><div class="kpi-label">Baseline -> Current</div><div class="kpi-val" style="font-size:15px;">${escapeHtml(bm.date)} -> ${escapeHtml(cm.date)}</div><div class="kpi-sub">${escapeHtml(bm.name)} vs ${escapeHtml(cm.name)}</div></div>
      <div class="kpi-card"><div class="kpi-label">Skill Risers / Fallers</div><div class="kpi-val">${(d.skillRisers || []).length} / ${(d.skillFallers || []).length}</div><div class="kpi-sub">Tracked player deltas</div></div>
      <div class="kpi-card"><div class="kpi-label">Rank Climbers / Fallers</div><div class="kpi-val">${(d.rankClimbers || []).length} / ${(d.rankFallers || []).length}</div><div class="kpi-sub">World rank shifts</div></div>
      <div class="kpi-card"><div class="kpi-label">New Transfers / Trophies</div><div class="kpi-val">${(d.newTransfers || []).length} / ${(d.newTrophies || []).length}</div><div class="kpi-sub">${(d.newAwards || []).length} new MVP/EVP/Top20s</div></div>
    </div>

    <div class="two-col">
      <div class="card">
        <div class="card-header"><h3 class="card-title">Biggest Skill Improvers</h3></div>
        <div class="table-wrap" style="max-height:320px;"><table>
          <thead><tr><th>Player</th><th>Team</th><th>Before</th><th>After</th><th>Delta</th></tr></thead>
          <tbody>${(d.skillRisers || []).map((r) => `<tr><td><span class="link-cell" onclick="openPlayerStatsModal(${r.playerId})">${escapeHtml(r.name)}</span></td><td>${escapeHtml(r.teamName)}</td><td class="mono">${r.beforeAvg}</td><td class="mono">${r.afterAvg}</td><td class="mono stat-good">+${r.delta}</td></tr>`).join("") || `<tr><td colspan="5" class="muted">No skill increases.</td></tr>`}</tbody>
        </table></div>
      </div>

      <div class="card">
        <div class="card-header"><h3 class="card-title">Biggest Skill Regressions</h3></div>
        <div class="table-wrap" style="max-height:320px;"><table>
          <thead><tr><th>Player</th><th>Team</th><th>Before</th><th>After</th><th>Delta</th></tr></thead>
          <tbody>${(d.skillFallers || []).map((r) => `<tr><td><span class="link-cell" onclick="openPlayerStatsModal(${r.playerId})">${escapeHtml(r.name)}</span></td><td>${escapeHtml(r.teamName)}</td><td class="mono">${r.beforeAvg}</td><td class="mono">${r.afterAvg}</td><td class="mono stat-bad">${r.delta}</td></tr>`).join("") || `<tr><td colspan="5" class="muted">No skill drops.</td></tr>`}</tbody>
        </table></div>
      </div>
    </div>

    <div class="two-col">
      <div class="card">
        <div class="card-header"><h3 class="card-title">World Rank Movers</h3></div>
        <div class="table-wrap" style="max-height:320px;"><table>
          <thead><tr><th>Team</th><th>Before #</th><th>Now #</th><th>Shift</th></tr></thead>
          <tbody>${[...(d.rankClimbers || []).slice(0, 15), ...(d.rankFallers || []).slice(0, 15)]
            .map((r) => `<tr><td><span class="link-cell" onclick="openTeamStatsModal(${r.teamId})">${escapeHtml(r.name)}</span></td><td class="mono">#${r.beforeRank}</td><td class="mono">#${r.afterRank}</td><td class="mono ${r.climb > 0 ? "stat-good" : "stat-bad"}">${r.climb > 0 ? `+${r.climb}` : r.climb}</td></tr>`)
            .join("") || `<tr><td colspan="4" class="muted">No ranking changes.</td></tr>`}</tbody>
        </table></div>
      </div>

      <div class="card">
        <div class="card-header"><h3 class="card-title">New Transfers &amp; Trophies Since Baseline</h3></div>
        <div class="table-wrap" style="max-height:320px;"><table>
          <thead><tr><th>Type</th><th>Details</th><th>Meta</th></tr></thead>
          <tbody>
            ${(d.newTrophies || []).map((t) => `<tr><td><span class="pill pill-warn">Trophy</span></td><td><strong>${escapeHtml(t.teamName)}</strong> won ${escapeHtml(t.tournamentName)}</td><td class="mono muted">${t.year}</td></tr>`).join("")}
            ${(d.newAwards || []).slice(0, 20).map((a) => `<tr><td><span class="pill pill-blue">${escapeHtml(a.typeLabel)}</span></td><td><strong>${escapeHtml(a.playerName)}</strong> (${escapeHtml(a.tournamentName)})</td><td class="mono muted">${escapeHtml(a.date)}</td></tr>`).join("")}
            ${(d.newTransfers || []).slice(0, 30).map((x) => `<tr><td><span class="pill">${escapeHtml(x.personType)}</span></td><td><strong>${escapeHtml(x.personName)}</strong>: ${escapeHtml(x.fromTeamName)} &rarr; ${escapeHtml(x.toTeamName)}</td><td class="mono">${x.purchasePrice > 0 ? formatMoney(x.purchasePrice) : "Free"}</td></tr>`).join("")}
          </tbody>
        </table></div>
      </div>
    </div>`;
}
