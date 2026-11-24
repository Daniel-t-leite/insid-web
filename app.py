import sqlite3
import streamlit as st
import re
import pandas as pd
import os
import time
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Optional
from contextlib import closing
import plotly.graph_objects as go
import plotly.express as px

BASE_DIR = Path(__file__).resolve().parent
UPLOADS_DIR = BASE_DIR / "uploads"
LOGO_PATH = BASE_DIR / "inSID_logo.jpg"
ALLOWED_IMAGE_EXTS = {".jpg", ".jpeg", ".png"}


def resolver_caminho_arquivo(caminho: Optional[str]) -> Optional[Path]:
    """Resolve caminhos relativos ao diretório da aplicação e restaura uploads da BD se o disco reiniciar."""
    if not caminho:
        return None
    normalizado = str(caminho).replace("\\", "/").strip()
    if not normalizado:
        return None
    candidato = Path(normalizado)
    if not candidato.is_absolute():
        candidato = (BASE_DIR / candidato).resolve()
    try:
        candidato.relative_to(BASE_DIR)
    except ValueError:
        return None
    if candidato.exists():
        return candidato
    # Se o disco efémero foi reiniciado, restaura a imagem a partir da BD persistente (Turso/SQLite)
    dados = carregar_midia_db(normalizado)
    if dados:
        try:
            candidato.parent.mkdir(parents=True, exist_ok=True)
            with open(candidato, "wb") as f:
                f.write(dados)
            return candidato
        except OSError:
            return None
    return None


def salvar_arquivo_upload(arquivo, subpasta: str, prefixo: str, max_mb: int = 5) -> Optional[str]:
    """Valida, grava em uploads/<subpasta> e persiste na BD (Turso/SQLite) devolvendo caminho POSIX relativo."""
    if arquivo is None:
        return None
    try:
        if getattr(arquivo, "size", 0) > max_mb * 1024 * 1024:
            st.error(f"Ficheiro demasiado grande (máximo permitido: {max_mb} MB).")
            return None
        extensao = Path(arquivo.name).suffix.lower()
        if extensao not in ALLOWED_IMAGE_EXTS:
            st.error("Formato de imagem não suportado. Utilize JPG, JPEG ou PNG.")
            return None
        slug = re.sub(r"[^a-z0-9_-]+", "_", prefixo.lower()).strip("_") or "imagem"
        nome_arquivo = f"{slug}_{int(time.time())}{extensao}"
        destino_dir = UPLOADS_DIR / subpasta
        destino_dir.mkdir(parents=True, exist_ok=True)
        destino = destino_dir / nome_arquivo
        dados = bytes(arquivo.getbuffer())
        with open(destino, "wb") as f:
            f.write(dados)
        caminho_rel = f"uploads/{subpasta}/{nome_arquivo}"
        salvar_midia_db(caminho_rel, dados)
        return caminho_rel
    except OSError:
        st.error("Não foi possível guardar a imagem no servidor. Tente novamente.")
        return None
    except Exception:
        st.error("Ocorreu um erro inesperado ao processar a imagem enviada.")
        return None


from db import (
    conectar_db, criar_usuario, verificar_credenciais, email_existe,
    obter_proximo_codigo_usuario, obter_tipos_barragem, 
    definir_barragem_analise, obter_barragem_analise, 
    obter_barragens_usuario, atualizar_barragem, excluir_barragem, 
    cadastrar_barragem, listar_usuarios, atualizar_status_usuario, 
    atualizar_admin_usuario, excluir_usuario,
    salvar_midia_db, carregar_midia_db, remover_midia_db
)
from rbac import (
    ROLE_SUPER_ADMIN, ROLE_APPROVER, ROLE_USER, VALID_ROLES,
    ROLE_LABELS, ENTITY_LABELS, ACTION_LABELS,
    normalize_role, can_manage_users, can_approve_configs,
    can_apply_config_directly, can_access_dam_analyses, can_view_all_dam_analyses,
    alterar_role_usuario_seguro, alterar_status_usuario_seguro, excluir_usuario_seguro,
    listar_barragens_escopo, obter_barragem_autorizada, obter_barragem_analise_escopo,
    definir_barragem_analise_escopo, atualizar_barragem_escopo, excluir_barragem_escopo,
    submeter_alteracao_configuracao, contar_propostas_pendentes,
    listar_propostas_configuracao, aprovar_proposta_configuracao, rejeitar_proposta_configuracao,
)
from i18n import get_text, SUPPORTED_LANGS
from theme_desproj import aplicar_tema_desproj

# Configuração da página e tema visual alinhado a https://www.desproj.com/
st.set_page_config(page_title="Plataforma inSID — desproj", page_icon="🔐", layout="wide")
aplicar_tema_desproj()


def obter_idioma() -> str:
    lang = st.session_state.get("lang", "pt")
    return lang if lang in SUPPORTED_LANGS else "pt"


def t(key: str, **kwargs) -> str:
    return get_text(key, lang=obter_idioma(), **kwargs)


def render_seletor_idioma(key_suffix: str = "sidebar") -> None:
    atual = obter_idioma()
    escolha = st.radio(
        t("lang_label"),
        options=["pt", "en"],
        format_func=lambda c: "🇵🇹 Português" if c == "pt" else "🇬🇧 English",
        index=0 if atual == "pt" else 1,
        horizontal=True,
        key=f"lang_selector_{key_suffix}",
    )
    if escolha != atual:
        st.session_state["lang"] = escolha
        st.rerun()


def obter_perfil_atual() -> str:
    return normalize_role(st.session_state.get("role"), st.session_state.get("is_admin"))


def rotulo_perfil(role: str) -> str:
    return t(f"role_{role}")


def pagina_inicial_por_perfil(role: str) -> str:
    return "fila_aprovacoes" if role == ROLE_APPROVER else "principal"


def exibir_aviso_workflow_config() -> None:
    role = obter_perfil_atual()
    if role == ROLE_USER:
        st.info(t("workflow_user_banner"))
    elif can_approve_configs(role):
        pend = contar_propostas_pendentes()
        if pend > 0:
            st.caption(t("workflow_pending_caption", count=pend))


def executar_alteracao_config_ui(
    entity_type: str,
    action: str,
    payload: dict,
    target_id=None,
    msg_sucesso: str = "Alteração aplicada com sucesso!",
) -> bool:
    role = obter_perfil_atual()
    res = submeter_alteracao_configuracao(
        role=role,
        user_id=st.session_state.get("usuario_id", "1"),
        user_name=st.session_state.get("usuario_nome", "Utilizador"),
        entity_type=entity_type,
        action=action,
        payload=payload,
        target_id=target_id,
    )
    if res["status"] == "pending":
        st.info(t("workflow_submitted_pending", req_id=res["request_id"]))
        return False
    st.success(msg_sucesso)
    return True


def pagina_fila_aprovacoes():
    """Fila de aprovação de alterações de configurações globais (Aprovador e Usuário Supremo)."""
    role = obter_perfil_atual()
    if not can_approve_configs(role):
        st.error(t("approvals_denied"))
        return

    st.title(t("approvals_title"))
    st.caption(t("approvals_caption"))

    tab_pend, tab_aprov, tab_rej = st.tabs([
        t("approvals_tab_pending"),
        t("approvals_tab_approved"),
        t("approvals_tab_rejected"),
    ])

    with tab_pend:
        pendentes = listar_propostas_configuracao(role, st.session_state.get("usuario_id"), status_filter="pending")
        if not pendentes:
            st.success(t("approvals_empty_pending"))
        else:
            for prop in pendentes:
                ent_label = t(f"entity_{prop['entity_type']}")
                act_label = t(f"action_{prop['action']}")
                titulo = f"#{prop['id']} · [{act_label}] {ent_label} — {prop['proposed_by_name']}"
                with st.expander(titulo, expanded=True):
                    st.write(f"**Data:** {prop['created_at']} | **ID:** {prop['target_id'] or 'Novo / New'}")
                    st.json(prop["payload"])
                    nota = st.text_input(t("approvals_review_note"), key=f"nota_rev_{prop['id']}")
                    col_a, col_r = st.columns(2)
                    with col_a:
                        if st.button(t("approvals_btn_approve"), key=f"aprov_{prop['id']}", type="primary"):
                            try:
                                aprovar_proposta_configuracao(prop["id"], st.session_state["usuario_id"], role, nota)
                                st.success(t("approvals_approved_ok", req_id=prop["id"]))
                                st.rerun()
                            except Exception as e:
                                st.error(str(e))
                    with col_r:
                        if st.button(t("approvals_btn_reject"), key=f"rej_{prop['id']}"):
                            try:
                                rejeitar_proposta_configuracao(prop["id"], st.session_state["usuario_id"], role, nota)
                                st.warning(t("approvals_rejected_ok", req_id=prop["id"]))
                                st.rerun()
                            except Exception as e:
                                st.error(str(e))

    with tab_aprov:
        aprovadas = listar_propostas_configuracao(role, st.session_state.get("usuario_id"), status_filter="approved")
        if not aprovadas:
            st.info(t("approvals_empty_approved"))
        else:
            for prop in aprovadas:
                ent_label = t(f"entity_{prop['entity_type']}")
                act_label = t(f"action_{prop['action']}")
                with st.expander(f"🟢 #{prop['id']} · [{act_label}] {ent_label} — {prop['proposed_by_name']}"):
                    st.write(f"**Data:** {prop['reviewed_at']} | **Nota:** {prop['review_note'] or '—'}")
                    st.json(prop["payload"])

    with tab_rej:
        rejeitadas = listar_propostas_configuracao(role, st.session_state.get("usuario_id"), status_filter="rejected")
        if not rejeitadas:
            st.info(t("approvals_empty_rejected"))
        else:
            for prop in rejeitadas:
                ent_label = t(f"entity_{prop['entity_type']}")
                act_label = t(f"action_{prop['action']}")
                with st.expander(f"🔴 #{prop['id']} · [{act_label}] {ent_label} — {prop['proposed_by_name']}"):
                    st.write(f"**Data:** {prop['reviewed_at']} | **Nota:** {prop['review_note'] or '—'}")
                    st.json(prop["payload"])


def pagina_minhas_propostas():
    """Lista as propostas de alteração de configuração submetidas pelo utilizador atual."""
    role = obter_perfil_atual()
    st.title(t("my_proposals_title"))
    st.caption(t("my_proposals_caption"))

    propostas = listar_propostas_configuracao(role, st.session_state.get("usuario_id"))
    if not propostas:
        st.info(t("my_proposals_empty"))
        return

    badges = {
        "pending": t("status_pending"),
        "approved": t("status_approved"),
        "rejected": t("status_rejected"),
    }
    for prop in propostas:
        ent_label = t(f"entity_{prop['entity_type']}")
        act_label = t(f"action_{prop['action']}")
        st_badge = badges.get(prop["status"], prop["status"])
        with st.expander(f"{st_badge} · #{prop['id']} [{act_label}] {ent_label} ({prop['created_at']})"):
            if prop["review_note"]:
                st.write(f"**Nota:** {prop['review_note']}")
            st.json(prop["payload"])


def gerenciar_tipos_anomalia():
    """Página de gerenciamento de tipos de anomalia"""
    st.title("📋 Gerenciamento de Tipos de Anomalia")
    exibir_aviso_workflow_config()

    # Conexão com o banco
    conn = conectar_db()

    # Inicialização de estados
    if 'editando_tipo_anomalia' not in st.session_state:
        st.session_state.editando_tipo_anomalia = None
    if 'ultima_atualizacao' not in st.session_state:
        st.session_state.ultima_atualizacao = time.time()

    # Carrega tipos de anomalia existentes
    df_tipos = pd.read_sql("SELECT id, nome, descricao FROM tipo_anomalia ORDER BY nome", conn)

    # Operações disponíveis
    operacao = st.radio("Selecione a operação:", ["Visualizar", "Adicionar", "Editar", "Excluir"], horizontal=True)

    if operacao == "Visualizar":
        st.subheader("Tipos de Anomalia Cadastrados")
        if not df_tipos.empty:
            st.dataframe(df_tipos.set_index('id'), use_container_width=True)
        else:
            st.info("ℹ️ Nenhum tipo de anomalia cadastrado ainda.")

    elif operacao == "Adicionar":
        st.subheader("Adicionar Novo Tipo de Anomalia")
        with st.form("form_add_tipo_anomalia", clear_on_submit=True):
            nome = st.text_input("Nome do Tipo de Anomalia*", max_chars=100)
            descricao = st.text_area("Descrição", height=100)
            
            if st.form_submit_button("💾 Salvar Tipo de Anomalia"):
                if not nome.strip():
                    st.error("O nome do tipo de anomalia é obrigatório")
                else:
                    try:
                        aplicado = executar_alteracao_config_ui(
                            "tipo_anomalia",
                            "create",
                            {"nome": nome.strip(), "descricao": descricao.strip() if descricao else None},
                            msg_sucesso="Tipo de anomalia cadastrado com sucesso!",
                        )
                        if aplicado:
                            st.session_state.ultima_atualizacao = time.time()
                            st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("Já existe um tipo de anomalia com este nome.")
                    except Exception as e:
                        st.error(f"Erro ao cadastrar: {str(e)}")

    elif operacao == "Editar":
        st.subheader("Editar Tipo de Anomalia")

        if df_tipos.empty:
            st.warning("Nenhum tipo de anomalia cadastrado para editar.")
        else:
            tipo_id = st.selectbox(
                "Selecione o tipo de anomalia para editar:",
                options=df_tipos['id'],
                format_func=lambda x: f"{df_tipos[df_tipos['id']==x]['nome'].values[0]}"
            )
            
            # Armazena o tipo selecionado na sessão
            st.session_state.editando_tipo_anomalia = tipo_id

            tipo_anomalia = pd.read_sql(f"""
                SELECT * FROM tipo_anomalia WHERE id = {tipo_id}
            """, conn).iloc[0]

            with st.form("form_edit_tipo_anomalia"):
                novo_nome = st.text_input("Nome do Tipo de Anomalia*", 
                                        value=tipo_anomalia['nome'], 
                                        max_chars=100)
                nova_descricao = st.text_area("Descrição", 
                                            value=tipo_anomalia['descricao'] or "", 
                                            height=100)

                col1, col2 = st.columns([1, 1])
                with col1:
                    if st.form_submit_button("💾 Salvar Alterações"):
                        if not novo_nome.strip():
                            st.error("O nome do tipo de anomalia é obrigatório")
                        else:
                            try:
                                aplicado = executar_alteracao_config_ui(
                                    "tipo_anomalia",
                                    "update",
                                    {"nome": novo_nome.strip(), "descricao": nova_descricao.strip() if nova_descricao else None},
                                    target_id=int(tipo_id),
                                    msg_sucesso="Tipo de anomalia atualizado com sucesso!",
                                )
                                if aplicado:
                                    st.session_state.editando_tipo_anomalia = None
                                    st.session_state.ultima_atualizacao = time.time()
                                    st.rerun()
                            except sqlite3.IntegrityError:
                                st.error("Já existe outro tipo de anomalia com este nome.")
                            except Exception as e:
                                st.error(f"Erro ao atualizar: {str(e)}")
                with col2:
                    if st.form_submit_button("❌ Cancelar"):
                        st.session_state.editando_tipo_anomalia = None
                        st.rerun()

    elif operacao == "Excluir":
        st.subheader("Excluir Tipo de Anomalia")

        if df_tipos.empty:
            st.warning("Nenhum tipo de anomalia cadastrado para excluir.")
        else:
            tipo_id = st.selectbox(
                "Selecione o tipo de anomalia para excluir:",
                options=df_tipos['id'],
                format_func=lambda x: f"{df_tipos[df_tipos['id']==x]['nome'].values[0]}"
            )

            tipo_anomalia = pd.read_sql(f"""
                SELECT * FROM tipo_anomalia WHERE id = {tipo_id}
            """, conn).iloc[0]

            st.warning("⚠️ Você está prestes a excluir permanentemente este tipo de anomalia:")
            st.write(f"**Nome:** {tipo_anomalia['nome']}")
            st.write(f"**Descrição:** {tipo_anomalia['descricao'][:100]}..." if tipo_anomalia['descricao'] else "Sem descrição")

            # Verifica se existem anomalias associadas
            anomalias_associadas = pd.read_sql(
                f"SELECT 1 FROM anomalias WHERE tipo_anomalia_id = {tipo_id} LIMIT 1",
                conn
            )
            
            if not anomalias_associadas.empty:
                st.error("⛔ Este tipo de anomalia possui registros associados e não pode ser excluído.")
            else:
                if st.button("🗑️ Confirmar Exclusão", type="primary"):
                    try:
                        aplicado = executar_alteracao_config_ui(
                            "tipo_anomalia",
                            "delete",
                            {"nome": tipo_anomalia['nome']},
                            target_id=int(tipo_id),
                            msg_sucesso="Tipo de anomalia excluído com sucesso!",
                        )
                        if aplicado:
                            st.session_state.ultima_atualizacao = time.time()
                            st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao excluir: {str(e)}")

    conn.close()
    
    if st.button("← Voltar"):
        st.session_state['pagina'] = "principal"
        st.rerun()

