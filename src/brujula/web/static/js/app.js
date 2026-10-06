/* Brújula — dashboard. Fetch + render + ECharts. Re-renderiza al instante tras cada cambio. */
"use strict";

const C = {
  accent: "#d97757", violet: "#9b8afb", green: "#6cc08b",
  amber: "#e0b252", red: "#e2725f", blue: "#7aa2d4", teal: "#5fb3a8", pink: "#c98ab0",
  txt: "#ececee", muted: "#9a9aa2", grid: "rgba(255,255,255,0.07)",
};
const MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];

/* Preferencias locales de este navegador (no salen del dispositivo). */
const PREFS_KEY = "brujula.prefs";
const PREFS_DEF = { privado: true, autorefresh: true, rango: "mes" };
const TOAST_DURATION_MS = 7000;
function loadPrefs() {
  try { return { ...PREFS_DEF, ...JSON.parse(localStorage.getItem(PREFS_KEY) || "{}") }; }
  catch (_) { return { ...PREFS_DEF }; }
}
function savePrefs(p) {
  try { localStorage.setItem(PREFS_KEY, JSON.stringify(p)); } catch (_) { /* modo privado */ }
}

const state = {
  overview: null, catalogos: null, movs: [], transfers: [], filtro: "", filtroCat: "",
  filtroCuenta: "", activeView: "resumen",
  loanGroups: [], loanTotals: { por_cobrar: 0, por_pagar: 0 },
  editId: null, editKind: null, prefs: loadPrefs(),
  // Periodo del Resumen: arranca en el último mes CON datos.
  resRange: { preset: "mes", desde: null, hasta: null },
  movRange: { preset: "mes", desde: null, hasta: null },
  repRange: { preset: "mes", desde: null, hasta: null },
  dias: { dias: [], meses: [], primero: null, ultimo: null,
    primero_contable: null, ultimo_contable: null, total: 0 },
  diasSet: new Set(),
  cfgCats: [], cfgCatsBase: [], autoTimer: null, cfgHistModo: "mes",
  cfgFuentes: [], cfgFuentesBase: [], cfgCatFlujo: "egreso",
  cfgAccounts: [], cfgAccountsBase: [],
};
const charts = {};

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];

/* ---------- utilidades ---------- */
async function api(path, opts = {}) {
  const headers = new Headers(opts.headers || {});
  if (state.databaseIdentity) headers.set("X-Brujula-Database", state.databaseIdentity);
  const res = await fetch(path, { credentials: "same-origin", ...opts, headers });
  const identity = res.headers.get("X-Brujula-Database");
  if (identity && state.databaseIdentity && identity !== state.databaseIdentity) {
    throw new Error("La base de datos cambió. Revisa la conexión antes de continuar.");
  }
  if (identity) state.databaseIdentity = identity;
  if (res.status === 401) { window.location.href = "/login"; throw new Error("401"); }
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (_) {}
    throw new Error(typeof detail === "string" ? detail : "Error de validación");
  }
  return res.status === 204 ? null : res.json();
}
const jsonReq = (method, body) => ({
  method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
});
const money = (n) => "$" + Number(n || 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const moneyK = (n) => Math.abs(n) >= 1000 ? "$" + (n / 1000).toFixed(1) + "k" : "$" + Math.round(n);
const pct = (n) => (Number(n || 0) * 100).toFixed(0) + "%";
const mesCorto = (p) => { const [y, m] = p.split("-"); return MESES[+m - 1] + (m === "01" ? " " + y.slice(2) : ""); };
const fechaCorta = (iso) => { const [, m, d] = iso.split("-"); return `${d}/${m}`; };
const fmtDMY = (iso) => { if (!iso) return "—"; const [y, m, d] = iso.split("-"); return `${d}/${m}/${y}`; };
const MESES_LARGO = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
  "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"];
const mesLargo = (iso) => { const [y, m] = iso.split("-"); return `${MESES_LARGO[+m - 1]} ${y}`; };
const finDeMes = (iso) => {
  const [y, m] = iso.split("-").map(Number);
  return `${y}-${String(m).padStart(2, "0")}-${String(new Date(y, m, 0).getDate()).padStart(2, "0")}`;
};
const primerDia = (iso) => iso.slice(0, 7) + "-01";
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

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
  backgroundColor: "#1d1d21", borderColor: "rgba(255,255,255,0.14)",
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
      { name: "Ingreso", type: "bar", data: s.map((x) => x.ingreso), barWidth: 12, itemStyle: { borderRadius: [3, 3, 0, 0], color: C.blue } },
      { name: "Gasto", type: "bar", data: s.map((x) => x.gasto), barWidth: 12, itemStyle: { borderRadius: [3, 3, 0, 0], color: C.accent } },
      { name: "Ahorro", type: "line", smooth: true, data: s.map((x) => x.ahorro), symbol: "circle", symbolSize: 6, lineStyle: { color: C.green, width: 2.5 }, itemStyle: { color: C.green } },
    ],
  });
}

function renderDistribucion() {
  const ch = ensureChart("chart-sobres"); if (!ch) return;
  const cats = state.overview.distribucion;
  const palette = [C.accent, C.blue, C.green, C.amber, C.violet, C.teal, C.pink, C.red];
  ch.setOption({
    tooltip: { trigger: "item", ...baseTooltip },
    legend: { type: "scroll", bottom: 0, textStyle: { color: C.muted }, icon: "circle" },
    series: [{
      type: "pie", radius: ["52%", "74%"], center: ["50%", "44%"], avoidLabelOverlap: true,
      itemStyle: { borderColor: "#17171a", borderWidth: 3 },
      label: { show: false }, labelLine: { show: false },
      data: cats.length
        ? cats.map((c, i) => ({ name: c.nombre, value: c.monto, itemStyle: { color: palette[i % palette.length] } }))
        : [{ name: "Sin gastos", value: 1, itemStyle: { color: "#2a2a30" } }],
    }],
  });
}

/* ---------- render de vistas ---------- */
/* Texto humano del periodo activo: "mayo 2026", "16/05/2026" o "01/04 → 16/05/2026". */
function periodoTexto(p, largo = true) {
  if (!p) return "—";
  if (p.desde === p.hasta) return fmtDMY(p.desde);
  if (p.mes_exacto || (p.desde && p.desde === primerDia(p.desde) && p.hasta === finDeMes(p.desde))) {
    return largo ? mesLargo(p.desde) : p.desde.slice(0, 7);
  }
  return `${fmtDMY(p.desde)} → ${fmtDMY(p.hasta)}`;
}

function renderKPIs() {
  const k = state.overview.kpis;
  $("#kpi-ingreso").textContent = money(k.ingreso_mes);
  $("#kpi-gasto").textContent = money(k.gasto_mes);
  $("#kpi-ahorro").textContent = money(k.ahorro_mes);
  $("#kpi-tasa").textContent = pct(k.tasa_ahorro);
  $("#kpi-cuentas").textContent = money(state.overview.cuentas.total);
  const accounts = state.overview.cuentas.items;
  $("#account-balance-grid").innerHTML = accounts.map((a) => `
    <div class="account-balance${a.activa ? "" : " inactive"}">
      <span>${esc(a.nombre)}</span><strong class="amount">${money(a.saldo)}</strong>
    </div>`).join("");
  const p = state.overview.periodo;
  if (state.activeView === "resumen") $("#periodo-lbl").textContent = periodoTexto(p);
  $("#mes-cat").textContent = periodoTexto(p, false);
}

