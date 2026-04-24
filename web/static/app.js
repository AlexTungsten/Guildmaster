// app.js — Guildmaster Combat UI
// ─────────────────────────────────────────────────────────────────────────────

// ═══════════════════════════════════════════════════════════════ STATE

const S = {
  archetypes: [],   // [{id, name, max_health, stats, skills, ...}]
  enemies:    [],   // [{id, name, max_health, skills, ...}]
  combat:     null, // last state received from server
  selectedHeroId: null,   // hero being assigned
  selectedInfoId: null,   // entity shown in info panel

  // Tracks current user assignments: { heroId: { skillIdx: [dieValue,...] } }
  // Die identity = its index in hero.rolled_dice
  assignments: {},          // heroId -> { "0": [values...], "1": [...], ... }
  assignedIndices: {},      // heroId -> Set of die-indices already placed
};


// ═══════════════════════════════════════════════════════════════ FETCH HELPERS

async function api(path, method = "GET", body = null) {
  const opts = { method, headers: { "Content-Type": "application/json" } };
  if (body !== null) opts.body = JSON.stringify(body);
  const res = await fetch(path, opts);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error(err.error || res.statusText);
  }
  return res.json();
}


// ═══════════════════════════════════════════════════════════════ SETUP SCREEN

async function initSetup() {
  try {
    [S.archetypes, S.enemies] = await Promise.all([
      api("/api/archetypes"),
      api("/api/enemies"),
    ]);
  } catch (e) {
    alert("Failed to load data: " + e.message);
    return;
  }

  // Add one hero row and one enemy row by default
  addHeroRow();
  addEnemyRow();
}

function addHeroRow() {
  const container = document.getElementById("hero-builder");
  if (container.children.length >= 4) return;

  const row = document.createElement("div");
  row.className = "builder-row";

  const defaultNames = { barbarian: "Beowulf", rogue: "Odysseus", mage: "Merlin", cleric: "Hildegard" };

  const nameInput = document.createElement("input");
  nameInput.type = "text";
  nameInput.placeholder = "Name";
  nameInput.style.width = "90px";

  const sel = document.createElement("select");
  sel.className = "archetype-select";
  S.archetypes.forEach(a => {
    const opt = document.createElement("option");
    opt.value = a.id;
    opt.textContent = a.name;
    sel.appendChild(opt);
  });

  const preview = document.createElement("span");
  preview.className = "archetype-preview";

  function updatePreview() {
    const a = S.archetypes.find(x => x.id === sel.value);
    if (a) preview.textContent = `${a.base_dice_count}d${a.base_dice_sides} · ${a.max_health}HP`;
  }

  // Auto-fill name when archetype changes
  const fillName = () => {
    if (!nameInput.value || Object.values(defaultNames).includes(nameInput.value)) {
      nameInput.value = defaultNames[sel.value] || sel.options[sel.selectedIndex]?.text || "";
    }
    updatePreview();
  };
  sel.addEventListener("change", fillName);
  sel.addEventListener("change", updatePreview);
  fillName();

  const removeBtn = document.createElement("button");
  removeBtn.className = "btn btn-sm btn-danger";
  removeBtn.textContent = "×";
  removeBtn.onclick = () => container.removeChild(row);

  row.append(nameInput, sel, preview, removeBtn);
  container.appendChild(row);
}

