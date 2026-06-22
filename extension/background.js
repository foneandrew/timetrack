// Service worker: the ONLY place native messaging is available (content
// scripts can't call it). Relays review ticks to the native host, one-shot.
const HOST = "com.timetrack.review";

function logTick(tick) {
  chrome.runtime.sendNativeMessage(HOST, tick, () => {
    if (chrome.runtime.lastError) {
      console.warn("timetrack: native message failed —", chrome.runtime.lastError.message);
    }
  });
}

chrome.runtime.onMessage.addListener((msg) => {
  if (msg && msg.type === "review-tick") {
    logTick({ epoch: msg.epoch, jira: msg.jira, url: msg.url, title: msg.title });
  }
});

// Toolbar click = bridge self-test (writes a TEST-1 line to review.log).
chrome.action.onClicked.addListener(() => {
  logTick({
    epoch: Math.floor(Date.now() / 1000),
    jira: "TEST-1",
    url: "test://toolbar",
    title: "toolbar bridge test"
  });
});
