import argparse
import getpass
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rca.auth import create_user


parser = argparse.ArgumentParser(description="Creează un utilizator RCA.")
parser.add_argument("username")
parser.add_argument(
    "role",
    choices=("problem_manager", "technical_expert"),
)
args = parser.parse_args()

password = getpass.getpass("Parola: ")
confirmation = getpass.getpass("Repetă parola: ")

if password != confirmation:
    parser.error("Parolele nu coincid.")

try:
    create_user(args.username, password, args.role)
except (ValueError, sqlite3.IntegrityError) as exc:
    parser.error(str(exc))

print(f"Utilizatorul {args.username} a fost creat cu rolul {args.role}.")