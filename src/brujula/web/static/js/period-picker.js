/* Selector de periodos: meses completos, un día o un rango en una sola ventana. */
"use strict";

function makePeriodPicker({ getRange, getPreset, getDays, onApply }) {
  const months = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"];
  const iso = (y, m, d = 1) => `${y}-${String(m + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
  const monthEnd = (y, m) => iso(y, m, new Date(y, m + 1, 0).getDate());
  const format = (value) => new Date(value + "T12:00:00").toLocaleDateString("es", {
    day: "numeric", month: "short", year: "numeric",
  });
  const dialog = document.createElement("dialog");
  dialog.className = "period-dialog";
  dialog.id = "period-dialog";
  dialog.setAttribute("aria-labelledby", "period-title");
  document.body.appendChild(dialog);
  let context, anchor, mode, year, month, draft, waitingEnd = false;
  let historyDays = [], historyMonths = [], historyYears = [];
  const monthsFor = (y) => historyMonths.filter(value => Number(value.slice(0, 4)) === y);
  const monthKey = () => iso(year, month).slice(0, 7);
  function moveTarget(step) {
    const values = mode === "month" ? historyYears : historyMonths;
    return values[values.indexOf(mode === "month" ? year : monthKey()) + step];
  }
  function validRange(value) {
    return value.desde && value.hasta && value.desde <= value.hasta &&
      historyDays.some(day => day >= value.desde && day <= value.hasta);
  }

  function close() { dialog.close(); anchor?.focus(); }
  function apply(value) { if (validRange(value)) { close(); onApply(context, value); } }
  function calendar(y, m) {
    const first = (new Date(y, m, 1).getDay() + 6) % 7;
    const days = getDays();
    let cells = ["L", "M", "X", "J", "V", "S", "D"].map(d => `<span class="cal-dow">${d}</span>`).join("");
    cells += "<span></span>".repeat(first);
    for (let d = 1; d <= new Date(y, m + 1, 0).getDate(); d++) {
      const value = iso(y, m, d);
      const edge = value === draft.desde || value === draft.hasta;
      const inside = draft.desde && draft.hasta && value > draft.desde && value < draft.hasta;
      const hasData = days.has(value);
      const allowed = mode === "day" ? hasData
        : value >= historyDays[0] && value <= historyDays[historyDays.length - 1];
      cells += `<button type="button" class="cal-day${edge ? " selected" : ""}${inside ? " in-range" : ""}${hasData ? " con-datos" : ""}"
        data-day="${value}"${allowed ? "" : " disabled"} aria-pressed="${edge || !!inside}" aria-label="${d} de ${months[m]} de ${y}${hasData ? ", con movimientos" : ""}">${d}</button>`;
    }
    return `<section class="period-calendar" aria-label="${months[m]} ${y}"><h3>${months[m]} ${y}</h3><div class="cal-grid">${cells}</div></section>`;
  }
  function render(focusKey) {
    const lastDay = getPreset(context, "dia");
    const lastMonth = getPreset(context, "mes");
    const nextKey = historyMonths[historyMonths.indexOf(monthKey()) + 1];
    const next = nextKey ? new Date(nextKey + "-01T12:00:00") : null;
    const summary = !historyDays.length ? "Sin historial" : draft.desde ? (draft.hasta
      ? (draft.desde === draft.hasta ? format(draft.desde) : `${format(draft.desde)} → ${format(draft.hasta)}`)
      : `${format(draft.desde)} → Elige el final`) : "Elige una fecha";
    const help = mode === "month" ? "Solo se muestran meses con movimientos."
      : mode === "day" ? "Selecciona un día con movimientos."
      : waitingEnd ? "Ahora elige el final del rango. Puede estar en otro mes."
      : "Marca el inicio y después el final, en estos calendarios.";
    dialog.innerHTML = `<header class="period-header"><div><h2 id="period-title">Elegir periodo</h2><p>Consulta tus movimientos por mes, día o rango.</p></div>
      <button type="button" class="btn btn-ghost btn-sm" data-action="close" aria-label="Cerrar selector de periodo">×</button></header>
      <div class="period-layout"><aside class="period-shortcuts" aria-label="Atajos de periodo"><span class="range-title muted">Acceso rápido</span>
        <button type="button" data-preset="dia"${historyDays.length ? "" : " disabled"}><b>Último día</b><small>${historyDays.length ? format(lastDay.desde) : "Sin historial"}</small></button>
        <button type="button" data-preset="mes"${historyDays.length ? "" : " disabled"}><b>Último mes</b><small>${historyDays.length ? months[+lastMonth.desde.slice(5, 7) - 1] + " " + lastMonth.desde.slice(0, 4) : "Sin historial"}</small></button>
        <button type="button" data-preset="todo"${historyDays.length ? "" : " disabled"}><b>Todo el historial</b></button>
        <p>Los atajos usan las fechas más recientes con movimientos.</p></aside>
      <div class="period-main"><div class="seg seg-sm period-modes" role="group" aria-label="Seleccionar por">
        ${[["month", "Mes"], ["day", "Día"], ["range", "Rango"]].map(([key, label]) => `<button type="button" class="seg-btn${mode === key ? " active" : ""}" data-mode="${key}" aria-pressed="${mode === key}">${label}</button>`).join("")}</div>
      ${historyDays.length ? `<div class="period-navigation"><button type="button" class="cal-nav" data-nav="-1"${moveTarget(-1) === undefined ? " disabled" : ""} aria-label="${mode === "month" ? "Año" : "Mes"} anterior">‹</button>
        <div>${mode !== "month" ? `<select aria-label="Mes del calendario" data-select="month">${months.map((name, i) => monthsFor(year).includes(iso(year, i).slice(0, 7)) ? `<option value="${i}"${i === month ? " selected" : ""}>${name}</option>` : "").join("")}</select>` : ""}
        <select aria-label="Año" data-select="year">${historyYears.map(y => `<option value="${y}"${y === year ? " selected" : ""}>${y}</option>`).join("")}</select></div>
        <button type="button" class="cal-nav" data-nav="1"${moveTarget(1) === undefined ? " disabled" : ""} aria-label="${mode === "month" ? "Año" : "Mes"} siguiente">›</button></div>
      <p class="period-help" aria-live="polite">${help}</p>
      ${mode === "month" ? `<div class="period-months">${months.map((name, i) => {
        if (!monthsFor(year).includes(iso(year, i).slice(0, 7))) return "";
        const selected = draft.desde === iso(year, i) && draft.hasta === monthEnd(year, i);
        return `<button type="button" data-month="${i}" class="${selected ? "selected" : ""}" aria-pressed="${selected}">${name}</button>`;
      }).join("")}</div>` : `<div class="period-calendars${mode === "day" || !next ? " single" : ""}">${calendar(year, month)}${mode === "range" && next ? calendar(next.getFullYear(), next.getMonth()) : ""}</div>
      <p class="period-legend"><span></span> Día con movimientos</p>`}` : `<p class="period-help">Todavía no hay movimientos registrados.</p>`}</div></div>
      <footer class="period-footer"><div><small>Periodo seleccionado</small><strong aria-live="polite">${summary}</strong></div>
        <div class="period-actions"><button type="button" class="btn btn-ghost" data-action="close">Cancelar</button>
        <button type="button" class="btn btn-primary" data-action="apply"${!validRange(draft) ? " disabled" : ""}>Aplicar</button></div></footer>`;
    if (focusKey) dialog.querySelector(focusKey)?.focus();
  }
  dialog.addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!button) { if (event.target === dialog) {
      const rect = dialog.getBoundingClientRect();
      if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) close();
    } return; }
    if (button.disabled) return;
    if (button.dataset.action === "close") return close();
    if (button.dataset.action === "apply") return apply({ ...draft, preset: "custom" });
    if (button.dataset.preset) return apply({ ...getPreset(context, button.dataset.preset), preset: button.dataset.preset });
    if (button.dataset.mode) {
      mode = button.dataset.mode; waitingEnd = false;
      if (mode === "day") {
        const day = historyDays.find(day => day >= draft.desde) || historyDays[historyDays.length - 1];
        draft = { desde: day, hasta: day };
        if (day) { year = Number(day.slice(0, 4)); month = Number(day.slice(5, 7)) - 1; }
      }
      render(`[data-mode="${mode}"]`); return;
    }
    if (button.dataset.nav) {
      const step = Number(button.dataset.nav);
      const target = moveTarget(step);
      if (target === undefined) return;
      if (mode === "month") { year = target; month = Number(monthsFor(year)[0].slice(5, 7)) - 1; }
      else { year = Number(target.slice(0, 4)); month = Number(target.slice(5, 7)) - 1; }
      render(`[data-nav="${step}"]`); return;
    }
    if (button.dataset.month !== undefined) {
      const selected = Number(button.dataset.month);
      if (!monthsFor(year).includes(iso(year, selected).slice(0, 7))) return;
      return apply({ desde: iso(year, selected), hasta: monthEnd(year, selected), preset: "custom" });
    }
    if (button.dataset.day) {
      const selected = button.dataset.day;
      if (mode === "day") draft = { desde: selected, hasta: selected };
      else if (!waitingEnd) { draft = { desde: selected, hasta: null }; waitingEnd = true; }
      else { draft = { desde: selected < draft.desde ? selected : draft.desde,
        hasta: selected > draft.desde ? selected : draft.desde }; waitingEnd = false; }
      render(`[data-day="${selected}"]`);
    }
  });
  function changeCalendar(event) {
    if (!event.target.dataset.select) return;
    if (event.target.dataset.select === "year") {
      const value = Number(event.target.value);
      if (!historyYears.includes(value)) return;
      year = value;
      if (!monthsFor(year).includes(monthKey())) month = Number(monthsFor(year)[0].slice(5, 7)) - 1;
    } else {
      const value = Number(event.target.value);
      if (!monthsFor(year).includes(iso(year, value).slice(0, 7))) return;
      month = value;
    }
    render(`[data-select="${event.target.dataset.select}"]`);
  }
  dialog.addEventListener("change", changeCalendar);
  dialog.addEventListener("close", () => anchor?.setAttribute("aria-expanded", "false"));
  return {
    close,
    open(pfx, trigger) {
      context = pfx; anchor = trigger;
      historyDays = [...getDays()].sort();
      historyMonths = [...new Set(historyDays.map(day => day.slice(0, 7)))];
      historyYears = [...new Set(historyMonths.map(value => Number(value.slice(0, 4))))];
      draft = { ...getRange(pfx) };
      if (!draft.desde) Object.assign(draft, getPreset(pfx, "mes"));
      year = Number(draft.desde.slice(0, 4)); month = Number(draft.desde.slice(5, 7)) - 1;
      mode = draft.desde === draft.hasta ? "day"
        : draft.desde === iso(year, month) && draft.hasta === monthEnd(year, month) ? "month" : "range";
      if (historyMonths.length && !historyMonths.includes(monthKey())) {
        const ref = historyMonths[historyMonths.length - 1];
        year = Number(ref.slice(0, 4)); month = Number(ref.slice(5, 7)) - 1;
      }
      waitingEnd = false;
      render(); dialog.showModal(); anchor.setAttribute("aria-expanded", "true");
      dialog.querySelector(`[data-mode="${mode}"]`).focus();
    },
  };
}
