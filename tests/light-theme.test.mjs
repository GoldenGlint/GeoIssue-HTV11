import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { build, lightColor, parseColor } from '../scripts/build-light-theme.mjs';

const luminance = hex => {
  const channel = c => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  const [r, g, b] = parseColor(hex).rgb.map(channel);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};
const contrast = (a, b) => {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
};

test('generated light theme matches styles.css', () => {
  assert.equal(readFileSync(new URL('../src/theme-light.css', import.meta.url), 'utf8'), build(),
    'Run `npm run theme` after editing src/styles.css.');
});

test('dark surfaces become light and text stays readable', () => {
  const background = lightColor('#07121f'), panel = lightColor('#0b1929');
  assert.ok(luminance(background) > 0.85 && luminance(panel) > 0.85);
  assert.ok(contrast(lightColor('#e8eef7'), panel) >= 12, 'body text');
  assert.ok(contrast(lightColor('#8398b1'), panel) >= 4.5, 'muted text');
  assert.ok(contrast(lightColor('#27b8f6'), panel) >= 4.5, 'accent text');
});

test('translucent shadows stay dark instead of turning into glows', () => {
  assert.equal(lightColor('#0004', { shadow: true }), '#0000001f');
  assert.equal(lightColor('#27b8f62b').length, 9);
});

test('every generated rule is scoped to the light theme', () => {
  const rules = build().split('\n').filter(line => line.includes('{') && !line.startsWith('@media'));
  for (const rule of rules) {
    for (const selector of rule.slice(0, rule.indexOf('{')).split(/,(?![^(]*\))/)) {
      assert.ok(selector.startsWith(':root[data-theme="light"]'), selector);
    }
  }
});
