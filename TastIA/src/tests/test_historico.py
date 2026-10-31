"""Testes da rota de gerar (salvar / erro de inventário vazio) e do histórico de receitas.

Rodam sem modelo e sem internet, com um banco SQLite temporário.
  python tests/test_historico.py        (ou: python -m pytest tests/test_historico.py)
"""
import os
import sys
import tempfile
from types import SimpleNamespace

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, RAIZ)

from receitas.historico import inferir_categoria, interpretar_receita

RECEITA = """# Arroz com ovo e tomate
**Tempo de preparo:** 1 hora e 30 minutos
**Porções:** 2
## Ingredientes
- 1 xícara de arroz
- 2 ovos
- 1 tomate picado
- Sal a gosto
## Modo de preparo
1. Refogue o tomate.
2. Junte o arroz e os ovos.
"""

RECEITA_FORA = RECEITA.replace("- 2 ovos", "- 200 g de frango")


# --------------------------------------------------------------------------- #
# Interpretação do texto e categorias
# --------------------------------------------------------------------------- #
def test_interpretar_receita():
    r = interpretar_receita(RECEITA, "almoço rápido")
    assert r["titulo"] == "Arroz com ovo e tomate"
    assert r["tempo_min"] == 90 and r["porcoes"] == 2
    assert r["ingredientes"][0] == "1 xícara de arroz" and len(r["ingredientes"]) == 4
    assert r["preparo"] == ["Refogue o tomate.", "Junte o arroz e os ovos."]
    assert r["categoria"] == "Almoço"


def test_interpretar_texto_fora_do_formato_nao_quebra():
    r = interpretar_receita("qualquer coisa solta", "jantar leve")
    assert r["ingredientes"] == [] and r["preparo"] == []
    assert r["titulo"] == "qualquer coisa solta"[:60] or r["titulo"]
    assert r["categoria"] == "Jantar"


def test_categorias():
    assert inferir_categoria("almoço com batata doce", "") == "Almoço"
    assert inferir_categoria("quero um doce", "") == "Sobremesa"
    assert inferir_categoria("algo rápido", "Bolo de banana") == "Sobremesa"
    assert inferir_categoria("café da manhã saudável", "Omelete") == "Café da manhã"
    assert inferir_categoria("lanche da tarde", "") == "Lanche"
    assert inferir_categoria("qualquer", "Arroz") == "Outros"


# --------------------------------------------------------------------------- #
# API com banco temporário
# --------------------------------------------------------------------------- #
class GeradorFalso:
    def __init__(self, texto):
        self.texto, self.chamadas = texto, 0

    def gerar_de_prompt(self, prompt, max_tokens=400):
        self.chamadas += 1
        return SimpleNamespace(texto=self.texto, backend="falso")


def _montar(texto_receita=RECEITA):
    from flask import Flask
    import banco_dados.database as dbm
    tmp = tempfile.mkdtemp()
    dbm.DB_DIR, dbm.DB_PATH = tmp, os.path.join(tmp, "teste.db")
    from banco_dados.create_db import criar_tabelas
    criar_tabelas()
    conn = dbm.obter_conexao()
    for nome in ("Ana", "Beto"):
        conn.execute("INSERT INTO usuarios (nome, email, senha_hash) VALUES (?, ?, 'x')", (nome, nome + "@t.com"))
    conn.commit()
    conn.close()

    import rotas.receita as rr
    gerador = GeradorFalso(texto_receita)
    rr.gerar_receita = lambda *a, **k: rr_original(*a, gerador=gerador, **k)
    app = Flask(__name__)
    app.secret_key = "teste"
    app.register_blueprint(rr.bp_receita)
    return app, dbm, gerador


import rotas.receita as _rr  # noqa: E402
rr_original = _rr.gerar_receita


def _cliente(app, usuario_id):
    c = app.test_client()
    if usuario_id:
        with c.session_transaction() as s:
            s["usuario_id"] = usuario_id
    return c


CORPO = {"pedido": "almoço rápido", "ingredientes": "arroz, ovos, tomate"}


def test_gerar_valida_salva_no_historico():
    app, dbm, _ = _montar()
    r = _cliente(app, 1).post("/api/receita/gerar", json=CORPO)
    assert r.status_code == 200 and r.json["valida"] and r.json["salva"]
    assert r.json["receita_id"] == 1
    h = _cliente(app, 1).get("/api/receita/historico").json
    assert h["total"] == 1 and h["receitas"][0]["titulo"] == "Arroz com ovo e tomate"
    assert h["receitas"][0]["criado_em"].endswith("Z")


