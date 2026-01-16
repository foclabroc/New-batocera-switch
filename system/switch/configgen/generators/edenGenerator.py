from __future__ import annotations

import filecmp
import logging
import os
from os import environ
import re
import shutil
import subprocess
import sys
import json
import stat
import glob
import pathlib

from shutil import copyfile
from pathlib import Path
from typing import TYPE_CHECKING
from configgen.utils import vulkan
from configgen import Command as Command
from configgen.batoceraPaths import CONFIGS, HOME, ROMS, SAVES, mkdir_if_not_exists
from configgen.controller import generate_sdl_game_controller_config
from configgen.generators.Generator import Generator
from configgen.utils.configparser import CaseSensitiveRawConfigParser
from configgen.input import Input, InputDict, InputMapping
from datetime import datetime
from evdev import InputDevice, ecodes

os.environ["PYSDL2_DLL_PATH"] = "/userdata/system/switch/configgen/sdl2/"

import sdl2
from sdl2 import joystick
from ctypes import create_string_buffer

eslog = logging.getLogger(__name__)

if TYPE_CHECKING:
    from configgen.types import HotkeysContext

class DictToObject:
    def __init__(self, dictionary):
        for key, value in dictionary.items():
            if isinstance(value, dict):
                value = DictToObject(value)
            setattr(self, key, value)

def switch_log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"{ts} [SWITCH-DEBUG] {msg}", flush=True)

def log_stderr(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"{ts} [SWITCH-DEBUG] {msg}", file=sys.stdout)	
###START PAD DETECTION--SEE-ES_LAUNCH_STDOUT.LOG#######################################################################
#######################################################################################################################
def hidraw_get_guid(devpath):
    try:
        vid = pid = None
        p = devpath
        while p != "/" and p:
            if os.path.exists(os.path.join(p, "idVendor")):
                with open(os.path.join(p, "idVendor")) as f:
                    vid = f.read().strip()
                with open(os.path.join(p, "idProduct")) as f:
                    pid = f.read().strip()
                break
            p = os.path.dirname(p)
        if not vid or not pid:
            return "00000000000000000000000000000000"
        return f"{vid}{pid}000000000000000000000000"
    except:
        return "00000000000000000000000000000000"
def list_hidraw_devices():
    devices = []
    for h in glob.glob("/sys/class/hidraw/hidraw*"):
        dev = os.path.basename(h)
        devpath = os.path.realpath(os.path.join(h, "device"))
        # Nom humain
        name = "unknown"
        try:
            with open(os.path.join(devpath, "uevent")) as f:
                for line in f:
                    if line.startswith("HID_NAME="):
                        name = line.strip().split("=",1)[1]
        except:
            pass
        # Bus USB / Bluetooth
        bus = os.path.basename(devpath).split(":")[0]
        guid = hidraw_get_guid(devpath)
        devices.append({
            "hidraw": f"/dev/{dev}",
            "name": name,
            "bus": bus,
            "guid": guid
        })
    return devices
def map_hidraw_to_evdev():
    mapping = {}
    for h in glob.glob("/sys/class/hidraw/hidraw*"):
        hid = os.path.basename(h)
        devpath = os.path.realpath(os.path.join(h, "device"))
        for root, dirs, files in os.walk(devpath):
            for d in dirs:
                if d.startswith("event"):
                    mapping[f"/dev/{hid}"] = f"/dev/input/{d}"
    return mapping
hidraws = list_hidraw_devices()
hidmap = map_hidraw_to_evdev()
for d in hidraws:
    hid = d["hidraw"]
    ev = hidmap.get(hid, "no evdev")

    switch_log(f"[HID] {d['name']}")
    switch_log(f"  hidraw = {hid}")
    switch_log(f"  evdev  = {ev}")
    #switch_log(f"  bus    = {d['bus']}")
    switch_log(f"  guid   = {d['guid']}")
###END PAD DETECTION--SEE-ES_LAUNCH_STDOUT.LOG#########################################################################
#######################################################################################################################

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
    os.environ["SDL_JOYSTICK_HIDAPI_XBOX"] = "0"
    os.environ["SDL_JOYSTICK_HIDAPI_XBOX_ONE"] = "0"
    os.environ["SDL_JOYSTICK_HIDAPI_SWITCH"] = "0"
    os.environ["SDL_JOYSTICK_HIDAPI_STEAMDECK"] = "0"
    os.environ["SDL_JOYSTICK_HIDAPI_PS4"] = "0"
    os.environ["SDL_JOYSTICK_HIDAPI_PS5"] = "0"

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

