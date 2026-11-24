"""Combinações de alimentos do TastIA: o que combina com o quê (sem IA, roda sem modelo e sem internet).

O módulo coerencia.py confere o formato, as quantidades, o tempo e as restrições. Este módulo cuida do SENTIDO do
prato, isto é, se os alimentos formam uma refeição de verdade:

  - cada tipo de prato é montado por PAPÉIS: lanche = pão + recheio (+ vegetal); macarrão = massa + proteína,
    queijo ou molho; almoço/jantar = proteína + base (arroz, batata...) + legume; salada = folhas e legumes...
  - pares que não combinam no mesmo prato: arroz com macarrão, pão com arroz, peixe com leite, frango com carne
    de boi, leite com limão, chocolate com carne...
  - doce com doce e salgado com salgado (bolo, vitamina e sobremesa sem carne ou cebola; sopa e omelete sem
    banana);
  - café da manhã sem feijão, arroz, macarrão ou carne vermelha.

Ele é usado em dois lugares:

  1. prompt.py chama `texto_orientacao` para dizer ao modelo QUAIS combinações o inventário permite (sempre com
     alimentos que o usuário tem) e o que não misturar;
  2. coerencia.py chama `verificar_combinacoes` para apontar, em português, o que está sem sentido na receita
     pronta. Cada problema vira uma frase para o campo CORREÇÃO da nova tentativa.

Para ensinar uma combinação nova basta editar as tabelas abaixo (grupos de alimentos, `ARQUETIPOS` e `_PARES`).
"""
import re
from dataclasses import dataclass
from typing import Dict, FrozenSet, Iterable, List, Optional, Sequence, Set, Tuple, Union

from receitas.validador import ALIMENTOS, _canon, _palavras, _subtokens, normalizar_texto


def _g(*palavras: str) -> FrozenSet[str]:
    return frozenset(_canon(p) for p in palavras)


# --------------------------------------------------------------------------- #
# Grupos de alimentos (os nomes já normalizados: sem acento e no singular)
# --------------------------------------------------------------------------- #
QUEIJOS = _g("queijo", "mussarela", "parmesao", "ricota", "requeijao", "coalho")
FRIOS = _g("presunto", "mortadela", "peru")
EMBUTIDOS = _g("bacon", "linguica", "calabresa", "salsicha", "presunto", "mortadela")
AVES = _g("frango")
BOVINAS = _g("carne", "boi", "bovino", "bife", "costela", "charque")
SUINOS = _g("porco", "suino", "costela")
PEIXES = _g("peixe", "atum", "sardinha", "salmao", "tilapia")
FRUTOS_DO_MAR = _g("camarao")
OVO = _g("ovo")
LEGUMINOSAS = _g("feijao", "lentilha", "grao", "ervilha")
LEITES = _g("leite")
GORDURAS_PAO = _g("manteiga", "margarina")

PROTEINAS_ANIMAIS = AVES | BOVINAS | SUINOS | EMBUTIDOS | PEIXES | FRUTOS_DO_MAR
PROTEINAS_REFEICAO = PROTEINAS_ANIMAIS | OVO | LEGUMINOSAS | QUEIJOS

MASSAS = _g("macarrao", "espaguete", "lasanha")
FOLHAS = _g("alface", "couve", "repolho", "espinafre", "rucula", "agriao")
VEGETAIS = FOLHAS | _g(
    "tomate", "cebola", "cenoura", "abobora", "abobrinha", "chuchu", "beterraba", "pimentao", "pepino", "brocolis",
    "vagem", "quiabo", "berinjela", "cogumelo", "champignon", "palmito", "rabanete", "milho",
)
SALADA_DE_LANCHE = _g("alface", "tomate", "cebola", "pepino", "cenoura", "rucula", "agriao", "palmito", "azeitona")
TUBERCULOS = _g("batata", "mandioca", "inhame")

