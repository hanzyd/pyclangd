#!/usr/bin/env python3
from pylspclient import LspClient, LspEndpoint, JsonRpcEndpoint
from os import path, getpid, environ, makedirs, getcwd
from subprocess import Popen, PIPE
from argparse import ArgumentParser
from multiprocessing import cpu_count
from sys import exit, platform, stdout
from select import select
from compile import create_compile_commands_json
import json
import yaml
import sys

# https://github.com/llvm/clangd-www/blob/main/faq.md

class Devnull(object):
    def write(self, *_): pass
    def flush(self, *_): pass

def read_yaml_path_matches():

    home = environ.get('HOME')

    if platform == "darwin":
        conf_dir = 'Library/Preferences'
    else:
        conf_dir = '.config'

    config_file = path.join(home, conf_dir, 'clangd', 'config.yaml')

    try:
        with open(config_file, 'r') as file:
            document = file.read()
            configs = yaml.load_all(document, Loader=yaml.FullLoader)
    except FileNotFoundError:
        configs = {}

    src_dirs = []
    for config in configs:
        try:
            path_match = config['If']['PathMatch']
            src_dirs.append(path_match[:-3])
        except KeyError:
            pass

    return src_dirs


def update_yaml_config(directory, verbose):

    home = environ.get('HOME')

    if platform == "darwin":
        conf_dir = 'Library/Preferences'
    else:
        conf_dir = '.config'

    config_file = path.join(home, conf_dir, 'clangd', 'config.yaml')
    if verbose:
        print("Clangd configuration: {}".format(config_file))

    sub_dir = directory.strip(home)
    cache_dir = path.join(home, '.cache', 'clangd', sub_dir)
    conf_dir = path.dirname(config_file)

    try:
        makedirs(conf_dir)
    except FileExistsError:
        pass

    try:
        makedirs(cache_dir)
    except FileExistsError:
        pass

    try:
        with open(config_file, 'r') as file:
            document = file.read()
            configs = yaml.load_all(document, Loader=yaml.FullLoader)
    except FileNotFoundError:
        configs = {}

    entry = None
    for config in configs:
        try:
            path_match = config['If']['PathMatch']
            if path_match[:-3] == directory:
                entry = config
                break
        except KeyError:
            pass

    if not entry:
        entry = dict()
        entry['If'] = dict()
        entry['If']['PathMatch'] = directory + '/.*'
        entry['CompileFlags'] = dict()
        entry['CompileFlags']['CompilationDatabase'] = cache_dir

        with open(config_file, 'a') as file:
            file.writelines(['---\n'])
            document = yaml.dump(entry, default_flow_style=False,
                                 indent=2, sort_keys=False)
            file.write(document)

    return entry['CompileFlags']['CompilationDatabase']


def index_directory(directory, verbose, timeout):

    if verbose:
        log = '--log=verbose'
    else:
        log = '--log=info'

    count = '-j={}'.format(int((cpu_count() * 80) / 100))

    try:
        cmd = ['clangd', '--background-index', count, '--enable-config', log]
        proc = Popen(cmd, stdout=PIPE, stdin=PIPE, stderr=PIPE)
    except FileNotFoundError:
        print('Can not find clangd')
        exit(1)

    while True:
        line = proc.stderr.readline().decode('utf-8')
        if not line:
            break
        else:
            if 'Starting LSP over stdin/stdout' in str(line):
                break

    client = LspClient(LspEndpoint(JsonRpcEndpoint(proc.stdin, proc.stdout)))

    try:
        with open(path.join(directory, 'compile_commands.json'), 'r') as file:
            try:
                command = json.load(file)[0]
            except IndexError:
                print('No files to index')
                return 1

        name = path.join(command.get('directory'), command.get('file'))
        with open(name, 'r') as file:
            source = file.read()
    except FileNotFoundError as err:
        print(err)
        return 1

    root_uri = 'file://' + command.get('directory')
    workspace = [{"uri": root_uri, "name": "linux"}]

    file = root_uri + '/' + command.get('file')
    document = {"uri": file, "languageId": "c", "version": 1, "text": source}

    sys_stdout = sys.stdout
    sys.stdout = Devnull()

    client.initialize(getpid(), None, root_uri, None, None, 'off', workspace)
    client.initialized()
    client.didOpen(document)

    try:
        while True:
            r, _, _ = select([proc.stderr.fileno()], [], [], timeout)
            if not r:
                break

            line = proc.stderr.readline().decode('utf-8')
            if not line:
                break
            else:
                if 'background indexer is idle' in str(line):
                    break
    except KeyboardInterrupt:
        pass

    client.exit()
    sys.stdout = sys_stdout
    return 0


def main():
    usage = 'Setup clangd configuration environment'
    parser = ArgumentParser(description=usage)

    directory_help = ('Path to the source directory '
                      '(defaults to the current directory)')
    verbose_help = ('Be verbose'
                    '(defaults to False)')
    index_help = ('Force clangd to index source directory'
                  ' (defaults to False)')
    compiler_help = ('Compiler name: gcc|clang'
                     ' (defaults to gcc)')
    timeout_help = ('How long to wait for new message from clangd and then'
                    ' consider index is ready (defaults to 10 seconds)')

    refresh_help = ('Rebuild compile_commands.json for existing configurations'
                    ' (defaults to False)')

    parser.add_argument('-d', '--directory', type=str, help=directory_help)
    parser.add_argument('-v', '--verbose', action='store_true',
                        default=False, help=verbose_help)
    parser.add_argument('-i', '--index', action='store_true',
                        default=False, help=index_help)
    parser.add_argument('-c', '--compiler', type=str,
                        default='gcc', help=compiler_help)
    parser.add_argument('-t', '--timeout', type=int,
                        default=10, help=timeout_help)
    parser.add_argument('-r', '--refresh', action='store_true',
                        default=False, help=refresh_help)

    args = parser.parse_args()

    directory = args.directory or getcwd()
    directory = path.abspath(directory)

    if args.refresh:
        src_dirs = read_yaml_path_matches()
    else:
        src_dirs = [directory]

    for directory in src_dirs:
        if args.verbose:
            print("Processing directory: {}".format(directory))
        cache_dir = update_yaml_config(directory, args.verbose)

        create_compile_commands_json(directory, cache_dir, args.compiler, args.verbose)
        if args.index:
            index_directory(cache_dir, args.verbose, args.timeout)

    return 0


if __name__ == '__main__':
    exit(main())
