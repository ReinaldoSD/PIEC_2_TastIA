"""Checagens de qualidade da receita gerada (sem IA, roda sem modelo e sem internet).

O validador (validador.py) só confere se a receita usa ingredientes do inventário. Este módulo confere o
resto do que o usuário espera de uma receita BOA e que siga o que ele pediu:

  1. todo ingrediente tem quantidade ("300 g de queijo ralado", "2 ovos", "sal a gosto");
  2. todo ingrediente listado é usado no modo de preparo (ingredientes e passos combinam);
  3. o tempo de preparo não passa do máximo escolhido na tela;
  4. as restrições alimentares (vegetariano, vegano, sem lactose, sem glúten...) são respeitadas;
  5. os alimentos que o usuário citou no pedido (e que ele tem) aparecem na receita;
  6. o tipo de prato pedido (sopa, omelete, bolo, salada...) aparece no nome da receita;
  7. o nome da receita só cita alimentos que estão na lista de ingredientes;
  8. tudo o que o modo de preparo usa (alimentos e básicos como sal, óleo e água) está na lista de Ingredientes;
  9. a unidade de medida combina com o alimento (queijo em g, leite em ml, ovo em unidades);
 10. o prato tem sentido: o nome do prato tem seu ingrediente-chave (omelete sem ovo não vale), o que precisa de
     cozimento é cozido, não mistura fruta doce com carne/peixe, quantidades não são absurdas e o preparo
     tem passos suficientes;
 11. os alimentos combinam entre si (receitas/combinacoes.py): lanche tem pão e recheio, macarrão tem molho ou
     proteína, almoço tem proteína, salada tem legumes; nada de arroz com macarrão, peixe com leite, doce com
     carne, café da manhã com feijão...

Cada problema vira uma frase em português pronta para ir no campo "CORREÇÃO" do prompt da nova tentativa.
"""
import re
from typing import Dict, List, Optional, Sequence, Set

from receitas.combinacoes import verificar_combinacoes
from receitas.formatador import _estruturar
from receitas.unidades import unidade_errada
from receitas.validador import (
    ALIMENTOS, _canon, _eh_basico, _palavras, _subtokens, _tokens_inventario, normalizar_texto,
)

TEMPOS_MAXIMOS = {"15": 15, "30": 30, "45": 45, "60": 60}

# --------------------------------------------------------------------------- #
# 1. Quantidade
# --------------------------------------------------------------------------- #
_RE_TEM_QUANTIDADE = re.compile(
    r"\d|[½¼¾⅓⅔]|\ba gosto\b|\bpitadas?\b|\bfios?\b|\bpunhados?\b|\bmeio\b|\bmeia\b|"
    r"\bum\b|\buma\b|\bdois\b|\bduas\b|\btres\b|\bquatro\b|\bcinco\b"
)


def _sem_quantidade(ingredientes: Sequence[str]) -> List[str]:
    faltando = []
    for item in ingredientes:
        if item.endswith(":"):
            continue
        nucleo = _tokens_inventario(item)
        if not nucleo or _eh_basico(nucleo):   # sal, água, óleo... podem vir sem número
            continue
        if not _RE_TEM_QUANTIDADE.search(normalizar_texto(item)):
            faltando.append(re.sub(r"^[-*•]\s*", "", item).strip())
    return faltando


# --------------------------------------------------------------------------- #
# 1b. Quantidades exageradas ou irreais / fora da realidade
# --------------------------------------------------------------------------- #
_RE_MEDIDA_NUM = re.compile(
    r"(?:^|[-*•]\s*)(\d+(?:[.,]\d+)?)\s*(kg|g|gr|gramas?|ml|l|litros?|colheres?\s+de\s+sopa|colher\s+de\s+sopa)\b",
    re.IGNORECASE,
)

_TETOS_TOTAIS: Dict[str, float] = {
    "bacon": 250.0,
    "frango": 1500.0,
    "carne": 1500.0,
    "boi": 1500.0,
    "porco": 1500.0,
    "queijo": 600.0,
    "mussarela": 600.0,
    "macarrao": 1000.0,
    "espaguete": 1000.0,
    "arroz": 1000.0,
    "sal": 15.0,
    "oleo": 120.0,
    "azeite": 120.0,
    "oregano": 8.0,
    "pimenta": 10.0,
    "farinha": 1000.0,
    "trigo": 1000.0,
    "acucar": 500.0,
    "batata": 2000.0,
    "peixe": 1000.0,
    "leite": 2000.0,
}

