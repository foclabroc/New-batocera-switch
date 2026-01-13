from __future__ import annotations

import filecmp
import logging
import os
import re
import shutil
import subprocess
import sys
import json
import stat
import uuid
from shutil import copyfile

from pathlib import Path
from typing import TYPE_CHECKING

from configgen import Command as Command
from configgen.batoceraPaths import CONFIGS, HOME, ROMS, SAVES, CACHE, mkdir_if_not_exists
from configgen.controller import generate_sdl_game_controller_config
from configgen.generators.Generator import Generator
from configgen.utils.configparser import CaseSensitiveRawConfigParser

eslog = logging.getLogger(__name__)

if TYPE_CHECKING:
    from configgen.types import HotkeysContext

subprocess.run(["batocera-mouse", "show"], check=False)

def getCurrentCard() -> str | None:
    proc = subprocess.Popen(["/userdata/system/switch/configgen/generators/detectvideo.sh"], stdout=subprocess.PIPE, shell=True)
    (out, err) = proc.communicate()
    for val in out.decode().splitlines():
        return val # return the first line

def detect_device():
    # 1) DMI product name (primary, most reliable)
    try:
        with open("/sys/class/dmi/id/product_name", "r") as f:
            name = f.read().strip()
            lname = name.lower()

            if lname in ("jupiter", "galileo") or "steam deck" in lname:
                return True, name

            # Known device but not Steam Deck
            return False, name
    except:
        pass
    return False, "Unknown"

