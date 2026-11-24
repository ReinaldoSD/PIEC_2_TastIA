"""Esqueleto da receita do TastIA: o CÓDIGO escolhe o prato e o MODELO só escreve o modo de preparo.

Por que existe (veja os resultados de avaliação): o modelo pequeno errava justamente nas partes que o código já
sabe fazer com segurança, e cada erro custava uma nova geração de vários minutos:

  - inventava ingredientes ('frango' e 'arroz' num pedido de macarrão), repetia linhas em loop e copiava o exemplo;
  - escrevia título, tempo e porções fora do formato, ou quantidades acima do que o usuário tem;
  - gastava 400 a 600 tokens por tentativa para escrever tudo.

Agora, quando o pedido permite (um tipo de prato conhecido ou um pedido livre só com alimentos do inventário), este
módulo monta de forma determinística:

  1. o PRATO: escolhe, entre os itens do inventário, os que cumprem os papéis do prato (lanche = pão + recheio...),
     usando as mesmas tabelas de combinacoes.py, sem misturar o que não combina e respeitando as restrições;
  2. o CABEÇALHO: título, tempo de preparo, porções e a lista de ingredientes com quantidade e unidade certas,
     nunca acima da quantidade que o usuário tem;
  3. o PREFIXO do prompt: o início da resposta do assistente, já escrito, terminando em 'Modo de preparo / 1.'.
     O modelo só continua dali (uns 150 tokens, em vez de 500) e não consegue mudar a lista nem o título;
  4. a RECEITA DE RESERVA: passos padrão do mesmo prato, usados só se todas as tentativas do modelo falharem,
     para o usuário nunca receber uma receita inválida.

Se o pedido cita um prato que não está aqui (bolo, pizza, lasanha, feijoada...) ou não dá para montar o prato com
o inventário, `escolher_pratos` devolve lista vazia e o gerador segue o caminho livre de sempre (o modelo escreve
tudo). Roda sem modelo e sem internet, então é fácil de testar.
"""
import re
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, Iterable, List, Optional, Sequence, Set, Tuple, Union

from receitas.coerencia import _PRECISA_COZINHAR, _prato_pedido_ausente_no_titulo, alimentos_proibidos
from receitas.combinacoes import (
    AVES, BOVINAS, FOLHAS, FRIOS, FRUTAS, GORDURAS_PAO, LEGUMINOSAS, MASSAS, OVO, PROTEINAS_REFEICAO, QUEIJOS,
    SALADA_DE_LANCHE, TUBERCULOS, VEGETAIS, _ACOMP_MASSA, _conflitos, _g, _nome_limpo, _tokens_linha,
    arquetipos_do_pedido,
)
from receitas.formatador import montar_texto, tempo_real_dos_passos
from receitas.prompt import dias_para_vencer
from receitas.reparos import disponivel
from receitas.unidades import _plural, quantidade_padrao
from receitas.validador import ALIMENTOS, DESCARTAR, _canon, normalizar_texto

PORCOES_ESQUELETO = "2"           # as quantidades de unidades.quantidade_padrao são para 2 porções
MAX_TOKENS_PASSOS = 260           # o modelo só escreve de 4 a 6 passos curtos


# --------------------------------------------------------------------------- #
# Grupos de alimentos (os nomes já normalizados: sem acento e no singular)
# --------------------------------------------------------------------------- #
PAO = _g("pao")
AROMAS = _g("cebola", "alho")
COZINHAR = frozenset(_PRECISA_COZINHAR) - _g("macarrao", "espaguete", "lasanha", "arroz", "feijao", "lentilha",
                                             "batata", "mandioca", "inhame")
EMBUTIDOS_FRITOS = _g("bacon", "linguica", "calabresa", "salsicha")
FOLHAS_CRUAS = FOLHAS | _g("pepino", "rabanete", "palmito", "azeitona")
FRUTAS_DE_SALADA = FRUTAS - _g("limao", "coco")
CITRICOS_ETC = _g("limao")
SALADA_COZIDOS = _g("ovo", "frango", "batata", "mandioca", "inhame")

_MINUTOS_COZIMENTO = {
    "ovo": 3, "mortadela": 3, "camarao": 5, "bacon": 5, "salsicha": 5, "linguica": 6, "calabresa": 6, "bife": 6,
    "carne": 8, "boi": 8, "bovino": 8, "peixe": 8, "frango": 10, "porco": 10, "suino": 10, "charque": 10,
}

_GENERO = {
    "pao": "o", "queijo": "o", "mussarela": "o", "presunto": "o", "ovo": "o", "tomate": "o", "macarrao": "o",
    "espaguete": "o", "leite": "o", "frango": "o", "peixe": "o", "arroz": "o", "bacon": "o", "atum": "o",
    "iogurte": "o", "cuscuz": "o", "pimentao": "o", "pepino": "o", "brocolis": "o", "milho": "o", "requeijao": "o",
    "parmesao": "o", "coalho": "o", "peru": "o", "salmao": "o", "camarao": "o", "alho": "o", "mel": "o",
    "batata": "a", "cenoura": "a", "cebola": "a", "carne": "a", "alface": "a", "manteiga": "a", "margarina": "a",
    "tapioca": "a", "banana": "a", "maca": "a", "laranja": "a", "abobrinha": "a", "abobora": "a", "mandioca": "a",
    "linguica": "a", "calabresa": "a", "salsicha": "a", "mortadela": "a", "ricota": "a", "couve": "a",
    "beterraba": "a", "berinjela": "a", "manga": "a", "mamao": "o", "abacate": "o", "morango": "o", "sardinha": "a",
    "aveia": "a", "granola": "a", "coco": "o", "chocolate": "o", "rucula": "a", "espinafre": "o", "repolho": "o", "chuchu": "o", "inhame": "o",
    "cogumelo": "o", "champignon": "o", "palmito": "o", "vagem": "a", "pera": "a", "uva": "a", "melancia": "a",
    "abacaxi": "o", "goiaba": "a", "acerola": "a", "tilapia": "a", "costela": "a", "coxa": "a",
    "lasanha": "a", "massa": "a", "farinha": "a", "acucar": "o", "fermento": "o", "canela": "a", "fuba": "o", "cacau": "o",
    "biscoito": "o", "bolacha": "a", "amido": "o", "maisena": "a", "pera": "a", "pessego": "o", "uva": "a",
    "linguica": "a", "ervilha": "a", "lentilha": "a", "bife": "o", "boi": "o", "porco": "o", "creme": "o",
    "nata": "a", "coentro": "o", "cebolinha": "a", "salsinha": "a", "salsa": "a", "gengibre": "o",
}


