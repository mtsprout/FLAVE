#!/bin/bash
# upstream_watch.sh - daily check of FilmLadd's FLAVE for new commits.
# READ-ONLY toward upstream: only `git fetch upstream` (its push URL is
# disabled). Nothing is merged, checked out or pushed. When upstream/main has
# moved since the last report, Claude (headless, read-only git tools) writes a
# triage report to upstream-reports/YYYY-MM-DD.md and a macOS notification is
# posted. Run by launchd (tools/io.github.mtsprout.flave-upstream-watch.plist)
# at 07:00; run it by hand any time.   --force  re-reports the current state.

set -u
export PATH="$HOME/.local/bin:/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$REPO/upstream-reports"
STATE="$OUT/.last_reported"
LOG="$OUT/watch.log"
mkdir -p "$OUT"
cd "$REPO" || exit 1

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "$LOG"; }
notify() {
  /usr/bin/osascript -e "display notification \"$2\" with title \"$1\"" >/dev/null 2>&1
}

log "check start"
if ! git fetch upstream >>"$LOG" 2>&1; then
  log "fetch failed"
  exit 0
fi
NEW="$(git rev-parse upstream/main)"
LAST="$(cat "$STATE" 2>/dev/null || true)"
if [ "$NEW" = "$LAST" ] && [ "${1:-}" != "--force" ]; then
  log "no change ($NEW)"
  exit 0
fi

BASE="$(git merge-base HEAD upstream/main)"
if [ "$BASE" = "$NEW" ]; then
  log "upstream/main already merged ($NEW)"
  echo "$NEW" > "$STATE"
  exit 0
fi
COUNT="$(git rev-list --count "$BASE..upstream/main")"
REPORT="$OUT/$(date +%F).md"
log "upstream moved: $COUNT new commit(s), $BASE..$NEW"

PROMPT="You are triaging new commits in FilmLadd's original FLAVE repo for a Mac fork (branch macos-cpu-backend, a CPU/numpy backend with a unified Qt window). Read MACOS-PORT.md and the memory-style notes in it first (seams, shared files that are merge hot spots, the sync routine). New upstream commits: git log $BASE..upstream/main ; diff: git diff $BASE upstream/main . Do NOT modify anything; you only have read-only git and file reads. Write a markdown report with these sections:
1. Summary - what changed, in plain words, per commit (use counter.txt BUILD bumps and messages).
2. Does it apply to the Mac fork? For each change say: applies as is / needs a Mac port / Windows-NVIDIA only (ignore).
3. Port work needed - changes to GPU kernels or _blend in sequence_player_gpu.py that must be mirrored in cpu_compositor.blend_layer; new windows or menus to hook into workspace.py; new CUDA-only calls needing a CPU path; new DB columns/migrations that touch our added columns (clips.fit_percent, footage.display_name, sequences.mark_in/mark_out).
4. Merge forecast - files changed upstream that we also edited (conflict likely); run: git merge-tree $(git merge-base HEAD upstream/main) HEAD upstream/main  (this git has no --write-tree) and report whether it is clean or lists conflicts.
5. Recommendation - merge now / merge after porting X / skip, and the first steps.
Be concise and concrete. Output only the report."

if REPORT_BODY="$(claude -p "$PROMPT" \
    --allowedTools "Read,Grep,Glob,Bash(git log:*),Bash(git diff:*),Bash(git show:*),Bash(git merge-tree:*),Bash(git merge-base:*),Bash(git rev-parse:*),Bash(git status:*),Bash(git ls-tree:*)" \
    --max-turns 40 2>>"$LOG")" && [ -n "$REPORT_BODY" ]; then
  {
    echo "# Upstream changes: $COUNT new commit(s)"
    echo
    echo "Checked $(date '+%Y-%m-%d %H:%M'). Range \`${BASE:0:9}..${NEW:0:9}\` on filmladd-sys/FLAVE main."
    echo "Nothing was merged. To act on this, start a session and say \"merge upstream\"."
    echo
    echo "$REPORT_BODY"
  } > "$REPORT"
  log "report written: $REPORT"
else
  {
    echo "# Upstream changes: $COUNT new commit(s)"
    echo
    echo "Automatic triage failed (see watch.log). Raw commits:"
    echo
    git log --stat "$BASE..upstream/main"
  } > "$REPORT"
  log "triage failed; wrote raw log to $REPORT"
fi

echo "$NEW" > "$STATE"
notify "FLAVE: FilmLadd pushed changes" "$COUNT new commit(s). Report: upstream-reports/$(basename "$REPORT")"
# open the report from the notification is not possible with osascript; the
# path above is in the repo folder.
