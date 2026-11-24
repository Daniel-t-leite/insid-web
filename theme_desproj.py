"""
Identidade visual coerente com https://www.desproj.com/
Paleta geotécnica/topográfica: terracota (#b8520e), ouro (#d99b26),
fundo areia (#faf8f5) e barra lateral escura (#1a130e).
"""

import streamlit as st


def aplicar_tema_desproj() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Plus+Jakarta+Sans:wght@600;700;800&display=swap');

        :root {
            --brand-primary: #b8520e;
            --brand-primary-dark: #943f08;
            --brand-primary-light: #f6e7dc;
            --brand-gold: #d99b26;
            --earth-950: #1a130e;
            --earth-900: #261c15;
            --earth-800: #3a2b20;
            --earth-200: #e5ddd5;
            --earth-100: #f3eee8;
            --bg-page: #faf8f5;
            --text-main: #231a14;
            --text-muted: #5c4f45;
        }

        html, body, [class*="css"] {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            color: var(--text-main);
        }

        h1, h2, h3, h4 {
            font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
            color: var(--earth-950);
            letter-spacing: -0.015em;
        }

        /* Área principal sóbria */
        .stApp {
            background-color: var(--bg-page);
        }

        /* Barra lateral escura alinhada ao cabeçalho desproj.com */
        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #1a130e 0%, #261c15 100%);
            border-right: 2px solid var(--brand-primary);
        }
        [data-testid="stSidebar"] * {
            color: #f3eee8 !important;
        }
        [data-testid="stSidebar"] hr {
            border-color: rgba(255, 255, 255, 0.14);
        }
        [data-testid="stSidebar"] .stButton > button {
            width: 100%;
            text-align: left;
            justify-content: flex-start;
            background-color: rgba(255, 255, 255, 0.06);
            border: 1px solid rgba(255, 255, 255, 0.14);
            color: #ffffff !important;
            border-radius: 8px;
            font-weight: 500;
            transition: all 0.2s ease;
        }
        [data-testid="stSidebar"] .stButton > button:hover {
            background-color: var(--brand-primary);
            border-color: var(--brand-primary);
            color: #ffffff !important;
        }

        /* Botões principais */
        .stButton > button[kind="primary"],
        .stFormSubmitButton > button {
            background-color: var(--brand-primary) !important;
            color: #ffffff !important;
            border: none !important;
            border-radius: 8px !important;
            font-weight: 600 !important;
        }
        .stButton > button[kind="primary"]:hover,
        .stFormSubmitButton > button:hover {
            background-color: var(--brand-primary-dark) !important;
        }

        /* Cartões, expanders e formulários */
        [data-testid="stForm"],
        [data-testid="stExpander"] {
            background-color: #ffffff;
            border: 1px solid var(--earth-200) !important;
            border-radius: 12px !important;
            box-shadow: 0 2px 10px rgba(35, 26, 20, 0.04);
        }

        /* Badges de perfil e estado */
        .desproj-role-badge {
            display: inline-block;
            padding: 0.3rem 0.7rem;
            border-radius: 999px;
            font-size: 0.78rem;
            font-weight: 700;
            letter-spacing: 0.02em;
            background-color: rgba(217, 155, 38, 0.2);
            border: 1px solid var(--brand-gold);
            color: #f6e7dc !important;
            margin-bottom: 0.5rem;
        }

        .desproj-brand-header {
            padding: 0.4rem 0 0.75rem;
            border-bottom: 1px solid rgba(255, 255, 255, 0.12);
            margin-bottom: 0.75rem;
        }
        .desproj-brand-title {
            font-family: 'Plus Jakarta Sans', sans-serif;
            font-weight: 800;
            font-size: 1.15rem;
            color: #ffffff !important;
            margin: 0;
        }
        .desproj-brand-sub {
            font-size: 0.76rem;
            color: #d99b26 !important;
            margin: 0;
        }

        /* Tabs limpas */
        .stTabs [data-baseweb="tab-list"] {
            gap: 0.5rem;
        }
        .stTabs [aria-selected="true"] {
            color: var(--brand-primary) !important;
            border-bottom-color: var(--brand-primary) !important;
            font-weight: 700;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
