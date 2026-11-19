/* Save Studio - Players Pro, Staff, Orgs/Sponsors & Transfers/Relations */

let _plSearchT = null;
let _stSearchT = null;
let _tmSearchT = null;

function bindEditorEvents() {
  $("plFilterQ").addEventListener("input", () => { clearTimeout(_plSearchT); _plSearchT = setTimeout(() => { state.plOffset = 0; loadPlayersList(); }, 150); });
  $("plFilterTeam").addEventListener("change", () => { state.plOffset = 0; loadPlayersList(); });
  $("plFreeOnly").addEventListener("change", () => { state.plOffset = 0; loadPlayersList(); });
  $("btnPlPrev").addEventListener("click", () => { state.plOffset = Math.max(0, state.plOffset - state.plLimit); loadPlayersList(); });
  $("btnPlNext").addEventListener("click", () => { if (state.plOffset + state.plLimit < state.plTotal) { state.plOffset += state.plLimit; loadPlayersList(); } });
  $("btnNewPlayerOpen").addEventListener("click", openNewPlayerPrompt);

  $("stFilterQ").addEventListener("input", () => { clearTimeout(_stSearchT); _stSearchT = setTimeout(() => { state.stOffset = 0; loadStaffList(); }, 150); });
  $("stFilterTeam").addEventListener("change", () => { state.stOffset = 0; loadStaffList(); });
  $("stFilterRole").addEventListener("change", () => { state.stOffset = 0; loadStaffList(); });
  $("btnStPrev").addEventListener("click", () => { state.stOffset = Math.max(0, state.stOffset - state.stLimit); loadStaffList(); });
  $("btnStNext").addEventListener("click", () => { if (state.stOffset + state.stLimit < state.stTotal) { state.stOffset += state.stLimit; loadStaffList(); } });
  $("btnNewStaffOpen").addEventListener("click", openNewStaffPrompt);

  $("tmFilterQ").addEventListener("input", () => { clearTimeout(_tmSearchT); _tmSearchT = setTimeout(loadTeamsPickList, 120); });

  $("txPlayerSearch").addEventListener("input", renderTransferDeskPlayerOptions);
  $("btnTxExecute").addEventListener("click", executePlayerTransfer);
  $("relNewP1Q").addEventListener("input", renderRelPlayerDropdowns);
  $("relNewP2Q").addEventListener("input", renderRelPlayerDropdowns);
  $("relFilterQ").addEventListener("input", loadRelationsManager);
  $("btnRelSaveNew").addEventListener("click", saveNewRelationship);
}

// ---- Players Pro Editor ----

async function loadPlayersList() {
  try {
    const params = new URLSearchParams({
      q: $("plFilterQ").value.trim(),
      team_id: $("plFilterTeam").value || "",
      free_only: $("plFreeOnly").checked ? "true" : "false",
      offset: String(state.plOffset),
      limit: String(state.plLimit),
    });
    const res = await api(`/api/players?${params.toString()}`);
    state.plTotal = res.total || 0;
    const end = Math.min(state.plOffset + (res.items || []).length, state.plTotal);
    $("plPageInfo").textContent = `${state.plTotal ? state.plOffset + 1 : 0}-${end} of ${state.plTotal}`;
    const curId = state.selectedPlayer?.player?.id || 0;
    $("plPickList").innerHTML = (res.items || [])
      .map(
        (p) => `<div class="pick-item ${p.id === curId ? "active" : ""}" data-pid="${p.id}">
        <div><div><strong>${escapeHtml(p.name)}</strong>${p.benched ? ' <span class="pill pill-warn">Bench</span>' : ""}</div><div class="muted" style="font-size:11.5px;">${escapeHtml(p.teamName)} · ${p.age}y</div></div>
        <span class="mono">${p.avgSkill.toFixed(2)}</span>
      </div>`
      )
      .join("");
    $("plPickList").querySelectorAll(".pick-item").forEach((el) => {
      el.addEventListener("click", () => openPlayerPro(Number(el.dataset.pid)));
    });
    if ((res.items || []).length && !curId) openPlayerPro(res.items[0].id);
  } catch (err) {
    toast(err.message, "err");
  }
}

async function openNewPlayerPrompt() {
  const name = window.prompt("New player alias:", "");
  if (!name || !name.trim()) return;
  try {
    const res = await api("/api/players", { method: "POST", body: JSON.stringify({ name: name.trim(), age: 18 }) });
    toast(`Created player ${name}`, "ok");
    await refreshSaveSummary();
    await loadPlayersList();
    openPlayerPro(res.player.id);
  } catch (err) {
    toast(err.message, "err");
  }
}

