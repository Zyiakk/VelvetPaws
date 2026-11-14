# Copy to config.sh and adjust. scripts/build.sh sources config.sh.
_W="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export W="$_W" BUILD="$_W/build" VELVETPAWS_DEV="$_W"; unset _W
export ALTUI_DEV="$HOME/src/AltUI"                                   # an AltUI checkout: bpgen, scripts (ue.sh, edtest.sh, wincook.sh, pak library), tools/bpdump
export TKAINFO_DEV="$HOME/src/TKAInfo"                               # provides scripts/verify_modpak.py
export KIT="$HOME/Unreal Projects/TheKillingAntidote_Ani_And_Hair"  # the game's sample mod project (UE 4.27) with Plugins/TKA_BPGen -> $ALTUI_DEV/bpgen
export UPROJECT="$KIT/TheKillingAntidote.uproject"
export ENGINE="$HOME/UnrealEngine-4.27"                              # UE 4.27 source build
export UE_CMD="$ENGINE/Engine/Binaries/Linux/UE4Editor-Cmd"
export UNREALPAK="$ENGINE/Engine/Binaries/Linux/UnrealPak"
export GAME="$HOME/.steam/steam/steamapps/common/TheKillingAntidote/TheKillingAntidote"   # deploy target
export COOKED="$KIT/Saved/Cooked/LinuxNoEditor/TheKillingAntidote/Content"
export GAME_PAK_FILELIST="$TKAINFO_DEV/knowledge/game_pak_filelist.txt"   # file list of the game paks (import check)
# Windows cook under Wine (AltUI's scripts/wincook.sh)
export UE_WIN="$HOME/UE_4.27_Win"
export WINE_UE_PREFIX="$HOME/wine_ue427"
export WINCOOK_PROJECT="$ALTUI_DEV/build/wincook/TheKillingAntidote"
export COOKED_WIN="$WINCOOK_PROJECT/Saved/Cooked/WindowsNoEditor/TheKillingAntidote/Content"
UMODEL="${UMODEL:-$BUILD/tools/UEViewer/umodel}"                    # UE Viewer for the office meshes (scripts/office_extract.sh)
