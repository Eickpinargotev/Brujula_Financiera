/* Brújula — dashboard. Fetch + render + ECharts. Re-renderiza al instante tras cada cambio. */
"use strict";

const C = {
  cyan: "#22d3ee", violet: "#a855f7", green: "#34d399",
  amber: "#fbbf24", red: "#f87171", txt: "#e7eefc",
  muted: "#8aa0c6", grid: "rgba(120,160,220,0.12)",
};
const MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];

const state = { overview: null, catalogos: null, movs: [], filtro: "", activeView: "resumen", simTimer: null, editId: null };
const charts = {};

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];

/* ---------- utilidades ---------- */
async function api(path, opts = {}) {
  const res = await fetch(path, { credentials: "same-origin", ...opts });
  if (res.status === 401) { window.location.href = "/login"; throw new Error("401"); }
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (_) {}
    throw new Error(typeof detail === "string" ? detail : "Error de validación");
  }
  return res.status === 204 ? null : res.json();
}
const money = (n) => "$" + Number(n || 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const moneyK = (n) => Math.abs(n) >= 1000 ? "$" + (n / 1000).toFixed(1) + "k" : "$" + Math.round(n);
const pct = (n) => (Number(n || 0) * 100).toFixed(0) + "%";
const mesCorto = (p) => { const [y, m] = p.split("-"); return MESES[+m - 1] + (m === "01" ? " " + y.slice(2) : ""); };
const fechaCorta = (iso) => { const [, m, d] = iso.split("-"); return `${d}/${m}`; };
const mesAnio = (iso) => { if (!iso) return "—"; const [y, m] = iso.split("-"); return MESES[+m - 1] + " " + y; };
const addMonths = (iso, n) => { const d = new Date(iso + "T00:00:00"); d.setMonth(d.getMonth() + n); return d.toISOString().slice(0, 10); };

/* ---------- ECharts ---------- */
function ensureChart(id) {
  if (!charts[id]) {
    const el = document.getElementById(id);
    if (el && window.echarts) charts[id] = echarts.init(el, null, { renderer: "canvas" });
  }
  return charts[id];
}
const baseAxis = {
  axisLine: { lineStyle: { color: C.grid } },
  axisTick: { show: false },
  axisLabel: { color: C.muted, fontSize: 11 },
  splitLine: { lineStyle: { color: C.grid } },
};
const baseTooltip = {
  backgroundColor: "rgba(10,16,32,0.92)", borderColor: "rgba(120,160,220,0.25)",
  textStyle: { color: C.txt }, valueFormatter: (v) => money(v),
};

function renderFlujo() {
  const ch = ensureChart("chart-flujo"); if (!ch) return;
  const s = state.overview.serie;
  ch.setOption({
    grid: { left: 8, right: 8, top: 30, bottom: 4, containLabel: true },
    legend: { top: 0, right: 0, textStyle: { color: C.muted }, itemWidth: 10, itemHeight: 10, icon: "roundRect" },
    tooltip: { trigger: "axis", ...baseTooltip, axisPointer: { type: "shadow" } },
    xAxis: { type: "category", data: s.map((x) => mesCorto(x.periodo)), ...baseAxis, splitLine: { show: false } },
    yAxis: { type: "value", ...baseAxis, axisLabel: { ...baseAxis.axisLabel, formatter: moneyK } },
    series: [
      { name: "Ingreso", type: "bar", data: s.map((x) => x.ingreso), barWidth: 12, itemStyle: { borderRadius: [4, 4, 0, 0], color: C.cyan } },
      { name: "Gasto", type: "bar", data: s.map((x) => x.gasto), barWidth: 12, itemStyle: { borderRadius: [4, 4, 0, 0], color: C.violet } },
      { name: "Ahorro", type: "line", smooth: true, data: s.map((x) => x.ahorro), symbol: "circle", symbolSize: 6, lineStyle: { color: C.green, width: 2.5 }, itemStyle: { color: C.green } },
    ],
  });
}

function renderCategorias() {
  const ch = ensureChart("chart-categorias"); if (!ch) return;
  const cats = state.overview.categorias;
  const palette = [C.cyan, C.violet, C.green, C.amber, "#60a5fa", "#f472b6", "#2dd4bf", C.red];
  ch.setOption({
    tooltip: { trigger: "item", ...baseTooltip },
    legend: { type: "scroll", bottom: 0, textStyle: { color: C.muted }, icon: "circle" },
    series: [{
      type: "pie", radius: ["52%", "74%"], center: ["50%", "44%"], avoidLabelOverlap: true,
      itemStyle: { borderColor: "rgba(7,11,22,0.8)", borderWidth: 3 },
      label: { show: false }, labelLine: { show: false },
      data: cats.length
        ? cats.map((c, i) => ({ name: c.nombre, value: c.monto, itemStyle: { color: palette[i % palette.length] } }))
        : [{ name: "Sin gastos", value: 1, itemStyle: { color: C.grid } }],
    }],
  });
}

function renderProyeccion() {
  const ch = ensureChart("chart-proyeccion"); if (!ch) return;
  const p = state.overview.proyeccion;
  const k = state.overview.kpis;
  const delta = +($("#sim-delta")?.value || 0);
  const labels = p.map((x) => mesCorto(x.periodo));
  const series = [{
    name: "Proyección base", type: "line", smooth: true, data: p.map((x) => x.saldo),
    symbol: "none", lineStyle: { color: C.cyan, width: 3 },
    areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
      { offset: 0, color: "rgba(34,211,238,0.35)" }, { offset: 1, color: "rgba(34,211,238,0.02)" }]) },
  }];
  // Línea simulada: refleja en vivo el "ahorro extra" del slider sobre el ahorro promedio.
  if (delta > 0) {
    const sim = p.map((_, i) => Math.round((k.saldo_estimado + (k.ahorro_promedio + delta) * i) * 100) / 100);
    series.push({
      name: "Con ahorro extra", type: "line", smooth: true, data: sim,
      symbol: "none", lineStyle: { color: C.violet, width: 2.5, type: "dashed" },
      areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
        { offset: 0, color: "rgba(168,85,247,0.22)" }, { offset: 1, color: "rgba(168,85,247,0.02)" }]) },
    });
  }
  ch.setOption({
    grid: { left: 8, right: 14, top: delta > 0 ? 30 : 18, bottom: 4, containLabel: true },
    legend: { show: delta > 0, top: 0, right: 0, textStyle: { color: C.muted }, itemWidth: 12, itemHeight: 8, icon: "roundRect" },
    tooltip: { trigger: "axis", ...baseTooltip },
    xAxis: { type: "category", data: labels, boundaryGap: false, ...baseAxis, splitLine: { show: false } },
    yAxis: { type: "value", ...baseAxis, axisLabel: { ...baseAxis.axisLabel, formatter: moneyK } },
    series,
  }, { replaceMerge: ["series"] });
}

