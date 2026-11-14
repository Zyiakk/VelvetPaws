#!/usr/bin/env bash
# Builds build/VelvetPaws.pak (/Game/Mod/VelvetPaws) and installs it to the game's Mods/. Usage: scripts/build.sh [--no-deploy]
# Steps: Blender model (cat.fbx + cat.blend), bake (pattern masks, normal map, card and eye textures), animation sequences
# (cat_anims.py, tools/blender/cat_seqs.py) with review tiles -> contact sheets (anim_sheet.py) -> sounds (sound_synth.py, sound_sheet.py) -> unit tests -> kit import with
# its own skeleton and physics asset (scripts/import_cat.py + sounds scripts/import_sounds.py) -> BPGen (office structs and tables, SG_VP_Cat, sequences, blend space,
# ABP_VP_Cat, montages, BP_VP_Cat as a Character with its component defaults, AltUI tables, loader and mod tables) -> kit animation test (scripts/test_anims_kit.py) -> kit behaviour test (scripts/test_behaviour_kit.py) -> Wine cook -> pak -> verify_modpak.py +
# scripts/verify_cooked.py -> Mods/. The game must be closed (ue.sh and wincook.sh refuse otherwise).
# Measured 2026-11-14 (stage 5, with AltUI page and UI kit test): 398 s (6 min 38 s); stage 4 (sounds) was 396 s; stage 3 was 335 s (model 86 s, bake 115 s, anims with tiles 29 s, import 16 s, BPGen 16 s, kit test 10 s, cook 58 s).
# Needs AltUI's interface and structs in the kit (/Game/Mod/AltUI/...) and Mods/AltUI.pak in the game.
# Needs in the kit: /Game/Mod/TKA_BlueprintLoader/BlueprintToLoad_Struct and /Game/Project/Tables/DLC_Struct (stand-ins of the
# loader's and the game's structs, never packed); in the game: Content/Paks/~mods/TKA_BlueprintLoader.pak.
# Deploy: the game's file is removed before the `cp`, so a hardlink to the file elsewhere is never written through
# (the archived pak stays as it was; the deployed file becomes a new, separate copy).
set -eo pipefail
source "$(dirname "$0")/../config.sh"
MOD=VelvetPaws; H="$BUILD/velvetpaws"; mkdir -p "$H"
BL=(blender -b --factory-startup --python-exit-code 1 --python)
fail() { echo "$1 failed: $2"; tail -8 "$2" 2>/dev/null; exit 1; }

for f in Mod/TKA_BlueprintLoader/BlueprintToLoad_Struct Project/Tables/DLC_Struct Mod/AltUI/BPI_AltUIMod Mod/AltUI/S_AltUIModEntry \
         Mod/AltUI/S_AltUIModField Mod/AltUI/S_AltUIModAction Mod/AltUI/S_AltUIModPreset; do
  [ -f "$KIT/Content/$f.uasset" ] || { echo "kit lacks /Game/$f (stand-in of the Blueprint Loader / game struct, or AltUI's mod interface: build AltUI first)"; exit 1; }; done
[ -f "$GAME/Mods/AltUI.pak" ] || { echo "AltUI.pak missing: $GAME/Mods/AltUI.pak (the cat's page and interface come from it; the import check needs its file list)"; exit 1; }
[ -f "$GAME/Content/Paks/~mods/TKA_BlueprintLoader.pak" ] || { echo "Blueprint Loader pak missing: $GAME/Content/Paks/~mods/TKA_BlueprintLoader.pak (install it first; the build needs its struct and the cat will not spawn without it)"; exit 1; }

