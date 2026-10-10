#!/bin/bash

# ===============================
# LANGUAGE SELECTION
# ===============================
LANG_UI="fr"

select_language() {
    dialog --backtitle "Foclabroc Switch AppImages Updater" \
           --title "Language / Langue" \
		   --ok-label "OK" \
		   --cancel-label "Cancel" \
           --menu "Please select your language / Veuillez choisir la langue :" 12 65 2 \
           fr "Français" \
           en "English" 2> /tmp/lang.choice

    if [[ $? -ne 0 ]]; then
        clear
        exit 0
    fi

    LANG_UI=$(cat /tmp/lang.choice)
    rm -f /tmp/lang.choice
}

tr() {
    case "$LANG_UI:$1" in
        fr:SYS_FILES) echo "Fichiers système" ;;
        en:SYS_FILES) echo "System files" ;;

        fr:SYS_UPDATE) echo "Mise à jour des fichiers système…" ;;
        en:SYS_UPDATE) echo "Updating system files…" ;;

        fr:SYS_DONE) echo "Fichiers système mis à jour" ;;
        en:SYS_DONE) echo "System files updated" ;;

        fr:SYS_FAIL) echo "Échec mise à jour fichiers système" ;;
        en:SYS_FAIL) echo "System files update failed" ;;

        fr:BACKTITLE) echo "Foclabroc Switch AppImages Updater" ;;
        en:BACKTITLE) echo "Foclabroc Switch AppImages Updater" ;;

        fr:ERROR) echo "ERREUR" ;;
        en:ERROR) echo "ERROR" ;;

        fr:ERROR_EMU) echo "NON MIS A JOUR" ;;
        en:ERROR_EMU) echo "NOT UPDATED" ;;

        fr:CONFIRM_TITLE) echo "Switch AppImages Updater" ;;
        en:CONFIRM_TITLE) echo "Switch AppImages Updater" ;;

        fr:CANCEL_LABEL) echo "Annuler" ;;
        en:CANCEL_LABEL) echo "Cancel" ;;

        fr:OK_LABEL) echo "Accepter" ;;
        en:OK_LABEL) echo "OK" ;;

        fr:YES_LABEL) echo "Oui" ;;
        en:YES_LABEL) echo "Yes" ;;

        fr:NO_LABEL) echo "Non" ;;
        en:NO_LABEL) echo "No" ;;

        fr:PROGRESS) echo "Téléchargement en cours..." ;;
        en:PROGRESS) echo "Download in progress..." ;;

        fr:CONFIRM_TEXT) echo "
Voulez-vous mettre à jour les AppImages Switch ?

• Citron
• Eden
• Eden PGO
• Eden Nightly
• Ryujinx" ;;
        en:CONFIRM_TEXT) echo "
Do you want to update Switch AppImages?

• Citron
• Eden
• Eden PGO
• Eden Nightly
• Ryujinx" ;;

        fr:GAUGE_TITLE) echo "Mise à jour des AppImages Switch" ;;
        en:GAUGE_TITLE) echo "Updating Switch AppImages" ;;

        fr:GAUGE_TEXT) echo "Téléchargement des fichiers…" ;;
        en:GAUGE_TEXT) echo "Downloading files…" ;;

        fr:FINAL_TITLE) echo "Mise à jour terminée" ;;
        en:FINAL_TITLE) echo "Update completed" ;;

        fr:DOWNLOAD_DONE) echo "Téléchargement terminé" ;;
        en:DOWNLOAD_DONE) echo "Download completed" ;;

        fr:UPDATE_RESULT) echo "Résultat mise à jour :" ;;
        en:UPDATE_RESULT) echo "Update Result :" ;;

        *) echo "$1" ;;
    esac
}

select_language
BACKTITLE="$(tr BACKTITLE)"

# ===============================
# PATHS
# ===============================
SWITCH_APPIMAGES="/userdata/system/switch/appimages-updater-temp"
SWITCH_APPIMAGES_FINAL="/userdata/system/switch/appimages"
TEMP_DIR="/userdata/system/switch/appimages-updater-temp"
LOG_DIR="/userdata/system/switch/appimages-updater-temp"

LOG_FILE="$LOG_DIR/update.log"
VERSIONS_FILE="$TEMP_DIR/versions.log"
STATUS_FILE="$TEMP_DIR/status.log"

rm -rf "$SWITCH_APPIMAGES"
mkdir -p "$SWITCH_APPIMAGES" "$TEMP_DIR" "$LOG_DIR"
> "$LOG_FILE"
> "$VERSIONS_FILE"
> "$STATUS_FILE"

# ===============================
# LOG
# ===============================
log() {
    echo "[$(date '+%H:%M:%S')] $1" >> "$LOG_FILE"
}

