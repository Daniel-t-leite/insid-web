"""
Módulo RBAC, Isolamento de Dados (Data Scoping) e Fluxo de Aprovação de Configurações
para a plataforma inSID Web.

Perfis:
- super_admin (Usuário Supremo): controlo total, gestão de utilizadores/perfis, aprovação e
  acesso global às análises de barragens de todos os utilizadores.
- approver (Aprovador): aprova/rejeita propostas de configuração global e pode gerir
  configurações globais diretamente. NÃO tem acesso às análises de barragens dos utilizadores.
- user (Usuário Normal): gere exclusivamente as suas próprias análises de barragens e pode
  propor alterações em configurações globais, que ficam pendentes até aprovação.
"""

from contextlib import closing
import json
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from db import conectar_db, atualizar_role_usuario, atualizar_status_usuario, excluir_usuario

ROLE_SUPER_ADMIN = "super_admin"
ROLE_APPROVER = "approver"
ROLE_USER = "user"

VALID_ROLES = (ROLE_SUPER_ADMIN, ROLE_APPROVER, ROLE_USER)

ROLE_LABELS = {
    ROLE_SUPER_ADMIN: "Usuário Supremo",
    ROLE_APPROVER: "Aprovador",
    ROLE_USER: "Usuário Normal",
}

ENTITY_LABELS = {
    "tipos_barragem": "Tipos de Barragem",
    "tipos_zonas_bar": "Zonas das Barragens",
    "tipos_materiais": "Tipos de Materiais",
    "tipo_anomalia": "Tipos de Anomalias",
    "tipo_modo_falha": "Tipos de Modos de Falha",
    "modos_falha": "Modos de Falha",
    "anomalias": "Regras Anomalia × Modo de Falha",
}

ACTION_LABELS = {
    "create": "Criar",
    "update": "Editar",
    "delete": "Excluir",
}


# ============================================================================
# 1. Guards RBAC
# ============================================================================
def normalize_role(role: Optional[str], is_admin: Any = False) -> str:
    if role in VALID_ROLES:
        return str(role)
    return ROLE_SUPER_ADMIN if bool(is_admin) else ROLE_USER


def can_manage_users(role: Optional[str]) -> bool:
    return role == ROLE_SUPER_ADMIN


def can_approve_configs(role: Optional[str]) -> bool:
    return role in (ROLE_SUPER_ADMIN, ROLE_APPROVER)


def can_apply_config_directly(role: Optional[str]) -> bool:
    return role in (ROLE_SUPER_ADMIN, ROLE_APPROVER)


def can_propose_config(role: Optional[str]) -> bool:
    return role in VALID_ROLES


def can_access_dam_analyses(role: Optional[str]) -> bool:
    """Apenas Usuário Supremo e Usuário Normal acedem a análises de barragens; Aprovador é bloqueado."""
    return role in (ROLE_SUPER_ADMIN, ROLE_USER)


def can_view_all_dam_analyses(role: Optional[str]) -> bool:
    return role == ROLE_SUPER_ADMIN


def can_access_dam_record(role: Optional[str], user_id: Any, owner_id: Any) -> bool:
    if role == ROLE_SUPER_ADMIN:
        return True
    if role == ROLE_APPROVER:
        return False
    if role == ROLE_USER:
        return str(user_id) == str(owner_id)
    return False


# ============================================================================
# 2. Gestão de Utilizadores Protegida por RBAC
# ============================================================================
def alterar_role_usuario_seguro(actor_role: str, target_codigo: str, novo_role: str) -> bool:
    if not can_manage_users(actor_role):
        raise PermissionError("Apenas o Usuário Supremo pode alterar perfis de utilizadores.")
    return atualizar_role_usuario(target_codigo, novo_role)


def alterar_status_usuario_seguro(actor_role: str, target_codigo: str, ativo: str) -> bool:
    if not can_manage_users(actor_role):
        raise PermissionError("Apenas o Usuário Supremo pode alterar o estado de utilizadores.")
    return atualizar_status_usuario(target_codigo, ativo)


