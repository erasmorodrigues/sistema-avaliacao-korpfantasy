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
from typing import Optional, Dict, Any

# Chave secreta da aplicação (carregada do ambiente ou gerada na inicialização)
SECRET_KEY = os.environ.get("APP_SECRET_KEY", "chave-secreta-antigravity-avaliacao-juizes-2026")
TOKEN_EXPIRATION_SECONDS = 60 * 60 * 24  # 24 horas


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


def create_access_token(user_id: int, role: str, name: str, email: str, expires_in: int = TOKEN_EXPIRATION_SECONDS) -> str:
    """Cria um token JWT assinado com HMAC-SHA256 válido pelo tempo especificado."""
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": user_id,
        "role": role,
        "name": name,
        "email": email,
        "iat": int(time.time()),
        "exp": int(time.time()) + expires_in
    }

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

        # Validar expiração
        if "exp" in payload and payload["exp"] < time.time():
            return None

        return payload
    except Exception:
        return None
