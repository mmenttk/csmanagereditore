/* CS Manager Save Studio - Core Shell, Routing, Charts, Command Palette & Undo Snapshots */

const state = {
  meta: null,
  summary: null,
  saves: [],
  teams: [],
  activeTab: "dashboard",

  // Dashboard & Diff
  hqData: null,
  comparableSaves: [],
  diffData: null,

  // Sandbox
  sandboxTeamId: 0,
  sandboxSlots: [],
  sandboxCandidates: [],
  sandboxResult: null,

  // Labs
  growthData: null,
  growthMode: "risers",
  growthSelectedPid: 0,
  weaponsData: null,
  selectedWeaponId: 0,

  // World & Market
  radarData: null,
  tournamentsData: null,
  selectedTournamentDetail: null,

  // Editors
  plOffset: 0,
  plLimit: 60,
  plTotal: 0,
  selectedPlayer: null,
  plSubTab: "basics",
  stOffset: 0,
  stLimit: 60,
  stTotal: 0,
  selectedStaff: null,
  selectedTeam: null,
  txPlayers: [],
  allRelations: [],

  // Analytics & God Mode
  statsData: null,
  eventStatsData: null,
  selectedEventId: null,
  showcaseData: null,
  showcaseTxShown: [],
  godMode: null,
  godModeResult: null,
  godNerfSelectedTeamId: 0,
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
  if (!stack) return;
  const el = document.createElement("div");
  el.className = `toast ${kind === "ok" ? "ok" : kind === "err" ? "err" : ""}`;
  el.textContent = msg;
  stack.appendChild(el);
  setTimeout(() => el.remove(), 4200);
}