function renderTendenciaAhorro() {
  const ch = ensureChart("chart-ahorro"); if (!ch) return;
  const s = state.overview.serie;
  ch.setOption({
    grid: { left: 8, right: 14, top: 18, bottom: 4, containLabel: true },
    tooltip: { trigger: "axis", ...baseTooltip },
    xAxis: { type: "category", data: s.map((x) => mesCorto(x.periodo)), ...baseAxis, splitLine: { show: false } },
    yAxis: { type: "value", ...baseAxis, axisLabel: { ...baseAxis.axisLabel, formatter: moneyK } },
    series: [{
      type: "bar", data: s.map((x) => x.ahorro), barWidth: "46%",
      itemStyle: { borderRadius: [4, 4, 4, 4], color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
        { offset: 0, color: C.violet }, { offset: 1, color: "rgba(168,85,247,0.25)" }]) },
    }],
  });
}

/* ---------- render de vistas ---------- */
function renderKPIs() {
  const k = state.overview.kpis;
  $("#kpi-ingreso").textContent = money(k.ingreso_mes);
  $("#kpi-gasto").textContent = money(k.gasto_mes);
  $("#kpi-ahorro").textContent = money(k.ahorro_mes);
  $("#kpi-tasa").textContent = pct(k.tasa_ahorro);
  $("#mes-actual").textContent = state.overview.mes_actual;
  $("#mes-cat").textContent = state.overview.mes_actual;
}