async function openPlayerPro(pid) {
  try {
    state.selectedPlayer = await api(`/api/studio/player/${pid}`);
    renderPlayerPro();
  } catch (err) {
    toast(err.message, "err");
  }
}

function renderPlayerPro() {
  const d = state.selectedPlayer;
  if (!d || !d.player) return;
  const p = d.player;
  const c = d.contract;
  const pro = d.pro || {};
  const nationOpts = Object.entries(state.meta?.nations || {})
    .sort((a, b) => String(a[1]).localeCompare(String(b[1])))
    .map(([id, n]) => `<option value="${id}" ${Number(id) === Number(p.nation) ? "selected" : ""}>${escapeHtml(n)}</option>`)
    .join("");
  const teamOpts = [`<option value="0">Free Agent</option>`]
    .concat(state.teams.map((t) => `<option value="${t.id}" ${c && t.id === c.teamId ? "selected" : ""}>${escapeHtml(t.name)}</option>`))
    .join("");

  const sk = p.skills || {};
  const potMap = {};
  (p.potential?.m_Keys || []).forEach((k, i) => { potMap[k] = p.potential.m_Values[i]; });

  const skillRows = (state.meta?.playerSkills || [])
    .map(
      (s) => `<div class="subcard" style="padding:8px;">
        <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:4px;"><strong>${escapeHtml(s.label)}</strong><span class="muted">${escapeHtml(s.group)}</span></div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;">
          <input class="pl-skill-in" data-key="${s.key}" type="number" step="0.1" min="1" max="20" value="${Number(sk[s.key] ?? 10).toFixed(2)}" title="Current skill" />
          <input class="pl-pot-in" data-id="${s.id}" type="number" min="1" max="20" value="${potMap[s.id] ?? 15}" title="Skill cap" />
        </div>
      </div>`
    )
    .join("");

  const histPts = pro.skillHistory || [];
  const histChart = renderMultiLineChartSvg(
    histPts.map((x) => x.label),
    [
      { label: "Overall", color: "#38bdf8", values: histPts.map((x) => x.overall) },
      { label: "Mechanics", color: "#22c55e", values: histPts.map((x) => x.mechanics) },
      { label: "Weapons", color: "#f59e0b", values: histPts.map((x) => x.weapons) },
    ]
  );

  const tplOpts = (pro.tournamentTemplates || []).map((t) => `<option value="${t.id}">${escapeHtml(t.name)}</option>`).join("");
  const sub = state.plSubTab || "basics";

  $("plEditorBody").innerHTML = `
    <div class="card-header">
      <div>
        <h3 class="card-title">${escapeHtml(p.name)} <span class="muted">(#${p.id} · ${escapeHtml(d.teamName)})</span></h3>
        <div class="muted" style="font-size:12px;">Practical Avg: <strong>${pro.practicalAvg}</strong> · Potential Avg: <strong>${pro.potentialAvg}</strong> · Burnout: <strong>${((pro.totalBurnout || 0) * 100).toFixed(1)}%</strong> · Mood: <strong>${pro.moodScore}</strong></div>
      </div>
      <div class="inline-actions">
        <button id="btnPlHealNow" class="btn btn-sm btn-ok">Zero Burnout &amp; Max Mood</button>
        <button id="btnPlSaveAll" class="btn btn-sm btn-cyan">Save Player</button>
      </div>
    </div>

    <div class="subtabs">
      <button class="subtab-btn ${sub === "basics" ? "active" : ""}" data-pltab="basics">Basics &amp; Contract</button>
      <button class="subtab-btn ${sub === "skills" ? "active" : ""}" data-pltab="skills">Skills &amp; Caps</button>
      <button class="subtab-btn ${sub === "personality" ? "active" : ""}" data-pltab="personality">Personality &amp; Awards</button>
      <button class="subtab-btn ${sub === "history" ? "active" : ""}" data-pltab="history">Skill Trajectory</button>
    </div>

    <div id="plsub-basics" class="subtab-panel ${sub === "basics" ? "active" : ""}">
      <div class="form-grid">
        <div class="field"><label>Name</label><input id="peName" type="text" value="${escapeHtml(p.name)}" /></div>
        <div class="field"><label>Age</label><input id="peAge" type="number" min="15" max="55" value="${p.age}" /></div>
        <div class="field"><label>Nation</label><select id="peNation">${nationOpts}</select></div>
        <div class="field"><label>Reputation (1-20)</label><input id="peRep" type="number" min="1" max="20" value="${p.reputation}" /></div>
        <div class="field"><label>Longevity</label><input id="peLongevity" type="number" min="1" max="20" value="${p.longevity ?? 10}" /></div>
        <div class="field"><label>Starting Potential (50-275)</label><input id="peStartPot" type="number" min="50" max="275" value="${pro.startingPotential || 150}" /></div>
        <div class="field"><label>Practice Burnout (0-1)</label><input id="peBurnPrac" type="number" step="0.01" min="0" max="1" value="${Number(pro.burnout?.burnoutFromPractice || 0).toFixed(3)}" /></div>
        <div class="field"><label>Match Burnout (0-1)</label><input id="peBurnMatch" type="number" step="0.01" min="0" max="1" value="${Number(pro.burnout?.burnoutFromMatches || 0).toFixed(3)}" /></div>
      </div>
      <div class="inline-actions" style="margin-top:10px;">
        <label class="checkbox-row"><input id="peUseStartPot" type="checkbox" ${pro.useStartingPotential ? "checked" : ""} /><span>Use Custom Starting Potential</span></label>
        <label class="checkbox-row"><input id="peRetire" type="checkbox" ${p.setForRetirement ? "checked" : ""} /><span>Set For Retirement</span></label>
      </div>
      <div class="subcard" style="margin-top:12px;">
        <div style="font-weight:600;margin-bottom:8px;">Contract Details</div>
        <div class="form-grid">
          <div class="field"><label>Team</label><select id="peTeam">${teamOpts}</select></div>
          <div class="field"><label>Salary ($/yr)</label><input id="peSalary" type="number" step="5000" value="${c ? c.salaryYear : 250000}" /></div>
          <div class="field"><label>Role Status</label><select id="peStatus">${Object.entries(state.meta?.playerStatus || {}).map(([k, v]) => `<option value="${k}" ${c && Number(k) === Number(c.status) ? "selected" : ""}>${escapeHtml(v)}</option>`).join("")}</select></div>
          <div class="field"><label>Benched</label><select id="peBenched"><option value="false" ${!c?.benched ? "selected" : ""}>Starter</option><option value="true" ${c?.benched ? "selected" : ""}>Benched</option></select></div>
        </div>
      </div>
    </div>

    <div id="plsub-skills" class="subtab-panel ${sub === "skills" ? "active" : ""}">
      <div class="muted" style="font-size:12px;margin-bottom:8px;">Left box = current skill (1.0–20.0) &bull; Right box = hidden ceiling potential (1–20)</div>
      <div class="form-grid">${skillRows}</div>
    </div>

    <div id="plsub-personality" class="subtab-panel ${sub === "personality" ? "active" : ""}">
      <div class="form-grid" style="margin-bottom:12px;">
        ${(state.meta?.personalityAxes || [])
          .map(
            (ax) => `<div class="field"><label>${escapeHtml(ax.label)} (${ax.low}-${ax.high})</label><input class="pe-pers-in" data-key="${ax.key}" type="number" min="1" max="20" value="${p.personality?.[ax.key] ?? 10}" /></div>`
          )
          .join("")}
      </div>
      <div class="subcard">
        <div style="font-weight:600;margin-bottom:8px;">Player Trophy &amp; Medal Cabinet (${(pro.awards || []).length})</div>
        <div class="form-grid" style="margin-bottom:8px;">
          <div class="field"><label>Award Type</label><select id="peNewAwType"><option value="0">MVP</option><option value="2">EVP</option><option value="1">Event Win</option><option value="3">Top 20</option></select></div>
          <div class="field"><label>Tournament Template</label><select id="peNewAwTpl">${tplOpts}</select></div>
          <div class="field"><label>Year</label><input id="peNewAwYear" type="number" value="${state.summary?.datetime?.year || 2026}" /></div>
          <div class="field"><label>Month</label><input id="peNewAwMonth" type="number" min="1" max="12" value="${state.summary?.datetime?.month || 1}" /></div>
          <div class="field"><label>Top20 Rank (if Top20)</label><input id="peNewAwT20" type="number" min="0" max="20" value="0" /></div>
        </div>
        <button id="btnPeAddAward" class="btn btn-sm btn-ok" style="margin-bottom:10px;">+ Grant Award</button>
        <div class="table-wrap" style="max-height:240px;"><table>
          <thead><tr><th>Date</th><th>Type</th><th>Tournament</th><th>Team</th><th>Action</th></tr></thead>
          <tbody>${(pro.awards || [])
            .map(
              (a) => `<tr><td class="mono">${a.year}-${String(a.month).padStart(2, "0")}</td><td><span class="pill pill-blue">${escapeHtml(a.typeLabel)}${a.top20Placement ? ` #${a.top20Placement}` : ""}</span></td><td>${escapeHtml(a.tournamentName)}</td><td>${escapeHtml(a.teamName)}</td><td><button class="btn btn-sm btn-bad pe-del-aw" data-idx="${a.index}">Del</button></td></tr>`
            )
            .join("") || `<tr><td colspan="5" class="muted">No awards recorded.</td></tr>`}</tbody>
        </table></div>
      </div>
    </div>

    <div id="plsub-history" class="subtab-panel ${sub === "history" ? "active" : ""}">
      ${histChart}
    </div>`;

  $("plEditorBody").querySelectorAll("[data-pltab]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.plSubTab = btn.dataset.pltab;
      $("plEditorBody").querySelectorAll("[data-pltab]").forEach((b) => b.classList.remove("active"));
      $("plEditorBody").querySelectorAll("[id^='plsub-']").forEach((x) => x.classList.remove("active"));
      btn.classList.add("active");
      $(`plsub-${state.plSubTab}`).classList.add("active");
    });
  });

  $("btnPlHealNow").addEventListener("click", () => healPlayerPro(p.id));
  $("btnPlSaveAll").addEventListener("click", () => savePlayerPro(p.id));
  $("btnPeAddAward").addEventListener("click", () => addPlayerAwardForm(p.id));
  $("plEditorBody").querySelectorAll(".pe-del-aw").forEach((btn) => {
    btn.addEventListener("click", () => removePlayerAward(p.id, Number(btn.dataset.idx)));
  });
}

