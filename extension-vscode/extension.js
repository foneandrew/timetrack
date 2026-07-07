// timetrack focus logger — the VSCode sibling of the iTerm2 focus daemon.
//
// It answers the same two questions the daemon does — "is this app frontmost?"
// and "what worktree am I looking at?" — and appends a tick to the SAME
// ~/.timetrack/focus.log in the SAME `<epoch>\t<cwd>\t<branch>` format, so the
// report stitches VSCode ticks and iTerm ticks into one dwell timeline.
//
// Unlike the browser extension there's no native-messaging host: VSCode runs in
// Node, so it writes the log file directly.
//
// The worktree is read from VSCode's built-in Git extension: only files inside a
// tracked repo resolve to a repository, which reproduces the daemon's rule that
// a directory only counts when it's a git worktree.

const vscode = require("vscode");
const fs = require("fs");
const os = require("os");
const path = require("path");

const FOCUS_LOG = path.join(os.homedir(), ".timetrack", "focus.log");
const POLL_INTERVAL_MS = 10000; // mirror the daemon's 10s poll
const MIN_LOG_GAP_SEC = 30;     // same-lane debounce, mirror the daemon

let gitApi = null;
let lastRepoRoot = null; // sticky: repo of the file we last looked at
let lastTickCwd = null;
let lastTickTime = 0;
let timer = null;

async function loadGitApi() {
  const ext = vscode.extensions.getExtension("vscode.git");
  if (!ext) return null;
  if (!ext.isActive) await ext.activate();
  try {
    return ext.exports.getAPI(1);
  } catch (_) {
    return null;
  }
}

// The repo the user is looking at: the active editor's file, else the last file
// we saw, else a repo backing an open workspace folder. Returns null when none
// resolves — same silent skip as the daemon on a non-worktree dir.
function currentRepo() {
  if (!gitApi) return null;

  const ed = vscode.window.activeTextEditor;
  if (ed && ed.document && ed.document.uri.scheme === "file") {
    const r = gitApi.getRepository(ed.document.uri);
    if (r) {
      lastRepoRoot = r.rootUri.fsPath;
      return r;
    }
  }

  if (lastRepoRoot) {
    const r = gitApi.repositories.find((x) => x.rootUri.fsPath === lastRepoRoot);
    if (r) return r;
  }

  for (const f of vscode.workspace.workspaceFolders || []) {
    const r = gitApi.getRepository(f.uri);
    if (r) return r;
  }

  return null;
}

function branchOf(repo) {
  return (repo.state.HEAD && repo.state.HEAD.name) || "HEAD";
}

// Write a tick unless it's a same-lane repeat inside the debounce window. A lane
// change always writes immediately (sharp switch boundary); `force` bypasses the
// debounce for the manual self-test.
function writeTick(cwd, branch, force) {
  const now = Math.floor(Date.now() / 1000);
  if (!force && cwd === lastTickCwd && now - lastTickTime < MIN_LOG_GAP_SEC) {
    return false;
  }
  try {
    fs.mkdirSync(path.dirname(FOCUS_LOG), { recursive: true });
    fs.appendFileSync(FOCUS_LOG, `${now}\t${cwd}\t${branch || ""}\tvscode\n`);
    lastTickCwd = cwd;
    lastTickTime = now;
    return true;
  } catch (_) {
    return false; // never let a write failure surface to the user
  }
}

function poll() {
  if (!vscode.window.state.focused) return;
  const repo = currentRepo();
  if (!repo) return;
  writeTick(repo.rootUri.fsPath, branchOf(repo), false);
}

async function activate(context) {
  gitApi = await loadGitApi();

  // Tick promptly on a focus/editor switch (the sharp boundary), like the
  // daemon's tab-change path; the interval covers motionless reading.
  context.subscriptions.push(
    vscode.window.onDidChangeWindowState(poll),
    vscode.window.onDidChangeActiveTextEditor(poll)
  );

  timer = setInterval(poll, POLL_INTERVAL_MS);
  context.subscriptions.push({ dispose: () => clearInterval(timer) });

  context.subscriptions.push(
    vscode.commands.registerCommand("timetrack.testTick", () => {
      const repo = currentRepo();
      if (!repo) {
        vscode.window.showWarningMessage(
          "timetrack: no git repo in focus — open a file in a repo and retry."
        );
        return;
      }
      const ok = writeTick(repo.rootUri.fsPath, branchOf(repo), true);
      vscode.window.showInformationMessage(
        ok
          ? `timetrack: wrote a test tick for ${path.basename(repo.rootUri.fsPath)}`
          : "timetrack: failed to write focus.log"
      );
    })
  );

  poll();
}

function deactivate() {
  if (timer) clearInterval(timer);
}

module.exports = { activate, deactivate };