# --------------------------------------------------------------------------- #
# Definição dos pratos que o esqueleto sabe montar
# --------------------------------------------------------------------------- #
# partes: (rótulo, grupo de alimentos, máximo de itens, obrigatória)
_RECHEIO_LANCHE = QUEIJOS | FRIOS | OVO | AVES | BOVINAS | GORDURAS_PAO | _g(
    "atum", "sardinha", "bacon", "calabresa", "linguica", "salsicha")
_RECHEIO_CAFE = OVO | QUEIJOS | FRIOS | GORDURAS_PAO | _g("bacon")
_MOLHO_MASSA = _g("tomate", "cebola", "alho", "brocolis", "abobrinha", "cenoura", "cogumelo", "champignon",
                  "pimentao", "manteiga", "espinafre")
_BASE_REFEICAO = _g("arroz") | TUBERCULOS | MASSAS
_PROTEINA_REFEICAO = PROTEINAS_REFEICAO - LEGUMINOSAS - QUEIJOS - FRIOS
_RECHEIO_OMELETE = QUEIJOS | FRIOS | AVES | _g("bacon", "calabresa", "linguica", "espinafre") | (VEGETAIS - FOLHAS)
_BASE_SOPA = (VEGETAIS | TUBERCULOS | _g("macarrao", "arroz")) - FOLHAS_CRUAS - AROMAS
_RECHEIO_RISOTO = AVES | BOVINAS | QUEIJOS | (VEGETAIS - FOLHAS) | _g("alho", "bacon", "linguica")

DEFINICOES: Dict[str, Dict] = {
    "lanche": {
        "minutos": 10, "minimo": 2,
        "partes": (("pão", PAO, 1, True), ("recheio", _RECHEIO_LANCHE, 2, True),
                   ("vegetal", SALADA_DE_LANCHE - _g("cebola", "azeitona", "palmito"), 1, False)),
    },
    "cafe_salgado": {
        "minutos": 10, "minimo": 2,
        "partes": (("pão", PAO, 1, True), ("recheio", _RECHEIO_CAFE, 2, True)),
    },
    "macarrao": {
        "minutos": 25, "minimo": 2,
        "partes": (("macarrão", MASSAS, 1, True), ("proteína ou queijo", _ACOMP_MASSA - OVO, 1, False),
                   ("molho ou legume", _MOLHO_MASSA, 2, False)),
        "vetar": _g("ovo"),
    },
    "refeicao": {
        "minutos": 35, "minimo": 2,
        "partes": (("base", _BASE_REFEICAO, 1, False), ("proteína", _PROTEINA_REFEICAO, 1, True),
                   ("legume", VEGETAIS, 2, False)),
    },
    "salada_de_frutas": {
        "minutos": 10, "minimo": 2,
        "partes": (("fruta", FRUTAS_DE_SALADA, 3, True), ("complemento", _g("iogurte", "mel", "granola", "aveia"), 1,
                                                          False)),
    },
    "salada": {
        "minutos": 15, "minimo": 2,
        "partes": (("folhas ou legumes", VEGETAIS - _g("cebola"), 3, True),
                   ("proteína", OVO | AVES | _g("atum", "sardinha") | QUEIJOS | FRIOS, 1, False)),
    },
    "sopa": {
        "minutos": 35, "minimo": 2,
        "partes": (("base", _BASE_SOPA, 3, True), ("proteína", AVES | BOVINAS | _g("linguica", "bacon"), 1, False),
                   ("tempero", AROMAS, 2, False)),
    },
    "omelete": {
        "minutos": 10, "minimo": 1,
        "partes": (("ovo", OVO, 1, True), ("recheio", _RECHEIO_OMELETE, 2, False)),
    },
    "tapioca": {
        "minutos": 10, "minimo": 2,
        "partes": (("tapioca", _g("tapioca"), 1, True),
                   ("recheio", QUEIJOS | OVO | FRIOS | AVES | _g("coco", "banana", "chocolate"), 1, True)),
    },
    "cuscuz": {
        "minutos": 20, "minimo": 2,
        "partes": (("cuscuz", _g("cuscuz"), 1, True),
                   ("complemento", OVO | QUEIJOS | FRIOS | AVES | BOVINAS | _g("calabresa", "linguica", "manteiga"),
                    1, True)),
    },
    "risoto": {
        "minutos": 35, "minimo": 2,
        "partes": (("arroz", _g("arroz"), 1, True), ("recheio", _RECHEIO_RISOTO, 2, True)),
    },
    "vitamina": {
        "minutos": 5, "minimo": 1,
        "partes": (("fruta", FRUTAS - _g("limao"), 2, True), ("leite ou iogurte", _g("leite", "iogurte"), 1, False)),
    },
}
ORDEM = ("lanche", "cafe_salgado", "macarrao", "refeicao", "omelete", "tapioca", "cuscuz", "risoto", "sopa",
         "salada_de_frutas", "salada", "vitamina")
# nunca no esqueleto: leguminosas precisam de molho e de cozimento longo (o caminho livre trata isso no prompt)
VETADOS_SEMPRE = LEGUMINOSAS