async function savePlayerPro(pid) {
  const skills = {};
  $("plEditorBody").querySelectorAll(".pl-skill-in").forEach((el) => { skills[el.dataset.key] = Number(el.value); });
  const mKeys = [];
  const mVals = [];
  $("plEditorBody").querySelectorAll(".pl-pot-in").forEach((el) => { mKeys.push(Number(el.dataset.id)); mVals.push(Number(el.value)); });
  const personality = {};
  $("plEditorBody").querySelectorAll(".pe-pers-in").forEach((el) => { personality[el.dataset.key] = Number(el.value); });

  const teamVal = Number($("peTeam").value || 0);
  try {
    state.selectedPlayer = await api(`/api/studio/player/${pid}`, {
      method: "POST",
      body: JSON.stringify({
        player: {
          name: $("peName").value.trim(),
          age: Number($("peAge").value),
          nation: Number($("peNation").value),
          reputation: Number($("peRep").value),
          longevity: Number($("peLongevity").value),
          useStartingPotential: $("peUseStartPot").checked,
          startingPotential: Number($("peStartPot").value),
          setForRetirement: $("peRetire").checked,
          burnout: {
            burnoutFromPractice: Number($("peBurnPrac").value),
            burnoutFromMatches: Number($("peBurnMatch").value),
          },
          skills,
          potential: { m_Keys: mKeys, m_Values: mVals },
          personality,
        },
        contract: teamVal > 0 || state.selectedPlayer.contract
          ? {
              teamId: teamVal,
              salaryYear: Number($("peSalary").value),
              status: Number($("peStatus").value),
              benched: $("peBenched").value === "true",
            }
          : null,
      }),
    });
    toast(`Saved player ${$("peName").value}`, "ok");
    await refreshSaveSummary();
    loadPlayersList();
    renderPlayerPro();
  } catch (err) {
    toast(err.message, "err");
  }
}