async function api(url, opts = {}) {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

function formatDateObj(d) {
  if (!d || typeof d !== "object" || !d.year) return "-";
  const p = (n) => String(n).padStart(2, "0");
  return `${d.year}-${p(d.month || 1)}-${p(d.day || 1)}`;
}

function formatMoney(v) {
  const n = Number(v || 0);
  const sign = n < 0 ? "-" : "";
  return `${sign}$${Math.abs(Math.round(n)).toLocaleString()}`;
}

function renderSparklineSvg(values, opts = {}) {
  const arr = (values || []).map(Number).filter((x) => !Number.isNaN(x));
  if (arr.length < 2) return `<div class="muted" style="font-size:12px;">Not enough history points</div>`;
  const w = opts.width || 420;
  const h = opts.height || 86;
  const pad = 8;
  const invert = Boolean(opts.invert);
  let minV = opts.minVal !== undefined ? opts.minVal : Math.min(...arr);
  let maxV = opts.maxVal !== undefined ? opts.maxVal : Math.max(...arr);
  if (maxV - minV < 0.001) {
    maxV += 1;
    minV -= 1;
  }
  const color = opts.color || "#38bdf8";
  const pts = arr.map((v, idx) => {
    const x = pad + (idx * (w - pad * 2)) / Math.max(arr.length - 1, 1);
    const ratio = (v - minV) / (maxV - minV);
    const y = invert ? pad + ratio * (h - pad * 2) : h - pad - ratio * (h - pad * 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  const lastPt = pts[pts.length - 1].split(",");
  return `
    <svg viewBox="0 0 ${w} ${h}" style="width:100%;height:${h}px;display:block;">
      <polyline fill="none" stroke="${color}" stroke-width="2.2" points="${pts.join(" ")}" />
      <circle cx="${lastPt[0]}" cy="${lastPt[1]}" r="3.4" fill="${color}" />
      <text x="6" y="13" fill="#8b9bb4" font-size="10">${invert ? `#${minV}` : maxV.toFixed(1)}</text>
      <text x="6" y="${h - 4}" fill="#8b9bb4" font-size="10">${invert ? `#${maxV}` : minV.toFixed(1)}</text>
    </svg>`;
}

function renderMultiLineChartSvg(labels, seriesList, height = 220) {
  if (!labels || !labels.length || !seriesList.length) {
    return `<div class="muted" style="font-size:12px;">No multi-month chart data available.</div>`;
  }
  const w = 540;
  const h = height;
  const padL = 34;
  const padR = 14;
  const padT = 16;
  const padB = 26;
  const allVals = seriesList.flatMap((s) => s.values.filter((v) => v > 0));
  if (!allVals.length) return `<div class="muted">No numeric points.</div>`;
  const minV = Math.max(1, Math.floor(Math.min(...allVals) - 0.8));
  const maxV = Math.min(20, Math.ceil(Math.max(...allVals) + 0.8));
  const span = Math.max(maxV - minV, 1);

  const linesSvg = seriesList
    .map((s) => {
      const pts = s.values.map((v, idx) => {
        const x = padL + (idx * (w - padL - padR)) / Math.max(labels.length - 1, 1);
        const y = padT + (1 - (v - minV) / span) * (h - padT - padB);
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      });
      return `<polyline fill="none" stroke="${s.color}" stroke-width="2.2" points="${pts.join(" ")}" />`;
    })
    .join("");

  const legend = seriesList
    .map((s) => `<span style="display:inline-flex;align-items:center;gap:4px;margin-right:12px;font-size:11.5px;"><span style="width:10px;height:3px;background:${s.color};display:inline-block;"></span>${escapeHtml(s.label)}</span>`)
    .join("");

  return `
    <div style="margin-bottom:6px;">${legend}</div>
    <svg viewBox="0 0 ${w} ${h}" style="width:100%;height:${h}px;display:block;background:#070c17;border-radius:6px;">
      <line x1="${padL}" y1="${padT}" x2="${w - padR}" y2="${padT}" stroke="#1f2a40" stroke-dasharray="3,3" />
      <line x1="${padL}" y1="${h - padB}" x2="${w - padR}" y2="${h - padB}" stroke="#1f2a40" />
      ${linesSvg}
      <text x="6" y="${padT + 4}" fill="#8b9bb4" font-size="10">${maxV}</text>
      <text x="6" y="${h - padB}" fill="#8b9bb4" font-size="10">${minV}</text>
      <text x="${padL}" y="${h - 7}" fill="#8b9bb4" font-size="10">${escapeHtml(labels[0])}</text>
      <text x="${w - padR - 45}" y="${h - 7}" fill="#8b9bb4" font-size="10">${escapeHtml(labels[labels.length - 1])}</text>
    </svg>`;
}

function isSaveLoaded() {
  return Boolean(state.summary && (state.summary.loaded || state.summary.path));
}

function updateTopBarStatus() {
  const s = state.summary;
  if (!isSaveLoaded()) {
    $("statusBarMeta").textContent = "No save loaded";
    $("dirtyBadge").style.display = "none";
    return;
  }
  const fname = s.filename || s.fileName || "Uploaded Save";
  const dt = formatDateObj(s.datetime);
  $("statusBarMeta").innerHTML = `<strong>${escapeHtml(fname)}</strong> &middot; ${escapeHtml(dt)} &middot; ${escapeHtml(s.userTeamName || "-")} &middot; ${s.counts?.players || 0} players / ${s.counts?.teams || 0} teams`;
  $("dirtyBadge").style.display = s.dirty ? "inline-block" : "none";
  const picker = $("savePickerSelect");
  if (picker && s.path && Array.from(picker.options).some((o) => o.value === s.path)) {
    picker.value = s.path;
  }
}

async function refreshSnapshotBadge() {
  try {
    const res = await api("/api/studio/snapshots");
    const snaps = res.snapshots || [];
    $("snapCountBadge").textContent = String(snaps.length);
  } catch {
    $("snapCountBadge").textContent = "0";
  }
}

async function refreshSaveSummary() {
  state.summary = await api("/api/summary");
  updateTopBarStatus();
  refreshSnapshotBadge();
}

function activateTab(tabKey) {
  state.activeTab = tabKey;
  document.querySelectorAll(".nav-btn[data-tab]").forEach((b) => b.classList.toggle("active", b.dataset.tab === tabKey));
  document.querySelectorAll(".tab-panel").forEach((p) => p.classList.toggle("active", p.id === `tab-${tabKey}`));
  loadActiveTabData(tabKey);
}

function loadActiveTabData(tabKey) {
  if (!isSaveLoaded()) return;
  if (tabKey === "dashboard") loadCareerHq();
  else if (tabKey === "sandbox") initSandboxTab();
  else if (tabKey === "diff") loadComparableSaves();
  else if (tabKey === "radar") loadMarketRadar();
  else if (tabKey === "tournaments") loadTournamentsHub();
  else if (tabKey === "growth") loadGrowthLab();
  else if (tabKey === "weapons") loadWeaponMeta();
  else if (tabKey === "players") loadPlayersList();
  else if (tabKey === "staff") loadStaffList();
  else if (tabKey === "teams") loadTeamsPickList();
  else if (tabKey === "transfers") initTransfersDesk();
  else if (tabKey === "stats") loadStatsHub();
  else if (tabKey === "showcase") loadBugShowcaseStudio();
  else if (tabKey === "godmode") loadGodModeStudio();
}

async function reloadEntireWorkspace() {
  state.hqData = null;
  state.diffData = null;
  state.sandboxTeamId = 0;
  state.sandboxSlots = [];
  state.sandboxCandidates = [];
  state.sandboxResult = null;
  state.growthData = null;
  state.growthSelectedPid = 0;
  state.weaponsData = null;
  state.selectedWeaponId = 0;
  state.radarData = null;
  state.tournamentsData = null;
  state.selectedTournamentDetail = null;
  state.plOffset = 0;
  state.stOffset = 0;
  state.selectedPlayer = null;
  state.selectedStaff = null;
  state.selectedTeam = null;
  state.statsData = null;
  state.eventStatsData = null;
  state.selectedEventId = null;
  state.showcaseData = null;
  state.showcaseTxShown = [];
  state.godMode = null;
  state.godModeResult = null;
  state.godNerfSelectedTeamId = 0;

  if ($("plEditorBody")) $("plEditorBody").innerHTML = `<div class="muted">Select a player on the left...</div>`;
  if ($("stEditorBody")) $("stEditorBody").innerHTML = `<div class="muted">Select a staffer on the left...</div>`;
  if ($("tmEditorBody")) $("tmEditorBody").innerHTML = `<div class="muted">Select an organization...</div>`;
  if ($("tournDetailBody")) $("tournDetailBody").innerHTML = `<div class="muted">Select a tournament...</div>`;
  if ($("tournBatchResult")) $("tournBatchResult").innerHTML = "";
  if ($("diffBody")) $("diffBody").innerHTML = "";
  if ($("growthTrajectoryBox")) $("growthTrajectoryBox").innerHTML = `<div class="muted">Click any player row to plot their monthly curve.</div>`;
  if ($("weaponEditorBox")) $("weaponEditorBox").innerHTML = `<div class="muted">Select any weapon to tune its stats.</div>`;
  if ($("sandboxBody")) $("sandboxBody").innerHTML = "";

  await refreshSaveSummary();
  if (!isSaveLoaded()) return;
  const tRes = await api("/api/teams");
  state.teams = tRes.teams || [];
  populateCommonTeamSelects();
  loadActiveTabData(state.activeTab);
}

function populateCommonTeamSelects() {
  const optsAll = [`<option value="">All Teams</option>`]
    .concat(state.teams.map((t) => `<option value="${t.id}">${escapeHtml(t.name)} (#${t.worldRank || "-"})</option>`))
    .join("");
  if ($("plFilterTeam")) $("plFilterTeam").innerHTML = optsAll;
  if ($("stFilterTeam")) $("stFilterTeam").innerHTML = optsAll;
  if ($("statsFilterTeam")) $("statsFilterTeam").innerHTML = optsAll;

  if ($("hqMgrNation") && state.meta?.nations) {
    $("hqMgrNation").innerHTML = Object.entries(state.meta.nations)
      .sort((a, b) => String(a[1]).localeCompare(String(b[1])))
      .map(([id, name]) => `<option value="${id}">${escapeHtml(name)}</option>`)
      .join("");
  }
  if ($("stFilterRole") && state.meta?.staffRoles) {
    $("stFilterRole").innerHTML = [`<option value="">All Roles</option>`]
      .concat(Object.entries(state.meta.staffRoles).map(([id, name]) => `<option value="${id}">${escapeHtml(name)}</option>`))
      .join("");
  }
}

// ---- Command Palette (Ctrl+K) ----

function openCommandPalette() {
  $("cmdPaletteModal").classList.add("open");
  const inp = $("cmdPaletteInput");
  inp.value = "";
  setTimeout(() => inp.focus(), 40);
  runCommandSearch("");
}

let _cmdSearchTimer = null;
async function runCommandSearch(q) {
  try {
    const res = await api(`/api/studio/search?q=${encodeURIComponent(q)}&limit=7`);
    const sections = [
      ["Players", res.players || [], "player"],
      ["Organizations", res.teams || [], "team"],
      ["Staff", res.staff || [], "staff"],
      ["Tournaments", res.tournaments || [], "tournament"],
    ];
    $("cmdPaletteResults").innerHTML = sections
      .map(([title, items, kind]) => {
        if (!items.length) return "";
        return `
          <div style="margin-bottom:12px;">
            <div class="muted" style="font-size:11px;font-weight:700;text-transform:uppercase;margin-bottom:5px;">${title}</div>
            ${items
              .map(
                (it) => `<div class="pick-item cmd-hit" data-kind="${kind}" data-id="${it.id}">
                <div><strong>${escapeHtml(it.name)}</strong> <span class="muted" style="font-size:12px;">${escapeHtml(it.subtitle)}</span></div>
                <span class="pill pill-blue">#${it.id}</span>
              </div>`
              )
              .join("")}
          </div>`;
      })
      .join("") || `<div class="muted">No matching players, orgs, staff, or tournaments.</div>`;

    $("cmdPaletteResults").querySelectorAll(".cmd-hit").forEach((el) => {
      el.addEventListener("click", () => {
        const kind = el.dataset.kind;
        const id = Number(el.dataset.id);
        $("cmdPaletteModal").classList.remove("open");
        if (kind === "player") {
          activateTab("players");
          openPlayerPro(id);
        } else if (kind === "team") {
          activateTab("teams");
          openTeamPro(id);
        } else if (kind === "staff") {
          activateTab("staff");
          openStaffEditor(id);
        } else if (kind === "tournament") {
          activateTab("tournaments");
          openTournamentDetail(id);
        }
      });
    });
  } catch (err) {
    $("cmdPaletteResults").innerHTML = `<div class="stat-bad">${escapeHtml(err.message)}</div>`;
  }
}

// ---- Undo Snapshots Modal ----

async function openSnapshotsModal() {
  $("snapshotsModal").classList.add("open");
  try {
    const res = await api("/api/studio/snapshots");
    const snaps = res.snapshots || [];
    $("snapshotsModalBody").innerHTML = snaps.length
      ? `<div class="table-wrap" style="max-height:55vh;"><table>
          <thead><tr><th>#</th><th>Time</th><th>Checkpoint Label</th><th>Size</th><th>Action</th></tr></thead>
          <tbody>${snaps
            .map(
              (s) => `<tr>
              <td class="mono">${s.id}</td>
              <td class="mono muted">${escapeHtml(s.createdAt)}</td>
              <td><strong>${escapeHtml(s.label)}</strong></td>
              <td class="mono muted">${s.sizeKb} KB</td>
              <td><button class="btn btn-sm btn-warn snap-restore-btn" data-id="${s.id}">Restore</button></td>
            </tr>`
            )
            .join("")}</tbody>
        </table></div>`
      : `<div class="muted">No snapshots recorded yet.</div>`;

    $("snapshotsModalBody").querySelectorAll(".snap-restore-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        try {
          const r = await api("/api/studio/snapshot/restore", {
            method: "POST",
            body: JSON.stringify({ id: Number(btn.dataset.id) }),
          });
          $("snapshotsModal").classList.remove("open");
          toast(`Reverted to checkpoint: ${r.restored?.label || btn.dataset.id}`, "ok");
          await reloadEntireWorkspace();
        } catch (err) {
          toast(err.message, "err");
        }
      });
    });
  } catch (err) {
    $("snapshotsModalBody").innerHTML = `<div class="stat-bad">${escapeHtml(err.message)}</div>`;
  }
}

async function createManualSnapshot() {
  const lbl = window.prompt("Checkpoint label:", "Manual Studio Checkpoint");
  if (!lbl) return;
  try {
    await api("/api/studio/snapshot/create", { method: "POST", body: JSON.stringify({ label: lbl }) });
    toast(`Created checkpoint "${lbl}"`, "ok");
    await refreshSnapshotBadge();
    openSnapshotsModal();
  } catch (err) {
    toast(err.message, "err");
  }
}

// ---- Wire Core Shell Events ----

async function initStudioShell() {
  try {
    const [metaRes, savesRes] = await Promise.all([api("/api/meta"), api("/api/saves")]);
    state.meta = metaRes;
    state.saves = savesRes.saves || [];
    $("savePickerSelect").innerHTML = state.saves.length
      ? state.saves.map((s) => `<option value="${escapeHtml(s.path)}">${escapeHtml(s.name)} (${s.size_mb} MB)</option>`).join("")
      : `<option value="">No saves in SavedGames</option>`;
  } catch (err) {
    toast(`Studio init warning: ${err.message}`, "err");
  }

  document.querySelectorAll(".nav-btn[data-tab]").forEach((btn) => {
    btn.addEventListener("click", () => activateTab(btn.dataset.tab));
  });

  // Generic subtab wiring
  const wireSubtab = (attr, panelPrefix, onOpen) => {
    document.querySelectorAll(`.subtab-btn[data-${attr}]`).forEach((btn) => {
      btn.addEventListener("click", () => {
        const key = btn.dataset[attr];
        const parent = btn.closest(".card") || btn.closest(".tab-panel");
        parent.querySelectorAll(`.subtab-btn[data-${attr}]`).forEach((b) => b.classList.remove("active"));
        parent.querySelectorAll(`[id^="${panelPrefix}-"]`).forEach((p) => p.classList.remove("active"));
        btn.classList.add("active");
        $(`${panelPrefix}-${key}`)?.classList.add("active");
        if (onOpen) onOpen(key);
      });
    });
  };
  wireSubtab("rsubtab", "rsubtab");
  wireSubtab("gsubtab", "gsubtab", (key) => {
    state.growthMode = key;
    if (typeof renderGrowthTable === "function") renderGrowthTable();
  });
  wireSubtab("tsubtab", "tsubtab", (key) => {
    if (key === "relations" && typeof loadRelationsManager === "function") loadRelationsManager();
  });
  wireSubtab("subtab", "subtab", (key) => {
    if (key === "events" && !state.eventStatsData && typeof loadEventStatsStudio === "function") loadEventStatsStudio();
  });
  wireSubtab("bsubtab", "bsubtab");

  async function loadSaveFromPath(p) {
    if (!p) return;
    try {
      toast("Loading save into Save Studio...", "info");
      await api("/api/load", { method: "POST", body: JSON.stringify({ path: p }) });
      await reloadEntireWorkspace();
      toast(`Loaded ${state.summary?.filename || "save"}`, "ok");
    } catch (err) {
      toast(err.message, "err");
    }
  }

  $("btnLoadSelectedSave").addEventListener("click", () => loadSaveFromPath($("savePickerSelect").value));
  $("savePickerSelect").addEventListener("change", () => loadSaveFromPath($("savePickerSelect").value));

  $("btnUploadSave").addEventListener("click", () => $("saveUploadInput").click());
  $("saveUploadInput").addEventListener("change", async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      toast(`Uploading ${file.name}...`, "info");
      const content = await file.text();
      await api("/api/load-upload", { method: "POST", body: JSON.stringify({ filename: file.name, content }) });
      await reloadEntireWorkspace();
      toast(`Uploaded ${file.name}`, "ok");
    } catch (err) {
      toast(err.message, "err");
    } finally {
      e.target.value = "";
    }
  });

  $("btnSaveDisk").addEventListener("click", async () => {
    try {
      const r = await api("/api/save", { method: "POST", body: JSON.stringify({}) });
      toast(`Saved ${r.saved_path || r.savedPath || "save"}`, "ok");
      await refreshSaveSummary();
    } catch (err) {
      toast(err.message, "err");
    }
  });

  $("btnBackupDisk").addEventListener("click", async () => {
    try {
      const r = await api("/api/backup", { method: "POST", body: JSON.stringify({}) });
      toast(`Backup written (${r.sizeMb} MB): ${r.backupPath}`, "ok");
    } catch (err) {
      toast(err.message, "err");
    }
  });

  $("btnDownloadJson").addEventListener("click", () => {
    window.location.href = "/api/download";
  });

  $("btnValidateSave").addEventListener("click", async () => {
    try {
      const res = await api("/api/validate");
      if (res.issueCount === 0) {
        toast("Save Integrity Check: 0 issues found!", "ok");
      } else if (window.confirm(`Found ${res.issueCount} tactic/contract issue(s). Auto-fix now?`)) {
        const fixed = await api("/api/validate", { method: "POST", body: JSON.stringify({ fix: true }) });
        toast(`Fixed ${fixed.fixedTeamCount ?? fixed.issueCount} issue(s)`, "ok");
        await refreshSaveSummary();
      }
    } catch (err) {
      toast(err.message, "err");
    }
  });

  $("btnCommandPalette").addEventListener("click", openCommandPalette);
  $("btnCloseCmdModal").addEventListener("click", () => $("cmdPaletteModal").classList.remove("open"));
  $("cmdPaletteInput").addEventListener("input", (e) => {
    clearTimeout(_cmdSearchTimer);
    _cmdSearchTimer = setTimeout(() => runCommandSearch(e.target.value), 120);
  });

  $("btnOpenSnapshots").addEventListener("click", openSnapshotsModal);
  $("btnCloseSnapModal").addEventListener("click", () => $("snapshotsModal").classList.remove("open"));
  $("btnCreateManualSnap").addEventListener("click", createManualSnapshot);

  $("btnClosePsModal").addEventListener("click", () => $("playerStatsModal").classList.remove("open"));
  $("btnCloseTsModal").addEventListener("click", () => $("teamStatsModal").classList.remove("open"));
  $("btnCloseTbModal").addEventListener("click", () => $("transferBiddersModal").classList.remove("open"));

  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      openCommandPalette();
    } else if (e.key === "Escape") {
      document.querySelectorAll(".modal-backdrop.open").forEach((m) => m.classList.remove("open"));
    }
  });

  // Bind section listeners initialized in sibling modules cleanly
  if (typeof bindDashboardEvents === "function") bindDashboardEvents();
  if (typeof bindLabEvents === "function") bindLabEvents();
  if (typeof bindWorldEvents === "function") bindWorldEvents();
  if (typeof bindEditorEvents === "function") bindEditorEvents();
  if (typeof bindAnalyticsEvents === "function") bindAnalyticsEvents();

  await reloadEntireWorkspace();
}

document.addEventListener("DOMContentLoaded", initStudioShell);