FRUTAS_DOCES = _g(
    "banana", "abacaxi", "mamao", "melancia", "morango", "uva", "goiaba", "maracuja", "acerola", "caju", "pessego",
    "kiwi", "melao", "pera",
)
FRUTAS = FRUTAS_DOCES | _g("maca", "laranja", "limao", "manga", "abacate", "tangerina", "mexerica", "coco")
CITRICOS = _g("limao", "laranja", "maracuja")
DOCES_FORTES = _g("chocolate", "cacau", "rapadura", "pacoca", "melado")

# o que NÃO faz sentido em bolo, pudim, vitamina, sobremesa...
NAO_DOCE = PROTEINAS_ANIMAIS | _g(
    "cebola", "alho", "pimentao", "pepino", "alface", "feijao", "lentilha", "macarrao", "espaguete", "lasanha",
)
# o que NÃO faz sentido no café da manhã
PESADOS_DE_ALMOCO = BOVINAS | PEIXES | FRUTOS_DO_MAR | LEGUMINOSAS | MASSAS | _g("arroz", "porco", "suino")

# bases de refeição que não se misturam no mesmo prato (arroz com macarrão, pão com arroz...)
_FAMILIAS_DE_BASE: Tuple[Tuple[str, FrozenSet[str]], ...] = (
    ("arroz", _g("arroz")),
    ("macarrão", MASSAS),
    ("pão", _g("pao")),
    ("tapioca", _g("tapioca")),
    ("cuscuz", _g("cuscuz")),
)
_RE_PAO_PERMITIDO = re.compile(r"\b(sopa|caldo|canja|bolo|pudim|rabanada|torta|farofa)\b")

_EXIBIR = {
    "pao": "pão", "macarrao": "macarrão", "feijao": "feijão", "linguica": "linguiça", "salmao": "salmão",
    "camarao": "camarão", "limao": "limão", "pimentao": "pimentão", "mamao": "mamão", "maca": "maçã",
    "acucar": "açúcar", "tilapia": "tilápia", "brocolis": "brócolis", "requeijao": "requeijão",
    "parmesao": "parmesão", "grao": "grão-de-bico", "melao": "melão", "pacoca": "paçoca", "abobora": "abóbora",
    "rucula": "rúcula", "agriao": "agrião", "ervilha": "ervilha", "boi": "carne", "bovino": "carne",
    "suino": "porco",
}


def _nome(token: str) -> str:
    return _EXIBIR.get(token, token)


# --------------------------------------------------------------------------- #
# Ler os alimentos de uma lista (receita ou inventário)
# --------------------------------------------------------------------------- #
# 'creme de leite', 'leite de coco', 'leite condensado' não são 'leite' para efeito de combinação
_RE_LEITES_ESPECIAIS = re.compile(
    r"\b(creme de leite|leite condensado|leite de [a-z]+|leite em po|doce de leite|leite fermentado)\b"
)


def _tokens_linha(texto: str) -> List[str]:
    """Alimentos citados em um texto, na ordem em que aparecem e sem repetir."""
    limpo = _RE_LEITES_ESPECIAIS.sub(" ", normalizar_texto(texto))
    achados: List[str] = []
    for palavra in _palavras(limpo):
        for sub in _subtokens(palavra):
            if sub in ALIMENTOS and sub not in achados:
                achados.append(sub)
    return achados


def _alimentos_da_lista(ingredientes: Iterable[str]) -> List[str]:
    ordem: List[str] = []
    for item in ingredientes:
        if item.endswith(":"):
            continue
        for t in _tokens_linha(item):
            if t not in ordem:
                ordem.append(t)
    return ordem