async function healPlayerPro(pid) {
  try {
    state.selectedPlayer = await api(`/api/studio/player/${pid}/heal`, { method: "POST", body: JSON.stringify({ resetBurnout: true, maxMood: true }) });
    toast("Zeroed burnout & maximized player mood!", "ok");
    await refreshSaveSummary();
    renderPlayerPro();
  } catch (err) {
    toast(err.message, "err");
  }
}

async function addPlayerAwardForm(pid) {
  try {
    state.selectedPlayer = await api(`/api/studio/player/${pid}/award/add`, {
      method: "POST",
      body: JSON.stringify({
        type: Number($("peNewAwType").value),
        tournamentTemplate: Number($("peNewAwTpl").value),
        year: Number($("peNewAwYear").value),
        month: Number($("peNewAwMonth").value),
        top20Placement: Number($("peNewAwT20").value),
      }),
    });
    toast("Award added to player cabinet", "ok");
    await refreshSaveSummary();
    renderPlayerPro();
  } catch (err) {
    toast(err.message, "err");
  }
}

async function removePlayerAward(pid, idx) {
  try {
    state.selectedPlayer = await api(`/api/studio/player/${pid}/award/delete`, { method: "POST", body: JSON.stringify({ index: idx }) });
    toast("Award removed", "ok");
    await refreshSaveSummary();
    renderPlayerPro();
  } catch (err) {
    toast(err.message, "err");
  }
}

// ---- Staff Editor ----

