// Dashboard charts on a trimmed Apache ECharts build (src/vendor/echarts.js, fetched on first use; regenerate it
// with scripts/vendor-echarts.mjs). Colours come from the CSS tokens and follow the theme. A chart plays its
// entrance once it scrolls into view; when its page only redraws (a filter change, a refresh) it morphs from the
// previous frame instead, so the numbers visibly move rather than reload.
import { esc } from './format.js';
import { icon } from './icons.js';

let lib = null, loading = null;
export const loadCharts = () => loading ??= import('./vendor/echarts.js').then(module => (lib = module));

// Read on use rather than at import, so the module also loads under Node for the tests.
const still = { get matches() { return globalThis.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? true; } };
const live = new Set();    // { el, key, build, chart, stop }
const frames = new Map();  // key -> the last option drawn, kept while the page only redraws

export function chartTokens() {
  const css = getComputedStyle(document.documentElement), v = name => css.getPropertyValue(name).trim();
  return {
    surface: v('--surface'), surface3: v('--surface-3'), border: v('--border'), borderStrong: v('--border-strong'),
    text: v('--text'), text2: v('--text-2'), text3: v('--text-3'), accent: v('--accent'), accentText: v('--accent-text'),
    danger: v('--danger'), dangerText: v('--danger-text'), warning: v('--warning'), success: v('--success'), font: css.fontFamily,
  };
}

/** Settings every chart shares: motion timings, type, and the HTML tooltip styled by .chart-tooltip in styles.css. */
export function baseOption(t, extra = {}) {
  const motion = !still.matches;
  return {
    animation: motion, animationDuration: 700, animationEasing: 'cubicOut', animationDurationUpdate: 450, animationEasingUpdate: 'cubicInOut',
    stateAnimation: { duration: motion ? 180 : 0, easing: 'cubicOut' },
    textStyle: { fontFamily: t.font, fontSize: 12, color: t.text3 },
    ...extra,
    tooltip: {
      appendTo: 'body', className: 'chart-tooltip', backgroundColor: t.surface, borderColor: t.border, borderWidth: 1, padding: 0,
      transitionDuration: motion ? 0.18 : 0, textStyle: { fontFamily: t.font, color: t.text },
      // Above and right of the pointer, flipping left near the edge, so the hovered mark stays visible.
      position: (point, params, dom, rect, size) => [
        point[0] + 14 + size.contentSize[0] > size.viewSize[0] ? Math.max(0, point[0] - 14 - size.contentSize[0]) : point[0] + 14,
        Math.max(-size.contentSize[1], point[1] - size.contentSize[1] - 14)],
      ...extra.tooltip,
    },
  };
}

/** Tooltip body: the value leads, the label follows, keyed by a short stroke of the mark's colour. */
export const tipHtml = (value, label, color, note = '') => `<div class="chart-tip"><strong>${color ? `<i style="background:${esc(color)}"></i>` : ''}${esc(value)}</strong><span>${esc(label)}</span>${note ? `<small>${esc(note)}</small>` : ''}</div>`;

/** A Lucide icon as an image for ECharts rich text, stroked in `color`. */
export const iconImage = (name, color) => `data:image/svg+xml;charset=utf-8,${encodeURIComponent(icon(name).replace('<svg', '<svg xmlns="http://www.w3.org/2000/svg"').replace('currentColor', color))}`;

/**
 * Draws `build(tokens, el)` into `el`. `morph(previous, next)` returns the frame a redraw starts from (by default
 * the previous option itself); `onDraw(chart, previous)` runs once the chart is on screen.
 */
export function mountChart(el, key, build, { morph, onDraw } = {}) {
  if (!el) return;
  if (!lib) { loadCharts().then(() => el.isConnected && mountChart(el, key, build, { morph, onDraw }), () => el.classList.add('chart-failed')); return; }
  for (const entry of live) if (entry.key === key || !entry.el.isConnected) dispose(entry);
  const entry = { el, key, build }, previous = frames.get(key);
  live.add(entry);
  const draw = () => {
    if (!live.has(entry)) return;
    const chart = entry.chart = lib.init(el, null, { renderer: 'svg' }), option = build(chartTokens(), el);
    if (previous) chart.setOption({ ...(morph ? morph(previous, option) : previous), animation: false });
    chart.setOption(option);
    frames.set(key, option);
    el.closest('.row-chart')?.classList.add('is-charted');
    let size = `${el.clientWidth}x${el.clientHeight}`, frame;
    const resize = new ResizeObserver(() => {
      if (`${el.clientWidth}x${el.clientHeight}` === size) return;
      size = `${el.clientWidth}x${el.clientHeight}`;
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => { chart.resize(); chart.setOption({ ...build(chartTokens(), el), animation: false }); });
    });
    resize.observe(el);
    entry.stop = () => { resize.disconnect(); cancelAnimationFrame(frame); };
    onDraw?.(chart, previous);
  };
  // A redraw replaces the chart in place; a first draw waits until the chart is on screen so its entrance is seen.
  if (previous || still.matches) { draw(); return; }
  const seen = new IntersectionObserver(([hit]) => { if (hit.isIntersecting) { seen.disconnect(); draw(); } }, { threshold: .2 });
  seen.observe(el);
  entry.stop = () => seen.disconnect();
}

