from __future__ import annotations

import filecmp
import logging
import glob
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
try:
    from configgen.utils.configparser import CaseSensitiveRawConfigParser
except ImportError:
    from batocera_common.configparser import CaseSensitiveRawConfigParser
from configgen.input import Input, InputDict, InputMapping

os.environ["PYSDL2_DLL_PATH"] = "/userdata/system/switch/configgen/sdl2/"
os.environ["PATH"] = "/userdata/system/switch/extra/xdgfix:" + os.environ.get("PATH", "")

import sdl2
from sdl2 import joystick
from ctypes import create_string_buffer

eslog = logging.getLogger(__name__)

if TYPE_CHECKING:
    from configgen.types import HotkeysContext

subprocess.run(["batocera-mouse", "show"], check=False)

try:
    # exécute le script et attend la fin
    subprocess.Popen(["/userdata/system/switch/configgen/generators/ryujinxloadfirmware.sh"], stderr=subprocess.PIPE, shell=True)
    print("[RYUJINX] Script Bash exécuté avec succès", file=sys.stderr)
except subprocess.CalledProcessError as e:
    print("[RYUJINX][ERROR] Le script Bash a échoué :", file=sys.stderr)

def getCurrentCard() -> str | None:
    proc = subprocess.Popen(["/userdata/system/switch/configgen/generators/detectvideo.sh"], stdout=subprocess.PIPE, shell=True)
    (out, err) = proc.communicate()
    for val in out.decode().splitlines():
        return val # return the first line

def ensure_symlink(target, link_path):
    if os.path.exists(link_path):
        if not os.path.islink(link_path):
            shutil.rmtree(link_path)
            os.symlink(target, link_path)
        else:
            if os.readlink(link_path) != target:
                os.unlink(link_path)
                os.symlink(target, link_path)
    else:
        os.symlink(target, link_path)
def sdlmapping_to_controller(mapping, guid):

    sdl_to_batoinputmapping = {
        'a': 'b',
        'b': 'a',
        'y': 'x',
        'x': 'y',
        'lefttrigger': 'l2',
        'righttrigger': 'r2',
        'leftstick': 'l3',
        'rightstick': 'r3',
        'leftshoulder': 'pageup',
        'rightshoulder': 'pagedown',
        'start': 'start',
        'back': 'select',
        'dpup': 'up',
        'dpdown': 'down',
        'dpleft': 'left',
        'dpright': 'right',
        'lefty': 'joystick1up',
        'leftx': 'joystick1left',
        'righty': 'joystick2up',
        'rightx': 'joystick2left',
        'guide':  'hotkey'
    }


    elements = mapping.split(',')

    current_controller = {
        "guid": guid,
        "mapping": mapping,
        "platform": "",
        "inputs": {}
    }

    for element in elements[2:]:
        if not element:
            continue

        if element.startswith('platform:'):
            current_controller["platform"] = element[9:]  # Extraire après "platform:"
        elif ':' in element:
            logical_name, physical_mapping = element.split(':', 1)

            input_type = "unknown"
            clean_value = physical_mapping  # Valeur par défaut

            if physical_mapping.startswith('b'):
                input_type = "button"
                clean_value = physical_mapping[1:]  # Enlever le 'b'
            elif physical_mapping.startswith('a'):
                input_type = "axis"
                clean_value = physical_mapping[1:]  # Enlever le 'a'
            elif physical_mapping.startswith('h'):
                input_type = "hat"
                # Pour les hats, on conserve la partie après le 'h' qui contient des informations importantes
                clean_value = physical_mapping[1:]  # Enlever le 'h'
                clean_value_mask, clean_value = clean_value.split('.')

            if logical_name in sdl_to_batoinputmapping:
                logical_name = sdl_to_batoinputmapping[logical_name]

            input = Input(name=logical_name, type=input_type, id=clean_value, value=1, code=0 )
            current_controller["inputs"][logical_name] = input

    return current_controller


def evdev_to_hidraw():

    evdev_hidraw = {}

    for hid_path in glob.glob('/sys/class/hidraw/hidraw*'):
        # Obtenir le chemin du périphérique
        hid_dev = os.path.realpath(os.path.join(hid_path, "device"))

        events = []
        for root, dirs, files in os.walk(hid_dev):
            for dir in dirs:
                if dir.startswith("event"):
                    event_path = os.path.join(root, dir)
                    if "/input" in event_path and "/event" in event_path:
                        events.append(event_path)

        if events:
            for ev in events:
                ev_name = os.path.basename(ev)
                hid_name = os.path.basename(hid_path)
                evdev_hidraw[f"/dev/input/{ev_name}"] = f"/dev/{hid_name}"
    return evdev_hidraw