async function loadStaffList() {
  try {
    const params = new URLSearchParams({
      q: $("stFilterQ").value.trim(),
      team_id: $("stFilterTeam").value || "",
      role: $("stFilterRole").value || "",
      offset: String(state.stOffset),
      limit: String(state.stLimit),
    });
    const res = await api(`/api/staff?${params.toString()}`);
    state.stTotal = res.total || 0;
    const end = Math.min(state.stOffset + (res.items || []).length, state.stTotal);
    $("stPageInfo").textContent = `${state.stTotal ? state.stOffset + 1 : 0}-${end} of ${state.stTotal}`;
    const curId = state.selectedStaff?.staff?.id || 0;
    $("stPickList").innerHTML = (res.items || [])
      .map(
        (s) => `<div class="pick-item ${s.id === curId ? "active" : ""}" data-sid="${s.id}">
        <div><div><strong>${escapeHtml(s.name)}</strong></div><div class="muted" style="font-size:11.5px;">${escapeHtml(s.roleName)} · ${escapeHtml(s.teamName)}</div></div>
        <span class="mono">${s.avgSkill.toFixed(2)}</span>
      </div>`
      )
      .join("");
    $("stPickList").querySelectorAll(".pick-item").forEach((el) => {
      el.addEventListener("click", () => openStaffEditor(Number(el.dataset.sid)));
    });
    if ((res.items || []).length && !curId) openStaffEditor(res.items[0].id);
  } catch (err) {
    toast(err.message, "err");
  }
}

async function openNewStaffPrompt() {
  const name = window.prompt("New staffer name:", "");
  if (!name || !name.trim()) return;
  try {
    const res = await api("/api/staff", { method: "POST", body: JSON.stringify({ name: name.trim(), age: 30, role: 0 }) });
    toast(`Created staffer ${name}`, "ok");
    await refreshSaveSummary();
    await loadStaffList();
    openStaffEditor(res.staff.id);
  } catch (err) {
    toast(err.message, "err");
  }
}

async function openStaffEditor(sid) {
  try {
    state.selectedStaff = await api(`/api/staff/${sid}`);
    renderStaffEditor();
  } catch (err) {
    toast(err.message, "err");
  }
}

function renderStaffEditor() {
  const d = state.selectedStaff;
  if (!d || !d.staff) return;
  const s = d.staff;
  const c = d.contract;
  const sk = s.skills || {};
  $("stEditorBody").innerHTML = `
    <div class="card-header">
      <h3 class="card-title">${escapeHtml(s.name)} <span class="muted">(#${s.id} · ${escapeHtml(d.teamName)})</span></h3>
      <button id="btnSaveStaffOne" class="btn btn-sm btn-cyan">Save Staff</button>
    </div>
    <div class="form-grid" style="margin-bottom:12px;">
      <div class="field"><label>Name</label><input id="seName" type="text" value="${escapeHtml(s.name)}" /></div>
      <div class="field"><label>Age</label><input id="seAge" type="number" value="${s.age}" /></div>
      <div class="field"><label>Reputation (1-20)</label><input id="seRep" type="number" min="1" max="20" value="${s.reputation}" /></div>
      <div class="field"><label>Role</label><select id="seRole">${Object.entries(state.meta?.staffRoles || {}).map(([k, v]) => `<option value="${k}" ${c && Number(k) === Number(c.role) ? "selected" : ""}>${escapeHtml(v)}</option>`).join("")}</select></div>
      <div class="field"><label>Team</label><select id="seTeam"><option value="0">Free Agent</option>${state.teams.map((t) => `<option value="${t.id}" ${c && t.id === c.teamId ? "selected" : ""}>${escapeHtml(t.name)}</option>`).join("")}</select></div>
      <div class="field"><label>Salary ($/yr)</label><input id="seSalary" type="number" step="5000" value="${c ? c.salaryYear : 120000}" /></div>
    </div>
    <div class="form-grid">${(state.meta?.staffSkills || [])
      .map(
        (ss) => `<div class="field"><label>${escapeHtml(ss.label)}</label><input class="se-sk-in" data-key="${ss.key}" type="number" step="0.5" min="1" max="20" value="${Number(sk[ss.key] ?? 10).toFixed(1)}" /></div>`
      )
      .join("")}</div>`;

  $("btnSaveStaffOne").addEventListener("click", async () => {
    const skills = {};
    $("stEditorBody").querySelectorAll(".se-sk-in").forEach((el) => { skills[el.dataset.key] = Number(el.value); });
    const tid = Number($("seTeam").value || 0);
    try {
      state.selectedStaff = await api(`/api/staff/${s.id}`, {
        method: "PUT",
        body: JSON.stringify({
          staff: { name: $("seName").value.trim(), age: Number($("seAge").value), reputation: Number($("seRep").value), skills },
          contract: tid > 0 || state.selectedStaff.contract ? { teamId: tid, role: Number($("seRole").value), salaryYear: Number($("seSalary").value) } : null,
        }),
      });
      toast("Staffer saved", "ok");
      await refreshSaveSummary();
      loadStaffList();
      renderStaffEditor();
    } catch (err) {
      toast(err.message, "err");
    }
  });
}