function addEnemyRow() {
  const container = document.getElementById("enemy-builder");
  if (container.children.length >= 8) return;

  const row = document.createElement("div");
  row.className = "builder-row";

  const sel = document.createElement("select");
  S.enemies.forEach(e => {
    const opt = document.createElement("option");
    opt.value = e.id;
    opt.textContent = e.name;
    sel.appendChild(opt);
  });

  const countLabel = document.createElement("label");
  countLabel.textContent = "×";
  countLabel.style.color = "var(--muted)";

  const countInput = document.createElement("input");
  countInput.type = "number";
  countInput.value = 1; countInput.min = 1; countInput.max = 6;
  countInput.style.width = "44px";

  const actSel = document.createElement("select");
  actSel.style.width = "68px";
  ["Act 1", "Act 2", "Act 3"].forEach((label, i) => {
    const opt = document.createElement("option");
    opt.value = i + 1; opt.textContent = label;
    actSel.appendChild(opt);
  });

  const removeBtn = document.createElement("button");
  removeBtn.className = "btn btn-sm btn-danger";
  removeBtn.textContent = "×";
  removeBtn.onclick = () => container.removeChild(row);

  row.append(sel, countLabel, countInput, actSel, removeBtn);
  container.appendChild(row);
}

async function startCombat() {
  const heroRows  = [...document.getElementById("hero-builder").children];
  const enemyRows = [...document.getElementById("enemy-builder").children];

  if (!heroRows.length)  { alert("Add at least one hero."); return; }
  if (!enemyRows.length) { alert("Add at least one enemy."); return; }

  const heroes = heroRows.map(row => ({
    archetype_id: row.querySelector(".archetype-select").value,
    name:         row.querySelector("input[type=text]").value.trim() || "Hero",
  }));

  const enemies = enemyRows.map(row => ({
    enemy_id: row.querySelectorAll("select")[0].value,
    count:    parseInt(row.querySelector("input[type=number]").value) || 1,
    act:      parseInt(row.querySelectorAll("select")[1].value) || 1,
  }));

  try {
    const state = await api("/api/combat/start", "POST", { heroes, enemies });
    enterCombatScreen(state);
  } catch (e) {
    alert("Start failed: " + e.message);
  }
}


// ═══════════════════════════════════════════════════════════════ SCREEN SWITCH

function enterCombatScreen(state) {
  document.getElementById("setup-screen").classList.remove("active");
  const combatScreen = document.getElementById("combat-screen");
  combatScreen.classList.add("active");

  S.assignments    = {};
  S.assignedIndices = {};
  S.selectedHeroId = null;
  S.selectedInfoId = null;

  applyState(state);
}

async function backToSetup() {
  await api("/api/combat/reset", "POST").catch(() => {});
  document.getElementById("combat-screen").classList.remove("active");
  document.getElementById("setup-screen").classList.add("active");
  document.getElementById("hero-builder").innerHTML = "";
  document.getElementById("enemy-builder").innerHTML = "";
  S.combat = null;
  addHeroRow();
  addEnemyRow();
}


// ═══════════════════════════════════════════════════════════════ STATE APPLICATION

function applyState(state) {
  S.combat = state;

  // Round label
  document.getElementById("round-label").textContent =
    state.round > 0 ? `Round ${state.round}` : "Ready";

  // Barrier
  const barrierLabel = document.getElementById("barrier-label");
  if (state.barrier_hp > 0) {
    barrierLabel.classList.remove("hidden");
    document.getElementById("barrier-hp").textContent = state.barrier_hp;
  } else {
    barrierLabel.classList.add("hidden");
  }

  // Outcome banner
  const banner = document.getElementById("outcome-banner");
  if (state.winner === "heroes") {
    banner.textContent = "⚔️  Victory! The party triumphs!";
    banner.className = "outcome-banner victory";
  } else if (state.winner === "enemies") {
    banner.textContent = "💀  Defeat! The party has fallen.";
    banner.className = "outcome-banner defeat";
  } else {
    banner.className = "outcome-banner hidden";
  }

  // Buttons
  const isAssigning = state.status === "assigning";
  const isReady     = state.status === "ready";
  const isDone      = state.status === "done";
  document.getElementById("roll-btn").disabled    = !isReady || isDone;
  document.getElementById("confirm-btn").disabled = !isAssigning;
  document.getElementById("auto-btn").disabled    = isDone;

  // Render battlefield
  renderHeroCards(state.heroes);
  renderEnemyCards(state.enemies);

  // Refresh assignment panel if open
  if (S.selectedHeroId && isAssigning) {
    const hero = state.heroes.find(h => h.id === S.selectedHeroId);
    if (hero) renderAssignmentPanel(hero);
  } else if (!isAssigning) {
    closeAssignmentPanel();
  }

  // Refresh info panel if open
  if (S.selectedInfoId) {
    const all = [...(state.heroes || []), ...(state.enemies || [])];
    const ent = all.find(e => e.id === S.selectedInfoId);
    if (ent) renderInfoPanel(ent);
    else closeInfoPanel();
  }

  // Append new log entries
  appendLog(state.log);
}