# palavras de um pedido genérico ('algo rápido', 'o que dá para fazer com ovo')
_GENERICAS = frozenset(
    "algo alguma qualquer coisa rapido rapida facil simples pratico pratica gostoso gostosa receita receitas "
    "sugestao sugira sugere faz fazer preparar preparo quero queria gostaria preciso posso pode dar hoje agora noite "
    "dia bom boa pra opcao ideia ideias me uso usar usando tenho tem aqui casa minutos minuto hora leve saudavel "
    "barato economico criativo diferente favor vez bastante muito pouco pouca fome sobrou sobrando restou geladeira "
    "ajuda ajude o que qual quais vou quer vamos ter tenha so apenas somente mesmo tambem ainda mais menos "
    "agradavel nutritivo completo".split()
)


# quanto menor o número, mais típico do prato: o desempate quando a validade não decide (inventário sem datas)
_RANK_LEVE = {   # lanche, café da manhã, omelete, tapioca, cuscuz, salada
    **{t: 0 for t in QUEIJOS | _g("presunto", "peru", "tomate", "alface", "cenoura", "pepino")},
    **{t: 1 for t in OVO | _g("atum", "sardinha")},
    **{t: 2 for t in AVES | BOVINAS},
    **{t: 3 for t in _g("bacon", "calabresa", "linguica", "salsicha", "mortadela", "cebola", "alho")},
    **{t: 4 for t in GORDURAS_PAO},
}
_RANK_REFEICAO = {   # macarrão, almoço, sopa, risoto
    **{t: 0 for t in AVES | BOVINAS | _g("tomate", "cenoura", "batata", "abobrinha", "brocolis")},
    **{t: 1 for t in OVO | _g("atum", "sardinha", "pimentao", "cogumelo", "champignon", "espinafre")},
    **{t: 2 for t in _g("bacon", "calabresa", "linguica", "salsicha", "cebola", "alho", "alface")},
    **{t: 3 for t in QUEIJOS | _g("presunto", "peru", "mortadela") | GORDURAS_PAO},
}
_RANK_POR_PRATO = {c: _RANK_REFEICAO for c in ("macarrao", "refeicao", "sopa", "risoto")}
LIMITE_URGENTE = 7   # dias: o que vence em até uma semana passa na frente da afinidade


def _rank(chave: str, item: "Item") -> int:
    tabela = _RANK_POR_PRATO.get(chave, _RANK_LEVE)
    return min((tabela.get(t, 5) for t in item.tokens), default=5)


# --------------------------------------------------------------------------- #
# Estruturas
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Item:
    nome: str                  # 'carne moída' (minúsculas, sem parênteses)
    original: str              # como o usuário cadastrou ('Carne moída')
    tokens: Tuple[str, ...]    # alimentos reconhecidos (sem acento, no singular)
    quantidade: Optional[str]
    dias: Optional[int] = None  # dias para vencer (None = sem validade)

    @property
    def conjunto(self) -> Set[str]:
        return set(self.tokens)


@dataclass
class Prato:
    chave: str
    titulo: str
    tempo_min: int
    porcoes: str
    ingredientes: List[str]            # linhas '- 200 g de arroz' (já com a quantidade certa)
    passos: List[str]                  # passos padrão (receita de reserva)
    originais: List[str]               # nomes como o usuário cadastrou, na ordem de uso
    alimentos: Set[str] = field(default_factory=set)
    pontos: int = 0

    @property
    def prefixo(self) -> str:
        """Início da resposta do assistente: tudo pronto até 'Modo de preparo' e o '1.' do primeiro passo."""
        partes = [self.titulo, f"Tempo de preparo: {self.tempo_min} minutos", f"Porções: {self.porcoes}", "",
                  "Ingredientes"] + self.ingredientes + ["", "Modo de preparo", "1."]
        return "\n".join(partes)

    @property
    def texto_reserva(self) -> str:
        return montar_texto(self.titulo, f"{self.tempo_min} minutos", self.porcoes, self.ingredientes, self.passos)


# --------------------------------------------------------------------------- #
# Texto: artigos e listas
# --------------------------------------------------------------------------- #
def _com_artigo(nome: str) -> str:
    primeira = nome.split()[0] if nome.split() else ""
    genero = _GENERO.get(_canon(primeira))
    return f"{genero} {nome}" if genero else nome


def _do(nome: str) -> str:
    """'do pão', 'da tapioca', 'de queijo ralado' (de + artigo)."""
    art = _com_artigo(nome).split(" ", 1)[0] if _com_artigo(nome) != nome else ""
    return {"o": f"do {nome}", "a": f"da {nome}"}.get(art, f"de {nome}")


def _lista(textos: Sequence[str]) -> str:
    textos = list(textos)
    if len(textos) <= 1:
        return "".join(textos)
    return ", ".join(textos[:-1]) + " e " + textos[-1]


def _nomes(itens: Sequence[Item]) -> List[str]:
    return [i.nome for i in itens]


def _artigos(itens: Sequence[Item]) -> str:
    return _lista([_com_artigo(i.nome) for i in itens])


def _cap(texto: str) -> str:
    return texto[:1].upper() + texto[1:]


def _minutos(itens: Sequence[Item], padrao: int = 5) -> int:
    achados = [_MINUTOS_COZIMENTO[t] for i in itens for t in i.tokens if t in _MINUTOS_COZIMENTO]
    return max(achados) if achados else padrao


def _preparar(itens: Sequence[Item], forma: str = "em pedaços pequenos") -> str:
    """'Lave e corte o tomate em pedaços.' para vegetais e frutas; 'Corte o bacon em pedaços.' para o resto."""
    lavaveis, outros = _separar(itens, VEGETAIS | FRUTAS | _g("alho", "cebolinha", "salsinha"))
    frases = []
    if lavaveis:
        frases.append(f"Lave e corte {_artigos(lavaveis)} {forma}.")
    if outros:
        frases.append(f"Corte {_artigos(outros)} {forma}.")
    return " ".join(frases)


