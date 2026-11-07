"""Rotas da API de Percepção e Ingredientes (Detecção por Foto e Salvamento em Lote)."""

import io
import re
from flask import Blueprint, jsonify, request, session
from PIL import Image, UnidentifiedImageError
from typing import Dict, Optional, Tuple

from banco_dados.database import obter_conexao
from percepcao.pipeline import obter_pipeline
from servicos.fila import obter_fila, ESTADO_CONCLUIDO, ESTADO_ERRO, ESTADO_PENDENTE
from receitas.validador import normalizar_texto

bp_ingrediente = Blueprint("ingrediente", __name__, url_prefix="/api/ingredientes")

EXTENSOES_PERMITIDAS = {"png", "jpg", "jpeg", "webp", "bmp"}
TAMANHO_MAX_BYTES = 10 * 1024 * 1024  # 10 MB


def _nao_autenticado():
    return jsonify({"erro": "Faça login para continuar."}), 401


def _extensao_valida(nome_arquivo: str) -> bool:
    return "." in nome_arquivo and nome_arquivo.rsplit(".", 1)[1].lower() in EXTENSOES_PERMITIDAS
def _formatar_qtd_unidade(qtd_bruta: str, unidade_bruta: str = "") -> Tuple[str, str]:
    """Combina ou extrai quantidade e unidade para manter compatibilidade com toda a aplicação."""
    qtd_str = str(qtd_bruta or "").strip()
    unid_str = str(unidade_bruta or "").strip()

    if unid_str:
        if qtd_str and not qtd_str.lower().endswith(unid_str.lower()):
            qtd_exibicao = f"{qtd_str} {unid_str}".strip()
        else:
            qtd_exibicao = qtd_str or f"1 {unid_str}"
        return qtd_exibicao[:50], unid_str[:30]

    m = re.match(r"^(\d+(?:[.,]\d+)?)\s*(.*)$", qtd_str)
    if m:
        num, resto = m.group(1), m.group(2).strip() or "unidade"
        return f"{num} {resto}"[:50], resto[:30]

    return (qtd_str or "1 unidade")[:50], "unidade"


def _buscar_duplicado(conn, usuario_id: int, nome: str, ignorar_id: Optional[int] = None) -> Optional[Dict]:
    """Procura se o usuário já possui um ingrediente com o mesmo nome normalizado."""
    chave_nova = normalizar_texto(nome)
    linhas = conn.execute(
        "SELECT * FROM inventario WHERE usuario_id = ?", (usuario_id,)
    ).fetchall()
    for linha in linhas:
        if ignorar_id is not None and linha["id"] == ignorar_id:
            continue
        if normalizar_texto(linha["nome"]) == chave_nova:
            return dict(linha)
    return None


@bp_ingrediente.post("/detectar")
def detectar_ingredientes():
    if "usuario_id" not in session:
        return _nao_autenticado()

    if "imagem" not in request.files:
        return jsonify({"erro": "Nenhuma imagem foi enviada na requisição."}), 400

    arquivo = request.files["imagem"]
    if not arquivo or not arquivo.filename or arquivo.filename.strip() == "":
        return jsonify({"erro": "Arquivo de imagem vazio ou não selecionado."}), 400

    if not _extensao_valida(arquivo.filename):
        return jsonify({
            "erro": "Formato de imagem inválido. Envie PNG, JPG, JPEG ou WEBP."
        }), 400

    conteudo = arquivo.read()
    if not conteudo:
        return jsonify({"erro": "O arquivo enviado está vazio (0 bytes)."}), 400

    if len(conteudo) > TAMANHO_MAX_BYTES:
        return jsonify({"erro": "A imagem excede o tamanho máximo permitido de 10 MB."}), 400

    try:
        img_teste = Image.open(io.BytesIO(conteudo))
        img_teste.verify()
        imagem = Image.open(io.BytesIO(conteudo)).convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError):
        return jsonify({"erro": "Arquivo inválido ou imagem corrompida."}), 400

    assincrono = request.form.get("assincrono", "false").lower() == "true"

    if assincrono:
        fila = obter_fila()

        def _tarefa_deteccao():
            pipeline = obter_pipeline()
            return pipeline.executar(imagem)

        tarefa_id = fila.submeter(_tarefa_deteccao)
        return jsonify({"tarefa_id": tarefa_id, "status": ESTADO_PENDENTE}), 202

    try:
        pipeline = obter_pipeline()
        resultado = pipeline.executar(imagem)
        return jsonify(resultado), 200
    except Exception as e:
        return jsonify({
            "erro": "Erro interno ao processar a imagem nos modelos de IA.",
            "detalhes": str(e)
        }), 500


