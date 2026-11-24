import base64
import os
import sqlite3
from contextlib import closing
import hashlib
from pathlib import Path
import pandas as pd
from typing import Optional, Tuple

from turso_compat import TursoConnection

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "inSID.db"


def _obter_config_turso() -> Tuple[Optional[str], Optional[str]]:
    """Lê credenciais Turso de st.secrets (Streamlit Cloud) ou variáveis de ambiente."""
    url = os.environ.get("TURSO_DATABASE_URL", "").strip()
    token = os.environ.get("TURSO_AUTH_TOKEN", "").strip()
    if not (url and token):
        try:
            import streamlit as st
            url = url or str(st.secrets.get("TURSO_DATABASE_URL", "")).strip()
            token = token or str(st.secrets.get("TURSO_AUTH_TOKEN", "")).strip()
        except Exception:
            pass
    if url and token:
        return url, token
    return None, None


def usando_turso() -> bool:
    """Indica se a aplicação está ligada à base de dados persistente Turso na nuvem."""
    url, token = _obter_config_turso()
    return bool(url and token)


def hash_senha(senha):
    """Gera hash SHA-256 para senhas"""
    return hashlib.sha256(senha.encode()).hexdigest()


def conectar_db():
    """Estabelece conexão com Turso (produção na nuvem) ou SQLite local (desenvolvimento)."""
    url, token = _obter_config_turso()
    if url and token:
        return TursoConnection(url, token)
    return sqlite3.connect(str(DB_PATH))


def _migrar_seed_local_para_turso_se_vazio(conn) -> None:
    """Na primeira execução no Turso, importa automaticamente os dados iniciais de inSID.db."""
    if not isinstance(conn, TursoConnection) or not DB_PATH.exists():
        return
    cur = conn.cursor()
    if cur.execute("SELECT 1 FROM modos_falha LIMIT 1").fetchone():
        return

    tabelas_ordenadas = [
        "usuarios",
        "tipos_fundacao",
        "categorias_anomalias",
        "tipos_barragem",
        "tipos_materiais",
        "tipos_zonas_bar",
        "tipo_modo_falha",
        "tipo_anomalia",
        "barragens",
        "usuario_barragem_analise",
        "modos_falha",
        "modos_falha_tipo_barragem",
        "anomalias",
        "anomalia_zona",
        "anomalia_tipo_material",
        "anomalias_observadas",
    ]
    with closing(sqlite3.connect(str(DB_PATH))) as local_conn:
        lcur = local_conn.cursor()
        for tabela in tabelas_ordenadas:
            existe = lcur.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (tabela,)
            ).fetchone()
            if not existe:
                continue
            rows = lcur.execute(f'SELECT * FROM "{tabela}"').fetchall()
            if not rows:
                continue
            cols = [d[0] for d in lcur.description]
            placeholders = ", ".join(["?"] * len(cols))
            col_list = ", ".join(f'"{c}"' for c in cols)
            cur.executemany(
                f'INSERT OR IGNORE INTO "{tabela}" ({col_list}) VALUES ({placeholders})',
                rows,
            )


