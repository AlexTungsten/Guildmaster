/* app.js — Guildmaster WebSocket client */

// ── State ─────────────────────────────────────────────────────────────
let ws           = null;
let gameState    = null;
let openQuest    = null;    // quest object shown in panel
let stagedHeroes = [];      // hero_ids staged in the panel

// Freeze re-renders of the hero columns inside the quest panel only.
// Quest cards use smart in-place updates instead (see renderQuestList).
let panelFrozen = false;

function freezeOn(elementId, flagSetter) {
  const el = document.getElementById(elementId);
  if (!el) return;
  let timer = null;
  const freeze   = () => { clearTimeout(timer); flagSetter(true); };
  const unfreeze = () => { timer = setTimeout(() => flagSetter(false), 300); };
  el.addEventListener("mouseenter", freeze);
  el.addEventListener("mousedown",  freeze);
  el.addEventListener("mouseleave", unfreeze);
}

freezeOn("qp-available-heroes", v => { panelFrozen = v; });
freezeOn("qp-assigned-heroes",  v => { panelFrozen = v; });

// ── WebSocket ──────────────────────────────────────────────────────────
function connect() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws`);

  ws.onopen = () => {
    document.getElementById("conn-dot").classList.add("connected");
    document.getElementById("conn-dot").title = "Connected";
  };
  ws.onclose = () => {
    document.getElementById("conn-dot").classList.remove("connected");
    document.getElementById("conn-dot").title = "Disconnected — reconnecting…";
    setTimeout(connect, 2000);
  };
  ws.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    if (msg.type === "state") {
      gameState = msg.data;
      render();
    } else if (msg.type === "feedback") {
      showFeedback(msg.text);
    }
  };
}

function sendCommand(cmd) {
  if (ws && ws.readyState === WebSocket.OPEN)
    ws.send(JSON.stringify({ type: "command", command: cmd }));
}
function sendPause() {
  if (ws && ws.readyState === WebSocket.OPEN)
    ws.send(JSON.stringify({ type: "pause" }));
}
function sendResume() {
  if (ws && ws.readyState === WebSocket.OPEN)
    ws.send(JSON.stringify({ type: "resume" }));
}

// ── Feedback ───────────────────────────────────────────────────────────
function showFeedback(text) {
  const el = document.getElementById("feedback");
  el.textContent = text;
  el.className = text.startsWith("OK") ? "ok" : "err";
  clearTimeout(el._timer);
  el._timer = setTimeout(() => { el.textContent = ""; el.className = ""; }, 3000);
}

// ── Render ─────────────────────────────────────────────────────────────
function render() {
  if (!gameState) return;
  renderTopBar();
  renderQuestColumns();
  renderHeroStrip();
  if (openQuest) renderQuestPanel();
}

// ── Top bar ────────────────────────────────────────────────────────────
function renderTopBar() {
  const s = gameState;
  document.getElementById("gold-display").textContent = s.gold + "g";
  document.getElementById("tick-display").textContent = s.tick;

  const remaining = s.boss_ticks_remaining;
  const duration  = s.boss_timer_duration;
  const pct = duration > 0 ? (remaining / duration) * 100 : 0;

  const bossLabel = document.getElementById("boss-timer-label");
  const bossBar   = document.getElementById("boss-timer-bar-fill");

  if (s.boss && s.boss.revealed && !s.boss.defeated) {
    bossLabel.textContent = "BOSS ACTIVE";
    bossBar.style.width = "100%";
    bossBar.style.background = "var(--red)";
  } else if (s.boss && s.boss.defeated) {
    bossLabel.textContent = "Boss defeated";
    bossBar.style.width = "100%";
    bossBar.style.background = "var(--green)";
  } else {
    bossLabel.textContent = `Boss in ${remaining}`;
    bossBar.style.width = pct + "%";
    bossBar.style.background = pct < 25 ? "var(--red)" : "var(--orange)";
  }

  document.getElementById("paused-badge").classList.toggle("visible", !!openQuest);
}

// ── Quest columns ──────────────────────────────────────────────────────
function renderQuestColumns() {
  const s = gameState;

  const banner = document.getElementById("boss-banner");
  const bossActive = s.boss && s.boss.revealed && !s.boss.defeated;
  if (bossActive) {
    banner.textContent = `⚔ BARON MIDAS HAS APPEARED${s.boss.buffs.length ? " — Buffs: " + s.boss.buffs.join(", ") : ""}`;
    banner.classList.add("visible");
  } else {
    banner.classList.remove("visible");
  }

  document.getElementById("avail-count").textContent = s.available_quests.length;
  document.getElementById("active-count").textContent = s.active_quests.length;

  renderQuestList("quest-available", s.available_quests, true);
  renderQuestList("quest-active",    s.active_quests,    false);
}

function renderQuestList(containerId, quests, isAvailable) {
  const container = document.getElementById(containerId);

  if (!quests.length) {
    container.innerHTML = `<div class="empty-state">${isAvailable ? "No quests available" : "No quests in progress"}</div>`;
    return;
  }

  // Check whether the set of quest IDs has changed
  const existing = [...container.querySelectorAll(".quest-card")];
  const existingIds = existing.map(c => c.dataset.id).join(",");
  const newIds      = quests.map(q => q.quest_id).join(",");

  if (existingIds !== newIds) {
    // Full rebuild only when quests appear or disappear
    container.innerHTML = quests.map(q => questCardHTML(q, isAvailable)).join("");
    return;
  }

  // Same quests — update only the expiry countdown in-place (no DOM replacement)
  if (isAvailable) {
    quests.forEach(q => {
      const card = container.querySelector(`[data-id="${q.quest_id}"]`);
      if (!card) return;
      const el = card.querySelector(".quest-expiry");
      if (!el) return;
      el.textContent = `⏱ ${q.expiry}t`;
      el.className = `quest-expiry${q.expiry < 20 ? " urgent" : ""}`;
    });
  }
}

function questCardHTML(q, isAvailable) {
  let expiryHTML = "";
  if (isAvailable && q.expiry !== undefined) {
    const urgent = q.expiry < 20 ? "urgent" : "";
    expiryHTML = `<span class="quest-expiry ${urgent}">⏱ ${q.expiry}t</span>`;
  }
  const critBadge = q.is_critical
    ? ' <span style="color:var(--red);font-size:10px">CRITICAL</span>' : "";

  let assignedLine = "";
  if (!isAvailable && q.assigned_hero_ids?.length && gameState) {
    const names = q.assigned_hero_ids
      .map(id => gameState.heroes.find(h => h.hero_id === id)?.name || id)
      .join(", ");
    assignedLine = `<div class="quest-heroes">${names}</div>`;
  }
  let phaseLabel = "";
  if (!isAvailable) {
    const phaseMap = { assigned: "TRAVELING THERE", resolving: "ON QUEST", traveling: "TRAVELING BACK" };
    phaseLabel = `<div class="quest-phase">${phaseMap[q.status] || q.status.toUpperCase()}</div>`;
  }

  return `
    <div class="quest-card ${isAvailable ? "available" : ""} ${q.is_critical ? "critical" : ""}"
         data-id="${q.quest_id}">
      <div class="quest-header">
        <span class="quest-title">${q.title}${critBadge}</span>
        ${expiryHTML}
      </div>
      <div class="quest-meta">
        <span class="diff-${q.difficulty}">${q.difficulty.toUpperCase()}</span>
        <span>${q.quest_type === "combat" ? "⚔ Combat" : "🎲 Stat Check"}</span>
        <span>${q.required_heroes}–${q.max_heroes} heroes</span>
      </div>
      <div class="quest-reward">
        <span class="reward-gold">💰 ${q.reward.gold}g</span>
        <span class="reward-xp">✨ ${q.reward.xp} xp</span>
      </div>
      ${assignedLine}
      ${phaseLabel}
    </div>`;
}

// Click on available quest → open panel
document.getElementById("quest-available").addEventListener("click", e => {
  const card = e.target.closest(".quest-card.available");
  if (!card || !gameState) return;
  const quest = gameState.available_quests.find(q => q.quest_id === card.dataset.id);
  if (quest) openQuestPanel(quest);
});

// ── Quest panel ────────────────────────────────────────────────────────

function openQuestPanel(quest) {
  openQuest    = quest;
  stagedHeroes = [];
  sendPause();

  document.getElementById("qp-title").textContent = quest.title;
  document.getElementById("qp-description").textContent = quest.description || "";
  document.getElementById("qp-meta").innerHTML =
    `<span class="diff-${quest.difficulty}">${quest.difficulty.toUpperCase()}</span>
     <span>${quest.quest_type === "combat" ? "⚔ Combat" : "🎲 Stat Check"}</span>
     <span>${quest.required_heroes}–${quest.max_heroes} heroes required</span>`;
  document.getElementById("qp-rewards").innerHTML =
    `<span class="reward-gold" style="font-size:15px">💰 ${quest.reward.gold} gold</span>
     <span class="reward-xp"  style="font-size:15px">✨ ${quest.reward.xp} XP</span>`;

  document.getElementById("quest-overlay").classList.remove("hidden");
  renderQuestPanel();
}

function closeQuestPanel() {
  openQuest    = null;
  stagedHeroes = [];
  sendResume();
  document.getElementById("quest-overlay").classList.add("hidden");
}

function renderQuestPanel(force = false) {
  if (!openQuest || !gameState) return;
  if (panelFrozen && !force) return;

  // Drop staged heroes that are no longer idle
  stagedHeroes = stagedHeroes.filter(id => {
    const h = gameState.heroes.find(h => h.hero_id === id);
    return h && h.current_health > 0 && h.status === "idle";
  });

  const req   = openQuest.required_heroes;
  const max   = openQuest.max_heroes;
  const count = stagedHeroes.length;

  document.getElementById("qp-hero-count").textContent =
    `(${count} / max ${max} — need ${req})`;
  document.getElementById("qp-send").disabled = count < req;

  // ── Available heroes (idle, not staged) ──
  const idleHeroes = gameState.heroes.filter(h =>
    h.status === "idle" && h.current_health > 0 && !stagedHeroes.includes(h.hero_id)
  );
  const availContainer = document.getElementById("qp-available-heroes");
  const atMax = count >= max;

  if (!idleHeroes.length) {
    availContainer.innerHTML = `<div style="font-size:12px;color:var(--text-dim);padding:12px 0">No idle heroes available</div>`;
  } else {
    availContainer.innerHTML = idleHeroes.map(h => {
      const hpPct = Math.round((h.current_health / h.max_health) * 100);
      const disabled = atMax ? 'style="opacity:0.4;pointer-events:none"' : "";
      return `
        <div class="qp-hero-row available" data-id="${h.hero_id}" ${disabled}>
          <div class="qp-hero-row-info">
            <div class="qp-hero-row-name">${h.name}</div>
            <div class="qp-hero-row-sub">${h.archetype} · Lv ${h.level} · HP ${h.current_health}/${h.max_health} · Exhaust ${Math.round(h.exhaustion)}</div>
          </div>
          <span class="qp-action-icon">＋</span>
        </div>`;
    }).join("");

    availContainer.querySelectorAll(".qp-hero-row.available").forEach(row => {
      row.addEventListener("click", () => {
        if (stagedHeroes.length >= max) return;
        stagedHeroes.push(row.dataset.id);
        renderQuestPanel(true);
      });
    });
  }

  // ── Assigned heroes ──
  const assignedContainer = document.getElementById("qp-assigned-heroes");
  const emptyHint = document.getElementById("qp-empty-hint");

  if (!count) {
    emptyHint.style.display = "block";
    assignedContainer.querySelectorAll(".qp-hero-row.assigned").forEach(r => r.remove());
  } else {
    emptyHint.style.display = "none";
    assignedContainer.querySelectorAll(".qp-hero-row.assigned").forEach(r => r.remove());
    const rows = stagedHeroes.map(id => {
      const h = gameState.heroes.find(h => h.hero_id === id);
      if (!h) return "";
      return `
        <div class="qp-hero-row assigned" data-id="${id}">
          <div class="qp-hero-row-info">
            <div class="qp-hero-row-name">${h.name}</div>
            <div class="qp-hero-row-sub">${h.archetype} · Lv ${h.level} · HP ${h.current_health}/${h.max_health}</div>
          </div>
          <span class="qp-action-icon" title="Remove">✕</span>
        </div>`;
    }).join("");

    emptyHint.insertAdjacentHTML("afterend", rows);
    assignedContainer.querySelectorAll(".qp-hero-row.assigned").forEach(row => {
      row.addEventListener("click", () => {
        stagedHeroes = stagedHeroes.filter(id => id !== row.dataset.id);
        renderQuestPanel(true);
      });
    });
  }
}

// Send button
document.getElementById("qp-send").addEventListener("click", () => {
  if (!openQuest || stagedHeroes.length < openQuest.required_heroes) return;
  sendCommand(`assign ${openQuest.quest_id} ${stagedHeroes.join(" ")}`);
  closeQuestPanel();
});

document.getElementById("qp-close").addEventListener("click",  closeQuestPanel);
document.getElementById("qp-cancel").addEventListener("click", closeQuestPanel);
document.getElementById("quest-overlay").addEventListener("click", e => {
  if (e.target === document.getElementById("quest-overlay")) closeQuestPanel();
});

// ── Hero strip (display only — no dragging needed anymore) ─────────────
function renderHeroStrip() {
  const container = document.getElementById("hero-strip-cards");
  if (!gameState?.heroes.length) {
    container.innerHTML = "<div class='empty-state' style='padding:8px'>No heroes</div>";
    return;
  }
  container.innerHTML = gameState.heroes.map(h => heroMiniHTML(h)).join("");
}

function heroMiniHTML(h) {
  const isDead   = h.current_health <= 0;
  const isIdle   = h.status === "idle";
  const isStaged = stagedHeroes.includes(h.hero_id);

  const hpPct   = Math.max(0, (h.current_health / h.max_health) * 100);
  const hpColor = hpPct > 60 ? "var(--green)" : hpPct > 25 ? "var(--orange)" : "var(--red)";

  const extraClass  = isDead ? "dead" : (!isIdle || isStaged) ? "busy" : "idle-hero";
  const statusKey   = isStaged ? "staged" : h.status;
  const statusLabel = isStaged ? "STAGED"
    : h.status.replace("_", " ").toUpperCase();

  return `
    <div class="hero-mini ${extraClass}" title="${h.name}">
      <div class="hero-mini-name">${h.name}</div>
      <div class="hero-mini-sub">
        <span>${h.archetype} · Lv ${h.level}</span>
        <span class="status-badge status-${statusKey}">${statusLabel}</span>
      </div>
      <div class="hero-mini-hp">
        <div class="hero-mini-hp-fill" style="width:${hpPct}%;background:${hpColor}"></div>
      </div>
      <div style="font-size:10px;color:var(--text-dim)">
        HP ${h.current_health}/${h.max_health} · Exhaust ${Math.round(h.exhaustion)}
      </div>
    </div>`;
}

// ── Command bar ────────────────────────────────────────────────────────
document.getElementById("btn-send").addEventListener("click", submitCommand);
document.getElementById("cmd-input").addEventListener("keydown", e => {
  if (e.key === "Enter") submitCommand();
});
function submitCommand() {
  const input = document.getElementById("cmd-input");
  const cmd = input.value.trim();
  if (!cmd) return;
  sendCommand(cmd);
  input.value = "";
}

// ── Boot ───────────────────────────────────────────────────────────────
connect();