function renderSobres() {
  const grid = $("#sobres-grid");
  grid.innerHTML = state.overview.sobres.map((s) => {
    const ratio = s.asignado > 0 ? Math.min(s.gastado / s.asignado, 1) : (s.gastado > 0 ? 1 : 0);
    return `<div class="sobre">
      <div class="sobre-top">
        <span class="sobre-name">${s.nombre}</span>
        <span class="sobre-tag tag-${s.estado}">${s.estado}</span>
      </div>
      <div class="bar"><span class="fill-${s.estado}" style="width:${(ratio * 100).toFixed(0)}%"></span></div>
      <div class="sobre-foot"><span>Gastado <b>${money(s.gastado)}</b></span><span>de <b>${money(s.asignado)}</b></span></div>
    </div>`;
  }).join("");
}

function renderMovTable() {
  const tb = $("#mov-tbody");
  if (!state.movs.length) { tb.innerHTML = `<tr><td colspan="5" class="empty">Sin movimientos todavía.</td></tr>`; return; }
  tb.innerHTML = state.movs.map((m) => {
    const etiqueta = m.tipo === "gasto"
      ? `<span class="pill">${m.sobre || "—"}</span> <span class="pill">${m.categoria || "—"}</span>`
      : `<span class="pill">${m.fuente_ingreso || "ingreso"}</span>`;
    const signo = m.tipo === "ingreso" ? "+" : "−";
    const cls = m.tipo === "ingreso" ? "amount-in" : "amount-out";
    const detalle = `${m.descripcion}${m.comercio ? ` · <span class="muted">${m.comercio}</span>` : ""}`;
    const editing = state.editId === m.id ? " editing" : "";
    return `<tr class="mov-row${editing}">
      <td>${fechaCorta(m.fecha)}</td>
      <td>${detalle}</td>
      <td>${etiqueta}</td>
      <td class="num ${cls}">${signo}${money(m.monto)}</td>
      <td><div class="row-actions">
        <button class="row-edit" data-edit="${m.id}" title="Editar">✎</button>
        <button class="row-del" data-id="${m.id}" title="Eliminar">✕</button>
      </div></td>
    </tr>`;
  }).join("");
}

function ringSVG(p, color) {
  const r = 42, c = 2 * Math.PI * r, off = c * (1 - p);
  return `<svg class="ring" viewBox="0 0 100 100">
    <circle cx="50" cy="50" r="${r}" fill="none" stroke="rgba(120,160,220,0.14)" stroke-width="8"/>
    <circle cx="50" cy="50" r="${r}" fill="none" stroke="${color}" stroke-width="8" stroke-linecap="round"
      stroke-dasharray="${c}" stroke-dashoffset="${off}" transform="rotate(-90 50 50)"
      style="transition:stroke-dashoffset .6s ease"/>
    <text x="50" y="55" text-anchor="middle" fill="${C.txt}" font-family="ui-monospace,monospace" font-size="17" font-weight="700">${pct(p)}</text>
  </svg>`;
}

