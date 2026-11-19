/* Save Studio - Roster Sandbox & Matchup Sim, Growth Lab & Weapon Meta Lab */

let _sbSearchTimer = null;

function bindLabEvents() {
  $("sbTeamSelect").addEventListener("change", () => loadTeamIntoSandbox(Number($("sbTeamSelect").value)));
  $("sbRivalSelect").addEventListener("change", runSandboxSimulation);
  $("sbPlayerSearch").addEventListener("input", () => {
    clearTimeout(_sbSearchTimer);
    _sbSearchTimer = setTimeout(searchSandboxCandidates, 160);
  });
  $("btnSandboxSimulate").addEventListener("click", runSandboxSimulation);
  $("btnSandboxCommit").addEventListener("click", commitSandboxToSave);

  $("btnGrowthRefresh").addEventListener("click", loadGrowthLab);
  $("growthFilterQ").addEventListener("input", renderGrowthTable);

  $("weaponTypeFilter").addEventListener("change", renderWeaponsTable);
  $("weaponSearchQ").addEventListener("input", renderWeaponsTable);
  $("btnWepPresetAwp").addEventListener("click", () => applyWeaponPreset("awp_era"));
  $("btnWepPresetRifle").addEventListener("click", () => applyWeaponPreset("rifle_laser"));
  $("btnWepPresetEco").addEventListener("click", () => applyWeaponPreset("eco_chaos"));
  $("btnWepPresetBal").addEventListener("click", () => applyWeaponPreset("cs2_balanced"));
}

// ---- Roster Sandbox & Matchup Simulator ----

async function initSandboxTab() {
  if (!state.teams.length) return;
  const userTid = state.summary?.userTeamId || state.teams[0].id;
  if (!state.sandboxTeamId || !state.teams.some((t) => t.id === state.sandboxTeamId)) {
    state.sandboxTeamId = userTid;
  }
  const teamOpts = state.teams.map((t) => `<option value="${t.id}" ${t.id === state.sandboxTeamId ? "selected" : ""}>#${t.worldRank || "-"} ${escapeHtml(t.name)} (${t.avgSkill} sk)</option>`).join("");
  $("sbTeamSelect").innerHTML = teamOpts;
  const curRival = Number($("sbRivalSelect").value || state.teams.find((t) => t.id !== state.sandboxTeamId)?.id || state.teams[0].id);
  $("sbRivalSelect").innerHTML = state.teams.map((t) => `<option value="${t.id}" ${t.id === curRival ? "selected" : ""}>#${t.worldRank || "-"} ${escapeHtml(t.name)} (${t.avgSkill} sk)</option>`).join("");

  if (!state.sandboxCandidates.length) await searchSandboxCandidates();
  if (!state.sandboxSlots.length) await loadTeamIntoSandbox(state.sandboxTeamId);
  else renderSandboxView();
}

async function searchSandboxCandidates() {
  try {
    const q = $("sbPlayerSearch").value.trim();
    const res = await api(`/api/players?q=${encodeURIComponent(q)}&limit=100`);
    state.sandboxCandidates = res.items || [];
    $("sbCandidateSelect").innerHTML = state.sandboxCandidates
      .map((p) => `<option value="${p.id}">${escapeHtml(p.name)} (${p.avgSkill.toFixed(2)} sk · ${p.age}y · ${escapeHtml(p.teamName)})</option>`)
      .join("");
  } catch (err) {
    toast(err.message, "err");
  }
}

async function loadTeamIntoSandbox(teamId) {
  if (!teamId) return;
  state.sandboxTeamId = teamId;
  try {
    const tRes = await api(`/api/studio/team/${teamId}`);
    const starters = (tRes.roster || []).filter((r) => !r.benched).slice(0, 5);
    state.sandboxSlots = starters.map((r) => r.playerId);
    if (!state.sandboxSlots.length && tRes.roster?.length) {
      state.sandboxSlots = tRes.roster.slice(0, 5).map((r) => r.playerId);
    }
    await runSandboxSimulation();
  } catch (err) {
    toast(err.message, "err");
  }
}

