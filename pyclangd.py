#!/usr/bin/env python3
from pylspclient import LspClient, LspEndpoint, JsonRpcEndpoint
from os import path, getcwd, chdir, getpid
from subprocess import Popen, PIPE
from argparse import ArgumentParser
from sys import exit
import json


def main():
    usage = 'Creates a compile_commands.json from compile_flags.txt file'
    parser = ArgumentParser(description=usage)

    directory_help = ('Path to the kernel source directory '
                      '(defaults to the working directory)')

    parser.add_argument('-d', '--directory', type=str, help=directory_help)

    args = parser.parse_args()

    directory = args.directory or getcwd()
    directory = path.abspath(directory)
    chdir(directory)

    proc = Popen(['/usr/local/opt/llvm/bin/clangd', '--background-index',
                 '-j=4'], stdout=PIPE, stdin=PIPE, stderr=PIPE)
    
    while True:
        line = proc.stderr.readline().decode('utf-8')
        if not line:
            break
        else:
            print(line)
            if 'Starting LSP over stdin/stdout' in str(line):
                break

    client = LspClient(LspEndpoint(JsonRpcEndpoint(proc.stdin, proc.stdout)))

    try:
        with open('compile_commands.json', 'r') as file:
            command = json.load(file)[0]

        with open(command.get('file'), 'r') as file:
            source = file.read()

    except FileNotFoundError as err:
        print(err)
        exit(1)

    root_uri = 'file://' + command.get('directory')
    workspace = [{"uri": root_uri, "name": "linux"}]

    file = root_uri + '/' + command.get('file')
    document = {"uri": file, "languageId": "c", "version": 1, "text": source}

    res = client.initialize(getpid(), None, root_uri,
                            None, None, None, workspace)

    client.initialized()
    res = client.didOpen(document)

    try:
        while True:
            line = proc.stderr.readline().decode('utf-8')
            if not line:
                break
            else:
                print(line)
    except KeyboardInterrupt:
        client.shutdown()
        client.exit()
    
    return 0


if __name__ == '__main__':
    exit(main())
