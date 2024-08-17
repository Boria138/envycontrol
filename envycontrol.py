#!/usr/bin/env python3
import argparse
import logging
import os
import re
import subprocess
import sys
from contextlib import contextmanager

# begin constants definition

VERSION = '3.5.0'

# Note: Do NOT remove this in cleanup!
CACHE_FILE_PATH = '/var/cache/envycontrol/cache.json'

BLACKLIST_PATH = '/etc/modprobe.d/blacklist-nvidia.conf'

BLACKLIST_CONTENT = '''# Automatically generated by EnvyControl

blacklist nouveau
blacklist nvidia
blacklist nvidia_drm
blacklist nvidia_uvm
blacklist nvidia_modeset
blacklist nvidia_current
blacklist nvidia_current_drm
blacklist nvidia_current_uvm
blacklist nvidia_current_modeset
blacklist i2c_nvidia_gpu
alias nouveau off
alias nvidia off
alias nvidia_drm off
alias nvidia_uvm off
alias nvidia_modeset off
alias nvidia_current off
alias nvidia_current_drm off
alias nvidia_current_uvm off
alias nvidia_current_modeset off
alias i2c_nvidia_gpu off
'''

UDEV_INTEGRATED_PATH = '/etc/udev/rules.d/50-remove-nvidia.rules'

UDEV_INTEGRATED = '''# Automatically generated by EnvyControl

# Remove NVIDIA USB xHCI Host Controller devices, if present
ACTION=="add", SUBSYSTEM=="pci", ATTR{vendor}=="0x10de", ATTR{class}=="0x0c0330", ATTR{power/control}="auto", ATTR{remove}="1"

# Remove NVIDIA USB Type-C UCSI devices, if present
ACTION=="add", SUBSYSTEM=="pci", ATTR{vendor}=="0x10de", ATTR{class}=="0x0c8000", ATTR{power/control}="auto", ATTR{remove}="1"

# Remove NVIDIA Audio devices, if present
ACTION=="add", SUBSYSTEM=="pci", ATTR{vendor}=="0x10de", ATTR{class}=="0x040300", ATTR{power/control}="auto", ATTR{remove}="1"

# Remove NVIDIA VGA/3D controller devices
ACTION=="add", SUBSYSTEM=="pci", ATTR{vendor}=="0x10de", ATTR{class}=="0x03[0-9]*", ATTR{power/control}="auto", ATTR{remove}="1"
'''

UDEV_PM_PATH = '/etc/udev/rules.d/80-nvidia-pm.rules'

UDEV_PM_CONTENT = '''# Automatically generated by EnvyControl

# Remove NVIDIA USB xHCI Host Controller devices, if present
ACTION=="add", SUBSYSTEM=="pci", ATTR{vendor}=="0x10de", ATTR{class}=="0x0c0330", ATTR{remove}="1"

# Remove NVIDIA USB Type-C UCSI devices, if present
ACTION=="add", SUBSYSTEM=="pci", ATTR{vendor}=="0x10de", ATTR{class}=="0x0c8000", ATTR{remove}="1"

# Remove NVIDIA Audio devices, if present
ACTION=="add", SUBSYSTEM=="pci", ATTR{vendor}=="0x10de", ATTR{class}=="0x040300", ATTR{remove}="1"

# Enable runtime PM for NVIDIA VGA/3D controller devices on driver bind
ACTION=="bind", SUBSYSTEM=="pci", ATTR{vendor}=="0x10de", ATTR{class}=="0x030000", TEST=="power/control", ATTR{power/control}="auto"
ACTION=="bind", SUBSYSTEM=="pci", ATTR{vendor}=="0x10de", ATTR{class}=="0x030200", TEST=="power/control", ATTR{power/control}="auto"

# Disable runtime PM for NVIDIA VGA/3D controller devices on driver unbind
ACTION=="unbind", SUBSYSTEM=="pci", ATTR{vendor}=="0x10de", ATTR{class}=="0x030000", TEST=="power/control", ATTR{power/control}="on"
ACTION=="unbind", SUBSYSTEM=="pci", ATTR{vendor}=="0x10de", ATTR{class}=="0x030200", TEST=="power/control", ATTR{power/control}="on"
'''

XORG_PATH = '/etc/X11/xorg.conf'

