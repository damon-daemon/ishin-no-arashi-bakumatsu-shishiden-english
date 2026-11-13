#!/bin/bash
# hpress.sh out.png key ... : press buttons in the headless DuckStation, then take a screenshot
#   keys: X=Circle(confirm) x=Circle short tap Z=Cross(cancel) S=Triangle A=Square Return=Start
#   BackSpace=Select Q/W=L1/R1 E/R=L2/R2 Up/Down/Left/Right; 'w' alone = wait 1s;
#   out.png = /dev/null for no screenshot
# Keys go to gamescope's private X display only (tools/emu/xkeys.py).
D=$(cd "$(dirname "$0")" && pwd)
for k in "${@:2}"; do
  t=120
  case "$k" in
    w) timeout 1 tail -f /dev/null; continue;;
    x) t=40;;
    X|Z|S|A|Q|W|E|R) k=${k,,};;
  esac
  python3 "$D/xkeys.py" hold "$k" "$t" || exit 1; timeout 0.2 tail -f /dev/null
done
timeout 0.5 tail -f /dev/null
[ "$1" = /dev/null ] || "$D/hshot.sh" "$1"
