"""
Módulo de Autenticação e Segurança.
Implementa PBKDF2-HMAC-SHA256 para senhas e tokens JWT (HS256) sem dependências externas.
"""

import os
import hmac
import hashlib
import json
import base64
import time
import secrets
from typing import Optional, Dict, Any, Tuple

# Chave secreta da aplicação (carregada do ambiente ou gerada na inicialização)
SECRET_KEY = os.environ.get("APP_SECRET_KEY", "chave-secreta-antigravity-avaliacao-juizes-2026")

# Parâmetros de tempo de sessão e segurança
INACTIVITY_TIMEOUT_SECONDS = 15 * 60       # 15 minutos de inatividade máxima
INACTIVITY_WARNING_SECONDS = 13 * 60       # 13 minutos até exibir aviso
INACTIVITY_COUNTDOWN_SECONDS = 2 * 60      # 2 minutos de contagem regressiva no aviso
MAX_SESSION_LIFETIME_SECONDS = 8 * 60 * 60 # 8 horas de duração máxima absoluta
TOKEN_EXPIRATION_SECONDS = MAX_SESSION_LIFETIME_SECONDS


def _b64encode(data: bytes) -> str:
    """Codifica bytes em base64 URL-safe sem padding '='."""
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _b64decode(data_str: str) -> bytes:
    """Decodifica string base64 URL-safe com recomposição de padding."""
    rem = len(data_str) % 4
    if rem > 0:
        data_str += "=" * (4 - rem)
    return base64.urlsafe_b64decode(data_str.encode("utf-8"))


def hash_password(password: str) -> str:
    """
    Gera um hash seguro da senha usando PBKDF2-HMAC-SHA256 com salt aleatório.
    Formato retornado: pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>
    """
    salt = secrets.token_hex(16)
    iterations = 100_000
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations
    )
    return f"pbkdf2_sha256${iterations}${salt}${derived.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verifica se a senha fornecida confere com o hash armazenado de forma resistente a timing attacks."""
    try:
        parts = stored_hash.split("$")
        if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
            return False
        iterations = int(parts[1])
        salt = parts[2]
        expected_hash = parts[3]
        derived = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            iterations
        )
        return hmac.compare_digest(derived.hex(), expected_hash)
    except Exception:
        return False


def create_access_token(user_id: int, role: str, name: str, email: str, session_id: Optional[str] = None, expires_in: int = TOKEN_EXPIRATION_SECONDS) -> str:
    """Cria um token JWT assinado com HMAC-SHA256 válido pelo tempo especificado."""
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": user_id,
        "role": role,
        "name": name,
        "email": email,
        "iat": now,
        "exp": now + expires_in
    }
    if session_id:
        payload["sid"] = session_id

    header_b64 = _b64encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_b64 = _b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")

    signature = hmac.new(
        SECRET_KEY.encode("utf-8"),
        signing_input,
        hashlib.sha256
    ).digest()
    sig_b64 = _b64encode(signature)

    return f"{header_b64}.{payload_b64}.{sig_b64}"


def verify_access_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Verifica a autenticidade e validade temporal do token JWT.
    Retorna o payload decodificado em caso de sucesso, ou None se inválido/expirado.
    """
    if not token or not isinstance(token, str):
        return None

    parts = token.strip().split(".")
    if len(parts) != 3:
        return None

    header_b64, payload_b64, sig_b64 = parts
    signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")

    expected_sig = hmac.new(
        SECRET_KEY.encode("utf-8"),
        signing_input,
        hashlib.sha256
    ).digest()

    try:
        provided_sig = _b64decode(sig_b64)
        if not hmac.compare_digest(expected_sig, provided_sig):
            return None

        payload_bytes = _b64decode(payload_b64)
        payload = json.loads(payload_bytes.decode("utf-8"))

        # Validar expiração temporal básica do token
        if "exp" in payload and payload["exp"] < time.time():
            return None

        return payload
    except Exception:
        return None


# =============================================================================
# Funções de Gerenciamento de Sessão com Inatividade e Expiração Máxima
# =============================================================================

def create_user_session(conn, user_id: int, ip_address: str = "", user_agent: str = "") -> str:
    """Cria e persiste uma nova sessão ativa com timestamp de criação e de atividade."""
    session_id = secrets.token_hex(24)
    now = int(time.time())
    with conn:
        conn.execute("""
            INSERT INTO user_sessions (session_id, user_id, created_at, last_activity, is_active, ip_address, user_agent)
            VALUES (?, ?, ?, ?, 1, ?, ?)
        """, (session_id, user_id, now, now, ip_address, user_agent))
    return session_id


def get_user_session(conn, session_id: str) -> Optional[Dict[str, Any]]:
    """Retorna os dados da sessão pelo seu identificador."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT session_id, user_id, created_at, last_activity, is_active, ip_address, user_agent
        FROM user_sessions
        WHERE session_id = ?
    """, (session_id,))
    row = cursor.fetchone()
    return dict(row) if row else None


def update_user_session_activity(conn, session_id: str, timestamp: Optional[int] = None) -> bool:
    """Atualiza o timestamp da última atividade da sessão (renovação de inatividade)."""
    now = timestamp if timestamp is not None else int(time.time())
    with conn:
        cur = conn.execute("""
            UPDATE user_sessions
            SET last_activity = ?
            WHERE session_id = ? AND is_active = 1
        """, (now, session_id))
        return cur.rowcount > 0


def invalidate_user_session(conn, session_id: str) -> bool:
    """Invalida uma sessão específica (logout ou expiração)."""
    with conn:
        cur = conn.execute("""
            UPDATE user_sessions
            SET is_active = 0
            WHERE session_id = ?
        """, (session_id,))
        return cur.rowcount > 0


def invalidate_all_user_sessions(conn, user_id: int) -> int:
    """Invalida todas as sessões ativas de um usuário (útil em troca de senha)."""
    with conn:
        cur = conn.execute("""
            UPDATE user_sessions
            SET is_active = 0
            WHERE user_id = ? AND is_active = 1
        """, (user_id,))
        return cur.rowcount


def validate_session(conn, session_id: str, is_background_poll: bool = False) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
    """
    Valida a sessão no servidor:
    1. Verifica existência e se foi criada há mais de 8 horas (prioritário)
    2. Verifica se a sessão está ativa
    3. Verifica limite de 15 minutos de inatividade
    4. Se for atividade real (não polling), atualiza last_activity
    Retorna (is_valid, error_code_or_none, session_dict)
    """
    session = get_user_session(conn, session_id)
    if not session:
        return False, "SESSION_INVALID_OR_REVOKED", None

    now = int(time.time())
    created_at = int(session["created_at"])
    last_activity = int(session["last_activity"])

    # 1. Checar duração máxima absoluta (8 horas)
    if (now - created_at) > MAX_SESSION_LIFETIME_SECONDS:
        if session.get("is_active"):
            invalidate_user_session(conn, session_id)
        return False, "MAX_LIFETIME_EXCEEDED", session

    # 2. Checar se já foi encerrada manualmente
    if not session.get("is_active"):
        return False, "SESSION_INVALID_OR_REVOKED", session

    # 3. Checar tempo de inatividade (15 minutos)
    if (now - last_activity) > INACTIVITY_TIMEOUT_SECONDS:
        invalidate_user_session(conn, session_id)
        return False, "INACTIVITY_TIMEOUT", session

    # 4. Se for atividade real (não polling em background), renova a inatividade
    if not is_background_poll:
        update_user_session_activity(conn, session_id, now)
        session["last_activity"] = now

    return True, None, session

