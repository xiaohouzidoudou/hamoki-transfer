/* 好奇猴快传：独立的外观控制，不依赖任何第三方框架 */
(() => {
  'use strict';

  const storageKey = 'hamoki_theme';
  const modes = new Set(['auto', 'light', 'dark']);
  const systemTheme = window.matchMedia
    ? window.matchMedia('(prefers-color-scheme: dark)')
    : null;

  let preference = 'auto';
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
    if (colorMeta) colorMeta.content = dark ? '#0b1220' : '#f8fafc';

    const select = document.getElementById('theme-mode');
    if (select) select.value = preference;
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
      applyTheme();
    });
  });

  if (systemTheme) {
    const onSystemChange = () => {
      if (preference === 'auto') applyTheme();
    };
    if (typeof systemTheme.addEventListener === 'function') {
      systemTheme.addEventListener('change', onSystemChange);
    } else if (typeof systemTheme.addListener === 'function') {
      systemTheme.addListener(onSystemChange);
    }
  }
})();
