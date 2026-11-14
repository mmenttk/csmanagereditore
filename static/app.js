/* CS Manager Save Editor Frontend (vanilla JS) */

const state = {
  meta: null,
  summary: null,
  saves: [],
  teams: [],
  activeTab: "transfers",

  // Players pagination & selection
  playerOffset: 0,
  playerLimit: 80,
  playerTotal: 0,
  selectedPlayerId: null,
  selectedPlayerData: null,

  // Staff pagination & selection
  staffOffset: 0,
  staffLimit: 80,
  staffTotal: 0,
  selectedStaffId: null,
  selectedStaffData: null,

  // Teams selection
  selectedTeamId: null,
  selectedTeamData: null,

  // Transfers
  txAllPlayers: [],
  txAllStaff: [],
  txSelectedBenchPlayerId: 0,

  // Stats Hub
  statsData: null,
  statsSortKey: "rating",
  statsSortDir: -1,
  statsTeamSortKey: "worldRank",
  statsTeamSortDir: 1,
  top20VotePlayerId: null,

  // Bug Showcase
  showcaseData: null,

  // Data Science & Manager Helper & God Mode
  realismData: null,
  realismSortKey: "worldRank",
  realismSortDir: 1,
  helperData: null,
  godModeData: null,
};

const $ = (id) => document.getElementById(id);

function escapeHtml(str) {
  return String(str ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function toast(msg, kind = "info") {
  const stack = $("toastStack");
  const el = document.createElement("div");
  el.className = `toast ${kind === "ok" ? "ok" : kind === "err" ? "err" : ""}`;
  el.textContent = msg;
  stack.appendChild(el);
  setTimeout(() => el.remove(), 4500);
}

async function api(url, opts = {}) {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.error || `HTTP ${res.status}`);
  }
  return data;
}

function formatDateObj(d) {
  if (!d || typeof d !== "object" || !d.year) return "-";
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.year}-${pad(d.month)}-${pad(d.day)}`;
}

function dateObjToIso(d) {
  if (!d || typeof d !== "object" || !d.year) return "2028-12-31T00:00:00";
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.year}-${pad(d.month)}-${pad(d.day)}T${pad(d.hour || 0)}:${pad(d.minute || 0)}:${pad(d.second || 0)}`;
}

function isoToDateObj(isoStr, fallback) {
  const m = String(isoStr || "").trim().match(/^(\d{4})-(\d{1,2})-(\d{1,2})(?:T(\d{1,2}):(\d{1,2}):(\d{1,2}))?/);
  if (!m) return fallback || { year: 2028, month: 12, day: 31, hour: 0, minute: 0, second: 0 };
  return {
    year: Number(m[1]),
    month: Number(m[2]),
    day: Number(m[3]),
    hour: Number(m[4] || 0),
    minute: Number(m[5] || 0),
    second: Number(m[6] || 0),
  };
}

function populateSelect(sel, entries, selectedVal, includeEmptyLabel = null) {
  sel.innerHTML = "";
  if (includeEmptyLabel !== null) {
    const opt = document.createElement("option");
    opt.value = "";
    opt.textContent = includeEmptyLabel;
    sel.appendChild(opt);
  }
  for (const [val, label] of entries) {
    const opt = document.createElement("option");
    opt.value = String(val);
    opt.textContent = label;
    if (String(val) === String(selectedVal)) opt.selected = true;
    sel.appendChild(opt);
  }
}

function dictEntries(dictObj) {
  return Object.entries(dictObj || {}).sort((a, b) => a[1].localeCompare(b[1]));
}

function enumEntries(dictObj) {
  return Object.entries(dictObj || {}).sort((a, b) => Number(a[0]) - Number(b[0]));
}

// =========================================================================
// Save Loading / Status / Validation
// =========================================================================

async function refreshSavePicker() {
  const res = await api("/api/saves");
  state.saves = res.saves || [];
  const picker = $("savePicker");
  picker.innerHTML = "";
  for (const s of state.saves) {
    const opt = document.createElement("option");
    opt.value = s.path;
    opt.textContent = `[${s.source}] ${s.name} (${s.size_mb} MB - ${s.modified})`;
    if (state.summary && state.summary.path === s.path) opt.selected = true;
    picker.appendChild(opt);
  }
}

function renderStatusBar() {
  const bar = $("statusBar");
  const s = state.summary;
  if (!s || !s.path) {
    bar.innerHTML = `<span class="muted">No save loaded. Select a save file above and click Load.</span>`;
    return;
  }
  const dirtyBadge = s.dirty
    ? `<span class="pill pill-warn">Unsaved Changes</span>`
    : `<span class="pill pill-ok">Saved</span>`;
  bar.innerHTML = `
    ${dirtyBadge}
    <span><strong>File:</strong> <span class="mono">${escapeHtml(s.filename)}</span></span>
    <span><strong>Game Date:</strong> ${formatDateObj(s.datetime)}</span>
    <span><strong>Manager:</strong> ${escapeHtml(s.managerName || "-")}</span>
    <span><strong>User Org:</strong> <span class="pill pill-blue">${escapeHtml(s.userTeamName || "-")}</span></span>
    <span><strong>Players:</strong> ${s.counts?.players ?? 0}</span>
    <span><strong>Staff:</strong> ${s.counts?.staffers ?? 0}</span>
    <span><strong>Teams:</strong> ${s.counts?.teams ?? 0}</span>
    <span class="muted">v${escapeHtml(s.gameVersion || "")}</span>
  `;
}

async function loadSavePath(path) {
  try {
    state.summary = await api("/api/load", { method: "POST", body: JSON.stringify({ path }) });
    renderStatusBar();
    await refreshAllViews();
    toast(`Loaded ${state.summary.filename}`, "ok");
  } catch (err) {
    toast(`Load failed: ${err.message}`, "err");
  }
}

async function refreshSummaryOnly() {
  state.summary = await api("/api/summary");
  renderStatusBar();
}

async function refreshAllViews() {
  state.statsData = null;
  state.showcaseData = null;
  state.realismData = null;
  state.helperData = null;
  state.godModeData = null;
  const tRes = await api("/api/teams");
  state.teams = tRes.teams || [];

  populateFilters();
  await Promise.all([
    loadPlayersList(),
    loadStaffList(),
    renderTeamsTable(),
    initTransfersTab(),
  ]);
  if (state.activeTab === "stats") {
    await loadStatsOverview();
  } else if (state.activeTab === "showcase") {
    await loadBugShowcase();
  } else if (state.activeTab === "realism") {
    await loadStrengthRealism();
  } else if (state.activeTab === "helper") {
    await loadManagerHelper();
  } else if (state.activeTab === "godmode") {
    await loadGodMode();
  }

  if (state.selectedPlayerId) {
    try {
      await openPlayerEditor(state.selectedPlayerId);
    } catch {
      state.selectedPlayerId = null;
    }
  }
  if (state.selectedStaffId) {
    try {
      await openStaffEditor(state.selectedStaffId);
    } catch {
      state.selectedStaffId = null;
    }
  }
  if (state.selectedTeamId) {
    try {
      await openTeamEditor(state.selectedTeamId);
    } catch {
      state.selectedTeamId = null;
    }
  }
}

function populateFilters() {
  const teamOpts = state.teams.map((t) => [t.id, `${t.name}${t.isUserTeam ? " ★" : ""}`]);
  populateSelect($("playerFilterTeam"), [["0", "Free Agents"], ...teamOpts], $("playerFilterTeam").value, "All Teams");
  populateSelect($("staffFilterTeam"), [["0", "Free Agents"], ...teamOpts], $("staffFilterTeam").value, "All Teams");
  populateSelect($("playerFilterNation"), dictEntries(state.meta.nations), $("playerFilterNation").value, "All Nations");
  populateSelect($("staffFilterRole"), enumEntries(state.meta.staffRoles), $("staffFilterRole").value, "All Roles");
  if ($("statsFilterTeam")) {
    populateSelect($("statsFilterTeam"), teamOpts, $("statsFilterTeam").value, "All Teams");
  }
}

async function runValidate(fix = false) {
  try {
    const res = await api("/api/validate", { method: "POST", body: JSON.stringify({ fix }) });
    const body = $("validateModalBody");
    if (res.issueCount === 0) {
      body.innerHTML = `<div class="pill pill-ok" style="font-size:13px;padding:6px 12px;">All checks passed! 0 roster/tactics mismatches found.</div>`;
      $("btnRunAutoFix").style.display = "none";
    } else if (fix) {
      body.innerHTML = `
        <div class="pill pill-ok" style="margin-bottom:10px;">Auto-fixed ${res.fixedTeamCount} team(s) and recalculated AI tactics!</div>
        <p class="muted">Fixed team IDs: ${res.fixedTeamIds.join(", ") || "none"}. Click "Save (with Backup)" to write changes to disk.</p>
      `;
      $("btnRunAutoFix").style.display = "none";
      await refreshSummaryOnly();
      await refreshAllViews();
    } else {
      $("btnRunAutoFix").style.display = "";
      const listHtml = res.issues
        .map((iss) => {
          if (iss.type === "team_tactics_mismatch") {
            return `<div class="subcard"><strong>${escapeHtml(iss.teamName)} (ID ${iss.teamId})</strong><ul style="margin:6px 0 0 18px;">${iss.details
              .map((d) => `<li>${escapeHtml(d)}</li>`)
              .join("")}</ul></div>`;
          }
          return `<div class="subcard"><strong>${escapeHtml(iss.type)}</strong>: ${escapeHtml(JSON.stringify(iss))}</div>`;
        })
        .join("");
      body.innerHTML = `<p><span class="pill pill-bad">${res.issueCount} issue(s) found</span></p>${listHtml}`;
    }
    $("validateModal").classList.add("open");
  } catch (err) {
    toast(`Validation error: ${err.message}`, "err");
  }
}

// =========================================================================
// TRANSFERS TAB
// =========================================================================

async function initTransfersTab() {
  // Fetch all players (lightweight enough: ~2000 items) & staff for searchable transfer pickers
  const [pRes, sRes] = await Promise.all([
    api("/api/players?limit=5000"),
    api("/api/staff?limit=2000"),
  ]);
  state.txAllPlayers = pRes.items || [];
  state.txAllStaff = sRes.items || [];

  populateSelect($("txContractType"), enumEntries(state.meta.contractType), 0);
  populateSelect($("txPlayerStatus"), enumEntries(state.meta.playerStatus), 1);
  populateSelect($("txIglRole"), enumEntries(state.meta.roleStatus), 2);
  populateSelect($("txSniperRole"), enumEntries(state.meta.roleStatus), 2);
  populateSelect($("txStaffRole"), enumEntries(state.meta.staffRoles), 0);

  renderTxPlayerOptions();
  renderTxTeamOptions();
  renderTxStaffOptions();
  renderTxStaffTeamOptions();
  await Promise.all([loadTargetRosterPreview(), loadTransferHistory()]);
}

function renderTxPlayerOptions() {
  const q = $("txPlayerSearch").value.trim().toLowerCase();
  const sel = $("txPlayerSelect");
  const prev = sel.value;
  const filtered = state.txAllPlayers
    .filter((p) => !q || p.name.toLowerCase().includes(q) || p.teamName.toLowerCase().includes(q) || String(p.id) === q)
    .slice(0, 200);
  sel.innerHTML = "";
  for (const p of filtered) {
    const opt = document.createElement("option");
    opt.value = String(p.id);
    opt.textContent = `${p.name} (${p.teamName}${p.benched ? " - Bench" : ""}, Avg ${p.avgSkill})`;
    if (String(p.id) === String(prev)) opt.selected = true;
    sel.appendChild(opt);
  }
  onTxPlayerChange();
}

async function onTxPlayerChange() {
  const pid = $("txPlayerSelect").value;
  if (!pid) {
    $("txPlayerSummary").textContent = "";
    return;
  }
  const summaryItem = state.txAllPlayers.find((x) => String(x.id) === String(pid));
  if (summaryItem) {
    $("txPlayerSummary").innerHTML = `Current: <strong>${escapeHtml(summaryItem.teamName)}</strong> | Age ${summaryItem.age} | ${escapeHtml(
      summaryItem.nationName
    )} | Rep ${summaryItem.reputation} | Salary $${(summaryItem.salaryYear || 0).toLocaleString()}/yr`;
  }
  try {
    const detail = await api(`/api/player/${pid}`);
    const c = detail.contract;
    if (c) {
      $("txSalary").value = c.salaryYear ?? 250000;
      $("txEndDate").value = dateObjToIso(c.endDate);
      $("txContractType").value = String(c.contractType ?? 0);
      $("txPlayerStatus").value = String(c.status ?? 1);
      $("txIglRole").value = String(c.igl ?? 2);
      $("txSniperRole").value = String(c.sniper ?? 2);
      $("txSignFee").value = c.signingOnFee ?? 0;
    } else {
      $("txSalary").value = 180000;
      $("txEndDate").value = "2028-12-31T00:00:00";
      $("txContractType").value = "0";
      $("txPlayerStatus").value = "1";
      $("txIglRole").value = "2";
      $("txSniperRole").value = "2";
      $("txSignFee").value = 0;
    }
  } catch {
    // ignore transient fetch errors
  }
}

function renderTxTeamOptions() {
  const q = $("txTeamSearch").value.trim().toLowerCase();
  const sel = $("txTargetTeam");
  const prev = sel.value;
  sel.innerHTML = "";
  const faOpt = document.createElement("option");
  faOpt.value = "0";
  faOpt.textContent = "0 - Release to Free Agency";
  sel.appendChild(faOpt);

  for (const t of state.teams) {
    if (q && !t.name.toLowerCase().includes(q) && String(t.id) !== q) continue;
    const opt = document.createElement("option");
    opt.value = String(t.id);
    opt.textContent = `${t.name}${t.isUserTeam ? " ★" : ""} (${t.activeCount} active, ${t.benchedCount} bench)`;
    if (String(t.id) === String(prev)) opt.selected = true;
    sel.appendChild(opt);
  }
  if (!sel.value && state.teams.length > 0) {
    sel.value = String(state.teams[0].id);
  }
}

function getRosterRoleBadges(r, team) {
  const badges = [];
  const activeGt = (team?.generalTactics || []).find((g) => g.active) || (team?.generalTactics || [])[0];
  if (!r.benched && activeGt) {
    if (activeGt.iglId === r.playerId) badges.push({ label: "IGL", cls: "pill-blue" });
    else if (activeGt.secondIglId === r.playerId) badges.push({ label: "2nd IGL", cls: "pill-blue" });
    if (activeGt.sniperId === r.playerId) badges.push({ label: "AWP", cls: "pill-purple" });
    else if (activeGt.secondSniperId === r.playerId) badges.push({ label: "2nd AWP", cls: "pill-purple" });
  } else {
    if (r.igl === 0) badges.push({ label: r.benched ? "Pref IGL" : "IGL", cls: r.benched ? "" : "pill-blue" });
    else if (r.igl === 1) badges.push({ label: r.benched ? "Pref 2nd IGL" : "2nd IGL", cls: r.benched ? "" : "pill-blue" });
    if (r.sniper === 0) badges.push({ label: r.benched ? "Pref AWP" : "AWP", cls: r.benched ? "" : "pill-purple" });
    else if (r.sniper === 1) badges.push({ label: r.benched ? "Pref 2nd AWP" : "2nd AWP", cls: r.benched ? "" : "pill-purple" });
  }
  return badges;
}

function renderRosterRolePills(r, team) {
  return getRosterRoleBadges(r, team)
    .map((b) => `<span class="pill ${b.cls}">${escapeHtml(b.label)}</span>`)
    .join(" ");
}

async function loadTargetRosterPreview() {
  const tid = Number($("txTargetTeam").value || 0);
  const box = $("txTargetRoster");
  state.txSelectedBenchPlayerId = 0;
  if (!tid) {
    box.innerHTML = `<div class="muted">Free Agency selected — player's existing contract will be removed and old team tactics rebuilt.</div>`;
    $("btnTxRecalcTactics").disabled = true;
    return;
  }
  $("btnTxRecalcTactics").disabled = false;
  try {
    const data = await api(`/api/team/${tid}`);
    const active = data.roster.filter((r) => !r.benched);
    const bench = data.roster.filter((r) => r.benched);

    const renderCard = (r) => {
      const isChecked = state.txSelectedBenchPlayerId === r.playerId;
      return `
        <div class="roster-card ${isChecked ? "selected-bench" : ""}" data-pid="${r.playerId}">
          <div>
            <strong>${escapeHtml(r.name)}</strong>
            <span class="pill ${r.benched ? "pill-warn" : "pill-ok"}">${r.benched ? "Benched" : "Starter"}</span>
            ${renderRosterRolePills(r, data.team)}
            <div class="muted" style="font-size:11.5px;">ID ${r.playerId} | Avg Skill ${r.avgSkill} | ${escapeHtml(r.nationName)} | $${r.salaryYear.toLocaleString()}/yr</div>
          </div>
          <div class="inline-actions">
            ${
              !r.benched
                ? `<button class="btn btn-sm btn-pick-bench" data-pid="${r.playerId}">${isChecked ? "Will Bench ✓" : "Bench on Transfer"}</button>`
                : ""
            }
            <button class="btn btn-sm btn-toggle-bench" data-pid="${r.playerId}" data-benched="${r.benched ? "0" : "1"}">
              ${r.benched ? "Promote Now" : "Bench Now"}
            </button>
          </div>
        </div>
      `;
    };

    box.innerHTML = `
      <div style="margin-bottom:8px;">
        <strong>${escapeHtml(data.team.name)}</strong> — Balance: <span class="pill">$${(data.team.teamFinances?.currentBalance ?? 0).toLocaleString()}</span>
        <span class="pill">${active.length} Starters / ${bench.length} Benched</span>
      </div>
      ${active.map(renderCard).join("") || '<div class="muted">No active starters.</div>'}
      ${bench.length ? `<div class="muted" style="margin:8px 0 4px;font-size:11.5px;font-weight:700;">BENCH</div>${bench.map(renderCard).join("")}` : ""}
    `;

    box.querySelectorAll(".btn-pick-bench").forEach((btn) => {
      btn.addEventListener("click", () => {
        const pid = Number(btn.dataset.pid);
        state.txSelectedBenchPlayerId = state.txSelectedBenchPlayerId === pid ? 0 : pid;
        box.querySelectorAll(".roster-card").forEach((c) => {
          const cpid = Number(c.dataset.pid);
          c.classList.toggle("selected-bench", cpid === state.txSelectedBenchPlayerId);
          const pickBtn = c.querySelector(".btn-pick-bench");
          if (pickBtn) pickBtn.textContent = cpid === state.txSelectedBenchPlayerId ? "Will Bench ✓" : "Bench on Transfer";
        });
        $("txBenchHint").textContent = state.txSelectedBenchPlayerId
          ? `Player #${state.txSelectedBenchPlayerId} will be benched when transfer executes.`
          : "Optional: pick a starter on the right to bench during transfer.";
      });
    });

    box.querySelectorAll(".btn-toggle-bench").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const pid = Number(btn.dataset.pid);
        const benched = btn.dataset.benched === "1";
        try {
          await api(`/api/player/${pid}/bench`, {
            method: "POST",
            body: JSON.stringify({ benched, autoTactics: true }),
          });
          await refreshSummaryOnly();
          await refreshAllViews();
          toast(`${benched ? "Benched" : "Promoted"} player #${pid} & recalculated tactics`, "ok");
        } catch (err) {
          toast(err.message, "err");
        }
      });
    });
  } catch (err) {
    box.innerHTML = `<div class="muted">${escapeHtml(err.message)}</div>`;
  }
}

async function executePlayerTransfer() {
  const playerId = Number($("txPlayerSelect").value || 0);
  const targetTeamId = Number($("txTargetTeam").value || 0);
  if (!playerId) return toast("Select a player first.", "err");

  const payload = {
    playerId,
    targetTeamId,
    benchPlayerId: state.txSelectedBenchPlayerId || 0,
    joinBenched: $("txJoinBenched").checked,
    autoPromoteOldTeam: $("txAutoPromoteOld").checked,
    buyoutPrice: Number($("txBuyout").value || 0),
    applyFinances: $("txApplyFinances").checked,
    salaryYear: Number($("txSalary").value || 250000),
    endDate: isoToDateObj($("txEndDate").value),
    contractType: Number($("txContractType").value || 0),
    status: Number($("txPlayerStatus").value || 1),
    igl: Number($("txIglRole").value || 2),
    sniper: Number($("txSniperRole").value || 2),
    signingOnFee: Number($("txSignFee").value || 0),
  };

  try {
    const res = await api("/api/transfer/player", { method: "POST", body: JSON.stringify(payload) });
    await refreshSummaryOnly();
    await refreshAllViews();
    toast(
      res.status === "released"
        ? `Released player #${playerId} to Free Agency`
        : `Transferred player #${playerId} to team #${targetTeamId} & rebuilt tactics`,
      "ok"
    );
  } catch (err) {
    toast(`Transfer failed: ${err.message}`, "err");
  }
}

function renderTxStaffOptions() {
  const q = $("txStaffSearch").value.trim().toLowerCase();
  const sel = $("txStaffSelect");
  const prev = sel.value;
  const filtered = state.txAllStaff
    .filter((s) => !q || s.name.toLowerCase().includes(q) || s.teamName.toLowerCase().includes(q) || String(s.id) === q)
    .slice(0, 200);
  sel.innerHTML = "";
  for (const s of filtered) {
    const opt = document.createElement("option");
    opt.value = String(s.id);
    opt.textContent = `${s.name} (${s.teamName} - ${s.roleName}, Avg ${s.avgSkill})`;
    if (String(s.id) === String(prev)) opt.selected = true;
    sel.appendChild(opt);
  }
  onTxStaffChange();
}

async function onTxStaffChange() {
  const sid = $("txStaffSelect").value;
  if (!sid) return;
  try {
    const detail = await api(`/api/staff/${sid}`);
    const c = detail.contract;
    if (c) {
      $("txStaffRole").value = String(c.role ?? 0);
      $("txStaffSalary").value = c.salaryYear ?? 180000;
      $("txStaffEndDate").value = dateObjToIso(c.endDate);
    } else {
      $("txStaffRole").value = "0";
      $("txStaffSalary").value = 150000;
      $("txStaffEndDate").value = "2028-12-31T00:00:00";
    }
  } catch {
    // ignore
  }
}

function renderTxStaffTeamOptions() {
  const sel = $("txStaffTargetTeam");
  const prev = sel.value;
  sel.innerHTML = "";
  const faOpt = document.createElement("option");
  faOpt.value = "0";
  faOpt.textContent = "0 - Release to Free Agency";
  sel.appendChild(faOpt);
  for (const t of state.teams) {
    const opt = document.createElement("option");
    opt.value = String(t.id);
    opt.textContent = `${t.name}${t.isUserTeam ? " ★" : ""}`;
    if (String(t.id) === String(prev)) opt.selected = true;
    sel.appendChild(opt);
  }
}

async function executeStaffTransfer() {
  const staffId = Number($("txStaffSelect").value || 0);
  const targetTeamId = Number($("txStaffTargetTeam").value || 0);
  if (!staffId) return toast("Select a staff member first.", "err");

  const payload = {
    staffId,
    targetTeamId,
    role: Number($("txStaffRole").value || 0),
    replaceExisting: $("txStaffReplace").checked,
    buyoutPrice: Number($("txStaffBuyout").value || 0),
    applyFinances: $("txStaffApplyFinances").checked,
    salaryYear: Number($("txStaffSalary").value || 180000),
    endDate: isoToDateObj($("txStaffEndDate").value),
  };
  try {
    await api("/api/transfer/staff", { method: "POST", body: JSON.stringify(payload) });
    await refreshSummaryOnly();
    await refreshAllViews();
    toast(`Staff transfer complete (#${staffId})`, "ok");
  } catch (err) {
    toast(`Staff transfer failed: ${err.message}`, "err");
  }
}

async function loadTransferHistory() {
  const res = await api("/api/transfers?limit=80");
  const tbody = $("txHistoryBody");
  tbody.innerHTML = (res.transfers || [])
    .map(
      (th) => `
      <tr>
        <td>${formatDateObj(th.datetime)}</td>
        <td><span class="pill">${escapeHtml(th.personType)}</span></td>
        <td><strong>${escapeHtml(th.personName)}</strong></td>
        <td>${escapeHtml(th.fromTeamName)}</td>
        <td>${escapeHtml(th.toTeamName)}</td>
        <td>${th.purchasePrice > 0 ? "Paid" : "Free / End"}</td>
        <td>$${Number(th.purchasePrice || 0).toLocaleString()}</td>
      </tr>
    `
    )
    .join("");
}

// =========================================================================
// PLAYERS TAB
// =========================================================================

async function loadPlayersList() {
  const params = new URLSearchParams({
    q: $("playerFilterQ").value.trim(),
    team_id: $("playerFilterTeam").value,
    nation: $("playerFilterNation").value,
    free_only: $("playerFilterFree").checked ? "1" : "0",
    offset: String(state.playerOffset),
    limit: String(state.playerLimit),
  });
  const res = await api(`/api/players?${params.toString()}`);
  state.playerTotal = res.total;
  $("playersCountLabel").textContent = `${res.total} players`;

  const tbody = $("playersTableBody");
  tbody.innerHTML = res.items
    .map(
      (p) => `
      <tr data-id="${p.id}" class="${state.selectedPlayerId === p.id ? "selected" : ""}">
        <td class="mono">${p.id}</td>
        <td><strong>${escapeHtml(p.name)}</strong> ${p.benched ? '<span class="pill pill-warn">Bench</span>' : ""}</td>
        <td>${escapeHtml(p.teamName)}</td>
        <td>${escapeHtml(p.nationName)}</td>
        <td>${p.age}</td>
        <td>${p.reputation}</td>
      </tr>
    `
    )
    .join("");

  tbody.querySelectorAll("tr").forEach((tr) => {
    tr.addEventListener("click", () => openPlayerEditor(Number(tr.dataset.id)));
  });

  const start = res.total === 0 ? 0 : state.playerOffset + 1;
  const end = Math.min(state.playerOffset + state.playerLimit, res.total);
  $("playersPageInfo").textContent = `${start}-${end} of ${res.total}`;
  $("playersPrev").disabled = state.playerOffset <= 0;
  $("playersNext").disabled = state.playerOffset + state.playerLimit >= res.total;
}

