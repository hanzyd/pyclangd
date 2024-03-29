#!/usr/bin/env python3
import json
import subprocess
from os import path, walk


EXTS = ('.c', '.C', '.cpp', '.cc', '.cxx', '.m', '.mm'
          '.h', '.H', '.hpp', '.hh', '.hxx', '.S')

GCC_INCLUDES = [
    # '/usr/include'
]

DEF_INCLUDES = [
    '.',
    'include',
    'include/linux',
    'include/uapi',
    'include/generated',
    'include/generated/uapi',
]

ARCH_INCLUDES = [
    'arch/{}/include',
    'arch/{}/include/uapi',
    'arch/{}/include/generated',
    'arch/{}/include/generated/uapi',
    "tools/arch/{}/include",
    "tools/perf/arch/{}/include",
    'tools/objtool/arch/{}/include',
]

TOOLS_INCLUDES = [
    'tools/include',
    'tools/objtool/include',
    "tools/lib/perf/include",
    "tools/lib/thermal/include",
    "tools/perf/include",
    "tools/perf/trace/beauty/include",
    "tools/perf/util/include"
]


# Create architecture specific autogenerated files
def make_arch_prepare(src_dir, verbose):

    name = path.join(src_dir,'.config')
    if not path.isfile(name):
        print("{} not configured".format(src_dir))
        return

    make = "make -C {} --no-print-directory --silent".format(src_dir)
    cmd = ' {} olddefconfig'.format(make)
    exit_code = subprocess.call(cmd, shell=True)
    stat_code = "Ok" if exit_code == 0 else "Fail"
    if verbose:
        print("Kernel configuration: {}".format(stat_code))

    cmd = '{} archprepare'.format(make)
    exit_code = subprocess.call(cmd, shell=True)
    stat_code = "Ok" if exit_code == 0 else "Fail"
    if verbose:
        print("Architecture prepare: {}".format(stat_code))


# Scan .config file and try to find ARCH
def arch_detect(src_dir, verbose):
    arch = None
    try:
        name = path.join(src_dir,'.config')
        with open(name, 'r') as config:
            while True:
                line = config.readline()
                # end of file is reached
                if not line:
                    break
                if line.startswith('#') or line == '\n':
                    continue
                if "CONFIG_ARM64=y" in line:
                    arch = "arm64"
                elif "CONFIG_ARM=y" in line:
                    arch = "arm"
    except FileNotFoundError:
        pass

    if verbose:
        print('Kernel architecture : {}'.format(arch if arch else "arm64 (default)"))

    return arch if arch else "arm64"


def add_definitions(flags):
    try:
        with open('.config', 'r') as config:

            # returns output as byte string
            cmc = ['make', 'archprepare']
            returned_output = subprocess.check_output(cmc)
            # using decode() function to convert byte string to string
            print(returned_output.decode("utf-8"))

            while True:
                line = config.readline()
                # end of file is reached
                if not line:
                    break
                if line.startswith('#') or line == '\n':
                    continue

                flags.append('-D' + line)
    except FileNotFoundError:
        print('.config not found')


def add_includes(flags, includes):
    for include in includes:
        flags.append('-I' + include)


def assemble_linux_includes(src_dir, verbose):

    flags = []

    try:
        make_arch_prepare(src_dir, verbose)
    except KeyboardInterrupt:
        pass

    arch = arch_detect(src_dir, verbose)
    arch_inc = []
    for inc in ARCH_INCLUDES:
        arch_inc.append(inc.format(arch))

    add_includes(flags, GCC_INCLUDES)
    add_includes(flags, DEF_INCLUDES)
    add_includes(flags, arch_inc)
    add_includes(flags, TOOLS_INCLUDES)

    return flags


def assemble_all_includes(src_dir):

    entries = list()
    for root, _, files in walk(src_dir):
        if root.endswith('include'):
            entries.append('-I' + root.replace(src_dir, '.'))

    return entries


def create_compile_commands_json(src_dir, cache_dir, driver, verbose):

    is_linux = path.isdir(path.join(src_dir, 'include/linux'))
    is_u_boot = path.isdir(path.join(src_dir, 'include/u-boot'))

    if is_linux or is_u_boot:
        flags = assemble_linux_includes(src_dir, verbose);
        flags.append('%c -std=c98')
        flags.append('-nostdinc')
        flags.append('-D' + '__KERNEL__')
    else:
        flags = assemble_all_includes(src_dir)

    if driver == 'gcc':
        flags.append('-fsyntax-only')
    else:
        flags.append('-ferror-limit=0')

    flags.append('-w')

    entries = []

    for root, _, files in walk(src_dir):
        for file in files:
            ext = path.splitext(file)[1]
            name = path.join(root, file)
            name = path.relpath(name, src_dir)
            obj = path.splitext(name)[0] + '.o'
            if ext in EXTS:
                entries.append({
                    'directory': src_dir,
                    'file': name,
                    'arguments': [driver] + flags + [ '-c', '-o', obj] + [name]})

    name = path.join(cache_dir,'compile_commands.json')
    try:
        with open(name, 'w') as file:
            json.dump(entries, file, indent=2)

        if verbose:
            print('{}: have {} entries\n'.format(name, len(entries)))
    except FileNotFoundError:
        pass