function renderSobres() {
  const grid = $("#sobres-grid");
  // El tope y el semáforo son SOLO del mes; el arrastre va aparte porque es margen extra
  // (lo que puedes pasarte sin problema), no parte del tope.
  const sp = state.overview.sobres_periodo;
  if (sp) $("#sobres-mes").textContent = `${periodoTexto(sp)} · topes mensuales · arrastre anterior al ${fmtDMY(sp.arrastre_antes_de)}`;
  grid.innerHTML = state.overview.sobres.map((s) => {
    const arr = s.arrastre || 0;
    // La barra se llena contra el margen real (tope + arrastre), igual que el semáforo.
    const base = s.asignado + arr;
    const ratio = base > 0 ? Math.min(s.gastado / base, 1) : (s.gastado > 0 ? 1 : 0);
    const tope = s.estado === "libre" ? "<b>sin tope</b>" : `de <b>${money(s.asignado)}</b>`;
    const arrLinea = s.estado === "libre" || Math.abs(arr) < 0.005 ? "" :
      `<div class="sobre-arr">arrastre <b class="${arr > 0 ? "arr-pos" : "arr-neg"}">${arr > 0 ? "+" : "−"}${money(Math.abs(arr))}</b></div>`;
    return `<div class="sobre">
      <div class="sobre-top">
        <span class="sobre-name">${esc(s.nombre)}</span>
        <span class="sobre-tag tag-${s.estado}">${s.estado}</span>
      </div>
      <div class="bar"><span class="fill-${s.estado}" style="width:${(ratio * 100).toFixed(0)}%"></span></div>
      <div class="sobre-foot"><span>Gastado <b>${money(s.gastado)}</b></span><span>${tope}</span></div>
      ${arrLinea}
    </div>`;
  }).join("");
}

function renderMovTable() {
  const loanView = state.filtro === "prestamo";
  $("#loan-groups").hidden = !loanView;
  $("#mov-table-wrap").hidden = loanView;
  if (loanView) { renderLoanGroups(); return; }
  const tb = $("#mov-tbody");
  if (!state.movs.length) { tb.innerHTML = `<tr><td colspan="6" class="empty">Sin movimientos todavía.</td></tr>`; return; }
  tb.innerHTML = state.movs.map((m) => {
    const transfer = m.tipo === "transferencia";
    const etiqueta = transfer ? `<span class="pill">transferencia</span>` : m.tipo === "gasto"
      ? `<span class="pill">${esc(m.categoria || "—")}</span>`
      : `<span class="pill">${esc(m.fuente_ingreso || "ingreso")}</span>`;
    const signo = transfer ? "" : (m.tipo === "ingreso" ? "+" : "−");
    const cls = transfer ? "" : (m.tipo === "ingreso" ? "amount-in" : "amount-out");
    const editing = state.editId === m.id ? " editing" : "";
    let loanState = "";
    if (m.prestamo) {
      const p = m.prestamo;
      const labels = { pagado: "Pagado", abonado: `Resta ${money(p.saldo)}`,
        pendiente: `Pendiente ${money(p.saldo)}`, aplicado: `Pago aplicado ${money(p.aplicado)}` };
      loanState = `<span class="loan-state loan-${p.estado}">${labels[p.estado] || esc(p.estado)}</span>`;
    }
    return `<tr class="mov-row${editing}">
      <td>${fechaCorta(m.fecha)}</td>
      <td>${esc(m.descripcion)}${loanState}</td>
      <td>${etiqueta}</td>
      <td>${transfer ? `${esc(m.source_account)} → ${esc(m.destination_account)}` : esc(m.cuenta || "—")}</td>
      <td class="num amount ${cls}">${signo}${money(m.monto)}</td>
      <td><div class="row-actions">
        <button class="row-edit" data-edit="${m.id}" data-kind="${transfer ? "transfer" : "movement"}" title="Editar">✎</button>
        <button class="row-del" data-id="${m.id}" data-kind="${transfer ? "transfer" : "movement"}" title="Eliminar">✕</button>
      </div></td>
    </tr>`;
  }).join("");
}

function renderLoanGroups() {
  const box = $("#loan-groups");
  const totals = state.loanTotals;
  const summary = `<div class="loan-summary">
    <div><span>Por cobrar</span><strong class="amount amount-in">${money(totals.por_cobrar)}</strong></div>
    <div><span>Por pagar</span><strong class="amount loan-payable">${money(totals.por_pagar)}</strong></div>
    <div><span>Personas</span><strong>${state.loanGroups.length}</strong></div>
  </div>`;
  if (!state.loanGroups.length) {
    box.innerHTML = summary + `<div class="loan-empty"><span>✓</span><b>Sin préstamos</b><small>No hay cuentas abiertas ni movimientos en este periodo.</small></div>`;
    return;
  }
  const cards = state.loanGroups.map((group) => {
    const statusText = group.direccion === "cobrar" ? "Te debe"
      : (group.direccion === "pagar" ? "Debes" : "Saldado");
    const saldoLabel = group.direccion === "cobrar" ? "Resta por cobrar"
      : (group.direccion === "pagar" ? "Resta por pagar" : "Cuenta pagada");
    const rows = group.movimientos.length ? group.movimientos.map((m) => {
      const p = m.prestamo;
      const action = p.rol === "pago"
        ? (m.tipo === "ingreso" ? "Abono recibido" : "Pago realizado")
        : (m.tipo === "gasto" ? "Préstamo entregado" : "Préstamo recibido");
      const states = { pagado: "Pagado", abonado: `Resta ${money(p.saldo)}`,
        pendiente: `Pendiente ${money(p.saldo)}`, aplicado: "Aplicado" };
      const sign = m.tipo === "ingreso" ? "+" : "−";
      const amountClass = m.tipo === "ingreso" ? "amount-in" : "amount-out";
      return `<div class="loan-movement${state.editId === m.id ? " editing" : ""}">
        <time>${fechaCorta(m.fecha)}</time>
        <div class="loan-mov-detail"><b>${action}</b><span class="loan-state loan-${p.estado}">${states[p.estado]}</span></div>
        <strong class="amount ${amountClass}">${sign}${money(m.monto)}</strong>
        <div class="row-actions">
          <button class="row-edit" data-edit="${m.id}" title="Editar">✎</button>
          <button class="row-del" data-id="${m.id}" title="Eliminar">✕</button>
        </div>
      </div>`;
    }).join("") : `<p class="loan-no-period">Sin movimientos dentro del periodo seleccionado.</p>`;
    return `<article class="loan-person ${group.estado}">
      <header class="loan-person-head">
        <span class="loan-avatar">${esc(group.persona.trim().charAt(0).toUpperCase() || "?")}</span>
        <div class="loan-person-name"><h3>${esc(group.persona)}</h3><span>${group.movimientos.length} movimiento(s) en el periodo</span></div>
        <span class="loan-direction loan-direction-${group.direccion}">${statusText}</span>
        <div class="loan-balance"><span>${saldoLabel}</span><strong class="amount">${money(group.saldo)}</strong></div>
      </header>
      <div class="loan-history">${rows}</div>
    </article>`;
  }).join("");
  box.innerHTML = summary + cards;
}

/* ---------- formulario de movimientos ---------- */
function populateForm() {
  if (!state.catalogos) return;
  const sel = $("#f-categoria");
  const previo = sel.value;
  sel.innerHTML = state.catalogos.categorias
    .map((s) => `<option value="${esc(s)}">${esc(s)}</option>`).join("");
  if (previo && state.catalogos.categorias.includes(previo)) sel.value = previo;
  const fuentePrevia = $("#f-fuente").value;
  $("#f-fuente").innerHTML = state.catalogos.fuentes_ingreso
    .map((f) => `<option value="${esc(f)}">${esc(f)}</option>`).join("");
  if (fuentePrevia && state.catalogos.fuentes_ingreso.includes(fuentePrevia)) {
    $("#f-fuente").value = fuentePrevia;
  }
  if (!$("#f-fecha").value) $("#f-fecha").value = (state.overview ? state.overview.hoy : new Date().toISOString().slice(0, 10));
  const accountOptions = state.catalogos.cuentas
    .map((a) => `<option value="${a.id}">${esc(a.nombre)}</option>`).join("");
  for (const id of ["#f-account", "#f-transfer-source", "#f-transfer-destination"]) {
    const select = $(id); const previous = select.value;
    select.innerHTML = `<option value="">Selecciona una cuenta</option>${accountOptions}`;
    if (previous && state.catalogos.cuentas.some((a) => String(a.id) === previous)) select.value = previous;
  }
  updateLoanDetailField();
}

