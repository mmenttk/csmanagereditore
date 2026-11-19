/* CS Manager Save Studio Add-Ons (Merged into Save Editor UI)
 * All top-level symbols use the `studio` prefix so zero globals collide with app.js.
 */

const studioState = {
  initialized: false,
  activeStSubtab: "stCareerHq",
  lastSaveKey: "",
  searchSeq: 0,
  careerHq: null,
  diffSaves: null,
  tournaments: null,
  selectedTournamentId: null,
  selectedTournamentDetail: null,
  customAwardOrder: [],
  sandboxPool: null,
  sandboxSelectedIds: [],
  growthData: null,
  marketRadar: null,
  weaponsData: null,
  selectedWeaponId: null,
};

function studioHasSaveLoaded() {
  return Boolean(state.summary && (state.summary.path || state.summary.loaded || state.summary.filename));
}

function studioFmtMoney(n) {
  const num = Number(n || 0);
  const sign = num < 0 ? "-" : "";
  return `${sign}$${Math.abs(Math.round(num)).toLocaleString()}`;
}

function studioFmtDelta(n, digits = 2) {
  const v = Number(n || 0);
  if (Math.abs(v) < 1e-6) return `<span class="delta-flat">0.00</span>`;
  const cls = v > 0 ? "delta-up" : "delta-down";
  const prefix = v > 0 ? "+" : "";
  return `<span class="${cls}">${prefix}${v.toFixed(digits)}</span>`;
}

function studioResetLazyCaches() {
  const saveKey = String(state.summary?.path || state.summary?.filename || "");
  if (saveKey && saveKey !== studioState.lastSaveKey) {
    studioState.lastSaveKey = saveKey;
    studioState.selectedTournamentId = null;
    studioState.customAwardOrder = [];
    studioState.sandboxSelectedIds = [];
    studioState.selectedWeaponId = null;
  }
  studioState.careerHq = null;
  studioState.diffSaves = null;
  studioState.tournaments = null;
  studioState.selectedTournamentDetail = null;
  studioState.sandboxPool = null;
  studioState.growthData = null;
  studioState.marketRadar = null;
  studioState.weaponsData = null;
}

async function studioOnTabActivated(tabName) {
  if (!studioHasSaveLoaded()) return;
  if (tabName === "tournaments") {
    if (!studioState.tournaments) await studioLoadTournaments();
  } else if (tabName === "studiolabs") {
    if (studioState.activeStSubtab === "stCareerHq") {
      if (!studioState.careerHq) await studioLoadCareerHq();
    } else if (studioState.activeStSubtab === "stDiff") {
      if (!studioState.diffSaves) await studioLoadDiffSaves();
    } else if (studioState.activeStSubtab === "stGodMode") {
      if (!state.godModeData && typeof loadGodMode === "function") await loadGodMode();
    } else if (studioState.activeStSubtab === "stSandbox") {
      if (!studioState.sandboxPool) await studioInitSandbox();
    } else if (studioState.activeStSubtab === "stGrowth") {
      if (!studioState.growthData) await studioLoadGrowthLab();
    } else if (studioState.activeStSubtab === "stMarket") {
      if (!studioState.marketRadar) await studioLoadMarketRadar();
    } else if (studioState.activeStSubtab === "stWeapons") {
      if (!studioState.weaponsData) await studioLoadWeaponsLab();
    }
  }
}

// =========================================================================
// SVG Chart Builders
// =========================================================================

function studioBuildSparklineSvg(values, invertY = true, labelPrefix = "#") {
  if (!values || values.length < 2) {
    return '<span class="muted" style="font-size:12px;">Not enough history points yet.</span>';
  }
  const w = 460;
  const h = 92;
  const padX = 10;
  const padY = 12;
  const minV = Math.min(...values);
  const maxV = Math.max(...values);
  const span = Math.max(1, maxV - minV);
  const pts = values.map((v, idx) => {
    const x = padX + (idx / (values.length - 1)) * (w - padX * 2);
    const norm = (v - minV) / span;
    const y = invertY ? padY + norm * (h - padY * 2) : h - padY - norm * (h - padY * 2);
    return [x.toFixed(1), y.toFixed(1), v];
  });
  const pathD = pts.map((p, i) => `${i === 0 ? "M" : "L"}${p[0]},${p[1]}`).join(" ");
  const last = pts[pts.length - 1];
  const first = pts[0];
  return `
    <svg viewBox="0 0 ${w} ${h}" style="width:100%;height:92px;display:block;">
      <path d="${pathD}" fill="none" stroke="var(--blue)" stroke-width="2.2" />
      <circle cx="${first[0]}" cy="${first[1]}" r="3" fill="var(--text-muted)" />
      <circle cx="${last[0]}" cy="${last[1]}" r="4" fill="var(--accent)" />
      <text x="6" y="13" fill="var(--text-muted)" font-size="11">Start: ${labelPrefix}${first[2]}</text>
      <text x="${w - 110}" y="13" fill="var(--accent)" font-size="11" font-weight="bold">Latest: ${labelPrefix}${last[2]}</text>
    </svg>
  `;
}

function studioBuildTrajectorySvg(series) {
  if (!series || !series.length) {
    return '<div class="muted">No `playerSkillHistories` entries found for this player yet.</div>';
  }
  const w = 680;
  const h = 190;
  const padL = 34;
  const padR = 16;
  const padT = 18;
  const padB = 26;
  const plotW = w - padL - padR;
  const plotH = h - padT - padB;
  const keys = [
    { key: "overall", label: "Overall", color: "#f59e0b" },
    { key: "mechanics", label: "Mech", color: "#38bdf8" },
    { key: "weapons", label: "Weap", color: "#22c55e" },
    { key: "mental", label: "Mental", color: "#a78bfa" },
  ];
  const allVals = series.flatMap((pt) => keys.map((k) => Number(pt[k.key] || 0)));
  const minY = Math.max(1, Math.floor(Math.min(...allVals) - 0.5));
  const maxY = Math.min(20, Math.ceil(Math.max(...allVals) + 0.5));
  const spanY = Math.max(1, maxY - minY);
  const xFor = (i) => (series.length === 1 ? padL + plotW / 2 : padL + (i / (series.length - 1)) * plotW);
  const yFor = (v) => padT + plotH - ((v - minY) / spanY) * plotH;

  let gridHtml = "";
  for (let g = 0; g <= 4; g += 1) {
    const val = minY + (spanY * g) / 4;
    const y = yFor(val).toFixed(1);
    gridHtml += `<line x1="${padL}" y1="${y}" x2="${w - padR}" y2="${y}" stroke="rgba(142,160,186,0.18)" stroke-dasharray="3,3" />`;
    gridHtml += `<text x="4" y="${Number(y) + 4}" fill="#8ea0ba" font-size="10">${val.toFixed(1)}</text>`;
  }

  let linesHtml = "";
  for (const k of keys) {
    const d = series.map((pt, i) => `${i === 0 ? "M" : "L"}${xFor(i).toFixed(1)},${yFor(Number(pt[k.key] || 0)).toFixed(1)}`).join(" ");
    const lp = series[series.length - 1];
    linesHtml += `<path d="${d}" fill="none" stroke="${k.color}" stroke-width="2.1" />`;
    linesHtml += `<circle cx="${xFor(series.length - 1).toFixed(1)}" cy="${yFor(Number(lp[k.key] || 0)).toFixed(1)}" r="3.2" fill="${k.color}" />`;
  }

  const firstLbl = series[0].label;
  const lastLbl = series[series.length - 1].label;
  const legendHtml = keys
    .map((k) => {
      const lp = series[series.length - 1];
      return `<span style="color:${k.color};margin-right:12px;">&#9679; ${k.label}: ${Number(lp[k.key] || 0).toFixed(2)}</span>`;
    })
    .join("");

  return `
    <div style="font-size:12px;margin-bottom:4px;">${legendHtml}</div>
    <svg viewBox="0 0 ${w} ${h}" style="width:100%;max-height:190px;display:block;">
      ${gridHtml}
      ${linesHtml}
      <text x="${padL}" y="${h - 6}" fill="#8ea0ba" font-size="10">${escapeHtml(firstLbl)}</text>
      <text x="${w - padR - 55}" y="${h - 6}" fill="#8ea0ba" font-size="10">${escapeHtml(lastLbl)}</text>
    </svg>
  `;
}

// =========================================================================
// Topbar: Command Palette (Ctrl+K), Undo Time Machine Snapshots, Disk Backup
// =========================================================================

function studioOpenModal(id) {
  const el = $(id);
  if (el) el.classList.add("open");
}

function studioCloseModal(id) {
  const el = $(id);
  if (el) el.classList.remove("open");
}

async function studioRunGlobalSearch() {
  if (!studioHasSaveLoaded()) {
    $("cmdResultsList").innerHTML = '<div class="muted" style="padding:12px;">Load a save file first.</div>';
    return;
  }
  const q = ($("cmdSearchInput")?.value || "").trim();
  const seq = ++studioState.searchSeq;
  try {
    const res = await api(`/api/studio/search?q=${encodeURIComponent(q)}&limit=8`);
    if (seq !== studioState.searchSeq) return;
    const sections = [
      { key: "players", label: "Player", badge: "pill-blue" },
      { key: "teams", label: "Team / Org", badge: "pill-ok" },
      { key: "staff", label: "Staff", badge: "pill-purple" },
      { key: "tournaments", label: "Tournament", badge: "pill-warn" },
    ];
    let html = "";
    for (const sec of sections) {
      for (const item of res[sec.key] || []) {
        html += `
          <div class="pick-item cmd-hit" data-kind="${sec.key}" data-id="${item.id}">
            <div>
              <strong>${escapeHtml(item.name)}</strong>
              <div class="muted">${escapeHtml(item.subtitle || "")}</div>
            </div>
            <span class="pill ${sec.badge}">${sec.label} #${item.id}</span>
          </div>
        `;
      }
    }
    $("cmdResultsList").innerHTML = html || '<div class="muted" style="padding:12px;">No matching entities found.</div>';
    $("cmdResultsList").querySelectorAll(".cmd-hit").forEach((row) => {
      row.addEventListener("click", async () => {
        const kind = row.dataset.kind;
        const id = Number(row.dataset.id);
        studioCloseModal("cmdPaletteModal");
        if (kind === "players") {
          switchMainTab("players");
          await openPlayerEditor(id);
        } else if (kind === "teams") {
          switchMainTab("teams");
          await openTeamEditor(id);
        } else if (kind === "staff") {
          switchMainTab("staff");
          await openStaffEditor(id);
        } else if (kind === "tournaments") {
          switchMainTab("tournaments");
          await studioSelectTournament(id);
        }
      });
    });
  } catch (err) {
    $("cmdResultsList").innerHTML = `<div class="muted" style="padding:12px;">Search failed: ${escapeHtml(err.message)}</div>`;
  }
}

async function studioLoadSnapshotsModal() {
  if (!studioHasSaveLoaded()) {
    $("snapModalBody").innerHTML = '<div class="muted">No save file is currently loaded.</div>';
    return;
  }
  try {
    const res = await api("/api/studio/snapshots");
    const snaps = res.snapshots || [];
    const badge = $("snapCountBadge");
    if (badge) badge.textContent = String(snaps.length);
    if (!snaps.length) {
      $("snapModalBody").innerHTML = '<div class="muted">No checkpoints recorded yet.</div>';
      return;
    }
    $("snapModalBody").innerHTML = `
      <div class="table-wrap" style="max-height:52vh;">
        <table>
          <thead><tr><th>#</th><th>Label</th><th>Saved At</th><th>Size</th><th>Action</th></tr></thead>
          <tbody>
            ${snaps
              .map(
                (s) => `<tr>
                  <td class="mono">#${s.id}</td>
                  <td><strong>${escapeHtml(s.label)}</strong></td>
                  <td class="muted">${escapeHtml(s.createdAt || "-")}</td>
                  <td class="muted">${escapeHtml(s.sizeKb ?? 0)} KB</td>
                  <td><button type="button" class="btn btn-sm btn-blue snap-restore-btn" data-id="${s.id}">Restore Checkpoint</button></td>
                </tr>`
              )
              .join("")}
          </tbody>
        </table>
      </div>
    `;
    $("snapModalBody").querySelectorAll(".snap-restore-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const sid = Number(btn.dataset.id);
        try {
          const r = await api("/api/studio/snapshot/restore", {
            method: "POST",
            body: JSON.stringify({ id: sid }),
          });
          await refreshSummaryOnly();
          await refreshAllViews();
          await studioLoadSnapshotsModal();
          toast(`Restored checkpoint #${sid}: ${r.restored?.label || ""}`, "ok");
        } catch (err) {
          toast(`Restore failed: ${err.message}`, "err");
        }
      });
    });
  } catch (err) {
    $("snapModalBody").innerHTML = `<div class="muted">Failed to load snapshots: ${escapeHtml(err.message)}</div>`;
  }
}