function metaTargetText(m) {
  if (m.fecha_objetivo_manual) return "fecha " + mesAnio(m.fecha_objetivo);
  if (m.edad_objetivo != null) return "antes de los " + m.edad_objetivo;
  return "sin fecha límite";
}
function metaMensaje(m) {
  if (m.completada) return { msg: "🎉 Meta cubierta por tu patrimonio actual.", cls: "msg-ok" };
  if (!m.fecha_estimada) {
    return { msg: "Aún no hay ahorro suficiente para estimar una fecha. Separa dinero cada mes.", cls: "msg-warn" };
  }
  const e = m.edad_estimada;
  const edad = e ? ` (a los ${e.anios} años y ${e.meses} meses)` : "";
  const base = `A este ritmo la logras <b>${mesAnio(m.fecha_estimada)}</b>${edad}.`;
  if (m.fecha_objetivo && m.en_camino === false) {
    return { msg: `${base} Para cumplir tu fecha objetivo, ahorra <b>${money(m.ahorro_necesario)}/mes</b>.`, cls: "msg-warn" };
  }
  if (m.fecha_objetivo) return { msg: `${base} ¡Vas en camino! 🟢`, cls: "msg-ok" };
  return { msg: base, cls: "msg-ok" };
}
function renderMetasGrid() {
  const grid = $("#metas-grid");
  const metas = state.overview.metas;
  if (!metas.length) {
    grid.innerHTML = `<div class="card glass empty">Aún no tienes metas. Crea una con “＋ Nueva meta”.</div>`;
    return;
  }
  grid.innerHTML = metas.map((m, idx) => {
    const color = m.completada ? C.green : (m.en_camino === false ? C.amber : C.cyan);
    const badge = m.completada ? `<span class="meta-badge badge-done">completada</span>`
      : (m.es_proxima ? `<span class="meta-badge badge-proxima">en curso</span>` : "");
    const { msg, cls } = metaMensaje(m);
    return `<div class="card glass meta-card">
      <div class="meta-head">
        <span class="meta-prio" title="Prioridad ${m.prioridad}">${m.prioridad}</span>
        <span class="meta-ico">${m.emoji}</span>
        <h3 class="meta-title">${m.nombre} ${badge}
          <small>Meta ${money(m.monto_objetivo)} · ${metaTargetText(m)}</small>
        </h3>
        <div class="meta-actions">
          <button class="icon-btn" data-mover="arriba" data-id="${m.id}" title="Subir prioridad" ${idx === 0 ? "disabled" : ""}>▲</button>
          <button class="icon-btn" data-mover="abajo" data-id="${m.id}" title="Bajar prioridad" ${idx === metas.length - 1 ? "disabled" : ""}>▼</button>
          <button class="icon-btn" data-editmeta="${m.id}" title="Editar">✎</button>
          <button class="icon-btn danger" data-delmeta="${m.id}" title="Eliminar">✕</button>
        </div>
      </div>
      <div class="ring-wrap">
        ${ringSVG(m.progreso, color)}
        <div class="meta-stats">
          <div class="stat"><span>Ahorrado</span><b>${money(m.ahorrado)}</b></div>
          <div class="stat"><span>Falta</span><b>${money(m.restante)}</b></div>
          <div class="stat"><span>Fecha objetivo</span><b>${m.fecha_objetivo ? mesAnio(m.fecha_objetivo) : "—"}</b></div>
          <div class="stat"><span>Estimada</span><b>${m.fecha_estimada ? mesAnio(m.fecha_estimada) : "—"}</b></div>
        </div>
      </div>
      <div class="meta-msg ${cls}">${msg}</div>
    </div>`;
  }).join("");
}

/* ---------- insights (Resumen) ---------- */
function renderInsights() {
  const cont = $("#insights-list");
  const ins = state.overview.insights || [];
  if (!ins.length) { cont.innerHTML = `<div class="insight empty">Sin novedades por ahora.</div>`; return; }
  cont.innerHTML = ins.map((i) =>
    `<div class="insight ${i.nivel}"><span class="ins-dot"></span><span>${i.texto}</span></div>`
  ).join("");
}