const isLoanName = (value) => String(value || "").normalize("NFD")
  .replace(/[\u0300-\u036f]/g, "").toLowerCase().startsWith("prestamo");
function updateLoanDetailField() {
  const tipo = $("#f-tipo").value;
  if (tipo === "transferencia") {
    $("#f-desc-label").textContent = "Descripción";
    $("#f-desc").placeholder = "Ej. mover dinero a Binance";
    $("#loan-help").hidden = true;
    return;
  }
  const category = tipo === "gasto" ? $("#f-categoria").value : $("#f-fuente").value;
  const loan = isLoanName(category);
  $("#f-desc-label").textContent = loan ? "Persona" : "Descripción";
  $("#f-desc").placeholder = loan ? "Ej. Billy o Janaina" : "Ej. mercado, sueldo…";
  $("#loan-help").hidden = !loan;
}

/* ---------- filtro por categoría (Movimientos) ----------
   El valor lleva el tipo dentro ("gasto:pareja", "ingreso:trabajo") porque una categoría
   de egreso y una de ingreso pueden llamarse igual. */
function filtroCatPartes() {
  const i = state.filtroCat.indexOf(":");
  if (i < 0) return null;
  return { tipo: state.filtroCat.slice(0, i), nombre: state.filtroCat.slice(i + 1) };
}
function populateFiltroCat() {
  const sel = $("#filtro-cat");
  if (!sel || !state.catalogos) return;
  sel.hidden = state.filtro === "prestamo" || state.filtro === "transferencia";
  if (sel.hidden) { state.filtroCat = ""; return; }
  const sinPrestamos = (items) => (items || []).filter((name) => !isLoanName(name));
  const grupo = (label, tipo, items) => (items && items.length)
    ? `<optgroup label="${label}">` + items.map((n) =>
        `<option value="${tipo}:${esc(n)}">${esc(n)}</option>`).join("") + `</optgroup>`
    : "";
  let html = `<option value="">Todas las categorías</option>`;
  if (state.filtro !== "ingreso") html += grupo("Egresos", "gasto", sinPrestamos(state.catalogos.categorias));
  if (state.filtro !== "gasto") html += grupo("Ingresos", "ingreso", sinPrestamos(state.catalogos.fuentes_ingreso));
  sel.innerHTML = html;
  // Un filtro que ya no cabe (otro tipo, o categoría renombrada/borrada) se descarta.
  if (![...sel.options].some((o) => o.value === state.filtroCat)) state.filtroCat = "";
  sel.value = state.filtroCat;
}
function populateFiltroCuenta() {
  const sel = $("#filtro-cuenta");
  const options = (state.overview ? state.overview.cuentas.items : [])
    .map((a) => `<option value="${a.id}">${esc(a.nombre)}</option>`).join("");
  sel.innerHTML = `<option value="">Todas las cuentas</option>${options}`;
  if (![...sel.options].some((o) => o.value === state.filtroCuenta)) state.filtroCuenta = "";
  sel.value = state.filtroCuenta;
}
function setTipo(tipo) {
  $("#f-tipo").value = tipo;
  $$("#tipo-seg .seg-btn").forEach((b) => b.classList.toggle("active", b.dataset.tipo === tipo));
  const esTransferencia = tipo === "transferencia";
  const esGasto = tipo === "gasto";
  $$(".gasto-only").forEach((el) => (el.hidden = !esGasto));
  $$(".ingreso-only").forEach((el) => (el.hidden = tipo !== "ingreso"));
  $$(".movement-account").forEach((el) => (el.hidden = esTransferencia));
  $$(".transfer-only").forEach((el) => (el.hidden = !esTransferencia));
  $("#f-account").required = !esTransferencia;
  $("#f-transfer-source").required = esTransferencia;
  $("#f-transfer-destination").required = esTransferencia;
  $("#f-account-label").textContent = tipo === "ingreso" ? "Cuenta de destino" : "Cuenta de origen";
  updateLoanDetailField();
}
function enterEditMode(m) {
  if (state.savingMovement) return;
  state.editVersion = m.version;
  state.editId = m.id;
  state.editKind = m.tipo === "transferencia" ? "transfer" : "movement";
  setTipo(m.tipo);
  $("#f-monto").value = m.monto;
  $("#f-fecha").value = m.fecha;
  $("#f-desc").value = m.descripcion;
  if (m.tipo === "transferencia") {
    $("#f-transfer-source").value = m.source_account_id;
    $("#f-transfer-destination").value = m.destination_account_id;
  } else if (m.tipo === "gasto") {
    if (m.categoria) $("#f-categoria").value = m.categoria;
  } else if (m.fuente_ingreso) {
    $("#f-fuente").value = m.fuente_ingreso;
  }
  if (m.account_id) $("#f-account").value = m.account_id;
  updateLoanDetailField();
  $("#mov-form-title").textContent = "Editar movimiento";
  $("#mov-submit").textContent = "Guardar cambios";
  $("#mov-cancel-edit").hidden = false;
  $(".form-card").classList.add("editing");
  renderMovTable();
  $(".form-card").scrollIntoView({ behavior: "smooth", block: "nearest" });
}
function exitEditMode() {
  state.editId = null;
  state.editKind = null;
  $("#mov-form-title").textContent = "Agregar";
  $("#mov-submit").textContent = "Registrar";
  $("#mov-cancel-edit").hidden = true;
  $(".form-card").classList.remove("editing");
  $("#f-monto").value = ""; $("#f-desc").value = "";
  $("#mov-error").hidden = true;
  renderMovTable();
}
async function submitMov(ev) {
  ev.preventDefault();
  if (state.savingMovement) return;
  state.savingMovement = true;
  const err = $("#mov-error"); err.hidden = true;
  const btn = $("#mov-submit");
  btn.disabled = true;
  const tipo = $("#f-tipo").value;
  const payload = {
    tipo, monto: parseFloat($("#f-monto").value), fecha: $("#f-fecha").value,
    descripcion: $("#f-desc").value,
  };
  const transfer = tipo === "transferencia";
  if (transfer) {
    payload.source_account_id = Number($("#f-transfer-source").value);
    payload.destination_account_id = Number($("#f-transfer-destination").value);
  } else {
    payload.account_id = Number($("#f-account").value);
    if (tipo === "gasto") payload.categoria = $("#f-categoria").value;
    else payload.fuente_ingreso = $("#f-fuente").value;
  }
  const editing = Boolean(state.editId);
  const loan = !transfer && isLoanName(tipo === "gasto" ? payload.categoria : payload.fuente_ingreso);
  const item = loan ? "Préstamo" : (transfer ? "Transferencia" : (tipo === "gasto" ? "Gasto" : "Ingreso"));
  const savedLabel = transfer
    ? `Transferencia ${editing ? "actualizada" : "registrada"}`
    : `${item} ${editing ? "actualizado" : "registrado"}`;
  try {
    if (editing) {
      const base = state.editKind === "transfer" ? "/api/transferencias/" : "/api/movimientos/";
      const req = jsonReq("PUT", payload);
      if (state.editVersion) req.headers["If-Match"] = state.editVersion;
      await api(base + state.editId, req);
      exitEditMode();
    } else {
      await api(transfer ? "/api/transferencias" : "/api/movimientos", jsonReq("POST", payload));
      $("#f-monto").value = ""; $("#f-desc").value = "";
    }
  } catch (e) {
    err.textContent = "No se pudo guardar: " + e.message;
    err.hidden = false;
    showToast("No se pudo confirmar el guardado. Revisa los movimientos antes de reintentar. " + e.message, false);
    btn.disabled = false;
    state.savingMovement = false;
    return;
  }

  // La API responde únicamente después del commit. Desde este punto el dato sí quedó
  // persistido, aunque una recarga posterior de la vista pudiera fallar.
  showToast(`${savedLabel}. Guardado en la base de datos.`);
  try {
    await refresh();
    showToast(`${savedLabel}. Guardado en la base de datos.`);
  } catch (_) {
    setOnline(false);
    showToast("Guardado en la base de datos, pero no se pudo actualizar la pantalla.", false);
  } finally {
    btn.disabled = false;
    state.savingMovement = false;
  }
}
async function deleteMov(id, kind = "movement") {
  const m = state.movs.find((x) => x.id == id && (x.tipo === "transferencia") === (kind === "transfer"));
  const ok = await confirmDialog(
    `Se eliminará "${m ? m.descripcion : "este movimiento"}". Esta acción no se puede deshacer.`,
  );
  if (!ok) return;
  try {
    const base = kind === "transfer" ? "/api/transferencias/" : "/api/movimientos/";
    await api(base + id, { method: "DELETE" });
    if (state.editId === Number(id) && state.editKind === kind) exitEditMode();
    await refresh();
  } catch (e) { showToast("No se pudo eliminar", false); }
}

