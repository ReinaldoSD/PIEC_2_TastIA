"""Unidades de medida corretas para cada ingrediente (sem IA, roda sem modelo e sem internet).

Por que existe: a câmera (e o cadastro rápido) guarda quase tudo como "4 unidades". Isso é certo para ovo, tomate
ou banana, mas errado para queijo, leite, arroz, carne... O modelo de receitas lia "queijo: 4 unidades" e escrevia
"4 unidades de queijo". Este módulo:

  1. diz qual é a unidade natural de cada alimento (queijo -> g, leite -> ml, ovo -> unidade...);
  2. converte a quantidade do inventário para essa unidade antes de ir para o prompt;
  3. reconhece e CORRIGE linhas de ingrediente com unidade errada ("2 unidades de queijo" -> "100 g de queijo").

Para mudar um valor basta editar a tabela `_TABELA`.
"""
import re
from typing import Dict, Optional, Tuple

from receitas.validador import _canon, _palavras, normalizar_texto

CONTAVEL = "contavel"
PESO = "peso"
VOLUME = "volume"

_TABELA: Dict[str, Tuple[str, int, int]] = {
    # laticínios
    "queijo": (PESO, 200, 100), "mussarela": (PESO, 200, 100), "parmesao": (PESO, 100, 30),
    "ricota": (PESO, 250, 100), "requeijao": (PESO, 200, 100), "coalho": (PESO, 300, 100),
    "manteiga": (PESO, 200, 20), "margarina": (PESO, 250, 20), "iogurte": (PESO, 170, 170),
    "nata": (PESO, 200, 50), "creme": (PESO, 200, 100),
    "leite": (VOLUME, 1000, 250),
    # carnes e frios
    "frango": (PESO, 500, 300), "carne": (PESO, 500, 300), "boi": (PESO, 500, 300),
    "bovino": (PESO, 500, 300), "bife": (CONTAVEL, 1, 2), "porco": (PESO, 500, 300), "suino": (PESO, 500, 300),
    "linguica": (CONTAVEL, 1, 2), "salsicha": (CONTAVEL, 1, 2), "bacon": (PESO, 150, 50),
    "presunto": (PESO, 150, 100), "calabresa": (CONTAVEL, 1, 1), "mortadela": (PESO, 150, 100),
    "peru": (PESO, 150, 100), "peixe": (PESO, 300, 300), "atum": (PESO, 170, 170),
    "sardinha": (PESO, 125, 125), "salmao": (PESO, 300, 300), "tilapia": (PESO, 300, 300),
    "camarao": (PESO, 300, 300), "costela": (PESO, 1000, 500), "charque": (PESO, 500, 300),
    # grãos, massas, farinhas, doces
    "arroz": (PESO, 1000, 200), "feijao": (PESO, 1000, 200), "lentilha": (PESO, 500, 150),
    "grao": (PESO, 500, 150), "ervilha": (PESO, 200, 100), "milho": (PESO, 170, 100),
    "macarrao": (PESO, 500, 250), "espaguete": (PESO, 500, 250), "lasanha": (PESO, 500, 250),
    "farinha": (PESO, 1000, 150), "fuba": (PESO, 500, 100), "aveia": (PESO, 200, 40),
    "trigo": (PESO, 1000, 150), "amido": (PESO, 200, 30), "maisena": (PESO, 200, 30),
    "granola": (PESO, 250, 50), "tapioca": (PESO, 500, 60), "cuscuz": (PESO, 500, 150),
    "acucar": (PESO, 1000, 100), "mel": (PESO, 300, 30), "chocolate": (PESO, 100, 100),
    "biscoito": (PESO, 200, 100), "bolacha": (PESO, 200, 100), "farofa": (PESO, 500, 100),
    "quinoa": (PESO, 250, 100), "amendoim": (PESO, 200, 50), "castanha": (PESO, 100, 50),
    "noz": (PESO, 100, 50), "pipoca": (PESO, 500, 100),
    "molho": (PESO, 340, 170), "extrato": (PESO, 340, 30),
    # líquidos
    "suco": (VOLUME, 1000, 250), "refrigerante": (VOLUME, 2000, 250), "vinagre": (VOLUME, 750, 30),
    "vinho": (VOLUME, 750, 100), "cerveja": (VOLUME, 350, 350), "shoyu": (VOLUME, 150, 30),
    "azeite": (VOLUME, 500, 15), "oleo": (VOLUME, 900, 15), "agua": (VOLUME, 1000, 250),
    # contáveis
    "ovo": (CONTAVEL, 1, 2), "tomate": (CONTAVEL, 1, 1), "cebola": (CONTAVEL, 1, 1),
    "batata": (CONTAVEL, 1, 2), "cenoura": (CONTAVEL, 1, 1), "pimentao": (CONTAVEL, 1, 1),
    "banana": (CONTAVEL, 1, 2), "maca": (CONTAVEL, 1, 1), "laranja": (CONTAVEL, 1, 1),
    "limao": (CONTAVEL, 1, 1), "abobrinha": (CONTAVEL, 1, 1), "pepino": (CONTAVEL, 1, 1),
    "beterraba": (CONTAVEL, 1, 1), "abacate": (CONTAVEL, 1, 1), "manga": (CONTAVEL, 1, 1),
    "pao": (CONTAVEL, 1, 2),
}

