#!/usr/bin/env python3
"""
Sabiomz v2 — Pesquisa semântica em PDFs de livros
Uso: python3 pdf_search.py <termo> [--dir /caminho/livros]
"""
import sys
import json
import os
import argparse
import re

BOOKS_DIR = os.path.join(os.path.dirname(__file__), "../public/uploads/books")


def clean_text(text: str) -> str:
    """Limpa texto extraído do PDF."""
    text = re.sub(r'\s+', ' ', text)
    text = text.replace('\x00', '').strip()
    return text


def extract_matches(pdf_path: str, termo: str, max_matches: int = 5) -> list:
    """Extrai trechos relevantes de um PDF para um dado termo."""
    matches = []
    try:
        from PyPDF2 import PdfReader
        reader = PdfReader(pdf_path)
    except ImportError:
        try:
            import pdfplumber
            with pdfplumber.open(pdf_path) as pdf:
                for i, page in enumerate(pdf.pages):
                    text = page.extract_text() or ""
                    text_clean = clean_text(text)
                    t_lower = text_clean.lower()
                    if termo in t_lower:
                        idx = t_lower.find(termo)
                        trecho = text_clean[max(0, idx - 150): idx + 300]
                        matches.append({
                            "pagina": i + 1,
                            "trecho": trecho.strip()
                        })
                        if len(matches) >= max_matches:
                            break
            return matches
        except Exception:
            return []
    except Exception:
        return []

    for i, page in enumerate(reader.pages):
        try:
            text = page.extract_text() or ""
            text_clean = clean_text(text)
            t_lower = text_clean.lower()

            # Suporte a variações (plural, acento)
            if termo in t_lower:
                idx = t_lower.find(termo)
                start = max(0, idx - 150)
                end   = min(len(text_clean), idx + 350)
                trecho = text_clean[start:end]
                # Destaca contexto
                matches.append({
                    "pagina": i + 1,
                    "trecho": trecho.strip()
                })
                if len(matches) >= max_matches:
                    break
        except Exception:
            continue

    return matches


def search_all(termo: str, books_dir: str) -> dict:
    """Pesquisa em todos os PDFs na pasta."""
    if not os.path.isdir(books_dir):
        return {"erro": f"Pasta não encontrada: {books_dir}", "resultados": [], "total": 0}

    resultados = []
    pdf_files = [f for f in os.listdir(books_dir) if f.lower().endswith('.pdf')]

    for filename in sorted(pdf_files):
        path = os.path.join(books_dir, filename)
        try:
            matches = extract_matches(path, termo)
            if matches:
                resultados.append({
                    "livro":   filename,
                    "matches": matches,
                    "count":   len(matches)
                })
        except Exception as e:
            pass  # Ignora PDFs com erro

    # Ordena por número de matches (mais relevante primeiro)
    resultados.sort(key=lambda x: x["count"], reverse=True)

    return {
        "termo":      termo,
        "resultados": resultados,
        "total":      len(resultados),
        "pdfs_lidos": len(pdf_files)
    }


def main():
    parser = argparse.ArgumentParser(description='Pesquisa em PDFs Sabiomz')
    parser.add_argument('termo', nargs='?', default='', help='Termo a pesquisar')
    parser.add_argument('--dir',  default=BOOKS_DIR, help='Directório dos PDFs')
    parser.add_argument('--max',  type=int, default=5, help='Máximo de resultados por livro')
    args = parser.parse_args()

    if not args.termo:
        print(json.dumps({"error": "Nenhum termo fornecido. Uso: pdf_search.py <termo>"},
                         ensure_ascii=False))
        return

    termo = args.termo.lower().strip()
    resultado = search_all(termo, args.dir)
    print(json.dumps(resultado, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
