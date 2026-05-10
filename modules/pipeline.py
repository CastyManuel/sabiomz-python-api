"""
Sabiomz v5 — modules/pipeline.py
Executor do pipeline multi-etapas.
Chamado pela rota POST /pipeline/iniciar do app.py em thread separada.
Actualiza a BD MySQL directamente via pymysql/mysql-connector.
"""
import json
import time
import logging
import requests

log = logging.getLogger(__name__)


# ── Helpers de BD ────────────────────────────────────────────────────────────

def _get_db(cfg: dict):
    """Cria ligação MySQL. Tenta pymysql, depois mysql-connector."""
    try:
        import pymysql
        return pymysql.connect(
            host=cfg.get("db_host", "localhost"),
            db=cfg.get("db_name", "sabiomz"),
            user=cfg.get("db_user", "root"),
            password=cfg.get("db_pass", ""),
            charset="utf8mb4",
            autocommit=True,
        )
    except ImportError:
        pass

    try:
        import mysql.connector
        return mysql.connector.connect(
            host=cfg.get("db_host", "localhost"),
            database=cfg.get("db_name", "sabiomz"),
            user=cfg.get("db_user", "root"),
            password=cfg.get("db_pass", ""),
            autocommit=True,
        )
    except ImportError:
        log.warning("Nem pymysql nem mysql-connector estão disponíveis. BD desactivada.")
        return None


def _exec(conn, sql: str, params: tuple = ()):
    if conn is None:
        return
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
    except Exception as e:
        log.error(f"BD error: {e}")


def _update_job(conn, token: str, status: str, pct: int, etapa: str, resultado: str | None = None):
    if conn is None:
        return
    if resultado is not None:
        _exec(conn,
              "UPDATE sse_jobs SET status=%s,progresso=%s,etapa_atual=%s,resultado=%s,concluido_em=NOW() WHERE token=%s",
              (status, pct, etapa, resultado, token))
    else:
        _exec(conn,
              "UPDATE sse_jobs SET status=%s,progresso=%s,etapa_atual=%s WHERE token=%s",
              (status, pct, etapa, token))


def _salvar_mensagem(conn, conv_id: int, texto: str):
    if conn is None:
        return
    _exec(conn,
          "INSERT INTO mensagens (conversa_id,papel,conteudo) VALUES (%s,'assistant',%s)",
          (conv_id, texto))


# ── Chamada à IA (OpenRouter) ────────────────────────────────────────────────

def _call_ai(ai_key: str, ai_model: str, ai_endpoint: str,
             system: str, user_msg: str, max_tokens: int = 1200, temp: float = 0.7) -> str:
    try:
        resp = requests.post(
            ai_endpoint or "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {ai_key}",
                "HTTP-Referer": "https://sabiomz.co.mz",
                "X-Title": "Sabiomz v5",
            },
            json={
                "model": ai_model or "openai/gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user",   "content": user_msg},
                ],
                "max_tokens": max_tokens,
                "temperature": temp,
            },
            timeout=120,
        )
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"].strip()
        log.error(f"AI error {resp.status_code}: {resp.text[:200]}")
        return ""
    except Exception as e:
        log.error(f"AI call failed: {e}")
        return ""


# ── Geração de documentos ────────────────────────────────────────────────────

def _gerar_documentos(texto: str, titulo: str, job_id: str, out_dir: str) -> dict:
    from modules.pdf_gen import gerar_pdf, gerar_docx
    import os

    os.makedirs(out_dir, exist_ok=True)
    base = os.path.join(out_dir, f"trabalho_{job_id}")
    docs = {}

    pdf_result = gerar_pdf(texto, base + ".pdf", titulo)
    docs.update(pdf_result)

    docx_result = gerar_docx(texto, base + ".docx", titulo)
    docs.update(docx_result)

    return docs


# ── Pipeline principal ───────────────────────────────────────────────────────