function assignSandboxSlot(slotIndex) {
  const newPid = Number($("sbCandidateSelect").value || 0);
  if (!newPid) return toast("Pick a candidate player from the dropdown first.", "err");
  if (state.sandboxSlots.includes(newPid) && state.sandboxSlots[slotIndex] !== newPid) {
    return toast("That player is already in another starting slot.", "err");
  }
  state.sandboxSlots[slotIndex] = newPid;
  runSandboxSimulation();
}

async function runSandboxSimulation() {
  if (!state.sandboxTeamId || !state.sandboxSlots.length) return;
  try {
    state.sandboxResult = await api("/api/studio/sandbox/simulate", {
      method: "POST",
      body: JSON.stringify({
        teamId: state.sandboxTeamId,
        playerIds: state.sandboxSlots,
        vsTeamId: Number($("sbRivalSelect").value || 0),
      }),
    });
    renderSandboxView();
  } catch (err) {
    toast(err.message, "err");
  }
}

function renderSandboxView() {
  const r = state.sandboxResult;
  if (!r) {
    $("sandboxBody").innerHTML = `<div class="card muted">Select an organization to start simulating.</div>`;
    return;
  }
  const sim = r.simulated;
  const base = r.baseline;
  const opp = r.vsOpponent;

  const kpis = [
    ["Simulated Avg Skill", sim.avgSkill.toFixed(2), `${r.skillDiff >= 0 ? "+" : ""}${r.skillDiff.toFixed(2)} vs current (${base.avgSkill.toFixed(2)})`],
    ["Bo3 Odds vs Top-10", `${sim.simTop10Bo3Pct ?? r.simTop10Bo3Pct}%`, `Current baseline: ${r.baseTop10Bo3Pct}%`],
    [
      opp ? `H2H vs ${opp.teamName}` : "Head-to-Head",
      opp ? `Bo3 ${opp.bo3Pct}%` : "-",
      opp ? `Bo1 ${opp.bo1Pct}% · Bo5 ${opp.bo5Pct}% · Skill ${opp.skillDelta >= 0 ? "+" : ""}${opp.skillDelta}` : "-",
    ],
    ["Payroll / Avg Age", formatMoney(sim.totalSalary), `Diff ${r.salaryDiff >= 0 ? "+" : ""}${formatMoney(r.salaryDiff)} · ${sim.avgAge}y avg`],
    ["Core Breakdown", `${sim.mechAvg} / ${sim.weaponAvg} / ${sim.mentalAvg}`, "Mech / Weapons / Mental"],
  ];

  const slotsHtml = (sim.players || [])
    .map(
      (p, idx) => `<tr>
        <td class="mono muted">Slot ${idx + 1}</td>
        <td><strong>${escapeHtml(p.name)}</strong> <span class="muted">(${p.age}y · ${escapeHtml(p.teamName)})</span></td>
        <td class="mono">${p.practicalAvg.toFixed(2)}</td>
        <td class="mono">${p.desireToIgl >= 15 ? '<span class="pill pill-purple">IGL</span>' : p.desireToAwp >= 15 ? '<span class="pill pill-cyan">AWP</span>' : "Rifle"} <span class="muted">(${p.leadership}/${p.snipers})</span></td>
        <td style="font-size:11.5px;">${escapeHtml((p.languages || []).join(", ") || "None")}</td>
        <td class="mono">${formatMoney(p.salaryYear)}</td>
        <td><button class="btn btn-sm btn-cyan sb-swap-btn" data-slot="${idx}">Replace With Selected</button></td>
      </tr>`
    )
    .join("");

  const comms = r.comms || {};
  const chem = r.chemistry || {};
  const warnHtml = (r.roles?.warnings || []).map((w) => `<div class="warn-banner" style="margin-bottom:6px;">${escapeHtml(w)}</div>`).join("");

  const mapsHtml = (r.mapPool || [])
    .map((m) => {
      const pct = Math.min(100, (m.comfort / 10) * 100);
      const diffStr = m.oppComfort !== null ? ` (Opp ${m.oppComfort.toFixed(1)})` : "";
      return `<div class="bar-row">
        <div class="bar-head"><span><strong>${escapeHtml(m.mapName)}</strong> <span class="muted">${m.likes}/5 like</span></span><span class="mono">${m.comfort.toFixed(1)}/10${diffStr}</span></div>
        <div class="bar-track"><div class="bar-fill" style="width:${pct.toFixed(0)}%;"></div></div>
      </div>`;
    })
    .join("");

  $("sandboxBody").innerHTML = `
    <div class="kpi-grid">${kpis
      .map(
        ([l, v, s]) => `<div class="kpi-card"><div class="kpi-label">${escapeHtml(l)}</div><div class="kpi-val" style="font-size:17px;">${escapeHtml(v)}</div><div class="kpi-sub">${escapeHtml(s)}</div></div>`
      )
      .join("")}</div>

    <div class="card">
      <div class="card-header"><h3 class="card-title">Draft Starting Five — ${escapeHtml(r.teamName)}</h3></div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Slot</th><th>Player</th><th>Practical Skill</th><th>Role Profile (IGL/AWP)</th><th>Fluency (&ge;8)</th><th>Salary</th><th>Swap Action</th></tr></thead>
          <tbody>${slotsHtml}</tbody>
        </table>
      </div>
    </div>

    <div class="two-col">
      <div class="card">
        <div class="card-header"><h3 class="card-title">Comms, Chemistry &amp; Role Audit</h3></div>
        ${warnHtml}
        <div class="info-banner" style="margin-bottom:8px;">
          <strong>Shared Languages (&ge;12):</strong> ${escapeHtml((comms.sharedLanguages || []).join(", ") || "None full-5 shared")}<br>
          <strong>Best Common Tongue:</strong> ${escapeHtml(comms.bestLanguage || "-")} (${comms.bestLanguageCoverage || 0}/${(sim.players || []).length} fluent)${(comms.missingFluency || []).length ? `<br><span class="stat-warn">Missing fluency: ${escapeHtml(comms.missingFluency.join(", "))}</span>` : ""}
        </div>
        <div class="subcard">
          <div><strong>Friends in Lineup (${(chem.friends || []).length}):</strong> ${escapeHtml((chem.friends || []).join(" · ") || "None")}</div>
          <div style="margin-top:4px;"><strong>Rivals in Lineup (${(chem.rivals || []).length}):</strong> <span class="${(chem.rivals || []).length ? "stat-bad" : "muted"}">${escapeHtml((chem.rivals || []).join(" · ") || "None")}</span></div>
        </div>
      </div>

      <div class="card">
        <div class="card-header"><h3 class="card-title">Map Pool Comfort Comparison</h3></div>
        ${mapsHtml}
      </div>
    </div>`;

  $("sandboxBody").querySelectorAll(".sb-swap-btn").forEach((btn) => {
    btn.addEventListener("click", () => assignSandboxSlot(Number(btn.dataset.slot)));
  });
}