def test_gerar_invalida_nao_salva():
    app, dbm, _ = _montar(RECEITA_FORA)
    r = _cliente(app, 1).post("/api/receita/gerar", json=CORPO)
    assert r.status_code == 200 and not r.json["valida"] and not r.json["salva"]
    assert r.json["receita_id"] is None
    assert _cliente(app, 1).get("/api/receita/historico").json["total"] == 0


def test_inventario_vazio_da_erro_claro_sem_chamar_o_modelo():
    app, dbm, gerador = _montar()
    r = _cliente(app, 1).post("/api/receita/gerar", json={"pedido": "almoço", "ingredientes": ""})
    assert r.status_code == 400
    assert r.json["codigo"] == "inventario_vazio"
    assert "inventário está vazio" in r.json["erro"]
    assert r.json["acao_url"] == "/cadastrar_ingrediente"
    assert gerador.chamadas == 0


def test_todos_vencidos_da_erro_claro():
    app, dbm, gerador = _montar()
    conn = dbm.obter_conexao()
    conn.execute("INSERT INTO inventario (usuario_id, nome, categoria, quantidade, validade) "
                 "VALUES (1, 'Leite', 'Laticínios', '1 l', '2020-01-01')")
    conn.commit()
    conn.close()
    r = _cliente(app, 1).post("/api/receita/gerar", json={"pedido": "algo", "ingredientes": ""})
    assert r.status_code == 400 and r.json["codigo"] == "inventario_vazio"
    assert "vencidos" in r.json["erro"] and gerador.chamadas == 0


def test_historico_ordem_e_isolamento_entre_usuarios():
    app, dbm, _ = _montar()
    conn = dbm.obter_conexao()
    for uid, pedido, ts in [(1, "jantar antigo", "2026-10-01 10:00:00"),
                            (1, "almoço novo", "2026-10-29 12:00:00"),
                            (2, "receita do Beto", "2026-10-30 08:00:00")]:
        conn.execute("INSERT INTO receitas (usuario_id, pedido, conteudo, criado_em) VALUES (?,?,?,?)",
                     (uid, pedido, RECEITA, ts))
    conn.commit()
    conn.close()
    h = _cliente(app, 1).get("/api/receita/historico").json
    assert [x["pedido"] for x in h["receitas"]] == ["almoço novo", "jantar antigo"]
    assert _cliente(app, 2).get("/api/receita/historico").json["total"] == 1


def test_excluir_remove_receita_e_bebidas_ligadas():
    app, dbm, _ = _montar()
    _cliente(app, 1).post("/api/receita/gerar", json=CORPO)
    conn = dbm.obter_conexao()
    conn.execute("INSERT INTO bebidas_sugeridas (receita_id, nome_bebida, justificativa) VALUES (1,'Suco','combina')")
    conn.commit()
    conn.close()
    r = _cliente(app, 1).delete("/api/receita/historico/1")
    assert r.status_code == 200 and r.json["ok"]
    assert _cliente(app, 1).get("/api/receita/historico").json["total"] == 0
    conn = dbm.obter_conexao()
    assert conn.execute("SELECT COUNT(*) FROM bebidas_sugeridas").fetchone()[0] == 0
    conn.close()


def test_nao_exclui_receita_de_outro_usuario_nem_inexistente():
    app, dbm, _ = _montar()
    _cliente(app, 1).post("/api/receita/gerar", json=CORPO)
    assert _cliente(app, 2).delete("/api/receita/historico/1").status_code == 404
    assert _cliente(app, 1).delete("/api/receita/historico/999").status_code == 404
    assert _cliente(app, 1).get("/api/receita/historico").json["total"] == 1


def test_sem_login_retorna_401():
    app, _, _ = _montar()
    c = _cliente(app, None)
    assert c.get("/api/receita/historico").status_code == 401
    assert c.delete("/api/receita/historico/1").status_code == 401
    assert c.post("/api/receita/gerar", json=CORPO).status_code == 401


if __name__ == "__main__":
    testes = [f for n, f in sorted(globals().items()) if n.startswith("test_")]
    for t in testes:
        t()
        print("ok  ", t.__name__)
    print(f"\n{len(testes)} testes passaram.")
