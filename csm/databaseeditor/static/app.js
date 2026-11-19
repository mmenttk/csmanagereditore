/* CS Manager Database, Tournament Schedule, GameBalance & Weapons Studio */

const state = {
  meta: null,
  summary: null,
  teams: [],
  selectedTeamId: null,
  players: [],
  allPlayersBrief: [],
  selectedPlayerId: null,
  selectedPlayerData: null,
  playerSubTab: "basics",
  staff: [],
  selectedStaffId: null,
  staffSubTab: "basics",
  tournaments: [],
  selectedTemplate: null,
  schedule: null,
  dsBalance: null,
  weaponsPack: null,
  selectedWeaponId: null,
  balancePack: null,
  godMode: null,
  godModeResult: null,
};

const $ = (id) => document.getElementById(id);

function escapeHtml(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function toast(msg, type = "ok") {
  const el = $("toast");
  el.textContent = msg;
  el.className = `toast show ${type}`;
  clearTimeout(el._t);
  el._t = setTimeout(() => { el.className = "toast"; }, 3200);
}

async function apiGet(url) {
  const r = await fetch(url);
  const data = await r.json();
  if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`);
  return data;
}

async function apiPost(url, body = {}) {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await r.json();
  if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`);
  return data;
}

function openModal(title, html, wide = false) {
  $("modalTitle").textContent = title;
  $("modalBody").innerHTML = html;
  $("modalCard").classList.toggle("wide", !!wide);
  $("modalBackdrop").classList.add("open");
}

function closeModal() {
  $("modalBackdrop").classList.remove("open");
  $("modalCard").classList.remove("wide");
}

// ------------------------------------------------------------------
// Custom Logos / Icons Browser & Folder Importer
// ------------------------------------------------------------------

function logoImgUrl(kind, key) {
  if (!key) return "";
  return `/api/logo-img/${encodeURIComponent(kind)}/${encodeURIComponent(key)}`;
}

function logoImgHtml(kind, key, cls = "logo-thumb", idAttr = "") {
  const url = logoImgUrl(kind, key);
  const idPart = idAttr ? `id="${idAttr}"` : "";
  if (!url) return `<img ${idPart} class="${cls}" src="" style="display:none;" alt="" />`;
  return `<img ${idPart} class="${cls}" src="${url}" onerror="this.style.visibility='hidden'" onload="this.style.visibility='visible';this.style.display='inline-block'" alt="${escapeHtml(key)}" />`;
}

function updateLogoPreview(kind, key, previewId) {
  const img = $(previewId);
  if (!img) return;
  const k = (key || "").trim();
  if (!k) { img.style.display = "none"; img.removeAttribute("src"); return; }
  img.style.display = "inline-block";
  img.style.visibility = "visible";
  img.src = logoImgUrl(kind, k) + `?v=${Date.now()}`;
}

async function triggerLogoFolderImport(kind, onDone) {
  try {
    const res = await apiPost("/api/logos/import-folder", { kind, syncGlobal: true });
    if (res.ok) {
      toast(`Imported ${res.importedCount} ${kind} images! (${res.totalAvailable} total available)`);
      if (onDone) onDone(res);
      return;
    }
    if (res.cancelled && !res.unsupported) return;
    // Fallback for remote/non-tkinter browser: HTML5 directory upload
    const inp = $("logoFolderFileInput");
    inp.value = "";
    inp.onchange = async () => {
      const files = Array.from(inp.files || []).filter((f) => /\.(png|jpe?g|webp|bmp|gif)$/i.test(f.name));
      if (!files.length) { toast("No image files found in selected folder.", "err"); return; }
      const payload = [];
      for (const f of files.slice(0, 600)) {
        const b64 = await new Promise((resolve) => {
          const r = new FileReader();
          r.onload = () => resolve(String(r.result || "").split(",")[1] || "");
          r.readAsDataURL(f);
        });
        payload.push({ name: f.name, dataBase64: b64 });
      }
      const up = await apiPost("/api/logos/upload", { kind, files: payload, syncGlobal: true });
      toast(`Uploaded ${up.importedCount} ${kind} images!`);
      if (onDone) onDone(up);
    };
    inp.click();
  } catch (err) {
    toast(err.message, "err");
  }
}

async function openLogoPickerModal(kind, targetInputId, previewImgId, onPicked) {
  try {
    const logos = await apiGet(`/api/logos?kind=${encodeURIComponent(kind)}`);
    const curVal = ($(targetInputId)?.value || "").trim().toLowerCase();
    const labelMap = { team: "Team Logos", tournament: "Tournament Logos", sponsor: "Sponsor Logos", weapon_icon: "Weapon Icons", weapon_skin: "Weapon Skins" };
    openModal(`Pick or Import — ${labelMap[kind] || kind} (${logos.length})`, `
      <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;">
        <input id="logoPickerSearch" placeholder="Search logo key..." style="flex:1;min-width:180px;" />
        <button class="btn primary sm" id="btnModalImportLogoFolder">Import From Folder...</button>
      </div>
      <div id="logoPickerGrid" class="logo-grid"></div>
    `, true);

    const renderGrid = () => {
      const q = ($("logoPickerSearch").value || "").trim().toLowerCase();
      const filtered = logos.filter((l) => !q || l.stem.toLowerCase().includes(q)).slice(0, 240);
      $("logoPickerGrid").innerHTML = filtered.map((l) => `
        <div class="logo-card ${l.stem.toLowerCase() === curVal ? "selected" : ""}" data-stem="${escapeHtml(l.stem)}">
          <img src="${l.url}" loading="lazy" alt="${escapeHtml(l.stem)}" />
          <div class="stem">${escapeHtml(l.stem)}</div>
          <div class="src">${escapeHtml(l.source)}</div>
        </div>
      `).join("") || `<div class="muted" style="grid-column:1/-1;padding:18px;text-align:center;">No logos found. Click "Import From Folder..." to import PNG/JPG/WEBP images.</div>`;

      $("logoPickerGrid").querySelectorAll(".logo-card").forEach((card) => {
        card.addEventListener("click", () => {
          const stem = card.dataset.stem;
          if ($(targetInputId)) $(targetInputId).value = stem;
          if (previewImgId) updateLogoPreview(kind, stem, previewImgId);
          closeModal();
          if (onPicked) onPicked(stem);
        });
      });
    };

    $("logoPickerSearch").addEventListener("input", renderGrid);
    $("btnModalImportLogoFolder").addEventListener("click", () => {
      triggerLogoFolderImport(kind, () => openLogoPickerModal(kind, targetInputId, previewImgId, onPicked));
    });
    renderGrid();
  } catch (err) {
    toast(err.message, "err");
  }
}

function tierBadge(tier) {
  if (!tier) return `<span class="tag-pill c-tier">C-Tier</span>`;
  const cls =
    tier.engineTier === 5 ? "major"
    : tier.engineTier === 4 ? "s-tier"
    : tier.engineTier === 3 ? "a-tier"
    : tier.engineTier === 2 ? "b-tier"
    : "c-tier";
  return `<span class="tag-pill ${cls}">${escapeHtml(tier.label || tier.subCode)}</span>`;
}

function optionsHtml(mapObj, selectedVal) {
  return Object.entries(mapObj)
    .sort((a, b) => Number(a[0]) - Number(b[0]))
    .map(([k, v]) => `<option value="${escapeHtml(k)}" ${String(k) === String(selectedVal) ? "selected" : ""}>${escapeHtml(v)}</option>`)
    .join("");
}

function nationOptionsHtml(selectedVal) {
  return Object.entries(state.meta?.nations || {})
    .sort((a, b) => String(a[1]).localeCompare(String(b[1])))
    .map(([k, v]) => `<option value="${k}" ${String(k) === String(selectedVal) ? "selected" : ""}>${escapeHtml(v)}</option>`)
    .join("");
}

function teamSelectOptionsHtml(selectedTeamId, includeFree = true) {
  const opts = includeFree ? [`<option value="0" ${!selectedTeamId ? "selected" : ""}>Free Agent (0)</option>`] : [];
  for (const t of state.teams) {
    opts.push(`<option value="${t.id}" ${Number(t.id) === Number(selectedTeamId) ? "selected" : ""}>${escapeHtml(t.name)} (#${t.id})</option>`);
  }
  return opts.join("");
}

function updateTopbar() {
  const s = state.summary;
  if (!s) return;
  const packs = s.packs || { databases: [], gameBalances: [], weapons: [] };

  $("dbPackSelect").innerHTML = (packs.databases || [])
    .map((p) => `<option value="${escapeHtml(p.path)}" ${p.path === s.dbDir ? "selected" : ""}>${escapeHtml(p.name)}</option>`)
    .join("");

  $("balancePackSelect").innerHTML = (packs.gameBalances || [])
    .map((p) => `<option value="${escapeHtml(p.path)}" ${p.name === s.balanceName ? "selected" : ""}>${escapeHtml(p.name)}</option>`)
    .join("");

  $("weaponsPackSelect").innerHTML = (packs.weapons || [])
    .map((p) => `<option value="${escapeHtml(p.path)}" ${p.name === s.weaponsName ? "selected" : ""}>${escapeHtml(p.name)}</option>`)
    .join("");

  $("dbStatusBadge").textContent = s.loaded ? `DB: ${s.dbName}` : "No DB Loaded";
  $("dirtyDbBadge").style.display = (s.dirtyDb || s.dirtyBalance || s.dirtyWeapons) ? "inline-block" : "none";
}

function switchTab(tabKey) {
  document.querySelectorAll(".tab-btn").forEach((b) => b.classList.toggle("active", b.dataset.tab === tabKey));
  document.querySelectorAll(".tab-panel").forEach((p) => p.classList.toggle("active", p.id === `tab-${tabKey}`));
  if (tabKey === "overview") refreshOverview();
  if (tabKey === "teams") loadTeamsList();
  if (tabKey === "players") loadPlayersList();
  if (tabKey === "staff") { loadStaffList(); loadSponsors(); }
  if (tabKey === "tournaments") loadTournamentsList();
  if (tabKey === "schedule") loadScheduleAudit();
  if (tabKey === "datascience") loadDbBalanceScience();
  if (tabKey === "mods") { loadWeaponsLab(); loadBalanceLab(); }
  if (tabKey === "godmode") loadGodMode();
  if (tabKey === "legend") renderLegendTab();
}

// ------------------------------------------------------------------
// TAB 1: Overview & Validator
// ------------------------------------------------------------------

async function refreshOverview(autoFix = false) {
  try {
    state.summary = await apiGet("/api/summary");
    updateTopbar();
    const s = state.summary;
    if (!s.loaded) {
      $("ovKpis").innerHTML = `<div class="subcard">Select a database folder from the top bar or click <strong>Browse Folder...</strong>.</div>`;
      return;
    }
    const c = s.counts || {};
    const ov = s.overlapSummary || {};
    const val = autoFix ? await apiPost("/api/validate-db", { autoFix: true }) : await apiPost("/api/validate-db", { autoFix: false });
    if (autoFix && val.fixesApplied > 0) {
      toast(`Applied ${val.fixesApplied} safe DB fixes!`, "ok");
      state.summary = await apiGet("/api/summary");
      updateTopbar();
    }

    $("ovKpis").innerHTML = [
      { l: "Teams", v: c.teams, s: "Organizations" },
      { l: "Players / FAs", v: `${c.players} / ${c.freeAgents}`, s: `${c.playerContracts} contracts` },
      { l: "Staff / Sponsors", v: `${c.staffers} / ${c.sponsors}`, s: `${c.staffContracts} staff contracts` },
      { l: "Active Tournaments", v: `${c.activeTournaments} / ${c.tournaments}`, s: `${c.stages} total stages` },
      { l: "Schedule Conflicts", v: ov.totalConflicts || 0, s: `${ov.criticalConflicts || 0} Critical · ${ov.lanConflicts || 0} LAN`, cls: (ov.criticalConflicts || 0) > 0 ? "bad" : "ok" },
      { l: "Integrity Issues", v: val.issueCount || 0, s: `${val.errorCount || 0} Errors · ${val.warningCount || 0} Warn`, cls: (val.errorCount || 0) > 0 ? "bad" : "ok" },
    ].map((k) => `<div class="kpi"><div class="kpi-lbl">${k.l}</div><div class="kpi-val ${k.cls || ""}">${escapeHtml(k.v)}</div><div class="kpi-sub">${escapeHtml(k.s)}</div></div>`).join("");

    const tiers = c.tournamentTiers || {};
    const maxT = Math.max(1, ...Object.values(tiers));
    $("ovTierBreakdown").innerHTML = Object.entries(tiers).map(([lbl, cnt]) => `
      <div style="margin-bottom:9px;">
        <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:3px;">
          <strong>${escapeHtml(lbl)}</strong><span class="mono">${cnt} events</span>
        </div>
        <div style="height:8px;background:#0c121d;border-radius:4px;overflow:hidden;">
          <div style="height:100%;width:${(cnt / maxT) * 100}%;background:var(--accent);"></div>
        </div>
      </div>
    `).join("");

    $("ovValSummary").textContent = `${val.errorCount} Errors, ${val.warningCount} Warnings (${val.issueCount} total)`;
    $("ovValTable").innerHTML = val.issues.length
      ? val.issues.map((it) => `<tr><td><span class="tag-pill ${it.severity === "error" ? "err" : "warn"}">${escapeHtml(it.severity.toUpperCase())}</span></td><td>${escapeHtml(it.category)}</td><td>${escapeHtml(it.detail)}</td></tr>`).join("")
      : `<tr><td colspan="3" class="ok" style="text-align:center;padding:16px;">No integrity issues found!</td></tr>`;
  } catch (err) {
    toast(err.message, "err");
  }
}

// ------------------------------------------------------------------
// TAB 2: Teams
// ------------------------------------------------------------------

async function loadTeamsList() {
  try {
    const q = encodeURIComponent($("teamSearch").value || "");
    const reg = encodeURIComponent($("teamRegionFilter").value || "");
    state.teams = await apiGet(`/api/teams?q=${q}&region=${reg}`);
    $("teamList").innerHTML = state.teams.map((t) => `
      <div class="list-row ${Number(t.id) === Number(state.selectedTeamId) ? "selected" : ""}" onclick="selectTeam(${t.id})">
        <div style="display:flex;align-items:center;gap:8px;">
          ${logoImgHtml("team", t.logo)}
          <div>
            <strong>${escapeHtml(t.name)}</strong> <span class="muted mono">#${t.id}</span>
            <div class="muted" style="font-size:11px;">${escapeHtml(t.nationName)} · Rep ${t.reputation} · ${escapeHtml(t.hiringBiasName)}</div>
          </div>
        </div>
        <div style="text-align:right;">
          <div class="mono" style="font-weight:700;">${t.avgSkill.toFixed(1)} sk</div>
          <div class="muted" style="font-size:11px;">${t.rosterCount}+${t.benchCount}B · ${t.rankingPoints} pts</div>
        </div>
      </div>
    `).join("") || `<div class="muted" style="padding:14px;">No teams match filter.</div>`;
  } catch (err) {
    toast(err.message, "err");
  }
}

async function selectTeam(teamId) {
  state.selectedTeamId = teamId;
  loadTeamsList();
  try {
    const d = await apiGet(`/api/team?id=${teamId}`);
    const t = d.team;
    const tf = t.teamFinances || {};
    const owner = t.owner || {};
    const pts = (t.rankingPoints || []).reduce((acc, r) => acc + (r.currentPoints || 0), 0);

    $("teamEditorCard").innerHTML = `
      <div class="card-head">
        <div style="display:flex;align-items:center;gap:10px;">
          ${logoImgHtml("team", t.logo, "logo-thumb logo-thumb-lg", "edTeamLogoPrev")}
          <div>
            <span class="card-title">${escapeHtml(t.name)}</span>
            <span class="tag-pill info mono">ID #${t.id}</span>
          </div>
        </div>
        <div style="display:flex;gap:6px;">
          <button class="btn ok sm" onclick="saveSelectedTeam(${t.id})">Save Team</button>
          <button class="btn danger sm" onclick="deleteSelectedTeam(${t.id})">Delete Team</button>
        </div>
      </div>
      <div class="form-grid">
        <div class="field"><label>Team Name</label><input id="edTeamName" value="${escapeHtml(t.name)}" /></div>
        <div class="field"><label>Logo Key</label>
          <div class="logo-field-wrap">
            <input id="edTeamLogo" value="${escapeHtml(t.logo)}" oninput="updateLogoPreview('team', this.value, 'edTeamLogoPrev')" />
            <button type="button" class="btn sm" onclick="openLogoPickerModal('team', 'edTeamLogo', 'edTeamLogoPrev')">Pick/Import</button>
          </div>
        </div>
        <div class="field"><label>Nation</label><select id="edTeamNation">${nationOptionsHtml(t.nation)}</select></div>
        <div class="field"><label>Reputation (1-20)</label><input id="edTeamRep" type="number" min="1" max="20" value="${t.reputation}" /></div>
        <div class="field"><label>Starting Ranking Points</label><input id="edTeamPts" type="number" min="0" value="${Math.round(pts)}" /></div>
        <div class="field"><label>Pro Status</label><select id="edTeamPro">${optionsHtml(state.meta.professionalStatus, t.professionalStatus)}</select></div>
        <div class="field"><label>Owner Name</label><input id="edTeamOwner" value="${escapeHtml(owner.name || "")}" /></div>
        <div class="field"><label>Hiring Bias</label><select id="edTeamBias">${optionsHtml(state.meta.hiringBias, owner.hiringBias ?? 7)}</select></div>
        <div class="field"><label>Main Language</label><select id="edTeamLang">${optionsHtml(state.meta.languages, t.teamCohesion?.mainLanguage || 13)}</select></div>
        <div class="field"><label>Starting Balance ($)</label><input id="edTeamBal" type="number" value="${tf.currentBalance || 0}" /></div>
        <div class="field"><label>Owner Tier (1-20)</label><input id="edTeamOwnTier" type="number" step="0.5" min="1" max="20" value="${tf.ownerContribution || 1}" /></div>
        <div class="field"><label>Merch Tier (1-20)</label><input id="edTeamMerTier" type="number" step="0.5" min="1" max="20" value="${tf.merchandiseContribution || 1}" /></div>
      </div>

      <div class="subcard" style="margin-top:12px;">
        <div class="subcard-title">Contracted Players (${d.players.length})</div>
        <div class="table-wrap" style="max-height:240px;">
          <table>
            <thead><tr><th>Player</th><th>Nation</th><th>Age</th><th>Avg Skill</th><th>Roles</th><th>Salary</th><th>Status</th><th>Inspect</th></tr></thead>
            <tbody>
              ${d.players.map((p) => `
                <tr>
                  <td><strong>${escapeHtml(p.name)}</strong></td>
                  <td>${escapeHtml(p.nationName)}</td>
                  <td class="mono">${p.age}</td>
                  <td class="mono">${p.avgSkill.toFixed(2)}</td>
                  <td>${p.igl === 0 ? '<span class="tag-pill info">IGL</span> ' : ''}${p.sniper === 0 ? '<span class="tag-pill warn">AWP</span>' : ''}</td>
                  <td class="mono">$${Number(p.salaryYear || 0).toLocaleString()}</td>
                  <td>${p.benched ? '<span class="tag-pill warn">Bench</span>' : '<span class="tag-pill ok">Starter</span>'}</td>
                  <td><button class="btn sm" onclick="jumpToPlayer(${p.id})">Edit</button></td>
                </tr>
              `).join("") || '<tr><td colspan="8" class="muted">No contracted players.</td></tr>'}
            </tbody>
          </table>
        </div>
      </div>

      <div class="subcard">
        <div class="subcard-title">Contracted Staff (${d.staff.length})</div>
        <div class="table-wrap" style="max-height:170px;">
          <table>
            <thead><tr><th>Name</th><th>Role</th><th>Nation</th><th>Avg Skill</th><th>Salary</th><th>Inspect</th></tr></thead>
            <tbody>
              ${d.staff.map((st) => `<tr><td><strong>${escapeHtml(st.name)}</strong></td><td>${escapeHtml(st.roleName)}</td><td>${escapeHtml(st.nationName)}</td><td class="mono">${st.avgSkill.toFixed(2)}</td><td class="mono">$${Number(st.salaryYear).toLocaleString()}</td><td><button class="btn sm" onclick="jumpToStaff(${st.id})">Edit</button></td></tr>`).join("") || '<tr><td colspan="6" class="muted">No staff contracted.</td></tr>'}
            </tbody>
          </table>
        </div>
      </div>
    `;
  } catch (err) {
    toast(err.message, "err");
  }
}

async function saveSelectedTeam(teamId) {
  try {
    await apiPost("/api/team/update", {
      teamId,
      patch: {
        name: $("edTeamName").value,
        logo: $("edTeamLogo").value,
        nation: Number($("edTeamNation").value),
        reputation: Number($("edTeamRep").value),
        rankingPointsTotal: Number($("edTeamPts").value),
        professionalStatus: Number($("edTeamPro").value),
        mainLanguage: Number($("edTeamLang").value),
        owner: { name: $("edTeamOwner").value, hiringBias: Number($("edTeamBias").value) },
        teamFinances: {
          currentBalance: Number($("edTeamBal").value),
          ownerContribution: Number($("edTeamOwnTier").value),
          merchandiseContribution: Number($("edTeamMerTier").value),
        },
      },
    });
    toast("Team updated in memory (click Save DB to write disk).");
    state.summary = await apiGet("/api/summary");
    updateTopbar();
    loadTeamsList();
  } catch (err) {
    toast(err.message, "err");
  }
}

async function deleteSelectedTeam(teamId) {
  if (!confirm(`Delete team #${teamId} and clear its contracts?`)) return;
  try {
    await apiPost("/api/team/delete", { teamId });
    state.selectedTeamId = null;
    $("teamEditorCard").innerHTML = `<div class="muted">Team deleted.</div>`;
    toast("Team deleted.", "ok");
    loadTeamsList();
    state.summary = await apiGet("/api/summary");
    updateTopbar();
  } catch (err) {
    toast(err.message, "err");
  }
}

function openNewTeamModal() {
  openModal("Create New Team in Database", `
    <div class="form-grid">
      <div class="field"><label>Team Name</label><input id="newTeamName" placeholder="e.g. Apex Five" /></div>
      <div class="field"><label>Nation</label><select id="newTeamNation">${nationOptionsHtml(102)}</select></div>
      <div class="field"><label>Reputation (1-20)</label><input id="newTeamRep" type="number" min="1" max="20" value="12" /></div>
      <div class="field"><label>Starting Ranking Points</label><input id="newTeamPts" type="number" value="650" /></div>
      <div class="field"><label>Hiring Bias</label><select id="newTeamBias">${optionsHtml(state.meta.hiringBias, 7)}</select></div>
      <div class="field"><label>Main Language</label><select id="newTeamLang">${optionsHtml(state.meta.languages, 13)}</select></div>
      <div class="field"><label>Owner Name</label><input id="newTeamOwner" value="Owner" /></div>
      <div class="field"><label>Owner Contrib Tier</label><input id="newTeamOwn" type="number" step="1" min="1" max="20" value="12" /></div>
    </div>
    <div style="margin-top:14px;display:flex;justify-content:flex-end;gap:8px;">
      <button class="btn" onclick="closeModal()">Cancel</button>
      <button class="btn primary" onclick="submitNewTeam()">Create Team</button>
    </div>
  `);
}

async function submitNewTeam() {
  try {
    const res = await apiPost("/api/team/create", {
      name: $("newTeamName").value,
      nation: Number($("newTeamNation").value),
      reputation: Number($("newTeamRep").value),
      rankingPointsTotal: Number($("newTeamPts").value),
      hiringBias: Number($("newTeamBias").value),
      mainLanguage: Number($("newTeamLang").value),
      ownerName: $("newTeamOwner").value,
      ownerContribution: Number($("newTeamOwn").value),
    });
    closeModal();
    toast(`Created team ${res.team.name}!`);
    await loadTeamsList();
    selectTeam(res.team.id);
    state.summary = await apiGet("/api/summary");
    updateTopbar();
  } catch (err) {
    toast(err.message, "err");
  }
}

// ------------------------------------------------------------------
// TAB 3: Players
// ------------------------------------------------------------------

async function loadPlayersList() {
  try {
    if (!state.teams.length) state.teams = await apiGet("/api/teams");
    const q = encodeURIComponent($("playerSearch").value || "");
    const role = encodeURIComponent($("playerRoleFilter").value || "");
    const freeOnly = $("playerFreeOnly").checked;
    state.players = await apiGet(`/api/players?q=${q}&role=${role}&freeOnly=${freeOnly}`);
    $("playerList").innerHTML = state.players.map((p) => `
      <div class="list-row ${Number(p.id) === Number(state.selectedPlayerId) ? "selected" : ""}" onclick="selectPlayer(${p.id})">
        <div>
          <strong>${escapeHtml(p.name)}</strong> <span class="muted mono">${p.age}y</span> ${p.useStartingPotential ? `<span class="tag-pill ok mono" style="font-size:10px;">Pot ${p.startingPotential}</span>` : ""}
          <div class="muted" style="font-size:11px;">${escapeHtml(p.teamName)}${p.benched ? " (Bench)" : ""} · ${escapeHtml(p.nationName)}</div>
        </div>
        <div style="text-align:right;">
          <div class="mono" style="font-weight:700;">${p.avgSkill.toFixed(1)}</div>
          <div class="muted" style="font-size:11px;">Pot ${p.potentialAvg.toFixed(1)}</div>
        </div>
      </div>
    `).join("") || `<div class="muted" style="padding:14px;">No players match filter.</div>`;
  } catch (err) {
    toast(err.message, "err");
  }
}

