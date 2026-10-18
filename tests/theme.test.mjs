import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

// The two theme palettes in src/styles.css: light on :root, dark under :root[data-theme="dark"].
const css = readFileSync(new URL('../src/styles.css', import.meta.url), 'utf8');
const tokens = selector => {
  const body = css.match(new RegExp(`${selector.replace(/[[\]"=]/g, '\\$&')}\\{(--bg:[^}]*)\\}`))[1];
  return Object.fromEntries(body.split(';').filter(d => d.startsWith('--')).map(d => d.slice(2).split(/:(.*)/s).slice(0, 2)));
};
const themes = { light: tokens(':root'), dark: tokens(':root[data-theme="dark"]') };

const luminance = hex => {
  const [r, g, b] = hex.match(/^#(..)(..)(..)$/).slice(1).map(h => parseInt(h, 16) / 255).map(c => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};
const contrast = (a, b) => { const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x); return (hi + 0.05) / (lo + 0.05); };

test('both themes define the same tokens', () => {
  assert.deepEqual(Object.keys(themes.dark).sort(), Object.keys(themes.light).sort());
});

test('text tokens meet WCAG AA (4.5:1) on every surface they sit on, in both themes', () => {
  const pairs = [
    ...['text', 'text-2', 'text-3', 'accent-text', 'danger-text', 'warning-text', 'success-text', 'purple-text'].flatMap(fg => ['bg', 'surface', 'surface-2'].map(bg => [fg, bg])),
    ['text-3', 'surface-3'], ['on-accent', 'accent'], ['on-accent', 'accent-hover'], ['on-danger', 'danger'],
    ['accent-text', 'accent-soft'], ['danger-text', 'danger-soft'], ['warning-text', 'warning-soft'], ['success-text', 'success-soft'], ['purple-text', 'purple-soft'],
  ];
  for (const [name, t] of Object.entries(themes)) {
    for (const [fg, bg] of pairs) {
      const ratio = contrast(t[fg], t[bg]);
      assert.ok(ratio >= 4.5, `${name}: --${fg} on --${bg} is ${ratio.toFixed(2)}:1`);
    }
  }
});