// Keep track of how many log entries we've already rendered
let _logRendered = 0;
function appendLog(entries) {
  const logEl = document.getElementById("combat-log");
  for (let i = _logRendered; i < entries.length; i++) {
    const e = entries[i];
    const div = document.createElement("div");
    div.className = "log-entry " + (e.type || "info");
    div.textContent = e.text;
    logEl.appendChild(div);
  }
  _logRendered = entries.length;
  logEl.scrollTop = logEl.scrollHeight;
}


// ═══════════════════════════════════════════════════════════════ HERO CARDS

function renderHeroCards(heroes) {
  const container = document.getElementById("hero-cards");
  container.innerHTML = "";
  heroes.forEach(hero => {
    const card = makeHeroCard(hero);
    container.appendChild(card);
  });
}

function makeHeroCard(hero) {
  const card = document.createElement("div");
  card.className = "entity-card" + (hero.is_alive ? "" : " dead");
  card.dataset.id = hero.id;
  if (hero.id === S.selectedHeroId) card.classList.add("selected");
  card.style.borderColor = hero.color + "88";

  // Header (colored square with name)
  const header = document.createElement("div");
  header.className = "card-header";
  header.style.background = hero.color + "55";
  header.style.borderBottom = `2px solid ${hero.color}88`;
  header.innerHTML = `<span class="card-name">${escHtml(hero.name)}</span>`;

  // Body
  const body = document.createElement("div");
  body.className = "card-body";

  // HP bar
  const pct = hero.max_health > 0 ? (hero.current_health / hero.max_health) * 100 : 0;
  const barClass = pct > 50 ? "hero" : pct > 25 ? "low" : "crit";
  body.innerHTML += `
    <div class="hp-bar-wrap">
      <div class="hp-bar ${barClass}" style="width:${pct}%"></div>
    </div>
    <div class="hp-text">${hero.current_health}/${hero.max_health}${hero.temp_hp > 0 ? ` +${hero.temp_hp}` : ""}</div>
  `;

  // Status effects
  if (hero.status_effects.length) {
    const pills = document.createElement("div");
    pills.className = "status-pills";
    hero.status_effects.forEach(se => {
      const pill = document.createElement("span");
      pill.className = "status-pill " + (se.is_debuff ? "debuff" : "buff");
      pill.textContent = se.name + (se.stacks > 0 ? ` ×${se.stacks}` : se.duration > 0 ? ` (${se.duration})` : "");
      pills.appendChild(pill);
    });
    body.appendChild(pills);
  }

  // Dice indicators (only during assigning phase)
  if (S.combat?.status === "assigning" && hero.rolled_dice.length) {
    const diceRow = document.createElement("div");
    diceRow.className = "card-dice";
    const placed = S.assignedIndices[hero.id] || new Set();
    hero.rolled_dice.forEach((val, idx) => {
      const dot = document.createElement("div");
      dot.className = "card-die-dot" +
        (idx < hero.locked_count ? " locked" : "") +
        (placed.has(idx) ? " assigned" : "");
      dot.textContent = val;
      diceRow.appendChild(dot);
    });
    body.appendChild(diceRow);
  }

  card.append(header, body);

  card.addEventListener("click", () => onHeroCardClick(hero));
  return card;
}


// ═══════════════════════════════════════════════════════════════ ENEMY CARDS