def _separar(itens: Sequence[Item], grupo: Iterable[str]):
    grupo = set(grupo)
    dentro = [i for i in itens if i.conjunto & grupo]
    return dentro, [i for i in itens if i not in dentro]


# --------------------------------------------------------------------------- #
# Quantidades (nunca acima do que o usuário tem)
# --------------------------------------------------------------------------- #
_RE_PADRAO = re.compile(r"^(\d+(?:[.,]\d+)?)\s*(?:(g|ml)\b)?\s*(?:de\s+)?(.*)$")
def _disponivel(item: Item):
    """(valor, 'g'|'ml'|'unidades') do que o usuário tem; None se não souber."""
    return disponivel(item.original, item.quantidade)


def _linha_item(item: Item, quantidade_fixa: Optional[int] = None) -> str:
    padrao = quantidade_padrao(item.original)
    if not padrao:
        return f"- {item.nome} a gosto"
    m = _RE_PADRAO.match(padrao)
    disp = _disponivel(item)
    if not m or disp is None and quantidade_fixa is None:
        return f"- {padrao}"
    numero, un, resto = float(m.group(1).replace(",", ".")), m.group(2), m.group(3)
    if un:   # peso ou volume
        if quantidade_fixa:
            numero = quantidade_fixa
        if disp and disp[1] == un and disp[0] < numero:
            numero = max(1, int(disp[0]))
        return f"- {int(numero)} {un} de {resto}"
    if re.match(r"^(dentes?|colher|colheres|xicara|pitada)", normalizar_texto(resto)):
        return f"- {padrao}"
    if quantidade_fixa:
        numero = quantidade_fixa
    if disp and disp[1] == "unidades" and disp[0] < numero:
        numero = max(1, int(disp[0]))
    numero = int(numero)
    return f"- {numero} {_plural(item.nome)}" if numero != 1 else f"- 1 {item.nome}"


_LINHA_BASICO = {
    "sal": "- sal a gosto",
    "oleo": "- 1 colher de sopa de óleo",
    "azeite": "- 1 colher de sopa de azeite",
    "agua": "- água o suficiente",
}
_ORDEM_BASICOS = ("oleo", "azeite", "agua", "sal")


# --------------------------------------------------------------------------- #
# Passos padrão de cada prato (receita de reserva)
# --------------------------------------------------------------------------- #
def _passos_lanche(p: Dict[str, List[Item]]):
    base, rec, veg = p["pão"][0], p["recheio"], p.get("vegetal", [])
    gord, rec = _separar(rec, GORDURAS_PAO)
    cozidos, crus = _separar(rec, COZINHAR)
    fatiaveis, outros = _separar(crus, QUEIJOS | FRIOS)
    passos: List[str] = []
    basicos: Set[str] = set()
    if veg:
        passos.append(f"Lave e fatie {_artigos(veg)}.")
    if fatiaveis:
        passos.append(f"Corte {_artigos(fatiaveis)} em fatias finas.")
    if outros:
        passos.append(f"Separe {_artigos(outros)}.")
    if cozidos:
        passos.append(f"Aqueça uma frigideira com um fio de óleo e cozinhe {_artigos(cozidos)} em fogo médio por "
                      f"{_minutos(cozidos)} minutos, com sal a gosto.")
        basicos |= {"oleo", "sal"}
    if gord:
        passos.append(f"Passe {_artigos(gord)} nas fatias {_do(base.nome)} e deixe dourar na frigideira "
                      "por 2 minutos de cada lado.")
    else:
        passos.append(f"Corte {_com_artigo(base.nome)} ao meio e deixe aquecer na frigideira por 2 minutos.")
    if rec or veg:
        passos.append(f"Monte o lanche: coloque {_artigos(rec + veg)} sobre {_com_artigo(base.nome)}.")
    queijo = any(i.conjunto & QUEIJOS for i in rec)
    passos.append("Feche o sanduíche e aqueça por mais 2 minutos até o queijo derreter, depois sirva em seguida."
                  if queijo else "Feche o sanduíche e sirva em seguida.")
    return passos, basicos


def _passos_macarrao(p):
    massa = p["macarrão"][0]
    prot = p.get("proteína ou queijo", [])
    mol = p.get("molho ou legume", [])
    aromas, resto = _separar(mol, AROMAS)
    gord, veg = _separar(resto, GORDURAS_PAO)
    queijos, prot = _separar(prot, QUEIJOS)
    cozidos, prontos = _separar(prot, COZINHAR)
    passos = [f"Cozinhe {_com_artigo(massa.nome)} em água fervente com sal por 10 minutos, escorra e reserve."]
    basicos = {"agua", "sal"}
    cortar = [i for i in aromas + veg if "molho" not in normalizar_texto(i.nome)]
    if cortar:
        passos.append(f"Pique {_artigos(cortar)}.")
    if aromas or cozidos:
        if aromas and cozidos:
            passos.append(f"Em uma panela, aqueça um fio de óleo, refogue {_artigos(aromas)} por 3 minutos e junte "
                          f"{_artigos(cozidos)}, mexendo até dourar, por cerca de {_minutos(cozidos)} minutos.")
        elif cozidos:
            passos.append(f"Em uma panela, aqueça um fio de óleo e doure {_artigos(cozidos)} por "
                          f"{_minutos(cozidos)} minutos, mexendo de vez em quando.")
        else:
            passos.append(f"Em uma panela, aqueça um fio de óleo e refogue {_artigos(aromas)} por 3 minutos.")
        basicos.add("oleo")
    if veg:
        passos.append(f"Acrescente {_artigos(veg)} e cozinhe por 8 minutos, até formar um molho.")
    if prontos:
        passos.append(f"Junte {_artigos(prontos)} e misture bem.")
    passos.append(f"Misture {_com_artigo(massa.nome)} cozido ao molho e deixe no fogo por 2 minutos"
                  + (f", acrescentando {_artigos(gord)}." if gord else "."))
    passos.append(f"Finalize com {_artigos(queijos)} e sirva quente." if queijos else "Acerte o sal e sirva quente.")
    return passos, basicos


