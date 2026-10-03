// lite browser 示例扩展 —— MV3 后台 Service Worker
// 只做最小验证：能加载即说明扩展的后台脚本运行正常。
chrome.runtime.onInstalled.addListener(function (details) {
  console.log('[lite browser 示例扩展] onInstalled:', details.reason);
});

chrome.runtime.onMessage.addListener(function (message, sender, sendResponse) {
  if (message && message.type === 'ping') {
    sendResponse({ pong: true, from: 'lite browser 示例扩展' });
  }
  return true;
});
