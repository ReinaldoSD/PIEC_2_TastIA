"""Validador de receitas do TastIA.

Confere se a receita gerada pela IA:
  1. segue o formato esperado (título, 'Ingredientes', 'Modo de preparo');
  2. lista apenas ingredientes do inventário (ou básicos de despensa);
  3. não cita, no título ou no modo de preparo, alimentos que o usuário não tem.

É uma checagem heurística (sem IA): normaliza acentos, plural, quantidades,
unidades e palavras de preparo ("picado", "ralado"...) antes de comparar.
Roda sem baixar modelo e sem internet, então é fácil de testar.
"""
import re
import unicodedata
from dataclasses import dataclass, field, asdict
from typing import Dict, Iterable, List, Sequence, Set, Union


# --------------------------------------------------------------------------- #
# Normalização
# --------------------------------------------------------------------------- #
def normalizar_texto(texto: str) -> str:
    """minúsculas e sem acentos."""
    t = unicodedata.normalize("NFD", str(texto).lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def _singular(p: str) -> str:
    if len(p) <= 3:
        return p
    if p.endswith("oes") or p.endswith("aes"):
        return p[:-3] + "ao"
    if p.endswith("ais"):
        return p[:-3] + "al"
    if p.endswith("eis"):
        return p[:-3] + "el"
    if p.endswith(("res", "zes")) and len(p) > 4:  # colheres -> colher, nozes -> noz
        return p[:-2]
    if p.endswith("s") and not p.endswith(("ss", "us", "is")):
        return p[:-1]
    return p


# nomes regionais / grafias diferentes do mesmo alimento (já normalizados, no singular)
SINONIMOS: Dict[str, str] = {
    "aipim": "mandioca",
    "macaxeira": "mandioca",
    "jerimum": "abobora",
    "mucarela": "mussarela",
    "muzzarela": "mussarela",
    "mozzarela": "mussarela",
    "catchup": "ketchup",
    "batatinha": "batata",
}


def _canon(palavra: str) -> str:
    p = _singular(normalizar_texto(palavra))
    return SINONIMOS.get(p, p)


def _conjunto(palavras: str) -> Set[str]:
    return {_canon(p) for p in palavras.split()}


def _com_feminino(palavras: str) -> str:
    saida = []
    for p in palavras.split():
        saida.append(p)
        if p.endswith("o"):
            saida.append(p[:-1] + "a")
    return " ".join(saida)


# --------------------------------------------------------------------------- #
# Vocabulários
# --------------------------------------------------------------------------- #
_STOP = _conjunto(
    "de da do das dos a o as os e em com sem para por no na nos nas um uma uns umas ou ao aos "
    "gosto quanto bastar suficiente opcional cerca aproximadamente mais menos ate cada fio "
    "dois duas tres quatro cinco seis sete oito nove dez meio meia metade pouco pouca muito muita "
    "bem se que"
)

_UNIDADES = _conjunto(
    "g gr grama kg quilo ml l litro xicara colher sopa cha sobremesa cafe copo lata dente pitada "
    "fatia unidade pacote caixa punhado receita porcao talo maco ramo folha pote saco sache "
    "colherzinha concha pedaco cubo rodela tira gomo lasca"
)

_PREPARO = _conjunto(
    _com_feminino(
        "picado fatiado ralado cortado cozido cru fresco maduro inteiro moido descascado lavado "
        "pequeno medio fino grosso desfiado amassado batido escorrido temperado congelado seco "
        "refogado assado frito pronto grelhado limpo gelado picadinho"
    )
    + " grande quente frio morno fria"
)

DESCARTAR: Set[str] = _STOP | _UNIDADES | _PREPARO

# Básicos de despensa permitidos: palavra principal -> qualificadores aceitos junto dela.
BASICOS: Dict[str, Set[str]] = {
    "sal": _conjunto("grosso fino marinho refinado"),
    "agua": _conjunto("filtrada fervente mineral"),
    "oleo": _conjunto("soja girassol milho canola vegetal"),
    "azeite": _conjunto("oliva extra virgem"),
    "pimenta": _conjunto("reino preta branca moida"),
    "tempero": _conjunto("basico completo pronto seco"),
    "colorau": set(),
    "oregano": set(),
    "cominho": set(),
    "paprica": set(),
    "louro": set(),
}
_TOKENS_BASICOS: Set[str] = set(BASICOS) | {q for qs in BASICOS.values() for q in qs}

# Alimentos comuns. Servem para (a) achar alimentos citados no modo de preparo que o
# usuário não tem e (b) distinguir "queijo parmesão" (outro alimento) de "peito de frango"
# (só um corte do mesmo alimento).
ALIMENTOS: Set[str] = _conjunto(
    "frango carne boi bovino porco suino linguica salsicha bacon presunto peixe atum sardinha "
    "salmao tilapia camarao ovo calabresa mortadela peru bife costela charque "
    "leite queijo mussarela mucarela parmesao ricota requeijao coalho manteiga margarina iogurte nata "
    "arroz feijao lentilha grao ervilha milho aveia quinoa macarrao espaguete lasanha farinha fuba "
    "cuscuz tapioca goma pao biscoito bolacha trigo amido maisena farofa pipoca "
    "tomate cebola alho batata cenoura abobora abobrinha chuchu mandioca inhame beterraba pimentao "
    "pepino alface couve repolho espinafre brocolis rucula agriao coentro cebolinha salsa salsinha "
    "manjericao hortela vagem quiabo jilo berinjela cogumelo champignon palmito azeitona maxixe "
    "rabanete gengibre cheiro "
    "banana maca laranja limao abacaxi manga mamao melancia morango uva abacate coco maracuja "
    "goiaba acerola caju pera pessego melao kiwi tangerina mexerica "
    "acucar mel chocolate cacau vinagre ketchup mostarda maionese shoyu extrato fermento castanha "
    "amendoim noz granola vinho cerveja cachaca rapadura melado pacoca canela cravo"
)


# --------------------------------------------------------------------------- #
# Tokenização
# --------------------------------------------------------------------------- #
_RE_PAREN = re.compile(r"\([^)]*\)")
_RE_PALAVRA = re.compile(r"[^\W\d_]+(?:-[^\W\d_]+)*", re.UNICODE)


def _palavras(texto: str) -> List[str]:
    return _RE_PALAVRA.findall(_RE_PAREN.sub(" ", texto))


def _subtokens(palavra: str) -> List[str]:
    return [_canon(sub) for sub in palavra.split("-")]


def _analisar_trecho(trecho: str):
    """Devolve (conjunto de tokens úteis, nome para exibir)."""
    nucleo: Set[str] = set()
    exibir: List[str] = []
    for p in _palavras(trecho):
        uteis = [s for s in _subtokens(p) if s not in DESCARTAR]
        if uteis:
            nucleo.update(uteis)
            exibir.append(p.lower())
    return nucleo, " ".join(exibir)


def _tokens_inventario(nome: str) -> Set[str]:
    return _analisar_trecho(nome)[0]


def _eh_basico(nucleo: Set[str]) -> bool:
    return any(h in nucleo and (nucleo - {h}) <= quals for h, quals in BASICOS.items())


def _em_inventario(nucleo: Set[str], inventario: List[Set[str]]) -> bool:
    alimentos = {t for t in nucleo if t in ALIMENTOS}
    return any((nucleo & inv) and alimentos <= inv for inv in inventario)


# --------------------------------------------------------------------------- #
# Leitura da receita
# --------------------------------------------------------------------------- #
_RE_ING = re.compile(r"^ingredientes?\b")
_RE_PREPARO = re.compile(r"^(modo de (preparo|fazer)|preparo|instrucoes|como fazer|passo a passo)\b")
_RE_MARCADORES = re.compile(r"^[#*\s>_]+")
_RE_BULLET = re.compile(r"^\s*(?:[-*•·]+|\d+[.)])\s*")


def _dividir_secoes(texto: str) -> Dict:
    titulo = None
    estado = "inicio"
    achou_ing = achou_prep = False
    ing: List[str] = []
    prep: List[str] = []
    for linha in texto.splitlines():
        s = linha.strip()
        if not s:
            continue
        n = _RE_MARCADORES.sub("", normalizar_texto(s))
        if _RE_ING.match(n):
            estado, achou_ing = "ing", True
            continue
        if titulo is None:
            titulo = _RE_MARCADORES.sub("", s).strip("* ").strip()
            continue
        if _RE_PREPARO.match(n):
            estado, achou_prep = "prep", True
            continue
        if estado == "ing":
            ing.append(s)
        elif estado == "prep":
            prep.append(s)
    return {"titulo": titulo or "", "ing": ing, "prep": prep,
            "achou_ing": achou_ing, "achou_prep": achou_prep}


def _alternativas(linha: str) -> List[List[str]]:
    """'manteiga ou óleo' -> [['manteiga'], ['óleo']]; 'sal e pimenta' -> [['sal', 'pimenta']]."""
    limpa = _RE_BULLET.sub("", linha).replace("**", "")
    resultado = []
    for alt in re.split(r"\s+ou\s+", limpa, flags=re.I):
        itens = [i for i in re.split(r"\s+e\s+|,|;|\+|/", alt, flags=re.I) if i.strip()]
        resultado.append(itens)
    return resultado


def _avaliar_linha(linha: str, inventario: List[Set[str]]) -> Dict:
    """Devolve {'itens': n de itens reconhecidos, 'falhas': [nomes fora do inventário]}."""
    melhor = None
    n_itens = 0
    for alt in _alternativas(linha):
        falhas = []
        for item in alt:
            nucleo, exibir = _analisar_trecho(item)
            if not nucleo:
                continue
            n_itens += 1
            if _eh_basico(nucleo) or _em_inventario(nucleo, inventario):
                continue
            falhas.append(exibir)
        if not falhas:
            return {"itens": n_itens, "falhas": []}
        if melhor is None or len(falhas) < len(melhor):
            melhor = falhas
    return {"itens": n_itens, "falhas": melhor or []}


def _citados_no_texto(texto: str, cobertos: Set[str]) -> List[str]:
    achados: Dict[str, str] = {}
    for p in _palavras(texto):
        for sub in _subtokens(p):
            if sub in ALIMENTOS and sub not in cobertos and sub not in achados:
                achados[sub] = p.lower()
    return list(achados.values())


# --------------------------------------------------------------------------- #
# Resultado e função principal
# --------------------------------------------------------------------------- #
@dataclass
class ResultadoValidacao:
    valido: bool
    estrutura_ok: bool
    fora_do_inventario: List[str] = field(default_factory=list)   # listados em 'Ingredientes'
    citados_no_preparo: List[str] = field(default_factory=list)   # citados no título/preparo

    @property
    def problemas(self) -> List[str]:
        vistos, saida = set(), []
        for nome in self.fora_do_inventario + self.citados_no_preparo:
            chave = _canon(nome.split()[0]) if nome.split() else nome
            if nome not in vistos and chave not in vistos:
                vistos.update({nome, chave})
                saida.append(nome)
        return saida

    def como_dict(self) -> dict:
        d = asdict(self)
        d["problemas"] = self.problemas
        return d


def validar_receita(texto: str, inventario: Sequence[Union[str, Dict]]) -> ResultadoValidacao:
    """Confere se a receita só cita ingredientes do inventário (ou básicos de despensa).

    inventario: lista de nomes (str) ou de dicts com a chave 'nome'.
    """
    nomes = [i["nome"] if isinstance(i, dict) else str(i) for i in inventario]
    inv_tokens = [t for t in (_tokens_inventario(n) for n in nomes) if t]

    secoes = _dividir_secoes(texto or "")
    fora: List[str] = []
    n_itens = 0
    for linha in secoes["ing"]:
        if linha.rstrip().endswith(":") and not _RE_BULLET.match(linha):
            continue  # subtítulo como "Para o molho:"
        av = _avaliar_linha(linha, inv_tokens)
        n_itens += av["itens"]
        for nome in av["falhas"]:
            if nome not in fora:
                fora.append(nome)

    estrutura_ok = secoes["achou_ing"] and secoes["achou_prep"] and n_itens > 0

    cobertos: Set[str] = set().union(*inv_tokens) | _TOKENS_BASICOS if inv_tokens else set(_TOKENS_BASICOS)
    texto_preparo = "\n".join([secoes["titulo"]] + secoes["prep"])
    citados = [c for c in _citados_no_texto(texto_preparo, cobertos)]
    # não repete o que já foi apontado na lista de ingredientes
    ja = {_canon(w) for nome in fora for w in nome.split()}
    citados = [c for c in citados if _canon(c) not in ja]

    return ResultadoValidacao(
        valido=estrutura_ok and not fora and not citados,
        estrutura_ok=estrutura_ok,
        fora_do_inventario=fora,
        citados_no_preparo=citados,
    )