def gerenciar_modos_falha_anomalias():
    """Página de gerenciamento de modos de falha e anomalias com todos os relacionamentos"""
    st.title("⚙️ Gerenciamento de Modos de Falha e Anomalias")
    exibir_aviso_workflow_config()

    # Conexão com o banco
    conn = conectar_db()

    # --- INICIALIZAÇÃO DE ESTADOS ---
    if 'modo_falha_selecionado' not in st.session_state:
        st.session_state.modo_falha_selecionado = None
    if 'anomalias_selecionadas' not in st.session_state:
        st.session_state.anomalias_selecionadas = []
    if 'editando_anomalia' not in st.session_state:
        st.session_state.editando_anomalia = None
    if 'ultima_atualizacao' not in st.session_state:
        st.session_state.ultima_atualizacao = time.time()
    if 'editando_modo_falha' not in st.session_state:
        st.session_state.editando_modo_falha = None

    # --- CONTROLES SUPERIORES (SEMPRE VISÍVEIS) ---
    st.markdown("---")
    
    # Carrega dados para relacionamentos
    tipos_barragem = pd.read_sql("SELECT id, nome FROM tipos_barragem ORDER BY nome", conn)
    tipos_falha = pd.read_sql("SELECT id, nome FROM tipo_modo_falha ORDER BY nome", conn)
    tipos_anomalia = pd.read_sql("SELECT id, nome FROM tipo_anomalia ORDER BY nome", conn)
    tipos_zona = pd.read_sql("SELECT id, nome FROM tipos_zonas_bar ORDER BY nome", conn)
    tipos_material = pd.read_sql("SELECT id, nome FROM tipos_materiais ORDER BY nome", conn)

    # Container para controles superiores
    with st.container():
        # 1. SELEÇÃO DE MODO DE FALHA
        modos_falha = pd.read_sql("SELECT id, nome FROM modos_falha ORDER BY nome", conn)
        
        col1, col2 = st.columns([3, 1])
        with col1:
            novo_modo_selecionado = st.selectbox(
                "🔍 Modo de Falha Ativo:",
                options=[None] + modos_falha['id'].tolist(),
                format_func=lambda x: "Selecione um modo de falha..." if x is None 
                                    else modos_falha[modos_falha['id']==x]['nome'].values[0],
                key="select_modo_falha_global"
            )
        
        with col2:
            if st.button("Limpar Seleção"):
                st.session_state.modo_falha_selecionado = None
                st.session_state.anomalias_selecionadas = []
                st.session_state.editando_modo_falha = None
                st.rerun()
        
        # Atualiza estado se houve mudança
        if novo_modo_selecionado != st.session_state.modo_falha_selecionado:
            st.session_state.modo_falha_selecionado = novo_modo_selecionado
            st.session_state.anomalias_selecionadas = []
            st.session_state.ultima_atualizacao = time.time()
            st.rerun()

    st.markdown("---")

    # 2. SELEÇÃO DE TIPOS DE BARRAGEM E ANOMALIAS (APENAS SE MODO SELECIONADO E NÃO EDITANDO)
    if st.session_state.modo_falha_selecionado and not st.session_state.get('editando_modo_falha'):
        with st.container():
            # Forçar refresh dos dados se a página foi recarregada
            if st.session_state.ultima_atualizacao < time.time() - 1:
                st.session_state.anomalias_selecionadas = []
                st.session_state.ultima_atualizacao = time.time()
            
            # --- SELEÇÃO DE TIPOS DE BARRAGEM ASSOCIADOS ---
            tipos_barragem_associados = pd.read_sql(
                f"SELECT tipo_barragem_id FROM modos_falha_tipo_barragem WHERE modos_falha_id = {st.session_state.modo_falha_selecionado}",
                conn
            )['tipo_barragem_id'].tolist()
            
            novos_tipos_barragem = st.multiselect(
                "➕  Tipos de Barragem Associados (desmarque para remover):",
                options=tipos_barragem['id'].tolist(),
                default=tipos_barragem_associados,
                format_func=lambda x: tipos_barragem[tipos_barragem['id']==x]['nome'].values[0],
                key="multiselect_tipos_barragem"
            )
            
            if set(novos_tipos_barragem) != set(tipos_barragem_associados):
                if st.button("💾 Salvar Alterações nos Tipos de Barragem"):
                    try:
                        mf_info = pd.read_sql(
                            "SELECT nome, id_tipo_modo_falha, descricao, referencia_tecnica, image_path FROM modos_falha WHERE id = ?",
                            conn,
                            params=(int(st.session_state.modo_falha_selecionado),),
                        )
                        if not mf_info.empty:
                            row_mf = mf_info.iloc[0]
                            aplicado = executar_alteracao_config_ui(
                                "modos_falha",
                                "update",
                                {
                                    "nome": row_mf["nome"],
                                    "id_tipo_modo_falha": int(row_mf["id_tipo_modo_falha"]),
                                    "descricao": row_mf["descricao"],
                                    "referencia_tecnica": row_mf["referencia_tecnica"],
                                    "image_path": row_mf["image_path"],
                                    "tipos_barragem_ids": [int(x) for x in novos_tipos_barragem],
                                },
                                target_id=int(st.session_state.modo_falha_selecionado),
                                msg_sucesso="Tipos de barragem atualizados com sucesso!",
                            )
                            if aplicado:
                                st.session_state.ultima_atualizacao = time.time()
                                st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao atualizar tipos de barragem: {str(e)}")
            
            st.markdown("---")
            
            # --- SELEÇÃO DE ANOMALIAS ---
            anomalias = pd.read_sql(f"""
                SELECT a.id, ta.nome as tipo_anomalia 
                FROM anomalias a
                JOIN tipo_anomalia ta ON a.tipo_anomalia_id = ta.id
                WHERE a.modos_falha_id = {st.session_state.modo_falha_selecionado}
                ORDER BY ta.nome
            """, conn)
            
            if not anomalias.empty:
                if not st.session_state.anomalias_selecionadas:
                    st.session_state.anomalias_selecionadas = anomalias['id'].tolist()
                
                novas_anomalias_selecionadas = st.multiselect(
                    "➕  Anomalias Associadas (desmarque para excluir):",
                    options=anomalias['id'].tolist(),
                    default=st.session_state.anomalias_selecionadas,
                    format_func=lambda x: anomalias[anomalias['id']==x]['tipo_anomalia'].values[0],
                    key="multiselect_anomalias"
                )
                
                if set(novas_anomalias_selecionadas) != set(st.session_state.anomalias_selecionadas):
                    anomalias_para_excluir = list(set(st.session_state.anomalias_selecionadas) - set(novas_anomalias_selecionadas))
                    
                    if anomalias_para_excluir:
                        if st.button(f"Confirmar Exclusão de {len(anomalias_para_excluir)} Anomalia(s)"):
                            try:
                                houve_aplicacao = False
                                for anomalia_id in anomalias_para_excluir:
                                    aplicado = executar_alteracao_config_ui(
                                        "anomalias",
                                        "delete",
                                        {"id": int(anomalia_id)},
                                        target_id=int(anomalia_id),
                                        msg_sucesso="Anomalia excluída com sucesso!",
                                    )
                                    if aplicado:
                                        houve_aplicacao = True
                                if houve_aplicacao:
                                    st.session_state.anomalias_selecionadas = novas_anomalias_selecionadas
                                    st.session_state.ultima_atualizacao = time.time()
                                    st.rerun()
                            except Exception as e:
                                st.error(f"Erro ao excluir: {str(e)}")
                    else:
                        st.session_state.anomalias_selecionadas = novas_anomalias_selecionadas
                        st.session_state.ultima_atualizacao = time.time()
            else:
                st.info("ℹ️ Nenhuma anomalia cadastrada para este modo de falha.")
                st.session_state.anomalias_selecionadas = []
    
    st.markdown("---")

    

    # Modo de operação principal
    modo_principal = st.radio("Selecione o que gerenciar:", ["Modos de Falha", "Anomalias"], horizontal=True)

    if modo_principal == "Modos de Falha":
        st.header("Gerenciamento de Modos de Falha")
        
        # Carrega modos de falha existentes
        df_modos = pd.read_sql("""
            SELECT mf.id, mf.nome, tmf.nome as tipo, mf.descricao 
            FROM modos_falha mf
            JOIN tipo_modo_falha tmf ON mf.id_tipo_modo_falha = tmf.id
            ORDER BY mf.nome
        """, conn)

        submodo = st.radio("Operação:", ["Visualizar", "Adicionar", "Editar", "Excluir"], horizontal=True)

        if submodo == "Visualizar":
            st.subheader("Modos de Falha Cadastrados")
            if not df_modos.empty:
                contagem_anomalias = pd.read_sql("""
                    SELECT modos_falha_id, COUNT(*) as total 
                    FROM anomalias 
                    GROUP BY modos_falha_id
                """, conn)
                
                tipos_barragem_por_modo = pd.read_sql("""
                    SELECT mf.id as modo_falha_id, GROUP_CONCAT(tb.nome, ', ') as tipos_barragem
                    FROM modos_falha mf
                    LEFT JOIN modos_falha_tipo_barragem mftb ON mf.id = mftb.modos_falha_id
                    LEFT JOIN tipos_barragem tb ON mftb.tipo_barragem_id = tb.id
                    GROUP BY mf.id
                """, conn)
                
                df_display = df_modos.merge(contagem_anomalias, 
                                          left_on='id', 
                                          right_on='modos_falha_id', 
                                          how='left').fillna(0)
                df_display = df_display.merge(tipos_barragem_por_modo,
                                            left_on='id',
                                            right_on='modo_falha_id',
                                            how='left')
                df_display['total'] = df_display['total'].astype(int)
                
                st.dataframe(df_display[['id', 'nome', 'tipo', 'total', 'tipos_barragem']]
                            .rename(columns={
                                'total': 'Anomalias',
                                'tipos_barragem': 'Tipos de Barragem'
                            })
                            .set_index('id'), 
                           use_container_width=True)
                
            else:
                st.info("ℹ️ Nenhum modo de falha cadastrado ainda.")

        elif submodo == "Adicionar":
            st.subheader("Adicionar Novo Modo de Falha")
            with st.form("form_add_modo_falha", clear_on_submit=True):
                col1, col2 = st.columns(2)
                with col1:
                    nome = st.text_input("Nome do Modo de Falha*", max_chars=100)
                    id_tipo = st.selectbox(
                        "Tipo de Modo de Falha*",
                        options=tipos_falha['id'],
                        format_func=lambda x: tipos_falha[tipos_falha['id']==x]['nome'].values[0]
                    )
                with col2:
                    referencia = st.text_input("Referência Técnica (opcional)")
                    imagem = st.file_uploader("Imagem Representativa (opcional)", type=["jpg", "jpeg", "png"])
                
                descricao = st.text_area("Descrição Técnica", height=100)
                
                tipos_barragem_selecionados = st.multiselect(
                    "Tipos de Barragem Associados*",
                    options=tipos_barragem['id'],
                    format_func=lambda x: tipos_barragem[tipos_barragem['id']==x]['nome'].values[0]
                )

                if st.form_submit_button("💾 Salvar Modo de Falha"):
                    if not nome.strip():
                        st.error("O nome do modo de falha é obrigatório")
                    elif not tipos_barragem_selecionados:
                        st.error("Selecione pelo menos um tipo de barragem")
                    else:
                        caminho_imagem = None
                        if imagem is not None:
                            caminho_imagem = salvar_arquivo_upload(imagem, "modos_falha", f"modo_falha_{nome}")
                            if caminho_imagem is None:
                                return

                        try:
                            aplicado = executar_alteracao_config_ui(
                                "modos_falha",
                                "create",
                                {
                                    "id_tipo_modo_falha": int(id_tipo),
                                    "nome": nome.strip(),
                                    "descricao": descricao.strip() if descricao else None,
                                    "referencia_tecnica": referencia.strip() if referencia else None,
                                    "image_path": caminho_imagem,
                                    "tipos_barragem_ids": [int(x) for x in tipos_barragem_selecionados],
                                },
                                msg_sucesso="Modo de falha cadastrado com sucesso!",
                            )
                            if aplicado:
                                st.session_state.ultima_atualizacao = time.time()
                                st.rerun()
                        except sqlite3.IntegrityError:
                            st.error("Já existe um modo de falha com este nome.")
                        except Exception as e:
                            st.error(f"Erro ao cadastrar: {str(e)}")

        elif submodo == "Editar":
            st.subheader("Editar Modo de Falha")

            if df_modos.empty:
                st.warning("Nenhum modo de falha cadastrado para editar.")
            else:
                modo_id = st.selectbox(
                    "Selecione o modo de falha para editar:",
                    options=df_modos['id'],
                    format_func=lambda x: f"{df_modos[df_modos['id']==x]['nome'].values[0]}"
                )
                
                # Define que estamos editando um modo de falha
                st.session_state.editando_modo_falha = modo_id
                
                modo_falha = pd.read_sql(f"""
                    SELECT * FROM modos_falha WHERE id = {modo_id}
                """, conn).iloc[0]

                tipos_barragem_associados = pd.read_sql(
                    f"SELECT tipo_barragem_id FROM modos_falha_tipo_barragem WHERE modos_falha_id = {modo_id}",
                    conn
                )['tipo_barragem_id'].tolist()

                # Formulário de edição sem st.form() para permitir botões adicionais
                col1, col2 = st.columns(2)
                with col1:
                    novo_nome = st.text_input("Nome do Modo de Falha*", value=modo_falha['nome'], max_chars=100)
                    novo_id_tipo = st.selectbox(
                        "Tipo de Modo de Falha*",
                        options=tipos_falha['id'],
                        index=list(tipos_falha['id']).index(modo_falha['id_tipo_modo_falha']),
                        format_func=lambda x: tipos_falha[tipos_falha['id']==x]['nome'].values[0]
                    )
                with col2:
                    nova_referencia = st.text_input("Referência Técnica", 
                                                  value=modo_falha['referencia_tecnica'] or "")
                    nova_imagem = st.file_uploader("Substituir Imagem", 
                                                  type=["jpg", "jpeg", "png"])
                
                nova_descricao = st.text_area("Descrição Técnica", 
                                            value=modo_falha['descricao'] or "", 
                                            height=100)
                
                novos_tipos_barragem = st.multiselect(
                    "Tipos de Barragem Associados*",
                    options=tipos_barragem['id'],
                    default=tipos_barragem_associados,
                    format_func=lambda x: tipos_barragem[tipos_barragem['id']==x]['nome'].values[0]
                )

                col_botoes = st.columns(2)
                with col_botoes[0]:
                    if st.button("💾 Salvar Alterações"):
                        if not novo_nome.strip():
                            st.error("O nome do modo de falha é obrigatório")
                        elif not novos_tipos_barragem:
                            st.error("Selecione pelo menos um tipo de barragem")
                        else:
                            caminho_imagem = modo_falha['image_path']
                            if nova_imagem is not None:
                                caminho_imagem = salvar_arquivo_upload(nova_imagem, "modos_falha", f"modo_falha_{novo_nome}")
                                if caminho_imagem is None:
                                    return

                            try:
                                aplicado = executar_alteracao_config_ui(
                                    "modos_falha",
                                    "update",
                                    {
                                        "id_tipo_modo_falha": int(novo_id_tipo),
                                        "nome": novo_nome.strip(),
                                        "descricao": nova_descricao.strip() if nova_descricao else None,
                                        "referencia_tecnica": nova_referencia.strip() if nova_referencia else None,
                                        "image_path": caminho_imagem,
                                        "tipos_barragem_ids": [int(x) for x in novos_tipos_barragem],
                                    },
                                    target_id=int(modo_id),
                                    msg_sucesso="Modo de falha atualizado com sucesso!",
                                )
                                if aplicado:
                                    st.session_state.editando_modo_falha = None
                                    st.session_state.ultima_atualizacao = time.time()
                                    st.rerun()
                            except sqlite3.IntegrityError:
                                st.error("Já existe outro modo de falha com este nome.")
                            except Exception as e:
                                st.error(f"Erro ao atualizar: {str(e)}")
                
                with col_botoes[1]:
                    if st.button("❌ Cancelar Edição"):
                        st.session_state.editando_modo_falha = None
                        st.rerun()

        elif submodo == "Excluir":
            st.subheader("Excluir Modo de Falha")

            if df_modos.empty:
                st.warning("Nenhum modo de falha cadastrado para excluir.")
            else:
                modo_id = st.selectbox(
                    "Selecione o modo de falha para excluir:",
                    options=df_modos['id'],
                    format_func=lambda x: f"{df_modos[df_modos['id']==x]['nome'].values[0]}"
                )

                modo_falha = pd.read_sql(f"""
                    SELECT * FROM modos_falha WHERE id = {modo_id}
                """, conn).iloc[0]

                st.warning("⚠️ Você está prestes a excluir permanentemente este modo de falha:")
                st.write(f"**Nome:** {modo_falha['nome']}")
                st.write(f"**Descrição:** {modo_falha['descricao'][:100]}..." if modo_falha['descricao'] else "Sem descrição")

                # Verifica relacionamentos
                anomalias_associadas = pd.read_sql(
                    f"SELECT 1 FROM anomalias WHERE modos_falha_id = {modo_id} LIMIT 1",
                    conn
                )
                
                if not anomalias_associadas.empty:
                    st.error("⛔ Este modo de falha possui anomalias associadas e não pode ser excluído.")
                else:
                    img_modo = resolver_caminho_arquivo(modo_falha['image_path'])
                    if img_modo:
                        st.image(str(img_modo), caption="Imagem do Modo de Falha", use_container_width=True)

                    if st.button("🗑️ Confirmar Exclusão", type="primary"):
                        try:
                            aplicado = executar_alteracao_config_ui(
                                "modos_falha",
                                "delete",
                                {"nome": modo_falha['nome']},
                                target_id=int(modo_id),
                                msg_sucesso="Modo de falha excluído com sucesso!",
                            )
                            if aplicado:
                                if img_modo and img_modo.exists():
                                    try:
                                        img_modo.unlink()
                                    except OSError:
                                        pass
                                if modo_falha['image_path']:
                                    remover_midia_db(modo_falha['image_path'])
                                st.session_state.ultima_atualizacao = time.time()
                                st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao excluir: {str(e)}")

    elif modo_principal == "Anomalias":
        st.header("Gerenciamento de Anomalias")
        
        # Se há um modo de falha selecionado, filtra as anomalias
        if st.session_state.modo_falha_selecionado:
            modo_falha_nome = pd.read_sql(
                f"SELECT nome FROM modos_falha WHERE id = {st.session_state.modo_falha_selecionado}", 
                conn
            ).iloc[0]['nome']
            
            st.subheader(f"Anomalias para o Modo de Falha: {modo_falha_nome}")
            
            # Carrega anomalias mesmo que não existam (para mostrar a interface)
            df_anomalias = pd.read_sql(f"""
                SELECT a.id, ta.nome as tipo_anomalia, a.gravidade, a.peso
                FROM anomalias a
                JOIN tipo_anomalia ta ON a.tipo_anomalia_id = ta.id
                WHERE a.modos_falha_id = {st.session_state.modo_falha_selecionado}
                ORDER BY ta.nome
            """, conn)
        else:
            st.subheader("Todas as Anomalias")
            df_anomalias = pd.read_sql("""
                SELECT a.id, mf.nome as modo_falha, ta.nome as tipo_anomalia, 
                    a.gravidade, a.peso
                FROM anomalias a
                JOIN modos_falha mf ON a.modos_falha_id = mf.id
                JOIN tipo_anomalia ta ON a.tipo_anomalia_id = ta.id
                ORDER BY mf.nome, ta.nome
            """, conn)

        submodo = st.radio("Operação:", ["Visualizar", "Adicionar", "Editar", "Excluir"], 
                        horizontal=True, key="submodo_anomalias")

        if submodo == "Visualizar":
            st.subheader("Anomalias Cadastradas")
            if not df_anomalias.empty:
                st.dataframe(df_anomalias.set_index('id'), use_container_width=True)
            else:
                st.info("ℹ️ Nenhuma anomalia cadastrada ainda.")
                
                # Mostra botão para adicionar anomalia mesmo quando não há nenhuma
                if st.session_state.modo_falha_selecionado:
                    if st.button("➕ Cadastrar Primeira Anomalia"):
                        submodo = "Adicionar"
                        st.rerun()

        elif submodo == "Adicionar":
            st.subheader("Adicionar Nova Anomalia")
            
            # Se não há modo de falha selecionado, permite escolher
            if not st.session_state.modo_falha_selecionado:
                modos_falha = pd.read_sql("SELECT id, nome FROM modos_falha ORDER BY nome", conn)
                modo_falha_id = st.selectbox(
                    "Modo de Falha*",
                    options=modos_falha['id'],
                    format_func=lambda x: modos_falha[modos_falha['id']==x]['nome'].values[0]
                )
            else:
                modo_falha_id = st.session_state.modo_falha_selecionado
                modo_nome = pd.read_sql(
                    f"SELECT nome FROM modos_falha WHERE id = {modo_falha_id}", 
                    conn
                ).iloc[0]['nome']
                st.write(f"**Modo de Falha:** {modo_nome}")
            
            with st.form("form_add_anomalia", clear_on_submit=True):
                tipo_anomalia_id = st.selectbox(
                    "Tipo de Anomalia*",
                    options=tipos_anomalia['id'],
                    format_func=lambda x: tipos_anomalia[tipos_anomalia['id']==x]['nome'].values[0]
                )
                
                col1, col2 = st.columns(2)
                with col1:
                    gravidade = st.slider("Gravidade (0-10)*", 0.0, 10.0, 5.0, 0.1)
                with col2:
                    peso = st.slider("Peso (0-10)*", 0.0, 10.0, 5.0, 0.1)
                
                # Relacionamentos N:N
                zonas_selecionadas = st.multiselect(
                    "Zonas relacionadas:",
                    options=tipos_zona['id'],
                    format_func=lambda x: tipos_zona[tipos_zona['id']==x]['nome'].values[0]
                )
                
                materiais_selecionados = st.multiselect(
                    "Tipos de Material relacionados:",
                    options=tipos_material['id'],
                    format_func=lambda x: tipos_material[tipos_material['id']==x]['nome'].values[0]
                )
                
                imagem = st.file_uploader("Imagem (opcional)", type=["jpg", "jpeg", "png"])

                if st.form_submit_button("💾 Salvar Anomalia"):
                    # Processa a imagem se houver
                    caminho_imagem = None
                    if imagem is not None:
                        tipo_nome = tipos_anomalia[tipos_anomalia['id']==tipo_anomalia_id]['nome'].values[0]
                        modo_nome = pd.read_sql(
                            "SELECT nome FROM modos_falha WHERE id = ?",
                            conn,
                            params=(int(modo_falha_id),)
                        ).iloc[0]['nome']
                        caminho_imagem = salvar_arquivo_upload(imagem, "anomalias", f"anomalia_{modo_nome}_{tipo_nome}")
                        if caminho_imagem is None:
                            return

                    try:
                        cursor = conn.cursor()
                        # Verifica se já existe esta combinação
                        cursor.execute("""
                            SELECT 1 FROM anomalias 
                            WHERE modos_falha_id = ? AND tipo_anomalia_id = ?
                        """, (modo_falha_id, tipo_anomalia_id))
                        
                        if cursor.fetchone():
                            st.error("Esta combinação de modo de falha e tipo de anomalia já existe")
                        else:
                            aplicado = executar_alteracao_config_ui(
                                "anomalias",
                                "create",
                                {
                                    "modos_falha_id": int(modo_falha_id),
                                    "tipo_anomalia_id": int(tipo_anomalia_id),
                                    "gravidade": float(gravidade),
                                    "peso": float(peso),
                                    "image_path": caminho_imagem,
                                    "zonas_ids": [int(z) for z in zonas_selecionadas],
                                    "materiais_ids": [int(m) for m in materiais_selecionados],
                                },
                                msg_sucesso="Anomalia e relacionamentos cadastrados com sucesso!",
                            )
                            if aplicado:
                                st.session_state.ultima_atualizacao = time.time()
                                st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao cadastrar: {str(e)}")

        elif submodo == "Editar":
            st.subheader("Editar Anomalia")
            
            # Verifica se há anomalias para editar
            if df_anomalias.empty:
                st.warning("Nenhuma anomalia cadastrada para editar.")
                
                # Mostra opção para adicionar primeira anomalia
                if st.session_state.modo_falha_selecionado:
                    if st.button("➕ Cadastrar Primeira Anomalia"):
                        submodo = "Adicionar"
                        st.rerun()
            else:
                anomalia_id = st.selectbox(
                    "Selecione a anomalia para editar:",
                    options=df_anomalias['id'],
                    format_func=lambda x: (f"{df_anomalias[df_anomalias['id']==x]['tipo_anomalia'].values[0]}" 
                                        if st.session_state.modo_falha_selecionado 
                                        else f"{df_anomalias[df_anomalias['id']==x]['modo_falha'].values[0]} - {df_anomalias[df_anomalias['id']==x]['tipo_anomalia'].values[0]}")
                )
                
                st.session_state.editando_anomalia = anomalia_id

                anomalia = pd.read_sql(f"""
                    SELECT * FROM anomalias WHERE id = {anomalia_id}
                """, conn).iloc[0]
                
                zonas_relacionadas = pd.read_sql(
                    f"SELECT zona_id FROM anomalia_zona WHERE anomalia_id = {anomalia_id}",
                    conn
                )['zona_id'].tolist()
                
                materiais_relacionados = pd.read_sql(
                    f"SELECT tipo_mat_id FROM anomalia_tipo_material WHERE anomalia_id = {anomalia_id}",
                    conn
                )['tipo_mat_id'].tolist()

                with st.form("form_edit_anomalia"):
                    modo_atual = pd.read_sql(
                        f"SELECT nome FROM modos_falha WHERE id = {anomalia['modos_falha_id']}",
                        conn
                    ).iloc[0]['nome']
                    st.text_input("Modo de Falha", value=modo_atual, disabled=True)
                    
                    tipo_atual = pd.read_sql(
                        f"SELECT nome FROM tipo_anomalia WHERE id = {anomalia['tipo_anomalia_id']}",
                        conn
                    ).iloc[0]['nome']
                    st.text_input("Tipo de Anomalia", value=tipo_atual, disabled=True)
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        nova_gravidade = st.slider("Gravidade (0-10)*", 0.0, 10.0, float(anomalia['gravidade']), 0.1)
                    with col2:
                        novo_peso = st.slider("Peso (0-10)*", 0.0, 10.0, float(anomalia['peso']), 0.1)
                    
                    novas_zonas = st.multiselect(
                        "Zonas relacionadas:",
                        options=tipos_zona['id'],
                        default=zonas_relacionadas,
                        format_func=lambda x: tipos_zona[tipos_zona['id']==x]['nome'].values[0]
                    )
                    
                    novos_materiais = st.multiselect(
                        "Tipos de Material relacionados:",
                        options=tipos_material['id'],
                        default=materiais_relacionados,
                        format_func=lambda x: tipos_material[tipos_material['id']==x]['nome'].values[0]
                    )
                    
                    nova_imagem = st.file_uploader("Substituir Imagem", type=["jpg", "jpeg", "png"])

                    if st.form_submit_button("💾 Salvar Alterações"):
                        caminho_imagem = anomalia['image_path']
                        if nova_imagem is not None:
                            caminho_imagem = salvar_arquivo_upload(nova_imagem, "anomalias", f"anomalia_{modo_atual}_{tipo_atual}")
                            if caminho_imagem is None:
                                return

                        try:
                            aplicado = executar_alteracao_config_ui(
                                "anomalias",
                                "update",
                                {
                                    "modo_falha": modo_atual,
                                    "tipo_anomalia": tipo_atual,
                                    "gravidade": float(nova_gravidade),
                                    "peso": float(novo_peso),
                                    "image_path": caminho_imagem,
                                    "zonas_ids": [int(z) for z in novas_zonas],
                                    "materiais_ids": [int(m) for m in novos_materiais],
                                },
                                target_id=int(anomalia_id),
                                msg_sucesso="Anomalia e relacionamentos atualizados com sucesso!",
                            )
                            if aplicado:
                                st.session_state.ultima_atualizacao = time.time()
                                st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao atualizar: {str(e)}")

        elif submodo == "Excluir":
            st.subheader("Excluir Anomalia")

            # Verifica se há anomalias para excluir
            if df_anomalias.empty:
                st.warning("Nenhuma anomalia cadastrada para excluir.")
                
                # Mostra opção para adicionar primeira anomalia
                if st.session_state.modo_falha_selecionado:
                    if st.button("➕ Cadastrar Primeira Anomalia"):
                        submodo = "Adicionar"
                        st.rerun()
            else:
                anomalia_id = st.selectbox(
                    "Selecione a anomalia para excluir:",
                    options=df_anomalias['id'],
                    format_func=lambda x: (f"{df_anomalias[df_anomalias['id']==x]['tipo_anomalia'].values[0]}" 
                                        if st.session_state.modo_falha_selecionado 
                                        else f"{df_anomalias[df_anomalias['id']==x]['modo_falha'].values[0]} - {df_anomalias[df_anomalias['id']==x]['tipo_anomalia'].values[0]}")
                )

                anomalia = pd.read_sql(f"""
                    SELECT a.*, mf.nome as modo_falha, ta.nome as tipo_anomalia
                    FROM anomalias a
                    JOIN modos_falha mf ON a.modos_falha_id = mf.id
                    JOIN tipo_anomalia ta ON a.tipo_anomalia_id = ta.id
                    WHERE a.id = {anomalia_id}
                """, conn).iloc[0]

                st.warning("⚠️ Você está prestes a excluir permanentemente esta anomalia:")
                st.write(f"**Modo de Falha:** {anomalia['modo_falha']}")
                st.write(f"**Tipo de Anomalia:** {anomalia['tipo_anomalia']}")
                st.write(f"**Gravidade:** {anomalia['gravidade']}")
                st.write(f"**Peso:** {anomalia['peso']}")

                img_anom = resolver_caminho_arquivo(anomalia['image_path'])
                if img_anom:
                    st.image(str(img_anom), caption="Imagem da Anomalia", use_container_width=True)

                if st.button("🗑️ Confirmar Exclusão", type="primary"):
                    try:
                        aplicado = executar_alteracao_config_ui(
                            "anomalias",
                            "delete",
                            {"modo_falha": anomalia['modo_falha'], "tipo_anomalia": anomalia['tipo_anomalia']},
                            target_id=int(anomalia_id),
                            msg_sucesso="Anomalia e relacionamentos excluídos com sucesso!",
                        )
                        if aplicado:
                            if img_anom and img_anom.exists():
                                try:
                                    img_anom.unlink()
                                except OSError:
                                    pass
                            if anomalia['image_path']:
                                remover_midia_db(anomalia['image_path'])
                            st.session_state.ultima_atualizacao = time.time()
                            st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao excluir: {str(e)}")


