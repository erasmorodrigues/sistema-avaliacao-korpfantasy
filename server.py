"""
Servidor HTTP / WSGI Multi-threaded.
Executa a aplicação web sem necessidade de dependências externas.
"""

import os
import sys
from socketserver import ThreadingMixIn
from wsgiref.simple_server import make_server, WSGIServer, WSGIRequestHandler

# Adicionar raiz do projeto ao sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app.wsgi import application
from app.database import init_db, seed_default_data


class ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
    """Servidor WSGI com suporte a conexões concorrentes multi-threaded."""
    daemon_threads = True


class SilentRequestHandler(WSGIRequestHandler):
    """Handler com logs limpos e legíveis no terminal."""
    def log_message(self, format, *args):
        # Exibir logs de requisições no terminal
        sys.stderr.write(f"[{self.log_date_time_string()}] {args[0]} - {args[1]} (HTTP {args[2]})\n")


def run_server(host: str = "127.0.0.1", port: int = 8000):
    """Inicializa o banco de dados e executa o servidor web."""
    init_db()
    seed_default_data()

    from app.database import get_db_connection
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT name, email, role, active 
            FROM users 
            ORDER BY 
                CASE WHEN role = 'ADMIN' THEN 0 ELSE 1 END,
                id ASC
        """)
        users = [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

    admins = [u for u in users if u["role"] == "ADMIN"]
    judges = [u for u in users if u["role"] == "JUDGE"]

    print("=" * 70)
    print("  🏆 SISTEMA DE AVALIAÇÃO DE CANDIDATOS POR JUÍZES")
    print("=" * 70)
    print(f"  Servidor iniciado com sucesso!")
    print(f"  URL Local: http://{host}:{port}")
    print("-" * 70)
    print("  Usuários Cadastrados para Acesso:")
    print("  • ADMINISTRADOR (Sempre em 1º):")
    for a in admins:
        status_tag = "" if a["active"] else " (Inativo)"
        print(f"    - {a['name']}: {a['email']}{status_tag}")
    print(f"\n  • JUÍZES CADASTRADOS ({len(judges)}):")
    for j in judges:
        status_tag = "" if j["active"] else " (Inativo)"
        print(f"    - {j['name']}: {j['email']}{status_tag}")
    print("-" * 70)
    print("  Nota: Senhas padrão de demonstração: 'admin123' (Admin) e 'juiz123' (Juízes).")
    print("  Para novos usuários cadastrados pelo painel, utilize a senha definida na criação.")
    print("=" * 70)
    print("  Pressione Ctrl+C para encerrar o servidor.\n")

    httpd = make_server(host, port, application, server_class=ThreadingWSGIServer, handler_class=SilentRequestHandler)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor finalizado com sucesso.")
        httpd.server_close()


if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    run_server(host, port)
