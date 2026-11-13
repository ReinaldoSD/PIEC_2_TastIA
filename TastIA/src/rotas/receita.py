"""Rotas da API de receitas (telas templates/receitas.html e templates/historico.html)."""
import re
from flask import Blueprint, current_app, jsonify, request, session, url_for
from werkzeug.routing import BuildError

from banco_dados.database import obter_conexao
from receitas.formatador import formatar_receita
from receitas.gerador import InventarioVazioError, gerar_receita, preparar_inventario
from receitas.historico import interpretar_receita, montar_item_bebida, montar_item_historico
from receitas.validador import normalizar_texto, validar_receita
from servicos.fila import obter_fila, ESTADO_CONCLUIDO, ESTADO_ERRO, ESTADO_PENDENTE, ESTADO_PROCESSANDO

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


def _resolver_itens(usuario_id: int, texto_ing: str):
    """Ingredientes da caixa de texto (com validade do inventário, se existir); vazio = todo o inventário."""
    do_banco = _carregar_inventario(usuario_id)
    if texto_ing:
        por_nome = {normalizar_texto(i["nome"]): i for i in do_banco}
        return [por_nome.get(normalizar_texto(n), {"nome": n}) for n in _separar_nomes(texto_ing)]
    return do_banco


def _salvar_receita(usuario_id: int, pedido: str, texto: str):
    """Grava a receita no histórico e devolve o id (ou None se falhar)."""
    try:
        conn = obter_conexao()
        try:
            cur = conn.execute(
                "INSERT INTO receitas (usuario_id, pedido, conteudo) VALUES (?, ?, ?)",
                (usuario_id, pedido, texto),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()
    except Exception:
        current_app.logger.exception("Falha ao salvar a receita no histórico")
        return None


def _montar_resposta(r, pedido: str, receita_id, aguardando_aprovacao: bool = False):
    """JSON devolvido ao navegador: receita limpa + partes já separadas + id para ligar bebidas."""
    resposta = r.como_dict()
    resposta["receita"] = resposta.pop("texto")
    resposta["detalhes"] = interpretar_receita(resposta["receita"], pedido)
    resposta["receita_id"] = receita_id
    resposta["salva"] = receita_id is not None
    # True quando a receita está no formato certo e só será salva se o usuário aprovar (rota /aprovar).
    # Vale também para receita com itens fora do inventário: o aviso continua e o usuário decide.
    resposta["aguardando_aprovacao"] = bool(aguardando_aprovacao and r.estrutura_ok and receita_id is None)
    return resposta


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
    itens = _resolver_itens(session["usuario_id"], str(dados.get("ingredientes", "")).strip())

    # "salvar": false = a receita só entra no histórico depois que o usuário aprovar (/aprovar).
    # Sem esse campo, continua salvando sozinha quando a receita é válida (comportamento antigo).
    salvar_agora = dados.get("salvar", True) is not False

    if not itens:
        return _erro_inventario_vazio(
            "Seu inventário está vazio. Cadastre ingredientes ou digite-os na caixa "
            "'Ingredientes que você tem'."
        )

    # Se o cliente solicitar execução via Fila em Segundo Plano
    assincrono = dados.get("assincrono", False)
    if assincrono:
        fila = obter_fila()
        usuario_id = session["usuario_id"]

        def _tarefa_geracao():
            r = gerar_receita(itens, pedido, tempo, dificuldade, restricoes, evitar)
            receita_id = _salvar_receita(usuario_id, pedido, r.texto) if (r.valida and salvar_agora) else None
            return _montar_resposta(r, pedido, receita_id, aguardando_aprovacao=not salvar_agora)

        tarefa_id = fila.submeter(_tarefa_geracao)
        return jsonify({"tarefa_id": tarefa_id, "status": ESTADO_PENDENTE}), 202

    # Execução Síncrona Tradicional
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

    # Salva no banco de dados se for válida; o id volta para a tela usar ao salvar a bebida
    receita_id = _salvar_receita(session["usuario_id"], pedido, r.texto) if (r.valida and salvar_agora) else None
    return jsonify(_montar_resposta(r, pedido, receita_id, aguardando_aprovacao=not salvar_agora))


# --------------------------------------------------------------------------- #
# Aprovar receita (o usuário decide se ela entra no histórico)
# --------------------------------------------------------------------------- #
@bp_receita.post("/aprovar")
def aprovar():
    """Salva no histórico uma receita gerada com "salvar": false, depois que o usuário aprova.

    Recebe {pedido, receita, ingredientes}. O servidor limpa e confere o texto de novo contra os
    mesmos ingredientes da geração. Receita com itens fora do inventário PODE ser aprovada (o usuário
    já viu o aviso); o que não passa é um texto fora do formato (sem 'Ingredientes' e 'Modo de preparo').
    Aprovar duas vezes a mesma receita devolve o mesmo id, sem duplicar no histórico.
    """
    if "usuario_id" not in session:
        return _nao_autenticado()

    dados = request.get_json(silent=True) or {}
    pedido = str(dados.get("pedido", "")).strip()[:500]
    texto = formatar_receita(str(dados.get("receita", "")))
    if not texto.strip():
        return jsonify({"erro": "Não há receita para aprovar."}), 400
    if len(texto) > 20000:
        return jsonify({"erro": "A receita é grande demais para ser salva."}), 400

    usuario_id = session["usuario_id"]
    itens = _resolver_itens(usuario_id, str(dados.get("ingredientes", "")).strip())
    ativos, _vencidos = preparar_inventario(itens)
    if not ativos:
        return _erro_inventario_vazio("Não há ingredientes disponíveis para conferir a receita.")
    val = validar_receita(texto, [i["nome"] for i in ativos])
    if not val.estrutura_ok:
        return jsonify({"erro": "Esta receita não está no formato esperado e não pode ser salva. Gere outra."}), 422

    try:
        conn = obter_conexao()
        try:
            existente = conn.execute(
                "SELECT id FROM receitas WHERE usuario_id = ? AND conteudo = ? ORDER BY id DESC LIMIT 1",
                (usuario_id, texto),
            ).fetchone()
        finally:
            conn.close()
    except Exception:
        current_app.logger.exception("Falha ao procurar a receita no histórico")
        existente = None

    receita_id = existente["id"] if existente else _salvar_receita(usuario_id, pedido, texto)
    if receita_id is None:
        return jsonify({"erro": "Não foi possível salvar a receita agora. Tente novamente."}), 500
    return jsonify({
        "receita_id": receita_id,
        "salva": True,
        "valida": val.valido,
        "fora_do_inventario": val.problemas,
    })


# --------------------------------------------------------------------------- #
# Rota para consultar o Status de uma Tarefa em Segundo Plano
# --------------------------------------------------------------------------- #
@bp_receita.get("/status/<tarefa_id>")
def status_tarefa_receita(tarefa_id: str):
    if "usuario_id" not in session:
        return _nao_autenticado()

    fila = obter_fila()
    info = fila.obter_status(tarefa_id)
    if not info:
        return jsonify({"erro": "Tarefa não encontrada."}), 404

    if info["status"] == ESTADO_CONCLUIDO:
        return jsonify({"status": info["status"], "resultado": info["resultado"]}), 200
    elif info["status"] == ESTADO_ERRO:
        return jsonify({"status": info["status"], "erro": info["erro"]}), 500
    else:
        return jsonify({"status": info["status"]}), 200


# --------------------------------------------------------------------------- #
# Histórico
# --------------------------------------------------------------------------- #
@bp_receita.get("/historico")
def historico_listar():
    """Receitas e bebidas salvas do usuário logado, da mais nova para a mais antiga.

    - "receitas": cada receita traz em "bebidas" as bebidas escolhidas para ela (mesmo receita_id);
    - "bebidas": só as bebidas salvas sozinhas (sem receita).
    """
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
            linhas_bebidas = conn.execute(
                "SELECT id, receita_id, nome_bebida, justificativa, refeicao, criado_em "
                "FROM bebidas_sugeridas WHERE usuario_id = ? ORDER BY criado_em DESC, id DESC",
                (session["usuario_id"],),
            ).fetchall()
        finally:
            conn.close()
        bebidas = [montar_item_bebida(l) for l in linhas_bebidas]
        por_receita = {}
        for b in bebidas:
            if b["receita_id"] is not None:
                por_receita.setdefault(b["receita_id"], []).append(b)
        itens = [montar_item_historico(l, por_receita.get(l["id"])) for l in linhas]
        avulsas = [b for b in bebidas if b["receita_id"] is None]
    except Exception as e:
        current_app.logger.exception("Falha ao carregar o histórico")
        return jsonify({"erro": "Não foi possível carregar o histórico.", "detalhes": str(e)}), 500
    return jsonify({
        "total": len(itens),
        "total_bebidas": len(bebidas),
        "receitas": itens,
        "bebidas": avulsas,
    })


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
            conn.execute("DELETE FROM bebidas_sugeridas WHERE receita_id = ? AND usuario_id = ?",
                         (receita_id, session["usuario_id"]))
            conn.execute("DELETE FROM receitas WHERE id = ? AND usuario_id = ?",
                         (receita_id, session["usuario_id"]))
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        current_app.logger.exception("Falha ao excluir receita do histórico")
        return jsonify({"erro": "Não foi possível excluir a receita.", "detalhes": str(e)}), 500
    return jsonify({"ok": True, "id": receita_id})
