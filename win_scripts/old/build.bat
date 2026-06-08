## Windows native build compile script.
# Copyright (c) 2022 Alex313031. 

cd C:\src\chromium\src\ &&

echo "Setting NINJA_SUMMARIZE_BUILD=1" &&

set NINJA_SUMMARIZE_BUILD=1 &&

echo "Building Mcloud Browser..." &&

autoninja -C out\mcloud chrome chromedriver content_shell setup mini_installer -j %1