// ---- Organizations & Sponsors Editor ----

async function loadTeamsPickList() {
  try {
    const q = ($("tmFilterQ").value || "").trim().toLowerCase();
    const list = state.teams.filter((t) => !q || t.name.toLowerCase().includes(q));
    const curId = state.selectedTeam?.team?.id || 0;
    $("tmPickList").innerHTML = list
      .map(
        (t) => `<div class="pick-item ${t.id === curId ? "active" : ""}" data-tid="${t.id}">
        <div><div><strong>${escapeHtml(t.name)}</strong></div><div class="muted" style="font-size:11.5px;">Rank #${t.worldRank || "-"} · ${formatMoney(t.balance)}</div></div>
        <span class="mono">${t.avgSkill}</span>
      </div>`
      )
      .join("");
    $("tmPickList").querySelectorAll(".pick-item").forEach((el) => {
      el.addEventListener("click", () => openTeamPro(Number(el.dataset.tid)));
    });
    if (list.length && !curId) openTeamPro(state.summary?.userTeamId || list[0].id);
  } catch (err) {
    toast(err.message, "err");
  }
}

async function openTeamPro(tid) {
  try {
    state.selectedTeam = await api(`/api/studio/team/${tid}`);
    renderTeamPro();
  } catch (err) {
    toast(err.message, "err");
  }
}

