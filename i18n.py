"""
Sistema de Internacionalização (PT / EN) da Plataforma inSID Web — desproj.
Textos revistos sem gralhas ortográficas em português de Portugal e inglês.
"""

from typing import Dict

SUPPORTED_LANGS = ("pt", "en")

TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "pt": {
        "brand_title": "Plataforma inSID",
        "brand_sub": "desproj · Segurança de Barragens",
        "lang_label": "Idioma / Language",
        "role_super_admin": "Usuário Supremo",
        "role_approver": "Aprovador",
        "role_user": "Usuário Normal",
        # Login & Registo
        "tab_login": "Iniciar Sessão",
        "tab_register": "Criar Conta",
        "login_title": "Bem-vindo à Plataforma inSID",
        "login_subtitle": "Diagnóstico integrado de anomalias e modos de falha em barragens de aterro.",
        "email_label": "E-mail",
        "password_label": "Palavra-passe",
        "confirm_password_label": "Confirmar palavra-passe",
        "login_btn": "Entrar",
        "login_welcome": "Bem-vindo, {name}.",
        "login_invalid": "Credenciais inválidas ou conta inativa.",
        "logout_btn": "Sair",
        # Sidebar
        "nav_admin_section": "Administração",
        "nav_manage_users": "Gerir Utilizadores e Perfis",
        "nav_approval_queue": "Fila de Aprovações ({count})",
        "nav_my_proposals": "Minhas Propostas ({count})",
        "nav_analyses_section": "Análises de Barragens",
        "nav_home_all": "Todas as Barragens (Global)",
        "nav_home_mine": "As Minhas Barragens",
        "nav_register_dam": "Registar Nova Barragem",
        "nav_dam_configs": "Configurações das Barragens",
        "nav_dam_types": "Tipos de Barragens",
        "nav_dam_zones": "Zonas das Barragens",
        "nav_materials": "Tipos de Materiais",
        "nav_fm_configs": "Configurações dos Modos de Falha",
        "nav_anomaly_types": "Tipos de Anomalias",
        "nav_fm_categories": "Categorias de Modos de Falha",
        "nav_fm_manage": "Modos de Falha e Regras",
        # Workflow & Badges
        "workflow_user_banner": (
            "**Modo Proposta (Usuário Normal):** Pode criar, editar ou propor a exclusão de configurações globais. "
            "As alterações ficam **Pendentes de Aprovação** e só ficam visíveis para os demais utilizadores após aprovação de um Aprovador ou Usuário Supremo."
        ),
        "workflow_pending_caption": "Existem **{count}** proposta(s) pendente(s) na Fila de Aprovações.",
        "workflow_submitted_pending": (
            "**Proposta #{req_id} registada como Pendente de Aprovação.** "
            "Só será incorporada para os demais utilizadores após aprovação de um Aprovador ou Usuário Supremo."
        ),
        "status_pending": "Pendente",
        "status_approved": "Aprovada e Publicada",
        "status_rejected": "Rejeitada",
        # Fila de Aprovações
        "approvals_title": "Fila de Aprovação de Configurações Globais",
        "approvals_caption": "Reveja, aprove ou rejeite alterações propostas em Configurações das barragens e Configurações dos modos de falha.",
        "approvals_denied": "Acesso permitido apenas para Aprovadores e Usuário Supremo.",
        "approvals_tab_pending": "Pendentes",
        "approvals_tab_approved": "Aprovadas",
        "approvals_tab_rejected": "Rejeitadas",
        "approvals_empty_pending": "Não existem propostas pendentes de aprovação neste momento.",
        "approvals_empty_approved": "Ainda não existem propostas aprovadas.",
        "approvals_empty_rejected": "Não existem propostas rejeitadas.",
        "approvals_review_note": "Nota de revisão (opcional)",
        "approvals_btn_approve": "Aprovar e Incorporar",
        "approvals_btn_reject": "Rejeitar",
        "approvals_approved_ok": "Proposta #{req_id} aprovada e incorporada na plataforma.",
        "approvals_rejected_ok": "Proposta #{req_id} rejeitada.",
        # Minhas Propostas
        "my_proposals_title": "Minhas Propostas de Configuração",
        "my_proposals_caption": "Acompanhe o estado das suas propostas enviadas para aprovação.",
        "my_proposals_empty": "Ainda não submeteu propostas de alteração em configurações globais.",
        # Administração de Utilizadores
        "users_title": "Administração de Utilizadores e Perfis",
        "users_denied": "Apenas o Usuário Supremo pode gerir utilizadores e perfis.",
        "users_status": "Ativo",
        "users_role": "Perfil RBAC",
        "users_update_status": "Guardar Estado",
        "users_update_role": "Guardar Perfil",
        "users_delete": "Excluir",
        "users_role_updated": "Perfil atualizado com sucesso.",
        "users_role_blocked": "Não foi possível alterar o perfil (é obrigatório manter pelo menos um Usuário Supremo ativo).",
        # Análises de Barragens & Isolamento
        "approver_no_analyses": (
            "O perfil **Aprovador** dedica-se à revisão de configurações globais e não tem acesso às análises de barragens dos utilizadores."
        ),
        "go_to_approvals": "Abrir Fila de Aprovações",
        "principal_title_all": "Painel Global de Análises — Sistema inSID",
        "principal_title_mine": "As Minhas Análises de Barragens — Sistema inSID",
        "logged_user_line": "Utilizador: **{name}** · Perfil: **{role}**",
        "dam_in_analysis": "Barragem em Análise",
        "dam_current": "Barragem atualmente selecionada: **{name}**",
        "dam_none_selected": "Nenhuma barragem selecionada para análise.",
        "dam_select_label": "Selecione a barragem para análise:",
        "dam_select_placeholder": "Selecione uma barragem...",
        "dam_save_selection": "Selecionar",
        "dam_empty_cta": "Ainda não tem barragens registadas. Registe a sua primeira barragem para iniciar o diagnóstico inSID.",
        "dam_register_now": "Registar Primeira Barragem",
        "dam_unauthorized": "Não tem permissão para aceder à análise desta barragem.",
        "back_btn": "Voltar",
        # Entidades e ações
        "entity_tipos_barragem": "Tipos de Barragem",
        "entity_tipos_zonas_bar": "Zonas das Barragens",
        "entity_tipos_materiais": "Tipos de Materiais",
        "entity_tipo_anomalia": "Tipos de Anomalias",
        "entity_tipo_modo_falha": "Categorias de Modos de Falha",
        "entity_modos_falha": "Modos de Falha",
        "entity_anomalias": "Regras Anomalia × Modo de Falha",
        "action_create": "Criar",
        "action_update": "Editar",
        "action_delete": "Excluir",
    },
    "en": {
        "brand_title": "inSID Platform",
        "brand_sub": "desproj · Dam Safety",
        "lang_label": "Language / Idioma",
        "role_super_admin": "Super Admin",
        "role_approver": "Approver",
        "role_user": "Standard User",
        # Login & Register
        "tab_login": "Sign In",
        "tab_register": "Create Account",
        "login_title": "Welcome to the inSID Platform",
        "login_subtitle": "Integrated anomaly detection and failure-mode diagnostics for embankment dams.",
        "email_label": "Email",
        "password_label": "Password",
        "confirm_password_label": "Confirm password",
        "login_btn": "Sign In",
        "login_welcome": "Welcome, {name}.",
        "login_invalid": "Invalid credentials or inactive account.",
        "logout_btn": "Sign Out",
        # Sidebar
        "nav_admin_section": "Administration",
        "nav_manage_users": "Manage Users & Roles",
        "nav_approval_queue": "Approval Queue ({count})",
        "nav_my_proposals": "My Proposals ({count})",
        "nav_analyses_section": "Dam Analyses",
        "nav_home_all": "All Dams (Global)",
        "nav_home_mine": "My Dams",
        "nav_register_dam": "Register New Dam",
        "nav_dam_configs": "Dam Configurations",
        "nav_dam_types": "Dam Types",
        "nav_dam_zones": "Dam Zones",
        "nav_materials": "Material Types",
        "nav_fm_configs": "Failure Mode Configurations",
        "nav_anomaly_types": "Anomaly Types",
        "nav_fm_categories": "Failure Mode Categories",
        "nav_fm_manage": "Failure Modes & Rules",
        # Workflow & Badges
        "workflow_user_banner": (
            "**Proposal Mode (Standard User):** You may create, edit, or propose deleting global configurations. "
            "Changes remain **Pending Approval** and only take effect for other users once approved by an Approver or Super Admin."
        ),
        "workflow_pending_caption": "There are **{count}** pending proposal(s) in the Approval Queue.",
        "workflow_submitted_pending": (
            "**Proposal #{req_id} submitted as Pending Approval.** "
            "It will only be published to other users after approval by an Approver or Super Admin."
        ),
        "status_pending": "Pending",
        "status_approved": "Approved & Published",
        "status_rejected": "Rejected",
        # Approval Queue
        "approvals_title": "Global Configuration Approval Queue",
        "approvals_caption": "Review, approve, or reject configuration changes proposed for Dam Configurations and Failure Mode Configurations.",
        "approvals_denied": "Access restricted to Approvers and Super Admin.",
        "approvals_tab_pending": "Pending",
        "approvals_tab_approved": "Approved",
        "approvals_tab_rejected": "Rejected",
        "approvals_empty_pending": "There are no pending proposals to review right now.",
        "approvals_empty_approved": "No approved proposals yet.",
        "approvals_empty_rejected": "No rejected proposals.",
        "approvals_review_note": "Review note (optional)",
        "approvals_btn_approve": "Approve & Publish",
        "approvals_btn_reject": "Reject",
        "approvals_approved_ok": "Proposal #{req_id} approved and published to the platform.",
        "approvals_rejected_ok": "Proposal #{req_id} rejected.",
        # My Proposals
        "my_proposals_title": "My Configuration Proposals",
        "my_proposals_caption": "Track the review status of your proposed global configuration changes.",
        "my_proposals_empty": "You have not submitted any global configuration proposals yet.",
        # User Admin
        "users_title": "User & Role Administration",
        "users_denied": "Only the Super Admin can manage users and roles.",
        "users_status": "Active",
        "users_role": "RBAC Role",
        "users_update_status": "Save Status",
        "users_update_role": "Save Role",
        "users_delete": "Delete",
        "users_role_updated": "Role updated successfully.",
        "users_role_blocked": "Could not update role (at least one active Super Admin must remain).",
        # Dam Analyses & Scoping
        "approver_no_analyses": (
            "The **Approver** role is dedicated to reviewing global configurations and does not have access to users' dam analyses."
        ),
        "go_to_approvals": "Open Approval Queue",
        "principal_title_all": "Global Dam Analyses — inSID System",
        "principal_title_mine": "My Dam Analyses — inSID System",
        "logged_user_line": "User: **{name}** · Role: **{role}**",
        "dam_in_analysis": "Dam Under Analysis",
        "dam_current": "Currently selected dam: **{name}**",
        "dam_none_selected": "No dam selected for analysis.",
        "dam_select_label": "Select a dam to analyze:",
        "dam_select_placeholder": "Select a dam...",
        "dam_save_selection": "Select",
        "dam_empty_cta": "You have no registered dams yet. Register your first dam to start inSID diagnostics.",
        "dam_register_now": "Register First Dam",
        "dam_unauthorized": "You do not have permission to access this dam analysis.",
        "back_btn": "Back",
        # Entities & Actions
        "entity_tipos_barragem": "Dam Types",
        "entity_tipos_zonas_bar": "Dam Zones",
        "entity_tipos_materiais": "Material Types",
        "entity_tipo_anomalia": "Anomaly Types",
        "entity_tipo_modo_falha": "Failure Mode Categories",
        "entity_modos_falha": "Failure Modes",
        "entity_anomalias": "Anomaly × Failure Mode Rules",
        "action_create": "Create",
        "action_update": "Update",
        "action_delete": "Delete",
    },
}


def get_text(key: str, lang: str = "pt", **kwargs) -> str:
    lang_code = lang if lang in SUPPORTED_LANGS else "pt"
    template = TRANSLATIONS[lang_code].get(key) or TRANSLATIONS["pt"].get(key) or key
    return template.format(**kwargs) if kwargs else template