function handleMovRowAction(ev) {
  const del = ev.target.closest(".row-del");
  if (del) { deleteMov(del.dataset.id, del.dataset.kind); return; }
  const ed = ev.target.closest(".row-edit");
  if (!ed) return;
  const transfer = ed.dataset.kind === "transfer";
  const m = state.movs.find((x) => x.id == ed.dataset.edit &&
    (x.tipo === "transferencia") === transfer);
  if (m) enterEditMode(m);
}

/* ---------- categoría nueva desde el formulario (botón ＋) ---------- */
function toggleNewCat(show) {
  $("#new-cat").hidden = !show;
  $("#new-cat-name").value = "";
  if (show) $("#new-cat-name").focus();
}
async function crearCategoriaRapida() {
  const nombre = $("#new-cat-name").value.trim();
  if (!nombre) { toggleNewCat(false); return; }
  const err = $("#mov-error"); err.hidden = true;
  try {
    const cat = await api("/api/categorias", jsonReq("POST", { nombre }));
    state.catalogos = await api("/api/catalogos");
    populateForm();
    $("#f-categoria").value = cat.nombre;
    toggleNewCat(false);
    showToast(`Categoría "${cat.nombre}" creada`);
    await refresh();
  } catch (e) { err.textContent = e.message; err.hidden = false; }
}

function toggleNewFuente(show) {
  $("#new-fuente").hidden = !show;
  $("#new-fuente-name").value = "";
  if (show) $("#new-fuente-name").focus();
}
async function crearFuenteRapida() {
  const nombre = $("#new-fuente-name").value.trim();
  if (!nombre) { toggleNewFuente(false); return; }
  const err = $("#mov-error"); err.hidden = true;
  try {
    const f = await api("/api/fuentes", jsonReq("POST", { nombre }));
    state.catalogos = await api("/api/catalogos");
    populateForm();
    $("#f-fuente").value = f.nombre;
    toggleNewFuente(false);
    showToast(`Categoría de ingreso "${f.nombre}" creada`);
    await refresh();
  } catch (e) { err.textContent = e.message; err.hidden = false; }
}

/* ---------- Configuración (ventana flotante) ---------- */
const TIPOS_CAT = [
  ["fijo", "Monto fijo"],
  ["porcentaje", "% del ingreso"],
  ["residual", "El resto"],
];
function cfgShowPane(name) {
  $$(".cfg-tab").forEach((b) => b.classList.toggle("active", b.dataset.cfg === name));
  $$(".cfg-pane").forEach((p) => p.classList.toggle("active", p.dataset.cfg === name));
  const body = $(".cfg-body");
  if (body) body.scrollTop = 0;
}
function renderCfgCats() {
  const cont = $("#cfg-cats");
  const head = `<div class="cfg-cat-head">
    <span>Nombre</span><span>Tope</span><span>Valor</span><span>Uso</span><span></span>
  </div>`;
  if (!state.cfgCats.length) {
    cont.innerHTML = head + `<p class="muted">Aún no hay categorías. Agrega la primera abajo.</p>`;
    return;
  }
  cont.innerHTML = head + state.cfgCats.map((c, i) => {
    const base = state.cfgCatsBase.find((b) => b.id === c.id);
    const dirty = c._new || !base || base.nombre !== c.nombre || base.tipo !== c.tipo || base.valor !== c.valor;
    const opts = TIPOS_CAT.map(([v, t]) =>
      `<option value="${v}"${c.tipo === v ? " selected" : ""}>${t}</option>`).join("");
    const paso = c.tipo === "porcentaje" ? "0.1" : "1";
    const valor = c.tipo === "porcentaje" ? (c.valor * 100).toFixed(1).replace(/\.0$/, "") : c.valor;
    const disabled = c.tipo === "residual" ? " disabled" : "";
    const usos = c._new ? "nueva" : `${c.usos} mov.`;
    return `<div class="cfg-cat${dirty ? " dirty" : ""}" data-i="${i}">
      <input type="text" maxlength="30" data-f="nombre" value="${esc(c.nombre)}" placeholder="nombre" />
      <select data-f="tipo">${opts}</select>
      <input type="number" min="0" step="${paso}" data-f="valor" value="${disabled ? "" : valor}"${disabled} />
      <span class="cfg-usos">${usos}</span>
      <button type="button" class="cat-del" data-del="${i}" title="Eliminar categoría">✕</button>
    </div>`;
  }).join("");
}
/* --- Configuración › Categorías de ingreso (solo nombre) --- */
function cfgShowFlujo(flujo) {
  state.cfgCatFlujo = flujo;
  $$("#cfg-cat-flujo-seg .seg-btn").forEach((b) =>
    b.classList.toggle("active", b.dataset.flujo === flujo));
  $$(".cfg-flujo").forEach((p) => p.classList.toggle("active", p.dataset.flujo === flujo));
}
function renderCfgFuentes() {
  const cont = $("#cfg-fuentes");
  const head = `<div class="cfg-cat-head cfg-cat-in"><span>Nombre</span><span>Uso</span><span></span></div>`;
  if (!state.cfgFuentes.length) {
    cont.innerHTML = head + `<p class="muted">Aún no hay categorías de ingreso. Agrega la primera abajo.</p>`;
    return;
  }
  cont.innerHTML = head + state.cfgFuentes.map((f, i) => {
    const base = state.cfgFuentesBase.find((b) => b.id === f.id);
    const dirty = f._new || !base || base.nombre !== f.nombre;
    const usos = f._new ? "nueva" : `${f.usos} mov.`;
    return `<div class="cfg-cat cfg-cat-in${dirty ? " dirty" : ""}" data-i="${i}">
      <input type="text" maxlength="30" data-f="nombre" value="${esc(f.nombre)}" placeholder="nombre" />
      <span class="cfg-usos">${usos}</span>
      <button type="button" class="cat-del" data-del="${i}" title="Eliminar categoría de ingreso">✕</button>
    </div>`;
  }).join("");
}
function cfgFuenteInput(ev) {
  const row = ev.target.closest(".cfg-cat");
  if (!row || ev.target.dataset.f !== "nombre") return;
  state.cfgFuentes[+row.dataset.i].nombre = ev.target.value;
  row.classList.add("dirty");
}
async function cfgDeleteFuente(i) {
  const f = state.cfgFuentes[i];
  if (f._new) { state.cfgFuentes.splice(i, 1); renderCfgFuentes(); return; }
  const ok = await confirmDialog(
    `Se eliminará la categoría de ingreso "${f.nombre}".` +
    (f.usos ? ` La usan ${f.usos} movimiento(s), así que primero debes reasignarlos.` : ""),
    "Eliminar categoría",
  );
  if (!ok) return;
  try {
    await api("/api/fuentes/" + f.id, { method: "DELETE" });
    state.cfgFuentes.splice(i, 1);
    state.cfgFuentesBase = state.cfgFuentesBase.filter((b) => b.id !== f.id);
    renderCfgFuentes();
    state.catalogos = await api("/api/catalogos");
    populateForm();
    await refresh();
    showToast("Categoría de ingreso eliminada");
  } catch (e) { $("#cfg-error").textContent = e.message; $("#cfg-error").hidden = false; }
}
function cfgAddFuenteRow() {
  const nombre = $("#cfg-fuente-nueva").value.trim();
  if (!nombre) { $("#cfg-fuente-nueva").focus(); return; }
  state.cfgFuentes.push({ id: null, nombre, usos: 0, _new: true });
  $("#cfg-fuente-nueva").value = "";
  renderCfgFuentes();
}

