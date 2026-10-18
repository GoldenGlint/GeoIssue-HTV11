// Dark/light/system appearance. index.html applies the saved choice before first paint; this keeps it in sync.
import { read, persist } from './state.js';

const THEME_COLORS = { dark: '#07121f', light: '#eff4fa' };
const systemLight = matchMedia('(prefers-color-scheme: light)');

export const themePreference = () => read('theme', 'dark');
export const activeTheme = (preference = themePreference()) =>
  preference === 'light' || (preference === 'system' && systemLight.matches) ? 'light' : 'dark';

export function applyTheme(preference = themePreference()) {
  const theme = activeTheme(preference);
  document.documentElement.dataset.theme = theme;
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', THEME_COLORS[theme]);
  document.querySelector('meta[name="color-scheme"]')?.setAttribute('content', theme);
}

export function setTheme(preference) {
  persist('theme', preference);
  applyTheme(preference);
}

systemLight.addEventListener('change', () => { if (themePreference() === 'system') applyTheme(); });
