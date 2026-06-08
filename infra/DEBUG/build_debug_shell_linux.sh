#!/bin/bash

# Copyright (c) 2026 Alex313031.

YEL='\033[1;33m' # Yellow
CYA='\033[1;96m' # Cyan
RED='\033[1;31m' # Red
GRE='\033[1;32m' # Green
c0=$'\033[0m' # Reset Text
bold=$'\033[1m' # Bold Text
underline=$'\033[4m' # Underline Text

# Error handling
yell() { echo "$0: $*" >&2; }
die() { yell "$*"; exit 111; }
try() { "$@" || die "${RED}Failed $*"; }

# --help
displayHelp () {
	printf "\n" &&
	printf "${bold}${YEL}Script to build Mcloud Browser UI Debug Shell (views_examples_with_content).${c0}\n" &&
	printf "${underline}Usage: ${c0}build_debug_shell.sh # (where # is number of jobs)\n" &&
	printf "\n"
}
case $1 in
	--help) displayHelp; exit 0;;
esac

printf "\n" &&
printf "${YEL}Building Mcloud Browser UI Debug Shell for Linux...\n" &&
printf "${CYA}\n" &&

# chromium/src dir env variable
if [ -z "${CR_DIR}" ]; then 
    CR_SRC_DIR="$HOME/chromium/src"
    export CR_SRC_DIR
else 
    CR_SRC_DIR="${CR_DIR}"
    export CR_SRC_DIR
fi

# Build Mcloud Browser UI Debug Shell
export NINJA_SUMMARIZE_BUILD=1 &&

cd ${CR_SRC_DIR} &&
autoninja -C out/mcloud mcloud_ui_debug_shell minidump_stackwalk dump_syms -j$@ &&
cd ~/mcloud/infra/DEBUG &&

mkdir -v -p ${CR_SRC_DIR}/out/mcloud/Mcloud Browser_UI_Debug_Shell &&
mkdir -v -p ${CR_SRC_DIR}/out/mcloud/Mcloud Browser_UI_Debug_Shell/lib &&
mkdir -v -p ${CR_SRC_DIR}/out/mcloud/Mcloud Browser_UI_Debug_Shell/icons &&

