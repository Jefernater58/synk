import argparse
import getpass
import configparser
from pathlib import Path


def get_config():
    try:
        config = configparser.ConfigParser()
        config.read('config.ini')

        path = config.get('general', 'path')
        remote = config.get('general', 'remote')
        port = config.get('general', 'port')
        username = config.get('auth', 'username')
        password = config.get('auth', 'password')
    except configparser.Error as e:
        print("Error: missing or invalid config.ini. Maybe try 'synk init'.\n" + str(e))
        exit()

    return path, remote, port, username, password


def init(args):
    if args.path is None:
        path = Path(
            input("Local path was not specified. Please specify the local path to sync its contents with remote.\n> "))
    else:
        path = Path(args.path)
    # make the path absolute and resolve symlinks
    path = path.resolve(strict=False)
    # create the directory if it doesn't exist
    if not path.is_dir():
        print("Given directory does not exist, making new directory.")
        path.mkdir(parents=True, exist_ok=True)

    remote = args.remote or input("Remote was not specified. Please enter the address of the SFTP server\n> ")

    if args.port is None:
        port = input("Port was not specified. Please enter the port of the SFTP server (22)\n> ")
        port = port if port != "" else "22"
    else:
        port = args.port
    # check the port is an integer
    if not port.isdigit() or not 1 <= int(port) <= 65535:
        print("The port must be a numerical value 1-65535.")
        return

    username = args.username or input("Username was not specified. Please enter the username for the SFTP server\n> ")
    password = args.password or getpass.getpass(
        "Password was not specified. Please enter the password for the SFTP server\n> ")

    config = configparser.ConfigParser()
    config['general'] = {'path': path, 'remote': remote, 'port': port}
    config['auth'] = {'username': username, 'password': password}
    with open('config.ini', 'w') as configfile:
        config.write(configfile)


def push(args):
    path, remote, port, username, password = get_config()

    # do the sftp stuff here :)
    print(path, remote, port, username, password)


def pull(args):
    path, remote, port, username, password = get_config()

    # do the sftp stuff here :)
    print(path, remote, port, username, password)


def status(args):
    print("status", args)


# parse args
parser = argparse.ArgumentParser(prog="synk", description="Back up your files to your own server with ease.")
subparsers = parser.add_subparsers(title='Commands', dest='command')
subparsers.required = True

parser_init = subparsers.add_parser('init', help='Initialize the client')
parser_init.add_argument('path', nargs="?", default=None, help='Local folder path to sync')
parser_init.add_argument('remote', nargs="?", default=None, help='Remote location (SFTP server address)')
parser_init.add_argument('port', nargs="?", default=None, help='The port the remote is hosted on')
parser_init.add_argument('username', nargs="?", default=None, help='The username for the SFTP server')
parser_init.add_argument('password', nargs="?", default=None, help='The password for the SFTP server')
parser_init.set_defaults(func=init)

parser_push = subparsers.add_parser('push', help='Push changes to remote')
parser_push.set_defaults(func=push)
parser_pull = subparsers.add_parser('pull', help='Pull changes from remote')
parser_pull.set_defaults(func=pull)
parser_status = subparsers.add_parser('status', help='Show sync status')
parser_status.set_defaults(func=status)

args = parser.parse_args()
args.func(args)
