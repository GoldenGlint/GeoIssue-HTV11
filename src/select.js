// Dropdown select: the one control for picking from a list, everywhere in the app. selectHtml() draws a button with a
// native <select> hidden behind it, and that select stays the source of truth: forms submit it, views read `.value`
// and listen for `change` exactly as they would on a plain select. The list opens in one shared popover, built from
// the select's options each time, and every key and click is handled from the document, so a view only renders the
// markup. After setting `.value` or `.disabled` from code, call syncSelect() so the button shows it.
import { icon } from './icons.js';
import { esc } from './format.js';

const toOption = o => typeof o !== 'object' ? { value: String(o), text: String(o) }
  : Array.isArray(o) ? { value: String(o[0]), text: String(o[1]) }
  : { ...o, value: String(o.value), text: o.text ?? String(o.value) };
function optionsHtml(options, value) {
  return options.map(o => {
    if (o?.group) return `<optgroup label="${esc(o.group)}">${optionsHtml(o.options, value)}</optgroup>`;
    const { value: v, text, icon: glyph, color, disabled } = toOption(o);
    return `<option value="${esc(v)}" ${v === value ? 'selected' : ''} ${disabled ? 'disabled' : ''} ${glyph ? `data-icon="${esc(glyph)}"` : ''} ${color ? `data-color="${esc(color)}"` : ''}>${esc(text)}</option>`;
  }).join('');
}
const leadHtml = (glyph, color) => glyph ? `<span class="select-lead" ${color ? `style="color:${esc(color)}"` : ''}>${icon(glyph)}</span>` : '';

/**
 * options: strings, [value, text] pairs or { value, text, icon, color, disabled }; { group, options } is a labelled group.
 * placeholder: shown in muted text while the value is '' and left out of the list (a required select must then be chosen).
 * variant: '' for a 32px control, 'block' for a full-width form field, 'pill' for the header data switch, 'quiet' for bare text.
 * search: placeholder for a search field at the top of the list, for long lists. attrs: extra attributes for the <select>.
 */
export function selectHtml({ id = '', name = '', label = '', options = [], value = '', placeholder = '', icon: glyph = '', variant = '', search = '', required = false, disabled = false, title = '', className = '', attrs = '' }) {
  value = String(value ?? '');
  const native = `<select class="select-native" ${id ? `id="${esc(id)}"` : ''} ${name ? `name="${esc(name)}"` : ''} ${required ? 'required' : ''} ${disabled ? 'disabled' : ''} ${attrs} tabindex="-1" aria-hidden="true">${placeholder ? `<option value="" hidden ${value ? '' : 'selected'}>${esc(placeholder)}</option>` : ''}${optionsHtml(options, value)}</select>`;
  const flat = options.flatMap(o => o?.group ? o.options : [o]).map(toOption);
  const chosen = flat.find(o => o.value === value) || (placeholder ? null : flat[0]);
  const lead = chosen?.icon ? leadHtml(chosen.icon, chosen.color) : leadHtml(glyph);
  return `<div class="select ${variant} ${chosen ? '' : 'is-placeholder'} ${className}" ${glyph ? `data-icon="${esc(glyph)}"` : ''} ${search ? `data-search="${esc(search)}"` : ''} ${title ? `title="${esc(title)}"` : ''}><button type="button" class="select-trigger" role="combobox" aria-haspopup="listbox" aria-expanded="false" ${label ? `aria-label="${esc(label)}"` : ''} ${disabled ? 'disabled' : ''}>${lead}<span class="select-value">${esc(chosen ? chosen.text : placeholder)}</span>${icon('chevron', 'select-chevron')}</button>${native}</div>`;
}

/** Shows the native select's current value and disabled state on its button. */
export function syncSelect(native) {
  const root = native?.closest?.('.select'), trigger = root?.querySelector('.select-trigger');
  if (!trigger) return;
  const option = native.selectedOptions[0];
  root.querySelector('.select-value').textContent = option?.textContent ?? '';
  root.classList.toggle('is-placeholder', !option || option.hidden);
  trigger.disabled = native.disabled;
  const lead = root.querySelector('.select-lead'), html = leadHtml(option?.dataset.icon || root.dataset.icon, option?.dataset.icon ? option.dataset.color : '');
  if (lead) lead.outerHTML = html; else trigger.insertAdjacentHTML('afterbegin', html);
}

