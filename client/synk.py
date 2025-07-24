import argparse
import getpass
import configparser
import json
import hashlib
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

    def upload(self, local_filepath, remote_filepath):
        # TODO if there is a dir on remote of same name, delete that first
        self.ensure_remote_dirs(remote_filepath)
        with open(local_filepath, 'rb') as f:
            self.ftps.storbinary(f'STOR {remote_filepath}', f)

    def download(self, remote_filepath, local_filepath):
        with open(local_filepath, 'wb') as f:
            self.ftps.retrbinary(f'RETR {remote_filepath}', f.write)

    def delete(self, remote_filepath):
        self.ftps.delete(remote_filepath)

    def delete_dir(self, remote_path):
        self.ftps.rmd(remote_path)

    def make_dir(self, remote_path):
        self.ensure_remote_dirs(remote_path)
        try:
            self.ftps.mkd(remote_path)
        except ftplib.error_perm:
            pass

    def ensure_remote_dirs(self, remote_filepath):
        dirs = Path(remote_filepath).parent.parts
        for i in range(1, len(dirs) + 1):
            path = '/'.join(dirs[:i])
            try:
                self.ftps.mkd(path)
            except Exception:
                pass

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


def generate_file_hashes(path):
    file_dict = {}
    for directory, subdirectories, files in Path(path).walk():
        for file in files:
            h = hashlib.sha256()
            absolute = str(directory.joinpath(file))

            with open(absolute, 'rb') as f:
                while chunk := f.read(8192):
                    h.update(chunk)

            relative = Path(absolute).relative_to(path).as_posix()
            file_dict[relative] = h.hexdigest()

    return file_dict


def get_all_dirs(path):
    dirs = []
    for directory, _, _ in Path(path).walk():
        if Path(path) == Path(directory):
            continue
        dirs.append(Path(directory).relative_to(path).as_posix())

    return dirs


def push(args):
    path, remote, port, username, password = get_config()
    path_obj = Path(path)

    print("[.] checking files to push...")
    new_file_hashes = generate_file_hashes(path)

    if not Path("index.json").is_file():
        print("[.] First use detected, pushing all files to remote.")
        edited_files = []
        deleted_files = []
        new_files = list(new_file_hashes.keys())

        new_dirs = get_all_dirs(path)
        current_dirs = new_dirs
        deleted_dirs = []

    else:
        with open("index.json", "r") as indexfile:
            data = json.load(indexfile)
            old_file_hashes = data["files"]
            old_dirs = data["dirs"]

        edited_files = []
        deleted_files = []
        new_files = []
        for file in old_file_hashes.keys():
            if file in new_file_hashes:
                if old_file_hashes[file] != new_file_hashes[file]:
                    edited_files.append(file)
            else:
                deleted_files.append(file)
        for file in new_file_hashes.keys():
            if file not in old_file_hashes:
                new_files.append(file)

        current_dirs = get_all_dirs(path)
        new_dirs = []
        for d in current_dirs:
            if d not in old_dirs:
                new_dirs.append(d)
        deleted_dirs = []
        for d in old_dirs:
            if d not in current_dirs:
                deleted_dirs.append(d)

    with open("index.json", "w") as indexfile:
        json.dump({"files": new_file_hashes, "dirs": current_dirs}, indexfile)

    print("[.] Attempting to connect to the server...")
    client = FTPClient()
    client.connect(remote, int(port), username, password)
    print("[.] Connection established.")

    for d in new_dirs:
        client.make_dir(d)

    for file in new_files + edited_files:
        client.upload(str(path_obj.joinpath(file).as_posix()), file)

    for file in deleted_files:
        client.delete(file)

    for d in deleted_dirs:
        client.delete_dir(d)

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