class RyujinxGenerator(Generator):

    def getHotkeysContext(self) -> HotkeysContext:
        return {
            "name": "ryujinx-emu",
            "keys": { "exit": ["KEY_LEFTALT", "KEY_F4"]}
        }


    def generate(self, system, rom, playersControllers, metadata, guns, wheels, gameResolution):


        st = os.stat("/userdata/system/switch/appimages/ryujinx-emu.AppImage")
        os.chmod("/userdata/system/switch/appimages/ryujinx-emu.AppImage", st.st_mode | stat.S_IEXEC)
        st = os.stat("/userdata/system/switch/configgen/generators/detectvideo.sh")
        os.chmod("/userdata/system/switch/configgen/generators/detectvideo.sh", st.st_mode | stat.S_IEXEC)

        mkdir_if_not_exists(Path("/userdata/system/configs/Ryujinx"))
        mkdir_if_not_exists(Path("/userdata/system/configs/Ryujinx/system"))

        template = Path("/userdata/system/switch/configgen/Config.json.template")
        target = CONFIGS / "Ryujinx" / "Config.json.template"
        copyfile(template, target) 

        #Create Keys Folder
        mkdir_if_not_exists(Path("/userdata/system/configs/Ryujinx/bis"))
        mkdir_if_not_exists(Path("/userdata/system/configs/Ryujinx/bis/system"))
        mkdir_if_not_exists(Path("/userdata/system/configs/Ryujinx/bis/system/Contents"))

        #Link Ryujinx firmware/key folder
        #KEY-------
        if os.path.exists("/userdata/system/configs/Ryujinx/system"):
            if not os.path.islink("/userdata/system/configs/Ryujinx/system"):
                shutil.rmtree("/userdata/system/configs/Ryujinx/system")
                os.symlink("/userdata/bios/switch/keys_ryujinx", "/userdata/system/configs/Ryujinx/system")
            else:
                current_target = os.readlink("/userdata/system/configs/Ryujinx/system")
                if current_target != "/userdata/bios/switch/keys_ryujinx":
                    os.unlink("/userdata/bios/switch/keys_ryujinx")
                    os.symlink("/userdata/bios/switch/keys_ryujinx", "/userdata/system/configs/Ryujinx/system")
        else:
            os.symlink("/userdata/bios/switch/keys_ryujinx", "/userdata/system/configs/Ryujinx/system")
        # #FIRMWARE-------
        # if os.path.exists("/userdata/system/configs/Ryujinx/bis/system/Contents/registered"):
            # if not os.path.islink("/userdata/system/configs/Ryujinx/bis/system/Contents/registered"):
                # shutil.rmtree("/userdata/system/configs/Ryujinx/bis/system/Contents/registered")
                # os.symlink("/userdata/bios/switch/firmware_ryujinx", "/userdata/system/configs/Ryujinx/bis/system/Contents/registered")
            # else:
                # current_target = os.readlink("/userdata/system/configs/Ryujinx/bis/system/Contents/registered")
                # if current_target != "/userdata/bios/switch/firmware_ryujinx":
                    # os.unlink("/userdata/system/configs/Ryujinx/bis/system/Contents/registered")
                    # os.symlink("/userdata/bios/switch/firmware_ryujinx", "/userdata/system/configs/Ryujinx/bis/system/Contents/registered")
        # else:
            # os.symlink("/userdata/bios/switch/firmware_ryujinx", "/userdata/system/configs/Ryujinx/bis/system/Contents/registered")


        RyujinxConfig = Path('/userdata/system/configs/Ryujinx/Config.json')
        RyujinxConfigTemplate = str(CONFIGS) + '/Ryujinx/Config.json.template'
        RyujinxHome = CONFIGS

        RyujinxConfigFileBefore = str(CONFIGS) + '/Ryujinx/Config.json.before'

        RyujinxRegisteredBios = Path('/userdata/system/configs/Ryujinx/bis/system/Contents/registered')

        #Configuration update
        RyujinxGenerator.writeRyujinxConfig(str(CONFIGS) + '/Ryujinx/Config.json', RyujinxConfigFileBefore, RyujinxConfigTemplate, system, playersControllers)

        is_steamdeck, device_name = detect_device()

        environment = {
            "SDL_GAMECONTROLLERCONFIG": generate_sdl_game_controller_config(playersControllers),

            "DRI_PRIME": "1",
            "AMD_VULKAN_ICD": "RADV",
            "DISABLE_LAYER_AMD_SWITCHABLE_GRAPHICS_1": "1",

            "XDG_MENU_PREFIX": "batocera-",
            "XDG_CONFIG_DIRS": "/etc/xdg",
            "XDG_CURRENT_DESKTOP": "XFCE",
            "DESKTOP_SESSION": "XFCE",
            "QT_FONT_DPI": "96",
            "QT_SCALE_FACTOR": "1",
            "GDK_SCALE": "1",

            "DOTNET_EnableAlternateStackCheck": "1",
            "XDG_CONFIG_HOME": "/userdata/system/configs",
            "XDG_CACHE_HOME": "/userdata/system/.cache",
        }

        # --- SDL joystick backend selection ---
        if is_steamdeck:
            # Steam Deck requires evdev (no HIDAPI)
            environment["SDL_JOYSTICK_HIDAPI"] = "0"
            environment["SDL_JOYSTICK_RAWINPUT"] = "0"
        else:
            # PCs, Ally, Legion Go, USB controllers
            environment["SDL_JOYSTICK_HIDAPI"] = "1"

        if rom == 'config':
            commandArray = ["/userdata/system/switch/appimages/ryujinx-emu.AppImage"]
        else:
            commandArray = ["/userdata/system/switch/appimages/ryujinx-emu.AppImage" , rom]

        writelog("Controller Config before Playing: {}".format(generate_sdl_game_controller_config(playersControllers)))

        return Command.Command(array=commandArray, env=environment)

    def writeRyujinxConfig(RyujinxConfigFile, RyujinxConfigFileBefore, RyujinxConfigTemplateFile, system, playersControllers):

        writelog(RyujinxConfigTemplateFile)

        data = {}

        if os.path.exists("/userdata/system/configs/Ryujinx/Config.json.template"):
            with open("/userdata/system/configs/Ryujinx/Config.json.template", "r+") as read_file:
                data = json.load(read_file)

        #if manual controller configuration, keep current config
        if system.isOptSet('ryu_auto_controller_config') and system.config["ryu_auto_controller_config"] == "0":
            if os.path.exists("/userdata/system/configs/Ryujinx/Config.json"):
                with open("/userdata/system/configs/Ryujinx/Config.json", "r+") as read_file:
                    current_data = json.load(read_file)
                    data['input_config'] = current_data['input_config']

        if system.isOptSet('res_scale'):
            data['res_scale'] = int(system.config["res_scale"])
        else:
            data['res_scale'] = 1

        if system.isOptSet('max_anisotropy'):
            data['max_anisotropy'] = int(system.config["max_anisotropy"])
        else:
            data['max_anisotropy'] = -1 

        if system.isOptSet('aspect_ratio'):
            data['aspect_ratio'] = system.config["aspect_ratio"]
        else:
            data['aspect_ratio'] = 'Fixed16x9'

        if system.isOptSet('system_language'):
            data['system_language'] = system.config["system_language"]
        else:
            data['system_language'] = 'AmericanEnglish'

        if system.isOptSet('system_region'):
            data['system_region'] = system.config["system_region"]
        else:
            data['system_region'] = 'USA'

        if system.isOptSet('ryu_docked_mode'):
            data['docked_mode'] = bool(int(system.config["ryu_docked_mode"]))
        else:
            data['docked_mode'] = bool(1)

        if system.isOptSet('ryu_enable_discord_integration'):
            data['enable_discord_integration'] = bool(int(system.config["ryu_enable_discord_integration"]))
        else:
            data['enable_discord_integration'] = bool(1)

        #V-Sync
        if system.isOptSet('ryu_vsync'):
            data['enable_vsync'] = bool(int(system.config["ryu_vsync"]))
        else:
            data['enable_vsync'] = bool(1)


        data['language_code'] = str(getLangFromEnvironment())
        data['game_dirs'] = ["/userdata/roms/switch"]

        if not system.isOptSet('ryu_auto_controller_config') or system.config["ryu_auto_controller_config"] != "0":
            debugcontrollers = True

            if debugcontrollers:
                writelog("=====================================================Start Bato Controller Debug Info=========================================================")
                for index, controller in enumerate(playersControllers, start=0):
                    writelog("Controller configName: {}".format(controller.name))
                    writelog("Controller index: {}".format(controller.index))
                    writelog("Controller real_name: {}".format(controller.real_name))
                    writelog("Controller device_path: {}".format(controller.device_path))
                    writelog("Controller player: {}".format(controller.player_number))
                    writelog("Controller GUID: {}".format(controller.guid))
                    writelog("")
                writelog("=====================================================End Bato Controller Debug Info===========================================================")
                writelog("")

            input_config = []
            index_of_convuuid = {}
            for index, controller in enumerate(playersControllers, start=0):
                if(controller.guid != "050000007e0500000620000001800000" and controller.guid != "050000007e0500000720000001800000"):

                    invert_buttons = None

                    myid = uuid.UUID(controller.guid)
                    myid.bytes_le
                    convuuid = uuid.UUID(bytes=myid.bytes_le)
                    if myid in index_of_convuuid:
                        index_of_convuuid[myid] = index_of_convuuid[myid] + 1
                    else:
                        index_of_convuuid[myid] = 0

                    controllernumber = str(controller.index)
                    #Map Keys and GUIDs
                    cvalue = {}

                    motion = {}
                    motion['motion_backend'] = "GamepadDriver"
                    motion['sensitivity'] = 100
                    motion['gyro_deadzone'] = 1
                    motion['enable_motion'] = bool(1)

                    rumble = {}
                    rumble['strong_rumble'] = 1
                    rumble['weak_rumble'] = 1
                    rumble['enable_rumble'] = bool(1)


                    which_pad = "p" + str(int(controller.player_number)) + "_pad"
                    if ((system.isOptSet(which_pad) and ((system.config[which_pad] == "ProController") or (system.config[which_pad] == "JoyconPair")) ) or not system.isOptSet(which_pad)):
                        left_joycon_stick = {}
                        left_joycon_stick['joystick'] = "Left"
                        left_joycon_stick['rotate90_cw'] = bool(0)
                        left_joycon_stick['invert_stick_x'] = bool(0)
                        left_joycon_stick['invert_stick_y'] = bool(0)
                        left_joycon_stick['stick_button'] = "LeftStick"

                        right_joycon_stick = {}
                        right_joycon_stick['joystick'] = "Right"
                        right_joycon_stick['rotate90_cw'] = bool(0)
                        right_joycon_stick['invert_stick_x'] = bool(0)
                        right_joycon_stick['invert_stick_y'] = bool(0)
                        right_joycon_stick['stick_button'] = "RightStick" 



                        left_joycon = {}
                        left_joycon['button_minus'] = "Back"
                        left_joycon['button_l'] = "LeftShoulder"
                        left_joycon['button_zl'] = "LeftTrigger"
                        left_joycon['button_sl'] = "Unbound"
                        left_joycon['button_sr'] = "Unbound"
                        left_joycon['dpad_up'] = "DpadUp"
                        left_joycon['dpad_down'] = "DpadDown"
                        left_joycon['dpad_left'] = "DpadLeft"
                        left_joycon['dpad_right'] = "DpadRight"


                        right_joycon = {}
                        right_joycon['button_plus'] = "Start"
                        right_joycon['button_r'] = "RightShoulder"
                        right_joycon['button_zr'] = "RightTrigger"
                        right_joycon['button_sl'] = "Unbound"
                        right_joycon['button_sr'] = "Unbound"

                        if invert_buttons:
                            right_joycon['button_x'] = "X"
                            right_joycon['button_b'] = "B"
                            right_joycon['button_y'] = "Y"
                            right_joycon['button_a'] = "A" 
                        else:
                            right_joycon['button_x'] = "Y"
                            right_joycon['button_b'] = "A"
                            right_joycon['button_y'] = "X"
                            right_joycon['button_a'] = "B" 

                        if system.isOptSet(which_pad):
                            cvalue['controller_type'] = system.config["p1_pad"]
                        else: 
                            cvalue['controller_type'] = "ProController"
                    elif (system.isOptSet(which_pad) and (system.config[which_pad] == "JoyconLeft")):
                        left_joycon_stick = {}
                        left_joycon_stick['joystick'] = "Left"
                        left_joycon_stick['rotate90_cw'] = bool(0)
                        left_joycon_stick['invert_stick_x'] = bool(0)
                        left_joycon_stick['invert_stick_y'] = bool(0)
                        left_joycon_stick['stick_button'] = "LeftStick"            

                        right_joycon_stick = {}
                        right_joycon_stick['joystick'] = "Unbound"
                        right_joycon_stick['rotate90_cw'] = bool(0)
                        right_joycon_stick['invert_stick_x'] = bool(0)
                        right_joycon_stick['invert_stick_y'] = bool(0)
                        right_joycon_stick['stick_button'] = "Unbound"

                        left_joycon = {}
                        left_joycon['button_minus'] = "Back"
                        left_joycon['button_l'] = "LeftShoulder"
                        left_joycon['button_zl'] = "LeftTrigger"
                        left_joycon['button_sl'] = "LeftShoulder"
                        left_joycon['button_sr'] = "RightShoulder"

                        left_joycon['dpad_up'] = "Y"
                        left_joycon['dpad_down'] = "A"
                        left_joycon['dpad_left'] = "X"
                        left_joycon['dpad_right'] = "B"                        

                        right_joycon = {}
                        right_joycon['button_plus'] = "Start"
                        right_joycon['button_r'] = "RightShoulder"
                        right_joycon['button_zr'] = "RightTrigger"
                        right_joycon['button_sl'] = "Unbound"
                        right_joycon['button_sr'] = "Unbound"

                        if invert_buttons:
                            right_joycon['button_x'] = "X"
                            right_joycon['button_b'] = "B"
                            right_joycon['button_y'] = "Y"
                            right_joycon['button_a'] = "A"                         
                        else:
                            right_joycon['button_x'] = "Y"
                            right_joycon['button_b'] = "A"
                            right_joycon['button_y'] = "X"
                            right_joycon['button_a'] = "B" 

                        cvalue['controller_type'] = "JoyconLeft"
                        
                    elif (system.isOptSet(which_pad) and (system.config[which_pad] == "JoyconRight")):
                        left_joycon_stick = {}
                        left_joycon_stick['joystick'] = "Unbound"
                        left_joycon_stick['rotate90_cw'] = bool(1)
                        left_joycon_stick['invert_stick_x'] = bool(1)
                        left_joycon_stick['invert_stick_y'] = bool(1)
                        left_joycon_stick['stick_button'] = "Unbound"           

                        right_joycon_stick = {}
                        right_joycon_stick['joystick'] = "Left"
                        right_joycon_stick['rotate90_cw'] = bool(0)
                        right_joycon_stick['invert_stick_x'] = bool(0)
                        right_joycon_stick['invert_stick_y'] = bool(0)
                        right_joycon_stick['stick_button'] = "LeftStick" 

                        left_joycon = {}
                        left_joycon['button_minus'] = "Back"
                        left_joycon['button_l'] = "LeftShoulder"
                        left_joycon['button_zl'] = "LeftTrigger"
                        left_joycon['button_sl'] = "Unbound"
                        left_joycon['button_sr'] = "Unbound"

                        left_joycon['dpad_up'] = "DpadUp"
                        left_joycon['dpad_down'] = "DpadDown"
                        left_joycon['dpad_left'] = "DpadLeft"
                        left_joycon['dpad_right'] = "DpadRight"

                        right_joycon = {}
                        right_joycon['button_plus'] = "Start"
                        right_joycon['button_r'] = "RightShoulder"
                        right_joycon['button_zr'] = "RightTrigger"
                        right_joycon['button_sl'] = "LeftShoulder"
                        right_joycon['button_sr'] = "RightShoulder"

                        if invert_buttons:
                            right_joycon['button_x'] = "A"
                            right_joycon['button_b'] = "Y"
                            right_joycon['button_y'] = "X"
                            right_joycon['button_a'] = "B" 
                        else:
                            right_joycon['button_x'] = "B"
                            right_joycon['button_b'] = "X"
                            right_joycon['button_y'] = "Y"
                            right_joycon['button_a'] = "A"                         
                        cvalue['controller_type'] = "JoyconRight"
                    else:
                        #Handle old settings that don't match above
                        left_joycon_stick = {}
                        left_joycon_stick['joystick'] = "Left"
                        left_joycon_stick['rotate90_cw'] = bool(0)
                        left_joycon_stick['invert_stick_x'] = bool(0)
                        left_joycon_stick['invert_stick_y'] = bool(0)
                        left_joycon_stick['stick_button'] = "LeftStick"            

                        right_joycon_stick = {}
                        right_joycon_stick['joystick'] = "Right"
                        right_joycon_stick['rotate90_cw'] = bool(0)
                        right_joycon_stick['invert_stick_x'] = bool(0)
                        right_joycon_stick['invert_stick_y'] = bool(0)
                        right_joycon_stick['stick_button'] = "RightStick" 



                        left_joycon = {}
                        left_joycon['button_minus'] = "Back"
                        left_joycon['button_l'] = "LeftShoulder"
                        left_joycon['button_zl'] = "LeftTrigger"
                        left_joycon['button_sl'] = "Unbound"
                        left_joycon['button_sr'] = "Unbound"
                        left_joycon['dpad_up'] = "DpadUp"
                        left_joycon['dpad_down'] = "DpadDown"
                        left_joycon['dpad_left'] = "DpadLeft"
                        left_joycon['dpad_right'] = "DpadRight"


                        right_joycon = {}
                        right_joycon['button_plus'] = "Start"
                        right_joycon['button_r'] = "RightShoulder"
                        right_joycon['button_zr'] = "RightTrigger"
                        right_joycon['button_sl'] = "Unbound"
                        right_joycon['button_sr'] = "Unbound"

                        if invert_buttons:
                            right_joycon['button_x'] = "X"
                            right_joycon['button_b'] = "B"
                            right_joycon['button_y'] = "Y"
                            right_joycon['button_a'] = "A" 
                        else:
                            right_joycon['button_x'] = "Y"
                            right_joycon['button_b'] = "A"
                            right_joycon['button_y'] = "X"
                            right_joycon['button_a'] = "B" 

                        cvalue['controller_type'] = "ProController"

                    cvalue['left_joycon_stick'] = left_joycon_stick          
                    cvalue['right_joycon_stick'] = right_joycon_stick
                    cvalue['deadzone_left'] = 0.1           
                    cvalue['deadzone_right'] = 0.1 
                    cvalue['range_left'] = 1          
                    cvalue['range_right'] = 1 
                    cvalue['trigger_threshold'] = 0.5  
                    cvalue['motion'] = motion
                    cvalue['rumble'] = rumble
                    cvalue['led'] = {}
                    cvalue['led']['enable_led'] = False
                    cvalue['led']['turn_off_led'] = False
                    cvalue['led']['use_rainbow'] = False
                    cvalue['led']['led_color'] = 0
                    cvalue['left_joycon'] = left_joycon
                    cvalue['right_joycon'] = right_joycon

                    cvalue['version'] = 1
                    cvalue['backend'] = "GamepadSDL2"
                    cvalue['id'] = str(index_of_convuuid[myid]) + '-' + str(convuuid)
              
                    cvalue['player_index'] = "Player" +  str(int(controller.player_number))
                    input_config.append(cvalue)
            
            data['input_config'] = input_config

        #Resolution Scale
        if system.isOptSet('ryu_resolution_scale'):
            if system.config["ryu_resolution_scale"] in {'1.0', '2.0', '3.0', '4.0', 1.0, 2.0, 3.0, 4.0}:
                data['res_scale_custom'] = 1
                if system.config["ryu_resolution_scale"] in {'1.0', 1.0}:
                    data['res_scale'] = 1
                if system.config["ryu_resolution_scale"] in {'2.0', 2.0}:
                    data['res_scale'] = 2
                if system.config["ryu_resolution_scale"] in {'3.0', 3.0}:
                    data['res_scale'] = 3
                if system.config["ryu_resolution_scale"] in {'4.0', 4.0}:
                    data['res_scale'] = 4
            else:
                data['res_scale_custom'] = float(system.config["ryu_resolution_scale"])
                data['res_scale'] = -1
        else:
            data['res_scale_custom'] = 1
            data['res_scale'] = 1

        #Texture Recompression
        if system.isOptSet('ryu_texture_recompression'):
            if system.config["ryu_texture_recompression"] in {"true", "1", 1}:
                data['enable_texture_recompression'] = True
            elif system.config["ryu_texture_recompression"] in {"false", "0", 0}:
                data['enable_texture_recompression'] = False
        else:
            data['enable_texture_recompression'] = False

        dri_path = getCurrentCard()

        with open(dri_path + '/device/vendor', "r") as vendor_file:
            vendor_id = vendor_file.read().strip().upper().replace("0X","0x")

        with open(dri_path + '/device/device', "r") as device_file:
            device_id = device_file.read().strip().upper().replace("0X","0x")

        data['preferred_gpu'] = vendor_id + '_' + device_id

        with open(RyujinxConfigFile, "w") as outfile:
            outfile.write(json.dumps(data, indent=2))

        #just to be able to do diff to be sure than the emu is not changing values
        with open(RyujinxConfigFileBefore, "w") as outfile:
            outfile.write(json.dumps(data, indent=2))

def getLangFromEnvironment():
    lang = os.environ['LANG'][:5]
    availableLanguages = [ "en_US", "pt_BR", "es_ES", "fr_FR", "de_DE","it_IT", "el_GR", "tr_TR", "zh_CN"]
    if lang in availableLanguages:
        return lang
    else:
        return "en_US"

def writelog(log):
#    return
    f = open("/tmp/debugryujinx.txt", "a")
    f.write(log+"\n")
    f.close()
