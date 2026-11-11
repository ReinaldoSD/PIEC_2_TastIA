from datetime import date
import re
from typing import Dict, List, Optional, Tuple
from flask import Blueprint, jsonify, request, session

from banco_dados.database import obter_conexao
from percepcao.catalogo import LISTA_OFICIAL_INGREDIENTES, SINONIMOS_NORMALIZADOS
from percepcao.pipeline import obter_pipeline
from receitas.validador import normalizar_texto
from servicos.fila import obter_fila, ESTADO_CONCLUIDO, ESTADO_ERRO, ESTADO_PENDENTE
from servicos.imagem_servico import receber_e_reduzir_imagem

bp_ingrediente = Blueprint("ingrediente", __name__, url_prefix="/api/ingredientes")

# A lista oficial de ingredientes (autocomplete, Issue #45) vem do catálogo único em
# percepcao/catalogo.py: é a mesma que o classificador de imagens usa.


def _nao_autenticado():
    return jsonify({"erro": "Faça login para continuar."}), 401


def _validar_data_iso(valor: Optional[str]) -> Optional[str]:
    """Valida se a data está no formato AAAA-MM-DD."""
    if not valor:
        return None
    texto = str(valor).strip()[:10]
    try:
        date.fromisoformat(texto)
        return texto
    except ValueError:
        raise ValueError(f"Data de validade inválida: '{valor}'. Use o formato AAAA-MM-DD.")


def _validade_mais_proxima(val_atual: Optional[str], val_nova: Optional[str]) -> Optional[str]:
    """Issue #19: Mantém sempre a data de validade mais próxima (menor data ISO)."""
    d1 = _validar_data_iso(val_atual) if val_atual else None
    d2 = _validar_data_iso(val_nova) if val_nova else None
    if d1 and d2:
        return min(d1, d2)
    return d1 or d2


def _extrair_numero_e_unidade(qtd_bruta: str, unidade_bruta: str = "") -> Tuple[float, str, str]:
    """Extrai (numero_float, unidade_limpa, string_formatada) de quantidade e unidade."""
    qtd_str = str(qtd_bruta or "").strip()
    unid_str = str(unidade_bruta or "").strip()

    m = re.match(r"^(\d+(?:[.,]\d+)?)\s*(.*)$", qtd_str)
    if m:
        num = float(m.group(1).replace(",", "."))
        resto = m.group(2).strip()
        unidade = unid_str or resto or "unidade"
    else:
        num = 1.0
        unidade = unid_str or qtd_str or "unidade"

    num_fmt = int(num) if num.is_integer() else round(num, 2)
    if unidade in ("unidade", "unidades"):
        unidade_exibicao = "unidade" if num_fmt == 1 else "unidades"
    else:
        unidade_exibicao = unidade

    texto_final = f"{num_fmt} {unidade_exibicao}".strip()[:50]
    return num, unidade_exibicao[:30], texto_final


def _formatar_qtd_unidade(qtd_bruta: str, unidade_bruta: str = "") -> Tuple[str, str]:
    """Mantém assinatura compatível `(qtd_formatada, unidade)`."""
    _, unid, texto = _extrair_numero_e_unidade(qtd_bruta, unidade_bruta)
    return texto, unid


def _somar_quantidades(qtd_antiga: str, unid_antiga: str, qtd_nova: str, unid_nova: str) -> Tuple[str, str]:
    """Issue #19: Soma as quantidades quando um item já existente é adicionado/confirmado."""
    n1, u1, _ = _extrair_numero_e_unidade(qtd_antiga, unid_antiga)
    n2, u2, _ = _extrair_numero_e_unidade(qtd_nova, unid_nova)
    soma = n1 + n2
    _, unid_final, texto_final = _extrair_numero_e_unidade(str(soma), u1 or u2)
    return texto_final, unid_final


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

