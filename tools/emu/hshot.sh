#!/bin/bash
# hshot.sh out.png : native-resolution screenshot of the headless DuckStation (Screenshot
# hotkey F10 -> build/dsh/duckstation/screenshots/, moved to out.png)
D=$(cd "$(dirname "$0")" && pwd)
S="$D/../../build/dsh/duckstation/screenshots"
out=$(realpath -m "$1"); rm -f "$out"
before=$(ls -t "$S" 2>/dev/null | head -1)
python3 "$D/xkeys.py" hold F10 150 || exit 1
for i in $(seq 1 40); do
  new=$(ls -t "$S" 2>/dev/null | head -1)
  if [ -n "$new" ] && [ "$new" != "$before" ]; then
    timeout 0.4 tail -f /dev/null       # let the PNG finish
    mv "$S/$new" "$out"; exit 0; fi
  timeout 0.1 tail -f /dev/null
done
echo "no screenshot"; exit 1
