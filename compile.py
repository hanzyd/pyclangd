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


def arch_detect(src_dir):
    arch = None
    try:
        name = path.join(src_dir,'.config')
        print(name)
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
        print('.config not found')

    if not arch:
        print('ARCH not detected')
        arch = "arm64"

    print('ARCH set to {}'.format(arch))

    return arch

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


def assemble_linux_includes(src_dir):

    flags = []

    arch = arch_detect(src_dir)
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


def create_compile_commands_json(src_dir, cache_dir, driver):

    if path.isdir(path.join(src_dir, 'include/linux')):
        flags = assemble_linux_includes(src_dir);
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

    print('{}: files'.format(len(entries)))

    name = path.join(cache_dir,'compile_commands.json')
    with open(name, 'w') as file:
        json.dump(entries, file, indent=2)