@bp_ingrediente.get("/sugestoes")
def sugestoes_ingredientes():
    """Recebe o começo de um nome (?q=...) e devolve até 8 ingredientes da lista oficial."""
    termo = (
        request.args.get("q")
        or request.args.get("prefixo")
        or request.args.get("nome")
        or ""
    ).strip()
    chave = normalizar_texto(termo)

    if not chave:
        sugestoes = LISTA_OFICIAL_INGREDIENTES[:8]
    else:
        comecam = []
        contem = []
        vistos = set()
        for item in LISTA_OFICIAL_INGREDIENTES:
            nome_norm = normalizar_texto(item["nome"])
            if nome_norm in vistos:
                continue
            sinonimos = SINONIMOS_NORMALIZADOS.get(item["nome"], [])
            if nome_norm.startswith(chave):
                vistos.add(nome_norm)
                comecam.append(item)
            elif chave in nome_norm or any(chave in s for s in sinonimos):
                vistos.add(nome_norm)
                contem.append(item)
        sugestoes = (comecam + contem)[:8]

    return jsonify({
        "sugestoes": [s["nome"] for s in sugestoes],
        "itens": sugestoes,
        "total": len(sugestoes),
    }), 200


@bp_ingrediente.post("/reduzir")
def rota_reduzir_foto():
    """Issue #24: Recebe e reduz a foto enviada devolvendo os metadados."""
    if "usuario_id" not in session:
        return _nao_autenticado()

    if "imagem" not in request.files:
        return jsonify({"erro": "Nenhuma imagem foi enviada na requisição."}), 400

    arquivo = request.files["imagem"]
    if not arquivo or not arquivo.filename:
        return jsonify({"erro": "Arquivo de imagem vazio ou não selecionado."}), 400

    try:
        _, metadados = receber_e_reduzir_imagem(arquivo.read(), arquivo.filename)
        return jsonify(metadados), 200
    except ValueError as e:
        return jsonify({"erro": str(e)}), 400


