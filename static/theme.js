/* 好奇猴快传：独立的外观控制，不依赖任何第三方框架 */
(() => {
  'use strict';

  const storageKey = 'hamoki_theme';
  const modes = new Set(['auto', 'light', 'dark']);
  const systemTheme = window.matchMedia
    ? window.matchMedia('(prefers-color-scheme: dark)')
    : null;

  // The explorer theme is the visual default; explicit saved preferences still win.
  let preference = 'dark';
  try {
    const saved = localStorage.getItem(storageKey);
    if (modes.has(saved)) preference = saved;
  } catch {
    // 禁用本地存储时，仍可在本次页面中使用外观切换。
  }

  function applyTheme() {
    const dark = preference === 'dark' ||
      (preference === 'auto' && Boolean(systemTheme && systemTheme.matches));
    document.documentElement.dataset.theme = dark ? 'dark' : 'light';

    const colorMeta = document.querySelector('meta[name="theme-color"]');
    if (colorMeta) colorMeta.content = dark ? '#061310' : '#f7fdf2';

    const select = document.getElementById('theme-mode');
    if (select) select.value = preference;
  }

  // Crossfade full-page backgrounds on modern browsers; preserve instant
  // startup and accessibility for reduced-motion preferences.
  function applyThemeWithMotion() {
    const reduceMotion = window.matchMedia &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (document.startViewTransition && document.body && !reduceMotion) {
      document.startViewTransition(() => applyTheme());
    } else {
      applyTheme();
    }
  }

  // 在样式表下载前运行，减少首次打开页面的明暗闪烁。
  applyTheme();

  document.addEventListener('DOMContentLoaded', () => {
    applyTheme();
    const select = document.getElementById('theme-mode');
    if (!select) return;
    select.addEventListener('change', () => {
      if (!modes.has(select.value)) return;
      preference = select.value;
      try {
        localStorage.setItem(storageKey, preference);
      } catch {
        // 本地存储不可用时不影响当前页面切换。
      }
      applyThemeWithMotion();
    });
  });

  if (systemTheme) {
    const onSystemChange = () => {
      if (preference === 'auto') applyThemeWithMotion();
    };
    if (typeof systemTheme.addEventListener === 'function') {
      systemTheme.addEventListener('change', onSystemChange);
    } else if (typeof systemTheme.addListener === 'function') {
      systemTheme.addListener(onSystemChange);
    }
  }
})();
