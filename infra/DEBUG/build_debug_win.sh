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
	printf "${bold}${YEL}Script to build Mcloud Browser DEBUG for Windows on Linux.${c0}\n" &&
	printf "${underline}Usage: ${c0}build_debug_win.sh # (where # is number of jobs)\n" &&
	printf "\n"
}
case $1 in
	--help) displayHelp; exit 0;;
esac

printf "\n" &&
printf "${YEL}Building Mcloud Browser DEBUG for Windows...\n" &&
printf "${CYA}\n" &&

# Build Mcloud Browser and Mcloud Browser UI Debug Shell
export NINJA_SUMMARIZE_BUILD=1 &&

autoninja -C ~/chromium/src/out/mcloud chrome chromedriver mcloud_shell setup mini_installer mcloud_ui_debug_shell clear_key_cdm -j$@ &&

mkdir -v -p ~/chromium/src/out/mcloud/Mcloud Browser_UI_Debug_Shell &&
mkdir -v -p ~/chromium/src/out/mcloud/Mcloud Browser_UI_Debug_Shell/icons &&

cp -r -f -v ./icons/icon_16.png ~/chromium/src/out/mcloud/Mcloud Browser_UI_Debug_Shell/icons &&
cp -r -f -v ./icons/icon_24.png ~/chromium/src/out/mcloud/Mcloud Browser_UI_Debug_Shell/icons &&
cp -r -f -v ./icons/icon_32.png ~/chromium/src/out/mcloud/Mcloud Browser_UI_Debug_Shell/icons &&
cp -r -f -v ./icons/icon_48.png ~/chromium/src/out/mcloud/Mcloud Browser_UI_Debug_Shell/icons &&
cp -r -f -v ./icons/icon_64.png ~/chromium/src/out/mcloud/Mcloud Browser_UI_Debug_Shell/icons &&
cp -r -f -v ./icons/icon_128.png ~/chromium/src/out/mcloud/Mcloud Browser_UI_Debug_Shell/icons &&
cp -r -f -v ./icons/icon_256.png ~/chromium/src/out/mcloud/Mcloud Browser_UI_Debug_Shell/icons &&
cp -r -f -v ./icons/mcloud_debug_shell.ico ~/chromium/src/out/mcloud/Mcloud Browser_UI_Debug_Shell &&
cp -r -f -v DEBUG_SHELL_README.md ~/chromium/src/out/mcloud/Mcloud Browser_UI_Debug_Shell/README.md &&
cp -r -f -v ~/chromium/src/out/mcloud/locales ~/chromium/src/out/mcloud/Mcloud Browser_UI_Debug_Shell/ &&
cp -r -f -v ~/chromium/src/out/mcloud/test_fonts ~/chromium/src/out/mcloud/Mcloud Browser_UI_Debug_Shell/ &&
cp -r -f -v ~/chromium/src/out/mcloud/resources ~/chromium/src/out/mcloud/Mcloud Browser_UI_Debug_Shell/ &&
cp -r -f -v ~/chromium/src/out/mcloud/ui ~/chromium/src/out/mcloud/Mcloud Browser_UI_Debug_Shell/ &&
cp -r -f -v ~/chromium/src/out/mcloud/blink_test_plugin.dll ~/chromium/src/out/mcloud/Mcloud Browser_UI_Debug_Shell/ &&
cp -r -f -v ~/chromium/src/out/mcloud/icudtl.dat ~/chromium/src/out/mcloud/Mcloud Browser_UI_Debug_Shell/ &&
cp -r -f -v ~/chromium/src/out/mcloud/content_resources.pak ~/chromium/src/out/mcloud/Mcloud Browser_UI_Debug_Shell/ &&
cp -r -f -v ~/chromium/src/out/mcloud/libEGL.dll ~/chromium/src/out/mcloud/Mcloud Browser_UI_Debug_Shell/ &&
cp -r -f -v ~/chromium/src/out/mcloud/libGLESv2.dll ~/chromium/src/out/mcloud/Mcloud Browser_UI_Debug_Shell/ &&
cp -r -f -v ~/chromium/src/out/mcloud/vk_swiftshader.dll ~/chromium/src/out/mcloud/Mcloud Browser_UI_Debug_Shell/ &&
cp -r -f -v ~/chromium/src/out/mcloud/vulkan-1.dll ~/chromium/src/out/mcloud/Mcloud Browser_UI_Debug_Shell/ &&
cp -r -f -v ~/chromium/src/out/mcloud/vk_swiftshader_icd.json ~/chromium/src/out/mcloud/Mcloud Browser_UI_Debug_Shell/ &&
cp -r -f -v ~/chromium/src/out/mcloud/v8_context_snapshot.bin ~/chromium/src/out/mcloud/Mcloud Browser_UI_Debug_Shell/ &&
cp -r -f -v ~/chromium/src/out/mcloud/v8_context_snapshot_generator ~/chromium/src/out/mcloud/Mcloud Browser_UI_Debug_Shell/ &&
cp -r -f -v ~/chromium/src/out/mcloud/ui_resources_100_percent.pak ~/chromium/src/out/mcloud/Mcloud Browser_UI_Debug_Shell/ &&
cp -r -f -v ~/chromium/src/out/mcloud/ui_test.pak ~/chromium/src/out/mcloud/Mcloud Browser_UI_Debug_Shell/ &&
cp -r -f -v ~/chromium/src/out/mcloud/ui_test_200_percent.pak ~/chromium/src/out/mcloud/Mcloud Browser_UI_Debug_Shell/ &&
cp -r -f -v ~/chromium/src/out/mcloud/views_examples_resources.pak ~/chromium/src/out/mcloud/Mcloud Browser_UI_Debug_Shell/ &&
cp -r -f -v ~/chromium/src/out/mcloud/mcloud_ui_debug_shell.exe ~/chromium/src/out/mcloud/Mcloud Browser_UI_Debug_Shell/ &&

printf "\n" &&
printf "${GRE}Debug Windows Build Completed.\n" &&
tput sgr0
