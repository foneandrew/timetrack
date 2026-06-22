// Runs on github.com. Emits a heartbeat tick every ~75s while a PR page is
// the genuine foreground tab (lenient presence: visible + focused). The
// builder stitches ticks into review intervals — so a lost tick costs ~75s,
// not a whole session, and crashes/quits don't drop an open block.
//
// GitHub is an SPA (Turbo nav between PRs with no reload), so everything is
// re-evaluated against live location each tick rather than scraped once.

const TICK_MS = 75000;
const MIN_GAP_MS = 30000;
let lastSent = 0;

function isPR() {
  return /^\/[^/]+\/[^/]+\/pull\/\d+/.test(location.pathname);
}

function foreground() {
  return document.visibilityState === "visible" && document.hasFocus();
}

function inferJira() {
  // PR title leads (curated, e.g. "PBL-7317 ..."); branch names back it up.
  // A PR has two BranchName elements (base + head) — base is usually `main`
  // with no JIRA, so the first regex match across them is the head's ticket.
  const title = document.querySelector(".js-issue-title")?.textContent || document.title || "";
  const branches = [...document.querySelectorAll('[data-component="BranchName"]')]
    .map(e => e.textContent || "").join(" ");
  const m = (title + " " + branches).match(/([A-Za-z]+-\d+)/);
  return m ? m[1].toUpperCase() : "";
}

function tick() {
  if (!isPR() || !foreground()) return;
  const now = Date.now();
  if (now - lastSent < MIN_GAP_MS) return;
  lastSent = now;
  // url + title are logged raw every tick so the builder can re-infer the
  // JIRA later even when the branch/title scrape misses.
  try {
    chrome.runtime.sendMessage({
      type: "review-tick",
      epoch: Math.floor(now / 1000),
      jira: inferJira(),
      url: location.href,
      title: document.title
    });
  } catch (e) { /* SW asleep / context invalidated — next tick retries */ }
}

setInterval(tick, TICK_MS);
document.addEventListener("visibilitychange", tick);
window.addEventListener("focus", tick);
tick();
