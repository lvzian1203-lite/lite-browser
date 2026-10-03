// lite browser 示例扩展 —— 内容脚本
// 作用：在每个页面顶部插入一条横幅，方便确认扩展已被 Chromium 加载。
(function () {
  'use strict';
  if (document.getElementById('lb-ext-demo-banner')) {
    return;
  }
  function inject() {
    var bar = document.createElement('div');
    bar.id = 'lb-ext-demo-banner';
    bar.textContent = 'Chrome 扩展已注入：lite browser 示例扩展 v1.0.0';
    bar.style.cssText = [
      'position:fixed', 'z-index:2147483647', 'left:0', 'right:0', 'top:0',
      'height:28px', 'line-height:28px', 'text-align:center',
      'font:13px/28px "Microsoft YaHei UI",sans-serif',
      'color:#fff', 'background:linear-gradient(#0B5FE6,#0A46B8)',
      'box-shadow:0 1px 4px rgba(0,0,0,.4)', 'pointer-events:none'
    ].join(';');
    (document.body || document.documentElement).appendChild(bar);
    document.documentElement.style.paddingTop = '28px';
    window.__lbExtensionDemo = { injected: true, url: location.href };
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', inject);
  } else {
    inject();
  }
})();