# Teto de unidades inteiras numa receita caseira ('20 ovos', '15 pães' são quantidades fora da realidade)
_TETO_UNIDADES: Dict[str, float] = {"ovo": 12.0, "pao": 12.0, "tomate": 10.0, "cebola": 8.0, "batata": 12.0,
                                    "cenoura": 10.0, "banana": 12.0, "maca": 10.0, "laranja": 10.0, "limao": 10.0}
_RE_UNIDADES = re.compile(r"^(?:[-*•]\s*)?(\d+(?:[.,]\d+)?)\s*(?:unidades?\s+de\s+)?(?=[^\W\d_])", re.IGNORECASE)

# Mínimos razoáveis (em g ou ml) quando a receita usa medida de massa/volume para esses itens principais
_MINIMOS_TOTAIS: Dict[str, float] = {
    "bacon": 30.0,
    "frango": 80.0,
    "carne": 80.0,
    "boi": 80.0,
    "porco": 80.0,
    "queijo": 40.0,
    "mussarela": 40.0,
    "macarrao": 80.0,
    "espaguete": 80.0,
    "arroz": 80.0,
}

# Teto sugerido por porção (em g) para evitar exageros desproporcionais ao número de porções
_TETO_POR_PORCAO: Dict[str, float] = {
    "bacon": 60.0,
    "frango": 350.0,
    "carne": 350.0,
    "boi": 350.0,
    "porco": 350.0,
    "queijo": 150.0,
    "mussarela": 150.0,
}


def _para_base_comparavel(valor: float, unidade: str) -> Optional[float]:
    u = normalizar_texto(unidade).strip()
    if u in ("kg",):
        return valor * 1000.0
    if u in ("g", "gr", "grama", "gramas", "ml"):
        return valor
    if u in ("l", "litro", "litros"):
        return valor * 1000.0
    if "colher" in u and "sopa" in u:
        return valor * 15.0
    return None


def _numero_porcoes_float(valor: str) -> Optional[float]:
    if not valor:
        return None
    m = re.search(r"\d+(?:[.,]\d+)?", str(valor))
    if not m:
        return None
    try:
        num = float(m.group(0).replace(",", "."))
        return num if num > 0 else None
    except ValueError:
        return None


def _quantidades_exageradas(ingredientes: Sequence[str], porcoes_texto: str = "") -> List[str]:
    exageros: List[str] = []
    porcoes = _numero_porcoes_float(porcoes_texto)
    for item in ingredientes:
        if item.endswith(":"):
            continue
        m = _RE_MEDIDA_NUM.search(item)
        if not m:
            mu = _RE_UNIDADES.match(item.strip())
            if mu:
                try:
                    n_un = float(mu.group(1).replace(",", "."))
                except ValueError:
                    continue
                toks = _tokens_inventario(item)
                if any(_canon(k) in toks and n_un > lim for k, lim in _TETO_UNIDADES.items()):
                    exageros.append(re.sub(r"^[-*•]\s*", "", item).strip())
            continue
        try:
            qtd = float(m.group(1).replace(",", "."))
        except ValueError:
            continue
        base = _para_base_comparavel(qtd, m.group(2))
        if base is None:
            continue
        tokens = _tokens_inventario(item)
        limpo = re.sub(r"^[-*•]\s*", "", item).strip()

        for chave, limite in _TETOS_TOTAIS.items():
            if _canon(chave) in tokens and base > limite:
                if limpo not in exageros:
                    exageros.append(limpo)
                break

        for chave, minimo in _MINIMOS_TOTAIS.items():
            if _canon(chave) in tokens and base < minimo:
                if limpo not in exageros:
                    exageros.append(limpo)
                break

        if porcoes:
            for chave, teto_porcao in _TETO_POR_PORCAO.items():
                if _canon(chave) in tokens and (base / porcoes) > teto_porcao:
                    if limpo not in exageros:
                        exageros.append(limpo)
                    break

        if "pimenta" in tokens and "colher" in normalizar_texto(m.group(2)) and "sopa" in normalizar_texto(m.group(2)) and qtd >= 1:
            if limpo not in exageros:
                exageros.append(limpo)
    return exageros