function renderEnemyCards(enemies) {
  const container = document.getElementById("enemy-cards");
  container.innerHTML = "";
  enemies.forEach(enemy => {
    if (!enemy.is_alive) return; // skip dead enemies in the visual; still visible just faded
    const card = makeEnemyCard(enemy);
    container.appendChild(card);
  });
  // Also show dead enemies (faded)
  enemies.forEach(enemy => {
    if (enemy.is_alive) return;
    const card = makeEnemyCard(enemy);
    container.appendChild(card);
  });
}

function makeEnemyCard(enemy) {
  const card = document.createElement("div");
  card.className = "entity-card" + (enemy.is_alive ? "" : " dead");
  card.dataset.id = enemy.id;
  if (enemy.id === S.selectedInfoId) card.classList.add("selected");
  card.style.borderColor = "var(--red)";

  const header = document.createElement("div");
  header.className = "card-header";
  header.style.background = "#4a1a1a";
  header.style.borderBottom = "2px solid #7a2a2a";
  header.innerHTML = `<span class="card-name">${escHtml(enemy.name)}</span>`;

  const body = document.createElement("div");
  body.className = "card-body";

  const pct = enemy.max_health > 0 ? (enemy.current_health / enemy.max_health) * 100 : 0;
  const barClass = pct > 50 ? "enemy" : pct > 25 ? "low" : "crit";
  body.innerHTML += `
    <div class="hp-bar-wrap">
      <div class="hp-bar ${barClass}" style="width:${pct}%"></div>
    </div>
    <div class="hp-text">${enemy.current_health}/${enemy.max_health}${enemy.block > 0 ? ` 🛡${enemy.block}` : ""}</div>
  `;

  if (enemy.status_effects.length) {
    const pills = document.createElement("div");
    pills.className = "status-pills";
    enemy.status_effects.forEach(se => {
      const pill = document.createElement("span");
      pill.className = "status-pill " + (se.is_debuff ? "debuff" : "buff");
      pill.textContent = se.name + (se.stacks > 0 ? ` ×${se.stacks}` : se.duration > 0 ? ` (${se.duration})` : "");
      pills.appendChild(pill);
    });
    body.appendChild(pills);
  }

  if (enemy.intent) {
    const intent = document.createElement("div");
    intent.className = "intent-badge";
    intent.textContent = "→ " + enemy.intent;
    body.appendChild(intent);
  }

  card.append(header, body);
  card.addEventListener("click", () => onEnemyCardClick(enemy));
  return card;
}


// ═══════════════════════════════════════════════════════════════ CLICK HANDLERS

function onHeroCardClick(hero) {
  if (S.combat?.status === "assigning") {
    // Open assignment panel for this hero
    S.selectedHeroId = hero.id;
    S.selectedInfoId = null;
    closeInfoPanel();
    renderAssignmentPanel(hero);
    refreshCardSelection();
  } else {
    // Show info panel
    S.selectedInfoId = hero.id;
    S.selectedHeroId = null;
    closeAssignmentPanel();
    renderInfoPanel(hero);
    refreshCardSelection();
  }
}

function onEnemyCardClick(enemy) {
  S.selectedInfoId = enemy.id;
  closeAssignmentPanel();
  S.selectedHeroId = null;
  renderInfoPanel(enemy, true);
  refreshCardSelection();
}

function refreshCardSelection() {
  document.querySelectorAll(".entity-card").forEach(c => {
    c.classList.toggle("selected",
      c.dataset.id === S.selectedHeroId || c.dataset.id === S.selectedInfoId);
  });
}


// ═══════════════════════════════════════════════════════════════ ASSIGNMENT PANEL