async function commitSandboxToSave() {
  if (!state.sandboxTeamId || !state.sandboxSlots.length) return;
  if (!window.confirm(`Commit these ${state.sandboxSlots.length} starters to ${state.sandboxResult?.teamName}? Departed starters will be benched/transferred and AI tactics rebuilt.`)) return;
  try {
    const res = await api("/api/studio/sandbox/commit", {
      method: "POST",
      body: JSON.stringify({ teamId: state.sandboxTeamId, playerIds: state.sandboxSlots }),
    });
    state.sandboxResult = res.simulation;
    toast("Sandbox lineup committed & tactics recalculated!", "ok");
    await refreshSaveSummary();
    renderSandboxView();
  } catch (err) {
    toast(err.message, "err");
  }
}

// ---- Growth & Trajectory Lab ----

async function loadGrowthLab() {
  try {
    state.growthData = await api("/api/studio/growth?min_months=2");
    renderGrowthTable();
  } catch (err) {
    toast(`Growth Lab error: ${err.message}`, "err");
  }
}

function renderGrowthTable() {
  const g = state.growthData;
  if (!g || !g.loaded) return;
  const q = ($("growthFilterQ").value || "").trim().toLowerCase();
  const listKey = state.growthMode === "decliners" ? "decliners" : state.growthMode === "wonderkids" ? "wonderkids" : state.growthMode === "ceiling" ? "untappedCeiling" : "risers";
  const rows = (g[listKey] || []).filter((r) => !q || r.name.toLowerCase().includes(q) || r.teamName.toLowerCase().includes(q));

  $("growthTableBody").innerHTML = rows.length
    ? rows
        .map(
          (r) => `<tr class="growth-pick-row" data-pid="${r.playerId}" style="cursor:pointer;">
          <td><strong>${escapeHtml(r.name)}</strong>${r.useStartingPotential ? ` <span class="pill pill-purple">CP ${r.startingPotential}</span>` : ""}</td>
          <td>${r.age}y · ${escapeHtml(r.teamName)}</td>
          <td class="mono muted">${escapeHtml(r.span)}</td>
          <td class="mono">${r.currentAvg.toFixed(2)}</td>
          <td class="mono">${r.potentialAvg.toFixed(2)}</td>
          <td class="mono ${r.overallDelta > 0 ? "stat-good" : r.overallDelta < 0 ? "stat-bad" : ""}">${state.growthMode === "ceiling" ? `+${r.ceilingGap.toFixed(2)} gap` : (r.overallDelta >= 0 ? "+" : "") + r.overallDelta.toFixed(2)}</td>
        </tr>`
        )
        .join("")
    : `<tr><td colspan="6" class="muted">No matching tracked players.</td></tr>`;

  $("growthTableBody").querySelectorAll(".growth-pick-row").forEach((tr) => {
    tr.addEventListener("click", () => openGrowthTrajectory(Number(tr.dataset.pid)));
  });
  if (rows.length && !state.growthSelectedPid) openGrowthTrajectory(rows[0].playerId);
}

