// ==UserScript==
// @name         lite browser 示例脚本
// @namespace    litebrowser.test.demo
// @version      1.0.0
// @description  演示油猴脚本接口：注入横幅、GM 存储读写、跨域请求、注册菜单命令
// @author       lvzian
// @match        http://*/*
// @match        https://*/*
// @grant        GM_getValue
// @grant        GM_setValue
// @grant        GM_addStyle
// @grant        GM_log
// @grant        GM_registerMenuCommand
// @grant        GM_xmlhttpRequest
// @run-at       document-idle
// ==/UserScript==

(function () {
  'use strict';

  var runs = (GM_getValue('runs', 0) || 0) + 1;
  GM_setValue('runs', runs);
  GM_setValue('lastUrl', location.href);

  GM_addStyle([
    '#lb-userscript-demo{position:fixed;z-index:2147483646;right:8px;bottom:8px;',
    'padding:8px 12px;border:1px solid #003C74;border-radius:4px;',
    'background:linear-gradient(#FFFDF5,#FFE9B0);color:#003C74;',
    'font:12px/1.6 "Microsoft YaHei UI",sans-serif;box-shadow:0 2px 6px rgba(0,0,0,.35)}',
    '#lb-userscript-demo b{color:#C6362B}'
  ].join(''));

  var box = document.createElement('div');
  box.id = 'lb-userscript-demo';
  box.innerHTML =
    '油猴脚本已运行<br>' +
    '累计执行：<b>' + runs + '</b> 次<br>' +
    '当前站点：<b>' + location.hostname + '</b><br>' +
    '<span id="lb-userscript-demo-xhr">跨域请求测试中…</span>';
  (document.body || document.documentElement).appendChild(box);

  window.__lbUserscriptDemo = {
    runs: runs,
    url: location.href,
    hasGM: typeof GM_xmlhttpRequest === 'function'
  };

  GM_registerMenuCommand('查看脚本运行次数', function () {
    var total = GM_getValue('runs', 0);
    var last = GM_getValue('lastUrl', '');
    alert('本脚本已运行 ' + total + ' 次\n最近访问：' + last);
  });

  // 演示 GM_xmlhttpRequest：由宿主（Python）代为发起请求，绕过同源限制
  GM_xmlhttpRequest({
    method: 'GET',
    url: 'https://cn.bing.com/search?q=lite+browser+test',
    timeout: 15000,
    onload: function (response) {
      var node = document.getElementById('lb-userscript-demo-xhr');
      if (node) {
        node.textContent = 'GM_xmlhttpRequest：HTTP ' + response.status +
          '，返回 ' + (response.responseText || '').length + ' 字节';
      }
      window.__lbUserscriptDemo.xhrStatus = response.status;
      window.__lbUserscriptDemo.xhrLength = (response.responseText || '').length;
      GM_log('GM_xmlhttpRequest 成功，状态码 ' + response.status);
    },
    onerror: function (response) {
      var node = document.getElementById('lb-userscript-demo-xhr');
      if (node) {
        node.textContent = 'GM_xmlhttpRequest 失败：' + response.statusText;
      }
      window.__lbUserscriptDemo.xhrStatus = -1;
    }
  });
})();