function renderAssignmentPanel(hero) {
  const panel = document.getElementById("assignment-panel");
  panel.classList.remove("hidden");
  document.getElementById("info-panel").classList.add("hidden");

  document.getElementById("assign-hero-name").textContent =
    `${hero.name} — ${hero.archetype}`;

  // Init assignment tracking for this hero if not already done
  if (!S.assignments[hero.id]) {
    S.assignments[hero.id] = {};
    hero.skills.forEach(sk => { S.assignments[hero.id][String(sk.index)] = []; });
  }
  if (!S.assignedIndices[hero.id]) {
    S.assignedIndices[hero.id] = new Set();
  }

  renderDicePool(hero);
  renderSkillZones(hero);
}

function renderDicePool(hero) {
  const pool = document.getElementById("dice-pool");
  pool.innerHTML = "";
  const placed = S.assignedIndices[hero.id] || new Set();

  hero.rolled_dice.forEach((val, idx) => {
    const token = makeDieToken(val, idx, hero, idx < hero.locked_count);
    if (placed.has(idx)) token.classList.add("placed");
    pool.appendChild(token);
  });
}

function makeDieToken(value, dieIndex, hero, isLocked) {
  const el = document.createElement("div");
  el.className = "die-token" + (isLocked ? " locked" : "");
  el.textContent = value;
  el.dataset.dieIndex = dieIndex;
  el.dataset.dieValue = value;
  el.dataset.heroId   = hero.id;
  el.draggable = true;

  el.addEventListener("dragstart", e => {
    e.dataTransfer.setData("application/json", JSON.stringify({
      heroId:   hero.id,
      dieIndex: dieIndex,
      dieValue: value,
    }));
    el.classList.add("dragging");
  });
  el.addEventListener("dragend", () => el.classList.remove("dragging"));
  return el;
}

function renderSkillZones(hero) {
  const col = document.getElementById("skill-zones");
  col.innerHTML = "";
  const asgn = S.assignments[hero.id] || {};

  hero.skills.forEach(sk => {
    const zone = document.createElement("div");
    zone.className = "skill-zone";
    zone.dataset.skillIndex = sk.index;

    const isCharge = sk.charge_cost > 0;
    const meta = isCharge
      ? `${sk.effect_type} · Charge ${sk.current_charge}/${sk.charge_cost}`
      : `${sk.effect_type} · ${sk.dice_slots} dice · ${sk.stat}`;

    zone.innerHTML = `
      <div class="skill-zone-header">
        <span class="skill-zone-name">${escHtml(sk.name)}</span>
        <span class="skill-zone-meta">${meta}</span>
      </div>
      <div class="skill-zone-desc">${escHtml(sk.description)}</div>
    `;

    // Slot row
    const slotRow = document.createElement("div");
    slotRow.className = "slot-row";

    const currentValues = asgn[String(sk.index)] || [];
    for (let s = 0; s < sk.dice_slots; s++) {
      const slot = document.createElement("div");
      slot.className = "die-slot" + (isCharge ? " charge" : "");
      slot.dataset.skillIndex = sk.index;
      slot.dataset.slotIndex  = s;

      if (s < currentValues.length) {
        slot.textContent = currentValues[s];
        slot.classList.add("occupied");
        slot.title = "Click to remove";
        slot.addEventListener("click", () => {
          removeFromSlot(hero, sk.index, s);
        });
      } else {
        slot.textContent = "";
        slot.addEventListener("dragover",  e => { e.preventDefault(); slot.classList.add("dragover"); });
        slot.addEventListener("dragleave", () => slot.classList.remove("dragover"));
        slot.addEventListener("drop",      e => onDropToSlot(e, hero, sk.index, s));
      }
      slotRow.appendChild(slot);
    }
    zone.appendChild(slotRow);

    // Charge progress bar
    if (isCharge) {
      const pct = sk.charge_cost > 0 ? Math.min(100, (sk.current_charge / sk.charge_cost) * 100) : 0;
      zone.innerHTML += `
        <div class="charge-bar-wrap"><div class="charge-bar" style="width:${pct}%"></div></div>
        <div class="charge-label">Charge: ${sk.current_charge} / ${sk.charge_cost}</div>
      `;
    }

    col.appendChild(zone);
  });
}