def _criar_tabelas_schema(cursor) -> None:
    """Cria todas as tabelas com schema compatível com SQLite local e Turso (foreign_keys=ON)."""
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS usuarios (
        codigo TEXT PRIMARY KEY,
        nome TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        funcao TEXT,
        organizacao TEXT,
        senha_hash TEXT NOT NULL,
        ativo TEXT NOT NULL,
        data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        is_admin INTEGER DEFAULT 0,
        role TEXT NOT NULL DEFAULT 'user'
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS config_change_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        entity_type TEXT NOT NULL,
        action TEXT NOT NULL,
        target_id INTEGER,
        payload_json TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        proposed_by TEXT NOT NULL,
        proposed_by_name TEXT,
        reviewed_by TEXT,
        review_note TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        reviewed_at TIMESTAMP
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS midia_uploads (
        caminho TEXT PRIMARY KEY,
        conteudo_b64 TEXT NOT NULL,
        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tipos_fundacao (
        id INTEGER PRIMARY KEY,
        nome TEXT UNIQUE NOT NULL,
        descricao TEXT,
        caracteristicas TEXT,
        referencia_tecnica TEXT
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS categorias_anomalias (
        id INTEGER PRIMARY KEY,
        nome TEXT UNIQUE NOT NULL,
        descricao TEXT
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tipos_barragem (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario_id INTEGER NOT NULL,
        nome TEXT NOT NULL,
        descricao TEXT,
        referencia_tecnica TEXT,
        image_path TEXT
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tipos_materiais (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario_id INTEGER NOT NULL,
        nome TEXT NOT NULL,
        descricao TEXT
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tipos_zonas_bar (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        descricao TEXT
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tipo_modo_falha (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario_id INTEGER NOT NULL,
        nome TEXT NOT NULL,
        descricao TEXT,
        referencia_tecnica TEXT
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tipo_anomalia (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario_id INTEGER NOT NULL,
        nome TEXT NOT NULL,
        descricao TEXT,
        image_path TEXT
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS barragens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario_id INTEGER NOT NULL,
        owner_id TEXT,
        nome TEXT NOT NULL,
        tipo_id INTEGER NOT NULL,
        localizacao TEXT,
        altura REAL,
        comprimento REAL,
        rel_cordaaltura REAL,
        em_analise INTEGER DEFAULT 0,
        data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (tipo_id) REFERENCES tipos_barragem(id)
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS usuario_barragem_analise (
        usuario_id INTEGER NOT NULL,
        barragem_id INTEGER NOT NULL,
        data_selecao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (barragem_id) REFERENCES barragens(id),
        PRIMARY KEY (usuario_id)
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS modos_falha (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario_id INTEGER NOT NULL,
        id_tipo_modo_falha INTEGER NOT NULL,
        nome TEXT NOT NULL,
        descricao TEXT,
        referencia_tecnica TEXT,
        image_path TEXT,
        FOREIGN KEY (id_tipo_modo_falha) REFERENCES tipo_modo_falha(id)
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS modos_falha_tipo_barragem (
        modos_falha_id INTEGER NOT NULL,
        tipo_barragem_id INTEGER NOT NULL,
        FOREIGN KEY (modos_falha_id) REFERENCES modos_falha(id) ON DELETE CASCADE,
        FOREIGN KEY (tipo_barragem_id) REFERENCES tipos_barragem(id) ON DELETE CASCADE,
        PRIMARY KEY (modos_falha_id, tipo_barragem_id)
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS anomalias (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        modos_falha_id INTEGER NOT NULL,
        usuario_id INTEGER NOT NULL,
        tipo_anomalia_id INTEGER NOT NULL,
        gravidade REAL,
        peso REAL,
        image_path TEXT,
        FOREIGN KEY (modos_falha_id) REFERENCES modos_falha(id),
        FOREIGN KEY (tipo_anomalia_id) REFERENCES tipo_anomalia(id)
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS anomalia_zona (
        anomalia_id INTEGER NOT NULL,
        zona_id INTEGER NOT NULL,
        FOREIGN KEY (anomalia_id) REFERENCES anomalias(id) ON DELETE CASCADE,
        PRIMARY KEY (anomalia_id, zona_id)
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS anomalia_tipo_material (
        anomalia_id INTEGER NOT NULL,
        tipo_mat_id INTEGER NOT NULL,
        FOREIGN KEY (anomalia_id) REFERENCES anomalias(id) ON DELETE CASCADE,
        FOREIGN KEY (tipo_mat_id) REFERENCES tipos_materiais(id) ON DELETE CASCADE,
        PRIMARY KEY (anomalia_id, tipo_mat_id)
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS anomalias_observadas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        barragem_id INTEGER NOT NULL,
        tipo_anomalia_id INTEGER NOT NULL,
        tipos_zonas_bar_id INTEGER NOT NULL,
        tipos_materiais_id INTEGER NOT NULL,
        descricao TEXT,
        image_path TEXT,
        fonte_inspecao_visual BOOLEAN DEFAULT 0,
        fonte_instrumentacao BOOLEAN DEFAULT 0,
        fonte_drones BOOLEAN DEFAULT 0,
        fonte_insar BOOLEAN DEFAULT 0,
        fonte_satellite BOOLEAN DEFAULT 0,
        data_observacao DATE
    );
    """)


def inicializar_bd():
    with closing(conectar_db()) as conn:
        cursor = conn.cursor()

        # No Turso, se a primeira migração ainda não concluiu (modos_falha vazio),
        # limpa tabelas antigas com FK inválida (REFERENCES usuarios(id)) antes de recriar e migrar.
        if isinstance(conn, TursoConnection):
            mf_existe = cursor.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='modos_falha'"
            ).fetchone()
            mf_tem_dados = False
            if mf_existe:
                mf_tem_dados = cursor.execute("SELECT 1 FROM modos_falha LIMIT 1").fetchone() is not None
            if not mf_tem_dados:
                for t in [
                    "anomalias_observadas", "anomalia_tipo_material", "anomalia_zona",
                    "anomalias", "modos_falha_tipo_barragem", "modos_falha",
                    "usuario_barragem_analise", "barragens", "tipo_anomalia",
                    "tipo_modo_falha", "tipos_zonas_bar", "tipos_materiais",
                    "tipos_barragem", "categorias_anomalias", "tipos_fundacao", "usuarios"
                ]:
                    cursor.execute(f'DROP TABLE IF EXISTS "{t}"')

        _criar_tabelas_schema(cursor)

        # Se estiver ligado ao Turso pela primeira vez, importa os dados iniciais de inSID.db
        _migrar_seed_local_para_turso_se_vazio(conn)

        # Fallbacks mínimos caso não exista inSID.db seed
        if not cursor.execute("SELECT 1 FROM tipos_barragem LIMIT 1").fetchone():
            cursor.executemany("""
                INSERT INTO tipos_barragem (usuario_id, nome, descricao)
                VALUES (?, ?, ?)
            """, [
                (1, "Homogênea", "Barragem construída com um único tipo de material"),
                (1, "Terra e Enrocamento", "Barragem com núcleo de terra e envoltório de enrocamento"),
                (1, "Enrocamento com Face de Betão", "Barragem de enrocamento com face de concreto"),
                (1, "Enrocamento com Núcleo Betuminoso", "Barragem de enrocamento com núcleo impermeável de betume")
            ])

        if not cursor.execute("SELECT 1 FROM tipo_modo_falha LIMIT 1").fetchone():
            cursor.executemany("""
                INSERT INTO tipo_modo_falha (usuario_id, nome, descricao, referencia_tecnica)
                VALUES (?, ?, ?, ?)
            """, [
                (1, 'Erosão Interna', 'Erosão interna dos solos...', '*'),
                (1, 'Movimento de Grandes Massas', 'Instabilidades estáticas...', '*'),
                (1, 'Roturas Hidráulicas', 'Falhas devido a níveis de água...', '*')
            ])

        if not cursor.execute("SELECT 1 FROM usuarios LIMIT 1").fetchone():
            super_email = os.environ.get("INSID_SUPER_ADMIN_EMAIL", "admin@insid.com").strip()
            senha_inicial = os.environ.get("INSID_ADMIN_PASSWORD", "admin123")
            cursor.execute(
                """INSERT INTO usuarios (codigo, nome, email, funcao, organizacao, senha_hash, ativo, is_admin, role)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                ("1", "Administrador", super_email, "Administrador", "inSID", hash_senha(senha_inicial), "sim", 1, "super_admin")
            )

        _garantir_migracoes_rbac(cursor)
        conn.commit()


def _coluna_existe(cursor, tabela: str, coluna: str) -> bool:
    rows = cursor.execute(f'PRAGMA table_info("{tabela}")').fetchall()
    return any(r[1] == coluna for r in rows)


def _garantir_migracoes_rbac(cursor) -> None:
    """Migração idempotente para RBAC (usuarios.role) e isolamento de análises (barragens.owner_id)."""
    if not _coluna_existe(cursor, "usuarios", "role"):
        cursor.execute("ALTER TABLE usuarios ADD COLUMN role TEXT NOT NULL DEFAULT 'user'")

    # Promove administradores legados ou email configurado em INSID_SUPER_ADMIN_EMAIL para super_admin
    super_email = os.environ.get("INSID_SUPER_ADMIN_EMAIL", "admin@insid.com").strip()
    cursor.execute(
        "UPDATE usuarios SET role = 'super_admin', is_admin = 1 WHERE LOWER(email) = LOWER(?)",
        (super_email,),
    )
    cursor.execute(
        "UPDATE usuarios SET role = 'super_admin' WHERE is_admin = 1 AND (role IS NULL OR role = '' OR role = 'user')"
    )
    cursor.execute(
        "UPDATE usuarios SET role = 'user' WHERE role IS NULL OR role NOT IN ('super_admin', 'approver', 'user')"
    )

    if not _coluna_existe(cursor, "barragens", "owner_id"):
        cursor.execute("ALTER TABLE barragens ADD COLUMN owner_id TEXT")
    cursor.execute(
        "UPDATE barragens SET owner_id = CAST(usuario_id AS TEXT) WHERE owner_id IS NULL OR owner_id = ''"
    )

    # Índices de performance para queries frequentes em SQLite / Turso
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_barragens_owner ON barragens(owner_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_anomalias_obs_barragem ON anomalias_observadas(barragem_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_anomalias_mf ON anomalias(modos_falha_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_config_req_status ON config_change_requests(status, proposed_by)")


# ---------- Persistência de Imagens em Base de Dados ----------
def salvar_midia_db(caminho: str, dados: bytes) -> None:
    """Guarda uma imagem em base64 na base de dados para sobreviver a reinícios efémeros."""
    caminho_norm = str(caminho).replace("\\", "/").strip()
    conteudo_b64 = base64.b64encode(dados).decode("ascii")
    with closing(conectar_db()) as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO midia_uploads (caminho, conteudo_b64) VALUES (?, ?)",
            (caminho_norm, conteudo_b64),
        )
        conn.commit()


def carregar_midia_db(caminho: str) -> Optional[bytes]:
    """Recupera os bytes de uma imagem persistida na base de dados."""
    caminho_norm = str(caminho).replace("\\", "/").strip()
    try:
        with closing(conectar_db()) as conn:
            cur = conn.cursor()
            row = cur.execute(
                "SELECT conteudo_b64 FROM midia_uploads WHERE caminho = ?",
                (caminho_norm,),
            ).fetchone()
            if row and row[0]:
                return base64.b64decode(row[0])
    except Exception:
        return None
    return None


def remover_midia_db(caminho: str) -> None:
    """Remove uma imagem persistida da base de dados."""
    caminho_norm = str(caminho).replace("\\", "/").strip()
    try:
        with closing(conectar_db()) as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM midia_uploads WHERE caminho = ?", (caminho_norm,))
            conn.commit()
    except Exception:
        pass


# ---------- Operações de Usuário ----------
def criar_usuario(codigo, nome, email, funcao, organizacao, senha, ativo, role="user"):
    """Cadastra um novo usuário no sistema com perfil RBAC"""
    role_val = role if role in ("super_admin", "approver", "user") else "user"
    is_admin_val = 1 if role_val == "super_admin" else 0
    with closing(conectar_db()) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                """INSERT INTO usuarios (codigo, nome, email, funcao, organizacao, senha_hash, ativo, is_admin, role)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (codigo, nome, email, funcao, organizacao, hash_senha(senha), ativo, is_admin_val, role_val)
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

def verificar_credenciais(email, senha):
    """Verifica se as credenciais são válidas e retorna (codigo, nome, is_admin, role)"""
    with closing(conectar_db()) as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT codigo, nome, is_admin, COALESCE(NULLIF(role, ''), CASE WHEN is_admin = 1 THEN 'super_admin' ELSE 'user' END) as role
        FROM usuarios 
        WHERE email = ? AND senha_hash = ? AND LOWER(ativo) = 'sim'
        """, (email, hash_senha(senha)))
        return cursor.fetchone()

def email_existe(email):
    """Verifica se um email já está cadastrado"""
    with closing(conectar_db()) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM usuarios WHERE email = ?", (email,))
        return cursor.fetchone() is not None

def obter_proximo_codigo_usuario():
    """Obtém o próximo código disponível para novo usuário"""
    with closing(conectar_db()) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(CAST(codigo AS INTEGER)) FROM usuarios")
        max_codigo = cursor.fetchone()[0]
        return str(max_codigo + 1) if max_codigo is not None else "1"
    
# ---------- Operações de Administração de Usuários ----------
def listar_usuarios():
    """Lista todos os usuários cadastrados com respetivo perfil RBAC"""
    with closing(conectar_db()) as conn:
        query = """
        SELECT codigo, nome, email, funcao, organizacao, 
               ativo, is_admin,
               COALESCE(NULLIF(role, ''), CASE WHEN is_admin = 1 THEN 'super_admin' ELSE 'user' END) as role,
               strftime('%d/%m/%Y %H:%M', data_criacao) as data_criacao
        FROM usuarios
        ORDER BY nome
        """
        return pd.read_sql(query, conn)

def atualizar_status_usuario(codigo, ativo):
    """Atualiza o status ativo/inativo de um usuário"""
    with closing(conectar_db()) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE usuarios SET ativo = ? WHERE codigo = ?",
            (ativo, codigo)
        )
        conn.commit()
        return cursor.rowcount > 0

def atualizar_role_usuario(codigo, novo_role):
    """Atualiza o perfil RBAC (super_admin, approver, user), protegendo o último super_admin."""
    if novo_role not in ("super_admin", "approver", "user"):
        return False
    with closing(conectar_db()) as conn:
        cursor = conn.cursor()
        atual = cursor.execute("SELECT role FROM usuarios WHERE codigo = ?", (str(codigo),)).fetchone()
        if not atual:
            return False
        if atual[0] == "super_admin" and novo_role != "super_admin":
            total_supers = cursor.execute(
                "SELECT COUNT(*) FROM usuarios WHERE role = 'super_admin' AND LOWER(ativo) = 'sim'"
            ).fetchone()[0]
            if total_supers <= 1:
                return False
        is_admin_val = 1 if novo_role == "super_admin" else 0
        cursor.execute(
            "UPDATE usuarios SET role = ?, is_admin = ? WHERE codigo = ?",
            (novo_role, is_admin_val, str(codigo))
        )
        conn.commit()
        return cursor.rowcount > 0

def atualizar_admin_usuario(codigo, is_admin):
    """Compatibilidade legada: delega para atualizar_role_usuario"""
    return atualizar_role_usuario(codigo, "super_admin" if is_admin else "user")

def excluir_usuario(codigo):
    """Remove um usuário do sistema"""
    with closing(conectar_db()) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM usuarios WHERE codigo = ?", (codigo,))
        conn.commit()
        return cursor.rowcount > 0

# ---------- Operações de Tipos ----------
def obter_tipos_barragem():
    """Retorna todos os tipos de barragem cadastrados"""
    with closing(conectar_db()) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT *, nome FROM tipos_barragem ORDER BY nome")
        return cursor.fetchall()

def remover_tipo_barragem(tipo_id):
    """Remove um tipo de barragem pelo ID"""
    with closing(conectar_db()) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM tipos_barragem WHERE id = ?", (tipo_id,))
        conn.commit()
        return cursor.rowcount > 0

def cadastrar_barragem(usuario_id, nome, tipo_id, localizacao, altura, comprimento, rel_cordaaltura):
    """Insere uma nova barragem no banco de dados com owner_id explícito"""
    conn = conectar_db()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO barragens 
        (usuario_id, owner_id, nome, tipo_id, localizacao, altura, comprimento, rel_cordaaltura) 
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (usuario_id, str(usuario_id), nome, tipo_id, localizacao, altura, comprimento, rel_cordaaltura)
    )
    conn.commit()
    conn.close()

def listar_barragens(usuario_id=None):
    with closing(conectar_db()) as conn:
        cursor = conn.cursor()
        if usuario_id:
            cursor.execute("""
            SELECT * FROM barragens WHERE usuario_id = ?
            """, (usuario_id,))
        else:
            cursor.execute("""
            SELECT * FROM barragens
            """)
        return cursor.fetchall()


# Tipos de Materiais
def obter_todos_materiais():
    """Retorna todos os materiais cadastrados"""
    conn = conectar_db()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, usuario_id, nome, descricao FROM tipos_materiais")
        return cursor.fetchall()
    finally:
        conn.close()





  # se quiser pode validar se deletou mesmo

def obter_material_por_id(material_id):
    """Obtém material de forma segura"""
    conn = conectar_db()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, nome, descricao 
            FROM tipos_materiais
            WHERE id = ?
        """, (material_id,))
        return cursor.fetchone()  # Retorna (id, nome, descricao) ou None
    except Exception as e:
        print(f"Erro ao obter material: {str(e)}")
        return None
    finally:
        conn.close()


def pesquisar_materiais(termo):
    """Pesquisa materiais por nome ou descrição"""
    conn = None
    try:
        conn = conectar_db()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, nome, descricao 
            FROM tipos_materiais 
            WHERE nome LIKE ? OR descricao LIKE ?
            ORDER BY nome
        """, (f"%{termo}%", f"%{termo}%"))
        
        return cursor.fetchall()
        
    except sqlite3.Error as e:
        print(f"Erro na pesquisa: {str(e)}")
        return []
        
    finally:
        if conn:
            conn.close()

def obter_usuario_id(email):
    """Obtém o ID do usuário a partir do email"""
    with closing(conectar_db()) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT codigo FROM usuarios WHERE email = ?", (email,))
        result = cursor.fetchone()
        return result[0] if result else None

def obter_barragens_usuario(usuario_id):
    """Retorna todas as barragens cadastradas por um usuário"""
    conn = conectar_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, nome, tipo_id, localizacao, altura, comprimento, rel_cordaaltura FROM barragens WHERE usuario_id = ?", (usuario_id,))
    barragens = cursor.fetchall()
    conn.close()
    return barragens

def obter_barragem_analise(usuario_id):
    """Retorna a barragem atualmente em análise pelo usuário, com todos os dados"""
    conn = conectar_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT b.id, b.usuario_id, b.nome, b.tipo_id, b.localizacao, 
               b.altura, b.comprimento, b.rel_cordaaltura, 
               b.em_analise, b.data_criacao
        FROM barragens b
        JOIN usuario_barragem_analise uba ON b.id = uba.barragem_id
        WHERE uba.usuario_id = ?
    """, (usuario_id,))
    barragem = cursor.fetchone()
    conn.close()
    return barragem

def definir_barragem_analise(usuario_id, barragem_id):
    """Define qual barragem está em análise para o usuário"""
    conn = conectar_db()
    cursor = conn.cursor()
    
    # Remove qualquer análise existente
    cursor.execute("DELETE FROM usuario_barragem_analise WHERE usuario_id = ?", (usuario_id,))
    
    # Insere a nova análise
    cursor.execute("INSERT INTO usuario_barragem_analise (usuario_id, barragem_id) VALUES (?, ?)", 
                  (usuario_id, barragem_id))
    
    conn.commit()
    conn.close()

def atualizar_barragem(barragem_id, nome, tipo_id, localizacao, altura, comprimento, rel_cordaaltura):
    """Atualiza os dados de uma barragem existente"""
    conn = conectar_db()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE barragens 
        SET nome = ?, tipo_id = ?, localizacao = ?, altura = ?, comprimento = ?, rel_cordaaltura = ?
        WHERE id = ?
    """, (nome, tipo_id, localizacao, altura, comprimento, rel_cordaaltura, barragem_id))
    conn.commit()
    conn.close()

def excluir_barragem(barragem_id):
    """Remove uma barragem do sistema"""

    conn = conectar_db()
    cursor = conn.cursor()
    
    # Remove da tabela de análise primeiro (se existir)
    cursor.execute("DELETE FROM usuario_barragem_analise WHERE barragem_id = ?", (barragem_id,))
    
        # Remove a barragem
    cursor.execute("DELETE FROM barragens WHERE id = ?", (barragem_id,))
    
    conn.commit()
    conn.close()


# Inicializa o banco de dados
inicializar_bd()