def excluir_usuario_seguro(actor_role: str, target_codigo: str) -> bool:
    if not can_manage_users(actor_role):
        raise PermissionError("Apenas o Usuário Supremo pode excluir utilizadores.")
    return excluir_usuario(target_codigo)


# ============================================================================
# 3. Isolamento Estrito das Análises de Barragens (Data Scoping)
# ============================================================================
def listar_barragens_escopo(role: str, user_id: Any) -> List[Tuple]:
    """
    Retorna barragens acessíveis conforme o perfil:
    - super_admin: todas as barragens (inclui owner_id e nome do proprietário).
    - user: apenas barragens onde owner_id == str(user_id).
    - approver: lista vazia (sem acesso às análises de utilizadores).
    Formato de cada tupla:
    (id, nome, tipo_id, localizacao, altura, comprimento, rel_cordaaltura, owner_id, owner_nome)
    """
    if not can_access_dam_analyses(role):
        return []

    with closing(conectar_db()) as conn:
        cur = conn.cursor()
        if can_view_all_dam_analyses(role):
            cur.execute("""
                SELECT b.id, b.nome, b.tipo_id, b.localizacao, b.altura, b.comprimento,
                       b.rel_cordaaltura, COALESCE(b.owner_id, CAST(b.usuario_id AS TEXT)) as owner_id,
                       COALESCE(u.nome, 'Utilizador #' || COALESCE(b.owner_id, CAST(b.usuario_id AS TEXT))) as owner_nome
                FROM barragens b
                LEFT JOIN usuarios u ON CAST(u.codigo AS TEXT) = COALESCE(b.owner_id, CAST(b.usuario_id AS TEXT))
                ORDER BY b.id DESC
            """)
        else:
            cur.execute("""
                SELECT b.id, b.nome, b.tipo_id, b.localizacao, b.altura, b.comprimento,
                       b.rel_cordaaltura, COALESCE(b.owner_id, CAST(b.usuario_id AS TEXT)) as owner_id,
                       COALESCE(u.nome, '') as owner_nome
                FROM barragens b
                LEFT JOIN usuarios u ON CAST(u.codigo AS TEXT) = COALESCE(b.owner_id, CAST(b.usuario_id AS TEXT))
                WHERE COALESCE(b.owner_id, CAST(b.usuario_id AS TEXT)) = ?
                ORDER BY b.id DESC
            """, (str(user_id),))
        return cur.fetchall()


def obter_barragem_autorizada(role: str, user_id: Any, barragem_id: int) -> Optional[Tuple]:
    """Devolve o registo da barragem apenas se o utilizador tiver permissão RBAC sobre ela."""
    if not can_access_dam_analyses(role):
        return None
    with closing(conectar_db()) as conn:
        cur = conn.cursor()
        row = cur.execute("""
            SELECT id, usuario_id, nome, tipo_id, localizacao, altura, comprimento,
                   rel_cordaaltura, em_analise, data_criacao,
                   COALESCE(owner_id, CAST(usuario_id AS TEXT)) as owner_id
            FROM barragens
            WHERE id = ?
        """, (int(barragem_id),)).fetchone()
        if not row:
            return None
        if not can_access_dam_record(role, user_id, row[10]):
            return None
        return row


def obter_barragem_analise_escopo(role: str, user_id: Any) -> Optional[Tuple]:
    """Obtém a barragem em análise do utilizador respeitando isolamento por owner_id."""
    if not can_access_dam_analyses(role):
        return None
    with closing(conectar_db()) as conn:
        cur = conn.cursor()
        row = cur.execute("""
            SELECT b.id, b.usuario_id, b.nome, b.tipo_id, b.localizacao,
                   b.altura, b.comprimento, b.rel_cordaaltura,
                   b.em_analise, b.data_criacao,
                   COALESCE(b.owner_id, CAST(b.usuario_id AS TEXT)) as owner_id
            FROM barragens b
            JOIN usuario_barragem_analise uba ON b.id = uba.barragem_id
            WHERE CAST(uba.usuario_id AS TEXT) = ?
        """, (str(user_id),)).fetchone()
        if not row:
            return None
        if not can_access_dam_record(role, user_id, row[10]):
            return None
        return row


