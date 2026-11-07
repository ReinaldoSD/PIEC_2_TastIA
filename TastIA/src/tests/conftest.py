"""Base comum dos testes do TastIA.

Tudo aqui roda SEM baixar modelos e SEM internet:
  - o banco é um SQLite temporário, criado do zero a cada teste;
  - o app Flask de teste NÃO importa o app.py (que baixa os modelos ao ser importado);
  - os modelos de IA são trocados por versões falsas (veja MotorFalso e a fixture recomendador_falso).

Fixtures principais (use nos testes de qualquer módulo):
  app               -> Flask de teste com os blueprints registrados e banco temporário
  client            -> cliente HTTP sem login
  criar_usuario     -> função que cria um usuário no banco e devolve o dict dele
  usuario           -> um usuário já criado
  client_logado     -> cliente HTTP já logado como `usuario`
  logar             -> função logar(client, usuario) para logar outros usuários
  conn              -> conexão aberta com o banco temporário (fecha sozinha)
  recomendador_lexico / recomendador_falso -> recomendadores de bebidas para os testes
"""
import os
import sys

import pytest

# Garante que `import config`, `import bebidas...` etc. funcionem rodando `pytest` da raiz.
RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

# Antes de qualquer import do projeto: nada de baixar modelo, motor de bebidas sem MiniLM.
os.environ["BEBIDAS_MOTOR"] = "lexico"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ.setdefault("SECRET_KEY", "chave-de-teste")

from flask import Flask  # noqa: E402
from werkzeug.security import generate_password_hash  # noqa: E402


# --------------------------------------------------------------------------- #
# Proteção: se algum teste tentar baixar um modelo, falha na hora.
# --------------------------------------------------------------------------- #
@pytest.fixture(autouse=True)
def _sem_download_de_modelos(monkeypatch):
    def _proibido(*args, **kwargs):
        raise RuntimeError("Os testes não podem baixar modelos do Hugging Face.")

    try:
        import huggingface_hub
        monkeypatch.setattr(huggingface_hub, "snapshot_download", _proibido, raising=False)
    except ImportError:
        pass
    yield


# --------------------------------------------------------------------------- #
# Banco temporário
# --------------------------------------------------------------------------- #
@pytest.fixture
def banco_temporario(tmp_path, monkeypatch):
    """Aponta o projeto para um tastia.db novo (dentro da pasta temporária do pytest)."""
    import banco_dados.database as database

    caminho = tmp_path / "tastia_teste.db"
    # database.py faz `from config import DB_PATH, DB_DIR`, então o valor é copiado
    # para o módulo: é nele que precisamos trocar.
    monkeypatch.setattr(database, "DB_PATH", str(caminho))
    monkeypatch.setattr(database, "DB_DIR", str(tmp_path))

    from banco_dados.create_db import criar_tabelas
    criar_tabelas()
    return str(caminho)


@pytest.fixture
def conn(banco_temporario):
    from banco_dados.database import obter_conexao

    c = obter_conexao()
    yield c
    c.close()


# --------------------------------------------------------------------------- #
# App Flask de teste (sem o app.py)
# --------------------------------------------------------------------------- #
@pytest.fixture
def app(banco_temporario):
    from rotas.bebida import bp_bebida
    from rotas.ingrediente import bp_ingrediente
    from rotas.receita import bp_receita

    app = Flask("tastia_teste")
    app.config.update(TESTING=True, SECRET_KEY="chave-de-teste")
    app.register_blueprint(bp_bebida)
    app.register_blueprint(bp_ingrediente)
    app.register_blueprint(bp_receita)
    return app


@pytest.fixture
def client(app):
    return app.test_client()


# --------------------------------------------------------------------------- #
# Usuários e login
# --------------------------------------------------------------------------- #
@pytest.fixture
def criar_usuario(banco_temporario):
    """Uso: u = criar_usuario(), ou criar_usuario(nome='Ana', email='ana@x.com')."""
    from banco_dados.database import obter_conexao

    contador = {"n": 0}

    def _criar(nome="Usuário Teste", email=None, senha="senha12345"):
        contador["n"] += 1
        email = email or f"teste{contador['n']}@tastia.com"
        c = obter_conexao()
        try:
            cur = c.execute(
                "INSERT INTO usuarios (nome, email, senha_hash) VALUES (?, ?, ?)",
                (nome, email, generate_password_hash(senha)),
            )
            c.commit()
            return {"id": cur.lastrowid, "nome": nome, "email": email, "senha": senha}
        finally:
            c.close()

    return _criar


@pytest.fixture
def usuario(criar_usuario):
    return criar_usuario()


def _logar(client, usuario):
    """Simula o login gravando na sessão o mesmo que o app.py grava."""
    with client.session_transaction() as sessao:
        sessao["usuario_id"] = usuario["id"]
        sessao["usuario_nome"] = usuario["nome"]
        sessao["usuario_email"] = usuario["email"]
    return client


@pytest.fixture
def logar():
    return _logar


@pytest.fixture
def client_logado(client, usuario):
    return _logar(client, usuario)


# --------------------------------------------------------------------------- #
# Dados de apoio
# --------------------------------------------------------------------------- #
@pytest.fixture
def semear_inventario(banco_temporario):
    """Uso: semear_inventario(usuario['id'], [('Tomate', 'Verduras e legumes', '3 unidades', None)])"""
    from banco_dados.database import obter_conexao

    def _semear(usuario_id, itens):
        c = obter_conexao()
        try:
            for nome, categoria, quantidade, validade in itens:
                c.execute(
                    "INSERT INTO inventario (usuario_id, nome, categoria, quantidade, validade) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (usuario_id, nome, categoria, quantidade, validade),
                )
            c.commit()
        finally:
            c.close()

    return _semear


# --------------------------------------------------------------------------- #
# Recomendador de bebidas sem o MiniLM
# --------------------------------------------------------------------------- #
class MotorFalso:
    """Motor de similaridade falso: valores fixos, sem modelo e sem dependências."""
    nome = "falso"

    def __init__(self, n_docs):
        self.n_docs = n_docs

    def similaridades(self, consulta):
        # valores decrescentes e determinísticos (0.9, 0.88, 0.86, ...)
        return [max(0.0, 0.9 - 0.02 * i) for i in range(self.n_docs)]


@pytest.fixture
def recomendador_lexico():
    """Recomendador real (regras + catálogo completo) com o motor léxico, sem modelo."""
    from bebidas.recomendador import MotorLexico, Recomendador, documento_da_bebida
    from bebidas.catalogo import CATALOGO

    motor = MotorLexico([documento_da_bebida(b) for b in CATALOGO])
    return Recomendador(motor=motor)


@pytest.fixture
def recomendador_falso():
    """Recomendador com MotorFalso: ideal para testar as regras sem depender da similaridade."""
    from bebidas.catalogo import CATALOGO
    from bebidas.recomendador import Recomendador

    return Recomendador(motor=MotorFalso(len(CATALOGO)))


@pytest.fixture
def injetar_recomendador():
    """Troca o singleton de rotas/bebida por um recomendador de teste e restaura no fim."""
    from bebidas import recomendador as mod

    anterior = mod._unico

    def _injetar(r):
        mod.definir_recomendador(r)
        return r

    yield _injetar
    mod.definir_recomendador(anterior)