async function openGrowthTrajectory(pid) {
  state.growthSelectedPid = pid;
  try {
    const res = await api(`/api/studio/growth/player/${pid}`);
    const pts = res.series || [];
    const labels = pts.map((p) => p.label);
    const chartHtml = renderMultiLineChartSvg(labels, [
      { label: "Overall (16)", color: "#38bdf8", values: pts.map((p) => p.overall) },
      { label: "Mechanics", color: "#22c55e", values: pts.map((p) => p.mechanics) },
      { label: "Weapons", color: "#f59e0b", values: pts.map((p) => p.weapons) },
      { label: "Mental", color: "#a855f7", values: pts.map((p) => p.mental) },
    ]);
    $("growthTrajectoryBox").innerHTML = `
      <div class="card-header">
        <div><strong>${escapeHtml(res.name)}</strong> <span class="muted">(${res.age}y · ${escapeHtml(res.teamName)})</span></div>
        <button class="btn btn-sm btn-cyan" onclick="activateTab('players');openPlayerPro(${res.playerId});">Open in Player Pro</button>
      </div>
      <div class="muted" style="font-size:12px;margin-bottom:8px;">Current Avg: <strong>${res.currentAvg}</strong> · Skill Ceiling Avg: <strong>${res.potentialAvg}</strong> · ${pts.length} monthly snapshots</div>
      ${chartHtml}`;
  } catch (err) {
    toast(err.message, "err");
  }
}

// ---- Weapon Meta Lab ----

async function loadWeaponMeta() {
  try {
    state.weaponsData = await api("/api/studio/weapons");
    renderWeaponsTable();
  } catch (err) {
    toast(`Weapons error: ${err.message}`, "err");
  }
}

function renderWeaponsTable() {
  const wd = state.weaponsData;
  if (!wd || !wd.loaded) return;
  const tf = $("weaponTypeFilter").value;
  const q = ($("weaponSearchQ").value || "").trim().toLowerCase();
  const rows = (wd.weapons || []).filter((w) => (tf === "" || String(w.type) === tf) && (!q || w.name.toLowerCase().includes(q)));

  $("weaponsTableBody").innerHTML = rows
    .map(
      (w) => `<tr class="wep-pick-row" data-wid="${w.id}" style="cursor:pointer;">
        <td><strong>${escapeHtml(w.name)}</strong></td>
        <td><span class="pill pill-blue">${escapeHtml(w.typeLabel)}</span></td>
        <td class="mono">$${w.price.toLocaleString()}</td>
        <td class="mono">${w.damage} <span class="muted">(${w.armoredBodyDmg})</span></td>
        <td class="mono stat-warn">${w.armoredHsDmg}</td>
        <td class="mono">${w.shotsToKillBody}</td>
        <td class="mono">${w.rpm}</td>
        <td class="mono">$${w.killReward}</td>
      </tr>`
    )
    .join("");

  $("weaponsTableBody").querySelectorAll(".wep-pick-row").forEach((tr) => {
    tr.addEventListener("click", () => openWeaponEditor(Number(tr.dataset.wid)));
  });
  if (rows.length && !state.selectedWeaponId) openWeaponEditor(rows[0].id);
}