/* ---------- predicciones (patrimonio + simulador de cascada) ---------- */
function renderPredDom() {
  const p = state.overview.prediccion;
  $("#pred-pool").textContent = money(p.pool);
  $("#pred-pool-sub").textContent = p.saldo_inicial > 0
    ? `incluye ${money(p.saldo_inicial)} de saldo inicial`
    : "ahorro histórico acumulado";
  $("#pred-ahorro").textContent = money(p.ahorro_promedio);
  const prox = p.proxima;
  const val = $("#pred-proxima");
  val.classList.add("small");
  if (prox) {
    val.textContent = `${prox.emoji} ${prox.nombre}`;
    $("#pred-proxima-sub").textContent = `${money(prox.restante)} restante · ${Math.round(prox.progreso * 100)}%`;
  } else {
    val.textContent = p.todo_completado ? "¡Completadas!" : "—";
    $("#pred-proxima-sub").textContent = p.todo_completado ? "todas cubiertas por tu patrimonio" : "sin metas activas";
  }
  renderSimTimeline();
}

function renderSimTimeline() {
  const cont = $("#sim-timeline");
  if (!cont || !state.overview) return;
  const p = state.overview.prediccion;
  const metas = state.overview.metas;
  const hoy = state.overview.hoy;
  const delta = +($("#sim-delta")?.value || 0);
  const rate = p.ahorro_promedio;
  const rateSim = rate + delta;
  const pool = p.pool;
  if (!metas.length) { cont.innerHTML = `<p class="muted">Agrega metas para ver la proyección secuencial.</p>`; return; }
  let cum = 0;
  cont.innerHTML = metas.map((m) => {
    cum += m.monto_objetivo;
    const falta = Math.max(cum - pool, 0);
    const done = falta <= 0;
    const mesesBase = done ? 0 : (rate > 0 ? Math.ceil(falta / rate) : null);
    const mesesSim = done ? 0 : (rateSim > 0 ? Math.ceil(falta / rateSim) : null);
    const fBase = mesesBase != null ? addMonths(hoy, mesesBase) : null;
    const fSim = mesesSim != null ? addMonths(hoy, mesesSim) : null;
    const gan = (mesesBase != null && mesesSim != null) ? Math.max(mesesBase - mesesSim, 0) : 0;
    let dates;
    if (done) dates = `<span class="tl-dates">ya cubierta ✅</span>`;
    else if (!fBase) dates = `<span class="tl-dates">necesitas empezar a ahorrar</span>`;
    else if (delta > 0 && fSim && fSim !== fBase) dates = `<span class="tl-dates">${mesAnio(fBase)} <span class="arrow">→</span> ${mesAnio(fSim)}</span>`;
    else dates = `<span class="tl-dates">estimada ${mesAnio(fBase)}</span>`;
    const gain = (delta > 0 && gan > 0) ? `<span class="tl-gain">${gan} meses antes</span>` : "";
    return `<div class="tl-item${done ? " done" : ""}">
      <span class="tl-emoji">${m.emoji}</span>
      <div class="tl-body"><div class="tl-name">${m.nombre}</div>${dates}</div>
      ${gain}
    </div>`;
  }).join("");
}