class EdenGenerator(Generator):

    def getHotkeysContext(self) -> HotkeysContext:
        return {
            "name": "switch-emu",
            "keys": { "exit": ["KEY_LEFTALT", "KEY_F4"]}
        }

    def executionDirectory(self, config, rom):
        return "/userdata/system/switch/appimages"

    def generate(self, system, rom, playersControllers, metadata, guns, wheels, gameResolution):

        emulator = system.config['emulator']

        if emulator == 'citron-emu':
            emudir = 'citron'
        elif emulator == 'eden-pgo':
            emudir = 'eden'
        elif emulator == 'eden-emu':
            emudir = 'eden'
        else:
            emudir = emulator

        sdlversion = 2
        if emulator == 'citron-emu':
            sdlversion = 3

        #handles chmod so you just need to download yuzu.AppImage
        st = os.stat("/userdata/system/switch/appimages/"+emulator+".AppImage")
        os.chmod("/userdata/system/switch/appimages/"+emulator+".AppImage", st.st_mode | stat.S_IEXEC)

        #Create Keys/Firmware Folder
        mkdir_if_not_exists(Path("/userdata/bios/switch"))
        mkdir_if_not_exists(Path("/userdata/bios/switch/keys"))
        mkdir_if_not_exists(Path("/userdata/bios/switch/firmware"))
        mkdir_if_not_exists(Path("/userdata/system/configs/yuzu"))
        mkdir_if_not_exists(Path("/userdata/system/configs/yuzu/nand"))
        mkdir_if_not_exists(Path("/userdata/system/configs/yuzu/nand/system"))
        mkdir_if_not_exists(Path("/userdata/system/configs/yuzu/nand/system/Contents"))

        #Link Yuzu firmware/key folder
        #KEY-------
        if os.path.exists("/userdata/system/configs/yuzu/keys"):
            if not os.path.islink("/userdata/system/configs/yuzu/keys"):
                shutil.rmtree("/userdata/system/configs/yuzu/keys")
                os.symlink("/userdata/bios/switch/keys", "/userdata/system/configs/yuzu/keys")
            else:
                current_target = os.readlink("/userdata/system/configs/yuzu/keys")
                if current_target != "/userdata/bios/switch/keys":
                    os.unlink("/userdata/system/configs/yuzu/keys")
                    os.symlink("/userdata/bios/switch/keys", "/userdata/system/configs/yuzu/keys")
        else:
            os.symlink("/userdata/bios/switch/keys", "/userdata/system/configs/yuzu/keys")
        #FIRMWARE-------
        if os.path.exists("/userdata/system/configs/yuzu/nand/system/Contents/registered"):
            if not os.path.islink("/userdata/system/configs/yuzu/nand/system/Contents/registered"):
                shutil.rmtree("/userdata/system/configs/yuzu/nand/system/Contents/registered")
                os.symlink("/userdata/bios/switch/firmware", "/userdata/system/configs/yuzu/nand/system/Contents/registered")
            else:
                current_target = os.readlink("/userdata/system/configs/yuzu/nand/system/Contents/registered")
                if current_target != "/userdata/bios/switch/firmware":
                    os.unlink("/userdata/system/configs/yuzu/nand/system/Contents/registered")
                    os.symlink("/userdata/bios/switch/firmware", "/userdata/system/configs/yuzu/nand/system/Contents/registered")
        else:
            os.symlink("/userdata/bios/switch/firmware", "/userdata/system/configs/yuzu/nand/system/Contents/registered")

        #Link Yuzu App Directory to /system/configs/yuzu
        mkdir_if_not_exists(Path("/userdata/system/.local"))
        mkdir_if_not_exists(Path("/userdata/system/.local/share"))

        #Remove .local/share/yuzu if it exists and isnt' a link
        if os.path.exists("/userdata/system/.local/share/"+emudir):
            if not os.path.islink("/userdata/system/.local/share/"+emudir):
                shutil.rmtree("/userdata/system/.local/share/"+emudir)

        if not os.path.exists("/userdata/system/.local/share/"+emudir):
            st = os.symlink("/userdata/system/configs/yuzu","/userdata/system/.local/share/"+emudir)

        #Link Yuzu Config Directory to /system/configs/yuzu
        mkdir_if_not_exists(Path("/userdata/system/.config"))

        #Remove .config/yuzu if it exists and isnt' a link
        if os.path.exists("/userdata/system/.config/"+emudir):
            if not os.path.islink("/userdata/system/.config/"+emudir):
                shutil.rmtree("/userdata/system/.config/"+emudir)

        if not os.path.exists("/userdata/system/.config/"+emudir):
            st = os.symlink("/userdata/system/configs/yuzu","/userdata/system/.config/"+emudir)

        #Remove configs/emu if it exists and isnt' a link
        if os.path.exists("/userdata/system/configs/"+emudir):
            if not os.path.islink("/userdata/system/configs/"+emudir):
                shutil.rmtree("/userdata/system/configs/"+emudir)

        if not os.path.exists("/userdata/system/configs/"+emudir):
            st = os.symlink("/userdata/system/configs/yuzu","/userdata/system/configs/"+emudir)

        cachedir = ".cache/" + emudir
        #Link .cache Directory to /userdata/saves/yuzu
        mkdir_if_not_exists(Path("/userdata/system/.cache"))
        mkdir_if_not_exists(Path("/userdata/system/" + cachedir))

        #remove game_list if it exists and isn't a link
        if os.path.exists("/userdata/system/.cache/"+emudir+"/game_list"):
            if not os.path.islink("/userdata/system/.cache/"+emudir+"/game_list"):
                shutil.rmtree("/userdata/system/.cache/"+emudir+"/game_list")

        mkdir_if_not_exists(Path("/userdata/saves/yuzu"))
        mkdir_if_not_exists(Path("/userdata/saves/yuzu/game_list"))
        if not os.path.exists("/userdata/system/.cache/"+emudir+"/game_list"):
            st = os.symlink("/userdata/saves/yuzu/game_list","/userdata/system/.cache/"+emudir+"/game_list")

        #Create Save/Mods Folder
        mkdir_if_not_exists(Path("/userdata/system/configs/yuzu/nand/user"))
        mkdir_if_not_exists(Path("/userdata/system/configs/yuzu/nand/user/save"))
        mkdir_if_not_exists(Path("/userdata/system/configs/yuzu/load"))
        mkdir_if_not_exists(Path("/userdata/saves/switch"))
        mkdir_if_not_exists(Path("/userdata/saves/switch/eden_citron"))
        mkdir_if_not_exists(Path("/userdata/saves/switch/eden_citron/save"))
        mkdir_if_not_exists(Path("/userdata/saves/switch/eden_citron/mods"))

        #Link YUZU SAVE Directory to /userdata/saves/eden_citron/save
        if os.path.exists("/userdata/system/configs/yuzu/nand/user/save"):
            if not os.path.islink("/userdata/system/configs/yuzu/nand/user/save"):
                shutil.rmtree("/userdata/system/configs/yuzu/nand/user/save")
                os.symlink("/userdata/saves/switch/eden_citron/save", "/userdata/system/configs/yuzu/nand/user/save")
            else:
                current_target = os.readlink("/userdata/system/configs/yuzu/nand/user/save")
                if current_target != "/userdata/saves/switch/eden_citron/save":
                    os.unlink("/userdata/system/configs/yuzu/nand/user/save")
                    os.symlink("/userdata/saves/switch/eden_citron/save", "/userdata/system/configs/yuzu/nand/user/save")
        else:
            os.symlink("/userdata/saves/switch/eden_citron/save", "/userdata/system/configs/yuzu/nand/user/save")

        #Link YUZU MODS Directory to /userdata/saves/eden_citron/mods
        if os.path.exists("/userdata/system/configs/yuzu/load"):
            if not os.path.islink("/userdata/system/configs/yuzu/load"):
                shutil.rmtree("/userdata/system/configs/yuzu/load")
                os.symlink("/userdata/saves/switch/eden_citron/mods", "/userdata/system/configs/yuzu/load")
            else:
                current_target = os.readlink("/userdata/system/configs/yuzu/load")
                if current_target != "/userdata/saves/switch/eden_citron/mods":
                    os.unlink("/userdata/system/configs/yuzu/load")
                    os.symlink("/userdata/saves/switch/eden_citron/mods", "/userdata/system/configs/yuzu/load")
        else:
            os.symlink("/userdata/saves/switch/eden_citron/mods", "/userdata/system/configs/yuzu/load")

        yuzuConfig = str(CONFIGS) + '/yuzu/qt-config.ini'
        yuzuConfigTemplate = '/userdata/system/switch/configgen/qt-config.ini.template'

        EdenGenerator.writeYuzuConfig(yuzuConfig, yuzuConfigTemplate, system, playersControllers, sdlversion, emulator)

        commandArray = ["./"+emulator+".AppImage", "-f",  "-g", rom ]

        environment = { "DRI_PRIME":"1",
                        "AMD_VULKAN_ICD":"RADV",
                        "DISABLE_LAYER_AMD_SWITCHABLE_GRAPHICS_1":"1",
                        "QT_XKB_CONFIG_ROOT":"/usr/share/X11/xkb",
#                        "LC_ALL":"C.utf8",
                        "NO_AT_BRIDGE":"1",
                        "XDG_MENU_PREFIX":"batocera-",
                        "XDG_CONFIG_DIRS":"/etc/xdg",
                        "XDG_CURRENT_DESKTOP":"XFCE",
                        "DESKTOP_SESSION":"XFCE",

                        "QT_FONT_DPI":"96",
                        "QT_SCALE_FACTOR":"1",
                        "GDK_SCALE":"1",
                        "XDG_CACHE_HOME":"/userdata/system/.cache",
                        "QT_QPA_PLATFORM": "xcb",
                        "USER":"root",
                        "LANG":"en_US.UTF-8",
        }

        return Command.Command(array=commandArray, env=environment)


    # @staticmethod
    def writeYuzuConfig(yuzuConfigFile, yuzuConfigTemplateFile, system, playersControllers, sdlversion, emulator):
        # pads

        yuzuButtonsMapping = {
             "button_a":      "a",
             "button_b":      "b",
             "button_x":      "x",
             "button_y":      "y",
             "button_dup":    "up",
             "button_ddown":  "down",
             "button_dleft":  "left",
             "button_dright": "right",
             "button_l":      "pageup",
             "button_r":      "pagedown",
             "button_plus":   "start",
             "button_minus":  "select",
             "button_slleft": "pageup",
             "button_srleft": "pagedown",
             "button_slright": "pageup",
             "button_srright": "pagedown",
             "button_zl":     "l2",
             "button_zr":     "r2",
             "button_lstick": "l3",
             "button_rstick": "r3",
             "button_home":   "hotkey"
        }

        yuzuAxisMapping = {
             "lstick":    "joystick1",
             "rstick":    "joystick2"
        }

        # ini file
        yuzuConfig = CaseSensitiveRawConfigParser()
        yuzuConfig.optionxform=str
        yuzuoldConfig = CaseSensitiveRawConfigParser()
        yuzuoldConfig.optionxform=str

        if os.path.exists(yuzuConfigFile):
            yuzuoldConfig.read(yuzuConfigFile)

        if os.path.exists(yuzuConfigTemplateFile):
            yuzuConfig.read(yuzuConfigTemplateFile)


    # UI section
        if not yuzuConfig.has_section("UI"):
            yuzuConfig.add_section("UI")

        if system.isOptSet('yuzu_enable_discord_presence'):
            yuzuConfig.set("UI", "enable_discord_presence", system.config["yuzu_enable_discord_presence"])
        else:
            yuzuConfig.set("UI", "enable_discord_presence", "false")

        yuzuConfig.set("UI", "enable_discord_presence\\default", "false")

        yuzuConfig.set("UI", "check_for_updates_on_start", "false")
        yuzuConfig.set("UI", "check_for_updates_on_start\\default", "false")

        #citron shortcuts
        yuzuConfig.set("UI", "Shortcuts\\shortcuts\\size", "1")#adjust to number of shortcut sets
        #exit citron
        yuzuConfig.set("UI", "Shortcuts\\shortcuts\\1\\name", "Exit citron")
        yuzuConfig.set("UI", "Shortcuts\\shortcuts\\1\\group", "Main Window")
        yuzuConfig.set("UI", "Shortcuts\\shortcuts\\1\\keyseq", "Ctrl+Q")
        yuzuConfig.set("UI", "Shortcuts\\shortcuts\\1\\controller_keyseq", "Y+ZL")
        yuzuConfig.set("UI", "Shortcuts\\shortcuts\\1\\context", "1")
        yuzuConfig.set("UI", "Shortcuts\\shortcuts\\1\\repeat", "false")

        # Interface language (citron)
        if system.isOptSet('yuzu_intlanguage'):
            yuzuConfig.set("UI", "Paths\\language", system.config["yuzu_intlanguage"])
            yuzuConfig.set("UI", "Paths\\language\\default", "false")
        else:
            yuzuConfig.set("UI", "Paths\\language", "en")
            yuzuConfig.set("UI", "Paths\\language\\default", "true")

        # Single Window Mode
        if system.isOptSet('single_window'):
            yuzuConfig.set("UI", "singleWindowMode", system.config["single_window"])
            yuzuConfig.set("UI", "singleWindowMode\\default", "false")
        else:
            yuzuConfig.set("UI", "singleWindowMode", "true")
            yuzuConfig.set("UI", "singleWindowMode\\default", "true")

        # User Profile select on boot
        if system.isOptSet('user_profile'):
            yuzuConfig.set("UI", "select_user_on_boot", system.config["user_profile"])
            yuzuConfig.set("UI", "select_user_on_boot\\default", "false")
        else:
            yuzuConfig.set("UI", "select_user_on_boot", "true")
            yuzuConfig.set("UI", "select_user_on_boot\\default", "true")


    # Core section
        if not yuzuConfig.has_section("Core"):
            yuzuConfig.add_section("Core")

        # Multicore
        if system.isOptSet('multicore'):
            yuzuConfig.set("Core", "use_multi_core", system.config["multicore"])
            yuzuConfig.set("Core", "use_multi_core\\default", "false")
        else:
            yuzuConfig.set("Core", "use_multi_core", "true")
            yuzuConfig.set("Core", "use_multi_core\\default", "true")

        # Memory layout
        if system.isOptSet('yuzu_memory_layout'):
            yuzuConfig.set("Core", "memory_layout_mode", system.config["yuzu_memory_layout"])
            yuzuConfig.set("Core", "memory_layout_mode\\default", "false")
        else:
            yuzuConfig.set("Core", "memory_layout_mode", "0")
            yuzuConfig.set("Core", "memory_layout_mode\\default", "true")

    # Renderer section
        if not yuzuConfig.has_section("Renderer"):
            yuzuConfig.add_section("Renderer")

        # Aspect ratio
        if system.isOptSet('yuzu_ratio'):
            yuzuConfig.set("Renderer", "aspect_ratio", system.config["yuzu_ratio"])
            yuzuConfig.set("Renderer", "aspect_ratio\\default", "false")
        else:
            yuzuConfig.set("Renderer", "aspect_ratio", "0")
            yuzuConfig.set("Renderer", "aspect_ratio\\default", "true")

        # Graphical backend
        if system.isOptSet('yuzu_backend'):
            yuzuConfig.set("Renderer", "backend", system.config["yuzu_backend"])
            yuzuConfig.set("Renderer", "backend\\default", "false")
        else:
            yuzuConfig.set("Renderer", "backend", "1")
            yuzuConfig.set("Renderer", "backend\\default", "true")

        # Async Shader compilation
        if system.isOptSet('async_shaders'):
            yuzuConfig.set("Renderer", "use_asynchronous_shaders", system.config["async_shaders"])
            yuzuConfig.set("Renderer", "use_asynchronous_shaders\\default", "false")
        else:
            yuzuConfig.set("Renderer", "use_asynchronous_shaders", "false")
            yuzuConfig.set("Renderer", "use_asynchronous_shaders\\default", "true")

        # Assembly shaders
        if system.isOptSet('shaderbackend'):
            yuzuConfig.set("Renderer", "shader_backend", system.config["shaderbackend"])
            yuzuConfig.set("Renderer", "shader_backend\\default", "false")
        else:
            yuzuConfig.set("Renderer", "shader_backend", "0")
            yuzuConfig.set("Renderer", "shader_backend\\default", "true")

        # Async Gpu Emulation
        if system.isOptSet('async_gpu'):
            yuzuConfig.set("Renderer", "use_asynchronous_gpu_emulation", system.config["async_gpu"])
            yuzuConfig.set("Renderer", "use_asynchronous_gpu_emulation\\default", "false")
        else:
            yuzuConfig.set("Renderer", "use_asynchronous_gpu_emulation", "true")
            yuzuConfig.set("Renderer", "use_asynchronous_gpu_emulation\\default", "true")

        # NVDEC Emulation
        if system.isOptSet('nvdec_emu'):
            yuzuConfig.set("Renderer", "nvdec_emulation", system.config["nvdec_emu"])
            yuzuConfig.set("Renderer", "nvdec_emulation\\default", "false")
        else:
            yuzuConfig.set("Renderer", "nvdec_emulation", "2")
            yuzuConfig.set("Renderer", "nvdec_emulation\\default", "true")

        # Gpu Accuracy
        if system.isOptSet('gpuaccuracy'):
            yuzuConfig.set("Renderer", "gpu_accuracy", system.config["gpuaccuracy"])
        else:
            yuzuConfig.set("Renderer", "gpu_accuracy", "0")
        yuzuConfig.set("Renderer", "gpu_accuracy\\default", "false")

        # Vsync
        if system.isOptSet('vsync'):
            yuzuConfig.set("Renderer", "use_vsync", system.config["vsync"])
            yuzuConfig.set("Renderer", "use_vsync\\default", "false")
            if system.config["vsync"] == "2":
                yuzuConfig.set("Renderer", "use_vsync\\default", "true")
        else:
            yuzuConfig.set("Renderer", "use_vsync", "1")
            yuzuConfig.set("Renderer", "use_vsync\\default", "false")

        # Gpu cache garbage collection
        if system.isOptSet('gpu_cache_gc'):
            yuzuConfig.set("Renderer", "use_caches_gc", system.config["gpu_cache_gc"])
        else:
            yuzuConfig.set("Renderer", "use_caches_gc", "false")
        yuzuConfig.set("Renderer", "use_caches_gc\\default", "false")

        # Max anisotropy
        if system.isOptSet('anisotropy'):
            yuzuConfig.set("Renderer", "max_anisotropy", system.config["anisotropy"])
            yuzuConfig.set("Renderer", "max_anisotropy\\default", "false")
        else:
            yuzuConfig.set("Renderer", "max_anisotropy", "0")
            yuzuConfig.set("Renderer", "max_anisotropy\\default", "true")

        # Resolution scaler
        if system.isOptSet('resolution_scale'):
            yuzuConfig.set("Renderer", "resolution_setup", system.config["resolution_scale"])
            yuzuConfig.set("Renderer", "resolution_setup\\default", "false")
        else:
            yuzuConfig.set("Renderer", "resolution_setup", "2")
            yuzuConfig.set("Renderer", "resolution_setup\\default", "true")

        # Scaling filter
        if system.isOptSet('scale_filter'):
            yuzuConfig.set("Renderer", "scaling_filter", system.config["scale_filter"])
            yuzuConfig.set("Renderer", "scaling_filter\\default", "false")
        else:
            yuzuConfig.set("Renderer", "scaling_filter", "1")
            yuzuConfig.set("Renderer", "scaling_filter\\default", "true")

        # FSR Quality
        if system.isOptSet('fsr_quality'):
            yuzuConfig.set("Renderer", "fsr2_quality_mode", system.config["fsr_quality"])
            yuzuConfig.set("Renderer", "fsr2_quality_mode\\default", "false")
        else:
            yuzuConfig.set("Renderer", "fsr2_quality_mode", "0")
            yuzuConfig.set("Renderer", "fsr2_quality_mode\\default", "true")

        # Anti aliasing method
        if system.isOptSet('aliasing_method'):
            yuzuConfig.set("Renderer", "anti_aliasing", system.config["aliasing_method"])
            yuzuConfig.set("Renderer", "anti_aliasing\\default", "false")
        else:
            yuzuConfig.set("Renderer", "anti_aliasing", "0")
            yuzuConfig.set("Renderer", "anti_aliasing\\default", "true")

        #ASTC Decoding Method
        if system.isOptSet('accelerate_astc'):
            yuzuConfig.set("Renderer", "accelerate_astc", system.config["accelerate_astc"])
            yuzuConfig.set("Renderer", "accelerate_astc\\default", "false")
        else:
            yuzuConfig.set("Renderer", "accelerate_astc", "1")
            yuzuConfig.set("Renderer", "accelerate_astc\\default", "true")

        # ASTC Texture Recompression
        if system.isOptSet('astc_recompression'):

            yuzuConfig.set("Renderer", "astc_recompression", system.config["astc_recompression"])
            yuzuConfig.set("Renderer", "astc_recompression\\default", "false")
            if system.config["astc_recompression"] == "0":
                yuzuConfig.set("Renderer", "use_vsync\\default", "true")
            yuzuConfig.set("Renderer", "async_astc", "false")
            yuzuConfig.set("Renderer", "async_astc\\default", "true")
        else:
            yuzuConfig.set("Renderer", "astc_recompression", "0")
            yuzuConfig.set("Renderer", "astc_recompression\\default", "true")
            yuzuConfig.set("Renderer", "async_astc", "false")
            yuzuConfig.set("Renderer", "async_astc\\default", "true")


    # Cpu Section
        if not yuzuConfig.has_section("Cpu"):
            yuzuConfig.add_section("Cpu")

        # Cpu Accuracy
        if system.isOptSet('cpuaccuracy'):
            yuzuConfig.set("Cpu", "cpu_accuracy", system.config["cpuaccuracy"])
            yuzuConfig.set("Cpu", "cpu_accuracy\\default", "false")
        else:
            yuzuConfig.set("Cpu", "cpu_accuracy", "0")
            yuzuConfig.set("Cpu", "cpu_accuracy\\default", "true")


    # System section
        if not yuzuConfig.has_section("System"):
            yuzuConfig.add_section("System")

        # Language
        if system.isOptSet('language'):
            yuzuConfig.set("System", "language_index", system.config["language"])
            yuzuConfig.set("System", "language_index\\default", "false")
        else:
            yuzuConfig.set("System", "language_index", "1")
            yuzuConfig.set("System", "language_index\\default", "true")

        # Audio Mode
        if system.isOptSet('audio_mode'):
            yuzuConfig.set("System", "sound_index", system.config["audio_mode"])
            yuzuConfig.set("System", "sound_index\\default", "false")
        else:
            yuzuConfig.set("System", "sound_index", "1")
            yuzuConfig.set("System", "sound_index\\default", "true")

        # Region
        if system.isOptSet('region'):
            yuzuConfig.set("System", "region_index", system.config["region"])
            yuzuConfig.set("System", "region_index\\default", "false")
        else:
            yuzuConfig.set("System", "region_index", "1")
            yuzuConfig.set("System", "region_index\\default", "true")

        # Dock Mode
        if system.isOptSet('dock_mode'):
            if system.config["dock_mode"] == "1":
                yuzuConfig.set("System", "use_docked_mode", "1")
                yuzuConfig.set("System", "use_docked_mode\\default", "true")
            elif system.config["dock_mode"] == "0":
                yuzuConfig.set("System", "use_docked_mode", "0")
                yuzuConfig.set("System", "use_docked_mode\\default", "false")
        else:
            yuzuConfig.set("System", "use_docked_mode", "1")
            yuzuConfig.set("System", "use_docked_mode\\default", "true")


    # controls section
        if not yuzuConfig.has_section("Controls"):
            yuzuConfig.add_section("Controls")

        if not system.isOptSet('yuzu_auto_controller_config') or system.config["yuzu_auto_controller_config"] != "0":
            #get the evdev->hidraw mapping
            evdev_hidraw = evdev_to_hidraw()
            #get sdllib  hidapi/hidraw + evdev guid
            sdl_gamepads = list_sdl_gamepads(sdlversion)

            import pprint
            # pprint.pprint(evdev_hidraw, stream=sys.stderr)
            # pprint.pprint(sdl_gamepads, stream=sys.stderr)
            # pprint.pprint(playersControllers, stream=sys.stderr)
            nplayer = 0
            guid_port = {}
            for nplayer, pad in enumerate(playersControllers, start=0):
                player_nb_str = "player_" + str(nplayer)

                #if hidraw exist, replace the guid and use the provided mapping
                if pad.device_path in evdev_hidraw:
                    hidraw_path = evdev_hidraw[pad.device_path]
                    if hidraw_path in sdl_gamepads:
                        pad.guid = sdl_gamepads[hidraw_path]['guid']
                        pad.inputs = sdl_gamepads[hidraw_path]['inputs']
                #try to get to mapping from the yuzu libsdl (mapping is different than libsdl from ES for some gamepad like xbox one)
                elif pad.device_path in sdl_gamepads:
                    pad.inputs = sdl_gamepads[pad.device_path]['inputs']
                #fallback to inputs from ES

                #port index is by guid
                if pad.guid not in guid_port:
                    guid_port[pad.guid] = 0
                else:
                    guid_port[pad.guid] = guid_port[pad.guid] + 1

                yuzuConfig.set("Controls", player_nb_str + "_type\\default", "false")
                if system.isOptSet('p{}_pad'.format(nplayer)):
                    yuzuConfig.set("Controls", player_nb_str + "_type", system.config["p{}_pad".format(nplayer)])
                else:
                    yuzuConfig.set("Controls", player_nb_str + "_type", 0)

                for x in yuzuButtonsMapping:
                    yuzuConfig.set("Controls", player_nb_str + "_" + x, '"{}"'.format(EdenGenerator.setButton(emulator, yuzuButtonsMapping[x], pad.guid, pad.inputs, guid_port[pad.guid])))
                for x in yuzuAxisMapping:
                    yuzuConfig.set("Controls", player_nb_str + "_" + x, '"{}"'.format(EdenGenerator.setAxis(yuzuAxisMapping[x], pad.guid, pad.inputs, guid_port[pad.guid])))

                yuzuConfig.set("Controls", player_nb_str + "_button_screenshot\\default", "false")
                yuzuConfig.set("Controls", player_nb_str + "_button_screenshot", "[empty]")
                yuzuConfig.set("Controls", player_nb_str + "_motionleft\\default", "false")
                yuzuConfig.set("Controls", player_nb_str + "_motionleft", '"guid:{},port:{},motion:0,engine:sdl"'.format(pad.guid,guid_port[pad.guid]))
                yuzuConfig.set("Controls", player_nb_str + "_motionright\\default", "false")
                yuzuConfig.set("Controls", player_nb_str + "_motionright", '"guid:{},port:{},motion:0,engine:sdl"'.format(pad.guid,guid_port[pad.guid]))
                yuzuConfig.set("Controls", player_nb_str + "_connected", "true")
                yuzuConfig.set("Controls", player_nb_str + "_connected\\default", "false")
                yuzuConfig.set("Controls", player_nb_str + "_vibration_enabled", "true")
                yuzuConfig.set("Controls", player_nb_str + "_vibration_enabled\\default", "false")
                nplayer += 1
        else:
            if yuzuoldConfig is not None:
                old_controls = yuzuoldConfig.items("Controls")
                for option, value in old_controls:
                    yuzuConfig.set("Controls", option, value)


    # telemetry section
        if not yuzuConfig.has_section("WebService"):
            yuzuConfig.add_section("WebService") 
        yuzuConfig.set("WebService", "enable_telemetry", "false")
        yuzuConfig.set("WebService", "enable_telemetry\\default", "false") 


    # Services section
        if not yuzuConfig.has_section("Services"):
            yuzuConfig.add_section("Services")
        yuzuConfig.set("Services", "bcat_backend", "none")
        yuzuConfig.set("Services", "bcat_backend\\default", "none") 

        ### update the configuration file
        if not os.path.exists(os.path.dirname(yuzuConfigFile)):
            os.makedirs(os.path.dirname(yuzuConfigFile))

        with open(yuzuConfigFile, 'w') as configfile:
            yuzuConfig.write(configfile)

    def is_xbox_controller(padGuid, padName=None):
        return (
            padGuid.startswith("060000005e04") or
            (padName and "xbox" in padName.lower())
        )

    @staticmethod
    def setButton(emulator, key, padGuid, padInputs, port, padName=None):

        if key not in padInputs:
            return ""

        input = padInputs[key]

        XBOX_BUTTON_REMAP = {
            "a": 0,
            "b": 1,
            "x": 2,
            "y": 3,
            "pageup": 4,     # LB
            "pagedown": 5,   # RB
            "select": 6,     # Back
            "start": 7,
            "hotkey": 8,     # Guide
            "l3": 9,
            "r3": 10,
        }

        is_xbox = (
            padGuid.startswith("060000005e04") or
            (padName and "xbox" in padName.lower())
        )

        if is_xbox:
            log_stderr("[SETBUTTON] Xbox controller detected")

        if input.type == "button":
            if is_xbox and key in XBOX_BUTTON_REMAP:
                button_id = XBOX_BUTTON_REMAP[key]
                log_stderr(
                    f"[SETBUTTON][XBOX] remap key={key} "
                    f"hid_id={input.id} -> sdl_id={button_id}"
                )
            else:
                button_id = input.id
            mapping = (
                f"button:{button_id},guid:{padGuid},port:{port},engine:sdl"
            )

            return mapping

        elif input.type == "hat":
            mapping = (
                f"hat:0,pad:0,direction:{key},guid:{padGuid},port:{port},engine:sdl"
            )

            return mapping

        elif input.type == "axis":
            mapping = (
                f"threshold:0.5,axis:{input.id},guid:{padGuid},port:{port},engine:sdl"
            )

            return mapping

        return ""

    @staticmethod
    def hatdirectionvalue(value):
        if int(value) == 1:
            return "up"
        if int(value) == 4:
            return "down"
        if int(value) == 2:
            return "right"
        if int(value) == 8:
            return "left"
        return "unknown"

    @staticmethod
    def setAxis(key, padGuid, padInputs, port):
         inputx = "0"
         inputy = "0"

         if key == "joystick1" and "joystick1left" in padInputs:
             padinputx = padInputs["joystick1left"]
             if padinputx.id is not None:
                 inputx = padinputx.id
         elif key == "joystick2" and "joystick2left" in padInputs:
             padinputx = padInputs["joystick2left"]
             if padinputx.id is not None:
                 inputx = padinputx.id

         if key == "joystick1" and "joystick1up" in padInputs:
             padinputy = padInputs["joystick1up"]
             if padinputy.id is not None:
                 inputy = padinputy.id
         elif key == "joystick2" and "joystick2up" in padInputs:
             padinputy = padInputs["joystick2up"]
             if padinputy.id is not None:
                 inputy = padinputy.id

         return ("range:1.000000,deadzone:0.100000,invert_y:+,invert_x:+,offset_y:-0.000000,axis_y:{},offset_x:-0.000000,axis_x:{},guid:{},port:{},engine:sdl").format(inputy, inputx, padGuid, port)

    def getMouseMode(self, config, rom):
        return True