function onDropToSlot(e, hero, skillIndex, slotIndex) {
  e.preventDefault();
  const slot = e.currentTarget;
  slot.classList.remove("dragover");

  let data;
  try { data = JSON.parse(e.dataTransfer.getData("application/json")); }
  catch { return; }

  if (data.heroId !== hero.id) return;  // can't share dice between heroes

  const dieIndex = data.dieIndex;
  const dieValue = data.dieValue;

  // Already placed?
  if ((S.assignedIndices[hero.id] || new Set()).has(dieIndex)) return;

  // Ensure assignment arrays are initialized
  if (!S.assignments[hero.id]) S.assignments[hero.id] = {};
  if (!S.assignments[hero.id][String(skillIndex)]) S.assignments[hero.id][String(skillIndex)] = [];

  // Only fill up to dice_slots
  const sk = hero.skills.find(s => s.index === skillIndex);
  if (!sk) return;
  const arr = S.assignments[hero.id][String(skillIndex)];
  if (arr.length >= sk.dice_slots) return;

  arr.push(dieValue);
  S.assignedIndices[hero.id].add(dieIndex);

  // Re-render both pool and zones
  renderDicePool(hero);
  renderSkillZones(hero);
  renderHeroCards(S.combat.heroes);
}

function onDropToPool(e) {
  // Handle dropping a die back to the pool from a slot — handled by removeFromSlot
}

function removeFromSlot(hero, skillIndex, slotIndex) {
  if (!S.assignments[hero.id]) return;
  const arr = S.assignments[hero.id][String(skillIndex)] || [];
  const removedValue = arr.splice(slotIndex, 1)[0];
  if (removedValue === undefined) return;

  // Find the die index that corresponds to this value (first unmatched occurrence)
  const placed = S.assignedIndices[hero.id] || new Set();
  // We need to find which physical die index was assigned to this slot.
  // Since we track by value (not index) in arr, we find the earliest placed die with this value.
  // Rebuild index tracking by scanning all assignments.
  rebuildAssignedIndices(hero);

  renderDicePool(hero);
  renderSkillZones(hero);
  renderHeroCards(S.combat.heroes);
}

function rebuildAssignedIndices(hero) {
  // Recompute which die indices are placed based on current assignments
  const asgn = S.assignments[hero.id] || {};
  const allAssigned = Object.values(asgn).flat();  // list of values

  const placed = new Set();
  const valueCounts = {};
  allAssigned.forEach(v => { valueCounts[v] = (valueCounts[v] || 0) + 1; });

  const remaining = { ...valueCounts };
  hero.rolled_dice.forEach((val, idx) => {
    if (remaining[val] > 0) {
      placed.add(idx);
      remaining[val]--;
    }
  });
  S.assignedIndices[hero.id] = placed;
}

function autoAssignHero() {
  if (!S.selectedHeroId || !S.combat) return;
  const hero = S.combat.heroes.find(h => h.id === S.selectedHeroId);
  if (!hero) return;

  // Clear current assignments for this hero
  S.assignments[hero.id] = {};
  S.assignedIndices[hero.id] = new Set();
  hero.skills.forEach(sk => { S.assignments[hero.id][String(sk.index)] = []; });

  // Simple fill: assign dice in order to skills in order
  const diceLeft = [...hero.rolled_dice.entries()];  // [idx, value]
  hero.skills.forEach(sk => {
    const arr = S.assignments[hero.id][String(sk.index)];
    for (let s = 0; s < sk.dice_slots && diceLeft.length; s++) {
      const [idx, val] = diceLeft.shift();
      arr.push(val);
      S.assignedIndices[hero.id].add(idx);
    }
  });

  renderDicePool(hero);
  renderSkillZones(hero);
  renderHeroCards(S.combat.heroes);
}