def gerenciar_tipos_modo_falha():
    """Página de gerenciamento dos modos de falha"""
    st.title("⚙️ Tipos de modos de falha")
    exibir_aviso_workflow_config()

    # Conexão com o banco
    conn = conectar_db()

    # Modo de operação
    modo = st.radio("Modo:", ["Visualizar", "Adicionar", "Editar", "Excluir"], horizontal=True)

    # Carrega os tipos existentes
    df = pd.read_sql("SELECT id, nome, descricao, referencia_tecnica FROM tipo_modo_falha ORDER BY nome", conn)

    if modo == "Visualizar":
        st.subheader("Categorias de modos de falha cadastrados")
        st.dataframe(df.set_index('id'), use_container_width=True)

    elif modo == "Adicionar":
        st.subheader("Adicionar nova categoria de modo de falha")
        with st.form("form_add_modo_falha", clear_on_submit=True):
            nome = st.text_input("Nome do Modo de Falha*", max_chars=50)
            descricao = st.text_area("Descrição Técnica*", height=100)
            referencia = st.text_input("Referência Técnica (opcional)")

            if st.form_submit_button("💾 Salvar Novo Modo de Falha"):
                if not nome.strip() or not descricao.strip():
                    st.error("Nome e descrição são campos obrigatórios")
                else:
                    try:
                        aplicado = executar_alteracao_config_ui(
                            "tipo_modo_falha",
                            "create",
                            {
                                "nome": nome.strip(),
                                "descricao": descricao.strip(),
                                "referencia_tecnica": referencia.strip() if referencia else None,
                            },
                            msg_sucesso="Modo de falha adicionado com sucesso!",
                        )
                        if aplicado:
                            time.sleep(0.5)
                            st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("Já existe um modo de falha com este nome.")
                    except Exception as e:
                        st.error(f"Erro ao cadastrar: {str(e)}")

    elif modo == "Editar":
        st.subheader("Editar Modo de Falha Existente")

        if df.empty:
            st.warning("Nenhum modo de falha cadastrado para editar.")
        else:
            modo_id = st.selectbox(
                "Selecione o modo de falha para editar:",
                options=df['id'],
                format_func=lambda x: f"{df[df['id']==x]['nome'].values[0]} "
            )

            modo_falha = df[df['id'] == modo_id].iloc[0]

            with st.form("form_edit_modo_falha"):
                novo_nome = st.text_input("Nome do Modo de Falha*", value=modo_falha['nome'], max_chars=50)
                nova_descricao = st.text_area("Descrição Técnica*", value=modo_falha['descricao'], height=100)
                nova_referencia = st.text_input("Referência Técnica (opcional)", value=modo_falha['referencia_tecnica'] or "")

                if st.form_submit_button("💾 Salvar Alterações"):
                    if not novo_nome.strip() or not nova_descricao.strip():
                        st.error("Nome e descrição são campos obrigatórios")
                    else:
                        try:
                            # Verifica se já existe outro com o mesmo nome (exceto o atual)
                            existente = pd.read_sql(
                                "SELECT 1 FROM tipo_modo_falha WHERE LOWER(nome) = LOWER(?) AND id != ?", 
                                conn, 
                                params=(novo_nome.strip(), modo_id)
                            ).empty
                            
                            if not existente:
                                st.error("Já existe outro modo de falha com este nome")
                            else:
                                aplicado = executar_alteracao_config_ui(
                                    "tipo_modo_falha",
                                    "update",
                                    {
                                        "nome": novo_nome.strip(),
                                        "descricao": nova_descricao.strip(),
                                        "referencia_tecnica": nova_referencia.strip() or None,
                                    },
                                    target_id=int(modo_id),
                                    msg_sucesso="Modo de falha atualizado com sucesso!",
                                )
                                if aplicado:
                                    time.sleep(0.5)
                                    st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao atualizar: {str(e)}")

    elif modo == "Excluir":
        st.subheader("Excluir Modo de Falha")

        if df.empty:
            st.warning("Nenhum modo de falha cadastrado para excluir.")
        else:
            modo_id = st.selectbox(
                "Selecione o modo de falha para excluir:",
                options=df['id'],
                format_func=lambda x: f"{df[df['id']==x]['nome'].values[0]} "
            )

            modo_falha = df[df['id'] == modo_id].iloc[0]

            st.warning("⚠️ Você está prestes a excluir permanentemente o modo de falha:")
            st.write(f"**Nome:** {modo_falha['nome']}")
            st.write(f"**Descrição:** {modo_falha['descricao']}")
            st.write(f"**Referência:** {modo_falha['referencia_tecnica'] or 'Sem referência'}")

            if st.button("🗑️ Confirmar Exclusão", type="primary"):
                try:
                    aplicado = executar_alteracao_config_ui(
                        "tipo_modo_falha",
                        "delete",
                        {"nome": modo_falha['nome']},
                        target_id=int(modo_id),
                        msg_sucesso="Modo de falha excluído com sucesso!",
                    )
                    if aplicado:
                        time.sleep(0.5)
                        st.rerun()
                except sqlite3.Error as e:
                    st.error(f"Erro ao excluir: {str(e)}")

    conn.close()
    
    # Rodapé
    if st.button("← Voltar"):
        st.session_state['pagina'] = "principal"
        st.rerun()