def _nome_limpo(nome: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\(.*?\)", "", str(nome))).strip().lower()


def _itens_do_inventario(inventario: Sequence[Union[str, Dict]]) -> List[Tuple[str, List[str]]]:
    itens: List[Tuple[str, List[str]]] = []
    for item in inventario:
        nome = str(item.get("nome", "")) if isinstance(item, dict) else str(item)
        tokens = _tokens_linha(nome)
        if tokens:
            itens.append((_nome_limpo(nome), tokens))
    return itens


def _exemplos(grupo: FrozenSet[str], itens, proibidos: Set[str], quantos: int = 2) -> List[str]:
    achados: List[str] = []
    for nome, tokens in itens:
        if set(tokens) & grupo and not (set(tokens) & proibidos) and nome not in achados:
            achados.append(nome)
        if len(achados) >= quantos:
            break
    return achados


def _lista_em_texto(nomes: Sequence[str]) -> str:
    if len(nomes) <= 1:
        return "".join(nomes)
    return ", ".join(nomes[:-1]) + " ou " + nomes[-1]


# --------------------------------------------------------------------------- #
# Pares que não combinam no mesmo prato
# --------------------------------------------------------------------------- #
# (grupo A, grupo B, motivo, título em que o par é permitido)
_PARES: Tuple[Tuple[FrozenSet[str], FrozenSet[str], str, Optional[str]], ...] = (
    (PEIXES, AVES | BOVINAS, "são duas proteínas fortes de sabores muito diferentes", None),
    (AVES, BOVINAS, "são duas carnes fortes de sabores diferentes", None),
    (PEIXES, EMBUTIDOS, "o sabor curado e defumado do embutido encobre o do peixe", None),
    (PEIXES, LEITES, "o leite não combina com peixe", None),
    (LEITES, CITRICOS, "o leite talha com o ácido do limão, da laranja ou do maracujá",
     r"\b(bolo|torta|pudim|mousse|pave)\b"),
    (DOCES_FORTES, NAO_DOCE | _g("tomate"), "doce de chocolate ou cacau não forma um prato com salgados", None),
)


def _primeiro(ordem: Sequence[str], grupo: FrozenSet[str]) -> str:
    for t in ordem:
        if t in grupo:
            return t
    return ""


def _pares_conflitantes(presentes: Set[str], ordem: Sequence[str], titulo_norm: str = "") -> List[Tuple[str, str, str]]:
    """Lista (alimento A, alimento B, motivo) dos pares que não combinam entre os alimentos `presentes`."""
    achados: List[Tuple[str, str, str]] = []
    for a, b, motivo, excecao in _PARES:
        if excecao and re.search(excecao, titulo_norm):
            continue
        x, y = _primeiro(ordem, a & presentes), _primeiro(ordem, b & presentes)
        if x and y and x != y:
            achados.append((_nome(x), _nome(y), motivo))

    bases = [(rot, g) for rot, g in _FAMILIAS_DE_BASE if presentes & g]
    if any(rot == "pão" for rot, _ in bases) and _RE_PAO_PERMITIDO.search(titulo_norm):
        bases = [(rot, g) for rot, g in bases if rot != "pão"]
    if len(bases) >= 2:
        achados.append((bases[0][0], bases[1][0], "são duas bases de refeição, o prato fica pesado e sem sentido"))
    return achados


def _conflitos(presentes: Set[str], titulo_norm: str = "") -> bool:
    return bool(_pares_conflitantes(presentes, sorted(presentes), titulo_norm))


# --------------------------------------------------------------------------- #
# Tipos de prato e seus papéis
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Parte:
    rotulo: str
    grupo: FrozenSet[str]
    maximo: int = 1            # quantos itens do grupo entram na sugestão
    obrigatoria: bool = False  # sem ela o prato não é esse prato
    minimo: int = 1            # quantos itens distintos do grupo a receita precisa ter
    coberta: bool = False      # coerencia.py já cobra essa parte (não repetir a mensagem)


@dataclass(frozen=True)
class Arquetipo:
    chave: str
    rotulo: str                 # como aparece nas mensagens ("lanche")
    sugestao: str               # como aparece na sugestão do prompt ("Lanche")
    gatilho: str                # regex (texto sem acento) que identifica o prato no pedido e no nome da receita
    partes: Tuple[Parte, ...]
    minimo_alimentos: int = 2
    no_titulo: bool = True      # confere a receita quando o NOME dela é desse prato
    no_pedido: bool = False     # confere a receita quando só o PEDIDO cita o prato (almoço, jantar)
    checa_partes: bool = True


_ACOMP_MASSA = PROTEINAS_ANIMAIS - PEIXES | _g("atum", "sardinha") | FRUTOS_DO_MAR | OVO | QUEIJOS
_COMPLEMENTO_CAFE = OVO | QUEIJOS | FRIOS | GORDURAS_PAO | _g("bacon", "iogurte", "leite")
_BASE_DOCE_CAFE = _g("aveia", "granola", "tapioca", "pao", "cuscuz")

ARQUETIPOS: Tuple[Arquetipo, ...] = (
    Arquetipo(
        "lanche", "lanche", "Lanche",
        r"\b(lanche|sanduiche|misto|hamburguer|cachorro quente|cachorro-quente|x ?(salada|burger|tudo|bacon|egg))\b",
        (
            Parte("pão", _g("pao", "tapioca"), obrigatoria=True, coberta=True),
            Parte("recheio", QUEIJOS | FRIOS | OVO | AVES | BOVINAS | GORDURAS_PAO
                  | _g("atum", "sardinha", "bacon", "calabresa", "linguica", "salsicha"), 2, obrigatoria=True),
            Parte("vegetal", SALADA_DE_LANCHE),
        ),
    ),
    Arquetipo(
        "macarrao", "macarrão", "Macarrão",
        r"\b(macarrao|espaguete|talharim|parafuso|lasanha|massa(?! de| para))\b",
        (
            Parte("macarrão", MASSAS, obrigatoria=True, coberta=True),
            Parte("proteína ou queijo", _ACOMP_MASSA, 1),
            Parte("molho ou legume", _g("tomate", "cebola", "alho", "brocolis", "abobrinha", "cenoura", "cogumelo",
                                         "champignon", "pimentao", "manteiga", "leite", "espinafre"), 2),
        ),
    ),
    Arquetipo(
        "refeicao", "almoço ou jantar", "Almoço ou jantar",
        r"\b(almoco|jantar|janta|prato principal|marmita|prato feito|refeicao completa)\b",
        (
            Parte("base", _g("arroz") | TUBERCULOS | _g("cuscuz", "macarrao", "espaguete"), 1),
            Parte("proteína", PROTEINAS_REFEICAO - LEGUMINOSAS, 1, obrigatoria=True),
            Parte("leguminosa", LEGUMINOSAS, 1),
            Parte("legume ou salada", VEGETAIS, 2),
        ),
        no_titulo=False, no_pedido=True,
    ),
    Arquetipo(
        "salada_de_frutas", "salada de frutas", "Salada de frutas",
        r"\bsalada de frutas?\b",
        (
            Parte("fruta", FRUTAS - _g("limao", "coco"), 3, obrigatoria=True, minimo=2),
            Parte("complemento", _g("iogurte", "mel", "granola", "aveia", "leite"), 1),
        ),
    ),
    Arquetipo(
        "salada", "salada", "Salada",
        r"\bsalada\b(?! de frutas?)",
        (
            Parte("folhas ou legumes", VEGETAIS | TUBERCULOS, 3, obrigatoria=True),
            Parte("proteína", OVO | AVES | _g("atum", "sardinha") | QUEIJOS | FRIOS | LEGUMINOSAS, 1),
        ),
    ),
    Arquetipo(
        "sopa", "sopa", "Sopa",
        r"\b(sopa|caldo|canja)\b",
        (
            Parte("base de legumes ou grãos", VEGETAIS | TUBERCULOS | LEGUMINOSAS | _g("macarrao", "arroz"), 3,
                  obrigatoria=True),
            Parte("proteína", AVES | BOVINAS | _g("linguica", "bacon", "ovo"), 1),
            Parte("tempero", _g("cebola", "alho"), 1),
        ),
    ),
    Arquetipo(
        "omelete", "omelete", "Omelete",
        r"\b(omelete|ovos? mexidos?)\b",
        (
            Parte("ovo", OVO, obrigatoria=True, coberta=True),
            Parte("recheio", QUEIJOS | FRIOS | _g("bacon", "calabresa", "linguica") | AVES | VEGETAIS, 2),
        ),
        minimo_alimentos=1,
    ),
    Arquetipo(
        "tapioca", "tapioca", "Tapioca",
        r"\btapioca\b",
        (
            Parte("tapioca", _g("tapioca", "goma"), obrigatoria=True, coberta=True),
            Parte("recheio", QUEIJOS | OVO | FRIOS | AVES | _g("coco", "banana", "carne", "chocolate"), 1,
                  obrigatoria=True),
        ),
    ),
    Arquetipo(
        "cuscuz", "cuscuz", "Cuscuz",
        r"\bcuscuz\b",
        (
            Parte("cuscuz", _g("cuscuz", "fuba", "milho"), obrigatoria=True, coberta=True),
            Parte("complemento", OVO | QUEIJOS | FRIOS | AVES | BOVINAS | _g("calabresa", "linguica", "manteiga",
                                                                              "leite"), 1, obrigatoria=True),
        ),
    ),
    Arquetipo(
        "risoto", "risoto", "Risoto",
        r"\brisoto\b",
        (
            Parte("arroz", _g("arroz"), obrigatoria=True, coberta=True),
            Parte("recheio ou tempero", AVES | BOVINAS | QUEIJOS | VEGETAIS | _g("alho", "bacon", "linguica"), 2,
                  obrigatoria=True),
        ),
    ),
    Arquetipo(
        "vitamina", "vitamina", "Vitamina",
        r"\b(vitamina|smoothie|shake|batida)\b",
        (
            Parte("fruta", FRUTAS - _g("limao"), 2, obrigatoria=True),
            Parte("leite ou iogurte", _g("leite", "iogurte"), 1),
        ),
        minimo_alimentos=1,
    ),
    Arquetipo(
        "cafe_salgado", "café da manhã", "Café da manhã salgado",
        r"\b(cafe da manha|cafe da tarde|desjejum)\b",
        (
            Parte("base", _g("pao", "tapioca", "cuscuz"), obrigatoria=True),
            Parte("recheio", _COMPLEMENTO_CAFE - _g("leite", "iogurte"), 2, obrigatoria=True),
        ),
        no_titulo=False, checa_partes=False,
    ),
    Arquetipo(
        "cafe_doce", "café da manhã", "Café da manhã doce",
        r"\b(cafe da manha|cafe da tarde|desjejum)\b",
        (
            Parte("base", _BASE_DOCE_CAFE, obrigatoria=True),
            Parte("fruta", FRUTAS_DOCES | _g("maca", "manga", "laranja"), 1, obrigatoria=True),
            Parte("leite ou iogurte", _g("leite", "iogurte", "mel"), 1),
        ),
        no_titulo=False, checa_partes=False,
    ),
    Arquetipo(
        "sobremesa", "sobremesa", "Sobremesa",
        r"\b(sobremesa|algo doce|um doce|doces|docinho)\b|(?<!batata-)(?<!batata )\bdoce\b(?! de leite)",
        (
            Parte("fruta", FRUTAS - _g("limao"), 2, obrigatoria=True),
            Parte("cremoso", _g("leite", "iogurte"), 1),
            Parte("toque doce", _g("mel", "acucar", "chocolate", "cacau", "granola", "aveia"), 1),
        ),
        no_titulo=False, checa_partes=False,
    ),
)
_POR_CHAVE: Dict[str, Arquetipo] = {a.chave: a for a in ARQUETIPOS}

# títulos de receita: doce, bebida e salgado "puro" (sem fruta doce)
_RE_TITULO_DOCE = re.compile(r"\b(bolo|pudim|brigadeiro|mousse|mingau|sobremesa|docinho|pave)\b")
_RE_TITULO_BEBIDA = re.compile(r"\b(vitamina|suco|smoothie|shake|batida)\b")
_RE_TITULO_SALGADO = re.compile(
    r"\b(sopa|caldo|canja|omelete|macarrao|espaguete|lasanha|risoto|strogonoff|quiche|escondidinho|hamburguer)\b"
)
_RE_CAFE_DA_MANHA = re.compile(r"\b(cafe da manha|desjejum)\b")

_NEGACOES = {"sem", "nao", "evitar", "evite", "odeio", "alergia", "alergico", "alergica", "intolerante", "nem"}


def _acha(arq: Arquetipo, texto_norm: str) -> bool:
    return bool(re.search(arq.gatilho, texto_norm))


def arquetipos_do_pedido(pedido: str) -> List[Arquetipo]:
    t = normalizar_texto(pedido or "")
    return [a for a in ARQUETIPOS if _acha(a, t)]


def arquetipos_do_titulo(titulo: str) -> List[Arquetipo]:
    t = normalizar_texto(titulo or "")
    return [a for a in ARQUETIPOS if a.no_titulo and _acha(a, t)]


def _alimentos_do_pedido(pedido: str, presentes: Set[str]) -> Tuple[Set[str], Set[str]]:
    """(alimentos pedidos que o usuário tem, alimentos recusados no pedido: 'sem cebola')."""
    palavras = re.findall(r"[a-z]+", normalizar_texto(pedido or ""))
    pedidos: Set[str] = set()
    negados: Set[str] = set()
    for i, p in enumerate(palavras):
        c = _canon(p)
        if c not in ALIMENTOS:
            continue
        if any(w in _NEGACOES for w in palavras[max(0, i - 3):i]):
            negados.add(c)
        elif c in presentes:
            pedidos.add(c)
    return pedidos, negados


# --------------------------------------------------------------------------- #
# Sugestões para o prompt
# --------------------------------------------------------------------------- #
def _montar_combinacao(arq: Arquetipo, itens, proibidos: Set[str], preferidos: Set[str], negados: Set[str]):
    """Escolhe, entre os itens do inventário, os que preenchem os papéis do prato. None se não der para montar."""
    usados: Set[int] = set()
    selecionados: Set[str] = set()
    nomes: List[str] = []
    preenchidas = 0
    vetados = set(proibidos) | set(negados)
    for parte in arq.partes:
        candidatos = [i for i, (_, toks) in enumerate(itens)
                      if i not in usados and set(toks) & parte.grupo and not (set(toks) & vetados)]
        candidatos.sort(key=lambda i: (not (set(itens[i][1]) & preferidos), i))   # pedidos primeiro, depois a ordem de validade
        pegos = 0
        for i in candidatos:
            if pegos >= parte.maximo:
                break
            novos = selecionados | set(itens[i][1])
            if _conflitos(novos):
                continue
            usados.add(i)
            selecionados = novos
            nomes.append(itens[i][0])
            pegos += 1
        if pegos:
            preenchidas += 1
        elif parte.obrigatoria:
            return None
    if len(selecionados) < arq.minimo_alimentos:
        return None
    return {"arq": arq, "nomes": nomes, "alimentos": selecionados, "pontos": len(nomes) + preenchidas}


def sugerir_combinacoes(
    inventario: Sequence[Union[str, Dict]], pedido: str = "", proibidos: Iterable[str] = (), limite: int = 3,
) -> List[str]:
    """Combinações que o inventário permite, no formato 'Lanche: pão + queijo + tomate'.

    Se o pedido cita um tipo de prato (lanche, macarrão, almoço...), só ele é sugerido; se cita alimentos,
    só entram combinações que os usam. Itens que vencem primeiro (início da lista) têm preferência.
    """
    itens = _itens_do_inventario(inventario)
    if not itens:
        return []
    proibidos = set(proibidos)
    presentes = {t for _, toks in itens for t in toks}
    preferidos, negados = _alimentos_do_pedido(pedido, presentes)

    do_pedido = arquetipos_do_pedido(pedido)
    candidatos = do_pedido or list(ARQUETIPOS)
    montados = []
    for ordem, arq in enumerate(candidatos):
        m = _montar_combinacao(arq, itens, proibidos, preferidos, negados)
        if m is None or (preferidos and not (m["alimentos"] & preferidos)):
            continue
        m["ordem"] = ordem
        montados.append(m)
    if not do_pedido:
        montados.sort(key=lambda m: (-m["pontos"], m["ordem"]))
    elif len(do_pedido) > 2:
        montados.sort(key=lambda m: (-m["pontos"], m["ordem"]))
    return [f"{m['arq'].sugestao}: {' + '.join(m['nomes'])}" for m in montados[:max(1, limite)]]


def incompatibilidades_no_inventario(
    inventario: Sequence[Union[str, Dict]], proibidos: Iterable[str] = (), limite: int = 4,
) -> List[str]:
    """Pares do inventário que não devem ir juntos no mesmo prato ('arroz com macarrão')."""
    itens = _itens_do_inventario(inventario)
    vetados = set(proibidos)
    ordem: List[str] = []
    for _, toks in itens:
        for t in toks:
            if t not in ordem and t not in vetados:
                ordem.append(t)
    return [f"{a} com {b}" for a, b, _ in _pares_conflitantes(set(ordem), ordem)][:limite]


def texto_orientacao(
    inventario: Sequence[Union[str, Dict]], pedido: str = "", proibidos: Iterable[str] = (),
) -> str:
    """Linhas para o prompt: combinações possíveis e o que não misturar. Vazio se não houver o que dizer."""
    proibidos = set(proibidos)
    linhas: List[str] = []
    sugestoes = sugerir_combinacoes(inventario, pedido, proibidos)
    if sugestoes:
        linhas.append(
            "Combinações que fazem sentido com o que há no inventário (guia: escolha UMA, o pedido do usuário "
            "continua mandando): " + " | ".join(sugestoes) + "."
        )
    avisos = incompatibilidades_no_inventario(inventario, proibidos)
    if avisos:
        linhas.append("Estes itens NÃO combinam no mesmo prato, não os misture: " + "; ".join(avisos) + ".")
    return "\n".join(linhas)


# --------------------------------------------------------------------------- #
# Conferência da receita pronta
# --------------------------------------------------------------------------- #
def _checar_partes(arq: Arquetipo, presentes: Set[str], itens, proibidos: Set[str]) -> List[str]:
    problemas: List[str] = []
    vazias: List[Parte] = []
    for parte in arq.partes:
        usados = presentes & parte.grupo
        exemplos = _exemplos(parte.grupo, itens, proibidos)
        if not usados:
            if parte.obrigatoria and not parte.coberta and exemplos:
                problemas.append(
                    f"o prato é {arq.rotulo}, mas não tem {parte.rotulo}. Use {_lista_em_texto(exemplos)} "
                    f"(que você tem) como {parte.rotulo}, no modo de preparo e na lista de ingredientes."
                )
            elif exemplos:
                vazias.append(parte)
        elif len(usados) < parte.minimo and len(_exemplos(parte.grupo, itens, proibidos, parte.minimo)) >= parte.minimo:
            problemas.append(
                f"{arq.rotulo} precisa de pelo menos {parte.minimo} itens de {parte.rotulo}; a receita só tem "
                f"{_lista_em_texto([_nome(t) for t in sorted(usados)])}. Acrescente mais um que combine."
            )

    if not problemas and len(presentes) < arq.minimo_alimentos and vazias:
        sugestoes = _lista_em_texto([e for p in vazias for e in _exemplos(p.grupo, itens, proibidos, 1)][:3])
        problemas.append(
            f"o prato {arq.rotulo} está simples demais, com poucos ingredientes. Complete com {sugestoes} "
            "(que você tem), para o prato ficar completo."
        )
    return problemas


def verificar_combinacoes(
    titulo: str,
    ingredientes: Sequence[str],
    passos: Sequence[str],
    pedido: str,
    inventario: Sequence[Union[str, Dict]],
    proibidos: Iterable[str] = (),
) -> List[str]:
    """Problemas de combinação da receita, cada um como frase pronta para o campo CORREÇÃO (vazio = tudo certo).

    titulo/ingredientes/passos: partes da receita já padronizada. inventario: o que o usuário tem.
    proibidos: alimentos vetados pelas restrições (não são sugeridos como correção).
    """
    proibidos = set(proibidos)
    ordem = _alimentos_da_lista(ingredientes)
    presentes = set(ordem)
    if not presentes:
        return []
    titulo_norm = normalizar_texto(titulo or "")
    pedido_norm = normalizar_texto(pedido or "")
    itens = _itens_do_inventario(inventario)
    problemas: List[str] = []

    # 1. pares que não combinam
    for a, b, motivo in _pares_conflitantes(presentes, ordem, titulo_norm):
        problemas.append(
            f"a receita mistura {a} com {b}, que não combinam no mesmo prato ({motivo}). "
            "Refaça com um prato em que só um dos dois apareça."
        )

    # 2. doce com doce, salgado com salgado
    doce_no_titulo = _RE_TITULO_DOCE.search(titulo_norm)
    bebida_no_titulo = _RE_TITULO_BEBIDA.search(titulo_norm)
    sobremesa_pedida = _acha(_POR_CHAVE["sobremesa"], pedido_norm)
    if doce_no_titulo or bebida_no_titulo or sobremesa_pedida:
        proibidos_doce = NAO_DOCE
        if bebida_no_titulo and not doce_no_titulo:
            proibidos_doce = NAO_DOCE | QUEIJOS | OVO | _g("pao")
        salgados = [_nome(t) for t in ordem if t in proibidos_doce]
        if salgados:
            tipo = (doce_no_titulo or bebida_no_titulo).group(1) if (doce_no_titulo or bebida_no_titulo) \
                else "sobremesa"
            problemas.append(
                f"a receita é de {tipo} (doce), mas leva {_lista_em_texto(salgados[:3])}, que são salgados. "
                "Faça só com ingredientes que combinam com doce (frutas, leite, aveia, mel) ou mude o prato."
            )
    elif _RE_TITULO_SALGADO.search(titulo_norm) and not (presentes & (PROTEINAS_ANIMAIS | LEGUMINOSAS)):
        frutas = [_nome(t) for t in ordem if t in FRUTAS_DOCES]
        if frutas:
            problemas.append(
                f"o prato é salgado ({_RE_TITULO_SALGADO.search(titulo_norm).group(1)}), mas leva "
                f"{_lista_em_texto(frutas[:2])}, que é fruta doce. Tire a fruta ou faça uma receita doce."
            )

    # 3. tipo de refeição pedido
    if _RE_CAFE_DA_MANHA.search(pedido_norm):
        pesados = [_nome(t) for t in ordem if t in PESADOS_DE_ALMOCO]
        if pesados:
            problemas.append(
                f"o pedido foi café da manhã, mas a receita leva {_lista_em_texto(pesados[:3])}, que é comida de "
                "almoço. Monte um café da manhã de verdade, com pão, tapioca, cuscuz, ovo, queijo, frutas, leite ou "
                "iogurte."
            )
    if _acha(_POR_CHAVE["refeicao"], pedido_norm) and (doce_no_titulo or bebida_no_titulo):
        problemas.append(
            "o pedido foi uma refeição (almoço ou jantar), mas a receita é de doce ou bebida. Faça um prato salgado "
            "com proteína e acompanhamento."
        )

    # 4. papéis do prato (pão + recheio, massa + molho, proteína + base...)
    conferir: List[Arquetipo] = list(arquetipos_do_titulo(titulo))
    for arq in arquetipos_do_pedido(pedido):
        if arq.no_pedido and arq not in conferir and not (doce_no_titulo or bebida_no_titulo):
            conferir.append(arq)
    for arq in conferir:
        if arq.checa_partes:
            problemas += _checar_partes(arq, presentes, itens, proibidos)

    vistos: List[str] = []
    return [p for p in problemas if not (p in vistos or vistos.append(p))]