function clearHeroAssignment() {
  if (!S.selectedHeroId || !S.combat) return;
  const hero = S.combat.heroes.find(h => h.id === S.selectedHeroId);
  if (!hero) return;

  S.assignments[hero.id] = {};
  S.assignedIndices[hero.id] = new Set();
  hero.skills.forEach(sk => { S.assignments[hero.id][String(sk.index)] = []; });

  renderDicePool(hero);
  renderSkillZones(hero);
  renderHeroCards(S.combat.heroes);
}

function closeAssignmentPanel() {
  document.getElementById("assignment-panel").classList.add("hidden");
  S.selectedHeroId = null;
  refreshCardSelection();
}


// ═══════════════════════════════════════════════════════════════ INFO PANEL

function renderInfoPanel(entity, isEnemy = false) {
  const panel = document.getElementById("info-panel");
  panel.classList.remove("hidden");
  document.getElementById("assignment-panel").classList.add("hidden");
  S.selectedInfoId = entity.id;

  document.getElementById("info-title").textContent =
    entity.name + (isEnemy ? "" : ` — ${entity.archetype || ""}`);

  const body = document.getElementById("info-body");
  body.innerHTML = "";

  // HP
  const hpSection = document.createElement("div");
  hpSection.className = "info-section";
  const hp = entity.current_health, maxhp = entity.max_health;
  const pct = maxhp > 0 ? (hp / maxhp) * 100 : 0;
  const barCls = pct > 50 ? (isEnemy ? "enemy" : "hero") : pct > 25 ? "low" : "crit";
  hpSection.innerHTML = `
    <h4>Health</h4>
    <div class="hp-bar-wrap"><div class="hp-bar ${barCls}" style="width:${pct}%"></div></div>
    <div class="hp-text">${hp} / ${maxhp}${entity.temp_hp > 0 ? ` (+${entity.temp_hp} temp)` : ""}${entity.block > 0 ? ` 🛡 ${entity.block}` : ""}</div>
  `;
  body.appendChild(hpSection);

  // Stats (heroes only)
  if (!isEnemy && entity.stats) {
    const statsSection = document.createElement("div");
    statsSection.className = "info-section";
    statsSection.innerHTML = "<h4>Stats</h4>";
    Object.entries(entity.stats).forEach(([k, v]) => {
      const mod = Math.floor(v / 2) - 5;
      const row = document.createElement("div");
      row.className = "info-stat-row";
      row.innerHTML = `<span class="label">${k}</span><span>${v} (${mod >= 0 ? "+" : ""}${mod})</span>`;
      statsSection.appendChild(row);
    });
    body.appendChild(statsSection);
  }

  // Status effects
  if (entity.status_effects?.length) {
    const seSection = document.createElement("div");
    seSection.className = "info-section";
    seSection.innerHTML = "<h4>Status Effects</h4>";
    entity.status_effects.forEach(se => {
      const row = document.createElement("div");
      row.className = "info-stat-row";
      const detail = se.stacks > 0 ? `×${se.stacks}` : se.duration > 0 ? `${se.duration} turn(s)` : "";
      row.innerHTML = `<span class="label">${se.name}</span><span>${detail}</span>`;
      seSection.appendChild(row);
    });
    body.appendChild(seSection);
  }

  // Skills
  if (entity.skills?.length) {
    const skSection = document.createElement("div");
    skSection.className = "info-section";
    skSection.innerHTML = "<h4>Skills</h4>";
    entity.skills.forEach(sk => {
      const div = document.createElement("div");
      div.className = "info-skill-row";
      const chargeMeta = sk.charge_cost > 0
        ? `Charge: ${sk.current_charge ?? sk.buffered ?? 0} / ${sk.charge_cost}`
        : `${sk.dice_slots} dice`;
      div.innerHTML = `
        <div class="info-skill-name">${escHtml(sk.name)}</div>
        <div class="info-skill-desc">${escHtml(sk.description || "")}</div>
        <div class="info-skill-meta">${sk.effect_type} · ${chargeMeta}</div>
      `;
      skSection.appendChild(div);
    });
    body.appendChild(skSection);
  }

  // Passives (hero only)
  if (!isEnemy && entity.passives?.length) {
    const pSection = document.createElement("div");
    pSection.className = "info-section";
    pSection.innerHTML = `<h4>Passives</h4><div class="info-stat-row"><span>${entity.passives.join(", ")}</span></div>`;
    body.appendChild(pSection);
  }

  // Enemy intent
  if (isEnemy && entity.intent) {
    const intentSection = document.createElement("div");
    intentSection.className = "info-section";
    intentSection.innerHTML = `<h4>Intent</h4><div class="info-stat-row">${escHtml(entity.intent)}</div>`;
    body.appendChild(intentSection);
  }
}