# def cadastrar_zona_barragem(barragem_id):
#     """Formulário atualizado para nova estrutura"""
#     with st.form("form_nova_zona", clear_on_submit=True):
#         st.subheader("Cadastrar Nova Zona")
        
#         # Seleção de material primeiro (nova ordem)
#         materiais = obter_todos_materiais()
#         material_opcoes = {m[0]: m[2] for m in materiais} if materiais else {}
        
#         material_id = st.selectbox(
#             "Material Principal*",
#             options=list(material_opcoes.keys()),
#             format_func=lambda x: material_opcoes.get(x, "Selecione...")
#         )
        
#         nome = st.text_input("Nome da Zona*", max_chars=50)
#         descricao = st.text_area("Descrição Técnica")
        
#         submitted = st.form_submit_button("Salvar Zona")
        
#         if submitted:
#             if not nome or not material_id:
#                 st.error("Preencha os campos obrigatórios (*)")
#             else:
#                 sucesso = cadastrar_zona_db(
#                     usuario_id=st.session_state['usuario_id'],
#                     barragem_id=barragem_id,
#                     material_id=material_id,
#                     nome=nome.strip(),
#                     descricao=descricao.strip() if descricao else None
#                 )
                
#                 if sucesso:
#                     st.success("Zona cadastrada com sucesso!")
#                     time.sleep(1)
#                     st.rerun()

# def atualizar_zona_db(zona_id, material_id, nome, descricao=None):
#     """
#     Atualiza uma zona de barragem no banco de dados
#     :param zona_id: ID da zona a ser atualizada
#     :param material_id: ID do material associado
#     :param nome: Nome da zona
#     :param descricao: Descrição técnica (opcional)
#     :return: True se atualizado com sucesso, False caso contrário
#     """
#     conn = None
#     try:
#         conn = conectar_db()
#         cursor = conn.cursor()
        
#         # Verifica se a zona existe
#         cursor.execute("SELECT id FROM zonas_barragem WHERE id = ?", (zona_id,))
#         if not cursor.fetchone():
#             st.error("Zona não encontrada")
#             return False
        
#         # Atualiza os dados
#         cursor.execute("""
#             UPDATE zonas_barragem 
#             SET material_id = ?, nome = ?, descricao = ?
#             WHERE id = ?
#         """, (material_id, nome.strip(), descricao.strip() if descricao else None, zona_id))
        
#         conn.commit()
        
#         # Verifica se a atualização foi bem-sucedida
#         if cursor.rowcount == 1:
#             st.success("Zona atualizada com sucesso!")
#             return True
#         else:
#             st.error("Nenhuma alteração realizada")
#             return False
            
#     except sqlite3.IntegrityError as e:
#         if "FOREIGN KEY constraint failed" in str(e):
#             st.error("Material selecionado não existe")
#         elif "UNIQUE constraint" in str(e):
#             st.error("Já existe uma zona com este nome")
#         else:
#             st.error(f"Erro de integridade no banco de dados: {str(e)}")
#         return False
        
#     except sqlite3.Error as e:
#         st.error(f"Erro no banco de dados: {str(e)}")
#         return False
        
#     except Exception as e:
#         st.error(f"Erro inesperado: {str(e)}")
#         return False
        
#     finally:
#         if conn:
#             try:
#                 conn.close()
#             except:
#                 pass  # Garante que não falhe ao fechar conexão

def excluir_zona_barragem(zona_id):
    """
    Exclui uma zona de barragem do sistema de forma segura
    :param zona_id: ID da zona a ser excluída
    :return: 
        - True se a exclusão foi bem-sucedida
        - False se houve falha ou a zona não pode ser excluída
    """
    # Verificação inicial do ID
    try:
        zona_id = int(zona_id)
        if zona_id <= 0:
            st.error("ID da zona inválido")
            return False
    except (ValueError, TypeError):
        st.error("ID da zona deve ser um número inteiro positivo")
        return False

    conn = None
    try:
        conn = conectar_db()
        cursor = conn.cursor()

        # 1. Verifica se a zona existe
        cursor.execute("SELECT barragem_id FROM zonas_barragem WHERE id = ?", (zona_id,))
        resultado = cursor.fetchone()
        
        if not resultado:
            st.error("Zona não encontrada")
            return False

        barragem_id = resultado[0]

        # 2. Verifica se existem modos de falha associados (se aplicável)
        cursor.execute("SELECT COUNT(*) FROM modos_falha_zona WHERE zona_id = ?", (zona_id,))
        if cursor.fetchone()[0] > 0:
            st.error("Não é possível excluir: existem modos de falha associados a esta zona")
            return False

        # 3. Executa a exclusão
        cursor.execute("DELETE FROM zonas_barragem WHERE id = ?", (zona_id,))
        conn.commit()

        # Verifica se realmente excluiu
        if cursor.rowcount == 1:
            st.success(f"Zona {zona_id} da barragem {barragem_id} excluída com sucesso!")
            return True
        else:
            st.error("Nenhuma zona foi excluída")
            return False

    except sqlite3.Error as e:
        st.error(f"Erro no banco de dados: {str(e)}")
        return False

    except Exception as e:
        st.error(f"Erro inesperado: {str(e)}")
        return False

    finally:
        if conn:
            try:
                conn.close()
            except:
                pass  # Garante que não falhe ao fechar conexão

def atualizar_zona_db(zona_id, material_id, nome, descricao=None):
    """
    Atualiza uma zona de barragem no banco de dados
    :param zona_id: ID da zona a ser atualizada
    :param material_id: ID do material associado
    :param nome: Nome da zona
    :param descricao: Descrição técnica (opcional)
    :return: True se atualizado com sucesso, False caso contrário
    """
    conn = None
    try:
        conn = conectar_db()
        cursor = conn.cursor()
        
        # Verifica se a zona existe
        cursor.execute("SELECT id FROM zonas_barragem WHERE id = ?", (zona_id,))
        if not cursor.fetchone():
            st.error("Zona não encontrada")
            return False
        
        # Atualiza os dados
        cursor.execute("""
            UPDATE zonas_barragem 
            SET material_id = ?, nome = ?, descricao = ?
            WHERE id = ?
        """, (material_id, nome.strip(), descricao.strip() if descricao else None, zona_id))
        
        conn.commit()
        
        # Verifica se a atualização foi bem-sucedida
        if cursor.rowcount == 1:
            st.success("Zona atualizada com sucesso!")
            return True
        else:
            st.error("Nenhuma alteração realizada")
            return False
            
    except sqlite3.IntegrityError as e:
        if "FOREIGN KEY constraint failed" in str(e):
            st.error("Material selecionado não existe")
        elif "UNIQUE constraint" in str(e):
            st.error("Já existe uma zona com este nome")
        else:
            st.error(f"Erro de integridade no banco de dados: {str(e)}")
        return False
        
    except sqlite3.Error as e:
        st.error(f"Erro no banco de dados: {str(e)}")
        return False
        
    except Exception as e:
        st.error(f"Erro inesperado: {str(e)}")
        return False
        
    finally:
        if conn:
            try:
                conn.close()
            except:
                pass  # Garante que não falhe ao fechar conexão



def gerenciar_tipos_materiais():
    """Página de gerenciamento dos tipos de materiais"""
    st.title("⚙️ Gerenciamento de Tipos de Materiais")
    exibir_aviso_workflow_config()

    # Conexão com o banco
    conn = conectar_db()

    # Modo de operação
    modo = st.radio("Modo:", ["Visualizar", "Adicionar", "Editar", "Excluir"], horizontal=True)

    # Carrega os materiais existentes
    df = pd.read_sql("SELECT id, nome, descricao FROM tipos_materiais ORDER BY nome", conn)

    if modo == "Visualizar":
        st.subheader("Tipos de materiais cadastrados")
        if not df.empty:
            st.dataframe(df.set_index('id'), use_container_width=True)
        else:
            st.info("ℹ️ Nenhum material cadastrado ainda.")

    elif modo == "Adicionar":
        st.subheader("Adicionar Novo Tipo de Material")
        with st.form("form_add_tipo_material", clear_on_submit=True):
            nome = st.text_input("Nome do Material*", max_chars=50)
            descricao = st.text_area("Descrição Técnica", height=100)

            if st.form_submit_button("💾 Salvar Novo Material"):
                if not nome.strip():
                    st.error("⚠️ O nome do material é obrigatório.")
                else:
                    try:
                        aplicado = executar_alteracao_config_ui(
                            "tipos_materiais",
                            "create",
                            {"nome": nome.strip(), "descricao": descricao.strip() if descricao else None},
                            msg_sucesso="✅ Material cadastrado com sucesso!",
                        )
                        if aplicado:
                            time.sleep(0.5)
                            st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("⛔ Já existe um material com esse nome.")
                    except Exception as e:
                        st.error(f"Erro ao cadastrar material: {str(e)}")

    elif modo == "Editar":
        st.subheader("Editar Tipo de Material Existente")

        if df.empty:
            st.warning("Nenhum tipo de material cadastrado para editar.")
        else:
            material_id = st.selectbox(
                "Selecione o material para editar:",
                options=df['id'],
                format_func=lambda x: f"{df[df['id']==x]['nome'].values[0]} "
            )

            material = df[df['id'] == material_id].iloc[0]

            with st.form("form_edit_tipo_material"):
                novo_nome = st.text_input("Nome do Material*", value=material['nome'], max_chars=50)
                nova_descricao = st.text_area("Descrição Técnica", value=material['descricao'] or "", height=100)

                if st.form_submit_button("💾 Salvar Alterações"):
                    if not novo_nome.strip():
                        st.error("⚠️ O nome do material é obrigatório.")
                    else:
                        try:
                            # Verifica se o novo nome já existe (excluindo o próprio material)
                            existente = pd.read_sql(
                                "SELECT 1 FROM tipos_materiais WHERE LOWER(nome) = LOWER(?) AND id != ?", 
                                conn, 
                                params=(novo_nome.strip(), material_id)
                            ).empty
                            
                            if not existente:
                                st.error(f"⛔ Já existe outro material com o nome '{novo_nome.strip()}'")
                            else:
                                aplicado = executar_alteracao_config_ui(
                                    "tipos_materiais",
                                    "update",
                                    {"nome": novo_nome.strip(), "descricao": nova_descricao.strip() or None},
                                    target_id=int(material_id),
                                    msg_sucesso="✅ Material atualizado com sucesso!",
                                )
                                if aplicado:
                                    time.sleep(0.5)
                                    st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao atualizar material: {str(e)}")

    elif modo == "Excluir":
        st.subheader("Excluir Tipo de Material")

        if df.empty:
            st.warning("Nenhum tipo de material cadastrado para excluir.")
        else:
            material_id = st.selectbox(
                "Selecione o material para excluir:",
                options=df['id'],
                format_func=lambda x: f"{df[df['id']==x]['nome'].values[0]} )"
            )

            material = df[df['id'] == material_id].iloc[0]

            st.warning("⚠️ Você está prestes a excluir permanentemente o material:")
            st.write(f"**Nome:** {material['nome']}")
            st.write(f"**Descrição:** {material['descricao'] or 'Sem descrição'}")

            if st.button("🗑️ Confirmar Exclusão", type="primary"):
                try:
                    # Lista de tabelas para verificar
                    tabelas_para_verificar = [
                        ("materiais_utilizados", "tipo_material_id"),
                        ("estoque", "material_id"),
                        # Adicione mais aqui se precisar
                    ]

                    em_uso = False

                    for tabela, coluna in tabelas_para_verificar:
                        try:
                            query = f"SELECT 1 FROM {tabela} WHERE {coluna} = ? LIMIT 1"
                            resultado = pd.read_sql(query, conn, params=(material_id,))
                            if not resultado.empty:
                                em_uso = True
                                st.error(
                                    f"⛔ Este material está vinculado à tabela **{tabela}** e não pode ser excluído."
                                )
                                break  # Para na primeira ocorrência de vínculo
                        except Exception as e:
                            # Mostra o aviso se a tabela não existir
                            st.info(f"Tabela `{tabela}` não existe ou não pode ser consultada: {e}")

                    if not em_uso:
                        aplicado = executar_alteracao_config_ui(
                            "tipos_materiais",
                            "delete",
                            {"nome": material['nome']},
                            target_id=int(material_id),
                            msg_sucesso="✅ Material excluído com sucesso!",
                        )
                        if aplicado:
                            time.sleep(0.5)
                            st.rerun()

                except Exception as e:
                    st.error(f"Erro ao excluir material: {str(e)}")



    conn.close()
    
    # Rodapé
    if st.button("← Voltar"):
        st.session_state['pagina'] = "principal"
        st.rerun()