"${BL[@]}" "$W/tools/blender/cat_model.py" -- "$H" > "$H/model.log" 2>&1 || fail model "$H/model.log"
grep -q "CAT OK" "$H/model.log" || fail model "$H/model.log"
"${BL[@]}" "$W/tools/blender/cat_bake.py" -- "$H" > "$H/bake.log" 2>&1 || fail bake "$H/bake.log"
grep -q "BAKE OK 5" "$H/bake.log" || fail bake "$H/bake.log"
# sequences with review tiles (build/velvetpaws/review/anim/tiles, measures.json); contact sheets after the venv exists
NSEQ=$(cd "$W/tools/blender" && python3 -c 'import cat_seqs; print(len(cat_seqs.ORDER))')
rm -rf "$H/anim" "$H/review/anim/tiles"
"${BL[@]}" "$W/tools/blender/cat_anims.py" -- "$H" > "$H/anims.log" 2>&1 || fail anims "$H/anims.log"
grep -q "ANIMS OK $NSEQ\$" "$H/anims.log" || fail anims "$H/anims.log"
[ -x "$BUILD/venv/bin/python" ] || { python3 -m venv --system-site-packages "$BUILD/venv"; "$BUILD/venv/bin/pip" -q install pillow numpy; }
"$BUILD/venv/bin/python" "$W/scripts/velvetpaws/anim_sheet.py" "$H/review/anim" > "$H/sheets.log" 2>&1 || fail sheets "$H/sheets.log"
grep -q "SHEETS OK" "$H/sheets.log" || fail sheets "$H/sheets.log"
# sounds: synthesis (placeholders for every asset without a recording in assets/sounds/), spectrogram sheet + listening file
NSND=$(cd "$W/scripts" && python3 -c 'from velvetpaws import sounds; print(len(sounds.assets()))')
rm -rf "$H/sound"
"$BUILD/venv/bin/python" "$W/scripts/velvetpaws/sound_synth.py" "$H/sound" > "$H/sound.log" 2>&1 || fail sounds "$H/sound.log"
grep -q "SOUNDS OK $NSND\$" "$H/sound.log" || fail sounds "$H/sound.log"
"$BUILD/venv/bin/python" "$W/scripts/velvetpaws/sound_sheet.py" "$H/review/sound" >> "$H/sound.log" 2>&1 || fail "sound sheet" "$H/sound.log"
grep -q "SOUND SHEET OK $NSND\$" "$H/sound.log" || fail "sound sheet" "$H/sound.log"
(cd "$W" && "$BUILD/venv/bin/python" -m unittest tests.test_rig tests.test_textures tests.test_motion tests.test_anim_data tests.test_gen tests.test_brain tests.test_office_level tests.test_office_map tests.test_sounds tests.test_ui)

rm -rf "$KIT/Content/Mod/$MOD"
"$ALTUI_DEV/scripts/edtest.sh" "$W/scripts/import_cat.py" "$W/scripts/import_sounds.py" > "$H/import.log" 2>&1 || fail import "$H/import.log"
grep -q "EDTEST PASS" "$H/import.log" || fail import "$H/import.log"
grep -q "EDTEST PASS sounds $NSND " "$H/import.log" && ! grep -q "EDTEST FAIL" "$H/import.log" || fail import "$H/import.log"
python3 "$W/assets/gen/gen_velvetpaws.py"
"$ALTUI_DEV/scripts/ue.sh" "$UPROJECT" -run=TKA_BPGen.BPGen -manifest="$W/assets/velvetpaws_manifest.txt" \
  -fastexit -unattended -nullrhi -nosplash -stdout > "$H/bpgen_raw.log" 2>&1 || true
grep -q "BPGEN manifest ok .*91_velvetpaws.json" "$H/bpgen_raw.log" || { grep -iE "error|BPGEN.*fail" "$H/bpgen_raw.log" | head; echo "bpgen failed: $H/bpgen_raw.log"; exit 1; }
! grep -E "BPGEN FAILED|BPGEN compiled .*(warnings|errors)=[1-9]" "$H/bpgen_raw.log" || { echo "BPGEN: compile warnings/errors present ($H/bpgen_raw.log)"; exit 1; }
! grep -q "LogBlueprint: Error" "$H/bpgen_raw.log" || { echo "BPGEN: blueprint errors on load"; grep "LogBlueprint: Error" "$H/bpgen_raw.log" | sort -u | head -5; exit 1; }
# the inherited components' defaults of the Character (capsule, movement, mesh): three subobject_defaults entries (-stdout
# doubles every log line: count the distinct components)
[ "$(grep -o 'BPGEN subobject_defaults BP_VP_Cat [A-Za-z]*' "$H/bpgen_raw.log" | sort -u | wc -l)" -eq 3 ] || { echo "BPGEN: subobject_defaults of BP_VP_Cat missing ($H/bpgen_raw.log)"; exit 1; }
# the animation assets as built in the kit (ABP nodes and slot, blend space axis, montage segments, skeletons)
"$ALTUI_DEV/scripts/edtest.sh" "$W/scripts/test_anims_kit.py" > "$H/kit_anims.log" 2>&1 || fail "kit anim test" "$H/kit_anims.log"
grep -q "EDTEST PASS" "$H/kit_anims.log" && ! grep -q "EDTEST FAIL" "$H/kit_anims.log" || fail "kit anim test" "$H/kit_anims.log"
# the pure decision functions, the class and component defaults and the office tables as built in the kit
"$ALTUI_DEV/scripts/edtest.sh" "$W/scripts/test_behaviour_kit.py" "$W/scripts/test_ui_kit.py" > "$H/kit_behaviour.log" 2>&1 || fail "kit behaviour/ui test" "$H/kit_behaviour.log"
grep -q "EDTEST PASS" "$H/kit_behaviour.log" && ! grep -q "EDTEST FAIL" "$H/kit_behaviour.log" || fail "kit behaviour test" "$H/kit_behaviour.log"