async function openPlayerEditor(playerId) {
  state.selectedPlayerId = playerId;
  const data = await api(`/api/player/${playerId}`);
  state.selectedPlayerData = data;
  $("playersTableBody")
    .querySelectorAll("tr")
    .forEach((tr) => tr.classList.toggle("selected", Number(tr.dataset.id) === playerId));

  const p = data.player;
  const c = data.contract;
  $("playerEditorTitle").textContent = `Edit Player: ${p.name} (#${p.id})`;
  $("btnPlayerApply").disabled = false;

  // Build Potential map from m_Keys/m_Values
  const potMap = {};
  const pKeys = p.potential?.m_Keys || [];
  const pVals = p.potential?.m_Values || [];
  pKeys.forEach((k, idx) => {
    potMap[String(k)] = pVals[idx] ?? 10;
  });

  const nationOpts = dictEntries(state.meta.nations)
    .map(([k, v]) => `<option value="${k}" ${String(k) === String(p.nation) ? "selected" : ""}>${escapeHtml(v)}</option>`)
    .join("");
  const mentalityOpts = enumEntries(state.meta.playerMentalities)
    .map(([k, v]) => `<option value="${k}" ${String(k) === String(p.preferredMentality) ? "selected" : ""}>${escapeHtml(v)}</option>`)
    .join("");

  const skillsHtml = state.meta.playerSkills
    .map((sk) => {
      const val = Number(p.skills?.[sk.key] ?? 10).toFixed(1);
      const pot = potMap[String(sk.id)] ?? 10;
      return `
        <div class="skill-item">
          <div>
            <span class="skill-name">${escapeHtml(sk.label)}</span>
            <span class="skill-group">${escapeHtml(sk.group)}</span>
          </div>
          <input type="number" step="0.5" min="1" max="20" class="p-skill" data-key="${sk.key}" value="${val}" title="Current Skill (1-20)" />
          <input type="number" step="1" min="1" max="20" class="p-pot" data-id="${sk.id}" value="${pot}" title="Potential Cap (1-20)" />
        </div>
      `;
    })
    .join("");

  const rolesHtml = (p.mapPositionAttributes || [])
    .map((attr) => {
      const label = state.meta.playerPositions[String(attr.positionType)] || `Role ${attr.positionType}`;
      return `
        <div class="skill-item" style="grid-template-columns:1fr 64px 72px;">
          <span class="skill-name">${escapeHtml(label)}</span>
          <input type="number" min="1" max="10" step="1" class="p-role-comfort" data-pos="${attr.positionType}" value="${attr.roleComfort}" title="Comfort (1-10)" />
          <input type="number" min="0" max="100" step="1" class="p-role-prog" data-pos="${attr.positionType}" value="${Number(attr.progress || 0).toFixed(0)}" title="Progress" />
        </div>
      `;
    })
    .join("");

  const mapsById = Object.fromEntries((state.summary?.maps || []).map((m) => [m.id, m.name]));
  const mapHtml = (p.mapOpinions || [])
    .map((mo) => {
      const mname = mapsById[mo.mapId] || `Map ${mo.mapId}`;
      return `
        <label class="map-chip ${mo.like ? "liked" : ""}">
          <span>${escapeHtml(mname)}</span>
          <input type="checkbox" class="p-map-like" data-mapid="${mo.mapId}" ${mo.like ? "checked" : ""} />
        </label>
      `;
    })
    .join("");

  const persHtml = state.meta.personalityAxes
    .map((ax) => {
      const val = p.personality?.[ax.key] ?? 10;
      return `
        <div class="pers-item">
          <div class="pers-head">
            <span>${escapeHtml(ax.label)}</span>
            <span class="mono" id="persVal-${ax.key}">${val}</span>
          </div>
          <input type="range" min="1" max="20" step="1" class="p-pers" data-key="${ax.key}" value="${val}" />
          <div class="pers-ends"><span>1: ${escapeHtml(ax.low)}</span><span>20: ${escapeHtml(ax.high)}</span></div>
        </div>
      `;
    })
    .join("");

  const teamOptionsForContract = [
    `<option value="0">Free Agent (No Contract)</option>`,
    ...state.teams.map((t) => `<option value="${t.id}" ${c && t.id === c.teamId ? "selected" : ""}>${escapeHtml(t.name)}</option>`),
  ].join("");

  const contractHtml = `
    <div class="form-grid">
      <div class="field">
        <label>Team (changes route via Transfer)</label>
        <select id="pContractTeam">${teamOptionsForContract}</select>
      </div>
      <div class="field"><label>Salary / Year ($)</label><input id="pSalary" type="number" step="1000" value="${c ? c.salaryYear : 250000}" /></div>
      <div class="field"><label>End Date (ISO)</label><input id="pEndDate" type="text" value="${c ? dateObjToIso(c.endDate) : "2028-12-31T00:00:00"}" /></div>
      <div class="field"><label>Contract Type</label><select id="pContractType"></select></div>
      <div class="field"><label>Squad Status</label><select id="pStatus"></select></div>
      <div class="field"><label>IGL Status</label><select id="pIgl"></select></div>
      <div class="field"><label>Sniper / AWP</label><select id="pSniper"></select></div>
      <div class="field"><label>Transfer Status</label><select id="pTransferStatus"></select></div>
      <div class="field"><label>Asking Price ($)</label><input id="pAskingPrice" type="number" step="1000" value="${c ? c.askingPrice : 0}" /></div>
      <div class="field"><label>Signing-On Fee ($)</label><input id="pSignFee" type="number" step="1000" value="${c ? c.signingOnFee : 0}" /></div>
    </div>
    <div class="checkbox-row" style="margin-top:6px;">
      <input id="pBenched" type="checkbox" ${c && c.benched ? "checked" : ""} />
      <label for="pBenched">Benched on current team</label>
    </div>
  `;

  $("playerEditorBody").innerHTML = `
    <div class="subcard">
      <div class="subcard-title">Profile &amp; Mentality</div>
      <div class="form-grid">
        <div class="field"><label>Alias / Name</label><input id="pName" type="text" value="${escapeHtml(p.name)}" /></div>
        <div class="field"><label>Age</label><input id="pAge" type="number" min="15" max="55" value="${p.age}" /></div>
        <div class="field"><label>Nation</label><select id="pNation">${nationOpts}</select></div>
        <div class="field"><label>Reputation (1-20)</label><input id="pRep" type="number" min="1" max="20" value="${p.reputation}" /></div>
        <div class="field"><label>Mentality</label><select id="pMentality">${mentalityOpts}</select></div>
        <div class="field"><label>Longevity</label><input id="pLongevity" type="number" step="1" value="${p.longevity ?? 30}" /></div>
      </div>
      <div class="checkbox-row" style="margin-top:6px;">
        <input id="pRetire" type="checkbox" ${p.setForRetirement ? "checked" : ""} />
        <label for="pRetire">Set for Retirement</label>
      </div>
    </div>

    <div class="subcard">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
        <div class="subcard-title" style="margin:0;">Skills (Left) &amp; Potential Caps (Right)</div>
        <div class="inline-actions">
          <button type="button" class="btn btn-sm" id="btnPSyncPot">Sync Pot &ge; Skill</button>
          <button type="button" class="btn btn-sm" id="btnPAll20">Max All 20</button>
        </div>
      </div>
      <div class="skill-grid">${skillsHtml}</div>
    </div>

    <div class="subcard">
      <div class="subcard-title">Contract (${escapeHtml(data.teamName)})</div>
      ${contractHtml}
    </div>

    <div class="two-col">
      <div class="subcard">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
          <div class="subcard-title" style="margin:0;">Languages Spoken (1-20)</div>
          <button type="button" class="btn btn-sm" id="btnAddPlayerLang">+ Add Language</button>
        </div>
        <div id="pLangList"></div>
      </div>

      <div class="subcard">
        <div class="subcard-title">Map Preferences (Checked = Likes Map)</div>
        <div class="map-grid">${mapHtml || '<span class="muted">No map opinions</span>'}</div>
      </div>
    </div>

    <div class="subcard">
      <div class="subcard-title">Map Role Comforts (1-10) &amp; Progress</div>
      <div class="skill-grid">${rolesHtml}</div>
    </div>

    <div class="subcard">
      <div class="subcard-title">Personality (1-20)</div>
      <div class="pers-grid">${persHtml}</div>
    </div>
  `;

  populateSelect($("pContractType"), enumEntries(state.meta.contractType), c ? c.contractType : 0);
  populateSelect($("pStatus"), enumEntries(state.meta.playerStatus), c ? c.status : 1);
  populateSelect($("pIgl"), enumEntries(state.meta.roleStatus), c ? c.igl : 2);
  populateSelect($("pSniper"), enumEntries(state.meta.roleStatus), c ? c.sniper : 2);
  populateSelect($("pTransferStatus"), enumEntries(state.meta.transferStatus), c ? c.transferStatus : 0);

  renderLangRows($("pLangList"), p.languagesSpoken || []);
  $("btnAddPlayerLang").addEventListener("click", () => addLangRow($("pLangList")));

  $("playerEditorBody").querySelectorAll(".p-pers").forEach((inp) => {
    inp.addEventListener("input", () => {
      const span = $(`persVal-${inp.dataset.key}`);
      if (span) span.textContent = inp.value;
    });
  });

  $("playerEditorBody").querySelectorAll(".p-map-like").forEach((cb) => {
    cb.addEventListener("change", () => cb.closest(".map-chip").classList.toggle("liked", cb.checked));
  });

  $("btnPSyncPot").addEventListener("click", () => {
    const skInputs = $("playerEditorBody").querySelectorAll(".p-skill");
    const potById = {};
    $("playerEditorBody").querySelectorAll(".p-pot").forEach((pi) => {
      potById[pi.dataset.id] = pi;
    });
    state.meta.playerSkills.forEach((sk, idx) => {
      const sv = Math.ceil(Number(skInputs[idx].value || 1));
      const pi = potById[String(sk.id)];
      if (pi && Number(pi.value) < sv) pi.value = String(Math.min(20, sv));
    });
  });

  $("btnPAll20").addEventListener("click", () => {
    $("playerEditorBody").querySelectorAll(".p-skill, .p-pot").forEach((i) => (i.value = "20"));
  });
}

function renderLangRows(container, langs) {
  container.innerHTML = "";
  for (const l of langs) {
    appendLangRow(container, l.languageId, l.languageSkill, l.limit ?? 20, l.progress ?? 0);
  }
}

function appendLangRow(container, langId = 13, skill = 20, limit = 20, progress = 0) {
  const row = document.createElement("div");
  row.className = "lang-row";
  row.dataset.limit = String(limit);
  row.dataset.progress = String(progress);
  const opts = dictEntries(state.meta.languages)
    .map(([k, v]) => `<option value="${k}" ${String(k) === String(langId) ? "selected" : ""}>${escapeHtml(v)}</option>`)
    .join("");
  row.innerHTML = `
    <select class="lang-id">${opts}</select>
    <input type="number" class="lang-skill" min="1" max="20" value="${skill}" title="Fluency 1-20" />
    <button type="button" class="btn btn-sm btn-danger btn-del-lang">X</button>
  `;
  row.querySelector(".btn-del-lang").addEventListener("click", () => row.remove());
  container.appendChild(row);
}

function addLangRow(container) {
  appendLangRow(container, 13, 20, 20, 0);
}

function collectLangRows(container) {
  const seen = new Set();
  const list = [];
  container.querySelectorAll(".lang-row").forEach((row) => {
    const lid = Number(row.querySelector(".lang-id").value);
    if (seen.has(lid)) return;
    seen.add(lid);
    const sk = Number(row.querySelector(".lang-skill").value || 20);
    list.push({
      languageId: lid,
      languageSkill: Math.max(1, Math.min(20, sk)),
      limit: Math.max(sk, Number(row.dataset.limit || 20)),
      progress: Number(row.dataset.progress || 0),
    });
  });
  return list;
}