def definir_barragem_analise_escopo(role: str, user_id: Any, barragem_id: int) -> bool:
    """Define a barragem em análise apenas se o perfil tiver acesso à barragem."""
    if not can_access_dam_analyses(role):
        raise PermissionError("O perfil Aprovador não tem acesso a análises de barragens.")
    barragem = obter_barragem_autorizada(role, user_id, barragem_id)
    if not barragem:
        raise PermissionError("Sem permissão para aceder à análise desta barragem.")
    with closing(conectar_db()) as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM usuario_barragem_analise WHERE CAST(usuario_id AS TEXT) = ?", (str(user_id),))
        cur.execute(
            "INSERT INTO usuario_barragem_analise (usuario_id, barragem_id) VALUES (?, ?)",
            (user_id, int(barragem_id)),
        )
        conn.commit()
    return True


def atualizar_barragem_escopo(
    role: str, user_id: Any, barragem_id: int,
    nome: str, tipo_id: int, localizacao: str,
    altura: float, comprimento: float, rel_cordaaltura: float
) -> bool:
    if not obter_barragem_autorizada(role, user_id, barragem_id):
        raise PermissionError("Sem permissão para editar esta barragem.")
    with closing(conectar_db()) as conn:
        cur = conn.cursor()
        cur.execute("""
            UPDATE barragens
            SET nome = ?, tipo_id = ?, localizacao = ?, altura = ?, comprimento = ?, rel_cordaaltura = ?
            WHERE id = ?
        """, (nome, tipo_id, localizacao, altura, comprimento, rel_cordaaltura, int(barragem_id)))
        conn.commit()
        return cur.rowcount > 0


def excluir_barragem_escopo(role: str, user_id: Any, barragem_id: int) -> bool:
    if not obter_barragem_autorizada(role, user_id, barragem_id):
        raise PermissionError("Sem permissão para excluir esta barragem.")
    with closing(conectar_db()) as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM usuario_barragem_analise WHERE barragem_id = ?", (int(barragem_id),))
        cur.execute("DELETE FROM anomalias_observadas WHERE barragem_id = ?", (int(barragem_id),))
        cur.execute("DELETE FROM barragens WHERE id = ?", (int(barragem_id),))
        conn.commit()
        return cur.rowcount > 0