# --------------------------------------------------------------------------- #
# 2. Ingredientes x modo de preparo
# --------------------------------------------------------------------------- #
def _tokens_texto(texto: str) -> Set[str]:
    return {sub for p in _palavras(texto) for sub in _subtokens(p)}


def _nao_usados_no_preparo(ingredientes: Sequence[str], passos: Sequence[str]) -> List[str]:
    usados = _tokens_texto(" ".join(passos))
    sobrando = []
    for item in ingredientes:
        if item.endswith(":"):
            continue
        nucleo = _tokens_inventario(item)
        if not nucleo or _eh_basico(nucleo):
            continue
        chave = {t for t in nucleo if t in ALIMENTOS} or nucleo
        # 'cheiro-verde' na lista e 'cebolinha' no passo (ou 'queijo' x 'mussarela') é o mesmo alimento
        if not any(_coberto(t, usados) for t in chave):
            sobrando.append(re.sub(r"^[-*•]\s*", "", item).strip())
    return sobrando


# --------------------------------------------------------------------------- #
# 3. Tempo
# --------------------------------------------------------------------------- #
def minutos_do_tempo(valor: str) -> Optional[int]:
    """'30 minutos' -> 30; '1 hora e 10 minutos' -> 70; 'cerca de 25 minutos' -> 25; sem número -> None."""
    t = normalizar_texto(valor or "")
    horas = re.search(r"(\d+)\s*(?:h\b|hora)", t)
    minutos = re.search(r"(\d+)\s*min", t)
    if horas or minutos:
        return (int(horas.group(1)) * 60 if horas else 0) + (int(minutos.group(1)) if minutos else 0)
    numero = re.search(r"\d+", t)
    return int(numero.group(0)) if numero else None


# --------------------------------------------------------------------------- #
# 4. Restrições alimentares
# --------------------------------------------------------------------------- #
_CARNES = {
    "frango", "carne", "boi", "bovino", "porco", "suino", "linguica", "salsicha", "bacon", "presunto",
    "peixe", "atum", "sardinha", "salmao", "tilapia", "camarao", "calabresa", "mortadela", "peru",
    "bife", "costela", "charque",
}
_LATICINIOS = {
    "leite", "queijo", "mussarela", "parmesao", "ricota", "requeijao", "coalho", "manteiga", "iogurte", "nata",
}
_PORCO = {"porco", "suino", "bacon", "linguica", "presunto", "calabresa", "mortadela", "costela"}
_GLUTEN = {"trigo", "macarrao", "espaguete", "lasanha", "pao", "biscoito", "bolacha", "aveia"}

# (nome para a mensagem, padrão no pedido/restrições, alimentos proibidos)
_RESTRICOES = [
    ("vegana", r"\bvegan[oa]s?\b", _CARNES | _LATICINIOS | {"ovo", "mel"}),
    ("vegetariana", r"\bvegetarian[oa]s?\b|\bsem carnes?\b|\bnao como carne\b", _CARNES),
    ("sem lactose", r"\bsem lactose\b|\bintolerante a lactose\b|\bintolerancia a lactose\b|\bsem leite\b",
     _LATICINIOS),
    ("sem glúten", r"\bsem gluten\b|\bceliac[oa]s?\b|\bintolerante a gluten\b", _GLUTEN),
    ("sem ovo", r"\bsem ovos?\b|\balergi\w* a ovos?\b", {"ovo"}),
    ("sem porco", r"\bsem porco\b|\bnao como porco\b", _PORCO),
]
# "leite de coco" não é laticínio
_RE_LEITE_VEGETAL = re.compile(r"\bleite de (?:coco|soja|amendoa|amendoas|castanha|aveia|arroz)\b")


def _proibidos_usados(texto: str, proibidos: Set[str]) -> List[str]:
    limpo = _RE_LEITE_VEGETAL.sub(" ", normalizar_texto(texto))
    achados: List[str] = []
    for p in _palavras(limpo):
        for sub in _subtokens(p):
            if sub in proibidos and sub not in achados:
                achados.append(sub)
    return achados