def _passos_refeicao(p):
    base = p.get("base", [])
    prot = p["proteína"][0]
    legumes = p.get("legume", [])
    crus, cozidos_veg = _separar(legumes, FOLHAS_CRUAS | _g("tomate", "cebola"))
    passos: List[str] = []
    basicos: Set[str] = {"sal"}
    if base:
        b = base[0]
        if b.conjunto & _g("arroz"):
            passos.append(f"Lave {_com_artigo(b.nome)}, refogue por 1 minuto no óleo, junte o dobro de água e cozinhe "
                          "em fogo baixo por 15 minutos, com a panela tampada.")
            basicos |= {"oleo", "agua"}
        elif b.conjunto & MASSAS:
            passos.append(f"Cozinhe {_com_artigo(b.nome)} em água fervente com sal por 10 minutos e escorra.")
            basicos.add("agua")
        else:
            passos.append(f"Descasque e corte {_com_artigo(b.nome)} em cubos e cozinhe em água com sal por 15 minutos, "
                          "até ficar macia.")
            basicos.add("agua")
    passos.append(f"Tempere {_com_artigo(prot.nome)} com sal e doure em uma frigideira com um fio de óleo por "
                  f"{_minutos([prot], 8)} minutos, até cozinhar por completo.")
    basicos.add("oleo")
    if cozidos_veg:
        passos.append(f"Corte {_artigos(cozidos_veg)} e refogue na mesma frigideira por 5 minutos, até ficar macio.")
    if crus:
        passos.append(f"Lave e corte {_artigos(crus)} para acompanhar o prato.")
    itens_prato = [i for i in base] + [prot] + legumes
    passos.append(f"Monte o prato com {_artigos(itens_prato)} e sirva quente.")
    return passos, basicos


def _passos_salada_de_frutas(p):
    frutas, comp = p["fruta"], p.get("complemento", [])
    passos = [f"Lave, descasque e corte {_artigos(frutas)} em cubos.",
              "Coloque as frutas em uma tigela grande."]
    passos.append(f"Misture com {_artigos(comp)} delicadamente." if comp else "Misture delicadamente.")
    passos.append("Leve à geladeira por 15 minutos e sirva gelada.")
    return passos, set()


def _passos_salada(p):
    folhas, prot = p["folhas ou legumes"], p.get("proteína", [])
    cozidos = [i for i in folhas + prot if i.conjunto & SALADA_COZIDOS]
    crus = [i for i in folhas + prot if i not in cozidos]
    passos: List[str] = []
    basicos: Set[str] = {"sal", "azeite"}
    if cozidos:
        tempo_coz = "10 minutos" if all(i.conjunto & OVO for i in cozidos) else "15 minutos"
        passos.append(f"Cozinhe {_artigos(cozidos)} em água com sal por cerca de {tempo_coz}, deixe esfriar e corte "
                      "em pedaços.")
        basicos.add("agua")
    cortaveis = [i for i in crus if not (i.conjunto & _g("atum", "sardinha"))]
    prontos = [i for i in crus if i not in cortaveis]
    if cortaveis:
        passos.append(_preparar(cortaveis, "em pedaços"))
    if prontos:
        passos.append(f"Escorra {_artigos(prontos)}.")
    passos.append("Em uma tigela grande, misture tudo com cuidado.")
    passos.append("Tempere com sal e um fio de azeite e sirva em seguida.")
    return passos, basicos


def _passos_sopa(p):
    base, prot, temp = p["base"], p.get("proteína", []), p.get("tempero", [])
    graos, legumes = _separar(base, _g("macarrao", "arroz"))
    passos: List[str] = []
    if legumes:
        passos.append(f"Lave, descasque e corte {_artigos(legumes)} em cubos pequenos.")
    if temp:
        passos.append(f"Pique {_artigos(temp)}.")
    abertura = "Em uma panela, aqueça o óleo"
    if temp and prot:
        passos.append(f"{abertura}, refogue {_artigos(temp)} por 3 minutos e junte {_artigos(prot)}, mexendo até "
                      f"dourar, por cerca de {_minutos(prot)} minutos.")
    elif temp:
        passos.append(f"{abertura} e refogue {_artigos(temp)} por 3 minutos.")
    elif prot:
        passos.append(f"{abertura} e doure {_artigos(prot)} por {_minutos(prot)} minutos.")
    else:
        passos.append(f"{abertura} em fogo médio.")
    if legumes:
        passos.append(f"Acrescente {_artigos(legumes)}, cubra com água e cozinhe em fogo médio por 20 minutos, até "
                      "ficar macio.")
    else:
        passos.append("Cubra com água e deixe ferver.")
    if graos:
        passos.append(f"Junte {_artigos(graos)} e cozinhe por mais 10 minutos.")
    passos.append("Acerte o sal e sirva quente.")
    return passos, {"oleo", "agua", "sal"}


def _passos_omelete(p):
    ovo, rec = p["ovo"][0], p.get("recheio", [])
    cozidos, crus = _separar(rec, COZINHAR)
    passos: List[str] = []
    basicos = {"oleo", "sal"}
    if rec:
        passos.append(_preparar(rec))
    passos.append("Quebre os ovos em uma tigela, junte uma pitada de sal e bata com um garfo.")
    if cozidos:
        passos.append(f"Aqueça uma frigideira com um fio de óleo e refogue {_artigos(cozidos)} por "
                      f"{_minutos(cozidos)} minutos.")
    else:
        passos.append("Aqueça uma frigideira com um fio de óleo em fogo médio.")
    passos.append("Despeje os ovos batidos na frigideira" + (f", espalhe {_artigos(crus)} por cima" if crus else "")
                  + " e cozinhe por 3 minutos.")
    passos.append("Dobre a omelete ao meio, deixe mais 1 minuto no fogo e sirva em seguida.")
    return passos, basicos