rm -rf "$COOKED_WIN/Mod/$MOD"
"$ALTUI_DEV/scripts/wincook.sh" -cookdir=Mod/$MOD | tee "$H/cook.log"
RSP="$H/pak.rsp"; : > "$RSP"
(cd "$COOKED_WIN" && find "Mod/$MOD" -type f | sort) | while read -r f; do
  echo "\"$COOKED_WIN/$f\" \"../../../TheKillingAntidote/Content/$f\"" >> "$RSP"; done
# every asset of the mod (names.pak_assets: mesh, skeleton, sequences, blend space, ABP, montages, BP, tables, materials, textures)
PAK_ASSETS=$(python3 -c 'import sys; sys.path[:0] = [sys.argv[1] + "/scripts", sys.argv[1] + "/tools/blender"]
from velvetpaws import names; import cat_seqs as CS; print(" ".join(names.pak_assets(CS.ORDER, [m["name"] for m in CS.MONTAGES])))' "$W")
for a in $PAK_ASSETS; do
  grep -q "Mod/$MOD/$a.uasset" "$RSP" || { echo "missing in pak: $a"; exit 1; }; done
rm -f "$BUILD/$MOD.pak"
"$UNREALPAK" "$BUILD/$MOD.pak" -create="$RSP" 2>&1 | { grep -E "Added [0-9]+ files|Error|error" || true; } | tail -2 || true
[ -s "$BUILD/$MOD.pak" ] || { echo "UnrealPak failed: $BUILD/$MOD.pak missing or empty"; exit 1; }
# the loader row's struct comes from the Blueprint Loader's own pak (~mods), not from the game: add that pak's files to the list
FL="$H/game_filelist_with_loader.txt"; cp "$GAME_PAK_FILELIST" "$FL"
python3 -c 'import sys; sys.path.insert(0, sys.argv[1]); from pak11_extract import Pak; p = Pak(sys.argv[2])
print("\n".join((p.mount + f).replace("../../../", "") for f in p.files))' "$ALTUI_DEV/scripts" "$GAME/Content/Paks/~mods/TKA_BlueprintLoader.pak" >> "$FL"
# BPI_AltUIMod and the row structs of the cat's AltUI tables live in AltUI.pak: add its files to the list too
python3 -c 'import sys; sys.path.insert(0, sys.argv[1]); from pak11_extract import Pak; p = Pak(sys.argv[2])
print("\n".join((p.mount + f).replace("../../../", "").replace("//", "/") for f in p.files))' "$ALTUI_DEV/scripts" "$GAME/Mods/AltUI.pak" >> "$FL"
GAME_PAK_FILELIST="$FL" python3 "$TKAINFO_DEV/scripts/verify_modpak.py" "$BUILD/$MOD.pak" > "$H/verify.log" 2>&1 || true
grep -q "VERIFY OK" "$H/verify.log" || fail verify "$H/verify.log"
python3 "$W/scripts/verify_cooked.py" "$BUILD/$MOD.pak"
if [[ " $* " != *" --no-deploy "* ]]; then rm -f "$GAME/Mods/$MOD.pak"; cp -v "$BUILD/$MOD.pak" "$GAME/Mods/"; fi
echo "VELVETPAWS OK"
