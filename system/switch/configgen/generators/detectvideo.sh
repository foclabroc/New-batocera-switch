#!/bin/bash

get_connected_display() {
    local display_type="$1"
    local drm_connector=""
    local card_path=""

    for card_folder_path in /sys/class/drm/card*; do
        card_id=$(basename "$card_folder_path")
        if [ -d "$card_folder_path" ]; then
            card_folder_name=$(basename "$card_folder_path")
            if [[ "$card_folder_name" == card* ]]; then
                for sub_folder in "$card_folder_path"/*; do
                    if [[ "$(basename "$sub_folder")" == "card"* ]]; then
                        status_file="${sub_folder}/status"
                        if [ -f "$status_file" ] && [ "$(cat "$status_file")" == "connected" ] && [[ "$status_file" == *"$display_type"* ]]; then
                            drm_connector=$(echo "$status_file" | sed -n 's/.*\/card[0-9]\-\(.*\)\/status/\1/p')
                            card_number=$(echo "$card_id" | sed -n 's/card\([0-9]\+\).*/\1/p')
                            card_path="/sys/class/drm/card$card_number"
                            break 2  # We found a connected display, exit both loops
                        fi
                    fi
                done
            fi
        fi
    done
    echo "$drm_connector $card_path"
}


# determine the output display to use for MPV
# fixes splash video output where the user wants it
if preferred_display=$(batocera-settings-get global.videooutput); then
    display_type=$(echo "$preferred_display" | cut -d'-' -f1)
    if [[ "$display_type" == "DisplayPort" ]]; then
        # workaround some cards using DisplayPort as the xorg output name
        display_type="DP"
    fi
    read -r drm_connector card_path <<< "$(get_connected_display "$display_type")"
else
    # we choose the first connected display
    mpv_connector=$(mpv --drm-connector=help | grep "(connected)" | sed 's/ (connected)//' | sed 's/^[[:space:]]*//' | head -n1)
    if [ -n "$mpv_connector" ]; then
        display_type=$(echo "$mpv_connector" | cut -d'-' -f1)
        read -r drm_connector card_path <<< "$(get_connected_display "$display_type")"
    fi
fi
echo $card_path