@bp_ingrediente.get("/status/<tarefa_id>")
def status_tarefa_ingrediente(tarefa_id: str):
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


@bp_ingrediente.post("/confirmar")
@bp_ingrediente.post("/salvar_lote")
def salvar_lote():
    """Salva no banco apenas os ingredientes marcados pelo usuário após a foto, sem duplicar."""
    if "usuario_id" not in session:
        return _nao_autenticado()

    dados = request.get_json(silent=True) or {}
    itens = dados.get("itens", [])

    if not isinstance(itens, list) or not itens:
        return jsonify({"erro": "Nenhum ingrediente informado para salvar."}), 400

    usuario_id = session["usuario_id"]
    conn = obter_conexao()
    cursor = conn.cursor()

    inseridos = 0
    atualizados = 0
    ignorados_desmarcados = 0
    vistos_no_lote = set()

    for item in itens:
        # Só processa os itens marcados (default True caso o payload não envie a chave)
        marcado = item.get("marcado", item.get("confirmado", True))
        if not marcado:
            ignorados_desmarcados += 1
            continue

        nome = str(item.get("nome", "")).strip()[:100]
        if not nome:
            continue

        chave_nome = normalizar_texto(nome)
        # Evita duplicar se houver 2 linhas com o mesmo nome no próprio lote enviado
        if chave_nome in vistos_no_lote:
            continue
        vistos_no_lote.add(chave_nome)

        categoria = str(item.get("categoria", "Outros")).strip()[:50] or "Outros"
        quantidade, unidade = _formatar_qtd_unidade(
            item.get("quantidade", "1 unidade"), item.get("unidade", "")
        )
        validade = str(item.get("validade", "")).strip() or None

        existente = _buscar_duplicado(conn, usuario_id, nome)
        if existente:
            # Se já existe no inventário do usuário, atualiza sem criar duplicata
            cursor.execute(
                """UPDATE inventario
                   SET categoria = ?, quantidade = ?, unidade = ?,
                       validade = COALESCE(?, validade), atualizado_em = CURRENT_TIMESTAMP
                   WHERE id = ? AND usuario_id = ?""",
                (categoria, quantidade, unidade, validade, existente["id"], usuario_id),
            )
            atualizados += 1
        else:
            cursor.execute(
                """INSERT INTO inventario (usuario_id, nome, categoria, quantidade, unidade, validade)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (usuario_id, nome, categoria, quantidade, unidade, validade),
            )
            inseridos += 1

@bp_ingrediente.get("")
@bp_ingrediente.get("/listar")
def listar_itens_inventario():
    """Lista todos os itens do inventário do usuário logado."""
    if "usuario_id" not in session:
        return _nao_autenticado()

    conn = obter_conexao()
    linhas = conn.execute(
        "SELECT id, nome, categoria, quantidade, unidade, validade, atualizado_em "
        "FROM inventario WHERE usuario_id = ? ORDER BY nome COLLATE NOCASE",
        (session["usuario_id"],),
    ).fetchall()
    conn.close()

    itens = [dict(l) for l in linhas]
    return jsonify({"itens": itens, "total": len(itens)}), 200


@bp_ingrediente.delete("/<int:item_id>")
def remover_item_inventario(item_id: int):
    """Remove um item do inventário garantindo que pertence ao usuário logado."""
    if "usuario_id" not in session:
        return _nao_autenticado()

    conn = obter_conexao()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM inventario WHERE id = ? AND usuario_id = ?",
        (item_id, session["usuario_id"]),
    )
    removidos = cursor.rowcount
    conn.commit()
    conn.close()

    if removidos == 0:
        return jsonify({"erro": "Ingrediente não encontrado no seu inventário."}), 404

    return jsonify({"ok": True, "id": item_id, "mensagem": "Ingrediente removido com sucesso!"}), 200

@bp_ingrediente.post("/adicionar")
def adicionar_item_digitando():
    """Permite cadastrar um ingrediente digitando nome, quantidade, unidade, categoria e validade."""
    if "usuario_id" not in session:
        return _nao_autenticado()

    dados = request.get_json(silent=True) or request.form.to_dict() or {}
    nome = str(dados.get("nome", "")).strip()[:100]
    categoria = str(dados.get("categoria", "Outros")).strip()[:50] or "Outros"
    qtd_bruta = str(dados.get("quantidade", "")).strip()
    unid_bruta = str(dados.get("unidade", "")).strip()
    validade = str(dados.get("validade", "")).strip() or None

    if not nome:
        return jsonify({"erro": "Informe o nome do ingrediente."}), 400
    if not qtd_bruta:
        return jsonify({"erro": "Informe a quantidade do ingrediente."}), 400

    usuario_id = session["usuario_id"]
    quantidade, unidade = _formatar_qtd_unidade(qtd_bruta, unid_bruta)

    conn = obter_conexao()
    duplicado = _buscar_duplicado(conn, usuario_id, nome)
    if duplicado:
        conn.close()
        return jsonify({
            "erro": f"O ingrediente '{duplicado['nome']}' já está cadastrado no seu inventário."
        }), 409

    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO inventario (usuario_id, nome, categoria, quantidade, unidade, validade)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (usuario_id, nome, categoria, quantidade, unidade, validade),
    )
    novo_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return jsonify({
        "mensagem": "Ingrediente adicionado com sucesso!",
        "item": {
            "id": novo_id,
            "nome": nome,
            "categoria": categoria,
            "quantidade": quantidade,
            "unidade": unidade,
            "validade": validade,
        },
    }), 201

@bp_ingrediente.put("/<int:item_id>")
@bp_ingrediente.patch("/<int:item_id>")
def editar_item_inventario(item_id: int):
    """Permite corrigir quantidade, unidade, validade, categoria ou nome de um item já salvo."""
    if "usuario_id" not in session:
        return _nao_autenticado()

    usuario_id = session["usuario_id"]
    dados = request.get_json(silent=True) or request.form.to_dict() or {}

    conn = obter_conexao()
    cursor = conn.cursor()

    atual = cursor.execute(
        "SELECT * FROM inventario WHERE id = ? AND usuario_id = ?",
        (item_id, usuario_id),
    ).fetchone()

    if not atual:
        conn.close()
        return jsonify({"erro": "Ingrediente não encontrado no seu inventário."}), 404

    novo_nome = str(dados.get("nome", atual["nome"])).strip()[:100]
    nova_categoria = str(dados.get("categoria", atual["categoria"])).strip()[:50] or "Outros"
    qtd_bruta = str(dados.get("quantidade", atual["quantidade"])).strip()
    unid_bruta = str(dados.get("unidade", atual["unidade"] or "")).strip()
    nova_validade = dados.get("validade", atual["validade"])
    nova_validade = str(nova_validade).strip() if nova_validade else None

    if not novo_nome:
        conn.close()
        return jsonify({"erro": "O nome do ingrediente não pode ficar vazio."}), 400
    if not qtd_bruta:
        conn.close()
        return jsonify({"erro": "A quantidade não pode ficar vazia."}), 400

    # Verifica se o novo nome cria duplicidade com OUTRO item já salvo do mesmo usuário
    conflito = _buscar_duplicado(conn, usuario_id, novo_nome, ignorar_id=item_id)
    if conflito:
        conn.close()
        return jsonify({
            "erro": f"Já existe outro ingrediente com o nome '{conflito['nome']}' no seu inventário."
        }), 409

    nova_qtd, nova_unid = _formatar_qtd_unidade(qtd_bruta, unid_bruta)

    cursor.execute(
        """UPDATE inventario
           SET nome = ?, categoria = ?, quantidade = ?, unidade = ?, validade = ?,
               atualizado_em = CURRENT_TIMESTAMP
           WHERE id = ? AND usuario_id = ?""",
        (novo_nome, nova_categoria, nova_qtd, nova_unid, nova_validade, item_id, usuario_id),
    )
    conn.commit()
    conn.close()

    return jsonify({
        "mensagem": "Ingrediente atualizado com sucesso!",
        "item": {
            "id": item_id,
            "nome": novo_nome,
            "categoria": nova_categoria,
            "quantidade": nova_qtd,
            "unidade": nova_unid,
            "validade": nova_validade,
        },
    }), 200