# def cadastrar_tipo_material_db(usuario_id, nome, descricao=None):
#     """Insere novo tipo de material no banco de dados"""
#     conn = conectar_db()
#     cursor = conn.cursor()
#     try:
#         cursor.execute("""
#             INSERT INTO tipos_materiais (usuario_id, nome, descricao)
#             VALUES (?, ?, ?)
#         """, (usuario_id, nome, descricao))
#         conn.commit()
#         return (True, "✅ Material cadastrado com sucesso!")
#     except sqlite3.IntegrityError:
#         return (False, "⛔ Já existe um material com esse nome.")
#     except Exception as e:
#         return (False, f"Erro inesperado: {str(e)}")
#     finally:
#         conn.close()

def gerenciar_tipos_zonas():
    """Página de gerenciamento dos tipos de zonas de barragens"""
    st.title("⚙️ Gerenciamento de tipos de zonas de barragens")
    exibir_aviso_workflow_config()
    
    # Conexão com o banco
    conn = conectar_db()
    
    # Modo de visualização/edição
    modo = st.radio("Modo:", ["Visualizar", "Adicionar", "Editar", "Excluir"], horizontal=True)
    
    # Carrega os dados existentes
    df = pd.read_sql("SELECT id, nome, descricao FROM tipos_zonas_bar ORDER BY nome", conn)
    
    if modo == "Visualizar":
        st.subheader("Tipos de Zonas Cadastradas")
        st.dataframe(df.set_index('id'), use_container_width=True)
        
    elif modo == "Adicionar":
        st.subheader("Adicionar Novo Tipo de Zona")
        with st.form("form_add_zona", clear_on_submit=True):
            nome = st.text_input("Nome da Zona*", max_chars=100)
            descricao = st.text_area("Descrição Técnica", height=100)
            
            if st.form_submit_button("💾 Salvar Novo Tipo"):
                if nome:
                    try:
                        aplicado = executar_alteracao_config_ui(
                            "tipos_zonas_bar",
                            "create",
                            {"nome": nome.strip(), "descricao": descricao.strip() if descricao else None},
                            msg_sucesso="Tipo de zona adicionado com sucesso!",
                        )
                        if aplicado:
                            st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("Já existe um tipo de zona com este nome")
                else:
                    st.error("O nome da zona é obrigatório")
    
    elif modo == "Editar":
        st.subheader("Editar Tipo de Zona Existente")
        
        if df.empty:
            st.warning("Nenhum tipo de zona cadastrado para editar")
        else:
            zona_id = st.selectbox(
                "Selecione o tipo de zona para editar:",
                options=df['id'],
                format_func=lambda x: f"{df[df['id']==x]['nome'].values[0]} "
            )
            
            zona = df[df['id']==zona_id].iloc[0]
            
            with st.form("form_edit_zona"):
                novo_nome = st.text_input("Nome da Zona*", value=zona['nome'], max_chars=100)
                nova_descricao = st.text_area(
                    "Descrição Técnica", 
                    value=zona['descricao'] if zona['descricao'] else "",
                    height=100
                )
                
                if st.form_submit_button("💾 Salvar Alterações"):
                    if novo_nome:
                        try:
                            aplicado = executar_alteracao_config_ui(
                                "tipos_zonas_bar",
                                "update",
                                {"nome": novo_nome.strip(), "descricao": nova_descricao.strip() if nova_descricao else None},
                                target_id=int(zona_id),
                                msg_sucesso="Tipo de zona atualizado com sucesso!",
                            )
                            if aplicado:
                                st.rerun()
                        except sqlite3.IntegrityError:
                            st.error("Já existe outro tipo de zona com este nome")
                    else:
                        st.error("O nome da zona é obrigatório")
    
    elif modo == "Excluir":
        st.subheader("Excluir Tipo de Zona")
        
        if df.empty:
            st.warning("Nenhum tipo de zona cadastrado para excluir")
        else:
            zona_id = st.selectbox(
                "Selecione o tipo de zona para excluir:",
                options=df['id'],
                format_func=lambda x: f"{df[df['id']==x]['nome'].values[0]} "
            )
            
            zona = df[df['id']==zona_id].iloc[0]
            
            st.warning(f"Você está prestes a excluir permanentemente o tipo de zona:")
            st.write(f"**Nome:** {zona['nome']}")
            st.write(f"**Descrição:** {zona['descricao'] or 'Sem descrição'}")
            
            if st.button("🗑️ Confirmar Exclusão", type="primary"):
                try:
                    aplicado = executar_alteracao_config_ui(
                        "tipos_zonas_bar",
                        "delete",
                        {"nome": zona['nome']},
                        target_id=int(zona_id),
                        msg_sucesso="Tipo de zona excluído com sucesso!",
                    )
                    if aplicado:
                        st.rerun()
                except sqlite3.Error as e:
                    st.error(f"Erro ao excluir: {str(e)}")
    
    conn.close()

def exibir_formulario_cadastro_barragem():
    """Exibe o formulário padrão de cadastro de barragem"""
    st.title("📝 Cadastro de barragens")   

    st.subheader("Informações Básicas")
    nome = st.text_input("Nome da Barragem*", placeholder="Ex: Barragem do Rio Preto")

    # Lista de tipos de barragem: (id, nome)
    tipos = obter_tipos_barragem()

    # Criar dicionário nome -> id
    opcoes = {t[2]: t[0] for t in tipos}

    # Criar dicionário inverso id -> nome (para uso no valor inicial)
    id_para_nome = {t[0]: t[2] for t in tipos}

    # Obter nome correspondente ao ID atual (ou "" se não encontrado)
    tipo_nome_atual = id_para_nome.get(1, "")

    # Selectbox que mostra o nome e armazena o ID
    tipo_nome = st.selectbox(
        "Tipo de Barragem*",
        options=list(opcoes.keys()),
        index=list(opcoes.keys()).index(tipo_nome_atual) if tipo_nome_atual in opcoes else 0,
        help="Selecione o tipo construtivo da barragem"
    )

    # Recuperar o tipo_id correspondente ao nome selecionado
    tipo_id = opcoes[tipo_nome]

    localizacao = st.text_input("Localização*", placeholder="Ex: Município/Estado")

    st.subheader("Dimensões")
    col1, col2 = st.columns(2)
    with col1:
        altura = st.number_input("Altura (m)*", min_value=0.0, step=0.1, format="%.1f", key="altura_input")
    with col2:
        comprimento = st.number_input("Comprimento (m)*", min_value=0.0, step=0.1, format="%.1f", key="comprimento_input")

    # Cálculo dinâmico da relação Corda/Altura
    if altura > 0:
        rel_cordaaltura = round(comprimento / altura, 1)
        st.success(f"📐 Relação Corda/Altura: **{rel_cordaaltura:.1f}**")
    else:
        rel_cordaaltura = 0.0
        st.warning("⚠️ Informe um valor de altura maior que zero para calcular a relação Corda/Altura.")

    # Formulário de envio
    sucesso_cadastro = False
    with st.form("form_cadastro_barragem"):
        submitted = st.form_submit_button("Cadastrar Barragem")
        if submitted:
            if not nome or not tipo_id or not localizacao or altura == 0 or comprimento == 0:
                st.error("Preencha todos os campos obrigatórios (*) e certifique-se de que altura e comprimento sejam maiores que zero.")
            else:
                try:
                    cadastrar_barragem(
                        st.session_state['usuario_id'],
                        nome,
                        tipo_id,
                        localizacao,
                        altura,
                        comprimento,
                        rel_cordaaltura
                    )
                    st.success("✅ Barragem cadastrada com sucesso!")
                    sucesso_cadastro = True
                except Exception as e:
                    st.error(f"Erro ao cadastrar barragem: {str(e)}")

    # Botão externo ao formulário (ativado apenas após sucesso)
    if sucesso_cadastro:
        if st.button("📌 Definir como Barragem em Análise"):
            barragens = obter_barragens_usuario(st.session_state['usuario_id'])
            if barragens:
                ultima_barragem = barragens[-1][0]
                definir_barragem_analise(st.session_state['usuario_id'], ultima_barragem)
                st.success("Barragem definida para análise!")
                st.session_state['pagina'] = "principal"
                st.rerun()



def cadastrar_tipo_barragem_db(usuario_id, nome, descricao, referencia_tecnica=None, image_path=None):
    """
    Cadastra novo tipo de barragem com tratamento completo de erros e validações
    Retorna:
        - ID do novo registro se bem-sucedido
        - None em caso de falha
    """
    conn = None
    try:
        # Validações iniciais
        if not nome or not isinstance(nome, str) or len(nome.strip()) == 0:
            st.error("Nome do tipo de barragem é obrigatório")
            return None
            
        if len(nome.strip()) > 50:
            st.error("Nome deve ter no máximo 50 caracteres")
            return None
            
        if not descricao or len(descricao.strip()) == 0:
            st.error("Descrição técnica é obrigatória")
            return None

        # Conecta ao banco de dados
        conn = conectar_db()
        cursor = conn.cursor()
        
        # Verifica se já existe um tipo com o mesmo nome
        cursor.execute("SELECT id FROM tipos_barragem WHERE nome = ?", (nome.strip(),))
        if cursor.fetchone():
            st.error("Já existe um tipo de barragem com este nome")
            return None
        
        # Insere o novo registro
        cursor.execute("""
            INSERT INTO tipos_barragem 
            (usuario_id, nome, descricao, referencia_tecnica, image_path)
            VALUES (?, ?, ?, ?, ?)
        """, (
            usuario_id,
            nome.strip(),
            descricao.strip(),
            referencia_tecnica.strip() if referencia_tecnica else None,
            image_path if resolver_caminho_arquivo(image_path) else None
        ))
        
        conn.commit()
        
        # Retorna o ID do novo registro
        novo_id = cursor.lastrowid
        st.success(f"Tipo de barragem cadastrado com sucesso!")
        return novo_id
        
    except sqlite3.IntegrityError as e:
        st.error(f"Erro de integridade no banco de dados: {str(e)}")
        return None
        
    except sqlite3.Error as e:
        st.error(f"Erro no banco de dados: {str(e)}")
        return None
        
    except Exception as e:
        st.error(f"Erro inesperado: {str(e)}")
        return None
        
    finally:
        if conn:
            try:
                conn.close()
            except:
                pass  # Garante que não falhe ao fechar conexão



def gerenciar_tipos_barragem():
    """Página de gerenciamento dos tipos de barragem"""
    st.title("⚙️ Gerenciamento de tipos de barragem")
    exibir_aviso_workflow_config()

    # Conexão com o banco
    conn = conectar_db()

    # Modo de operação
    modo = st.radio("Modo:", ["Visualizar", "Adicionar", "Editar", "Excluir"], horizontal=True)

    # Carrega os tipos existentes
    df = pd.read_sql("SELECT id, nome, descricao, referencia_tecnica, image_path FROM tipos_barragem ORDER BY nome", conn)

    if modo == "Visualizar":
        st.subheader("Tipos de barragem cadastrados")
        st.dataframe(df.set_index('id'), use_container_width=True)

    elif modo == "Adicionar":
        st.subheader("Adicionar Novo Tipo de Barragem")
        with st.form("form_add_tipo_barragem", clear_on_submit=True):
            nome = st.text_input("Nome do Tipo*", max_chars=50)
            descricao = st.text_area("Descrição Técnica*", height=100)
            referencia = st.text_input("Referência Normativa (opcional)")
            imagem = st.file_uploader("Imagem Representativa (opcional)", type=["jpg", "jpeg", "png"])

            if st.form_submit_button("💾 Salvar Novo Tipo"):
                # Processa a imagem se houver
                caminho_imagem = None
                if imagem is not None:
                    caminho_imagem = salvar_arquivo_upload(imagem, "tipos_barragem", f"tipo_{nome}")
                    if caminho_imagem is None:
                        return

                if not nome.strip() or not descricao.strip():
                    st.error("Nome e descrição técnica são obrigatórios.")
                else:
                    try:
                        aplicado = executar_alteracao_config_ui(
                            "tipos_barragem",
                            "create",
                            {
                                "nome": nome.strip(),
                                "descricao": descricao.strip(),
                                "referencia_tecnica": referencia.strip() if referencia else None,
                                "image_path": caminho_imagem,
                            },
                            msg_sucesso="Tipo de barragem adicionado com sucesso!",
                        )
                        if aplicado:
                            st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("Já existe um tipo de barragem com este nome.")
                    except Exception as e:
                        st.error(f"Erro ao cadastrar tipo de barragem: {str(e)}")

    elif modo == "Editar":
        st.subheader("Editar Tipo de Barragem Existente")

        if df.empty:
            st.warning("Nenhum tipo de barragem cadastrado para editar.")
        else:
            tipo_id = st.selectbox(
                "Selecione o tipo de barragem para editar:",
                options=df['id'],
                format_func=lambda x: f"{df[df['id']==x]['nome'].values[0]} "
            )

            tipo = df[df['id'] == tipo_id].iloc[0]

            with st.form("form_edit_tipo_barragem"):
                novo_nome = st.text_input("Nome do Tipo*", value=tipo['nome'], max_chars=50)
                nova_descricao = st.text_area("Descrição Técnica*", value=tipo['descricao'], height=100)
                nova_referencia = st.text_input("Referência Normativa (opcional)", value=tipo['referencia_tecnica'] or "")
                nova_imagem = st.file_uploader("Substituir Imagem Representativa (opcional)", type=["jpg", "jpeg", "png"])

                if st.form_submit_button("💾 Salvar Alterações"):
                    caminho_imagem = tipo['image_path']
                    if nova_imagem is not None:
                        caminho_imagem = salvar_arquivo_upload(nova_imagem, "tipos_barragem", f"tipo_{novo_nome}")
                        if caminho_imagem is None:
                            return

                    try:
                        aplicado = executar_alteracao_config_ui(
                            "tipos_barragem",
                            "update",
                            {
                                "nome": novo_nome.strip(),
                                "descricao": nova_descricao.strip(),
                                "referencia_tecnica": nova_referencia.strip() or None,
                                "image_path": caminho_imagem,
                            },
                            target_id=int(tipo_id),
                            msg_sucesso="Tipo de barragem atualizado com sucesso!",
                        )
                        if aplicado:
                            st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("Já existe outro tipo de barragem com este nome.")

    elif modo == "Excluir":
        st.subheader("Excluir Tipo de Barragem")

        if df.empty:
            st.warning("Nenhum tipo de barragem cadastrado para excluir.")
        else:
            tipo_id = st.selectbox(
                "Selecione o tipo de barragem para excluir:",
                options=df['id'],
                format_func=lambda x: f"{df[df['id']==x]['nome'].values[0]} "
            )

            tipo = df[df['id'] == tipo_id].iloc[0]

            st.warning("⚠️ Você está prestes a excluir permanentemente o tipo de barragem:")
            st.write(f"**Nome:** {tipo['nome']}")
            st.write(f"**Descrição:** {tipo['descricao']}")
            st.write(f"**Referência:** {tipo['referencia_tecnica'] or 'Sem referência'}")

            img_tipo = resolver_caminho_arquivo(tipo['image_path'])
            if img_tipo:
                st.image(str(img_tipo), caption="Imagem Representativa", use_container_width=True)

            if st.button("🗑️ Confirmar Exclusão", type="primary"):
                try:
                    aplicado = executar_alteracao_config_ui(
                        "tipos_barragem",
                        "delete",
                        {"nome": tipo['nome']},
                        target_id=int(tipo_id),
                        msg_sucesso="Tipo de barragem excluído com sucesso!",
                    )
                    if aplicado:
                        st.rerun()
                except sqlite3.Error as e:
                    st.error(f"Erro ao excluir: {str(e)}")

    conn.close()