function closeInfoPanel() {
  document.getElementById("info-panel").classList.add("hidden");
  S.selectedInfoId = null;
  refreshCardSelection();
}


// ═══════════════════════════════════════════════════════════════ COMBAT ACTIONS

async function rollDice() {
  try {
    // Reset assignments for the new round
    S.assignments    = {};
    S.assignedIndices = {};
    const state = await api("/api/combat/begin-round", "POST");
    applyState(state);
    // Auto-open first living hero's assignment panel
    const firstHero = state.heroes.find(h => h.is_alive);
    if (firstHero) {
      S.selectedHeroId = firstHero.id;
      renderAssignmentPanel(firstHero);
      refreshCardSelection();
    }
  } catch (e) {
    alert("Roll error: " + e.message);
  }
}

async function confirmTurn() {
  if (!S.combat || S.combat.status !== "assigning") return;

  // Build the assignment payload
  // assignments[heroId][skillIdx] = [values...]
  const payload = {};
  S.combat.heroes.forEach(hero => {
    if (!hero.is_alive) return;
    const heroAsgn = S.assignments[hero.id] || {};
    payload[hero.id] = {};
    hero.skills.forEach(sk => {
      payload[hero.id][String(sk.index)] = heroAsgn[String(sk.index)] || [];
    });
  });

  try {
    closeAssignmentPanel();
    const state = await api("/api/combat/assign", "POST", { assignments: payload });
    applyState(state);
  } catch (e) {
    alert("Confirm error: " + e.message);
  }
}

async function autoTurn() {
  S.assignments    = {};
  S.assignedIndices = {};
  closeAssignmentPanel();
  try {
    const state = await api("/api/combat/auto-turn", "POST");
    applyState(state);
  } catch (e) {
    alert("Auto-turn error: " + e.message);
  }
}


// ═══════════════════════════════════════════════════════════════ UTILITIES

function escHtml(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}


// ═══════════════════════════════════════════════════════════════ EVENT WIRING

document.addEventListener("DOMContentLoaded", () => {
  // Setup screen
  document.getElementById("add-hero-btn").addEventListener("click",  addHeroRow);
  document.getElementById("add-enemy-btn").addEventListener("click", addEnemyRow);
  document.getElementById("start-btn").addEventListener("click",     startCombat);

  // Combat screen
  document.getElementById("back-to-setup-btn").addEventListener("click", backToSetup);
  document.getElementById("roll-btn").addEventListener("click",    rollDice);
  document.getElementById("confirm-btn").addEventListener("click", confirmTurn);
  document.getElementById("auto-btn").addEventListener("click",    autoTurn);

  // Assignment panel
  document.getElementById("auto-assign-hero-btn").addEventListener("click", autoAssignHero);
  document.getElementById("clear-assign-btn").addEventListener("click",     clearHeroAssignment);
  document.getElementById("close-assign-btn").addEventListener("click",     closeAssignmentPanel);

  // Info panel
  document.getElementById("close-info-btn").addEventListener("click", closeInfoPanel);

  // Init setup
  initSetup();
});
