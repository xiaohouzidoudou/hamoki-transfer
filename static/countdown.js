'use strict';
// Shared one-second countdown for the success panel and public pickup pages.
(() => {
  const timers = document.querySelectorAll('[data-expiry-countdown]');
  if (!timers.length) return;
  const pad = n => String(n).padStart(2, '0');
  function refresh() {
    const now = Date.now() / 1000;
    for (const timer of timers) {
      const output = timer.querySelector('strong');
      if (!output) continue;
      const expires = Number(timer.dataset.expires);
      if (!Number.isFinite(expires) || expires <= 0) {
        output.textContent = '等待生成';
        timer.classList.remove('expired');
        continue;
      }
      const remaining = Math.max(0, Math.ceil(expires - now));
      timer.classList.toggle('expired', remaining === 0);
      if (!remaining) {
        output.textContent = '已过期';
        continue;
      }
      const days = Math.floor(remaining / 86400);
      const hours = Math.floor(remaining % 86400 / 3600);
      const minutes = Math.floor(remaining % 3600 / 60);
      const seconds = remaining % 60;
      output.textContent = (days ? days + '天 ' : '') +
        pad(hours) + ':' + pad(minutes) + ':' + pad(seconds);
    }
  }
  window.hamokiRefreshCountdown = refresh;
  refresh();
  window.setInterval(refresh, 1000);
})();
