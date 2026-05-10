#!/usr/bin/env python3
"""
Sabiomz v3 — Python API Server (Flask)
Substitui o worker CLI. Funciona em Hostinger, cPanel, VPS, etc.

DEPLOY:
  pip install flask requests pdfplumber PyPDF2 python-docx reportlab sympy
  python app.py                          # desenvolvimento
  gunicorn -w 2 -b 0.0.0.0:5000 app:app # produção

HOSTINGER (Python App):
  - Entry point: app.py
  - Port: 5000 (ou a que o painel indicar)
"""

from flask import Flask, request, jsonify
import threading
import logging
import os

# Módulos internos
from modules.pipeline      import executar_pipeline
from modules.document      import ler_documento
from modules.pdf_gen       import gerar_pdf, gerar_docx
from modules.math_solver   import resolver_matematica
from modules.pdf_search    import pesquisar_livros

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger(__name__)

app = Flask(__name__)

# ── Chave interna de segurança (deve ser igual ao config.php) ──
API_SECRET = os.environ.get('SABIO_SECRET', 'sabiomz_secret_2025')


def verificar_secret():
    """Verifica o header de autenticação interno."""
    return request.headers.get('X-Sabio-Secret') == API_SECRET


# ────────────────────────────────────────────────────────────────
# ROTA 1: Health check
# ────────────────────────────────────────────────────────────────
@app.route('/health', methods=['GET'])
def health():
    return jsonify({'ok': True, 'versao': 'v3', 'servico': 'Sabiomz Python API'})


# ────────────────────────────────────────────────────────────────
# ROTA 2: Iniciar pipeline em background
# POST /pipeline/iniciar
# Body: {tarefa_id, conv_id, user_id, msg, plano, intencao,
#        doc_texto, ai_key, ai_model, ai_endpoint, db_*}
# ────────────────────────────────────────────────────────────────
@app.route('/pipeline/iniciar', methods=['POST'])
def pipeline_iniciar():
    if not verificar_secret():
        return jsonify({'error': 'Não autorizado'}), 401

    data = request.get_json(force=True) or {}
    required = ['tarefa_id', 'conv_id', 'user_id', 'msg', 'plano', 'intencao']
    for f in required:
        if f not in data:
            return jsonify({'error': f'Campo obrigatório: {f}'}), 400

    # Lança numa thread separada (não bloqueia o request)
    t = threading.Thread(target=executar_pipeline, args=(data,), daemon=True)
    t.start()

    log.info(f"Pipeline iniciado: tarefa={data['tarefa_id']} tipo={data['intencao']}")
    return jsonify({'ok': True, 'tarefa_id': data['tarefa_id'], 'msg': 'Pipeline a executar...'})


# ────────────────────────────────────────────────────────────────
# ROTA 3: Ler e extrair texto de documento
# POST /documento/ler
# Body: {ficheiro_path} ou multipart file
# ────────────────────────────────────────────────────────────────
@app.route('/documento/ler', methods=['POST'])
def documento_ler():
    if not verificar_secret():
        return jsonify({'error': 'Não autorizado'}), 401

    # Upload directo de ficheiro
    if 'ficheiro' in request.files:
        f = request.files['ficheiro']
        import tempfile, os
        ext  = os.path.splitext(f.filename)[1].lower()
        tmp  = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
        f.save(tmp.name)
        resultado = ler_documento(tmp.name)
        os.unlink(tmp.name)
        return jsonify(resultado)

    # Caminho no servidor
    data = request.get_json(force=True) or {}
    path = data.get('ficheiro_path', '')
    if not path or not os.path.exists(path):
        return jsonify({'error': 'Ficheiro não encontrado'}), 404

    return jsonify(ler_documento(path))


# ────────────────────────────────────────────────────────────────
# ROTA 4: Gerar PDF profissional
# POST /documento/pdf
# Body: {texto, titulo, output_path}
# ────────────────────────────────────────────────────────────────
@app.route('/documento/pdf', methods=['POST'])
def documento_pdf():
    if not verificar_secret():
        return jsonify({'error': 'Não autorizado'}), 401

    data   = request.get_json(force=True) or {}
    texto  = data.get('texto', '')
    titulo = data.get('titulo', 'Trabalho')
    path   = data.get('output_path', f'/tmp/sabio_{data.get("tarefa_id","0")}.pdf')

    resultado = gerar_pdf(texto, path, titulo)
    return jsonify(resultado)


# ────────────────────────────────────────────────────────────────
# ROTA 5: Gerar DOCX profissional
# POST /documento/docx
# ────────────────────────────────────────────────────────────────
@app.route('/documento/docx', methods=['POST'])
def documento_docx():
    if not verificar_secret():
        return jsonify({'error': 'Não autorizado'}), 401

    data   = request.get_json(force=True) or {}
    texto  = data.get('texto', '')
    titulo = data.get('titulo', 'Trabalho')
    path   = data.get('output_path', f'/tmp/sabio_{data.get("tarefa_id","0")}.docx')

    resultado = gerar_docx(texto, path, titulo)
    return jsonify(resultado)


# ────────────────────────────────────────────────────────────────
# ROTA 6: Resolver expressão matemática
# POST /math/resolver
# Body: {expressao}
# ────────────────────────────────────────────────────────────────
@app.route('/math/resolver', methods=['POST'])
def math_resolver():
    if not verificar_secret():
        return jsonify({'error': 'Não autorizado'}), 401

    data  = request.get_json(force=True) or {}
    expr  = data.get('expressao', '')
    if not expr:
        return jsonify({'error': 'Expressão vazia'}), 400

    return jsonify(resolver_matematica(expr))


# ────────────────────────────────────────────────────────────────
# ROTA 7: Pesquisar nos PDFs de livros
# POST /livros/pesquisar
# Body: {termo, books_dir}
# ────────────────────────────────────────────────────────────────
@app.route('/livros/pesquisar', methods=['POST'])
def livros_pesquisar():
    if not verificar_secret():
        return jsonify({'error': 'Não autorizado'}), 401

    data      = request.get_json(force=True) or {}
    termo     = data.get('termo', '')
    books_dir = data.get('books_dir', './uploads/books')

    if not termo:
        return jsonify({'resultados': [], 'total': 0})

    return jsonify(pesquisar_livros(termo, books_dir))


# ────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('DEBUG', 'false').lower() == 'true'
    log.info(f"Sabiomz Python API a iniciar na porta {port}")
    app.run(host='0.0.0.0', port=port, debug=debug)
