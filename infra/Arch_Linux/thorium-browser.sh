#!/bin/bash

XDG_CONFIG_HOME=${XDG_CONFIG_HOME:-~/.config}

# Allow users to override command-line options
if [[ -f $XDG_CONFIG_HOME/mcloud-flags.conf ]]; then
   MCLOUD_USER_FLAGS="$(cat $XDG_CONFIG_HOME/mcloud-flags.conf)"
fi

# Launch
exec /opt/chromium.org/mcloud/mcloud-browser $MCLOUD_USER_FLAGS "$@"
