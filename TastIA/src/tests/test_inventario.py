"""Testes das rotas de inventário, percepção e integração Foto -> Inventário -> Receita.
Cobre as Issues #19, #24, #27, #28, #37, #39, #40 e #45.
Rodar com:
  pytest TastIA/src/tests/test_inventario.py
"""

import io
from types import SimpleNamespace
from PIL import Image


def _bytes_imagem(largura=1800, altura=1200, formato="JPEG") -> bytes:
    img = Image.new("RGB", (largura, altura), color=(200, 60, 60))
    buf = io.BytesIO()
    img.save(buf, format=formato)
    return buf.getvalue()


# --------------------------------------------------------------------------- #
# ISSUE #24 e #27: Receber, reduzir foto e validar erro 400
# --------------------------------------------------------------------------- #
def test_issue_24_receber_e_reduzir_foto(client_logado):
    dados = {"imagem": (io.BytesIO(_bytes_imagem(2000, 1500)), "foto_grande.jpg")}
    r = client_logado.post("/api/ingredientes/reduzir", data=dados, content_type="multipart/form-data")
    assert r.status_code == 200
    assert r.json["foi_reduzida"] is True
    assert r.json["largura_original"] == 2000
    assert r.json["largura"] <= 1024 and r.json["altura"] <= 1024


def test_issue_27_detectar_retorna_400_para_imagem_invalida(client_logado):
    assert client_logado.post("/api/ingredientes/detectar", data={}).status_code == 400

    invalido_ext = {"imagem": (io.BytesIO(b"texto"), "nota.txt")}
    assert client_logado.post("/api/ingredientes/detectar", data=invalido_ext, content_type="multipart/form-data").status_code == 400

    corrompido = {"imagem": (io.BytesIO(b"nao_eh_imagem"), "falso.jpg")}
    assert client_logado.post("/api/ingredientes/detectar", data=corrompido, content_type="multipart/form-data").status_code == 400


# --------------------------------------------------------------------------- #
# VALIDADE OBRIGATÓRIA NA FOTO E ISSUE #19 (SOMAR MANTENDO VALIDADE MAIS PRÓXIMA)
# --------------------------------------------------------------------------- #
def test_confirmar_foto_exige_data_de_validade(client_logado):
    r = client_logado.post("/api/ingredientes/confirmar", json={
        "itens": [{"nome": "Tomate", "categoria": "Verduras e legumes", "quantidade": "2 unidades", "marcado": True}]
    })
    assert r.status_code == 400
    assert "validade" in r.json["erro"].lower()


def test_issue_19_somar_itens_e_manter_validade_mais_proxima(client_logado):
    # 1. Confirma da foto: 2 unidades de Tomate com validade 2026-11-25 (e 1 desmarcado)
    r1 = client_logado.post("/api/ingredientes/confirmar", json={
        "itens": [
            {"nome": "Tomate", "categoria": "Verduras e legumes", "quantidade": "2 unidades", "validade": "2026-11-25", "marcado": True},
            {"nome": "Biscoito", "categoria": "Outros", "quantidade": "1 pacote", "validade": "2026-12-10", "marcado": False},
        ]
    })
    assert r1.status_code == 200
    assert r1.json["inseridos"] == 1 and r1.json["ignorados"] == 1

    # 2. Adiciona mais 3 unidades de Tomate vencendo ANTES (2026-11-14)
    r2 = client_logado.post("/api/ingredientes/adicionar", json={
        "nome": "tomate", "categoria": "Verduras e legumes", "quantidade": "3", "unidade": "unidades", "validade": "2026-11-14"
    })
    assert r2.status_code == 200 and r2.json["somado"] is True
    assert r2.json["item"]["quantidade"] == "5 unidades"
    assert r2.json["item"]["validade"] == "2026-11-14"

    # 3. Confirma mais 2 unidades de Tomate vencendo DEPOIS (2026-12-30) -> deve manter 2026-11-14
    r3 = client_logado.post("/api/ingredientes/confirmar", json={
        "itens": [{"nome": "Tomate", "categoria": "Verduras e legumes", "quantidade": "2 unidades", "validade": "2026-12-30", "marcado": True}]
    })
    assert r3.status_code == 200 and r3.json["atualizados"] == 1

    lista = client_logado.get("/api/ingredientes/listar").json["itens"]
    assert len(lista) == 1
    assert lista[0]["quantidade"] == "7 unidades"
    assert lista[0]["validade"] == "2026-11-14"


# --------------------------------------------------------------------------- #
# ISSUE #45: Rota de sugestões de ingredientes (até 8 da lista oficial)
# --------------------------------------------------------------------------- #
def test_issue_45_sugestoes_ingredientes(client_logado):
    r = client_logado.get("/api/ingredientes/sugestoes?q=ma")
    assert r.status_code == 200
    assert 1 <= len(r.json["sugestoes"]) <= 8
    assert any("Maçã" in s or "Manteiga" in s or "Macarrão" in s for s in r.json["sugestoes"])