def _passos_tapioca(p):
    tap, rec = p["tapioca"][0], p["recheio"][0]
    passos: List[str] = []
    if rec.conjunto & COZINHAR:
        passos.append(f"Cozinhe {_com_artigo(rec.nome)} em uma frigideira com um fio de óleo por "
                      f"{_minutos([rec], 4)} minutos e reserve.")
        basicos = {"oleo"}
    else:
        passos.append(f"Prepare {_com_artigo(rec.nome)}: corte em pedaços pequenos, se for preciso.")
        basicos = set()
    passos.append("Aqueça uma frigideira antiaderente em fogo médio.")
    passos.append(f"Espalhe {_com_artigo(tap.nome)} na frigideira, formando uma camada fina, e deixe por 2 minutos, "
                  "até firmar.")
    passos.append(f"Coloque {_com_artigo(rec.nome)} sobre metade da tapioca e dobre ao meio.")
    passos.append("Deixe mais 1 minuto no fogo e sirva em seguida.")
    return passos, basicos


def _passos_cuscuz(p):
    cus, comp = p["cuscuz"][0], p["complemento"][0]
    passos = [f"Em uma tigela, misture {_com_artigo(cus.nome)} com sal a gosto e um pouco de água, até hidratar bem.",
              "Deixe descansar por 5 minutos.",
              "Cozinhe no vapor, em panela com peneira ou cuscuzeira, por 10 minutos."]
    basicos = {"sal", "agua"}
    if comp.conjunto & COZINHAR:
        passos.append(f"Enquanto isso, cozinhe {_com_artigo(comp.nome)} em uma frigideira com um fio de óleo por "
                      f"{_minutos([comp], 4)} minutos.")
        basicos.add("oleo")
    elif comp.conjunto & (QUEIJOS | FRIOS):
        passos.append(f"Enquanto isso, corte {_com_artigo(comp.nome)} em fatias ou cubos.")
    else:
        passos.append(f"Enquanto isso, separe {_com_artigo(comp.nome)}.")
    passos.append(f"Sirva {_com_artigo(cus.nome)} quente, com {_com_artigo(comp.nome)}.")
    return passos, basicos


def _passos_risoto(p):
    arroz, rec = p["arroz"][0], p["recheio"]
    queijos, resto = _separar(rec, QUEIJOS)
    passos: List[str] = []
    if resto:
        passos.append(_preparar(resto, "em cubos pequenos"))
        passos.append(f"Em uma panela, aqueça o óleo e refogue {_artigos(resto)} por 5 minutos.")
    else:
        passos.append("Em uma panela, aqueça o óleo em fogo médio.")
    passos.append(f"Junte {_com_artigo(arroz.nome)} e mexa por 1 minuto, para envolver no óleo.")
    passos.append("Adicione água quente aos poucos, cerca de 3 xícaras no total, e cozinhe em fogo baixo por 20 "
                  "minutos, mexendo de vez em quando.")
    passos.append(f"Desligue o fogo, misture {_artigos(queijos)}, acerte o sal e sirva em seguida." if queijos
                  else "Acerte o sal e sirva em seguida.")
    return passos, {"oleo", "agua", "sal"}


def _passos_vitamina(p):
    frutas, leite = p["fruta"], p.get("leite ou iogurte", [])
    passos = [f"Lave, descasque e corte {_artigos(frutas)} em pedaços.",
              f"Coloque as frutas no liquidificador com {_artigos(leite)}." if leite
              else "Coloque as frutas no liquidificador com um pouco de água.",
              "Bata por 2 minutos, até ficar homogêneo.",
              "Sirva em seguida, bem gelada."]
    return passos, (set() if leite else {"agua"})


_PASSOS = {
    "lanche": _passos_lanche, "cafe_salgado": _passos_lanche, "macarrao": _passos_macarrao,
    "refeicao": _passos_refeicao, "salada_de_frutas": _passos_salada_de_frutas, "salada": _passos_salada,
    "sopa": _passos_sopa, "omelete": _passos_omelete, "tapioca": _passos_tapioca, "cuscuz": _passos_cuscuz,
    "risoto": _passos_risoto, "vitamina": _passos_vitamina,
}


# --------------------------------------------------------------------------- #
# Título
# --------------------------------------------------------------------------- #
def _titulo(chave: str, p: Dict[str, List[Item]], pedido_norm: str) -> str:
    def nomes(*rotulos) -> List[str]:
        return [i.nome for r in rotulos for i in p.get(r, [])]

    if chave == "lanche":
        palavra = "Sanduíche" if re.search(r"\b(sanduiche|misto)\b", pedido_norm) else "Lanche"
        return f"{palavra} de {_lista(nomes('pão', 'recheio', 'vegetal')[:4])}"
    if chave == "cafe_salgado":
        return f"Pão com {_lista(nomes('recheio'))}"
    if chave == "macarrao":
        massa = p["macarrão"][0].nome
        extras = nomes("proteína ou queijo", "molho ou legume")
        return _cap(f"{massa} com {_lista(extras[:3])}" if extras else massa)
    if chave == "refeicao":
        return _cap(f"{p['proteína'][0].nome} com {_lista(nomes('base', 'legume')[:3])}"
                    if nomes("base", "legume") else p["proteína"][0].nome)
    if chave == "salada_de_frutas":
        return f"Salada de frutas com {_lista(nomes('fruta'))}"
    if chave == "salada":
        return f"Salada de {_lista(nomes('folhas ou legumes', 'proteína')[:4])}"
    if chave == "sopa":
        palavra = "Caldo" if re.search(r"\bcaldo\b", pedido_norm) else "Sopa"
        return f"{palavra} de {_lista(nomes('base', 'proteína')[:4])}"
    if chave == "omelete":
        rec = nomes("recheio")
        return f"Omelete de {_lista(rec)}" if rec else "Omelete simples"
    if chave == "tapioca":
        return f"Tapioca com {_lista(nomes('recheio'))}"
    if chave == "cuscuz":
        return f"Cuscuz com {_lista(nomes('complemento'))}"
    if chave == "risoto":
        return f"Risoto de {_lista(nomes('recheio'))}"
    if chave == "vitamina":
        palavra = "Smoothie" if "smoothie" in pedido_norm else "Shake" if re.search(r"\bshake\b", pedido_norm) \
            else "Vitamina"
        leite = nomes("leite ou iogurte")
        return f"{palavra} de {_lista(nomes('fruta'))}" + (f" com {leite[0]}" if leite else "")
    return _cap(_lista(nomes(*p.keys())))


