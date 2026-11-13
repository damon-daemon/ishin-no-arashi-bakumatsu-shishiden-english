#!/bin/bash
# headless.sh image.cue [state.sav] : run DuckStation on a disc inside a headless gamescope
# (no window on the desktop). Drive it with hpress.sh (keys via tools/emu/xkeys.py on
# gamescope's private X display), look with hshot.sh, read RAM with ram.py / gdbmem.py.
# Config/data: build/dsh (tools/emu/datapath.py). Log: build/dsh/headless.log
# Stop: tools/emu/headless.sh stop   (the disc path is passed without resolving symlinks, so it
# stays under this project and our process filter finds it: use the links in the project root)
#
# Runs side by side with other projects' headless emulators: input never leaves our X
# display, SDL pads are off, own data dir and GDB port, stop kills only our processes.
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
T="$ROOT/build/dsh"
if [ "$1" = stop ]; then
  # every process of ours has the disc path under $ROOT in its command line (gamescope, AppImage, AppRun)
  pkill -TERM -f -- "-nogui.*$ROOT/"; timeout 3 tail -f /dev/null
  pkill -f -- "-nogui.*$ROOT/"; exit 0
fi
python3 "$ROOT/tools/emu/datapath.py" "$T" >/dev/null
state=(); [ -n "$2" ] && state=(-statefile "$(realpath "$2")")
(XDG_CONFIG_HOME="$T" env -u WAYLAND_DISPLAY QT_QPA_PLATFORM=xcb gamescope --backend headless -W 640 -H 480 -- \
  ~/.local/bin/DuckStation-x64.AppImage -batch -fastboot -nogui "${state[@]}" -- "$(realpath -s "$1")" \
  > "$T/headless.log" 2>&1 &)