async function applyPlayerChanges() {
  if (!state.selectedPlayerId || !state.selectedPlayerData) return;
  const orig = state.selectedPlayerData;
  const skills = {};
  $("playerEditorBody").querySelectorAll(".p-skill").forEach((i) => {
    skills[i.dataset.key] = Number(i.value || 1);
  });

  const potKeys = [];
  const potVals = [];
  $("playerEditorBody").querySelectorAll(".p-pot").forEach((i) => {
    potKeys.push(Number(i.dataset.id));
    potVals.push(Math.max(1, Math.min(20, Number(i.value || 1))));
  });

  const mapPositionAttributes = [];
  $("playerEditorBody").querySelectorAll(".p-role-comfort").forEach((i) => {
    const pos = Number(i.dataset.pos);
    const progInput = $("playerEditorBody").querySelector(`.p-role-prog[data-pos="${pos}"]`);
    mapPositionAttributes.push({
      positionType: pos,
      roleComfort: Math.max(1, Math.min(10, Number(i.value || 1))),
      progress: Number(progInput?.value || 0),
    });
  });

  const mapOpinions = [];
  $("playerEditorBody").querySelectorAll(".p-map-like").forEach((cb) => {
    mapOpinions.push({ mapId: Number(cb.dataset.mapid), like: cb.checked });
  });

  const personality = {};
  $("playerEditorBody").querySelectorAll(".p-pers").forEach((i) => {
    personality[i.dataset.key] = Number(i.value || 10);
  });

  const targetTid = Number($("pContractTeam").value || 0);
  let contractPayload = null;
  if (orig.contract !== null || targetTid > 0) {
    contractPayload = {
      teamId: targetTid,
      salaryYear: Number($("pSalary").value || 0),
      endDate: isoToDateObj($("pEndDate").value, orig.contract?.endDate),
      contractType: Number($("pContractType").value || 0),
      status: Number($("pStatus").value || 1),
      igl: Number($("pIgl").value || 2),
      sniper: Number($("pSniper").value || 2),
      transferStatus: Number($("pTransferStatus").value || 0),
      askingPrice: Number($("pAskingPrice").value || 0),
      signingOnFee: Number($("pSignFee").value || 0),
      benched: $("pBenched").checked,
    };
  }

  const payload = {
    player: {
      name: $("pName").value.trim(),
      age: Number($("pAge").value || 18),
      nation: Number($("pNation").value || 1),
      reputation: Math.max(1, Math.min(20, Number($("pRep").value || 1))),
      preferredMentality: Number($("pMentality").value || 1),
      longevity: Number($("pLongevity").value || 30),
      setForRetirement: $("pRetire").checked,
      skills,
      potential: { m_Keys: potKeys, m_Values: potVals },
      languagesSpoken: collectLangRows($("pLangList")),
      mapPositionAttributes,
      mapOpinions,
      personality,
    },
    contract: contractPayload,
  };

  try {
    const updated = await api(`/api/player/${state.selectedPlayerId}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    });
    state.selectedPlayerData = updated;
    await refreshSummaryOnly();
    await refreshAllViews();
    toast(`Updated player ${updated.player.name}`, "ok");
  } catch (err) {
    toast(`Failed to update player: ${err.message}`, "err");
  }
}

// =========================================================================
// STAFF TAB
// =========================================================================

async function loadStaffList() {
  const params = new URLSearchParams({
    q: $("staffFilterQ").value.trim(),
    team_id: $("staffFilterTeam").value,
    role: $("staffFilterRole").value,
    free_only: $("staffFilterFree").checked ? "1" : "0",
    offset: String(state.staffOffset),
    limit: String(state.staffLimit),
  });
  const res = await api(`/api/staff?${params.toString()}`);
  state.staffTotal = res.total;
  $("staffCountLabel").textContent = `${res.total} staff`;

  const tbody = $("staffTableBody");
  tbody.innerHTML = res.items
    .map(
      (s) => `
      <tr data-id="${s.id}" class="${state.selectedStaffId === s.id ? "selected" : ""}">
        <td class="mono">${s.id}</td>
        <td><strong>${escapeHtml(s.name)}</strong></td>
        <td>${escapeHtml(s.teamName)}</td>
        <td><span class="pill">${escapeHtml(s.roleName)}</span></td>
        <td>${s.age}</td>
        <td>${s.reputation}</td>
      </tr>
    `
    )
    .join("");

  tbody.querySelectorAll("tr").forEach((tr) => {
    tr.addEventListener("click", () => openStaffEditor(Number(tr.dataset.id)));
  });

  const start = res.total === 0 ? 0 : state.staffOffset + 1;
  const end = Math.min(state.staffOffset + state.staffLimit, res.total);
  $("staffPageInfo").textContent = `${start}-${end} of ${res.total}`;
  $("staffPrev").disabled = state.staffOffset <= 0;
  $("staffNext").disabled = state.staffOffset + state.staffLimit >= res.total;
}

async function openStaffEditor(staffId) {
  state.selectedStaffId = staffId;
  const data = await api(`/api/staff/${staffId}`);
  state.selectedStaffData = data;
  $("staffTableBody")
    .querySelectorAll("tr")
    .forEach((tr) => tr.classList.toggle("selected", Number(tr.dataset.id) === staffId));

  const s = data.staff;
  const c = data.contract;
  $("staffEditorTitle").textContent = `Edit Staff: ${s.name} (#${s.id})`;
  $("btnStaffApply").disabled = false;

  const potMap = {};
  (s.potential?.m_Keys || []).forEach((k, idx) => {
    potMap[String(k)] = (s.potential?.m_Values || [])[idx] ?? 10;
  });

  const nationOpts = dictEntries(state.meta.nations)
    .map(([k, v]) => `<option value="${k}" ${String(k) === String(s.nation) ? "selected" : ""}>${escapeHtml(v)}</option>`)
    .join("");
  const mentalityOpts = enumEntries(state.meta.staffMentalities)
    .map(([k, v]) => `<option value="${k}" ${String(k) === String(s.preferredMentality) ? "selected" : ""}>${escapeHtml(v)}</option>`)
    .join("");

  const skillsHtml = state.meta.staffSkills
    .map((sk) => {
      const val = Number(s.skills?.[sk.key] ?? 10).toFixed(1);
      const pot = potMap[String(sk.id)] ?? 10;
      return `
        <div class="skill-item">
          <span class="skill-name">${escapeHtml(sk.label)}</span>
          <input type="number" step="0.5" min="1" max="20" class="s-skill" data-key="${sk.key}" value="${val}" />
          <input type="number" step="1" min="1" max="20" class="s-pot" data-id="${sk.id}" value="${pot}" />
        </div>
      `;
    })
    .join("");

  const interestsHtml = (s.careerInterests || [])
    .map((ci) => {
      const rname = state.meta.staffRoles[String(ci.roleType)] || `Role ${ci.roleType}`;
      return `
        <div class="skill-item" style="grid-template-columns:1fr 72px;">
          <span class="skill-name">${escapeHtml(rname)}</span>
          <input type="number" min="1" max="20" step="1" class="s-ci" data-roletype="${ci.roleType}" value="${ci.roleInterest}" />
        </div>
      `;
    })
    .join("");

  const teamOptions = [
    `<option value="0">Free Agent (No Contract)</option>`,
    ...state.teams.map((t) => `<option value="${t.id}" ${c && t.id === c.teamId ? "selected" : ""}>${escapeHtml(t.name)}</option>`),
  ].join("");

  $("staffEditorBody").innerHTML = `
    <div class="subcard">
      <div class="subcard-title">Profile &amp; Mentality</div>
      <div class="form-grid">
        <div class="field"><label>Name</label><input id="sName" type="text" value="${escapeHtml(s.name)}" /></div>
        <div class="field"><label>Age</label><input id="sAge" type="number" min="20" max="85" value="${s.age}" /></div>
        <div class="field"><label>Nation</label><select id="sNation">${nationOpts}</select></div>
        <div class="field"><label>Reputation (1-20)</label><input id="sRep" type="number" min="1" max="20" value="${s.reputation}" /></div>
        <div class="field"><label>Mentality</label><select id="sMentality">${mentalityOpts}</select></div>
        <div class="field"><label>Retirement Consid. Age</label><input id="sRetAge" type="number" value="${s.retirementConsiderationAge ?? 65}" /></div>
      </div>
      <div class="checkbox-row" style="margin-top:6px;">
        <input id="sRetire" type="checkbox" ${s.setForRetirement ? "checked" : ""} />
        <label for="sRetire">Set for Retirement</label>
      </div>
    </div>

    <div class="subcard">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
        <div class="subcard-title" style="margin:0;">Staff Skills (Left) &amp; Potential Caps (Right)</div>
        <button type="button" class="btn btn-sm" id="btnSAll20">Max All 20</button>
      </div>
      <div class="skill-grid">${skillsHtml}</div>
    </div>

    <div class="subcard">
      <div class="subcard-title">Contract (${escapeHtml(data.teamName)})</div>
      <div class="form-grid">
        <div class="field"><label>Team</label><select id="sContractTeam">${teamOptions}</select></div>
        <div class="field"><label>Role</label><select id="sRole"></select></div>
        <div class="field"><label>Salary / Year ($)</label><input id="sSalary" type="number" step="1000" value="${c ? c.salaryYear : 180000}" /></div>
        <div class="field"><label>End Date (ISO)</label><input id="sEndDate" type="text" value="${c ? dateObjToIso(c.endDate) : "2028-12-31T00:00:00"}" /></div>
      </div>
      <div class="checkbox-row" style="margin-top:6px;">
        <input id="sRejectOffers" type="checkbox" ${c && c.rejectAllStaffOffers ? "checked" : ""} />
        <label for="sRejectOffers">Reject All Staff Offers</label>
      </div>
    </div>

    <div class="two-col">
      <div class="subcard">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
          <div class="subcard-title" style="margin:0;">Languages Spoken</div>
          <button type="button" class="btn btn-sm" id="btnAddStaffLang">+ Add Language</button>
        </div>
        <div id="sLangList"></div>
      </div>
      <div class="subcard">
        <div class="subcard-title">Career Role Interests (1-20)</div>
        <div class="skill-grid">${interestsHtml}</div>
      </div>
    </div>
  `;

  populateSelect($("sRole"), enumEntries(state.meta.staffRoles), c ? c.role : 0);
  renderLangRows($("sLangList"), s.languagesSpoken || []);
  $("btnAddStaffLang").addEventListener("click", () => addLangRow($("sLangList")));
  $("btnSAll20").addEventListener("click", () => {
    $("staffEditorBody").querySelectorAll(".s-skill, .s-pot").forEach((i) => (i.value = "20"));
  });
}

async function applyStaffChanges() {
  if (!state.selectedStaffId || !state.selectedStaffData) return;
  const orig = state.selectedStaffData;
  const skills = {};
  $("staffEditorBody").querySelectorAll(".s-skill").forEach((i) => {
    skills[i.dataset.key] = Number(i.value || 1);
  });

  const potKeys = [];
  const potVals = [];
  $("staffEditorBody").querySelectorAll(".s-pot").forEach((i) => {
    potKeys.push(Number(i.dataset.id));
    potVals.push(Math.max(1, Math.min(20, Number(i.value || 1))));
  });

  const careerInterests = [];
  $("staffEditorBody").querySelectorAll(".s-ci").forEach((i) => {
    careerInterests.push({
      roleType: Number(i.dataset.roletype),
      roleInterest: Math.max(1, Math.min(20, Number(i.value || 1))),
    });
  });

  const targetTid = Number($("sContractTeam").value || 0);
  let contractPayload = null;
  if (orig.contract !== null || targetTid > 0) {
    contractPayload = {
      teamId: targetTid,
      role: Number($("sRole").value || 0),
      salaryYear: Number($("sSalary").value || 0),
      endDate: isoToDateObj($("sEndDate").value, orig.contract?.endDate),
      rejectAllStaffOffers: $("sRejectOffers").checked,
    };
  }

  const payload = {
    staff: {
      name: $("sName").value.trim(),
      age: Number($("sAge").value || 30),
      nation: Number($("sNation").value || 1),
      reputation: Math.max(1, Math.min(20, Number($("sRep").value || 1))),
      preferredMentality: Number($("sMentality").value || 1),
      retirementConsiderationAge: Number($("sRetAge").value || 65),
      setForRetirement: $("sRetire").checked,
      skills,
      potential: { m_Keys: potKeys, m_Values: potVals },
      languagesSpoken: collectLangRows($("sLangList")),
      careerInterests,
    },
    contract: contractPayload,
  };

  try {
    const updated = await api(`/api/staff/${state.selectedStaffId}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    });
    state.selectedStaffData = updated;
    await refreshSummaryOnly();
    await refreshAllViews();
    toast(`Updated staff ${updated.staff.name}`, "ok");
  } catch (err) {
    toast(`Failed to update staff: ${err.message}`, "err");
  }
}

// =========================================================================
// TEAMS / ORGS TAB
// =========================================================================

function renderTeamsTable() {
  const q = $("teamFilterQ").value.trim().toLowerCase();
  const rows = state.teams.filter((t) => !q || t.name.toLowerCase().includes(q) || String(t.id) === q);
  $("teamsCountLabel").textContent = `${rows.length} orgs`;
  const tbody = $("teamsTableBody");
  tbody.innerHTML = rows
    .map(
      (t) => `
      <tr data-id="${t.id}" class="${state.selectedTeamId === t.id ? "selected" : ""}">
        <td class="mono">${t.id}</td>
        <td><strong>${escapeHtml(t.name)}</strong> ${t.isUserTeam ? '<span class="pill pill-blue">YOU</span>' : ""}</td>
        <td>${t.reputation}</td>
        <td>${t.activeCount} / ${t.activeCount + t.benchedCount}</td>
        <td>$${Number(t.balance || 0).toLocaleString()}</td>
      </tr>
    `
    )
    .join("");

  tbody.querySelectorAll("tr").forEach((tr) => {
    tr.addEventListener("click", () => openTeamEditor(Number(tr.dataset.id)));
  });
}

async function openTeamEditor(teamId) {
  state.selectedTeamId = teamId;
  const data = await api(`/api/team/${teamId}`);
  state.selectedTeamData = data;
  $("teamsTableBody")
    .querySelectorAll("tr")
    .forEach((tr) => tr.classList.toggle("selected", Number(tr.dataset.id) === teamId));

  const t = data.team;
  const fin = t.teamFinances || {};
  const coh = t.teamCohesion || {};
  const owner = t.owner || {};
  const job = t.jobSecurity || {};

  $("teamEditorTitle").textContent = `Edit Org: ${t.name} (#${t.id})`;
  $("btnTeamApply").disabled = false;
  $("btnTeamRecalc").disabled = false;

  const nationOpts = dictEntries(state.meta.nations)
    .map(([k, v]) => `<option value="${k}" ${String(k) === String(t.nation) ? "selected" : ""}>${escapeHtml(v)}</option>`)
    .join("");
  const langOpts = dictEntries(state.meta.languages)
    .map(([k, v]) => `<option value="${k}" ${String(k) === String(coh.mainLanguage) ? "selected" : ""}>${escapeHtml(v)}</option>`)
    .join("");

  const rosterHtml = data.roster
    .map(
      (r) => `
      <div class="roster-card">
        <div>
          <strong>${escapeHtml(r.name)}</strong>
          <span class="pill ${r.benched ? "pill-warn" : "pill-ok"}">${r.benched ? "Benched" : "Starter"}</span>
          ${renderRosterRolePills(r, t)}
          <span class="muted" style="font-size:12px;">Avg ${r.avgSkill} | Age ${r.age} | $${r.salaryYear.toLocaleString()}/yr</span>
        </div>
        <button class="btn btn-sm btn-team-bench" data-pid="${r.playerId}" data-benched="${r.benched ? "0" : "1"}">
          ${r.benched ? "Promote" : "Bench"}
        </button>
      </div>
    `
    )
    .join("");

  const staffHtml = data.staff
    .map(
      (s) => `
      <div class="roster-card">
        <div>
          <strong>${escapeHtml(s.name)}</strong>
          <span class="pill">${escapeHtml(s.roleName)}</span>
          <span class="muted" style="font-size:12px;">Avg ${s.avgSkill} | $${s.salaryYear.toLocaleString()}/yr</span>
        </div>
      </div>
    `
    )
    .join("");

  $("teamEditorBody").innerHTML = `
    <div class="subcard">
      <div class="subcard-title">Organization &amp; Owner</div>
      <div class="form-grid">
        <div class="field"><label>Org Name</label><input id="tName" type="text" value="${escapeHtml(t.name)}" /></div>
        <div class="field"><label>Nation</label><select id="tNation">${nationOpts}</select></div>
        <div class="field"><label>Reputation (1-20)</label><input id="tRep" type="number" min="1" max="20" value="${t.reputation}" /></div>
        <div class="field"><label>Rep Progress</label><input id="tRepProg" type="number" step="0.1" value="${t.reputationProgress ?? 0}" /></div>
        <div class="field"><label>Professional Status</label><select id="tProfStatus"></select></div>
        <div class="field"><label>Financial Strength (1-20)</label><input id="tFinStrength" type="number" min="1" max="20" value="${t.financialStrength ?? 10}" /></div>
        <div class="field"><label>Owner Name</label><input id="tOwnerName" type="text" value="${escapeHtml(owner.name || "")}" /></div>
        <div class="field"><label>Owner Hiring Bias</label><select id="tHiringBias"></select></div>
      </div>
    </div>

    <div class="subcard">
      <div class="subcard-title">Team Finances</div>
      <div class="form-grid">
        <div class="field"><label>Current Balance ($)</label><input id="tBalance" type="number" step="10000" value="${fin.currentBalance ?? 0}" /></div>
        <div class="field"><label>Owner Contribution</label><input id="tOwnerContrib" type="number" step="0.5" value="${fin.ownerContribution ?? 0}" /></div>
        <div class="field"><label>Owner Multiplier</label><input id="tOwnerMult" type="number" step="0.05" value="${fin.ownerContributionMultipler ?? 1}" /></div>
        <div class="field"><label>Merch Contribution</label><input id="tMerchContrib" type="number" step="0.5" value="${fin.merchandiseContribution ?? 0}" /></div>
        <div class="field"><label>Prize Money ($)</label><input id="tPrize" type="number" step="1000" value="${fin.prizeMoney ?? 0}" /></div>
        <div class="field"><label>Sponsor Bonus ($)</label><input id="tSponsor" type="number" step="1000" value="${fin.sponsorBonus ?? 0}" /></div>
        <div class="field"><label>Buyout Expenses ($)</label><input id="tBuyoutExp" type="number" step="1000" value="${fin.buyoutAndSignOnExpenses ?? 0}" /></div>
        <div class="field"><label>Buyout Income ($)</label><input id="tBuyoutInc" type="number" step="1000" value="${fin.buyoutIncome ?? 0}" /></div>
      </div>
    </div>

    <div class="two-col">
      <div class="subcard">
        <div class="subcard-title">Facilities &amp; Academy</div>
        <div class="form-grid">
          <div class="field"><label>Coffee Machine (0-4)</label><input id="tCoffee" type="number" min="0" max="4" value="${t.coffeeMachine ?? 0}" /></div>
          <div class="field"><label>Cable / Network (0-4)</label><input id="tCable" type="number" min="0" max="4" value="${t.cable ?? 0}" /></div>
          <div class="field"><label>Ventilation (0-4)</label><input id="tVent" type="number" min="0" max="4" value="${t.ventilation ?? 0}" /></div>
          <div class="field"><label>Recreation (0-4)</label><input id="tRec" type="number" min="0" max="4" value="${t.recreation ?? 0}" /></div>
          <div class="field"><label>Branding (0-10)</label><input id="tBrand" type="number" min="0" max="10" value="${t.branding ?? 0}" /></div>
          <div class="field"><label>Academy Level (0-4)</label><input id="tAcademy" type="number" min="0" max="4" value="${t.academy ?? 0}" /></div>
          <div class="field"><label>Academy Focus</label><select id="tAcademyFocus"></select></div>
        </div>
      </div>

      <div class="subcard">
        <div class="subcard-title">Cohesion &amp; Board Goals</div>
        <div class="form-grid">
          <div class="field"><label>Main Language</label><select id="tMainLang">${langOpts}</select></div>
          <div class="field"><label>Training Cohesion (0-1)</label><input id="tCohTrain" type="number" step="0.05" min="0" max="1" value="${Number(coh.cohesionFromTraining ?? 0.5).toFixed(2)}" /></div>
          <div class="field"><label>Burnout Cohesion (0-1)</label><input id="tCohBurn" type="number" step="0.05" min="0" max="1" value="${Number(coh.cohesionFromBurnout ?? 1).toFixed(2)}" /></div>
          <div class="field"><label>Mentality Cohesion</label><input id="tCohMent" type="number" step="0.05" min="0" max="1" value="${Number(coh.cohesionFromMentality ?? 1).toFixed(2)}" /></div>
          <div class="field"><label>Ranking Goal</label><input id="tRankGoal" type="number" value="${job.rankingGoal ?? 1000}" /></div>
          <div class="field"><label>Grace Period</label><input id="tGrace" type="number" value="${job.gracePeriod ?? 0}" /></div>
        </div>
      </div>
    </div>

    <div class="two-col">
      <div class="subcard">
        <div class="subcard-title">Roster (${data.roster.length})</div>
        ${rosterHtml || '<span class="muted">No players contracted.</span>'}
      </div>
      <div class="subcard">
        <div class="subcard-title">Staff (${data.staff.length})</div>
        ${staffHtml || '<span class="muted">No staff contracted.</span>'}
      </div>
    </div>
  `;

  populateSelect($("tProfStatus"), enumEntries(state.meta.professionalStatus), t.professionalStatus ?? 0);
  populateSelect($("tHiringBias"), enumEntries(state.meta.hiringBias), owner.hiringBias ?? 0);
  populateSelect($("tAcademyFocus"), enumEntries(state.meta.academyFocus), t.academyFocus ?? 0);

  $("teamEditorBody").querySelectorAll(".btn-team-bench").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const pid = Number(btn.dataset.pid);
      const benched = btn.dataset.benched === "1";
      try {
        await api(`/api/player/${pid}/bench`, {
          method: "POST",
          body: JSON.stringify({ benched, autoTactics: true }),
        });
        await refreshSummaryOnly();
        await refreshAllViews();
        toast(`${benched ? "Benched" : "Promoted"} player #${pid} & recalculated tactics`, "ok");
      } catch (err) {
        toast(err.message, "err");
      }
    });
  });
}

async function applyTeamChanges() {
  if (!state.selectedTeamId) return;
  const payload = {
    team: {
      name: $("tName").value.trim(),
      nation: Number($("tNation").value || 1),
      reputation: Math.max(1, Math.min(20, Number($("tRep").value || 1))),
      reputationProgress: Number($("tRepProg").value || 0),
      professionalStatus: Number($("tProfStatus").value || 0),
      financialStrength: Math.max(1, Math.min(20, Number($("tFinStrength").value || 1))),
      coffeeMachine: Number($("tCoffee").value || 0),
      cable: Number($("tCable").value || 0),
      ventilation: Number($("tVent").value || 0),
      recreation: Number($("tRec").value || 0),
      branding: Number($("tBrand").value || 0),
      academy: Number($("tAcademy").value || 0),
      academyFocus: Number($("tAcademyFocus").value || 0),
      owner: {
        name: $("tOwnerName").value.trim(),
        hiringBias: Number($("tHiringBias").value || 0),
      },
      teamFinances: {
        currentBalance: Number($("tBalance").value || 0),
        ownerContribution: Number($("tOwnerContrib").value || 0),
        ownerContributionMultipler: Number($("tOwnerMult").value || 1),
        merchandiseContribution: Number($("tMerchContrib").value || 0),
        prizeMoney: Number($("tPrize").value || 0),
        sponsorBonus: Number($("tSponsor").value || 0),
        buyoutAndSignOnExpenses: Number($("tBuyoutExp").value || 0),
        buyoutIncome: Number($("tBuyoutInc").value || 0),
      },
      teamCohesion: {
        mainLanguage: Number($("tMainLang").value || 13),
        cohesionFromTraining: Number($("tCohTrain").value || 0),
        cohesionFromBurnout: Number($("tCohBurn").value || 1),
        cohesionFromMentality: Number($("tCohMent").value || 1),
      },
      jobSecurity: {
        rankingGoal: Number($("tRankGoal").value || 0),
        gracePeriod: Number($("tGrace").value || 0),
      },
    },
  };

  try {
    const updated = await api(`/api/team/${state.selectedTeamId}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    });
    state.selectedTeamData = updated;
    await refreshSummaryOnly();
    await refreshAllViews();
    toast(`Updated org ${updated.team.name}`, "ok");
  } catch (err) {
    toast(`Failed to update org: ${err.message}`, "err");
  }
}

// =========================================================================
// Bootstrap & Event Wiring
// =========================================================================

function bindEvents() {
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
      btn.classList.add("active");
      $(`tab-${btn.dataset.tab}`).classList.add("active");
      state.activeTab = btn.dataset.tab;
      if (state.activeTab === "stats" && !state.statsData && state.summary?.path) {
        loadStatsOverview();
      } else if (state.activeTab === "showcase" && !state.showcaseData && state.summary?.path) {
        loadBugShowcase();
      } else if (state.activeTab === "realism" && !state.realismData && state.summary?.path) {
        loadStrengthRealism();
      } else if (state.activeTab === "helper" && !state.helperData && state.summary?.path) {
        loadManagerHelper();
      } else if (state.activeTab === "godmode" && !state.godModeData && state.summary?.path) {
        loadGodMode();
      }
    });
  });

  $("btnLoadSelected").addEventListener("click", () => {
    const path = $("savePicker").value;
    if (path) loadSavePath(path);
  });

  $("btnBrowsePath").addEventListener("click", async () => {
    try {
      const dlg = await api("/api/dialog/open-save", { method: "POST", body: "{}" });
      if (dlg.unsupported) {
        $("uploadSaveInput").click();
        return;
      }
      if (!dlg.cancelled && dlg.path) {
        await loadSavePath(dlg.path);
        await refreshSavePicker();
      }
    } catch (err) {
      $("uploadSaveInput").click();
    }
  });

  $("uploadSaveInput").addEventListener("change", async (e) => {
    const file = e.target.files && e.target.files[0];
    e.target.value = "";
    if (!file) return;
    try {
      const text = await file.text();
      state.summary = await api("/api/load-upload", {
        method: "POST",
        body: JSON.stringify({ filename: file.name, content: text }),
      });
      renderStatusBar();
      await refreshAllViews();
      toast(`Loaded uploaded save: ${state.summary.filename}`, "ok");
    } catch (err) {
      toast(`Upload load failed: ${err.message}`, "err");
    }
  });

  $("btnOpenFolder").addEventListener("click", async () => {
    try {
      const res = await api("/api/dialog/open-folder", { method: "POST", body: "{}" });
      toast(`Opened folder: ${res.opened}`, "info");
    } catch (err) {
      toast(`Could not open folder: ${err.message}`, "err");
    }
  });

  $("btnValidate").addEventListener("click", () => runValidate(false));
  $("btnCloseValidateModal").addEventListener("click", () => $("validateModal").classList.remove("open"));
  $("btnCancelValidate").addEventListener("click", () => $("validateModal").classList.remove("open"));
  $("btnRunAutoFix").addEventListener("click", () => runValidate(true));

  $("btnSave").addEventListener("click", async () => {
    try {
      const res = await api("/api/save", { method: "POST", body: JSON.stringify({}) });
      state.summary = res.summary;
      renderStatusBar();
      toast(`Saved to ${res.saved_path} (Backup: ${res.backup_path || "new file"})`, "ok");
    } catch (err) {
      toast(`Save failed: ${err.message}`, "err");
    }
  });

  $("btnSaveAs").addEventListener("click", async () => {
    try {
      const dlg = await api("/api/dialog/save-as", { method: "POST", body: "{}" });
      if (dlg.unsupported) {
        triggerSaveDownload();
        return;
      }
      if (dlg.cancelled || !dlg.path) return;
      const res = await api("/api/save", { method: "POST", body: JSON.stringify({ path: dlg.path }) });
      state.summary = res.summary;
      renderStatusBar();
      await refreshSavePicker();
      toast(`Saved as ${res.saved_path}`, "ok");
    } catch (err) {
      toast(`Save As failed: ${err.message}`, "err");
    }
  });

  $("btnDownloadSave").addEventListener("click", triggerSaveDownload);

  // New Player / New Staff Modals
  $("btnOpenNewPlayer").addEventListener("click", openNewPlayerModal);
  $("btnCloseNewPlayerModal").addEventListener("click", () => $("newPlayerModal").classList.remove("open"));
  $("btnCancelNewPlayer").addEventListener("click", () => $("newPlayerModal").classList.remove("open"));
  $("npTeam").addEventListener("change", onNewPlayerTeamChange);
  $("npRolePreset").addEventListener("change", onNewPlayerPresetChange);
  $("btnCreatePlayerSubmit").addEventListener("click", submitCreatePlayer);

  $("btnOpenNewStaff").addEventListener("click", openNewStaffModal);
  $("btnCloseNewStaffModal").addEventListener("click", () => $("newStaffModal").classList.remove("open"));
  $("btnCancelNewStaff").addEventListener("click", () => $("newStaffModal").classList.remove("open"));
  $("btnCreateStaffSubmit").addEventListener("click", submitCreateStaff);

  // Transfers
  $("txPlayerSearch").addEventListener("input", renderTxPlayerOptions);
  $("txPlayerSelect").addEventListener("change", onTxPlayerChange);
  $("txTeamSearch").addEventListener("input", () => {
    renderTxTeamOptions();
    loadTargetRosterPreview();
  });
  $("txTargetTeam").addEventListener("change", loadTargetRosterPreview);
  $("btnTxRecalcTactics").addEventListener("click", async () => {
    const tid = Number($("txTargetTeam").value || 0);
    if (!tid) return;
    try {
      await api(`/api/team/${tid}/recalculate-tactics`, { method: "POST", body: "{}" });
      await refreshSummaryOnly();
      await loadTargetRosterPreview();
      toast(`Recalculated AI tactics for team #${tid}`, "ok");
    } catch (err) {
      toast(err.message, "err");
    }
  });
  $("btnExecutePlayerTransfer").addEventListener("click", executePlayerTransfer);

  $("txStaffSearch").addEventListener("input", renderTxStaffOptions);
  $("txStaffSelect").addEventListener("change", onTxStaffChange);
  $("btnExecuteStaffTransfer").addEventListener("click", executeStaffTransfer);
  $("btnRefreshTransfers").addEventListener("click", loadTransferHistory);

  // Players filters & paging
  const resetPlayerPage = () => {
    state.playerOffset = 0;
    loadPlayersList();
  };
  $("playerFilterQ").addEventListener("input", resetPlayerPage);
  $("playerFilterTeam").addEventListener("change", resetPlayerPage);
  $("playerFilterNation").addEventListener("change", resetPlayerPage);
  $("playerFilterFree").addEventListener("change", resetPlayerPage);
  $("playersPrev").addEventListener("click", () => {
    state.playerOffset = Math.max(0, state.playerOffset - state.playerLimit);
    loadPlayersList();
  });
  $("playersNext").addEventListener("click", () => {
    if (state.playerOffset + state.playerLimit < state.playerTotal) {
      state.playerOffset += state.playerLimit;
      loadPlayersList();
    }
  });
  $("btnPlayerApply").addEventListener("click", applyPlayerChanges);

  // Staff filters & paging
  const resetStaffPage = () => {
    state.staffOffset = 0;
    loadStaffList();
  };
  $("staffFilterQ").addEventListener("input", resetStaffPage);
  $("staffFilterTeam").addEventListener("change", resetStaffPage);
  $("staffFilterRole").addEventListener("change", resetStaffPage);
  $("staffFilterFree").addEventListener("change", resetStaffPage);
  $("staffPrev").addEventListener("click", () => {
    state.staffOffset = Math.max(0, state.staffOffset - state.staffLimit);
    loadStaffList();
  });
  $("staffNext").addEventListener("click", () => {
    if (state.staffOffset + state.staffLimit < state.staffTotal) {
      state.staffOffset += state.staffLimit;
      loadStaffList();
    }
  });
  $("btnStaffApply").addEventListener("click", applyStaffChanges);

  // Teams
  $("teamFilterQ").addEventListener("input", renderTeamsTable);
  $("btnTeamApply").addEventListener("click", applyTeamChanges);
  $("btnTeamRecalc").addEventListener("click", async () => {
    if (!state.selectedTeamId) return;
    try {
      await api(`/api/team/${state.selectedTeamId}/recalculate-tactics`, { method: "POST", body: "{}" });
      await refreshSummaryOnly();
      await openTeamEditor(state.selectedTeamId);
      toast(`Recalculated AI tactics for team #${state.selectedTeamId}`, "ok");
    } catch (err) {
      toast(err.message, "err");
    }
  });

  // Stats Page Events
  document.querySelectorAll(".subtab-btn[data-subtab]").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".subtab-btn[data-subtab]").forEach((b) => b.classList.remove("active"));
      document.querySelectorAll("#tab-stats .subtab-panel").forEach((p) => p.classList.remove("active"));
      btn.classList.add("active");
      $(`subtab-${btn.dataset.subtab}`).classList.add("active");
    });
  });

  // Bug Showcase Events
  document.querySelectorAll(".subtab-btn[data-bsubtab]").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".subtab-btn[data-bsubtab]").forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".bsubtab-panel").forEach((p) => p.classList.remove("active"));
      btn.classList.add("active");
      $(`bsubtab-${btn.dataset.bsubtab}`).classList.add("active");
    });
  });
  $("btnShowcaseRefresh").addEventListener("click", loadBugShowcase);
  $("btnCopyShowcaseMd").addEventListener("click", copyShowcaseMarkdown);
  $("showcaseFilterQ").addEventListener("input", renderBugShowcase);
  $("scBlowoutFilterMode").addEventListener("change", renderShowcaseBlowoutTable);
  $("scAwardsFilterMode").addEventListener("change", renderShowcaseAwardsTable);
  $("scPolicyFilterMode").addEventListener("change", renderShowcaseTransfers);

  // Strength & Realism Events
  document.querySelectorAll(".subtab-btn[data-rsubtab]").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".subtab-btn[data-rsubtab]").forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".rsubtab-panel").forEach((p) => p.classList.remove("active"));
      btn.classList.add("active");
      $(`rsubtab-${btn.dataset.rsubtab}`).classList.add("active");
    });
  });
  $("btnRealismRefresh").addEventListener("click", loadStrengthRealism);
  $("realismFilterYear").addEventListener("change", loadStrengthRealism);
  $("realismFocusTeam").addEventListener("change", loadStrengthRealism);
  $("realismFilterQ").addEventListener("input", () => state.realismData && renderRealismTab());
  $("diffTeamA").addEventListener("change", () => state.realismData && renderRealismDiff(state.realismData));
  $("diffTeamB").addEventListener("change", () => state.realismData && renderRealismDiff(state.realismData));
  $("btnDiffSwap").addEventListener("click", () => {
    const a = $("diffTeamA").value;
    const b = $("diffTeamB").value;
    if (!a || !b || b === "__TOP10__") return;
    $("diffTeamA").value = b;
    $("diffTeamB").value = a;
    if (state.realismData) renderRealismDiff(state.realismData);
  });
  document.querySelectorAll("th[data-rsort]").forEach((th) => {
    th.addEventListener("click", () => {
      const k = th.dataset.rsort;
      if (state.realismSortKey === k) state.realismSortDir *= -1;
      else {
        state.realismSortKey = k;
        state.realismSortDir = k === "worldRank" || k === "name" ? 1 : -1;
      }
      document.querySelectorAll("th[data-rsort]").forEach((x) => x.classList.remove("sort-active"));
      th.classList.add("sort-active");
      if (state.realismData) renderRealismDiffTable(state.realismData);
    });
  });
  ["labTeam1", "labTeam2", "labMap", "labFormat"].forEach((id) => {
    $(id).addEventListener("change", () => state.realismData && renderRealismMatchup(state.realismData));
  });

  // Manager Helper Events
  document.querySelectorAll(".subtab-btn[data-hsubtab]").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".subtab-btn[data-hsubtab]").forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".hsubtab-panel").forEach((p) => p.classList.remove("active"));
      btn.classList.add("active");
      $(`hsubtab-${btn.dataset.hsubtab}`).classList.add("active");
    });
  });
  $("btnHelperRefresh").addEventListener("click", loadManagerHelper);
  $("helperTeamSelect").addEventListener("change", loadManagerHelper);
  $("finderTargetPlayer").addEventListener("change", loadManagerHelper);
  $("finderRolePreset").addEventListener("change", loadManagerHelper);
  $("helperFilterQ").addEventListener("input", () => state.helperData && renderManagerHelperTab());
  $("finderAvailFilter").addEventListener("change", () => state.helperData && renderHelperFinder(state.helperData));
  $("marketFilterMode").addEventListener("change", () => state.helperData && renderHelperMarket(state.helperData));
  $("wonderkidFilterMode").addEventListener("change", () => state.helperData && renderHelperWonderkids(state.helperData));

  // God Mode Events
  $("btnGodRefresh").addEventListener("click", loadGodMode);
  const godBindings = [
    ["btnGodBoostPreview", "boost_floor_parity", true],
    ["btnGodBoostApply", "boost_floor_parity", false],
    ["btnGodNerfPreview", "nerf_superteam_keep_stars", true],
    ["btnGodNerfApply", "nerf_superteam_keep_stars", false],
    ["btnGodAiPreview", "fix_ai_sabotage", true],
    ["btnGodAiApply", "fix_ai_sabotage", false],
    ["btnGodEconPreview", "rebalance_economy", true],
    ["btnGodEconApply", "rebalance_economy", false],
    ["btnGodWkPreview", "inject_wonderkids", true],
    ["btnGodWkApply", "inject_wonderkids", false],
  ];
  godBindings.forEach(([btnId, act, isDry]) => {
    $(btnId).addEventListener("click", () => runGodModeAction(act, isDry));
  });

  $("btnStatsRefresh").addEventListener("click", loadStatsOverview);
  $("statsFilterYear").addEventListener("change", loadStatsOverview);
  $("statsFilterTeam").addEventListener("change", loadStatsOverview);
  $("statsFilterMinMaps").addEventListener("change", loadStatsOverview);
  $("statsFilterQ").addEventListener("input", renderStatsTables);

  document.querySelectorAll("th[data-sort]").forEach((th) => {
    th.addEventListener("click", () => {
      const k = th.dataset.sort;
      if (state.statsSortKey === k) state.statsSortDir *= -1;
      else {
        state.statsSortKey = k;
        state.statsSortDir = k === "name" || k === "teamName" ? 1 : -1;
      }
      document.querySelectorAll("th[data-sort]").forEach((x) => x.classList.remove("sort-active"));
      th.classList.add("sort-active");
      renderStatsPlayersTable();
    });
  });

  document.querySelectorAll("th[data-tsort]").forEach((th) => {
    th.addEventListener("click", () => {
      const k = th.dataset.tsort;
      if (state.statsTeamSortKey === k) state.statsTeamSortDir *= -1;
      else {
        state.statsTeamSortKey = k;
        state.statsTeamSortDir = k === "worldRank" || k === "name" ? 1 : -1;
      }
      document.querySelectorAll("th[data-tsort]").forEach((x) => x.classList.remove("sort-active"));
      th.classList.add("sort-active");
      renderStatsTeamsTable();
    });
  });

  $("btnClosePsModal").addEventListener("click", () => $("playerStatsModal").classList.remove("open"));
  $("btnCloseTsModal").addEventListener("click", () => $("teamStatsModal").classList.remove("open"));
  $("btnCloseMsModal").addEventListener("click", () => $("matchStatsModal").classList.remove("open"));
  $("btnTop20ClearVote").addEventListener("click", () => {
    state.top20VotePlayerId = null;
    renderStatsTop20Prediction();
  });
  $("btnTop20ApplySaveVote").addEventListener("click", () => {
    const sv = state.statsData?.top20Prediction?.saveVotePlayerId || 0;
    if (sv) {
      state.top20VotePlayerId = sv;
      renderStatsTop20Prediction();
    }
  });
}

// =========================================================================
// Detailed Statistics Hub
// =========================================================================

