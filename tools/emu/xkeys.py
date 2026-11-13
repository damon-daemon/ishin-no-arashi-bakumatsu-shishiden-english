"""Keyboard input for our headless DuckStation, isolated from every other program.

headless.sh runs DuckStation (Qt, xcb) inside a headless gamescope, which gives it a private
Xwayland server. XTEST key events sent to that X display reach only that DuckStation: not the
desktop, not another project's emulator. SDL input is off (datapath.py), so pads are ignored.

usage: xkeys.py hold KEY MS      press KEY (X keysym name, e.g. x, Return, Up, F10) for MS ms
       xkeys.py display          print our DuckStation's X display
       xkeys.py wayland          print our gamescope's socket
       xkeys.py pid              print our DuckStation's process id
Uses libX11 + libXtst through ctypes (no extra packages).
"""
import ctypes, os, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def emus():
    """[(pid, environment)] of our headless DuckStation's processes: those with -nogui and a disc
    path under this project in the command line that run under gamescope (the gamescope process
    itself has the same words in its command line but no GAMESCOPE_WAYLAND_DISPLAY). The AppImage
    runs as two such processes; both share the X display."""
    pids = subprocess.run(['pgrep', '-f', '--', '-nogui.*' + ROOT + '/'],
                          capture_output=True, text=True).stdout.split()
    found = []
    for pid in pids:
        try:
            env = dict(e.split(b'=', 1) for e in
                       open('/proc/%s/environ' % pid, 'rb').read().split(b'\0') if b'=' in e)
        except OSError:
            continue
        if b'GAMESCOPE_WAYLAND_DISPLAY' in env and b'DISPLAY' in env:
            found.append((int(pid), {k.decode(): v.decode() for k, v in env.items()}))
    if not found:
        sys.exit('headless DuckStation not running')
    return sorted(found)


def emu():
    """(pid, environment) of one of our emulator processes (for the display / socket)."""
    return emus()[-1]


def hold(key, ms):
    x11 = ctypes.CDLL('libX11.so.6')
    xtst = ctypes.CDLL('libXtst.so.6')
    x11.XOpenDisplay.restype = ctypes.c_void_p
    x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
    x11.XStringToKeysym.restype = ctypes.c_ulong
    x11.XStringToKeysym.argtypes = [ctypes.c_char_p]
    x11.XKeysymToKeycode.restype = ctypes.c_ubyte
    x11.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    x11.XFlush.argtypes = [ctypes.c_void_p]
    x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
    xtst.XTestFakeKeyEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]
    d = x11.XOpenDisplay(emu()[1]['DISPLAY'].encode())
    if not d:
        sys.exit('cannot open the headless X display')
    sym = x11.XStringToKeysym(key.encode())
    code = x11.XKeysymToKeycode(d, sym) if sym else 0
    if not code:
        sys.exit('unknown key %r' % key)
    xtst.XTestFakeKeyEvent(d, code, 1, 0)
    x11.XFlush(d)
    time.sleep(ms / 1000)
    xtst.XTestFakeKeyEvent(d, code, 0, 0)
    x11.XFlush(d)
    x11.XCloseDisplay(d)


if __name__ == '__main__':
    if sys.argv[1] == 'display':
        print(emu()[1]['DISPLAY'])
    elif sys.argv[1] == 'wayland':
        print(emu()[1]['GAMESCOPE_WAYLAND_DISPLAY'])
    elif sys.argv[1] == 'pid':
        print(emu()[0])
    elif sys.argv[1] == 'hold':
        hold(sys.argv[2], int(sys.argv[3]))
