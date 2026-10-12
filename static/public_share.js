'use strict';
// Keep the landing page visible while the browser starts an attachment download.
// Never claim the download has completed: the browser controls its own save UI.
const manual = document.getElementById('manual-download');
const notice = document.getElementById('wait-tip');
if (manual) {
  // No-JavaScript browsers can always use the ordinary link.
  manual.hidden = true;
  window.setTimeout(() => {
    const trigger = document.createElement('a');
    trigger.href = manual.href;
    trigger.download = '';
    trigger.hidden = true;
    document.body.append(trigger);
    trigger.click();
    trigger.remove();
  }, 350);
  window.setTimeout(() => {
    manual.hidden = false;
    if (notice) notice.textContent = '如果仍未出现下载提示，可以点击下方按钮手动下载。请勿连续点击。';
  }, 8000);
}