XORG_INTEL = '''# Automatically generated by EnvyControl

Section "ServerLayout"
    Identifier "layout"
    Screen 0 "nvidia"
    Inactive "intel"
EndSection

Section "Device"
    Identifier "nvidia"
    Driver "nvidia"
    BusID "{}"
EndSection

Section "Screen"
    Identifier "nvidia"
    Device "nvidia"
    Option "AllowEmptyInitialConfiguration"
EndSection

Section "Device"
    Identifier "intel"
    Driver "modesetting"
EndSection

Section "Screen"
    Identifier "intel"
    Device "intel"
EndSection
'''

XORG_AMD = '''# Automatically generated by EnvyControl

Section "ServerLayout"
    Identifier "layout"
    Screen 0 "nvidia"
    Inactive "amdgpu"
EndSection

Section "Device"
    Identifier "nvidia"
    Driver "nvidia"
    BusID "{}"
EndSection

Section "Screen"
    Identifier "nvidia"
    Device "nvidia"
    Option "AllowEmptyInitialConfiguration"
EndSection

Section "Device"
    Identifier "amdgpu"
    Driver "amdgpu"
EndSection

Section "Screen"
    Identifier "amd"
    Device "amdgpu"
EndSection
'''

EXTRA_XORG_PATH = '/etc/X11/xorg.conf.d/10-nvidia.conf'

EXTRA_XORG_CONTENT = '''# Automatically generated by EnvyControl

Section "OutputClass"
    Identifier "nvidia"
    MatchDriver "nvidia-drm"
    Driver "nvidia"
'''

FORCE_COMP = '    Option "ForceCompositionPipeline" "true"\n'

COOLBITS = '    Option "Coolbits" "{}"\n'

MODESET_PATH = '/etc/modprobe.d/nvidia.conf'

MODESET_CONTENT = '''# Automatically generated by EnvyControl

options nvidia-drm modeset=1
options nvidia NVreg_UsePageAttributeTable=1 NVreg_InitializeSystemMemoryAllocations=0
'''

MODESET_CURRENT_CONTENT = '''# Automatically generated by EnvyControl

options nvidia-current-drm modeset=1
options nvidia-current NVreg_UsePageAttributeTable=1 NVreg_InitializeSystemMemoryAllocations=0
'''

MODESET_RTD3 = '''# Automatically generated by EnvyControl

options nvidia-drm modeset=1
options nvidia "NVreg_DynamicPowerManagement=0x0{}"
options nvidia NVreg_UsePageAttributeTable=1 NVreg_InitializeSystemMemoryAllocations=0
'''

MODESET_CURRENT_RTD3 = '''# Automatically generated by EnvyControl

options nvidia-current-drm modeset=1
options nvidia-current "NVreg_DynamicPowerManagement=0x0{}"
options nvidia-current NVreg_UsePageAttributeTable=1 NVreg_InitializeSystemMemoryAllocations=0
'''

SDDM_XSETUP_PATH = '/usr/share/sddm/scripts/Xsetup'

SDDM_XSETUP_CONTENT = '''#!/bin/sh
# Xsetup - run as root before the login dialog appears

'''

LIGHTDM_SCRIPT_PATH = '/etc/lightdm/nvidia.sh'

LIGHTDM_CONFIG_PATH = '/etc/lightdm/lightdm.conf.d/20-nvidia.conf'

LIGHTDM_CONFIG_CONTENT = '''# Automatically generated by EnvyControl

[Seat:*]
display-setup-script=/etc/lightdm/nvidia.sh
'''

NVIDIA_XRANDR_SCRIPT = '''#!/bin/sh
# Automatically generated by EnvyControl

xrandr --setprovideroutputsource "{}" NVIDIA-0
xrandr --auto
'''

SUPPORTED_MODES = ['integrated', 'hybrid', 'nvidia']
SUPPORTED_DISPLAY_MANAGERS = ['gdm', 'gdm3', 'sddm', 'lightdm']
RTD3_MODES = [0, 1, 2, 3]

# end constants definition