def editar_barragem(barragem):
    """Formulário para edição de barragem existente"""
    with st.form("editar_barragem_form"):
        nome = st.text_input("Nome", value=barragem[2])


        # Lista de tipos de barragem: (id, nome)
        tipos = obter_tipos_barragem()

        # Criar dicionário nome -> id
        opcoes = {t[2]: t[0] for t in tipos}

        # Criar dicionário inverso id -> nome (para uso no valor inicial)
        id_para_nome = {t[0]: t[2] for t in tipos}

        # tipo_id previamente armazenado
    
        tipo_id_atual = barragem[3]

        # Obter nome correspondente ao ID atual (ou "" se não encontrado)
        tipo_nome_atual = id_para_nome.get(tipo_id_atual, "")

        # Selectbox que mostra o nome e armazena o ID
        tipo_nome = st.selectbox(
            "Tipo de Barragem*",
            options=list(opcoes.keys()),
            index=list(opcoes.keys()).index(tipo_nome_atual) if tipo_nome_atual in opcoes else 0,
            help="Selecione o tipo construtivo da barragem"
        )

        # Recuperar o tipo_id correspondente ao nome selecionado
        tipo_id = opcoes[tipo_nome]

        localizacao = st.text_input("Localização", value=barragem[4])
        altura = st.number_input("Altura (m)", value=barragem[5], min_value=0.0)
        comprimento = st.number_input("Comprimento (m)", value=barragem[6], min_value=0.0)
        rel_cordaaltura = st.number_input("Relação Corda/Altura", value=barragem[7], min_value=0.0)
        
        col1, col2, col3 = st.columns(3)
        with col2:
            submitted1 = st.form_submit_button("🗑️ Excluir")
            if submitted1:
                try:
                    excluir_barragem_escopo(obter_perfil_atual(), st.session_state['usuario_id'], barragem[0])
                    st.success("Barragem excluída com sucesso!")
                    st.rerun()
                except PermissionError:
                    st.error(t("dam_unauthorized"))

        with col3:
            submitted = st.form_submit_button("💾 Guardar Alterações")
            if submitted:
                try:
                    atualizar_barragem_escopo(
                        obter_perfil_atual(),
                        st.session_state['usuario_id'],
                        barragem[0],
                        nome,
                        tipo_id,
                        localizacao,
                        altura,
                        comprimento,
                        rel_cordaaltura,
                    )
                    st.success("Barragem atualizada com sucesso!")
                    st.rerun()
                except PermissionError:
                    st.error(t("dam_unauthorized"))
       
def mostrar_lista_barragens(barragens):
    """Mostra lista de barragens com exclusão segura"""
    st.subheader("📋 Lista de Barragens Cadastradas")
    
    if not barragens:
        st.warning("Nenhuma barragem cadastrada")
        return

    for barragem in barragens:
        barragem_id = barragem[0]
        nome_barragem = barragem[1]

        with st.expander(f"{nome_barragem}"):
            st.write(f"**Tipo:** {barragem[2]}")
            st.write(f"**Localização:** {barragem[3]}")
            st.write(f"**Altura:** {barragem[4]} m")
            st.write(f"**Comprimento:** {barragem[5]} m")

            col1, col2 = st.columns(2)
            with col1:
                if st.button("Selecionar para Análise", key=f"select_{barragem_id}"):
                    try:
                        definir_barragem_analise_escopo(obter_perfil_atual(), st.session_state['usuario_id'], barragem_id)
                        st.success(f"✅ Barragem **{nome_barragem}** selecionada para análise!")
                        st.rerun()
                    except PermissionError:
                        st.error(t("dam_unauthorized"))

            with col2:
                if st.button("🗑️ Excluir", key=f"delete_{barragem_id}"):
                    st.session_state[f'confirm_{barragem_id}'] = True
                    st.rerun()

    """Página para cadastro e gestão de zonas da barragem"""
    st.title("🏗️ Gerenciamento de Zonas da Barragem")

    from db import (
        obter_barragem_analise, obter_tipos_materiais_usuario,
        cadastrar_zona, obter_zonas_barragem, excluir_zona
    )

    # Obter barragem em análise
    barragem = obter_barragem_analise(st.session_state['usuario_id'])
    if not barragem:
        st.error("Selecione uma barragem para análise primeiro.")
        if st.button("⬅️ Voltar"):
            st.session_state['pagina'] = "principal"
            st.rerun()
        return

    barragem_id = barragem[0]
    st.info(f"Barragem em análise: {barragem[1]}")

    # Carregar materiais do usuário
    materiais = obter_tipos_materiais_usuario(st.session_state['usuario_id'])
    if not materiais:
        st.warning("Cadastre pelo menos um tipo de material antes de continuar.")
        if st.button("🧱 Ir para Cadastro de Materiais"):
            st.session_state['pagina'] = "gerenciar_materiais"
            st.rerun()
        return

    opcoes_materiais = {m[0]: m[1] for m in materiais}

    # Formulário de cadastro de zona
    st.subheader("➕ Cadastrar Nova Zona")
    with st.form("form_cadastro_zona"):
        nome = st.text_input("Nome da Zona*")
        material_id = st.selectbox(
            "Tipo de Material",
            options=list(opcoes_materiais.keys()),
            format_func=lambda x: opcoes_materiais[x]
        )
        submitted = st.form_submit_button("Cadastrar Zona")

        if submitted:
            if not nome.strip():
                st.error("Digite um nome para a zona.")
            else:
                cadastrar_zona(
                    st.session_state['usuario_id'],
                    barragem_id,
                    nome,
                    material_id
                )
                st.success("Zona cadastrada com sucesso!")
                st.rerun()

    # Lista de zonas já cadastradas
    st.subheader("📋 Zonas Cadastradas")
    zonas = obter_zonas_barragem(barragem_id)
    if zonas:
        for zona in zonas:
            col1, col2 = st.columns([4, 1])
            with col1:
                material_nome = opcoes_materiais.get(zona[3], "Desconhecido")
                st.markdown(f"**{zona[2]}** - Material: {material_nome}")
            with col2:
                if st.button("🗑️ Excluir", key=f"excluir_zona_{zona[0]}"):
                    excluir_zona(zona[0])
                    st.success("Zona excluída!")
                    st.rerun()
    else:
        st.info("Nenhuma zona cadastrada ainda.")

    # Botões extras
    if st.button("🧱 Gerenciar Materiais"):
        st.session_state['pagina'] = "gerenciar_materiais"
        st.rerun()

    if st.button("⬅️ Voltar"):
        st.session_state['pagina'] = "principal"
        st.rerun()

# ---------- Funções Utilitárias ----------
def email_valido(email):
    """Valida o formato do email"""
    return re.match(r"[^@]+@[^@]+\.[^@]+", email)

# ---------- Páginas ----------
def pagina_cadastro():
    """Página de cadastro de novos usuários"""
    st.subheader("📝 Cadastro de Novo Usuário")
    proximo_codigo = obter_proximo_codigo_usuario()

    with st.form("cadastro_form"):
        col1, col2 = st.columns(2)
        with col1:
            st.text_input("Código do Usuário", value=proximo_codigo, disabled=True)
            nome = st.text_input("Nome Completo", max_chars=100)
            funcao = st.text_input("Função/Cargo", max_chars=50)
            organizacao = st.text_input("Organização", max_chars=100)

        with col2:
            email = st.text_input("Email", max_chars=100)
            senha = st.text_input("Senha", type="password", max_chars=50)
            confirmar_senha = st.text_input("Confirmar Senha", type="password", max_chars=50)
            ativo = st.selectbox("Usuário Ativo?", ["sim", "não"])

        enviar = st.form_submit_button("Cadastrar")

        if enviar:
            if not email_valido(email):
                st.error("❌ Email inválido.")
            elif senha != confirmar_senha:
                st.error("❌ As senhas não coincidem.")
            elif len(senha) < 6:
                st.error("❌ A senha deve ter pelo menos 6 caracteres.")
            elif email_existe(email):
                st.warning("⚠️ Este email já está cadastrado.")
            else:
                if criar_usuario(proximo_codigo, nome, email, funcao, organizacao, senha, ativo):
                    st.success(f"✅ Usuário '{nome}' cadastrado com sucesso!")
                    st.balloons()
                else:
                    st.error("❌ Erro ao cadastrar usuário.")

def pagina_admin_usuarios():
    """Página de administração de utilizadores e perfis RBAC (apenas Usuário Supremo)."""
    role_atual = obter_perfil_atual()
    if not can_manage_users(role_atual):
        st.error(t("users_denied"))
        return

    st.title(t("users_title"))
    usuarios = listar_usuarios()

    if not usuarios.empty:
        opcoes_role = [ROLE_SUPER_ADMIN, ROLE_APPROVER, ROLE_USER]
        for _, usuario in usuarios.iterrows():
            col1, col2, col3, col4 = st.columns([3, 2, 3, 2])
            role_u = normalizar_role(usuario.get('role'), usuario.get('is_admin', 0))

            with col1:
                st.write(f"**{usuario['nome']}** · `{usuario['codigo']}`")
                st.caption(f"{t('email_label')}: {usuario['email']}")
                st.caption(f"{rotulo_perfil(role_u)} · {usuario['data_criacao']}")

            with col2:
                novo_status = st.selectbox(
                    t("users_status"),
                    ["sim", "não"],
                    index=0 if usuario['ativo'] == "sim" else 1,
                    key=f"status_{usuario['codigo']}"
                )
                if novo_status != usuario['ativo']:
                    if st.button(t("users_update_status"), key=f"upd_status_{usuario['codigo']}"):
                        try:
                            if alterar_status_usuario_seguro(role_atual, usuario['codigo'], novo_status):
                                st.success("✅")
                                st.rerun()
                        except PermissionError as exc:
                            st.error(str(exc))

            with col3:
                novo_role = st.selectbox(
                    t("users_role"),
                    opcoes_role,
                    index=opcoes_role.index(role_u) if role_u in opcoes_role else 2,
                    format_func=rotulo_perfil,
                    key=f"role_{usuario['codigo']}",
                )
                if novo_role != role_u:
                    if st.button(t("users_update_role"), key=f"upd_role_{usuario['codigo']}"):
                        try:
                            if alterar_role_usuario_seguro(role_atual, usuario['codigo'], novo_role):
                                st.success(t("users_role_updated"))
                                st.rerun()
                            else:
                                st.warning(t("users_role_blocked"))
                        except (PermissionError, ValueError) as exc:
                            st.error(str(exc))

            with col4:
                if usuario['email'] != "admin@insid.com" and usuario['codigo'] != st.session_state.get('usuario_id'):
                    if st.button(f"🗑️ {t('users_delete')}", key=f"del_{usuario['codigo']}"):
                        try:
                            if excluir_usuario_seguro(role_atual, usuario['codigo']):
                                st.success("✅")
                                st.rerun()
                        except PermissionError as exc:
                            st.error(str(exc))
                else:
                    st.write("")
    else:
        st.warning("Nenhum utilizador registado.")

    st.write("")
    if st.button(t("back_btn")):
        st.session_state['pagina'] = pagina_inicial_por_perfil(role_atual)
        st.rerun()

def pagina_login():
    """Página de login com seletor de idioma e encaminhamento por perfil RBAC."""
    col_top_l, col_top_r = st.columns([3, 1])
    with col_top_l:
        st.title(t("login_title"))
        st.caption(t("login_subtitle"))
    with col_top_r:
        render_seletor_idioma("login")

    col1, col2 = st.columns([1, 2])
    with col1:
        if LOGO_PATH.exists():
            st.image(str(LOGO_PATH), caption="Metodologia inSID", width=160)
    with col2:
        with st.form("login_form"):
            email = st.text_input(t("email_label"))
            senha = st.text_input(t("password_label"), type="password")
            entrar = st.form_submit_button(t("login_btn"), type="primary")

            if entrar:
                resultado = verificar_credenciais(email, senha)
                if resultado:
                    usuario_id, nome, is_admin, role = resultado
                    role_norm = normalizar_role(role, is_admin)
                    st.session_state.update({
                        'logado': True,
                        'email': email,
                        'usuario_id': usuario_id,
                        'usuario_nome': nome,
                        'is_admin': role_norm == ROLE_SUPER_ADMIN,
                        'role': role_norm,
                        'pagina': pagina_inicial_por_perfil(role_norm),
                    })
                    st.success(t("login_welcome", name=nome))
                    st.rerun()
                else:
                    st.error(t("login_invalid"))

def logout():
    """Limpa a sessão preservando o idioma escolhido e volta para o login."""
    idioma_atual = obter_idioma()
    st.session_state.clear()
    st.session_state["lang"] = idioma_atual
    st.rerun()


# ========================================
# FUNÇÕES DE BANCO DE DADOS CORRIGIDAS
# ========================================

def obter_anomalias_barragem(barragem_id: int) -> List[Tuple]:
    """
    Recupera todas as anomalias de uma barragem específica com informações relacionadas
    
    Args:
        barragem_id: ID da barragem para filtrar as anomalias
    
    Returns:
        Lista de tuplas contendo todos os dados das anomalias com joins nas tabelas relacionadas
    """
    conn = None
    try:
        conn = conectar_db()
        cursor = conn.cursor()
        
        query = """
        SELECT 
            ao.id,
            ao.barragem_id,
            ao.tipo_anomalia_id,
            ta.nome as nome_tipo_anomalia,
            ao.tipos_zonas_bar_id,
            tzb.nome as nome_zona,
            ao.tipos_materiais_id,
            tm.nome as nome_material,
            ao.descricao,
            ao.image_path,
            ao.fonte_inspecao_visual,
            ao.fonte_instrumentacao,
            ao.fonte_drones,
            ao.fonte_insar,
            ao.fonte_satellite,
            ao.data_observacao
        FROM 
            anomalias_observadas ao
        LEFT JOIN 
            tipo_anomalia ta ON ao.tipo_anomalia_id = ta.id
        LEFT JOIN 
            tipos_zonas_bar tzb ON ao.tipos_zonas_bar_id = tzb.id
        LEFT JOIN 
            tipos_materiais tm ON ao.tipos_materiais_id = tm.id
        WHERE 
            ao.barragem_id = ?
        ORDER BY 
            ao.data_observacao DESC
        """
        
        cursor.execute(query, (barragem_id,))
        return cursor.fetchall()
        
    except sqlite3.Error as e:
        st.error(f"Erro ao obter anomalias: {str(e)}")
        return []
    finally:
        if conn:
            conn.close()

# def obter_tipos_anomalia(usuario_id: int) -> List[Tuple]:
#     """
#     Obtém todos os tipos de anomalia cadastrados por um usuário
    
#     Args:
#         usuario_id: ID do usuário logado
    
#     Returns:
#         Lista de tuplas com (id, nome, descricao, image_path)
#     """
#     conn = None
#     try:
#         conn = conectar_db()
#         cursor = conn.cursor()
        
#         cursor.execute("""
#         SELECT id, nome, descricao, image_path 
#         FROM tipo_anomalia 
#         WHERE usuario_id = ?
#         ORDER BY nome
#         """, (usuario_id,))
        
#         return cursor.fetchall()
        
#     except sqlite3.Error as e:
#         st.error(f"Erro ao obter tipos de anomalia: {str(e)}")
#         return []
#     finally:
#         if conn:
#             conn.close()

def obter_tipos_anomalia(usuario_id: int = None) -> List[Tuple]:
    """
    Obtém todos os tipos de anomalia cadastrados no sistema
    
    Args:
        usuario_id: (Opcional) ID do usuário para filtrar apenas suas anomalias.
                   Se None, retorna todas as anomalias do sistema.
    
    Returns:
        Lista de tuplas com (id, nome, descricao, image_path)
    """
    conn = None
    try:
        conn = conectar_db()
        cursor = conn.cursor()
        
        if usuario_id is not None:
            cursor.execute("""
            SELECT id, nome, descricao, image_path 
            FROM tipo_anomalia 
            WHERE usuario_id = ?
            ORDER BY nome
            """, (usuario_id,))
        else:
            cursor.execute("""
            SELECT id, nome, descricao, image_path 
            FROM tipo_anomalia 
            ORDER BY nome
            """)
        
        return cursor.fetchall()
        
    except sqlite3.Error as e:
        st.error(f"Erro ao obter tipos de anomalia: {str(e)}")
        return []
    finally:
        if conn:
            conn.close()

def obter_tipos_zonas_bar() -> List[Tuple]:
    """
    Obtém todas as zonas de barragem disponíveis
    
    Returns:
        Lista de tuplas com (id, nome, descricao)
    """
    conn = None
    try:
        conn = conectar_db()
        cursor = conn.cursor()
        
        cursor.execute("""
        SELECT id, nome, descricao
        FROM tipos_zonas_bar
        ORDER BY nome
        """)
        
        return cursor.fetchall()
        
    except sqlite3.Error as e:
        st.error(f"Erro ao obter zonas da barragem: {str(e)}")
        return []
    finally:
        if conn:
            conn.close()

# def obter_tipos_materiais(usuario_id: int) -> List[Tuple]:
#     """
#     Obtém todos os tipos de materiais cadastrados por um usuário
    
#     Args:
#         usuario_id: ID do usuário logado
    
#     Returns:
#         Lista de tuplas com (id, nome, descricao)
#     """
#     conn = None
#     try:
#         conn = conectar_db()
#         cursor = conn.cursor()
        