def executar_pipeline(data: dict):
    """
    Executa o pipeline completo.
    Chamado em thread separada pelo Flask.

    data keys:
      token, conv_id, user_id, msg, plano, intencao,
      doc_texto (texto já extraído do documento, se houver),
      ai_key, ai_model, ai_endpoint,
      db_host, db_name, db_user, db_pass,
      output_dir (pasta para PDF/DOCX gerados)
    """
    token    = data.get("token", "")
    conv_id  = int(data.get("conv_id", 0))
    msg      = data.get("msg", "")
    plano    = data.get("plano", "free")
    intencao = data.get("intencao", "pergunta_simples")
    doc_txt  = data.get("doc_texto", "")
    ai_key   = data.get("ai_key", "")
    ai_model = data.get("ai_model", "openai/gpt-4o-mini")
    ai_ep    = data.get("ai_endpoint", "https://openrouter.ai/api/v1/chat/completions")
    out_dir  = data.get("output_dir", "/tmp/sabiomz_generated")

    max_tok = {"sabioblack": 2500, "sabiopro": 1500}.get(plano, 400)

    conn = _get_db(data)

    sys_base = (
        "És o Sabio, professor virtual de Moçambique (8ª-12ª classe). "
        "Responde em Português académico formal. "
        "Usa exemplos moçambicanos. "
        f"Plano activo: {plano}."
    )

    try:
        # ── TRABALHO / PROJECTO / RELATÓRIO / MONOGRAFIA ─────────────────────
        if intencao in ("trabalho", "projecto", "relatorio", "monografia"):
            _update_job(conn, token, "processando", 5, "🔎 Pesquisando conteúdo...")
            num_caps = {"sabioblack": 6, "sabiopro": 3}.get(plano, 1)

            _update_job(conn, token, "processando", 10, "🧠 Criando estrutura...")
            indice = _call_ai(ai_key, ai_model, ai_ep, sys_base,
                f"Cria índice académico para {intencao} sobre '{msg}' com {num_caps} capítulos. Formato numérico com subtítulos.",
                400, 0.5)

            titulos = _extrair_titulos(indice, num_caps)

            _update_job(conn, token, "processando", 18, "✍️ Gerando introdução...")
            intro = _call_ai(ai_key, ai_model, ai_ep, sys_base,
                f"Escreve introdução académica MUITO EXTENSA para {intencao} sobre '{msg}'. Mín 12 parágrafos. Contextualização em Moçambique.",
                min(int(max_tok * 1.2), 2500), 0.62)

            obj = _call_ai(ai_key, ai_model, ai_ep, sys_base,
                f"Para {intencao} sobre '{msg}': escreve Objectivo Geral e Objectivos Específicos (4-6).",
                400, 0.5)

            caps = {}
            for i, tit in enumerate(titulos):
                n = i + 1
                pct = 22 + int((n / num_caps) * 45)
                _update_job(conn, token, "processando", pct, f"📚 Gerando Capítulo {n} de {num_caps}...")
                cap = _call_ai(ai_key, ai_model, ai_ep, sys_base,
                    f"Escreve Capítulo {n} do {intencao} sobre '{msg}'.\nTítulo: '{tit}'\nSubtítulos, exemplos moçambicanos, mín 600 palavras.",
                    min(max_tok, 2000), 0.65)
                caps[n] = {"titulo": tit, "conteudo": cap}
                time.sleep(0.2)

            _update_job(conn, token, "processando", 70, "📖 Gerando conclusão...")
            resumo = " | ".join(c["conteudo"][:80] + "..." for c in caps.values())
            conclusao = _call_ai(ai_key, ai_model, ai_ep, sys_base,
                f"Conclusão para {intencao} sobre '{msg}'. Resumo: {resumo}. Mín 8 parágrafos.",
                800, 0.62)

            _update_job(conn, token, "processando", 80, "📑 Referências...")
            refs = _call_ai(ai_key, ai_model, ai_ep, sys_base,
                f"8-12 referências ABNT para {intencao} sobre '{msg}'. 2 autores moçambicanos.",
                400, 0.4)

            # Unir texto
            texto = f"# {msg.upper()}\n\n"
            texto += f"## ÍNDICE\n\n{indice}\n\n---\n\n"
            texto += f"{obj}\n\n---\n\n"
            texto += f"## 1. INTRODUÇÃO\n\n{intro}\n\n"
            for n, c in caps.items():
                texto += f"\n## {n + 1}. {c['titulo'].upper()}\n\n{c['conteudo']}\n\n"
            texto += f"\n## {len(caps) + 2}. CONCLUSÃO\n\n{conclusao}\n\n"
            texto += f"\n## {len(caps) + 3}. REFERÊNCIAS BIBLIOGRÁFICAS\n\n{refs}\n"

            _update_job(conn, token, "processando", 88, "📄 Gerando PDF e DOCX...")
            docs = _gerar_documentos(texto, msg, token[:12], out_dir)

            resposta = (
                f"## ✅ {intencao.capitalize()} sobre **{msg}** concluído!\n\n"
                f"**Estrutura:** Introdução ✓ | {num_caps} Capítulos ✓ | Conclusão ✓ | Referências ✓\n\n"
            )
            if docs.get("pdf"):
                resposta += f"📄 PDF gerado: `{docs['pdf']}`\n"
            if docs.get("docx"):
                resposta += f"📘 Word gerado: `{docs['docx']}`\n"
            if docs.get("html"):
                resposta += f"🌐 HTML gerado: `{docs['html']}`\n"
            resposta += f"\n---\n\n### Preview da Introdução\n\n{intro[:500]}..."

            _salvar_mensagem(conn, conv_id, resposta)
            resultado = json.dumps({"resposta": resposta, "texto_completo": texto,
                                    "pdf": docs.get("pdf"), "docx": docs.get("docx"),
                                    "html": docs.get("html")}, ensure_ascii=False)
            _update_job(conn, token, "completo", 100, "✅ Trabalho completo!", resultado)

        # ── EXAME ────────────────────────────────────────────────────────────
        elif intencao == "exame":
            _update_job(conn, token, "processando", 15, "🔎 Lendo exame...")
            ctx_doc = f"\n\n--- EXAME ---\n{doc_txt}" if doc_txt else ""
            _update_job(conn, token, "processando", 40, "🧠 Analisando perguntas...")
            sys_exame = (sys_base +
                " Resolve cada pergunta passo a passo."
                " Formato: **Pergunta N:** → **Resolução:** → **Resposta Final:**")
            _update_job(conn, token, "processando", 65, "✍️ Resolvendo...")
            resp = _call_ai(ai_key, ai_model, ai_ep, sys_exame, msg + ctx_doc, max_tok, 0.2)
            if not resp:
                resp = "❌ Não foi possível resolver. Verifica a API Key."
            _salvar_mensagem(conn, conv_id, resp)
            _update_job(conn, token, "completo", 100, "✅ Exame resolvido!",
                        json.dumps({"resposta": resp}, ensure_ascii=False))

        # ── ANÁLISE DOCUMENTO ─────────────────────────────────────────────────
        elif intencao == "analise_documento":
            _update_job(conn, token, "processando", 15, "📖 Lendo documento...")
            ctx = f"\n\n--- DOCUMENTO ---\n{doc_txt[:8000]}" if doc_txt else ""
            _update_job(conn, token, "processando", 50, "🧠 Analisando...")
            resp = _call_ai(ai_key, ai_model, ai_ep,
                            sys_base + " Analisa o documento e responde ao pedido com profundidade.",
                            msg + ctx, max_tok, 0.6)
            if not resp:
                resp = "❌ Erro na análise do documento."
            _salvar_mensagem(conn, conv_id, resp)
            _update_job(conn, token, "completo", 100, "✅ Análise completa!",
                        json.dumps({"resposta": resp}, ensure_ascii=False))

        # ── MATEMÁTICA ───────────────────────────────────────────────────────
        elif intencao == "matematica":
            from modules.math_solver import resolver_matematica
            _update_job(conn, token, "processando", 20, "🧮 Calculando...")
            sym = resolver_matematica(msg)
            extra = f"\n\nCALCULO VERIFICADO:\n{json.dumps(sym, ensure_ascii=False)}" if sym and "erro" not in sym else ""
            sys_math = (sys_base +
                " Resolve matemática passo a passo."
                " Formato: ## Dados | ## Objectivo | ## Fórmula | ## Resolução | ## Resultado | ## Verificação")
            _update_job(conn, token, "processando", 60, "✍️ Explicando...")
            resp = _call_ai(ai_key, ai_model, ai_ep, sys_math, msg + extra, max_tok, 0.15)
            if not resp:
                resp = sym.get("formatado", "❌ Não foi possível resolver.")
            _salvar_mensagem(conn, conv_id, resp)
            _update_job(conn, token, "completo", 100, "✅ Cálculo completo!",
                        json.dumps({"resposta": resp}, ensure_ascii=False))

        # ── PESQUISA / DEFAULT ────────────────────────────────────────────────
        else:
            _update_job(conn, token, "processando", 30, "✍️ A responder...")
            resp = _call_ai(ai_key, ai_model, ai_ep, sys_base, msg, max_tok, 0.7)
            if not resp:
                resp = "Não consigo ligar à IA. Verifica a chave de API."
            _salvar_mensagem(conn, conv_id, resp)
            _update_job(conn, token, "completo", 100, "✅ Resposta gerada!",
                        json.dumps({"resposta": resp}, ensure_ascii=False))

    except Exception as e:
        log.exception(f"Pipeline error: {e}")
        _update_job(conn, token, "erro", 0, f"❌ Erro: {e}")
        _salvar_mensagem(conn, conv_id, f"❌ Erro interno no pipeline: {e}")

    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


# ── Helpers ──────────────────────────────────────────────────────────────────

def _extrair_titulos(indice: str, n: int) -> list:
    import re
    titulos = []
    for linha in indice.split("\n"):
        linha = linha.strip()
        if re.match(r"^\d+\.\s+[A-ZÁÉÍÓÚÀÂÊÔÃÕÇ]", linha):
            m = re.match(r"^\d+\.\s+(.+?)(?:\s*\.{2,}|\s*$)", linha)
            if m:
                tit = m.group(1).strip()
                if not re.match(r"^(INTRODUÇÃO|CONCLUSÃO|REFERÊNCIAS|ÍNDICE)", tit, re.I):
                    titulos.append(tit)
        if len(titulos) >= n:
            break
    genericos = ["Fundamentação Teórica", "Metodologia", "Análise e Resultados",
                 "Estudo de Caso", "Perspectivas", "Considerações Finais"]
    while len(titulos) < n:
        titulos.append(genericos[len(titulos)] if len(titulos) < len(genericos) else f"Capítulo {len(titulos)+1}")
    return titulos[:n]
