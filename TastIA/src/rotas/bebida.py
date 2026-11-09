"""Rotas HTTP da API de Bebidas (TastIA - Módulo do Reinaldo)."""
from flask import Blueprint, jsonify, request, session
from bebidas.recomendador import obter_recomendador
from banco_dados.database import obter_conexao

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


@bp_bebida.post("/escolher")
def escolher_bebida():
    """Grava a bebida escolhida pelo utilizador na tabela bebidas_sugeridas.

    Se vier um receita_id (o mesmo devolvido por /api/receita/gerar) e a receita for do utilizador,
    a bebida fica ligada a ela. Sem receita (ou com um id que não existe mais), a bebida é guardada sozinha.
    """
    if "usuario_id" not in session:
        return _nao_autenticado()

    dados = request.get_json(silent=True) or {}
    nome_bebida = str(dados.get("nome_bebida", "")).strip()
    justificativa = str(dados.get("justificativa", "")).strip()
    refeicao = str(dados.get("refeicao", "")).strip()[:300] or None

    if not nome_bebida:
        return jsonify({"erro": "Nenhuma bebida foi informada."}), 400

    receita_id = None
    bruto = dados.get("receita_id")
    if bruto not in (None, ""):
        try:
            receita_id = int(bruto)
        except (TypeError, ValueError):
            return jsonify({"erro": "Receita inválida."}), 400

    try:
        conn = obter_conexao()
        try:
            if receita_id is not None:
                dona = conn.execute(
                    "SELECT id FROM receitas WHERE id = ? AND usuario_id = ?",
                    (receita_id, session["usuario_id"]),
                ).fetchone()
                if not dona:
                    receita_id = None  # receita apagada ou de outro utilizador: guarda a bebida sozinha

            if receita_id is not None:
                repetida = conn.execute(
                    "SELECT id FROM bebidas_sugeridas "
                    "WHERE usuario_id = ? AND receita_id = ? AND nome_bebida = ?",
                    (session["usuario_id"], receita_id, nome_bebida),
                ).fetchone()
                if repetida:
                    return jsonify({
                        "mensagem": "Esta bebida já estava guardada com a receita.",
                        "bebida_id": repetida["id"],
                        "receita_id": receita_id,
                        "vinculada": True,
                    }), 200

            cursor = conn.execute(
                """
                INSERT INTO bebidas_sugeridas (usuario_id, receita_id, nome_bebida, justificativa, refeicao)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session["usuario_id"], receita_id, nome_bebida, justificativa, refeicao)
            )
            conn.commit()
            bebida_id = cursor.lastrowid
        finally:
            conn.close()

        vinculada = receita_id is not None
        return jsonify({
            "mensagem": ("Bebida guardada junto com a receita!" if vinculada
                         else "Bebida escolhida e guardada com sucesso!"),
            "bebida_id": bebida_id,
            "receita_id": receita_id,
            "vinculada": vinculada,
        }), 200
    except Exception as e:
        return jsonify({"erro": "Erro ao guardar a bebida.", "detalhes": str(e)}), 500


@bp_bebida.delete("/historico/<int:bebida_id>")
def excluir_bebida(bebida_id: int):
    """Remove uma bebida guardada (apenas as do utilizador logado)."""
    if "usuario_id" not in session:
        return _nao_autenticado()

    try:
        conn = obter_conexao()
        try:
            cursor = conn.execute(
                "DELETE FROM bebidas_sugeridas WHERE id = ? AND usuario_id = ?",
                (bebida_id, session["usuario_id"]),
            )
            conn.commit()
            apagadas = cursor.rowcount
        finally:
            conn.close()
    except Exception as e:
        return jsonify({"erro": "Erro ao excluir a bebida.", "detalhes": str(e)}), 500

    if not apagadas:
        return jsonify({"erro": "Bebida não encontrada."}), 404
    return jsonify({"ok": True, "id": bebida_id})
