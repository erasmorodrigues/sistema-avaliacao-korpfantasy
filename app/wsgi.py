"""
Módulo WSGI da Aplicação.
Ponto de entrada para servidores web WSGI (wsgiref, Gunicorn, uWSGI) e roteamento de arquivos estáticos.
"""

import os
import mimetypes
from typing import Dict, Any, Callable

from app.database import init_db, seed_default_data
from app.routes import router, Request, json_response

# Diretório de arquivos estáticos
STATIC_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "static"
)

# Inicializar banco de dados e sementes ao importar o módulo
init_db()
seed_default_data()


def get_static_file(file_path: str):
    """Lê arquivo estático com segurança contra Directory Traversal."""
    # Normalizar caminho absoluto
    full_path = os.path.normpath(os.path.join(STATIC_DIR, file_path.lstrip("/")))
    if not full_path.startswith(STATIC_DIR):
        return None, None

    if os.path.isdir(full_path):
        full_path = os.path.join(full_path, "index.html")

    if not os.path.isfile(full_path):
        return None, None

    mime_type, _ = mimetypes.guess_type(full_path)
    if mime_type is None:
        if full_path.endswith(".js"):
            mime_type = "application/javascript"
        elif full_path.endswith(".css"):
            mime_type = "text/css"
        elif full_path.endswith(".html"):
            mime_type = "text/html"
        else:
            mime_type = "application/octet-stream"

    with open(full_path, "rb") as f:
        content = f.read()

    return mime_type, content


def application(environ: Dict[str, Any], start_response: Callable):
    """Função WSGI padrão em conformidade com PEP 3333."""
    req = Request(environ)

    # 1. Tratar rotas de API
    if req.path.startswith("/api/"):
        result = router.dispatch(req)
        if result is not None:
            status_code, headers, body = result
            status_str = f"{status_code} OK" if status_code == 200 else f"{status_code} Result"
            headers_list = list(headers.items())
            start_response(status_str, headers_list)
            return [body]
        else:
            status_code, headers, body = json_response({"success": False, "error": "Rota de API não encontrada."}, status=404)
            start_response("404 Not Found", list(headers.items()))
            return [body]

    # 2. Servir arquivos estáticos ou Single Page Application (SPA)
    path = req.path
    if path == "/" or path == "":
        path = "index.html"

    mime_type, content = get_static_file(path)
    if content is not None:
        headers = [
            ("Content-Type", f"{mime_type}; charset=utf-8" if "text" in mime_type or "javascript" in mime_type else mime_type),
            ("Content-Length", str(len(content))),
            ("Cache-Control", "no-cache")
        ]
        start_response("200 OK", headers)
        return [content]

    # Fallback para index.html em rotas de frontend SPA
    mime_type, content = get_static_file("index.html")
    if content is not None:
        headers = [
            ("Content-Type", "text/html; charset=utf-8"),
            ("Content-Length", str(len(content))),
            ("Cache-Control", "no-cache")
        ]
        start_response("200 OK", headers)
        return [content]

    start_response("404 Not Found", [("Content-Type", "text/plain")])
    return [b"Not Found"]
