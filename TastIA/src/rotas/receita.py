"""Rotas da API de receitas (usadas pela tela templates/receitas.html)[cite: 21]."""
import re

from flask import Blueprint, current_app, jsonify, request, session

from banco_dados.database import obter_conexao
from receitas.gerador import gerar_receita, preparar_inventario
from receitas.validador import normalizar_texto

bp_receita = Blueprint("receita", __name__, url_prefix="/api/receita")

TEMPOS_VALIDOS = {"15", "30", "45", "60", "qualquer"}
DIFICULDADES_VALIDAS = {"facil", "media", "dificil", "qualquer"}


def _nao_autenticado():
    return jsonify({"erro": "Faça login para continuar."}), 401


def _carregar_inventario(usuario_id: int):
    conn = obter_conexao()
    linhas = conn.execute(
        "SELECT nome, quantidade, validade FROM inventario WHERE usuario_id = ? "
        "ORDER BY nome COLLATE NOCASE",
        (usuario_id,),
    ).fetchall()
    conn.close()
    return [dict(l) for l in linhas]


def _separar_nomes(texto: str):
    nomes, vistos = [], set()
    for parte in re.split(r"[,;\n]", texto):
        nome = parte.strip()[:60]
        chave = normalizar_texto(nome)
        if nome and chave not in vistos:
            vistos.add(chave)
            nomes.append(nome)
    return nomes[:60]


@bp_receita.get("/inventario")
def inventario_usuario():
    if "usuario_id" not in session:
        return _nao_autenticado()
    ativos, vencidos = preparar_inventario(_carregar_inventario(session["usuario_id"]))
    return jsonify({"itens": ativos, "vencidos": vencidos})


@bp_receita.post("/gerar")
def gerar():
    if "usuario_id" not in session:
        return _nao_autenticado()

    dados = request.get_json(silent=True) or {}
    pedido = str(dados.get("pedido", "")).strip()
    if not pedido:
        return jsonify({"erro": "Descreva o que você gostaria de preparar."}), 400
    if len(pedido) > 500:
        return jsonify({"erro": "O pedido pode ter no máximo 500 caracteres."}), 400

    tempo = str(dados.get("tempo", "")).strip()
    dificuldade = str(dados.get("dificuldade", "")).strip()
    tempo = tempo if tempo in TEMPOS_VALIDOS else None
    dificuldade = dificuldade if dificuldade in DIFICULDADES_VALIDAS else None
    restricoes = str(dados.get("restricoes", "")).strip()[:300] or None
    evitar = str(dados.get("evitar", "")).strip()[:120] or None

    do_banco = _carregar_inventario(session["usuario_id"])
    texto_ing = str(dados.get("ingredientes", "")).strip()
    if texto_ing:
        por_nome = {normalizar_texto(i["nome"]): i for i in do_banco}
        itens = [por_nome.get(normalizar_texto(n), {"nome": n}) for n in _separar_nomes(texto_ing)]
    else:
        itens = do_banco

    try:
        r = gerar_receita(itens, pedido, tempo, dificuldade, restricoes, evitar)
    except ValueError as e:
        return jsonify({"erro": str(e)}), 400
    except ImportError as e:
        current_app.logger.exception("Dependência do gerador ausente")
        return jsonify({"erro": "O modelo de receitas não está disponível neste servidor.",
                        "detalhes": str(e)}), 503
    except Exception as e:
        current_app.logger.exception("Falha ao gerar receita")
        return jsonify({"erro": "Não foi possível gerar a receita agora.", "detalhes": str(e)}), 500

    receita_id = None
    if r.valida:
        conn = obter_conexao()
        cur = conn.execute(
            "INSERT INTO receitas (usuario_id, pedido, conteudo) VALUES (?, ?, ?)",
            (session["usuario_id"], pedido, r.texto),
        )
        conn.commit()
        receita_id = cur.lastrowid
        conn.close()

    resposta = r.como_dict()
    resposta["receita"] = resposta.pop("texto")
    resposta["receita_id"] = receita_id
    return jsonify(resposta)