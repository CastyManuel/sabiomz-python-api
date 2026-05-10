#!/usr/bin/env python3
"""
Sabiomz v3 — Math Formatter
Formata e resolve expressões matemáticas com SymPy.
Uso: python3 math_formatter.py <expressão>
"""
import sys
import json
import re


def tentar_eval_simples(expr: str) -> dict | None:
    """Tenta resolver expressão aritmética simples."""
    try:
        # Limpar a expressão (só operadores seguros)
        limpa = re.sub(r'[^0-9\+\-\*\/\.\(\)\s\^]', '', expr).strip()
        limpa = limpa.replace('^', '**')
        if limpa:
            resultado = eval(limpa, {"__builtins__": {}})
            return {"resultado": resultado, "tipo": "aritmetica", "expressao_limpa": limpa}
    except Exception:
        pass
    return None


def resolver_sympy(expr: str) -> dict:
    """Resolve com SymPy para álgebra, equações, cálculo."""
    try:
        import sympy as sp
        from sympy.parsing.sympy_parser import (
            parse_expr, standard_transformations,
            implicit_multiplication_application
        )

        transformations = (standard_transformations +
                          (implicit_multiplication_application,))

        # Detectar tipo
        resultado = {}

        # Equação: contém '='
        if '=' in expr and not expr.count('=') > 1:
            lhs_str, rhs_str = expr.split('=', 1)
            lhs = parse_expr(lhs_str.strip(), transformations=transformations)
            rhs = parse_expr(rhs_str.strip(), transformations=transformations)
            equacao = sp.Eq(lhs, rhs)
            variaveis = list(lhs.free_symbols | rhs.free_symbols)
            if variaveis:
                sols = sp.solve(equacao, variaveis[0])
                resultado = {
                    "tipo": "equacao",
                    "equacao": str(equacao),
                    "variavel": str(variaveis[0]),
                    "solucao": [str(s) for s in sols],
                    "latex": sp.latex(equacao),
                }
        else:
            # Expressão para simplificar/avaliar
            expr_sympy = parse_expr(expr.replace('^', '**'), transformations=transformations)
            simplificada = sp.simplify(expr_sympy)
            resultado = {
                "tipo": "expressao",
                "original": expr,
                "simplificada": str(simplificada),
                "latex": sp.latex(simplificada),
                "numerica": float(simplificada.evalf()) if simplificada.is_number else None,
            }

        return resultado

    except ImportError:
        # SymPy não instalado - tentar aritmética simples
        simples = tentar_eval_simples(expr)
        if simples:
            return simples
        return {"erro": "SymPy não instalado. Execute: pip install sympy", "fallback": True}
    except Exception as e:
        simples = tentar_eval_simples(expr)
        if simples:
            return simples
        return {"erro": str(e), "expressao": expr}


def formatar_resultado(data: dict) -> str:
    """Formata o resultado de forma legível."""
    if "erro" in data and not data.get("solucao"):
        return f"❌ Erro: {data['erro']}"

    linhas = []

    if data.get("tipo") == "equacao":
        linhas.append(f"**Equação:** {data.get('equacao', '')}")
        sols = data.get("solucao", [])
        if sols:
            linhas.append(f"**Solução:** {data.get('variavel', 'x')} = {', '.join(sols)}")
        if data.get("latex"):
            linhas.append(f"**LaTeX:** `{data['latex']}`")

    elif data.get("tipo") == "expressao":
        linhas.append(f"**Expressão:** {data.get('original', '')}")
        linhas.append(f"**Simplificada:** {data.get('simplificada', '')}")
        if data.get("numerica") is not None:
            linhas.append(f"**Valor numérico:** {data['numerica']:.6g}")

    elif data.get("tipo") == "aritmetica":
        linhas.append(f"**Resultado:** {data.get('resultado', '')}")

    return "\n".join(linhas)


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"erro": "Uso: math_formatter.py <expressão>"}))
        return

    expr   = ' '.join(sys.argv[1:])
    result = resolver_sympy(expr)
    result["formatado"] = formatar_resultado(result)

    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