function jumpToTeam(tid) {
  if (!tid || Number(tid) <= 0) return;
  switchTab("teams");
  selectTeam(tid);
}

function jumpToPlayer(pid) {
  switchTab("players");
  selectPlayer(pid);
}

function jumpToStaff(sid) {
  switchTab("staff");
  document.querySelectorAll("[data-stsub]").forEach((x) => x.classList.toggle("active", x.dataset.stsub === "staffers"));
  document.querySelectorAll("#tab-staff .subpanel").forEach((p) => p.classList.toggle("active", p.id === "stsub-staffers"));
  selectStaff(sid);
}

function switchPlayerSubTab(subKey) {
  state.playerSubTab = subKey;
  document.querySelectorAll("[data-plsub]").forEach((b) => b.classList.toggle("active", b.dataset.plsub === subKey));
  document.querySelectorAll("#playerEditorCard .subpanel").forEach((p) => p.classList.toggle("active", p.id === `plsub-${subKey}`));
}

function randomizePortraitFields(prefix = "edPlPt_") {
  for (const pf of (state.meta?.portraitFields || [])) {
    const el = $(`${prefix}${pf.key}`);
    if (!el) continue;
    el.value = Math.floor(Math.random() * (pf.max - pf.min + 1)) + pf.min;
  }
  toast("Randomized portrait genes (click Save to keep).");
}

function copyPortraitFromPlayer() {
  const srcId = Number($("plCopyPortraitSelect")?.value || 0);
  if (!srcId) return;
  apiGet(`/api/player?id=${srcId}`).then((res) => {
    const srcPt = res.player?.portrait || {};
    for (const pf of (state.meta?.portraitFields || [])) {
      const el = $(`edPlPt_${pf.key}`);
      if (el && srcPt[pf.key] !== undefined) el.value = srcPt[pf.key];
    }
    toast(`Copied portrait genes from ${res.player?.name || srcId} (click Save Player to keep).`);
  }).catch((e) => toast(e.message, "err"));
}

function applyPlayerPositionPreset(mode) {
  const presets = {
    entry: [10, 6, 4, 4, 7, 4, 8, 5, 5],
    awper: [3, 4, 7, 5, 4, 8, 6, 9, 5],
    igl: [5, 4, 6, 10, 5, 6, 8, 7, 5],
    anchor: [3, 8, 9, 4, 5, 10, 6, 4, 5],
    versatile: [8, 8, 8, 8, 8, 8, 8, 8, 8],
  };
  const arr = presets[mode];
  if (!arr) return;
  arr.forEach((v, i) => {
    const el = $(`edPlPos_${i}`);
    if (el) el.value = v;
  });
  toast(`Applied '${mode}' position comfort preset (click Save Player).`);
}

function adjustAllPlayerSkills(delta) {
  for (const sd of (state.meta?.playerSkills || [])) {
    const el = $(`edPlSk_${sd.key}`);
    if (el) el.value = Math.max(1, Math.min(20, Number(el.value) + delta)).toFixed(1);
  }
}

function syncPlayerSkillCaps() {
  for (const sd of (state.meta?.playerSkills || [])) {
    const skEl = $(`edPlSk_${sd.key}`);
    const ptEl = $(`edPlPot_${sd.key}`);
    if (skEl && ptEl) {
      ptEl.value = Math.max(1, Math.min(20, Math.round(Number(skEl.value) + 2)));
    }
  }
}

function renderPlayerLanguagesRows(langsList) {
  const tbody = $("plLangTableBody");
  if (!tbody) return;
  tbody.innerHTML = (langsList || []).map((lg, idx) => `
    <tr class="pl-lang-row">
      <td><select class="pl-lang-id">${optionsHtml(state.meta?.languages || {}, lg.languageId)}</select></td>
      <td><input class="pl-lang-skill" type="number" min="1" max="20" value="${lg.languageSkill ?? 20}" style="width:74px;" /></td>
      <td><input class="pl-lang-limit" type="number" min="0" max="20" value="${lg.limit ?? 20}" style="width:74px;" /></td>
      <td><button type="button" class="btn danger sm" onclick="this.closest('tr').remove()">Remove</button></td>
    </tr>
  `).join("");
}

function addPlayerLanguageRow(presetLangId = null) {
  const tbody = $("plLangTableBody");
  if (!tbody) return;
  const lid = presetLangId || Number($("plNewLangSelect")?.value || 13);
  const existing = Array.from(tbody.querySelectorAll(".pl-lang-id")).map((s) => Number(s.value));
  if (existing.includes(lid)) {
    toast("Language already in player list.", "warn");
    return;
  }
  const tr = document.createElement("tr");
  tr.className = "pl-lang-row";
  tr.innerHTML = `
    <td><select class="pl-lang-id">${optionsHtml(state.meta?.languages || {}, lid)}</select></td>
    <td><input class="pl-lang-skill" type="number" min="1" max="20" value="20" style="width:74px;" /></td>
    <td><input class="pl-lang-limit" type="number" min="0" max="20" value="20" style="width:74px;" /></td>
    <td><button type="button" class="btn danger sm" onclick="this.closest('tr').remove()">Remove</button></td>
  `;
  tbody.appendChild(tr);
}

function renderPlayerRelationsPanel(playerId, rels) {
  const container = $("plRelationsPanel");
  if (!container) return;
  const relTypes = state.meta?.relationshipTypes || { 0: "Rival", 1: "Friend", 2: "Mentor / Former Teammate", 3: "Strong Bond", 4: "Chemistry Link" };
  const pillCls = (t) => (Number(t) === 0 ? "err" : Number(t) === 1 ? "ok" : Number(t) >= 3 ? "info" : "warn");
  const allP = (state.allPlayersBrief.length ? state.allPlayersBrief : state.players).filter((x) => Number(x.id) !== Number(playerId));
  const q = ($("plRelSearch")?.value || "").trim().toLowerCase();
  const pickList = allP.filter((x) => !q || (x.name || "").toLowerCase().includes(q) || (x.teamName || "").toLowerCase().includes(q)).slice(0, 250);

  container.innerHTML = `
    <div class="subcard">
      <div class="subcard-title">Add Friend / Rival / Chemistry Link (<code>playerRelationships.json</code>)</div>
      <div class="form-grid" style="grid-template-columns:1fr 1.5fr 1fr 100px auto;align-items:end;">
        <div class="field"><label>Filter Player</label><input id="plRelSearch" placeholder="Search name or team..." value="${escapeHtml($("plRelSearch")?.value || "")}" oninput="filterRelationCandidates(${playerId})" /></div>
        <div class="field"><label>Partner Player (${allP.length} in DB)</label>
          <select id="plRelTarget">
            ${pickList.map((x) => `<option value="${x.id}">${escapeHtml(x.name)} (${escapeHtml(x.teamName)} · ${x.avgSkill})</option>`).join("")}
          </select>
        </div>
        <div class="field"><label>Relationship Type</label><select id="plRelType">${optionsHtml(relTypes, 1)}</select></div>
        <div class="field"><label>Duration (mo)</label><input id="plRelDuration" type="number" min="0" max="120" value="0" /></div>
        <div><button type="button" class="btn primary sm" onclick="savePlayerRelation(${playerId})">Add / Update</button></div>
      </div>
    </div>
    <div class="subcard">
      <div class="subcard-title">Existing Relations (${(rels || []).length})</div>
      <div class="table-wrap" style="max-height:340px;">
        <table>
          <thead><tr><th>Partner</th><th>Team / Skill</th><th>Type</th><th>Duration</th><th>Edit / Actions</th></tr></thead>
          <tbody>
            ${(rels || []).map((r) => `
              <tr>
                <td>${r.otherExists ? `<a href="javascript:void(0)" style="color:var(--accent);font-weight:700;" onclick="jumpToPlayer(${r.otherPlayerId})">${escapeHtml(r.otherPlayerName)}</a>` : `<span class="tag-pill err">${escapeHtml(r.otherPlayerName)}</span>`}</td>
                <td>${escapeHtml(r.otherTeamName)} · <span class="mono">${Number(r.otherAvgSkill || 0).toFixed(1)}</span></td>
                <td><span class="tag-pill ${pillCls(r.type)}">${escapeHtml(r.typeLabel)}</span></td>
                <td class="mono">${r.duration || 0} mo</td>
                <td>
                  <div style="display:flex;gap:4px;align-items:center;">
                    <select id="plRelRowType_${r.otherPlayerId}" style="width:155px;">${optionsHtml(relTypes, r.type)}</select>
                    <button type="button" class="btn ok sm" onclick="savePlayerRelation(${playerId}, ${r.otherPlayerId})">Update</button>
                    <button type="button" class="btn danger sm" onclick="removePlayerRelation(${playerId}, ${r.otherPlayerId})">Remove</button>
                  </div>
                </td>
              </tr>
            `).join("") || `<tr><td colspan="5" class="muted" style="text-align:center;padding:16px;">No friends or rivals defined for this player yet.</td></tr>`}
          </tbody>
        </table>
      </div>
    </div>
  `;
}

function filterRelationCandidates(playerId) {
  const q = ($("plRelSearch")?.value || "").trim().toLowerCase();
  const sel = $("plRelTarget");
  if (!sel) return;
  const allP = (state.allPlayersBrief.length ? state.allPlayersBrief : state.players).filter((x) => Number(x.id) !== Number(playerId));
  const pickList = allP.filter((x) => !q || (x.name || "").toLowerCase().includes(q) || (x.teamName || "").toLowerCase().includes(q)).slice(0, 250);
  sel.innerHTML = pickList.map((x) => `<option value="${x.id}">${escapeHtml(x.name)} (${escapeHtml(x.teamName)} · ${x.avgSkill})</option>`).join("");
}

async function savePlayerRelation(playerId, existingOtherId = null) {
  const otherId = existingOtherId !== null ? existingOtherId : Number($("plRelTarget")?.value || 0);
  if (!otherId) { toast("Select a partner player first.", "err"); return; }
  const relType = existingOtherId !== null
    ? Number($(`plRelRowType_${existingOtherId}`)?.value ?? 1)
    : Number($("plRelType")?.value ?? 1);
  const duration = existingOtherId !== null ? 0 : Number($("plRelDuration")?.value || 0);
  try {
    const updated = await apiPost("/api/player/relationship/save", {
      player1Id: playerId,
      player2Id: otherId,
      type: relType,
      duration,
    });
    if (state.selectedPlayerData) state.selectedPlayerData.relationships = updated.relationships;
    renderPlayerRelationsPanel(playerId, updated.relationships);
    state.summary = await apiGet("/api/summary");
    updateTopbar();
    toast("Player relationship saved in memory.");
  } catch (err) {
    toast(err.message, "err");
  }
}

async function removePlayerRelation(playerId, otherId) {
  try {
    const updated = await apiPost("/api/player/relationship/delete", {
      player1Id: playerId,
      player2Id: otherId,
    });
    if (state.selectedPlayerData) state.selectedPlayerData.relationships = updated.relationships;
    renderPlayerRelationsPanel(playerId, updated.relationships);
    state.summary = await apiGet("/api/summary");
    updateTopbar();
    toast("Relationship removed.");
  } catch (err) {
    toast(err.message, "err");
  }
}

function addPlayerAwardRow() {
  const tbody = $("plAwardsTableBody");
  if (!tbody) return;
  const tp = Number($("plNewAwType")?.value ?? 0);
  const tpl = Number($("plNewAwTourn")?.value ?? -1);
  const tid = Number($("plNewAwTeam")?.value ?? 0);
  const yr = Number($("plNewAwYear")?.value ?? 2025);
  const mo = Number($("plNewAwMonth")?.value ?? 0);
  const top20 = tp === 3 ? Math.max(1, Math.min(20, Number($("plNewAwTop20")?.value || 1))) : 0;
  const awardTypes = state.meta?.awardTypes || { 0: "Tournament MVP", 1: "Tournament EVP", 2: "Honorable Mention", 3: "Top-20 Player of the Year" };
  const tournOpts = `<option value="-1" ${tpl === -1 ? "selected" : ""}>Historic / Pre-Career (-1)</option>`
    + (state.tournaments || []).map((t) => `<option value="${t.template}" ${Number(t.template) === tpl ? "selected" : ""}>${escapeHtml(t.name)} (#${t.template})</option>`).join("");
  const tr = document.createElement("tr");
  tr.className = "pl-award-row";
  tr.innerHTML = `
    <td><select class="pl-aw-type">${optionsHtml(awardTypes, tp)}</select></td>
    <td><select class="pl-aw-tourn">${tournOpts}</select></td>
    <td><select class="pl-aw-team">${teamSelectOptionsHtml(tid, true)}</select></td>
    <td><input class="pl-aw-year" type="number" min="1" max="2040" value="${yr}" style="width:72px;" /></td>
    <td><input class="pl-aw-month" type="number" min="0" max="12" value="${mo}" style="width:58px;" /></td>
    <td><input class="pl-aw-top20" type="number" min="0" max="20" value="${top20}" style="width:58px;" /></td>
    <td><button type="button" class="btn danger sm" onclick="this.closest('tr').remove()">Remove</button></td>
  `;
  tbody.prepend(tr);
}

function renderPlayerAwardsRows(awardsList) {
  const tbody = $("plAwardsTableBody");
  if (!tbody) return;
  const awardTypes = state.meta?.awardTypes || { 0: "Tournament MVP", 1: "Tournament EVP", 2: "Honorable Mention", 3: "Top-20 Player of the Year" };
  const rows = (awardsList || []).slice(0, 120);
  const tournMapHtml = (selVal) => `<option value="-1" ${Number(selVal) === -1 ? "selected" : ""}>Historic / Pre-Career (-1)</option>`
    + (state.tournaments || []).map((t) => `<option value="${t.template}" ${Number(t.template) === Number(selVal) ? "selected" : ""}>${escapeHtml(t.name)} (#${t.template})</option>`).join("");
  tbody.innerHTML = rows.map((aw) => `
    <tr class="pl-award-row">
      <td><select class="pl-aw-type">${optionsHtml(awardTypes, aw.type)}</select></td>
      <td><select class="pl-aw-tourn">${tournMapHtml(aw.tournamentTemplate ?? -1)}</select></td>
      <td><select class="pl-aw-team">${teamSelectOptionsHtml(aw.teamId || 0, true)}</select></td>
      <td><input class="pl-aw-year" type="number" min="1" max="2040" value="${aw.year ?? 2025}" style="width:72px;" /></td>
      <td><input class="pl-aw-month" type="number" min="0" max="12" value="${aw.month ?? 0}" style="width:58px;" /></td>
      <td><input class="pl-aw-top20" type="number" min="0" max="20" value="${aw.top20Placement ?? 0}" style="width:58px;" /></td>
      <td><button type="button" class="btn danger sm" onclick="this.closest('tr').remove()">Remove</button></td>
    </tr>
  `).join("");
}

