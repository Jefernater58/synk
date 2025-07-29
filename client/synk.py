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
        self.ensure_remote_dirs(remote_filepath)
        with open(local_filepath, 'rb') as f:
            self.ftps.storbinary(f'STOR {remote_filepath}', f)

    def download(self, remote_filepath, local_filepath):
        with open(local_filepath, 'wb') as f:
            self.ftps.retrbinary(f'RETR {remote_filepath}', f.write)

    def delete(self, remote_filepath):
        self.ftps.delete(remote_filepath)

    def delete_dir(self, remote_path):
        try:
            self.ftps.rmd(remote_path)
        except ftplib.error_perm:
            # dir is not empty
            self.recursive_delete(remote_path)

    def recursive_delete(self, remote_path):
        # list all files and directories in the remote_path
        try:
            items = self.ftps.nlst(remote_path)
        except ftplib.error_perm as e:
            # directory is empty or does not exist
            items = []

        for item in items:
            # skip the directory itself
            if item == remote_path or item.rstrip('/') == remote_path.rstrip('/'):
                continue
            try:
                # try to delete as a file
                self.ftps.delete(str(Path(remote_path).joinpath(item)))
            except ftplib.error_perm:
                # if not a file, it's a directory; recurse
                self.recursive_delete(str(Path(remote_path).joinpath(item)))

        # Now delete the (now empty) directory itself
        self.ftps.rmd(remote_path)

    def make_dir(self, remote_path):
        self.ensure_remote_dirs(remote_path)
        self.ftps.mkd(remote_path)

    def ensure_remote_dirs(self, remote_filepath):
        dirs = Path(remote_filepath).parent.parts
        for i in range(1, len(dirs) + 1):
            path = '/'.join(dirs[:i])
            try:
                self.ftps.mkd(path)
            except Exception:
                pass

    def get_remote_hash(self, remote_filepath):
        resp = self.ftps.sendcmd(f"XHASH {remote_filepath}")
        print("Server file SHA256:", resp.split()[1])
        return resp

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

    print("[.] Checking files to push...")

    # generate all current file hashes and get all dirs
    current_file_hashes = generate_file_hashes(path)
    current_dirs = get_all_dirs(path)

    files_to_push = []
    files_to_delete = []

    dirs_to_create = []
    dirs_to_delete = []

    # if no index file, push everything
    if not Path("index.json").is_file():
        print("[.] first time use detected, pushing all contents...")
        files_to_push = list(current_file_hashes.keys())
        dirs_to_create = current_dirs

    else:
        # get data from index.json
        with open("index.json", "r") as indexfile:
            data = json.load(indexfile)
            old_file_hashes = data["files"]
            old_dirs = data["dirs"]

        # get all the files that have been changed, or are new
        for file in current_file_hashes.keys():
            # if the file has changed or is new
            if (file in old_file_hashes and current_file_hashes[file] != old_file_hashes[file]) or file not in old_file_hashes:
                files_to_push.append(file)

        # get all files that have been deleted
        for file in old_file_hashes.keys():
            # if the file does not exist
            if file not in current_file_hashes:
                files_to_delete.append(file)

        # get all the dirs that are new
        for directory in current_dirs:
            if directory not in old_dirs:
                dirs_to_create.append(directory)

        # get all the dirs that are deleted
        for directory in old_dirs:
            if directory not in current_dirs:
                dirs_to_delete.append(directory)

    with open("index.json", "w") as indexfile:
        json.dump({"files": current_file_hashes, "dirs": current_dirs}, indexfile)

    # keep only deepest dirs in dirs_to_create, and remove any dir if a file to push is inside it
    filtered_dirs = []
    for directory in dirs_to_create:
        # skip this dir if any file to push is inside it (or is the dir itself)
        if any(Path(f).is_relative_to(directory) for f in files_to_push):
            continue
        if not any(
            other != directory and Path(other).is_relative_to(directory)
            for other in dirs_to_create
        ):
            filtered_dirs.append(directory)
    dirs_to_create[:] = filtered_dirs

    # keep only shallowest directories in dirs_to_delete
    filtered_delete_dirs = []
    for directory in dirs_to_delete:
        if not any(
            other != directory and Path(directory).is_relative_to(other)
            for other in dirs_to_delete
        ):
            filtered_delete_dirs.append(directory)
    dirs_to_delete[:] = filtered_delete_dirs

    # remove files from files_to_delete that are inside any dir to delete
    files_to_delete[:] = [
        f for f in files_to_delete
        if not any(Path(f).is_relative_to(dir_) for dir_ in dirs_to_delete)
    ]

    print("[.] Attempting to connect to the server...")
    client = FTPClient()
    client.connect(remote, int(port), username, password)

    print("[.] Pushing to remote...")
    for directory in dirs_to_delete:
        client.delete_dir(directory)
    for file in files_to_delete:
        client.delete(file)

    for directory in dirs_to_create:
        client.make_dir(directory)
    local_path = Path(path)
    for file in files_to_push:
        client.upload(local_path.joinpath(file), file)

    print("[.] Closing connection to the server...")
    client.close()
    print("[.] Push operation completed successfully.")


def pull(args):
    path, remote, port, username, password = get_config()

    print("[.] Attempting to connect to the server...")
    client = FTPClient()
    client.connect(remote, int(port), username, password)

    print("[.] Pulling from remote...")
    print(client.get_remote_hash("testing.sigma"))


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