def detect_bus_from_hidraw(hidraw_path: str):
    # pass /dev/hidrawx
    hidraw_device = os.path.basename(hidraw_path)
    sysfs_path = f"/sys/class/hidraw/{hidraw_device}/device"

    if not os.path.exists(sysfs_path):
        return f"Device {hidraw_device} not found in sysfs"

    # Resolve the real path (follows symlinks)
    try:
        real_device_path = os.path.realpath(sysfs_path)
        bus_prefix = os.path.basename(real_device_path).split(":")[0]
    except Exception as e:
        return f"Error reading device path: {e}"

    return bus_prefix[2:]

def list_sdl_gamepads(sdlversion):

    os.environ["SDL_JOYSTICK_HIDAPI"] = "1"
    os.environ["SDL_JOYSTICK_HIDAPI_PS4"] = "0"
    os.environ["SDL_JOYSTICK_HIDAPI_PS5"] = "0"
    os.environ["SDL_JOYSTICK_HIDAPI_SWITCH"] = "0"
    os.environ["SDL_JOYSTICK_HIDAPI_XBOX"] = "0"
    os.environ["SDL_JOYSTICK_HIDAPI_STEAMDECK"] = "0"  #reported by foclabroc, not tested myself yet
    os.environ["SDL_GAMECONTROLLERCONFIG_FILE"] = "/userdata/system/switch/configgen/gamecontrollerdb.txt"

    sdl2.SDL_ClearError()
    try:
      ret = sdl2.SDL_Init(sdl2.SDL_INIT_GAMECONTROLLER)
    except:
      print("An exception occurred")

    count = joystick.SDL_NumJoysticks()

    sdl_devices = {}

    for i in range(count):
        if sdl2.SDL_IsGameController(i) == 1:
            pad = sdl2.SDL_GameControllerOpen(i)
            path = sdl2.SDL_GameControllerPath(pad)

            joy_guid = joystick.SDL_JoystickGetDeviceGUID(i)
            buff = create_string_buffer(33)
            joystick.SDL_JoystickGetGUIDString(joy_guid,buff,33)
            buff[2] = b'0'
            buff[3] = b'0'
            buff[4] = b'0'
            buff[5] = b'0'
            buff[6] = b'0'
            buff[7] = b'0'
            guidstring = ((bytes(buff)).decode()).split('\x00',1)[0]
            joy_path = joystick.SDL_JoystickPathForIndex(i).decode()

            #sdl3 have implemented bus type in hidraw guid, we still use old sdl2 for this script
            if 'hidraw' in joy_path and sdlversion == 3:
                bustype = detect_bus_from_hidraw(joy_path)
                guidstring = bustype + guidstring[2:]

            mapping = sdl2.SDL_GameControllerMapping(pad);
            import pprint
            pprint.pprint(mapping)
            eslog.debug(str(mapping))
            controller = sdlmapping_to_controller(str(mapping), guidstring)

            sdl_devices[joy_path] = controller

    sdl2.SDL_Quit()

    return sdl_devices