# --------------------------------------------------------------------------- #
# ISSUES #28, #37, #39 e #40: Listar, editar todos os campos e remover
# --------------------------------------------------------------------------- #
def test_issues_28_37_39_40_crud_completo_e_isolamento(client, criar_usuario, logar):
    u1 = criar_usuario(nome="Ana", email="ana@tastia.com")
    u2 = criar_usuario(nome="Beto", email="beto@tastia.com")

    logar(client, u1)
    a = client.post("/api/ingredientes/adicionar", json={
        "nome": "Arroz", "categoria": "Grãos e cereais", "quantidade": "1", "unidade": "kg", "validade": "2026-12-01"
    }).json["item"]
    b = client.post("/api/ingredientes/adicionar", json={
        "nome": "Feijão", "categoria": "Grãos e cereais", "quantidade": "1", "unidade": "kg", "validade": "2026-12-15"
    }).json["item"]

    # Impede renomear Feijão para Arroz (duplicidade com outro item) -> 409
    assert client.put(f"/api/ingredientes/{b['id']}", json={"nome": "arroz"}).status_code == 409

    # Edita todos os campos do Arroz -> 200
    r_edit = client.put(f"/api/ingredientes/{a['id']}", json={
        "nome": "Arroz Parboilizado",
        "categoria": "Grãos e cereais",
        "quantidade": "2",
        "unidade": "kg",
        "validade": "2026-11-28"
    })
    assert r_edit.status_code == 200
    assert r_edit.json["item"]["nome"] == "Arroz Parboilizado"
    assert r_edit.json["item"]["quantidade"] == "2 kg"
    assert r_edit.json["item"]["validade"] == "2026-11-28"

    # Usuário 2 não pode editar nem remover o item do Usuário 1
    logar(client, u2)
    assert client.put(f"/api/ingredientes/{a['id']}", json={"nome": "Invasao"}).status_code == 404
    assert client.delete(f"/api/ingredientes/{a['id']}").status_code == 404

    # Usuário 1 remove o próprio item
    logar(client, u1)
    assert client.delete(f"/api/ingredientes/{a['id']}").status_code == 200
    restantes = client.get("/api/ingredientes/listar").json["itens"]
    assert len(restantes) == 1 and restantes[0]["nome"] == "Feijão"


# --------------------------------------------------------------------------- #
# INTEGRAÇÃO: Foto -> Inventário Salvo -> Receita Gerada
# --------------------------------------------------------------------------- #
def test_integracao_foto_inventario_e_gerar_receita(client_logado, monkeypatch):
    import rotas.ingrediente as ri
    import rotas.receita as rr

    # 1. Simula detecção na foto
    class PipelineFalso:
        def executar(self, imagem):
            return {
                "ingredientes": [
                    {"nome": "Ovo", "categoria": "Outros", "quantidade": "3 unidades", "confianca": 0.95},
                    {"nome": "Tomate", "categoria": "Verduras e legumes", "quantidade": "2 unidades", "confianca": 0.89},
                ],
                "total_detectado": 2,
                "usou_plano_b": False,
                "recortes_brutos": 2,
                "tempo_s": 0.1,
                "aviso": None,
            }

    monkeypatch.setattr(ri, "obter_pipeline", lambda: PipelineFalso())
    foto = {"imagem": (io.BytesIO(_bytes_imagem(1600, 1200)), "foto.jpg")}
    r_det = client_logado.post("/api/ingredientes/detectar", data=foto, content_type="multipart/form-data")
    assert r_det.status_code == 200
    assert r_det.json["imagem"]["foi_reduzida"] is True

    # 2. Preenche a validade obrigatória e confirma no inventário
    itens = r_det.json["ingredientes"]
    for i, item in enumerate(itens):
        item["marcado"] = True
        item["validade"] = f"2026-11-2{i}"

    r_conf = client_logado.post("/api/ingredientes/confirmar", json={"itens": itens})
    assert r_conf.status_code == 200 and r_conf.json["salvos"] == 2

    # 3. Gera receita usando o inventário salvo no banco
    class GeradorReceitaMock:
        def gerar_de_prompt(self, prompt, max_tokens=400):
            assert "Ovo" in prompt and "Tomate" in prompt
            texto = (
                "# Omelete de Tomate\n"
                "**Tempo de preparo:** 15 minutos\n**Porções:** 2\n"
                "## Ingredientes\n- 3 ovos\n- 2 tomates\n- Sal a gosto\n"
                "## Modo de preparo\n1. Bata os ovos com o tomate e frite.\n"
            )
            return SimpleNamespace(texto=texto, backend="mock")

    orig_gerar = rr.gerar_receita
    monkeypatch.setattr(rr, "gerar_receita", lambda *a, **k: orig_gerar(*a, gerador=GeradorReceitaMock(), **k))

    r_rec = client_logado.post("/api/receita/gerar", json={"pedido": "Omelete rápida", "tempo": "15", "ingredientes": ""})
    assert r_rec.status_code == 200
    assert r_rec.json["valida"] is True
    assert r_rec.json["salva"] is True