async function selectPlayer(playerId) {
  state.selectedPlayerId = playerId;
  loadPlayersList();
  try {
    if (!state.teams.length) state.teams = await apiGet("/api/teams");
    if (!state.tournaments.length) state.tournaments = await apiGet("/api/tournaments");
    if (!state.allPlayersBrief.length) state.allPlayersBrief = await apiGet("/api/players?limit=2500");
    const d = await apiGet(`/api/player?id=${playerId}`);
    state.selectedPlayerData = d;
    const p = d.player;
    const c = d.contract || { teamId: 0, salaryYear: 0, status: 1, igl: 2, sniper: 2, benched: false, transferStatus: 0, askingPrice: 0, contractType: 0, endDate: { year: 2028 } };
    const sk = p.skills || {};
    const pers = p.personality || {};
    const pt = p.portrait || {};
    const rels = d.relationships || [];
    const awards = p.playerAwards || [];
    const mvpCnt = awards.filter((a) => Number(a.type) === 0).length;
    const evpCnt = awards.filter((a) => Number(a.type) === 1).length;
    const top20Best = awards.filter((a) => Number(a.type) === 3 && a.top20Placement > 0).map((a) => a.top20Placement);
    const potKeys = p.potential?.m_Keys || [];
    const potVals = p.potential?.m_Values || [];
    const potById = {};
    potKeys.forEach((k, i) => { potById[k] = potVals[i]; });

    const posComfort = {};
    (p.mapPositionAttributes || []).forEach((m) => { posComfort[m.positionType] = m.roleComfort; });
    const mapOps = {};
    (p.mapOpinions || []).forEach((m) => { mapOps[m.mapId] = m.like ? "like" : "dislike"; });

    const activeSub = state.playerSubTab || "basics";
    const prefAxes = (state.meta.personalityAxes || []).filter((a) => a.key === "desireToIgl" || a.key === "desireToAwp");
    const persAxes = (state.meta.personalityAxes || []).filter((a) => a.key !== "desireToIgl" && a.key !== "desireToAwp");
    const skillGroups = ["Mechanics", "Weapons", "Mental"];
    const portraitGroups = ["Head & Skin", "Eyes & Brows", "Nose & Mouth", "Hair & Beard", "Accessories"];
    const mapEntries = Object.entries(state.meta.mapNames || {}).sort((a, b) => Number(a[0]) - Number(b[0]));
    const tournOptsNew = `<option value="-1">Historic / Pre-Career (-1)</option>`
      + (state.tournaments || []).map((t) => `<option value="${t.template}">${escapeHtml(t.name)} (#${t.template})</option>`).join("");

    $("playerEditorCard").innerHTML = `
      <div class="card-head">
        <div>
          <span class="card-title">${escapeHtml(p.name)}</span>
          <span class="tag-pill info mono">ID #${p.id}</span>
          ${p.useStartingPotential ? `<span class="tag-pill ok mono">Custom Pot ${p.startingPotential || 0}</span>` : ""}
          <span class="tag-pill ${rels.length ? "info" : ""}">${rels.length} Relations</span>
          <span class="tag-pill">${(p.languagesSpoken || []).length} Langs</span>
          ${awards.length ? `<span class="tag-pill warn">${mvpCnt} MVP · ${evpCnt} EVP</span>` : ""}
        </div>
        <div style="display:flex;gap:6px;">
          ${c.teamId ? `<button class="btn sm" onclick="jumpToTeam(${c.teamId})">View Team</button>` : ""}
          <button class="btn ok sm" onclick="saveSelectedPlayer(${p.id})">Save Player</button>
          <button class="btn danger sm" onclick="deleteSelectedPlayer(${p.id})">Delete</button>
        </div>
      </div>

      <div class="subtabs">
        <button type="button" class="subtab-btn ${activeSub === "basics" ? "active" : ""}" data-plsub="basics" onclick="switchPlayerSubTab('basics')">Basics &amp; Personality</button>
        <button type="button" class="subtab-btn ${activeSub === "skills" ? "active" : ""}" data-plsub="skills" onclick="switchPlayerSubTab('skills')">Skills &amp; Caps</button>
        <button type="button" class="subtab-btn ${activeSub === "maps" ? "active" : ""}" data-plsub="maps" onclick="switchPlayerSubTab('maps')">Maps &amp; Positions</button>
        <button type="button" class="subtab-btn ${activeSub === "languages" ? "active" : ""}" data-plsub="languages" onclick="switchPlayerSubTab('languages')">Languages</button>
        <button type="button" class="subtab-btn ${activeSub === "career" ? "active" : ""}" data-plsub="career" onclick="switchPlayerSubTab('career')">Career &amp; Awards (${awards.length})</button>
        <button type="button" class="subtab-btn ${activeSub === "relations" ? "active" : ""}" data-plsub="relations" onclick="switchPlayerSubTab('relations')">Relations (${rels.length})</button>
        <button type="button" class="subtab-btn ${activeSub === "portrait" ? "active" : ""}" data-plsub="portrait" onclick="switchPlayerSubTab('portrait')">Portrait Mod</button>
        <button type="button" class="subtab-btn ${activeSub === "contract" ? "active" : ""}" data-plsub="contract" onclick="switchPlayerSubTab('contract')">Contract &amp; Flags</button>
      </div>

      <!-- SUBTAB 1: BASICS, IGL/SNIPER PREFERENCE & PERSONALITY -->
      <div id="plsub-basics" class="subpanel ${activeSub === "basics" ? "active" : ""}">
        <div class="subcard">
          <div class="subcard-title">Identity &amp; Potential</div>
          <div class="form-grid">
            <div class="field"><label>Alias / Name</label><input id="edPlName" value="${escapeHtml(p.name)}" /></div>
            <div class="field"><label>Age</label><input id="edPlAge" type="number" min="15" max="45" value="${p.age}" /></div>
            <div class="field"><label>Nation</label><select id="edPlNation">${nationOptionsHtml(p.nation)}</select></div>
            <div class="field"><label>Reputation (1-20)</label><input id="edPlRep" type="number" min="1" max="20" value="${p.reputation}" /></div>
            <div class="field"><label>Preferred Mentality</label><select id="edPlMent">${optionsHtml(state.meta.playerMentalities, p.preferredMentality)}</select></div>
            <div class="field"><label>Longevity (1-20)</label><input id="edPlLong" type="number" min="1" max="20" value="${p.longevity ?? 10}" /></div>
            <div class="field"><label>Use Custom Potential</label>
              <select id="edPlUseCustomPot" onchange="$('edPlCustomPot').disabled = (this.value !== 'true');">
                <option value="false" ${!p.useStartingPotential ? "selected" : ""}>Off (Engine Dynamic / Per-Skill Caps)</option>
                <option value="true" ${p.useStartingPotential ? "selected" : ""}>On (Override Starting Potential)</option>
              </select>
            </div>
            <div class="field"><label>Custom Potential (50-275)</label>
              <div style="display:flex;gap:4px;align-items:center;">
                <input id="edPlCustomPot" type="number" min="50" max="275" value="${p.startingPotential >= 50 ? p.startingPotential : 200}" ${!p.useStartingPotential ? "disabled" : ""} style="width:90px;" />
                <button type="button" class="btn sm" onclick="$('edPlUseCustomPot').value='true';$('edPlCustomPot').disabled=false;$('edPlCustomPot').value=260;" title="Generational Talent">260</button>
                <button type="button" class="btn sm" onclick="$('edPlUseCustomPot').value='true';$('edPlCustomPot').disabled=false;$('edPlCustomPot').value=220;" title="Tier-1 Star">220</button>
              </div>
            </div>
          </div>
        </div>

        <div class="split-equal">
          <div class="subcard">
            <div class="subcard-title">IGL &amp; Sniper Preference (1-20)</div>
            <p class="hint" style="margin-bottom:8px;">Controls whether the player pushes to call tactics or AWP on teams and during transfers.</p>
            ${prefAxes.map((ax) => {
              const v = pers[ax.key] ?? 10;
              return `
                <div style="margin-bottom:10px;">
                  <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:3px;">
                    <strong>${escapeHtml(ax.label)}</strong>
                    <span class="muted">${escapeHtml(ax.low)} (1) <-> ${escapeHtml(ax.high)} (20) · <strong id="lblPlPers_${ax.key}" class="mono">${v}</strong></span>
                  </div>
                  <input id="edPlPers_${ax.key}" type="range" min="1" max="20" value="${v}" oninput="$('lblPlPers_${ax.key}').textContent=this.value" style="width:100%;" />
                </div>
              `;
            }).join("")}
          </div>

          <div class="subcard">
            <div class="subcard-title">Personality Spectrum (1-20)</div>
            ${persAxes.map((ax) => {
              const v = pers[ax.key] ?? 10;
              return `
                <div style="margin-bottom:8px;">
                  <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:2px;">
                    <strong>${escapeHtml(ax.label)}</strong>
                    <span class="muted">${escapeHtml(ax.low)} (1) <-> ${escapeHtml(ax.high)} (20) · <strong id="lblPlPers_${ax.key}" class="mono">${v}</strong></span>
                  </div>
                  <input id="edPlPers_${ax.key}" type="range" min="1" max="20" value="${v}" oninput="$('lblPlPers_${ax.key}').textContent=this.value" style="width:100%;" />
                </div>
              `;
            }).join("")}
          </div>
        </div>
      </div>

      <!-- SUBTAB 2: 18 SKILLS & POTENTIAL CAPS -->
      <div id="plsub-skills" class="subpanel ${activeSub === "skills" ? "active" : ""}">
        <div class="subcard">
          <div class="card-head" style="margin-bottom:8px;">
            <span class="subcard-title" style="margin:0;">18 Core Skills (1-20) &amp; Per-Skill Potential Caps (1=auto)</span>
            <div style="display:flex;gap:6px;">
              <button type="button" class="btn sm" onclick="adjustAllPlayerSkills(-1)">All Skills -1</button>
              <button type="button" class="btn sm" onclick="adjustAllPlayerSkills(1)">All Skills +1</button>
              <button type="button" class="btn sm" onclick="syncPlayerSkillCaps()">Set Caps = Skill+2</button>
            </div>
          </div>
          ${skillGroups.map((grp) => `
            <div style="margin-bottom:10px;">
              <div style="font-size:11px;font-weight:700;color:var(--accent);text-transform:uppercase;margin-bottom:6px;">${escapeHtml(grp)}</div>
              <div class="form-grid" style="grid-template-columns:repeat(auto-fit,minmax(160px,1fr));">
                ${state.meta.playerSkills.filter((sd) => sd.group === grp).map((sd) => `
                  <div class="field">
                    <label>${escapeHtml(sd.label)}</label>
                    <div style="display:flex;gap:4px;">
                      <input id="edPlSk_${sd.key}" type="number" step="0.5" min="1" max="20" value="${Number(sk[sd.key] ?? 10).toFixed(1)}" title="Skill" style="width:72px;" />
                      <input id="edPlPot_${sd.key}" type="number" min="1" max="20" value="${potById[sd.id] ?? 1}" title="Potential Cap (1=auto)" style="width:58px;" />
                    </div>
                  </div>
                `).join("")}
              </div>
            </div>
          `).join("")}
        </div>
      </div>

      <!-- SUBTAB 3: MAPS & POSITIONS -->
      <div id="plsub-maps" class="subpanel ${activeSub === "maps" ? "active" : ""}">
        <div class="split-equal">
          <div class="subcard">
            <div class="card-head" style="margin-bottom:8px;">
              <span class="subcard-title" style="margin:0;">Tactical Position Comfort (1-10)</span>
              <div style="display:flex;gap:4px;flex-wrap:wrap;">
                <button type="button" class="btn sm" onclick="applyPlayerPositionPreset('entry')">Entry</button>
                <button type="button" class="btn sm" onclick="applyPlayerPositionPreset('awper')">AWPer</button>
                <button type="button" class="btn sm" onclick="applyPlayerPositionPreset('igl')">IGL</button>
                <button type="button" class="btn sm" onclick="applyPlayerPositionPreset('anchor')">Anchor</button>
                <button type="button" class="btn sm" onclick="applyPlayerPositionPreset('versatile')">All 8+</button>
              </div>
            </div>
            <div class="form-grid" style="grid-template-columns:repeat(auto-fit,minmax(150px,1fr));">
              ${Object.entries(state.meta.playerPositions || {}).sort((a, b) => Number(a[0]) - Number(b[0])).map(([pidKey, label]) => `
                <div class="field">
                  <label>${escapeHtml(label)} (#${pidKey})</label>
                  <input id="edPlPos_${pidKey}" type="number" min="1" max="10" value="${posComfort[pidKey] ?? 5}" />
                </div>
              `).join("")}
            </div>
          </div>

          <div class="subcard">
            <div class="card-head" style="margin-bottom:8px;">
              <span class="subcard-title" style="margin:0;">Map Pool Opinions (<code>mapOpinions</code>)</span>
              <div style="display:flex;gap:4px;">
                <button type="button" class="btn ok sm" onclick="document.querySelectorAll('.pl-map-op').forEach(el => { if (Number(el.dataset.mid) <= 8) el.value='like'; })">Like Active 8</button>
              </div>
            </div>
            <div class="form-grid" style="grid-template-columns:repeat(auto-fit,minmax(150px,1fr));">
              ${mapEntries.map(([mid, mname]) => {
                const curOp = mapOps[mid] || "omit";
                return `
                  <div class="field">
                    <label>${escapeHtml(mname)} (Map ${mid})</label>
                    <select id="edPlMap_${mid}" class="pl-map-op" data-mid="${mid}">
                      <option value="like" ${curOp === "like" ? "selected" : ""}>Like (Favored)</option>
                      <option value="dislike" ${curOp === "dislike" ? "selected" : ""}>Dislike (Avoid)</option>
                      <option value="omit" ${curOp === "omit" ? "selected" : ""}>Not Listed / Neutral</option>
                    </select>
                  </div>
                `;
              }).join("")}
            </div>
          </div>
        </div>
      </div>

      <!-- SUBTAB 4: LANGUAGES SPOKEN -->
      <div id="plsub-languages" class="subpanel ${activeSub === "languages" ? "active" : ""}">
        <div class="subcard">
          <div class="card-head">
            <span class="subcard-title" style="margin:0;">Languages Spoken (<code>languagesSpoken</code>)</span>
            <div style="display:flex;gap:6px;align-items:center;">
              <select id="plNewLangSelect" style="width:160px;">${optionsHtml(state.meta.languages || {}, 13)}</select>
              <button type="button" class="btn primary sm" onclick="addPlayerLanguageRow()">+ Add Language</button>
              <button type="button" class="btn sm" onclick="addPlayerLanguageRow(13)">+ Fluent English</button>
            </div>
          </div>
          <div class="table-wrap" style="max-height:320px;">
            <table>
              <thead><tr><th>Language</th><th>Fluency (1-20)</th><th>Max Limit (0-20)</th><th>Action</th></tr></thead>
              <tbody id="plLangTableBody"></tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- SUBTAB 5: CAREER & AWARDS (UNLOCKED FROM IN-GAME DB EDITOR!) -->
      <div id="plsub-career" class="subpanel ${activeSub === "career" ? "active" : ""}">
        <div class="subcard">
          <div class="card-head">
            <span class="subcard-title" style="margin:0;">Unlocked Career Counters &amp; Trophy Cabinet (<code>playerAwards</code>)</span>
            <span class="hint">In-game DB editor locks this tab, but CS Manager reads <code>playerAwards</code> (MVP/EVP/HM/Top-20) and career counters directly at new-career start.</span>
          </div>
          <div class="kpi-grid" style="margin-bottom:10px;">
            <div class="kpi"><div class="kpi-lbl">Tournament MVPs</div><div class="kpi-val">${mvpCnt}</div></div>
            <div class="kpi"><div class="kpi-lbl">Tournament EVPs</div><div class="kpi-val">${evpCnt}</div></div>
            <div class="kpi"><div class="kpi-lbl">Honorable Mentions</div><div class="kpi-val">${awards.filter((a) => Number(a.type) === 2).length}</div></div>
            <div class="kpi"><div class="kpi-lbl">Top-20 Placements</div><div class="kpi-val">${top20Best.length ? `#${Math.min(...top20Best)} (${top20Best.length}x)` : "None"}</div></div>
          </div>
          <div class="form-grid" style="margin-bottom:10px;">
            <div class="field"><label>Months Since New Contract</label><input id="edPlMoCon" type="number" min="0" value="${p.monthsSinceNewContract ?? 6}" /></div>
            <div class="field"><label>Months Benched / Free Agent</label><input id="edPlMoBench" type="number" min="0" value="${p.monthsBenchedOrWithoutContract ?? 0}" /></div>
            <div class="field"><label>Reputation Progress</label><input id="edPlRepProg" type="number" step="0.1" value="${Number(p.reputationProgress ?? 0).toFixed(2)}" /></div>
            <div class="field"><label>Hidden Skill Offset</label><input id="edPlSkOff" type="number" step="0.1" value="${Number(p.skillOffset ?? 0).toFixed(2)}" /></div>
          </div>
        </div>
        <div class="subcard">
          <div class="subcard-title">Add Pre-Career / Historic Award or Top-20 Ranking</div>
          <div class="form-grid" style="grid-template-columns:1.2fr 1.4fr 1.2fr 80px 70px 80px auto;align-items:end;margin-bottom:10px;">
            <div class="field"><label>Award Type</label><select id="plNewAwType">${optionsHtml(state.meta.awardTypes || {}, 0)}</select></div>
            <div class="field"><label>Tournament (-1 Historic)</label><select id="plNewAwTourn">${tournOptsNew}</select></div>
            <div class="field"><label>Team</label><select id="plNewAwTeam">${teamSelectOptionsHtml(c.teamId || 0, true)}</select></div>
            <div class="field"><label>Year</label><input id="plNewAwYear" type="number" value="2025" /></div>
            <div class="field"><label>Month</label><input id="plNewAwMonth" type="number" min="0" max="12" value="6" /></div>
            <div class="field"><label>Top20 #</label><input id="plNewAwTop20" type="number" min="0" max="20" value="0" /></div>
            <div><button type="button" class="btn primary sm" onclick="addPlayerAwardRow()">+ Add Award</button></div>
          </div>
          <div class="table-wrap" style="max-height:290px;">
            <table>
              <thead><tr><th>Type</th><th>Tournament</th><th>Team</th><th>Year</th><th>Month</th><th>Top-20 #</th><th>Action</th></tr></thead>
              <tbody id="plAwardsTableBody"></tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- SUBTAB 6: RELATIONS (FRIENDS & RIVALS) -->
      <div id="plsub-relations" class="subpanel ${activeSub === "relations" ? "active" : ""}">
        <div id="plRelationsPanel"></div>
      </div>

      <!-- SUBTAB 7: PORTRAIT MOD (CLEAN GENE INPUTS, NO PREVIEW) -->
      <div id="plsub-portrait" class="subpanel ${activeSub === "portrait" ? "active" : ""}">
        <div class="subcard">
          <div class="card-head">
            <span class="subcard-title" style="margin:0;">Portrait Appearance Mod (17 CS Manager Portrait Genes)</span>
            <div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center;">
              <select id="plCopyPortraitSelect" style="width:185px;">
                <option value="">Copy portrait from player...</option>
                ${(state.allPlayersBrief.length ? state.allPlayersBrief : state.players).slice(0, 300).map((x) => `<option value="${x.id}">${escapeHtml(x.name)} (#${x.id})</option>`).join("")}
              </select>
              <button type="button" class="btn sm" onclick="copyPortraitFromPlayer()">Copy</button>
              <button type="button" class="btn sm" onclick="if($('edPlPt_beard'))$('edPlPt_beard').value=0;">Clean Shaven</button>
              <button type="button" class="btn warn sm" onclick="randomizePortraitFields('edPlPt_')">Randomize</button>
            </div>
          </div>
          ${portraitGroups.map((pg) => `
            <div style="margin-bottom:10px;">
              <div style="font-size:11px;font-weight:700;color:var(--accent);text-transform:uppercase;margin-bottom:5px;">${escapeHtml(pg)}</div>
              <div class="form-grid" style="grid-template-columns:repeat(auto-fit,minmax(160px,1fr));">
                ${(state.meta.portraitFields || []).filter((pf) => pf.group === pg).map((pf) => `
                  <div class="field">
                    <label>${escapeHtml(pf.label)} (${pf.min}-${pf.max})</label>
                    <input id="edPlPt_${pf.key}" type="number" min="${pf.min}" max="${pf.max}" value="${pt[pf.key] ?? pf.min}" />
                  </div>
                `).join("")}
              </div>
            </div>
          `).join("")}
        </div>
      </div>

      <!-- SUBTAB 8: CONTRACT & CAREER FLAGS -->
      <div id="plsub-contract" class="subpanel ${activeSub === "contract" ? "active" : ""}">
        <div class="subcard">
          <div class="subcard-title">Contract &amp; Team Assignment</div>
          <div class="form-grid">
            <div class="field"><label>Team</label><select id="edPlTeam">${teamSelectOptionsHtml(c.teamId, true)}</select></div>
            <div class="field"><label>Annual Salary ($)</label><input id="edPlSal" type="number" step="5000" value="${c.salaryYear || 0}" /></div>
            <div class="field"><label>Role Status</label><select id="edPlStatus">${optionsHtml(state.meta.playerStatus, c.status ?? 1)}</select></div>
            <div class="field"><label>Team IGL Role</label><select id="edPlIgl">${optionsHtml(state.meta.roleStatus, c.igl ?? 2)}</select></div>
            <div class="field"><label>Team AWP Role</label><select id="edPlAwp">${optionsHtml(state.meta.roleStatus, c.sniper ?? 2)}</select></div>
            <div class="field"><label>Contract Expiry Year</label><input id="edPlExp" type="number" min="2026" max="2035" value="${c.endDate?.year || 2028}" /></div>
            <div class="field"><label>Benched</label><select id="edPlBench"><option value="false" ${!c.benched ? "selected" : ""}>Starter</option><option value="true" ${c.benched ? "selected" : ""}>Benched</option></select></div>
            <div class="field"><label>Transfer Status</label><select id="edPlTransStat">${optionsHtml(state.meta.transferStatus || {}, c.transferStatus ?? 0)}</select></div>
            <div class="field"><label>Asking Price ($)</label><input id="edPlAskPrice" type="number" step="10000" value="${c.askingPrice || 0}" /></div>
            <div class="field"><label>Contract Type</label><select id="edPlConType">${optionsHtml(state.meta.contractType || {}, c.contractType ?? 0)}</select></div>
          </div>
        </div>
        <div class="subcard">
          <div class="subcard-title">Career &amp; Roster Flags</div>
          <div style="display:flex;gap:16px;flex-wrap:wrap;padding-top:4px;">
            <label style="display:flex;gap:6px;align-items:center;"><input type="checkbox" id="edPlFlagAcad" ${p.academyPlayer ? "checked" : ""} /> Academy Player</label>
            <label style="display:flex;gap:6px;align-items:center;"><input type="checkbox" id="edPlFlagStandIn" ${p.temporaryStandIn ? "checked" : ""} /> Temporary Stand-In</label>
            <label style="display:flex;gap:6px;align-items:center;"><input type="checkbox" id="edPlFlagNoRetire" ${p.dontReplaceOnRetire ? "checked" : ""} /> Don't Replace on Retire</label>
            <label style="display:flex;gap:6px;align-items:center;"><input type="checkbox" id="edPlFlagRetiring" ${p.setForRetirement ? "checked" : ""} /> Set for Retirement</label>
          </div>
        </div>
      </div>
    `;
    renderPlayerLanguagesRows(p.languagesSpoken || []);
    renderPlayerAwardsRows(awards);
    renderPlayerRelationsPanel(p.id, rels);
  } catch (err) {
    toast(err.message, "err");
  }
}

async function saveSelectedPlayer(playerId) {
  try {
    const skills = {};
    const potential = {};
    for (const sd of state.meta.playerSkills) {
      skills[sd.key] = Number($(`edPlSk_${sd.key}`).value);
      potential[sd.key] = Number($(`edPlPot_${sd.key}`).value);
    }
    const personality = {};
    for (const ax of (state.meta.personalityAxes || [])) {
      const el = $(`edPlPers_${ax.key}`);
      if (el) personality[ax.key] = Number(el.value);
    }
    const mapPositionAttributes = Object.keys(state.meta.playerPositions || {}).map((k) => ({
      positionType: Number(k),
      roleComfort: Number($(`edPlPos_${k}`)?.value ?? 5),
      progress: 0.0,
    }));
    const mapOpinions = [];
    document.querySelectorAll(".pl-map-op").forEach((el) => {
      if (el.value === "like" || el.value === "dislike") {
        mapOpinions.push({ mapId: Number(el.dataset.mid), like: el.value === "like" });
      }
    });
    const languagesSpoken = [];
    document.querySelectorAll("#plLangTableBody .pl-lang-row").forEach((tr) => {
      languagesSpoken.push({
        languageId: Number(tr.querySelector(".pl-lang-id").value),
        languageSkill: Number(tr.querySelector(".pl-lang-skill").value),
        limit: Number(tr.querySelector(".pl-lang-limit").value),
      });
    });
    const playerAwards = [];
    document.querySelectorAll("#plAwardsTableBody .pl-award-row").forEach((tr) => {
      playerAwards.push({
        type: Number(tr.querySelector(".pl-aw-type").value),
        tournamentTemplate: Number(tr.querySelector(".pl-aw-tourn").value),
        teamId: Number(tr.querySelector(".pl-aw-team").value),
        year: Number(tr.querySelector(".pl-aw-year").value),
        month: Number(tr.querySelector(".pl-aw-month").value),
        top20Placement: Number(tr.querySelector(".pl-aw-top20").value),
      });
    });
    const portrait = {};
    for (const pf of (state.meta.portraitFields || [])) {
      const el = $(`edPlPt_${pf.key}`);
      if (el) portrait[pf.key] = Number(el.value);
    }

    await apiPost("/api/player/update", {
      playerId,
      patch: {
        name: $("edPlName").value,
        age: Number($("edPlAge").value),
        nation: Number($("edPlNation").value),
        reputation: Number($("edPlRep").value),
        preferredMentality: Number($("edPlMent").value),
        longevity: Number($("edPlLong").value),
        useStartingPotential: $("edPlUseCustomPot").value === "true",
        startingPotential: $("edPlUseCustomPot").value === "true" ? Number($("edPlCustomPot").value) : 0,
        academyPlayer: $("edPlFlagAcad").checked,
        temporaryStandIn: $("edPlFlagStandIn").checked,
        dontReplaceOnRetire: $("edPlFlagNoRetire").checked,
        setForRetirement: $("edPlFlagRetiring").checked,
        monthsSinceNewContract: Number($("edPlMoCon")?.value ?? 6),
        monthsBenchedOrWithoutContract: Number($("edPlMoBench")?.value ?? 0),
        reputationProgress: Number($("edPlRepProg")?.value ?? 0),
        skillOffset: Number($("edPlSkOff")?.value ?? 0),
        skills,
        potential,
        personality,
        mapPositionAttributes,
        mapOpinions,
        languagesSpoken,
        playerAwards,
        portrait,
        contract: {
          teamId: Number($("edPlTeam").value),
          salaryYear: Number($("edPlSal").value),
          status: Number($("edPlStatus").value),
          igl: Number($("edPlIgl").value),
          sniper: Number($("edPlAwp").value),
          endYear: Number($("edPlExp").value),
          benched: $("edPlBench").value === "true",
          transferStatus: Number($("edPlTransStat").value),
          askingPrice: Number($("edPlAskPrice").value),
          contractType: Number($("edPlConType").value),
        },
      },
    });
    state.allPlayersBrief = [];
    toast("Player saved in memory (Basics, Personality, Maps, Languages, Portrait & Contract).");
    loadPlayersList();
    state.summary = await apiGet("/api/summary");
    updateTopbar();
  } catch (err) {
    toast(err.message, "err");
  }
}

async function deleteSelectedPlayer(playerId) {
  if (!confirm(`Delete player #${playerId}?`)) return;
  try {
    await apiPost("/api/player/delete", { playerId });
    state.selectedPlayerId = null;
    $("playerEditorCard").innerHTML = `<div class="muted">Player deleted.</div>`;
    toast("Player deleted.");
    loadPlayersList();
  } catch (err) {
    toast(err.message, "err");
  }
}

function openNewPlayerModal() {
  openModal("Add Custom Player", `
    <div class="form-grid">
      <div class="field"><label>Alias</label><input id="npName" placeholder="e.g. NewStar" /></div>
      <div class="field"><label>Age</label><input id="npAge" type="number" min="15" max="40" value="19" /></div>
      <div class="field"><label>Nation</label><select id="npNation">${nationOptionsHtml(102)}</select></div>
      <div class="field"><label>Primary Language</label><select id="npLang">${optionsHtml(state.meta.languages, 13)}</select></div>
      <div class="field"><label>Role Template Preset</label>
        <select id="npPreset">
          <option value="rifler">Star Rifler</option>
          <option value="awper">AWPer (High Snipers/Flicks)</option>
          <option value="igl">IGL (High Leadership/Decisions)</option>
          <option value="entry">Entry Fragger</option>
          <option value="support">Support / Utility</option>
        </select>
      </div>
      <div class="field"><label>Base Skill (1-20)</label><input id="npBaseSkill" type="number" step="0.5" min="5" max="19" value="15.0" /></div>
      <div class="field"><label>Potential Ceiling (1-20)</label><input id="npPot" type="number" min="5" max="20" value="18" /></div>
      <div class="field"><label>Use Custom Potential</label>
        <select id="npUseCustomPot" onchange="$('npCustomPot').disabled = (this.value !== 'true');">
          <option value="false" selected>Off (Per-Skill Caps / Engine)</option>
          <option value="true">On (Override 50-275 Pool)</option>
        </select>
      </div>
      <div class="field"><label>Custom Potential (50-275)</label><input id="npCustomPot" type="number" min="50" max="275" value="220" disabled /></div>
      <div class="field"><label>Team Assignment</label><select id="npTeam">${teamSelectOptionsHtml(0, true)}</select></div>
      <div class="field"><label>Salary / Yr ($)</label><input id="npSal" type="number" step="10000" value="180000" /></div>
    </div>
    <div style="margin-top:14px;display:flex;justify-content:flex-end;gap:8px;">
      <button class="btn" onclick="closeModal()">Cancel</button>
      <button class="btn primary" onclick="submitNewPlayer()">Create Player</button>
    </div>
  `);
}

async function submitNewPlayer() {
  try {
    const useCp = $("npUseCustomPot").value === "true";
    const res = await apiPost("/api/player/create", {
      name: $("npName").value,
      age: Number($("npAge").value),
      nation: Number($("npNation").value),
      languageId: Number($("npLang").value),
      preset: $("npPreset").value,
      baseSkill: Number($("npBaseSkill").value),
      potentialTarget: Number($("npPot").value),
      useStartingPotential: useCp,
      startingPotential: useCp ? Number($("npCustomPot").value) : 0,
      teamId: Number($("npTeam").value),
      salaryYear: Number($("npSal").value),
    });
    closeModal();
    toast(`Created player ${res.player.name}!`);
    await loadPlayersList();
    selectPlayer(res.player.id);
  } catch (err) {
    toast(err.message, "err");
  }
}

// ------------------------------------------------------------------
// TAB 4: Staff & Sponsors
// ------------------------------------------------------------------

async function loadStaffList() {
  try {
    if (!state.teams.length) state.teams = await apiGet("/api/teams");
    const q = encodeURIComponent($("staffSearch").value || "");
    state.staff = await apiGet(`/api/staff?q=${q}`);
    $("staffList").innerHTML = state.staff.map((s) => `
      <div class="list-row ${Number(s.id) === Number(state.selectedStaffId) ? "selected" : ""}" onclick="selectStaff(${s.id})">
        <div>
          <strong>${escapeHtml(s.name)}</strong> <span class="muted mono">${s.age}y</span>
          <div class="muted" style="font-size:11px;">${escapeHtml(s.roleName)} · ${escapeHtml(s.teamName)}</div>
        </div>
        <div class="mono" style="font-weight:700;">${s.avgSkill.toFixed(1)}</div>
      </div>
    `).join("");
  } catch (err) {
    toast(err.message, "err");
  }
}

function switchStaffSubTab(subKey) {
  state.staffSubTab = subKey;
  document.querySelectorAll("[data-stfsub]").forEach((b) => b.classList.toggle("active", b.dataset.stfsub === subKey));
  document.querySelectorAll("#staffEditorCard .subpanel").forEach((p) => p.classList.toggle("active", p.id === `stfsub-${subKey}`));
}

function applyStaffInterestPreset(roleId) {
  for (let r = 0; r < 6; r += 1) {
    const el = $(`edStInt_${r}`);
    const lbl = $(`lblStInt_${r}`);
    const v = r === roleId ? 20 : (r === 1 && roleId === 0 ? 12 : 4);
    if (el) el.value = v;
    if (lbl) lbl.textContent = v;
  }
  toast("Applied staff career interest preset (click Save Staff).");
}

function renderStaffLanguagesRows(langsList) {
  const tbody = $("stLangTableBody");
  if (!tbody) return;
  tbody.innerHTML = (langsList || []).map((lg) => `
    <tr class="st-lang-row">
      <td><select class="st-lang-id">${optionsHtml(state.meta?.languages || {}, lg.languageId)}</select></td>
      <td><input class="st-lang-skill" type="number" min="1" max="20" value="${lg.languageSkill ?? 20}" style="width:74px;" /></td>
      <td><input class="st-lang-limit" type="number" min="0" max="20" value="${lg.limit ?? 20}" style="width:74px;" /></td>
      <td><button type="button" class="btn danger sm" onclick="this.closest('tr').remove()">Remove</button></td>
    </tr>
  `).join("");
}

function addStaffLanguageRow(presetLangId = null) {
  const tbody = $("stLangTableBody");
  if (!tbody) return;
  const lid = presetLangId || Number($("stNewLangSelect")?.value || 13);
  const existing = Array.from(tbody.querySelectorAll(".st-lang-id")).map((s) => Number(s.value));
  if (existing.includes(lid)) {
    toast("Language already in staff list.", "warn");
    return;
  }
  const tr = document.createElement("tr");
  tr.className = "st-lang-row";
  tr.innerHTML = `
    <td><select class="st-lang-id">${optionsHtml(state.meta?.languages || {}, lid)}</select></td>
    <td><input class="st-lang-skill" type="number" min="1" max="20" value="20" style="width:74px;" /></td>
    <td><input class="st-lang-limit" type="number" min="0" max="20" value="20" style="width:74px;" /></td>
    <td><button type="button" class="btn danger sm" onclick="this.closest('tr').remove()">Remove</button></td>
  `;
  tbody.appendChild(tr);
}

function renderStaffCareerStatsRows(statsList) {
  const tbody = $("stCareerStatsBody");
  if (!tbody) return;
  tbody.innerHTML = (statsList || []).map((cs) => `
    <tr class="st-cs-row">
      <td><select class="st-cs-team">${teamSelectOptionsHtml(cs.teamId || 0, true)}</select></td>
      <td><select class="st-cs-role">${optionsHtml(state.meta?.staffRoles || {}, cs.staffRole ?? 0)}</select></td>
      <td><input class="st-cs-year" type="number" min="1999" max="2040" value="${cs.year ?? 2025}" style="width:74px;" /></td>
      <td><input class="st-cs-wins" type="number" min="0" value="${cs.matchesWon ?? 0}" style="width:74px;" /></td>
      <td><input class="st-cs-losses" type="number" min="0" value="${cs.matchesLost ?? 0}" style="width:74px;" /></td>
      <td><button type="button" class="btn danger sm" onclick="this.closest('tr').remove()">Remove</button></td>
    </tr>
  `).join("");
}

function addStaffCareerStatRow() {
  const tbody = $("stCareerStatsBody");
  if (!tbody) return;
  const tid = Number($("edStTeam")?.value || 0);
  const role = Number($("edStRole")?.value || 0);
  const tr = document.createElement("tr");
  tr.className = "st-cs-row";
  tr.innerHTML = `
    <td><select class="st-cs-team">${teamSelectOptionsHtml(tid, true)}</select></td>
    <td><select class="st-cs-role">${optionsHtml(state.meta?.staffRoles || {}, role)}</select></td>
    <td><input class="st-cs-year" type="number" min="1999" max="2040" value="2025" style="width:74px;" /></td>
    <td><input class="st-cs-wins" type="number" min="0" value="0" style="width:74px;" /></td>
    <td><input class="st-cs-losses" type="number" min="0" value="0" style="width:74px;" /></td>
    <td><button type="button" class="btn danger sm" onclick="this.closest('tr').remove()">Remove</button></td>
  `;
  tbody.prepend(tr);
}

async function selectStaff(staffId) {
  state.selectedStaffId = staffId;
  loadStaffList();
  try {
    if (!state.teams.length) state.teams = await apiGet("/api/teams");
    const d = await apiGet(`/api/staff/item?id=${staffId}`);
    const s = d.staff;
    const c = d.contract || { teamId: 0, role: 0, salaryYear: 90000, rejectAllStaffOffers: false, endDate: { year: 2028, month: 1, day: 1 } };
    const sk = s.skills || {};
    const pt = s.portrait || {};
    const potKeys = s.potential?.m_Keys || [];
    const potVals = s.potential?.m_Values || [];
    const potById = {};
    potKeys.forEach((k, i) => { potById[k] = potVals[i]; });
    const intMap = {};
    (s.careerInterests || []).forEach((it) => { intMap[it.roleType] = it.roleInterest; });
    const activeSub = state.staffSubTab || "basics";
    const portraitGroups = ["Head & Skin", "Eyes & Brows", "Nose & Mouth", "Hair & Beard", "Accessories"];

    $("staffEditorCard").innerHTML = `
      <div class="card-head">
        <div>
          <span class="card-title">${escapeHtml(s.name)}</span>
          <span class="tag-pill info mono">ID #${s.id}</span>
          <span class="tag-pill">${escapeHtml((state.meta.staffMentalities || {})[s.preferredMentality] || "Balanced")}</span>
          <span class="tag-pill">${(s.languagesSpoken || []).length} Langs</span>
          ${c.rejectAllStaffOffers ? `<span class="tag-pill warn">Reject Offers</span>` : ""}
        </div>
        <div style="display:flex;gap:6px;">
          ${c.teamId ? `<button class="btn sm" onclick="jumpToTeam(${c.teamId})">View Team</button>` : ""}
          <button class="btn ok sm" onclick="saveSelectedStaff(${s.id})">Save Staff</button>
          <button class="btn danger sm" onclick="deleteSelectedStaff(${s.id})">Delete</button>
        </div>
      </div>

      <div class="subtabs">
        <button type="button" class="subtab-btn ${activeSub === "basics" ? "active" : ""}" data-stfsub="basics" onclick="switchStaffSubTab('basics')">Basics &amp; Mentality</button>
        <button type="button" class="subtab-btn ${activeSub === "skills" ? "active" : ""}" data-stfsub="skills" onclick="switchStaffSubTab('skills')">Skills &amp; Caps</button>
        <button type="button" class="subtab-btn ${activeSub === "interests" ? "active" : ""}" data-stfsub="interests" onclick="switchStaffSubTab('interests')">Career Interests</button>
        <button type="button" class="subtab-btn ${activeSub === "languages" ? "active" : ""}" data-stfsub="languages" onclick="switchStaffSubTab('languages')">Languages</button>
        <button type="button" class="subtab-btn ${activeSub === "portrait" ? "active" : ""}" data-stfsub="portrait" onclick="switchStaffSubTab('portrait')">Portrait Mod</button>
        <button type="button" class="subtab-btn ${activeSub === "contract" ? "active" : ""}" data-stfsub="contract" onclick="switchStaffSubTab('contract')">Contract, Offers &amp; History</button>
      </div>

      <!-- STAFF SUBTAB 1: BASICS & MENTALITY -->
      <div id="stfsub-basics" class="subpanel ${activeSub === "basics" ? "active" : ""}">
        <div class="subcard">
          <div class="subcard-title">Staff Identity &amp; Mentality</div>
          <div class="form-grid">
            <div class="field"><label>Name</label><input id="edStName" value="${escapeHtml(s.name)}" /></div>
            <div class="field"><label>Age</label><input id="edStAge" type="number" min="18" max="75" value="${s.age}" /></div>
            <div class="field"><label>Nation</label><select id="edStNation">${nationOptionsHtml(s.nation)}</select></div>
            <div class="field"><label>Reputation (1-20)</label><input id="edStRep" type="number" min="1" max="20" value="${s.reputation}" /></div>
            <div class="field"><label>Preferred Mentality</label><select id="edStMent">${optionsHtml(state.meta.staffMentalities || {}, s.preferredMentality ?? 1)}</select></div>
            <div class="field"><label>Retirement Age</label><input id="edStRetAge" type="number" min="35" max="80" value="${s.retirementConsiderationAge ?? 55}" /></div>
          </div>
          <div style="margin-top:10px;">
            <label style="display:flex;gap:6px;align-items:center;"><input type="checkbox" id="edStFlagRetiring" ${s.setForRetirement ? "checked" : ""} /> Set for Retirement</label>
          </div>
        </div>
      </div>

      <!-- STAFF SUBTAB 2: SKILLS & POTENTIAL CAPS -->
      <div id="stfsub-skills" class="subpanel ${activeSub === "skills" ? "active" : ""}">
        <div class="subcard">
          <div class="subcard-title">Staff Skills (1-20) &amp; Potential Caps (1=auto)</div>
          <div class="form-grid">
            ${state.meta.staffSkills.map((sd) => `
              <div class="field">
                <label>${escapeHtml(sd.label)}</label>
                <div style="display:flex;gap:4px;">
                  <input id="edStSk_${sd.key}" type="number" step="0.5" min="1" max="20" value="${Number(sk[sd.key] ?? 10).toFixed(1)}" title="Skill" style="width:74px;" />
                  <input id="edStPot_${sd.key}" type="number" min="1" max="20" value="${potById[sd.id] ?? 1}" title="Potential Cap (1=auto)" style="width:58px;" />
                </div>
              </div>
            `).join("")}
          </div>
        </div>
      </div>

      <!-- STAFF SUBTAB 3: CAREER INTERESTS -->
      <div id="stfsub-interests" class="subpanel ${activeSub === "interests" ? "active" : ""}">
        <div class="subcard">
          <div class="card-head">
            <span class="subcard-title" style="margin:0;">Role Career Interests (1-20, <code>careerInterests</code>)</span>
            <div style="display:flex;gap:4px;flex-wrap:wrap;">
              <button type="button" class="btn sm" onclick="applyStaffInterestPreset(0)">Coach Focus</button>
              <button type="button" class="btn sm" onclick="applyStaffInterestPreset(2)">Analyst Focus</button>
              <button type="button" class="btn sm" onclick="applyStaffInterestPreset(4)">Scout Focus</button>
              <button type="button" class="btn sm" onclick="applyStaffInterestPreset(5)">Academy Focus</button>
            </div>
          </div>
          <div class="form-grid" style="grid-template-columns:1fr 1fr;">
            ${Object.entries(state.meta.staffRoles || {}).sort((a, b) => Number(a[0]) - Number(b[0])).map(([rid, rlabel]) => {
              const iv = intMap[rid] ?? 5;
              return `
                <div style="margin-bottom:6px;">
                  <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:2px;">
                    <strong>${escapeHtml(rlabel)}</strong>
                    <strong id="lblStInt_${rid}" class="mono">${iv}</strong>
                  </div>
                  <input id="edStInt_${rid}" type="range" min="1" max="20" value="${iv}" oninput="$('lblStInt_${rid}').textContent=this.value" style="width:100%;" />
                </div>
              `;
            }).join("")}
          </div>
        </div>
      </div>

      <!-- STAFF SUBTAB 4: LANGUAGES -->
      <div id="stfsub-languages" class="subpanel ${activeSub === "languages" ? "active" : ""}">
        <div class="subcard">
          <div class="card-head">
            <span class="subcard-title" style="margin:0;">Languages Spoken (<code>languagesSpoken</code>)</span>
            <div style="display:flex;gap:6px;align-items:center;">
              <select id="stNewLangSelect" style="width:160px;">${optionsHtml(state.meta.languages || {}, 13)}</select>
              <button type="button" class="btn primary sm" onclick="addStaffLanguageRow()">+ Add Language</button>
              <button type="button" class="btn sm" onclick="addStaffLanguageRow(13)">+ Fluent English</button>
            </div>
          </div>
          <div class="table-wrap" style="max-height:300px;">
            <table>
              <thead><tr><th>Language</th><th>Fluency (1-20)</th><th>Max Limit (0-20)</th><th>Action</th></tr></thead>
              <tbody id="stLangTableBody"></tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- STAFF SUBTAB 5: PORTRAIT MOD -->
      <div id="stfsub-portrait" class="subpanel ${activeSub === "portrait" ? "active" : ""}">
        <div class="subcard">
          <div class="card-head">
            <span class="subcard-title" style="margin:0;">Staff Portrait Appearance Mod (17 Genes)</span>
            <div style="display:flex;gap:6px;">
              <button type="button" class="btn sm" onclick="if($('edStPt_beard'))$('edStPt_beard').value=0;">Clean Shaven</button>
              <button type="button" class="btn warn sm" onclick="randomizePortraitFields('edStPt_')">Randomize</button>
            </div>
          </div>
          ${portraitGroups.map((pg) => `
            <div style="margin-bottom:10px;">
              <div style="font-size:11px;font-weight:700;color:var(--accent);text-transform:uppercase;margin-bottom:5px;">${escapeHtml(pg)}</div>
              <div class="form-grid" style="grid-template-columns:repeat(auto-fit,minmax(160px,1fr));">
                ${(state.meta.portraitFields || []).filter((pf) => pf.group === pg).map((pf) => `
                  <div class="field">
                    <label>${escapeHtml(pf.label)} (${pf.min}-${pf.max})</label>
                    <input id="edStPt_${pf.key}" type="number" min="${pf.min}" max="${pf.max}" value="${pt[pf.key] ?? pf.min}" />
                  </div>
                `).join("")}
              </div>
            </div>
          `).join("")}
        </div>
      </div>

      <!-- STAFF SUBTAB 6: CONTRACT, OFFERS & CAREER HISTORY -->
      <div id="stfsub-contract" class="subpanel ${activeSub === "contract" ? "active" : ""}">
        <div class="subcard">
          <div class="subcard-title">Active Contract &amp; Offer Settings</div>
          <div class="form-grid">
            <div class="field"><label>Team</label><select id="edStTeam">${teamSelectOptionsHtml(c.teamId, true)}</select></div>
            <div class="field"><label>Staff Role</label><select id="edStRole">${optionsHtml(state.meta.staffRoles, c.role ?? 0)}</select></div>
            <div class="field"><label>Salary / Yr ($)</label><input id="edStSal" type="number" step="5000" value="${c.salaryYear || 0}" /></div>
            <div class="field"><label>Contract Expiry Year</label><input id="edStEndYear" type="number" min="2026" max="2040" value="${c.endDate?.year ?? 2028}" /></div>
            <div class="field"><label>Expiry Month (1-12)</label><input id="edStEndMonth" type="number" min="1" max="12" value="${c.endDate?.month ?? 1}" /></div>
            <div class="field"><label>Expiry Day (1-28)</label><input id="edStEndDay" type="number" min="1" max="28" value="${c.endDate?.day ?? 1}" /></div>
            <div class="field"><label>Months Since New Contract</label><input id="edStMoCon" type="number" min="0" value="${s.monthsSinceNewContract ?? 6}" /></div>
            <div class="field"><label>Months Free Agent / Without Contract</label><input id="edStMoFree" type="number" min="0" value="${s.monthsBenchedOrWithoutContract ?? 0}" /></div>
          </div>
          <div style="margin-top:8px;">
            <label style="display:flex;gap:6px;align-items:center;"><input type="checkbox" id="edStRejectOffers" ${c.rejectAllStaffOffers ? "checked" : ""} /> Reject All Staff Offers (<code>rejectAllStaffOffers</code>)</label>
          </div>
        </div>
        <div class="subcard">
          <div class="card-head">
            <span class="subcard-title" style="margin:0;">Past Stints &amp; Completed Contract History (<code>careerStats</code>)</span>
            <button type="button" class="btn primary sm" onclick="addStaffCareerStatRow()">+ Add Stint Record</button>
          </div>
          <div class="table-wrap" style="max-height:240px;">
            <table>
              <thead><tr><th>Team</th><th>Role</th><th>Year</th><th>Matches Won</th><th>Matches Lost</th><th>Action</th></tr></thead>
              <tbody id="stCareerStatsBody"></tbody>
            </table>
          </div>
        </div>
      </div>
    `;
    renderStaffLanguagesRows(s.languagesSpoken || []);
    renderStaffCareerStatsRows(s.careerStats || []);
  } catch (err) {
    toast(err.message, "err");
  }
}

async function saveSelectedStaff(staffId) {
  try {
    const skills = {};
    const potential = {};
    state.meta.staffSkills.forEach((sd) => {
      skills[sd.key] = Number($(`edStSk_${sd.key}`).value);
      potential[sd.key] = Number($(`edStPot_${sd.key}`).value);
    });
    const careerInterests = Object.keys(state.meta.staffRoles || {}).map((rid) => ({
      roleType: Number(rid),
      roleInterest: Number($(`edStInt_${rid}`)?.value ?? 5),
    }));
    const languagesSpoken = [];
    document.querySelectorAll("#stLangTableBody .st-lang-row").forEach((tr) => {
      languagesSpoken.push({
        languageId: Number(tr.querySelector(".st-lang-id").value),
        languageSkill: Number(tr.querySelector(".st-lang-skill").value),
        limit: Number(tr.querySelector(".st-lang-limit").value),
      });
    });
    const portrait = {};
    for (const pf of (state.meta.portraitFields || [])) {
      const el = $(`edStPt_${pf.key}`);
      if (el) portrait[pf.key] = Number(el.value);
    }
    const careerStats = [];
    document.querySelectorAll("#stCareerStatsBody .st-cs-row").forEach((tr) => {
      careerStats.push({
        teamId: Number(tr.querySelector(".st-cs-team").value),
        staffRole: Number(tr.querySelector(".st-cs-role").value),
        year: Number(tr.querySelector(".st-cs-year").value),
        matchesWon: Number(tr.querySelector(".st-cs-wins").value),
        matchesLost: Number(tr.querySelector(".st-cs-losses").value),
      });
    });

    await apiPost("/api/staff/update", {
      staffId,
      patch: {
        name: $("edStName").value,
        age: Number($("edStAge").value),
        nation: Number($("edStNation").value),
        reputation: Number($("edStRep").value),
        preferredMentality: Number($("edStMent").value),
        retirementConsiderationAge: Number($("edStRetAge").value),
        setForRetirement: $("edStFlagRetiring").checked,
        monthsSinceNewContract: Number($("edStMoCon")?.value ?? 6),
        monthsBenchedOrWithoutContract: Number($("edStMoFree")?.value ?? 0),
        skills,
        potential,
        careerInterests,
        languagesSpoken,
        portrait,
        careerStats,
        contract: {
          teamId: Number($("edStTeam").value),
          role: Number($("edStRole").value),
          salaryYear: Number($("edStSal").value),
          endYear: Number($("edStEndYear").value),
          endMonth: Number($("edStEndMonth").value),
          endDay: Number($("edStEndDay").value),
          rejectAllStaffOffers: $("edStRejectOffers").checked,
        },
      },
    });
    toast("Staff updated (Mentality, Interests, Languages, Portrait & Contract).");
    loadStaffList();
    state.summary = await apiGet("/api/summary");
    updateTopbar();
  } catch (err) {
    toast(err.message, "err");
  }
}

async function deleteSelectedStaff(staffId) {
  if (!confirm(`Delete staff #${staffId}?`)) return;
  try {
    await apiPost("/api/staff/delete", { staffId });
    state.selectedStaffId = null;
    $("staffEditorCard").innerHTML = `<div class="muted">Deleted.</div>`;
    loadStaffList();
  } catch (err) {
    toast(err.message, "err");
  }
}

function openNewStaffModal() {
  openModal("Add Staff Member", `
    <div class="form-grid">
      <div class="field"><label>Name</label><input id="nsName" placeholder="e.g. Tactician" /></div>
      <div class="field"><label>Age</label><input id="nsAge" type="number" value="34" /></div>
      <div class="field"><label>Nation</label><select id="nsNation">${nationOptionsHtml(102)}</select></div>
      <div class="field"><label>Base Skill (1-20)</label><input id="nsBase" type="number" step="0.5" value="14" /></div>
      <div class="field"><label>Team</label><select id="nsTeam">${teamSelectOptionsHtml(0, true)}</select></div>
      <div class="field"><label>Role</label><select id="nsRole">${optionsHtml(state.meta.staffRoles, 0)}</select></div>
    </div>
    <div style="margin-top:14px;display:flex;justify-content:flex-end;gap:8px;">
      <button class="btn" onclick="closeModal()">Cancel</button>
      <button class="btn primary" onclick="submitNewStaff()">Create Staff</button>
    </div>
  `);
}

async function submitNewStaff() {
  try {
    const res = await apiPost("/api/staff/create", {
      name: $("nsName").value,
      age: Number($("nsAge").value),
      nation: Number($("nsNation").value),
      baseSkill: Number($("nsBase").value),
      teamId: Number($("nsTeam").value),
      role: Number($("nsRole").value),
    });
    closeModal();
    toast(`Created staff ${res.staff.name}!`);
    loadStaffList();
    selectStaff(res.staff.id);
  } catch (err) {
    toast(err.message, "err");
  }
}

async function loadSponsors() {
  try {
    const rows = await apiGet("/api/sponsors");
    $("sponsorsTable").innerHTML = rows.map((s) => `
      <tr>
        <td class="mono">${s.id}</td>
        <td>
          <div class="logo-field-wrap">
            ${logoImgHtml("sponsor", s.logo, "logo-thumb", `spLogoPrev_${s.id}`)}
            <input id="spLogo_${s.id}" value="${escapeHtml(s.logo || "")}" style="width:95px;" oninput="updateLogoPreview('sponsor', this.value, 'spLogoPrev_${s.id}')" />
            <button class="btn sm" onclick="openLogoPickerModal('sponsor', 'spLogo_${s.id}', 'spLogoPrev_${s.id}')">Pick</button>
          </div>
        </td>
        <td><input id="spName_${s.id}" value="${escapeHtml(s.name)}" style="width:140px;" /></td>
        <td><input id="spRep_${s.id}" type="number" min="1" max="20" value="${s.reputation}" style="width:55px;" /></td>
        <td><input id="spMon_${s.id}" type="number" step="500" value="${s.fixedMonthlyContribution}" style="width:90px;" /></td>
        <td><input id="spReq_${s.id}" type="number" value="${s.bonusPositionRequirement}" style="width:55px;" /></td>
        <td><input id="spBon_${s.id}" type="number" step="1000" value="${s.bonusPayout}" style="width:90px;" /></td>
        <td>
          <button class="btn ok sm" onclick="saveSponsorRow(${s.id})">Save</button>
          <button class="btn danger sm" onclick="deleteSponsorRow(${s.id})">Del</button>
        </td>
      </tr>
    `).join("");
  } catch (err) {
    toast(err.message, "err");
  }
}

async function saveSponsorRow(id) {
  try {
    await apiPost("/api/sponsor/save", {
      id,
      logo: $(`spLogo_${id}`).value,
      name: $(`spName_${id}`).value,
      reputation: Number($(`spRep_${id}`).value),
      fixedMonthlyContribution: Number($(`spMon_${id}`).value),
      bonusPositionRequirement: Number($(`spReq_${id}`).value),
      bonusPayout: Number($(`spBon_${id}`).value),
    });
    toast("Sponsor updated.");
    loadSponsors();
  } catch (err) {
    toast(err.message, "err");
  }
}

async function deleteSponsorRow(id) {
  try {
    await apiPost("/api/sponsor/delete", { id });
    toast("Sponsor deleted.");
    loadSponsors();
  } catch (err) {
    toast(err.message, "err");
  }
}

// ------------------------------------------------------------------
// TAB 5: Tournaments & Stages
// ------------------------------------------------------------------

function _awardsRowForRep(rep) {
  const r = Math.max(1, Math.min(20, Number(rep) || 1));
  const list = state.meta?.awardBreakdownByRep || [];
  return list.find((x) => Number(x.reputation) === r) || { reputation: r, tierLabel: tierBadge({ engineTier: 1 }), mvp: 0, evp: 0, honorableMentions: 5, stars: 0.5 };
}

function _formatAwardsHtml(rep) {
  const a = _awardsRowForRep(rep);
  const parts = [];
  if (a.mvp) parts.push(`<span class="award-pill award-mvp">${a.mvp} MVP</span>`);
  if (a.evp) parts.push(`<span class="award-pill award-evp">${a.evp} EVP</span>`);
  if (a.honorableMentions) parts.push(`<span class="award-pill award-hm">${a.honorableMentions} HM</span>`);
  return `<span class="tag-pill info">${a.stars}★ ${escapeHtml(a.tierLabel)}</span> ${parts.join("")}`;
}

function stageNameOptionsHtml(selectedKey) {
  const labels = state.meta?.stageNameLabels || {};
  const entries = Object.entries(labels);
  const matched = entries.some(([k]) => k === selectedKey);
  const opts = entries.map(([k, lbl]) => `<option value="${escapeHtml(k)}" ${k === selectedKey ? "selected" : ""}>${escapeHtml(lbl)} (${escapeHtml(k.replace("__CONTEXT_TOURNAMENT_STAGE_NAME", ""))})</option>`);
  if (selectedKey && !matched) {
    opts.unshift(`<option value="${escapeHtml(selectedKey)}" selected>${escapeHtml(selectedKey.replace("__CONTEXT_TOURNAMENT_STAGE_NAME", ""))}</option>`);
  }
  opts.push(`<option value="__CUSTOM__">+ Custom Stage Key...</option>`);
  return opts.join("");
}

function onStageNameSelectChange(sel) {
  if (sel.value === "__CUSTOM__") {
    const custom = prompt("Enter custom stage key (e.g. STAGE_3__CONTEXT_TOURNAMENT_STAGE_NAME):", "FINALS__CONTEXT_TOURNAMENT_STAGE_NAME");
    if (custom && custom.trim()) {
      const opt = document.createElement("option");
      opt.value = custom.trim();
      opt.textContent = custom.trim().replace("__CONTEXT_TOURNAMENT_STAGE_NAME", "");
      sel.insertBefore(opt, sel.lastElementChild);
      sel.value = opt.value;
    } else {
      sel.selectedIndex = 0;
    }
  }
  const item = sel.closest(".stage-editor-item");
  const titleEl = item?.querySelector(".st-title-lbl");
  if (titleEl) titleEl.textContent = sel.options[sel.selectedIndex]?.textContent.split(" (")[0] || sel.value;
}

function renderPrizeRowHtml(p) {
  return `
    <tr class="prize-row">
      <td><input class="pz-pos" type="number" min="1" value="${Number(p.position) || 1}" style="width:52px;" /></td>
      <td><input class="pz-mon" type="number" min="0" step="500" value="${Number(p.money) || 0}" style="width:95px;" oninput="recalcStagePrizeBadge(this)" /></td>
      <td><select class="pz-prog" onchange="recalcStagePrizeBadge(this)">${optionsHtml(state.meta.progressTypes, p.progressType ?? 0)}</select></td>
      <td><input class="pz-stk" type="number" min="0" max="100" step="0.1" value="${Number(p.stickerMoneyPercentages) || 0}" style="width:65px;" oninput="_updateTournamentStickerUi()" /></td>
      <td><button type="button" class="btn danger sm" onclick="const it=this.closest('.stage-editor-item');this.closest('tr').remove();recalcStagePrizeBadge(it);">×</button></td>
    </tr>
  `;
}

function recalcStagePrizeBadge(el) {
  const item = el?.closest ? el.closest(".stage-editor-item") : el;
  if (!item) return;
  let total = 0;
  let adv = 0;
  item.querySelectorAll("tbody.st-prizes-tbody tr.prize-row").forEach((tr) => {
    total += Number(tr.querySelector(".pz-mon").value) || 0;
    if (Number(tr.querySelector(".pz-prog").value) === 1) adv += 1;
  });
  const totEl = item.querySelector(".st-total-prize");
  const advEl = item.querySelector(".st-adv-count");
  if (totEl) totEl.textContent = `$${total.toLocaleString()}`;
  if (advEl) {
    advEl.textContent = adv ? `${adv} advance` : "0 advance";
    advEl.style.display = adv ? "inline-block" : "none";
  }
  _updateTournamentStickerUi();
}

function addPrizeRowToStage(btn) {
  const item = btn.closest(".stage-editor-item");
  const tbody = item.querySelector("tbody.st-prizes-tbody");
  const nextPos = tbody.querySelectorAll("tr.prize-row").length + 1;
  tbody.insertAdjacentHTML("beforeend", renderPrizeRowHtml({ position: nextPos, money: 0, progressType: 0, stickerMoneyPercentages: 0 }));
  recalcStagePrizeBadge(item);
}

function quickFillStagePrizes(btn) {
  const item = btn.closest(".stage-editor-item");
  const parts = Math.max(2, Number(item.querySelector(".st-parts")?.value) || 8);
  const rawTotal = prompt("Total prize pool ($) to distribute for this stage (e.g. 500000, or 0 for qualifier):", "250000");
  if (rawTotal === null) return;
  const totalMoney = Math.max(0, Number(rawTotal) || 0);
  const advRaw = prompt("How many top placements advance to the next stage? (0 for Playoffs / Finals):", "0");
  if (advRaw === null) return;
  const advCount = Math.max(0, Math.min(parts, Number(advRaw) || 0));

  const weights = [];
  for (let i = 1; i <= parts; i++) {
    weights.push(1 / Math.pow(i, 1.35));
  }
  const wSum = weights.reduce((a, b) => a + b, 0) || 1;
  let allocated = 0;
  const rows = [];
  for (let i = 1; i <= parts; i++) {
    let m = i < parts ? Math.round((totalMoney * weights[i - 1] / wSum) / 250) * 250 : Math.max(0, totalMoney - allocated);
    allocated += m;
    rows.push({ position: i, money: totalMoney === 0 ? 0 : m, progressType: i <= advCount ? 1 : 0, stickerMoneyPercentages: 0 });
  }
  item.querySelector("tbody.st-prizes-tbody").innerHTML = rows.map(renderPrizeRowHtml).join("");
  recalcStagePrizeBadge(item);
}

async function openVisualizerModal(template) {
  try {
    const v = await apiGet(`/api/tournaments/visualize?template=${template}`);
    const renderCycle = (title, cyc) => `
      <div class="subcard">
        <div class="card-head" style="margin-bottom:6px;">
          <strong>${escapeHtml(title)}: ${escapeHtml(cyc.sim.startDate)} .. ${escapeHtml(cyc.sim.endDate)} (${cyc.sim.durationDays}d)</strong>
          <span class="muted mono">Invite sent: ${escapeHtml(cyc.sim.invitationDate)} · Anchor DoW: ${escapeHtml(cyc.sim.anchorDow)}</span>
        </div>
        <div class="viz-timeline">
          ${(cyc.rounds || []).map((r) => `
            <div class="viz-round ${r.isLan ? "lan" : ""} ${/Grand Final|Semi|Quarter/i.test(r.roundLabel) ? "final" : ""}">
              <div style="display:flex;justify-content:space-between;align-items:center;">
                <strong class="mono">${escapeHtml(r.date)} (${escapeHtml(r.dow)})</strong>
                <span class="tag-pill ${r.isLan ? "warn" : "info"}" style="font-size:10px;">${escapeHtml(r.slotLabel)}</span>
              </div>
              <div style="margin-top:3px;font-weight:700;">Stage ${r.stageNum}: ${escapeHtml(r.stageLabel)}</div>
              <div style="color:var(--accent);font-weight:600;">${escapeHtml(r.roundLabel)}</div>
              <div class="muted" style="font-size:10.5px;">${escapeHtml(r.venueName)} · ${r.participants} teams · ${r.groups} grp</div>
            </div>
          `).join("") || '<div class="muted">No scheduled rounds generated.</div>'}
        </div>
      </div>
    `;
    openModal(`Tournament Run Visualizer — ${v.name} (tpl=${v.template})`, `
      <div style="display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:10px;">
        ${_formatAwardsHtml(v.awards.reputation)}
        <span class="tag-pill ok mono">Rep ${v.awards.reputation}</span>
      </div>
      ${renderCycle("Spring Cycle (Months 1-6)", v.spring)}
      ${renderCycle("Fall Cycle (Months 7-12, +6m Wrap)", v.fall)}
      <div class="subcard">
        <div class="subcard-title">How This Tournament Shifts Across All 7 Anchor Start Weekdays</div>
        <p class="muted" style="margin:0 0 6px;">Because Stages specify allowed <code>daysOfWeekPlayed</code>, the exact same <code>startMonthRange / startDayRange</code> shifts start/end dates depending on which weekday Day 1 lands on:</p>
        <div class="table-wrap">
          <table>
            <thead><tr><th>If Anchor Lands On</th><th>Calendar Year Sample</th><th>First Match Date</th><th>End Date</th><th>Total Span</th></tr></thead>
            <tbody>
              ${(v.weekdayShifts || []).map((ws) => `
                <tr>
                  <td><strong>${escapeHtml(ws.anchorDow)}</strong></td>
                  <td class="mono">${ws.year}</td>
                  <td class="mono">${escapeHtml(ws.startDate)}</td>
                  <td class="mono">${escapeHtml(ws.endDate)}</td>
                  <td class="mono">${ws.durationDays}d</td>
                </tr>
              `).join("")}
            </tbody>
          </table>
        </div>
      </div>
    `, true);
  } catch (err) {
    toast(err.message, "err");
  }
}

async function loadTournamentsList() {
  try {
    state.tournaments = await apiGet("/api/tournaments");
    const q = ($("tournSearch").value || "").trim().toLowerCase();
    const tf = $("tournTierFilter").value;
    const filtered = state.tournaments.filter((t) => {
      if (tf && String(t.tier.engineTier) !== tf) return false;
      if (q && !`${t.name} ${t.template}`.toLowerCase().includes(q)) return false;
      return true;
    });
    $("tournList").innerHTML = filtered.map((t) => `
      <div class="list-row ${Number(t.template) === Number(state.selectedTemplate) ? "selected" : ""}" onclick="selectTournament(${t.template})">
        <div style="display:flex;align-items:center;gap:8px;">
          ${logoImgHtml("tournament", t.logo)}
          <div>
            <strong>${escapeHtml(t.name)}</strong> ${t.outdated ? '<span class="tag-pill warn">Outdated</span>' : ""}
            <div class="muted" style="font-size:11px;">tpl=${t.template} · M${t.startMonthRange}/D${t.startDayRange} (${escapeHtml(t.simSpring.start)}..${escapeHtml(t.simSpring.end)})</div>
          </div>
        </div>
        <div style="text-align:right;">
          ${tierBadge(t.tier)}
          <div class="muted mono" style="font-size:11px;">$${Number(t.prizePool).toLocaleString()}</div>
        </div>
      </div>
    `).join("") || `<div class="muted" style="padding:14px;">No tournaments match filter.</div>`;
  } catch (err) {
    toast(err.message, "err");
  }
}

function jumpToTournament(template) {
  switchTab("tournaments");
  selectTournament(template);
}

function _updateTournamentStickerUi() {
  const rep = Number($("edTrRep")?.value) || 0;
  const isMajor = rep >= 19;
  let totalPct = 0;
  document.querySelectorAll("#edStagesContainer input.pz-stk").forEach((inp) => {
    totalPct += Number(inp.value) || 0;
    inp.disabled = !isMajor;
    inp.title = isMajor ? "Share % of Major Sticker Pool" : "Sticker Money is Major Only (Rep >= 19)";
  });
  if ($("edTrStLow")) $("edTrStLow").disabled = !isMajor;
  if ($("edTrStHigh")) $("edTrStHigh").disabled = !isMajor;
  if ($("edTrStickerStatus")) {
    const low = Number($("edTrStLow")?.value) || 0;
    const high = Number($("edTrStHigh")?.value) || 0;
    if (!isMajor) {
      $("edTrStickerStatus").innerHTML = (low > 0 || high > 0 || totalPct > 0)
        ? `<span class="tag-pill err">Non-Major has Sticker Data!</span> <button type="button" class="btn danger sm" onclick="zeroTournamentStickers()">Zero Sticker Data</button>`
        : `<span class="muted">Major Only (Rep 19-20)</span>`;
    } else {
      const ok = high === 0 || Math.abs(totalPct - 100) <= 0.5;
      $("edTrStickerStatus").innerHTML = `<span class="tag-pill ${ok ? "ok" : "warn"} mono">Stage Sum: ${totalPct.toFixed(2)}% ${high > 0 ? "(Target 100%)" : "(Disabled)"}</span>`;
    }
  }
}

function zeroTournamentStickers() {
  if ($("edTrStLow")) $("edTrStLow").value = 0;
  if ($("edTrStHigh")) $("edTrStHigh").value = 0;
  document.querySelectorAll("#edStagesContainer input.pz-stk").forEach((inp) => { inp.value = 0; });
  _updateTournamentStickerUi();
  toast("Cleared sticker money & percentages on this non-Major tournament.");
}

async function cloneSelectedTournament(template) {
  try {
    const res = await apiPost("/api/tournament/clone", { template });
    state.tournaments = res.tournaments;
    toast(`Copied tournament to template=${res.template}!`);
    selectTournament(res.template);
    state.summary = await apiGet("/api/summary");
    updateTopbar();
  } catch (err) {
    toast(err.message, "err");
  }
}

function selectTournament(template) {
  state.selectedTemplate = template;
  loadTournamentsList();
  const t = state.tournaments.find((x) => Number(x.template) === Number(template));
  if (!t) return;
  const stages = t.stages || [];
  const isMajor = Number(t.reputation) >= 19;

  $("tournEditorCard").innerHTML = `
    <div class="card-head">
      <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
        ${logoImgHtml("tournament", t.logo, "logo-thumb logo-thumb-lg", "edTrLogoPrev")}
        <div>
          <span class="card-title">${escapeHtml(t.name)}</span>
          ${tierBadge(t.tier)}
          <span class="tag-pill info mono">tpl=${t.template}</span>
          <div id="edTrAwardsBadge" style="margin-top:4px;">${_formatAwardsHtml(t.reputation)}</div>
        </div>
      </div>
      <div style="display:flex;gap:6px;flex-wrap:wrap;">
        <button class="btn primary sm" onclick="openVisualizerModal(${t.template})">Visualize Run</button>
        <button class="btn sm" onclick="openSlotFinderModal(${t.template})">Find Conflict-Free Slot</button>
        <button class="btn sm" onclick="cloneSelectedTournament(${t.template})">Copy Tournament</button>
        <button class="btn ok sm" onclick="saveSelectedTournament(${t.template})">Save Tournament</button>
        <button class="btn danger sm" onclick="deleteSelectedTournament(${t.template})">Delete</button>
      </div>
    </div>

    <div class="form-grid">
      <div class="field"><label>Event Name</label><input id="edTrName" value="${escapeHtml(t.name)}" /></div>
      <div class="field"><label>Logo Key</label>
        <div class="logo-field-wrap">
          <input id="edTrLogo" value="${escapeHtml(t.logo)}" oninput="updateLogoPreview('tournament', this.value, 'edTrLogoPrev')" />
          <button type="button" class="btn sm" onclick="openLogoPickerModal('tournament', 'edTrLogo', 'edTrLogoPrev')">Pick/Import</button>
        </div>
      </div>
      <div class="field"><label>Unique Template ID</label><input id="edTrTpl" type="number" min="1" value="${t.template}" /></div>
      <div class="field"><label>Reputation (1-20) -> Tier &amp; Awards</label><input id="edTrRep" type="number" min="1" max="20" value="${t.reputation}" oninput="$('edTrAwardsBadge').innerHTML = _formatAwardsHtml(this.value); _updateTournamentStickerUi();" /></div>
      <div class="field"><label>Start Month (1-6 Half-Yr Loop)</label><input id="edTrMonth" type="number" min="1" max="6" value="${t.startMonthRange}" /></div>
      <div class="field"><label>Start Day (1-28 Safest / 1-31)</label><input id="edTrDay" type="number" min="1" max="31" value="${t.startDayRange}" /></div>
      <div class="field"><label>Dynamic Location</label><select id="edTrDyn">${optionsHtml(state.meta.dynamicLocations, t.dynamicLocation)}</select></div>
      <div class="field"><label>BO5 Grand Finals</label><select id="edTrBo5"><option value="true" ${t.bestOfFiveGrandFinals ? "selected" : ""}>Yes (BO5)</option><option value="false" ${!t.bestOfFiveGrandFinals ? "selected" : ""}>No</option></select></div>
      <div class="field"><label>Outdated / Disabled</label><select id="edTrOut"><option value="false" ${!t.outdated ? "selected" : ""}>Active</option><option value="true" ${t.outdated ? "selected" : ""}>Outdated (Disabled)</option></select></div>
      <div class="field" style="grid-column: span 2;"><label>Sticker Money Low / High <span class="muted">(Major Only: Rep 19-20)</span></label>
        <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;">
          <input id="edTrStLow" type="number" step="250000" value="${t.stickerMoneyLow}" ${!isMajor ? "disabled" : ""} style="width:110px;" oninput="_updateTournamentStickerUi()" />
          <input id="edTrStHigh" type="number" step="250000" value="${t.stickerMoneyHigh}" ${!isMajor ? "disabled" : ""} style="width:110px;" oninput="_updateTournamentStickerUi()" />
          <span id="edTrStickerStatus"></span>
        </div>
      </div>
    </div>

    <div class="subcard" style="margin-top:12px;">
      <div class="card-head" style="margin-bottom:8px;">
        <span class="subcard-title" style="margin:0;">Stages (${stages.length}) — Spring Window: <span class="mono">${escapeHtml(t.simSpring.start)} .. ${escapeHtml(t.simSpring.end)}</span> (${t.simSpring.days}d)</span>
        <button class="btn primary sm" onclick="addStageToEditor(${t.template})">+ Add Stage</button>
      </div>
      <div id="edStagesContainer">${stages.map((st, idx) => renderStageEditorBlock(st, idx)).join("")}</div>
    </div>
  `;
  _updateTournamentStickerUi();
}

function renderStageEditorBlock(st, idx) {
  const dows = new Set((st.daysOfWeekPlayed || []).map(Number));
  const prizes = st.prizes || [];
  const totalPrize = prizes.reduce((acc, p) => acc + (p.money || 0), 0);
  const advSpots = prizes.filter((p) => Number(p.progressType) === 1).length;
  const stageLabel = (state.meta?.stageNameLabels || {})[st.name] || (st.name || "").replace("__CONTEXT_TOURNAMENT_STAGE_NAME", "");
  return `
    <div class="subcard stage-editor-item" data-sidx="${idx}" style="border-left:3px solid var(--accent);">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
        <strong>Stage #${st.stage} — <span class="st-title-lbl">${escapeHtml(stageLabel)}</span></strong>
        <div style="display:flex;gap:6px;align-items:center;">
          <span class="tag-pill ok mono st-total-prize">$${totalPrize.toLocaleString()}</span>
          <span class="tag-pill info st-adv-count" style="display:${advSpots ? "inline-block" : "none"};">${advSpots} advance</span>
          <button class="btn danger sm" onclick="this.closest('.stage-editor-item').remove()">Remove</button>
        </div>
      </div>
      <div class="form-grid">
        <div class="field"><label>Stage #</label><input class="st-num" type="number" min="1" value="${st.stage}" /></div>
        <div class="field"><label>Stage Name</label><select class="st-name" onchange="onStageNameSelectChange(this)">${stageNameOptionsHtml(st.name)}</select></div>
        <div class="field"><label>Format Type</label><select class="st-fmt">${optionsHtml(state.meta.formatTypes, st.formatType)}</select></div>
        <div class="field"><label>Participants</label><input class="st-parts" type="number" min="2" value="${st.numberOfParticipants}" /></div>
        <div class="field"><label>Groups</label><input class="st-grps" type="number" min="1" value="${st.groups}" /></div>
        <div class="field"><label>Maps / Match (BO1/3/5)</label><input class="st-bo" type="number" min="1" max="5" step="2" value="${st.mapsPerMatch}" /></div>
        <div class="field"><label>Venue</label><select class="st-venue">${optionsHtml(state.meta.venues, st.venue)}</select></div>
        <div class="field"><label>Region Eligibility</label><select class="st-reg">${optionsHtml(state.meta.regions, st.regionEligibility)}</select></div>
        <div class="field"><label>Match Session Slot</label><select class="st-slot">${optionsHtml(state.meta.sessionSlots, st.matchSessionSlot || 3)}</select></div>
        <div class="field"><label>Swiss Req Wins / Max Loss</label>
          <div style="display:flex;gap:4px;">
            <input class="st-rw" type="number" min="1" max="5" value="${st.requiredWins ?? 3}" style="width:65px;" />
            <input class="st-ml" type="number" min="1" max="5" value="${st.maxLosses ?? 2}" style="width:65px;" />
          </div>
        </div>
        <div class="field"><label>Open Signup</label><select class="st-open"><option value="false" ${!st.openSignup ? "selected" : ""}>Invite Only</option><option value="true" ${st.openSignup ? "selected" : ""}>Open Signup</option></select></div>
      </div>
      <div style="margin-top:8px;">
        <label style="font-size:11px;color:var(--muted);font-weight:600;display:block;margin-bottom:4px;">Days of Week Played:</label>
        <div class="dow-chips">
          ${[1, 2, 3, 4, 5, 6, 7].map((d) => `<span class="dow-chip ${dows.has(d) ? "on" : ""}" data-dow="${d}" onclick="this.classList.toggle('on')">${state.meta.daysOfWeek[d]}</span>`).join("")}
        </div>
      </div>
      <div class="prize-table-wrap">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;flex-wrap:wrap;gap:6px;">
          <span style="font-size:11px;font-weight:700;color:var(--muted);">Prize Pool Allotment &amp; Stage Progression</span>
          <div style="display:flex;gap:5px;">
            <button type="button" class="btn sm" onclick="quickFillStagePrizes(this)">Quick-Fill Standard Split</button>
            <button type="button" class="btn primary sm" onclick="addPrizeRowToStage(this)">+ Add Placement</button>
          </div>
        </div>
        <div class="table-wrap" style="max-height:190px;">
          <table>
            <thead><tr><th>Pos #</th><th>Money ($)</th><th>Progress Type</th><th>Sticker %</th><th></th></tr></thead>
            <tbody class="st-prizes-tbody">${prizes.map(renderPrizeRowHtml).join("")}</tbody>
          </table>
        </div>
      </div>
    </div>
  `;
}

function addStageToEditor(template) {
  const cont = $("edStagesContainer");
  const curCount = cont.querySelectorAll(".stage-editor-item").length;
  const blank = {
    stage: curCount + 1,
    name: "PLAYOFFS__CONTEXT_TOURNAMENT_STAGE_NAME",
    formatType: 0,
    numberOfParticipants: 8,
    groups: 1,
    mapsPerMatch: 3,
    matchSessionSlot: 3,
    daysOfWeekPlayed: [5, 6, 7],
    venue: 2,
    regionEligibility: 3,
    openSignup: false,
    requiredWins: 0,
    maxLosses: 0,
    prizes: [{ position: 1, money: 100000, progressType: 0, stickerMoneyPercentages: 0 }],
  };
  cont.insertAdjacentHTML("beforeend", renderStageEditorBlock(blank, curCount));
  _updateTournamentStickerUi();
}

function collectStagesFromEditor() {
  return Array.from(document.querySelectorAll("#edStagesContainer .stage-editor-item")).map((el) => {
    const dows = Array.from(el.querySelectorAll(".dow-chip.on")).map((c) => Number(c.dataset.dow));
    const prizes = Array.from(el.querySelectorAll("tbody.st-prizes-tbody tr.prize-row")).map((tr) => ({
      position: Math.max(1, Number(tr.querySelector(".pz-pos").value) || 1),
      money: Math.max(0, Number(tr.querySelector(".pz-mon").value) || 0),
      progressType: Number(tr.querySelector(".pz-prog").value) || 0,
      stickerMoneyPercentages: Number(tr.querySelector(".pz-stk").value) || 0,
    }));
    return {
      stage: Number(el.querySelector(".st-num").value),
      name: el.querySelector(".st-name").value,
      formatType: Number(el.querySelector(".st-fmt").value),
      numberOfParticipants: Number(el.querySelector(".st-parts").value),
      groups: Number(el.querySelector(".st-grps").value),
      mapsPerMatch: Number(el.querySelector(".st-bo").value),
      venue: Number(el.querySelector(".st-venue").value),
      regionEligibility: Number(el.querySelector(".st-reg").value),
      matchSessionSlot: Number(el.querySelector(".st-slot").value),
      requiredWins: Number(el.querySelector(".st-rw").value),
      maxLosses: Number(el.querySelector(".st-ml").value),
      openSignup: el.querySelector(".st-open").value === "true",
      daysOfWeekPlayed: dows.length ? dows : [1, 2, 3],
      prizes,
    };
  });
}

async function saveSelectedTournament(origTemplate) {
  try {
    const stages = collectStagesFromEditor();
    const res = await apiPost("/api/tournament/save", {
      origTemplate,
      template: Number($("edTrTpl").value),
      name: $("edTrName").value,
      logo: $("edTrLogo").value,
      reputation: Number($("edTrRep").value),
      startMonthRange: Number($("edTrMonth").value),
      startDayRange: Number($("edTrDay").value),
      dynamicLocation: Number($("edTrDyn").value),
      bestOfFiveGrandFinals: $("edTrBo5").value === "true",
      outdated: $("edTrOut").value === "true",
      stickerMoneyLow: Number($("edTrStLow").value),
      stickerMoneyHigh: Number($("edTrStHigh").value),
      stages,
    });
    state.tournaments = res.tournaments;
    state.selectedTemplate = res.template;
    toast("Tournament & stages saved in memory!");
    selectTournament(res.template);
    state.summary = await apiGet("/api/summary");
    updateTopbar();
  } catch (err) {
    toast(err.message, "err");
  }
}

async function deleteSelectedTournament(template) {
  if (!confirm(`Delete tournament template ${template} and all its stages?`)) return;
  try {
    await apiPost("/api/tournament/delete", { template });
    state.selectedTemplate = null;
    $("tournEditorCard").innerHTML = `<div class="muted">Tournament deleted.</div>`;
    toast("Tournament deleted.");
    loadTournamentsList();
  } catch (err) {
    toast(err.message, "err");
  }
}

function openNewTournamentModal() {
  openModal("Add New Tournament", `
    <div class="form-grid">
      <div class="field"><label>Tournament Name</label><input id="ntName" placeholder="e.g. Global Masters" /></div>
      <div class="field"><label>Tier Preset</label>
        <select id="ntPreset" onchange="if(this.value==='MAJOR')$('ntRep').value=20;else if(this.value==='S')$('ntRep').value=16;else if(this.value==='A')$('ntRep').value=10;else if(this.value==='B')$('ntRep').value=7;else $('ntRep').value=3;">
          <option value="S">S-Tier (16-Team Swiss + 8-Team Arena Playoffs)</option>
          <option value="MAJOR">Major / Flagship (T5)</option>
          <option value="A">A-Tier LAN/Studio (T3)</option>
          <option value="B">B-Tier Online Cup (T2)</option>
          <option value="C">C-Tier Regional Cup (T1)</option>
        </select>
      </div>
      <div class="field"><label>Reputation (1-20)</label><input id="ntRep" type="number" min="1" max="20" value="16" /></div>
      <div class="field"><label>Start Month (1-6)</label><input id="ntMonth" type="number" min="1" max="6" value="2" /></div>
      <div class="field"><label>Start Day (1-31)</label><input id="ntDay" type="number" min="1" max="31" value="10" /></div>
      <div class="field"><label>BO5 Final</label><select id="ntBo5"><option value="true" selected>Yes</option><option value="false">No</option></select></div>
    </div>
    <div style="margin-top:14px;display:flex;justify-content:flex-end;gap:8px;">
      <button class="btn" onclick="closeModal()">Cancel</button>
      <button class="btn primary" onclick="submitNewTournament()">Create Tournament</button>
    </div>
  `);
}

async function submitNewTournament() {
  try {
    const res = await apiPost("/api/tournament/save", {
      origTemplate: 0,
      name: $("ntName").value,
      presetTier: $("ntPreset").value,
      reputation: Number($("ntRep").value),
      startMonthRange: Number($("ntMonth").value),
      startDayRange: Number($("ntDay").value),
      bestOfFiveGrandFinals: $("ntBo5").value === "true",
    });
    closeModal();
    state.tournaments = res.tournaments;
    toast(`Created tournament template=${res.template}!`);
    selectTournament(res.template);
    state.summary = await apiGet("/api/summary");
    updateTopbar();
  } catch (err) {
    toast(err.message, "err");
  }
}

async function openSlotFinderModal(template) {
  try {
    const res = await apiGet(`/api/tournaments/suggest-slots?template=${template}`);
    openModal(`Conflict-Free Start Windows — ${res.name}`, `
      <p class="muted" style="margin-top:0;">Current: <strong>Month ${res.current.startMonthRange} / Day ${res.current.startDayRange}</strong>. Ranked by <strong>Clean Anchor Weekdays (7/7 = zero overlaps regardless which weekday Jan 1 falls on)</strong>, then fewest same/higher tier &amp; LAN collisions:</p>
      <div class="table-wrap" style="max-height:400px;">
        <table>
          <thead><tr><th>Start Anchor</th><th>Sample Window</th><th>Clean Weekdays</th><th>Same/Higher Hits</th><th>LAN Hits</th><th>Blocking Events</th><th>Apply</th></tr></thead>
          <tbody>
            ${res.suggestions.map((s) => `
              <tr>
                <td class="mono">M${s.startMonthRange} / D${s.startDayRange}</td>
                <td class="mono">${escapeHtml(s.startDate)} .. ${escapeHtml(s.endDate)}</td>
                <td><span class="tag-pill ${s.cleanWeekdays === 7 ? "ok" : (s.cleanWeekdays >= 4 ? "warn" : "err")}">${s.cleanWeekdays ?? 0}/7 clean</span></td>
                <td><span class="tag-pill ${s.sameOrHigherConflicts === 0 ? "ok" : "err"}">${s.sameOrHigherConflicts}</span></td>
                <td><span class="tag-pill ${s.lanConflicts === 0 ? "ok" : "warn"}">${s.lanConflicts}</span></td>
                <td style="font-size:11px;">${escapeHtml((s.blockingNames || []).join(", ") || "Year-Proof Clean!")}</td>
                <td><button class="btn primary sm" onclick="applySuggestedSlot(${template}, ${s.startMonthRange}, ${s.startDayRange})">Move Here</button></td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>
    `, true);
  } catch (err) {
    toast(err.message, "err");
  }
}

async function applySuggestedSlot(template, month, day) {
  try {
    await apiPost("/api/tournament/save", { origTemplate: template, startMonthRange: month, startDayRange: day });
    closeModal();
    toast(`Moved tournament tpl=${template} to M${month}/D${day}.`);
    state.tournaments = await apiGet("/api/tournaments");
    if (document.querySelector('#tab-schedule.active')) loadScheduleAudit();
    if (document.querySelector('#tab-tournaments.active')) selectTournament(template);
  } catch (err) {
    toast(err.message, "err");
  }
}

// ------------------------------------------------------------------
// TAB 6: Schedule Overlap Audit
// ------------------------------------------------------------------

async function loadScheduleAudit() {
  try {
    state.schedule = await apiGet("/api/tournaments/schedule");
    renderScheduleAudit();
  } catch (err) {
    toast(err.message, "err");
  }
}

function _matchTierFilter(evOrPairTier, filterVal) {
  if (filterVal === "all") return true;
  if (filterVal === "S") return evOrPairTier.engineTier >= 4;
  return `T${evOrPairTier.engineTier}` === filterVal;
}

function _dowMatrixHtml(matrix) {
  const letters = ["M", "T", "W", "T", "F", "S", "S"];
  const arr = matrix && matrix.length === 7 ? matrix : [false, false, false, false, false, false, false];
  return `<span class="dow-matrix" title="Overlap by Start Anchor Weekday (Mon..Sun)">${arr.map((hit, i) => `<span class="dow-dot ${hit ? "hit" : "clean"}">${letters[i]}</span>`).join("")}</span>`;
}

function renderScheduleAudit() {
  const sc = state.schedule;
  if (!sc) return;
  const sum = sc.summary || {};
  const tierFilter = $("schedTierFilter").value;
  const whenFilter = $("schedWhenFilter")?.value || "all";
  const lanOnly = $("schedLanOnly").checked;

  $("schedKpis").innerHTML = [
    { l: "Total Overlaps (7-Anchor)", v: sum.totalConflicts, s: `${sum.alwaysOverlaps || 0} Always (7/7) · ${sum.conditionalOverlaps || 0} Weekday-Dep`, cls: (sum.alwaysOverlaps || 0) > 0 ? "bad" : "ok" },
    { l: "Critical / High", v: `${sum.criticalConflicts} / ${sum.highConflicts}`, s: "Same/high tier overlaps", cls: sum.criticalConflicts > 0 ? "bad" : "ok" },
    { l: "S-Tier vs S-Tier", v: sum.sTierConflicts, s: "Rep 13-20 self-clashes", cls: sum.sTierConflicts > 0 ? "bad" : "ok" },
    { l: "LAN Collisions", v: sum.lanConflicts, s: "Overlapping Studio/Arena LANs", cls: sum.lanConflicts > 0 ? "bad" : "ok" },
    { l: "Safe Parallel Regionals", v: sum.safeParallelRegionals, s: "Distinct regions (EU/AM/AS)" },
    { l: "Stage Chain Errors", v: sum.stageChainIssues, s: "Format / spot / day checks", cls: sum.stageChainIssues > 0 ? "bad" : "ok" },
  ].map((k) => `<div class="kpi"><div class="kpi-lbl">${k.l}</div><div class="kpi-val ${k.cls || ""}">${k.v}</div><div class="kpi-sub">${escapeHtml(k.s)}</div></div>`).join("");

  const conflicts = (sc.conflicts || []).filter((c) => {
    if (lanOnly && !c.hasLanOverlap) return false;
    if (whenFilter === "always" && !c.alwaysOverlaps) return false;
    if (whenFilter === "conditional" && c.alwaysOverlaps) return false;
    if (tierFilter === "all") return true;
    return _matchTierFilter(c.a.tier, tierFilter) || _matchTierFilter(c.b.tier, tierFilter);
  });

  $("schedConflictTable").innerHTML = conflicts.length
    ? conflicts.map((c) => `
      <tr>
        <td><span class="tag-pill ${c.severity}">${escapeHtml(c.severity.toUpperCase())}</span></td>
        <td><strong>${escapeHtml(c.scenarioLabel)}</strong></td>
        <td>
          <strong>${escapeHtml(c.a.name)}</strong> ${tierBadge(c.a.tier)}
          <div class="muted mono" style="font-size:11px;">${escapeHtml(c.a.start)} .. ${escapeHtml(c.a.end)} (${escapeHtml(c.a.region)})</div>
        </td>
        <td>
          <strong>${escapeHtml(c.b.name)}</strong> ${tierBadge(c.b.tier)}
          <div class="muted mono" style="font-size:11px;">${escapeHtml(c.b.start)} .. ${escapeHtml(c.b.end)} (${escapeHtml(c.b.region)})</div>
        </td>
        <td>
          <span class="tag-pill ${c.alwaysOverlaps ? "err" : "warn"}">${c.weekdayHits ?? 7}/7 ${c.alwaysOverlaps ? "ALWAYS" : "COND"}</span>
          <div style="margin-top:4px;">${_dowMatrixHtml(c.weekdayMatrix)}</div>
        </td>
        <td style="font-size:11px;">${escapeHtml((c.triggerWeekdays || []).join(", ") || "All 7")}</td>
        <td class="mono">${c.minOverlapDays ?? c.overlapDays}..${c.maxOverlapDays ?? c.overlapDays}d ${c.hasLanOverlap ? `<span class="tag-pill err">${c.lanOverlapDays}d LAN</span>` : `<span class="muted">Online/Split</span>`}</td>
        <td class="mono">${c.exactSlotCollisions}</td>
        <td style="display:flex;gap:4px;flex-wrap:wrap;">
          <button class="btn sm" onclick="openVisualizerModal(${c.a.template})">Viz A</button>
          <button class="btn sm" onclick="openVisualizerModal(${c.b.template})">Viz B</button>
          <button class="btn sm" onclick="openSlotFinderModal(${c.a.template})">Move A</button>
          <button class="btn sm" onclick="openSlotFinderModal(${c.b.template})">Move B</button>
        </td>
      </tr>
    `).join("")
    : `<tr><td colspan="9" class="ok" style="text-align:center;padding:18px;">Zero overlapping tournaments for selected filter!</td></tr>`;

  // 6-month Gantt Timeline (Jan 1 .. Jun 30 = 181 days)
  const gStart = new Date("2026-01-01T00:00:00Z").getTime();
  const gEnd = new Date("2026-07-05T00:00:00Z").getTime();
  const gSpan = gEnd - gStart;
  const filteredEvs = (sc.eventsSpring || []).filter((e) => _matchTierFilter(e.tier, tierFilter));

  $("schedGantt").innerHTML = `
    <div class="gantt-header">
      <div>Tournament (Rep / Tier)</div>
      <div>Jan</div><div>Feb</div><div>Mar</div><div>Apr</div><div>May</div><div>Jun</div>
    </div>
    ${filteredEvs.map((e) => {
      const sMs = Math.max(gStart, new Date(e.startDate + "T00:00:00Z").getTime());
      const eMs = Math.min(gEnd, new Date(e.endDate + "T23:59:59Z").getTime());
      const leftPct = ((sMs - gStart) / gSpan) * 100;
      const widthPct = Math.max(1.8, ((eMs - sMs) / gSpan) * 100);
      return `
        <div class="gantt-row">
          <div class="gantt-lbl" title="${escapeHtml(e.name)} (${e.effectiveRegionName})">
            <span style="overflow:hidden;text-overflow:ellipsis;">${escapeHtml(e.name)}</span>
            <span class="tag-pill ${e.conflictCount > 0 ? "err" : "ok"}" style="font-size:10px;">${e.tier.subCode}${e.conflictCount ? " · " + e.conflictCount + "x" : ""}</span>
          </div>
          <div class="gantt-track">
            <div class="gantt-bar ${e.conflictCount > 0 ? "conflict" : ""}" style="left:${leftPct.toFixed(2)}%;width:${widthPct.toFixed(2)}%;background:${e.tier.color};"
              title="${escapeHtml(e.name)}: ${e.startDate} .. ${e.endDate} (${e.durationDays}d) | ${e.conflictCount} overlaps"
              onclick="openSlotFinderModal(${e.template})">${e.hasLan ? "LAN " : ""}${e.startMonthRange}/${e.startDayRange}</div>
          </div>
        </div>
      `;
    }).join("")}
  `;

  // Tier-by-Tier Breakdown Cards
  $("schedTierCards").innerHTML = (sc.tierBuckets || []).map((b) => `
    <div class="subcard">
      <div class="card-head" style="margin-bottom:6px;">
        <strong>${escapeHtml(b.title)}</strong>
        <div style="display:flex;gap:6px;">
          <span class="tag-pill info">${b.tournamentCount} events (${b.lanCount} LAN)</span>
          <span class="tag-pill ${b.withinTierConflicts > 0 ? "err" : "ok"}">${b.withinTierConflicts} same-tier clashes</span>
          <span class="tag-pill ${b.touchingConflicts > 0 ? "warn" : "ok"}">${b.touchingConflicts} total touches</span>
          <span class="tag-pill ok mono">$${Number(b.totalPrizePool).toLocaleString()}</span>
        </div>
      </div>
      <div style="display:flex;flex-wrap:wrap;gap:6px;">
        ${b.tournaments.map((t) => `<button class="btn sm" onclick="openSlotFinderModal(${t.template})">${escapeHtml(t.name)} <span class="muted">(${t.startDate.slice(5)}..${t.endDate.slice(5)})</span> ${t.conflictCount ? `<span class="bad">(${t.conflictCount})</span>` : ""}</button>`).join("") || '<span class="muted">None</span>'}
      </div>
    </div>
  `).join("");

  // Stage issues & Safe Parallel Regionals
  $("schedStageIssues").innerHTML = (sc.stageChainIssues || []).length
    ? sc.stageChainIssues.map((it) => `<div class="alert-box ${it.severity}"><strong>${escapeHtml(it.name)} (tpl=${it.template}):</strong> ${escapeHtml(it.message)}</div>`).join("")
    : `<div class="alert-box ok">All tournament stage brackets, group divisors, match days, and advancement spots look valid!</div>`;

  $("schedParallelTable").innerHTML = (sc.parallelRegionals || []).length
    ? sc.parallelRegionals.map((r) => `<tr><td>${escapeHtml(r.tierBand)}</td><td>${escapeHtml(r.aName)} (${escapeHtml(r.aRegion)})</td><td>${escapeHtml(r.bName)} (${escapeHtml(r.bRegion)})</td><td class="mono">${escapeHtml(r.window)}</td></tr>`).join("")
    : `<tr><td colspan="4" class="muted">None detected.</td></tr>`;
}

// ------------------------------------------------------------------
// TAB 7: DB Unbalance Data Science
// ------------------------------------------------------------------

async function loadDbBalanceScience() {
  try {
    state.dsBalance = await apiGet("/api/data-science/balance");
    renderDbBalanceScience();
  } catch (err) {
    toast(err.message, "err");
  }
}

function renderDbBalanceScience() {
  const d = state.dsBalance;
  if (!d) return;
  const par = d.parity || {};
  const corr = d.correlations || {};

  $("dsKpis").innerHTML = [
    { l: "DB Unbalance Score", v: `${d.unbalanceScore}/100`, s: d.verdict, cls: d.unbalanceScore >= 65 ? "bad" : d.unbalanceScore >= 38 ? "warn" : "ok" },
    { l: "Top-10 Gini", v: par.top10Skill?.gini ?? 0, s: `Spread ${par.top10Skill?.min}..${par.top10Skill?.max}` },
    { l: "Top-30 Gini", v: par.top30Skill?.gini ?? 0, s: `Median ${par.top30Skill?.p50}` },
    { l: "All Players Gini", v: par.allPlayersSkill?.gini ?? 0, s: `P10=${par.allPlayersSkill?.p10} P90=${par.allPlayersSkill?.p90}` },
    { l: "Skill <-> Rep r", v: corr.skillVsReputationR ?? 0, s: `Skill <-> Pts r=${corr.skillVsRankingPointsR ?? 0}` },
    { l: "Skill <-> Payroll r", v: corr.skillVsPayrollR ?? 0, s: `Wage Gini=${par.payrolls?.gini ?? 0}` },
  ].map((k) => `<div class="kpi"><div class="kpi-lbl">${k.l}</div><div class="kpi-val ${k.cls || ""}">${escapeHtml(k.v)}</div><div class="kpi-sub">${escapeHtml(k.s)}</div></div>`).join("");

  $("dsAlerts").innerHTML = (d.alerts || []).length
    ? d.alerts.map((a) => `<div class="alert-box ${a.severity}"><strong>${escapeHtml(a.title)}</strong><div>${escapeHtml(a.detail)}</div></div>`).join("")
    : `<div class="alert-box ok">No runaway superteam gaps detected in this database!</div>`;

  $("dsTop16Table").innerHTML = (d.top16Projection || []).map((r, i) => `
    <tr>
      <td class="mono">${i + 1}</td>
      <td><strong style="cursor:pointer;text-decoration:underline dotted;" onclick="switchTab('teams');selectTeam(${r.id})">${escapeHtml(r.name)}</strong></td>
      <td>${escapeHtml(r.regionName)}</td>
      <td class="mono"><strong>${r.avgSkill.toFixed(2)}</strong></td>
      <td class="mono">${r.floorSkill.toFixed(2)}</td>
      <td class="mono">${r.starSkill.toFixed(2)}</td>
      <td class="mono">${r.projMapWinVsTop10}%</td>
      <td class="mono ${r.projBo3WinVsTop10 >= 78 ? "bad" : ""}"><strong>${r.projBo3WinVsTop10}%</strong></td>
      <td class="mono">${r.projTrophySharePct}%</td>
      <td class="mono">${r.projSTierOutOf10} / 10</td>
      <td>${escapeHtml(r.hiringBiasName)}</td>
    </tr>
  `).join("");

  const pRows = [
    ["Top-10 Team Skill", par.top10Skill],
    ["Top-30 Team Skill", par.top30Skill],
    ["All Teams Skill", par.allTeamsSkill],
    ["All Players Skill", par.allPlayersSkill],
    ["Team Payroll ($)", par.payrolls],
  ];
  $("dsGiniTable").innerHTML = pRows.map(([lbl, p]) => p ? `
    <tr><td>${escapeHtml(lbl)}</td><td class="mono"><strong>${p.gini}</strong></td><td class="mono">${Number(p.min).toLocaleString()}</td><td class="mono">${Number(p.p10).toLocaleString()}</td><td class="mono">${Number(p.p50).toLocaleString()}</td><td class="mono">${Number(p.p90).toLocaleString()}</td><td class="mono">${Number(p.max).toLocaleString()}</td></tr>
  ` : "").join("");

  $("dsRegionTable").innerHTML = (d.regionMeta || []).map((r) => `
    <tr><td><strong>${escapeHtml(r.region)}</strong></td><td class="mono">${r.teams}</td><td class="mono">${r.top30Teams}</td><td class="mono">${r.top10AvgSkill}</td><td class="mono">${r.players}</td><td class="mono">${r.elitePlayers}</td><td class="mono">${r.awpers14}</td><td class="mono">${r.igls14}</td><td class="mono">${r.wonderkidsU20}</td></tr>
  `).join("");

  $("dsCorrTag").textContent = `Pearson r(Skill, Rep) = ${corr.skillVsReputationR} | r(Skill, Pts) = ${corr.skillVsRankingPointsR}`;
  $("dsRepOutliersTable").innerHTML = (d.repOutliers || []).map((o) => `
    <tr>
      <td><strong>${escapeHtml(o.team)}</strong></td>
      <td class="mono">${o.avgSkill}</td>
      <td class="mono">#${o.skillRank}</td>
      <td class="mono">#${o.dbRank}</td>
      <td class="mono ${o.rankGap >= 10 ? "ok" : o.rankGap <= -10 ? "bad" : ""}">${o.rankGap > 0 ? "+" : ""}${o.rankGap}</td>
      <td class="mono">${o.reputation}</td>
      <td class="mono">${o.expectedRep}</td>
      <td class="mono ${Math.abs(o.repResid) >= 4 ? "warn" : ""}">${o.repResid > 0 ? "+" : ""}${o.repResid}</td>
    </tr>
  `).join("") || `<tr><td colspan="8" class="muted">No large reputation/rank calibration mismatches.</td></tr>`;

  const maxAge = Math.max(1, ...(d.ageBuckets || []).map((b) => b.count));
  $("dsAgePyramid").innerHTML = (d.ageBuckets || []).map((b) => `
    <div style="margin-bottom:10px;">
      <div style="display:flex;justify-content:space-between;font-size:12px;"><strong>${escapeHtml(b.label)}</strong><span class="mono">${b.count}</span></div>
      <div style="height:10px;background:#0c121d;border-radius:4px;overflow:hidden;margin-top:3px;">
        <div style="height:100%;width:${(b.count / maxAge) * 100}%;background:var(--accent-2);"></div>
      </div>
    </div>
  `).join("");

  $("dsPlayerOutliersTable").innerHTML = (d.topPlayerOutliers || []).map((p) => `
    <tr>
      <td><strong style="cursor:pointer;text-decoration:underline dotted;" onclick="jumpToPlayer(${p.id})">${escapeHtml(p.name)}</strong></td>
      <td>${escapeHtml(p.team)}</td>
      <td class="mono">${p.age}</td>
      <td class="mono"><strong>${p.avgSkill}</strong></td>
      <td class="mono">${p.potential}</td>
      <td class="mono ${p.maxedCount >= 4 ? "warn" : ""}">${p.maxedCount}</td>
      <td class="mono">$${Number(p.salary || 0).toLocaleString()}</td>
    </tr>
  `).join("");
}

// ------------------------------------------------------------------
// TAB 8: GameBalance & Weapons Mod Lab
// ------------------------------------------------------------------

async function loadWeaponsLab() {
  try {
    state.weaponsPack = await apiGet("/api/mod/weapons");
    renderWeaponsLab();
  } catch (err) {
    toast(err.message, "err");
  }
}

function renderWeaponsLab() {
  const wp = state.weaponsPack;
  if (!wp || !wp.loaded) {
    $("wepKpis").innerHTML = `<div class="subcard">No weapons pack loaded.</div>`;
    return;
  }
  const an = wp.analysis || {};
  const rows = an.rows || [];
  $("wepKpis").innerHTML = [
    { l: "Loaded Weapons Pack", v: wp.name, s: `${rows.length} weapons` },
    { l: "Armored DPS Gini", v: an.dpsGini, s: "Damage output spread" },
    { l: "Value/$1k Gini", v: an.valueGini, s: "Economic efficiency spread" },
    { l: "Outlier Flags", v: (an.alerts || []).length, s: "|Z-Score| >= 1.25 in type", cls: (an.alerts || []).length > 3 ? "warn" : "ok" },
  ].map((k) => `<div class="kpi"><div class="kpi-lbl">${k.l}</div><div class="kpi-val ${k.cls || ""}">${escapeHtml(k.v)}</div><div class="kpi-sub">${escapeHtml(k.s)}</div></div>`).join("");

  $("wepAlerts").innerHTML = (an.alerts || []).map((a) => `<div class="alert-box ${a.severity}"><strong>${escapeHtml(a.weapon)} (${escapeHtml(a.typeName)}):</strong> ${escapeHtml(a.detail)}</div>`).join("");

  $("wepSideTable").innerHTML = (an.sideSummary || []).map((s) => `
    <tr><td><strong>${escapeHtml(s.label)}</strong></td><td class="mono">${s.count}</td><td class="mono">$${Number(s.avgPrice).toLocaleString()}</td><td class="mono">${s.avgArmoredDps}</td><td class="mono">${s.avgTtkMs} ms</td><td class="mono">${s.avgAccuracy}</td></tr>
  `).join("");

  $("wepSciTable").innerHTML = rows.map((r) => `
    <tr>
      <td><strong style="cursor:pointer;text-decoration:underline dotted;" onclick="selectWeapon(${r.id})">${escapeHtml(r.customName)}</strong></td>
      <td>${escapeHtml(r.typeName)}</td>
      <td>${escapeHtml(r.availabilityName)}</td>
      <td class="mono">$${r.price}</td>
      <td class="mono">${r.damage}</td>
      <td class="mono">${r.armorMultiplier}</td>
      <td class="mono">${r.rpm}</td>
      <td class="mono"><strong>${r.armoredDps}</strong></td>
      <td class="mono">${r.stkArmor}</td>
      <td class="mono">${r.ttkArmorMs}</td>
      <td class="mono">${r.intendedHsArmorDmg}</td>
      <td class="mono warn">${r.engineArmoredHsDmg}</td>
      <td class="mono">${r.valueIndex}</td>
      <td class="mono ${Math.abs(r.typeZScore) >= 1.2 ? "warn" : ""}">${r.typeZScore > 0 ? "+" : ""}${r.typeZScore}</td>
      <td>${(r.flags || []).map((f) => `<span class="tag-pill ${f.includes("OP") ? "err" : "warn"}">${escapeHtml(f)}</span>`).join(" ")}</td>
    </tr>
  `).join("");

  $("weaponList").innerHTML = (wp.weapons || []).map((w) => `
    <div class="list-row ${Number(w.id) === Number(state.selectedWeaponId) ? "selected" : ""}" onclick="selectWeapon(${w.id})">
      <div><strong>${escapeHtml(w.customName)}</strong> <span class="muted">(${escapeHtml(state.meta.weaponTypes[w.type] || "")})</span></div>
      <div class="mono">$${w.price} · Dmg ${w.damage}</div>
    </div>
  `).join("");
}

function selectWeapon(id) {
  state.selectedWeaponId = id;
  document.querySelectorAll('[data-msub]').forEach((b) => {
    if (b.dataset.msub === "weapons-edit") b.click();
  });
  const w = (state.weaponsPack?.weapons || []).find((x) => Number(x.id) === Number(id));
  if (!w) return;
  renderWeaponsLab();
  $("weaponEditorCard").innerHTML = `
    <div class="card-head">
      <div style="display:flex;align-items:center;gap:10px;">
        ${logoImgHtml("weapon_icon", w.iconName || "", "logo-thumb logo-thumb-lg", "edWepIconPrev")}
        <span class="card-title">${escapeHtml(w.customName)} (#${w.id})</span>
      </div>
      <button class="btn ok sm" onclick="saveSelectedWeapon(${w.id})">Update Weapon</button>
    </div>
    <div class="form-grid">
      <div class="field"><label>Name</label><input id="edWepName" value="${escapeHtml(w.customName)}" /></div>
      <div class="field"><label>Icon Key</label>
        <div class="logo-field-wrap">
          <input id="edWepIcon" value="${escapeHtml(w.iconName || "")}" oninput="updateLogoPreview('weapon_icon', this.value, 'edWepIconPrev')" />
          <button type="button" class="btn sm" onclick="openLogoPickerModal('weapon_icon', 'edWepIcon', 'edWepIconPrev')">Pick/Import</button>
        </div>
      </div>
      <div class="field"><label>Type</label><select id="edWepType">${optionsHtml(state.meta.weaponTypes, w.type)}</select></div>
      <div class="field"><label>Side</label><select id="edWepAvail">${optionsHtml(state.meta.weaponAvailability, w.availability)}</select></div>
      <div class="field"><label>Tier (1-6)</label><input id="edWepTier" type="number" min="1" max="6" value="${w.tier}" /></div>
      <div class="field"><label>Price ($)</label><input id="edWepPrice" type="number" step="50" value="${w.price}" /></div>
      <div class="field"><label>Base Damage</label><input id="edWepDmg" type="number" value="${w.damage}" /></div>
      <div class="field"><label>Armor Penetration (0..1)</label><input id="edWepArm" type="number" step="0.01" value="${w.armorMultiplier}" /></div>
      <div class="field"><label>HS Multiplier</label><input id="edWepHs" type="number" step="0.1" value="${w.hsMultiplier}" /></div>
      <div class="field"><label>Shot Interval (sec)</label><input id="edWepInt" type="number" step="0.005" value="${w.shotInterval}" /></div>
      <div class="field"><label>Accuracy</label><input id="edWepAcc" type="number" step="0.5" value="${w.accuracy}" /></div>
      <div class="field"><label>Ammo</label><input id="edWepAmmo" type="number" value="${w.ammo}" /></div>
      <div class="field"><label>Kill Reward ($)</label><input id="edWepKill" type="number" step="50" value="${w.killReward}" /></div>
    </div>
    <div style="margin-top:8px;">
      <button type="button" class="btn sm" onclick="openLogoPickerModal('weapon_skin', 'edWepSkinHelper', null, (s) => toast('Skin asset selected: ' + s))">Browse / Import Custom Weapon Skins</button>
      <input type="hidden" id="edWepSkinHelper" value="" />
    </div>
  `;
}

async function saveSelectedWeapon(id) {
  try {
    state.weaponsPack = await apiPost("/api/mod/weapons/update", {
      id,
      patch: {
        customName: $("edWepName").value,
        iconName: $("edWepIcon").value,
        type: Number($("edWepType").value),
        availability: Number($("edWepAvail").value),
        tier: Number($("edWepTier").value),
        price: Number($("edWepPrice").value),
        damage: Number($("edWepDmg").value),
        armorMultiplier: Number($("edWepArm").value),
        hsMultiplier: Number($("edWepHs").value),
        shotInterval: Number($("edWepInt").value),
        accuracy: Number($("edWepAcc").value),
        ammo: Number($("edWepAmmo").value),
        killReward: Number($("edWepKill").value),
      },
    });
    toast("Weapon updated (remember to Save weapons.json).");
    renderWeaponsLab();
    selectWeapon(id);
    state.summary = await apiGet("/api/summary");
    updateTopbar();
  } catch (err) {
    toast(err.message, "err");
  }
}

async function loadBalanceLab() {
  try {
    state.balancePack = await apiGet("/api/mod/balance");
    renderBalanceLab();
  } catch (err) {
    toast(err.message, "err");
  }
}

function renderBalanceLab() {
  const bp = state.balancePack;
  if (!bp || !bp.loaded) {
    $("balKpis").innerHTML = `<div class="subcard">No GameBalance pack loaded.</div>`;
    return;
  }
  const an = bp.analysis || {};
  const d = bp.data || {};
  const groups = bp.sortedGroups || [{ id: "all", title: `All Parameters (${Object.keys(d).length})`, keys: Object.keys(d) }];
  const dev = an.devBaseline || {};
  const dbEcon = an.dbEcon || {};
  const fmtDiff = (v) => {
    const n = Number(v || 0);
    return n === 0 ? "Matches dev test.json" : `${n > 0 ? "+" : ""}${n}% vs dev test.json`;
  };
  const facSum = Number(an.allFacilitySum ?? ((an.practiceSum || 0) + (an.academySum || 0) + (an.brandingSum || 0)));
  const t20Mo = Number((an.ownerTier20 || 0) + (an.merchTier20 || 0));

  $("balKpis").innerHTML = [
    { l: "Loaded Balance Pack", v: bp.name, s: "gameBalance.json" },
    { l: "Regen Pool Total", v: an.totalRegens, s: `${an.regenPcts?.great}% Great · ${fmtDiff(dev.regenDiffPct)}` },
    { l: "Maxed Facility Totals", v: `$${facSum.toLocaleString()}`, s: `Practice+Acad+Brand · ${fmtDiff(dev.facilityDiffPct)}` },
    { l: "Tier-20 Monthly Income", v: `$${t20Mo.toLocaleString()}`, s: `Owner $${Number(an.ownerTier20 || 0).toLocaleString()} + Merch $${Number(an.merchTier20 || 0).toLocaleString()} · ${fmtDiff(dev.tier20DiffPct)}` },
    { l: "DB Top-10 Avg Payroll", v: dbEcon.top10AvgPayroll ? `$${Number(dbEcon.top10AvgPayroll).toLocaleString()}/yr` : "Load a DB", s: dbEcon.top10AvgPayroll ? `T20 Income covers ${dbEcon.t20PayrollCoveragePct}% of payroll` : "Compares org payroll vs T20" },
    { l: "DB Orgs in Base Deficit", v: dbEcon.totalOrgsChecked ? `${dbEcon.deficitOrgsCount} / ${dbEcon.totalOrgsChecked}` : "-", s: "Payroll > Owner+Merch annual income" },
  ].map((k) => `<div class="kpi"><div class="kpi-lbl">${k.l}</div><div class="kpi-val">${escapeHtml(k.v)}</div><div class="kpi-sub">${escapeHtml(k.s)}</div></div>`).join("");

  $("balAlerts").innerHTML = (an.alerts || []).map((a) => `<div class="alert-box warn">${escapeHtml(a)}</div>`).join("") || `<div class="alert-box ok">Regen &amp; economy scaling curves look smooth.</div>`;

  const totalKeys = Object.keys(d).length;
  const groupsHtml = groups.map((g) => `
    <div style="margin-bottom:14px;">
      <div style="font-size:12px;font-weight:700;color:var(--accent);text-transform:uppercase;letter-spacing:.4px;margin-bottom:6px;border-bottom:1px solid var(--border);padding-bottom:4px;">${escapeHtml(g.title)} (${g.keys.length})</div>
      <div class="form-grid">
        ${(g.keys || []).map((k) => `<div class="field"><label>${escapeHtml(k)}</label><input class="bal-input" data-bkey="${escapeHtml(k)}" type="number" value="${d[k]}" /></div>`).join("")}
      </div>
    </div>
  `).join("");

  $("balEditorBody").innerHTML = `
    <div class="subcard" style="margin-top:8px;margin-bottom:10px;">
      <div class="card-head" style="margin-bottom:6px;">
        <span class="subcard-title" style="margin:0;">Dev <code>test/gameBalance.json</code> Baseline &amp; Category Batch Scaler</span>
        <span class="hint">Scale full curves cleanly or reset to Crumana's baseline (${dev.devTotalRegens || 320} regens, $${Number(dev.devFacilityTotal || 771000).toLocaleString()} facilities, $${Number(dev.devTier20Monthly || 525000).toLocaleString()}/mo T20)</span>
      </div>
      <div class="row" style="gap:6px;flex-wrap:wrap;">
        <button class="btn sm" onclick="batchScaleBalance('owner', 15)">Owner +15%</button>
        <button class="btn sm" onclick="batchScaleBalance('owner', -15)">Owner -15%</button>
        <button class="btn sm" onclick="batchScaleBalance('merch', 20)">Merch +20%</button>
        <button class="btn sm" onclick="batchScaleBalance('merch', -20)">Merch -20%</button>
        <button class="btn sm" onclick="batchScaleBalance('facilities', 25)">Facilities +25%</button>
        <button class="btn sm" onclick="batchScaleBalance('facilities', -25)">Facilities -25%</button>
        <button class="btn sm" onclick="batchScaleBalance('regens', 25)">Regens +25%</button>
        <button class="btn warn sm" onclick="batchScaleBalance('reset_dev', 0)">Reset to Dev test.json</button>
      </div>
    </div>
    <div class="split-equal" style="margin-top:8px;">
      <div class="subcard">
        <div class="card-head">
          <span class="subcard-title" style="margin:0;">Sorted Parameters (${totalKeys} across ${groups.length} groups)</span>
          <button class="btn ok sm" onclick="applyAllBalanceInputs()">Apply Edits</button>
        </div>
        <div style="max-height:460px;overflow-y:auto;padding-right:4px;">
          ${groupsHtml}
        </div>
      </div>
      <div class="subcard">
        <div class="subcard-title">Owner &amp; Merch Tier 1..20 Curve vs Branding ROI</div>
        <div class="table-wrap" style="max-height:460px;">
          <table>
            <thead><tr><th>Tier</th><th>Owner/mo</th><th>Merch/mo</th><th>Merch%</th><th>Combined/yr</th><th>Jump%</th><th>Brand Payback</th></tr></thead>
            <tbody>
              ${(an.tierCurve || []).map((t) => `
                <tr><td class="mono">${t.tier}</td><td class="mono">$${t.owner.toLocaleString()}</td><td class="mono">$${t.merch.toLocaleString()}</td><td class="mono">${t.merchSharePct ?? "-"}%</td><td class="mono">$${t.annualCombined.toLocaleString()}</td><td class="mono ${t.ownerJumpPct >= 50 ? "warn" : ""}">+${t.ownerJumpPct}%</td><td class="mono">${t.estPaybackMonths ?? "-"} mo</td></tr>
              `).join("")}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  `;
}

async function batchScaleBalance(category, pct) {
  try {
    state.balancePack = await apiPost("/api/mod/balance/scale", { category, pct });
    renderBalanceLab();
    toast(category === "reset_dev" ? "Reset GameBalance values to dev test.json baseline (click Save to write disk)." : `Scaled '${category}' by ${pct > 0 ? "+" : ""}${pct}% (unsaved).`);
    state.summary = await apiGet("/api/summary");
    updateTopbar();
  } catch (err) {
    toast(err.message, "err");
  }
}

async function applyAllBalanceInputs() {
  try {
    const patch = {};
    document.querySelectorAll(".bal-input").forEach((inp) => {
      patch[inp.dataset.bkey] = Number(inp.value);
    });
    state.balancePack = await apiPost("/api/mod/balance/update", { patch });
    toast("GameBalance updated in memory (click Save gameBalance.json to persist).");
    renderBalanceLab();
    state.summary = await apiGet("/api/summary");
    updateTopbar();
  } catch (err) {
    toast(err.message, "err");
  }
}

// ------------------------------------------------------------------
// TAB 9: Legend, Meta Circuit & Hardware Load Guide
// ------------------------------------------------------------------

async function renderLegendTab() {
  if (!state.schedule && state.summary?.loaded) {
    try { state.schedule = await apiGet("/api/tournaments/schedule"); } catch {}
  }
  const rows = state.meta?.awardBreakdownByRep || [];
  const ch = state.schedule?.circuitAndHardware || null;
  const strayList = ch?.strayEvpEvents || [];

  $("legendBody").innerHTML = `
    <div class="subtabs">
      <button class="subtab-btn active" data-lgsub="awards">Awards &amp; Tier Matrix (Rep 1..20)</button>
      <button class="subtab-btn" data-lgsub="circuit">Meta Circuit System (Prevent Stray EVPs)</button>
      <button class="subtab-btn" data-lgsub="ai">AI Selection &amp; Invites (Decompiled)</button>
      <button class="subtab-btn" data-lgsub="hardware">Tournament Count vs Hardware Ratio</button>
      <button class="subtab-btn" data-lgsub="mechanics">Engine Mechanics &amp; Formulas</button>
    </div>

    <!-- SUBTAB 1: AWARDS MATRIX -->
    <div id="lgsub-awards" class="subpanel active">
      <div class="card">
        <div class="card-head">
          <span class="card-title">Tournament Reputation 1..20 — Tier, Stars &amp; Exact Engine Awards (MVP / EVP / HM)</span>
          <span class="muted">Exact logic from CS Manager <code>Tournament.GetTier</code>, <code>GetReputationStars</code> &amp; <code>GetNumberOfAwards</code></span>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Rep</th><th>Engine Tier</th><th>Sub-Tier Band</th><th>Stars</th>
                <th>MVP</th><th>EVP</th><th>Honorable Mentions (HM)</th><th>Circuit Role</th>
              </tr>
            </thead>
            <tbody>
              ${rows.map((r) => `
                <tr style="${r.reputation >= 8 && r.reputation <= 12 ? "background:rgba(245,158,11,0.06);" : ""}">
                  <td class="mono"><strong>${r.reputation}</strong></td>
                  <td><span class="tag-pill ${r.engineTier >= 5 ? "major" : (r.engineTier === 4 ? "s-tier" : (r.engineTier === 3 ? "a-tier" : (r.engineTier === 2 ? "b-tier" : "c-tier")))}">T${r.engineTier} ${escapeHtml(r.tierLabel)}</span></td>
                  <td>${escapeHtml(r.subBand)}</td>
                  <td class="mono">${r.stars}★</td>
                  <td>${r.mvp ? `<span class="award-pill award-mvp">${r.mvp} MVP</span>` : `<span class="muted">0</span>`}</td>
                  <td>${r.evp ? `<span class="award-pill award-evp">${r.evp} EVP</span>` : `<span class="muted">0</span>`}</td>
                  <td>${r.honorableMentions ? `<span class="award-pill award-hm">${r.honorableMentions} HM</span>` : `<span class="muted">0</span>`}</td>
                  <td class="muted" style="font-size:11.5px;">${r.reputation >= 19 ? "Valve Major / Flagships (Major = Sticker Money Eligible)" : (r.reputation >= 13 ? "Safe S-Tier Event (1 MVP + 3-5 EVPs)" : (r.reputation >= 8 ? "<strong class='warn'>STRAY-EVP ZONE:</strong> Awards EVPs without MVP — avoid for T2/T3 events!" : "Safe T2/T3/Regional Event (0 MVP, 0 EVP, 5 HM only)"))}</td>
                </tr>
              `).join("")}
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- SUBTAB 2: META TOURNAMENT CIRCUIT SYSTEM -->
    <div id="lgsub-circuit" class="subpanel">
      <div class="card">
        <div class="card-head">
          <span class="card-title">Meta Tournament Circuit Design — Why Pros Skip Rep 8..12</span>
          ${ch ? `<span class="tag-pill ${ch.strayEvpZoneCount === 0 ? "ok" : "warn"}">${ch.strayEvpZoneCount === 0 ? "Clean Circuit (0 Stray-EVP Events)" : ch.strayEvpZoneCount + " Events in Stray-EVP Zone"}</span>` : ""}
        </div>
        <div class="alert-box warn">
          <strong>Why Rep 8..12 Ruins Career Award Profiles:</strong> In CS Manager's award formula, <strong>Rep 13-20</strong> triggers full <strong>1 MVP + 3-7 EVPs</strong>, while <strong>Rep 8-12</strong> still hands out <strong>1 to 3 EVPs</strong> even though Tier-1 elite teams usually skip them! If you rate a T2/T3 regional LAN or CCT cup at Rep 8-12, Tier-3 players farm <strong>stray EVPs</strong> on their Hall-of-Fame profile alongside real S-Tier stars.
        </div>
        <div class="legend-grid" style="margin-top:10px;">
          <div class="subcard">
            <div class="subcard-title">Recommended Meta Rep Separation</div>
            <ul style="margin:0;padding-left:18px;line-height:1.65;font-size:12.5px;">
              <li><strong>Rep 20 — Valve Major + Katowice/Cologne Flagships:</strong> Major gets <code>stickerMoneyLow/High</code> + Stage 2-4 <code>stickerMoneyPercentages</code> (~100% sum); Katowice/Cologne get Rep 20, <code>0</code> sticker money. (1 MVP, 7 EVPs)</li>
              <li><strong>Rep 16–18 — Tier-1 Circuit (EPL, BLAST Open/Rival, PGL, StarLadder):</strong> Invited Tier-1 LANs. (1 MVP, 4–5 EVPs)</li>
              <li><strong>Rep 13–15 — Entry S-Tier (optional big international studio LANs):</strong> (1 MVP, 3–4 EVPs)</li>
              <li><strong>Rep 8–12 — SKIP / KEEP EMPTY FOR T2/T3:</strong> The Stray-EVP Trap! Only put an event here if you genuinely want sub-S-tier LANs to give official EVPs.</li>
              <li><strong>Rep 5–7 — Top Tier-2 / Tier-3 Events (CCT, DraculaN, FiReLEAGUE, DreamHack Knockout, Thunderpick):</strong> Capped at <strong>Rep 7 max</strong> -> <code>0 MVP, 0 EVP, 5 Honorable Mentions</code>!</li>
              <li><strong>Rep 1–4 — Grassroots / Regional Cups:</strong> Open local feeder circuit (<code>0 MVP, 0 EVP, 5 HM</code>).</li>
            </ul>
          </div>
          <div class="subcard">
            <div class="subcard-title">Live Current DB Circuit Audit (${escapeHtml(state.summary?.dbName || "None")})</div>
            ${ch ? `
              <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px;">
                <span class="tag-pill info">S-Tier/Major (13-20): ${ch.sTierCount}</span>
                <span class="tag-pill ${ch.strayEvpZoneCount ? "err" : "ok"}">Stray-EVP Zone (8-12): ${ch.strayEvpZoneCount}</span>
                <span class="tag-pill ok">Safe Low-Tier (1-7): ${ch.safeLowTierCount}</span>
              </div>
              ${strayList.length ? `
                <p class="muted" style="margin:0 0 6px;">These active tournaments currently sit in <strong>Rep 8..12</strong> and will award stray EVPs (click Edit to cap at Rep 7 or promote to Rep 13+):</p>
                <div class="table-wrap" style="max-height:220px;">
                  <table>
                    <thead><tr><th>Name</th><th>Rep</th><th>Awards/Run</th><th>Action</th></tr></thead>
                    <tbody>
                      ${strayList.map((e) => `<tr><td>${escapeHtml(e.name)}</td><td class="mono">${e.reputation}</td><td class="mono">${e.evp} EVP / ${e.hm} HM</td><td><button class="btn sm" onclick="jumpToTournament(${e.template})">Edit</button></td></tr>`).join("")}
                    </tbody>
                  </table>
                </div>
              ` : `<div class="alert-box ok">Zero active tournaments sit in the Rep 8-12 Stray-EVP Zone! Your database follows the clean T1 / T2+T3 separation.</div>`}
            ` : `<div class="muted">Load a database to inspect circuit separation.</div>`}
          </div>
        </div>
      </div>
    </div>

    <!-- SUBTAB 3: AI TOURNAMENT SELECTION & INVITES (DECOMPILED FROM ASSEMBLY-CSHARP) -->
    <div id="lgsub-ai" class="subpanel">
      <div class="card">
        <div class="card-head">
          <span class="card-title">How AI Teams Choose Tournaments (Decompiled from <code>Assembly-CSharp.dll</code>)</span>
          <span class="tag-pill info">Verified IL Mechanics</span>
        </div>
        <div class="alert-box warn">
          <strong>Key Takeaways for Database Authors:</strong>
          (1) AI teams <strong>NEVER skip a tournament for rest or fatigue</strong> — there is zero player-fatigue or stamina check in <code>InviteTeamsToTournament</code>.
          (2) If two MVP-level or high-tier LAN tournaments collide, Tier-1 teams <strong>pick ONE and completely ignore the 2nd</strong> because of hard LAN-overlap + higher-rep reservation guards.
        </div>
        <div class="legend-grid" style="margin-top:10px;">
          <div class="subcard">
            <div class="subcard-title">1. Daily Invite Queue &amp; Tie-Breaking</div>
            <ul style="margin:0;padding-left:18px;line-height:1.65;font-size:12.5px;">
              <li><strong>Stage Priority (<code>UpdateTournamentInvites</code>):</strong> Every day, open stages whose <code>invitationDate == today</code> are sorted <strong>descending by parent <code>reputation</code></strong>. Highest-prestige events always draft teams first.</li>
              <li><strong>Team Priority:</strong> All eligible teams are sorted <strong>descending by Ranking Points (#1 downward)</strong> and processed sequentially until open spots hit <code>0</code>.</li>
              <li><strong>Tied-Reputation Collision:</strong> When two Rep-17 or Rep-20 events overlap LAN dates, whichever invites first (or sorts earlier) signs #1..#16; the 2nd event then hits <code>HasOverlappingLanDates == true</code> and gets <strong>0 Tier-1 teams</strong>.</li>
              <li><strong>Template 1–3 League Exclusivity:</strong> Templates <code>&lt;= 3</code> (e.g. <code>1: EPL</code>, <code>2: ECL</code>, <code>3: ESEA</code>) are mutually exclusive — any team entered in one <code>template &lt;= 3</code> league automatically skips all others.</li>
            </ul>
          </div>
          <div class="subcard">
            <div class="subcard-title">2. Overlap Lockouts (Why Colliding Events Get Ignored)</div>
            <ul style="margin:0;padding-left:18px;line-height:1.65;font-size:12.5px;">
              <li><strong>Already Entered LAN Lock:</strong> Any team already in an unfinished LAN event whose LAN window overlaps (<code>HasOverlappingLanDates</code>) is skipped immediately.</li>
              <li><strong>Expecting Better Invite (<code>IsExpectingAnInviteToTournament</code>):</strong> Even BEFORE the bigger event invites, if another overlapping tournament has <strong>strictly higher reputation</strong> and <code>teamWorldRank &lt;= totalSpots(higherEvent)</code>, AI declines the lower event to hold its calendar open.</li>
              <li><strong>Top-40 &amp; LAN-Spot Cutoff:</strong> When overlapping higher-rep tournaments exist, the engine sums concurrent regional spots (<code>maxOverlapSpots</code>) and LAN spots (<code>maxOverlapLanSpots</code>). Any team with <code>(worldRank &lt;= 40 &amp;&amp; maxOverlapSpots &gt; worldRank)</code> or <code>(worldRank &lt;= maxOverlapLanSpots)</code> is <strong>hard-skipped</strong>.</li>
              <li><strong>No Rest Day Check:</strong> Back-to-back tournaments with even a 1-day gap between LAN end and next start are accepted greedily by Tier-1 AI teams.</li>
            </ul>
          </div>
        </div>
        <div class="subcard" style="margin-top:10px;">
          <div class="subcard-title">3. Exact Acceptance Probability Formula (When Unblocked)</div>
          <ul style="margin:0;padding-left:18px;line-height:1.65;font-size:12.5px;">
            <li><strong>Rep &gt;= 16 Auto-Accept:</strong> If not blocked by any overlap guard, AI teams <strong>100% accept</strong> every tournament with <code>reputation &gt;= 16</code> regardless of club prestige.</li>
            <li><strong>Base Score (<code>Rep &lt; 16</code>):</strong> <code>acceptScore = 0.8 + (tournament.reputation - team.reputation) / 10.0</code>. If <code>tournRep &lt;= teamRep - 8</code>, <code>acceptScore &lt;= 0</code> (<strong>0% chance</strong> — Tier-1 teams Rep 18–20 skip Rep &lt;= 10 cups automatically!).</li>
            <li><strong>Decline Weight Penalties:</strong> When <code>0 &lt; acceptScore &lt; 0.3</code>, non-LAN events add <code>declineWeight = 2.0</code> (online qualifier stages add <code>1.0</code>). Any non-blocking higher-rep overlap adds up to <code>10 * (worldRank / teamCount)</code> penalty. Final roll: <code>Random(0, acceptScore + declineWeight) &lt;= acceptScore</code>.</li>
            <li><strong>Bottom-of-Pool Fill Override:</strong> Near the bottom of the ranked team list, once remaining eligible teams shrink to <code>&lt;= openSpots + 2</code>, AI forces acceptance so brackets always fill cleanly.</li>
          </ul>
        </div>
      </div>
    </div>

    <!-- SUBTAB 4: TOURNAMENT COUNT VS HARDWARE RATIO -->
    <div id="lgsub-hardware" class="subpanel">
      <div class="card">
        <div class="card-head">
          <span class="card-title">Tournament Count per Hardware Ratio — Don't Overcook Your Sim</span>
          ${ch ? `<span class="tag-pill ${ch.hardwareBadge}">${escapeHtml(ch.hardwareTier)}</span>` : ""}
        </div>
        ${ch ? `
          <div class="kpi-grid">
            <div class="kpi"><div class="kpi-lbl">Active Templates</div><div class="kpi-val">${ch.activeTemplates}</div><div class="kpi-sub">${ch.yearlyEventRuns} event runs / yr (x2 loop)</div></div>
            <div class="kpi"><div class="kpi-lbl">Active Stages</div><div class="kpi-val">${ch.activeStages}</div><div class="kpi-sub">${ch.yearlyStageRuns} stage runs / yr</div></div>
            <div class="kpi"><div class="kpi-lbl">Est. Matches / Yr</div><div class="kpi-val">${ch.estMatchesPerYear.toLocaleString()}</div><div class="kpi-sub">All formats combined</div></div>
            <div class="kpi"><div class="kpi-lbl">Est. Maps Simmed / Yr</div><div class="kpi-val ${ch.hardwareBadge}">${ch.estMapsPerYear.toLocaleString()}</div><div class="kpi-sub">Max stage size: ${ch.maxStageParticipants} teams</div></div>
          </div>
        ` : ""}
        <p class="muted">Because CS Manager runs every active tournament twice per year (Spring M1-M6 &amp; Fall M7-M12) and tracks every map, player rating, demo stat history, and calendar tick in JSON saves, excessive Round-Robin groups or 70+ tournaments cause multi-second Sunday/monthly freezes.</p>
        <div class="table-wrap">
          <table>
            <thead>
              <tr><th>Hardware Profile</th><th>Active Templates</th><th>Event Runs / Yr</th><th>Est. Maps / Yr</th><th>Bracket Rule of Thumb</th><th>Multi-Season Feel (Yr 5+)</th></tr>
            </thead>
            <tbody>
              <tr>
                <td><span class="tag-pill ok">Lightweight</span> Laptop / Steam Deck / Budget CPU</td>
                <td class="mono">15 – 25</td><td class="mono">30 – 50</td><td class="mono">&lt; 4,500</td>
                <td>Prefer Single Elim / Swiss over huge Round Robins</td><td>Instant weekly ticks; tiny save files</td>
              </tr>
              <tr>
                <td><span class="tag-pill ok">Balanced Standard</span> Mid-Range Desktop (Sweet Spot)</td>
                <td class="mono">26 – 45 (Base ~41)</td><td class="mono">52 – 90</td><td class="mono">4,500 – 8,500</td>
                <td>~10 T1 + ~30 Regional/T2/T3 events (8–16t stages)</td><td>Snappy sim with rich T1+T2+T3 ecosystem</td>
              </tr>
              <tr>
                <td><span class="tag-pill warn">Heavy Load</span> Fast Gaming Desktop (8+ Cores)</td>
                <td class="mono">46 – 62</td><td class="mono">92 – 124</td><td class="mono">8,500 – 12,000</td>
                <td>Avoid multiple 24–32t Round Robin leagues on same weekend</td><td>Noticeable Sunday/end-of-month pauses by Yr 4+</td>
              </tr>
              <tr>
                <td><span class="tag-pill bad">Overcooked</span> Danger Zone</td>
                <td class="mono">63+ templates</td><td class="mono">126+ runs</td><td class="mono">&gt; 12,000</td>
                <td>Calendar congestion, huge save bloat, UI stutters</td><td>Long sim hangs, save/load slowdowns, transfer lag</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- SUBTAB 4: ENGINE MECHANICS & FORMULAS -->
    <div id="lgsub-mechanics" class="subpanel">
      <div class="legend-grid">
        <div class="card">
          <div class="card-head"><span class="card-title">Custom Potentials, Sticker Money &amp; Dates</span></div>
          <ul style="margin:0;padding-left:18px;line-height:1.65;font-size:12.5px;">
            <li><strong>Custom Potential (<code>useStartingPotential</code> + <code>startingPotential</code> 50–275):</strong> Overrides dynamic per-skill roll at career start so young prospects cleanly peak near their target sum (<code>~255-275</code> = generational GOAT, <code>210-235</code> = T1 star, <code>150-185</code> = T2/Academy).</li>
            <li><strong>Sticker Money (Major Only):</strong> Only Majors (<code>Rep 19-20</code>) should have <code>stickerMoneyLow/High</code> &gt; 0 and non-zero <code>stickerMoneyPercentages</code> across their stages (Stage 2+3+Playoffs sum to <strong>100%</strong>).</li>
            <li><strong>6-Month Loop &amp; 7-Weekday Drift:</strong> Every template runs twice/year; stages advance only on <code>daysOfWeekPlayed</code>, so all 7 starting weekdays (<code>Mon..Sun</code>) are tested in the Overlap Audit.</li>
            <li><strong>Advancement:</strong> Stage Prizes with <code>Progress Type = 1 (Advance)</code> feed winners into the next Stage #.</li>
          </ul>
        </div>
        <div class="card">
          <div class="card-head"><span class="card-title">Match Odds (<code>skill^2.8</code>) &amp; Weapons Damage</span></div>
          <ul style="margin:0;padding-left:18px;line-height:1.65;font-size:12.5px;">
            <li><strong>Superteam Math:</strong> Team power compounds around <code>skill^2.8</code>; +1.5 avg skill gap creates ~65-80% trophy monopolies.</li>
            <li><strong>Armored Hit (<code>Weapon::CalculateDamage</code>):</strong> <code>damage * armorMultiplier * (HS ? hsMultiplier : 1)</code> minus distance dropoff.</li>
            <li><strong>Unarmored Hit:</strong> Full <code>damage * (HS ? hsMultiplier : 1)</code> (ignores <code>armorMultiplier</code>).</li>
            <li><strong>Custom Logos Folder Import:</strong> PNG/JPG/WEBP filename stem becomes its DB key (e.g., <code>TeamLogo.png -> logo: "TeamLogo"</code>).</li>
          </ul>
        </div>
      </div>
    </div>
  `;

  $("legendBody").querySelectorAll("[data-lgsub]").forEach((b) => {
    b.addEventListener("click", () => {
      $("legendBody").querySelectorAll("[data-lgsub]").forEach((x) => x.classList.toggle("active", x === b));
      $("legendBody").querySelectorAll(".subpanel").forEach((p) => p.classList.toggle("active", p.id === `lgsub-${b.dataset.lgsub}`));
    });
  });
}

// ------------------------------------------------------------------
// Event Wiring & Bootstrap
// ------------------------------------------------------------------

document.addEventListener("DOMContentLoaded", async () => {
  try {
    state.meta = await apiGet("/api/meta");
    state.summary = await apiGet("/api/summary");
    updateTopbar();
    refreshOverview();
  } catch (err) {
    toast(err.message, "err");
  }

  document.querySelectorAll(".tab-btn").forEach((b) => {
    b.addEventListener("click", () => switchTab(b.dataset.tab));
  });

  // Subtabs
  document.querySelectorAll("[data-stsub]").forEach((b) => b.addEventListener("click", () => {
    document.querySelectorAll("[data-stsub]").forEach((x) => x.classList.toggle("active", x === b));
    document.querySelectorAll("#tab-staff .subpanel").forEach((p) => p.classList.toggle("active", p.id === `stsub-${b.dataset.stsub}`));
  }));
  document.querySelectorAll("[data-scsub]").forEach((b) => b.addEventListener("click", () => {
    document.querySelectorAll("[data-scsub]").forEach((x) => x.classList.toggle("active", x === b));
    document.querySelectorAll("#tab-schedule .subpanel").forEach((p) => p.classList.toggle("active", p.id === `scsub-${b.dataset.scsub}`));
  }));
  document.querySelectorAll("[data-dssub]").forEach((b) => b.addEventListener("click", () => {
    document.querySelectorAll("[data-dssub]").forEach((x) => x.classList.toggle("active", x === b));
    document.querySelectorAll("#tab-datascience .subpanel").forEach((p) => p.classList.toggle("active", p.id === `dssub-${b.dataset.dssub}`));
  }));
  document.querySelectorAll("[data-msub]").forEach((b) => b.addEventListener("click", () => {
    document.querySelectorAll("[data-msub]").forEach((x) => x.classList.toggle("active", x === b));
    document.querySelectorAll("#tab-mods .subpanel").forEach((p) => p.classList.toggle("active", p.id === `msub-${b.dataset.msub}`));
  }));

  // Topbar actions
  $("btnLoadDbPack").addEventListener("click", async () => {
    try {
      state.summary = await apiPost("/api/load-database", { path: $("dbPackSelect").value });
      updateTopbar();
      toast(`Loaded database: ${state.summary.dbName}`);
      refreshOverview();
    } catch (e) { toast(e.message, "err"); }
  });
  $("btnBrowseDb").addEventListener("click", async () => {
    try {
      const dlg = await apiPost("/api/browse-folder", {});
      if (dlg.ok && dlg.path) {
        state.summary = await apiPost("/api/load-database", { path: dlg.path });
        updateTopbar();
        toast(`Loaded database: ${state.summary.dbName}`);
        refreshOverview();
      }
    } catch (e) { toast(e.message, "err"); }
  });
  $("btnCloneDb").addEventListener("click", async () => {
    const name = prompt("New custom database folder name:", `${state.summary?.dbName || "custom"}_mod`);
    if (!name) return;
    try {
      const res = await apiPost("/api/clone-database", { name });
      state.summary = res.summary;
      updateTopbar();
      toast(`Cloned database into ${res.name}!`);
    } catch (e) { toast(e.message, "err"); }
  });
  $("btnSaveDb").addEventListener("click", async () => {
    try {
      const res = await apiPost("/api/save-database", {});
      toast(`Saved database to ${res.name} (backup created).`);
      state.summary = await apiGet("/api/summary");
      updateTopbar();
    } catch (e) { toast(e.message, "err"); }
  });

  $("btnRunValidate").addEventListener("click", () => refreshOverview(false));
  $("btnAutoFixDb").addEventListener("click", () => refreshOverview(true));

  $("teamSearch").addEventListener("input", loadTeamsList);
  $("teamRegionFilter").addEventListener("change", loadTeamsList);
  $("btnOpenNewTeam").addEventListener("click", openNewTeamModal);

  $("playerSearch").addEventListener("input", loadPlayersList);
  $("playerRoleFilter").addEventListener("change", loadPlayersList);
  $("playerFreeOnly").addEventListener("change", loadPlayersList);
  $("btnOpenNewPlayer").addEventListener("click", openNewPlayerModal);

  $("staffSearch").addEventListener("input", loadStaffList);
  $("btnOpenNewStaff").addEventListener("click", openNewStaffModal);
  $("btnNewSponsor").addEventListener("click", async () => {
    try {
      await apiPost("/api/sponsor/save", { name: "New Sponsor", reputation: 10, fixedMonthlyContribution: 5000, bonusPositionRequirement: 8, bonusPayout: 10000 });
      toast("Added new sponsor.");
      loadSponsors();
    } catch (e) { toast(e.message, "err"); }
  });

  $("tournSearch").addEventListener("input", loadTournamentsList);
  $("tournTierFilter").addEventListener("change", loadTournamentsList);
  $("btnOpenNewTournament").addEventListener("click", openNewTournamentModal);

  $("schedTierFilter").addEventListener("change", renderScheduleAudit);
  $("schedWhenFilter").addEventListener("change", renderScheduleAudit);
  $("schedLanOnly").addEventListener("change", renderScheduleAudit);
  $("btnImportSponsorLogos")?.addEventListener("click", () => triggerLogoFolderImport("sponsor", () => loadSponsors()));
  $("btnRefreshSched").addEventListener("click", loadScheduleAudit);
  $("btnRefreshDs").addEventListener("click", loadDbBalanceScience);

  $("btnLoadWeaponsPack").addEventListener("click", async () => {
    try {
      state.weaponsPack = await apiPost("/api/mod/weapons/load", { path: $("weaponsPackSelect").value });
      renderWeaponsLab();
      toast(`Loaded weapons pack: ${state.weaponsPack.name}`);
    } catch (e) { toast(e.message, "err"); }
  });
  $("btnApplyWeaponBatch").addEventListener("click", async () => {
    try {
      state.weaponsPack = await apiPost("/api/mod/weapons/scale", {
        action: $("wepBatchAction").value,
        weaponType: $("wepBatchType").value,
        pct: Number($("wepBatchPct").value),
      });
      renderWeaponsLab();
      toast("Batch weapon scaling applied!");
    } catch (e) { toast(e.message, "err"); }
  });
  $("btnSaveWeapons").addEventListener("click", async () => {
    try {
      const res = await apiPost("/api/mod/weapons/save", {});
      toast(`Saved weapons.json in ${res.name}.`);
    } catch (e) { toast(e.message, "err"); }
  });
  $("btnCloneWeapons").addEventListener("click", async () => {
    const newPackName = prompt("Save as new Weapons pack folder name:", `${state.weaponsPack?.name || "custom"}_balanced`);
    if (!newPackName) return;
    try {
      const res = await apiPost("/api/mod/weapons/save", { newPackName });
      state.summary = await apiGet("/api/summary");
      updateTopbar();
      toast(`Saved new Weapons pack: ${res.name}!`);
    } catch (e) { toast(e.message, "err"); }
  });

  $("btnLoadBalancePack").addEventListener("click", async () => {
    try {
      state.balancePack = await apiPost("/api/mod/balance/load", { path: $("balancePackSelect").value });
      renderBalanceLab();
      toast(`Loaded GameBalance: ${state.balancePack.name}`);
    } catch (e) { toast(e.message, "err"); }
  });
  $("btnSaveBalance").addEventListener("click", async () => {
    try {
      const res = await apiPost("/api/mod/balance/save", {});
      toast(`Saved gameBalance.json in ${res.name}.`);
    } catch (e) { toast(e.message, "err"); }
  });
  $("btnCloneBalance").addEventListener("click", async () => {
    const newPackName = prompt("Save as new GameBalance pack folder name:", `${state.balancePack?.name || "custom"}_mod`);
    if (!newPackName) return;
    try {
      const res = await apiPost("/api/mod/balance/save", { newPackName });
      state.summary = await apiGet("/api/summary");
      updateTopbar();
      toast(`Saved new GameBalance pack: ${res.name}!`);
    } catch (e) { toast(e.message, "err"); }
  });

  $("btnCloseModal").addEventListener("click", closeModal);
  $("modalBackdrop").addEventListener("click", (e) => { if (e.target === $("modalBackdrop")) closeModal(); });
});

// ------------------------------------------------------------------
// TAB 10: God Mode DB Balancer & Smoothing Toolkit
// ------------------------------------------------------------------

async function loadGodMode() {
  try {
    state.godMode = await apiGet("/api/god-mode/state");
    renderGodMode();
  } catch (err) {
    $("godModeBody").innerHTML = `<div class="card"><div class="alert-box err">${escapeHtml(err.message)}</div></div>`;
  }
}

function filterGodModeTeams() {
  const gm = state.godMode;
  const sel = $("gmNerfTeam");
  if (!gm || !sel) return;
  const q = ($("gmNerfTeamSearch")?.value || "").trim().toLowerCase();
  const curId = Number(state.godNerfSelectedTeamId || sel.value || 0);
  const teams = (gm.teams || []).filter((t) => !q || `${t.dbRank} ${t.name}`.toLowerCase().includes(q));
  sel.innerHTML = teams.length
    ? teams
        .map(
          (t) =>
            `<option value="${t.teamId}" ${t.teamId === curId ? "selected" : ""}>#${t.dbRank} ${escapeHtml(t.name)} (Avg ${t.avgSkill}, Floor ${t.weakestFloor})</option>`
        )
        .join("")
    : `<option value="">No matching teams</option>`;
  if (sel.value) state.godNerfSelectedTeamId = Number(sel.value);
}

function renderGodMode() {
  const gm = state.godMode;
  if (!gm || !gm.loaded) {
    $("godModeBody").innerHTML = `<div class="card"><div class="subcard">Load a CS Manager database first to use God Mode DB Balancer.</div></div>`;
    return;
  }
  const prevState = {
    nerfSearch: $("gmNerfTeamSearch")?.value || "",
    nerfTeam: $("gmNerfTeam")?.value || state.godNerfSelectedTeamId || "",
    nerfProtect: $("gmNerfProtect")?.value ?? "",
    nerfTarget: $("gmNerfTargetAvg")?.value || "16.2",
    nerfCap: $("gmNerfCap")?.value || "17.0",
    floorProtect: $("gmFloorProtect")?.value ?? "",
  };
  const sn = gm.snapshot || {};
  const teams = gm.teams || [];
  const res = state.godModeResult;

  const teamOptions = teams
    .map(
      (t) =>
        `<option value="${t.teamId}" ${String(t.teamId) === String(prevState.nerfTeam) ? "selected" : ""}>#${t.dbRank} ${escapeHtml(t.name)} (Avg ${t.avgSkill}, Floor ${t.weakestFloor})</option>`
    )
    .join("");
  const kpiCards = [
    { l: "DB Top-1 Star Team", v: sn.top1TeamName || "-", s: `Avg ${sn.top1AvgSkill} · ${sn.top1Bo3VsTop10}% Bo3 vs Top-10` },
    { l: "Top-10 / Top-20 Avg", v: `${sn.top10AvgSkill} / ${sn.top20AvgSkill}`, s: `Top-10 Spread: ${sn.top10Spread}` },
    { l: "Top-10 Parity Gini", v: sn.top10Gini, s: "Lower = closer title race" },
    { l: "AI Bench Sabotages (Top-20)", v: sn.aiBenchSabotagesTop20, s: "Starters weaker than benched sub" },
  ].map((k) => `<div class="kpi"><div class="kpi-lbl">${k.l}</div><div class="kpi-val">${escapeHtml(k.v)}</div><div class="kpi-sub">${escapeHtml(k.s)}</div></div>`).join("");

  let resultHtml = "";
  if (res) {
    const bef = res.before || {};
    const aft = res.after || {};
    const rows = (res.changes || []).map((c) => `<tr><td class="mono">${escapeHtml(c.target)}</td><td>${escapeHtml(c.team)}</td><td>${escapeHtml(c.detail)}</td></tr>`).join("");
    resultHtml = `
      <div class="card" style="margin-top:12px;border-color:${res.dryRun ? "var(--warn)" : "var(--ok)"};">
        <div class="card-head">
          <span class="card-title">${res.dryRun ? "DRY-RUN PREVIEW" : "APPLIED TO WORKSPACE"} — ${escapeHtml(res.action)} (${res.changeCount} edits)</span>
          <span class="pill ${res.dryRun ? "warn" : "ok"}">${res.dryRun ? "Preview Only (Not Applied)" : "Applied (Save Database to write disk)"}</span>
        </div>
        <p class="hint" style="margin-bottom:8px;">${escapeHtml(res.summary)}</p>
        <div class="kpi-grid">
          <div class="kpi"><div class="kpi-lbl">Top-1 Bo3 vs Top-10</div><div class="kpi-val">${bef.top1Bo3VsTop10}% -> ${aft.top1Bo3VsTop10}%</div><div class="kpi-sub">${escapeHtml(aft.top1TeamName || "")}</div></div>
          <div class="kpi"><div class="kpi-lbl">Top-10 Avg Skill</div><div class="kpi-val">${bef.top10AvgSkill} -> ${aft.top10AvgSkill}</div><div class="kpi-sub">Spread: ${bef.top10Spread} -> ${aft.top10Spread}</div></div>
          <div class="kpi"><div class="kpi-lbl">Top-20 Avg Skill</div><div class="kpi-val">${bef.top20AvgSkill} -> ${aft.top20AvgSkill}</div><div class="kpi-sub">Gini: ${bef.top10Gini} -> ${aft.top10Gini}</div></div>
          <div class="kpi"><div class="kpi-lbl">AI Bench Sabotages</div><div class="kpi-val">${bef.aiBenchSabotagesTop20} -> ${aft.aiBenchSabotagesTop20}</div><div class="kpi-sub">Top-20 active rosters</div></div>
        </div>
        <div class="table-wrap" style="max-height:240px;margin-top:8px;">
          <table><thead><tr><th>Target</th><th>Team</th><th>Change</th></tr></thead><tbody>${rows || '<tr><td colspan="3">No changes matched criteria.</td></tr>'}</tbody></table>
        </div>
      </div>
    `;
  }

  $("godModeBody").innerHTML = `
    <div class="card">
      <div class="card-head">
        <span class="card-title">God Mode DB Balancer &amp; Parity Smoothing Suite</span>
        <span class="hint">Pre-career database tuning adapted from the Save Editor. Use Dry-Run Preview first, then Apply and Save Database.</span>
      </div>
      <div class="kpi-grid">${kpiCards}</div>
    </div>

    <div class="split-equal" style="margin-top:12px;">
      <div class="card">
        <div class="card-head"><span class="card-title">1. League Skill Floor &amp; Target Smoother</span></div>
        <div class="form-grid">
          <div class="field"><label>Scope</label>
            <select id="gmFloorScope"><option value="top10">Top 10 Teams</option><option value="top20" selected>Top 20 Teams</option><option value="top30">Top 30 Teams</option><option value="all">All DB Teams</option></select>
          </div>
          <div class="field"><label>Mode</label>
            <select id="gmFloorMode"><option value="floor" selected>Raise Players Below Floor</option><option value="smooth_target">Smooth Teams Toward Target Avg</option><option value="weakest_slot_boost">Boost Weakest 2 Slots (+Delta)</option></select>
          </div>
          <div class="field"><label>Floor / Smooth Target</label><input id="gmFloorTarget" type="number" step="0.1" value="15.8" /></div>
          <div class="field"><label>Pull Strength (%)</label><input id="gmFloorStrength" type="number" value="75" min="5" max="100" /></div>
          <div class="field"><label>Weakest-Slot +Delta</label><input id="gmFloorDelta" type="number" step="0.1" value="1.2" /></div>
          <div class="field"><label>Protect Stars (csv)</label><input id="gmFloorProtect" type="text" value="${escapeHtml(prevState.floorProtect)}" /></div>
        </div>
        <div class="row" style="margin-top:8px;justify-content:space-between;">
          <label class="row" style="gap:6px;"><input type="checkbox" id="gmProtectTop1" /> Exclude DB #1 Team</label>
          <div class="row" style="gap:6px;">
            <button class="btn sm" onclick="execGodMode('boost_floor_parity', true)">Preview Dry-Run</button>
            <button class="btn ok sm" onclick="execGodMode('boost_floor_parity', false)">Apply Floor/Smooth</button>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-head"><span class="card-title">2. Team Smoother (Keep Your Favorite Star)</span></div>
        <div class="form-grid">
          <div class="field"><label>Filter Any Team (${teams.length} in DB)</label><input id="gmNerfTeamSearch" type="text" value="${escapeHtml(prevState.nerfSearch)}" oninput="filterGodModeTeams()" /></div>
          <div class="field"><label>Target Team</label><select id="gmNerfTeam" onchange="state.godNerfSelectedTeamId=Number(this.value)">${teamOptions}</select></div>
          <div class="field"><label>Protected Star(s) (csv)</label><input id="gmNerfProtect" type="text" value="${escapeHtml(prevState.nerfProtect)}" /></div>
          <div class="field"><label>New Team Target Avg</label><input id="gmNerfTargetAvg" type="number" step="0.1" value="${escapeHtml(prevState.nerfTarget)}" /></div>
          <div class="field"><label>Cap Teammate Avg</label><input id="gmNerfCap" type="number" step="0.1" value="${escapeHtml(prevState.nerfCap)}" /></div>
        </div>
        <div class="row" style="margin-top:10px;justify-content:flex-end;gap:6px;">
          <button class="btn sm" onclick="execGodMode('nerf_superteam_keep_stars', true)">Preview Dry-Run</button>
          <button class="btn warn sm" onclick="execGodMode('nerf_superteam_keep_stars', false)">Smooth Superteam</button>
        </div>
      </div>
    </div>

    <div class="split-equal" style="margin-top:12px;">
      <div class="card">
        <div class="card-head"><span class="card-title">3. AI Roster, Language &amp; Staff Sabotage Fixer</span></div>
        <div class="form-grid">
          <div class="field"><label>Scope</label><select id="gmAiScope"><option value="top10">Top 10</option><option value="top20" selected>Top 20</option><option value="top30">Top 30</option><option value="all">All Teams</option></select></div>
          <div class="field"><label>Min Staff Skill Floor</label><input id="gmAiStaff" type="number" step="0.5" value="15.0" /></div>
        </div>
        <div class="row" style="gap:12px;margin-top:8px;">
          <label class="row" style="gap:5px;"><input type="checkbox" id="gmAiBench" checked /> Auto-unbench stronger subs (Top-5 play)</label>
          <label class="row" style="gap:5px;"><input type="checkbox" id="gmAiLang" checked /> Sync team mainLanguage fluency (&gt;=16)</label>
        </div>
        <div class="row" style="margin-top:10px;justify-content:flex-end;gap:6px;">
          <button class="btn sm" onclick="execGodMode('fix_ai_sabotage', true)">Preview Dry-Run</button>
          <button class="btn ok sm" onclick="execGodMode('fix_ai_sabotage', false)">Fix AI Sabotages</button>
        </div>
      </div>

      <div class="card">
        <div class="card-head"><span class="card-title">4. Org Finances &amp; Owner Tier Rebalancer</span></div>
        <div class="form-grid">
          <div class="field"><label>Scope</label><select id="gmEconScope"><option value="top10">Top 10</option><option value="top20" selected>Top 20</option><option value="top30">Top 30</option><option value="all">All Teams</option></select></div>
          <div class="field"><label>Min Starting Balance ($)</label><input id="gmEconMinBal" type="number" step="100000" value="1500000" /></div>
          <div class="field"><label>Max Balance Cap (0=off)</label><input id="gmEconMaxCap" type="number" step="100000" value="0" /></div>
          <div class="field"><label>Min Owner Tier (0-20)</label><input id="gmEconOwnerTier" type="number" min="0" max="20" value="10" /></div>
        </div>
        <div class="row" style="margin-top:10px;justify-content:flex-end;gap:6px;">
          <button class="btn sm" onclick="execGodMode('rebalance_economy', true)">Preview Dry-Run</button>
          <button class="btn ok sm" onclick="execGodMode('rebalance_economy', false)">Rebalance Economy</button>
        </div>
      </div>
    </div>

    <div class="card" style="margin-top:12px;">
      <div class="card-head">
        <span class="card-title">5. U21 Wonderkid Intake Injector (Supports Custom Potential 50-275)</span>
        <div class="row" style="gap:6px;">
          <button class="btn sm" onclick="execGodMode('inject_wonderkids', true)">Preview Dry-Run</button>
          <button class="btn ok sm" onclick="execGodMode('inject_wonderkids', false)">Spawn Wonderkids</button>
        </div>
      </div>
      <div class="form-grid">
        <div class="field"><label>Count (1-25)</label><input id="gmWkCount" type="number" min="1" max="25" value="10" /></div>
        <div class="field"><label>Min Age</label><input id="gmWkMinAge" type="number" min="15" max="21" value="16" /></div>
        <div class="field"><label>Max Age</label><input id="gmWkMaxAge" type="number" min="15" max="22" value="18" /></div>
        <div class="field"><label>Base Avg Skill</label><input id="gmWkSkill" type="number" step="0.5" value="13.5" /></div>
        <div class="field"><label>Skill Limit Target</label><input id="gmWkPot" type="number" min="10" max="20" value="19" /></div>
        <div class="field"><label>Custom Potential (50-275)</label><input id="gmWkCp" type="number" min="50" max="275" value="255" /></div>
        <div class="field"><label>Placement</label><select id="gmWkAssign"><option value="free_agents" selected>Free Agent Pool</option><option value="top20_bench">Benched on Top-20 Teams</option></select></div>
        <div class="field"><label>Region Pool</label><select id="gmWkNation"><option value="diverse_pro" selected>Global Mix</option><option value="eu">Europe</option><option value="cis">CIS</option><option value="americas">Americas</option><option value="asia">Asia/OCE</option></select></div>
      </div>
      <label class="row" style="gap:6px;margin-top:6px;"><input type="checkbox" id="gmWkUseCp" checked /> Enable <code>useStartingPotential</code> lock on spawned wonderkids</label>
    </div>

    ${resultHtml}
  `;
  if (prevState.nerfSearch) filterGodModeTeams();
}

async function execGodMode(action, dryRun) {
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
      protectTop1Team: $("gmProtectTop1").checked,
    };
  } else if (action === "nerf_superteam_keep_stars") {
    params = {
      teamId: Number($("gmNerfTeam").value),
      protectedNames: $("gmNerfProtect").value,
      targetAvg: Number($("gmNerfTargetAvg").value),
      capNonProtected: Number($("gmNerfCap").value),
    };
  } else if (action === "fix_ai_sabotage") {
    params = {
      scope: $("gmAiScope").value,
      fixBench: $("gmAiBench").checked,
      syncLanguages: $("gmAiLang").checked,
      minStaffSkill: Number($("gmAiStaff").value),
    };
  } else if (action === "rebalance_economy") {
    params = {
      scope: $("gmEconScope").value,
      minBalance: Number($("gmEconMinBal").value),
      maxBalanceCap: Number($("gmEconMaxCap").value),
      minOwnerTier: Number($("gmEconOwnerTier").value),
    };
  } else if (action === "inject_wonderkids") {
    params = {
      count: Number($("gmWkCount").value),
      minAge: Number($("gmWkMinAge").value),
      maxAge: Number($("gmWkMaxAge").value),
      baseSkill: Number($("gmWkSkill").value),
      potTarget: Number($("gmWkPot").value),
      useStartingPotential: $("gmWkUseCp").checked,
      startingPotential: Number($("gmWkCp").value),
      assignMode: $("gmWkAssign").value,
      nationMode: $("gmWkNation").value,
    };
  }
  try {
    state.godModeResult = await apiPost("/api/god-mode/run", { action, params, dryRun });
    if (!dryRun) {
      state.godMode = await apiGet("/api/god-mode/state");
      state.summary = await apiGet("/api/summary");
      updateTopbar();
      toast(`Applied ${action} (${state.godModeResult.changeCount} edits). Save Database when ready.`);
    } else {
      toast(`Previewed ${action} (${state.godModeResult.changeCount} prospective edits).`);
    }
    renderGodMode();
  } catch (err) {
    toast(err.message, "err");
  }
}