# ===============================
# STEP DOWNLOAD (GAUGE PAR ÉTAPES) — wget
# ===============================
wget_step() {
    local url="$1"
    local dest="$2"
    local label="$3"

    log "Downloading $label"

    local spinner=(⠋ ⠙ ⠹ ⠸ ⠼ ⠴ ⠦ ⠧ ⠇ ⠏)
    local i=0

    wget -nv --tries=3 --timeout=10 --connect-timeout=5 \
         "$url" -O "$dest" 2>>"$LOG_FILE" &
    pid=$!

    while kill -0 $pid 2>/dev/null; do
        echo "XXX"
        echo "$GLOBAL_PERCENT"
        echo "$(tr GAUGE_TEXT)"
        echo "======================="
        echo " "
        echo "-->[${label}-emu]"
        echo "--> ${spinner[$i]} $(tr PROGRESS)"
        echo "XXX"

        i=$(( (i + 1) % ${#spinner[@]} ))
        sleep 0.15
    done

    wait $pid || return 1
    chmod +x "$dest"
    return 0
}

# ===============================
# STEP DOWNLOAD (GAUGE PAR ÉTAPES) — curl
# Écrit toujours la réponse dans un fichier (jamais sur stdout),
# pour ne pas polluer la sortie avec les lignes du gauge et pour
# ne jamais figer l'affichage pendant un check HEAD.
# Usage: curl_step "<label>" "<fichier_de_sortie|/dev/null>" <options curl...>
# ===============================
curl_step() {
    local label="$1"
    local outfile="$2"
    shift 2

    local spinner=(⠋ ⠙ ⠹ ⠸ ⠼ ⠴ ⠦ ⠧ ⠇ ⠏)
    local i=0

    curl "$@" -o "$outfile" 2>>"$LOG_FILE" &
    pid=$!

    while kill -0 $pid 2>/dev/null; do
        echo "XXX"
        echo "$GLOBAL_PERCENT"
        echo "$(tr GAUGE_TEXT)"
        echo "======================="
        echo " "
        echo "-->[${label}-emu]"
        echo "--> ${spinner[$i]} $(tr PROGRESS)"
        echo "XXX"

        i=$(( (i + 1) % ${#spinner[@]} ))
        sleep 0.15
    done

    wait $pid
    return $?
}

deploy_if_valid() {
    local src="$1"
    local name
    local size_mb

    name=$(basename "$src")

    if [[ ! -f "$src" ]]; then
        log "ERROR deploy: $name not found"
        return 1
    fi

    sync
    size_mb=$(( $(stat -c%s "$src") / 1048576 ))

    if (( size_mb < 20 )); then
        log "ERROR deploy: $name too small (${size_mb}MB) – skipped"
        return 1
    fi

    mkdir -p "$SWITCH_APPIMAGES_FINAL"
    mv -f "$src" "$SWITCH_APPIMAGES_FINAL/$name"

    log "Deployed $name to final folder (${size_mb}MB)"
    log "!!!!Update $name AppImage Finished!!!!"
    return 0
}

# ===============================
# UPDATE SYSTEM FILES
# ===============================
install_new_pack() {

    log "!!!!Starting system files update pack!!!!"
    log "  "

    PACK_URL="https://github.com/foclabroc/New-batocera-switch/archive/refs/heads/main.zip"
    PACK_ZIP="/userdata/tmpf/pack.zip"
    EXTRACT_DIR="/userdata/tmpf/new_switch_pack"

    mkdir -p /userdata/tmpf
    rm -rf "$PACK_ZIP"

    echo "XXX"
    echo "$GLOBAL_PERCENT"
    echo "$(tr GAUGE_TEXT)"
    echo "======================="
    echo " "
    echo "-->$(tr SYS_UPDATE)"
    echo "XXX"

	log "Download system .zip at : $PACK_URL"

	wget -q --tries=3 --timeout=20 --retry-connrefused -O "$PACK_ZIP" "$PACK_URL"
	WGET_STATUS=$?

	FILE_SIZE=$(stat -c%s "$PACK_ZIP" 2>/dev/null)

	if [ $WGET_STATUS -ne 0 ] || [ -z "$FILE_SIZE" ] || [ "$FILE_SIZE" -lt 1048576 ]; then
		log "ERROR system pack download failed"
		log "WGET_STATUS=$WGET_STATUS SIZE=$FILE_SIZE"
		echo "STATUS_SYS=ERREUR" >> "$STATUS_FILE"
		rm -f "$PACK_ZIP"
		return 1
	fi

    if [[ ! -s "$PACK_ZIP" ]]; then
        log "ERROR system pack zip empty"
        echo "STATUS_SYS=ERREUR" >> "$STATUS_FILE"
        return
    fi

    log "Download system .zip done."
    log "  "
    log "Extracting system .zip."
    rm -rf "$EXTRACT_DIR"
    mkdir -p "$EXTRACT_DIR"
    unzip -q -o "$PACK_ZIP" -d "$EXTRACT_DIR" >>"$LOG_FILE" 2>&1
    log "System pack extraction done."

    ROOT_DIR=$(find "$EXTRACT_DIR" -mindepth 1 -maxdepth 1 -type d | head -n1)

    [[ -d "$ROOT_DIR" ]] || {
        log "ERROR system pack extraction failed"
        echo "STATUS_SYS=ERREUR" >> "$STATUS_FILE"
        return
    }

    log "  "
    log "Copy extracted files to finale destination"
    shopt -s dotglob nullglob
    cp -rv "$ROOT_DIR"/* /userdata/ >>"$LOG_FILE" 2>&1
    shopt -u dotglob nullglob

    log "System files copied"

    CUSTOM="/userdata/system/custom.sh"
    if [[ -f "$CUSTOM" ]]; then
        sed -i '\|/userdata/system/switch/extra/batocera-switch-startup|d' "$CUSTOM"
    fi

    BATOCERA_CONF="/userdata/system/batocera.conf"
	if [[ -f "$BATOCERA_CONF" ]]; then
		# Récupère la langue système Batocera
		batocera_language=$(grep '^system.language=' "$BATOCERA_CONF" | cut -d '=' -f2)

		# Ajoute la config UNIQUEMENT si absente
		grep -q '^switch\.bezel=none' "$BATOCERA_CONF" || \
		echo 'switch.bezel=none' >> "$BATOCERA_CONF"
		grep -q 'switch\["citron_config.xci_config"\]\.core=citron-emu' "$BATOCERA_CONF" || \
		echo 'switch["citron_config.xci_config"].core=citron-emu' >> "$BATOCERA_CONF"
		grep -q 'switch\["citron_config.xci_config"\]\.emulator=citron-emu' "$BATOCERA_CONF" || \
		echo 'switch["citron_config.xci_config"].emulator=citron-emu' >> "$BATOCERA_CONF"

		grep -q 'switch\["eden_qlaunch.xci_config"\]\.core=eden-emu' "$BATOCERA_CONF" || \
		echo 'switch["eden_qlaunch.xci_config"].core=eden-emu' >> "$BATOCERA_CONF"
		grep -q 'switch\["eden_qlaunch.xci_config"\]\.emulator=eden-emu' "$BATOCERA_CONF" || \
		echo 'switch["eden_qlaunch.xci_config"].emulator=eden-emu' >> "$BATOCERA_CONF"

		grep -q 'switch\["eden_config.xci_config"\]\.core=eden-emu' "$BATOCERA_CONF" || \
		echo 'switch["eden_config.xci_config"].core=eden-emu' >> "$BATOCERA_CONF"
		grep -q 'switch\["eden_config.xci_config"\]\.emulator=eden-emu' "$BATOCERA_CONF" || \
		echo 'switch["eden_config.xci_config"].emulator=eden-emu' >> "$BATOCERA_CONF"

		grep -q 'switch\["ryujinx_config.xci_config"\]\.core=ryujinx-emu' "$BATOCERA_CONF" || \
		echo 'switch["ryujinx_config.xci_config"].core=ryujinx-emu' >> "$BATOCERA_CONF"
		grep -q 'switch\["ryujinx_config.xci_config"\]\.emulator=ryujinx-emu' "$BATOCERA_CONF" || \
		echo 'switch["ryujinx_config.xci_config"].emulator=ryujinx-emu' >> "$BATOCERA_CONF"

		# Préconfiguration langue FR si Batocera est en français
		if [ "$batocera_language" = "fr_FR" ]; then
			grep -q "^switch.region=" "$BATOCERA_CONF" || echo "switch.region=2" >> "$BATOCERA_CONF"
			grep -q "^switch.language=" "$BATOCERA_CONF" || echo "switch.language=2" >> "$BATOCERA_CONF"
			grep -q "^switch.system_language=" "$BATOCERA_CONF" || echo "switch.system_language=French" >> "$BATOCERA_CONF"
			grep -q "^switch.system_region=" "$BATOCERA_CONF" || echo "switch.system_region=Europe" >> "$BATOCERA_CONF"
			grep -q "^switch.yuzu_intlanguage=" "$BATOCERA_CONF" || echo "switch.yuzu_intlanguage=fr" >> "$BATOCERA_CONF"
		fi
	fi

    # --- XMLSTARLET SETUP ---
    XMLSTARLET_DIR="/userdata/system/switch/extra"
    XMLSTARLET_BIN="$XMLSTARLET_DIR/xmlstarlet"
    XMLSTARLET_SYMLINK="/usr/bin/xmlstarlet"

    if [ -f "$XMLSTARLET_BIN" ]; then
        chmod +x "$XMLSTARLET_BIN"
        ln -sf "$XMLSTARLET_BIN" "$XMLSTARLET_SYMLINK"
        log "xmlstarlet ready"
    fi

    gamelist_file="/userdata/roms/ports/gamelist.xml"
    gamelist_file2="/userdata/roms/switch/gamelist.xml"

    [[ -f "$gamelist_file" ]] || echo '<?xml version="1.0"?><gameList></gameList>' > "$gamelist_file"
    [[ -f "$gamelist_file2" ]] || echo '<?xml version="1.0"?><gameList></gameList>' > "$gamelist_file2"

    remove_game_by_path() {
        xmlstarlet ed -L -d "/gameList/game[path='$2']" "$1" 2>/dev/null
    }

    log "Updating gamelists"

    # Supprimer anciennes entrées
    remove_game_by_path "$gamelist_file" "./updateryujinx.sh"
    remove_game_by_path "$gamelist_file" "./updateryujinxavalonia.sh"
    remove_game_by_path "$gamelist_file" "./batocera-switch-installer.sh"
    remove_game_by_path "$gamelist_file" "./Suyu Qlauncher.sh"
    remove_game_by_path "$gamelist_file" "./batocera-switch-updater.sh"
    remove_game_by_path "$gamelist_file" "./Switch Updater.sh"
    remove_game_by_path "$gamelist_file" "./updateyuzuEA.sh"
    remove_game_by_path "$gamelist_file" "./updateyuzu.sh"
    remove_game_by_path "$gamelist_file" "./ryujinx_config.sh"
    remove_game_by_path "$gamelist_file" "./yuzu_config.sh"
    remove_game_by_path "$gamelist_file" "./citron_config.sh"
    remove_game_by_path "$gamelist_file2" "./_Switch-Home-menu.xci"

    # Supprimer entrée avant création
    remove_game_by_path "$gamelist_file2" "./ryujinx_config.sh"
    # Ajouter Ryujinx Config
    xmlstarlet ed -L \
        -s "/gameList" -t elem -n "game" -v "" \
        -s "/gameList/game[last()]" -t elem -n "path" -v "./ryujinx_config.xci_config" \
        -s "/gameList/game[last()]" -t elem -n "name" -v "1-Ryujinx Config App" \
        -s "/gameList/game[last()]" -t elem -n "desc" -v "Lancement de RYUJINX en mode application pour configuration manuelle." \
        -s "/gameList/game[last()]" -t elem -n "developer" -v "Foclabroc DreamerCG Spirit" \
        -s "/gameList/game[last()]" -t elem -n "publisher" -v "Foclabroc DreamerCG Spirit" \
        -s "/gameList/game[last()]" -t elem -n "genre" -v "Switch" \
        -s "/gameList/game[last()]" -t elem -n "rating" -v "1.00" \
        -s "/gameList/game[last()]" -t elem -n "region" -v "eu" \
        -s "/gameList/game[last()]" -t elem -n "lang" -v "fr" \
        -s "/gameList/game[last()]" -t elem -n "image" -v "./images/ryujinx_config_screen.png" \
        -s "/gameList/game[last()]" -t elem -n "wheel" -v "./images/ryujinx_config_logo.png" \
        -s "/gameList/game[last()]" -t elem -n "thumbnail" -v "./images/ryujinx_config.png" \
        "$gamelist_file2"

    # Supprimer entrée avant création
    remove_game_by_path "$gamelist_file2" "./yuzu_config.sh"
    # Ajouter Eden Config
    xmlstarlet ed -L \
        -s "/gameList" -t elem -n "game" -v "" \
        -s "/gameList/game[last()]" -t elem -n "path" -v "./eden_config.xci_config" \
        -s "/gameList/game[last()]" -t elem -n "name" -v "1-Eden Config App" \
        -s "/gameList/game[last()]" -t elem -n "desc" -v "Lancement de EDEN en mode application pour configuration manuelle de Eden." \
        -s "/gameList/game[last()]" -t elem -n "developer" -v "Foclabroc DreamerCG Spirit" \
        -s "/gameList/game[last()]" -t elem -n "publisher" -v "Foclabroc DreamerCG Spirit" \
        -s "/gameList/game[last()]" -t elem -n "genre" -v "Switch" \
        -s "/gameList/game[last()]" -t elem -n "rating" -v "1.00" \
        -s "/gameList/game[last()]" -t elem -n "region" -v "eu" \
        -s "/gameList/game[last()]" -t elem -n "lang" -v "fr" \
        -s "/gameList/game[last()]" -t elem -n "image" -v "./images/yuzu_config_screen.png" \
        -s "/gameList/game[last()]" -t elem -n "wheel" -v "./images/yuzu_config_logo.png" \
        -s "/gameList/game[last()]" -t elem -n "thumbnail" -v "./images/yuzu_config.png" \
        "$gamelist_file2"

    # Supprimer entrée avant création
    remove_game_by_path "$gamelist_file2" "./citron_config.sh"
    # Ajouter Citron Config
    xmlstarlet ed -L \
        -s "/gameList" -t elem -n "game" -v "" \
        -s "/gameList/game[last()]" -t elem -n "path" -v "./citron_config.xci_config" \
        -s "/gameList/game[last()]" -t elem -n "name" -v "1-Citron Config App" \
        -s "/gameList/game[last()]" -t elem -n "desc" -v "Lancement de CITRON en mode application pour configuration manuelle de Citron." \
        -s "/gameList/game[last()]" -t elem -n "developer" -v "Foclabroc DreamerCG Spirit" \
        -s "/gameList/game[last()]" -t elem -n "publisher" -v "Foclabroc DreamerCG Spirit" \
        -s "/gameList/game[last()]" -t elem -n "genre" -v "Switch" \
        -s "/gameList/game[last()]" -t elem -n "rating" -v "1.00" \
        -s "/gameList/game[last()]" -t elem -n "region" -v "eu" \
        -s "/gameList/game[last()]" -t elem -n "lang" -v "fr" \
        -s "/gameList/game[last()]" -t elem -n "image" -v "./images/citron_config_screen.png" \
        -s "/gameList/game[last()]" -t elem -n "wheel" -v "./images/citron_config_logo.png" \
        -s "/gameList/game[last()]" -t elem -n "thumbnail" -v "./images/citron_config.png" \
        "$gamelist_file2"

    # Supprimer entrée avant création
    remove_game_by_path "$gamelist_file" "./Switch AppImages Updater.sh"
    # Ajouter Updater
    xmlstarlet ed -L \
        -s "/gameList" -t elem -n "game" -v "" \
        -s "/gameList/game[last()]" -t elem -n "path" -v "./Switch AppImages Updater.sh" \
        -s "/gameList/game[last()]" -t elem -n "name" -v "Switch Emulator Updater" \
        -s "/gameList/game[last()]" -t elem -n "desc" -v "Script de Mise à jour des emulateurs Switch." \
        -s "/gameList/game[last()]" -t elem -n "developer" -v "Foclabroc" \
        -s "/gameList/game[last()]" -t elem -n "publisher" -v "Foclabroc" \
        -s "/gameList/game[last()]" -t elem -n "genre" -v "Switch" \
        -s "/gameList/game[last()]" -t elem -n "rating" -v "1.00" \
        -s "/gameList/game[last()]" -t elem -n "region" -v "eu" \
        -s "/gameList/game[last()]" -t elem -n "lang" -v "fr" \
        -s "/gameList/game[last()]" -t elem -n "image" -v "./images/updater_app_screen.png" \
        -s "/gameList/game[last()]" -t elem -n "wheel" -v "./images/updater_app_logo.png" \
        -s "/gameList/game[last()]" -t elem -n "thumbnail" -v "./images/updater_app.png" \
        "$gamelist_file"

    # Supprimer entrée avant création
    remove_game_by_path "$gamelist_file2" "./eden_qlaunch.xci_config"
    # Ajouter Qlauncher
    xmlstarlet ed -L \
        -s "/gameList" -t elem -n "game" -v "" \
        -s "/gameList/game[last()]" -t elem -n "path" -v "./eden_qlaunch.xci_config" \
        -s "/gameList/game[last()]" -t elem -n "name" -v "1-Switch Home Menu (Only with Eden-emu)" \
        -s "/gameList/game[last()]" -t elem -n "desc" -v "Démarrage en mode Ecran d'accueil Switch réel (qlauncher) A lancer uniquement avec EDEN !!!." \
        -s "/gameList/game[last()]" -t elem -n "developer" -v "Foclabroc" \
        -s "/gameList/game[last()]" -t elem -n "publisher" -v "Foclabroc" \
        -s "/gameList/game[last()]" -t elem -n "genre" -v "Switch" \
        -s "/gameList/game[last()]" -t elem -n "rating" -v "1.00" \
        -s "/gameList/game[last()]" -t elem -n "region" -v "eu" \
        -s "/gameList/game[last()]" -t elem -n "lang" -v "fr" \
        -s "/gameList/game[last()]" -t elem -n "image" -v "./images/_Switch-Home-menu-screen.png" \
        -s "/gameList/game[last()]" -t elem -n "wheel" -v "./images/_Switch-Home-menu-logo.png" \
        -s "/gameList/game[last()]" -t elem -n "thumbnail" -v "./images/_Switch-Home-menu-box.png" \
        "$gamelist_file2"

        for file in "$gamelist_file" "$gamelist_file2"; do
            [ -f "$file" ] && sed -i '/<sortname>[^<]*<\/sortname>/d' "$file"
        done

    log "Cleanup temporary files"
    rm -f "/userdata/README.md"
    rm -rf "/userdata/tmpf"
    rm -f "/userdata/system/services/foclaswitch"

    # --- CUSTOM SERVICE (labwc window decorations, x86-64-v3 only) ---
    ARCH_LEVEL=$(batocera-info | grep '^Board:' | awk '{print $2}')
    if [[ "$ARCH_LEVEL" == "x86-64-v3" ]]; then
        log "Architecture x86-64-v3 détectée, déploiement du custom_service labwc"
        SERVICE_FILE="/userdata/system/services/custom_service"
        mkdir -p /userdata/system/services

        MARKER_START="# >>> FOCLABROC LABWC WINDOW RULES >>>"
        MARKER_END="# <<< FOCLABROC LABWC WINDOW RULES <<<"

        read -r -d '' SERVICE_BLOCK <<'SVCEOF'
# >>> FOCLABROC LABWC WINDOW RULES >>>
ln -sf /userdata/system/switch/extra/xmlstarlet /usr/bin/xmlstarlet

RC_XML="/userdata/system/.config/labwc/rc.xml"

if [ ! -f "$RC_XML" ]; then
    /etc/init.d/S14labwc start
fi

add_rule() {
    local id="$1"
    if ! grep -qF "identifier=\"${id}\"" "$RC_XML"; then
        xmlstarlet ed -L \
            -s "/labwc_config/windowRules" -t elem -n "windowRule" -v "" \
            -s "/labwc_config/windowRules/windowRule[last()]" -t attr -n "identifier" -v "${id}" \
            -s "/labwc_config/windowRules/windowRule[last()]" -t attr -n "serverDecoration" -v "yes" \
            "$RC_XML"
    fi
}

if [ -f "$RC_XML" ]; then
    add_rule "eden"
    add_rule "Ryujinx"
    add_rule "*citron*"

    LABWC_PID=$(pgrep -o -x labwc)
    if [ -n "$LABWC_PID" ]; then
        LABWC_PID="$LABWC_PID" labwc --reconfigure
    fi
fi
# <<< FOCLABROC LABWC WINDOW RULES <<<
SVCEOF

        BLOCK_FILE=$(mktemp)
        printf '%s\n' "$SERVICE_BLOCK" > "$BLOCK_FILE"

        if [ -f "$SERVICE_FILE" ]; then
            if grep -qF "$MARKER_START" "$SERVICE_FILE"; then
                # Bloc déjà présent : le remplace (mise à jour) sans toucher au reste du fichier
                awk -v start="$MARKER_START" -v end="$MARKER_END" -v blockfile="$BLOCK_FILE" '
                    $0 == start {
                        while ((getline line < blockfile) > 0) print line
                        close(blockfile)
                        skip=1
                        next
                    }
                    $0 == end {skip=0; next}
                    skip {next}
                    {print}
                ' "$SERVICE_FILE" > "${SERVICE_FILE}.tmp" && mv "${SERVICE_FILE}.tmp" "$SERVICE_FILE"
                log "Bloc labwc mis à jour dans custom_service existant"
            else
                # custom_service existant mais sans notre bloc : on l'ajoute à la fin, on préserve le reste
                printf '\n%s\n' "$SERVICE_BLOCK" >> "$SERVICE_FILE"
                log "Bloc labwc ajouté à custom_service existant (contenu préservé)"
            fi
        else
            printf '#!/bin/bash\n\n%s\n' "$SERVICE_BLOCK" > "$SERVICE_FILE"
            log "custom_service créé avec le bloc labwc"
        fi

        rm -f "$BLOCK_FILE"

        chmod +x "$SERVICE_FILE"
        batocera-services enable custom_service
        "$SERVICE_FILE"
    else
        log "Architecture ${ARCH_LEVEL:-inconnue} — custom_service labwc non déployé"
        SERVICE_FILE="/userdata/system/services/custom_service"
        MARKER_START="# >>> FOCLABROC LABWC WINDOW RULES >>>"
        MARKER_END="# <<< FOCLABROC LABWC WINDOW RULES <<<"

        if [ -f "$SERVICE_FILE" ] && grep -qF "$MARKER_START" "$SERVICE_FILE"; then
            awk -v start="$MARKER_START" -v end="$MARKER_END" '
                $0 == start {skip=1; next}
                $0 == end {skip=0; next}
                skip {next}
                {print}
            ' "$SERVICE_FILE" > "${SERVICE_FILE}.tmp" && mv "${SERVICE_FILE}.tmp" "$SERVICE_FILE"
            log "Bloc labwc retiré de custom_service (architecture non compatible)"

            # Si le fichier ne contient plus rien d'utile (juste le shebang, ou vide), on le désactive/supprime
            REMAINING=$(grep -vE '^\s*#!/bin/bash\s*$|^\s*$' "$SERVICE_FILE")
            if [ -z "$REMAINING" ]; then
                rm -f "$SERVICE_FILE"
                log "custom_service supprimé (plus aucun contenu après retrait du bloc labwc)"
            fi
        fi
    fi

    log "!!!!System pack update finished!!!!"
    echo "STATUS_SYS=OK" >> "$STATUS_FILE"
}

# ===============================
# UPDATE CITRON
# ===============================
update_citron() {
    local assets_page tag_page appimage_path appimage_url file_name commit build_date dest tmp1 tmp2

    log "  "
    log "  "
    log "!!!!START Citron AppImage update!!!!"
    log "Checking latest Citron nightly-linux release on GitHub"

    tmp1=$(mktemp)
    curl_step "citron" "$tmp1" -Ls --connect-timeout 5 --max-time 15 "https://github.com/NextendoNetwork/citron-nextendo/releases/expanded_assets/nightly-linux"
    assets_page=$(cat "$tmp1")
    rm -f "$tmp1"

    if [[ -z "$assets_page" ]]; then
        log "ERROR Citron: unable to fetch expanded assets page"
        echo "STATUS_CITRON=ERREUR" >> "$STATUS_FILE"
        return
    fi

    appimage_path=$(echo "$assets_page" \
        | grep -Eo '/NextendoNetwork/citron-nextendo/releases/download/nightly-linux/citron_nightly-[0-9a-f]+-linux-x86_64_v3\.AppImage' \
        | head -n1)

    if [[ -z "$appimage_path" ]]; then
        log "ERROR Citron: no Linux x86_64_v3 AppImage found in release assets"
        echo "STATUS_CITRON=ERREUR" >> "$STATUS_FILE"
        return
    fi

    appimage_url="https://github.com${appimage_path}"
    file_name="${appimage_url##*/}"
    commit=$(echo "$file_name" | sed -E 's/^citron_nightly-([0-9a-f]+)-linux.*/\1/')

    tmp2=$(mktemp)
    curl_step "citron" "$tmp2" -Ls --connect-timeout 5 --max-time 15 "https://github.com/NextendoNetwork/citron-nextendo/releases/tag/nightly-linux"
    tag_page=$(cat "$tmp2")
    rm -f "$tmp2"

    build_date=$(echo "$tag_page" | grep -Eo 'Date: [0-9]{4}-[0-9]{2}-[0-9]{2}' | head -n1 | sed 's/Date: //')

    dest="$SWITCH_APPIMAGES/citron-emu.AppImage"

    log "Detected AppImage file: $file_name"
    log "Detected commit: $commit"
    log "Detected build date: ${build_date:-unknown}"
    log "Downloading: $appimage_url"

    if wget_step "$appimage_url" "$dest" "citron" && deploy_if_valid "$dest"; then
        echo "STATUS_CITRON=OK" >> "$STATUS_FILE"
        if [[ -n "$build_date" ]]; then
            echo "CITRON_VERSION=$build_date" >> "$VERSIONS_FILE"
        else
            echo "CITRON_VERSION=nightly-$commit" >> "$VERSIONS_FILE"
        fi
    else
        log "ERROR Citron: download or deploy failed"
        echo "STATUS_CITRON=ERREUR" >> "$STATUS_FILE"
    fi
}
# update_citron() {
    # local appimage_url dest full_version

    # log "  "
    # log "  "
    # log "!!!!START Citron AppImage download (fixed version)!!!!"

    # # Version fixe
    # full_version="Neo-2026.09.10"
    # # URL directe
    # appimage_url="https://foclabroc.freeboxos.fr:55973/share/4Hd7ueCAGnpabXA5/citron-emu(2026.09.10).AppImage"

    # dest="$SWITCH_APPIMAGES/citron-emu.AppImage"

    # log "Fixed version: $full_version"
    # log "Downloading: $appimage_url"

    # if wget_step "$appimage_url" "$dest" "citron" && deploy_if_valid "$dest"; then
        # echo "STATUS_CITRON=OK" >> "$STATUS_FILE"
        # echo "CITRON_VERSION=$full_version" >> "$VERSIONS_FILE"
    # else
        # log "ERROR Citron: download or deploy failed"
        # echo "STATUS_CITRON=ERREUR" >> "$STATUS_FILE"
    # fi
# }

# ===============================
# UPDATE EDEN NIGHTLY
# ===============================
update_nightly() {
    local json release raw date base short url dest tmp

    log ""
    log ""
    log "!!!!START Eden Nightly AppImage update!!!!"
    log "Checking Eden Nightly latest release"

    tmp=$(mktemp)
    curl_step "eden-nightly" "$tmp" -fsL --connect-timeout 5 --max-time 15 "https://nightly.eden-emu.dev/latest/release.json"
    json=$(cat "$tmp")
    rm -f "$tmp"

    if [[ -z "$json" ]]; then
        log "ERROR Nightly: release.json unreachable"
        echo "STATUS_NIGHTLY=ERREUR" >> "$STATUS_FILE"
        return
    fi

    release=$(echo "$json" \
        | grep -Eo '"tag_name": *"[^"]+"' \
        | sed -E 's/.*"([^"]+)"$/\1/')
    if [[ -z "$release" ]]; then
        log "ERROR Nightly: tag_name not found"
        echo "STATUS_NIGHTLY=ERREUR" >> "$STATUS_FILE"
        return
    fi

    # Base URL (fallback si absente du JSON)
    base=$(echo "$json" \
        | grep -Eo '"base": *"[^"]+"' \
        | sed -E 's/.*"([^"]+)"$/\1/')
    [[ -z "$base" ]] && base="https://nightly.eden-emu.dev"

    # Commit court = partie après le "." du tag
    short="${release#*.}"
    if [[ "$short" == "$release" || -z "$short" ]]; then
        log "ERROR Nightly: unexpected tag format ($release)"
        echo "STATUS_NIGHTLY=ERREUR" >> "$STATUS_FILE"
        return
    fi

    # Date depuis le champ "name": "Eden Nightly - Apr 23 2026"
    raw=$(echo "$json" \
        | grep -Eo '"name": *"Eden Nightly - [^"]+"' \
        | sed -E 's/.*"Eden Nightly - ([^"]+)"$/\1/')
    date=$(date -d "$raw" +%Y-%m-%d 2>/dev/null)
    [[ -n "$date" ]] && log "Release date: $date"

    # Construction de l'URL
    url="${base}/${release}/Eden-Linux-${short}-amd64-gcc-standard.AppImage"

    # Vérification d'existence (HEAD)
    if ! curl_step "eden-nightly" /dev/null -fsLI --connect-timeout 5 --max-time 15 "$url"; then
        log "ERROR Nightly: AppImage not reachable ($url)"
        echo "STATUS_NIGHTLY=ERREUR" >> "$STATUS_FILE"
        return
    fi

    dest="$SWITCH_APPIMAGES/eden-nightly.AppImage"
    log "Detected Nightly version: $release"
    log "Downloading: $url"

    if wget_step "$url" "$dest" "eden-nightly" && deploy_if_valid "$dest"; then
        echo "STATUS_NIGHTLY=OK" >> "$STATUS_FILE"
        echo "NIGHTLY_VERSION=$release" >> "$VERSIONS_FILE"
        [[ -n "$date" ]] && echo "NIGHTLY_DATE=$date" >> "$VERSIONS_FILE"
    else
        echo "STATUS_NIGHTLY=ERREUR" >> "$STATUS_FILE"
    fi
}

# ===============================
# UPDATE EDEN
# ===============================
update_eden() {
    local json release base url dest tmp

    log ""
    log ""
    log "!!!!START Eden AppImage update!!!!"
    log "Checking Eden latest release"

    tmp=$(mktemp)
    curl_step "eden" "$tmp" -fsL --connect-timeout 5 --max-time 15 "https://stable.eden-emu.dev/latest/release.json"
    json=$(cat "$tmp")
    rm -f "$tmp"

    if [[ -z "$json" ]]; then
        log "ERROR Eden: release.json unreachable"
        echo "STATUS_EDEN=ERREUR" >> "$STATUS_FILE"
        return
    fi

    release=$(echo "$json" \
        | grep -Eo '"tag_name": *"[^"]+"' \
        | sed -E 's/.*"([^"]+)"$/\1/')
    if [[ -z "$release" ]]; then
        log "ERROR Eden: tag_name not found"
        echo "STATUS_EDEN=ERREUR" >> "$STATUS_FILE"
        return
    fi

    base=$(echo "$json" \
        | grep -Eo '"base": *"[^"]+"' \
        | sed -E 's/.*"([^"]+)"$/\1/')
    [[ -z "$base" ]] && base="https://stable.eden-emu.dev"

    url="${base}/${release}/Eden-Linux-${release}-amd64-gcc-standard.AppImage"

    if ! curl_step "eden" /dev/null -fsLI --connect-timeout 5 --max-time 15 "$url"; then
        log "ERROR Eden: AppImage not reachable ($url)"
        echo "STATUS_EDEN=ERREUR" >> "$STATUS_FILE"
        return
    fi

    dest="$SWITCH_APPIMAGES/eden-emu.AppImage"
    log "Detected Eden version: $release"
    log "Downloading: $url"

    if wget_step "$url" "$dest" "eden" && deploy_if_valid "$dest"; then
        echo "STATUS_EDEN=OK" >> "$STATUS_FILE"
        echo "EDEN_VERSION=$release" >> "$VERSIONS_FILE"
    else
        echo "STATUS_EDEN=ERREUR" >> "$STATUS_FILE"
    fi
}

# ===============================
# UPDATE EDEN PGO
# ===============================
update_eden_pgo() {
    local release url dest

    log ""
    log ""
    log "!!!!START Eden PGO AppImage update!!!!"
    log "Checking Eden PGO latest release"

    release=$(grep '^EDEN_VERSION=' "$VERSIONS_FILE" | cut -d= -f2)
    if [[ -z "$release" ]]; then
        log "ERROR Eden-PGO: Eden version missing"
        echo "STATUS_EDEN_PGO=ERREUR" >> "$STATUS_FILE"
        return
    fi

    url="https://stable.eden-emu.dev/${release}/Eden-Linux-${release}-amd64-clang-pgo.AppImage"

    if ! curl_step "eden-pgo" /dev/null -fsLI --connect-timeout 5 --max-time 15 "$url"; then
        log "ERROR Eden-PGO: AppImage not reachable ($url)"
        echo "STATUS_EDEN_PGO=ERREUR" >> "$STATUS_FILE"
        return
    fi

    dest="$SWITCH_APPIMAGES/eden-pgo.AppImage"
    log "Detected Eden PGO version: $release"
    log "Downloading: $url"

    if wget_step "$url" "$dest" "eden-pgo" && deploy_if_valid "$dest"; then
        echo "STATUS_EDEN_PGO=OK" >> "$STATUS_FILE"
        echo "EDEN_PGO_VERSION=$release" >> "$VERSIONS_FILE"
    else
        echo "STATUS_EDEN_PGO=ERREUR" >> "$STATUS_FILE"
    fi
}

# ===============================
# UPDATE RYUJINX
# ===============================
 
# Build de secours (utilisé si la version standard Canary est indisponible)
RYUJINX_FALLBACK_URL="https://foclabroc.freeboxos.fr:55973/share/zmkgBds8BiTLW3fG/ryujinx-canary-1.3.351.tar.gz"
RYUJINX_FALLBACK_VERSION="Canary-1.3.351-Last"
 
# Télécharge et extrait un build Ryujinx au format tar.gz
# $1 = URL de l'archive, $2 = version (pour le fichier de versions), $3 = nom local de l'archive
install_ryujinx_tarball() {
    local archive_url="$1" release="$2" archive_name="$3" dest
 
    dest="$SWITCH_APPIMAGES/$archive_name"
    log "Detected Ryujinx version: $release"
 
    if wget_step "$archive_url" "$dest" "ryujinx" && deploy_if_valid "$dest"; then
        log "Extraction du build Ryujinx (tar.gz)..."
        cd "$SWITCH_APPIMAGES_FINAL"
        rm -rf ryujinx-extracted ryujinx-extracted-tmp
        mkdir -p ryujinx-extracted-tmp
        tar -xzf "$archive_name" -C ryujinx-extracted-tmp 2>>"$LOG_FILE"
 
        if [ -d "ryujinx-extracted-tmp/usr/bin" ]; then
            mv ryujinx-extracted-tmp ryujinx-extracted
            rm -f "$archive_name"
            chmod +x ryujinx-extracted/usr/bin/Ryujinx
            log "Extraction du build Ryujinx terminée"
            chmod +x /userdata/system/switch/extra/ryu_wrapper 2>/dev/null
            echo "STATUS_RYUJINX=OK" >> "$STATUS_FILE"
            echo "RYUJINX_VERSION=$release" >> "$VERSIONS_FILE"
            return 0
        else
            log "ERROR Ryujinx: structure usr/bin introuvable dans l'archive"
            rm -rf ryujinx-extracted-tmp
            rm -f "$archive_name"
            echo "STATUS_RYUJINX=ERREUR" >> "$STATUS_FILE"
            return 1
        fi
    else
        log "ERROR Ryujinx: téléchargement ou déploiement de l'archive échoué"
        echo "STATUS_RYUJINX=ERREUR" >> "$STATUS_FILE"
        return 1
    fi
}
 
# Version standard (AppImage Canary). Retourne 1 en cas d'échec, sans écrire de statut
# (le fallback s'en charge).
update_ryujinx_standard() {
    local html release url dest tmp
 
    tmp=$(mktemp)
    curl_step "ryujinx" "$tmp" -fsL --connect-timeout 5 --max-time 15 "https://git.ryujinx.app/Ryubing/Canary/releases"
    html=$(cat "$tmp")
    rm -f "$tmp"
 
    if [[ -z "$html" ]]; then
        log "ERROR Ryujinx: unable to fetch releases page"
        return 1
    fi
 
    release=$(echo "$html" \
        | grep -oP 'releases/download/\K[0-9.]+' \
        | head -n1)
 
    if [[ -z "$release" ]]; then
        log "ERROR Ryujinx: version parsing failed"
        return 1
    fi
 
    url="https://git.ryujinx.app/Ryubing/Canary/releases/download/${release}/ryujinx-canary-${release}-x64.AppImage"
    dest="$SWITCH_APPIMAGES/ryujinx-emu.AppImage"
 
    log "Detected Ryujinx version: $release"
    log "Downloading: $url"
 
    if wget_step "$url" "$dest" "ryujinx-emu" && deploy_if_valid "$dest"; then
        log "Extraction Ryujinx AppImage..."
        cd "$SWITCH_APPIMAGES_FINAL"
        rm -rf ryujinx-extracted
        ./ryujinx-emu.AppImage --appimage-extract 2>>"$LOG_FILE"
        if [ -d "squashfs-root/usr/bin" ]; then
            mv squashfs-root ryujinx-extracted
            rm -f ryujinx-emu.AppImage
            log "Extraction Ryujinx terminée, AppImage supprimée"
        else
            log "WARN: Extraction échouée, AppImage conservée"
        fi
 
        chmod +x /userdata/system/switch/extra/ryu_wrapper 2>/dev/null
 
        echo "STATUS_RYUJINX=OK" >> "$STATUS_FILE"
        echo "RYUJINX_VERSION=$release" >> "$VERSIONS_FILE"
        return 0
    fi
 
    log "ERROR Ryujinx: téléchargement de l'AppImage standard échoué"
    return 1
}
 
update_ryujinx() {
    local release archive_url product_name sys_vendor is_steamdeck
 
    log "  "
    log "  "
    log "!!!!START Ryujinx AppImage update!!!!"
 
    # Détection Steam Deck
    product_name=$(cat /sys/class/dmi/id/product_name 2>/dev/null)
    sys_vendor=$(cat /sys/class/dmi/id/sys_vendor 2>/dev/null)
    log "DEBUG dmi raw product_name='$product_name' sys_vendor='$sys_vendor'"
 
    product_name="${product_name,,}"
    sys_vendor="${sys_vendor,,}"
 
    is_steamdeck=0
    if [[ "$product_name" == "jupiter" || "$product_name" == "galileo" || "$product_name" == *"steam deck"* ]]; then
        is_steamdeck=1
    elif [[ "$sys_vendor" == "valve" ]]; then
        is_steamdeck=1
    fi
 
    if [[ "$is_steamdeck" -eq 1 ]]; then
        log "Steam Deck detected (product_name: $product_name) — using custom patched Ryujinx build"
 
        release="Canary-1.3.351-steamdeck-patched-Last"
        archive_url="https://foclabroc.freeboxos.fr:55973/share/C_RhYyewjbV-1wMa/ryujinx-1.3.351-steamdeck.tar.gz"
 
        # Supprime la DB de mapping périmée pour forcer le mapping custom Batocera
        rm -f "/userdata/system/configs/Ryujinx/gamecontrollerdb.txt"
        rm -f "/userdata/system/configs/Ryujinx/SDL_GameControllerDB.txt"
        log "Ancien gamecontrollerdb.txt supprimé (si présent)"
 
        install_ryujinx_tarball "$archive_url" "$release" "ryujinx-patched.tar.gz"
        return
    fi
 
    log "Non-Steam Deck device — checking Ryujinx Canary latest release"
 
    if update_ryujinx_standard; then
        return
    fi
 
    log "WARN Ryujinx: version standard indisponible — fallback vers le build $RYUJINX_FALLBACK_VERSION (tar.gz)"
    install_ryujinx_tarball "$RYUJINX_FALLBACK_URL" "$RYUJINX_FALLBACK_VERSION" "ryujinx-fallback.tar.gz"
}

# ===============================
# RUN UPDATE
# ===============================
run_update() {

GLOBAL_PERCENT=0

(
    install_new_pack
    GLOBAL_PERCENT=20

    update_citron
    GLOBAL_PERCENT=33

    update_nightly
    GLOBAL_PERCENT=53

    update_eden
    GLOBAL_PERCENT=68

    update_eden_pgo
    GLOBAL_PERCENT=83

    update_ryujinx
    GLOBAL_PERCENT=100

) | dialog --backtitle "$BACKTITLE" \
           --title "$(tr GAUGE_TITLE)" \
           --gauge "\n$(tr GAUGE_TEXT)" 12 60 0

    touch "$STATUS_FILE" "$VERSIONS_FILE"
    set -a
    source "$STATUS_FILE"
    source "$VERSIONS_FILE"
    set +a

    [[ "$STATUS_SYS" == "OK" ]] \
        && SYS_LINE="$(tr SYS_FILES) : OK" \
        || SYS_LINE="$(tr SYS_FILES) : $(tr SYS_FAIL)"

    [[ "$STATUS_CITRON" == "OK" ]] \
        && CITRON_LINE="Citron-Neo     : OK ---->(${CITRON_VERSION})" \
        || CITRON_LINE="Citron-Neo     : $(tr ERROR) [CITRON SERVERS DOWN!!] citron-emu $(tr ERROR_EMU)"

    [[ "$STATUS_NIGHTLY" == "OK" ]] \
        && NIGHTLY_LINE="Eden-Nightly   : OK ---->(${NIGHTLY_DATE})" \
        || NIGHTLY_LINE="Eden-Nightly   : $(tr ERROR) eden-nightly $(tr ERROR_EMU)"

    [[ "$STATUS_EDEN" == "OK" ]] \
        && EDEN_LINE="Eden           : OK ---->(${EDEN_VERSION})" \
        || EDEN_LINE="Eden           : $(tr ERROR) eden-emu $(tr ERROR_EMU)"

    [[ "$STATUS_EDEN_PGO" == "OK" ]] \
        && EDEN_PGO_LINE="Eden-PGO       : OK ---->(${EDEN_PGO_VERSION})" \
        || EDEN_PGO_LINE="Eden-PGO       : $(tr ERROR) eden-pgo $(tr ERROR_EMU)"

    [[ "$STATUS_RYUJINX" == "OK" ]] \
        && RYUJINX_LINE="Ryujinx        : OK ---->(${RYUJINX_VERSION})" \
        || RYUJINX_LINE="Ryujinx        : $(tr ERROR) Ryujinx $(tr ERROR_EMU)"
    curl http://127.0.0.1:1234/reloadgames
    dialog --backtitle "$BACKTITLE" \
           --title "$(tr FINAL_TITLE)" \
           --ok-label "$(tr OK_LABEL)" \
           --no-collapse \
           --msgbox "$(cat <<EOF

$(tr UPDATE_RESULT)

$SYS_LINE

$CITRON_LINE
$NIGHTLY_LINE
$EDEN_LINE
$EDEN_PGO_LINE
$RYUJINX_LINE

Logs : $LOG_FILE
EOF
)" 18 70

clear
exit 0
}

# ===============================
# CONFIRMATION
# ===============================
dialog --backtitle "$BACKTITLE" \
       --title "$(tr CONFIRM_TITLE)" \
       --yes-label "$(tr YES_LABEL)" \
       --no-label "$(tr NO_LABEL)" \
       --yesno "$(tr CONFIRM_TEXT)" 14 60

case $? in
    0) run_update ;;
    *) clear; exit 0;;
esac
