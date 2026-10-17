import { isSampleData, sampleWord } from './state.js';
// Small accessible search popup. Items come from the shared, filtered dataset.
export function attachSearch(input, { getItems, onChoose, icon }) {
  const popup = document.createElement('div');
  popup.className = 'search-suggestions';
  popup.id = 'map-search-results';
  popup.setAttribute('role', 'listbox');
  popup.setAttribute('aria-label', `Matching ${sampleWord()}places and issues`);
  popup.hidden = true;
  input.closest('.map-search-row').append(popup);
  input.setAttribute('role', 'combobox');
  input.setAttribute('aria-autocomplete', 'list');
  input.setAttribute('aria-controls', popup.id);
  input.setAttribute('aria-expanded', 'false');
  input.autocomplete = 'off';
  let items = [], active = -1;

  const close = () => {
    popup.hidden = true;
    active = -1;
    input.setAttribute('aria-expanded', 'false');
    input.removeAttribute('aria-activedescendant');
  };
  const highlight = () => {
    for (const [index, row] of [...popup.querySelectorAll('[role=option]')].entries()) {
      row.classList.toggle('active', index === active);
      row.setAttribute('aria-selected', String(index === active));
    }
    if (active >= 0) input.setAttribute('aria-activedescendant', `search-option-${active}`);
    else input.removeAttribute('aria-activedescendant');
  };
  const choose = index => {
    const item = items[index];
    if (!item) return;
    close();
    onChoose(item);
  };
  const update = () => {
    const query = input.value.trim();
    if (query.length < 2) { close(); return; }
    items = getItems(query).slice(0, 6);
    active = -1;
    popup.replaceChildren();
    const heading = document.createElement('div');
    heading.className = 'search-suggestion-heading';
    heading.textContent = items.length ? 'Jump to a place or issue' : `No matching ${sampleWord()}issues`;
    popup.append(heading);
    for (const [index, item] of items.entries()) {
      const row = document.createElement('div');
      row.className = 'search-suggestion';
      row.id = `search-option-${index}`;
      row.setAttribute('role', 'option');
      row.setAttribute('aria-selected', 'false');
      const glyph = document.createElement('span');
      glyph.className = 'suggestion-icon';
      glyph.innerHTML = icon(item.kind === 'area' ? 'map' : 'pin');
      const copy = document.createElement('span');
      const title = document.createElement('strong'); title.textContent = item.label;
      const description = document.createElement('small'); description.textContent = item.description;
      copy.append(title, description);
      const enter = document.createElement('span'); enter.className = 'suggestion-enter'; enter.textContent = '↵';
      row.append(glyph, copy, enter);
      row.onpointerdown = event => { event.preventDefault(); choose(index); };
      row.onpointermove = () => { active = index; highlight(); };
      popup.append(row);
    }
    if (!items.length) {
      const hint = document.createElement('p');
      hint.textContent = 'Try an address, neighbourhood, or issue ID. Other filters still apply.';
      popup.append(hint);
    }
    const footer = document.createElement('div');
    footer.className = 'search-suggestion-footer';
    footer.textContent = `↑ ↓ Navigate   ↵ Open   Esc Close${isSampleData() ? ' · Sample records' : ''}`;
    popup.append(footer);
    popup.hidden = false;
    input.setAttribute('aria-expanded', 'true');
  };

  input.addEventListener('input', update);
  input.addEventListener('focus', update);
  input.addEventListener('blur', close);
  input.addEventListener('keydown', event => {
    if (event.key === 'Escape' && !popup.hidden) { event.preventDefault(); event.stopPropagation(); close(); return; }
    if (!['ArrowDown', 'ArrowUp', 'Enter'].includes(event.key)) return;
    if (popup.hidden && event.key !== 'Enter') update();
    if (popup.hidden || !items.length) return;
    event.preventDefault();
    if (event.key === 'Enter') choose(active < 0 ? 0 : active);
    else {
      const down = event.key === 'ArrowDown';
      active = active < 0 ? (down ? 0 : items.length - 1) : (active + (down ? 1 : -1) + items.length) % items.length;
      highlight();
    }
  });
  return { close };
}
