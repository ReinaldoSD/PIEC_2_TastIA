"""Rotas da API de Percepção e Ingredientes (Detecção por Foto e Salvamento em Lote)."""

import io
from flask import Blueprint, jsonify, request, session
from PIL import Image, UnidentifiedImageError

from banco_dados.database import obter_conexao
from percepcao.pipeline import obter_pipeline
from servicos.fila import obter_fila, ESTADO_CONCLUIDO, ESTADO_ERRO, ESTADO_PENDENTE

bp_ingrediente = Blueprint("ingrediente", __name__, url_prefix="/api/ingredientes")

EXTENSOES_PERMITIDAS = {"png", "jpg", "jpeg", "webp", "bmp"}
TAMANHO_MAX_BYTES = 10 * 1024 * 1024  # 10 MB


def _nao_autenticado():
    return jsonify({"erro": "Faça login para continuar."}), 401


def _extensao_valida(nome_arquivo: str) -> bool:
    return "." in nome_arquivo and nome_arquivo.rsplit(".", 1)[1].lower() in EXTENSOES_PERMITIDAS


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


@bp_ingrediente.post("/salvar_lote")
def salvar_lote():
    """Salva no banco os ingredientes revisados/confirmados pelo usuário após a foto."""
    if "usuario_id" not in session:
        return _nao_autenticado()

    dados = request.get_json(silent=True) or {}
    itens = dados.get("itens", [])

    if not isinstance(itens, list) or not itens:
        return jsonify({"erro": "Nenhum ingrediente informado para salvar."}), 400

    conn = obter_conexao()
    cursor = conn.cursor()
    salvos = 0

    for item in itens:
        nome = str(item.get("nome", "")).strip()[:100]
        categoria = str(item.get("categoria", "Outros")).strip()[:50] or "Outros"
        quantidade = str(item.get("quantidade", "1 unidade")).strip()[:50] or "1 unidade"
        validade = str(item.get("validade", "")).strip() or None

        if not nome:
            continue

        cursor.execute(
            "INSERT INTO inventario (usuario_id, nome, categoria, quantidade, validade) VALUES (?, ?, ?, ?, ?)",
            (session["usuario_id"], nome, categoria, quantidade, validade),
        )
        salvos += 1

    conn.commit()
    conn.close()

    if salvos == 0:
        return jsonify({"erro": "Nenhum ingrediente válido para salvar."}), 400

    return jsonify({"mensagem": f"{salvos} ingrediente(s) adicionado(s) ao inventário!", "salvos": salvos}), 200
