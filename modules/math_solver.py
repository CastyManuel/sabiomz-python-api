"""
Sabiomz v5 — modules/math_solver.py
Resolve expressões matemáticas com SymPy.
Fallback: eval Python para aritmética simples.
"""
import re


def resolver_matematica(expr: str) -> dict:
    """
    Resolve uma expressão matemática.
    Retorna dict com: tipo, resultado/solucao, formatado, latex (se SymPy disponível).
    """
    expr = expr.strip()
    if not expr:
        return {"erro": "Expressão vazia."}

    # Tentar SymPy
    resultado = _resolver_sympy(expr)
    if resultado and "erro" not in resultado:
        resultado["formatado"] = _formatar(resultado)
        return resultado

    # Fallback: aritmética simples
    resultado_simples = _eval_simples(expr)
    if resultado_simples is not None:
        return {
            "tipo": "aritmetica",
            "resultado": resultado_simples,
            "formatado": f"**Resultado:** {resultado_simples}",
            "metodo": "python_eval",
        }

    return {"erro": "Não foi possível resolver. Verifica a expressão.", "expressao": expr}


def _resolver_sympy(expr: str) -> dict | None:
    try:
        import sympy as sp
        from sympy.parsing.sympy_parser import (
            parse_expr,
            standard_transformations,
            implicit_multiplication_application,
        )

        transf = standard_transformations + (implicit_multiplication_application,)
        expr_clean = expr.replace("^", "**").replace("²", "**2").replace("³", "**3")

        # Equação com "="
        if "=" in expr_clean and expr_clean.count("=") == 1:
            lhs_s, rhs_s = expr_clean.split("=", 1)
            try:
                lhs = parse_expr(lhs_s.strip(), transformations=transf)
                rhs = parse_expr(rhs_s.strip(), transformations=transf)
                equacao = sp.Eq(lhs, rhs)
                variaveis = sorted(list(lhs.free_symbols | rhs.free_symbols), key=str)
                if variaveis:
                    sols = sp.solve(equacao, variaveis[0])
                    return {
                        "tipo": "equacao",
                        "equacao": str(equacao),
                        "variavel": str(variaveis[0]),
                        "solucao": [str(s) for s in sols],
                        "latex": sp.latex(equacao),
                        "metodo": "sympy",
                    }
            except Exception:
                pass

        # Expressão para simplificar
        expr_sympy = parse_expr(expr_clean, transformations=transf)
        simplificada = sp.simplify(expr_sympy)
        numerica = None
        try:
            numerica = float(simplificada.evalf())
            if abs(numerica) > 1e15 or numerica != numerica:  # inf/nan
                numerica = None
        except Exception:
            pass

        return {
            "tipo": "expressao",
            "original": expr,
            "simplificada": str(simplificada),
            "latex": sp.latex(simplificada),
            "numerica": round(numerica, 8) if numerica is not None else None,
            "metodo": "sympy",
        }

    except ImportError:
        return None  # SymPy não disponível → usar fallback
    except Exception:
        return None


def _eval_simples(expr: str) -> float | int | None:
    """Avalia aritmética simples de forma segura."""
    try:
        limpa = re.sub(r"[^0-9\+\-\*\/\.\(\)\s\^]", "", expr)
        limpa = limpa.replace("^", "**").strip()
        if limpa and len(limpa) < 200:
            resultado = eval(limpa, {"__builtins__": {}})  # noqa: S307
            if isinstance(resultado, (int, float)):
                return round(resultado, 10) if isinstance(resultado, float) else resultado
    except Exception:
        pass
    return None


def _formatar(data: dict) -> str:
    """Formata o resultado de forma legível para Markdown."""
    if data.get("tipo") == "equacao":
        var = data.get("variavel", "x")
        sols = data.get("solucao", [])
        linhas = [f"**Equação:** {data.get('equacao', '')}"]
        if sols:
            linhas.append(f"**Solução:** {var} = {', '.join(sols)}")
        if data.get("latex"):
            linhas.append(f"**LaTeX:** `{data['latex']}`")
        return "\n".join(linhas)

    elif data.get("tipo") == "expressao":
        linhas = [f"**Expressão original:** {data.get('original', '')}"]
        if data.get("simplificada"):
            linhas.append(f"**Simplificada:** {data['simplificada']}")
        if data.get("numerica") is not None:
            linhas.append(f"**Valor numérico:** {data['numerica']}")
        return "\n".join(linhas)

    elif data.get("tipo") == "aritmetica":
        return f"**Resultado:** {data.get('resultado', '')}"

    return ""
