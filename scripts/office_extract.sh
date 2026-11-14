#!/usr/bin/env bash
# Measures Jodi's office from the game (Etappe 3, E10): extracts the cooked level and what it references from the game pak, reads the
# actors (office_level.py), exports the meshes with UE Viewer (umodel, glTF), samples them in Blender (tools/blender/office_scan.py) and
# builds the cat's map (office_map.py -> assets/office/office_map.json + review picture). Everything else stays in build/velvetpaws/office/.
# Usage: scripts/office_extract.sh [--level]   (--level: only extract and read the level)
set -eo pipefail
source "$(dirname "$0")/../config.sh"
O="$BUILD/velvetpaws/office"; P="$O/pak"; C="$P/TheKillingAntidote/Content"; PY="$BUILD/venv/bin/python"
mkdir -p "$O"
PAK="$GAME/Content/Paks/pakchunk0-WindowsNoEditor.pak"
python3 "$ALTUI_DEV/scripts/pak11_extract.py" "$PAK" "$P" 'Project/Maps/JodisOffice\.u' 'Project/Maps/JodisOffice/' > "$O/extract_level.log"
# Blueprint classes of placed actors live elsewhere too: read the level once, extract what it names, read again until nothing is missing
for round in 1 2 3 4 5 6; do   # one round per parent Blueprint level (door: 3 levels deep, 4 rounds)
  "$PY" "$W/scripts/velvetpaws/office_level.py" "$C" "$O/actors.json" | tee "$O/level.log"
  missing=$("$PY" -c 'import json,os,sys; L=json.load(open(sys.argv[1])); c=sys.argv[2]
print(" ".join("^.*Content/"+p[len("/Game/"):]+"\\." for p in L["packages"] if not os.path.exists(os.path.join(c, p[len("/Game/"):]+".uasset"))))' "$O/actors.json" "$C")
  [ -z "$missing" ] && break
  python3 "$ALTUI_DEV/scripts/pak11_extract.py" "$PAK" "$P" $missing >> "$O/extract_level.log"
done
[ -z "$missing" ] || { echo "office: packages still missing after 6 rounds: $missing"; exit 1; }
[[ " $* " == *" --level "* ]] && exit 0
test -x "$UMODEL" || { echo "umodel missing: $UMODEL (git clone --depth 1 https://github.com/gildor2/UEViewer \"$BUILD/tools/UEViewer\" && cd it && ./build.sh)"; exit 1; }
G="$O/gltf"; rm -rf "$G"; mkdir -p "$G"; : > "$O/umodel.log"
"$PY" -c 'import json,sys; [print(p) for p in json.load(open(sys.argv[1]))["packages"]]' "$O/actors.json" | while read -r pkg; do
  rel="${pkg#/Game/}"
  [ -f "$C/$rel.uasset" ] || continue
  (cd "$C" && timeout 120 "$UMODEL" -game=ue4.27 -path="$C" -export -gltf -notex -out="$G" "$rel.uasset" >> "$O/umodel.log" 2>&1) || echo "umodel failed: $rel" >> "$O/umodel.log"
done
blender -b --factory-startup --python-exit-code 1 --python "$W/tools/blender/office_scan.py" -- "$O" > "$O/scan.log" 2>&1 || { tail -20 "$O/scan.log"; exit 1; }
grep "SCAN" "$O/scan.log"; grep -q "SCAN OK" "$O/scan.log"
"$PY" "$W/scripts/velvetpaws/office_map.py" "$O" "$W/assets/office/office_map.json" "$BUILD/velvetpaws/review/office/office_map.png" | tee "$O/map.log"
grep -q "MAP OK" "$O/map.log"
