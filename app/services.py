"""
Módulo de Regras de Negócio e Serviços.
Contém a lógica de cálculo de médias, rankings, empates, estatísticas e validações.
"""

import sqlite3
from typing import Dict, Any, List, Optional, Tuple
from app.database import get_brasilia_now_iso


def log_audit(conn: sqlite3.Connection, user_id: Optional[int], user_name: Optional[str], action: str, details: str, ip_address: str = "127.0.0.1"):
    """Registra uma ação no log de auditoria."""
    now = get_brasilia_now_iso()
    conn.execute("""
        INSERT INTO audit_logs (user_id, user_name, action, details, ip_address, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (user_id, user_name or "Sistema", action, details, ip_address, now))


def get_all_settings(conn: sqlite3.Connection) -> Dict[str, str]:
    """Retorna todas as configurações do sistema em formato de dicionário."""
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM settings")
    rows = cursor.fetchall()
    return {row["key"]: row["value"] for row in rows}


def get_setting(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    """Retorna o valor de uma configuração específica."""
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    return row["value"] if row else default


def update_setting(conn: sqlite3.Connection, key: str, value: str, user_id: Optional[int] = None, user_name: Optional[str] = None):
    """Atualiza uma configuração e registra no log de auditoria."""
    now = get_brasilia_now_iso()
    with conn:
        conn.execute("""
            INSERT INTO settings (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
        """, (key, str(value), now))
        log_audit(conn, user_id, user_name, "UPDATE_SETTING", f"Configuração '{key}' alterada para '{value}'")


def get_active_campaign_id(conn: sqlite3.Connection) -> int:
    """Retorna o ID da campanha de votação ativa no momento."""
    raw = get_setting(conn, "active_campaign_id", "1")
    try:
        camp_id = int(raw)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM campaigns WHERE id = ?", (camp_id,))
        if cursor.fetchone():
            return camp_id
    except Exception:
        pass
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM campaigns ORDER BY id ASC LIMIT 1")
    row = cursor.fetchone()
    return row[0] if row else 1


def get_active_campaign(conn: sqlite3.Connection) -> Dict[str, Any]:
    """Retorna os dados da campanha ativa."""
    camp_id = get_active_campaign_id(conn)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, description, status, created_at FROM campaigns WHERE id = ?", (camp_id,))
    row = cursor.fetchone()
    if row:
        return dict(row)
    return {"id": 1, "name": "Campanha Principal", "description": "", "status": "ACTIVE", "created_at": ""}


def get_dashboard_stats(conn: sqlite3.Connection, campaign_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Retorna métricas consolidadas do painel administrativo:
    - Quantidade total de candidatos cadastrados na campanha
    - Quantidade total de juízes cadastrados
    - Quantidade de categorias ativas
    - Quantidade de avaliações realizadas e pendentes
    - Percentual de conclusão da votação
    - Status atual da votação
    - Informações da campanha ativa
    """
    cursor = conn.cursor()
    if campaign_id is None:
        campaign_id = get_active_campaign_id(conn)
    active_campaign = get_active_campaign(conn)

    # Contagem de candidatos ativos da campanha
    cursor.execute("SELECT COUNT(*) FROM candidates WHERE active = 1 AND campaign_id = ?", (campaign_id,))
    total_candidates = cursor.fetchone()[0]

    # Contagem de juízes ativos
    cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'JUDGE' AND active = 1")
    total_judges = cursor.fetchone()[0]

    # Contagem de categorias ativas
    cursor.execute("SELECT COUNT(*) FROM categories WHERE active = 1")
    total_categories = cursor.fetchone()[0]

    # Total de submissões esperadas (cada juiz avalia cada candidato)
    expected_submissions = total_candidates * total_judges

    # Total de submissões concluídas para candidatos desta campanha
    cursor.execute("""
        SELECT COUNT(DISTINCT cs.id)
        FROM candidate_submissions cs
        JOIN users u ON u.id = cs.judge_id AND u.active = 1 AND u.role = 'JUDGE'
        JOIN candidates c ON c.id = cs.candidate_id AND c.active = 1 AND c.campaign_id = ?
        WHERE cs.status = 'COMPLETED'
    """, (campaign_id,))
    completed_submissions = cursor.fetchone()[0]
    pending_submissions = max(0, expected_submissions - completed_submissions)

    # Total de notas individuais registradas
    cursor.execute("""
        SELECT COUNT(e.id)
        FROM evaluations e
        JOIN users u ON u.id = e.judge_id AND u.active = 1
        JOIN candidates c ON c.id = e.candidate_id AND c.active = 1 AND c.campaign_id = ?
        JOIN categories cat ON cat.id = e.category_id AND cat.active = 1
    """, (campaign_id,))
    total_evaluations_recorded = cursor.fetchone()[0]

    # Total de notas esperadas
    expected_evaluations = expected_submissions * total_categories

    completion_percentage = 0.0
    if expected_submissions > 0:
        completion_percentage = round((completed_submissions / expected_submissions) * 100, 1)

    settings = get_all_settings(conn)

    return {
        "total_candidates": total_candidates,
        "total_judges": total_judges,
        "total_categories": total_categories,
        "expected_submissions": expected_submissions,
        "completed_submissions": completed_submissions,
        "pending_submissions": pending_submissions,
        "expected_evaluations": expected_evaluations,
        "total_evaluations_recorded": total_evaluations_recorded,
        "completion_percentage": completion_percentage,
        "voting_status": settings.get("voting_status", "OPEN"),
        "allow_corrections": settings.get("allow_corrections", "true").lower() == "true",
        "public_results_published": settings.get("public_results_published", "false").lower() == "true",
        "show_provisional_winner": settings.get("show_provisional_winner", "true").lower() == "true",
        "event_name": settings.get("event_name", "Sistema de Avaliação de Candidatos"),
        "active_campaign": active_campaign
    }


def calculate_rankings(conn: sqlite3.Connection, campaign_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Calcula a classificação dos candidatos de acordo com as regras de negócio:
    - Média final = soma de todas as notas válidas do candidato ÷ quantidade total de notas válidas
    - Exibição com duas casas decimais
    - Ordenação decrescente por média final
    - Identificação exata de empates (sem escolha arbitrária)
    - Determinação do vencedor provisório ou oficial
    - Desmembramento de médias por categoria
    """
    cursor = conn.cursor()
    if campaign_id is None:
        campaign_id = get_active_campaign_id(conn)
    active_campaign = get_active_campaign(conn)

    # 1. Carregar categorias ativas
    cursor.execute("SELECT id, name, display_order FROM categories WHERE active = 1 ORDER BY display_order ASC, name ASC")
    categories = [dict(row) for row in cursor.fetchall()]
    category_map = {cat["id"]: cat["name"] for cat in categories}

    # 2. Carregar todos os candidatos ativos da campanha
    cursor.execute("""
        SELECT id, name, number, photo_url, description 
        FROM candidates 
        WHERE active = 1 AND campaign_id = ? 
        ORDER BY CAST(number AS INTEGER) ASC, id ASC
    """, (campaign_id,))
    candidates = [dict(row) for row in cursor.fetchall()]

    if not candidates:
        return {
            "rankings": [],
            "winners": [],
            "is_tie": False,
            "is_winner_tie": False,
            "total_candidates": 0,
            "categories": categories,
            "is_closed": False,
            "is_published": False,
            "campaign": active_campaign
        }

    # 3. Carregar todas as avaliações válidas da campanha
    # Notas atribuídas por juízes ativos em categorias ativas com submissão concluída
    cursor.execute("""
        SELECT 
            e.candidate_id,
            e.category_id,
            e.judge_id,
            e.score
        FROM evaluations e
        JOIN candidate_submissions cs ON cs.judge_id = e.judge_id AND cs.candidate_id = e.candidate_id
        JOIN users u ON u.id = e.judge_id AND u.active = 1 AND u.role = 'JUDGE'
        JOIN candidates c ON c.id = e.candidate_id AND c.active = 1 AND c.campaign_id = ?
        JOIN categories cat ON cat.id = e.category_id AND cat.active = 1
        WHERE cs.status = 'COMPLETED'
    """, (campaign_id,))
    eval_rows = cursor.fetchall()

    # Organizar notas por candidato e categoria
    candidate_scores: Dict[int, List[int]] = {c["id"]: [] for c in candidates}
    candidate_judges: Dict[int, set] = {c["id"]: set() for c in candidates}
    candidate_cat_scores: Dict[int, Dict[int, List[int]]] = {
        c["id"]: {cat["id"]: [] for cat in categories} for c in candidates
    }

    for row in eval_rows:
        cand_id = row["candidate_id"]
        cat_id = row["category_id"]
        score = row["score"]
        judge_id = row["judge_id"]

        if cand_id in candidate_scores:
            candidate_scores[cand_id].append(score)
            candidate_judges[cand_id].add(judge_id)
            if cat_id in candidate_cat_scores[cand_id]:
                candidate_cat_scores[cand_id][cat_id].append(score)

    # 4. Calcular estatísticas de cada candidato
    candidate_results = []
    for cand in candidates:
        cand_id = cand["id"]
        scores = candidate_scores[cand_id]
        total_valid_scores = len(scores)
        sum_scores = sum(scores)

        # Fórmula: Média final = soma de todas as notas válidas ÷ quantidade total de notas válidas
        if total_valid_scores > 0:
            final_average = round(sum_scores / total_valid_scores, 2)
            raw_average = sum_scores / total_valid_scores
        else:
            final_average = 0.0
            raw_average = 0.0

        # Médias por categoria
        category_averages = {}
        for cat in categories:
            cat_id = cat["id"]
            cat_scores = candidate_cat_scores[cand_id][cat_id]
            if cat_scores:
                cat_avg = round(sum(cat_scores) / len(cat_scores), 2)
            else:
                cat_avg = 0.0
            category_averages[cat_id] = {
                "category_id": cat_id,
                "category_name": category_map[cat_id],
                "average": cat_avg,
                "average_formatted": f"{cat_avg:.2f}",
                "votes_count": len(cat_scores)
            }

        candidate_results.append({
            "id": cand["id"],
            "name": cand["name"],
            "number": cand["number"],
            "photo_url": cand["photo_url"],
            "description": cand["description"],
            "total_scores_count": total_valid_scores,
            "sum_scores": sum_scores,
            "final_average": final_average,
            "raw_average": raw_average,
            "final_average_formatted": f"{final_average:.2f}",
            "judges_evaluated_count": len(candidate_judges[cand_id]),
            "category_averages": category_averages
        })

    # 5. Ordenação: maior média primeiro
    # Caso as médias arredondadas em 2 casas decimais sejam iguais, trata-se de empate.
    candidate_results.sort(
        key=lambda item: (-item["final_average"], -item["total_scores_count"], item["name"])
    )

    # 6. Atribuição de Posição (Rank) e Identificação de Empates
    # Sistema não escolhe arbitrariamente: candidatos com mesma média final recebem o mesmo rank!
    current_rank = 1
    total_ranked = len(candidate_results)
    
    for i in range(total_ranked):
        if i == 0:
            candidate_results[i]["rank"] = 1
            candidate_results[i]["is_tie"] = False
        else:
            prev = candidate_results[i - 1]
            curr = candidate_results[i]
            # Empate se ambas têm notas e média final idêntica (com duas casas decimais)
            if curr["final_average"] == prev["final_average"] and curr["total_scores_count"] > 0:
                curr["rank"] = prev["rank"]
                curr["is_tie"] = True
                prev["is_tie"] = True
            else:
                curr["rank"] = i + 1
                curr["is_tie"] = False

    # Identificar o(s) vencedor(es) (1º lugar)
    settings = get_all_settings(conn)
    is_closed = settings.get("voting_status", "OPEN") == "CLOSED"
    is_published = settings.get("public_results_published", "false").lower() == "true"
    show_provisional = settings.get("show_provisional_winner", "true").lower() == "true"

    winners = []
    has_winner_tie = False

    # Só há vencedores se houver candidatos com notas avaliadas
    candidates_with_votes = [c for c in candidate_results if c["total_scores_count"] > 0]
    if candidates_with_votes:
        top_rank = candidates_with_votes[0]["rank"]
        top_candidates = [c for c in candidates_with_votes if c["rank"] == top_rank]
        winners = top_candidates
        if len(top_candidates) > 1:
            has_winner_tie = True

    return {
        "rankings": candidate_results,
        "winners": winners,
        "is_winner_tie": has_winner_tie,
        "total_candidates": len(candidate_results),
        "categories": categories,
        "is_closed": is_closed,
        "is_published": is_published,
        "show_provisional_winner": show_provisional,
        "voting_status": settings.get("voting_status", "OPEN"),
        "campaign": active_campaign
    }


def get_judge_voting_screen(conn: sqlite3.Connection, judge_id: int, campaign_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Retorna os dados exclusivos necessários para a interface de votação do juiz:
    - Lista de candidatos disponíveis da campanha ativa
    - Status de cada candidato para este juiz (PENDING / COMPLETED)
    - Notas atribuídas por este juiz (se já existirem)
    - Categorias ativas disponíveis para avaliação
    - Progresso do juiz (quantos avaliou e quantos faltam)
    - Regras da votação (status aberto/fechado, permissão de edição)
    """
    cursor = conn.cursor()
    settings = get_all_settings(conn)
    if campaign_id is None:
        campaign_id = get_active_campaign_id(conn)
    active_campaign = get_active_campaign(conn)

    # 1. Categorias ativas ordenadas
    cursor.execute("""
        SELECT id, name, description, display_order 
        FROM categories 
        WHERE active = 1 
        ORDER BY display_order ASC, name ASC
    """)
    categories = [dict(row) for row in cursor.fetchall()]

    # 2. Candidatos ativos da campanha
    cursor.execute("""
        SELECT id, name, number, photo_url, description 
        FROM candidates 
        WHERE active = 1 AND campaign_id = ?
        ORDER BY CAST(number AS INTEGER) ASC, name ASC
    """, (campaign_id,))
    candidates = [dict(row) for row in cursor.fetchall()]

    # 3. Status de submissão deste juiz para cada candidato
    cursor.execute("""
        SELECT candidate_id, status, submitted_at
        FROM candidate_submissions
        WHERE judge_id = ?
    """, (judge_id,))
    submissions_map = {row["candidate_id"]: dict(row) for row in cursor.fetchall()}

    # 4. Notas já atribuídas por este juiz
    cursor.execute("""
        SELECT candidate_id, category_id, score
        FROM evaluations
        WHERE judge_id = ?
    """, (judge_id,))
    scores_rows = cursor.fetchall()

    scores_by_candidate: Dict[int, Dict[int, int]] = {}
    for row in scores_rows:
        c_id = row["candidate_id"]
        cat_id = row["category_id"]
        if c_id not in scores_by_candidate:
            scores_by_candidate[c_id] = {}
        scores_by_candidate[c_id][cat_id] = row["score"]

    # Montar lista consolidada de candidatos com status
    evaluated_count = 0
    candidate_items = []
    
    for c in candidates:
        cand_id = c["id"]
        sub = submissions_map.get(cand_id)
        is_completed = sub is not None and sub.get("status") == "COMPLETED"
        if is_completed:
            evaluated_count += 1

        cand_scores = scores_by_candidate.get(cand_id, {})

        candidate_items.append({
            "id": c["id"],
            "name": c["name"],
            "number": c["number"],
            "photo_url": c["photo_url"],
            "description": c["description"],
            "is_evaluated": is_completed,
            "status": "COMPLETED" if is_completed else "PENDING",
            "scores": cand_scores,
            "submitted_at": sub.get("submitted_at") if sub else None
        })

    total_candidates = len(candidates)
    pending_count = max(0, total_candidates - evaluated_count)
    progress_percentage = 0.0
    if total_candidates > 0:
        progress_percentage = round((evaluated_count / total_candidates) * 100, 1)

    return {
        "categories": categories,
        "candidates": candidate_items,
        "progress": {
            "total_candidates": total_candidates,
            "evaluated_count": evaluated_count,
            "pending_count": pending_count,
            "percentage": progress_percentage
        },
        "voting_status": settings.get("voting_status", "OPEN"),
        "allow_corrections": settings.get("allow_corrections", "true").lower() == "true",
        "event_name": settings.get("event_name", "Sistema de Avaliação"),
        "campaign": active_campaign
    }


def submit_candidate_evaluation(
    conn: sqlite3.Connection,
    judge_id: int,
    judge_name: str,
    candidate_id: int,
    scores: Dict[int, int],
    ip_address: str = "127.0.0.1"
) -> Dict[str, Any]:
    """
    Salva e confirma a avaliação de um candidato feita por um juiz:
    - Valida se a votação está ABERTA
    - Valida se o candidato está ativo
    - Valida se todas as categorias ativas possuem nota atribuída
    - Valida se cada nota é um número inteiro de 1 a 10
    - Valida permissão de alteração (caso já tenha sido submetido)
    - Persiste com garantia de unicidade (UNIQUE judge_id, candidate_id, category_id)
    """
    settings = get_all_settings(conn)
    voting_status = settings.get("voting_status", "OPEN")
    allow_corrections = settings.get("allow_corrections", "true").lower() == "true"

    if voting_status != "OPEN":
        if voting_status == "CLOSED":
            raise ValueError("A votação está encerrada para envio ou alteração de notas.")
        raise ValueError("A votação está pausada para envio ou alteração de notas.")

    cursor = conn.cursor()

    # Verificar candidato
    cursor.execute("SELECT id, name FROM candidates WHERE id = ? AND active = 1", (candidate_id,))
    cand = cursor.fetchone()
    if not cand:
        raise ValueError("Candidato não encontrado ou inativo.")
    candidate_name = cand["name"]

    # Verificar categorias ativas
    cursor.execute("SELECT id, name FROM categories WHERE active = 1")
    active_categories = cursor.fetchall()
    active_cat_ids = {row["id"] for row in active_categories}

    if not active_cat_ids:
        raise ValueError("Nenhuma categoria de avaliação ativa configurada no sistema.")

    # Validar se o juiz já submeteu este candidato anteriormente
    cursor.execute("""
        SELECT status FROM candidate_submissions 
        WHERE judge_id = ? AND candidate_id = ?
    """, (judge_id, candidate_id))
    sub = cursor.fetchone()
    already_submitted = sub is not None and sub["status"] == "COMPLETED"

    if already_submitted and not allow_corrections:
        raise ValueError("A votação deste candidato já foi concluída e a alteração de notas está desabilitada pelo administrador.")

    # Validar que todas as categorias ativas possuem notas
    scores_int_map: Dict[int, int] = {}
    for cat_id in active_cat_ids:
        if str(cat_id) in scores:
            raw_score = scores[str(cat_id)]
        elif cat_id in scores:
            raw_score = scores[cat_id]
        else:
            raise ValueError("Avaliação incompleta: todas as categorias ativas devem receber nota de 1 a 10.")

        # Validar número inteiro entre 1 e 10
        try:
            if isinstance(raw_score, bool):
                raise ValueError()
            score_val = int(raw_score)
            if score_val < 1 or score_val > 10:
                raise ValueError()
        except (ValueError, TypeError):
            raise ValueError("As notas devem ser números inteiros no intervalo de 1 a 10.")

        scores_int_map[cat_id] = score_val

    # Persistir no banco de dados dentro de transação atômica
    now = get_brasilia_now_iso()
    with conn:
        for cat_id, score_val in scores_int_map.items():
            conn.execute("""
                INSERT INTO evaluations (judge_id, candidate_id, category_id, score, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(judge_id, candidate_id, category_id) DO UPDATE SET
                    score = excluded.score,
                    updated_at = excluded.updated_at
            """, (judge_id, candidate_id, cat_id, score_val, now, now))

        # Registrar submissão concluída
        conn.execute("""
            INSERT INTO candidate_submissions (judge_id, candidate_id, status, submitted_at)
            VALUES (?, ?, 'COMPLETED', ?)
            ON CONFLICT(judge_id, candidate_id) DO UPDATE SET
                status = 'COMPLETED',
                submitted_at = excluded.submitted_at
        """, (judge_id, candidate_id, now))

        action_type = "UPDATE_EVALUATION" if already_submitted else "SUBMIT_EVALUATION"
        log_audit(
            conn,
            judge_id,
            judge_name,
            action_type,
            f"Avaliação do candidato '{candidate_name}' (ID {candidate_id}) salva/atualizada com {len(scores_int_map)} notas.",
            ip_address
        )

    return {
        "success": True,
        "candidate_id": candidate_id,
        "candidate_name": candidate_name,
        "scores": scores_int_map,
        "is_update": already_submitted
    }


def get_detailed_results_by_category(conn: sqlite3.Connection, campaign_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Retorna a matriz completa de notas para consulta do administrador:
    - Candidatos e suas notas por categoria da campanha ativa
    - Detalhamento de notas por juiz
    - Médias consolidadas
    """
    cursor = conn.cursor()
    if campaign_id is None:
        campaign_id = get_active_campaign_id(conn)

    # Juízes
    cursor.execute("SELECT id, name, email FROM users WHERE role = 'JUDGE' AND active = 1 ORDER BY name ASC")
    judges = [dict(row) for row in cursor.fetchall()]

    # Categorias
    cursor.execute("SELECT id, name, description FROM categories WHERE active = 1 ORDER BY display_order ASC, name ASC")
    categories = [dict(row) for row in cursor.fetchall()]

    # Candidatos da campanha atual
    cursor.execute("""
        SELECT id, name, number, photo_url 
        FROM candidates 
        WHERE active = 1 AND campaign_id = ? 
        ORDER BY CAST(number AS INTEGER) ASC, name ASC
    """, (campaign_id,))
    candidates = [dict(row) for row in cursor.fetchall()]

    # Todas as notas registradas da campanha
    cursor.execute("""
        SELECT e.candidate_id, e.category_id, e.judge_id, e.score
        FROM evaluations e
        JOIN users u ON u.id = e.judge_id AND u.active = 1
        JOIN candidates c ON c.id = e.candidate_id AND c.active = 1 AND c.campaign_id = ?
        JOIN categories cat ON cat.id = e.category_id AND cat.active = 1
    """, (campaign_id,))
    evaluations_raw = cursor.fetchall()

    eval_matrix: Dict[int, Dict[int, Dict[int, int]]] = {}
    for r in evaluations_raw:
        c_id = r["candidate_id"]
        cat_id = r["category_id"]
        j_id = r["judge_id"]
        if c_id not in eval_matrix:
            eval_matrix[c_id] = {}
        if cat_id not in eval_matrix[c_id]:
            eval_matrix[c_id][cat_id] = {}
        eval_matrix[c_id][cat_id][j_id] = r["score"]

    # Progresso detalhado de cada juiz na campanha
    judge_progress = []
    total_candidates = len(candidates)
    for j in judges:
        j_id = j["id"]
        cursor.execute("""
            SELECT COUNT(DISTINCT cs.candidate_id)
            FROM candidate_submissions cs
            JOIN candidates c ON c.id = cs.candidate_id AND c.active = 1 AND c.campaign_id = ?
            WHERE cs.judge_id = ? AND cs.status = 'COMPLETED'
        """, (campaign_id, j_id))
        completed = cursor.fetchone()[0]
        pct = round((completed / total_candidates) * 100, 1) if total_candidates > 0 else 0.0
        judge_progress.append({
            "judge_id": j_id,
            "judge_name": j["name"],
            "judge_email": j["email"],
            "completed_candidates": completed,
            "total_candidates": total_candidates,
            "percentage": pct,
            "is_finished": completed >= total_candidates and total_candidates > 0
        })

    return {
        "judges": judges,
        "categories": categories,
        "candidates": candidates,
        "matrix": eval_matrix,
        "judge_progress": judge_progress
    }


def delete_category_safe(conn: sqlite3.Connection, category_id: int, user_id: int, user_name: str) -> Tuple[bool, str]:
    """
    Exclui uma categoria respeitando a integridade dos dados:
    - Se houver avaliações registradas nesta categoria, a desativa (soft delete) para proteger o histórico.
    - Se não houver avaliações, realiza a exclusão física (hard delete).
    """
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM categories WHERE id = ?", (category_id,))
    cat = cursor.fetchone()
    if not cat:
        return False, "Categoria não encontrada."

    cat_name = cat["name"]
    cursor.execute("SELECT COUNT(*) FROM evaluations WHERE category_id = ?", (category_id,))
    eval_count = cursor.fetchone()[0]

    with conn:
        if eval_count > 0:
            # Desativar para manter integridade
            conn.execute("UPDATE categories SET active = 0, updated_at = ? WHERE id = ?", (get_brasilia_now_iso(), category_id))
            log_audit(conn, user_id, user_name, "DEACTIVATE_CATEGORY", f"Categoria '{cat_name}' (ID {category_id}) desativada pois possui {eval_count} notas registradas.")
            return True, f"A categoria '{cat_name}' possui avaliações registradas e foi desativada para preservar a integridade dos resultados."
        else:
            # Exclusão física permitida
            conn.execute("DELETE FROM categories WHERE id = ?", (category_id,))
            log_audit(conn, user_id, user_name, "DELETE_CATEGORY", f"Categoria '{cat_name}' (ID {category_id}) excluída com sucesso.")
            return True, f"Categoria '{cat_name}' excluída com sucesso."


def delete_candidate_safe(conn: sqlite3.Connection, candidate_id: int, user_id: int, user_name: str) -> Tuple[bool, str]:
    """Exclui ou desativa um candidato garantindo auditoria e integridade."""
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM candidates WHERE id = ?", (candidate_id,))
    cand = cursor.fetchone()
    if not cand:
        return False, "Candidato não encontrado."

    cand_name = cand["name"]
    now = get_brasilia_now_iso()
    with conn:
        # Excluir candidato e avaliações relacionadas em cascata
        conn.execute("DELETE FROM evaluations WHERE candidate_id = ?", (candidate_id,))
        conn.execute("DELETE FROM candidate_submissions WHERE candidate_id = ?", (candidate_id,))
        conn.execute("DELETE FROM candidates WHERE id = ?", (candidate_id,))
        log_audit(conn, user_id, user_name, "DELETE_CANDIDATE", f"Candidato '{cand_name}' (ID {candidate_id}) excluído com suas avaliações associadas.")
        return True, f"Candidato '{cand_name}' excluído com sucesso."


def delete_judge_safe(conn: sqlite3.Connection, judge_id: int, user_id: int, user_name: str) -> Tuple[bool, str]:
    """Exclui ou desativa um juiz."""
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, role FROM users WHERE id = ?", (judge_id,))
    u = cursor.fetchone()
    if not u:
        return False, "Usuário não encontrado."
    if u["role"] != "JUDGE":
        return False, "Apenas juízes podem ser excluídos por esta rota."

    judge_name = u["name"]
    with conn:
        conn.execute("DELETE FROM evaluations WHERE judge_id = ?", (judge_id,))
        conn.execute("DELETE FROM candidate_submissions WHERE judge_id = ?", (judge_id,))
        conn.execute("DELETE FROM users WHERE id = ?", (judge_id,))
        log_audit(conn, user_id, user_name, "DELETE_JUDGE", f"Juiz '{judge_name}' (ID {judge_id}) excluído.")
        return True, f"Juiz '{judge_name}' excluído com sucesso."