async function loadStatsOverview() {
  if (!state.summary?.path) return;
  try {
    const params = new URLSearchParams({
      year: $("statsFilterYear").value || "",
      team_id: $("statsFilterTeam").value || "",
      min_maps: $("statsFilterMinMaps").value || "0",
    });
    const data = await api(`/api/stats/overview?${params.toString()}`);
    state.statsData = data;
    const cands = data.top20Prediction?.candidates || [];
    if (state.top20VotePlayerId && !cands.some((c) => c.playerId === state.top20VotePlayerId)) {
      state.top20VotePlayerId = null;
    }

    // Populate available years preserving selection
    const curYear = $("statsFilterYear").value;
    populateSelect(
      $("statsFilterYear"),
      (data.years || []).map((y) => [String(y), String(y)]),
      curYear,
      "All Years"
    );

    renderStatsKpis(data.totals || {});
    renderStatsTables();
  } catch (err) {
    toast(`Stats load error: ${err.message}`, "err");
  }
}

function renderStatsKpis(t) {
  const grid = $("statsKpiGrid");
  const cards = [
    ["Matches Played", (t.matchesPlayed || 0).toLocaleString(), `${(t.mapsPlayed || 0).toLocaleString()} maps`],
    ["Rounds Simulated", (t.roundsPlayed || 0).toLocaleString(), `${t.mapsPlayed ? (t.roundsPlayed / t.mapsPlayed).toFixed(1) : "0"} avg/map`],
    ["Total Kills", (t.kills || 0).toLocaleString(), `${(t.clutches || 0).toLocaleString()} clutches won`],
    ["Aces (5K)", (t.aces || 0).toLocaleString(), `${(t.quads || 0).toLocaleString()} 4Ks / ${(t.triples || 0).toLocaleString()} 3Ks`],
    ["MVP / EVP Medals", `${t.mvps || 0} / ${t.evps || 0}`, `${t.wins || 0} player event wins`],
    ["Titles Awarded", (t.titlesAwarded || 0).toLocaleString(), `$${Number(t.totalPrizePool || 0).toLocaleString()} prizes`],
  ];
  grid.innerHTML = cards
    .map(
      ([lbl, val, sub]) => `
      <div class="kpi-card">
        <div class="kpi-label">${escapeHtml(lbl)}</div>
        <div class="kpi-val">${escapeHtml(val)}</div>
        <div class="kpi-sub">${escapeHtml(sub)}</div>
      </div>`
    )
    .join("");
}

function renderStatsTables() {
  renderStatsPlayersTable();
  renderStatsTeamsTable();
  renderStatsMapsTable();
  renderStatsMatchesTable();
  renderStatsAwardsTables();
  renderStatsTop20Prediction();
}

function renderStatsPlayersTable() {
  const data = state.statsData;
  if (!data) return;
  const q = $("statsFilterQ").value.trim().toLowerCase();
  const key = state.statsSortKey;
  const dir = state.statsSortDir;

  const rows = (data.players || [])
    .filter((p) => !q || p.name.toLowerCase().includes(q) || p.teamName.toLowerCase().includes(q))
    .slice()
    .sort((a, b) => {
      const va = a[key] ?? 0;
      const vb = b[key] ?? 0;
      if (typeof va === "string") return dir * va.localeCompare(String(vb));
      return dir * (va - vb);
    });

  $("statsPlayerCount").textContent = `${rows.length} players`;
  const shown = rows.slice(0, 300);
  const tbody = $("statsPlayersBody");
  tbody.innerHTML = shown
    .map((p, idx) => {
      const rCls = p.rating >= 1.1 ? "stat-good" : p.rating > 0 && p.rating < 0.95 ? "stat-bad" : "";
      const kdCls = p.kd >= 1.1 ? "stat-good" : p.kd < 0.95 ? "stat-bad" : "";
      const diffSign = p.kDiff > 0 ? `+${p.kDiff}` : String(p.kDiff);
      const okod = `${p.openingKills}-${p.openingDeaths}`;
      return `
        <tr data-pid="${p.playerId}">
          <td class="muted">${idx + 1}</td>
          <td><strong>${escapeHtml(p.name)}</strong></td>
          <td>${escapeHtml(p.teamName)}</td>
          <td>${p.age}</td>
          <td>${p.avgSkill}</td>
          <td class="${rCls}">${p.rating.toFixed(2)}</td>
          <td>${p.matches} <span class="muted">(${p.matchesWon}-${p.matchesLost})</span></td>
          <td>${p.mapsPlayed}</td>
          <td>${p.rounds}</td>
          <td>${p.kills}</td>
          <td>${p.assists}</td>
          <td>${p.flashAssists}</td>
          <td>${p.deaths}</td>
          <td class="${kdCls}">${p.kd.toFixed(2)}</td>
          <td class="${p.kDiff > 0 ? "stat-good" : p.kDiff < 0 ? "stat-bad" : ""}">${diffSign}</td>
          <td>${p.adr.toFixed(1)}</td>
          <td>${p.hsPct.toFixed(1)}%</td>
          <td>${okod}</td>
          <td>${p.sniperKills}</td>
          <td>${p.clutchKills}</td>
          <td class="mono">${p.k2}/${p.k3}/${p.k4}/${p.k5}</td>
          <td>${
            p.mvps || p.evps || p.wins
              ? [
                  p.mvps ? `<span class="pill pill-warn">${p.mvps} MVP</span>` : "",
                  p.evps ? `<span class="pill pill-blue">${p.evps} EVP</span>` : "",
                  p.wins ? `<span class="pill pill-ok">${p.wins} Win</span>` : "",
                ]
                  .filter(Boolean)
                  .join(" ")
              : "-"
          }</td>
        </tr>
      `;
    })
    .join("");

  tbody.querySelectorAll("tr").forEach((tr) => {
    tr.addEventListener("click", () => openPlayerStatsModal(Number(tr.dataset.pid)));
  });
}

function renderStatsTeamsTable() {
  const data = state.statsData;
  if (!data) return;
  const q = $("statsFilterQ").value.trim().toLowerCase();
  const key = state.statsTeamSortKey;
  const dir = state.statsTeamSortDir;

  const rows = (data.teams || [])
    .filter((t) => !q || t.name.toLowerCase().includes(q))
    .slice()
    .sort((a, b) => {
      if (key === "worldRank") {
        const ra = a.worldRank || 9999;
        const rb = b.worldRank || 9999;
        return dir * (ra - rb);
      }
      const va = a[key] ?? 0;
      const vb = b[key] ?? 0;
      if (typeof va === "string") return dir * va.localeCompare(String(vb));
      return dir * (va - vb);
    });

  $("statsTeamCount").textContent = `${rows.length} teams`;
  const tbody = $("statsTeamsBody");
  tbody.innerHTML = rows
    .map((t) => {
      const deltaHtml =
        t.rankDelta > 0
          ? `<span class="stat-good">▲${t.rankDelta}</span>`
          : t.rankDelta < 0
          ? `<span class="stat-bad">▼${Math.abs(t.rankDelta)}</span>`
          : "";
      return `
        <tr data-tid="${t.teamId}">
          <td><strong>${t.worldRank ? "#" + t.worldRank : "-"}</strong> ${deltaHtml}</td>
          <td><strong>${escapeHtml(t.name)}</strong></td>
          <td>${t.rankingPoints.toLocaleString()}</td>
          <td>${t.avgSkill}</td>
          <td>${t.avgAge}</td>
          <td>${t.matchesWon}-${t.matchesLost} <span class="muted">(${t.matchWinPct}%)</span></td>
          <td>${t.mapsWon}-${t.mapsLost} <span class="muted">(${t.mapWinPct}%)</span></td>
          <td>${t.pistolWinPct}%</td>
          <td>${t.clutchesWon}</td>
          <td>${t.titles ? `<span class="pill pill-warn">${t.titles}🏆</span>` : "0"} / ${t.top4}</td>
          <td>$${Number(t.prizeWon || 0).toLocaleString()}</td>
          <td>$${Number(t.balance || 0).toLocaleString()}</td>
        </tr>
      `;
    })
    .join("");

  tbody.querySelectorAll("tr").forEach((tr) => {
    tr.addEventListener("click", () => openTeamStatsModal(Number(tr.dataset.tid)));
  });
}

function renderStatsMapsTable() {
  const data = state.statsData;
  if (!data) return;
  $("statsMapsBody").innerHTML = (data.maps || [])
    .map(
      (m) => `
      <tr>
        <td><strong>${escapeHtml(m.name)}</strong></td>
        <td>${m.played}</td>
        <td>${m.rounds.toLocaleString()}</td>
        <td>${m.avgRounds}</td>
        <td>${m.otPct}% <span class="muted">(${m.otMaps})</span></td>
        <td>${m.picks}</td>
        <td>${m.bans}</td>
        <td>${m.kills.toLocaleString()}</td>
        <td>${m.aces}</td>
      </tr>`
    )
    .join("");
}

function renderStatsMatchesTable() {
  const data = state.statsData;
  if (!data) return;
  const q = $("statsFilterQ").value.trim().toLowerCase();
  const rows = (data.recentMatches || []).filter(
    (m) => !q || m.team1Name.toLowerCase().includes(q) || m.team2Name.toLowerCase().includes(q) || m.tournamentName.toLowerCase().includes(q)
  );
  const tbody = $("statsMatchesBody");
  tbody.innerHTML = rows
    .map(
      (m) => `
      <tr data-mid="${m.id}">
        <td>${formatDateObj(m.datetime)}</td>
        <td>${escapeHtml(m.tournamentName)}</td>
        <td class="${m.winnerTeamId === m.team1Id ? "stat-good" : ""}">${escapeHtml(m.team1Name)} ${m.team1RankBefore ? `<span class="muted">(#${m.team1RankBefore})</span>` : ""}</td>
        <td class="mono"><strong>${m.team1Maps} - ${m.team2Maps}</strong></td>
        <td class="${m.winnerTeamId === m.team2Id ? "stat-good" : ""}">${escapeHtml(m.team2Name)} ${m.team2RankBefore ? `<span class="muted">(#${m.team2RankBefore})</span>` : ""}</td>
        <td class="muted" style="font-size:12px;">${escapeHtml(m.scoresSummary)}</td>
      </tr>`
    )
    .join("");

  tbody.querySelectorAll("tr").forEach((tr) => {
    tr.addEventListener("click", () => openMatchStatsModal(Number(tr.dataset.mid)));
  });
}

function renderStatsAwardsTables() {
  const data = state.statsData;
  if (!data) return;
  $("statsHofBody").innerHTML = (data.hallOfFame || [])
    .map(
      (h) => `
      <tr>
        <td>${formatDateObj(h.datetime)}</td>
        <td>${escapeHtml(h.tournamentName)}</td>
        <td><strong>${escapeHtml(h.teamName)}</strong></td>
        <td>$${Number(h.prizeMoney || 0).toLocaleString()}</td>
        <td>${h.points}</td>
      </tr>`
    )
    .join("");

  $("statsAwardsBody").innerHTML = (data.awardsFeed || [])
    .map(
      (a) => {
        const cls = a.type === 0 ? "pill-warn" : a.type === 1 ? "pill-ok" : a.type === 2 ? "pill-blue" : "pill-purple";
        return `
      <tr>
        <td>${a.year}${a.month ? "-" + String(a.month).padStart(2, "0") : ""}</td>
        <td><span class="pill ${cls}">${escapeHtml(a.typeLabel)}</span></td>
        <td><strong>${escapeHtml(a.playerName)}</strong></td>
        <td>${escapeHtml(a.teamName)}</td>
        <td>${escapeHtml(a.tournamentName)}</td>
      </tr>`;
      }
    )
    .join("");
}

function renderStatsTop20Prediction() {
  const pred = state.statsData?.top20Prediction;
  if (!pred) return;

  const tbody = $("statsTop20Body");
  const snubBody = $("statsTop20SnubbedBody");
  const cands = pred.candidates || [];
  const q = $("statsFilterQ").value.trim().toLowerCase();
  const teamFilter = Number($("statsFilterTeam").value || 0);
  const votePid = state.top20VotePlayerId;
  const saveVotePid = pred.saveVotePlayerId || 0;

  // Compute simulated scores & global projected ranks
  const ranked = cands
    .map((c) => {
      const isVoted = votePid !== null && c.playerId === votePid;
      const finalScore = isVoted ? c.votedScore : c.baseScore;
      return { ...c, isVoted, finalScore };
    })
    .sort((a, b) => (b.finalScore - a.finalScore) || (b.t10Rating - a.t10Rating) || (a.playerId - b.playerId));

  ranked.forEach((c, idx) => {
    c.projRank = idx + 1;
  });

  const votedPlayer = votePid ? ranked.find((c) => c.playerId === votePid) : null;
  const saveVotedPlayer = saveVotePid ? cands.find((c) => c.playerId === saveVotePid) : null;
  $("top20Title").textContent = `HLTV / CSTV Top 20 Prediction — Season ${pred.year || "?"}`;

  const statusParts = [];
  if (pred.finalized) statusParts.push("Dec 30 Top 20 finalized");
  else if (pred.hasDec23Snapshot) statusParts.push("Dec 23 CSTV voting window open");
  else statusParts.push("Live pre-Dec 23 projection");
  statusParts.push(`${pred.eligibleCount || 0} eligible players`);
  if (saveVotedPlayer) statusParts.push(`Save vote: ${saveVotedPlayer.name}`);

  $("top20FormulaNote").textContent =
    `Game formula: AvgRating_vsTop10 × 1.05^MVP × 1.01^EVP × min(Matches_vsTop10 / 50, 1), then × 1.10 for CSTV vote. ${statusParts.join(" • ")}.`;

  const pill = $("top20StatusPill");
  if (votedPlayer) {
    const dRank = votedPlayer.baseRank - votedPlayer.projRank;
    const shiftTxt = dRank > 0 ? `+${dRank} ▲` : dRank < 0 ? `${dRank} ▼` : "unchanged";
    pill.className = "pill pill-ok";
    pill.textContent = `Simulated Vote: ${votedPlayer.name} (#${votedPlayer.baseRank} -> #${votedPlayer.projRank}, ${shiftTxt})`;
  } else {
    pill.className = "pill pill-blue";
    pill.textContent = "Base Projection (Click Vote on any player)";
  }

  const applyBtn = $("btnTop20ApplySaveVote");
  if (saveVotedPlayer) {
    applyBtn.style.display = "";
    applyBtn.textContent = `Use Save's Vote (${saveVotedPlayer.name})`;
  } else {
    applyBtn.style.display = "none";
  }
  $("btnTop20ClearVote").style.display = votedPlayer ? "" : "none";

  // Show Top 20 + up to 10 bubble candidates (or all matching if user typed search/team filter)
  const hasFilter = Boolean(q || teamFilter);
  const visible = ranked.filter((c) => {
    if (!hasFilter) return c.projRank <= 30 || c.isVoted;
    if (teamFilter && c.teamId !== teamFilter) return false;
    if (q && !c.name.toLowerCase().includes(q) && !c.teamName.toLowerCase().includes(q)) return false;
    return true;
  });

  if (!visible.length) {
    tbody.innerHTML = `<tr><td colspan="13" class="muted">No eligible players (requires 1+ MVP/EVP and 1+ match vs Top 10 in ${pred.year}).</td></tr>`;
  } else {
    const htmlRows = [];
    let insertedCut = false;
    for (const c of visible) {
      if (!hasFilter && !insertedCut && c.projRank > 20) {
        insertedCut = true;
        htmlRows.push(`<tr class="row-cutoff"><td colspan="13">— TOP 20 CUTOFF (Players below #20 miss out unless a +10% vote lifts them in) —</td></tr>`);
      }

      let shiftHtml = `<span class="delta-flat">—</span>`;
      if (votedPlayer) {
        const diff = c.baseRank - c.projRank;
        if (c.baseRank > 20 && c.projRank <= 20) {
          shiftHtml = `<span class="delta-up">IN TOP 20 (+${diff} ▲)</span>`;
        } else if (c.baseRank <= 20 && c.projRank > 20) {
          shiftHtml = `<span class="delta-down">OUT (${diff} ▼)</span>`;
        } else if (diff > 0) {
          shiftHtml = `<span class="delta-up">+${diff} ▲</span>`;
        } else if (diff < 0) {
          shiftHtml = `<span class="delta-down">${diff} ▼</span>`;
        }
      }

      const sampleWarn = c.t10Matches < 50;
      const sampleBadge = sampleWarn
        ? `<span class="tag-pill">${c.t10Matches} / 50 (${c.sampleWeight.toFixed(2)}x)</span>`
        : `<span class="muted">${c.t10Matches} (1.00x)</span>`;

      let ballotHtml = `<span class="tag-pill warn">Bubble (#${c.baseRank})</span>`;
      if (c.cstvBallotRank) {
        ballotHtml = `<span class="tag-pill info">CSTV Ballot #${c.cstvBallotRank}</span>`;
      } else if (c.inGameTop20) {
        ballotHtml = `<span class="tag-pill warn">Top 20 (Off Ballot)</span>`;
      }

      const actualHtml = c.actualTop20 > 0 ? ` <span class="pill pill-purple">Actual #${c.actualTop20}</span>` : "";
      const saveVoteTag = c.saveVoted ? ` <span class="pill pill-blue">Save Vote</span>` : "";
      const rowCls = [c.isVoted ? "row-voted" : "", c.projRank > 20 ? "row-bubble" : ""].filter(Boolean).join(" ");
      const voteBtnCls = c.isVoted ? "btn btn-sm btn-voted" : "btn btn-sm btn-ghost";
      const voteBtnTxt = c.isVoted ? "✓ Voted (+10%)" : "Vote (+10%)";

      htmlRows.push(`
        <tr class="${rowCls}">
          <td><strong>#${c.projRank}</strong>${actualHtml}</td>
          <td>${shiftHtml}</td>
          <td class="muted">#${c.baseRank}</td>
          <td><span class="link-cell top20-player-link" data-pid="${c.playerId}">${escapeHtml(c.name)}</span>${saveVoteTag}</td>
          <td>${escapeHtml(c.teamName)}</td>
          <td class="${c.t10Rating >= 1.15 ? "stat-good" : ""}"><strong>${c.t10Rating.toFixed(3)}</strong></td>
          <td class="muted">${c.overallRating.toFixed(3)} (${c.overallMatches}m)</td>
          <td>${sampleBadge}</td>
          <td>${c.mvps} MVP / ${c.evps} EVP <span class="muted">(${c.awardMult.toFixed(3)}x)</span></td>
          <td class="muted">${c.baseScore.toFixed(3)}</td>
          <td><strong>${c.finalScore.toFixed(3)}</strong></td>
          <td>${ballotHtml}</td>
          <td><button class="${voteBtnCls} top20-vote-btn" data-pid="${c.playerId}">${voteBtnTxt}</button></td>
        </tr>`);
    }
    tbody.innerHTML = htmlRows.join("");

    tbody.querySelectorAll(".top20-vote-btn").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const pid = Number(btn.dataset.pid);
        state.top20VotePlayerId = state.top20VotePlayerId === pid ? null : pid;
        renderStatsTop20Prediction();
      });
    });
    tbody.querySelectorAll(".top20-player-link").forEach((el) => {
      el.addEventListener("click", () => openPlayerStatsModal(Number(el.dataset.pid)));
    });
  }

  // Render high-rated snubbed / ineligible watchlist
  const snubbed = (pred.snubbed || []).filter((s) => {
    if (teamFilter && s.teamId !== teamFilter) return false;
    if (q && !s.name.toLowerCase().includes(q) && !s.teamName.toLowerCase().includes(q)) return false;
    return true;
  });
  $("top20SnubbedCount").textContent = `${snubbed.length} players`;
  snubBody.innerHTML = snubbed.length
    ? snubbed
        .map(
          (s) => `
      <tr>
        <td><span class="link-cell top20-snub-link" data-pid="${s.playerId}">${escapeHtml(s.name)}</span></td>
        <td>${escapeHtml(s.teamName)}</td>
        <td class="${s.overallRating >= 1.15 ? "stat-good" : ""}"><strong>${s.overallRating.toFixed(3)}</strong></td>
        <td>${s.overallMatches}</td>
        <td>${s.t10Matches > 0 ? s.t10Rating.toFixed(3) : "<span class='muted'>—</span>"}</td>
        <td>${s.t10Matches}</td>
        <td>${s.mvps} MVP / ${s.evps} EVP</td>
        <td><span class="tag-pill warn">${escapeHtml(s.reason)}</span></td>
      </tr>`
        )
        .join("")
    : `<tr><td colspan="8" class="muted">No notable high-rated snubs found for this filter.</td></tr>`;

  snubBody.querySelectorAll(".top20-snub-link").forEach((el) => {
    el.addEventListener("click", () => openPlayerStatsModal(Number(el.dataset.pid)));
  });
}

async function openPlayerStatsModal(playerId) {
  try {
    const d = await api(`/api/stats/player/${playerId}`);
    const p = d.player;
    const c = d.career;
    $("psModalTitle").textContent = `${p.name} — Detailed Career Statistics`;

    const kpis = [
      ["Rating", c.rating.toFixed(2), `${c.matches} matches (${c.matchesWon}W-${c.matchesLost}L)`],
      ["K / D", c.kd.toFixed(2), `${c.kills}K / ${c.deaths}D / ${c.assists}A`],
      ["ADR", c.adr.toFixed(1), `${c.rounds} rounds across ${c.maps} maps`],
      ["HS%", `${c.hsPct}%`, `${c.flashAssists} flash assists`],
      ["Opening K-D", `${c.openingKills}-${c.openingDeaths}`, `Diff ${c.openingKills - c.openingDeaths >= 0 ? "+" : ""}${c.openingKills - c.openingDeaths}`],
      ["AWP / Clutches", `${c.sniperKills} / ${c.clutchKills}`, `${c.k2}x2K ${c.k3}x3K ${c.k4}x4K ${c.k5}x5K`],
    ];

    const mapRows = (d.mapBreakdown || [])
      .map(
        (m) => `
        <tr>
          <td><strong>${escapeHtml(m.mapName)}</strong></td>
          <td>${m.maps} (${m.wins}W-${m.maps - m.wins}L, ${m.winPct}%)</td>
          <td>${m.kd.toFixed(2)}</td>
          <td>${m.adr.toFixed(1)}</td>
          <td>${m.hsPct}%</td>
          <td>${m.sniperKills}</td>
          <td>${m.clutchKills}</td>
          <td>${m.aces}</td>
        </tr>`
      )
      .join("");

    const skillRows = (d.skillProgression || [])
      .map((s) => {
        const cls = s.delta > 0.05 ? "stat-good" : s.delta < -0.05 ? "stat-bad" : "muted";
        const sign = s.delta > 0 ? `+${s.delta.toFixed(2)}` : s.delta.toFixed(2);
        return `
          <tr>
            <td>${escapeHtml(s.label)}</td>
            <td class="muted">${s.group}</td>
            <td>${s.start.toFixed(2)}</td>
            <td><strong>${s.current.toFixed(2)}</strong></td>
            <td class="${cls}">${sign}</td>
          </tr>`;
      })
      .join("");

    const eventRows = (d.eventBreakdown || [])
      .map(
        (ev) => `
        <tr>
          <td>${ev.year}-${String(ev.month).padStart(2, "0")}</td>
          <td>${escapeHtml(ev.teamName)}</td>
          <td>${escapeHtml(ev.tournamentName)}</td>
          <td>${ev.matchesWon}-${ev.matchesLost}</td>
          <td><strong>${ev.rating.toFixed(2)}</strong></td>
          <td>${ev.adr.toFixed(1)}</td>
          <td>${ev.kills}/${ev.deaths}</td>
        </tr>`
      )
      .join("");

    const recentRows = (d.recentMaps || [])
      .map(
        (rm) => `
        <tr class="ps-match-row" data-mid="${rm.matchId}">
          <td>${formatDateObj(rm.datetime)}</td>
          <td>${escapeHtml(rm.opponentName)}</td>
          <td>${escapeHtml(rm.mapName)}</td>
          <td class="${rm.won ? "stat-good" : "stat-bad"}">${rm.score}</td>
          <td>${rm.kills}-${rm.assists}-${rm.deaths}</td>
          <td>${rm.adr}</td>
          <td>${rm.hsPct}%</td>
          <td class="mono">${rm.k2}/${rm.k3}/${rm.k4}/${rm.k5}</td>
        </tr>`
      )
      .join("");

    const awardsHtml = (d.awards || []).length
      ? d.awards
          .map((a) => {
            const cls = a.type === 0 ? "pill-warn" : a.type === 1 ? "pill-ok" : a.type === 2 ? "pill-blue" : "pill-purple";
            return `<span class="pill ${cls}" style="margin:2px;">${escapeHtml(a.typeLabel)} &bull; ${escapeHtml(a.tournamentName)} (${a.year})</span>`;
          })
          .join("")
      : `<span class="muted">No individual awards recorded yet.</span>`;

    const victimsHtml = (d.topVictims || [])
      .map((v) => `<span class="pill" style="margin:2px;">${escapeHtml(v.name)}: <strong>${v.kills}</strong></span>`)
      .join("");

    $("psModalBody").innerHTML = `
      <div style="margin-bottom:10px;">
        <strong>${escapeHtml(p.teamName)}</strong> &bull; Age ${p.age} &bull; ${escapeHtml(p.nationName)} &bull; Avg Skill <strong>${p.avgSkill}</strong> &bull; Rep ${p.reputation}
      </div>
      <div class="kpi-grid">
        ${kpis.map(([l, v, s]) => `<div class="kpi-card"><div class="kpi-label">${l}</div><div class="kpi-val">${v}</div><div class="kpi-sub">${s}</div></div>`).join("")}
      </div>
      <div class="subcard"><div class="subcard-title">Awards Cabinet</div>${awardsHtml}</div>
      <div class="two-col">
        <div class="subcard">
          <div class="subcard-title">Performance by Map</div>
          <div class="table-wrap" style="max-height:260px;">
            <table><thead><tr><th>Map</th><th>Record</th><th>K/D</th><th>ADR</th><th>HS%</th><th>AWP</th><th>Clutch</th><th>5K</th></tr></thead><tbody>${mapRows}</tbody></table>
          </div>
        </div>
        <div class="subcard">
          <div class="subcard-title">Skill Progression (Earliest &rarr; Current)</div>
          <div class="table-wrap" style="max-height:260px;">
            <table><thead><tr><th>Skill</th><th>Group</th><th>Start</th><th>Now</th><th>Delta</th></tr></thead><tbody>${skillRows}</tbody></table>
          </div>
        </div>
      </div>
      <div class="subcard"><div class="subcard-title">Most Eliminated Opponents (All Maps)</div>${victimsHtml || '<span class="muted">None recorded</span>'}</div>
      <div class="two-col">
        <div class="subcard">
          <div class="subcard-title">Tournament History</div>
          <div class="table-wrap" style="max-height:260px;">
            <table><thead><tr><th>Date</th><th>Team</th><th>Event</th><th>W-L</th><th>Rating</th><th>ADR</th><th>K/D</th></tr></thead><tbody>${eventRows}</tbody></table>
          </div>
        </div>
        <div class="subcard">
          <div class="subcard-title">Recent Maps (Click for Match Scoreboard)</div>
          <div class="table-wrap" style="max-height:260px;">
            <table><thead><tr><th>Date</th><th>vs</th><th>Map</th><th>Score</th><th>K-A-D</th><th>ADR</th><th>HS%</th><th>MK</th></tr></thead><tbody>${recentRows}</tbody></table>
          </div>
        </div>
      </div>
    `;

    $("psModalBody").querySelectorAll(".ps-match-row").forEach((tr) => {
      tr.addEventListener("click", () => openMatchStatsModal(Number(tr.dataset.mid)));
    });
    $("playerStatsModal").classList.add("open");
  } catch (err) {
    toast(`Could not load player stats: ${err.message}`, "err");
  }
}

