/* Shared helpers for both progress artifacts. No dependencies. */
const PP = (() => {
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const STATUS = {
    done: "Done", in_progress: "In progress", ready: "Ready to start", blocked: "Blocked", dropped: "Dropped",
    on_track: "On track", at_risk: "At risk", off_track: "Off track", complete: "Complete", active: "In progress",
    late: "Past due", not_started: "Not started",
  };
  const chip = (s, extra = "") => `<span class="chip ${esc(s)} ${extra}">${esc(STATUS[s] || s)}</span>`;
  const fmtDate = (iso, tz, opts = { day: "numeric", month: "short", year: "numeric" }) => {
    if (!iso) return "";
    const d = iso.length === 10 ? new Date(iso + "T12:00:00Z") : new Date(iso);
    try { return new Intl.DateTimeFormat("en-GB", { ...opts, timeZone: iso.length === 10 ? "UTC" : tz }).format(d); }
    catch (e) { return iso.slice(0, 10); }
  };
  const daysBetween = (a, b) => Math.round((new Date(b) - new Date(a)) / 86400000);
  const bar = (done, prog, blocked, total) => {
    const pc = (x) => (total ? (100 * x) / total : 0).toFixed(2);
    return `<div class="bar" role="img" aria-label="${done} of ${total} done"><i class="d" style="width:${pc(done)}%"></i><i class="p" style="width:${pc(prog)}%"></i><i class="b" style="width:${pc(blocked)}%"></i></div>`;
  };
  const issueLink = (repoUrl, n) => `<a class="mono" href="${esc(repoUrl)}/issues/${n}" target="_blank" rel="noopener">#${n}</a>`;

  /* Sparkline of % complete over time. */
  function spark(history, w = 220, h = 48) {
    if (!history || history.length < 2) return "";
    const pad = 4, xs = history.map((_, i) => pad + (i * (w - 2 * pad)) / (history.length - 1));
    const ys = history.map((p) => h - pad - ((h - 2 * pad) * p.pct) / 100);
    const line = xs.map((x, i) => `${i ? "L" : "M"}${x.toFixed(1)},${ys[i].toFixed(1)}`).join(" ");
    const area = `${line} L${xs[xs.length - 1].toFixed(1)},${h - pad} L${xs[0].toFixed(1)},${h - pad} Z`;
    const lx = xs[xs.length - 1], ly = ys[ys.length - 1];
    return `<svg viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" role="img" aria-label="Completion trend">
      <line x1="${pad}" x2="${w - pad}" y1="${h - pad}" y2="${h - pad}" stroke="var(--line)"/>
      <path d="${area}" fill="var(--accent-soft)"/><path d="${line}" fill="none" stroke="var(--accent)" stroke-width="2"/>
      <circle cx="${lx}" cy="${ly}" r="3.5" fill="var(--accent)"/></svg>`;
  }

  /* Wrap a title into at most `lines` lines of roughly `max` characters. */
  function wrap(text, max, lines = 2) {
    const words = String(text).split(/\s+/), out = [];
    let cur = "";
    for (const w of words) {
      if ((cur + " " + w).trim().length <= max) cur = (cur + " " + w).trim();
      else { if (cur) out.push(cur); cur = w; }
      if (out.length === lines) break;
    }
    if (out.length < lines && cur) out.push(cur);
    const used = out.join(" ").split(/\s+/).length;
    if (used < words.length || out.some((l) => l.length > max)) {
      let last = out[out.length - 1] || "";
      if (last.length > max - 1) last = last.slice(0, max - 1);
      out[out.length - 1] = last.replace(/[\s,.;:–-]+$/, "") + "…";
    }
    return out;
  }

  /* Layered left-to-right flow chart in dependency order.
     nodes: [{id, stage, title, idText, meta, cls, aria}]  edges: [{from, to, cls}] */
  function flow(host, nodes, edges, o = {}) {
    const W = o.nodeW || 216, H = o.nodeH || 66, GX = o.gapX || 64, GY = o.gapY || 14, PAD = 18, TOP = o.stageLabel ? 34 : 14;
    const stages = [...new Set(nodes.map((n) => n.stage))].sort((a, b) => a - b);
    const col = new Map(stages.map((s, i) => [s, i]));
    const byId = new Map(nodes.map((n) => [n.id, n]));
    const E = edges.filter((e) => byId.has(e.from) && byId.has(e.to));
    const preds = new Map(nodes.map((n) => [n.id, []])), succs = new Map(nodes.map((n) => [n.id, []]));
    E.forEach((e) => { preds.get(e.to).push(e.from); succs.get(e.from).push(e.to); });
    const cols = stages.map((s) => nodes.filter((n) => n.stage === s));
    const y = new Map();
    const place = (list, desired) => {
      list.sort((a, b) => desired(a) - desired(b) || a.id - b.id);
      let next = TOP;
      list.forEach((n) => { const want = desired(n); const d = want >= 1e6 ? next : Math.max(want, next); y.set(n.id, d); next = d + H + GY; });
    };
    cols.forEach((list, ci) => {
      if (ci === 0) { let k = TOP; list.forEach((n) => { y.set(n.id, k); k += H + GY; }); return; }
      place(list, (n) => { const p = preds.get(n.id).filter((id) => y.has(id)); return p.length ? p.reduce((s, id) => s + y.get(id), 0) / p.length : 1e6 + n.id; });
    });
    // one backward sweep pulls sources toward their successors, then re-settle forward
    for (let ci = cols.length - 2; ci >= 0; ci--) {
      place(cols[ci], (n) => { const s = succs.get(n.id); return s.length ? s.reduce((a, id) => a + y.get(id), 0) / s.length : y.get(n.id); });
    }
    for (let ci = 1; ci < cols.length; ci++) {
      place(cols[ci], (n) => { const p = preds.get(n.id); return p.length ? p.reduce((s, id) => s + y.get(id), 0) / p.length : y.get(n.id); });
    }
    const minY = Math.min(...[...y.values()], TOP);
    if (minY < TOP) y.forEach((v, k) => y.set(k, v - minY + TOP));
    const x = (n) => PAD + col.get(n.stage) * (W + GX);
    const width = PAD * 2 + stages.length * W + (stages.length - 1) * GX;
    const height = Math.max(...[...y.values()].map((v) => v + H), TOP + H) + PAD;
    const uid = "m" + Math.random().toString(36).slice(2, 8);
    let s = `<svg viewBox="0 0 ${width} ${height}" width="${width}" height="${height}" role="img" aria-label="${esc(o.aria || "Dependency flow chart")}">
      <defs><marker id="${uid}a" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path class="arrow" d="M0,0 L8,4 L0,8 z"/></marker>
      <marker id="${uid}c" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path class="arrow-crit" d="M0,0 L8,4 L0,8 z"/></marker></defs>`;
    if (o.stageLabel) stages.forEach((st, i) => {
      const cx = PAD + i * (W + GX);
      s += `<rect class="stage-band" x="${cx}" y="6" width="${W}" height="20" rx="3"/><text class="stage-label" x="${cx + 8}" y="20">${esc(o.stageLabel(st, i))}</text>`;
    });
    E.forEach((e) => {
      const a = byId.get(e.from), b = byId.get(e.to);
      const x1 = x(a) + W, y1 = y.get(a.id) + H / 2, x2 = x(b) - 2, y2 = y.get(b.id) + H / 2, dx = Math.max(28, (x2 - x1) / 2);
      const crit = (e.cls || "").includes("crit");
      s += `<path class="edge ${esc(e.cls || "")}" data-f="${a.id}" data-t="${b.id}" d="M${x1},${y1} C${x1 + dx},${y1} ${x2 - dx},${y2} ${x2},${y2}" marker-end="url(#${uid}${crit ? "c" : "a"})"/>`;
    });
    nodes.forEach((n) => {
      const nx = x(n), ny = y.get(n.id), maxc = Math.floor((W - 22) / 6.4);
      const lines = wrap(n.title, maxc, o.titleLines || 2);
      s += `<g class="node ${esc(n.cls || "")}" data-id="${n.id}" tabindex="0" role="link" aria-label="${esc(n.aria || n.title)}">
        <rect class="box" x="${nx}" y="${ny}" width="${W}" height="${H}" rx="6"/>
        <text class="id" x="${nx + 11}" y="${ny + 17}">${esc(n.idText || "")}</text>
        ${n.meta ? `<text class="meta" x="${nx + W - 11}" y="${ny + 17}" text-anchor="end">${esc(n.meta)}</text>` : ""}
        ${lines.map((l, i) => `<text x="${nx + 11}" y="${ny + 35 + i * 15}">${esc(l)}</text>`).join("")}
      </g>`;
    });
    s += "</svg>";
    host.innerHTML = s;
    const svg = host.querySelector("svg");
    const chain = (id) => {
      const seen = new Set([id]);
      const walk = (m, k) => { (m.get(k) || []).forEach((j) => { if (!seen.has(j)) { seen.add(j); walk(m, j); } }); };
      walk(preds, id); walk(succs, id); return seen;
    };
    svg.querySelectorAll(".node").forEach((g) => {
      const id = +g.dataset.id;
      const on = () => {
        const keep = chain(id);
        svg.querySelectorAll(".node").forEach((k) => k.classList.toggle("dim", !keep.has(+k.dataset.id)));
        svg.querySelectorAll(".edge").forEach((p) => p.classList.toggle("dim", !(keep.has(+p.dataset.f) && keep.has(+p.dataset.t))));
      };
      const off = () => svg.querySelectorAll(".dim").forEach((k) => k.classList.remove("dim"));
      g.addEventListener("mouseenter", on); g.addEventListener("mouseleave", off);
      g.addEventListener("focus", on); g.addEventListener("blur", off);
      if (o.onClick) {
        g.addEventListener("click", () => o.onClick(id));
        g.addEventListener("keydown", (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); o.onClick(id); } });
      }
    });
  }


  /* Timeline / Gantt with finish-to-start dependency arrows.
     host: element. rows: [{type:"group", key, label, start, end, due, collapsed, sub} | {type:"task", id, group, label, start, end, due, status, kind, overdue, conflicts:[id], tip}]
     deps: [{from, to}] task ids. o: {today, tz} */
  function gantt(host, rows, deps, o = {}) {
    const ROW = 30, HEAD = 42, DAY = 86400000;
    const toD = (s) => new Date(s + "T00:00:00Z").getTime();
    const state = { collapsed: new Set(rows.filter((r) => r.type === "group" && r.collapsed).map((r) => r.key)) };
    const dates = [];
    rows.forEach((r) => { [r.start, r.end, r.due].forEach((d) => d && dates.push(toD(d))); });
    if (o.today) dates.push(toD(o.today));
    if (!dates.length) { host.innerHTML = `<p class="empty">No dated work to show yet.</p>`; return; }
    const min = Math.min(...dates) - 3 * DAY, max = Math.max(...dates) + 8 * DAY;
    const span = Math.round((max - min) / DAY);
    let dayW = span <= 45 ? 22 : span <= 120 ? 9 : span <= 300 ? 4 : 2;
    let W, X;
    const fmt = (s) => fmtDate(s, o.tz, { day: "numeric", month: "short" });
    const uid = "g" + Math.random().toString(36).slice(2, 7);
    host.classList.add("gantt");
    host.innerHTML = `<div class="g-labels" role="rowgroup"></div><div class="g-scroll"></div><div class="g-tip" hidden></div>`;
    const L = host.querySelector(".g-labels"), SC = host.querySelector(".g-scroll"), TIP = host.querySelector(".g-tip");

    function draw() {
      dayW = Math.max(dayW, (SC.clientWidth - 2) / span);
      W = Math.round(span * dayW); X = (s) => ((toD(s) - min) / DAY) * dayW;
      const vis = rows.filter((r) => r.type === "group" || !state.collapsed.has(r.group));
      const y = new Map(); vis.forEach((r, i) => y.set(r.type === "group" ? "g:" + r.key : r.id, HEAD + i * ROW));
      const H = HEAD + vis.length * ROW + 6;
      // labels
      L.innerHTML = `<div class="g-lhead" style="height:${HEAD}px"></div>` + vis.map((r) => r.type === "group"
        ? `<button type="button" class="g-row g-group" data-g="${esc(r.key)}" aria-expanded="${!state.collapsed.has(r.key)}" style="height:${ROW}px"><span class="g-caret" aria-hidden="true">${state.collapsed.has(r.key) ? "▸" : "▾"}</span><span class="g-txt">${esc(r.label)}</span>${r.sub ? `<span class="g-sub">${esc(r.sub)}</span>` : ""}</button>`
        : `<div class="g-row g-task" tabindex="0" data-t="${r.id}" style="height:${ROW}px" title="${esc(r.label)}"><span class="g-dot ${esc(r.status)}"></span><span class="g-txt">${esc(r.label)}</span></div>`).join("");
      // grid + axis
      let s = `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(o.aria || "Project timeline")}">
        <defs><marker id="${uid}a" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto"><path class="g-arrowhead" d="M0,0 L8,4 L0,8 z"/></marker>
        <marker id="${uid}c" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto"><path class="g-arrowhead bad" d="M0,0 L8,4 L0,8 z"/></marker>
        <pattern id="${uid}h" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="6" height="6" class="g-hatch-bg"/><line x1="0" y1="0" x2="0" y2="6" class="g-hatch"/></pattern></defs>`;
      vis.forEach((r, i) => { if (r.type === "group") s += `<rect class="g-band" x="0" y="${HEAD + i * ROW}" width="${W}" height="${ROW}"/>`; });
      for (let t = min; t <= max; t += DAY) {
        const d = new Date(t), x = ((t - min) / DAY) * dayW;
        if (d.getUTCDate() === 1) {
          s += `<line class="g-month" x1="${x}" x2="${x}" y1="0" y2="${H}"/><text class="g-axis strong" x="${x + 4}" y="14">${esc(fmtDate(d.toISOString().slice(0, 10), o.tz, { month: "short", year: "numeric" }))}</text>`;
        } else if (d.getUTCDay() === 1 && dayW >= 4) {
          s += `<line class="g-week" x1="${x}" x2="${x}" y1="22" y2="${H}"/>` + (dayW >= 9 ? `<text class="g-axis" x="${x + 3}" y="34">${d.getUTCDate()}</text>` : "");
        }
      }
      s += `<line class="g-base" x1="0" x2="${W}" y1="${HEAD - 0.5}" y2="${HEAD - 0.5}"/>`;
      if (o.today) { const tx = X(o.today); s += `<line class="g-today" x1="${tx}" x2="${tx}" y1="18" y2="${H}"/><text class="g-today-t" x="${tx + 4}" y="${HEAD - 4}">Today</text>`; }
      // bars
      const pos = (id) => y.get(id) ?? y.get("g:" + rows.find((r) => r.id === id)?.group);
      vis.forEach((r) => {
        const ry = y.get(r.type === "group" ? "g:" + r.key : r.id);
        if (!r.start || !r.end) return;
        const x1 = X(r.start), x2 = X(r.end) + dayW, w = Math.max(x2 - x1, 4);
        if (r.type === "group") {
          s += `<g class="g-sum"><rect x="${x1}" y="${ry + 12}" width="${w}" height="6" rx="1"/><path d="M${x1},${ry + 12} v10 l4,-4 M${x1 + w},${ry + 12} v10 l-4,-4"/></g>`;
        } else {
          const cls = `g-bar ${r.status} ${r.kind}${r.overdue ? " overdue" : ""}`;
          s += `<rect class="${cls}" data-t="${r.id}" x="${x1}" y="${ry + 7}" width="${w}" height="${ROW - 14}" rx="4"${r.kind === "estimated" ? ` style="fill:url(#${uid}h)"` : ""}/>`;
        }
        if (r.due) { const dx = X(r.due) + dayW / 2; s += `<path class="g-due${r.overdue ? " bad" : ""}" d="M${dx},${ry + 7} l6,8 l-6,8 l-6,-8 z"><title>Due ${esc(fmt(r.due))}</title></path>`; }
      });
      // dependency arrows (finish-to-start); collapsed tasks attach to their group row
      const seen = new Set();
      deps.forEach((e) => {
        const a = rows.find((r) => r.id === e.from), b = rows.find((r) => r.id === e.to);
        if (!a || !b || !a.end || !b.start) return;
        if (o.openOnly !== false && (a.status === "done" || b.status === "done")) return;
        const ya = pos(e.from), yb = pos(e.to);
        if (ya == null || yb == null || ya === yb) return;
        const ga = state.collapsed.has(a.group), gb = state.collapsed.has(b.group);
        const ax = X(ga ? rows.find((r) => r.key === a.group).end : a.end) + dayW, bx = X(gb ? rows.find((r) => r.key === b.group).start : b.start);
        const key = `${ya}>${yb}`; if (seen.has(key)) return; seen.add(key);
        const bad = b.conflicts && b.conflicts.includes(a.id);
        const y1 = ya + ROW / 2, y2 = yb + ROW / 2, mid = yb > ya ? yb - 3 : yb + ROW + 3;
        const d = bx - 8 >= ax + 6
          ? `M${ax},${y1} H${ax + 6} V${y2} H${bx - 1}`
          : `M${ax},${y1} H${ax + 6} V${mid} H${bx - 10} V${y2} H${bx - 1}`;
        s += `<path class="g-dep${bad ? " bad" : ""}" d="${d}" marker-end="url(#${uid}${bad ? "c" : "a"})"/>`;
      });
      s += "</svg>";
      SC.innerHTML = s;
      L.querySelectorAll(".g-group").forEach((btn) => btn.addEventListener("click", () => {
        const k = btn.dataset.g; state.collapsed.has(k) ? state.collapsed.delete(k) : state.collapsed.add(k); draw();
      }));
      const show = (id, ev) => {
        const r = rows.find((q) => q.id === id); if (!r) return;
        TIP.innerHTML = r.tip; TIP.hidden = false;
        const hb = host.getBoundingClientRect(), tw = TIP.offsetWidth;
        let left, top;
        if (ev && ev.clientX) { left = ev.clientX - hb.left + 14; top = ev.clientY - hb.top + 14; }
        else { const el = L.querySelector(`[data-t="${id}"]`); left = L.offsetWidth + 8; top = el.offsetTop + ROW; }
        TIP.style.left = Math.max(0, Math.min(left, hb.width - tw - 4)) + "px"; TIP.style.top = top + "px";
        host.querySelectorAll(`[data-t="${id}"]`).forEach((n) => n.classList.add("hot"));
      };
      const hide = () => { TIP.hidden = true; host.querySelectorAll(".hot").forEach((n) => n.classList.remove("hot")); };
      host.querySelectorAll("[data-t]").forEach((n) => {
        const id = +n.dataset.t;
        n.addEventListener("mousemove", (ev) => { hide(); show(id, ev); }); n.addEventListener("mouseleave", hide);
        n.addEventListener("focus", () => show(id)); n.addEventListener("blur", hide);
      });
      if (o.scrollToToday && o.today && !draw.done) { SC.scrollLeft = Math.max(0, X(o.today) - SC.clientWidth * 0.6); draw.done = true; }
    }
    draw();
  }

  return { gantt, esc, chip, fmtDate, daysBetween, bar, spark, flow, issueLink, STATUS };
})();