/** Places a top-layer menu under its anchor (left or right edges aligned), or above it when there is more room there. */
export function placeMenu(menu, anchor, align = 'start') {
  const r = anchor.getBoundingClientRect(), gap = 6, edge = 8;
  const below = innerHeight - r.bottom - gap - edge, above = r.top - gap - edge;
  menu.style.removeProperty('--menu-room');
  const up = menu.offsetHeight > below && above > below;
  menu.style.setProperty('--menu-room', `${Math.floor(up ? above : below)}px`);
  const width = menu.offsetWidth, height = menu.offsetHeight;
  const left = Math.max(edge, Math.min(align === 'end' ? r.right - width : r.left, innerWidth - edge - width));
  menu.style.left = `${Math.round(left)}px`;
  menu.style.top = `${Math.round(up ? r.top - gap - height : r.bottom + gap)}px`;
  menu.dataset.side = up ? 'top' : 'bottom';
}

// ---- The shared list ----
let menu, open = null, closed = { trigger: null, at: 0 }, typed = '', typedAt = 0;

function ensureMenu() {
  if (menu) return menu;
  menu = document.createElement('div');
  menu.className = 'menu select-menu';
  menu.popover = 'auto';
  document.body.append(menu);
  menu.addEventListener('beforetoggle', e => { if (e.newState === 'closed') ended(); });
  menu.addEventListener('pointermove', e => {
    const item = e.target.closest('[role="option"]');
    if (item && !item.classList.contains('active')) highlight(Number(item.dataset.index), false);
  });
  // Keep focus on the button (or the search field) when an option is pressed.
  menu.addEventListener('mousedown', e => { if (!e.target.closest('input')) e.preventDefault(); });
  menu.addEventListener('input', e => { if (e.target.matches('.menu-search input')) filter(e.target.value); });
  return menu;
}

function show(trigger, { focusSearch = false, at = 'selected' } = {}) {
  const root = trigger.closest('.select'), native = root.querySelector('.select-native');
  if (native.disabled || open?.trigger === trigger) return;
  if (open) hide();
  ensureMenu();
  const items = [];
  const item = option => {
    const index = items.push({ option, value: option.value, text: option.textContent, disabled: option.disabled }) - 1;
    const lead = option.dataset.icon ? `<span class="menu-item-icon" style="color:${esc(option.dataset.color || '')}">${icon(option.dataset.icon)}</span>` : '';
    return `<div class="menu-item" role="option" id="select-option-${index}" data-index="${index}" aria-selected="${option.selected}" ${option.disabled ? 'aria-disabled="true"' : ''}>${lead}<span>${esc(option.textContent)}</span>${icon('check', 'menu-item-check')}</div>`;
  };
  const list = [...native.children].map((child, g) => child.tagName === 'OPTGROUP'
    ? `<div role="group" aria-labelledby="select-group-${g}"><div class="menu-label" id="select-group-${g}">${esc(child.label)}</div>${[...child.children].filter(o => !o.hidden).map(item).join('')}</div>`
    : child.hidden ? '' : item(child)).join('');
  const label = trigger.getAttribute('aria-label') || root.closest('label')?.firstChild?.textContent?.trim() || 'Options';
  const search = root.dataset.search ? `<div class="menu-search">${icon('search')}<input type="text" role="combobox" aria-expanded="true" aria-controls="select-listbox" aria-autocomplete="list" aria-label="${esc(root.dataset.search)}" placeholder="${esc(root.dataset.search)}" autocomplete="off" spellcheck="false"></div>` : '';
  menu.innerHTML = `${search}<div class="menu-list" role="listbox" id="select-listbox" aria-label="${esc(label)}">${list}</div><p class="menu-empty" hidden>No matches</p>`;
  menu.style.minWidth = `${Math.max(root.offsetWidth, 160)}px`;
  open = { root, trigger, native, items, active: -1, place: null };
  trigger.setAttribute('aria-expanded', 'true');
  trigger.setAttribute('aria-controls', 'select-listbox');
  menu.showPopover({ source: trigger });
  // Follow the button while the list is open: the map's filters slide when its panel opens, and rows scroll sideways.
  let last = '';
  const track = () => {
    if (!open) return;
    if (!trigger.isConnected) { hide(); return; }
    const r = trigger.getBoundingClientRect(), key = `${r.left},${r.top},${r.width},${innerWidth},${innerHeight}`;
    if (key !== last) { last = key; placeMenu(menu, root); }
    open.place = requestAnimationFrame(track);
  };
  track();
  const enabled = items.map((it, i) => it.disabled ? -1 : i).filter(i => i >= 0);
  const selected = items.findIndex(it => it.option.selected && !it.disabled);
  highlight(at === 'last' ? enabled.at(-1) : at === 'first' ? enabled[0] : selected >= 0 ? selected : enabled[0], true, 'center');
  if (search && focusSearch) menu.querySelector('.menu-search input').focus();
}