# --------------------------------------------------------------------------- #
# Seleção dos itens
# --------------------------------------------------------------------------- #
def _itens_do_inventario(ativos: Sequence[Dict]) -> List[Item]:
    itens: List[Item] = []
    for d in ativos:
        original = str(d.get("nome", "")).strip()
        tokens = _tokens_linha(original)
        if original and tokens:
            itens.append(Item(_nome_limpo(original), original, tuple(tokens), d.get("quantidade"),
                              dias_para_vencer(d.get("validade"))))
    return itens


def _montar(chave: str, itens: Sequence[Item], vetados: Set[str], preferidos: Set[str]):
    """Escolhe os itens que cumprem os papéis do prato. None se não der para montar com esse inventário."""
    d = DEFINICOES[chave]
    vet = set(vetados) | set(d.get("vetar", ())) | set(VETADOS_SEMPRE)
    if chave in ("lanche", "cafe_salgado", "refeicao"):
        vet |= {"tapioca", "cuscuz"}
    if preferidos & vet:
        return None   # o usuário pediu algo que o esqueleto não trata (ex.: feijão): segue o caminho livre
    usados: Set[int] = set()
    selecionados: Set[str] = set()
    papeis: Dict[str, List[Item]] = {}
    preenchidas = 0
    for rotulo, grupo, maximo, obrigatoria in d["partes"]:
        if chave == "salada":
            grupo = grupo | (TUBERCULOS & preferidos) | (_g("cebola") & preferidos)   # só se o pedido citar
        candidatos = [i for i, it in enumerate(itens) if i not in usados and it.conjunto & grupo
                      and not (it.conjunto & vet)]
        candidatos.sort(key=lambda i: (
            not (itens[i].conjunto & preferidos),                                   # o que o pedido cita
            not (itens[i].dias is not None and itens[i].dias <= LIMITE_URGENTE),   # o que vence logo
            _rank(chave, itens[i]),                                                 # o mais típico do prato
            i))
        pegos: List[Item] = []
        for i in candidatos:
            if len(pegos) >= maximo:
                break
            novos = selecionados | itens[i].conjunto
            if _conflitos(novos):
                continue
            usados.add(i)
            selecionados = novos
            pegos.append(itens[i])
        if pegos:
            papeis[rotulo] = pegos
            preenchidas += 1
        elif obrigatoria:
            return None
    if len(selecionados) < d["minimo"] or not (preferidos <= selecionados):
        return None
    if chave == "salada_de_frutas" and len(papeis.get("fruta", [])) < 2:
        return None
    if chave == "cuscuz" and "cuscuz" not in selecionados:
        return None
    if chave == "tapioca" and "tapioca" not in selecionados:
        return None
    return {"chave": chave, "papeis": papeis, "alimentos": selecionados,
            "pontos": sum(len(v) for v in papeis.values()) + preenchidas}


def _variantes(chave: str, itens, vetados: Set[str], preferidos: Set[str]) -> List[Dict]:
    """O prato principal e, para variar ('gerar outra receita'), os mesmos sem cada item opcional."""
    base = _montar(chave, itens, vetados, preferidos)
    if base is None:
        return []
    achados = [base]
    vistos = {tuple(sorted(i.nome for v in base["papeis"].values() for i in v))}
    for itens_papel in list(base["papeis"].values()):
        for it in itens_papel:
            if it.conjunto & preferidos:
                continue
            alt = _montar(chave, itens, vetados | it.conjunto, preferidos)
            if alt is None:
                continue
            chave_alt = tuple(sorted(i.nome for v in alt["papeis"].values() for i in v))
            if chave_alt not in vistos:
                vistos.add(chave_alt)
                achados.append(alt)
    return achados


def _basicos_em_linhas(basicos: Set[str]) -> List[str]:
    return [_LINHA_BASICO[b] for b in _ORDEM_BASICOS if b in basicos]


def _construir(m: Dict, pedido_norm: str, tempo_max: Optional[int]) -> Prato:
    chave, papeis = m["chave"], m["papeis"]
    d = DEFINICOES[chave]
    passos, basicos = _PASSOS[chave](papeis)
    ordem_itens = [i for itens in papeis.values() for i in itens]
    linhas = [_linha_item(i, 4 if chave == "omelete" and "ovo" in i.conjunto else None) for i in ordem_itens]
    linhas += _basicos_em_linhas(basicos)
    # tempo REAL: soma dos tempos dos passos + preparo. Nunca o tempo máximo pedido (o `tempo_max` só escolhe
    # pratos que cabem nele, em escolher_pratos; se nenhum couber, o tempo mostrado continua sendo o verdadeiro).
    minutos = tempo_real_dos_passos(passos, extra=d.get("extra", 0))
    return Prato(
        chave=chave, titulo=_titulo(chave, papeis, pedido_norm), tempo_min=minutos, porcoes=PORCOES_ESQUELETO,
        ingredientes=linhas, passos=passos, originais=[i.original for i in ordem_itens],
        alimentos=set(m["alimentos"]), pontos=m["pontos"],
    )