cp -r -f -v ./icons/icon_16.png ${CR_SRC_DIR}/out/mcloud/Mcloud Browser_UI_Debug_Shell/icons &&
cp -r -f -v ./icons/icon_24.png ${CR_SRC_DIR}/out/mcloud/Mcloud Browser_UI_Debug_Shell/icons &&
cp -r -f -v ./icons/icon_32.png ${CR_SRC_DIR}/out/mcloud/Mcloud Browser_UI_Debug_Shell/icons &&
cp -r -f -v ./icons/icon_48.png ${CR_SRC_DIR}/out/mcloud/Mcloud Browser_UI_Debug_Shell/icons &&
cp -r -f -v ./icons/icon_64.png ${CR_SRC_DIR}/out/mcloud/Mcloud Browser_UI_Debug_Shell/icons &&
cp -r -f -v ./icons/icon_128.png ${CR_SRC_DIR}/out/mcloud/Mcloud Browser_UI_Debug_Shell/icons &&
cp -r -f -v ./icons/icon_256.png ${CR_SRC_DIR}/out/mcloud/Mcloud Browser_UI_Debug_Shell/icons &&
cp -r -f -v ./icons/icon_256.png ${CR_SRC_DIR}/out/mcloud/Mcloud Browser_UI_Debug_Shell/ &&
# cp -r -f -v ./icons/mcloud_debug_shell.ico ${CR_SRC_DIR}/out/mcloud/Mcloud Browser_UI_Debug_Shell &&
cp -r -f -v DEBUG_SHELL_README.md ${CR_SRC_DIR}/out/mcloud/Mcloud Browser_UI_Debug_Shell/README.md &&
cp -r -f -v Mcloud Browser_Debug_Shell.sh ${CR_SRC_DIR}/out/mcloud/Mcloud Browser_UI_Debug_Shell &&
cp -r -f -v ${CR_SRC_DIR}/out/mcloud/locales ${CR_SRC_DIR}/out/mcloud/Mcloud Browser_UI_Debug_Shell/ &&
cp -r -f -v ${CR_SRC_DIR}/out/mcloud/test_fonts ${CR_SRC_DIR}/out/mcloud/Mcloud Browser_UI_Debug_Shell/ &&
cp -r -f -v ${CR_SRC_DIR}/out/mcloud/resources ${CR_SRC_DIR}/out/mcloud/Mcloud Browser_UI_Debug_Shell/ &&
cp -r -f -v ${CR_SRC_DIR}/out/mcloud/ui ${CR_SRC_DIR}/out/mcloud/Mcloud Browser_UI_Debug_Shell/ &&
# cp -r -f -v ${CR_SRC_DIR}/out/mcloud/libffmpeg.so ${CR_SRC_DIR}/out/mcloud/Mcloud Browser_UI_Debug_Shell/ &&
cp -r -f -v ${CR_SRC_DIR}/out/mcloud/libffmpeg.so ${CR_SRC_DIR}/out/mcloud/Mcloud Browser_UI_Debug_Shell/lib &&
# cp -r -f -v ${CR_SRC_DIR}/out/mcloud/libblink_test_plugin.so ${CR_SRC_DIR}/out/mcloud/Mcloud Browser_UI_Debug_Shell/ &&
# cp -r -f -v ${CR_SRC_DIR}/out/mcloud/libmojo_core.so ${CR_SRC_DIR}/out/mcloud/Mcloud Browser_UI_Debug_Shell/ &&
cp -r -f -v ${CR_SRC_DIR}/out/mcloud/icudtl.dat ${CR_SRC_DIR}/out/mcloud/Mcloud Browser_UI_Debug_Shell/ &&
cp -r -f -v ${CR_SRC_DIR}/out/mcloud/content_resources.pak ${CR_SRC_DIR}/out/mcloud/Mcloud Browser_UI_Debug_Shell/ &&
cp -r -f -v ${CR_SRC_DIR}/out/mcloud/libEGL.so ${CR_SRC_DIR}/out/mcloud/Mcloud Browser_UI_Debug_Shell/ &&
cp -r -f -v ${CR_SRC_DIR}/out/mcloud/libGLESv2.so ${CR_SRC_DIR}/out/mcloud/Mcloud Browser_UI_Debug_Shell/ &&
cp -r -f -v ${CR_SRC_DIR}/out/mcloud/libvk_swiftshader.so ${CR_SRC_DIR}/out/mcloud/Mcloud Browser_UI_Debug_Shell/ &&
cp -r -f -v ${CR_SRC_DIR}/out/mcloud/libvulkan.so.1 ${CR_SRC_DIR}/out/mcloud/Mcloud Browser_UI_Debug_Shell/ &&
cp -r -f -v ${CR_SRC_DIR}/out/mcloud/vk_swiftshader_icd.json ${CR_SRC_DIR}/out/mcloud/Mcloud Browser_UI_Debug_Shell/ &&
cp -r -f -v ${CR_SRC_DIR}/out/mcloud/v8_context_snapshot.bin ${CR_SRC_DIR}/out/mcloud/Mcloud Browser_UI_Debug_Shell/ &&
cp -r -f -v ${CR_SRC_DIR}/out/mcloud/ui_resources_100_percent.pak ${CR_SRC_DIR}/out/mcloud/Mcloud Browser_UI_Debug_Shell/ &&
cp -r -f -v ${CR_SRC_DIR}/out/mcloud/ui_test.pak ${CR_SRC_DIR}/out/mcloud/Mcloud Browser_UI_Debug_Shell/ &&
cp -r -f -v ${CR_SRC_DIR}/out/mcloud/ui_test_200_percent.pak ${CR_SRC_DIR}/out/mcloud/Mcloud Browser_UI_Debug_Shell/ &&
cp -r -f -v ${CR_SRC_DIR}/out/mcloud/views_examples_resources.pak ${CR_SRC_DIR}/out/mcloud/Mcloud Browser_UI_Debug_Shell/ &&
cp -r -f -v ${CR_SRC_DIR}/out/mcloud/mcloud_ui_debug_shell ${CR_SRC_DIR}/out/mcloud/Mcloud Browser_UI_Debug_Shell/ &&
cp -r -f -v ${CR_SRC_DIR}/out/mcloud/minidump_stackwalk ${CR_SRC_DIR}/out/mcloud/Mcloud Browser_UI_Debug_Shell/ &&
cp -r -f -v ${CR_SRC_DIR}/out/mcloud/dump_syms ${CR_SRC_DIR}/out/mcloud/Mcloud Browser_UI_Debug_Shell/ &&
cp -r -f -v ${CR_SRC_DIR}/out/mcloud/ClearKeyCdm ${CR_SRC_DIR}/out/mcloud/Mcloud Browser_UI_Debug_Shell/ &&
cp -r -f -v ${CR_SRC_DIR}/out/mcloud/ClearKeyCdm/_platform_specific/linux_x64/libclearkeycdm.so ${CR_SRC_DIR}/out/mcloud/Mcloud Browser_UI_Debug_Shell/lib &&

cd ${CR_SRC_DIR}/out/mcloud/Mcloud Browser_UI_Debug_Shell &&
zip -r ../Mcloud Browser_UI_Debug_Shell.zip * &&

printf "\n" &&
printf "${GRE}Mcloud Browser UI Debug Shell Build Completed!\n" &&
tput sgr0
