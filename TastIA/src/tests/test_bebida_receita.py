"""Testes: bebida salva com o id da receita (ou sozinha), histórico com os dois tipos,
validade na geração e limpeza do texto da receita.

Rodam sem modelo e sem internet (usam as fixtures de conftest.py).
  python -m pytest tests/test_bebida_receita.py
"""
from datetime import date
from types import SimpleNamespace

from receitas.formatador import formatar_receita, limpar_markdown
from receitas.gerador import gerar_receita, preparar_inventario

RECEITA = """Arroz com ovo e tomate
Tempo de preparo: 20 minutos
Porções: 2

Ingredientes
- 1 xícara de arroz
- 2 ovos
- 1 tomate picado

Modo de preparo
1. Refogue o tomate.
2. Junte o arroz e os ovos.
"""


def _criar_receita(usuario_id, conteudo=RECEITA, pedido="almoço rápido"):
    from banco_dados.database import obter_conexao
    c = obter_conexao()
    try:
        cur = c.execute("INSERT INTO receitas (usuario_id, pedido, conteudo) VALUES (?, ?, ?)",
                        (usuario_id, pedido, conteudo))
        c.commit()
        return cur.lastrowid
    finally:
        c.close()


# --------------------------------------------------------------------------- #
# Bebida ligada à receita / bebida sozinha
# --------------------------------------------------------------------------- #
def test_bebida_com_receita_usa_o_mesmo_id(client_logado, usuario, conn):
    rid = _criar_receita(usuario["id"])
    r = client_logado.post("/api/bebida/escolher", json={
        "nome_bebida": "Suco de laranja", "justificativa": "combina", "receita_id": rid, "refeicao": "Arroz"})
    assert r.status_code == 200 and r.json["vinculada"] and r.json["receita_id"] == rid
    linha = conn.execute("SELECT receita_id, refeicao FROM bebidas_sugeridas").fetchone()
    assert linha["receita_id"] == rid and linha["refeicao"] == "Arroz"


def test_bebida_sozinha_sem_receita(client_logado, conn):
    r = client_logado.post("/api/bebida/escolher", json={"nome_bebida": "Chá gelado", "justificativa": "leve"})
    assert r.status_code == 200 and not r.json["vinculada"] and r.json["receita_id"] is None
    assert conn.execute("SELECT receita_id FROM bebidas_sugeridas").fetchone()["receita_id"] is None


def test_receita_de_outro_usuario_ou_inexistente_salva_bebida_sozinha(client_logado, criar_usuario, conn):
    outro = criar_usuario()
    rid_outro = _criar_receita(outro["id"])
    for rid in (rid_outro, 999):
        r = client_logado.post("/api/bebida/escolher", json={"nome_bebida": "Suco", "receita_id": rid})
        assert r.status_code == 200 and not r.json["vinculada"]
    assert conn.execute("SELECT COUNT(*) FROM bebidas_sugeridas WHERE receita_id IS NULL").fetchone()[0] == 2


def test_receita_id_invalido_da_400(client_logado):
    r = client_logado.post("/api/bebida/escolher", json={"nome_bebida": "Suco", "receita_id": "abc"})
    assert r.status_code == 400


def test_mesma_bebida_na_mesma_receita_nao_duplica(client_logado, usuario, conn):
    rid = _criar_receita(usuario["id"])
    corpo = {"nome_bebida": "Suco de laranja", "receita_id": rid}
    client_logado.post("/api/bebida/escolher", json=corpo)
    r = client_logado.post("/api/bebida/escolher", json=corpo)
    assert r.status_code == 200 and r.json["vinculada"]
    assert conn.execute("SELECT COUNT(*) FROM bebidas_sugeridas").fetchone()[0] == 1


def test_escolher_sem_login_e_sem_nome(app, client_logado):
    assert app.test_client().post("/api/bebida/escolher", json={"nome_bebida": "Suco"}).status_code == 401
    assert client_logado.post("/api/bebida/escolher", json={"nome_bebida": " "}).status_code == 400


# --------------------------------------------------------------------------- #
# Histórico com os dois tipos
# --------------------------------------------------------------------------- #
def test_historico_traz_receita_com_bebida_e_bebida_avulsa(client_logado, usuario):
    rid = _criar_receita(usuario["id"])
    client_logado.post("/api/bebida/escolher", json={"nome_bebida": "Suco de laranja", "receita_id": rid})
    client_logado.post("/api/bebida/escolher", json={"nome_bebida": "Chá gelado", "refeicao": "lanche"})
    h = client_logado.get("/api/receita/historico").json
    assert h["total"] == 1 and h["total_bebidas"] == 2
    assert [b["nome"] for b in h["receitas"][0]["bebidas"]] == ["Suco de laranja"]
    assert [b["nome"] for b in h["bebidas"]] == ["Chá gelado"]
    assert h["bebidas"][0]["refeicao"] == "lanche" and h["bebidas"][0]["criado_em"].endswith("Z")


def test_historico_nao_mistura_usuarios(client_logado, criar_usuario, logar, app):
    outro = criar_usuario()
    c2 = logar(app.test_client(), outro)
    c2.post("/api/bebida/escolher", json={"nome_bebida": "Suco do outro"})
    h = client_logado.get("/api/receita/historico").json
    assert h["total_bebidas"] == 0 and h["bebidas"] == []


def test_excluir_bebida_avulsa_e_isolamento(client_logado, criar_usuario, logar, app):
    bid = client_logado.post("/api/bebida/escolher", json={"nome_bebida": "Suco"}).json["bebida_id"]
    c2 = logar(app.test_client(), criar_usuario())
    assert c2.delete(f"/api/bebida/historico/{bid}").status_code == 404
    assert client_logado.delete(f"/api/bebida/historico/{bid}").status_code == 200
    assert client_logado.delete(f"/api/bebida/historico/{bid}").status_code == 404
    assert client_logado.get("/api/receita/historico").json["total_bebidas"] == 0


