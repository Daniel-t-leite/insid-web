"""
Testes automatizados de RBAC, isolamento de análises de barragens,
fluxo de aprovação de configurações globais e paridade PT/EN no insid-web.
"""

import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import db
import i18n
import rbac


class TestInsidRbacAndWorkflow(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "test_insid.db"

        # Garantir ambiente 100% SQLite temporário (nunca tocar em Turso nem no inSID.db real)
        self._orig_db_path = db.DB_PATH
        self._orig_usando_turso = db.usando_turso
        db.DB_PATH = self.db_path
        db.usando_turso = lambda: False

        # Ativar foreign keys em todas as ligações de teste
        self._orig_conectar = db.conectar_db

        def _conectar_fk():
            conn = sqlite3.connect(str(self.db_path))
            conn.execute("PRAGMA foreign_keys = ON")
            return conn

        db.conectar_db = _conectar_fk
        rbac.conectar_db = _conectar_fk

        db.inicializar_bd()

        # Criar utilizadores de teste para os 3 perfis (códigos numéricos como no sistema real)
        db.criar_usuario("1001", "Supremo", "supremo@insid.com", "Admin", "desproj", "secret123", "sim", role=rbac.ROLE_SUPER_ADMIN)
        db.criar_usuario("1002", "Aprovador", "aprovador@insid.com", "Revisor", "desproj", "secret123", "sim", role=rbac.ROLE_APPROVER)
        db.criar_usuario("1003", "Engenheiro A", "usera@insid.com", "Eng.", "Org A", "secret123", "sim", role=rbac.ROLE_USER)
        db.criar_usuario("1004", "Engenheiro B", "userb@insid.com", "Eng.", "Org B", "secret123", "sim", role=rbac.ROLE_USER)

        # Criar tipo de barragem base para associar barragens
        conn = db.conectar_db()
        try:
            cur = conn.cursor()
            cur.execute("INSERT INTO tipos_barragem (usuario_id, nome, descricao) VALUES (1, 'Aterro Zonado', 'Barragem de aterro zonado')")
            self.tipo_barragem_id = cur.lastrowid
            cur.execute("INSERT INTO tipo_modo_falha (usuario_id, nome, descricao) VALUES (1, 'Erosão Interna', 'Categoria base')")
            self.tipo_mf_id = cur.lastrowid
            cur.execute("INSERT INTO tipos_zonas_bar (nome, descricao) VALUES ('Núcleo', 'Zona central')")
            self.zona_id = cur.lastrowid
            cur.execute("INSERT INTO tipos_materiais (usuario_id, nome, descricao) VALUES (1, 'Argila', 'Material argiloso')")
            self.material_id = cur.lastrowid
            cur.execute("INSERT INTO tipo_anomalia (usuario_id, nome, descricao) VALUES (1, 'Fissuração', 'Fissuras no coroamento')")
            self.tipo_anomalia_id = cur.lastrowid
            conn.commit()
        finally:
            conn.close()

        # Cadastrar barragens para User A e User B
        db.cadastrar_barragem("1003", "Barragem Alfa", self.tipo_barragem_id, "Norte", 45.0, 320.0, 7.1)
        db.cadastrar_barragem("1004", "Barragem Beta", self.tipo_barragem_id, "Sul", 60.0, 410.0, 6.8)

        conn = db.conectar_db()
        try:
            cur = conn.cursor()
            cur.execute("SELECT id FROM barragens WHERE nome = 'Barragem Alfa'")
            self.barragem_a_id = cur.fetchone()[0]
            cur.execute("SELECT id FROM barragens WHERE nome = 'Barragem Beta'")
            self.barragem_b_id = cur.fetchone()[0]
        finally:
            conn.close()

    def tearDown(self):
        db.DB_PATH = self._orig_db_path
        db.usando_turso = self._orig_usando_turso
        db.conectar_db = self._orig_conectar
        rbac.conectar_db = self._orig_conectar
        self.tmpdir.cleanup()

    def test_01_credenciais_e_roles(self):
        res_sup = db.verificar_credenciais("supremo@insid.com", "secret123")
        self.assertIsNotNone(res_sup)
        self.assertEqual(res_sup[3], rbac.ROLE_SUPER_ADMIN)
        self.assertEqual(res_sup[2], 1)

        res_app = db.verificar_credenciais("aprovador@insid.com", "secret123")
        self.assertEqual(res_app[3], rbac.ROLE_APPROVER)
        self.assertEqual(res_app[2], 0)

        res_usr = db.verificar_credenciais("usera@insid.com", "secret123")
        self.assertEqual(res_usr[3], rbac.ROLE_USER)

        # Proteção do último super_admin ativo:
        # 1001 pode ser rebaixado porque admin@insid.com (0001) ainda é super_admin,
        # mas tentar rebaixar 0001 depois disso tem de ser bloqueado!
        self.assertTrue(rbac.alterar_role_usuario_seguro(rbac.ROLE_SUPER_ADMIN, "1001", rbac.ROLE_USER))
        self.assertFalse(rbac.alterar_role_usuario_seguro(rbac.ROLE_SUPER_ADMIN, "0001", rbac.ROLE_USER))

        # Apenas super_admin pode gerir utilizadores
        with self.assertRaises(PermissionError):
            rbac.alterar_role_usuario_seguro(rbac.ROLE_APPROVER, "1003", rbac.ROLE_APPROVER)
        with self.assertRaises(PermissionError):
            rbac.alterar_role_usuario_seguro(rbac.ROLE_USER, "1003", rbac.ROLE_SUPER_ADMIN)

    def test_02_isolamento_analises_barragens(self):
        # User A vê apenas Barragem Alfa
        barragens_a = rbac.listar_barragens_escopo(rbac.ROLE_USER, "1003")
        self.assertEqual([b[1] for b in barragens_a], ["Barragem Alfa"])
        self.assertIsNotNone(rbac.obter_barragem_autorizada(rbac.ROLE_USER, "1003", self.barragem_a_id))
        self.assertIsNone(rbac.obter_barragem_autorizada(rbac.ROLE_USER, "1003", self.barragem_b_id))

        # User A bloqueado ao tentar selecionar/editar/excluir barragem do User B
        with self.assertRaises(PermissionError):
            rbac.definir_barragem_analise_escopo(rbac.ROLE_USER, "1003", self.barragem_b_id)
        with self.assertRaises(PermissionError):
            rbac.atualizar_barragem_escopo(rbac.ROLE_USER, "1003", self.barragem_b_id, "Hack", self.tipo_barragem_id, "X", 10, 20, 2)
        with self.assertRaises(PermissionError):
            rbac.excluir_barragem_escopo(rbac.ROLE_USER, "1003", self.barragem_b_id)

        # Aprovador NÃO vê nem acede a nenhuma análise de barragem
        self.assertFalse(rbac.can_access_dam_analyses(rbac.ROLE_APPROVER))
        self.assertEqual(rbac.listar_barragens_escopo(rbac.ROLE_APPROVER, "1002"), [])
        self.assertIsNone(rbac.obter_barragem_autorizada(rbac.ROLE_APPROVER, "1002", self.barragem_a_id))
        self.assertIsNone(rbac.obter_barragem_analise_escopo(rbac.ROLE_APPROVER, "1002"))
        with self.assertRaises(PermissionError):
            rbac.definir_barragem_analise_escopo(rbac.ROLE_APPROVER, "1002", self.barragem_a_id)

        # Super Admin vê e acede a TODAS as barragens
        barragens_sup = rbac.listar_barragens_escopo(rbac.ROLE_SUPER_ADMIN, "1001")
        self.assertEqual({b[1] for b in barragens_sup}, {"Barragem Alfa", "Barragem Beta"})
        self.assertIsNotNone(rbac.obter_barragem_autorizada(rbac.ROLE_SUPER_ADMIN, "1001", self.barragem_b_id))
        self.assertTrue(rbac.definir_barragem_analise_escopo(rbac.ROLE_SUPER_ADMIN, "1001", self.barragem_b_id))
        analise_sup = rbac.obter_barragem_analise_escopo(rbac.ROLE_SUPER_ADMIN, "1001")
        self.assertIsNotNone(analise_sup)
        self.assertEqual(analise_sup[0], self.barragem_b_id)

    def test_03_fluxo_aprovacao_configuracoes_barragens(self):
        # User normal submete criação de novo tipo de barragem -> fica PENDING sem alterar tabela global
        res = rbac.submeter_alteracao_configuracao(
            role=rbac.ROLE_USER,
            user_id="1003",
            user_name="Engenheiro A",
            entity_type="tipos_barragem",
            action="create",
            payload={"nome": "Enrocamento CFRD", "descricao": "Face de betão", "referencia_tecnica": "ICOLD", "image_path": None},
        )
        self.assertEqual(res["status"], "pending")
        req_id = res["request_id"]
        self.assertEqual(rbac.contar_propostas_pendentes(), 1)
        self.assertEqual(len(rbac.listar_propostas_configuracao(rbac.ROLE_USER, "1003", status_filter="pending")), 1)
        self.assertEqual(len(rbac.listar_propostas_configuracao(rbac.ROLE_USER, "1004", status_filter="pending")), 0)

        # Confirmar que ainda NÃO existe na tabela global
        conn = db.conectar_db()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM tipos_barragem WHERE nome = 'Enrocamento CFRD'")
            self.assertEqual(cur.fetchone()[0], 0)
        finally:
            conn.close()

        # User normal não pode aprovar nem rejeitar
        with self.assertRaises(PermissionError):
            rbac.aprovar_proposta_configuracao(req_id, "1003", rbac.ROLE_USER)
        with self.assertRaises(PermissionError):
            rbac.rejeitar_proposta_configuracao(req_id, "1003", rbac.ROLE_USER)

        # Aprovador aprova -> passa a existir globalmente
        res_ok = rbac.aprovar_proposta_configuracao(req_id, "1002", rbac.ROLE_APPROVER, "Validado tecnicamente")
        self.assertEqual(res_ok["status"], "approved")
        self.assertEqual(rbac.contar_propostas_pendentes(), 0)

        conn = db.conectar_db()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM tipos_barragem WHERE nome = 'Enrocamento CFRD'")
            self.assertEqual(cur.fetchone()[0], 1)
        finally:
            conn.close()

    def test_04_fluxo_aprovacao_e_rejeicao_modos_falha(self):
        # User normal propõe novo modo de falha -> pending
        res_mf = rbac.submeter_alteracao_configuracao(
            role=rbac.ROLE_USER,
            user_id="1003",
            user_name="Engenheiro A",
            entity_type="modos_falha",
            action="create",
            payload={
                "nome": "Piping no Núcleo",
                "id_tipo_modo_falha": self.tipo_mf_id,
                "descricao": "Erosão interna regressiva",
                "image_path": None,
                "tipos_barragem_ids": [self.tipo_barragem_id],
            },
        )
        self.assertEqual(res_mf["status"], "pending")

        # User normal propõe zona inválida que será rejeitada
        res_rej = rbac.submeter_alteracao_configuracao(
            role=rbac.ROLE_USER,
            user_id="1003",
            user_name="Engenheiro A",
            entity_type="tipos_zonas_bar",
            action="create",
            payload={"nome": "Zona Teste Incorreta", "descricao": "Não aprovar"},
        )
        self.assertEqual(res_rej["status"], "pending")

        # Aprovador aprova modo de falha e rejeita zona incorreta
        self.assertEqual(rbac.aprovar_proposta_configuracao(res_mf["request_id"], "1002", rbac.ROLE_APPROVER)["status"], "approved")
        self.assertEqual(rbac.rejeitar_proposta_configuracao(res_rej["request_id"], "1002", rbac.ROLE_APPROVER, "Fora da taxonomia")["status"], "rejected")

        conn = db.conectar_db()
        try:
            cur = conn.cursor()
            cur.execute("SELECT id FROM modos_falha WHERE nome = 'Piping no Núcleo'")
            mf_row = cur.fetchone()
            self.assertIsNotNone(mf_row)
            cur.execute("SELECT COUNT(*) FROM tipos_zonas_bar WHERE nome = 'Zona Teste Incorreta'")
            self.assertEqual(cur.fetchone()[0], 0)
        finally:
            conn.close()

        # Super Admin aplica diretamente (sem staging)
        res_direct = rbac.submeter_alteracao_configuracao(
            role=rbac.ROLE_SUPER_ADMIN,
            user_id="1001",
            user_name="Supremo",
            entity_type="anomalias",
            action="create",
            payload={
                "modos_falha_id": mf_row[0],
                "tipo_anomalia_id": self.tipo_anomalia_id,
                "gravidade": 4.0,
                "peso": 3.5,
                "zonas_ids": [self.zona_id],
                "materiais_ids": [self.material_id],
            },
        )
        self.assertEqual(res_direct["status"], "applied")

    def test_05_i18n_paridade_pt_en_e_ortografia(self):
        pt_keys = set(i18n.TRANSLATIONS["pt"].keys())
        en_keys = set(i18n.TRANSLATIONS["en"].keys())
        self.assertEqual(pt_keys, en_keys, f"Chaves divergentes: PT-EN={pt_keys - en_keys}, EN-PT={en_keys - pt_keys}")

        for lang in i18n.SUPPORTED_LANGS:
            for k, val in i18n.TRANSLATIONS[lang].items():
                self.assertTrue(isinstance(val, str) and val.strip(), f"Tradução vazia em {lang}.{k}")

        # Garantir que as gralhas antigas conhecidas foram eliminadas de app.py
        app_text = (ROOT_DIR / "app.py").read_text(encoding="utf-8")
        self.assertNotIn("⚙️Configurações", app_text)
        self.assertNotIn("Barragem excluida", app_text)


if __name__ == "__main__":
    unittest.main()
