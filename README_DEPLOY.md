# Deploy da Plataforma inSID no Streamlit Community Cloud (\$0/mês)

Guia objetivo para colocar a aplicação **inSID Platform** em produção gratuitamente e integrá-la no site **https://www.desproj.com/**.

---

## 1. Publicar no Streamlit Community Cloud (3 cliques)

> **Pré-requisito:** Fazer `git push` deste repositório para `https://github.com/Daniel-t-leite/insid-web`.

1. **Aceder e autenticar:** Abra https://share.streamlit.io/ e inicie sessão com a sua conta **GitHub** (`Daniel-t-leite`).
2. **Criar aplicação:** Clique em **Create app** → **Yup, I have an app** e preencha:
   - **Repository:** `Daniel-t-leite/insid-web`
   - **Branch:** `main`
   - **Main file path:** `app.py`
   - **App URL (sugestão):** `insid-web` *(ficará `https://insid-web.streamlit.app`)*
3. **Publicar:** Clique em **Deploy!** — o Streamlit instala automaticamente `requirements.txt` e aplica `.streamlit/config.toml`.

---

## 2. Nota Importante sobre Persistência de Dados (`inSID.db` e `uploads/`)

- A aplicação inclui a base de dados pré-populada `inSID.db` e as imagens em `uploads/modos_falha/` versionadas no repositório, pelo que arranca imediatamente funcional com os 14 modos de falha e exemplos.
- **Limitação do plano gratuito (\$0/mês):** O sistema de ficheiros do Streamlit Community Cloud é **efémero**. Novos registos criados em execução (novas barragens, anomalias observadas ou novas imagens carregadas) persistem enquanto o contentor estiver ativo, mas são **repostos para o estado do GitHub** quando a aplicação reinicia ou após um novo deploy.
- **Evolução recomendada para produção multi-utilizador (opcional, também \$0/mês):** Migrar `db.py` para uma base de dados SQLite/Postgres gerida na nuvem (ex.: **Turso/libSQL**, **Neon** ou **Supabase**), guardando as credenciais em *Streamlit Secrets* (`st.secrets`).

---

## 3. Incorporar ou Vincular em `https://www.desproj.com/`

Cole o bloco HTML abaixo na página `insid.html` (ou numa nova secção de `projetos.html`), substituindo `https://insid-web.streamlit.app` pelo URL final da sua app caso escolha outro nome:

```html
<section class="insid-embed-section" style="margin: 2.5rem 0;">
  <div style="display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 1rem; margin-bottom: 1rem;">
    <div>
      <h3 style="margin: 0;">Plataforma Interativa inSID (Demonstração Online)</h3>
      <p style="margin: 0.25rem 0 0; opacity: 0.85;">
        Explore a classificação de modos de falha em barragens de aterro diretamente no navegador.
      </p>
    </div>
    <a href="https://insid-web.streamlit.app"
       target="_blank"
       rel="noopener noreferrer"
       class="btn btn--primary">
      Abrir Plataforma em Nova Aba ↗
    </a>
  </div>

  <div style="position: relative; width: 100%; min-height: 760px; border: 1px solid #d9d0c5; border-radius: 12px; overflow: hidden; background: #faf8f5;">
    <iframe
      src="https://insid-web.streamlit.app/?embed=true"
      title="Plataforma Interativa inSID — desproj"
      style="width: 100%; height: 760px; border: 0; display: block;"
      loading="lazy"
      allow="clipboard-read; clipboard-write"
      referrerpolicy="strict-origin-when-cross-origin">
    </iframe>
  </div>

  <noscript>
    <p style="margin-top: 1rem;">
      O seu navegador não suporta incorporação.
      <a href="https://insid-web.streamlit.app" target="_blank" rel="noopener noreferrer">
        Aceda diretamente à Plataforma inSID aqui →
      </a>
    </p>
  </noscript>
</section>
```
