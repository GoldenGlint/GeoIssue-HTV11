// Generates src/theme-light.css from src/styles.css: every declaration with a colour literal is
// repeated under :root[data-theme="light"] with its lightness remapped in OKLab. Run `npm run theme`
// after editing styles.css; tests fail if the generated file is stale.
import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const ROOT = new URL('../', import.meta.url);
const SOURCE = new URL('src/styles.css', ROOT);
const TARGET = new URL('src/theme-light.css', ROOT);
const SCOPE = ':root[data-theme="light"]';

// Hand-tuned exceptions that a colour remap cannot express.
const MANUAL = `${SCOPE}{color-scheme:light}
${SCOPE} .tile-layer img{filter:grayscale(.6) brightness(1.03) contrast(.94)}
${SCOPE} .map-pin{color:color-mix(in srgb,var(--pin),#000 30%)}
${SCOPE} .map-pin.cluster{color:#0d4f7a}
${SCOPE} .route-bar i{background:#e08a12}
${SCOPE} .route-bar.faded i{background:#efd2a6}`;

// Dark-theme OKLab lightness → light-theme lightness. The darkest page background becomes a pale
// grey, raised panels become whiter, borders mid-light, and light text/accents become dark.
const LIGHTNESS = [[0, 0.9], [0.12, 0.94], [0.2, 0.975], [0.25, 0.997], [0.3, 0.935], [0.4, 0.85],
  [0.55, 0.65], [0.7, 0.53], [0.82, 0.46], [0.92, 0.3], [1, 0.2]];
const SHADOW_PROPS = /^(box-shadow|text-shadow|filter)$/;
const COLOR = /#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)/g;

const toLinear = c => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
const toGamma = c => (c <= 0.0031308 ? 12.92 * c : 1.055 * c ** (1 / 2.4) - 0.055);

function toOklab([r, g, b]) {
  [r, g, b] = [r, g, b].map(toLinear);
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  return [0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s,
    1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s,
    0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s];
}

function fromOklab([L, a, b]) {
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3;
  return [4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s].map(toGamma);
}

export function parseColor(text) {
  if (text.startsWith('#')) {
    let hex = text.slice(1);
    if (hex.length <= 4) hex = [...hex].map(c => c + c).join('');
    const values = hex.match(/../g).map(h => parseInt(h, 16) / 255);
    return { rgb: values.slice(0, 3), alpha: values[3] ?? 1 };
  }
  const parts = text.slice(text.indexOf('(') + 1, -1).split(/[\s,/]+/).filter(Boolean).map(Number);
  return { rgb: parts.slice(0, 3).map(v => v / 255), alpha: parts[3] ?? 1 };
}

function formatColor(rgb, alpha) {
  const hex = [...rgb, ...(alpha < 1 ? [alpha] : [])]
    .map(v => Math.round(Math.min(1, Math.max(0, v)) * 255).toString(16).padStart(2, '0')).join('');
  return `#${hex}`;
}

function mapLightness(L) {
  for (let i = 1; i < LIGHTNESS.length; i++) {
    const [x0, y0] = LIGHTNESS[i - 1], [x1, y1] = LIGHTNESS[i];
    if (L <= x1) return y0 + ((L - x0) / (x1 - x0)) * (y1 - y0);
  }
  return LIGHTNESS.at(-1)[1];
}

/** Light-theme equivalent of one dark-theme colour. `shadow` keeps translucent dark shadows dark. */
export function lightColor(text, { shadow = false } = {}) {
  const { rgb, alpha } = parseColor(text);
  const [L, a, b] = toOklab(rgb);
  if (shadow && alpha < 1 && L < 0.4) return formatColor(rgb, alpha * 0.45);
  const target = mapLightness(L);
  // Pale surfaces keep only a hint of their tint; then reduce chroma until the colour fits sRGB.
  let chroma = target > 0.9 ? 0.3 : 1;
  let out = fromOklab([target, a * chroma, b * chroma]);
  while (out.some(v => v < -0.001 || v > 1.001) && chroma > 0.01) {
    chroma *= 0.95;
    out = fromOklab([target, a * chroma, b * chroma]);
  }
  return formatColor(out, alpha);
}

// Minimal CSS reader for this hand-written stylesheet: rules, nested @media/@supports, comments.
function split(text, separator) {
  const parts = [];
  let depth = 0, quote = '', start = 0;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (quote) { if (c === quote && text[i - 1] !== '\\') quote = ''; continue; }
    if (c === '"' || c === "'") quote = c;
    else if (c === '(' || c === '[') depth++;
    else if (c === ')' || c === ']') depth--;
    else if (c === separator && depth === 0) { parts.push(text.slice(start, i)); start = i + 1; }
  }
  parts.push(text.slice(start));
  return parts.map(p => p.trim()).filter(Boolean);
}

function blocks(text) {
  const found = [];
  let i = 0;
  while (i < text.length) {
    const open = text.indexOf('{', i);
    const semi = text.indexOf(';', i);
    if (open === -1) break;
    if (semi !== -1 && semi < open && text.slice(i, semi).trim().startsWith('@')) { i = semi + 1; continue; }
    let depth = 1, j = open + 1;
    while (depth && j < text.length) {
      if (text[j] === '{') depth++;
      else if (text[j] === '}') depth--;
      j++;
    }
    found.push({ prelude: text.slice(i, open).trim(), body: text.slice(open + 1, j - 1) });
    i = j;
  }
  return found;
}

function scopeSelector(selector) {
  return split(selector, ',').map(s => {
    if (s.startsWith(':root')) return SCOPE + s.slice(5);
    if (/^html\b/.test(s)) return SCOPE + s.slice(4);
    return `${SCOPE} ${s}`;
  }).join(',');
}

function convert(text) {
  const out = [];
  for (const { prelude, body } of blocks(text)) {
    if (prelude.startsWith('@media') || prelude.startsWith('@supports')) {
      const inner = convert(body);
      if (inner) out.push(`${prelude}{\n${inner}\n}`);
      continue;
    }
    if (prelude.startsWith('@')) continue;
    const declarations = split(body, ';').filter(d => d.includes(':') && d.match(COLOR))
      .map(d => {
        const property = d.slice(0, d.indexOf(':')).trim();
        return d.replace(COLOR, c => lightColor(c, { shadow: SHADOW_PROPS.test(property) }));
      });
    if (declarations.length) out.push(`${scopeSelector(prelude)}{${declarations.join(';')}}`);
  }
  return out.join('\n');
}

export function build(source = readFileSync(SOURCE, 'utf8')) {
  const css = source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/@import\s+url\([^)]*\)[^;]*;/g, '');
  return `/* Generated by scripts/build-light-theme.mjs from styles.css. Do not edit; run \`npm run theme\`. */\n${convert(css)}\n${MANUAL}\n`;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  writeFileSync(TARGET, build());
  console.log(`Wrote ${fileURLToPath(TARGET)}`);
}