// =========================================================================
// Career HQ & Club Takeover + Save Diff
// =========================================================================

const STUDIO_SEC_AXES = [
  ["securityFromLeague", "League Standing"],
  ["securityFromChampionship", "Playoffs / Majors"],
  ["securityFromRanking", "World Ranking"],
  ["securityFromBudget", "Budget Health"],
  ["securityFromLongevity", "Manager Longevity"],
  ["securityFromSquadComposition", "Squad Composition"],
  ["securityFromPreviousSeason", "Previous Season"],
];

async function studioLoadCareerHq() {
  if (!studioHasSaveLoaded()) return;
  try {
    const d = await api("/api/studio/career-hq");
    studioState.careerHq = d;
    if (!d.loaded) return;

    const p = d.profile || {};
    const t = d.team;
    const mc = d.managerContract || {};
    const ms = d.managerStaff || {};

    $("chKpiGrid").innerHTML = [
      { label: "Managed Club", val: t ? t.name : "Unemployed", sub: t ? `${t.worldRank ? `#${t.worldRank}` : "Unranked"} · Rep ${t.reputation}` : "Pick a team to take over" },
      { label: "Club Balance", val: t ? studioFmtMoney(t.balance) : "-", sub: t ? `${t.starterCount} starters / ${t.benchedCount} bench` : "" },
      { label: "5-Man Avg Skill", val: t ? t.avgSkill : "-", sub: t ? `Trophies: ${t.trophiesCount}` : "" },
      { label: "Squad Mood / Burnout", val: t ? `${t.avgMood} / ${t.avgBurnout}` : "-", sub: "Higher mood & lower burnout = peak form" },
      { label: "Manager Salary", val: mc.salaryYear ? studioFmtMoney(mc.salaryYear) : "-", sub: `Exp: ${formatDateObj(mc.endDate)}` },
    ]
      .map(
        (k) => `<div class="kpi-card">
          <div class="kpi-label">${escapeHtml(k.label)}</div>
          <div class="kpi-val">${escapeHtml(k.val)}</div>
          <div class="kpi-sub">${escapeHtml(k.sub)}</div>
        </div>`
      )
      .join("");

    $("chManagerName").value = p.name || "";
    $("chManagerAge").value = p.age || 30;
    populateSelect($("chManagerNation"), dictEntries(state.meta.nations), p.nation);
    $("chManagerSalary").value = mc.salaryYear ?? 0;
    const endIso = formatDateObj(mc.endDate);
    $("chManagerEndDate").value = endIso === "-" ? "" : endIso;

    $("chManagerSkillsGrid").innerHTML = (state.meta.staffSkills || [])
      .map((sk) => {
        const val = Number(ms.skills?.[sk.key] ?? 10).toFixed(1);
        return `
          <div class="skill-item" style="grid-template-columns:1fr 78px;">
            <div>
              <span class="skill-name">${escapeHtml(sk.label)}</span>
              <span class="skill-group">${escapeHtml(sk.group)}</span>
            </div>
            <input type="number" min="1" max="20" step="0.5" class="ch-mgr-skill" data-key="${sk.key}" value="${val}" />
          </div>
        `;
      })
      .join("");

    const js = t?.jobSecurity || {};
    $("chRankGoal").value = js.rankingGoal ?? 1000;
    $("chGracePeriod").value = js.gracePeriod ?? 0;
    $("chSecSliders").innerHTML = STUDIO_SEC_AXES.map(([key, label]) => {
      const val = Number(js[key] ?? 0.5).toFixed(2);
      return `
        <div class="pers-item">
          <div class="pers-head">
            <span>${escapeHtml(label)}</span>
            <span class="mono" id="chSecVal-${key}">${val}</span>
          </div>
          <input type="range" min="0" max="1" step="0.02" class="ch-sec-slider" data-key="${key}" value="${val}" />
        </div>
      `;
    }).join("");

    $("chSecSliders").querySelectorAll(".ch-sec-slider").forEach((sl) => {
      sl.addEventListener("input", () => {
        const sp = $(`chSecVal-${sl.dataset.key}`);
        if (sp) sp.textContent = Number(sl.value).toFixed(2);
      });
    });

    studioRenderSwitchTeamsSelect();

    if (t) {
      $("chRankSparkline").innerHTML = studioBuildSparklineSvg(t.rankingHistory || [], true, "#");
      const trs = t.recentTrophies || [];
      $("chRecentTrophies").innerHTML = trs.length
        ? trs.map((x) => `<span class="tag-pill">${escapeHtml(x.year || "")} · Trophy #${escapeHtml(x.tournamentTemplate || x.tournamentId || "")}</span>`).join(" ")
        : '<span class="muted">No trophy history recorded at this club yet.</span>';

      $("chRosterTableBody").innerHTML = (t.roster || []).length
        ? t.roster
            .map(
              (r) => `<tr class="ch-player-row" data-pid="${r.playerId}" style="cursor:pointer;">
                <td><strong>${escapeHtml(r.name)}</strong> <span class="muted">(${r.age})</span></td>
                <td>${r.benched ? '<span class="pill pill-warn">Bench</span>' : '<span class="pill pill-ok">Starter</span>'}</td>
                <td class="mono">${r.avgSkill}</td>
                <td class="mono">${r.mood}</td>
                <td class="mono">${r.burnout}</td>
                <td class="mono">${studioFmtMoney(r.salaryYear)}</td>
              </tr>`
            )
            .join("")
        : '<tr><td colspan="6" class="muted">No active squad players.</td></tr>';

      $("chRosterTableBody").querySelectorAll(".ch-player-row").forEach((tr) => {
        tr.addEventListener("click", async () => {
          switchMainTab("players");
          await openPlayerEditor(Number(tr.dataset.pid));
        });
      });
    } else {
      $("chRankSparkline").innerHTML = '<span class="muted">No team managed.</span>';
      $("chRecentTrophies").innerHTML = "-";
      $("chRosterTableBody").innerHTML = "";
    }

    $("chTransfersTableBody").innerHTML = (d.recentTransfers || []).length
      ? d.recentTransfers
          .map(
            (tx) => `<tr>
              <td class="muted">${escapeHtml(tx.date || formatDateObj(tx.datetime))}</td>
              <td><strong>${escapeHtml(tx.personName || "")}</strong></td>
              <td>${escapeHtml(tx.fromTeamName || "-")}</td>
              <td>${escapeHtml(tx.toTeamName || "-")}</td>
              <td class="mono">${studioFmtMoney(tx.purchasePrice)}</td>
            </tr>`
          )
          .join("")
      : '<tr><td colspan="5" class="muted">No transfers recorded yet.</td></tr>';
  } catch (err) {
    toast(`Career HQ error: ${err.message}`, "err");
  }
}

function studioRenderSwitchTeamsSelect() {
  const all = studioState.careerHq?.allTeams || state.teams || [];
  const q = ($("chSwitchTeamSearch")?.value || "").trim().toLowerCase();
  const filtered = q
    ? all.filter((t) => `${t.worldRank ? `#${t.worldRank} ` : ""}${t.name}`.toLowerCase().includes(q))
    : all;
  const curTid = studioState.careerHq?.profile?.teamId || filtered[0]?.id || "";
  populateSelect(
    $("chSwitchTeamSelect"),
    filtered.map((t) => {
      const pCount = (t.activeCount ?? 0) + (t.benchedCount ?? 0);
      return [
        t.id,
        `${t.worldRank ? `#${t.worldRank} ` : ""}${t.name}${t.isUserTeam ? " ★" : ""} (${pCount}p · ${t.avgSkill ?? 0} avg)`,
      ];
    }),
    curTid
  );
}

async function studioLoadDiffSaves() {
  if (!studioHasSaveLoaded()) return;
  try {
    const res = await api("/api/studio/diff/saves");
    studioState.diffSaves = res.saves || [];
    const curVal = $("diffBaselineSelect").value;
    const defaultPick = studioState.diffSaves.find((s) => !s.isCurrent)?.path || studioState.diffSaves[0]?.path || "";
    populateSelect(
      $("diffBaselineSelect"),
      studioState.diffSaves.map((s) => [s.path, `[${s.source}] ${s.name}${s.isCurrent ? " (CURRENT)" : ""} · ${s.modified}`]),
      curVal || defaultPick
    );
  } catch (err) {
    toast(`Failed to list comparable saves: ${err.message}`, "err");
  }
}

async function studioRunSaveDiff() {
  const baselinePath = $("diffBaselineSelect").value;
  if (!baselinePath) {
    toast("Pick a baseline save or backup first.", "err");
    return;
  }
  try {
    const d = await api("/api/studio/diff/compare", {
      method: "POST",
      body: JSON.stringify({ baselinePath }),
    });
    const bm = d.baselineMeta || {};
    const cm = d.currentMeta || {};
    $("diffMetaBanner").innerHTML = `<strong>Baseline:</strong> ${escapeHtml(bm.name)} (${escapeHtml(bm.date)}, ${bm.matches} matches) &rarr; <strong>Current:</strong> ${escapeHtml(cm.name)} (${escapeHtml(cm.date)}, ${cm.matches} matches)`;

    $("diffKpiGrid").innerHTML = [
      { label: "Skill Risers", val: (d.skillRisers || []).length, sub: "Players improving" },
      { label: "Skill Fallers", val: (d.skillFallers || []).length, sub: "Players declining" },
      { label: "Rank Movers", val: (d.rankClimbers || []).length + (d.rankFallers || []).length, sub: "Climbers + Fallers" },
      { label: "New Transfers", val: (d.newTransfers || []).length, sub: "Since baseline date" },
      { label: "New Trophies & Awards", val: (d.newTrophies || []).length + (d.newAwards || []).length, sub: `${(d.newTrophies || []).length} team / ${(d.newAwards || []).length} player` },
    ]
      .map(
        (k) => `<div class="kpi-card"><div class="kpi-label">${escapeHtml(k.label)}</div><div class="kpi-val">${escapeHtml(k.val)}</div><div class="kpi-sub">${escapeHtml(k.sub)}</div></div>`
      )
      .join("");

    const renderSkillDiffs = (rows) =>
      rows && rows.length
        ? rows
            .map(
              (r) => `<tr>
                <td><strong>${escapeHtml(r.name)}</strong> <span class="muted">(${r.age})</span></td>
                <td>${escapeHtml(r.teamName)}</td>
                <td class="mono">${r.beforeAvg}</td>
                <td class="mono">${r.afterAvg}</td>
                <td class="mono">${studioFmtDelta(r.delta)}</td>
              </tr>`
            )
            .join("")
        : '<tr><td colspan="5" class="muted">No changes recorded.</td></tr>';

    $("diffSkillRisersBody").innerHTML = renderSkillDiffs(d.skillRisers);
    $("diffSkillFallersBody").innerHTML = renderSkillDiffs(d.skillFallers);

    const combinedRanks = [...(d.rankClimbers || []).slice(0, 20), ...(d.rankFallers || []).slice(0, 20)];
    $("diffRankClimbersBody").innerHTML = combinedRanks.length
      ? combinedRanks
          .map(
            (r) => `<tr>
              <td><strong>${escapeHtml(r.name)}</strong></td>
              <td class="mono">#${r.beforeRank}</td>
              <td class="mono">#${r.afterRank}</td>
              <td class="mono">${r.climb > 0 ? `<span class="delta-up">+${r.climb}</span>` : `<span class="delta-down">${r.climb}</span>`}</td>
            </tr>`
          )
          .join("")
      : '<tr><td colspan="4" class="muted">No world rank movements.</td></tr>';

    $("diffTransfersBody").innerHTML = (d.newTransfers || []).length
      ? d.newTransfers
          .map(
            (tx) => `<tr>
              <td class="muted">${escapeHtml(tx.date)}</td>
              <td><strong>${escapeHtml(tx.personName)}</strong></td>
              <td>${escapeHtml(tx.fromTeamName)}</td>
              <td>${escapeHtml(tx.toTeamName)}</td>
              <td class="mono">${studioFmtMoney(tx.purchasePrice)}</td>
            </tr>`
          )
          .join("")
      : '<tr><td colspan="5" class="muted">No new transfers since baseline.</td></tr>';

    const trTags = (d.newTrophies || []).map(
      (x) => `<span class="tag-pill">${escapeHtml(x.year)} Trophy: <strong>${escapeHtml(x.teamName)}</strong> (${escapeHtml(x.tournamentName)})</span>`
    );
    const awTags = (d.newAwards || []).map(
      (a) => `<span class="tag-pill">${escapeHtml(a.date)} ${escapeHtml(a.typeLabel)}${a.top20Placement ? ` #${a.top20Placement}` : ""}: <strong>${escapeHtml(a.playerName)}</strong> (${escapeHtml(a.tournamentName)})</span>`
    );
    $("diffAwardsBody").innerHTML = [...trTags, ...awTags].join(" ") || '<span class="muted">No new trophies or player awards earned since baseline.</span>';
  } catch (err) {
    toast(`Save Diff failed: ${err.message}`, "err");
  }
}

// =========================================================================
// Tournaments Hub & Fair-Award Patcher
// =========================================================================

async function studioLoadTournaments() {
  if (!studioHasSaveLoaded()) return;
  try {
    const res = await api("/api/studio/tournaments");
    studioState.tournaments = res.tournaments || [];
    studioState.awardYears = res.awardYears || [];
    const yrSel = $("tmTop20Year");
    if (yrSel) {
      const yrs = studioState.awardYears.length ? studioState.awardYears : [state.summary?.datetime?.year || 2026];
      const curYr = yrSel.value || String(yrs[0]);
      populateSelect(yrSel, yrs.map((y) => [y, String(y)]), curYr);
    }
    studioRenderTournamentsList();
    const validTid = studioState.selectedTournamentId && studioState.tournaments.some((t) => t.id === studioState.selectedTournamentId);
    if (!validTid) studioState.selectedTournamentId = null;
    if (!studioState.selectedTournamentId && studioState.tournaments.length) {
      const firstPlayed = studioState.tournaments.find((t) => t.matchCount > 0) || studioState.tournaments[0];
      await studioSelectTournament(firstPlayed.id);
    } else if (studioState.selectedTournamentId) {
      await studioSelectTournament(studioState.selectedTournamentId);
    }
  } catch (err) {
    toast(`Tournaments load error: ${err.message}`, "err");
  }
}

function studioRenderTournamentsList() {
  const rows = studioState.tournaments || [];
  const q = ($("tmSearchInput")?.value || "").trim().toLowerCase();
  const mismatchOnly = Boolean($("tmMismatchOnly")?.checked);
  const hideUpcoming = Boolean($("tmHideUpcoming")?.checked);
  const sortBy = $("tmSortBy")?.value || "awards_first";

  const filtered = rows.filter((r) => {
    if (hideUpcoming && ((r.matchCount || 0) === 0 || r.date === "Upcoming")) return false;
    if (mismatchOnly && !r.mvpMismatch) return false;
    if (q && !`${r.name} ${r.championName} ${r.recordedMvpName} ${r.fairMvpName}`.toLowerCase().includes(q)) return false;
    return true;
  });

  filtered.sort((a, b) => {
    const sa = a.awardSlots || {};
    const sb = b.awardSlots || {};
    if (sortBy === "awards_first") {
      return (
        (sb.mvp || 0) - (sa.mvp || 0) ||
        (sb.evp || 0) - (sa.evp || 0) ||
        ((b.hasRecordedAwards ? 1 : 0) - (a.hasRecordedAwards ? 1 : 0)) ||
        (b.reputation || 0) - (a.reputation || 0) ||
        (b.year || 0) - (a.year || 0) ||
        (b.month || 0) - (a.month || 0) ||
        (b.matchCount || 0) - (a.matchCount || 0) ||
        b.id - a.id
      );
    }
    if (sortBy === "mismatch_first") {
      return (
        ((b.mvpMismatch ? 1 : 0) - (a.mvpMismatch ? 1 : 0)) ||
        (sb.mvp || 0) - (sa.mvp || 0) ||
        (sb.evp || 0) - (sa.evp || 0) ||
        (b.reputation || 0) - (a.reputation || 0) ||
        (b.year || 0) - (a.year || 0) ||
        (b.month || 0) - (a.month || 0)
      );
    }
    if (sortBy === "rep_desc") {
      return (
        (b.reputation || 0) - (a.reputation || 0) ||
        (b.year || 0) - (a.year || 0) ||
        (b.month || 0) - (a.month || 0) ||
        (b.matchCount || 0) - (a.matchCount || 0)
      );
    }
    // date_desc
    return (
      (b.year || 0) - (a.year || 0) ||
      (b.month || 0) - (a.month || 0) ||
      (b.reputation || 0) - (a.reputation || 0) ||
      b.id - a.id
    );
  });

  $("tmListCount").textContent = String(filtered.length);
  $("tmTableBody").innerHTML = filtered.length
    ? filtered
        .map((r) => {
          const sl = r.awardSlots || {};
          const slotTag = sl.mvp ? `${sl.mvp}M/${sl.evp || 0}E` : sl.evp ? `${sl.evp}E` : "—";
          return `<tr class="${Number(studioState.selectedTournamentId) === r.id ? "selected" : ""}" data-tid="${r.id}" style="cursor:pointer;">
            <td><strong>${escapeHtml(r.name)}</strong><div class="muted" style="font-size:11px;">${escapeHtml(r.date)} · ${r.matchCount}m</div></td>
            <td class="mono">${r.reputation} <span class="muted" style="font-size:10px;">${escapeHtml(slotTag)}</span></td>
            <td>${escapeHtml(r.championName || "-")}</td>
            <td>${r.recordedMvpName ? escapeHtml(r.recordedMvpName) : '<span class="muted">-</span>'}</td>
            <td>${r.fairMvpName ? `${escapeHtml(r.fairMvpName)} ${r.mvpMismatch ? '<span class="pill pill-warn">Mismatch</span>' : ""}` : '<span class="muted">-</span>'}</td>
          </tr>`;
        })
        .join("")
    : '<tr><td colspan="5" class="muted">No tournaments match filters.</td></tr>';

  $("tmTableBody").querySelectorAll("tr[data-tid]").forEach((tr) => {
    tr.addEventListener("click", () => studioSelectTournament(Number(tr.dataset.tid)));
  });
}

async function studioSelectTournament(tournamentId) {
  studioState.selectedTournamentId = tournamentId;
  studioState.customAwardOrder = [];
  studioRenderTournamentsList();
  try {
    const d = await api(`/api/studio/tournament/${tournamentId}`);
    studioState.selectedTournamentDetail = d;
    const m = d.meta || {};
    const ev = d.event || {};
    const slots = ev.awardSlots || {};
    const players = d.players || [];

    $("tmDetailTitle").textContent = `${m.name || ev.name || `Tournament #${tournamentId}`}`;
    $("tmDetailSubtitle").textContent = `${ev.date || "Upcoming"} · Champion: ${ev.championName || "-"} · Runner-Up: ${ev.runnerUpName || "-"} · Tier: ${ev.tierLabel || "-"}`;
    $("tmEditRep").value = m.reputation ?? 15;
    $("tmEditBo5").checked = Boolean(m.bestOfFiveGrandFinals);
    $("tmEditStickLow").value = m.stickerMoneyLow ?? 0;
    $("tmEditStickHigh").value = m.stickerMoneyHigh ?? 0;

    const recStr = ev.recordedMvp ? `${ev.recordedMvp.playerName} (${ev.recordedMvp.placement || "-"})` : "None";
    const gmStr = ev.gameMvp ? `${ev.gameMvp.playerName} (${Number(ev.gameMvp.score || 0).toFixed(3)}, ${ev.gameMvp.placement || "-"})` : "None";
    const fmStr = ev.fairMvp ? `${ev.fairMvp.playerName} (${Number(ev.fairMvp.score || 0).toFixed(3)}, ${ev.fairMvp.placement || "-"})` : "None";
    $("tmPatchSlotInfo").innerHTML = `<strong>Award Slots for Rep ${m.reputation}:</strong> ${slots.mvp ?? 1} MVP + ${slots.evp ?? 0} EVP${slots.hm ? ` + ${slots.hm} HM` : ""} (${slots.total ?? 1} total saved slots). &bull; <strong>Saved MVP:</strong> ${escapeHtml(recStr)} &bull; <strong>Game MVP:</strong> ${escapeHtml(gmStr)} &bull; <strong>Fair MVP:</strong> ${escapeHtml(fmStr)}`;
    $("tmPatchPreview").innerHTML = "";

    for (const id of ["btnTmRefreshDetail", "btnTmSaveMeta"]) {
      if ($(id)) $(id).disabled = false;
    }
    for (const id of ["btnTmPatchFairDry", "btnTmPatchFairApply", "btnTmPatchCustom"]) {
      if ($(id)) $(id).disabled = players.length === 0;
    }

    const stages = d.stages || [];
    $("tmStagesList").innerHTML = stages.length
      ? stages.map((s) => `<span class="tag-pill">#${s.stage} ${escapeHtml(s.name)} (${s.participants} teams, ${s.matchCount} matches, ${escapeHtml(s.startDate)})</span>`).join(" ")
      : '<span class="muted">No stage records yet.</span>';

    $("tmPlayersTableBody").innerHTML = players.length
      ? players
          .slice(0, 120)
          .map((r) => {
            const rCls = r.rating >= 1.15 ? "stat-good" : r.rating > 0 && r.rating < 0.95 ? "stat-bad" : "";
            const ratTitle = r.ratingSource === "estimated" ? "Estimated fallback (no PCS row yet)" : "Exact rating from save playerCareerStats";
            const deltaStr =
              r.rankDelta === null || r.rankDelta === undefined
                ? `<span class="tag-pill warn">Inelig</span>`
                : r.rankDelta > 0
                  ? `<span class="stat-good">+${r.rankDelta}</span>`
                  : r.rankDelta < 0
                    ? `<span class="stat-bad">${r.rankDelta}</span>`
                    : `<span class="muted">0</span>`;
            const gameScoreStr = r.gameEligible
              ? `<strong>${Number(r.gameScore || 0).toFixed(3)}</strong> ${_awardBadgeHtml(r.gameProjectedAward)}`
              : `<span class="muted">Inelig (9th+)</span>`;
            const breakdown = `Bayes: ${Number(r.bayesRating || 0).toFixed(3)} | Place: ${Number(r.fairPlaceBonus || 0) >= 0 ? "+" : ""}${Number(r.fairPlaceBonus || 0).toFixed(3)} | Opp: ${Number(r.fairOppBonus || 0) >= 0 ? "+" : ""}${Number(r.fairOppBonus || 0).toFixed(3)} | PO: +${Number(r.fairPoBonus || 0).toFixed(3)}`;
            const fairScoreStr = `<strong title="${escapeHtml(breakdown)}">${Number(r.fairScore || 0).toFixed(3)}</strong> ${_awardBadgeHtml(r.fairProjectedAward)}`;
            const savedAwardHtml = r.actualAward ? _awardBadgeHtml(r.actualAward) : '<span class="muted">&mdash;</span>';

            return `<tr>
              <td><input type="checkbox" class="tm-custom-pick" data-pid="${r.playerId}" /></td>
              <td><strong>#${r.fairRank}</strong></td>
              <td>${r.gameRank ? `#${r.gameRank}` : '<span class="muted">&mdash;</span>'}</td>
              <td>${deltaStr}</td>
              <td><strong>${escapeHtml(r.playerName)}</strong></td>
              <td>${escapeHtml(r.teamName)}</td>
              <td>${escapeHtml(r.placement || "-")}</td>
              <td>${r.matches ?? 0} <span class="muted">(${r.wins ?? 0}-${r.losses ?? 0})</span></td>
              <td>${r.maps ?? 0}${r.poMaps ? ` <span class="muted">(${r.poMaps})</span>` : ""}</td>
              <td class="${rCls}" title="${escapeHtml(ratTitle)}"><strong>${Number(r.rating || 0).toFixed(3)}</strong>${r.ratingSource === "estimated" ? "*" : ""}</td>
              <td>${r.avgOppRank !== null && r.avgOppRank !== undefined ? `#${Number(r.avgOppRank).toFixed(1)}` : '<span class="muted">&mdash;</span>'}</td>
              <td>${gameScoreStr}</td>
              <td title="${escapeHtml(breakdown)}">${fairScoreStr}</td>
              <td>${savedAwardHtml}</td>
            </tr>`;
          })
          .join("")
      : '<tr><td colspan="14" class="muted">No match player stats recorded yet for this event.</td></tr>';

    $("tmPlayersTableBody").querySelectorAll(".tm-custom-pick").forEach((cb) => {
      cb.addEventListener("change", () => {
        const pid = Number(cb.dataset.pid);
        if (cb.checked) {
          if (!studioState.customAwardOrder.includes(pid)) studioState.customAwardOrder.push(pid);
        } else {
          studioState.customAwardOrder = studioState.customAwardOrder.filter((x) => x !== pid);
        }
      });
    });
  } catch (err) {
    toast(`Failed loading tournament #${tournamentId}: ${err.message}`, "err");
  }
}

async function studioPatchSingleTournament(mode, dryRun) {
  if (!studioState.selectedTournamentId) return;
  if (mode === "custom" && !studioState.customAwardOrder.length) {
    toast("Check 1 or more players in the leaderboard first (checked order = MVP then EVPs).", "err");
    return;
  }
  try {
    const res = await api(`/api/studio/tournament/${studioState.selectedTournamentId}/patch-awards`, {
      method: "POST",
      body: JSON.stringify({
        mode,
        customPlayerIds: studioState.customAwardOrder,
        dryRun,
      }),
    });
    const oldTxt = (res.oldAwards || []).map((x) => `${x.playerName} (${x.role})`).join(", ") || "None";
    const newTxt = (res.newAwards || []).map((x) => `${x.playerName} (${x.role})`).join(", ") || "None";
    $("tmPatchPreview").innerHTML = `
      <div class="verdict-banner">
        <strong>${dryRun ? "Dry-Run Preview" : "Applied"}</strong> (${res.changed ? "Changes detected" : "Already matches"})<br/>
        <strong>Old:</strong> ${escapeHtml(oldTxt)}<br/>
        <strong>New:</strong> ${escapeHtml(newTxt)}
      </div>
    `;
    if (!dryRun) {
      await refreshSummaryOnly();
      await studioLoadTournaments();
      toast(`Patched awards for ${res.tournamentName}`, "ok");
    } else {
      toast("Previewed tournament award patch.", "info");
    }
  } catch (err) {
    toast(`Award patch failed: ${err.message}`, "err");
  }
}

async function studioRunTop20Action(year, mode, votePlayerId = 0, outputEl = null) {
  if (!studioHasSaveLoaded()) return toast("Load a save file first.", "err");
  const yr = Number(year || state.summary?.datetime?.year || 2026);
  try {
    const preview = await api("/api/studio/top20/apply", {
      method: "POST",
      body: JSON.stringify({ year: yr, mode, votePlayerId, dryRun: true }),
    });
    const promptMsg =
      mode === "clear"
        ? `Reset / Clear all ${preview.oldCount} Top 20 awards and remove the ${yr} CSTV Top 20 result email?\n\n(An Undo Snapshot will be saved automatically before applying.)`
        : `Recalculate & Save ${yr} Top 20 using current save MVPs/EVPs & ratings?\nTop 3 projected: ${(preview.newTop20 || []).slice(0, 3).map((x) => `#${x.rank} ${x.name}`).join(", ") || "none"}\n(Previous count: ${preview.oldCount} -> New count: ${preview.newCount}. Undo Snapshot created automatically.)`;
    if (!confirm(promptMsg)) return;

    const res = await api("/api/studio/top20/apply", {
      method: "POST",
      body: JSON.stringify({ year: yr, mode, votePlayerId, dryRun: false }),
    });
    const top5Txt = (res.newTop20 || []).slice(0, 5).map((x) => `#${x.rank} ${x.name}`).join(", ");
    const msg =
      mode === "clear"
        ? `Cleared ${res.oldCount} Top 20 award(s) for ${res.year} (removed ${res.emailsRemoved} CSTV email(s)).`
        : `Recalculated ${res.year} Top 20 (${res.newCount} players; ${res.emailsUpdated} CSTV email(s) synced): ${top5Txt || "none"}.`;

    await refreshSummaryOnly();
    state.statsData = null;
    if (state.activeTab === "stats" && typeof loadStatsOverview === "function") {
      await loadStatsOverview();
    }
    if (state.activeTab === "tournaments") {
      await studioLoadTournaments();
    }
    if (state.selectedPlayerId && typeof openPlayerEditor === "function") {
      await openPlayerEditor(state.selectedPlayerId);
    }
    if (outputEl) {
      outputEl.innerHTML = `<div class="verdict-banner ok"><strong>${mode === "clear" ? "Top 20 Reset" : "Top 20 Recalculated"}:</strong> ${escapeHtml(msg)}</div>`;
    }
    toast(msg, "ok");
  } catch (err) {
    toast(`Top 20 update failed: ${err.message}`, "err");
  }
}

// =========================================================================
// Studio Labs: Sandbox, Growth Lab, Market Radar, Weapon Meta Lab
// =========================================================================

async function studioInitSandbox() {
  if (!studioHasSaveLoaded()) return;
  const teams = state.teams || [];
  if (!$("sbTeamSelect").options.length || $("sbTeamSelect").options.length !== teams.length) {
    const uTid = teams.find((t) => t.isUserTeam)?.id ?? teams[0]?.id ?? "";
    const oppTid = teams.find((t) => !t.isUserTeam)?.id ?? teams[1]?.id ?? teams[0]?.id ?? "";
    populateSelect(
      $("sbTeamSelect"),
      teams.map((t) => [t.id, `${t.worldRank ? `#${t.worldRank} ` : ""}${t.name}${t.isUserTeam ? " ★" : ""}`]),
      $("sbTeamSelect").value || uTid
    );
    populateSelect(
      $("sbVsTeamSelect"),
      teams.map((t) => [t.id, `${t.worldRank ? `#${t.worldRank} ` : ""}${t.name}`]),
      $("sbVsTeamSelect").value || oppTid
    );
  }
  try {
    const res = await api("/api/players?limit=500");
    studioState.sandboxPool = res.items || res.players || [];
    const poolIds = new Set(studioState.sandboxPool.map((p) => p.id));
    studioState.sandboxSelectedIds = studioState.sandboxSelectedIds.filter((pid) => poolIds.has(pid));
    studioRenderSandboxSelection();
    studioRenderSandboxPool();
    if (!studioState.sandboxSelectedIds.length && $("sbTeamSelect").value) {
      await studioLoadTeamIntoSandbox();
    }
  } catch (err) {
    toast(`Sandbox init error: ${err.message}`, "err");
  }
}

async function studioLoadTeamIntoSandbox() {
  const tid = Number($("sbTeamSelect").value || 0);
  if (!tid) return;
  try {
    const d = await api(`/api/team/${tid}`);
    const starters = (d.roster || []).filter((r) => !r.benched).slice(0, 5).map((r) => r.playerId);
    studioState.sandboxSelectedIds = starters;
    studioRenderSandboxSelection();
    studioRenderSandboxPool();
    if (starters.length) await studioRunSandboxSimulation();
  } catch (err) {
    toast(`Failed loading team into sandbox: ${err.message}`, "err");
  }
}

function studioRenderSandboxSelection() {
  const poolById = Object.fromEntries((studioState.sandboxPool || []).map((p) => [p.id, p]));
  $("sbSelectedCount").textContent = String(studioState.sandboxSelectedIds.length);
  $("sbSelectedSlots").innerHTML = studioState.sandboxSelectedIds.length
    ? studioState.sandboxSelectedIds
        .map((pid) => {
          const p = poolById[pid];
          return `<button type="button" class="btn btn-sm btn-success sb-remove-slot" data-pid="${pid}">${escapeHtml(p ? p.name : `#${pid}`)} &times;</button>`;
        })
        .join("")
    : '<span class="muted" style="font-size:12px;">Click players below to add up to 5 starters.</span>';

  $("sbSelectedSlots").querySelectorAll(".sb-remove-slot").forEach((btn) => {
    btn.addEventListener("click", () => {
      const pid = Number(btn.dataset.pid);
      studioState.sandboxSelectedIds = studioState.sandboxSelectedIds.filter((x) => x !== pid);
      studioRenderSandboxSelection();
      studioRenderSandboxPool();
    });
  });
}

function studioRenderSandboxPool() {
  const pool = studioState.sandboxPool || [];
  const q = ($("sbPlayerSearch")?.value || "").trim().toLowerCase();
  const filtered = q
    ? pool.filter((p) => `${p.name} ${p.teamName || ""}`.toLowerCase().includes(q))
    : pool;
  const shown = filtered.slice(0, 140);
  $("sbPoolList").innerHTML = shown.length
    ? shown
        .map((p) => {
          const picked = studioState.sandboxSelectedIds.includes(p.id);
          return `
            <div class="pick-item ${picked ? "picked" : ""}" data-pid="${p.id}">
              <div>
                <strong>${escapeHtml(p.name)}</strong> <span class="muted">(${p.age}y)</span>
                <div class="muted">${escapeHtml(p.teamName || "Free Agent")}</div>
              </div>
              <span class="mono">${p.avgSkill} avg</span>
            </div>
          `;
        })
        .join("")
    : '<div class="muted" style="padding:10px;">No players match filter.</div>';

  $("sbPoolList").querySelectorAll(".pick-item").forEach((el) => {
    el.addEventListener("click", () => {
      const pid = Number(el.dataset.pid);
      if (studioState.sandboxSelectedIds.includes(pid)) {
        studioState.sandboxSelectedIds = studioState.sandboxSelectedIds.filter((x) => x !== pid);
      } else if (studioState.sandboxSelectedIds.length >= 5) {
        toast("Lineup already has 5 starters — remove one first.", "err");
        return;
      } else {
        studioState.sandboxSelectedIds.push(pid);
      }
      studioRenderSandboxSelection();
      studioRenderSandboxPool();
    });
  });
}

async function studioRunSandboxSimulation() {
  const teamId = Number($("sbTeamSelect").value || 0);
  const vsTeamId = Number($("sbVsTeamSelect").value || 0);
  if (!teamId || !studioState.sandboxSelectedIds.length) {
    toast("Pick target team and at least 1 starter.", "err");
    return;
  }
  try {
    const res = await api("/api/studio/sandbox/simulate", {
      method: "POST",
      body: JSON.stringify({
        teamId,
        playerIds: studioState.sandboxSelectedIds,
        vsTeamId,
      }),
    });
    const base = res.baseline || {};
    const sim = res.simulated || {};
    const opp = res.vsOpponent;
    $("sbKpiGrid").innerHTML = [
      { label: "Simulated Avg", val: sim.avgSkill ?? 0, sub: `Base: ${base.avgSkill ?? 0} (${res.skillDiff >= 0 ? "+" : ""}${res.skillDiff})` },
      { label: "Top-10 Bo3 Win%", val: `${res.simTop10Bo3Pct}%`, sub: `Current 5: ${res.baseTop10Bo3Pct}%` },
      { label: opp ? `vs ${opp.teamName} (Bo3)` : "vs Opponent", val: opp ? `${opp.bo3Pct}%` : "-", sub: opp ? `Bo1: ${opp.bo1Pct}% · Bo5: ${opp.bo5Pct}%` : "" },
      { label: "Salary Delta / yr", val: studioFmtMoney(res.salaryDiff), sub: `Total: ${studioFmtMoney(sim.totalSalary)}` },
    ]
      .map(
        (k) => `<div class="kpi-card"><div class="kpi-label">${escapeHtml(k.label)}</div><div class="kpi-val">${escapeHtml(k.val)}</div><div class="kpi-sub">${escapeHtml(k.sub)}</div></div>`
      )
      .join("");

    const comms = res.comms || {};
    const chem = res.chemistry || {};
    const roles = res.roles || {};
    $("sbSimBanner").innerHTML = `<strong>${escapeHtml(res.teamName)}:</strong> Mech <strong>${sim.mechAvg}</strong> · Weap <strong>${sim.weaponAvg}</strong> · Mental <strong>${sim.mentalAvg}</strong> · Avg Age <strong>${sim.avgAge}</strong>`;

    const warns = (roles.warnings || []).map((w) => `<div class="warn-banner"><strong>Warning:</strong> ${escapeHtml(w)}</div>`).join("");
    const shared = (comms.sharedLanguages || []).join(", ") || "None (100% fluent)";
    const missing = (comms.missingFluency || []).join(", ") || "None";
    $("sbCommsWarnings").innerHTML = `
      ${warns}
      <div style="font-size:12px;margin-top:6px;">
        <span class="pill pill-cyan">Best Language: ${escapeHtml(comms.bestLanguage)} (${comms.bestLanguageCoverage}/${(sim.players || []).length})</span>
        <span class="pill pill-ok">Shared 100%: ${escapeHtml(shared)}</span>
        ${comms.missingFluency?.length ? `<span class="pill pill-bad">Needs Tutoring: ${escapeHtml(missing)}</span>` : ""}
        ${chem.friends?.length ? `<span class="pill pill-purple">Bonds: ${escapeHtml(chem.friends.join("; "))}</span>` : ""}
      </div>
    `;

    $("sbMapPoolBars").innerHTML = (res.mapPool || [])
      .map(
        (m) => `<div class="bar-row">
          <div class="bar-head">
            <span><strong>${escapeHtml(m.mapName)}</strong> (${m.likes} likes)</span>
            <span class="mono">${m.comfort}/10${m.oppComfort !== null ? ` vs ${m.oppComfort}/10` : ""}</span>
          </div>
          <div class="bar-track"><div class="bar-fill" style="width:${Math.min(100, m.comfort * 10)}%;"></div></div>
        </div>`
      )
      .join("");

    $("sbSimRosterBody").innerHTML = (sim.players || [])
      .map(
        (r) => `<tr>
          <td><strong>${escapeHtml(r.name)}</strong><div class="muted" style="font-size:11px;">${escapeHtml(r.teamName)}</div></td>
          <td class="mono">${r.age}</td>
          <td class="mono">${r.practicalAvg}</td>
          <td class="muted">${escapeHtml((r.languages || []).join(", "))}</td>
          <td class="mono">${studioFmtMoney(r.salaryYear)}</td>
          <td class="mono">${r.desireToIgl}/${r.desireToAwp}</td>
        </tr>`
      )
      .join("");
  } catch (err) {
    toast(`Simulation failed: ${err.message}`, "err");
  }
}

async function studioLoadGrowthLab() {
  if (!studioHasSaveLoaded()) return;
  const minM = Number($("grMinMonths")?.value || 2);
  try {
    const d = await api(`/api/studio/growth?min_months=${minM}`);
    studioState.growthData = d;
    if (!d.loaded) return;

    const spanTxt = d.monthsSpan?.length ? `${d.monthsSpan[0]} .. ${d.monthsSpan[d.monthsSpan.length - 1]}` : "No history";
    $("grKpiGrid").innerHTML = [
      { label: "Total Players", val: d.totalPlayers, sub: "In active save" },
      { label: "Tracked (>=Min Months)", val: d.trackedCount, sub: spanTxt },
      { label: "Top Riser", val: d.risers?.[0]?.name || "-", sub: d.risers?.[0] ? `+${d.risers[0].overallDelta}` : "" },
      { label: "Wonderkid #1 (U-20)", val: d.wonderkids?.[0]?.name || "-", sub: d.wonderkids?.[0] ? `${d.wonderkids[0].currentAvg} avg` : "" },
    ]
      .map(
        (k) => `<div class="kpi-card"><div class="kpi-label">${escapeHtml(k.label)}</div><div class="kpi-val">${escapeHtml(k.val)}</div><div class="kpi-sub">${escapeHtml(k.sub)}</div></div>`
      )
      .join("");

    const renderGrowthRows = (rows, cols) =>
      rows && rows.length
        ? rows
            .map(
              (r) => `<tr class="gr-player-row" data-pid="${r.playerId}" style="cursor:pointer;">
                <td><strong>${escapeHtml(r.name)}</strong></td>
                <td class="mono">${r.age}</td>
                <td>${escapeHtml(r.teamName)}</td>
                ${cols(r)}
              </tr>`
            )
            .join("")
        : '<tr><td colspan="6" class="muted">No data.</td></tr>';

    $("grRisersBody").innerHTML = renderGrowthRows(d.risers, (r) => `<td class="mono">${r.startOverall}</td><td class="mono">${r.endOverall}</td><td class="mono">${studioFmtDelta(r.overallDelta)}</td>`);
    $("grDeclinersBody").innerHTML = renderGrowthRows(d.decliners, (r) => `<td class="mono">${r.startOverall}</td><td class="mono">${r.endOverall}</td><td class="mono">${studioFmtDelta(r.overallDelta)}</td>`);
    $("grWonderkidsBody").innerHTML = renderGrowthRows(d.wonderkids, (r) => `<td class="mono">${r.currentAvg}</td><td class="mono">${r.potentialAvg}</td><td class="mono">${r.startingPotential || "-"}</td>`);
    $("grCeilingBody").innerHTML = renderGrowthRows(d.untappedCeiling, (r) => `<td class="mono">${r.currentAvg}</td><td class="mono">${r.potentialAvg}</td><td class="mono"><span class="delta-up">+${r.ceilingGap}</span></td>`);

    document.querySelectorAll(".gr-player-row").forEach((tr) => {
      tr.addEventListener("click", () => studioLoadPlayerTrajectory(Number(tr.dataset.pid)));
    });
    if (d.risers?.[0]) {
      await studioLoadPlayerTrajectory(d.risers[0].playerId);
    }
  } catch (err) {
    toast(`Growth Lab failed: ${err.message}`, "err");
  }
}

async function studioLoadPlayerTrajectory(playerId) {
  try {
    const t = await api(`/api/studio/growth/player/${playerId}`);
    $("grTrajectoryTitle").textContent = `${t.name} (${t.age}y) — ${t.teamName}`;
    $("grTrajectoryMeta").textContent = `Current: ${t.currentAvg} · Potential: ${t.potentialAvg} · ${(t.series || []).length} monthly points`;
    $("grTrajectoryChart").innerHTML = studioBuildTrajectorySvg(t.series || []);
  } catch (err) {
    toast(`Failed loading trajectory: ${err.message}`, "err");
  }
}

async function studioLoadMarketRadar() {
  if (!studioHasSaveLoaded()) return;
  try {
    const d = await api("/api/studio/market-radar");
    studioState.marketRadar = d;
    if (!d.loaded) return;
    const s = d.summary || {};
    $("mrKpiGrid").innerHTML = [
      { label: "Total Interest Rows", val: s.totalInterestRows ?? 0, sub: "Across all clubs" },
      { label: "Hunted Players", val: s.huntedPlayers ?? 0, sub: "Distinct players targeted" },
      { label: "Active Bids", val: s.activeBids ?? 0, sub: "Status 1-6 live negotiations" },
      { label: "Cooldown Locks", val: s.cooldownRows ?? 0, sub: "Status 7/8" },
      { label: "Policy Violations", val: s.policyViolations ?? 0, sub: "Nationality / Language mismatch" },
    ]
      .map(
        (k) => `<div class="kpi-card"><div class="kpi-label">${escapeHtml(k.label)}</div><div class="kpi-val">${escapeHtml(k.val)}</div><div class="kpi-sub">${escapeHtml(k.sub)}</div></div>`
      )
      .join("");
    studioRenderMarketTables();
  } catch (err) {
    toast(`Market Radar failed: ${err.message}`, "err");
  }
}

function studioRenderMarketTables() {
  const d = studioState.marketRadar;
  if (!d) return;
  const q = ($("mrSearchInput")?.value || "").trim().toLowerCase();
  const polOnly = Boolean($("mrPolicyOnly")?.checked);

  const swarms = (d.vultureSwarms || []).filter((r) => {
    if (polOnly && r.policyMismatches === 0) return false;
    if (q && !`${r.playerName} ${r.teamName} ${(r.clubs || []).map((c) => c.teamName).join(" ")}`.toLowerCase().includes(q)) return false;
    return true;
  });
  $("mrSwarmsBody").innerHTML = swarms.length
    ? swarms
        .map(
          (r) => `<tr>
            <td><strong>${escapeHtml(r.playerName)}</strong></td>
            <td class="mono">${r.age}</td>
            <td class="mono">${r.avgSkill}</td>
            <td>${escapeHtml(r.teamName)}</td>
            <td class="mono">${r.distinctClubs}</td>
            <td class="mono">${r.activeBids}</td>
            <td class="mono">${r.cooldowns}</td>
            <td>${r.policyMismatches ? `<span class="pill pill-bad">${r.policyMismatches}</span>` : '<span class="muted">0</span>'}</td>
            <td><button type="button" class="btn btn-sm mr-clear-p-cd" data-pid="${r.playerId}">Clear Cooldowns</button></td>
          </tr>`
        )
        .join("")
    : '<tr><td colspan="9" class="muted">No hunted players match filter.</td></tr>';

  const bids = (d.activeBids || []).filter((b) => {
    if (polOnly && !b.violatesPolicy) return false;
    if (q && !`${b.bidderName} ${b.playerName} ${b.fromTeamName}`.toLowerCase().includes(q)) return false;
    return true;
  });
  $("mrActiveBidsBody").innerHTML = bids.length
    ? bids
        .map(
          (b) => `<tr>
            <td><strong>${escapeHtml(b.bidderName)}</strong></td>
            <td>${escapeHtml(b.playerName)}</td>
            <td class="muted">${escapeHtml(b.fromTeamName)}</td>
            <td><span class="pill pill-blue">${escapeHtml(b.statusLabel)}</span></td>
            <td class="mono">${Number(b.score || 0).toFixed(1)}</td>
            <td>${b.violatesPolicy ? `<span class="pill pill-bad" title="${escapeHtml(b.violationReason)}">Bad</span>` : '<span class="pill pill-ok">OK</span>'}</td>
            <td><button type="button" class="btn btn-sm btn-danger mr-cancel-bid" data-tid="${b.bidderId}" data-pid="${b.playerId}">Cancel</button></td>
          </tr>`
        )
        .join("")
    : '<tr><td colspan="7" class="muted">No active bids match filter.</td></tr>';

  const clubs = (d.clubActivity || []).filter((c) => {
    if (polOnly && c.policyViolations === 0) return false;
    if (q && !`${c.teamName}`.toLowerCase().includes(q)) return false;
    return true;
  });
  $("mrClubsBody").innerHTML = clubs.length
    ? clubs
        .map(
          (c) => `<tr>
            <td><strong>${escapeHtml(c.teamName)}</strong></td>
            <td class="mono">${c.totalInterests}</td>
            <td class="mono">${c.activeBids}</td>
            <td class="mono">${c.cooldowns}</td>
            <td>${c.policyViolations ? `<span class="pill pill-bad">${c.policyViolations}</span>` : '<span class="muted">0</span>'}</td>
            <td><button type="button" class="btn btn-sm mr-clear-t-cd" data-tid="${c.teamId}">Clear Club CDs</button></td>
          </tr>`
        )
        .join("")
    : '<tr><td colspan="6" class="muted">No club activity matches filter.</td></tr>';

  $("mrSwarmsBody").querySelectorAll(".mr-clear-p-cd").forEach((b) =>
    b.addEventListener("click", () => studioMarketAction("clear_player_cooldowns", Number(b.dataset.pid), 0))
  );
  $("mrActiveBidsBody").querySelectorAll(".mr-cancel-bid").forEach((b) =>
    b.addEventListener("click", () => studioMarketAction("cancel_bid", Number(b.dataset.pid), Number(b.dataset.tid)))
  );
  $("mrClubsBody").querySelectorAll(".mr-clear-t-cd").forEach((b) =>
    b.addEventListener("click", () => studioMarketAction("clear_team_cooldowns", 0, Number(b.dataset.tid)))
  );
}

async function studioMarketAction(mode, playerId = 0, teamId = 0) {
  try {
    const res = await api("/api/studio/market-radar/action", {
      method: "POST",
      body: JSON.stringify({ mode, playerId, teamId }),
    });
    studioState.marketRadar = res.radar;
    studioRenderMarketTables();
    await studioLoadMarketRadar();
    await refreshSummaryOnly();
    toast(`Market action removed ${res.removedCount} interest row(s)`, "ok");
  } catch (err) {
    toast(`Market action failed: ${err.message}`, "err");
  }
}

async function studioLoadWeaponsLab() {
  if (!studioHasSaveLoaded()) return;
  try {
    const d = await api("/api/studio/weapons");
    studioState.weaponsData = d.weapons || [];
    studioRenderWeaponsTable();
    const validWid = studioState.selectedWeaponId && studioState.weaponsData.some((w) => w.id === studioState.selectedWeaponId);
    if (!validWid) studioState.selectedWeaponId = null;
    if (!studioState.selectedWeaponId && studioState.weaponsData.length) {
      studioSelectWeapon(studioState.weaponsData[0].id);
    } else if (studioState.selectedWeaponId) {
      studioSelectWeapon(studioState.selectedWeaponId);
    }
  } catch (err) {
    toast(`Weapons Lab error: ${err.message}`, "err");
  }
}

function studioRenderWeaponsTable() {
  const list = studioState.weaponsData || [];
  const wType = $("wpTypeFilter")?.value ?? "";
  const q = ($("wpSearchInput")?.value || "").trim().toLowerCase();
  const filtered = list.filter((w) => {
    if (wType !== "" && String(w.type) !== String(wType)) return false;
    if (q && !`${w.name} ${w.typeLabel}`.toLowerCase().includes(q)) return false;
    return true;
  });
  $("wpTableBody").innerHTML = filtered.length
    ? filtered
        .map(
          (w) => `<tr class="${Number(studioState.selectedWeaponId) === w.id ? "selected" : ""}" data-wid="${w.id}" style="cursor:pointer;">
            <td><strong>${escapeHtml(w.name)}</strong></td>
            <td><span class="pill pill-blue">${escapeHtml(w.typeLabel)}</span></td>
            <td class="mono">$${w.price}</td>
            <td class="mono">${w.damage}</td>
            <td class="mono">$${w.killReward}</td>
            <td class="mono">${w.shotsToKillBody}</td>
            <td class="mono">${w.armoredHsDmg}</td>
          </tr>`
        )
        .join("")
    : '<tr><td colspan="7" class="muted">No weapons match filters.</td></tr>';

  $("wpTableBody").querySelectorAll("tr[data-wid]").forEach((tr) => {
    tr.addEventListener("click", () => studioSelectWeapon(Number(tr.dataset.wid)));
  });
}

function studioSelectWeapon(weaponId) {
  const w = (studioState.weaponsData || []).find((x) => x.id === weaponId);
  if (!w) return;
  studioState.selectedWeaponId = weaponId;
  studioRenderWeaponsTable();
  $("wpEditorTitle").textContent = `Edit Weapon: ${w.name} (${w.typeLabel})`;
  $("btnWpSaveWeapon").disabled = false;
  $("wpComputedStats").innerHTML = `<strong>Computed Combat Profile:</strong> ${w.rpm} RPM · Armored Body: <strong>${w.armoredBodyDmg} dmg</strong> (${w.shotsToKillBody} shots to kill) · Armored Headshot: <strong>${w.armoredHsDmg} dmg</strong>`;

  $("wpPrice").value = w.price;
  $("wpDamage").value = w.damage;
  $("wpAmmo").value = w.ammo;
  $("wpKillReward").value = w.killReward;
  $("wpReloadTime").value = w.reloadTime;
  $("wpTier").value = w.tier;
  $("wpHsMult").value = w.hsMultiplier;
  $("wpArmorMult").value = w.armorMultiplier;
  $("wpAccuracy").value = w.accuracy;
  $("wpMovePenalty").value = w.movingAccuracyPenalty;
  $("wpRecoilInc").value = w.recoilIncreasePerShot;
  $("wpRecoilReset").value = w.recoilResetTime;
  $("wpShotInterval").value = w.shotInterval;
  $("wpDropOff").value = w.damageDropOffPerUnitOfDistance;
}

async function studioApplyWeaponPreset(preset) {
  try {
    const res = await api("/api/studio/weapons/preset", {
      method: "POST",
      body: JSON.stringify({ preset }),
    });
    studioState.weaponsData = res.weapons || [];
    studioRenderWeaponsTable();
    if (studioState.selectedWeaponId) studioSelectWeapon(studioState.selectedWeaponId);
    await refreshSummaryOnly();
    toast(`Applied '${preset}' preset (${res.updatedCount} weapon(s) tuned)`, "ok");
  } catch (err) {
    toast(`Preset failed: ${err.message}`, "err");
  }
}

// =========================================================================
// Inline Player Pro & Team Pro Extras
// =========================================================================

window.studioRenderPlayerPro = function studioRenderPlayerPro(p, data) {
  const container = $("playerProExtras");
  const pro = data?.pro;
  if (!container || !pro) return;

  const tmpls = pro.tournamentTemplates || [];
  const tmplOpts = tmpls.map((t) => `<option value="${t.id}">${escapeHtml(t.name)}</option>`).join("");
  const awTypeOpts = enumEntries(state.meta?.awardTypes || { 0: "MVP", 1: "Event Win", 2: "EVP", 3: "Top 20" })
    .map(([k, v]) => `<option value="${k}">${escapeHtml(v)}</option>`)
    .join("");
  const teamOpts = (state.teams || [])
    .map((t) => `<option value="${t.id}" ${t.id === (data.contract?.teamId || 0) ? "selected" : ""}>${escapeHtml(t.name)}</option>`)
    .join("");

  const awardsHtml = (pro.awards || []).length
    ? (pro.awards || [])
        .map(
          (a) => `<tr>
            <td><span class="pill ${a.type === 0 ? "pill-warn" : a.type === 2 ? "pill-blue" : "pill-ok"}">${escapeHtml(a.typeLabel)}${a.top20Placement ? ` #${a.top20Placement}` : ""}</span></td>
            <td>${escapeHtml(a.tournamentName)}</td>
            <td class="mono">${a.year}-${String(a.month || 1).padStart(2, "0")}</td>
            <td>${escapeHtml(a.teamName)}</td>
            <td><button type="button" class="btn btn-sm btn-danger p-pro-del-aw" data-idx="${a.index}">Del</button></td>
          </tr>`
        )
        .join("")
    : '<tr><td colspan="5" class="muted">No career awards recorded.</td></tr>';

  container.innerHTML = `
    <div class="subcard">
      <div class="subcard-title" style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;">
        <span>Player Pro: Wellness &amp; Starting Potential</span>
        <button type="button" class="btn btn-sm btn-success" id="btnPProHeal">Zero Burnout &amp; Max Mood</button>
      </div>
      <div style="margin-bottom:8px;display:flex;gap:6px;flex-wrap:wrap;">
        <span class="pill pill-cyan">Mood Score: ${Number(pro.moodScore ?? 0).toFixed(2)}</span>
        <span class="pill ${pro.totalBurnout > 0.3 ? "pill-bad" : "pill-ok"}">Total Burnout: ${Number(pro.totalBurnout ?? 0).toFixed(2)}</span>
        <span class="pill pill-purple">Practical Avg: ${Number(pro.practicalAvg ?? 0).toFixed(2)}</span>
        <span class="pill pill-blue">Potential Avg: ${Number(pro.potentialAvg ?? 0).toFixed(2)}</span>
      </div>
      <div class="form-grid">
        <div class="field">
          <label>Starting Potential Toggle</label>
          <label class="checkbox-row" style="margin-top:6px;">
            <input id="pUseStartPot" type="checkbox" ${pro.useStartingPotential ? "checked" : ""} />
            <span>Use Starting Potential</span>
          </label>
        </div>
        <div class="field"><label>Starting Potential (50-275)</label><input id="pStartPot" type="number" min="50" max="275" value="${pro.startingPotential}" /></div>
        <div class="field"><label>Burnout Practice (0-1)</label><input id="pBurnPrac" type="number" min="0" max="1" step="0.02" value="${Number(pro.burnout?.burnoutFromPractice ?? 0).toFixed(2)}" /></div>
        <div class="field"><label>Burnout Matches (0-1)</label><input id="pBurnMatch" type="number" min="0" max="1" step="0.02" value="${Number(pro.burnout?.burnoutFromMatches ?? 0).toFixed(2)}" /></div>
      </div>
    </div>

    <div class="subcard">
      <div class="subcard-title">Monthly Skill Trajectory (${(pro.skillHistory || []).length} pts)</div>
      <div class="chart-box">${studioBuildTrajectorySvg(pro.skillHistory || [])}</div>
    </div>

    <div class="subcard">
      <div class="subcard-title">Career Awards &amp; Top-20 CRUD (${(pro.awards || []).length})</div>
      <div class="table-wrap" style="max-height:200px;margin-bottom:8px;">
        <table>
          <thead><tr><th>Award</th><th>Event</th><th>Date</th><th>Team</th><th></th></tr></thead>
          <tbody>${awardsHtml}</tbody>
        </table>
      </div>
      <div class="form-grid">
        <div class="field"><label>Type</label><select id="pProAwType">${awTypeOpts}</select></div>
        <div class="field"><label>Tournament Template</label><select id="pProAwTmpl"><option value="0">-- None / Annual --</option>${tmplOpts}</select></div>
        <div class="field"><label>Year</label><input id="pProAwYear" type="number" min="2012" max="2100" value="${state.summary?.datetime?.year || 2026}" /></div>
        <div class="field"><label>Month</label><input id="pProAwMonth" type="number" min="1" max="12" value="${state.summary?.datetime?.month || 1}" /></div>
        <div class="field"><label>Team</label><select id="pProAwTeam"><option value="0">-- Free / Any --</option>${teamOpts}</select></div>
        <div class="field"><label>Top-20 # (Type=3)</label><input id="pProAwTop20" type="number" min="0" max="20" value="0" /></div>
      </div>
      <div class="inline-actions" style="margin-top:8px;">
        <button type="button" class="btn btn-sm btn-primary" id="btnPProAddAward">+ Add Career Award</button>
      </div>
    </div>
  `;

  $("btnPProHeal").addEventListener("click", async () => {
    try {
      const updated = await api(`/api/studio/player/${p.id}/heal`, {
        method: "POST",
        body: JSON.stringify({ resetBurnout: true, maxMood: true }),
      });
      state.selectedPlayerData = updated;
      await refreshSummaryOnly();
      await openPlayerEditor(p.id);
      toast(`Healed burnout & maxed mood for ${p.name}`, "ok");
    } catch (err) {
      toast(`Heal failed: ${err.message}`, "err");
    }
  });

  $("btnPProAddAward").addEventListener("click", async () => {
    try {
      const updated = await api(`/api/studio/player/${p.id}/award/add`, {
        method: "POST",
        body: JSON.stringify({
          type: Number($("pProAwType").value || 0),
          tournamentTemplate: Number($("pProAwTmpl").value || 0),
          year: Number($("pProAwYear").value || 2026),
          month: Number($("pProAwMonth").value || 1),
          teamId: Number($("pProAwTeam").value || 0),
          top20Placement: Number($("pProAwTop20").value || 0),
        }),
      });
      state.selectedPlayerData = updated;
      await refreshSummaryOnly();
      await openPlayerEditor(p.id);
      toast(`Added career award to ${p.name}`, "ok");
    } catch (err) {
      toast(`Add award failed: ${err.message}`, "err");
    }
  });

  container.querySelectorAll(".p-pro-del-aw").forEach((btn) => {
    btn.addEventListener("click", async () => {
      try {
        const updated = await api(`/api/studio/player/${p.id}/award/delete`, {
          method: "POST",
          body: JSON.stringify({ index: Number(btn.dataset.idx) }),
        });
        state.selectedPlayerData = updated;
        await refreshSummaryOnly();
        await openPlayerEditor(p.id);
        toast("Deleted award entry.", "ok");
      } catch (err) {
        toast(`Delete failed: ${err.message}`, "err");
      }
    });
  });
};

window.studioRenderTeamPro = function studioRenderTeamPro(data) {
  const container = $("teamProExtras");
  const pro = data?.pro;
  const t = data?.team;
  if (!container || !pro || !t) return;

  const sh = pro.squadHealth || {};
  const sponsors = pro.sponsors || [];
  const cat = pro.sponsorCatalog || [];
  const catOpts = cat.map((c) => `<option value="${c.id}">${escapeHtml(c.name)} (Rep ${c.reputation} · ${studioFmtMoney(c.fixedMonthlyContribution)}/mo)</option>`).join("");

  const spRows = sponsors.length
    ? sponsors
        .map(
          (sp, idx) => `<tr data-idx="${idx}">
            <td><strong>${escapeHtml(sp.name || `Sponsor #${sp.id}`)}</strong> <span class="muted">(Slot ${sp.slot ?? idx + 1})</span></td>
            <td><input type="number" class="t-sp-mo" value="${sp.fixedMonthlyContribution ?? 0}" style="width:105px;" /></td>
            <td><input type="number" class="t-sp-bon" value="${sp.bonusPayout ?? 0}" style="width:105px;" /></td>
            <td><input type="number" class="t-sp-yr" value="${sp.dealLength?.year ?? 2027}" style="width:72px;" /></td>
            <td class="inline-actions">
              <button type="button" class="btn btn-sm btn-blue t-sp-save" data-idx="${idx}">Save</button>
              <button type="button" class="btn btn-sm btn-danger t-sp-del" data-idx="${idx}">Del</button>
            </td>
          </tr>`
        )
        .join("")
    : '<tr><td colspan="5" class="muted">No active sponsor deals.</td></tr>';

  container.innerHTML = `
    <div class="subcard">
      <div class="subcard-title" style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;">
        <span>Org Pro: Squad Wellness, Transfer Bids &amp; World Rank Trend</span>
        <div class="inline-actions">
          <button type="button" class="btn btn-sm btn-success" id="btnTProHealSquad">Heal Squad Mood &amp; Burnout</button>
          <button type="button" class="btn btn-sm btn-blue" id="btnTProHealAndClear">Heal + Clear Transfer Cooldowns (${sh.cooldowns ?? 0})</button>
        </div>
      </div>
      <div style="margin-bottom:8px;display:flex;gap:6px;flex-wrap:wrap;">
        <span class="pill pill-cyan">Avg Mood: ${sh.avgMood ?? 0}</span>
        <span class="pill ${(sh.avgBurnout ?? 0) > 0.3 ? "pill-bad" : "pill-ok"}">Avg Burnout: ${sh.avgBurnout ?? 0}</span>
        <span class="pill pill-blue">Active Bids: ${sh.activeBids ?? 0}</span>
        <span class="pill pill-warn">Cooldown Locks: ${sh.cooldowns ?? 0}</span>
      </div>
      <div class="chart-box">${studioBuildSparklineSvg(pro.rankingHistory || [], true, "#")}</div>
    </div>

    <div class="subcard">
      <div class="subcard-title">Sponsors Manager (${sponsors.length})</div>
      <div class="table-wrap" style="max-height:210px;margin-bottom:8px;">
        <table>
          <thead><tr><th>Sponsor</th><th>Monthly ($)</th><th>Bonus ($)</th><th>End Year</th><th>Actions</th></tr></thead>
          <tbody>${spRows}</tbody>
        </table>
      </div>
      <div class="form-grid">
        <div class="field"><label>Catalog Sponsor</label><select id="tProNewSpId">${catOpts}</select></div>
        <div class="field"><label>Monthly Contribution ($)</label><input id="tProNewSpMo" type="number" min="0" step="5000" value="50000" /></div>
        <div class="field"><label>Bonus Payout ($)</label><input id="tProNewSpBon" type="number" min="0" step="10000" value="100000" /></div>
        <div class="field"><label>End Year</label><input id="tProNewSpYr" type="number" min="2020" max="2100" value="${(state.summary?.datetime?.year || 2026) + 2}" /></div>
      </div>
      <div class="inline-actions" style="margin-top:8px;">
        <button type="button" class="btn btn-sm btn-primary" id="btnTProAddSp">+ Add Sponsor Deal</button>
      </div>
    </div>

    <div class="subcard">
      <div class="subcard-title">Trophy Cabinet (${(pro.trophies || []).length})</div>
      <div>${(pro.trophies || []).length ? (pro.trophies || []).map((tr) => `<span class="tag-pill">${escapeHtml(tr.year)} · <strong>${escapeHtml(tr.name)}</strong> (${escapeHtml((tr.players || []).join(", "))})</span>`).join(" ") : '<span class="muted">No trophies yet.</span>'}</div>
    </div>
  `;

  async function healSquad(clearCooldowns) {
    try {
      const res = await api(`/api/studio/team/${t.id}/heal`, {
        method: "POST",
        body: JSON.stringify({ resetBurnout: true, maxMood: true, clearCooldowns }),
      });
      await refreshSummaryOnly();
      await openTeamEditor(t.id);
      toast(`Healed ${res.healedPlayers} player(s)${clearCooldowns ? `, cleared ${res.cooldownsCleared} cooldown(s)` : ""}`, "ok");
    } catch (err) {
      toast(`Squad heal failed: ${err.message}`, "err");
    }
  }

  $("btnTProHealSquad").addEventListener("click", () => healSquad(false));
  $("btnTProHealAndClear").addEventListener("click", () => healSquad(true));

  container.querySelectorAll(".t-sp-save").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const idx = Number(btn.dataset.idx);
      const tr = btn.closest("tr");
      try {
        await api(`/api/studio/team/${t.id}/sponsor`, {
          method: "POST",
          body: JSON.stringify({
            mode: "update",
            index: idx,
            fixedMonthlyContribution: Number(tr.querySelector(".t-sp-mo").value || 0),
            bonusPayout: Number(tr.querySelector(".t-sp-bon").value || 0),
            endYear: Number(tr.querySelector(".t-sp-yr").value || 2027),
          }),
        });
        await refreshSummaryOnly();
        await openTeamEditor(t.id);
        toast("Updated sponsor contract.", "ok");
      } catch (err) {
        toast(`Sponsor update failed: ${err.message}`, "err");
      }
    });
  });

  container.querySelectorAll(".t-sp-del").forEach((btn) => {
    btn.addEventListener("click", async () => {
      try {
        await api(`/api/studio/team/${t.id}/sponsor`, {
          method: "POST",
          body: JSON.stringify({ mode: "delete", index: Number(btn.dataset.idx) }),
        });
        await refreshSummaryOnly();
        await openTeamEditor(t.id);
        toast("Removed sponsor.", "ok");
      } catch (err) {
        toast(`Sponsor remove failed: ${err.message}`, "err");
      }
    });
  });

  $("btnTProAddSp").addEventListener("click", async () => {
    try {
      await api(`/api/studio/team/${t.id}/sponsor`, {
        method: "POST",
        body: JSON.stringify({
          mode: "add",
          sponsorId: Number($("tProNewSpId").value || 0),
          fixedMonthlyContribution: Number($("tProNewSpMo").value || 50000),
          bonusPayout: Number($("tProNewSpBon").value || 100000),
          endYear: Number($("tProNewSpYr").value || 2027),
        }),
      });
      await refreshSummaryOnly();
      await openTeamEditor(t.id);
      toast("Added sponsor deal.", "ok");
    } catch (err) {
      toast(`Add sponsor failed: ${err.message}`, "err");
    }
  });
};

// =========================================================================
// Initialization & Event Wiring
// =========================================================================

window.studioResetLazyCaches = studioResetLazyCaches;
window.studioOnTabActivated = studioOnTabActivated;

function studioInit() {
  if (studioState.initialized) return;
  studioState.initialized = true;

  // Sync badge if summary already loaded before studio_addons.js ran
  if (state.summary && $("snapCountBadge")) {
    $("snapCountBadge").textContent = String(state.summary.snapshotCount ?? 0);
  }

  // Topbar Command Palette & Shortcuts
  $("btnCommandPalette")?.addEventListener("click", () => {
    studioOpenModal("cmdPaletteModal");
    $("cmdSearchInput")?.focus();
    studioRunGlobalSearch();
  });
  $("btnCloseCmdModal")?.addEventListener("click", () => studioCloseModal("cmdPaletteModal"));
  $("cmdPaletteModal")?.addEventListener("click", (e) => {
    if (e.target === $("cmdPaletteModal")) studioCloseModal("cmdPaletteModal");
  });
  $("cmdSearchInput")?.addEventListener("input", () => studioRunGlobalSearch());

  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      studioOpenModal("cmdPaletteModal");
      $("cmdSearchInput")?.focus();
      studioRunGlobalSearch();
    } else if (e.key === "Escape") {
      studioCloseModal("cmdPaletteModal");
      studioCloseModal("snapshotsModal");
    }
  });

  // Undo Time Machine Snapshots Modal
  $("btnOpenSnapshots")?.addEventListener("click", async () => {
    studioOpenModal("snapshotsModal");
    await studioLoadSnapshotsModal();
  });
  $("btnCloseSnapshotsModal")?.addEventListener("click", () => studioCloseModal("snapshotsModal"));
  $("snapshotsModal")?.addEventListener("click", (e) => {
    if (e.target === $("snapshotsModal")) studioCloseModal("snapshotsModal");
  });
  $("btnCreateSnapshot")?.addEventListener("click", async () => {
    const label = ($("snapNewLabel")?.value || "").trim() || "Manual Checkpoint";
    try {
      const res = await api("/api/studio/snapshot/create", {
        method: "POST",
        body: JSON.stringify({ label }),
      });
      $("snapNewLabel").value = "";
      await refreshSummaryOnly();
      await studioLoadSnapshotsModal();
      toast(`Created checkpoint #${res.id}: ${res.label}`, "ok");
    } catch (err) {
      toast(`Snapshot failed: ${err.message}`, "err");
    }
  });

  // Non-destructive Disk Backup Copy
  $("btnDiskBackup")?.addEventListener("click", async () => {
    try {
      const res = await api("/api/backup", { method: "POST", body: "{}" });
      toast(`Backup saved (${res.sizeMb} MB): ${res.backupPath}`, "ok");
    } catch (err) {
      toast(`Backup failed: ${err.message}`, "err");
    }
  });

  // God Mode Superteam Smoother: All-Team Filter
  $("godNerfTeamSearch")?.addEventListener("input", () => renderGodNerfTeamSelect());

  // Subtabs: Studio Labs (Career HQ, Save Diff, God Mode, Sandbox, Growth, Market, Weapons)
  document.querySelectorAll(".subtab-btn[data-stsubtab]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      document.querySelectorAll(".subtab-btn[data-stsubtab]").forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".stsubtab-panel").forEach((p) => p.classList.remove("active"));
      btn.classList.add("active");
      $(`stSub-${btn.dataset.stsubtab}`)?.classList.add("active");
      studioState.activeStSubtab = btn.dataset.stsubtab;
      await studioOnTabActivated("studiolabs");
    });
  });

  // Career HQ controls
  $("chSwitchTeamSearch")?.addEventListener("input", () => studioRenderSwitchTeamsSelect());
  $("btnChSaveIdentity")?.addEventListener("click", async () => {
    const skills = {};
    document.querySelectorAll(".ch-mgr-skill").forEach((inp) => {
      skills[inp.dataset.key] = Number(inp.value || 10);
    });
    const payload = {
      profile: {
        name: $("chManagerName").value.trim(),
        age: Number($("chManagerAge").value || 30),
        nation: Number($("chManagerNation").value || 1),
      },
      managerSkills: skills,
      managerContract: {
        salaryYear: Number($("chManagerSalary").value || 0),
        endDate: isoToDateObj($("chManagerEndDate").value, studioState.careerHq?.managerContract?.endDate),
      },
    };
    try {
      await api("/api/studio/career-hq/update", { method: "POST", body: JSON.stringify(payload) });
      await refreshSummaryOnly();
      await studioLoadCareerHq();
      toast("Saved Manager Identity & Contract", "ok");
    } catch (err) {
      toast(`Career HQ save failed: ${err.message}`, "err");
    }
  });

  $("btnChMaxSecurity")?.addEventListener("click", () => {
    $("chSecSliders")?.querySelectorAll(".ch-sec-slider").forEach((sl) => {
      sl.value = "1.00";
      const sp = $(`chSecVal-${sl.dataset.key}`);
      if (sp) sp.textContent = "1.00";
    });
  });

  $("btnChSaveSecurity")?.addEventListener("click", async () => {
    const jobSecurity = {
      rankingGoal: Number($("chRankGoal").value || 1000),
      gracePeriod: Number($("chGracePeriod").value || 0),
    };
    $("chSecSliders")?.querySelectorAll(".ch-sec-slider").forEach((sl) => {
      jobSecurity[sl.dataset.key] = Number(sl.value || 0.5);
    });
    try {
      await api("/api/studio/career-hq/update", { method: "POST", body: JSON.stringify({ jobSecurity }) });
      await refreshSummaryOnly();
      await studioLoadCareerHq();
      toast("Saved Board Job Security sliders", "ok");
    } catch (err) {
      toast(`Security update failed: ${err.message}`, "err");
    }
  });

  $("btnChSwitchTeam")?.addEventListener("click", async () => {
    const teamId = Number($("chSwitchTeamSelect").value || 0);
    if (!teamId) return;
    try {
      await api("/api/studio/career-hq/switch-team", {
        method: "POST",
        body: JSON.stringify({ teamId, swapCoach: Boolean($("chSwapCoach")?.checked) }),
      });
      await refreshSummaryOnly();
      await refreshAllViews();
      await studioLoadCareerHq();
      toast(`Switched managed club to #${teamId}`, "ok");
    } catch (err) {
      toast(`Club switch failed: ${err.message}`, "err");
    }
  });

  $("btnChHealSquad")?.addEventListener("click", async () => {
    const tid = studioState.careerHq?.profile?.teamId;
    if (!tid) return toast("No managed club selected.", "err");
    try {
      const r = await api(`/api/studio/team/${tid}/heal`, {
        method: "POST",
        body: JSON.stringify({ resetBurnout: true, maxMood: true, clearCooldowns: false }),
      });
      await refreshSummaryOnly();
      await studioLoadCareerHq();
      toast(`Healed burnout & maxed mood for ${r.healedPlayers} players`, "ok");
    } catch (err) {
      toast(`Heal squad failed: ${err.message}`, "err");
    }
  });

  $("btnChOpenTeamEditor")?.addEventListener("click", async () => {
    const tid = studioState.careerHq?.profile?.teamId;
    if (!tid) return;
    switchMainTab("teams");
    await openTeamEditor(tid);
  });

  $("btnRunSaveDiff")?.addEventListener("click", () => studioRunSaveDiff());

  // Tournaments Hub controls
  $("tmSearchInput")?.addEventListener("input", () => studioRenderTournamentsList());
  $("tmMismatchOnly")?.addEventListener("change", () => studioRenderTournamentsList());
  $("tmHideUpcoming")?.addEventListener("change", () => studioRenderTournamentsList());
  $("tmSortBy")?.addEventListener("change", () => studioRenderTournamentsList());
  $("btnTmRecalcTop20")?.addEventListener("click", () =>
    studioRunTop20Action(Number($("tmTop20Year")?.value || state.summary?.datetime?.year || 2026), "recalculate", 0, $("tmBatchResult"))
  );
  $("btnTmResetTop20")?.addEventListener("click", () =>
    studioRunTop20Action(Number($("tmTop20Year")?.value || state.summary?.datetime?.year || 2026), "clear", 0, $("tmBatchResult"))
  );
  $("btnTop20RecalcSave")?.addEventListener("click", () =>
    studioRunTop20Action(
      state.statsData?.top20Prediction?.year || state.summary?.datetime?.year || 2026,
      "recalculate",
      state.top20VotePlayerId || 0,
      $("top20PatchResult")
    )
  );
  $("btnTop20ResetClear")?.addEventListener("click", () =>
    studioRunTop20Action(
      state.statsData?.top20Prediction?.year || state.summary?.datetime?.year || 2026,
      "clear",
      0,
      $("top20PatchResult")
    )
  );
  $("btnTmRefreshDetail")?.addEventListener("click", () => studioState.selectedTournamentId && studioSelectTournament(studioState.selectedTournamentId));
  $("btnTmSaveMeta")?.addEventListener("click", async () => {
    if (!studioState.selectedTournamentId) return;
    try {
      await api(`/api/studio/tournament/${studioState.selectedTournamentId}/meta`, {
        method: "POST",
        body: JSON.stringify({
          reputation: Number($("tmEditRep").value || 15),
          bestOfFiveGrandFinals: Boolean($("tmEditBo5").checked),
          stickerMoneyLow: Number($("tmEditStickLow").value || 0),
          stickerMoneyHigh: Number($("tmEditStickHigh").value || 0),
        }),
      });
      await refreshSummaryOnly();
      await studioLoadTournaments();
      toast("Updated tournament metadata", "ok");
    } catch (err) {
      toast(`Tournament meta save failed: ${err.message}`, "err");
    }
  });
  $("btnTmPatchFairDry")?.addEventListener("click", () => studioPatchSingleTournament("fair", true));
  $("btnTmPatchFairApply")?.addEventListener("click", () => studioPatchSingleTournament("fair", false));
  $("btnTmPatchCustom")?.addEventListener("click", () => studioPatchSingleTournament("custom", false));

  async function runBatchAwards(dryRun) {
    try {
      const res = await api("/api/studio/tournaments/batch-fair-awards", {
        method: "POST",
        body: JSON.stringify({ minReputation: Number($("tmBatchMinRep").value || 13), dryRun }),
      });
      const rowsHtml = (res.diffs || [])
        .map((x) => `<li><strong>${escapeHtml(x.name)}</strong> (${escapeHtml(x.date)}): Old MVP <em>${escapeHtml(x.oldMvp)}</em> &rarr; Fair MVP <strong>${escapeHtml(x.newMvp)}</strong></li>`)
        .join("");
      $("tmBatchResult").innerHTML = `
        <strong>${res.dryRun ? "Dry-Run Batch Scan" : "Batch Patch Applied"}:</strong> Scanned ${res.scannedEvents} Rep&ge;${res.minReputation} event(s), changed <strong>${res.changedEvents}</strong> event(s) (${res.mvpChanges} MVP change(s)).
        ${rowsHtml ? `<ul style="margin:6px 0 0 18px;font-size:12px;">${rowsHtml}</ul>` : ""}
      `;
      if (!dryRun) {
        await refreshSummaryOnly();
        await studioLoadTournaments();
        toast(`Patched ${res.changedEvents} tournament(s)`, "ok");
      } else {
        toast(`Previewed batch patch (${res.changedEvents} change(s))`, "info");
      }
    } catch (err) {
      toast(`Batch patch failed: ${err.message}`, "err");
    }
  }
  $("btnTmBatchDry")?.addEventListener("click", () => runBatchAwards(true));
  $("btnTmBatchApply")?.addEventListener("click", () => runBatchAwards(false));
  $("btnTmSyncAwards")?.addEventListener("click", async () => {
    if (!studioHasSaveLoaded()) return toast("Load a save file first.", "err");
    try {
      const pre = await api("/api/studio/tournaments/sync-player-awards", {
        method: "POST",
        body: JSON.stringify({ dryRun: true }),
      });
      if (!confirm(`Repair / Sync all players' MVP & EVP awards strictly from saved tournament winners & end months?\nEvents scanned: ${pre.eventsSynced}\nMismatched events: ${pre.mismatchedEventsBefore}\nAwards removed: ${pre.removedCount}, added: ${pre.addedCount}\n(Undo Snapshot will be saved automatically.)`)) {
        return;
      }
      const res = await api("/api/studio/tournaments/sync-player-awards", {
        method: "POST",
        body: JSON.stringify({ dryRun: false }),
      });
      await refreshSummaryOnly();
      state.statsData = null;
      await studioLoadTournaments();
      if (state.selectedPlayerId && typeof openPlayerEditor === "function") {
        await openPlayerEditor(state.selectedPlayerId);
      }
      $("tmBatchResult").innerHTML = `<div class="verdict-banner ok"><strong>Repaired &amp; Synced Player Awards:</strong> Scanned ${res.eventsSynced} event(s), fixed ${res.mismatchedEventsBefore} mismatched event(s) (-${res.removedCount} / +${res.addedCount} awards). Use <strong>Recalc Top 20</strong> next if needed.</div>`;
      toast(`Synced ${res.eventsSynced} tournament(s) (-${res.removedCount}/+${res.addedCount} awards)`, "ok");
    } catch (err) {
      toast(`Sync failed: ${err.message}`, "err");
    }
  });

  // Sandbox controls
  $("sbPlayerSearch")?.addEventListener("input", () => studioRenderSandboxPool());
  $("btnSbLoadTeam")?.addEventListener("click", () => studioLoadTeamIntoSandbox());
  $("btnSbClearLineup")?.addEventListener("click", () => {
    studioState.sandboxSelectedIds = [];
    studioRenderSandboxSelection();
    studioRenderSandboxPool();
  });
  $("btnSbRunSim")?.addEventListener("click", () => studioRunSandboxSimulation());
  $("btnSbCommitRoster")?.addEventListener("click", async () => {
    const teamId = Number($("sbTeamSelect").value || 0);
    if (!teamId || !studioState.sandboxSelectedIds.length) return toast("Pick team and 1-5 players first.", "err");
    if (!confirm(`Commit ${studioState.sandboxSelectedIds.length} player(s) to team #${teamId} and rebuild tactics?`)) return;
    try {
      const res = await api("/api/studio/sandbox/commit", {
        method: "POST",
        body: JSON.stringify({ teamId, playerIds: studioState.sandboxSelectedIds }),
      });
      await refreshSummaryOnly();
      await refreshAllViews();
      toast(`Committed lineup to ${res.teamName} & rebuilt tactics`, "ok");
    } catch (err) {
      toast(`Commit failed: ${err.message}`, "err");
    }
  });

  // Growth Lab controls
  $("btnGrRefresh")?.addEventListener("click", () => studioLoadGrowthLab());

  // Market Radar controls
  $("mrSearchInput")?.addEventListener("input", () => studioRenderMarketTables());
  $("mrPolicyOnly")?.addEventListener("change", () => studioRenderMarketTables());
  $("btnMrRefresh")?.addEventListener("click", () => studioLoadMarketRadar());
  $("btnMrPurgePolicy")?.addEventListener("click", () => studioMarketAction("purge_policy_violations"));

  // Weapons Lab controls
  $("wpTypeFilter")?.addEventListener("change", () => studioRenderWeaponsTable());
  $("wpSearchInput")?.addEventListener("input", () => studioRenderWeaponsTable());
  $("btnWpRefresh")?.addEventListener("click", () => studioLoadWeaponsLab());
  $("btnWpPresetCs2")?.addEventListener("click", () => studioApplyWeaponPreset("cs2_balanced"));
  $("btnWpPresetAwp")?.addEventListener("click", () => studioApplyWeaponPreset("awp_era"));
  $("btnWpPresetRifle")?.addEventListener("click", () => studioApplyWeaponPreset("rifle_laser"));
  $("btnWpPresetEco")?.addEventListener("click", () => studioApplyWeaponPreset("eco_chaos"));
  $("btnWpSaveWeapon")?.addEventListener("click", async () => {
    if (!studioState.selectedWeaponId) return;
    try {
      const res = await api(`/api/studio/weapon/${studioState.selectedWeaponId}`, {
        method: "POST",
        body: JSON.stringify({
          price: Number($("wpPrice").value),
          damage: Number($("wpDamage").value),
          ammo: Number($("wpAmmo").value),
          killReward: Number($("wpKillReward").value),
          reloadTime: Number($("wpReloadTime").value),
          tier: Number($("wpTier").value),
          hsMultiplier: Number($("wpHsMult").value),
          armorMultiplier: Number($("wpArmorMult").value),
          accuracy: Number($("wpAccuracy").value),
          movingAccuracyPenalty: Number($("wpMovePenalty").value),
          recoilIncreasePerShot: Number($("wpRecoilInc").value),
          recoilResetTime: Number($("wpRecoilReset").value),
          shotInterval: Number($("wpShotInterval").value),
          damageDropOffPerUnitOfDistance: Number($("wpDropOff").value),
        }),
      });
      studioState.weaponsData = res.weapons || [];
      studioSelectWeapon(studioState.selectedWeaponId);
      await refreshSummaryOnly();
      toast(`Updated weapon ${res.weapon?.name || ""}`, "ok");
    } catch (err) {
      toast(`Weapon save failed: ${err.message}`, "err");
    }
  });
}

window.studioInit = studioInit;
studioInit();
