"""
Módulo de Banco de Dados SQLite.
Gerencia conexão, criação de tabelas, índices e dados iniciais (seeding).
"""

import sqlite3
import os
from datetime import datetime

try:
    import zoneinfo
    TZ_BRASILIA = zoneinfo.ZoneInfo("America/Sao_Paulo")
except Exception:
    from datetime import timezone, timedelta
    TZ_BRASILIA = timezone(timedelta(hours=-3))


def get_brasilia_now_iso() -> str:
    """Retorna data/hora atual no fuso horário de Brasília (UTC-3) em formato ISO 8601."""
    return datetime.now(TZ_BRASILIA).isoformat()

DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "sistema_avaliacao.db"
)

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- Configurações globais do sistema e do evento
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Usuários: Administrador e Juízes
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('ADMIN', 'JUDGE')),
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Campanhas de votação (permite iniciar do zero e alternar eventos/etapas)
CREATE TABLE IF NOT EXISTS campaigns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Candidatos cadastrados (sem login ou acesso ao sistema)
CREATE TABLE IF NOT EXISTS candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id INTEGER NOT NULL DEFAULT 1 REFERENCES campaigns(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    number TEXT,
    photo_url TEXT,
    description TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Categorias de avaliação definidas pelo administrador
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    weight REAL NOT NULL DEFAULT 1.0,
    display_order INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Avaliações: notas individuais de 1 a 10 por juiz, candidato e categoria
CREATE TABLE IF NOT EXISTS evaluations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    judge_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    candidate_id INTEGER NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
    category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE RESTRICT,
    score INTEGER NOT NULL CHECK (score >= 1 AND score <= 10),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(judge_id, candidate_id, category_id)
);

-- Status de submissão do candidato pelo juiz (controle de finalização)
CREATE TABLE IF NOT EXISTS candidate_submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    judge_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    candidate_id INTEGER NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK (status IN ('PENDING', 'COMPLETED')),
    submitted_at TEXT NOT NULL,
    UNIQUE(judge_id, candidate_id)
);

-- Logs de auditoria para ações administrativas e eventos
CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    user_name TEXT,
    action TEXT NOT NULL,
    details TEXT,
    ip_address TEXT,
    created_at TEXT NOT NULL
);