/* --- Configuración › Cuentas y conciliación --- */
function renderCfgAccounts() {
  const cont = $("#cfg-accounts");
  cont.innerHTML = `<div class="cfg-account-head"><span>Nombre</span><span>Saldo</span><span>Activa</span><span>Saldo real</span></div>` +
    state.cfgAccounts.map((a, i) => `<div class="cfg-account" data-i="${i}">
      <input data-f="nombre" maxlength="60" value="${esc(a.nombre)}" />
      <strong class="amount">${money(a.saldo)}</strong>
      <label class="switch"><input data-f="activa" type="checkbox"${a.activa ? " checked" : ""} /><span></span></label>
      <div class="account-reconcile">
        <input type="number" step="0.01" data-balance placeholder="0.00" />
        <button type="button" class="btn btn-ghost btn-sm" data-reconcile="${i}"${a._new ? " disabled" : ""}>Conciliar</button>
      </div>
    </div>`).join("");
}
function cfgAccountInput(ev) {
  const row = ev.target.closest(".cfg-account");
  if (!row || !ev.target.dataset.f) return;
  const account = state.cfgAccounts[+row.dataset.i];
  account[ev.target.dataset.f] = ev.target.dataset.f === "activa" ? ev.target.checked : ev.target.value;
}
function cfgAddAccountRow() {
  const nombre = $("#cfg-account-new").value.trim();
  if (!nombre) return;
  state.cfgAccounts.push({ id: null, nombre, moneda: "USD", activa: true, saldo: 0, _new: true });
  $("#cfg-account-new").value = "";
  renderCfgAccounts();
}
async function cfgReconcileAccount(i) {
  const account = state.cfgAccounts[i];
  const input = $(`.cfg-account[data-i="${i}"] [data-balance]`);
  if (input.value === "") { input.focus(); return; }
  const saldoReal = Number(input.value);
  if (!Number.isFinite(saldoReal)) return;
  try {
    await api(`/api/cuentas/${account.id}/conciliaciones`, jsonReq("POST", {
      saldo_real: saldoReal,
      fecha: state.overview.hoy,
      descripcion: "Conciliación manual de saldo real",
    }));
    await refresh();
    const accounts = await api("/api/cuentas");
    state.cfgAccounts = accounts.items.map((a) => ({ ...a }));
    state.cfgAccountsBase = accounts.items.map((a) => ({ ...a }));
    renderCfgAccounts();
    showToast(`${account.nombre} conciliada`);
  } catch (e) { $("#cfg-error").textContent = e.message; $("#cfg-error").hidden = false; }
}

/* --- Configuración › Historial (borrado por mes, por día o todo) --- */
function setCfgHistModo(modo) {
  state.cfgHistModo = modo;
  $$("#cfg-hist-seg .seg-btn").forEach((b) => b.classList.toggle("active", b.dataset.modo === modo));
  $("#cfg-hist-row-mes").hidden = modo !== "mes";
  $("#cfg-hist-row-dia").hidden = modo !== "dia";
  $("#cfg-hist-row-todo").hidden = modo !== "todo";
}
function renderCfgHist() {
  const d = state.dias;
  const total = d.total || 0;
  $("#cfg-hist-resumen").textContent = total
    ? `${total} movimiento(s) entre ${fmtDMY(d.primero)} y ${fmtDMY(d.ultimo)}.`
    : "No hay movimientos registrados.";
  $("#cfg-hist-total").textContent = `${total} movimiento(s)`;
  $("#cfg-hist-mes").innerHTML = d.meses.length
    ? d.meses.slice().reverse().map((m) =>
        `<option value="${m.periodo}">${mesLargo(m.periodo + "-01")} — ${m.movimientos} mov.</option>`).join("")
    : `<option value="">sin datos</option>`;
  $("#cfg-hist-dia").innerHTML = d.dias.length
    ? d.dias.slice().reverse().map((x) =>
        `<option value="${x.fecha}">${fmtDMY(x.fecha)} — ${x.movimientos} mov.</option>`).join("")
    : `<option value="">sin datos</option>`;
  $("#cfg-hist-borrar").disabled = !total;
}
async function borrarHistorial() {
  const modo = state.cfgHistModo;
  let desde = null, hasta = null, que = "";
  if (modo === "mes") {
    const p = $("#cfg-hist-mes").value;
    if (!p) return;
    desde = p + "-01"; hasta = finDeMes(desde);
    que = `todos los movimientos de ${mesLargo(desde)}`;
  } else if (modo === "dia") {
    const f = $("#cfg-hist-dia").value;
    if (!f) return;
    desde = hasta = f;
    que = `los movimientos del ${fmtDMY(f)}`;
  } else {
    que = `los ${state.dias.total} movimientos del histórico completo`;
  }
  const ok = await confirmDialog(
    `Se eliminarán ${que}. Esta acción no se puede deshacer.`,
    "Eliminar", "¿Borrar historial?",
  );
  if (!ok) return;
  const err = $("#cfg-error"); err.hidden = true;
  try {
    const qs = desde ? `?desde=${desde}&hasta=${hasta}` : "";
    const res = await api("/api/historial" + qs, { method: "DELETE" });
    await refresh();
    renderCfgHist();
    showToast(`${res.eliminados} movimiento(s) eliminados`);
  } catch (e) { err.textContent = "No se pudo borrar: " + e.message; err.hidden = false; }
}