def _restricoes_violadas(texto_receita: str, pedido: str, restricoes: Optional[str]) -> List[str]:
    contexto = normalizar_texto(f"{pedido or ''} {restricoes or ''}")
    problemas = []
    for nome, padrao, proibidos in _RESTRICOES:
        if re.search(padrao, contexto):
            usados = _proibidos_usados(texto_receita, proibidos)
            if usados:
                problemas.append(
                    f"a receita precisa ser {nome}, mas usa: {', '.join(usados)}. "
                    "Refaça sem esses itens, escolhendo um prato que não dependa deles."
                )
    return problemas


def alimentos_proibidos(pedido: str, restricoes: Optional[str]) -> Set[str]:
    """Alimentos que as restrições do usuário (vegetariano, sem lactose...) proíbem."""
    contexto = normalizar_texto(f"{pedido or ''} {restricoes or ''}")
    proibidos: Set[str] = set()
    for _nome, padrao, itens in _RESTRICOES:
        if re.search(padrao, contexto):
            proibidos |= itens
    return proibidos


# --------------------------------------------------------------------------- #
# 5. Alimentos citados no pedido
# --------------------------------------------------------------------------- #
_NEGACOES = {"sem", "nao", "evitar", "evite", "odeio", "alergia", "alergico", "alergica", "intolerante", "nem"}


def _alimentos_pedidos(pedido: str, inventario: Sequence[str]) -> List[str]:
    """Alimentos que o pedido cita (sem negação, ex.: 'sem cebola') e que o usuário realmente tem."""
    tem: Set[str] = set()
    for nome in inventario:
        tem |= {t for t in _tokens_inventario(nome) if t in ALIMENTOS}
    palavras = re.findall(r"[a-z]+", normalizar_texto(pedido or ""))
    achados: List[str] = []
    for i, p in enumerate(palavras):
        c = _canon(p)
        if c in ALIMENTOS and c in tem and c not in achados:
            if not any(w in _NEGACOES for w in palavras[max(0, i - 3):i]):
                achados.append(c)
    return achados


def _alimentos_nao_usados_do_pedido(pedido: str, inventario: Sequence[str], ingredientes: Sequence[str]) -> List[str]:
    usados: Set[str] = set()
    for item in ingredientes:
        usados |= _tokens_inventario(item)
    return [a for a in _alimentos_pedidos(pedido, inventario) if a not in usados]


# --------------------------------------------------------------------------- #
# 6. Tipo de prato pedido x nome da receita
# --------------------------------------------------------------------------- #
_PRATOS = [
    {"sopa", "caldo", "creme"}, {"salada"}, {"vitamina", "smoothie", "shake"}, {"suco"},
    {"sanduiche", "lanche", "misto"}, {"pizza"}, {"risoto"}, {"lasanha"}, {"strogonoff"}, {"farofa"},
    {"mingau"}, {"torta"}, {"bolo"}, {"pudim"}, {"cuscuz"}, {"tapioca"}, {"omelete"},
    {"panqueca", "crepe"}, {"macarrao", "espaguete", "massa", "talharim"}, {"hamburguer"},
    {"brigadeiro"}, {"mousse"}, {"quiche"}, {"empada"}, {"coxinha"}, {"escondidinho"}, {"salpicao"},
]
_PRATOS = [{_canon(p) for p in grupo} for grupo in _PRATOS]


def _prato_pedido_ausente_no_titulo(pedido: str, titulo: str) -> Optional[str]:
    palavras = re.findall(r"[a-z]+", normalizar_texto(pedido or ""))
    tokens_titulo = {_canon(p) for p in re.findall(r"[a-z]+", normalizar_texto(titulo or ""))}
    for i, p in enumerate(palavras):
        c = _canon(p)
        for grupo in _PRATOS:
            if c in grupo and not any(w in _NEGACOES for w in palavras[max(0, i - 3):i]):
                if not (grupo & tokens_titulo):
                    return p
    return None