-- Índices para otimização de consultas frequentes
CREATE INDEX IF NOT EXISTS idx_evaluations_candidate ON evaluations(candidate_id);
CREATE INDEX IF NOT EXISTS idx_evaluations_judge ON evaluations(judge_id);
CREATE INDEX IF NOT EXISTS idx_evaluations_category ON evaluations(category_id);
CREATE INDEX IF NOT EXISTS idx_submissions_judge ON candidate_submissions(judge_id);
CREATE INDEX IF NOT EXISTS idx_submissions_status ON candidate_submissions(status);
"""


def get_db_connection(db_path: str = None) -> sqlite3.Connection:
    """Retorna uma conexão SQLite com suporte a dicionários (Row factory)."""
    if db_path is None:
        db_path = os.environ.get("DATABASE_PATH", DEFAULT_DB_PATH)
    
    conn = sqlite3.connect(db_path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(db_path: str = None):
    """Inicializa as tabelas do banco de dados caso não existam."""
    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.executescript(SCHEMA_SQL)
            
            now = get_brasilia_now_iso()
            
            # Garantir migração da coluna campaign_id na tabela candidates
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(candidates)")
            candidate_cols = [col[1] for col in cursor.fetchall()]
            if "campaign_id" not in candidate_cols and "candidates" in [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]:
                cursor.execute("ALTER TABLE candidates ADD COLUMN campaign_id INTEGER DEFAULT 1")
                cursor.execute("UPDATE candidates SET campaign_id = 1 WHERE campaign_id IS NULL")

            # Garantir existência da campanha padrão inicial
            cursor.execute("SELECT COUNT(*) FROM campaigns")
            if cursor.fetchone()[0] == 0:
                cursor.execute("""
                    INSERT INTO campaigns (id, name, description, status, created_at, updated_at)
                    VALUES (1, 'Campanha Principal', 'Campanha de avaliação inicial', 'ACTIVE', ?, ?)
                """, (now, now))

            # Inicializar configurações padrões se não existirem
            default_settings = [
                ("event_name", "Grande Festival de Talentos 2026", now),
                ("active_campaign_id", "1", now),  # ID da campanha ativa
                ("voting_status", "OPEN", now),  # OPEN, CLOSED, PAUSED
                ("allow_corrections", "true", now),  # Permitir juiz alterar nota antes de encerrar
                ("public_results_published", "false", now),  # Divulgar resultado oficial
                ("show_provisional_winner", "true", now),  # Mostrar vencedor provisório no admin
            ]
            for key, val, updated in default_settings:
                conn.execute(
                    "INSERT OR IGNORE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
                    (key, val, updated)
                )
    finally:
        conn.close()


def seed_default_data(db_path: str = None, force: bool = False):
    """
    Popula dados de demonstração iniciais caso a base esteja vazia:
    - 1 Administrador (admin@sistema.com / admin123)
    - 3 Juízes (juiz1@sistema.com / juiz123, etc.)
    - 3 Categorias de exemplo (Criatividade, Figurino, Apresentação)
    - 4 Candidatos de exemplo
    """
    from app.auth import hash_password

    conn = get_db_connection(db_path)
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM users")
            user_count = cursor.fetchone()[0]

            if user_count > 0 and not force:
                return  # Já possui usuários, não sobrescrever

            now = get_brasilia_now_iso()

            # 1. Administrador padrão
            admin_pwd = hash_password("admin123")
            cursor.execute("""
                INSERT OR REPLACE INTO users (name, email, password_hash, role, active, created_at, updated_at)
                VALUES (?, ?, ?, 'ADMIN', 1, ?, ?)
            """, ("Administrador Geral", "admin@sistema.com", admin_pwd, now, now))

            # 2. Juízes iniciais
            judge_pwd = hash_password("juiz123")
            judges = [
                ("Dra. Helena Martins", "helena@sistema.com"),
                ("Prof. Carlos Eduardo", "carlos@sistema.com"),
                ("Dra. Beatriz Albuquerque", "beatriz@sistema.com")
            ]
            for name, email in judges:
                cursor.execute("""
                    INSERT OR REPLACE INTO users (name, email, password_hash, role, active, created_at, updated_at)
                    VALUES (?, ?, ?, 'JUDGE', 1, ?, ?)
                """, (name, email, judge_pwd, now, now))

            # 3. Categorias iniciais solicitadas no edital (Criatividade, Figurino, Apresentação)
            cursor.execute("SELECT COUNT(*) FROM categories")
            if cursor.fetchone()[0] == 0:
                categories = [
                    ("Criatividade", "Originalidade, inovação e autenticidade da proposta.", 1),
                    ("Figurino", "Harmonia visual, acabamento e adequação da vestimenta.", 2),
                    ("Apresentação", "Postura cênica, desenvoltura e impacto perante o público.", 3)
                ]
                for name, desc, order in categories:
                    cursor.execute("""
                        INSERT INTO categories (name, description, weight, display_order, active, created_at, updated_at)
                        VALUES (?, ?, 1.0, ?, 1, ?, ?)
                    """, (name, desc, order, now, now))

            # 4. Candidatos de exemplo
            cursor.execute("SELECT COUNT(*) FROM candidates")
            if cursor.fetchone()[0] == 0:
                candidates = [
                    ("Mariana Souza", "01", "Apresentação teatral contemporânea focada em narrativa visual e dramaturgia física."),
                    ("Lucas Andrade", "02", "Performance musical autoral misturando ritmos tradicionais brasileiros e jazz."),
                    ("Camila Ramos", "03", "Dança solo contemporânea com coreografia experimental de alto impacto visual."),
                    ("Gabriel Monteiro", "04", "Interpretação poética com figurino temático confeccionado em materiais reciclados.")
                ]
                for name, num, desc in candidates:
                    cursor.execute("""
                        INSERT INTO candidates (name, number, photo_url, description, active, campaign_id, created_at, updated_at)
                        VALUES (?, ?, '', ?, 1, 1, ?, ?)
                    """, (name, num, desc, now, now))

            # Registrar log de auditoria do seed
            cursor.execute("""
                INSERT INTO audit_logs (user_id, user_name, action, details, ip_address, created_at)
                VALUES (1, 'Sistema', 'DATABASE_SEEDED', 'Inicialização com dados padrão do sistema realizada com sucesso', '127.0.0.1', ?)
            """, (now,))

    finally:
        conn.close()
