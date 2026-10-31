import os
import sys
import time
import types
from datetime import date, timedelta
from types import SimpleNamespace

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, RAIZ)
os.chdir(RAIZ)


class GeradorDemo:
    def gerar_de_prompt(self, prompt, max_tokens=400):
        time.sleep(2)
        usuario = prompt.split("<|im_start|>user\n", 1)[1]
        itens = [l[2:].split(" (")[0] for l in usuario.splitlines() if l.startswith("- ")]
        a, b = (itens + ["sal", "água"])[:2]
        extra = ""
        if "teste-aviso" in usuario.lower():
            extra = "- 200 g de frango\n"
        elif "feijoada" in usuario.lower() and "CORREÇÃO" not in usuario:
            extra = "- 200 g de linguiça\n"
        texto = (
            f"# {a.capitalize()} com {b} (DEMO)\n"
            "**Tempo de preparo:** 15 minutos\n**Porções:** 2\n"
            f"## Ingredientes\n- 1 porção de {a}\n- 2 unidades de {b}\n{extra}- Sal a gosto\n"
            f"## Modo de preparo\n1. Misture {a} e {b}.\n2. Cozinhe, tempere com sal e sirva.\n"
        )
        return SimpleNamespace(texto=texto, backend="demo")


def preparar(limpar: bool = False):
    import config
    config.DB_PATH = os.path.join(config.DB_DIR, "tastia_demo.db")
    if limpar and os.path.exists(config.DB_PATH):
        os.remove(config.DB_PATH)

    falso = types.ModuleType("servicos.modelos_servico")
    falso.baixar_ou_carregar_modelos = lambda: print("[DEMO] download de modelos desativado")
    sys.modules["servicos.modelos_servico"] = falso

    import servicos.gerador_receita as gr
    gr.obter_gerador = lambda: GeradorDemo()

    from app import app
    _semear()
    return app


def _semear():
    from werkzeug.security import generate_password_hash
    from banco_dados.database import obter_conexao

    conn = obter_conexao()
    if conn.execute("SELECT 1 FROM usuarios WHERE email = 'demo@tastia.com'").fetchone():
        conn.close()
        return
    cur = conn.execute("INSERT INTO usuarios (nome, email, senha_hash) VALUES (?, ?, ?)",
                       ("Usuário Demo", "demo@tastia.com", generate_password_hash("demo123")))
    uid = cur.lastrowid
    hoje = date.today()
    inventario = [
        ("Arroz", "Grãos e cereais", "1 kg", None),
        ("Ovos", "Outros", "6 unidades", (hoje + timedelta(days=2)).isoformat()),
        ("Tomate", "Verduras e legumes", "3 unidades", None),
        ("Cebola", "Verduras e legumes", "2 unidades", None),
        ("Leite", "Laticínios", "1 litro", (hoje - timedelta(days=5)).isoformat()),
    ]
    for nome, cat, qtd, val in inventario:
        conn.execute("INSERT INTO inventario (usuario_id, nome, categoria, quantidade, validade) "
                     "VALUES (?, ?, ?, ?, ?)", (uid, nome, cat, qtd, val))

    antigas = [
        ("Quero um café da manhã rápido", "Panqueca de banana", "Café da manhã", "2026-10-20 09:10:00"),
        ("Jantar leve com legumes", "Sopa de abóbora", "Jantar", "2026-10-25 20:30:00"),
        ("Uma sobremesa fácil", "Bolo de caneca", "Sobremesa", "2026-10-28 15:00:00"),
    ]
    for pedido, titulo, _, quando in antigas:
        conteudo = (f"# {titulo}\n**Tempo de preparo:** 20 minutos\n**Porções:** 2\n"
                    "## Ingredientes\n- 2 ovos\n- 1 xícara de arroz\n- Sal a gosto\n"
                    "## Modo de preparo\n1. Misture tudo.\n2. Cozinhe e sirva.\n")
        conn.execute("INSERT INTO receitas (usuario_id, pedido, conteudo, criado_em) VALUES (?, ?, ?, ?)",
                     (uid, pedido, conteudo, quando))
    conn.commit()
    conn.close()
    print("[DEMO] usuário demo@tastia.com criado, com inventário e 3 receitas antigas.")


if __name__ == "__main__":
    app = preparar(limpar="--limpar" in sys.argv)
    print("\n" + "=" * 60)
    print(" MODO DEMO: receitas de mentira, só para testar a interface")
    print(" Abra http://localhost:5000  |  login: demo@tastia.com / demo123")
    print("=" * 60 + "\n")
    app.run(debug=True, use_reloader=False, host="127.0.0.1", port=5000)
