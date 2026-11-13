#!/bin/bash
# restart.sh [state.sav] : stop this project's emulator and boot the English build (optionally
# from a state). CUE=path boots another image (e.g. the clean ishin_shishiden.cue). WAIT=seconds.
D=$(cd "$(dirname "$0")" && pwd); R=$(cd "$D/../.." && pwd)
"$D/headless.sh" stop; timeout 2 tail -f /dev/null
"$D/headless.sh" "${CUE:-$R/build/ishin_shishiden_en.cue}" ${1:+"$1"}
for i in $(seq 1 40); do python3 "$D/xkeys.py" pid >/dev/null 2>&1 && break; timeout 0.5 tail -f /dev/null; done
timeout ${WAIT:-10} tail -f /dev/null
