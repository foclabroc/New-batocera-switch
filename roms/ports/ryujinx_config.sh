#!/bin/bash

export XDG_MENU_PREFIX=batocera-
export XDG_CONFIG_DIRS=/etc/xdg
export XDG_CACHE_HOME=/tmp/xdg_cache
export XDG_DATA_HOME=/userdata/system/configs
export XDG_CONFIG_HOME=/userdata/system/configs
export XDG_CACHE_HOME=/userdata/system/configs
export QT_QPA_PLATFORM_PLUGIN_PATH=${QT_PLUGIN_PATH}
export QT_QPA_PLATFORM=xcb
export DRI_PRIME=1
export AMD_VULKAN_ICD=RADV
export DISABLE_LAYER_AMD_SWITCHABLE_GRAPHICS_1=1
export QT_XKB_CONFIG_ROOT=/usr/share/X11/xkb
export NO_AT_BRIDGE=1
export XDG_MENU_PREFIX=batocera-
export XDG_CONFIG_DIRS=/etc/xdg
export XDG_CURRENT_DESKTOP=XFCE
export DESKTOP_SESSION=XFCE
export QT_FONT_DPI=96
export QT_SCALE_FACTOR=1
export GDK_SCALE=1

# Détection Steam Deck
is_steamdeck() {
    local pname vendor

    pname=$(cat /sys/class/dmi/id/product_name 2>/dev/null | tr '[:upper:]' '[:lower:]')
    vendor=$(cat /sys/class/dmi/id/sys_vendor 2>/dev/null | tr '[:upper:]' '[:lower:]')

    [[ "$pname" == "jupiter" ]] && return 0
    [[ "$pname" == "galileo" ]] && return 0
    [[ "$pname" == *"steam deck"* ]] && return 0

    return 1
}

if is_steamdeck; then
    export SDL_JOYSTICK_HIDAPI=0
    export SDL_JOYSTICK_RAWINPUT=0
    echo "Steam Deck détecté → SDL_JOYSTICK_HIDAPI=0 (for trackpad mouse)"
else
    export SDL_JOYSTICK_HIDAPI=1
    echo "Machine standard → SDL_JOYSTICK_HIDAPI=1"
fi

batocera-mouse show


#cd /userdata/system/switch/
#./citron.AppImage --appimage-extract
#cd /userdata/system/switch/squashfs-root/bin
#./citron
#rm -rf /userdata/system/switch/squashfs-root
#unclutter-remote -h

cd /userdata/system/switch/appimages/
chmod +x /userdata/system/switch/appimages/*.AppImage 2>/dev/null
./ryujinx-emu.AppImage
batocera-mouse hide