def graphics_mode_switcher(graphics_mode, user_display_manager, enable_force_comp, coolbits_value, rtd3_value, use_nvidia_current):
    print(f"Switching to {graphics_mode} mode")

    if graphics_mode == 'integrated':

        if logging.getLogger().level == logging.DEBUG:
            service = subprocess.run(
                ["systemctl", "disable", "nvidia-persistenced.service"])
        else:
            service = subprocess.run(
                ["systemctl", "disable", "nvidia-persistenced.service"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if service.returncode == 0:
            print('Successfully disabled nvidia-persistenced.service')
        else:
            logging.error("An error ocurred while disabling service")

        cleanup()

        # blacklist all nouveau and Nvidia modules
        create_file(BLACKLIST_PATH, BLACKLIST_CONTENT)

        # power off the Nvidia GPU with udev rules
        create_file(UDEV_INTEGRATED_PATH, UDEV_INTEGRATED)

        rebuild_initramfs()
    elif graphics_mode == 'hybrid':
        print(
            f"Enable PCI-Express Runtime D3 (RTD3) Power Management: {rtd3_value or False}")
        cleanup()

        if logging.getLogger().level == logging.DEBUG:
            service = subprocess.run(
                ["systemctl", "enable", "nvidia-persistenced.service"])
        else:
            service = subprocess.run(
                ["systemctl", "enable", "nvidia-persistenced.service"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if service.returncode == 0:
            print('Successfully enabled nvidia-persistenced.service')
        else:
            logging.error("An error ocurred while enabling service")

        if rtd3_value == None:
            if use_nvidia_current:
                create_file(MODESET_PATH, MODESET_CURRENT_CONTENT)
            else:
                create_file(MODESET_PATH, MODESET_CONTENT)
        else:
            # setup rtd3
            if use_nvidia_current:
                create_file(
                    MODESET_PATH, MODESET_CURRENT_RTD3.format(rtd3_value))
            else:
                create_file(MODESET_PATH, MODESET_RTD3.format(rtd3_value))
            create_file(UDEV_PM_PATH, UDEV_PM_CONTENT)

        rebuild_initramfs()
    elif graphics_mode == 'nvidia':
        print(f"Enable ForceCompositionPipeline: {enable_force_comp}")
        print(f"Enable Coolbits: {coolbits_value or False}")

        if logging.getLogger().level == logging.DEBUG:
            service = subprocess.run(
                ["systemctl", "enable", "nvidia-persistenced.service"])
        else:
            service = subprocess.run(
                ["systemctl", "enable", "nvidia-persistenced.service"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if service.returncode == 0:
            print('Successfully enabled nvidia-persistenced.service')
        else:
            logging.error("An error ocurred while enabling service")

        cleanup()
        # get the Nvidia dGPU PCI bus
        nvidia_gpu_pci_bus = get_nvidia_gpu_pci_bus()

        # get iGPU vendor
        igpu_vendor = get_igpu_vendor()

        # create the X.org config
        if igpu_vendor == 'intel':
            create_file(XORG_PATH, XORG_INTEL.format(nvidia_gpu_pci_bus))
        elif igpu_vendor == 'amd':
            create_file(XORG_PATH, XORG_AMD.format(nvidia_gpu_pci_bus))

        # enable modeset for Nvidia driver
        if use_nvidia_current:
            create_file(MODESET_PATH, MODESET_CURRENT_CONTENT)
        else:
            create_file(MODESET_PATH, MODESET_CONTENT)

        # extra Xorg config
        if enable_force_comp and coolbits_value != None:
            create_file(EXTRA_XORG_PATH, EXTRA_XORG_CONTENT + FORCE_COMP +
                        COOLBITS.format(coolbits_value) + 'EndSection\n')
        elif enable_force_comp:
            create_file(EXTRA_XORG_PATH, EXTRA_XORG_CONTENT +
                        FORCE_COMP + 'EndSection\n')
        elif coolbits_value != None:
            create_file(EXTRA_XORG_PATH, EXTRA_XORG_CONTENT +
                        COOLBITS.format(coolbits_value) + 'EndSection\n')

        # try to detect the display manager if not provided
        if user_display_manager == None:
            display_manager = get_display_manager()
        else:
            display_manager = user_display_manager

        # only sddm and lightdm require further config
        if display_manager == 'sddm':
            # backup Xsetup
            if os.path.exists(SDDM_XSETUP_PATH):
                logging.info("Creating Xsetup backup")
                with open(SDDM_XSETUP_PATH, mode='r', encoding='utf-8') as f:
                    create_file(SDDM_XSETUP_PATH+'.bak', f.read())
            create_file(SDDM_XSETUP_PATH,
                        generate_xrandr_script(igpu_vendor), True)
        elif display_manager == 'lightdm':
            create_file(LIGHTDM_SCRIPT_PATH,
                        generate_xrandr_script(igpu_vendor), True)
            create_file(LIGHTDM_CONFIG_PATH, LIGHTDM_CONFIG_CONTENT)

        rebuild_initramfs()
    print('Operation completed successfully')
    print('Please reboot your computer for changes to take effect!')


def cleanup():
    # define list of files to remove
    to_remove = [
        BLACKLIST_PATH,
        UDEV_INTEGRATED_PATH,
        UDEV_PM_PATH,
        XORG_PATH,
        EXTRA_XORG_PATH,
        MODESET_PATH,
        LIGHTDM_SCRIPT_PATH,
        LIGHTDM_CONFIG_PATH,
        # legacy files
        '/etc/X11/xorg.conf.d/90-nvidia.conf',
        '/lib/udev/rules.d/50-remove-nvidia.rules',
        '/lib/udev/rules.d/80-nvidia-pm.rules'
    ]

    # remove each file in the list
    for file_path in to_remove:
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logging.info(f"Removed file {file_path}")
        except OSError as e:
            # only warn if file exists (code 2)
            if e.errno != 2:
                logging.error(f"Failed to remove file '{file_path}': {e}")

    # restore Xsetup backup if found
    backup_path = SDDM_XSETUP_PATH + ".bak"
    if os.path.exists(backup_path):
        logging.info("Restoring Xsetup backup")
        with open(backup_path, mode="r", encoding="utf-8") as f:
            create_file(SDDM_XSETUP_PATH, f.read())
        # remove backup
        os.remove(backup_path)
        logging.info(f"Removed file {backup_path}")


def get_nvidia_gpu_pci_bus():
    lspci_output = subprocess.check_output(['lspci']).decode('utf-8')
    for line in lspci_output.splitlines():
        if 'NVIDIA' in line and ('VGA compatible controller' in line or '3D controller' in line):
            # remove leading zeros
            pci_bus_id = line.split()[0].replace("0000:", "")
            logging.info(f"Found Nvidia GPU at {pci_bus_id}")
            break
    else:
        logging.error("Could not find Nvidia GPU")
        print("Try switching to hybrid mode first!")
        sys.exit(1)

    # need to return the BusID in 'PCI:bus:device:function' format
    # also perform hexadecimal to decimal conversion
    bus, device_function = pci_bus_id.split(":")
    device, function = device_function.split(".")
    return f"PCI:{int(bus, 16)}:{int(device, 16)}:{int(function, 16)}"


def get_igpu_vendor():
    lspci_output = subprocess.check_output(["lspci"]).decode('utf-8')
    for line in lspci_output.splitlines():
        if 'VGA compatible controller' in line or 'Display controller' in line:
            if 'Intel' in line:
                logging.info("Found Intel iGPU")
                return 'intel'
            elif 'ATI' in line or 'AMD' in line or 'AMD/ATI' in line:
                logging.info("Found AMD iGPU")
                return 'amd'
    logging.warning("Could not find Intel or AMD iGPU")
    return None


def get_display_manager():
    try:
        with open('/etc/systemd/system/display-manager.service', 'r', encoding='utf-8') as f:
            content = f.read()
            match = re.search(r'ExecStart=(.+)\n', content)
            if match:
                # only return the final component of the path
                display_manager = os.path.basename(match.group(1))
                logging.info(f"Found {display_manager} Display Manager")
                return display_manager
    except FileNotFoundError:
        logging.warning("Display Manager detection is not available")


def generate_xrandr_script(igpu_vendor):
    if igpu_vendor == 'intel':
        return NVIDIA_XRANDR_SCRIPT.format('modesetting')
    elif igpu_vendor == 'amd':
        amd_igpu_name = get_amd_igpu_name()
        if amd_igpu_name != None:
            return NVIDIA_XRANDR_SCRIPT.format(amd_igpu_name)
        else:
            return NVIDIA_XRANDR_SCRIPT.format('modesetting')
    else:
        return NVIDIA_XRANDR_SCRIPT.format('modesetting')


def get_amd_igpu_name():
    if not os.path.exists('/usr/bin/xrandr'):
        logging.warning(
            "The 'xrandr' command is not available. Make sure the package is installed!")
        return None

    try:
        xrandr_output = subprocess.check_output(
            ['xrandr', '--listproviders']).decode('utf-8')
    except subprocess.CalledProcessError:
        logging.warning(
            "Failed to run the 'xrandr' command.")

    pattern = re.compile(r'(name:).*(ATI*|AMD*|AMD\/ATI)*')

    if pattern.findall(xrandr_output):
        return re.search(pattern, xrandr_output).group(0)[5:]
    else:
        logging.warning(
            "Could not find AMD iGPU in 'xrandr' output.")
        return None


def rebuild_initramfs():
    # OSTree systems first
    if any(os.path.exists(dir) for dir in ['/ostree', '/sysroot/ostree']):
        print('Rebuilding the initramfs with rpm-ostree...')
        command = ['rpm-ostree', 'initramfs', '--enable', '--arg=--force']

    # Debian and Ubuntu derivatives
    elif os.path.exists('/etc/debian_version'):
        command = ['update-initramfs', '-u', '-k', 'all']
    # RHEL and SUSE derivatives
    elif os.path.exists('/etc/redhat-release') or os.path.exists('/usr/bin/zypper'):
        command = ['dracut', '--force', '--regenerate-all']
    # EndeavourOS with dracut
    elif os.path.exists('/usr/lib/endeavouros-release') and os.path.exists('/usr/bin/dracut'):
        command = ['dracut-rebuild']
    else:
        command = []

    if len(command) != 0:
        print('Rebuilding the initramfs...')
        if logging.getLogger().level == logging.DEBUG:
            p = subprocess.run(command)
        else:
            p = subprocess.run(
                command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if p.returncode == 0:
            print('Successfully rebuilt the initramfs!')
        else:
            logging.error("An error ocurred while rebuilding the initramfs")


def create_file(path, content, executable=False):
    try:
        # create the parent folders if needed
        if not os.path.exists(os.path.dirname(path)):
            os.makedirs(os.path.dirname(path))
        with open(path, mode='w', encoding='utf-8') as f:
            f.write(content)
        logging.info(f"Created file {path}")
        if logging.getLogger().level == logging.DEBUG:
            print(content)

        # add execution privilege
        if executable:
            subprocess.run(['chmod', '+x', path], stdout=subprocess.DEVNULL)
            logging.info(f"Added execution privilege to file {path}")
    except OSError as e:
        logging.error(f"Failed to create file '{path}': {e}")


def assert_root():
    if os.geteuid() != 0:
        logging.error("This operation requires root privileges")
        sys.exit(1)


def main():
    # define CLI arguments
    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--version', action='version', version=VERSION,
                        help='Output the current version')
    parser.add_argument('-q', '--query', action='store_true',
                        help='Query the current graphics mode')
    parser.add_argument('-s', '--switch', type=str, metavar='MODE', action='store', choices=SUPPORTED_MODES,
                        help='Switch the graphics mode. Available choices: %(choices)s')
    parser.add_argument('--dm', type=str, metavar='DISPLAY_MANAGER', action='store', choices=SUPPORTED_DISPLAY_MANAGERS,
                        help='Manually specify your Display Manager for Nvidia mode. Available choices: %(choices)s')
    parser.add_argument('--force-comp', action='store_true',
                        help='Enable ForceCompositionPipeline on Nvidia mode')
    parser.add_argument('--coolbits', type=int, nargs='?', metavar='VALUE', action='store', const=28,
                        help='Enable Coolbits on Nvidia mode. Default if specified: %(const)s')
    parser.add_argument('--rtd3', type=int, nargs='?', metavar='VALUE', action='store', choices=RTD3_MODES, const=2,
                        help='Setup PCI-Express Runtime D3 (RTD3) Power Management on Hybrid mode. Available choices: %(choices)s. Default if specified: %(const)s')
    parser.add_argument('--use-nvidia-current', action='store_true',
                        help='Use nvidia-current instead of nvidia for kernel modules')
    parser.add_argument('--reset-sddm', action='store_true',
                        help='Restore default Xsetup file')
    parser.add_argument('--reset', action='store_true',
                        help='Revert changes made by EnvyControl')
    parser.add_argument('--cache-create', action='store_true',
                        help='Create cache used by EnvyControl; only works in hybrid mode')
    parser.add_argument('--cache-delete', action='store_true',
                        help='Delete cache created by EnvyControl')
    parser.add_argument('--cache-query', action='store_true',
                        help='Show cache created by EnvyControl')
    parser.add_argument('--verbose', default=False, action='store_true',
                        help='Enable verbose mode')

    # print help if no arg is provided
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(1)

    args = parser.parse_args()

    # log formatting
    logging.basicConfig(format='%(levelname)s: %(message)s')

    # set debug level for verbose mode
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.query:
        mode = get_current_mode()
        print(mode)
        return
    elif args.cache_create:
        assert_root()
        CachedConfig(args).create_cache_file()
        return
    elif args.cache_delete:
        assert_root()
        CachedConfig.delete_cache_file()
        return
    elif args.cache_query:
        CachedConfig.show_cache_file()
        return

    if args.switch or args.reset_sddm or args.reset:
        with CachedConfig(args).adapter():
            if args.switch:
                assert_root()
                graphics_mode_switcher(
                    args.switch, args.dm,
                    args.force_comp, args.coolbits, args.rtd3, args.use_nvidia_current
                )
            elif args.reset_sddm:
                assert_root()
                create_file(SDDM_XSETUP_PATH, SDDM_XSETUP_CONTENT, True)
                print('Operation completed successfully')
            elif args.reset:
                assert_root()
                cleanup()
                CachedConfig.delete_cache_file()
                rebuild_initramfs()
                print('Operation completed successfully')


class CachedConfig:
    '''Adapter for config from CACHE_FILE_PATH'''

    def __init__(self, app_args) -> None:
        self.app_args = app_args
        self.current_mode = get_current_mode()

    @contextmanager
    def adapter(self):
        global get_nvidia_gpu_pci_bus
        use_cache = os.path.exists(CACHE_FILE_PATH)

        if self.is_hybrid():  # recreate cache file when in hybrid mode
            self.create_cache_file()

        if use_cache:
            self.read_cache_file()  # might not be in hybrid mode

            # rebind function to use cached value instead of detection
            get_nvidia_gpu_pci_bus = self.get_nvidia_gpu_pci_bus

        yield  # back to main ...

    def create_cache_file(self):
        if not self.is_hybrid():
            raise ValueError(
                '--cache-create requires that the system be in the hybrid Optimus mode')

        self.nvidia_gpu_pci_bus = get_nvidia_gpu_pci_bus()
        self.obj = self.create_cache_obj(self.nvidia_gpu_pci_bus)
        self.write_cache_file()

    def create_cache_obj(self, nvidia_gpu_pci_bus):
        return {
            'nvidia_gpu_pci_bus': nvidia_gpu_pci_bus
        }

    def is_hybrid(self):
        return 'hybrid' == self.current_mode

    def get_nvidia_gpu_pci_bus(self):
        return self.nvidia_gpu_pci_bus

    @staticmethod
    def delete_cache_file():
        os.remove(CACHE_FILE_PATH)
        os.removedirs(os.path.dirname(CACHE_FILE_PATH))
        logging.debug(f"Removed file {CACHE_FILE_PATH}")

    def read_cache_file(self):
        from json import loads
        if os.path.exists(CACHE_FILE_PATH):
            with open(CACHE_FILE_PATH, 'r', encoding='utf-8') as f:
                content = f.read()
            self.obj = loads(content)
            self.nvidia_gpu_pci_bus = self.obj['nvidia_gpu_pci_bus']
        elif self.is_hybrid():
            self.nvidia_gpu_pci_bus = get_nvidia_gpu_pci_bus()
        else:
            raise ValueError(
                'No cache present. Operation requires that the system be in the hybrid Optimus mode')

    @staticmethod
    def show_cache_file():
        content = f'ERROR: Could not read {CACHE_FILE_PATH}'
        if os.path.exists(CACHE_FILE_PATH):
            with open(CACHE_FILE_PATH, 'r', encoding='utf-8') as f:
                content = f.read()
        print(content)

    def write_cache_file(self):
        from json import dump
        os.makedirs(os.path.dirname(CACHE_FILE_PATH), exist_ok=True)

        with open(CACHE_FILE_PATH, 'w', encoding='utf-8') as f:
            dump(self.obj, fp=f, indent=4, sort_keys=False)

        logging.debug(f"Created file {CACHE_FILE_PATH}")


def get_current_mode():
    mode = 'hybrid'
    if os.path.exists(BLACKLIST_PATH) and os.path.exists(UDEV_INTEGRATED_PATH):
        mode = 'integrated'
    elif os.path.exists(XORG_PATH) and os.path.exists(MODESET_PATH):
        mode = 'nvidia'
    return mode


if __name__ == '__main__':
    main()