function renderTeamPro() {
  const d = state.selectedTeam;
  if (!d || !d.team) return;
  const t = d.team;
  const pro = d.pro || {};
  const catOpts = (pro.sponsorCatalog || []).map((s) => `<option value="${s.id}">${escapeHtml(s.name)} (Rep ${s.reputation} · ${formatMoney(s.fixedMonthlyContribution)}/mo)</option>`).join("");

  $("tmEditorBody").innerHTML = `
    <div class="card-header">
      <div>
        <h3 class="card-title">${escapeHtml(t.name)} <span class="muted">(#${t.id} · Avg Burnout ${((pro.squadHealth?.avgBurnout || 0) * 100).toFixed(1)}% · Mood ${pro.squadHealth?.avgMood || 0})</span></h3>
      </div>
      <div class="inline-actions">
        <button id="btnTmHealSquad" class="btn btn-sm btn-ok">Heal Squad + Clear Cooldowns</button>
        <button id="btnTmSaveOrg" class="btn btn-sm btn-cyan">Save Organization</button>
      </div>
    </div>

    <div class="form-grid" style="margin-bottom:12px;">
      <div class="field"><label>Balance ($)</label><input id="teBalance" type="number" step="50000" value="${t.teamFinances?.currentBalance || 0}" /></div>
      <div class="field"><label>Reputation (1-20)</label><input id="teRep" type="number" min="1" max="20" value="${t.reputation || 1}" /></div>
      <div class="field"><label>Hiring Bias</label><select id="teHiringBias">${Object.entries(state.meta?.hiringBias || {}).map(([k, v]) => `<option value="${k}" ${Number(k) === Number(t.owner?.hiringBias) ? "selected" : ""}>${escapeHtml(v)}</option>`).join("")}</select></div>
      <div class="field"><label>Branding (1-10)</label><input id="teBranding" type="number" min="0" max="20" value="${t.branding || 0}" /></div>
      <div class="field"><label>Academy (1-10)</label><input id="teAcademy" type="number" min="0" max="20" value="${t.academy || 0}" /></div>
      <div class="field"><label>Cohesion (0-1)</label><input id="teCohesion" type="number" step="0.05" min="0" max="1" value="${Number(t.teamCohesion?.cohesionFromTraining || 0).toFixed(2)}" /></div>
    </div>

    <div class="chart-box" style="margin-bottom:12px;">
      <div class="muted" style="font-size:11.5px;margin-bottom:4px;">World Ranking History</div>
      ${renderSparklineSvg(pro.rankingHistory || [], { invert: true, minVal: 1, height: 74 })}
    </div>

    <div class="subcard">
      <div class="card-header"><h4 style="margin:0;">Active Sponsors (${(pro.sponsors || []).length})</h4></div>
      <div class="inline-actions" style="margin-bottom:10px;">
        <select id="teAddSponsorCat" style="max-width:300px;">${catOpts}</select>
        <input id="teAddSponsorMonthly" type="number" step="5000" value="100000" style="width:130px;" title="Monthly $" />
        <button id="btnTeAddSponsor" class="btn btn-sm btn-ok">+ Add Sponsor</button>
      </div>
      <div class="table-wrap" style="max-height:220px;"><table>
        <thead><tr><th>Sponsor</th><th>Monthly</th><th>Bonus</th><th>Req Pos</th><th>Ends</th><th>Action</th></tr></thead>
        <tbody>${(pro.sponsors || [])
          .map(
            (sp, idx) => `<tr>
            <td><strong>${escapeHtml(sp.name)}</strong> <span class="muted">(Rep ${sp.reputation})</span></td>
            <td class="mono">${formatMoney(sp.fixedMonthlyContribution)}/mo</td>
            <td class="mono">${formatMoney(sp.bonusPayout)}</td>
            <td class="mono">Top ${sp.bonusPositionRequirement}</td>
            <td class="mono muted">${formatDateObj(sp.dealLength)}</td>
            <td><button class="btn btn-sm btn-bad te-del-sp" data-idx="${idx}">Remove</button></td>
          </tr>`
          )
          .join("") || `<tr><td colspan="6" class="muted">No active sponsors.</td></tr>`}</tbody>
      </table></div>
    </div>`;

  $("btnTmHealSquad").addEventListener("click", async () => {
    try {
      const r = await api(`/api/studio/team/${t.id}/heal`, { method: "POST", body: JSON.stringify({ resetBurnout: true, maxMood: true, clearCooldowns: true }) });
      state.selectedTeam = r.team;
      toast(`Healed ${r.healedPlayers} players & cleared ${r.cooldownsCleared} cooldowns`, "ok");
      await refreshSaveSummary();
      renderTeamPro();
    } catch (err) {
      toast(err.message, "err");
    }
  });

  $("btnTmSaveOrg").addEventListener("click", async () => {
    try {
      await api(`/api/team/${t.id}`, {
        method: "PUT",
        body: JSON.stringify({
          team: {
            reputation: Number($("teRep").value),
            branding: Number($("teBranding").value),
            academy: Number($("teAcademy").value),
            owner: { hiringBias: Number($("teHiringBias").value) },
            teamFinances: { currentBalance: Number($("teBalance").value) },
            teamCohesion: { cohesionFromTraining: Number($("teCohesion").value) },
          },
        }),
      });
      state.selectedTeam = await api(`/api/studio/team/${t.id}`);
      toast(`Saved ${t.name}`, "ok");
      await refreshSaveSummary();
      loadTeamsPickList();
      renderTeamPro();
    } catch (err) {
      toast(err.message, "err");
    }
  });

  $("btnTeAddSponsor").addEventListener("click", async () => {
    try {
      state.selectedTeam = await api(`/api/studio/team/${t.id}/sponsor`, {
        method: "POST",
        body: JSON.stringify({
          mode: "add",
          sponsorId: Number($("teAddSponsorCat").value),
          fixedMonthlyContribution: Number($("teAddSponsorMonthly").value),
        }),
      });
      toast("Sponsor added to club", "ok");
      await refreshSaveSummary();
      renderTeamPro();
    } catch (err) {
      toast(err.message, "err");
    }
  });

  $("tmEditorBody").querySelectorAll(".te-del-sp").forEach((btn) => {
    btn.addEventListener("click", async () => {
      try {
        state.selectedTeam = await api(`/api/studio/team/${t.id}/sponsor`, {
          method: "POST",
          body: JSON.stringify({ mode: "delete", index: Number(btn.dataset.idx) }),
        });
        toast("Sponsor removed", "ok");
        await refreshSaveSummary();
        renderTeamPro();
      } catch (err) {
        toast(err.message, "err");
      }
    });
  });
}

// ---- Transfers & Relations Desk ----

async function initTransfersDesk() {
  try {
    const [pRes, txRes] = await Promise.all([api("/api/players?limit=400"), api("/api/transfers?limit=100")]);
    state.txPlayers = pRes.items || [];
    $("txTargetTeamSelect").innerHTML = [`<option value="0">Free Agency (Release)</option>`]
      .concat(state.teams.map((t) => `<option value="${t.id}">${escapeHtml(t.name)}</option>`))
      .join("");
    $("relNewType").innerHTML = Object.entries(state.meta?.relationshipTypes || {})
      .map(([id, n]) => `<option value="${id}">${escapeHtml(n)}</option>`)
      .join("");
    renderTransferDeskPlayerOptions();
    renderRelPlayerDropdowns();
    loadRelationsManager();
    $("txLogBody").innerHTML = (txRes.transfers || [])
      .map(
        (x) => `<tr><td class="mono muted">${formatDateObj(x.datetime)}</td><td>${escapeHtml(x.personType)}</td><td><strong>${escapeHtml(x.personName)}</strong></td><td>${escapeHtml(x.fromTeamName)} &rarr; <strong>${escapeHtml(x.toTeamName)}</strong></td><td class="mono">${x.purchasePrice ? formatMoney(x.purchasePrice) : "Free"}</td></tr>`
      )
      .join("");
  } catch (err) {
    toast(err.message, "err");
  }
}

