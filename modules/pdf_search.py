"""
Sabiomz v5 — modules/pdf_search.py
Pesquisa semântica (por termo) nos PDFs de livros carregados.
"""
import os
import re


def pesquisar_livros(termo: str, books_dir: str = "./uploads/books", max_per_book: int = 5) -> dict:
    """
    Pesquisa 'termo' em todos os PDFs de books_dir.
    Retorna: {termo, resultados: [{livro, matches: [{pagina, trecho}], count}], total, pdfs_lidos}
    """
    termo_norm = termo.lower().strip()
    if not termo_norm:
        return {"erro": "Termo vazio.", "resultados": [], "total": 0}

    if not os.path.isdir(books_dir):
        return {"erro": f"Pasta não encontrada: {books_dir}", "resultados": [], "total": 0}

    pdfs = [f for f in os.listdir(books_dir) if f.lower().endswith(".pdf")]
    resultados = []

    for filename in sorted(pdfs):
        path = os.path.join(books_dir, filename)
        try:
            matches = _extrair_matches(path, termo_norm, max_per_book)
            if matches:
                resultados.append({
                    "livro": filename,
                    "matches": matches,
                    "count": len(matches),
                })
        except Exception:
            pass  # Ignorar PDFs com erro

    # Ordenar por relevância (mais matches primeiro)
    resultados.sort(key=lambda x: x["count"], reverse=True)

    return {
        "termo": termo,
        "resultados": resultados,
        "total": len(resultados),
        "pdfs_lidos": len(pdfs),
    }


def _extrair_matches(pdf_path: str, termo: str, max_matches: int = 5) -> list:
    matches = []

    # Tentar pdfplumber
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                texto = page.extract_text() or ""
                texto_limpo = _limpar(texto)
                t_low = texto_limpo.lower()
                if termo in t_low:
                    idx = t_low.find(termo)
                    trecho = texto_limpo[max(0, idx - 150): idx + 350]
                    matches.append({"pagina": i + 1, "trecho": trecho.strip()})
                    if len(matches) >= max_matches:
                        break
        if matches:
            return matches
    except ImportError:
        pass
    except Exception:
        pass

    # Fallback PyPDF2
    try:
        from PyPDF2 import PdfReader
        reader = PdfReader(pdf_path)
        for i, page in enumerate(reader.pages):
            try:
                texto = page.extract_text() or ""
                texto_limpo = _limpar(texto)
                t_low = texto_limpo.lower()
                if termo in t_low:
                    idx = t_low.find(termo)
                    trecho = texto_limpo[max(0, idx - 150): idx + 350]
                    matches.append({"pagina": i + 1, "trecho": trecho.strip()})
                    if len(matches) >= max_matches:
                        break
            except Exception:
                continue
    except ImportError:
        pass
    except Exception:
        pass

    return matches


def _limpar(texto: str) -> str:
    texto = re.sub(r"\s+", " ", texto)
    texto = texto.replace("\x00", "")
    return texto.strip()