#         cursor.execute("""
#         SELECT id, nome, descricao 
#         FROM tipos_materiais 
#         WHERE usuario_id = ?
#         ORDER BY nome
#         """, (usuario_id,))
        
#         return cursor.fetchall()
        
#     except sqlite3.Error as e:
#         st.error(f"Erro ao obter tipos de materiais: {str(e)}")
#         return []
#     finally:
#         if conn:
#             conn.close()


def obter_tipos_materiais(usuario_id: int = None) -> List[Tuple]:
    """
    Obtém todos os tipos de materiais cadastrados no sistema
    
    Args:
        usuario_id: (Opcional) ID do usuário para filtrar apenas seus materiais.
                   Se None, retorna todos os materiais do sistema.
    
    Returns:
        Lista de tuplas com (id, nome, descricao)
    """
    conn = None
    try:
        conn = conectar_db()
        cursor = conn.cursor()
        
        if usuario_id is not None:
            cursor.execute("""
            SELECT id, nome, descricao 
            FROM tipos_materiais 
            WHERE usuario_id = ?
            ORDER BY nome
            """, (usuario_id,))
        else:
            cursor.execute("""
            SELECT id, nome, descricao 
            FROM tipos_materiais 
            ORDER BY nome
            """)
        
        return cursor.fetchall()
        
    except sqlite3.Error as e:
        st.error(f"Erro ao obter tipos de materiais: {str(e)}")
        return []
    finally:
        if conn:
            conn.close()

