#!/bin/bash
# toduel.sh out.png : loadsave.sh, then the route to Nihonbashi > Find Person > Mori Yōzō (6th in the list).
# Ends on the search result ("on the road" or "inside Genbukan": check the picture; the search can also fail).
# On the road: X, Down, X (Attack at Once), X (yes), X, X -> duel field after ~8 s.
D=$(cd "$(dirname "$0")" && pwd)
"$D/loadsave.sh"; timeout 10 tail -f /dev/null
"$D/hpress.sh" /dev/null E Up w X w w w X w w w
"$D/hpress.sh" /dev/null E Down Down Down Down w X w w w w
"$D/hpress.sh" /dev/null E X w w Down Down Down w X w w Down Down Down w X w w w w w
"$D/hpress.sh" /dev/null E Down w X w w Down Down Down Down Down w X w w X w w w w
"$D/hshot.sh" "${1:-/dev/null}"