@bp_ingrediente.post("/detectar")
def detectar_ingredientes():
    if "usuario_id" not in session:
        return _nao_autenticado()

    if "imagem" not in request.files:
        return jsonify({"erro": "Nenhuma imagem foi enviada na requisição."}), 400

    arquivo = request.files["imagem"]
    if not arquivo or not arquivo.filename or arquivo.filename.strip() == "":
        return jsonify({"erro": "Arquivo de imagem vazio ou não selecionado."}), 400

    # Usa o serviço da Issue #24 para validar (400 se inválida) e reduzir a imagem
    try:
        imagem, meta_imagem = receber_e_reduzir_imagem(arquivo.read(), arquivo.filename)
    except ValueError as e:
        return jsonify({"erro": str(e)}), 400

    assincrono = request.form.get("assincrono", "false").lower() == "true"

    if assincrono:
        fila = obter_fila()

        def _tarefa_deteccao():
            pipeline = obter_pipeline()
            res = pipeline.executar(imagem)
            res["imagem"] = meta_imagem
            return res

        tarefa_id = fila.submeter(_tarefa_deteccao)
        return jsonify({"tarefa_id": tarefa_id, "status": ESTADO_PENDENTE, "imagem": meta_imagem}), 202

    try:
        pipeline = obter_pipeline()
        resultado = pipeline.executar(imagem)
        resultado["imagem"] = meta_imagem
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
    """Salva no banco os ingredientes marcados após a foto, exigindo validade e somando duplicados."""
    if "usuario_id" not in session:
        return _nao_autenticado()

    dados = request.get_json(silent=True) or {}
    itens = dados.get("itens", [])

    if not isinstance(itens, list) or not itens:
        return jsonify({"erro": "Nenhum ingrediente informado para salvar."}), 400

    usuario_id = session["usuario_id"]
    conn = obter_conexao()
    cursor = conn.cursor()

    chaves_inseridas = set()
    chaves_atualizadas = set()
    ignorados_desmarcados = 0

    try:
        for item in itens:
            marcado = item.get("marcado", item.get("confirmado", True))
            if not marcado:
                ignorados_desmarcados += 1
                continue

            nome = str(item.get("nome", "")).strip()[:100]
            if not nome:
                continue

            validade_bruta = str(item.get("validade") or "").strip()
            if not validade_bruta:
                conn.close()
                return jsonify({
                    "erro": f"A data de validade é obrigatória para cadastrar o ingrediente '{nome}'."
                }), 400

            validade = _validar_data_iso(validade_bruta)
            categoria = str(item.get("categoria", "Outros")).strip()[:50] or "Outros"
            quantidade, unidade = _formatar_qtd_unidade(
                item.get("quantidade", "1 unidade"), item.get("unidade", "")
            )
            chave_nome = normalizar_texto(nome)

            existente = _buscar_duplicado(conn, usuario_id, nome)
            if existente:
                nova_qtd, nova_unid = _somar_quantidades(
                    existente["quantidade"], existente.get("unidade") or "", quantidade, unidade
                )
                menor_validade = _validade_mais_proxima(existente["validade"], validade)
                cursor.execute(
                    """UPDATE inventario
                       SET categoria = ?, quantidade = ?, unidade = ?, validade = ?,
                           atualizado_em = CURRENT_TIMESTAMP
                       WHERE id = ? AND usuario_id = ?""",
                    (categoria, nova_qtd, nova_unid, menor_validade, existente["id"], usuario_id),
                )
                if chave_nome not in chaves_inseridas:
                    chaves_atualizadas.add(chave_nome)
            else:
                cursor.execute(
                    """INSERT INTO inventario (usuario_id, nome, categoria, quantidade, unidade, validade)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (usuario_id, nome, categoria, quantidade, unidade, validade),
                )
                chaves_inseridas.add(chave_nome)

        conn.commit()
    except ValueError as e:
        conn.close()
        return jsonify({"erro": str(e)}), 400

    conn.close()
    inseridos = len(chaves_inseridas)
    atualizados = len(chaves_atualizadas)
    salvos = inseridos + atualizados

    if salvos == 0:
        return jsonify({"erro": "Nenhum ingrediente marcado ou válido para salvar."}), 400

    return jsonify({
        "mensagem": f"{salvos} ingrediente(s) confirmado(s) no inventário!",
        "salvos": salvos,
        "inseridos": inseridos,
        "atualizados": atualizados,
        "ignorados": ignorados_desmarcados,
    }), 200

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
    """Cadastra ingrediente digitando; se já existir, soma quantidade e mantém a validade mais próxima."""
    if "usuario_id" not in session:
        return _nao_autenticado()

    dados = request.get_json(silent=True) or request.form.to_dict() or {}
    nome = str(dados.get("nome", "")).strip()[:100]
    categoria = str(dados.get("categoria", "Outros")).strip()[:50] or "Outros"
    qtd_bruta = str(dados.get("quantidade", "")).strip()
    unid_bruta = str(dados.get("unidade", "")).strip()
    validade_bruta = str(dados.get("validade") or "").strip() or None

    if not nome:
        return jsonify({"erro": "Informe o nome do ingrediente."}), 400
    if not qtd_bruta:
        return jsonify({"erro": "Informe a quantidade do ingrediente."}), 400

    try:
        validade = _validar_data_iso(validade_bruta)
    except ValueError as e:
        return jsonify({"erro": str(e)}), 400

    usuario_id = session["usuario_id"]
    quantidade, unidade = _formatar_qtd_unidade(qtd_bruta, unid_bruta)

    conn = obter_conexao()
    cursor = conn.cursor()
    existente = _buscar_duplicado(conn, usuario_id, nome)

    if existente:
        # Issue #19: Soma a quantidade e mantém a validade mais próxima
        nova_qtd, nova_unid = _somar_quantidades(
            existente["quantidade"], existente.get("unidade") or "", quantidade, unidade
        )
        menor_validade = _validade_mais_proxima(existente["validade"], validade)
        cursor.execute(
            """UPDATE inventario
               SET categoria = ?, quantidade = ?, unidade = ?, validade = ?,
                   atualizado_em = CURRENT_TIMESTAMP
               WHERE id = ? AND usuario_id = ?""",
            (categoria, nova_qtd, nova_unid, menor_validade, existente["id"], usuario_id),
        )
        conn.commit()
        conn.close()
        return jsonify({
            "mensagem": "Ingrediente já existia: quantidade somada e validade mais próxima mantida!",
            "somado": True,
            "item": {
                "id": existente["id"],
                "nome": existente["nome"],
                "categoria": categoria,
                "quantidade": nova_qtd,
                "unidade": nova_unid,
                "validade": menor_validade,
            },
        }), 200

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
        "somado": False,
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

    if not novo_nome:
        conn.close()
        return jsonify({"erro": "O nome do ingrediente não pode ficar vazio."}), 400
    if not qtd_bruta:
        conn.close()
        return jsonify({"erro": "A quantidade não pode ficar vazia."}), 400

    try:
        nova_validade = _validar_data_iso(nova_validade) if nova_validade else None
    except ValueError as e:
        conn.close()
        return jsonify({"erro": str(e)}), 400

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