# ============================================================================
# 4. Motor de Workflow de Aprovação para Configurações Globais
# ============================================================================
def _aplicar_operacao_config(conn, entity_type: str, action: str, payload: Dict[str, Any], target_id: Optional[int], actor_id: Any) -> Optional[int]:
    """Aplica efetivamente uma operação (create/update/delete) numa tabela de configuração global."""
    cur = conn.cursor()
    uid = int(actor_id) if str(actor_id).isdigit() else 1

    if entity_type == "tipos_barragem":
        if action == "create":
            cur.execute(
                "INSERT INTO tipos_barragem (usuario_id, nome, descricao, referencia_tecnica, image_path) VALUES (?, ?, ?, ?, ?)",
                (uid, payload["nome"], payload.get("descricao"), payload.get("referencia_tecnica"), payload.get("image_path")),
            )
            return cur.lastrowid
        if action == "update":
            cur.execute(
                "UPDATE tipos_barragem SET nome = ?, descricao = ?, referencia_tecnica = ?, image_path = ? WHERE id = ?",
                (payload["nome"], payload.get("descricao"), payload.get("referencia_tecnica"), payload.get("image_path"), int(target_id)),
            )
            return int(target_id)
        if action == "delete":
            cur.execute("DELETE FROM tipos_barragem WHERE id = ?", (int(target_id),))
            return int(target_id)

    elif entity_type == "tipos_zonas_bar":
        if action == "create":
            cur.execute(
                "INSERT INTO tipos_zonas_bar (nome, descricao) VALUES (?, ?)",
                (payload["nome"], payload.get("descricao")),
            )
            return cur.lastrowid
        if action == "update":
            cur.execute(
                "UPDATE tipos_zonas_bar SET nome = ?, descricao = ? WHERE id = ?",
                (payload["nome"], payload.get("descricao"), int(target_id)),
            )
            return int(target_id)
        if action == "delete":
            cur.execute("DELETE FROM tipos_zonas_bar WHERE id = ?", (int(target_id),))
            return int(target_id)

    elif entity_type == "tipos_materiais":
        if action == "create":
            cur.execute(
                "INSERT INTO tipos_materiais (usuario_id, nome, descricao) VALUES (?, ?, ?)",
                (uid, payload["nome"], payload.get("descricao")),
            )
            return cur.lastrowid
        if action == "update":
            cur.execute(
                "UPDATE tipos_materiais SET nome = ?, descricao = ? WHERE id = ?",
                (payload["nome"], payload.get("descricao"), int(target_id)),
            )
            return int(target_id)
        if action == "delete":
            cur.execute("DELETE FROM tipos_materiais WHERE id = ?", (int(target_id),))
            return int(target_id)

    elif entity_type == "tipo_anomalia":
        if action == "create":
            cur.execute(
                "INSERT INTO tipo_anomalia (usuario_id, nome, descricao, image_path) VALUES (?, ?, ?, ?)",
                (uid, payload["nome"], payload.get("descricao"), payload.get("image_path")),
            )
            return cur.lastrowid
        if action == "update":
            cur.execute(
                "UPDATE tipo_anomalia SET nome = ?, descricao = ?, image_path = ? WHERE id = ?",
                (payload["nome"], payload.get("descricao"), payload.get("image_path"), int(target_id)),
            )
            return int(target_id)
        if action == "delete":
            cur.execute("DELETE FROM tipo_anomalia WHERE id = ?", (int(target_id),))
            return int(target_id)

    elif entity_type == "tipo_modo_falha":
        if action == "create":
            cur.execute(
                "INSERT INTO tipo_modo_falha (usuario_id, nome, descricao, referencia_tecnica) VALUES (?, ?, ?, ?)",
                (uid, payload["nome"], payload.get("descricao"), payload.get("referencia_tecnica")),
            )
            return cur.lastrowid
        if action == "update":
            cur.execute(
                "UPDATE tipo_modo_falha SET nome = ?, descricao = ?, referencia_tecnica = ? WHERE id = ?",
                (payload["nome"], payload.get("descricao"), payload.get("referencia_tecnica"), int(target_id)),
            )
            return int(target_id)
        if action == "delete":
            cur.execute("DELETE FROM tipo_modo_falha WHERE id = ?", (int(target_id),))
            return int(target_id)

    elif entity_type == "modos_falha":
        if action == "create":
            cur.execute(
                "INSERT INTO modos_falha (usuario_id, id_tipo_modo_falha, nome, descricao, referencia_tecnica, image_path) VALUES (?, ?, ?, ?, ?, ?)",
                (uid, int(payload["id_tipo_modo_falha"]), payload["nome"], payload.get("descricao"), payload.get("referencia_tecnica"), payload.get("image_path")),
            )
            novo_id = cur.lastrowid
            for tb_id in payload.get("tipos_barragem_ids", []):
                cur.execute(
                    "INSERT OR IGNORE INTO modos_falha_tipo_barragem (modos_falha_id, tipo_barragem_id) VALUES (?, ?)",
                    (int(novo_id), int(tb_id)),
                )
            return novo_id
        if action == "update":
            cur.execute(
                "UPDATE modos_falha SET id_tipo_modo_falha = ?, nome = ?, descricao = ?, referencia_tecnica = ?, image_path = ? WHERE id = ?",
                (int(payload["id_tipo_modo_falha"]), payload["nome"], payload.get("descricao"), payload.get("referencia_tecnica"), payload.get("image_path"), int(target_id)),
            )
            if "tipos_barragem_ids" in payload:
                cur.execute("DELETE FROM modos_falha_tipo_barragem WHERE modos_falha_id = ?", (int(target_id),))
                for tb_id in payload["tipos_barragem_ids"]:
                    cur.execute(
                        "INSERT OR IGNORE INTO modos_falha_tipo_barragem (modos_falha_id, tipo_barragem_id) VALUES (?, ?)",
                        (int(target_id), int(tb_id)),
                    )
            return int(target_id)
        if action == "delete":
            cur.execute("DELETE FROM modos_falha_tipo_barragem WHERE modos_falha_id = ?", (int(target_id),))
            cur.execute("DELETE FROM modos_falha WHERE id = ?", (int(target_id),))
            return int(target_id)

    elif entity_type == "anomalias":
        if action == "create":
            cur.execute(
                "INSERT INTO anomalias (modos_falha_id, usuario_id, tipo_anomalia_id, gravidade, peso, image_path) VALUES (?, ?, ?, ?, ?, ?)",
                (int(payload["modos_falha_id"]), uid, int(payload["tipo_anomalia_id"]), float(payload["gravidade"]), float(payload["peso"]), payload.get("image_path")),
            )
            novo_id = cur.lastrowid
            for z_id in payload.get("zonas_ids", []):
                cur.execute("INSERT OR IGNORE INTO anomalia_zona (anomalia_id, zona_id) VALUES (?, ?)", (int(novo_id), int(z_id)))
            for m_id in payload.get("materiais_ids", []):
                cur.execute("INSERT OR IGNORE INTO anomalia_tipo_material (anomalia_id, tipo_mat_id) VALUES (?, ?)", (int(novo_id), int(m_id)))
            return novo_id
        if action == "update":
            cur.execute(
                "UPDATE anomalias SET gravidade = ?, peso = ?, image_path = ? WHERE id = ?",
                (float(payload["gravidade"]), float(payload["peso"]), payload.get("image_path"), int(target_id)),
            )
            if "zonas_ids" in payload:
                cur.execute("DELETE FROM anomalia_zona WHERE anomalia_id = ?", (int(target_id),))
                for z_id in payload["zonas_ids"]:
                    cur.execute("INSERT OR IGNORE INTO anomalia_zona (anomalia_id, zona_id) VALUES (?, ?)", (int(target_id), int(z_id)))
            if "materiais_ids" in payload:
                cur.execute("DELETE FROM anomalia_tipo_material WHERE anomalia_id = ?", (int(target_id),))
                for m_id in payload["materiais_ids"]:
                    cur.execute("INSERT OR IGNORE INTO anomalia_tipo_material (anomalia_id, tipo_mat_id) VALUES (?, ?)", (int(target_id), int(m_id)))
            return int(target_id)
        if action == "delete":
            cur.execute("DELETE FROM anomalia_zona WHERE anomalia_id = ?", (int(target_id),))
            cur.execute("DELETE FROM anomalia_tipo_material WHERE anomalia_id = ?", (int(target_id),))
            cur.execute("DELETE FROM anomalias WHERE id = ?", (int(target_id),))
            return int(target_id)

    raise ValueError(f"Operação não suportada: {entity_type}.{action}")


