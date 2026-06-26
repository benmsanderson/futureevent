#!/usr/bin/env bash
# Refresh the June 2026 event on ERA5T *reanalysis*, centred on 24 June.
#
# Safe to run repeatedly (e.g. from a daily cron). It aborts cleanly until
# ERA5T reanalysis has cleared the 24 June peak (FE_REQUIRE_ERA5T_THROUGH),
# and once it succeeds it drops a sentinel so later runs become no-ops.
#
#   - FE_TODAY=2026-07-02        pins the 20-day event window to ~12 Jun-2 Jul
#                               (covers 24 June no matter when this fires).
#   - FE_REQUIRE_ERA5T_THROUGH  the event peak day; event_field aborts if
#                               reanalysis has not reached it (peak still forecast).
#   - climatology + CMIP6 caches are reused (cache/ is populated); no 1.1 TB re-read.
#   - MAX_WORKERS self-caps at 24 on the shared node (good-neighbour).
set -euo pipefail

REPO="/storage/no-backup-nac/users/bensan/futureevent"
# Absolute pixi path: cron runs with a minimal PATH that lacks ~/.pixi/bin.
PIXI="/uio/kant/div-cicero-u1/bensan/.pixi/bin/pixi"
cd "$REPO"

export FE_TODAY="2026-07-02"
export FE_REQUIRE_ERA5T_THROUGH="2026-06-24"

LOG="$REPO/cache/reanalysis_refresh.log"
SENTINEL="$REPO/cache/.reanalysis_refresh.done"

if [[ -f "$SENTINEL" ]]; then
  echo "$(date -u +%FT%TZ) already refreshed (sentinel present); nothing to do." >>"$LOG"
  exit 0
fi

echo "$(date -u +%FT%TZ) starting reanalysis refresh (FE_TODAY=$FE_TODAY, require>=$FE_REQUIRE_ERA5T_THROUGH)" >>"$LOG"

# 1. Coarse grid + live event on reanalysis (event field re-run; GEV fits reused).
#    No --reuse-event: we WANT the fresh reanalysis event.
if ! "$PIXI" run python -m precompute.grid >>"$LOG" 2>&1; then
  echo "$(date -u +%FT%TZ) precompute.grid aborted (reanalysis not ready yet?). Will retry." >>"$LOG"
  exit 1
fi

# 2. Fine local_txx grid + France-peak (climatology cache reused).
if ! "$PIXI" run python -m precompute.local_peak >>"$LOG" 2>&1; then
  echo "$(date -u +%FT%TZ) precompute.local_peak failed." >>"$LOG"
  exit 1
fi

touch "$SENTINEL"
echo "$(date -u +%FT%TZ) refresh complete; outputs regenerated. Sentinel written." >>"$LOG"
echo "$(date -u +%FT%TZ) NEXT: validate (event_peak_day set, Toulouse rises), update RESULTS.md, commit output/**." >>"$LOG"
