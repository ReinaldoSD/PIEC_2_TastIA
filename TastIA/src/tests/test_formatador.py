"""Testes do formatador de receitas: nome da receita, filtro de saudação/apresentação e limpeza.

Não usam modelo nem internet. Rode com:  python -m pytest tests/test_formatador.py -v
"""
import pytest

from receitas.formatador import eh_conversa_do_modelo, formatar_receita

CORPO = (
    "\nTempo de preparo: 10 minutos\nPorções: 2\nIngredientes\n- 2 ovos\n- 1 tomate\n- sal\n"
    "Modo de preparo\n1. Bata os ovos.\n2. Junte o tomate."
)
RESERVA = "Receita com ovos e tomate"


def primeira_linha(antes: str, pedido=None) -> str:
    return formatar_receita(antes + CORPO, pedido).splitlines()[0]


# --------------------------------------------------------------------------- #
# Preâmbulo antes do nome: o nome certo deve sobrar
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("antes", [
    "Omelete de tomate",
    "Claro! Aqui está sua receita:\n\nOmelete de tomate",
    "Olá, amigo! Tudo bem?\n## Omelete de tomate",
    "Olá!\nOmelete de tomate",
    "Oi, chef!\nOmelete de tomate",
    "Bom dia!\nVou criar uma receita para você.\n**Omelete de tomate**",
    "Boa tarde, Maria! Aqui está sua receita: Omelete de tomate",
    "Maria, aqui está a receita que você pediu:\nOmelete de tomate",
    "Claro! Omelete de tomate",
    "Com certeza, aqui vai a receita! Omelete de tomate",
    "Ótima escolha! Omelete de tomate",
    "Sure! Here is your recipe:\nOmelete de tomate",
    "Hello! Let me create a recipe for you.\nOmelete de tomate",
    "Aqui está:\nTítulo: Omelete de tomate",
    "Receita sugerida: Omelete de tomate",
    "Segue a receita:\nOmelete de tomate",
    "Preparei uma receita simples com os ingredientes que você tem.\nOmelete de tomate",
    "Com base nos ingredientes disponíveis, criei esta receita.\nOmelete de tomate",
    "Desculpe pelo erro anterior! Aqui está a versão corrigida:\nOmelete de tomate",
    "Entendi seu pedido. Vamos lá!\nOmelete de tomate",
    "Espero que goste!\nOmelete de tomate",
    "Para aproveitar seus ingredientes, sugiro esta receita:\nOmelete de tomate",
    "Como assistente culinário, sugiro:\nOmelete de tomate",
    "Nota: usei apenas ingredientes do inventário.\nOmelete de tomate",
    "Omelete de tomate.",
    "# Receita de omelete de tomate",
    "OMELETE DE TOMATE",
    "Omelete De Tomate",
    "🍳 Omelete de tomate 🍅",
])
def test_nome_correto_sobra(antes):
    assert primeira_linha(antes) == "Omelete de tomate"


# --------------------------------------------------------------------------- #
# Sem nome válido: cai no título de reserva
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("antes", [
    "Olá, tudo bem? Vou te ajudar com essa receita.",
    "Claro! Aqui está sua receita:",
    "Que delícia!",
    "Esta é uma receita muito simples e saborosa que você vai amar fazer hoje em casa.",
    "<Título da receita>",
    "<Nome do prato, na primeira linha>",
    "Nome do prato",
    "Receita com seus ingredientes favoritos",
    "Pessoal, bora cozinhar!\nGalera,",
])
def test_sem_nome_usa_reserva(antes):
    assert primeira_linha(antes) == RESERVA


# --------------------------------------------------------------------------- #
# Nomes legítimos NÃO podem ser descartados
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("nome", [
    "Bom bolo de cenoura",
    "Arroz de forno com frango, queijo e presunto",
    "Sanduíche de frango, queijo e tomate",
    "Frango ao molho de tomate",
    "Ovos mexidos cremosos",
    "Tapioca de queijo",
    "Bolo da minha avó",
    "Falafel de grão-de-bico",
    "Salada ok de tomate",
    "Oitavo de galinha",
    "Hiper omelete",
    "Sim bolo",
])
def test_nomes_legitimos_ficam(nome):
    assert primeira_linha(nome) == nome