function buildRankHistorySvg(history) {
  const pts = (history || []).filter((r) => r > 0);
  if (pts.length < 2) return `<span class="muted">Not enough ranking snapshots for chart.</span>`;
  const w = 480;
  const h = 110;
  const maxR = Math.max(...pts, 10);
  const minR = Math.min(...pts, 1);
  const span = Math.max(maxR - minR, 1);
  const coords = pts.map((val, idx) => {
    const x = Math.round((idx / (pts.length - 1)) * (w - 20) + 10);
    const y = Math.round(((val - minR) / span) * (h - 24) + 12);
    return `${x},${y}`;
  });
  return `
    <svg viewBox="0 0 ${w} ${h}" style="width:100%;max-width:520px;height:110px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;">
      <polyline fill="none" stroke="#38bdf8" stroke-width="2.5" points="${coords.join(" ")}" />
      <text x="12" y="16" fill="#8ea0ba" font-size="11">Best #${minR}</text>
      <text x="12" y="${h - 6}" fill="#8ea0ba" font-size="11">Worst #${maxR} &bull; Current #${pts[pts.length - 1]}</text>
    </svg>
  `;
}

async function openTeamStatsModal(teamId) {
  try {
    const d = await api(`/api/stats/team/${teamId}`);
    const t = d.team;
    $("tsModalTitle").textContent = `${t.name} — Team Analytics`;

    const mapRows = (d.mapPool || [])
      .map(
        (m) => `
        <tr>
          <td><strong>${escapeHtml(m.mapName)}</strong></td>
          <td>${m.played}</td>
          <td>${m.won}-${m.lost}</td>
          <td>
            <span class="stat-bar-bg"><span class="stat-bar-fill" style="width:${m.winPct}%;"></span></span>
            <strong>${m.winPct}%</strong>
          </td>
          <td>${m.picked} / ${m.banned}</td>
        </tr>`
      )
      .join("");

    const tournRows = (d.tournaments || [])
      .map(
        (tr) => `
        <tr>
          <td>${formatDateObj(tr.datetime)}</td>
          <td>${escapeHtml(tr.tournamentName)}</td>
          <td><strong>#${tr.placement}</strong></td>
          <td>$${Number(tr.prizeMoney || 0).toLocaleString()}</td>
          <td>${tr.points}</td>
        </tr>`
      )
      .join("");

    const matchRows = (d.recentMatches || [])
      .map(
        (m) => `
        <tr class="ts-match-row" data-mid="${m.id}">
          <td>${formatDateObj(m.datetime)}</td>
          <td>${escapeHtml(m.tournamentName)}</td>
          <td>vs <strong>${escapeHtml(m.opponentName)}</strong></td>
          <td class="${m.won ? "stat-good" : "stat-bad"}">${m.won ? "W" : "L"} ${m.seriesScore}</td>
          <td class="muted">${escapeHtml(m.mapScores)}</td>
        </tr>`
      )
      .join("");

    $("tsModalBody").innerHTML = `
      <div class="kpi-grid">
        <div class="kpi-card"><div class="kpi-label">World Rank</div><div class="kpi-val">${t.worldRank ? "#" + t.worldRank : "-"}</div><div class="kpi-sub">${t.rankingPoints.toLocaleString()} pts</div></div>
        <div class="kpi-card"><div class="kpi-label">Match Record</div><div class="kpi-val">${t.matchesWon}-${t.matchesLost}</div><div class="kpi-sub">Maps ${t.mapsWon}-${t.mapsLost}</div></div>
        <div class="kpi-card"><div class="kpi-label">Pistol Win%</div><div class="kpi-val">${t.pistolWinPct}%</div><div class="kpi-sub">${t.clutchesWon} clutches won</div></div>
        <div class="kpi-card"><div class="kpi-label">Prize Money</div><div class="kpi-val">$${Number(t.prizeWon || 0).toLocaleString()}</div><div class="kpi-sub">${t.saves} saves / ${t.fullbuys} fullbuys</div></div>
      </div>
      <div class="subcard"><div class="subcard-title">World Ranking Trajectory</div>${buildRankHistorySvg(t.rankingHistory)}</div>
      <div class="two-col">
        <div class="subcard">
          <div class="subcard-title">Map Pool Breakdown</div>
          <div class="table-wrap" style="max-height:280px;">
            <table><thead><tr><th>Map</th><th>Played</th><th>W-L</th><th>Win %</th><th>Pick / Ban</th></tr></thead><tbody>${mapRows}</tbody></table>
          </div>
        </div>
        <div class="subcard">
          <div class="subcard-title">Tournament Placements</div>
          <div class="table-wrap" style="max-height:280px;">
            <table><thead><tr><th>Date</th><th>Event</th><th>Place</th><th>Prize</th><th>Pts</th></tr></thead><tbody>${tournRows || '<tr><td colspan="5" class="muted">No placements recorded.</td></tr>'}</tbody></table>
          </div>
        </div>
      </div>
      <div class="subcard">
        <div class="subcard-title">Recent Match History (Click any match for scoreboard)</div>
        <div class="table-wrap" style="max-height:280px;">
          <table><thead><tr><th>Date</th><th>Event</th><th>Opponent</th><th>Result</th><th>Maps</th></tr></thead><tbody>${matchRows}</tbody></table>
        </div>
      </div>
    `;

    $("tsModalBody").querySelectorAll(".ts-match-row").forEach((tr) => {
      tr.addEventListener("click", () => openMatchStatsModal(Number(tr.dataset.mid)));
    });
    $("teamStatsModal").classList.add("open");
  } catch (err) {
    toast(`Could not load team stats: ${err.message}`, "err");
  }
}

async function openMatchStatsModal(matchId) {
  try {
    const m = await api(`/api/stats/match/${matchId}`);
    $("msModalTitle").textContent = `${m.team1Name} ${m.team1Maps} - ${m.team2Maps} ${m.team2Name} (${m.tournamentName})`;

    const vetoHtml = (m.veto || [])
      .map((v) => `<span class="pill ${v.picked ? "pill-ok" : "pill-bad"}">${v.order}. ${v.picked ? "Pick" : "Ban"}: ${escapeHtml(v.mapName)} (${escapeHtml(v.by)})</span>`)
      .join("");

    const renderTeamBox = (teamName, players) => `
      <div style="margin-bottom:10px;">
        <strong>${escapeHtml(teamName)}</strong>
        <div class="table-wrap" style="margin-top:4px;">
          <table>
            <thead><tr><th>Player</th><th>K</th><th>A</th><th>FA</th><th>D</th><th>K/D</th><th>ADR</th><th>HS%</th><th>OK-OD</th><th>AWP</th><th>Clutch</th><th>2K/3K/4K/5K</th></tr></thead>
            <tbody>
              ${players
                .map(
                  (p) => `
                <tr class="ms-player-row" data-pid="${p.playerId}">
                  <td><strong>${escapeHtml(p.name)}</strong></td>
                  <td>${p.kills}</td>
                  <td>${p.assists}</td>
                  <td>${p.flashAssists}</td>
                  <td>${p.deaths}</td>
                  <td class="${p.kd >= 1.1 ? "stat-good" : p.kd < 0.9 ? "stat-bad" : ""}">${p.kd.toFixed(2)}</td>
                  <td>${p.adr.toFixed(1)}</td>
                  <td>${p.hsPct}%</td>
                  <td>${p.openingKills}-${p.openingDeaths}</td>
                  <td>${p.sniperKills}</td>
                  <td>${p.clutchKills}</td>
                  <td class="mono">${p.k2}/${p.k3}/${p.k4}/${p.k5}</td>
                </tr>`
                )
                .join("")}
            </tbody>
          </table>
        </div>
      </div>
    `;

    const mapsHtml = (m.maps || [])
      .map(
        (mp) => `
        <div class="subcard">
          <div class="subcard-title">${escapeHtml(mp.mapName)} &mdash; ${escapeHtml(m.team1Name)} ${mp.team1Score} : ${mp.team2Score} ${escapeHtml(m.team2Name)} (${mp.rounds} rounds)</div>
          ${renderTeamBox(m.team1Name, mp.team1Players)}
          ${renderTeamBox(m.team2Name, mp.team2Players)}
        </div>`
      )
      .join("");

    $("msModalBody").innerHTML = `
      <div style="margin-bottom:10px;">
        <strong>${formatDateObj(m.datetime)}</strong> &bull; ${escapeHtml(m.tournamentName)} &bull;
        Ranks: ${escapeHtml(m.team1Name)} #${m.team1RankBefore || "-"} (${m.team1PointsDelta >= 0 ? "+" : ""}${m.team1PointsDelta} pts) vs
        ${escapeHtml(m.team2Name)} #${m.team2RankBefore || "-"} (${m.team2PointsDelta >= 0 ? "+" : ""}${m.team2PointsDelta} pts)
      </div>
      <div class="veto-row">${vetoHtml}</div>
      ${mapsHtml}
    `;

    $("msModalBody").querySelectorAll(".ms-player-row").forEach((tr) => {
      tr.addEventListener("click", () => {
        $("matchStatsModal").classList.remove("open");
        openPlayerStatsModal(Number(tr.dataset.pid));
      });
    });
    $("matchStatsModal").classList.add("open");
  } catch (err) {
    toast(`Could not load match scoreboard: ${err.message}`, "err");
  }
}

function triggerSaveDownload() {
  if (!state.summary?.path) return toast("Load a save file first.", "err");
  const a = document.createElement("a");
  a.href = `/api/download?t=${Date.now()}`;
  a.download = state.summary.filename || "cs_manager_save.json";
  document.body.appendChild(a);
  a.click();
  a.remove();
  toast(`Downloading ${a.download}...`, "ok");
}

// =========================================================================
// Create New Player / Staff Modals
// =========================================================================

function openNewPlayerModal() {
  if (!state.summary?.path) return toast("Load a save file first.", "err");
  $("npName").value = "";
  $("npAge").value = "18";
  $("npRep").value = "12";
  $("npBaseSkill").value = "14";
  $("npBasePot").value = "18";
  $("npSalary").value = "250000";
  $("npEndDate").value = "2028-12-31T00:00:00";
  $("npJoinBenched").checked = false;
  $("npRolePreset").value = "balanced";
  $("npDesireIgl").value = "6";
  $("npDesireAwp").value = "6";

  populateSelect($("npNation"), dictEntries(state.meta.nations), "1");
  populateSelect($("npMentality"), enumEntries(state.meta.playerMentalities), "1");
  populateSelect($("npLang"), dictEntries(state.meta.languages), "13");
  const teamOpts = [["0", "Free Agent (No Team)"], ...state.teams.map((t) => [t.id, `${t.name}${t.isUserTeam ? " ★" : ""}`])];
  populateSelect($("npTeam"), teamOpts, "0");
  populateSelect($("npStatus"), enumEntries(state.meta.playerStatus), "1");
  populateSelect($("npIgl"), enumEntries(state.meta.roleStatus), "2");
  populateSelect($("npSniper"), enumEntries(state.meta.roleStatus), "2");
  onNewPlayerTeamChange();
  $("newPlayerModal").classList.add("open");
}

function onNewPlayerPresetChange() {
  const preset = $("npRolePreset").value;
  if (preset === "awper") {
    $("npDesireAwp").value = "18";
    $("npDesireIgl").value = "4";
    $("npSniper").value = "0";
    $("npIgl").value = "2";
  } else if (preset === "igl") {
    $("npDesireIgl").value = "18";
    $("npDesireAwp").value = "4";
    $("npIgl").value = "0";
    $("npSniper").value = "2";
  } else {
    $("npDesireIgl").value = "6";
    $("npDesireAwp").value = "6";
    $("npIgl").value = "2";
    $("npSniper").value = "2";
  }
}

async function onNewPlayerTeamChange() {
  const tid = Number($("npTeam").value || 0);
  const benchSel = $("npBenchStarter");
  benchSel.innerHTML = `<option value="0">(None — keep all starters active)</option>`;
  if (!tid) return;
  try {
    const data = await api(`/api/team/${tid}`);
    for (const r of data.roster.filter((x) => !x.benched)) {
      const roles = getRosterRoleBadges(r, data.team).map((b) => b.label).join(", ");
      const opt = document.createElement("option");
      opt.value = String(r.playerId);
      opt.textContent = `Bench ${r.name} (${roles ? roles + ", " : ""}Avg ${r.avgSkill})`;
      benchSel.appendChild(opt);
    }
  } catch {
    // ignore
  }
}

async function submitCreatePlayer() {
  const name = $("npName").value.trim();
  if (!name) return toast("Enter a player alias / name.", "err");

  const preset = $("npRolePreset").value;
  const roleComforts = { 0: 6, 1: 6, 2: 6, 3: 6, 4: 6, 5: 6, 6: 6, 7: 6, 8: 6 };
  if (preset === "star_rifler") {
    Object.assign(roleComforts, { 0: 10, 4: 9, 6: 9, 7: 8 });
  } else if (preset === "awper") {
    Object.assign(roleComforts, { 2: 8, 3: 9, 6: 9, 7: 10 });
  } else if (preset === "igl") {
    Object.assign(roleComforts, { 3: 10, 2: 9, 5: 8, 6: 9 });
  } else if (preset === "lurker") {
    Object.assign(roleComforts, { 1: 10, 2: 9, 5: 10, 8: 9 });
  } else if (preset === "support") {
    Object.assign(roleComforts, { 2: 8, 3: 8, 5: 9, 6: 9 });
  }

  const baseSkill = Number($("npBaseSkill").value || 14);
  const skills = {};
  for (const sk of state.meta.playerSkills) skills[sk.key] = baseSkill;
  if (preset === "awper") {
    skills.snipers = Math.min(20, baseSkill + 2);
    skills.flicks = Math.min(20, baseSkill + 1.5);
  } else if (preset === "igl") {
    skills.leadership = Math.min(20, baseSkill + 2.5);
    skills.decisions = Math.min(20, baseSkill + 1.5);
  } else if (preset === "star_rifler") {
    skills.rifles = Math.min(20, baseSkill + 2);
    skills.crosshairPlacement = Math.min(20, baseSkill + 1.5);
  }

  const targetTeamId = Number($("npTeam").value || 0);
  const payload = {
    player: {
      name,
      age: Number($("npAge").value || 18),
      nation: Number($("npNation").value || 1),
      reputation: Number($("npRep").value || 12),
      preferredMentality: Number($("npMentality").value || 1),
      baseSkill,
      basePotential: Number($("npBasePot").value || 18),
      skills,
      roleComforts,
      languagesSpoken: [
        { languageId: Number($("npLang").value || 13), languageSkill: 20, limit: 20, progress: 0.0 },
      ],
      personality: {
        desireToIgl: Number($("npDesireIgl").value || 6),
        desireToAwp: Number($("npDesireAwp").value || 6),
      },
    },
    contract: targetTeamId
      ? {
          teamId: targetTeamId,
          benchPlayerId: Number($("npBenchStarter").value || 0),
          benched: $("npJoinBenched").checked,
          salaryYear: Number($("npSalary").value || 250000),
          endDate: isoToDateObj($("npEndDate").value),
          status: Number($("npStatus").value || 1),
          igl: Number($("npIgl").value || 2),
          sniper: Number($("npSniper").value || 2),
        }
      : null,
  };

  try {
    const created = await api("/api/players", { method: "POST", body: JSON.stringify(payload) });
    $("newPlayerModal").classList.remove("open");
    state.selectedPlayerId = created.player.id;
    await refreshSummaryOnly();
    await refreshAllViews();
    toast(`Created player ${created.player.name} (#${created.player.id})`, "ok");
  } catch (err) {
    toast(`Create player failed: ${err.message}`, "err");
  }
}

function openNewStaffModal() {
  if (!state.summary?.path) return toast("Load a save file first.", "err");
  $("nsName").value = "";
  $("nsAge").value = "32";
  $("nsRep").value = "14";
  $("nsBaseSkill").value = "15";
  $("nsBasePot").value = "18";
  $("nsSalary").value = "180000";
  $("nsEndDate").value = "2028-12-31T00:00:00";
  $("nsReplaceExisting").checked = true;

  populateSelect($("nsNation"), dictEntries(state.meta.nations), "1");
  populateSelect($("nsMentality"), enumEntries(state.meta.staffMentalities), "1");
  populateSelect($("nsLang"), dictEntries(state.meta.languages), "13");
  const teamOpts = [["0", "Free Agent (No Team)"], ...state.teams.map((t) => [t.id, `${t.name}${t.isUserTeam ? " ★" : ""}`])];
  populateSelect($("nsTeam"), teamOpts, "0");
  populateSelect($("nsRole"), enumEntries(state.meta.staffRoles), "0");
  $("newStaffModal").classList.add("open");
}

async function submitCreateStaff() {
  const name = $("nsName").value.trim();
  if (!name) return toast("Enter a staff name / alias.", "err");

  const targetTeamId = Number($("nsTeam").value || 0);
  const payload = {
    staff: {
      name,
      age: Number($("nsAge").value || 32),
      nation: Number($("nsNation").value || 1),
      reputation: Number($("nsRep").value || 14),
      preferredMentality: Number($("nsMentality").value || 1),
      baseSkill: Number($("nsBaseSkill").value || 15),
      basePotential: Number($("nsBasePot").value || 18),
      languagesSpoken: [
        { languageId: Number($("nsLang").value || 13), languageSkill: 20, limit: 20, progress: 0.0 },
      ],
    },
    contract: targetTeamId
      ? {
          teamId: targetTeamId,
          role: Number($("nsRole").value || 0),
          salaryYear: Number($("nsSalary").value || 180000),
          endDate: isoToDateObj($("nsEndDate").value),
          replaceExisting: $("nsReplaceExisting").checked,
        }
      : { role: Number($("nsRole").value || 0) },
  };

  try {
    const created = await api("/api/staff", { method: "POST", body: JSON.stringify(payload) });
    $("newStaffModal").classList.remove("open");
    state.selectedStaffId = created.staff.id;
    await refreshSummaryOnly();
    await refreshAllViews();
    toast(`Created staff ${created.staff.name} (#${created.staff.id})`, "ok");
  } catch (err) {
    toast(`Create staff failed: ${err.message}`, "err");
  }
}

// =========================================================================
// Bug Showcase & Save Anomaly Audit
// =========================================================================

async function loadBugShowcase() {
  if (!state.summary?.path) return;
  try {
    const data = await api("/api/bug-showcase");
    state.showcaseData = data;
    renderBugShowcase();
  } catch (err) {
    toast(`Bug Showcase error: ${err.message}`, "err");
  }
}

function renderBugShowcase() {
  const data = state.showcaseData;
  if (!data) return;
  const b = data.blowouts || {};
  const a = data.awards || {};
  const t = data.transfers || {};
  const s = data.stability || {};

  // 1. Top Summary KPI Cards
  const kpiCards = [
    [
      "13-0 Shutout Rate",
      `${b.shutoutPct ?? 0}%`,
      `${b.shutouts13_0 || 0} / ${(b.totalMaps || 0).toLocaleString()} maps · ${b.shutoutMultiplier || 0}x CS2 pro avg (${b.pro13_0Range || "0.8-1.5%"})`,
    ],
    [
      "13-<=3 Blowouts",
      `${b.blowoutLe3Pct ?? 0}%`,
      `${b.blowoutsLe3 || 0} maps · ${b.blowoutMultiplier || 0}x CS2 pro (${b.proLe3Range || "12-15%"})`,
    ],
    [
      "12-0 First Halves",
      `${b.half12_0Pct ?? 0}% (${b.halves12_0 || 0})`,
      `${b.halves12_0T || 0} T-side vs ${b.halves12_0Ct || 0} CT-side · R13 held ${b.r13After12_0HeldPct ?? 0}%`,
    ],
    [
      "Flagged MVPs / EVPs",
      `${a.flaggedCount || 0}`,
      `${a.outrankedMvps || 0} carried/robbed MVPs · ${a.sub110Evps || 0} sub-1.10 EVPs · ${a.duplicateMvpEvps || 0} dupes`,
    ],
    [
      "AI Transfer & Policy Bugs",
      `${t.benchedOverStarterCount || 0} Bench / ${t.policyTxPlayers || 0}P+${t.policyTxStaff || 0}S Policy`,
      `${t.policyHb0Players || 0} National + ${t.policyHb1Players || 0} Lang player breaches · $${Number(t.totalWastedSpend || 0).toLocaleString()} spent`,
    ],
    [
      "Ended / Benched Stints",
      `${s.avgStintMonths ?? 0}m avg (${s.sub6MonthsPct ?? 0}% <6m)`,
      `${s.sub6MonthsCount || 0}/${s.completedStintsCount || 0} below 6m CS2 pro low end · ${s.carouselTeamsCount || 0} high-churn orgs`,
    ],
  ];
  $("showcaseKpiGrid").innerHTML = kpiCards
    .map(
      ([lbl, val, sub]) => `
      <div class="kpi-card">
        <div class="kpi-label">${escapeHtml(lbl)}</div>
        <div class="kpi-val">${escapeHtml(val)}</div>
        <div class="kpi-sub">${escapeHtml(sub)}</div>
      </div>`
    )
    .join("");

  renderShowcaseBlowouts();
  renderShowcaseAwardsTable();
  renderShowcaseTransfers();
  renderShowcaseStability();
  renderShowcaseFindings();
}

function renderShowcaseBlowouts() {
  const b = state.showcaseData?.blowouts;
  if (!b) return;

  $("scBlowoutSummaryTag").textContent = `${b.shutoutMultiplier || 0}x 13-0 Rate vs CS2 Pro`;

  // Save vs CS2 Pro comparison bars
  const rows = [
    {
      label: "13-0 Shutout Rate",
      saveVal: `${b.shutoutPct}% (${b.shutouts13_0} maps)`,
      proVal: `Pro Avg: ~1.1% (${b.pro13_0Range})`,
      fillPct: Math.min(100, (b.shutoutPct / 6.0) * 100),
      proPct: Math.min(100, ((b.pro13_0Baseline || 1.1) / 6.0) * 100),
    },
    {
      label: "13-<=3 Blowout Rate",
      saveVal: `${b.blowoutLe3Pct}% (${b.blowoutsLe3} maps)`,
      proVal: `Pro Avg: ~13.5% (${b.proLe3Range})`,
      fillPct: Math.min(100, (b.blowoutLe3Pct / 35.0) * 100),
      proPct: Math.min(100, ((b.proLe3Baseline || 13.5) / 35.0) * 100),
    },
    {
      label: "12-0 Half Rate",
      saveVal: `${b.half12_0Pct}% (${b.halves12_0T} T / ${b.halves12_0Ct} CT)`,
      proVal: `Pro Avg: <0.5%`,
      fillPct: Math.min(100, (b.half12_0Pct / 10.0) * 100),
      proPct: Math.min(100, ((b.pro12_0Baseline || 0.45) / 10.0) * 100),
    },
    {
      label: "Even-Odds T-Side Round Win %",
      saveVal: `${b.closeTWinPct}% (R1 Pistol: ${b.closeR1TWinPct}%)`,
      proVal: `Balanced CS2: ~50.0%`,
      fillPct: Math.min(100, b.closeTWinPct || 50),
      proPct: 50,
    },
  ];
  $("scBenchmarkBars").innerHTML = rows
    .map(
      (r) => `
      <div class="bench-compare-row">
        <div class="bench-compare-head">
          <strong>${escapeHtml(r.label)}</strong>
          <span><span class="stat-bad">${escapeHtml(r.saveVal)}</span> <span class="muted">| ${escapeHtml(r.proVal)}</span></span>
        </div>
        <div class="bench-track" title="Green line = CS2 Pro Baseline">
          <div class="bench-fill-save" style="width:${r.fillPct.toFixed(1)}%;"></div>
          <div class="bench-marker-pro" style="left:${r.proPct.toFixed(1)}%;"></div>
        </div>
      </div>`
    )
    .join("");

  // Intra-half streak snowball
  const curve = b.streakCurve || [];
  $("scStreakBars").innerHTML = curve.length
    ? curve
        .map(
          (c) => `
        <div class="bench-compare-row" style="margin-bottom:8px;">
          <div class="bench-compare-head">
            <span>Streak <strong>${escapeHtml(c.streakLabel)}</strong> in a row</span>
            <span><strong>${c.holdPct}%</strong> win next round <span class="muted">(${c.wins}/${c.total})</span></span>
          </div>
          <div class="bench-track" style="height:9px;">
            <div class="bench-fill-streak" style="width:${Math.min(100, c.holdPct)}%;"></div>
            <div class="bench-marker-pro" style="left:50%;"></div>
          </div>
        </div>`
        )
        .join("")
    : `<div class="muted">Not enough simulated rounds yet.</div>`;

  renderShowcaseBlowoutTable();
}