# --------------------------------------------------------------------------- #
# O pedido permite o esqueleto?
# --------------------------------------------------------------------------- #
def _pedido_so_com_alimentos(pedido_norm: str, itens: Sequence[Item]) -> bool:
    """True se o pedido não cita nenhum prato desconhecido: só palavras genéricas, alimentos ou itens do inventário."""
    do_inventario = {t for i in itens for p in normalizar_texto(i.original).split() for t in (p, _canon(p))}
    for palavra in re.findall(r"[a-z]+", pedido_norm):
        c = _canon(palavra)
        if (c in ALIMENTOS or palavra in _GENERICAS or c in DESCARTAR or palavra in DESCARTAR
                or palavra in do_inventario or c in do_inventario):
            continue
        return False
    return True


def escolher_pratos(
    ativos: Sequence[Dict],
    pedido: str,
    tempo: Optional[str] = None,
    restricoes: Optional[str] = None,
    urgentes: Sequence[str] = (),
    evitar: Optional[str] = None,
    limite: int = 4,
) -> List[Prato]:
    """Pratos que o inventário permite para o pedido, do melhor para o pior. Lista vazia = use o caminho livre.

    ativos: itens do inventário sem os vencidos, já ordenados pela validade (como devolve preparar_inventario).
    urgentes: nomes dos itens que vencem primeiro (têm preferência quando o pedido é genérico).
    evitar: título da receita anterior ('gerar outra'): o mesmo prato não volta.
    """
    itens = _itens_do_inventario(ativos)
    if not itens:
        return []
    pedido_norm = normalizar_texto(pedido or "")
    vetados = set(alimentos_proibidos(pedido, restricoes))
    presentes = {t for i in itens for t in i.tokens}

    # alimentos pedidos (e que o usuário tem), sem os negados ('sem cebola')
    palavras = re.findall(r"[a-z]+", pedido_norm)
    negacoes = {"sem", "nao", "evitar", "evite", "odeio", "alergia", "alergico", "alergica", "intolerante", "nem"}
    preferidos: Set[str] = set()
    for pos, palavra in enumerate(palavras):
        c = _canon(palavra)
        if c in ALIMENTOS and not any(w in negacoes for w in palavras[max(0, pos - 3):pos]):
            if c in presentes:
                preferidos.add(c)
    for pos, palavra in enumerate(palavras):
        c = _canon(palavra)
        if c in ALIMENTOS and any(w in negacoes for w in palavras[max(0, pos - 3):pos]):
            vetados.add(c)
            preferidos.discard(c)
    preferidos -= vetados

    do_pedido = [a.chave for a in arquetipos_do_pedido(pedido) if a.chave in DEFINICOES]
    nao_suportados = [a.chave for a in arquetipos_do_pedido(pedido)
                      if a.chave not in DEFINICOES and a.chave != "cafe_doce"]
    if nao_suportados:
        return []
    tempo_max = {"15": 15, "30": 30, "45": 45, "60": 60}.get(str(tempo or ""))
    if do_pedido:
        candidatos = [c for c in ORDEM if c in do_pedido]
    elif _pedido_so_com_alimentos(pedido_norm, itens):
        candidatos = list(ORDEM)
        if tempo_max:
            rapidos = [c for c in candidatos if DEFINICOES[c]["minutos"] <= tempo_max]
            candidatos = rapidos or candidatos
    else:
        return []

    tokens_urgentes: Set[str] = set()
    for nome in urgentes:
        tokens_urgentes |= set(_tokens_linha(nome))

    montados: List[Tuple[Tuple, Dict]] = []
    for posicao, chave in enumerate(candidatos):
        for m in _variantes(chave, itens, vetados, preferidos):
            ordem = (-len(m["alimentos"] & tokens_urgentes), -m["pontos"], posicao)
            montados.append((ordem, m))
    montados.sort(key=lambda x: x[0])

    pratos: List[Prato] = []
    vistos: Set[str] = set()
    anterior = normalizar_texto(evitar or "").strip()
    for _, m in montados:
        prato = _construir(m, pedido_norm, tempo_max)
        if _prato_pedido_ausente_no_titulo(pedido, prato.titulo):
            continue   # o pedido cita outro prato (hambúrguer, lasanha...): este esqueleto não serve
        titulo_norm = normalizar_texto(prato.titulo)
        if titulo_norm in vistos or (anterior and (titulo_norm == anterior or titulo_norm in anterior)):
            continue
        vistos.add(titulo_norm)
        pratos.append(prato)
        if len(pratos) >= max(1, limite) * (2 if tempo_max else 1):
            break
    if tempo_max:   # o tempo mostrado é o real: os pratos que realmente cabem no tempo escolhido vêm primeiro
        pratos.sort(key=lambda pr: pr.tempo_min > tempo_max)
    return pratos[:max(1, limite)]


# --------------------------------------------------------------------------- #
# Juntar o que o modelo escreveu ao prefixo
# --------------------------------------------------------------------------- #
_RE_CABECALHO = re.compile(r"(?im)^\W*(ingredientes?|modo de (preparo|fazer))\b")
_RE_PASSO_INICIAL = re.compile(r"^\s*\d+\s*[.)]\s*")


def eh_receita_completa(texto: Optional[str]) -> bool:
    """True se o modelo escreveu a receita inteira (com 'Ingredientes') em vez de só continuar nos passos."""
    t = str(texto or "")
    if _RE_PASSO_INICIAL.match(t):
        return False
    return bool(_RE_CABECALHO.search(t[:600]))


def juntar(prato: Prato, continuacao: Optional[str]) -> str:
    """Prefixo escrito pelo código + passos escritos pelo modelo (o '1.' do primeiro passo já está no prefixo)."""
    resto = _RE_PASSO_INICIAL.sub("", str(continuacao or "").strip(), count=1).strip()
    resto = re.sub(r"(?<=[.!?])[ \t]+(?=\d{1,2}[.)]\s)", "\n", resto)   # '... 2. Pique' na mesma linha -> nova linha
    return prato.prefixo + (" " + resto if resto else "")
