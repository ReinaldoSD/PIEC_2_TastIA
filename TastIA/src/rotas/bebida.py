"""Rotas HTTP da API de Bebidas (TastIA - Módulo do Reinaldo)."""
from flask import Blueprint, jsonify, request, session
from bebidas.recomendador import obter_recomendador

bp_bebida = Blueprint("bebida", __name__, url_prefix="/api/bebida")


def _nao_autenticado():
    return jsonify({"erro": "Faça login para continuar."}), 401


@bp_bebida.post("/sugerir")
def sugerir_bebida():
    if "usuario_id" not in session:
        return _nao_autenticado()

    dados = request.get_json(silent=True) or {}
    refeicao = str(dados.get("refeicao", "")).strip()
    ingredientes = str(dados.get("ingredientes", "")).strip()
    preferencias = str(dados.get("preferencias", "")).strip()
    temperatura = str(dados.get("temperatura", "")).strip() or None
    tipo = str(dados.get("tipo", "qualquer")).strip()

    if not refeicao and not ingredientes:
        return jsonify({"erro": "Informe qual refeição você vai preparar ou os ingredientes."}), 400

    try:
        recomendador = obter_recomendador()
        resultado = recomendador.sugerir(
            refeicao=refeicao,
            ingredientes=ingredientes,
            preferencias=preferencias,
            alcool="sem",  # Garantia restrita de apenas bebidas sem álcool
            temperatura=temperatura,
            tipo=tipo,
            qtd=3
        )
        return jsonify(resultado), 200

    except ValueError as e:
        return jsonify({"erro": str(e)}), 400
    except Exception as e:
        return jsonify({"erro": "Erro ao sugerir bebida.", "detalhes": str(e)}), 500