def submeter_alteracao_configuracao(
    role: str,
    user_id: Any,
    user_name: str,
    entity_type: str,
    action: str,
    payload: Dict[str, Any],
    target_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Ponto único para alterações em configurações globais:
    - super_admin / approver: aplica imediatamente nas tabelas globais (status='applied').
    - user: cria proposta pendente em config_change_requests (status='pending');
      não altera as tabelas globais até aprovação.
    """
    if not can_propose_config(role):
        raise PermissionError("Perfil inválido para alterar configurações.")
    if entity_type not in ENTITY_LABELS or action not in ACTION_LABELS:
        raise ValueError(f"Entidade ou ação inválida: {entity_type}/{action}")

    with closing(conectar_db()) as conn:
        if can_apply_config_directly(role):
            affected_id = _aplicar_operacao_config(conn, entity_type, action, payload, target_id, user_id)
            conn.commit()
            return {"status": "applied", "id": affected_id}

        cur = conn.cursor()
        cur.execute(
            """INSERT INTO config_change_requests
               (entity_type, action, target_id, payload_json, status, proposed_by, proposed_by_name)
               VALUES (?, ?, ?, ?, 'pending', ?, ?)""",
            (entity_type, action, int(target_id) if target_id is not None else None, json.dumps(payload, ensure_ascii=False), str(user_id), str(user_name)),
        )
        req_id = cur.lastrowid
        conn.commit()
        return {"status": "pending", "request_id": req_id}


def contar_propostas_pendentes() -> int:
    try:
        with closing(conectar_db()) as conn:
            row = conn.cursor().execute(
                "SELECT COUNT(*) FROM config_change_requests WHERE status = 'pending'"
            ).fetchone()
            return int(row[0]) if row else 0
    except Exception:
        return 0


def listar_propostas_configuracao(role: str, user_id: Any, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    - approver / super_admin: vê toda a fila de propostas.
    - user: vê apenas as suas próprias propostas.
    """
    with closing(conectar_db()) as conn:
        cur = conn.cursor()
        clauses = []
        params: List[Any] = []
        if not can_approve_configs(role):
            clauses.append("proposed_by = ?")
            params.append(str(user_id))
        if status_filter and status_filter in ("pending", "approved", "rejected"):
            clauses.append("status = ?")
            params.append(status_filter)

        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = cur.execute(f"""
            SELECT id, entity_type, action, target_id, payload_json, status,
                   proposed_by, proposed_by_name, reviewed_by, review_note,
                   created_at, reviewed_at
            FROM config_change_requests
            {where}
            ORDER BY id DESC
        """, params).fetchall()

    resultado = []
    for r in rows:
        try:
            payload = json.loads(r[4]) if r[4] else {}
        except Exception:
            payload = {}
        resultado.append({
            "id": r[0],
            "entity_type": r[1],
            "action": r[2],
            "target_id": r[3],
            "payload": payload,
            "status": r[5],
            "proposed_by": r[6],
            "proposed_by_name": r[7] or r[6],
            "reviewed_by": r[8],
            "review_note": r[9] or "",
            "created_at": r[10],
            "reviewed_at": r[11],
        })
    return resultado


def aprovar_proposta_configuracao(request_id: int, reviewer_id: Any, reviewer_role: str, review_note: str = "") -> Dict[str, Any]:
    """Aprova uma proposta pendente e incorpora-a nas tabelas globais."""
    if not can_approve_configs(reviewer_role):
        raise PermissionError("Apenas Aprovadores ou o Usuário Supremo podem aprovar alterações.")

    with closing(conectar_db()) as conn:
        cur = conn.cursor()
        row = cur.execute("""
            SELECT id, entity_type, action, target_id, payload_json, status, proposed_by
            FROM config_change_requests
            WHERE id = ?
        """, (int(request_id),)).fetchone()
        if not row:
            raise ValueError("Proposta não encontrada.")
        if row[5] != "pending":
            raise ValueError(f"Esta proposta já foi processada (estado: {row[5]}).")

        payload = json.loads(row[4]) if row[4] else {}
        affected_id = _aplicar_operacao_config(conn, row[1], row[2], payload, row[3], row[6])

        cur.execute("""
            UPDATE config_change_requests
            SET status = 'approved', reviewed_by = ?, review_note = ?, reviewed_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (str(reviewer_id), review_note.strip() or None, int(request_id)))
        conn.commit()
        return {"status": "approved", "request_id": int(request_id), "affected_id": affected_id}


def rejeitar_proposta_configuracao(request_id: int, reviewer_id: Any, reviewer_role: str, review_note: str = "") -> Dict[str, Any]:
    """Rejeita uma proposta pendente sem alterar as tabelas globais."""
    if not can_approve_configs(reviewer_role):
        raise PermissionError("Apenas Aprovadores ou o Usuário Supremo podem rejeitar alterações.")

    with closing(conectar_db()) as conn:
        cur = conn.cursor()
        row = cur.execute(
            "SELECT id, status FROM config_change_requests WHERE id = ?",
            (int(request_id),),
        ).fetchone()
        if not row:
            raise ValueError("Proposta não encontrada.")
        if row[1] != "pending":
            raise ValueError(f"Esta proposta já foi processada (estado: {row[1]}).")

        cur.execute("""
            UPDATE config_change_requests
            SET status = 'rejected', reviewed_by = ?, review_note = ?, reviewed_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (str(reviewer_id), review_note.strip() or None, int(request_id)))
        conn.commit()
        return {"status": "rejected", "request_id": int(request_id)}