async function openCfg() {
  $("#cfg-error").hidden = true;
  $("#cfg-saved").hidden = true;
  try {
    const [cats, fuentes, accounts] = await Promise.all([
      api("/api/categorias"), api("/api/fuentes"), api("/api/cuentas"),
    ]);
    state.cfgCats = cats.map((c) => ({ ...c }));
    state.cfgCatsBase = cats.map((c) => ({ ...c }));
    state.cfgFuentes = fuentes.map((f) => ({ ...f }));
    state.cfgFuentesBase = fuentes.map((f) => ({ ...f }));
    state.cfgAccounts = accounts.items.map((a) => ({ ...a }));
    state.cfgAccountsBase = accounts.items.map((a) => ({ ...a }));
  } catch (e) { showToast("No se pudo cargar la configuración", false); return; }
  renderCfgCats();
  renderCfgFuentes();
  renderCfgAccounts();
  cfgShowFlujo(state.cfgCatFlujo);
  setCfgHistModo(state.cfgHistModo);
  renderCfgHist();
  $("#cfg-privado").checked = !!state.prefs.privado;
  $("#cfg-autorefresh").checked = !!state.prefs.autorefresh;
  $("#cfg-rango").value = state.prefs.rango;
  $("#cfg-search").value = "";
  filtrarCfg("");
  $("#cfg-modal").hidden = false;
}
function closeCfg() { $("#cfg-modal").hidden = true; }
function filtrarCfg(q) {
  const term = q.trim().toLowerCase();
  const tabs = $$(".cfg-tab");
  tabs.forEach((t) => (t.hidden = !!term && !t.textContent.toLowerCase().includes(term)));
  const visible = tabs.find((t) => !t.hidden);
  if (term && visible && !visible.classList.contains("active")) cfgShowPane(visible.dataset.cfg);
}
function cfgCatInput(ev) {
  const row = ev.target.closest(".cfg-cat");
  if (!row) return;
  const cat = state.cfgCats[+row.dataset.i];
  const campo = ev.target.dataset.f;
  if (campo === "nombre") cat.nombre = ev.target.value;
  else if (campo === "tipo") {
    cat.tipo = ev.target.value;
    if (cat.tipo === "residual") cat.valor = 0;
    renderCfgCats();
    return;
  } else if (campo === "valor") {
    const n = parseFloat(ev.target.value) || 0;
    cat.valor = cat.tipo === "porcentaje" ? n / 100 : n;
  }
  row.classList.add("dirty");
}
async function cfgDeleteCat(i) {
  const cat = state.cfgCats[i];
  if (cat._new) { state.cfgCats.splice(i, 1); renderCfgCats(); return; }
  const ok = await confirmDialog(
    `Se eliminará la categoría "${cat.nombre}".` +
    (cat.usos ? ` La usan ${cat.usos} movimiento(s), así que primero debes reasignarlos.` : ""),
    "Eliminar categoría",
  );
  if (!ok) return;
  try {
    await api("/api/categorias/" + cat.id, { method: "DELETE" });
    state.cfgCats.splice(i, 1);
    state.cfgCatsBase = state.cfgCatsBase.filter((b) => b.id !== cat.id);
    renderCfgCats();
    state.catalogos = await api("/api/catalogos");
    populateForm();
    await refresh();
    showToast("Categoría eliminada");
  } catch (e) { $("#cfg-error").textContent = e.message; $("#cfg-error").hidden = false; }
}
function cfgAddCatRow() {
  const nombre = $("#cfg-cat-nueva").value.trim();
  if (!nombre) { $("#cfg-cat-nueva").focus(); return; }
  state.cfgCats.push({ id: null, nombre, tipo: "fijo", valor: 0, usos: 0, _new: true });
  $("#cfg-cat-nueva").value = "";
  renderCfgCats();
}
async function cfgSave() {
  const err = $("#cfg-error"); err.hidden = true;
  $("#cfg-saved").hidden = true;
  const btn = $("#cfg-save");
  btn.disabled = true;
  try {
    // 1) Categorías: crea las nuevas y actualiza las que cambiaron.
    for (const c of state.cfgCats) {
      const nombre = c.nombre.trim().toLowerCase();
      if (!nombre) throw new Error("Hay una categoría sin nombre.");
      if (c._new) {
        await api("/api/categorias", jsonReq("POST", { nombre, tipo: c.tipo, valor: c.valor }));
        continue;
      }
      const base = state.cfgCatsBase.find((b) => b.id === c.id);
      if (base && (base.nombre !== nombre || base.tipo !== c.tipo || base.valor !== c.valor)) {
        await api("/api/categorias/" + c.id, jsonReq("PATCH", { nombre, tipo: c.tipo, valor: c.valor }));
      }
    }
    // 2) Categorías de ingreso: mismas reglas, sin tope.
    for (const f of state.cfgFuentes) {
      const nombre = f.nombre.trim().toLowerCase();
      if (!nombre) throw new Error("Hay una categoría de ingreso sin nombre.");
      if (f._new) {
        await api("/api/fuentes", jsonReq("POST", { nombre }));
        continue;
      }
      const base = state.cfgFuentesBase.find((b) => b.id === f.id);
      if (base && base.nombre !== nombre) {
        await api("/api/fuentes/" + f.id, jsonReq("PATCH", { nombre }));
      }
    }
    // 3) Cuentas.
    for (const a of state.cfgAccounts) {
      const nombre = a.nombre.trim();
      if (!nombre) throw new Error("Hay una cuenta sin nombre.");
      if (a._new) {
        await api("/api/cuentas", jsonReq("POST", { nombre, moneda: "USD" }));
        continue;
      }
      const base = state.cfgAccountsBase.find((b) => b.id === a.id);
      if (base && (base.nombre !== nombre || base.activa !== a.activa)) {
        await api("/api/cuentas/" + a.id, jsonReq("PATCH", { nombre, activa: a.activa }));
      }
    }
    // 4) Preferencias locales.
    state.prefs = {
      privado: $("#cfg-privado").checked,
      autorefresh: $("#cfg-autorefresh").checked,
      rango: $("#cfg-rango").value,
    };
    savePrefs(state.prefs);
    applyAutoRefresh();

    // Recarga catálogos y datos para que todo quede consistente al instante.
    const [frescas, fuentesFrescas, accountsFresh] = await Promise.all([
      api("/api/categorias"), api("/api/fuentes"), api("/api/cuentas"),
    ]);
    state.cfgCats = frescas.map((c) => ({ ...c }));
    state.cfgCatsBase = frescas.map((c) => ({ ...c }));
    state.cfgFuentes = fuentesFrescas.map((f) => ({ ...f }));
    state.cfgFuentesBase = fuentesFrescas.map((f) => ({ ...f }));
    state.cfgAccounts = accountsFresh.items.map((a) => ({ ...a }));
    state.cfgAccountsBase = accountsFresh.items.map((a) => ({ ...a }));
    renderCfgCats();
    renderCfgFuentes();
    renderCfgAccounts();
    state.catalogos = await api("/api/catalogos");
    populateForm();
    await refresh();
    renderCfgHist();

    $("#cfg-saved").hidden = false;
    setTimeout(() => ($("#cfg-saved").hidden = true), 2600);
    showToast("Configuración guardada");
  } catch (e) {
    err.textContent = "No se pudo guardar: " + e.message;
    err.hidden = false;
  } finally {
    btn.disabled = false;
  }
}

/* ---------- confirmación flotante ---------- */
let _confirmResolve = null;
function confirmDialog(msg, okText = "Eliminar", title = "¿Estás seguro?") {
  if (_cal) _cal.close();
  $("#confirm-title").textContent = title;
  $("#confirm-msg").textContent = msg;
  $("#confirm-ok").textContent = okText;
  $("#confirm-modal").hidden = false;
  return new Promise((resolve) => { _confirmResolve = resolve; });
}
function closeConfirm(val) {
  $("#confirm-modal").hidden = true;
  const r = _confirmResolve; _confirmResolve = null;
  if (r) r(val);
}

/* ---------- periodos compartidos (resumen + movimientos + reportes) ---------- */
let _cal = null;
const rangoDe = (pfx) =>
  pfx === "mov" ? state.movRange : (pfx === "rep" ? state.repRange : state.resRange);
const presetRange = (preset) => movPresetRange(preset);
const periodPreset = (pfx, preset) => pfx === "res" ? resPresetRange(preset) : movPresetRange(preset);

function updateRangeLabels(pfx) {
  const r = rangoDe(pfx);
  const label = document.getElementById(pfx + "-period-label");
  if (label) label.textContent = r.preset === "todo" ? "Todo el historial"
    : r.desde && r.hasta ? periodoTexto(r) : "Elegir periodo";
  $$(`#${pfx}-range-seg .seg-btn`).forEach((b) => {
    const active = b.dataset.preset === r.preset;
    b.classList.toggle("active", active);
    b.setAttribute("aria-pressed", String(active));
    b.disabled = state.diasSet.size === 0;
  });
}