/* ---------- metas: modal (crear/editar) + acciones ---------- */
const EMOJIS = ["🚗", "🏠", "🚁", "✈️", "🏍️", "💻", "📱", "🎓", "💍", "🏖️", "⌚", "🎸", "📷", "🚲"];
function fillEmojiSuggest() {
  $("#emoji-suggest").innerHTML = EMOJIS.map((e) => `<button type="button" class="emoji-chip" data-emoji="${e}">${e}</button>`).join("");
}
function setMetaFechaTipo(tipo) {
  $$("#meta-fecha-seg .seg-btn").forEach((b) => b.classList.toggle("active", b.dataset.fecha === tipo));
  $$(".meta-fecha-input").forEach((el) => (el.hidden = el.dataset.for !== tipo));
}
function openMetaModal(meta) {
  const m = meta || null;
  $("#meta-modal-title").textContent = m ? "Editar meta" : "Nueva meta";
  $("#meta-id").value = m ? m.id : "";
  $("#meta-emoji").value = m ? m.emoji : "🎯";
  $("#meta-nombre").value = m ? m.nombre : "";
  $("#meta-monto").value = m ? m.monto_objetivo : "";
  $("#meta-edad").value = "";
  $("#meta-fecha").value = "";
  $("#meta-error").hidden = true;
  let tipo = "edad";
  if (m && m.fecha_objetivo_manual) { tipo = "fecha"; $("#meta-fecha").value = m.fecha_objetivo_manual; }
  else if (m && m.edad_objetivo != null) { tipo = "edad"; $("#meta-edad").value = m.edad_objetivo; }
  else if (m) { tipo = "none"; }
  setMetaFechaTipo(tipo);
  $("#meta-modal").hidden = false;
  setTimeout(() => $("#meta-nombre").focus(), 40);
}
function closeMetaModal() { $("#meta-modal").hidden = true; }
async function saveMeta(ev) {
  ev.preventDefault();
  const err = $("#meta-error"); err.hidden = true;
  const id = $("#meta-id").value;
  const tipo = $("#meta-fecha-seg .seg-btn.active").dataset.fecha;
  const payload = {
    nombre: $("#meta-nombre").value.trim(),
    monto_objetivo: parseFloat($("#meta-monto").value),
    emoji: $("#meta-emoji").value.trim() || null,
    edad_objetivo: tipo === "edad" ? (parseInt($("#meta-edad").value, 10) || null) : null,
    fecha_objetivo: tipo === "fecha" ? ($("#meta-fecha").value || null) : null,
  };
  if (!payload.nombre || !(payload.monto_objetivo > 0)) {
    err.textContent = "Pon un nombre y un monto válido."; err.hidden = false; return;
  }
  try {
    if (id) {
      await api("/api/metas/" + id, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    } else {
      await api("/api/metas", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    }
    closeMetaModal();
    await refresh();
  } catch (e) { err.textContent = e.message; err.hidden = false; }
}
async function moverMeta(id, hacia) {
  try { await api(`/api/metas/${id}/mover?hacia=${hacia}`, { method: "POST" }); await refresh(); } catch (e) { /* noop */ }
}
async function deleteMeta(id) {
  const m = state.overview.metas.find((x) => x.id == id);
  if (!window.confirm(`¿Eliminar la meta "${m ? m.nombre : ""}"?`)) return;
  try { await api("/api/metas/" + id, { method: "DELETE" }); await refresh(); } catch (e) { /* noop */ }
}

/* ---------- formulario de movimientos ---------- */
function populateForm() {
  if (!state.catalogos) return;
  $("#f-sobre").innerHTML = state.catalogos.sobres.map((s) => `<option value="${s}">${s}</option>`).join("");
  $("#f-categoria").innerHTML = state.catalogos.categorias.map((c) => `<option value="${c}">${c}</option>`).join("");
  $("#f-fuente").innerHTML = state.catalogos.fuentes_ingreso.map((f) => `<option value="${f}">${f}</option>`).join("");
  if (!$("#f-fecha").value) $("#f-fecha").value = (state.overview ? state.overview.hoy : new Date().toISOString().slice(0, 10));
}
function setTipo(tipo) {
  $("#f-tipo").value = tipo;
  $$("#tipo-seg .seg-btn").forEach((b) => b.classList.toggle("active", b.dataset.tipo === tipo));
  const esGasto = tipo === "gasto";
  $$(".gasto-only").forEach((el) => (el.hidden = !esGasto));
  $$(".ingreso-only").forEach((el) => (el.hidden = esGasto));
}
function enterEditMode(m) {
  state.editId = m.id;
  setTipo(m.tipo);
  $("#f-monto").value = m.monto;
  $("#f-fecha").value = m.fecha;
  $("#f-desc").value = m.descripcion;
  $("#f-comercio").value = m.comercio || "";
  if (m.tipo === "gasto") {
    if (m.sobre) $("#f-sobre").value = m.sobre;
    if (m.categoria) $("#f-categoria").value = m.categoria;
  } else if (m.fuente_ingreso) {
    $("#f-fuente").value = m.fuente_ingreso;
  }
  $("#mov-form-title").textContent = "Editar movimiento";
  $("#mov-submit").textContent = "Guardar cambios";
  $("#mov-cancel-edit").hidden = false;
  $(".form-card").classList.add("editing");
  renderMovTable();
  $(".form-card").scrollIntoView({ behavior: "smooth", block: "nearest" });
}
function exitEditMode() {
  state.editId = null;
  $("#mov-form-title").textContent = "Agregar";
  $("#mov-submit").textContent = "Registrar";
  $("#mov-cancel-edit").hidden = true;
  $(".form-card").classList.remove("editing");
  $("#f-monto").value = ""; $("#f-desc").value = ""; $("#f-comercio").value = "";
  $("#mov-error").hidden = true;
  renderMovTable();
}
async function submitMov(ev) {
  ev.preventDefault();
  const err = $("#mov-error"); err.hidden = true;
  const tipo = $("#f-tipo").value;
  const payload = {
    tipo, monto: parseFloat($("#f-monto").value), fecha: $("#f-fecha").value,
    descripcion: $("#f-desc").value, comercio: $("#f-comercio").value || null,
  };
  if (tipo === "gasto") { payload.sobre = $("#f-sobre").value; payload.categoria = $("#f-categoria").value; }
  else { payload.fuente_ingreso = $("#f-fuente").value; }
  const headers = { "Content-Type": "application/json" };
  try {
    if (state.editId) {
      await api("/api/movimientos/" + state.editId, { method: "PUT", headers, body: JSON.stringify(payload) });
      exitEditMode();
    } else {
      await api("/api/movimientos", { method: "POST", headers, body: JSON.stringify(payload) });
      $("#f-monto").value = ""; $("#f-desc").value = ""; $("#f-comercio").value = "";
    }
    await refresh();
  } catch (e) { err.textContent = "No se pudo guardar: " + e.message; err.hidden = false; }
}
async function deleteMov(id) {
  try {
    await api("/api/movimientos/" + id, { method: "DELETE" });
    if (state.editId === Number(id)) exitEditMode();
    await refresh();
  } catch (e) { /* noop */ }
}

/* ---------- navegación + refresco ---------- */
const TITLES = { resumen: "Resumen", movimientos: "Movimientos", metas: "Metas", predicciones: "Predicciones" };
function showView(view) {
  state.activeView = view;
  $$(".nav-item").forEach((b) => b.classList.toggle("active", b.dataset.view === view));
  $$(".view").forEach((v) => v.classList.toggle("active", v.dataset.view === view));
  $("#view-title").textContent = TITLES[view];
  const sa = document.querySelector(".scroll-area");
  if (sa) sa.scrollTop = 0;
  renderActiveCharts();
}
function renderActiveCharts() {
  if (!state.overview) return;
  if (state.activeView === "resumen") { renderFlujo(); renderCategorias(); }
  if (state.activeView === "predicciones") { renderProyeccion(); renderTendenciaAhorro(); }
  requestAnimationFrame(() => Object.values(charts).forEach((c) => c.resize()));
}

async function refresh() {
  state.overview = await api("/api/overview");
  const q = "/api/movimientos?limit=100" + (state.filtro ? "&tipo=" + state.filtro : "");
  state.movs = await api(q);
  renderKPIs(); renderInsights(); renderSobres(); renderMovTable();
  renderMetasGrid(); renderPredDom(); populateForm();
  renderActiveCharts();
}

/* ---------- refresco con confirmación visual ---------- */
function showToast(msg, ok = true) {
  const t = $("#toast");
  if (!t) return;
  $("#toast-msg").textContent = msg;
  t.querySelector(".toast-ico").textContent = ok ? "✓" : "⚠";
  t.querySelector(".toast-ico").style.color = ok ? "var(--green)" : "var(--amber)";
  t.classList.add("show");
  clearTimeout(state.toastTimer);
  state.toastTimer = setTimeout(() => t.classList.remove("show"), 1800);
}

async function refreshWithFeedback() {
  const fab = $("#fab-refresh");
  if (fab) fab.classList.add("is-loading");
  const t0 = Date.now();
  try {
    await refresh();
    // garantiza que el giro se vea aunque la respuesta sea instantánea
    const espera = Math.max(0, 450 - (Date.now() - t0));
    await new Promise((r) => setTimeout(r, espera));
    if (fab) {
      fab.classList.remove("is-loading");
      fab.classList.add("is-done");
      setTimeout(() => fab.classList.remove("is-done"), 1100);
    }
    showToast("Datos actualizados");
  } catch (e) {
    if (fab) fab.classList.remove("is-loading");
    showToast("Error al actualizar", false);
  }
}

async function init() {
  try {
    state.catalogos = await api("/api/catalogos");
  } catch (e) { return; }
  setTipo("gasto");

  // navegación
  $$(".nav-item").forEach((b) => b.addEventListener("click", () => showView(b.dataset.view)));
  $("#btn-refresh").addEventListener("click", refreshWithFeedback);
  $("#fab-refresh").addEventListener("click", refreshWithFeedback);

  // formulario de movimientos (agregar/editar)
  $$("#tipo-seg .seg-btn").forEach((b) => b.addEventListener("click", () => setTipo(b.dataset.tipo)));
  $("#mov-form").addEventListener("submit", submitMov);
  $("#mov-cancel-edit").addEventListener("click", exitEditMode);
  $("#mov-tbody").addEventListener("click", (ev) => {
    const del = ev.target.closest(".row-del");
    if (del) { deleteMov(del.dataset.id); return; }
    const ed = ev.target.closest(".row-edit");
    if (ed) { const m = state.movs.find((x) => x.id == ed.dataset.edit); if (m) enterEditMode(m); }
  });

  // filtro de la tabla
  $$("#filtro-seg .seg-btn").forEach((b) => b.addEventListener("click", () => {
    $$("#filtro-seg .seg-btn").forEach((x) => x.classList.toggle("active", x === b));
    state.filtro = b.dataset.filtro;
    refresh();
  }));

  // metas: crear / editar / reordenar / eliminar
  $("#btn-nueva-meta").addEventListener("click", () => openMetaModal(null));
  $("#metas-grid").addEventListener("click", (ev) => {
    const mv = ev.target.closest("[data-mover]");
    if (mv) { moverMeta(mv.dataset.id, mv.dataset.mover); return; }
    const ed = ev.target.closest("[data-editmeta]");
    if (ed) { const m = state.overview.metas.find((x) => x.id == ed.dataset.editmeta); if (m) openMetaModal(m); return; }
    const dl = ev.target.closest("[data-delmeta]");
    if (dl) { deleteMeta(dl.dataset.delmeta); }
  });

  // modal de meta
  fillEmojiSuggest();
  $("#meta-form").addEventListener("submit", saveMeta);
  $("#meta-modal-close").addEventListener("click", closeMetaModal);
  $("#meta-cancel").addEventListener("click", closeMetaModal);
  $("#meta-modal").addEventListener("click", (ev) => { if (ev.target.id === "meta-modal") closeMetaModal(); });
  $$("#meta-fecha-seg .seg-btn").forEach((b) => b.addEventListener("click", () => setMetaFechaTipo(b.dataset.fecha)));
  $("#emoji-suggest").addEventListener("click", (ev) => {
    const c = ev.target.closest(".emoji-chip");
    if (c) $("#meta-emoji").value = c.dataset.emoji;
  });

  // simulador de cascada (cliente: reacciona en vivo)
  $("#sim-delta").addEventListener("input", () => {
    $("#sim-delta-label").textContent = money(+$("#sim-delta").value);
    if (state.overview) { renderProyeccion(); renderSimTimeline(); }
  });

  window.addEventListener("keydown", (ev) => { if (ev.key === "Escape") closeMetaModal(); });
  window.addEventListener("resize", () => Object.values(charts).forEach((c) => c.resize()));
  // refresco suave por si el bot agrega algo desde Telegram
  setInterval(() => { if (document.visibilityState === "visible") refresh(); }, 60000);

  await refresh();
}

document.addEventListener("DOMContentLoaded", init);