function renderTransferDeskPlayerOptions() {
  const q = ($("txPlayerSearch").value || "").trim().toLowerCase();
  const list = state.txPlayers.filter((p) => !q || p.name.toLowerCase().includes(q) || p.teamName.toLowerCase().includes(q));
  $("txPlayerSelect").innerHTML = list.slice(0, 120).map((p) => `<option value="${p.id}">${escapeHtml(p.name)} (${escapeHtml(p.teamName)} · ${p.avgSkill.toFixed(2)})</option>`).join("");
}

function renderRelPlayerDropdowns() {
  const fill = (qId, selId) => {
    const q = ($(qId).value || "").trim().toLowerCase();
    const list = state.txPlayers.filter((p) => !q || p.name.toLowerCase().includes(q) || p.teamName.toLowerCase().includes(q));
    $(selId).innerHTML = list.slice(0, 100).map((p) => `<option value="${p.id}">${escapeHtml(p.name)} (${escapeHtml(p.teamName)})</option>`).join("");
  };
  fill("relNewP1Q", "relNewP1");
  fill("relNewP2Q", "relNewP2");
}

async function executePlayerTransfer() {
  const pid = Number($("txPlayerSelect").value || 0);
  const tid = Number($("txTargetTeamSelect").value || 0);
  if (!pid) return;
  try {
    await api("/api/transfer/player", {
      method: "POST",
      body: JSON.stringify({
        playerId: pid,
        targetTeamId: tid,
        buyoutPrice: Number($("txBuyoutFee").value || 0),
        salaryYear: Number($("txSalaryYear").value || 250000),
        joinBenched: $("txJoinBenched").checked,
        applyFinances: $("txApplyFinances").checked,
      }),
    });
    toast("Transfer executed & AI tactics rebuilt", "ok");
    await refreshSaveSummary();
    initTransfersDesk();
  } catch (err) {
    toast(err.message, "err");
  }
}

async function loadRelationsManager() {
  try {
    const q = $("relFilterQ").value.trim();
    const res = await api(`/api/player-relationships?q=${encodeURIComponent(q)}`);
    state.allRelations = res.items || [];
    $("relCountInfo").textContent = `${state.allRelations.length} relations`;
    $("relTableBody").innerHTML = state.allRelations
      .slice(0, 200)
      .map(
        (r) => `<tr>
        <td><strong>${escapeHtml(r.player1Name)}</strong> <span class="muted">(${escapeHtml(r.player1TeamName)})</span></td>
        <td><strong>${escapeHtml(r.player2Name)}</strong> <span class="muted">(${escapeHtml(r.player2TeamName)})</span></td>
        <td><span class="pill ${r.type === 0 ? "pill-bad" : "pill-ok"}">${escapeHtml(r.typeLabel)}</span></td>
        <td class="mono">${r.duration || "Perm"}</td>
        <td class="mono">${r.player1Resolved ? "Yes" : "No"} / ${r.player2Resolved ? "Yes" : "No"}</td>
        <td><button class="btn btn-sm btn-bad rel-del-btn" data-p1="${r.player1Id}" data-p2="${r.player2Id}">Delete</button></td>
      </tr>`
      )
      .join("");
    $("relTableBody").querySelectorAll(".rel-del-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        try {
          await api("/api/player/relationship/delete", { method: "POST", body: JSON.stringify({ player1Id: Number(btn.dataset.p1), player2Id: Number(btn.dataset.p2) }) });
          toast("Deleted relationship", "ok");
          loadRelationsManager();
        } catch (err) {
          toast(err.message, "err");
        }
      });
    });
  } catch (err) {
    toast(err.message, "err");
  }
}

async function saveNewRelationship() {
  const p1 = Number($("relNewP1").value || 0);
  const p2 = Number($("relNewP2").value || 0);
  if (!p1 || !p2 || p1 === p2) return toast("Select two different players.", "err");
  try {
    await api("/api/player/relationship/save", {
      method: "POST",
      body: JSON.stringify({ player1Id: p1, player2Id: p2, type: Number($("relNewType").value || 1), duration: Number($("relNewDur").value || 0) }),
    });
    toast("Saved relationship", "ok");
    await refreshSaveSummary();
    loadRelationsManager();
  } catch (err) {
    toast(err.message, "err");
  }
}
