import argparse
import getpass
import configparser
from pathlib import Path
import ftplib


class FTPClient:
    def __init__(self):
        self.ftps = ftplib.FTP_TLS()

    def connect(self, remote, port, username, password):
        try:
            self.ftps.connect(remote, port)
            self.ftps.auth()
            self.ftps.prot_p()
            self.ftps.login(username, password)
            return
        except ConnectionRefusedError as e:
            print("[!] Error: the server refused connection. Make sure the remote address and port are correct, and the server is up.\n" + str(e))
        except ftplib.error_perm as e:
            print("[!] Error: authentication failed, the username does not exist or the password is incorrect.\n" + str(e))
        except Exception as e:
            print("[!] Error: an unknown error has occurred when connecting to the server.\n" + str(e))
        exit(1)

    def close(self):
        self.ftps.quit()


def get_config():
    if Path("config.ini").is_file():
        try:
            config = configparser.ConfigParser()
            config.read('config.ini')

            path = config.get('general', 'path')
            remote = config.get('general', 'remote')
            port = config.get('general', 'port')
            username = config.get('auth', 'username')
            password = config.get('auth', 'password')
        except configparser.Error as e:
            print("[!] Error: invalid or incomplete config file. Maybe try 'synk init' first.\n" + str(e))
            exit(1)

        return path, remote, port, username, password

    print("[!] Error: config file does not exist. Maybe try 'synk init' first.")
    exit(1)


def init(args):
    if args.path is None:
        path = Path(
            input("[?] Local path was not specified. Please specify the path to use as the root for FTP users.\n> "))
    else:
        path = Path(args.path)
    # make the path absolute and resolve symlinks
    path = path.resolve(strict=False)
    # create the directory if it doesn't exist
    if not path.is_dir():
        print("[.] Given directory does not exist, making new directory.")
        path.mkdir(parents=True, exist_ok=True)

    remote = args.remote or input("[?] Remote was not specified. Please enter the address of the FTP server.\n> ")

    if args.port is None:
        port = input("[?] Port was not specified. Please enter the port of the FTP server. (22)\n> ")
        port = port if port != "" else "22"
    else:
        port = args.port
    # check the port is an integer
    if not port.isdigit() or not 1 <= int(port) <= 65535:
        print("[!] Error: The port must be a numerical value 1-65535.")
        return

    username = args.username or input("[?] Username was not specified. Please enter the username for the FTP server.\n> ")
    password = args.password or getpass.getpass(
        "[?] Password was not specified. Please enter the password for the FTP server.\n> ")

    config = configparser.ConfigParser()
    config['general'] = {'path': path, 'remote': remote, 'port': port}
    config['auth'] = {'username': username, 'password': password}
    with open('config.ini', 'w') as configfile:
        config.write(configfile)

    print("[.] synk has been successfully initialised.")


def push(args):
    path, remote, port, username, password = get_config()

    print("[.] Attempting to connect to the server...")
    client = FTPClient()
    client.connect(remote, int(port), username, password)
    print("[.] Connection established.")

    # in order to keep track of changes, i will store filenames in a file along with a hash

    print("[.] Closing connection to the server...")
    client.close()
    print("[.] Push operation completed successfully.")


def pull(args):
    path, remote, port, username, password = get_config()

    # do the FTP stuff here :)
    print(path, remote, port, username, password)


def status(args):
    print("status", args)


parser = argparse.ArgumentParser(prog="synk", description="Back up your files to your own server with ease.")
subparsers = parser.add_subparsers(title='Commands', dest='command', required=True)

parser_init = subparsers.add_parser('init', help='Initialize the client')
parser_init.add_argument('path', nargs="?", default=None, help='Local path to sync')
parser_init.add_argument('remote', nargs="?", default=None, help='Remote location (FTP server address)')
parser_init.add_argument('port', nargs="?", default=None, help='The port the remote is hosted on')
parser_init.add_argument('username', nargs="?", default=None, help='The username for the FTP server')
parser_init.add_argument('password', nargs="?", default=None, help='The password for the FTP server')
parser_init.set_defaults(func=init)

parser_push = subparsers.add_parser('push', help='Push changes to remote')
parser_push.set_defaults(func=push)
parser_pull = subparsers.add_parser('pull', help='Pull changes from remote')
parser_pull.set_defaults(func=pull)
parser_status = subparsers.add_parser('status', help='Show sync status')
parser_status.set_defaults(func=status)

args = parser.parse_args()
args.func(args)