def pedido_especifico(pedido: str, inventario: Sequence[str]) -> bool:
    """True se o pedido já define o prato ou os alimentos (ex.: 'omelete', 'algo com macarrão').

    Nesse caso a validade dos ingredientes NÃO pode mandar na receita; só em pedidos genéricos
    ('algo rápido', 'o que dá pra fazer?') ela ajuda a escolher.
    """
    palavras = re.findall(r"[a-z]+", normalizar_texto(pedido or ""))
    if _alimentos_pedidos(pedido, inventario):
        return True
    return any(_canon(p) in grupo for p in palavras for grupo in _PRATOS)


# --------------------------------------------------------------------------- #
# 7. Nome da receita x ingredientes
# --------------------------------------------------------------------------- #
_GENERICOS = {
    "queijo": {"mussarela", "parmesao", "ricota", "requeijao", "coalho"},
    "carne": {"boi", "bovino", "bife", "costela", "charque"},
}


def _titulo_cita_alimento_ausente(titulo: str, ingredientes: Sequence[str]) -> List[str]:
    presentes: Set[str] = set()
    for item in ingredientes:
        presentes |= _tokens_inventario(item)
    ausentes: List[str] = []
    for p in _palavras(titulo):
        for sub in _subtokens(p):
            if sub in ALIMENTOS and sub not in presentes and not (_GENERICOS.get(sub, set()) & presentes):
                if p.lower() not in ausentes:
                    ausentes.append(p.lower())
    return ausentes


# --------------------------------------------------------------------------- #
# 8. Usado no preparo, mas fora da lista de Ingredientes
# --------------------------------------------------------------------------- #
_GRUPOS_EQUIVALENTES = [
    {_canon(t) for t in g} for g in (
        {"queijo", "mussarela", "parmesao", "ricota", "requeijao", "coalho"},
        {"carne", "boi", "bovino", "bife", "costela", "charque"},
        {"cheiro", "salsa", "salsinha", "cebolinha", "coentro"},
        {"oleo", "azeite"},
        {"farinha", "trigo"},
        {"porco", "suino"},
        {"pimentao", "pimenta"},
    )
]
BASICOS_DE_LISTA = {_canon(t) for t in ("sal", "agua", "oleo", "azeite", "pimenta", "oregano", "colorau", "cominho",
                                        "paprica", "louro", "tempero")}

_NOME_EXIBIDO = {"oleo": "óleo", "agua": "água", "oregano": "orégano", "paprica": "páprica", "acucar": "açúcar"}


def _coberto(token: str, presentes: Set[str]) -> bool:
    if token in presentes:
        return True
    return any(token in g and (g & presentes) for g in _GRUPOS_EQUIVALENTES)


def usados_no_preparo_fora_da_lista(ingredientes: Sequence[str], passos: Sequence[str]) -> List[str]:
    """Alimentos e básicos que o modo de preparo usa mas que não estão em 'Ingredientes' (sem repetir, na ordem)."""
    listados: Set[str] = set()
    for item in ingredientes:
        if not item.endswith(":"):
            listados |= _tokens_inventario(item) | {_canon(p) for p in _palavras(item)}
    achados: List[str] = []
    for passo in passos:
        for p in _palavras(passo):
            for sub in _subtokens(p):
                if (sub in ALIMENTOS or sub in BASICOS_DE_LISTA) and not _coberto(sub, listados) and sub not in achados:
                    achados.append(sub)
    return achados


# --------------------------------------------------------------------------- #
# 10. Receita com sentido
# --------------------------------------------------------------------------- #
_PRATO_EXIGE = {
    "omelete": ({"ovo"}, "ovo"),
    "farofa": ({"farinha", "fuba", "mandioca"}, "farinha"),
    "tapioca": ({"tapioca", "goma"}, "tapioca"),
    "cuscuz": ({"cuscuz", "fuba", "milho"}, "cuscuz ou fubá"),
    "bolo": ({"farinha", "trigo", "fuba", "aveia", "maisena", "amido", "cacau", "chocolate"}, "farinha"),
    "pudim": ({"leite", "ovo", "coco"}, "leite ou ovo"),
    "panqueca": ({"farinha", "trigo", "aveia", "ovo"}, "farinha ou ovo"),
    "macarrao": ({"macarrao", "espaguete", "lasanha"}, "macarrão"),
    "risoto": ({"arroz"}, "arroz"),
    "pizza": ({"farinha", "trigo", "pao", "massa", "macarrao"}, "massa ou farinha"),
    "sanduiche": ({"pao", "tapioca", "biscoito"}, "pão"),
    "lanche": ({"pao", "tapioca", "biscoito"}, "pão"),
}
_PRATO_EXIGE = {_canon(k): ({_canon(t) for t in v[0]}, v[1]) for k, v in _PRATO_EXIGE.items()}