_PRECISAM_MEDIDA = {k for k, (tipo, _, _) in _TABELA.items() if tipo in (PESO, VOLUME)}

_UNIDADE_NA_LINHA = re.compile(
    r"^\s*(?:[-•*]\s*)?(?P<n>\d+(?:[.,]\d+)?|\d+\s*/\s*\d+|meio|meia|um|uma|dois|duas|tres|quatro|cinco)\s*"
    r"(?P<un>unidades?|unid\.?|un\.?)\s*(?:de\s+|do\s+|da\s+)?(?P<resto>.+)$",
    re.IGNORECASE,
)
_RE_OVO_EM_PESO = re.compile(
    r"^\s*(?:[-•*]\s*)?(?P<n>\d+(?:[.,]\d+)?)\s*(?P<un>g|gramas?|ml|mililitros?|kg|xicaras?|copos?)\s+(?:de\s+)?"
    r"(?P<resto>ovos?\b.*)$",
    re.IGNORECASE,
)
_NUMEROS_EXTENSO = {"meio": 0.5, "meia": 0.5, "um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5}


def _numero(valor: str) -> float:
    v = normalizar_texto(valor).strip()
    if v in _NUMEROS_EXTENSO:
        return float(_NUMEROS_EXTENSO[v])
    if "/" in v:
        a, b = [x.strip() for x in v.split("/", 1)]
        return float(a) / float(b) if b not in ("", "0") else 1.0
    return float(v.replace(",", "."))


def _formatar_numero(n: float) -> str:
    return str(int(n)) if float(n).is_integer() else str(round(n, 2)).replace(".", ",")


def _arredondar(n: float) -> int:
    """Arredonda para um número 'de cozinha': de 5 em 5 g até 100 g, de 10 em 10 até 500, depois de 50 em 50."""
    passo = 5 if n <= 100 else 10 if n <= 500 else 50
    return max(passo, int(round(n / passo)) * passo)


def alimento_principal(nome: str) -> Optional[str]:
    """'Queijo ralado' -> 'queijo'; 'creme de leite' -> 'creme'; devolve None se não estiver na tabela."""
    canon = [_canon(p) for p in _palavras(nome)]
    for c in canon:
        if c in _TABELA:
            return c
    return None


def tipo_de_medida(nome: str) -> Optional[str]:
    a = alimento_principal(nome)
    return _TABELA[a][0] if a else None


def unidade_natural(nome: str) -> str:
    """'g', 'ml' ou 'unidade(s)' — a unidade em que o alimento deve ser escrito numa receita."""
    tipo = tipo_de_medida(nome)
    return {PESO: "g", VOLUME: "ml"}.get(tipo, "unidades")


# --------------------------------------------------------------------------- #
# 1. Quantidade do inventário -> unidade natural (usada no prompt)
# --------------------------------------------------------------------------- #
_RE_QTD_INVENTARIO = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*([^\d]*?)\s*$")


def _para_base(numero: float, unidade: str, nome: str) -> Optional[Tuple[float, str]]:
    """Converte 'numero unidade' do inventário para (valor, 'g'|'ml'|'unidades'). None se não souber."""
    u = normalizar_texto(unidade).strip(" .")
    a = alimento_principal(nome)
    if u in ("g", "gr", "grama", "gramas"):
        return numero, "g"
    if u in ("kg", "quilo", "quilos", "quilograma", "quilogramas"):
        return numero * 1000, "g"
    if u in ("ml", "mililitro", "mililitros"):
        return numero, "ml"
    if u in ("l", "litro", "litros", "lt"):
        return numero * 1000, "ml"
    if u in ("", "un", "unid", "unidade", "unidades", "pacote", "pacotes", "caixa", "caixas", "lata", "latas",
             "pote", "potes", "garrafa", "garrafas", "peca", "pecas"):
        if a is None:
            return numero, "unidades"
        tipo, tamanho, _ = _TABELA[a]
        if tipo == CONTAVEL:
            return numero, "unidades"
        return numero * tamanho, "g" if tipo == PESO else "ml"
    return None


def quantidade_natural(nome: str, quantidade: Optional[str]) -> str:
    """'4 unidades' (queijo) -> '800 g'; '2 unidades' (ovo) -> '2 unidades'; '500 g' fica '500 g'."""
    texto = str(quantidade or "").strip()
    if not texto:
        return ""
    m = _RE_QTD_INVENTARIO.match(texto)
    if not m:
        return texto
    numero = float(m.group(1).replace(",", "."))
    convertido = _para_base(numero, m.group(2), nome)
    if convertido is None:
        return texto
    valor, unidade = convertido
    if unidade == "g" and valor >= 1000:
        return f"{_formatar_numero(round(valor / 1000, 2))} kg"
    if unidade == "ml" and valor >= 1000:
        return f"{_formatar_numero(round(valor / 1000, 2))} L"
    if unidade == "unidades":
        return f"{_formatar_numero(valor)} {'unidade' if valor == 1 else 'unidades'}"
    return f"{_formatar_numero(valor)} {unidade}"


def dica_de_unidade(nome: str) -> str:
    """Frase curta para o prompt: 'escreva em gramas (g)' / 'escreva em ml'. '' para o que é contável/desconhecido."""
    tipo = tipo_de_medida(nome)
    if tipo == PESO:
        return "na receita escreva em gramas (g), nunca em unidades"
    if tipo == VOLUME:
        return "na receita escreva em ml ou colheres/xícaras, nunca em unidades"
    return ""


# --------------------------------------------------------------------------- #
# 2. Correção de linhas de ingrediente com unidade errada
# --------------------------------------------------------------------------- #
def _plural(nome: str) -> str:
    """'ovo' -> 'ovos'; 'pimentão' -> 'pimentões'; 'tomate cereja' -> 'tomates cereja' (só a 1ª palavra)."""
    primeira, _, resto = nome.partition(" ")
    if primeira.endswith("ão"):
        primeira = primeira[:-2] + ("ães" if primeira in ("pão",) else "ões")
    elif primeira.endswith(("r", "z")):
        primeira += "es"
    elif not primeira.endswith("s"):
        primeira += "s"
    return f"{primeira} {resto}".strip()


_ERVAS = {"cheiro", "salsa", "salsinha", "cebolinha", "coentro", "manjericao", "hortela", "rucula", "agriao"}
_VERDURAS_100G = {"couve", "alface", "espinafre", "brocolis", "repolho", "abobora", "mandioca", "chuchu", "vagem",
                  "inhame", "berinjela", "quiabo", "cogumelo", "champignon", "palmito", "milho"}


def quantidade_padrao(nome: str) -> str:
    """Quantidade típica para uma receita de 2 porções, já na unidade certa ('100 g de queijo', '2 ovos')."""
    nome_curto = re.sub(r"\s+", " ", re.sub(r"\(.*?\)", "", nome)).strip().lower()
    canon = [_canon(p) for p in _palavras(nome)]
    if "alho" in canon:
        return f"2 dentes de {nome_curto}"
    if any(c in _ERVAS for c in canon):
        return f"{nome_curto} a gosto"
    if any(c in _VERDURAS_100G for c in canon) and alimento_principal(nome) is None:
        return f"100 g de {nome_curto}"
    a = alimento_principal(nome)
    if a is None:
        return ""
    tipo, _, porcao = _TABELA[a]
    nome_limpo = re.sub(r"\s+", " ", re.sub(r"\(.*?\)", "", nome)).strip().lower()
    if tipo == PESO:
        return f"{porcao} g de {nome_limpo}"
    if tipo == VOLUME:
        return f"{porcao} ml de {nome_limpo}"
    return f"{porcao} {_plural(nome_limpo)}" if porcao != 1 else f"1 {nome_limpo}"


def corrigir_linha_ingrediente(linha: str) -> str:
    """Troca a unidade errada pela certa. Só mexe quando tem certeza; qualquer outra linha volta igual."""
    item = linha.strip()
    prefixo = "- " if item.startswith("-") else ""

    m = _RE_OVO_EM_PESO.match(item)
    if m:
        qtd = _numero(m.group("n"))
        un = normalizar_texto(m.group("un"))
        if un == "kg":
            ovos = qtd * 20
        elif un.startswith(("xicara", "copo")):
            ovos = qtd * 4
        else:
            ovos = qtd / 50
        ovos = max(1, int(round(ovos)))
        resto = re.sub(r"^ovos?\b", "ovo" if ovos == 1 else "ovos", m.group("resto"), flags=re.I)
        return f"{prefixo}{ovos} {resto}".strip()

    m = _UNIDADE_NA_LINHA.match(item)
    if not m:
        return linha
    resto = m.group("resto").strip()
    alimento = alimento_principal(resto)
    if alimento is None or alimento not in _PRECISAM_MEDIDA:
        return linha
    tipo, tamanho, porcao = _TABELA[alimento]
    n = _numero(m.group("n"))
    base = min(porcao, tamanho)
    total = _arredondar(max(base, min(n, 4) * base / 2))
    un = "g" if tipo == PESO else "ml"
    return f"{prefixo}{total} {un} de {resto}"


def unidade_errada(linha: str) -> Optional[str]:
    """Texto do problema se a linha usa uma unidade inadequada para o alimento; None se está ok."""
    item = linha.strip()
    if _RE_OVO_EM_PESO.match(item):
        return re.sub(r"^[-•*]\s*", "", item)
    m = _UNIDADE_NA_LINHA.match(item)
    if m and alimento_principal(m.group("resto")) in _PRECISAM_MEDIDA:
        return re.sub(r"^[-•*]\s*", "", item)
    return None