async function applyPeriod(pfx, range) {
  Object.assign(rangoDe(pfx), range);
  updateRangeLabels(pfx);
  try {
    if (pfx === "rep") await updateRepCount();
    else await refresh();
  } catch (e) {
    setOnline(false);
    showToast("No se pudo cargar el periodo. Intenta refrescar.", false);
  }
}

/* Presets basados en DATOS: el último mes con movimientos, el anterior a ese, o todo. */
function resPresetRange(preset) {
  const primero = state.dias.primero_contable;
  const ultimo = state.dias.ultimo_contable;
  return rangeFromData(preset, primero, ultimo);
}
function movPresetRange(preset) {
  return rangeFromData(preset, state.dias.primero, state.dias.ultimo);
}
function rangeFromData(preset, primero, ultimo) {
  const hoy = state.overview ? state.overview.hoy : new Date().toISOString().slice(0, 10);
  const ref = ultimo || hoy;
  if (preset === "dia") return { desde: ref, hasta: ref };
  if (preset === "todo") return { desde: primero || primerDia(ref), hasta: ultimo || ref };
  if (preset === "mes_pasado") {
    // Mes calendario anterior al último con datos.
    const [y, m] = ref.split("-").map(Number);
    const d = new Date(y, m - 2, 1);
    const iso = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-01`;
    return { desde: iso, hasta: finDeMes(iso) };
  }
  return { desde: primerDia(ref), hasta: finDeMes(ref) }; // "mes"
}
async function updateRepCount() {
  const r = state.repRange;
  const el = $("#rep-count");
  if (!el) return;
  if (!r.desde || !r.hasta) { el.textContent = "Elige un rango."; return; }
  try {
    const list = await api(`/api/movimientos?desde=${r.desde}&hasta=${r.hasta}&limit=500`);
    el.textContent = `${list.length} movimiento(s) entre ${fmtDMY(r.desde)} y ${fmtDMY(r.hasta)}.`;
  } catch (e) { /* noop */ }
}
async function descargarReporte() {
  const r = state.repRange;
  if (!r.desde || !r.hasta) { showToast("Elige un rango", false); return; }
  try {
    const res = await fetch(`/api/reporte?desde=${r.desde}&hasta=${r.hasta}`, { credentials: "same-origin" });
    if (res.status === 401) { window.location.href = "/login"; return; }
    if (!res.ok) throw new Error();
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `brujula_movimientos_${r.desde}_a_${r.hasta}.csv`;
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
    showToast("Reporte descargado");
  } catch (e) { showToast("No se pudo descargar", false); }
}

/* ---------- navegación + refresco ---------- */
const TITLES = { resumen: "Resumen", movimientos: "Movimientos", reportes: "Reportes" };
function showView(view) {
  if (_cal) _cal.close();
  state.activeView = view;
  $$(".nav-item[data-view]").forEach((b) => b.classList.toggle("active", b.dataset.view === view));
  $$(".view").forEach((v) => v.classList.toggle("active", v.dataset.view === view));
  $("#view-title").textContent = TITLES[view];
  const SUBS = { movimientos: "Alta, edición y borrado", reportes: "Descarga en CSV" };
  $("#periodo-lbl").textContent = view === "resumen"
    ? periodoTexto(state.overview ? state.overview.periodo : null)
    : SUBS[view];
  const sa = document.querySelector(".scroll-area");
  if (sa) sa.scrollTop = 0;
  if (view === "reportes") {
    if (state.repRange.preset !== "custom") Object.assign(state.repRange, presetRange(state.repRange.preset));
    updateRangeLabels("rep");
    updateRepCount();
  }
  renderActiveCharts();
}
function renderActiveCharts() {
  if (!state.overview) return;
  if (state.activeView === "resumen") { renderFlujo(); renderDistribucion(); }
  requestAnimationFrame(() => Object.values(charts).forEach((c) => c.resize()));
}

async function refresh() {
  // Días con datos: definen los atajos y los puntos del calendario.
  state.dias = await api("/api/dias");
  state.diasSet = new Set(state.dias.dias.map((d) => d.fecha));
  const rr = state.resRange;
  if (rr.preset !== "custom") Object.assign(rr, resPresetRange(rr.preset));
  // El rango personalizado se respeta tal cual lo eligió el dueño (aunque no tenga datos:
  // un periodo vacío es información válida — el semáforo lo muestra con el arrastre).
  const qs = rr.desde && rr.hasta ? `?desde=${rr.desde}&hasta=${rr.hasta}` : "";
  state.overview = await api("/api/overview" + qs);
  updateRangeLabels("res");
  // Recalcula el rango de movimientos con la fecha del servidor (salvo personalizado).
  if (state.movRange.preset !== "custom") Object.assign(state.movRange, presetRange(state.movRange.preset));
  const r = state.movRange;
  let q = "/api/movimientos?limit=500";
  // La categoría elegida ya implica el tipo, así que basta con mandarlo una vez.
  const fc = filtroCatPartes();
  const tipo = (["prestamo", "transferencia"].includes(state.filtro) ? "" : state.filtro) || (fc ? fc.tipo : "");
  if (tipo) q += "&tipo=" + tipo;
  if (fc) q += (fc.tipo === "gasto" ? "&categoria=" : "&fuente=") + encodeURIComponent(fc.nombre);
  if (state.filtroCuenta) q += "&account_id=" + state.filtroCuenta;
  if (r.desde) q += "&desde=" + r.desde;
  if (r.hasta) q += "&hasta=" + r.hasta;
  if (state.filtro === "prestamo") {
    let loanQ = "/api/prestamos";
    if (r.desde && r.hasta) loanQ += `?desde=${r.desde}&hasta=${r.hasta}`;
    const loanData = await api(loanQ);
    state.loanGroups = loanData.personas;
    state.loanTotals = { por_cobrar: loanData.por_cobrar, por_pagar: loanData.por_pagar };
    state.movs = state.loanGroups.flatMap((group) => group.movimientos);
  } else {
    let movements = [];
    if (state.filtro !== "transferencia") {
      q += "&prestamos=false";
      movements = await api(q);
    }
    let transfers = [];
    if ((!state.filtro && !fc) || state.filtro === "transferencia") {
      let tq = "/api/transferencias";
      const parts = [];
      if (r.desde) parts.push("desde=" + r.desde, "hasta=" + r.hasta);
      if (state.filtroCuenta) parts.push("account_id=" + state.filtroCuenta);
      if (parts.length) tq += "?" + parts.join("&");
      transfers = (await api(tq)).map((t) => ({ ...t, tipo: "transferencia" }));
    }
    state.transfers = transfers;
    state.movs = [...movements, ...transfers].sort((a, b) =>
      b.fecha.localeCompare(a.fecha) || b.id - a.id);
    state.loanGroups = [];
  }
  renderKPIs(); renderSobres(); renderMovTable();
  populateForm(); populateFiltroCat(); populateFiltroCuenta();
  updateRangeLabels("mov");
  renderActiveCharts();
  setOnline(true);
}

/* ---------- indicador de conexión ---------- */
function setOnline(ok) {
  const l = $("#sync-label");
  if (!l) return;
  l.textContent = ok ? "en vivo" : "sin conexión";
  const d = document.querySelector(".status-dot .dot");
  if (d) d.style.background = ok ? "var(--green)" : "var(--amber)";
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
  state.toastTimer = setTimeout(() => t.classList.remove("show"), TOAST_DURATION_MS);
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
    setOnline(false);
    showToast("Error al actualizar", false);
  }
}

/* Refresco suave para mantener el panel sincronizado entre pestañas. */
function applyAutoRefresh() {
  clearInterval(state.autoTimer);
  state.autoTimer = null;
  if (!state.prefs.autorefresh) return;
  state.autoTimer = setInterval(() => {
    if (document.visibilityState === "visible" && !state.editId && !state.savingMovement &&
        !$("#f-monto").value && !$("#f-desc").value && $("#cfg-modal").hidden) {
      refresh().catch(() => setOnline(false));
    }
  }, 60000);
}

async function init() {
  try {
    state.catalogos = await api("/api/catalogos");
  } catch (e) { return; }
  setTipo("gasto");
  document.body.classList.toggle("private", !!state.prefs.privado);
  state.movRange.preset = state.prefs.rango === "todo" ? "todo" : "mes";
  $$("#mov-range-seg .seg-btn").forEach((b) =>
    b.classList.toggle("active", b.dataset.preset === state.movRange.preset));

  // navegación
  $$(".nav-item[data-view]").forEach((b) => b.addEventListener("click", () => showView(b.dataset.view)));
  $("#btn-refresh").addEventListener("click", refreshWithFeedback);
  $("#fab-refresh").addEventListener("click", refreshWithFeedback);

  // formulario de movimientos (agregar/editar)
  $$("#tipo-seg .seg-btn").forEach((b) => b.addEventListener("click", () => setTipo(b.dataset.tipo)));
  $("#f-categoria").addEventListener("change", updateLoanDetailField);
  $("#f-fuente").addEventListener("change", updateLoanDetailField);
  $("#mov-form").addEventListener("submit", submitMov);
  $("#mov-cancel-edit").addEventListener("click", exitEditMode);
  $("#mov-tbody").addEventListener("click", handleMovRowAction);
  $("#loan-groups").addEventListener("click", handleMovRowAction);

  // categoría nueva al vuelo (＋)
  $("#btn-add-cat").addEventListener("click", () => toggleNewCat($("#new-cat").hidden));
  $("#new-cat-save").addEventListener("click", crearCategoriaRapida);
  $("#new-cat-cancel").addEventListener("click", () => toggleNewCat(false));
  $("#new-cat-name").addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") { ev.preventDefault(); crearCategoriaRapida(); }
    if (ev.key === "Escape") toggleNewCat(false);
  });

  // categoría de ingreso nueva al vuelo (＋)
  $("#btn-add-fuente").addEventListener("click", () => toggleNewFuente($("#new-fuente").hidden));
  $("#new-fuente-save").addEventListener("click", crearFuenteRapida);
  $("#new-fuente-cancel").addEventListener("click", () => toggleNewFuente(false));
  $("#new-fuente-name").addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") { ev.preventDefault(); crearFuenteRapida(); }
    if (ev.key === "Escape") toggleNewFuente(false);
  });

  // filtro de la tabla: tipo + categoría del tipo elegido
  $$("#filtro-seg .seg-btn").forEach((b) => b.addEventListener("click", () => {
    $$("#filtro-seg .seg-btn").forEach((x) => x.classList.toggle("active", x === b));
    state.filtro = b.dataset.filtro;
    populateFiltroCat();  // descarta la categoría si ya no cabe en el tipo elegido
    refresh();
  }));
  $("#filtro-cat").addEventListener("change", (ev) => {
    state.filtroCat = ev.target.value;
    refresh();
  });
  $("#filtro-cuenta").addEventListener("change", (ev) => {
    state.filtroCuenta = ev.target.value;
    refresh();
  });

  // configuración (ventana flotante)
  $("#btn-config").addEventListener("click", openCfg);
  $("#cfg-close").addEventListener("click", closeCfg);
  $("#cfg-cancel").addEventListener("click", closeCfg);
  $("#cfg-save").addEventListener("click", cfgSave);
  $("#cfg-modal").addEventListener("click", (ev) => { if (ev.target.id === "cfg-modal") closeCfg(); });
  $$(".cfg-tab").forEach((b) => b.addEventListener("click", () => cfgShowPane(b.dataset.cfg)));
  $("#cfg-search").addEventListener("input", (ev) => filtrarCfg(ev.target.value));
  $("#cfg-cats").addEventListener("input", cfgCatInput);
  $("#cfg-cats").addEventListener("change", cfgCatInput);
  $("#cfg-cats").addEventListener("click", (ev) => {
    const d = ev.target.closest("[data-del]");
    if (d) cfgDeleteCat(+d.dataset.del);
  });
  $("#cfg-cat-add").addEventListener("click", cfgAddCatRow);
  $$("#cfg-cat-flujo-seg .seg-btn").forEach((b) =>
    b.addEventListener("click", () => cfgShowFlujo(b.dataset.flujo)));
  $("#cfg-fuentes").addEventListener("input", cfgFuenteInput);
  $("#cfg-fuentes").addEventListener("click", (ev) => {
    const d = ev.target.closest("[data-del]");
    if (d) cfgDeleteFuente(+d.dataset.del);
  });
  $("#cfg-fuente-add").addEventListener("click", cfgAddFuenteRow);
  $("#cfg-fuente-nueva").addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") { ev.preventDefault(); cfgAddFuenteRow(); }
  });
  $("#cfg-accounts").addEventListener("input", cfgAccountInput);
  $("#cfg-accounts").addEventListener("change", cfgAccountInput);
  $("#cfg-accounts").addEventListener("click", (ev) => {
    const button = ev.target.closest("[data-reconcile]");
    if (button) cfgReconcileAccount(+button.dataset.reconcile);
  });
  $("#cfg-account-add").addEventListener("click", cfgAddAccountRow);
  $("#cfg-account-new").addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") { ev.preventDefault(); cfgAddAccountRow(); }
  });
  $$("#cfg-hist-seg .seg-btn").forEach((b) =>
    b.addEventListener("click", () => setCfgHistModo(b.dataset.modo)));
  $("#cfg-hist-borrar").addEventListener("click", borrarHistorial);
  $("#cfg-cat-nueva").addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") { ev.preventDefault(); cfgAddCatRow(); }
  });

  // privacidad: ojo global
  $("#btn-eye").addEventListener("click", () => document.body.classList.toggle("private"));

  // Un selector para meses, días y rangos en las tres vistas.
  _cal = makePeriodPicker({
    getRange: rangoDe, getPreset: periodPreset, getDays: () => state.diasSet,
    onApply: applyPeriod,
  });
  for (const pfx of ["res", "mov", "rep"]) {
    $$(`#${pfx}-range-seg .seg-btn`).forEach((b) => b.addEventListener("click", () =>
      applyPeriod(pfx, { ...periodPreset(pfx, b.dataset.preset), preset: b.dataset.preset })));
    $(`[data-period="${pfx}"]`).addEventListener("click", (ev) => _cal.open(pfx, ev.currentTarget));
  }
  $("#btn-descargar").addEventListener("click", descargarReporte);

  // confirmación flotante
  $("#confirm-ok").addEventListener("click", () => closeConfirm(true));
  $("#confirm-cancel").addEventListener("click", () => closeConfirm(false));
  $("#confirm-modal").addEventListener("click", (ev) => { if (ev.target.id === "confirm-modal") closeConfirm(false); });

  window.addEventListener("keydown", (ev) => {
    if (ev.key !== "Escape") return;
    if (!$("#confirm-modal").hidden) { closeConfirm(false); return; }
    closeCfg();
  });
  window.addEventListener("resize", () => Object.values(charts).forEach((c) => c.resize()));
  window.addEventListener("online", () => setOnline(true));
  window.addEventListener("offline", () => setOnline(false));
  applyAutoRefresh();

  try { await refresh(); } catch (e) { setOnline(false); }
}

document.addEventListener("DOMContentLoaded", init);
