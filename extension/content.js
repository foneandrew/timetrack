// Runs on github.com. Emits a heartbeat tick while you're genuinely engaged
// with a PR page. The builder stitches ticks into review intervals, so a lost
// tick costs ~75s, not a whole session.
//
// Presence is interaction-driven, not focus-gated, because you can scroll a
// window on a second monitor without it being the focused OS window (the DOM
// `scroll` event still fires). So:
//   - interactions (scroll / click / keydown / wheel) tick even when the
//     browser isn't focused, as long as the tab is visible (on screen);
//   - a 75s heartbeat ticks while the tab IS focused, to cover motionless
//     reading;
//   - everything is debounced to at most one tick per 30s.
// An ignored/parked tab gets no interactions, so it doesn't count.
//
// GitHub is an SPA, so location/JIRA are re-read live on every tick.

const HEARTBEAT_MS = 75000;
const DEBOUNCE_MS = 30000;
let lastSent = 0;

function isPR() {
  return /^\/[^/]+\/[^/]+\/pull\/\d+/.test(location.pathname);
}

function visible() {
  return document.visibilityState === "visible";
}

function branchNames() {
  return [...document.querySelectorAll('[data-component="BranchName"]')]
    .map(e => (e.textContent || "").trim()).filter(Boolean);
}

function inferJira() {
  const title = document.querySelector(".js-issue-title")?.textContent || document.title || "";
  const m = (title + " " + branchNames().join(" ")).match(/([A-Za-z]+-\d+)/);
  return m ? m[1].toUpperCase() : "";
}

// the PR's head (feature) branch — prefer the one carrying a jira tag, else the
// last BranchName on the page (head is rendered after base)
function prBranch() {
  const names = branchNames();
  return names.find(n => /[A-Za-z]+-\d+/.test(n)) || names[names.length - 1] || "";
}

function maybeTick() {
  if (!isPR() || !visible()) return;
  const now = Date.now();
  if (now - lastSent < DEBOUNCE_MS) return;
  lastSent = now;
  try {
    chrome.runtime.sendMessage({
      type: "review-tick",
      epoch: Math.floor(now / 1000),
      jira: inferJira(),
      url: location.href,
      title: document.title,
      branch: prBranch()
    });
  } catch (e) { /* SW asleep / context invalidated — next interaction retries */ }
}

// intentful interactions — fire even when the window isn't focused
["scroll", "click", "keydown", "wheel"].forEach(ev =>
  window.addEventListener(ev, maybeTick, { passive: true, capture: true }));
document.addEventListener("visibilitychange", maybeTick);
window.addEventListener("focus", maybeTick);

// heartbeat only while clearly active, for reading without interacting
setInterval(() => { if (document.hasFocus()) maybeTick(); }, HEARTBEAT_MS);

maybeTick();