_PRECISA_COZINHAR = {_canon(t) for t in (
    "frango", "carne", "boi", "bovino", "porco", "suino", "linguica", "bacon", "calabresa", "peixe", "camarao",
    "salsicha", "bife", "costela", "ovo", "macarrao", "espaguete", "lasanha", "arroz", "feijao", "lentilha",
    "batata", "mandioca", "inhame", "mortadela",
)}
_RE_COZIMENTO = re.compile(
    r"\b(cozinh\w*|coz[ae]\w*|cozid\w*|frit\w*|assa\w*|asse\b|assad\w*|grelh\w*|refog\w*|ferv\w*|dour\w*|"
    r"sotei\w*|salte\w*|forno|frigideira|panela|fogo|micro-?ondas|chapa|airfryer|fritadeira|torre\w*)\b"
)
_FRUTAS_DOCES = {_canon(t) for t in (
    "banana", "abacaxi", "mamao", "melancia", "morango", "uva", "goiaba", "maracuja", "acerola", "caju", "pessego", "kiwi",
    "melao", "pera",
)}
_SALGADOS_FORTES = {_canon(t) for t in (
    "peixe", "atum", "sardinha", "frango", "carne", "boi", "bovino", "porco", "suino", "linguica", "calabresa",
    "bacon", "presunto", "salsicha", "feijao", "camarao", "mortadela", "peru", "bife", "costela", "charque",
)}


def _tokens_da_lista(ingredientes: Sequence[str]) -> Set[str]:
    achados: Set[str] = set()
    for item in ingredientes:
        if not item.endswith(":"):
            achados |= {t for t in _tokens_inventario(item) if t in ALIMENTOS}
    return achados


def _problemas_de_sentido(titulo: str, ingredientes: Sequence[str], passos: Sequence[str]) -> List[str]:
    problemas: List[str] = []
    na_lista = _tokens_da_lista(ingredientes)
    tokens_titulo = {_canon(p) for p in re.findall(r"[a-z]+", normalizar_texto(titulo or ""))}

    for prato, (exigidos, rotulo) in _PRATO_EXIGE.items():
        if prato in tokens_titulo and not any(_coberto(e, na_lista) for e in exigidos):
            problemas.append(
                f"o nome da receita é de {prato}, mas a lista de ingredientes não tem {rotulo}. "
                f"Faça um prato de {prato} de verdade, com {rotulo} nos ingredientes, ou mude o nome para o prato "
                "que os ingredientes realmente formam."
            )

    texto_passos = normalizar_texto(" ".join(passos))
    crus = sorted(a for a in na_lista if a in _PRECISA_COZINHAR)
    if crus and not _RE_COZIMENTO.search(texto_passos):
        problemas.append(
            "a receita usa " + ", ".join(crus[:3]) + " mas nenhum passo cozinha, frita ou assa. Inclua o passo de "
            "cozimento (fogo, forno ou panela), com o tempo, antes de servir."
        )

    doces = sorted(na_lista & _FRUTAS_DOCES)
    salgados = sorted(na_lista & _SALGADOS_FORTES)
    if doces and salgados:
        problemas.append(
            f"a receita mistura {doces[0]} com {salgados[0]}, o que não é um prato conhecido. Escolha um prato "
            "coerente: ou doce (com as frutas) ou salgado (com os demais ingredientes)."
        )

    ingr = [i for i in ingredientes if not i.endswith(":")]
    if len(ingr) >= 3 and len(passos) < 3:
        problemas.append(
            "o modo de preparo tem poucos passos para tantos ingredientes. Escreva de 4 a 7 passos numerados, na "
            "ordem real do preparo."
        )
    return problemas