function dispose(entry) {
  entry.stop?.();
  entry.chart?.dispose();
  live.delete(entry);
}

/** Before a page redraws: drop the charts, keeping their frames to morph from unless the visitor is leaving the page. */
export function destroyCharts(keepFrames) {
  live.forEach(dispose);
  if (!keepFrames) frames.clear();
}

export const chartFor = el => [...live].find(entry => entry.el === el)?.chart;

// A theme switch repaints every chart from the new tokens; the colours ease across rather than snapping.
if (globalThis.document) new MutationObserver(() => {
  const t = chartTokens();
  for (const entry of live) if (entry.chart) { const option = entry.build(t, entry.el); entry.chart.setOption(option); frames.set(entry.key, option); }
}).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });

// ---- Shared chart forms ----

/** A line over time with a 10% wash, a snapping crosshair and a readout, `tips(index)`, per position. */
export function lineOption(t, { labels, values, tips, ticks, color = t.accent, height }) {
  const n = values.length, marks = new Set(ticks ?? [0, Math.round((n - 1) / 3), Math.round(2 * (n - 1) / 3), n - 1]);
  return baseOption(t, {
    grid: { left: 0, right: 10, top: 12, bottom: 2, outerBoundsMode: 'same', outerBoundsContain: 'axisLabel' },
    xAxis: {
      type: 'category', data: labels, boundaryGap: false,
      axisLine: { lineStyle: { color: t.border } }, axisTick: { show: false },
      axisLabel: { color: t.text3, fontSize: 12, margin: 10, interval: index => marks.has(index), hideOverlap: true },
      axisPointer: { show: true, type: 'line', snap: true, label: { show: false }, lineStyle: { color: t.borderStrong, width: 1, type: 'solid' } },
    },
    yAxis: {
      type: 'value', minInterval: 1, splitNumber: height < 160 ? 2 : 3, max: ({ max }) => Math.max(2, Math.ceil(max / 2) * 2),
      axisLabel: { color: t.text3, fontSize: 12, margin: 12 }, splitLine: { lineStyle: { color: t.border, width: 1, type: 'solid' } },
    },
    tooltip: { trigger: 'axis', axisPointer: { type: 'line' }, formatter: ([point]) => tips(point.dataIndex) },
    series: [{
      type: 'line', data: values, color, showSymbol: false, symbol: 'circle', symbolSize: 9,
      lineStyle: { width: 2, cap: 'round', join: 'round' }, areaStyle: { color, opacity: .1 },
      itemStyle: { color, borderColor: t.surface, borderWidth: 2 },
      emphasis: { scale: 1.25, itemStyle: { color, borderColor: t.surface, borderWidth: 2 }, lineStyle: { width: 2 } },
      animationDuration: 900, animationEasing: 'cubicInOut',
    }],
  });
}

/** A trend line for a stat tile: no axes, no readout, just the shape. */
export const sparkOption = (t, values, color) => baseOption(t, {
  grid: { left: 2, right: 2, top: 3, bottom: 3 },
  xAxis: { type: 'category', show: false, boundaryGap: false, data: values.map((_, j) => j) },
  yAxis: { type: 'value', show: false, min: 0, max: ({ max }) => Math.max(1, max) },
  tooltip: { show: false },
  series: [{ type: 'line', data: values, color, silent: true, showSymbol: false, lineStyle: { width: 1.6, join: 'round' }, areaStyle: { color, opacity: .08 }, animationDuration: 1100, animationDelay: 250 }],
});

let ruler;
const textWidth = (text, font) => { ruler ??= document.createElement('canvas').getContext('2d'); ruler.font = `12px ${font}`; return ruler.measureText(text).width; };
/** Splits `text` at spaces into lines no wider than `width`. */
const wrap = (text, width, font) => text.split(' ').reduce((lines, word) => {
  const joined = lines.length ? `${lines.at(-1)} ${word}` : word;
  if (lines.length && textWidth(joined, font) <= width) lines[lines.length - 1] = joined; else lines.push(word);
  return lines;
}, []);

/**
 * Horizontal bars, one row per item in the given order: labels (with an optional icon and note) on the left,
 * values on the right. `display` overrides the value shown, for bars drawn on a transformed scale.
 */
