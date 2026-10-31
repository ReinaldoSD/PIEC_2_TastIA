"""Rotas da API de receitas (telas templates/receitas.html e templates/historico.html)."""
import re

from flask import Blueprint, current_app, jsonify, request, session, url_for
from werkzeug.routing import BuildError

from banco_dados.database import obter_conexao
from receitas.gerador import InventarioVazioError, gerar_receita, preparar_inventario
from receitas.historico import montar_item_historico
from receitas.validador import normalizar_texto

bp_receita = Blueprint("receita", __name__, url_prefix="/api/receita")

TEMPOS_VALIDOS = {"15", "30", "45", "60", "qualquer"}
DIFICULDADES_VALIDAS = {"facil", "media", "dificil", "qualquer"}


def _nao_autenticado():
    return jsonify({"erro": "Faça login para continuar."}), 401


def _url_cadastro_ingrediente() -> str:
    try:
        return url_for("cadastrar_ingrediente")
    except BuildError:  # blueprint usado fora do app completo (ex.: testes)
        return "/cadastrar_ingrediente"


def _erro_inventario_vazio(mensagem: str):
    return jsonify({
        "erro": mensagem,
        "codigo": "inventario_vazio",
        "acao_url": _url_cadastro_ingrediente(),
    }), 400


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


# --------------------------------------------------------------------------- #
# Inventário (botão "Usar meu inventário")
# --------------------------------------------------------------------------- #
@bp_receita.get("/inventario")
def inventario_usuario():
    if "usuario_id" not in session:
        return _nao_autenticado()
    ativos, vencidos = preparar_inventario(_carregar_inventario(session["usuario_id"]))
    return jsonify({"itens": ativos, "vencidos": vencidos})


# --------------------------------------------------------------------------- #
# Gerar receita (salva no histórico quando a receita é válida)
# --------------------------------------------------------------------------- #
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

    # Ingredientes: o que está na caixa de texto; se vazia, todo o inventário do usuário.
    do_banco = _carregar_inventario(session["usuario_id"])
    texto_ing = str(dados.get("ingredientes", "")).strip()
    if texto_ing:
        por_nome = {normalizar_texto(i["nome"]): i for i in do_banco}
        itens = [por_nome.get(normalizar_texto(n), {"nome": n}) for n in _separar_nomes(texto_ing)]
    else:
        itens = do_banco

    if not itens:
        return _erro_inventario_vazio(
            "Seu inventário está vazio. Cadastre ingredientes ou digite-os na caixa "
            "'Ingredientes que você tem'."
        )

    try:
        r = gerar_receita(itens, pedido, tempo, dificuldade, restricoes, evitar)
    except InventarioVazioError as e:  # ex.: todos os itens vencidos
        return _erro_inventario_vazio(str(e))
    except ValueError as e:
        return jsonify({"erro": str(e)}), 400
    except ImportError as e:
        current_app.logger.exception("Dependência do gerador ausente")
        return jsonify({"erro": "O modelo de receitas não está disponível neste servidor.",
                        "detalhes": str(e)}), 503
    except Exception as e:  # download do modelo, falta de RAM, etc.
        current_app.logger.exception("Falha ao gerar receita")
        return jsonify({"erro": "Não foi possível gerar a receita agora.", "detalhes": str(e)}), 500

    # Só receitas conferidas (sem ingredientes fora do inventário) entram no histórico.
    receita_id = None
    if r.valida:
        try:
            conn = obter_conexao()
            try:
                cur = conn.execute(
                    "INSERT INTO receitas (usuario_id, pedido, conteudo) VALUES (?, ?, ?)",
                    (session["usuario_id"], pedido, r.texto),
                )
                conn.commit()
                receita_id = cur.lastrowid
            finally:
                conn.close()
        except Exception:
            current_app.logger.exception("Falha ao salvar a receita no histórico")

    resposta = r.como_dict()
    resposta["receita"] = resposta.pop("texto")
    resposta["receita_id"] = receita_id
    resposta["salva"] = receita_id is not None
    return jsonify(resposta)


# --------------------------------------------------------------------------- #
# Histórico
# --------------------------------------------------------------------------- #
@bp_receita.get("/historico")
def historico_listar():
    """Todas as receitas salvas do usuário logado, da mais nova para a mais antiga."""
    if "usuario_id" not in session:
        return _nao_autenticado()
    try:
        conn = obter_conexao()
        try:
            linhas = conn.execute(
                "SELECT id, pedido, conteudo, criado_em FROM receitas "
                "WHERE usuario_id = ? ORDER BY criado_em DESC, id DESC",
                (session["usuario_id"],),
            ).fetchall()
        finally:
            conn.close()
        itens = [montar_item_historico(l) for l in linhas]
    except Exception as e:
        current_app.logger.exception("Falha ao carregar o histórico")
        return jsonify({"erro": "Não foi possível carregar o histórico.", "detalhes": str(e)}), 500
    return jsonify({"total": len(itens), "receitas": itens})


@bp_receita.delete("/historico/<int:receita_id>")
def historico_excluir(receita_id: int):
    """Exclui uma receita do histórico (e as bebidas sugeridas ligadas a ela)."""
    if "usuario_id" not in session:
        return _nao_autenticado()
    try:
        conn = obter_conexao()
        try:
            dona = conn.execute(
                "SELECT id FROM receitas WHERE id = ? AND usuario_id = ?",
                (receita_id, session["usuario_id"]),
            ).fetchone()
            if not dona:
                return jsonify({"erro": "Receita não encontrada."}), 404
            conn.execute("DELETE FROM bebidas_sugeridas WHERE receita_id = ?", (receita_id,))
            conn.execute("DELETE FROM receitas WHERE id = ? AND usuario_id = ?",
                         (receita_id, session["usuario_id"]))
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        current_app.logger.exception("Falha ao excluir receita do histórico")
        return jsonify({"erro": "Não foi possível excluir a receita.", "detalhes": str(e)}), 500
    return jsonify({"ok": True, "id": receita_id})