def test_excluir_receita_apaga_as_bebidas_ligadas_e_mantem_as_avulsas(client_logado, usuario):
    rid = _criar_receita(usuario["id"])
    client_logado.post("/api/bebida/escolher", json={"nome_bebida": "Suco", "receita_id": rid})
    client_logado.post("/api/bebida/escolher", json={"nome_bebida": "Chá"})
    assert client_logado.delete(f"/api/receita/historico/{rid}").status_code == 200
    h = client_logado.get("/api/receita/historico").json
    assert h["total"] == 0 and h["total_bebidas"] == 1 and h["bebidas"][0]["nome"] == "Chá"


def test_historico_limpa_receita_antiga_com_markdown(client_logado, usuario):
    antiga = "# Arroz\n**Tempo de preparo:** 10 minutos\n## Ingredientes\n- 1 xícara de arroz\n## Modo de preparo\n1. Cozinhe."
    _criar_receita(usuario["id"], antiga)
    item = client_logado.get("/api/receita/historico").json["receitas"][0]
    assert "#" not in item["texto"] and "**" not in item["texto"] and item["titulo"] == "Arroz"


# --------------------------------------------------------------------------- #
# Texto da receita limpo
# --------------------------------------------------------------------------- #
BRUTO = """Claro! Aqui está a receita:
# **Arroz com ovo e tomate**
**Tempo de preparo:** 20 minutos
**Porções:** 2
## Ingredientes
* 1 xícara de arroz
* **2 ovos**
- 1 tomate picado
## Modo de preparo
1. Refogue o *tomate* picado
2) Junte o arroz e os ovos.
Dica: acompanhe com queijo.
"""


def test_formatar_receita_sem_markdown_nem_texto_solto():
    t = formatar_receita(BRUTO)
    assert t.startswith("Arroz com ovo e tomate\nTempo de preparo: 20 minutos\nPorções: 2\n")
    assert "#" not in t and "*" not in t and "Claro" not in t and "Dica" not in t and "queijo" not in t
    assert "- 2 ovos" in t and "1. Refogue o tomate picado." in t and "2. Junte o arroz e os ovos." in t
    assert formatar_receita(t) == t   # idempotente


def test_formatar_remove_ultimo_passo_cortado():
    t = formatar_receita(BRUTO.replace("Dica: acompanhe com queijo.", "3. Deixe descansar por alguns"))
    assert "descansar" not in t and t.rstrip().endswith("2. Junte o arroz e os ovos.")


def test_limpar_markdown_remove_think_e_tokens():
    assert limpar_markdown("<think>x</think>**Oi**<|im_end|>") == "Oi"


def test_formatar_sem_secoes_devolve_texto_limpo():
    assert formatar_receita("**qualquer** coisa") == "qualquer coisa"


# --------------------------------------------------------------------------- #
# Validade na geração
# --------------------------------------------------------------------------- #
class GeradorSequencia:
    def __init__(self, *textos):
        self.textos, self.chamadas, self.prompts = list(textos), 0, []

    def gerar_de_prompt(self, prompt, max_tokens=400):
        self.prompts.append(prompt)
        texto = self.textos[min(self.chamadas, len(self.textos) - 1)]
        self.chamadas += 1
        return SimpleNamespace(texto=texto, backend="falso")


HOJE = date(2026, 11, 8)
INVENTARIO = [
    {"nome": "Arroz"},
    {"nome": "Tomate", "validade": "2026-12-30"},
    {"nome": "Ovos", "validade": "2026-11-09"},
]
SEM_OVO = RECEITA.replace("- 2 ovos\n", "").replace(" e os ovos", "")


def test_preparar_inventario_ordena_por_validade():
    ativos, _ = preparar_inventario(INVENTARIO, HOJE)
    assert [i["nome"] for i in ativos] == ["Ovos", "Tomate", "Arroz"]


def test_prompt_marca_prioridade_alta_e_ordena():
    g = GeradorSequencia(RECEITA)
    gerar_receita(INVENTARIO, "almoço", gerador=g, hoje=HOJE)
    prompt = g.prompts[0]
    assert "PRIORIDADE ALTA: vence amanhã" in prompt
    assert prompt.index("- Ovos") < prompt.index("- Tomate") < prompt.index("- Arroz")


def test_refaz_quando_receita_ignora_item_que_vence_logo():
    g = GeradorSequencia(SEM_OVO, RECEITA)
    r = gerar_receita(INVENTARIO, "almoço", gerador=g, hoje=HOJE)
    assert g.chamadas == 2 and r.tentativas == 2
    assert "Ovos" in "".join(r.urgentes_usados) and not r.urgentes_nao_usados
    assert "- 2 ovos" in r.texto
    assert "Ovos" in g.prompts[1].split("CORREÇÃO:")[1]


def test_nao_refaz_quando_ja_usou_o_que_vence_logo():
    g = GeradorSequencia(RECEITA)
    r = gerar_receita(INVENTARIO, "almoço", gerador=g, hoje=HOJE)
    assert g.chamadas == 1 and r.valida and r.urgentes_usados == ["Ovos"]


def test_texto_da_receita_gerada_sai_sem_markdown():
    r = gerar_receita(INVENTARIO, "almoço", gerador=GeradorSequencia(BRUTO), hoje=HOJE)
    assert r.valida and "#" not in r.texto and "*" not in r.texto