function renderShowcaseBlowoutTable() {
  const b = state.showcaseData?.blowouts;
  if (!b) return;
  const q = ($("showcaseFilterQ").value || "").trim().toLowerCase();
  const mode = $("scBlowoutFilterMode").value || "all";

  const rows = (b.examples || []).filter((e) => {
    if (mode === "13-0" && e.loseScore !== 0) return false;
    if (mode === "top20" && !(e.loseScore === 0 && e.isTop20)) return false;
    if (mode === "upset" && !(e.loseScore === 0 && e.isUpset)) return false;
    if (q) {
      const hay = `${e.event} ${e.mapName} ${e.team1Name} ${e.team2Name}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });

  $("scBlowoutCount").textContent = `${rows.length} shown`;
  const tbody = $("scBlowoutBody");
  tbody.innerHTML = rows.length
    ? rows
        .map((e) => {
          const r1 = e.team1Rank ? `#${e.team1Rank} ` : "";
          const r2 = e.team2Rank ? `#${e.team2Rank} ` : "";
          const t1Win = e.team1Score > e.team2Score;
          const tagsHtml = (e.tags || [])
            .map((tg) => `<span class="tag-pill ${tg === "13-0" ? "" : tg.startsWith("Top") ? "info" : "warn"}">${escapeHtml(tg)}</span>`)
            .join("");
          return `<tr style="cursor:pointer;" onclick="openMatchStatsModal(${e.matchId})">
            <td class="mono muted">${escapeHtml(e.date)}</td>
            <td>${escapeHtml(e.event)}</td>
            <td>${escapeHtml(e.mapName)}</td>
            <td><span class="${t1Win ? "stat-good" : "muted"}">${escapeHtml(r1 + e.team1Name)}</span> vs <span class="${!t1Win ? "stat-good" : "muted"}">${escapeHtml(r2 + e.team2Name)}</span></td>
            <td class="mono ${e.loseScore === 0 ? "stat-bad" : ""}"><strong>${e.team1Score} - ${e.team2Score}</strong></td>
            <td class="mono">${e.winnerOdds}%</td>
            <td>${tagsHtml}</td>
          </tr>`;
        })
        .join("")
    : `<tr><td colspan="7" class="muted" style="text-align:center;padding:18px;">No blowouts matching filter.</td></tr>`;
}

function renderShowcaseAwardsTable() {
  const a = state.showcaseData?.awards;
  if (!a) return;
  const q = ($("showcaseFilterQ").value || "").trim().toLowerCase();
  const mode = $("scAwardsFilterMode").value || "all";

  $("scAwardsNote").textContent = `Evaluated ${a.totalEvaluated || 0} awards across real MVP/EVP tournaments (${a.totalMvps || 0} MVPs, ${a.totalEvps || 0} EVPs). Trophy champions keep MVP unless <1.18, outperformed by a teammate, or outcarried by >=+0.18 (2nd) / >=+0.25 (SF) / >=+0.30 (other). Low-rep non-award tournaments and ${a.mockAwardsHidden || 0} Year<=10 mock awards excluded.`;

  const rows = (a.flagged || []).filter((r) => {
    if (mode === "mvp" && r.role !== "MVP") return false;
    if (mode === "sub110" && !(r.role === "EVP" && r.rating > 0 && r.rating < 1.10)) return false;
    if (mode === "dup" && r.role !== "MVP + EVP") return false;
    if (q) {
      const hay = `${r.playerName} ${r.teamName} ${r.event} ${r.bestPlayerName}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });

  $("scAwardsCount").textContent = `${rows.length} flagged`;
  const tbody = $("scAwardsBody");
  tbody.innerHTML = rows.length
    ? rows
        .map((r) => {
          const roleClass = r.role === "MVP" ? "warn" : r.role === "MVP + EVP" ? "" : "info";
          const ratClass = r.rating > 0 && r.rating < 1.10 ? "stat-bad" : "";
          const pClick = r.playerId > 0 ? `onclick="openPlayerStatsModal(${r.playerId})" style="cursor:pointer;text-decoration:underline dotted;"` : "";
          const bClick = r.bestPlayerId > 0 ? `onclick="openPlayerStatsModal(${r.bestPlayerId})" style="cursor:pointer;text-decoration:underline dotted;"` : "";
          const plNote = r.placement && r.placement !== "—" ? ` [${r.placement}]` : "";
          const statsTxt = r.matches > 0 ? `${r.rating.toFixed(2)} (${r.wins}W-${r.losses}L) · ${r.kpr.toFixed(2)} KPR · ${r.adr.toFixed(0)} ADR${plNote}` : "—";
          const rankTxt = r.eventRank > 0 ? `#${r.eventRank} / ${r.fieldSize}` : "—";
          const bestTxt = r.bestPlayerName !== "—" ? `<span ${bClick}>${escapeHtml(r.bestPlayerName)}</span> <span class="stat-good mono">(${r.bestPlayerRating.toFixed(2)}${r.bestPlacement ? `, ${r.bestPlacement}` : ""})</span>` : "—";
          return `<tr>
            <td><span class="tag-pill ${roleClass}">${escapeHtml(r.role)}</span></td>
            <td class="mono muted">${escapeHtml(r.date)}</td>
            <td>${escapeHtml(r.event)}</td>
            <td><strong ${pClick}>${escapeHtml(r.playerName)}</strong> <span class="muted">(${escapeHtml(r.teamName)})</span></td>
            <td class="mono ${ratClass}">${escapeHtml(statsTxt)}</td>
            <td class="mono">${escapeHtml(rankTxt)}</td>
            <td>${bestTxt}</td>
            <td>${(r.reasons || []).map((rs) => `<div style="font-size:12px;">${escapeHtml(rs)}</div>`).join("")}</td>
          </tr>`;
        })
        .join("")
    : `<tr><td colspan="8" class="muted" style="text-align:center;padding:18px;">No undeserved MVPs/EVPs found matching filter.</td></tr>`;
}

function renderShowcaseTransfers() {
  const t = state.showcaseData?.transfers;
  if (!t) return;
  const q = ($("showcaseFilterQ").value || "").trim().toLowerCase();

  const crimes = (t.benchedCrimes || []).filter((c) => {
    if (!q) return true;
    return `${c.teamName} ${c.benchedName} ${c.starterName}`.toLowerCase().includes(q);
  });
  $("scBenchCrimesCount").textContent = `${crimes.length} teams`;
  $("scBenchCrimesBody").innerHTML = crimes.length
    ? crimes
        .map(
          (c) => `<tr>
          <td><strong style="cursor:pointer;text-decoration:underline dotted;" onclick="openTeamStatsModal(${c.teamId})">${escapeHtml(c.teamName)}</strong></td>
          <td><span style="cursor:pointer;text-decoration:underline dotted;" onclick="openPlayerStatsModal(${c.benchedId})"><strong>${escapeHtml(c.benchedName)}</strong></span> <span class="muted">(age ${c.benchedAge})</span></td>
          <td class="mono stat-good">${c.benchedSkill.toFixed(2)}</td>
          <td><span style="cursor:pointer;text-decoration:underline dotted;" onclick="openPlayerStatsModal(${c.starterId})">${escapeHtml(c.starterName)}</span> <span class="muted">(age ${c.starterAge})</span></td>
          <td class="mono stat-bad">${c.starterSkill.toFixed(2)}</td>
          <td class="mono"><span class="tag-pill">+${c.skillDiff.toFixed(2)} wasted</span></td>
        </tr>`
        )
        .join("")
    : `<tr><td colspan="6" class="muted" style="text-align:center;padding:18px;">No active bench-over-starter anomalies found.</td></tr>`;

  const txs = (t.flaggedTransfers || []).filter((r) => {
    if (!q) return true;
    return `${r.playerName} ${r.fromTeamName} ${r.toTeamName} ${r.compareName}`.toLowerCase().includes(q);
  });
  $("scTransfersCount").textContent = `${txs.length} flagged`;
  $("scTransfersBody").innerHTML = txs.length
    ? txs
        .map(
          (r) => `<tr>
          <td class="mono muted">${escapeHtml(r.date)}</td>
          <td><strong style="cursor:pointer;text-decoration:underline dotted;" onclick="openPlayerStatsModal(${r.playerId})">${escapeHtml(r.playerName)}</strong> <span class="mono muted">(${r.skill.toFixed(2)} sk, ${r.age}y)</span></td>
          <td>${escapeHtml(r.fromTeamName)} &rarr; <strong>${escapeHtml(r.toTeamName)}</strong></td>
          <td class="mono">${r.purchasePrice > 0 ? `$${r.purchasePrice.toLocaleString()}` : "Free"}</td>
          <td>${r.compareName !== "—" ? `${escapeHtml(r.compareName)} <span class="stat-good mono">(${r.compareSkill.toFixed(2)})</span>` : "—"}</td>
          <td>${(r.reasons || []).map((rs) => `<div style="font-size:12px;">${escapeHtml(rs)}</div>`).join("")}</td>
        </tr>`
        )
        .join("")
    : `<tr><td colspan="6" class="muted" style="text-align:center;padding:18px;">No unexplainable transfers matching filter.</td></tr>`;

  // "Only National" & "Only National Language" Policy Violations
  const pMode = $("scPolicyFilterMode").value || "players";
  $("scPolicyNote").textContent = `${t.onlyNationalTeamCount || 0} 'Only National' + ${t.onlyLangTeamCount || 0} 'Only National Language' clubs — ${t.policyHb0Players || 0} national / ${t.policyHb1Players || 0} language player transfers (${t.policyActivePlayers || 0} active) + ${t.policyTxStaff || 0} staff transfers, $${Number(t.policySpend || 0).toLocaleString()} spent.`;
  const pvRows = (t.policyViolations || []).filter((r) => {
    if (pMode === "players" && r.personType !== "Player") return false;
    if (pMode === "hb0_players" && !(r.personType === "Player" && r.policyCode === "hb0")) return false;
    if (pMode === "hb1_players" && !(r.personType === "Player" && r.policyCode === "hb1")) return false;
    if (pMode === "paid_all" && r.personType !== "Player" && !(r.purchasePrice > 0)) return false;
    if (q) {
      const hay = `${r.teamName} ${r.teamNation} ${r.personName} ${r.personNation} ${r.policyDetail} ${r.route}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
  $("scPolicyCount").textContent = `${pvRows.length} shown`;
  $("scPolicyBody").innerHTML = pvRows.length
    ? pvRows
        .map((r) => {
          const pClick = r.personType === "Player" ? `onclick="openPlayerStatsModal(${r.personId})" style="cursor:pointer;text-decoration:underline dotted;"` : "";
          const polClass = r.policyCode === "hb0" ? "" : "warn";
          return `<tr>
            <td><strong style="cursor:pointer;text-decoration:underline dotted;" onclick="openTeamStatsModal(${r.teamId})">${escapeHtml(r.teamName)}</strong> <span class="muted">(${escapeHtml(r.teamNation)})</span> <span class="tag-pill ${polClass}">${escapeHtml(r.policyLabel || "Only National")}</span></td>
            <td><span class="tag-pill ${r.personType === "Player" ? "warn" : "info"}">${escapeHtml(r.personType)}</span></td>
            <td><strong ${pClick}>${escapeHtml(r.personName)}</strong> <span class="stat-bad">(${escapeHtml(r.personNation)})</span></td>
            <td style="font-size:12px;">${escapeHtml(r.policyDetail || "")}</td>
            <td class="mono muted">${r.skill.toFixed(2)} sk · ${r.age}y</td>
            <td>${escapeHtml(r.route)} <span class="mono muted">(${escapeHtml(r.date)})</span></td>
            <td class="mono">${r.purchasePrice > 0 ? `$${r.purchasePrice.toLocaleString()}` : "Free"}</td>
            <td><span class="tag-pill ${r.activeOnTeam ? "" : "info"}">${escapeHtml(r.source)}</span></td>
          </tr>`;
        })
        .join("")
    : `<tr><td colspan="8" class="muted" style="text-align:center;padding:18px;">No policy violations matching filter.</td></tr>`;
}

function renderShowcaseStability() {
  const s = state.showcaseData?.stability;
  if (!s) return;
  const q = ($("showcaseFilterQ").value || "").trim().toLowerCase();

  $("scStabilitySummaryTag").textContent = `${s.avgStintMonths || 0}m Avg vs ${s.proLowEndMonths || 6}m Pro Low End`;

  const bars = [
    {
      label: "Avg Ended / Benched Post-Transfer Stint",
      saveVal: `${s.avgStintMonths} months (${s.avgStintDays}d)`,
      proVal: `CS2 Pro Low End: 6.0m (Avg: ${s.proFullRange})`,
      fillPct: Math.min(100, ((s.avgStintMonths || 0) / 14.0) * 100),
      proPct: (6.0 / 14.0) * 100,
    },
    {
      label: "Median Ended / Benched Stint",
      saveVal: `${s.medianStintMonths} months (${s.medianStintDays}d)`,
      proVal: `Tier-1 Pro Median: ${s.proMedianRange}`,
      fillPct: Math.min(100, ((s.medianStintMonths || 0) / 14.0) * 100),
      proPct: (8.0 / 14.0) * 100,
    },
    {
      label: "Stints Shorter Than Pro Low End (< 6.0 Months)",
      saveVal: `${s.sub6MonthsPct}% (${s.sub6MonthsCount}/${s.completedStintsCount} stints)`,
      proVal: `${s.sub3MonthsCount || 0} lasted <3 months`,
      fillPct: Math.min(100, s.sub6MonthsPct || 0),
      proPct: 25,
    },
  ];
  $("scStabilityBars").innerHTML = bars
    .map(
      (r) => `
      <div class="bench-compare-row">
        <div class="bench-compare-head">
          <strong>${escapeHtml(r.label)}</strong>
          <span><span class="stat-bad">${escapeHtml(r.saveVal)}</span> <span class="muted">| ${escapeHtml(r.proVal)}</span></span>
        </div>
        <div class="bench-track" title="Green line = CS2 Pro Baseline">
          <div class="bench-fill-save" style="width:${r.fillPct.toFixed(1)}%;"></div>
          <div class="bench-marker-pro" style="left:${r.proPct.toFixed(1)}%;"></div>
        </div>
      </div>`
    )
    .join("");

  $("scStintsNote").textContent = `${s.sub6MonthsCount || 0} of ${s.completedStintsCount || 0} ended/benched post-transfer stints lasted under 6.0 months (CS2 pro tier low end: ${s.proFullRange}).`;
  const stintRows = (s.stints || []).filter((r) => {
    if (!q) return true;
    return `${r.playerName} ${r.teamName} ${r.outcome}`.toLowerCase().includes(q);
  });
  $("scStintsCount").textContent = `${stintRows.length} stints`;
  $("scStintsBody").innerHTML = stintRows.length
    ? stintRows
        .map((r) => {
          const badge = r.activeDays < 90 ? "" : r.belowProLowEnd ? "warn" : "info";
          const stintLabel = `${r.activeDays}d (${r.activeMonths}m)${r.belowProLowEnd ? ` · -${r.proLowDiffMonths}m vs 6m min` : ""}`;
          return `<tr>
            <td><strong style="cursor:pointer;text-decoration:underline dotted;" onclick="openPlayerStatsModal(${r.playerId})">${escapeHtml(r.playerName)}</strong> <span class="mono muted">(${r.skill.toFixed(2)} sk)</span></td>
            <td><strong style="cursor:pointer;text-decoration:underline dotted;" onclick="openTeamStatsModal(${r.teamId})">${escapeHtml(r.teamName)}</strong></td>
            <td class="mono">${r.fee > 0 ? `$${r.fee.toLocaleString()}` : "Free"}</td>
            <td class="mono muted">${escapeHtml(r.signDate)} &rarr; ${escapeHtml(r.endDate)}</td>
            <td><span class="tag-pill ${badge}">${escapeHtml(stintLabel)}</span></td>
            <td class="mono">${r.matchesPlayed}</td>
            <td>${escapeHtml(r.outcome)}${r.heldDays > r.activeDays ? ` <span class="muted">(${r.heldDays}d on payroll)</span>` : ""}</td>
          </tr>`;
        })
        .join("")
    : `<tr><td colspan="7" class="muted" style="text-align:center;padding:18px;">No completed/benched stints matching filter.</td></tr>`;

  const churnRows = (s.teamChurn || []).filter((r) => {
    if (!q) return true;
    return `${r.teamName}`.toLowerCase().includes(q);
  });
  $("scChurnCount").textContent = `${churnRows.length} clubs`;
  $("scChurnBody").innerHTML = churnRows.length
    ? churnRows
        .map(
          (r) => `<tr>
          <td><strong style="cursor:pointer;text-decoration:underline dotted;" onclick="openTeamStatsModal(${r.teamId})">${escapeHtml(r.teamName)}</strong></td>
          <td class="mono"><span class="${r.totalPlayerMoves >= 5 ? "stat-bad" : ""}"><strong>${r.totalPlayerMoves} moves</strong></span> <span class="muted">(+${r.playersIn} in / -${r.playersOut} out)</span></td>
          <td class="mono">${r.staffIn} staff hired</td>
          <td class="mono">${r.spend > 0 ? `$${r.spend.toLocaleString()}` : "$0"}</td>
          <td class="mono">${r.startersNow} active / <span class="${r.benchedNow > 0 ? "stat-bad" : "muted"}">${r.benchedNow} benched</span></td>
        </tr>`
        )
        .join("")
    : `<tr><td colspan="5" class="muted" style="text-align:center;padding:18px;">No high-churn teams matching filter.</td></tr>`;
}

function renderShowcaseFindings() {
  const sections = state.showcaseData?.findings || [];
  const q = ($("showcaseFilterQ").value || "").trim().toLowerCase();
  let totalShown = 0;

  const html = sections
    .map((sec) => {
      const items = (sec.items || []).filter(
        (it) => !q || `${sec.category} ${it.title} ${it.symbol} ${it.rootCause} ${it.devFix} ${it.liveImpact}`.toLowerCase().includes(q)
      );
      if (!items.length) return "";
      totalShown += items.length;
      const cardsHtml = items
        .map((it) => {
          const sevCls = it.severity === "critical" ? "bad" : it.severity === "high" ? "warn" : it.severity === "warn" ? "info" : "ok";
          const sevLbl = String(it.severity || "info").toUpperCase();
          return `<div class="bug-cause-card ${sevCls}">
            <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;">
              <div class="bug-cause-title">${escapeHtml(it.title)}</div>
              <span class="tag-pill ${it.severity === "critical" ? "err" : it.severity === "high" ? "warn" : "info"}">${sevLbl}</span>
            </div>
            <div class="bug-cause-sym mono">${escapeHtml(it.symbol)}</div>
            <div style="font-size:11.5px;color:#cbd5e1;margin-bottom:5px;"><strong>Save Impact:</strong> ${escapeHtml(it.liveImpact)}</div>
            <div class="bug-cause-desc"><strong>Root Cause:</strong> ${escapeHtml(it.rootCause)}</div>
            <div class="bug-cause-desc" style="margin-top:5px;"><strong>Suggested Fix:</strong> ${escapeHtml(it.devFix)}</div>
          </div>`;
        })
        .join("");
      return `<div class="subcard" style="margin-top:10px;">
        <div class="subcard-title" style="display:flex;justify-content:space-between;align-items:center;">
          <span>${escapeHtml(sec.category)}</span>
          <span class="tag-pill info">${escapeHtml(sec.tag)}</span>
        </div>
        <div class="bug-cause-grid">${cardsHtml}</div>
      </div>`;
    })
    .join("");

  $("scFindingsCount").textContent = `${totalShown} findings`;
  $("scFindingsContainer").innerHTML = html || '<div class="muted">No documented findings match your filter.</div>';
}

async function copyShowcaseMarkdown() {
  const d = state.showcaseData;
  if (!d) return toast("Run Re-Scan Save first.", "err");
  const b = d.blowouts || {};
  const a = d.awards || {};
  const t = d.transfers || {};
  const s = d.stability || {};
  const lines = [
    `# CS Manager Save Bug Showcase (${state.summary?.fileName || "save"})`,
    ``,
    `## 1. Blowouts vs CS2 Pro Average`,
    `- **13-0 Shutout Rate**: **${b.shutoutPct}%** (${b.shutouts13_0}/${b.totalMaps} maps) — **${b.shutoutMultiplier}x** CS2 Pro Avg (${b.pro13_0Range})`,
    `- **13-<=3 Blowout Rate**: **${b.blowoutLe3Pct}%** (${b.blowoutsLe3} maps) — **${b.blowoutMultiplier}x** CS2 Pro Avg (${b.proLe3Range})`,
    `- **12-0 First Halves**: **${b.halves12_0}** (${b.half12_0Pct}%) — ${b.halves12_0T} T-side vs ${b.halves12_0Ct} CT-side`,
    `- **Top-20 13-0s / Underdog 13-0s**: ${b.top20_13_0} Top-20 vs Top-20 · ${b.upset_13_0} upsets (${b.upset_13_0Pct}%)`,
    `- **Even-Odds T Win %**: ${b.closeTWinPct}% (R1 Pistol: ${b.closeR1TWinPct}%)`,
    ``,
    `## 2. Undeserved MVPs & EVPs (${a.flaggedCount} flagged / ${a.totalEvaluated} evaluated)`,
    ...(a.flagged || []).slice(0, 8).map(
      (r) => `- **${r.role}** \`${r.playerName}\` (${r.teamName}) at ${r.event} (${r.date}): **${r.rating}** rat — ${r.reasons.join("; ")}`
    ),
    ``,
    `## 3. Unexplainable AI Transfers, Bench Crimes & Policy Violations`,
    `- **${t.benchedOverStarterCount} teams** currently bench a stronger player than a starter:`,
    ...(t.benchedCrimes || []).slice(0, 6).map(
      (c) => `- **${c.teamName}**: Benched \`${c.benchedName}\` (${c.benchedSkill}) > Starter \`${c.starterName}\` (${c.starterSkill}) [+${c.skillDiff}]`
    ),
    `- **Hiring Policy Breaches (${t.policyHb0Players} National + ${t.policyHb1Players} Language players / ${t.policyTxStaff} staff)**:`,
    ...(t.policyViolations || []).filter((r) => r.personType === "Player").slice(0, 8).map(
      (r) => `- **${r.teamName}** (${r.policyLabel}, ${r.teamNation}) hired **${r.personName}** (${r.personNation}) [${r.policyDetail}] — ${r.route} ($${r.purchasePrice.toLocaleString()})`
    ),
    ``,
    `## 4. Squad Stability vs CS2 Pro Low End (6.0 Months)`,
    `- **Ended / Benched Post-Transfer Stints**: **${s.avgStintMonths}m avg** (${s.medianStintMonths}m median), **${s.sub6MonthsPct}%** (${s.sub6MonthsCount}/${s.completedStintsCount}) lasted under the 6.0m CS2 pro low end`,
    ...(s.stints || []).slice(0, 8).map(
      (r) => `- \`${r.playerName}\` -> **${r.teamName}** ($${r.fee.toLocaleString()}): **${r.activeDays}d (${r.activeMonths}m)**, ${r.matchesPlayed} matches — ${r.outcome}`
    ),
    ``,
    `## 5. Documented Engine Root Causes & Findings`,
    ...(d.findings || []).flatMap((sec) => [
      `### ${sec.category}`,
      ...(sec.items || []).map(
        (it) => `- **${it.title}** [\`${it.symbol}\`]: ${it.rootCause} *(Impact: ${it.liveImpact})*`
      ),
    ]),
  ];
  const md = lines.join("\n");
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(md);
    } else {
      const ta = document.createElement("textarea");
      ta.value = md;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
    }
    toast("Copied Markdown Bug Showcase report to clipboard!", "ok");
  } catch {
    toast("Clipboard copy unavailable in this browser.", "err");
  }
}

// ==================== STRENGTH & REALISM ====================
const _fmtUsd = (n) => "$" + Math.round(Number(n || 0)).toLocaleString("en-US");

function _realismFindTeam(d, tid) {
  return (d.teamStrengths || []).find((t) => String(t.teamId) === String(tid)) || null;
}

function _realismBuildTop10AvgTeam(d, excludeId) {
  const pool = (d.teamStrengths || []).filter(
    (t) => t.worldRank && t.worldRank <= 10 && String(t.teamId) !== String(excludeId)
  );
  const rows = pool.length ? pool : (d.teamStrengths || []).slice(0, 10);
  if (!rows.length) return null;
  const avg = (k) => rows.reduce((s, r) => s + Number(r[k] || 0), 0) / rows.length;
  return {
    teamId: "__TOP10__",
    name: `Top-10 Rival Field (${rows.length})`,
    worldRank: 5,
    avgSkill: Number(avg("avgSkill").toFixed(2)),
    mechanicsAvg: Number(avg("mechanicsAvg").toFixed(2)),
    mentalAvg: Number(avg("mentalAvg").toFixed(2)),
    weaponsAvg: Number(avg("weaponsAvg").toFixed(2)),
    bestStarSkill: Number(avg("bestStarSkill").toFixed(2)),
    weakestLinkSkill: Number(avg("weakestLinkSkill").toFixed(2)),
    bestAwp: Number(avg("bestAwp").toFixed(2)),
    bestIgl: Number(avg("bestIgl").toFixed(2)),
    staffAvgSkill: Number(avg("staffAvgSkill").toFixed(2)),
    cohesionAvg: Number(avg("cohesionAvg").toFixed(1)),
    mapReadinessAvg: Number(avg("mapReadinessAvg").toFixed(1)),
    facilityScore: Number(avg("facilityScore").toFixed(1)),
    annualWages: Math.round(avg("annualWages")),
    winPct: Number(avg("winPct").toFixed(1)),
    trophiesCount: Number(avg("trophiesCount").toFixed(1)),
    starters: [],
    isVirtualField: true,
  };
}

async function loadStrengthRealism() {
  if (!state.summary?.path) return;
  const yr = $("realismFilterYear").value;
  const focus = $("realismFocusTeam").value;
  const qs = new URLSearchParams();
  if (yr) qs.set("year", yr);
  if (focus) qs.set("focus_team_id", focus);
  try {
    const d = await api(`/api/strength-realism?${qs.toString()}`);
    state.realismData = d;
    if (!d.loaded) return;

    populateSelect(
      $("realismFilterYear"),
      (d.years || []).map((y) => [y, `Season ${y}`]),
      d.year
    );

    const teams = d.teamStrengths || [];
    const teamOpts = teams.map((t) => [
      t.teamId,
      `${t.worldRank ? `#${t.worldRank} ` : ""}${t.name}${t.isUserTeam ? " (YOU)" : ""} — ${t.avgSkill} avg`,
    ]);
    const focusId = d.trophyRealism?.focusTeamId ?? teams[0]?.teamId ?? "";
    populateSelect($("realismFocusTeam"), teamOpts, focusId);

    const curA = $("diffTeamA").value || focusId;
    const defaultB = teams.find((t) => String(t.teamId) !== String(curA))?.teamId || "__TOP10__";
    const curB = $("diffTeamB").value || defaultB;
    populateSelect($("diffTeamA"), teamOpts, curA);
    populateSelect(
      $("diffTeamB"),
      [["__TOP10__", "Top-10 Rival Field (Average)"], ...teamOpts],
      curB
    );

    const lab1 = $("labTeam1").value || curA;
    const lab2 = $("labTeam2").value || (teams.find((t) => String(t.teamId) !== String(lab1))?.teamId ?? lab1);
    populateSelect($("labTeam1"), teamOpts, lab1);
    populateSelect($("labTeam2"), teamOpts, lab2);
    const mapsMeta = d.mapsMeta || [];
    const curMap = $("labMap").value || mapsMeta[0]?.mapId || "";
    populateSelect($("labMap"), mapsMeta.map((m) => [m.mapId, m.name]), curMap);

    renderRealismTab();
  } catch (err) {
    toast(`Strength & Realism load failed: ${err.message}`, "err");
  }
}

function renderRealismTab() {
  const d = state.realismData;
  if (!d || !d.loaded) return;
  renderRealismKpis(d);
  renderRealismDiff(d);
  renderRealismDiffTable(d);
  renderRealismTrophies(d);
  renderRealismMatchup(d);
  renderRealismRegression(d);
  renderRealismParity(d);
}

function renderRealismKpis(d) {
  const tr = d.trophyRealism || {};
  const edge = Number(tr.skillEdgeVsTop10 || 0);
  const def = Number(tr.oddsDefiancePp || 0);
  const kpis = [
    { label: `${tr.focusTeamName || "Focus"} Avg Skill`, val: tr.avgSkill ?? "-", sub: `${edge >= 0 ? "+" : ""}${edge} vs Top-10 (${tr.rivalTop10AvgSkill ?? "-"})` },
    { label: `${d.year} Trophies Won`, val: tr.trophiesWon ?? 0, sub: `${tr.tier1TrophiesWon ?? 0}/${tr.totalTier1Completed ?? 0} Tier-1 (${tr.trophySharePct ?? 0}% share)` },
    { label: "Match Record", val: `${tr.wins ?? 0}W - ${tr.losses ?? 0}L`, sub: `${tr.winPct ?? 0}% win rate • Streak ${tr.maxWinStreak ?? 0}` },
    { label: "Odds Defiance", val: `${def >= 0 ? "+" : ""}${def} pp`, sub: `Expected ${tr.avgPreMatchOdds ?? 0}% pre-match` },
    { label: "#1 World Skill Bar", val: d.rank1Skill ?? "-", sub: `Top-10 Avg: ${d.top10AvgSkill ?? "-"}` },
  ];
  $("realismKpiGrid").innerHTML = kpis
    .map(
      (k) => `<div class="kpi-card">
        <div class="kpi-label">${escapeHtml(k.label)}</div>
        <div class="kpi-val">${escapeHtml(k.val)}</div>
        <div class="kpi-sub">${escapeHtml(k.sub)}</div>
      </div>`
    )
    .join("");
}

function renderRealismDiff(d) {
  const tA = _realismFindTeam(d, $("diffTeamA").value);
  const bVal = $("diffTeamB").value;
  const tB = bVal === "__TOP10__" ? _realismBuildTop10AvgTeam(d, tA?.teamId) : _realismFindTeam(d, bVal);
  if (!tA || !tB) {
    $("diffH2HSummary").innerHTML = "Select two teams to compare.";
    $("diffH2HBars").innerHTML = "";
    $("diffH2HRosters").innerHTML = "";
    return;
  }

  const skillDiff = Number((tA.avgSkill - tB.avgSkill).toFixed(2));
  const floorDiff = Number((tA.weakestLinkSkill - tB.weakestLinkSkill).toFixed(2));
  const pA = Math.pow(Math.max(1, tA.avgSkill), 2.8);
  const pB = Math.pow(Math.max(1, tB.avgSkill), 2.8);
  const mapOddsA = Number(((pA / (pA + pB)) * 100).toFixed(1));
  const cls = Math.abs(skillDiff) >= 1.2 ? "bad" : Math.abs(skillDiff) >= 0.45 ? "warn" : "ok";

  $("diffH2HSummary").className = `verdict-banner ${cls}`;
  $("diffH2HSummary").innerHTML = `<div class="verdict-headline">${escapeHtml(tA.name)} (${tA.avgSkill}) vs ${escapeHtml(tB.name)} (${tB.avgSkill})</div>
    <div>Skill edge: <strong class="${skillDiff >= 0 ? "stat-good" : "stat-bad"}">${skillDiff >= 0 ? "+" : ""}${skillDiff}</strong> per skill avg &bull; Weakest-link floor diff: <strong>${floorDiff >= 0 ? "+" : ""}${floorDiff}</strong> &bull; Neutral-map engine odds (<code>skill^2.8</code>): <strong>${mapOddsA}%</strong> vs <strong>${(100 - mapOddsA).toFixed(1)}%</strong>.</div>`;

  const metrics = [
    { label: "Active Avg Skill (1-20)", a: tA.avgSkill, b: tB.avgSkill, max: 20 },
    { label: "Star Peak (Best Starter)", a: tA.bestStarSkill, b: tB.bestStarSkill, max: 20 },
    { label: "Weakest-Link Floor", a: tA.weakestLinkSkill, b: tB.weakestLinkSkill, max: 20 },
    { label: "Mechanics Avg (6)", a: tA.mechanicsAvg, b: tB.mechanicsAvg, max: 20 },
    { label: "Mental Avg (4)", a: tA.mentalAvg, b: tB.mentalAvg, max: 20 },
    { label: "Weapons Avg (5)", a: tA.weaponsAvg, b: tB.weaponsAvg, max: 20 },
    { label: "Best AWPer Score", a: tA.bestAwp, b: tB.bestAwp, max: 20 },
    { label: "Best IGL Score", a: tA.bestIgl, b: tB.bestIgl, max: 20 },
    { label: "Coaching Staff Avg", a: tA.staffAvgSkill, b: tB.staffAvgSkill, max: 20 },
    { label: "Cohesion / Chemistry %", a: tA.cohesionAvg, b: tB.cohesionAvg, max: 100 },
    { label: "Map Pool Comfort Avg", a: tA.mapReadinessAvg, b: tB.mapReadinessAvg, max: 100 },
    { label: "Facility Grade Score", a: tA.facilityScore, b: tB.facilityScore, max: 100 },
  ];

  $("diffH2HBars").innerHTML = `<div class="h2h-list">${metrics
    .map((m) => {
      const aPct = Math.min(100, Math.max(2, (Number(m.a || 0) / m.max) * 100)).toFixed(1);
      const bPct = Math.min(100, Math.max(2, (Number(m.b || 0) / m.max) * 100)).toFixed(1);
      const dVal = Number((Number(m.a || 0) - Number(m.b || 0)).toFixed(2));
      const dTag = dVal > 0 ? `+${dVal}` : `${dVal}`;
      return `<div class="h2h-row">
        <div class="h2h-head">
          <span class="h2h-val-a" style="color:${dVal >= 0 ? "#7dd3fc" : "var(--text-muted)"};">${m.a}</span>
          <span class="h2h-label">${escapeHtml(m.label)} (${dTag})</span>
          <span class="h2h-val-b" style="color:${dVal <= 0 ? "#fbbf24" : "var(--text-muted)"};">${m.b}</span>
        </div>
        <div class="h2h-track">
          <div class="h2h-half left"><div class="h2h-fill-a" style="width:${aPct}%"></div></div>
          <div class="h2h-half right"><div class="h2h-fill-b" style="width:${bPct}%"></div></div>
        </div>
      </div>`;
    })
    .join("")}</div>`;

  const renderRosterCard = (team, accent) => {
    if (team.isVirtualField) {
      return `<div class="roster-vs-card">
        <div class="roster-vs-title"><span style="color:${accent};">${escapeHtml(team.name)}</span><span>${team.avgSkill} avg</span></div>
        <div class="muted" style="font-size:12px;">Aggregate benchmark across Top-10 rivals.<br>Avg Win%: ${team.winPct}% &bull; Avg Titles: ${team.trophiesCount}<br>Avg Wages: ${_fmtUsd(team.annualWages)}/yr</div>
      </div>`;
    }
    const items = (team.starters || [])
      .map(
        (p) => `<div class="roster-vs-item">
          <a href="#" class="link-btn ps-open" data-pid="${p.playerId}">${escapeHtml(p.name)} <span class="muted">(${p.age}y)</span></a>
          <span><strong>${p.avgSkill}</strong> <span class="muted">(${p.yearRating > 0 ? p.yearRating.toFixed(2) : "-"})</span></span>
        </div>`
      )
      .join("");
    return `<div class="roster-vs-card">
      <div class="roster-vs-title"><span style="color:${accent};">${escapeHtml(team.name)}</span><span>${team.avgSkill} avg &bull; ${_fmtUsd(team.annualWages)}</span></div>
      ${items || '<div class="muted">No active starters</div>'}
    </div>`;
  };

  $("diffH2HRosters").innerHTML = `<div class="roster-vs-grid">${renderRosterCard(tA, "#38bdf8")}${renderRosterCard(tB, "#fbbf24")}</div>`;
  $("diffH2HRosters").querySelectorAll(".ps-open").forEach((el) => {
    el.addEventListener("click", (ev) => {
      ev.preventDefault();
      openPlayerStatsModal(Number(el.dataset.pid));
    });
  });
}

function renderRealismDiffTable(d) {
  const q = ($("realismFilterQ").value || "").trim().toLowerCase();
  const rows = (d.teamStrengths || []).filter((r) => {
    if (!q) return true;
    const starterMatch = (r.starters || []).some((p) => p.name.toLowerCase().includes(q));
    return r.name.toLowerCase().includes(q) || (r.nationName || "").toLowerCase().includes(q) || starterMatch;
  });

  const k = state.realismSortKey;
  const dir = state.realismSortDir;
  rows.sort((a, b) => {
    if (k === "name") return String(a.name).localeCompare(String(b.name)) * dir;
    const va = a[k] ?? (dir > 0 ? 999999 : -999999);
    const vb = b[k] ?? (dir > 0 ? 999999 : -999999);
    if (va === vb) return (a.worldRank || 9999) - (b.worldRank || 9999);
    return (va < vb ? -1 : 1) * dir;
  });

  $("diffTableCount").textContent = `${rows.length} teams`;
  $("diffTableBody").innerHTML = rows
    .map((r) => {
      const gapCls = r.gapVsRank1 >= 0 ? "stat-good" : r.gapVsRank1 <= -1.2 ? "stat-bad" : "";
      const benchNote = r.benchWasteGap > 0 ? ` <span class="tag-pill warn" title="Best benched ${r.bestBenchedName} (${r.bestBenchedSkill}) exceeds weakest starter by +${r.benchWasteGap}">Bench +${r.benchWasteGap}</span>` : "";
      return `<tr>
        <td>${r.worldRank ? `#${r.worldRank}` : "-"}</td>
        <td><a href="#" class="link-btn ts-open" data-tid="${r.teamId}">${escapeHtml(r.name)}</a>${r.isUserTeam ? ' <span class="tag-pill info">YOU</span>' : ""}${benchNote}</td>
        <td><strong>${r.avgSkill}</strong> <span class="muted">(${Math.round(r.practicalSkillTotal)})</span></td>
        <td class="${gapCls}">${r.gapVsRank1 >= 0 ? "+" : ""}${r.gapVsRank1}</td>
        <td>${r.bestStarSkill} / <span class="muted">${r.weakestLinkSkill}</span></td>
        <td class="muted">${r.mechanicsAvg} / ${r.mentalAvg} / ${r.weaponsAvg}</td>
        <td>${r.staffAvgSkill}</td>
        <td>${r.cohesionAvg}%</td>
        <td>${r.mapReadinessAvg}</td>
        <td>${r.gameOddsVsRank1}%</td>
        <td>${r.winPct}% <span class="muted">(${r.wins}-${r.losses})</span></td>
        <td><strong>${r.trophiesCount}</strong></td>
        <td><button class="btn btn-sm r-compare-btn" data-tid="${r.teamId}">Compare</button></td>
      </tr>`;
    })
    .join("");

  $("diffTableBody").querySelectorAll(".ts-open").forEach((el) => {
    el.addEventListener("click", (ev) => {
      ev.preventDefault();
      openTeamStatsModal(Number(el.dataset.tid));
    });
  });
  $("diffTableBody").querySelectorAll(".r-compare-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      $("diffTeamB").value = btn.dataset.tid;
      renderRealismDiff(d);
      $("diffH2HSummary").scrollIntoView({ behavior: "smooth", block: "nearest" });
    });
  });
}

function renderRealismTrophies(d) {
  const tr = d.trophyRealism || {};
  const pillCls = tr.verdictLevel === "bad" ? "pill err" : tr.verdictLevel === "warn" ? "pill warn" : "pill ok";
  $("realismVerdictTitle").textContent = `${tr.focusTeamName || "Team"} — ${d.year} Trophy & Dominance Realism Audit`;
  $("realismVerdictPill").className = pillCls;
  $("realismVerdictPill").textContent = tr.verdict || "N/A";

  const pb = tr.proBenchmarks || {};
  $("realismVerdictBanner").className = `verdict-banner ${tr.verdictLevel || "ok"}`;
  $("realismVerdictBanner").innerHTML = `<div class="verdict-headline">${escapeHtml(tr.focusTeamName)} won ${tr.trophiesWon} titles (${tr.tier1TrophiesWon}/${tr.totalTier1Completed} Tier-1 = ${tr.trophySharePct}% share) at ${tr.winPct}% match win rate</div>
    <div><strong>Real CS2 Pro Peak (${escapeHtml(pb.proBestExamples)}):</strong> ${escapeHtml(pb.proPeakTitlesYr)}/yr &bull; ${escapeHtml(pb.proPeakMatchWinPct)} match win% &bull; ${escapeHtml(pb.proPeakSweepShare)} big-event share. <strong>Save Reality:</strong> +${tr.skillEdgeVsTop10} avg skill edge produced <strong>${tr.wins}W-${tr.losses}L</strong> (max streak ${tr.maxWinStreak}) even though pre-match game odds averaged only <strong>${tr.avgPreMatchOdds}%</strong>.</div>`;

  $("realismReasonsGrid").innerHTML = (tr.factors || [])
    .map(
      (f) => `<div class="bug-cause-card">
        <div class="bug-cause-title">${escapeHtml(f.title)}</div>
        <div class="bug-cause-desc">${escapeHtml(f.summary)}</div>
      </div>`
    )
    .join("");

  $("realismCalBars").innerHTML = (d.oddsCalibration || [])
    .map((c) => {
      const diffCls = c.diffPp >= 10 ? "stat-good" : c.diffPp <= -5 ? "stat-bad" : "";
      return `<div class="cal-row">
        <div><strong>${escapeHtml(c.bucket)}</strong><div class="muted" style="font-size:10px;">${c.matches}m</div></div>
        <div class="cal-bar-wrap" title="Bar = Actual ${c.actualPct}%, Gold line = Pre-Match ${c.expectedPct}%">
          <div class="cal-bar-actual" style="width:${c.actualPct}%"></div>
          <div class="cal-marker-exp" style="left:${c.expectedPct}%"></div>
        </div>
        <div style="text-align:right;">Actual <strong>${c.actualPct}%</strong> <span class="${diffCls}">(${c.diffPp >= 0 ? "+" : ""}${c.diffPp}pp)</span></div>
      </div>`;
    })
    .join("");

  $("realismFormatBody").innerHTML = (d.formatCalibration || [])
    .map(
      (f) => `<tr>
        <td><strong>${escapeHtml(f.format)}</strong></td>
        <td>${f.matches}</td>
        <td>${f.expectedPct}%</td>
        <td><strong>${f.actualPct}%</strong></td>
        <td class="${f.diffPp >= 5 ? "stat-good" : ""}">${f.diffPp >= 0 ? "+" : ""}${f.diffPp} pp</td>
      </tr>`
    )
    .join("");

  const league = tr.leagueTrophyTable || [];
  $("realismChampCount").textContent = `${league.length} contenders`;
  $("realismLeagueBody").innerHTML = league
    .map(
      (r) => `<tr>
        <td><a href="#" class="link-btn ts-open" data-tid="${r.teamId}">${escapeHtml(r.name)}</a></td>
        <td>${r.worldRank ? `#${r.worldRank}` : "-"}</td>
        <td>${r.avgSkill}</td>
        <td><strong>${r.trophiesCount}</strong></td>
        <td>${r.tier1TrophiesCount} <span class="muted">(${r.trophySharePct}%)</span></td>
        <td>${r.winPct}% <span class="muted">(streak ${r.maxWinStreak})</span></td>
      </tr>`
    )
    .join("");

  const focusObj = _realismFindTeam(d, tr.focusTeamId);
  const haul = focusObj?.trophies || [];
  $("realismHaulTitle").textContent = `${focusObj?.name || "Focus Team"}'s ${d.year} Trophy Haul & Winning Lineups`;
  $("realismHaulCount").textContent = `${haul.length} trophies`;
  $("realismHaulBody").innerHTML = haul.length
    ? haul
        .map(
          (h) => `<tr>
            <td>${escapeHtml(h.seasonPart)}</td>
            <td><strong>${escapeHtml(h.tournamentName)}</strong></td>
            <td>${h.reputation}</td>
            <td>${h.isTier1 ? '<span class="tag-pill info">Tier 1</span>' : '<span class="tag-pill">Minor/Tier 2</span>'}</td>
            <td>${escapeHtml((h.winningRoster || []).join(", ") || "-")}</td>
          </tr>`
        )
        .join("")
    : '<tr><td colspan="5" class="muted">No trophies recorded in this season year.</td></tr>';

  $("realismLeagueBody").querySelectorAll(".ts-open").forEach((el) => {
    el.addEventListener("click", (ev) => {
      ev.preventDefault();
      openTeamStatsModal(Number(el.dataset.tid));
    });
  });
}

function renderRealismMatchup(d) {
  const t1 = _realismFindTeam(d, $("labTeam1").value);
  const t2 = _realismFindTeam(d, $("labTeam2").value);
  const mapId = Number($("labMap").value || 0);
  const mapName = (d.mapsMeta || []).find((m) => Number(m.mapId) === mapId)?.name || "Selected Map";
  const fmt = Number($("labFormat").value || 3);
  if (!t1 || !t2) {
    $("labResultPanel").innerHTML = '<div class="muted">Select two teams to simulate matchup odds.</div>';
    return;
  }

  const c1 = Number(t1.mapComforts?.[String(mapId)] ?? t1.mapReadinessAvg ?? 50);
  const c2 = Number(t2.mapComforts?.[String(mapId)] ?? t2.mapReadinessAvg ?? 50);
  const mult = (c) => 1.0 + 0.2 * ((c - 50.0) / 50.0);
  const pwr1 = Math.pow(Math.max(1, t1.avgSkill), 2.8) * mult(c1);
  const pwr2 = Math.pow(Math.max(1, t2.avgSkill), 2.8) * mult(c2);
  const mapProb1 = pwr1 / (pwr1 + pwr2);
  const seriesProb = (p, bo) => {
    if (bo === 1) return p;
    if (bo === 3) return p * p * (3 - 2 * p);
    return p * p * p * (10 - 15 * p + 6 * p * p);
  };
  const s1 = seriesProb(mapProb1, fmt);

  const favIs1 = mapProb1 >= 0.5;
  const favMapPct = Math.max(mapProb1, 1 - mapProb1) * 100;
  const fmtRow = (d.formatCalibration || []).find((f) => f.format === `BO${fmt}`);
  const calBucket = (d.oddsCalibration || []).find((b) => {
    const [lo, hi] = b.bucket.replace("%", "").split("-").map(Number);
    return favMapPct >= lo && favMapPct <= hi + 0.01;
  }) || d.oddsCalibration?.[d.oddsCalibration.length - 1];

  const boxHtml = (label, val, sub, cls = "") => `<div class="lab-box">
    <div class="lab-box-title">${escapeHtml(label)}</div>
    <div class="lab-odds-big ${cls}">${escapeHtml(val)}</div>
    <div class="muted" style="font-size:12px;margin-top:4px;">${sub}</div>
  </div>`;

  $("labResultPanel").innerHTML = `<div class="lab-grid">
    ${boxHtml(`Single Map Odds (${mapName})`, `${(mapProb1 * 100).toFixed(1)}% vs ${((1 - mapProb1) * 100).toFixed(1)}%`, `${escapeHtml(t1.name)} comfort ${c1} (&times;${mult(c1).toFixed(2)}) vs ${escapeHtml(t2.name)} comfort ${c2} (&times;${mult(c2).toFixed(2)})`, favIs1 ? "stat-good" : "")}
    ${boxHtml(`BO${fmt} IID Series Odds`, `${(s1 * 100).toFixed(1)}% vs ${((1 - s1) * 100).toFixed(1)}%`, `Compounded from single-map ${mapName} probability`, s1 >= 0.65 ? "stat-good" : "")}
    ${boxHtml(`Save Empirical ${calBucket ? calBucket.bucket : ""} Bucket`, calBucket ? `${calBucket.actualPct}%` : "-", `${escapeHtml(favIs1 ? t1.name : t2.name)} favorite tier across ${calBucket?.matches ?? 0} save matches (BO${fmt} avg ${fmtRow?.actualPct ?? "-"}%)`, "stat-good")}
    ${boxHtml("Roster Edge Breakdown", `${(t1.avgSkill - t2.avgSkill) >= 0 ? "+" : ""}${(t1.avgSkill - t2.avgSkill).toFixed(2)} avg`, `Floor: ${t1.weakestLinkSkill} vs ${t2.weakestLinkSkill} &bull; Coh: ${t1.cohesionAvg}% vs ${t2.cohesionAvg}%`)}
  </div>`;
}

function _renderSignedCorrBars(rows, titleSuffix = "") {
  if (!rows || !rows.length) return '<div class="muted">Not enough sample data yet.</div>';
  return rows
    .map((c) => {
      const r = Number(c.r || 0);
      const w = Math.min(100, Math.round(Math.abs(r) * 100));
      const cls = r >= 0 ? "corr-fill-pos" : "corr-fill-neg";
      const valCls = r >= 0.35 ? "stat-good" : r <= -0.35 ? "stat-bad" : "";
      return `<div class="corr-row">
        <div><strong>${escapeHtml(c.label)}</strong>${c.group ? ` <span class="muted" style="font-size:10px;">${escapeHtml(c.group)}</span>` : ""}</div>
        <div class="corr-track"><div class="${cls}" style="width:${w}%"></div></div>
        <div class="${valCls}" style="text-align:right;font-variant-numeric:tabular-nums;">${r >= 0 ? "+" : ""}${r.toFixed(2)}${titleSuffix}</div>
      </div>`;
    })
    .join("");
}

function renderRealismRegression(d) {
  const reg = d.regression || {};
  const ols = reg.olsModel || {};
  $("regSamplePill").textContent = `${reg.sampleSize || 0} players`;
  $("regOlsSubtitle").textContent = `OLS fit: Expected Rating = ${ols.slope ?? 0} * AvgSkill + ${ols.intercept ?? 0} (R² = ${ols.r2 ?? 0})`;
  $("regSkillBars").innerHTML = _renderSignedCorrBars(reg.skillCorrelations || []);

  const curve = reg.ageCurve || [];
  $("regAgeCurveBody").innerHTML = curve.length
    ? curve
        .map(
          (a) => `<tr>
            <td><strong>${escapeHtml(a.bracket)}</strong></td>
            <td>${a.count}</td>
            <td>${a.avgSkill}</td>
            <td>${a.avgPot}</td>
            <td class="${a.headroom >= 1.5 ? "stat-good" : ""}">+${a.headroom}</td>
            <td><strong>${a.avgRating > 0 ? a.avgRating.toFixed(3) : "-"}</strong></td>
          </tr>`
        )
        .join("")
    : '<tr><td colspan="6" class="muted">No age curve data.</td></tr>';

  const q = ($("realismFilterQ").value || "").trim().toLowerCase();
  const renderResidTable = (bodyId, list, isPos) => {
    const filtered = (list || []).filter((r) => !q || r.name.toLowerCase().includes(q) || r.teamName.toLowerCase().includes(q));
    $(bodyId).innerHTML = filtered.length
      ? filtered
          .map(
            (r) => `<tr>
              <td><a href="#" class="link-btn ps-open" data-pid="${r.playerId}">${escapeHtml(r.name)}</a> <span class="muted">(${r.age}y)</span></td>
              <td><a href="#" class="link-btn ts-open" data-tid="${r.teamId}">${escapeHtml(r.teamName)}</a></td>
              <td>${r.avgSkill}</td>
              <td class="muted">${r.expectedRating.toFixed(2)}</td>
              <td><strong>${r.actualRating.toFixed(2)}</strong></td>
              <td class="${isPos ? "stat-good" : "stat-bad"}">${r.residual >= 0 ? "+" : ""}${r.residual.toFixed(3)}</td>
            </tr>`
          )
          .join("")
      : '<tr><td colspan="6" class="muted">No matching players.</td></tr>';
    _bindStatsModalLinks($(bodyId));
  };
  renderResidTable("regOverBody", reg.overperformers, true);
  renderResidTable("regUnderBody", reg.underperformers, false);
}

function renderRealismParity(d) {
  const par = d.parity || {};
  const dist = par.distributions || {};
  const fmtVal = (k, v) => (k === "teamWages" || k === "teamBalance" ? _fmtUsd(v) : Number(v || 0).toFixed(2));
  const cards = [
    ["teamSkill", "Team Avg Skill (1-20)"],
    ["playerSkill", "All Players Avg Skill (1-20)"],
    ["teamWages", "Team Annual Payroll"],
    ["teamBalance", "Team Cash Reserves"],
  ];
  $("parityDistGrid").innerHTML = cards
    .map(([key, title]) => {
      const m = dist[key] || {};
      return `<div class="lab-box">
        <div class="lab-box-title">${escapeHtml(title)}</div>
        <div class="lab-odds-big">${(m.gini ?? 0).toFixed(3)} <span class="muted" style="font-size:12px;font-weight:500;">Gini</span></div>
        <div class="muted" style="font-size:12px;margin-top:6px;">
          P10: ${fmtVal(key, m.p10)} &bull; Med: <strong>${fmtVal(key, m.p50)}</strong> &bull; P90: ${fmtVal(key, m.p90)}<br>
          Min: ${fmtVal(key, m.min)} &bull; Max: ${fmtVal(key, m.max)} (${m.count || 0} samples)
        </div>
      </div>`;
    })
    .join("");

  $("parityTeamSample").textContent = `${par.teamSampleSize || 0} teams`;
  $("parityTeamCorrBars").innerHTML = _renderSignedCorrBars(par.teamFactorCorrelations || []);

  const nations = par.nationMeta || [];
  $("parityNationBody").innerHTML = nations.length
    ? nations
        .map(
          (n) => `<tr>
            <td><strong>${escapeHtml(n.nationName)}</strong></td>
            <td>${n.playerCount}</td>
            <td class="${n.elite16Plus >= 5 ? "stat-good" : ""}">${n.elite16Plus}</td>
            <td>${n.avgSkill}</td>
            <td>${n.avgPot}</td>
            <td>${n.avgRating > 0 ? n.avgRating.toFixed(3) : "-"}</td>
          </tr>`
        )
        .join("")
    : '<tr><td colspan="6" class="muted">No nation aggregates.</td></tr>';
}

function _bindStatsModalLinks(container) {
  if (!container) return;
  container.querySelectorAll(".ps-open").forEach((el) => {
    el.addEventListener("click", (ev) => {
      ev.preventDefault();
      openPlayerStatsModal(Number(el.dataset.pid));
    });
  });
  container.querySelectorAll(".ts-open").forEach((el) => {
    el.addEventListener("click", (ev) => {
      ev.preventDefault();
      const tid = Number(el.dataset.tid);
      if (tid > 0) openTeamStatsModal(tid);
    });
  });
}

// ==================== MANAGER HELPER LAB ====================
async function loadManagerHelper() {
  if (!state.summary?.path) return;
  const tid = $("helperTeamSelect").value;
  const targetPid = $("finderTargetPlayer").value;
  const preset = $("finderRolePreset").value || "match";
  const qs = new URLSearchParams();
  if (tid) qs.set("team_id", tid);
  if (targetPid) qs.set("target_player_id", targetPid);
  qs.set("role_preset", preset);
  try {
    const d = await api(`/api/manager-helper?${qs.toString()}`);
    state.helperData = d;
    if (!d.loaded) return;

    const teams = d.teams || [];
    const selTid = d.rosterOptimizer?.teamId ?? teams[0]?.teamId ?? "";
    populateSelect(
      $("helperTeamSelect"),
      teams.map((t) => [t.teamId, `${t.worldRank ? `#${t.worldRank} ` : ""}${t.name}${t.isUserTeam ? " (YOU)" : ""} — ${t.avgSkill}`]),
      selTid
    );

    const starters = d.rosterOptimizer?.starters || [];
    const curTarget = $("finderTargetPlayer").value;
    const keepTarget = starters.some((s) => String(s.playerId) === String(curTarget));
    const refPid = d.replacementFinder?.reference?.playerId || starters[starters.length - 1]?.playerId || "";
    populateSelect(
      $("finderTargetPlayer"),
      starters.map((s) => [s.playerId, `${s.name} (${s.bestRole}, ${s.avgSkill} avg)`]),
      keepTarget ? curTarget : refPid
    );

    renderManagerHelperTab();
  } catch (err) {
    toast(`Manager Helper load failed: ${err.message}`, "err");
  }
}

async function prepTransferFromHelper(pid, destTid) {
  document.querySelector('.tab-btn[data-tab="transfers"]')?.click();
  $("txPlayerSearch").value = String(pid);
  renderTxPlayerOptions();
  if ($("txPlayerSelect").querySelector(`option[value="${pid}"]`)) {
    $("txPlayerSelect").value = String(pid);
    await onTxPlayerChange();
  }
  if (destTid > 0) {
    $("txTeamSearch").value = "";
    renderTxTeamOptions();
    if ($("txTargetTeam").querySelector(`option[value="${destTid}"]`)) {
      $("txTargetTeam").value = String(destTid);
      await loadTargetRosterPreview();
    }
  }
  toast(`Loaded player #${pid} in Transfers tab`, "info");
}

function _bindHelperActionButtons(container, managingTid) {
  _bindStatsModalLinks(container);
  container.querySelectorAll(".btn-prep-tx").forEach((btn) => {
    btn.addEventListener("click", () => {
      prepTransferFromHelper(Number(btn.dataset.pid), managingTid);
    });
  });
}

function renderManagerHelperTab() {
  const d = state.helperData;
  if (!d || !d.loaded) return;
  renderHelperKpis(d);
  renderHelperRoster(d);
  renderHelperFinder(d);
  renderHelperMarket(d);
  renderHelperWonderkids(d);
}

function renderHelperKpis(d) {
  const ro = d.rosterOptimizer || {};
  const mr = d.marketRadar || {};
  const benchGain = ro.benched?.[0]?.upgradeVsWorstStarter || 0;
  const kpis = [
    { label: `${ro.name || "Team"} Active Avg`, val: ro.avgSkill ?? "-", sub: `${ro.worldRank ? `World #${ro.worldRank} • ` : ""}${ro.mainLanguageName || ""} • ${ro.hiringBiasLabel || "Open"}` },
    { label: "Cash / Payroll", val: _fmtUsd(ro.balance), sub: `Annual wages: ${_fmtUsd(ro.annualWages)}` },
    { label: "Best Bench Delta", val: benchGain > 0 ? `+${benchGain}` : "Optimal", sub: `${ro.benched?.length || 0} benched player(s)` },
    { label: "Market Bargains / FAs", val: `${(mr.bargains || []).length} / ${(mr.freeAgents || []).length}`, sub: `${(mr.expiring || []).length} expiring <=12m` },
    { label: "U21 Wonderkids", val: (d.wonderkids || []).length, sub: `Top pot: ${d.wonderkids?.[0]?.avgPot ?? "-"}` },
  ];
  $("helperKpiGrid").innerHTML = kpis
    .map(
      (k) => `<div class="kpi-card">
        <div class="kpi-label">${escapeHtml(k.label)}</div>
        <div class="kpi-val">${escapeHtml(k.val)}</div>
        <div class="kpi-sub">${escapeHtml(k.sub)}</div>
      </div>`
    )
    .join("");
}

function renderHelperRoster(d) {
  const ro = d.rosterOptimizer || {};
  $("helperOptTitle").textContent = `${ro.name || "Team"} — GM Diagnostics & Lineup Audit`;
  $("helperPolicyPill").textContent = `Main: ${ro.mainLanguageName || "-"} • ${ro.hiringBiasLabel || "Open"}`;
  $("helperAlertsList").innerHTML = (ro.alerts || [])
    .map(
      (a) => `<div class="bug-cause-card ${escapeHtml(a.severity || "info")}">
        <div class="bug-cause-title">${escapeHtml(a.title)}</div>
        <div class="bug-cause-desc">${escapeHtml(a.detail)}</div>
      </div>`
    )
    .join("");

  const q = ($("helperFilterQ").value || "").trim().toLowerCase();
  const combined = [
    ...(ro.starters || []).map((r, i) => ({ ...r, _isBench: false, _weakest: i === (ro.starters || []).length - 1 })),
    ...(ro.benched || []).map((r) => ({ ...r, _isBench: true, _weakest: false })),
  ].filter((r) => !q || r.name.toLowerCase().includes(q) || r.languages.toLowerCase().includes(q));

  $("helperSquadCount").textContent = `${ro.starters?.length || 0} active / ${ro.benched?.length || 0} bench`;
  $("helperRosterBody").innerHTML = combined.length
    ? combined
        .map((r) => {
          const badges = [
            r._isBench ? '<span class="tag-pill warn">Bench</span>' : '<span class="tag-pill ok">Starter</span>',
            r._weakest ? '<span class="tag-pill info">Floor</span>' : "",
            r.isCurrentIgl ? '<span class="tag-pill info">IGL</span>' : "",
            r.isCurrentAwp ? '<span class="tag-pill info">AWP</span>' : "",
            !r.speaksMainLang ? '<span class="tag-pill err">No Lang</span>' : "",
            !r.policyOk ? '<span class="tag-pill err">Policy!</span>' : "",
          ].join("");
          const btnTxt = r._isBench ? "Promote" : "Find Sub";
          return `<tr>
            <td><a href="#" class="link-btn ps-open" data-pid="${r.playerId}">${escapeHtml(r.name)}</a> <span class="muted">(${r.age}y)</span></td>
            <td>${badges}</td>
            <td>${escapeHtml(r.bestRole)}</td>
            <td><strong>${r.avgSkill}</strong> <span class="muted">(${r.avgPot})</span></td>
            <td class="muted">${r.iglScore} / ${r.awpScore}</td>
            <td style="font-size:11.5px;">${escapeHtml(r.languages)}</td>
            <td>${_fmtUsd(r.salaryYear)}</td>
            <td><button class="btn btn-sm helper-row-act" data-pid="${r.playerId}" data-bench="${r._isBench ? 1 : 0}">${btnTxt}</button></td>
          </tr>`;
        })
        .join("")
    : '<tr><td colspan="8" class="muted">No matching players.</td></tr>';

  _bindStatsModalLinks($("helperRosterBody"));
  $("helperRosterBody").querySelectorAll(".helper-row-act").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const pid = Number(btn.dataset.pid);
      if (btn.dataset.bench === "1") {
        await api(`/api/player/${pid}/bench`, { method: "POST", body: JSON.stringify({ benched: false, autoTactics: true }) });
        toast(`Promoted player #${pid} & recalculated tactics`, "ok");
        await refreshSummaryOnly();
        await loadManagerHelper();
      } else {
        $("finderTargetPlayer").value = String(pid);
        $("finderRolePreset").value = "match";
        document.querySelector('.subtab-btn[data-hsubtab="finder"]')?.click();
        await loadManagerHelper();
      }
    });
  });

  const maps = ro.mapComforts || [];
  $("helperMapBars").innerHTML = maps.length
    ? maps
        .map((m) => {
          const c = Number(m.comfort || 0);
          const barCls = c >= 75 ? "corr-fill-pos" : c < 55 ? "corr-fill-neg" : "h2h-fill-b";
          return `<div class="corr-row">
            <div><strong>${escapeHtml(m.name)}</strong></div>
            <div class="corr-track"><div class="${barCls}" style="width:${c}%"></div></div>
            <div class="${c >= 75 ? "stat-good" : c < 55 ? "stat-bad" : ""}" style="text-align:right;"><strong>${c}</strong>/100</div>
          </div>`;
        })
        .join("")
    : '<div class="muted">No map pool comfort data.</div>';
}

function renderHelperFinder(d) {
  const ff = d.replacementFinder || {};
  const ref = ff.reference || {};
  const avail = $("finderAvailFilter").value || "all";
  const q = ($("helperFilterQ").value || "").trim().toLowerCase();
  const managingTid = Number(d.rosterOptimizer?.teamId || 0);

  $("finderRefSubtitle").textContent = `Reference: ${ref.name || "-"} (${ref.bestRole || "-"}, ${ref.avgSkill ?? "-"} avg) • Ranked by skill upgrade, 18-skill cosine similarity, language & availability`;

  const rows = (ff.candidates || []).filter((r) => {
    if (avail === "fa_exp" && !(r.isFreeAgent || r.monthsLeft <= 12.5)) return false;
    if (avail === "benched_fa" && !(r.isFreeAgent || r.benched)) return false;
    if (avail === "lang_safe" && !r.speaksMainLang) return false;
    if (avail === "policy_safe" && !r.policyOk) return false;
    if (q && !r.name.toLowerCase().includes(q) && !r.teamName.toLowerCase().includes(q) && !r.languages.toLowerCase().includes(q)) return false;
    return true;
  });

  $("finderCount").textContent = `${rows.length} targets`;
  $("finderTableBody").innerHTML = rows.length
    ? rows
        .map((r) => {
          const deltaCls = r.skillDelta > 0 ? "stat-good" : r.skillDelta < 0 ? "stat-bad" : "";
          const langTag = r.speaksMainLang ? '<span class="tag-pill ok">Main Lang</span>' : '<span class="tag-pill warn">Foreign</span>';
          const polTag = r.policyOk ? "" : '<span class="tag-pill err">Policy!</span>';
          const statusTag = r.isFreeAgent ? '<span class="tag-pill ok">Free Agent</span>' : r.benched ? '<span class="tag-pill warn">Benched</span>' : "";
          return `<tr>
            <td><a href="#" class="link-btn ps-open" data-pid="${r.playerId}">${escapeHtml(r.name)}</a> <span class="muted">(${r.age}y, ${escapeHtml(r.nationName)})</span></td>
            <td>${r.teamId > 0 ? `<a href="#" class="link-btn ts-open" data-tid="${r.teamId}">${escapeHtml(r.teamName)}</a>` : '<span class="muted">Free Agent</span>'} ${statusTag}</td>
            <td>${escapeHtml(r.bestRole)}</td>
            <td><strong>${r.avgSkill}</strong> <span class="muted">(${r.avgPot})</span></td>
            <td class="${deltaCls}">${r.skillDelta >= 0 ? "+" : ""}${r.skillDelta}</td>
            <td><strong>${r.similarityPct}%</strong></td>
            <td>${r.salaryYear > 0 ? _fmtUsd(r.salaryYear) : "$0"} <span class="muted">(${r.isFreeAgent ? "FA" : `${r.monthsLeft}m`})</span></td>
            <td>${langTag}${polTag}<div class="muted" style="font-size:10.5px;">${escapeHtml(r.languages)}</div></td>
            <td><button class="btn btn-sm btn-blue btn-prep-tx" data-pid="${r.playerId}">Prep Sign</button></td>
          </tr>`;
        })
        .join("")
    : '<tr><td colspan="9" class="muted">No candidates match filters.</td></tr>';
  _bindHelperActionButtons($("finderTableBody"), managingTid);
}

function renderHelperMarket(d) {
  const mode = $("marketFilterMode").value || "bargains";
  const q = ($("helperFilterQ").value || "").trim().toLowerCase();
  const managingTid = Number(d.rosterOptimizer?.teamId || 0);
  const raw = d.marketRadar?.[mode] || [];
  const rows = raw.filter(
    (r) => !q || r.name.toLowerCase().includes(q) || r.teamName.toLowerCase().includes(q) || (r.languages || "").toLowerCase().includes(q)
  );
  $("marketCount").textContent = `${rows.length} players`;
  $("marketTableBody").innerHTML = rows.length
    ? rows
        .map((r) => {
          const status = r.isFreeAgent
            ? '<span class="tag-pill ok">Free Agent</span>'
            : r.benched
              ? '<span class="tag-pill warn">Benched</span>'
              : r.monthsLeft <= 6
                ? '<span class="tag-pill err">Expiring</span>'
                : r.ratio <= 0.72
                  ? '<span class="tag-pill ok">Bargain</span>'
                  : '<span class="tag-pill">Active</span>';
          const ratioCls = r.ratio > 0 && r.ratio <= 0.72 ? "stat-good" : r.ratio >= 1.55 ? "stat-bad" : "";
          return `<tr>
            <td><a href="#" class="link-btn ps-open" data-pid="${r.playerId}">${escapeHtml(r.name)}</a> <span class="muted">(${r.age}y &bull; ${escapeHtml(r.bestRole || "")})</span></td>
            <td>${r.teamId > 0 ? `<a href="#" class="link-btn ts-open" data-tid="${r.teamId}">${escapeHtml(r.teamName)}</a>` : '<span class="muted">Free Agent</span>'}</td>
            <td><strong>${r.avgSkill}</strong> <span class="muted">(${r.avgPot ?? r.avgSkill})</span></td>
            <td>${r.yearRating > 0 ? r.yearRating.toFixed(2) : "-"}</td>
            <td>${_fmtUsd(r.salaryYear)}</td>
            <td class="muted">${_fmtUsd(r.peerMedianSalary)}</td>
            <td class="${ratioCls}">${r.isFreeAgent ? "0.00x" : `${r.ratio.toFixed(2)}x`}</td>
            <td>${escapeHtml(r.endDate)} ${r.isFreeAgent ? "" : `<span class="muted">(${r.monthsLeft}m)</span>`}</td>
            <td>${status} <button class="btn btn-sm btn-prep-tx" data-pid="${r.playerId}">Sign</button></td>
          </tr>`;
        })
        .join("")
    : '<tr><td colspan="9" class="muted">No matching contracts in this view.</td></tr>';
  _bindHelperActionButtons($("marketTableBody"), managingTid);
}

function renderHelperWonderkids(d) {
  const mode = $("wonderkidFilterMode").value || "all";
  const q = ($("helperFilterQ").value || "").trim().toLowerCase();
  const managingTid = Number(d.rosterOptimizer?.teamId || 0);
  const rows = (d.wonderkids || []).filter((r) => {
    if (mode === "fa_exp" && !(r.isFreeAgent || r.monthsLeft <= 12.5)) return false;
    if (mode === "high_headroom" && r.headroom < 2.0) return false;
    if (mode === "lang_safe" && !r.speaksMainLang) return false;
    if (q && !r.name.toLowerCase().includes(q) && !r.teamName.toLowerCase().includes(q) && !r.nationName.toLowerCase().includes(q) && !r.languages.toLowerCase().includes(q)) return false;
    return true;
  });
  $("wonderkidCount").textContent = `${rows.length} gems`;
  $("wonderkidTableBody").innerHTML = rows.length
    ? rows
        .map((r) => {
          const teamCell = r.isFreeAgent
            ? '<span class="tag-pill ok">Free Agent</span>'
            : `<a href="#" class="link-btn ts-open" data-tid="${r.teamId}">${escapeHtml(r.teamName)}</a>${r.benched ? ' <span class="tag-pill warn">Bench</span>' : ""}`;
          return `<tr>
            <td><a href="#" class="link-btn ps-open" data-pid="${r.playerId}">${escapeHtml(r.name)}</a> <span class="muted">(${r.age}y)</span></td>
            <td>${escapeHtml(r.nationName)}</td>
            <td>${teamCell}</td>
            <td>${escapeHtml(r.bestRole)}</td>
            <td><strong>${r.avgSkill}</strong></td>
            <td class="stat-good"><strong>${r.avgPot}</strong></td>
            <td class="${r.headroom >= 2.0 ? "stat-good" : ""}">+${r.headroom}</td>
            <td>${r.salaryYear > 0 ? _fmtUsd(r.salaryYear) : "$0"} <span class="muted">(${r.isFreeAgent ? "FA" : `${r.monthsLeft}m`})</span></td>
            <td><button class="btn btn-sm btn-blue btn-prep-tx" data-pid="${r.playerId}">Scout/Sign</button></td>
          </tr>`;
        })
        .join("")
    : '<tr><td colspan="9" class="muted">No U21 wonderkids match filter.</td></tr>';
  _bindHelperActionButtons($("wonderkidTableBody"), managingTid);
}

// ==================== GOD MODE LAB ====================
async function loadGodMode() {
  if (!state.summary?.path && !state.summary?.filename) return;
  try {
    const d = await api("/api/god-mode/state");
    state.godModeData = d;
    if (!d.loaded) return;

    const teams = d.teams || [];
    const curNerfTid = $("godNerfTeam").value || (teams.find((t) => t.isUserTeam)?.teamId ?? teams[0]?.teamId ?? "");
    populateSelect(
      $("godNerfTeam"),
      teams.map((t) => [t.teamId, `${t.worldRank ? `#${t.worldRank} ` : ""}${t.name}${t.isUserTeam ? " (YOU)" : ""} — ${t.avgSkill} avg`]),
      curNerfTid
    );
    if (d.defaultProtectedStar) {
      $("godProtectedNames").placeholder = `e.g. ${d.defaultProtectedStar}`;
      $("godNerfProtected").placeholder = `e.g. ${d.defaultProtectedStar}`;
    }

    const s = d.snapshot || {};
    const kpis = [
      { label: `${s.userTeamName || "Focus"} Avg Skill`, val: s.userAvgSkill ?? "-", sub: `Weakest floor: ${s.userFloor ?? "-"}` },
      { label: "Top-10 Rival Avg", val: s.top10AvgSkill ?? "-", sub: `Top-20 Avg: ${s.top20AvgSkill ?? "-"}` },
      { label: "Top-10 Skill Spread", val: s.top10Spread ?? "-", sub: `Max minus #10 floor` },
      { label: "Top-10 Parity Gini", val: s.top10Gini ?? "-", sub: "Lower = closer Tier-1 parity" },
      { label: "AI Bench Sabotages", val: s.aiBenchSabotagesTop20 ?? 0, sub: "Top-20 AI teams benching better player" },
    ];
    $("godKpiGrid").innerHTML = kpis
      .map(
        (k) => `<div class="kpi-card">
          <div class="kpi-label">${escapeHtml(k.label)}</div>
          <div class="kpi-val">${escapeHtml(k.val)}</div>
          <div class="kpi-sub">${escapeHtml(k.sub)}</div>
        </div>`
      )
      .join("");
  } catch (err) {
    toast(`God Mode load failed: ${err.message}`, "err");
  }
}

function _collectGodModeParams(action) {
  if (action === "boost_floor_parity") {
    const val = Number($("godBoostFloor").value || 15.8);
    return {
      scope: $("godBoostScope").value,
      mode: $("godBoostMode").value,
      targetFloor: val,
      smoothTarget: val,
      strengthPct: Number($("godBoostStrength").value || 75),
      boostDelta: Number($("godBoostDelta").value || 1.2),
      protectUserTeam: $("godProtectUser").checked,
      protectedNames: $("godProtectedNames").value,
    };
  }
  if (action === "nerf_superteam_keep_stars") {
    return {
      teamId: Number($("godNerfTeam").value || 0),
      targetAvg: Number($("godNerfTargetAvg").value || 16.2),
      capNonProtected: Number($("godNerfCapNon").value || 17.0),
      protectedNames: $("godNerfProtected").value,
    };
  }
  if (action === "fix_ai_sabotage") {
    return {
      scope: $("godAiScope").value,
      fixBench: $("godAiFixBench").checked,
      minMapComfort: Number($("godAiMapComfort").value || 0),
      syncLanguages: $("godAiSyncLang").checked,
      minStaffSkill: Number($("godAiMinStaff").value || 0),
      applyBurnoutToTopTeams: $("godAiBurnout").checked,
    };
  }
  if (action === "rebalance_economy") {
    return {
      scope: $("godEconScope").value,
      minBalance: Number($("godEconMinBal").value || 0),
      maxBalanceCap: Number($("godEconMaxCap").value || 0),
      minFacilityLevel: Number($("godEconMinFac").value || 0),
    };
  }
  if (action === "inject_wonderkids") {
    return {
      count: Number($("godWkCount").value || 10),
      maxAge: Number($("godWkMaxAge").value || 18),
      nationMode: $("godWkNation").value,
      assignMode: $("godWkAssign").value,
    };
  }
  return {};
}

async function runGodModeAction(action, dryRun) {
  if (!state.summary?.path && !state.summary?.filename) {
    toast("Load a save file first.", "err");
    return;
  }
  try {
    const res = await api("/api/god-mode/apply", {
      method: "POST",
      body: JSON.stringify({
        action,
        params: _collectGodModeParams(action),
        dryRun,
      }),
    });
    const b = res.before || {};
    const a = res.after || {};
    const tag = res.dryRun ? "PREVIEW (Not Applied Yet)" : "APPLIED TO MEMORY (Click Save to Write)";
    $("godResultCount").textContent = `${res.changeCount || 0} changes (${res.dryRun ? "Dry Run" : "Live"})`;
    $("godResultBanner").className = `verdict-banner ${res.dryRun ? "warn" : "ok"}`;
    $("godResultBanner").innerHTML = `<div class="verdict-headline">${tag} — ${escapeHtml(res.summary || "")}</div>
      <div>
        <strong>${escapeHtml(a.userTeamName || "Focus")}:</strong> ${b.userAvgSkill} &rarr; <strong>${a.userAvgSkill}</strong> avg (floor ${b.userFloor} &rarr; ${a.userFloor}) &bull;
        <strong>Top-10 Avg:</strong> ${b.top10AvgSkill} &rarr; <strong>${a.top10AvgSkill}</strong> &bull;
        <strong>Top-10 Spread:</strong> ${b.top10Spread} &rarr; <strong>${a.top10Spread}</strong> &bull;
        <strong>AI Bench Bugs:</strong> ${b.aiBenchSabotagesTop20} &rarr; <strong>${a.aiBenchSabotagesTop20}</strong>
      </div>`;

    const rows = res.changes || [];
    $("godResultTableBody").innerHTML = rows.length
      ? rows
          .map(
            (c) => `<tr>
              <td><strong>${escapeHtml(c.target)}</strong></td>
              <td>${escapeHtml(c.team)}</td>
              <td>${escapeHtml(c.detail)}</td>
            </tr>`
          )
          .join("")
      : '<tr><td colspan="3" class="muted">No adjustments were needed for the chosen thresholds.</td></tr>';

    if (!res.dryRun) {
      toast(`${res.summary}`, "ok");
      await refreshSummaryOnly();
      await refreshAllViews();
      await loadGodMode();
    } else {
      toast(`Previewed ${res.changeCount} change(s) — click Apply to commit to memory`, "info");
    }
  } catch (err) {
    toast(`God Mode error: ${err.message}`, "err");
  }
}

async function init() {
  bindEvents();
  try {
    state.meta = await api("/api/meta");
    state.summary = await api("/api/summary");
    await refreshSavePicker();
    renderStatusBar();
    if (state.summary && state.summary.path) {
      await refreshAllViews();
    }
  } catch (err) {
    toast(`Startup error: ${err.message}`, "err");
  }
}

init();