function openWeaponEditor(wid) {
  state.selectedWeaponId = wid;
  const w = (state.weaponsData?.weapons || []).find((x) => x.id === wid);
  if (!w) return;
  $("weaponEditorBox").innerHTML = `
    <div class="card-header">
      <div><strong>${escapeHtml(w.name)}</strong> <span class="pill pill-blue">${escapeHtml(w.typeLabel)}</span></div>
      <button id="btnSaveSingleWeapon" class="btn btn-sm btn-ok">Save Weapon</button>
    </div>
    <div class="info-banner" style="margin-bottom:10px;">
      Armored Body: <strong>${w.armoredBodyDmg}</strong> (${w.shotsToKillBody} hits to kill) &bull; Armored HS: <strong>${w.armoredHsDmg}</strong> &bull; Fire Rate: <strong>${w.rpm} RPM</strong>
    </div>
    <div class="form-grid">
      <div class="field"><label>Price ($)</label><input id="wePrice" type="number" step="50" value="${w.price}" /></div>
      <div class="field"><label>Base Damage</label><input id="weDamage" type="number" value="${w.damage}" /></div>
      <div class="field"><label>HS Multiplier</label><input id="weHsMult" type="number" step="0.1" value="${w.hsMultiplier}" /></div>
      <div class="field"><label>Armor Multiplier</label><input id="weArmorMult" type="number" step="0.025" value="${w.armorMultiplier}" /></div>
      <div class="field"><label>Shot Interval (sec)</label><input id="weShotInt" type="number" step="0.01" value="${w.shotInterval}" /></div>
      <div class="field"><label>Accuracy</label><input id="weAcc" type="number" step="0.5" value="${w.accuracy}" /></div>
      <div class="field"><label>Recoil / Shot</label><input id="weRecoil" type="number" step="0.05" value="${w.recoilIncreasePerShot}" /></div>
      <div class="field"><label>Ammo</label><input id="weAmmo" type="number" value="${w.ammo}" /></div>
      <div class="field"><label>Kill Reward ($)</label><input id="weKillReward" type="number" step="50" value="${w.killReward}" /></div>
      <div class="field"><label>Reload Time</label><input id="weReload" type="number" value="${w.reloadTime}" /></div>
    </div>`;

  $("btnSaveSingleWeapon").addEventListener("click", async () => {
    try {
      const res = await api(`/api/studio/weapon/${wid}`, {
        method: "POST",
        body: JSON.stringify({
          price: Number($("wePrice").value),
          damage: Number($("weDamage").value),
          hsMultiplier: Number($("weHsMult").value),
          armorMultiplier: Number($("weArmorMult").value),
          shotInterval: Number($("weShotInt").value),
          accuracy: Number($("weAcc").value),
          recoilIncreasePerShot: Number($("weRecoil").value),
          ammo: Number($("weAmmo").value),
          killReward: Number($("weKillReward").value),
          reloadTime: Number($("weReload").value),
        }),
      });
      state.weaponsData.weapons = res.weapons;
      toast(`Saved ${w.name}`, "ok");
      await refreshSaveSummary();
      renderWeaponsTable();
      openWeaponEditor(wid);
    } catch (err) {
      toast(err.message, "err");
    }
  });
}

async function applyWeaponPreset(preset) {
  try {
    const res = await api("/api/studio/weapons/preset", { method: "POST", body: JSON.stringify({ preset }) });
    state.weaponsData = { loaded: true, weapons: res.weapons };
    toast(`Applied "${preset}" preset (${res.updatedCount} weapons tuned)`, "ok");
    await refreshSaveSummary();
    renderWeaponsTable();
    if (state.selectedWeaponId) openWeaponEditor(state.selectedWeaponId);
  } catch (err) {
    toast(err.message, "err");
  }
}