let hiding = false;
function hide() {
  if (!menu?.matches(':popover-open')) return;
  hiding = true;
  menu.hidePopover();
  hiding = false;
}
function ended() {
  if (!open) return;
  const { trigger, place } = open;
  cancelAnimationFrame(place);
  trigger.setAttribute('aria-expanded', 'false');
  trigger.removeAttribute('aria-controls');
  trigger.removeAttribute('aria-activedescendant');
  // Focus left in the list (the search field) goes back to the button, unless the click went somewhere else.
  if (menu.contains(document.activeElement)) trigger.focus({ preventScroll: true });
  // Only a light dismiss (a press outside the list, which may be on this button) guards against reopening.
  closed = { trigger: hiding ? null : trigger, at: performance.now() };
  open = null;
}

const visible = () => open.items.map((it, i) => i).filter(i => !open.items[i].disabled && !menu.querySelector(`#select-option-${i}`).hidden);
function highlight(index, scroll = true, block = 'nearest') {
  if (!open || index == null || index < 0) return;
  menu.querySelector('.menu-item.active')?.classList.remove('active');
  const el = menu.querySelector(`#select-option-${index}`);
  el.classList.add('active');
  open.active = index;
  open.trigger.setAttribute('aria-activedescendant', el.id);
  menu.querySelector('.menu-search input')?.setAttribute('aria-activedescendant', el.id);
  if (!scroll) return;
  // Scroll the list by hand: scrollIntoView could also move the page under a fixed menu.
  const list = menu.querySelector('.menu-list'), top = el.offsetTop, bottom = top + el.offsetHeight;
  if (block === 'center') list.scrollTop = top - (list.clientHeight - el.offsetHeight) / 2;
  else if (top < list.scrollTop) list.scrollTop = top - 5;
  else if (bottom > list.scrollTop + list.clientHeight) list.scrollTop = bottom - list.clientHeight + 5;
}
function move(step) {
  const order = visible(), at = order.indexOf(open.active);
  if (!order.length) return;
  const next = at < 0 ? (step > 0 ? 0 : order.length - 1) : Math.max(0, Math.min(order.length - 1, at + step));
  highlight(order[next]);
}

function filter(query) {
  const q = query.trim().toLowerCase();
  open.items.forEach((it, i) => { menu.querySelector(`#select-option-${i}`).hidden = !!q && !it.text.toLowerCase().includes(q); });
  menu.querySelectorAll('[role="group"]').forEach(g => { g.hidden = !g.querySelector('[role="option"]:not([hidden])'); });
  const order = visible();
  menu.querySelector('.menu-empty').hidden = order.length > 0;
  if (order.length) highlight(order.includes(open.active) ? open.active : order[0]);
  else { menu.querySelector('.menu-item.active')?.classList.remove('active'); open.active = -1; }
}

/** Jumps to the next option starting with what was typed; repeating one letter cycles through its options. */
function typeahead(char) {
  const now = performance.now();
  typed = now - typedAt > 700 ? char : typed + char;
  typedAt = now;
  const query = [...typed].every(c => c === typed[0]) ? typed[0] : typed, order = visible();
  const from = order.indexOf(open.active) + (query.length === 1 ? 1 : 0);
  const match = [...order.slice(from), ...order.slice(0, from)].find(i => open.items[i].text.toLowerCase().startsWith(query.toLowerCase()));
  if (match != null) highlight(match);
}