def registrar_anomalia(
    barragem_id: int,
    tipo_anomalia_id: int,
    tipos_zonas_bar_id: int,
    tipos_materiais_id: int,
    descricao: str,
    image_path: Optional[str],
    fonte_inspecao_visual: bool,
    fonte_instrumentacao: bool,
    fonte_drones: bool,
    fonte_insar: bool,
    fonte_satellite: bool,
    data_observacao: str
) -> bool:
    """
    Registra uma nova anomalia no banco de dados
    
    Returns:
        True se o registro foi bem sucedido, False caso contrário
    """
    conn = None
    try:
        conn = conectar_db()
        cursor = conn.cursor()
        
        cursor.execute("""
        INSERT INTO anomalias_observadas (
            barragem_id, tipo_anomalia_id, tipos_zonas_bar_id,
            tipos_materiais_id, descricao, image_path,
            fonte_inspecao_visual, fonte_instrumentacao, fonte_drones,
            fonte_insar, fonte_satellite, data_observacao
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            barragem_id, tipo_anomalia_id, tipos_zonas_bar_id,
            tipos_materiais_id, descricao, image_path,
            int(fonte_inspecao_visual), int(fonte_instrumentacao), int(fonte_drones),
            int(fonte_insar), int(fonte_satellite), data_observacao
        ))
        
        conn.commit()
        return True
        
    except sqlite3.Error as e:
        st.error(f"Erro ao registrar anomalia: {str(e)}")
        return False
    finally:
        if conn:
            conn.close()

def atualizar_anomalia(
    anomalia_id: int,
    tipo_anomalia_id: int,
    tipos_zonas_bar_id: int,
    tipos_materiais_id: int,
    descricao: str,
    image_path: Optional[str],
    fonte_inspecao_visual: bool,
    fonte_instrumentacao: bool,
    fonte_drones: bool,
    fonte_insar: bool,
    fonte_satellite: bool,
    data_observacao: str
) -> bool:
    """
    Atualiza uma anomalia existente no banco de dados
    
    Returns:
        True se a atualização foi bem sucedida, False caso contrário
    """
    conn = None
    try:
        conn = conectar_db()
        cursor = conn.cursor()
        
        cursor.execute("""
        UPDATE anomalias_observadas SET
            tipo_anomalia_id = ?,
            tipos_zonas_bar_id = ?,
            tipos_materiais_id = ?,
            descricao = ?,
            image_path = ?,
            fonte_inspecao_visual = ?,
            fonte_instrumentacao = ?,
            fonte_drones = ?,
            fonte_insar = ?,
            fonte_satellite = ?,
            data_observacao = ?
        WHERE id = ?
        """, (
            tipo_anomalia_id, tipos_zonas_bar_id, tipos_materiais_id,
            descricao, image_path,
            int(fonte_inspecao_visual), int(fonte_instrumentacao), int(fonte_drones),
            int(fonte_insar), int(fonte_satellite), data_observacao,
            anomalia_id
        ))
        
        conn.commit()
        return cursor.rowcount > 0
        
    except sqlite3.Error as e:
        st.error(f"Erro ao atualizar anomalia: {str(e)}")
        return False
    finally:
        if conn:
            conn.close()

def excluir_anomalia(anomalia_id: int) -> bool:
    """
    Exclui uma anomalia do banco de dados
    
    Args:
        anomalia_id: ID da anomalia a ser excluída
    
    Returns:
        True se a exclusão foi bem sucedida, False caso contrário
    """
    conn = None
    try:
        conn = conectar_db()
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM anomalias_observadas WHERE id = ?", (anomalia_id,))
        conn.commit()
        
        return cursor.rowcount > 0
        
    except sqlite3.Error as e:
        st.error(f"Erro ao excluir anomalia: {str(e)}")
        return False
    finally:
        if conn:
            conn.close()

def salvar_imagem_anomalia(uploaded_file, barragem_id: int) -> Optional[str]:
    """
    Salva uma imagem de anomalia no sistema de arquivos
    
    Args:
        uploaded_file: Arquivo enviado pelo usuário
        barragem_id: ID da barragem
    
    Returns:
        Caminho do arquivo salvo ou None se houve erro
    """
    return salvar_arquivo_upload(uploaded_file, "anomalias", f"anomalia_{barragem_id}")

def inicializar_zonas_padrao():
    """
    Inicializa zonas padrão se a tabela estiver vazia
    """
    conn = None
    try:
        conn = conectar_db()
        cursor = conn.cursor()
        
        # Verifica se já existem zonas
        cursor.execute("SELECT COUNT(*) FROM tipos_zonas_bar")
        count = cursor.fetchone()[0]
        
        if count == 0:
            zonas_padrao = [
                ("Núcleo", "Zona central da barragem"),
                ("Filtro", "Zona de filtro da barragem"),
                ("Enrocamento de Montante", "Zona de enrocamento na face de montante"),
                ("Enrocamento de Jusante", "Zona de enrocamento na face de jusante"),
                ("Fundação", "Zona de fundação da barragem"),
                ("Coroamento", "Zona do coroamento da barragem"),
                ("Talude de Montante", "Talude da face de montante"),
                ("Talude de Jusante", "Talude da face de jusante"),
                ("Dreno", "Sistema de drenagem"),
                ("Face de Concreto", "Face de concreto (para barragens CFRD)")
            ]
            
            cursor.executemany("""
                INSERT INTO tipos_zonas_bar (nome, descricao)
                VALUES (?, ?)
            """, zonas_padrao)
            
            conn.commit()
            st.success("Zonas padrão inicializadas com sucesso!")
            
    except sqlite3.Error as e:
        st.error(f"Erro ao inicializar zonas padrão: {str(e)}")
    finally:
        if conn:
            conn.close()


def identificar_modo_falha_provavel(barragem_id):
    """
    Identifica o modo de falha mais provável considerando:
    1. Correspondência entre tipo de barragem e modos de falha
    2. Tipo de material da anomalia observada vs materiais associados às anomalias do sistema
    3. Zona da anomalia observada vs zonas associadas às anomalias do sistema
    4. Peso das anomalias para cada modo de falha
    """
    role = obter_perfil_atual()
    usuario_id = st.session_state.get('usuario_id')
    if not obter_barragem_autorizada(role, usuario_id, barragem_id):
        st.error(t("dam_unauthorized"))
        return

    conn = conectar_db()
    
    try:
        # Verifica se existem anomalias observadas para esta barragem
        count_anomalias = pd.read_sql(
            f"SELECT COUNT(*) FROM anomalias_observadas WHERE barragem_id = {barragem_id}", 
            conn
        ).iloc[0,0]
        
        if count_anomalias == 0:
            st.info("ℹ️ Adicione pelo menos uma anomalia observada para identificar o modo de falha provável.")
            return
        
        # Obter o tipo da barragem em análise
        tipo_barragem = pd.read_sql(
            f"""SELECT b.tipo_id, tb.nome as tipo_nome 
                FROM barragens b
                JOIN tipos_barragem tb ON b.tipo_id = tb.id
                WHERE b.id = {barragem_id}""",
            conn
        ).iloc[0]
        
        st.subheader(f"🔍 Análise para Barragem (Tipo: {tipo_barragem['tipo_nome']})")
        
        if st.button("🔍 Calcular Modo de Falha Provável", type="primary"):
            with st.spinner("Processando critérios de análise..."):
                # 1. Obter modos de falha associados ao tipo desta barragem (incluindo imagem e descrição)
                modos_falha = pd.read_sql(f"""
                    SELECT mf.id, mf.nome, mf.descricao, mf.image_path 
                    FROM modos_falha mf
                    JOIN modos_falha_tipo_barragem mftb ON mf.id = mftb.modos_falha_id
                    WHERE mftb.tipo_barragem_id = {tipo_barragem['tipo_id']}
                """, conn)
                
                if modos_falha.empty:
                    st.warning("⚠️ Nenhum modo de falha definido para este tipo de barragem")
                    return
                
                # 2. Obter todas as anomalias observadas para esta barragem
                anomalias_obs = pd.read_sql(f"""
                    SELECT 
                        ao.id,
                        ao.tipo_anomalia_id,
                        ao.tipos_zonas_bar_id as zona_id,
                        ao.tipos_materiais_id as material_id,
                        tz.nome as zona_nome,
                        tm.nome as material_nome,
                        ta.nome as anomalia_nome
                    FROM anomalias_observadas ao
                    JOIN tipos_zonas_bar tz ON ao.tipos_zonas_bar_id = tz.id
                    JOIN tipos_materiais tm ON ao.tipos_materiais_id = tm.id
                    JOIN tipo_anomalia ta ON ao.tipo_anomalia_id = ta.id
                    WHERE ao.barragem_id = {barragem_id}
                """, conn)
                
                # Estrutura para resultados
                resultados = []
                
                # 3. Para cada modo de falha, calcular o score
                for _, mf in modos_falha.iterrows():
                    score_total = 0.0
                    anomalias_contribuintes = []
                    
                    # Obter todas as anomalias do sistema para este modo de falha
                    anomalias_sistema = pd.read_sql(f"""
                        SELECT 
                            a.id,
                            a.tipo_anomalia_id,
                            a.peso,
                            ta.nome as nome_anomalia
                        FROM anomalias a
                        JOIN tipo_anomalia ta ON a.tipo_anomalia_id = ta.id
                        WHERE a.modos_falha_id = {mf['id']}
                    """, conn)
                    
                    # Para cada anomalia observada, verificar correspondência
                    for _, obs in anomalias_obs.iterrows():
                        # Verificar se há correspondência com anomalias do sistema
                        for _, anom in anomalias_sistema.iterrows():
                            if anom['tipo_anomalia_id'] == obs['tipo_anomalia_id']:
                                # Verificar material (anomalia_tipo_material)
                                material_match = pd.read_sql(f"""
                                    SELECT 1 FROM anomalia_tipo_material 
                                    WHERE anomalia_id = {anom['id']} 
                                    AND tipo_mat_id = {obs['material_id']}
                                    LIMIT 1
                                """, conn).shape[0] > 0
                                
                                # Verificar zona (anomalia_zona)
                                zona_match = pd.read_sql(f"""
                                    SELECT 1 FROM anomalia_zona 
                                    WHERE anomalia_id = {anom['id']} 
                                    AND zona_id = {obs['zona_id']}
                                    LIMIT 1
                                """, conn).shape[0] > 0
                                
                                # Se atender aos critérios, calcular contribuição
                                if material_match and zona_match:
                                    contribuicao = anom['peso'] * (1 + 0.5*material_match + 0.5*zona_match)
                                    score_total += contribuicao
                                    
                                    anomalias_contribuintes.append({
                                        'anomalia_obs_id': obs['id'],
                                        'anomalia_obs_nome': obs['anomalia_nome'],
                                        'anomalia_sistema_id': anom['id'],
                                        'anomalia_sistema_nome': anom['nome_anomalia'],
                                        'material': obs['material_nome'],
                                        'zona': obs['zona_nome'],
                                        'peso': anom['peso'],
                                        'contribuicao': contribuicao
                                    })
                    
                    if score_total > 0:
                        resultados.append({
                            'modo_falha_id': mf['id'],
                            'modo_falha_nome': mf['nome'],
                            'modo_falha_descricao': mf['descricao'],
                            'modo_falha_imagem': mf['image_path'],
                            'score_total': score_total,
                            'anomalias_contribuintes': anomalias_contribuintes
                        })
                
                if not resultados:
                    st.warning("⚠️ Nenhum modo de falha atendeu a todos os critérios de análise")
                    return
                
                # Ordenar por score
                resultados.sort(key=lambda x: x['score_total'], reverse=True)
                
                # Normalizar scores para porcentagem
                total_score = sum(r['score_total'] for r in resultados)
                for r in resultados:
                    r['probabilidade'] = (r['score_total'] / total_score) * 100
                
                # Exibir resultados
                st.success("🎯 Resultados da Análise")
                
                # Gráfico de probabilidades
                df_plot = pd.DataFrame({
                    'Modo de Falha': [r['modo_falha_nome'] for r in resultados],
                    'Probabilidade (%)': [r['probabilidade'] for r in resultados]
                })
                
                fig = px.bar(
                    df_plot,
                    x='Modo de Falha',
                    y='Probabilidade (%)',
                    color='Modo de Falha',
                    text='Probabilidade (%)',
                    title='Probabilidade por Modo de Falha',
                    labels={'Probabilidade (%)': 'Probabilidade (%)'}
                )
                fig.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
                st.plotly_chart(fig, use_container_width=True)
                
                # Tabela detalhada com imagens e descrições
                st.subheader("📊 Detalhes da Análise")
                
                for res in resultados:
                    with st.expander(f"{res['modo_falha_nome']} ({res['probabilidade']:.1f}%)"):
                        # Criar colunas para imagem e descrição
                        col1, col2 = st.columns([1, 2])
                        
                        with col1:
                            # Exibir imagem se existir
                            img_res = resolver_caminho_arquivo(res['modo_falha_imagem'])
                            if img_res:
                                try:
                                    st.image(
                                        str(img_res),
                                        caption=f"Modo de Falha: {res['modo_falha_nome']}",
                                        use_container_width=True
                                    )
                                except Exception:
                                    st.warning("Não foi possível apresentar a imagem deste modo de falha.")
                            else:
                                st.warning("Sem imagem disponível")
                        
                        with col2:
                            st.write(f"**Descrição:**")
                            st.write(res['modo_falha_descricao'] or "Sem descrição disponível")
                        
                        st.write(f"**Score Total:** {res['score_total']:.2f}")
                        
                        df_contrib = pd.DataFrame(res['anomalias_contribuintes'])
                        st.dataframe(
                            df_contrib[['anomalia_obs_nome', 'anomalia_sistema_nome', 
                                      'material', 'zona', 'peso', 'contribuicao']],
                            column_config={
                                'contribuicao': st.column_config.NumberColumn(
                                    'Contribuição',
                                    format="%.2f"
                                ),
                                'peso': st.column_config.NumberColumn(
                                    'Peso Original',
                                    format="%.2f"
                                )
                            },
                            hide_index=True,
                            use_container_width=True
                        )
    
    except Exception as e:
        st.error(f"⛔ Erro durante a análise: {str(e)}")
    finally:
        conn.close()


def pagina_principal():
    """Página principal de análises de barragens com isolamento estrito por perfil RBAC."""
    role = obter_perfil_atual()
    usuario_id = st.session_state['usuario_id']

    if not can_access_dam_analyses(role):
        st.title(t("approvals_title"))
        st.info(t("approver_no_analyses"))
        if st.button(t("go_to_approvals"), type="primary"):
            st.session_state['pagina'] = "fila_aprovacoes"
            st.rerun()
        return

    titulo = t("principal_title_all") if can_view_all_dam_analyses(role) else t("principal_title_mine")
    st.title(titulo)
    st.markdown(t("logged_user_line", name=st.session_state['usuario_nome'], role=rotulo_perfil(role)))

    # Inicializar zonas padrão se necessário
    inicializar_zonas_padrao()

    # Barra de seleção de barragem em análise (com isolamento estrito por perfil)
    st.subheader(t("dam_in_analysis"))
    barragens_usuario = listar_barragens_escopo(role, usuario_id)
    barragem_analise = obter_barragem_analise_escopo(role, usuario_id)

    if barragem_analise:
        st.success(t("dam_current", name=barragem_analise[2]))
    else:
        st.warning(t("dam_none_selected"))

    if barragens_usuario:
        barragem_selecionada = str(barragem_analise[0]) if barragem_analise else ""
        opcoes_barragens = {"": t("dam_select_placeholder")}
        for b in barragens_usuario:
            if can_view_all_dam_analyses(role) and len(b) > 7 and b[7]:
                opcoes_barragens[str(b[0])] = f"{b[1]} · ({b[7]})"
            else:
                opcoes_barragens[str(b[0])] = f"{b[1]}"

        chaves_opcoes = list(opcoes_barragens.keys())
        idx_atual = chaves_opcoes.index(barragem_selecionada) if barragem_selecionada in chaves_opcoes else 0

        col1, col2 = st.columns([3, 1])
        with col1:
            nova_barragem = st.selectbox(
                t("dam_select_label"),
                options=chaves_opcoes,
                format_func=lambda x: opcoes_barragens.get(x, t("dam_select_placeholder")),
                index=idx_atual
            )

        with col2:
            st.write("")
            st.write("")
            if st.button(t("dam_save_selection"), type="primary"):
                if nova_barragem:
                    try:
                        definir_barragem_analise_escopo(role, usuario_id, int(nova_barragem))
                        st.success(t("dam_current", name=opcoes_barragens[nova_barragem]))
                        st.rerun()
                    except PermissionError:
                        st.error(t("dam_unauthorized"))
                else:
                    st.error(t("dam_none_selected"))

        if barragem_analise:
            with st.expander("📝 Editar Barragem"):
                editar_barragem(barragem_analise)

            # === ANOMALIAS ===
            st.subheader("🚨 Anomalias Observadas")
            tab_listar, tab_adicionar, tab_editar = st.tabs(["📋 Listar Anomalias", "➕ Adicionar Anomalia", "✏️ Editar/Excluir"])

            with tab_listar:
                st.write("### Lista de Anomalias Registradas")
                anomalias = obter_anomalias_barragem(barragem_analise[0])
                if anomalias:
                    for anomalia in anomalias:
                        # with st.expander(f"Anomalia #{anomalia[0]} - {anomalia[3]}"):
                        with st.expander(f"Anomalia #{anomalia[0]} - {anomalia[3]} - {anomalia[5]}"):
                            cols = st.columns([1, 3])
                            with cols[0]:
                                img_obs = resolver_caminho_arquivo(anomalia[9])
                                if img_obs:
                                    try:
                                        st.image(str(img_obs), caption="Imagem da anomalia", width=200)
                                    except Exception:
                                        st.write("⚠️ Imagem indisponível")
                            with cols[1]:
                                st.write(f"**Tipo:** {anomalia[3]}")
                                st.write(f"**Zona:** {anomalia[5]}")
                                st.write(f"**Material:** {anomalia[7]}")
                                st.write(f"**Data:** {anomalia[15]}")
                                st.write(f"**Descrição:** {anomalia[8]}")
                                fontes = []
                                if anomalia[10]: fontes.append("🔍 Inspeção Visual")
                                if anomalia[11]: fontes.append("📊 Instrumentação")
                                if anomalia[12]: fontes.append("🚁 Drones")
                                if anomalia[13]: fontes.append("🛰️ InSAR")
                                if anomalia[14]: fontes.append("🌍 Satélite")
                                st.write("**Fontes de detecção:**", " | ".join(fontes) if fontes else "Nenhuma")

                    st.markdown("---")
                    st.subheader("🎯 Identificação do modo de falha provável")
                    identificar_modo_falha_provavel(barragem_analise[0])

                else:
                    st.info("Nenhuma anomalia registrada para esta barragem")

            with tab_adicionar:
                st.write("### Registrar nova anomalia")
                with st.form("form_adicionar_anomalia", clear_on_submit=True):
                    # ✅ Sem filtro por usuário
                    tipos_anomalia = obter_tipos_anomalia()
                    zonas_barragem = obter_tipos_zonas_bar()
                    materiais = obter_tipos_materiais()

                    if not tipos_anomalia:
                        st.error("⚠️ Nenhum tipo de anomalia cadastrado. Cadastre tipos de anomalia primeiro.")
                        st.stop()

                    if not zonas_barragem:
                        st.error("⚠️ Nenhuma zona de barragem disponível.")
                        st.stop()

                    if not materiais:
                        st.error("⚠️ Nenhum material cadastrado. Cadastre tipos de materiais primeiro.")
                        st.stop()

                    tipo_selecionado = st.selectbox("Tipo de Anomalia*", options=tipos_anomalia, format_func=lambda x: x[1])
                    zona_selecionada = st.selectbox("Zona da Barragem*", options=zonas_barragem, format_func=lambda x: f"{x[1]} - {x[2]}" if x[2] else x[1])
                    material_selecionado = st.selectbox("Material*", options=materiais, format_func=lambda x: x[1])
                    descricao = st.text_area("Descrição Detalhada*")
                    data_observacao = st.date_input("Data de Observação*")
                    image_path = st.file_uploader("Imagem da Anomalia (opcional)", type=['png', 'jpg', 'jpeg'])

                    st.write("**Fontes de Detecção** (selecione pelo menos uma)*")
                    col1, col2 = st.columns(2)
                    with col1:
                        fonte_visual = st.checkbox("Inspeção Visual")
                        fonte_instrumentacao = st.checkbox("Instrumentação")
                        fonte_drones = st.checkbox("Drones")
                    with col2:
                        fonte_insar = st.checkbox("InSAR")
                        fonte_satellite = st.checkbox("Satélite")

                    if st.form_submit_button("✅ Registrar Anomalia"):
                        if not descricao.strip():
                            st.error("A descrição é obrigatória")
                        elif not any([fonte_visual, fonte_instrumentacao, fonte_drones, fonte_insar, fonte_satellite]):
                            st.error("Selecione pelo menos uma fonte de detecção")
                        else:
                            img_path_str = salvar_imagem_anomalia(image_path, barragem_analise[0]) if image_path else None
                            sucesso = registrar_anomalia(
                                barragem_id=barragem_analise[0],
                                tipo_anomalia_id=tipo_selecionado[0],
                                tipos_zonas_bar_id=zona_selecionada[0],
                                tipos_materiais_id=material_selecionado[0],
                                descricao=descricao.strip(),
                                image_path=img_path_str,
                                fonte_inspecao_visual=fonte_visual,
                                fonte_instrumentacao=fonte_instrumentacao,
                                fonte_drones=fonte_drones,
                                fonte_insar=fonte_insar,
                                fonte_satellite=fonte_satellite,
                                data_observacao=data_observacao.strftime('%Y-%m-%d')
                            )
                            if sucesso:
                                st.success("Anomalia registrada com sucesso!")
                                st.rerun()

            with tab_editar:
                st.write("### Editar ou Excluir Anomalias")
                anomalias = obter_anomalias_barragem(barragem_analise[0])
                if anomalias:
                    anomalia_selecionada = st.selectbox(
                        "Selecione a anomalia para edição/exclusão",
                        options=anomalias,
                        format_func=lambda x: f"Anomalia #{x[0]} - {x[3]} ({x[15]})"
                    )

                    if anomalia_selecionada:
                        col_excluir, _ = st.columns([1, 3])
                        with col_excluir:
                            if st.button("🗑️ Excluir Anomalia", type="secondary"):
                                if st.session_state.get('confirmar_exclusao') != anomalia_selecionada[0]:
                                    st.session_state['confirmar_exclusao'] = anomalia_selecionada[0]
                                    st.warning("⚠️ Clique novamente para confirmar a exclusão")
                                else:
                                    if excluir_anomalia(anomalia_selecionada[0]):
                                        st.success("Anomalia excluída com sucesso!")
                                        del st.session_state['confirmar_exclusao']
                                        st.rerun()
                                    else:
                                        st.error("Erro ao excluir anomalia")

                        with st.form("form_editar_anomalia"):
                            st.write("#### Editar Anomalia")

                            # ✅ Sem filtro por usuário
                            tipos_anomalia = obter_tipos_anomalia()
                            zonas_barragem = obter_tipos_zonas_bar()
                            materiais = obter_tipos_materiais()

                            tipo_atual = next((t for t in tipos_anomalia if t[0] == anomalia_selecionada[2]), tipos_anomalia[0])
                            zona_atual = next((z for z in zonas_barragem if z[0] == anomalia_selecionada[4]), zonas_barragem[0])
                            material_atual = next((m for m in materiais if m[0] == anomalia_selecionada[6]), materiais[0])

                            novo_tipo = st.selectbox("Tipo de Anomalia", options=tipos_anomalia, format_func=lambda x: x[1], index=tipos_anomalia.index(tipo_atual))
                            nova_zona = st.selectbox("Zona da Barragem", options=zonas_barragem, format_func=lambda x: f"{x[1]} - {x[2]}" if x[2] else x[1], index=zonas_barragem.index(zona_atual))
                            novo_material = st.selectbox("Material", options=materiais, format_func=lambda x: x[1], index=materiais.index(material_atual))
                            nova_descricao = st.text_area("Descrição detalhada", value=anomalia_selecionada[8] or "")
                            try:
                                data_atual = datetime.strptime(anomalia_selecionada[15], '%Y-%m-%d').date()
                            except:
                                data_atual = datetime.now().date()
                            nova_data = st.date_input("Data de Observação", value=data_atual)

                            st.write("Fontes de Detecção:")
                            col1, col2 = st.columns(2)
                            with col1:
                                fonte_visual = st.checkbox("Inspeção Visual", value=bool(anomalia_selecionada[10]))
                                fonte_instrumentacao = st.checkbox("Instrumentação", value=bool(anomalia_selecionada[11]))
                                fonte_drones = st.checkbox("Drones", value=bool(anomalia_selecionada[12]))
                            with col2:
                                fonte_insar = st.checkbox("InSAR", value=bool(anomalia_selecionada[13]))
                                fonte_satellite = st.checkbox("Satélite", value=bool(anomalia_selecionada[14]))

                            if st.form_submit_button("💾 Salvar Alterações"):
                                if not nova_descricao.strip():
                                    st.error("A descrição é obrigatória")
                                elif not any([fonte_visual, fonte_instrumentacao, fonte_drones, fonte_insar, fonte_satellite]):
                                    st.error("Selecione pelo menos uma fonte de detecção")
                                else:
                                    sucesso = atualizar_anomalia(
                                        anomalia_id=anomalia_selecionada[0],
                                        tipo_anomalia_id=novo_tipo[0],
                                        tipos_zonas_bar_id=nova_zona[0],
                                        tipos_materiais_id=novo_material[0],
                                        descricao=nova_descricao.strip(),
                                        image_path=anomalia_selecionada[9],
                                        fonte_inspecao_visual=fonte_visual,
                                        fonte_instrumentacao=fonte_instrumentacao,
                                        fonte_drones=fonte_drones,
                                        fonte_insar=fonte_insar,
                                        fonte_satellite=fonte_satellite,
                                        data_observacao=nova_data.strftime('%Y-%m-%d')
                                    )
                                    if sucesso:
                                        st.success("Anomalia atualizada com sucesso!")
                                        st.rerun()
                                    else:
                                        st.error("Erro ao atualizar anomalia")
                else:
                    st.info("Nenhuma anomalia registrada para esta barragem")

    else:
        st.info(t("dam_empty_cta"))
        if st.button(t("dam_register_now"), type="primary"):
            st.session_state['pagina'] = "cadastro_barragem"
            st.rerun()


def menu_lateral():
    """Menu lateral limpo e contextual por perfil RBAC com seletor de idioma PT/EN."""
    role = obter_perfil_atual()
    usuario_id = st.session_state.get('usuario_id')
    nome_utilizador = st.session_state.get('usuario_nome', '')

    with st.sidebar:
        st.markdown(
            f'<div class="desproj-brand-header">'
            f'<div class="brand-title">{t("brand_title")}</div>'
            f'<div class="brand-sub">{t("brand_sub")}</div>'
            f'<span class="desproj-role-badge">{rotulo_perfil(role)}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
        st.caption(f"👤 {nome_utilizador}")
        render_seletor_idioma("sidebar")

        redirecionar = None

        # 1. Secção de Administração e Aprovações
        if can_manage_users(role) or can_approve_configs(role):
            st.markdown("---")
            st.subheader(t("nav_admin_section"))
            if can_manage_users(role):
                if st.button(t("nav_manage_users"), use_container_width=True):
                    redirecionar = "admin_usuarios"
            if can_approve_configs(role):
                qtd_pend = contar_propostas_pendentes()
                if st.button(t("nav_approval_queue", count=qtd_pend), use_container_width=True):
                    redirecionar = "fila_aprovacoes"
        else:
            st.markdown("---")
            minhas_pend = len(listar_propostas_configuracao(role, usuario_id, status_filter="pending"))
            if st.button(t("nav_my_proposals", count=minhas_pend), use_container_width=True):
                redirecionar = "minhas_propostas"

        # 2. Análises de Barragens (oculto para Aprovador; global para Usuário Supremo; próprio para Usuário Normal)
        if can_access_dam_analyses(role):
            st.markdown("---")
            st.subheader(t("nav_analyses_section"))
            home_label = t("nav_home_all") if can_view_all_dam_analyses(role) else t("nav_home_mine")
            if st.button(home_label, use_container_width=True):
                redirecionar = "principal"
            if st.button(t("nav_register_dam"), use_container_width=True):
                redirecionar = "cadastro_barragem"

        # 3. Configurações das Barragens (todos os perfis; Usuário Normal cria propostas pendentes)
        st.markdown("---")
        st.subheader(t("nav_dam_configs"))
        if st.button(t("nav_dam_types"), use_container_width=True):
            redirecionar = "gerenciar_tipos_barragem"
        if st.button(t("nav_dam_zones"), use_container_width=True):
            redirecionar = "cadastro_zonas_barragem"
        if st.button(t("nav_materials"), use_container_width=True):
            redirecionar = "gerenciar_tipos_materiais"

        # 4. Configurações dos Modos de Falha
        st.markdown("---")
        st.subheader(t("nav_fm_configs"))
        if st.button(t("nav_anomaly_types"), use_container_width=True):
            redirecionar = "gerenciar_tipos_anomalia"
        if st.button(t("nav_fm_categories"), use_container_width=True):
            redirecionar = "gerenciar_tipos_modo_falha"
        if st.button(t("nav_fm_manage"), use_container_width=True):
            redirecionar = "gerenciar_modos_falha_anomalias"

        st.markdown("---")
        if st.button(t("logout_btn"), use_container_width=True):
            logout()
            return

        if redirecionar:
            st.session_state['pagina'] = redirecionar
            st.rerun()


def main():
    """Função principal que controla o fluxo do aplicativo com RBAC e i18n."""
    if 'logado' not in st.session_state:
        st.session_state['logado'] = False
        st.session_state['pagina'] = "login"

    if not st.session_state['logado']:
        tab1, tab2 = st.tabs([t("tab_login"), t("tab_register")])
        with tab1:
            pagina_login()
        with tab2:
            pagina_cadastro()
    else:
        role = obter_perfil_atual()
        menu_lateral()

        pagina = st.session_state.get('pagina') or pagina_inicial_por_perfil(role)

        if pagina == "cadastro_barragem":
            exibir_formulario_cadastro_barragem()

        elif pagina == "admin_usuarios":
            pagina_admin_usuarios()

        elif pagina == "fila_aprovacoes":
            pagina_fila_aprovacoes()

        elif pagina == "minhas_propostas":
            pagina_minhas_propostas()

        elif pagina == "gerenciar_tipos_barragem":
            gerenciar_tipos_barragem()

        elif pagina == "cadastro_zonas_barragem":
            gerenciar_tipos_zonas()

        elif pagina == "gerenciar_tipos_materiais":
            gerenciar_tipos_materiais()

        elif pagina == "gerenciar_tipos_modo_falha":
            gerenciar_tipos_modo_falha()

        elif pagina == "gerenciar_tipos_anomalia":
            gerenciar_tipos_anomalia()

        elif pagina == "gerenciar_modos_falha_anomalias":
            gerenciar_modos_falha_anomalias()

        elif pagina == "principal":
            pagina_principal()

        else:
            if can_access_dam_analyses(role):
                pagina_principal()
            else:
                pagina_fila_aprovacoes()

if __name__ == "__main__":
    main()