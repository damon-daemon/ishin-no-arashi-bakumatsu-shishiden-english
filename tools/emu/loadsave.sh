#!/bin/bash
# loadsave.sh [out.png] : cold boot the English build (CUE= for another image) and load a memory-card save
# (title: cursor starts on 再開 = load). SLOT=2 loads the second save (default 1). Ends at the saved place
# (~70 s). The card lives in build/dsh/duckstation/memcards/; copies are kept in sstates/card_*.mcd
# (card_s43_two_saves.mcd: 1 = Ryōma at the Chiba Dōjō menu 1857/6/6, 2 = own hero, unaffiliated start,
# enrolled at the Shigakukan, Edo: Tsukiji 1862/3/6; card_s45_three_saves.mcd adds 3 = the same hero at the
# Shinoya Inn daily menu, Kyōto: Nakagyō 1862/3/13; card_s48_osaka_nagasaki.mcd = the current card:
# 2 = that hero in Ōsaka: Dōtonbori 3/13, 3 = in Nagasaki: Dejima 3/24. The game has three slots).
D=$(cd "$(dirname "$0")" && pwd)
WAIT=20 "$D/restart.sh" >/dev/null 2>&1
"$D/hpress.sh" /dev/null Return w w w Return w w w w
"$D/hpress.sh" /dev/null X w w w w w w
# the first key after a pause is often dropped: a harmless L2 goes first, in the same call
for i in $(seq 2 "${SLOT:-1}"); do "$D/hpress.sh" /dev/null E w Down w; done
"$D/hpress.sh" /dev/null X w w w w w w w w w w w w X w w w w w w w w w w w w w w
"$D/hpress.sh" /dev/null E w   # the first key after a pause is often dropped: spend a harmless L2 (L1 switches tabs)
if [ -n "$1" ]; then "$D/hshot.sh" "$1"; fi
