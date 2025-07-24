import generate_keys
import configparser
import getpass
import argparse
import tabulate
import json
from pathlib import Path
from pyftpdlib.authorizers import DummyAuthorizer
from pyftpdlib.handlers import TLS_FTPHandler
from pyftpdlib.servers import FTPServer


def get_config():
    if Path("config.ini").is_file():
        try:
            config = configparser.ConfigParser()
            config.read('config.ini')

            path = config.get('general', 'path')
            port = config.get('general', 'port')
        except configparser.Error as e:
            print("[!] Error: invalid or incomplete config file. Maybe try 'synk init' first.\n" + str(e))
            exit(1)

        return path, port

    print("[!] Error: config file does not exist. Maybe try 'synk init' first.")
    exit(1)


def get_users():
    if Path("users.json").is_file():
        try:
            with open("users.json", "r") as usersfile:
                users_json = json.load(usersfile)
            return users_json["users"]
        except (json.JSONDecodeError, KeyError) as e:
            print("[!] Error: users file is invalid. Maybe try 'synk-server init' first.\n" + str(e))
            exit(1)
    print("[!] Error: users file does not exist. Maybe try 'synk-server init' first.")
    exit(1)


def set_users(users):
    with open("users.json", "w") as usersfile:
        json.dump({"users": users}, usersfile)


def init(args):
    if args.path is None:
        path = Path(
            input("[?] Root path was not specified. Please specify the local path to sync its contents with remote.\n> "))
    else:
        path = Path(args.path)
    # make the path absolute and resolve symlinks
    path = path.resolve(strict=False)
    # create the directory if it doesn't exist
    if not path.is_dir():
        print("[.] Given directory does not exist, making new directory.")
        path.mkdir(parents=True, exist_ok=True)

    if args.port is None:
        port = input("[?] Port was not specified. Please enter the port to host the server on. (22)\n> ")
        port = port if port != "" else "22"
    else:
        port = args.port
    # check the port is an integer
    if not port.isdigit() or not 1 <= int(port) <= 65535:
        print("[!] Error: The port must be a numerical value 1-65535.")
        return

    config = configparser.ConfigParser()
    config['general'] = {'path': path, 'port': port}
    with open('config.ini', 'w') as configfile:
        config.write(configfile)

    if not Path("users.json").is_file():
        with open("users.json", "w") as usersfile:
            usersfile.write('{"users": []}')

    print("[.] Generating SSL certificate...")
    generate_keys.generate_keys()
    print("[.] synk-server has been successfully initialised.")


def start(args):
    path, port = get_config()
    users = get_users()

    print("[.] creating the server...")
    authorizer = DummyAuthorizer()
    ftp_root = Path(path)
    ftp_root.mkdir(parents=True, exist_ok=True)

    for user in users:
        authorizer.add_user(user["username"], user["password"], ftp_root.joinpath(user["root"]), perm="elradfmwMT")

    handler = TLS_FTPHandler
    handler.certfile = "cert.pem"
    handler.keyfile = "key.pem"
    handler.authorizer = authorizer

    handler.tls_control_required = True
    handler.tls_data_required = True

    handler.passive_ports = range(60000, 60010)

    print("[.] starting the server...")
    server = FTPServer(("0.0.0.0", int(port)), handler)
    server.serve_forever()


def stop(args):
    pass


def user_list(args):
    users = get_users()
    print(tabulate.tabulate(users, headers="keys", tablefmt="fancy_outline"))


def user_add(args):
    path, _ = get_config()

    username = args.username or input("[?] Username was not specified. Please enter the username for the new user\n> ")
    password = args.password or getpass.getpass("[?] Password was not specified. Please enter the password for the new user\n> ")
    if args.root is None:
        root = input(f"[?] Root was not specified. Please enter the root directory name for the new user. ({username})\n> ")
        if root == "":
            root = username
    else:
        root = args.root

    root_path = Path(path).joinpath(root)
    if not root_path.is_dir():
        print("[.] Given root directory does not exist, making new directory.")
        root_path.mkdir(parents=True, exist_ok=True)

    users = get_users()
    users.append({"username": username, "password": password, "root": root})

    set_users(users)
    print("[.] Added new user '" + username + "' to the server.")


def user_remove(args):
    username = args.username or input("[?] Username was not specified. Please enter the username of the user to remove\n> ")

    users = get_users()
    new_users = [user for user in users if user["username"] != username]

    set_users(new_users)
    print("[.] Removed user '" + username + "' from the server.")


parser = argparse.ArgumentParser(prog="synk-server", description="Back up your files to your own server with ease.")
subparsers = parser.add_subparsers(title='Commands', dest='command', required=True)

parser_init = subparsers.add_parser('init', help='Initialize the server')
parser_init.add_argument('path', nargs="?", default=None, help='Root path to use for the server')
parser_init.add_argument('port', nargs="?", default=None, help='The port to host the server on')
parser_init.set_defaults(func=init)

parser_start = subparsers.add_parser('start', help='Start the server')
parser_start.set_defaults(func=start)

parser_stop = subparsers.add_parser('stop', help='Stop the server')
parser_stop.set_defaults(func=stop)

parser_user = subparsers.add_parser('user', help='Manage allowed users of the server')
subparsers_user = parser_user.add_subparsers(title="User Commands", dest="user_command", required=True)

parser_user_list = subparsers_user.add_parser("list", help="List the allowed users of the server")
parser_user_list.set_defaults(func=user_list)

parser_user_add = subparsers_user.add_parser("add", help="Add a new user to the server")
parser_user_add.add_argument("username", nargs="?", default=None, help="Set the username of the new user")
parser_user_add.add_argument("password", nargs="?", default=None, help="Set the password of the new user")
parser_user_add.add_argument("root", nargs="?", default=None, help="Set the root directory for the new user")
parser_user_add.set_defaults(func=user_add)

parser_user_remove = subparsers_user.add_parser("remove", help="Remove an existing user from the server")
parser_user_remove.add_argument("username", nargs="?", default=None, help="The username of the user to remove")
parser_user_remove.set_defaults(func=user_remove)


args = parser.parse_args()
args.func(args)
