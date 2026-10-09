#!/usr/bin/env python3
"""
Utilitário de Linha de Comando (CLI) para Administração e Operação do Sistema.
Comandos disponíveis:
  python manage.py runserver [port]
  python manage.py createadmin <email> <nome> <senha>
  python manage.py createjudge <email> <nome> <senha>
  python manage.py seed
  python manage.py resetdb
  python manage.py test
"""

import sys
import os
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app.database import get_db_connection, init_db, seed_default_data, DEFAULT_DB_PATH
from app.auth import hash_password


def cmd_runserver(args):
    port = int(args[0]) if args else int(os.environ.get("PORT", "8000"))
    host = os.environ.get("HOST", "127.0.0.1")
    from server import run_server
    run_server(host, port)


def cmd_createadmin(args):
    if len(args) < 3:
        print("Uso: python manage.py createadmin <email> <nome> <senha>")
        sys.exit(1)

    email = args[0].strip().lower()
    name = args[1].strip()
    password = args[2]

    init_db()
    pwd_hash = hash_password(password)
    now = datetime.utcnow().isoformat()

    conn = get_db_connection()
    try:
        with conn:
            conn.execute("""
                INSERT INTO users (name, email, password_hash, role, active, created_at, updated_at)
                VALUES (?, ?, ?, 'ADMIN', 1, ?, ?)
                ON CONFLICT(email) DO UPDATE SET
                    name = excluded.name,
                    password_hash = excluded.password_hash,
                    role = 'ADMIN',
                    active = 1,
                    updated_at = excluded.updated_at
            """, (name, email, pwd_hash, now, now))
        print(f"✓ Administrador '{name}' ({email}) configurado com sucesso!")
    finally:
        conn.close()


def cmd_createjudge(args):
    if len(args) < 3:
        print("Uso: python manage.py createjudge <email> <nome> <senha>")
        sys.exit(1)

    email = args[0].strip().lower()
    name = args[1].strip()
    password = args[2]

    init_db()
    pwd_hash = hash_password(password)
    now = datetime.utcnow().isoformat()

    conn = get_db_connection()
    try:
        with conn:
            conn.execute("""
                INSERT INTO users (name, email, password_hash, role, active, created_at, updated_at)
                VALUES (?, ?, ?, 'JUDGE', 1, ?, ?)
                ON CONFLICT(email) DO UPDATE SET
                    name = excluded.name,
                    password_hash = excluded.password_hash,
                    role = 'JUDGE',
                    active = 1,
                    updated_at = excluded.updated_at
            """, (name, email, pwd_hash, now, now))
        print(f"✓ Juiz '{name}' ({email}) cadastrado com sucesso!")
    finally:
        conn.close()


def cmd_seed(args):
    init_db()
    seed_default_data(force=True)
    print("✓ Banco de dados populado com dados padrão de demonstração.")


def cmd_resetdb(args):
    db_file = os.environ.get("DATABASE_PATH", DEFAULT_DB_PATH)
    if os.path.exists(db_file):
        os.remove(db_file)
        print(f"Arquivo de banco de dados '{db_file}' removido.")
    init_db()
    seed_default_data(force=True)
    print("✓ Banco de dados reinicializado e populado com sucesso.")


def cmd_test(args):
    import unittest
    loader = unittest.TestLoader()
    suite = loader.discover("tests")
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)


COMMANDS = {
    "runserver": cmd_runserver,
    "createadmin": cmd_createadmin,
    "createjudge": cmd_createjudge,
    "seed": cmd_seed,
    "resetdb": cmd_resetdb,
    "test": cmd_test
}


def print_help():
    print(__doc__)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print_help()
        sys.exit(1)

    cmd = sys.argv[1].lower()
    if cmd in COMMANDS:
        COMMANDS[cmd](sys.argv[2:])
    else:
        print(f"Comando desconhecido: '{cmd}'")
        print_help()
        sys.exit(1)
