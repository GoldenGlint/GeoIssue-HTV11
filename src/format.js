// Small presentation helpers shared by every view.
import { categories, wards, DEMO_DATE } from './data.js';
import { icon } from './icons.js';

export const DAY = 86400000;
export const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
export const typeColor = type => categories[type]?.color || '#4ea8ff';
export const typeIcon = type => icon(categories[type]?.icon || 'pin');
export const badge = (text, kind = '') => `<span class="badge ${kind || String(text).toLowerCase().replaceAll(' ', '-')}">${esc(text)}</span>`;
export const date = (value, options = {}) => new Date(value).toLocaleDateString('en-CA', { month: 'short', day: 'numeric', timeZone: 'America/Toronto', ...options });
export const age = issue => Math.max(0, Math.floor((Date.parse(DEMO_DATE) - Date.parse(issue.first_seen_at)) / DAY));
export const wardLabel = id => wards[id] ? `Ward ${id} · ${wards[id]}` : `Ward ${id}`;
export const percent = (part, whole) => whole ? Math.round(part / whole * 100) : 0;
export const plural = (n, word, many = `${word}s`) => `${n.toLocaleString()} ${n === 1 ? word : many}`;
export const countBy = (rows, key) => rows.reduce((counts, row) => { const k = typeof key === 'function' ? key(row) : row[key]; counts[k] = (counts[k] || 0) + 1; return counts; }, {});
/** Only http(s) links from data make it into an href; anything else (e.g. javascript:) becomes ''. */
export const safeUrl = url => { if (!url) return ''; try { const u = new URL(url, location.href); return ['http:', 'https:'].includes(u.protocol) ? u.href : ''; } catch { return ''; } };