def test_usando_ovos_aproveita_o_nome_depois_dos_dois_pontos():
    assert primeira_linha("Usando ovos: omelete simples") == "Omelete simples"


def test_receita_com_nao_perde_o_com():
    assert primeira_linha("Receita com ovos") == "Receita com ovos"


# --------------------------------------------------------------------------- #
# Título de reserva usando o pedido
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("pedido, esperado", [
    ("lanche leve em 15 minutos", "Lanche leve com ovos e tomate"),
    ("quero um jantar rápido", "Jantar rápido com ovos e tomate"),
    ("uma sobremesa rápida", "Sobremesa rápida com ovos e tomate"),
    ("sopa simples", "Sopa simples com ovos e tomate"),
    ("algo gostoso", RESERVA),
    ("", RESERVA),
    (None, RESERVA),
])
def test_reserva_usa_o_pedido(pedido, esperado):
    assert primeira_linha("Claro! Aqui está:", pedido) == esperado


def test_reserva_ignora_basicos_de_despensa():
    texto = "Claro!\nIngredientes\n- sal\n- 2 colheres de azeite\n- 3 ovos\nModo de preparo\n1. Frite os ovos."
    assert formatar_receita(texto).splitlines()[0] == "Receita com ovos"


# --------------------------------------------------------------------------- #
# Conversa solta dentro das seções
# --------------------------------------------------------------------------- #
def test_conversa_solta_nao_vira_ingrediente_nem_passo():
    texto = (
        "Omelete de tomate\nIngredientes\nAqui estão os ingredientes:\n- 2 ovos\n- 1 tomate\n"
        "Modo de preparo\nVamos lá!\nAqui estão os passos:\n1. Bata os ovos.\n2. Junte o tomate.\nBom apetite!"
    )
    saida = formatar_receita(texto)
    assert "Aqui estão" not in saida and "Vamos lá" not in saida and "Bom apetite" not in saida
    assert "1. Bata os ovos." in saida and "2. Junte o tomate." in saida


def test_passo_sem_numero_que_comeca_com_usando_nao_e_apagado():
    texto = "Omelete\nIngredientes\n- 2 ovos\nModo de preparo\nUsando uma frigideira, aqueça o óleo.\nBata os ovos."
    assert "Usando uma frigideira" in formatar_receita(texto)


# --------------------------------------------------------------------------- #
# Formato geral
# --------------------------------------------------------------------------- #
def test_formato_final_padronizado():
    saida = formatar_receita("Omelete de tomate" + CORPO)
    assert saida.splitlines()[:4] == ["Omelete de tomate", "Tempo de preparo: 10 minutos", "Porções: 2", ""]
    assert "Ingredientes\n- 2 ovos" in saida
    assert "Modo de preparo\n1. Bata os ovos.\n2. Junte o tomate." in saida


def test_markdown_e_ultima_frase_cortada():
    texto = ("## Omelete\n**Ingredientes**\n* 2 ovos\n**Modo de preparo**\n1. Bata os ovos.\n"
             "2. Frite por alguns")
    saida = formatar_receita(texto)
    assert "*" not in saida and "#" not in saida
    assert saida.rstrip().endswith("1. Bata os ovos.")


def test_sem_secoes_devolve_texto_limpo():
    assert formatar_receita("**Só um texto qualquer**") == "Só um texto qualquer"


@pytest.mark.parametrize("linha, esperado", [
    ("Claro!", True), ("Olá, tudo bem?", True), ("Aqui está sua receita:", True),
    ("Omelete de tomate", False), ("Bom bolo de cenoura", False), ("Sim bolo", False),
])
def test_eh_conversa_do_modelo(linha, esperado):
    assert eh_conversa_do_modelo(linha) is esperado