# --------------------------------------------------------------------------- #
# Função principal
# --------------------------------------------------------------------------- #
def verificar_qualidade(
    texto: str,
    pedido: str,
    inventario: Sequence[str],
    tempo: Optional[str] = None,
    restricoes: Optional[str] = None,
) -> List[str]:
    """Devolve a lista de problemas de qualidade (vazia = receita boa), cada um como frase de correção.

    texto: receita já padronizada por formatar_receita. inventario: nomes dos ingredientes disponíveis.
    """
    _, d = _estruturar(texto, corrigir_unidades=False)   # a unidade errada é APONTADA aqui, não corrigida
    if d is None:   # sem 'Ingredientes'/'Modo de preparo': o validador já cuida disso
        return []
    ingredientes, passos, titulo = d["ingredientes"], d["passos"], d["titulo"]
    problemas: List[str] = []

    faltando = _sem_quantidade(ingredientes)
    if faltando:
        problemas.append(
            "estes ingredientes estão sem quantidade: " + ", ".join(faltando) + ". Escreva cada ingrediente como "
            "'- <quantidade> <unidade> de <ingrediente>' (por exemplo '- 300 g de queijo ralado' ou '- 2 ovos')."
        )

    exagerados = _quantidades_exageradas(ingredientes, d.get("porcoes", ""))
    if exagerados:
        problemas.append(
            "estes ingredientes têm quantidades fora da faixa ideal para a receita: " + ", ".join(exagerados)
            + ". Ajuste para quantidades realistas e proporcionais ao número de porções e aos temperos."
        )

    sobrando = _nao_usados_no_preparo(ingredientes, passos)
    if sobrando:
        problemas.append(
            "estes ingredientes estão na lista mas não aparecem no modo de preparo: " + ", ".join(sobrando)
            + ". Use cada um deles em algum passo ou tire-os da lista."
        )

    maximo = TEMPOS_MAXIMOS.get(str(tempo or ""))
    minutos = minutos_do_tempo(d["tempo"])
    if maximo and minutos and minutos > maximo:
        problemas.append(
            f"o tempo de preparo escrito ({minutos} minutos) passa do máximo pedido ({maximo} minutos). "
            "Escolha um prato mais rápido ou simplifique as etapas."
        )

    corpo = " ".join([titulo] + ingredientes + passos)
    problemas += _restricoes_violadas(corpo, pedido, restricoes)

    nao_usados = _alimentos_nao_usados_do_pedido(pedido, inventario, ingredientes)
    if nao_usados:
        problemas.append(
            "o pedido do usuário cita " + ", ".join(nao_usados) + ", mas a receita não usa. Inclua esses itens."
        )

    prato = _prato_pedido_ausente_no_titulo(pedido, titulo)
    if prato:
        problemas.append(
            f"o pedido foi '{prato}', mas o nome da receita não é de {prato}. "
            f"Refaça uma receita de {prato}, com o nome do prato na primeira linha."
        )

    citados = _titulo_cita_alimento_ausente(titulo, ingredientes)
    if citados:
        problemas.append(
            "o nome da receita cita " + ", ".join(citados) + ", que não está na lista de ingredientes. "
            "Ajuste o nome para combinar com os ingredientes usados."
        )

    fora_da_lista = usados_no_preparo_fora_da_lista(ingredientes, passos)
    if fora_da_lista:
        problemas.append(
            "estes itens são usados no modo de preparo mas NÃO estão na lista de Ingredientes: "
            + ", ".join(_NOME_EXIBIDO.get(t, t) for t in fora_da_lista) + ". Coloque cada um na lista, com quantidade e unidade, ou não use no preparo."
        )

    errados = [l for l in (unidade_errada(i) for i in ingredientes if not i.endswith(":")) if l]
    if errados:
        problemas.append(
            "a unidade de medida está errada em: " + "; ".join(errados) + ". Queijo, carnes, arroz, farinha e "
            "similares vão em gramas (g); leite, suco e óleo em ml ou colheres; só ovos, frutas e legumes inteiros "
            "vão em unidades."
        )

    problemas += _problemas_de_sentido(titulo, ingredientes, passos)
    problemas += [
        p for p in verificar_combinacoes(
            titulo, ingredientes, passos, pedido, inventario, alimentos_proibidos(pedido, restricoes)
        ) if p not in problemas
    ]
    return problemas