export function rowsOption(t, el, rows, { max, delay = 0 } = {}) {
  // The label column fits the longest label, up to 45% of the chart; a note that is still too long wraps.
  const width = el.clientWidth, counted = rows.every(r => r.display === undefined), indent = r => r.icon ? 26 : 0;
  const left = Math.min(14 + Math.max(...rows.map(r => indent(r) + Math.max(textWidth(r.name, t.font), r.note ? textWidth(r.note, t.font) : 0))), Math.round(width * .45));
  const lines = (r, key) => wrap(r[key], left - 12 - indent(r), t.font).map(line => `{${key}|${line}}`).join('\n');
  const right = 14 + 7 * Math.max(2, ...rows.map(r => (r.display ?? r.value.toLocaleString()).length)); // room for the widest value
  const rich = { name: { color: t.text2, fontSize: 12, lineHeight: 16 }, note: { color: t.text3, fontSize: 12, lineHeight: 16 }, gap: { width: 9 } };
  rows.forEach((r, j) => { if (r.icon) rich[`i${j}`] = { width: 17, height: 17, backgroundColor: { image: iconImage(r.icon, r.color) } }; });
  return baseOption(t, {
    grid: { left, right, top: 0, bottom: 0, outerBoundsMode: 'none' },
    xAxis: { type: 'value', show: false, min: 0, max: max ?? Math.max(1, ...rows.map(r => r.value)) },
    yAxis: {
      type: 'category', inverse: true, data: rows.map(r => r.key), axisLine: { show: false }, axisTick: { show: false },
      axisLabel: {
        align: 'left', margin: left, rich,
        formatter: (key, j) => { const r = rows[j]; return `${r.icon ? `{i${j}|}{gap|}` : ''}${lines(r, 'name')}${r.note ? `\n${lines(r, 'note')}` : ''}`; },
      },
    },
    tooltip: { trigger: 'item', formatter: ({ dataIndex }) => rows[dataIndex].tip },
    series: [{
      type: 'bar', barWidth: 8, data: rows.map(r => ({ name: r.key, value: r.value, itemStyle: { color: r.color } })),
      showBackground: true, backgroundStyle: { color: t.surface3, borderRadius: 4 }, itemStyle: { borderRadius: 4 },
      label: {
        show: true, position: 'right', color: t.text, fontSize: 12, fontWeight: 500, valueAnimation: counted,
        formatter: ({ dataIndex, value }) => counted ? Math.round(value).toLocaleString() : rows[dataIndex].display,
      },
      labelLayout: { x: width, align: 'right', verticalAlign: 'middle' },
      emphasis: { focus: 'self' }, blur: { itemStyle: { opacity: .35 }, label: { opacity: .5 } },
      animationDelay: j => delay + j * 45, animationDuration: 650, animationEasing: 'cubicOut',
    }],
  });
}

/** A redraw of a row chart starts every bar from its own previous value, in the new order, so no bar slides between rows. */
export function morphRows(previous, next) {
  const was = new Map(previous.series[0].data.map(d => [d.name, d.value]));
  return { ...next, series: [{ ...next.series[0], data: next.series[0].data.map(d => ({ ...d, value: was.get(d.name) ?? 0 })) }] };
}

/** Hovering or focusing an overlay row (a real button or div over the chart) lights up its bar and readout. */
export function bindRows(container) {
  container?.querySelectorAll('.chart-rows>*').forEach((row, dataIndex) => {
    const chart = () => chartFor(container.querySelector('.chart-canvas'));
    const on = () => { chart()?.dispatchAction({ type: 'highlight', seriesIndex: 0, dataIndex }); chart()?.dispatchAction({ type: 'showTip', seriesIndex: 0, dataIndex }); };
    const off = () => { chart()?.dispatchAction({ type: 'downplay', seriesIndex: 0, dataIndex }); chart()?.dispatchAction({ type: 'hideTip' }); };
    row.addEventListener('pointerenter', on); row.addEventListener('pointerleave', off);
    row.addEventListener('focus', on); row.addEventListener('blur', off);
  });
}

/** Eases a number shown in `el` from what it shows now to `to`. */
const tweens = new WeakMap();
export function countTo(el, to, { from, duration = 600 } = {}) {
  if (!el) return;
  cancelAnimationFrame(tweens.get(el));
  const start = from ?? (Number(el.dataset.shown) || 0), began = performance.now();
  const paint = value => { el.dataset.shown = value; el.textContent = Math.round(value).toLocaleString(); };
  if (still.matches || start === to) { paint(to); return; }
  const step = now => {
    const k = Math.min(1, (now - began) / duration);
    paint(start + (to - start) * (1 - (1 - k) ** 3));
    if (k < 1) tweens.set(el, requestAnimationFrame(step));
  };
  tweens.set(el, requestAnimationFrame(step));
}