function choose(index) {
  const it = open?.items[index];
  if (!it || it.disabled) return;
  const { native, trigger } = open, changed = !it.option.selected;
  // Changing a filter can redraw the page, so remember how to find this select's new button afterwards.
  const key = native.id ? `#${CSS.escape(native.id)}` : native.dataset.filter ? `[data-filter="${native.dataset.filter}"]` : '';
  it.option.selected = true;
  hide();
  trigger.focus({ preventScroll: true });
  syncSelect(native);
  if (!changed) return;
  native.dispatchEvent(new Event('input', { bubbles: true }));
  native.dispatchEvent(new Event('change', { bubbles: true }));
  if (!trigger.isConnected && key) document.querySelector(`.select-native${key}`)?.closest('.select').querySelector('.select-trigger').focus({ preventScroll: true });
}

document.addEventListener('click', e => {
  const trigger = e.target.closest?.('.select-trigger');
  if (trigger) {
    // A press on the open button closes the list through light dismiss before this click arrives; don't reopen it.
    if (open?.trigger === trigger) hide();
    else if (!(closed.trigger === trigger && performance.now() - closed.at < 400)) show(trigger, { focusSearch: matchMedia('(pointer: fine)').matches });
    return;
  }
  const item = e.target.closest?.('.select-menu [role="option"]');
  if (item) choose(Number(item.dataset.index));
});

// Capture phase, so an open list gets Escape and the arrow keys before the dialog or the page shortcuts do.
document.addEventListener('keydown', e => {
  // Form validation focuses the native select of a required field it rejects; keys there drive the drawn list too.
  const trigger = e.target.closest?.('.select-trigger') || (e.target.matches?.('.select-native') ? e.target.closest('.select').querySelector('.select-trigger') : null);
  const inMenu = !!open && menu.contains(e.target);
  if (!trigger && !inMenu) return;
  const printable = e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey && e.key !== '/';
  const handled = () => { e.preventDefault(); e.stopPropagation(); };
  if (!open || open.trigger !== trigger && !inMenu) {
    if (['ArrowDown', 'ArrowUp', 'Enter', ' '].includes(e.key)) { handled(); show(trigger, { focusSearch: true, at: e.key === 'ArrowUp' ? 'last' : 'selected' }); }
    else if (printable && e.key !== ' ') {
      handled();
      show(trigger, { focusSearch: true });
      const input = menu.querySelector('.menu-search input');
      if (input) { input.value = e.key; filter(e.key); } else typeahead(e.key);
    }
    return;
  }
  const inSearch = e.target.matches('.menu-search input');
  switch (e.key) {
    case 'ArrowDown': handled(); move(1); break;
    case 'ArrowUp': handled(); if (e.altKey) choose(open.active); else move(-1); break;
    case 'PageDown': handled(); move(10); break;
    case 'PageUp': handled(); move(-10); break;
    case 'Home': case 'End': if (!inSearch) { handled(); move(e.key === 'Home' ? -Infinity : Infinity); } break;
    case 'Enter': handled(); choose(open.active); break;
    case 'Escape': handled(); hide(); trigger?.focus(); break;
    // Tab closes the list without choosing; from the search field it returns to the button first.
    case 'Tab': if (inSearch) handled(); hide(); break;
    case ' ': if (!inSearch && performance.now() - typedAt > 700) { handled(); choose(open.active); break; }
    // fall through: a space inside a typed word is part of the word
    default:
      if (printable && !inSearch) {
        handled();
        const input = menu.querySelector('.menu-search input');
        if (input) { input.focus(); input.value += e.key; filter(input.value); } else typeahead(e.key);
      }
  }
}, true);
// Space opens the list on keydown; its keyup would otherwise click the button and close it again.
document.addEventListener('keyup', e => { if (e.key === ' ' && e.target.closest?.('.select-trigger')) e.preventDefault(); }, true);

// A select changed some other way (the keyboard on its native control after form validation focused it) redraws its button.
document.addEventListener('change', e => { if (e.target.matches?.('.select-native')) syncSelect(e.target); }, true);