class RyujinxGenerator(Generator):

    def getHotkeysContext(self) -> HotkeysContext:
        return {
            "name": "ryujinx-emu",
            "keys": { "menu": "KEY_F4"}
        }

    def generate(self, system, rom, playersControllers, metadata, guns, wheels, gameResolution):

        ryujinx_appimage = "/userdata/system/switch/appimages/ryujinx-emu.AppImage"
        ryujinx_extracted = "/userdata/system/switch/appimages/ryujinx-extracted/usr/bin/Ryujinx"
        ryujinx_extracted_dir = "/userdata/system/switch/appimages/ryujinx-extracted"
        ryujinx_wrapper = "/userdata/system/switch/extra/ryu_wrapper"
        ryujinx_libs = "/userdata/system/switch/appimages/ryujinx-extracted/usr/lib"

        # Si un AppImage est présent, l'extraire automatiquement
        if os.path.exists(ryujinx_appimage):
            st = os.stat(ryujinx_appimage)
            os.chmod(ryujinx_appimage, st.st_mode | stat.S_IEXEC)
            if os.path.exists(ryujinx_extracted_dir):
                shutil.rmtree(ryujinx_extracted_dir)
            subprocess.run(
                [ryujinx_appimage, "--appimage-extract"],
                cwd="/userdata/system/switch/appimages",
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            squashfs = "/userdata/system/switch/appimages/squashfs-root"
            if os.path.isdir(squashfs + "/usr/bin"):
                os.rename(squashfs, ryujinx_extracted_dir)
                os.remove(ryujinx_appimage)
                writelog("AppImage extrait et supprimé automatiquement")
            else:
                writelog("WARN: extraction AppImage échouée")

        st = os.stat(ryujinx_extracted)
        os.chmod(ryujinx_extracted, st.st_mode | stat.S_IEXEC)
        st = os.stat(ryujinx_wrapper)
        os.chmod(ryujinx_wrapper, st.st_mode | stat.S_IEXEC)
        st = os.stat("/userdata/system/switch/configgen/generators/detectvideo.sh")
        os.chmod("/userdata/system/switch/configgen/generators/detectvideo.sh", st.st_mode | stat.S_IEXEC)

        mkdir_if_not_exists(Path("/userdata/system/configs/Ryujinx"))
        # mkdir_if_not_exists(Path("/userdata/system/configs/Ryujinx/system"))

        template = Path("/userdata/system/switch/configgen/Config.json.template")
        target = CONFIGS / "Ryujinx" / "Config.json.template"
        copyfile(template, target) 

    #Create Folder
        mkdir_if_not_exists(Path("/userdata/system/configs/Ryujinx/mods"))
        mkdir_if_not_exists(Path("/userdata/system/configs/Ryujinx/bis"))
        mkdir_if_not_exists(Path("/userdata/system/configs/Ryujinx/bis/system"))
        mkdir_if_not_exists(Path("/userdata/system/configs/Ryujinx/bis/system/save"))
        mkdir_if_not_exists(Path("/userdata/system/configs/Ryujinx/bis/system/Contents"))
        mkdir_if_not_exists(Path("/userdata/system/configs/Ryujinx/bis/user"))
        mkdir_if_not_exists(Path("/userdata/saves/switch"))
        mkdir_if_not_exists(Path("/userdata/saves/switch/ryujinx"))
        mkdir_if_not_exists(Path("/userdata/saves/switch/ryujinx/save"))
        mkdir_if_not_exists(Path("/userdata/saves/switch/ryujinx/save/save_user"))
        mkdir_if_not_exists(Path("/userdata/saves/switch/ryujinx/save/save_system"))
        mkdir_if_not_exists(Path("/userdata/saves/switch/ryujinx/mods"))

        # Ryujinx User XDG 
        if os.path.exists("/userdata/system/switch/extra/xdgfix/xdg-open"):
            st = os.stat("/userdata/system/switch/extra/xdgfix/xdg-open")
            os.chmod("/userdata/system/switch/extra/xdgfix/xdg-open", st.st_mode | stat.S_IEXEC)

    # #Link Ryujinx key folder
        # #KEY-------
        # if os.path.exists("/userdata/system/configs/Ryujinx/system"):
            # if not os.path.islink("/userdata/system/configs/Ryujinx/system"):
                # shutil.rmtree("/userdata/system/configs/Ryujinx/system")
                # os.symlink("/userdata/bios/switch/keys", "/userdata/system/configs/Ryujinx/system")
            # else:
                # current_target = os.readlink("/userdata/system/configs/Ryujinx/system")
                # if current_target != "/userdata/bios/switch/keys":
                    # os.unlink("/userdata/bios/switch/keys")
                    # os.symlink("/userdata/bios/switch/keys", "/userdata/system/configs/Ryujinx/system")
        # else:
            # os.symlink("/userdata/bios/switch/keys", "/userdata/system/configs/Ryujinx/system")

    #Link Ryujinx User save/mods folder (bis/user)/(bis/system/save)
        # #USER SAVE (bis/user)-------
        if os.path.exists("/userdata/system/configs/Ryujinx/bis/user"):
            if not os.path.islink("/userdata/system/configs/Ryujinx/bis/user"):
                shutil.rmtree("/userdata/system/configs/Ryujinx/bis/user")
                os.symlink("/userdata/saves/switch/ryujinx/save/save_user", "/userdata/system/configs/Ryujinx/bis/user")
            else:
                current_target = os.readlink("/userdata/system/configs/Ryujinx/bis/user")
                if current_target != "/userdata/saves/switch/ryujinx/save/save_user":
                    os.unlink("/userdata/saves/switch/ryujinx/save/save_user")
                    os.symlink("/userdata/saves/switch/ryujinx/save/save_user", "/userdata/system/configs/Ryujinx/bis/user")
        else:
            os.symlink("/userdata/saves/switch/ryujinx/save/save_user", "/userdata/system/configs/Ryujinx/bis/user")

        # #USER SAVE (bis/system/save)-------
        if os.path.exists("/userdata/system/configs/Ryujinx/bis/system/save"):
            if not os.path.islink("/userdata/system/configs/Ryujinx/bis/system/save"):
                shutil.rmtree("/userdata/system/configs/Ryujinx/bis/system/save")
                os.symlink("/userdata/saves/switch/ryujinx/save/save_system", "/userdata/system/configs/Ryujinx/bis/system/save")
            else:
                current_target = os.readlink("/userdata/system/configs/Ryujinx/bis/system/save")
                if current_target != "/userdata/saves/switch/ryujinx/save/save_system":
                    os.unlink("/userdata/saves/switch/ryujinx/save/save_system")
                    os.symlink("/userdata/saves/switch/ryujinx/save/save_system", "/userdata/system/configs/Ryujinx/bis/system/save")
        else:
            os.symlink("/userdata/saves/switch/ryujinx/save/save_system", "/userdata/system/configs/Ryujinx/bis/system/save")

        # #USER MODS (Ryujinx/mods)-------
        if os.path.exists("/userdata/system/configs/Ryujinx/mods"):
            if not os.path.islink("/userdata/system/configs/Ryujinx/mods"):
                shutil.rmtree("/userdata/system/configs/Ryujinx/mods")
                os.symlink("/userdata/saves/switch/ryujinx/mods", "/userdata/system/configs/Ryujinx/mods")
            else:
                current_target = os.readlink("/userdata/system/configs/Ryujinx/mods")
                if current_target != "/userdata/saves/switch/ryujinx/mods":
                    os.unlink("/userdata/saves/switch/ryujinx/mods")
                    os.symlink("/userdata/saves/switch/ryujinx/mods", "/userdata/system/configs/Ryujinx/mods")
        else:
            os.symlink("/userdata/saves/switch/ryujinx/mods", "/userdata/system/configs/Ryujinx/mods")

        RyujinxConfig = Path('/userdata/system/configs/Ryujinx/Config.json')
        RyujinxConfigTemplate = str(CONFIGS) + '/Ryujinx/Config.json.template'
        RyujinxHome = CONFIGS

        RyujinxConfigFileBefore = str(CONFIGS) + '/Ryujinx/Config.json.before'

        RyujinxRegisteredBios = Path('/userdata/system/configs/Ryujinx/bis/system/Contents/registered')

        writelog("Controller mapping before: {}".format(generate_sdl_game_controller_config(playersControllers)))

        #Configuration update
        sdl_mapping = RyujinxGenerator.writeRyujinxConfig(str(CONFIGS) + '/Ryujinx/Config.json', RyujinxConfigFileBefore, RyujinxConfigTemplate, system, playersControllers)

        writelog("Controller mapping after: {}".format(str(sdl_mapping)))

        environment = { 
                        "LD_LIBRARY_PATH": "/userdata/system/switch/appimages/ryujinx-extracted/usr/lib",
                        "SDL_JOYSTICK_HIDAPI": "1",
                        "SDL_JOYSTICK_HIDAPI_XBOX": "0",
                        "SDL_JOYSTICK_HIDAPI_STEAMDECK" : "0",
                        "SDL_JOYSTICK_HIDAPI_PS4" : "0",
                        "SDL_JOYSTICK_HIDAPI_PS5" : "0",
                        "SDL_JOYSTICK_HIDAPI_SWITCH" : "0",
                        "SDL_GAMECONTROLLERCONFIG": sdl_mapping,
                        "DRI_PRIME":"1",
                        "AMD_VULKAN_ICD":"RADV",
                        "DISABLE_LAYER_AMD_SWITCHABLE_GRAPHICS_1":"1",
                        "XDG_MENU_PREFIX":"batocera-",
                        "XDG_CONFIG_DIRS":"/etc/xdg",
                        "XDG_CURRENT_DESKTOP":"XFCE",
                        "DESKTOP_SESSION":"XFCE",
                        "QT_FONT_DPI":"96",
                        "QT_SCALE_FACTOR":"1",
                        "GDK_SCALE":"1",
                        "DOTNET_EnableAlternateStackCheck":"1",
                        "XDG_CONFIG_HOME":"/userdata/system/configs",
                        "XDG_DATA_HOME":"/userdata/system/configs",
                        "XDG_CACHE_HOME":"/userdata/system/.cache",
        }

        rom_nameq = os.path.basename(rom)
        if rom_nameq == 'ryujinx_config.xci_config':
            commandArray = [ryujinx_wrapper, ryujinx_extracted]
        else:
            commandArray = [ryujinx_wrapper, ryujinx_extracted, rom]

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

        #V-Sync
        if system.isOptSet('ryu_vsync'):
            data['enable_vsync'] = bool(int(system.config["ryu_vsync"]))
        else:
            data['enable_vsync'] = bool(1)

        if system.isOptSet('ryu_backend'):
            data['graphics_backend'] = system.config["ryu_backend"]
        else:
            data['graphics_backend'] = 'Vulkan'

        if system.isOptSet('ryu_audio_backend'):
            data['audio_backend'] = system.config["ryu_audio_backend"]
        else:
            data['audio_backend'] = 'OpenAl'

        # # Fullscreen mode
        # if system.isOptSet('fullscreen_mode'):
            # data['fullscreen_mode'] = bool(int(system.config["fullscreen_mode"]))
        # else:
            # data['fullscreen_mode'] = bool(1)

        # # Hide Cursor Mouse
        # data['hide_cursor'] = bool(2)
        data['language_code'] = str(getLangFromEnvironment())
        data['game_dirs'] = ["/userdata/roms/switch"]

        sdl_mapping = generate_sdl_game_controller_config(playersControllers)

        if not system.isOptSet('ryu_auto_controller_config') or system.config["ryu_auto_controller_config"] != "0":
            debugcontrollers = True
            sdl_mapping = ""

            #get the evdev->hidraw mapping
            evdev_hidraw = evdev_to_hidraw()
            #get sdllib  hidapi/hidraw + evdev guid
            sdl_gamepads = list_sdl_gamepads(2)            

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
                    NINTENDO_GUIDS = {
                        "050000007e0500000620000001800000",
                        "050000007e0500000720000001800000",
                        "050000007e0500000920000001800000",
                    }

                    invert_buttons = controller.guid in NINTENDO_GUIDS

                    #if hidraw exist, replace the guid and use the provided mapping
                    hidraw_path = None
                    if controller.device_path in evdev_hidraw:
                        hidraw_path = evdev_hidraw[controller.device_path]

                    if hidraw_path and hidraw_path in sdl_gamepads:
                        writelog("sdlmapping: hidraw")
                        controller.guid = sdl_gamepads[hidraw_path]['guid']
                        sdl_mapping += sdl_gamepads[hidraw_path]['mapping']
                    #try to get to mapping from the yuzu libsdl
                    elif controller.device_path in sdl_gamepads:
                        writelog("sdlmapping: native libsdl mapping")
                        sdl_mapping += sdl_gamepads[controller.device_path]['mapping']
                    else:
                        #fallback to inputs from ES
                        writelog("sdlmapping: fallback to ES")
                        sdl_mapping +=controller.generate_sdl_game_db_line()
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

                    #invert based on "Nintendo", like Ryujinx code
                    ryu_inverse_button = system.config.get('ryu_inverse_button', 'false').lower() == 'true'

                    if controller.real_name and "Nintendo" in controller.real_name:
                        right_joycon['button_x'] = "X"
                        right_joycon['button_b'] = "B"
                        right_joycon['button_y'] = "Y"
                        right_joycon['button_a'] = "A" 
                    elif ryu_inverse_button:
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

        # dri_path = getCurrentCard()

        # with open(dri_path + '/device/vendor', "r") as vendor_file:
            # vendor_id = vendor_file.read().strip().upper().replace("0X","0x")

        # with open(dri_path + '/device/device', "r") as device_file:
            # device_id = device_file.read().strip().upper().replace("0X","0x")

        # data['preferred_gpu'] = vendor_id + '_' + device_id

        with open(RyujinxConfigFile, "w") as outfile:
            outfile.write(json.dumps(data, indent=2))

        #just to be able to do diff to be sure than the emu is not changing values
        with open(RyujinxConfigFileBefore, "w") as outfile:
            outfile.write(json.dumps(data, indent=2))

        return sdl_mapping
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
