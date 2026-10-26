import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from receitas.validador import normalizar_texto

# --------------------------------------------------------------------------- #
# Perfil do prato
# --------------------------------------------------------------------------- #
# Para cada tag: (padrões fortes, padrões fracos). A tag é atribuída se houver 1 padrão forte
# ou 2 padrões fracos diferentes. O texto é normalizado antes (minúsculas, sem acento).
_PADROES: Dict[str, Tuple[Sequence[str], Sequence[str]]] = {
    "apimentado": (
        [r"apimentad\w*", r"picante\w*", r"pimenta\b", r"pimentas\b", r"malagueta", r"jalapeno",
         r"curry", r"chili", r"chilli", r"sriracha", r"tabasco", r"ardid\w*"],
        [r"gengibre", r"paprica picante"],
    ),
    "frito": (
        [r"(?:re)?frit\w+", r"empanad\w+", r"milanesa", r"pastel\b", r"pasteis", r"coxinha", r"bolinho",
         r"croquete", r"torresmo", r"tempura", r"nugget\w*", r"a dorê", r"a dore"],
        [r"crocante\w*", r"oleo quente", r"muito oleo"],
    ),
    "doce": (
        [r"doces?\b", r"sobremesa", r"bolo\b", r"pudim", r"brigadeiro", r"mousse", r"sorvete",
         r"caramelo", r"goiabada", r"brownie", r"cocada", r"torta doce", r"leite condensado", r"calda"],
        [r"acucar", r"\bmel\b", r"banana", r"chocolate", r"canela", r"rapadura"],
    ),
    "leve": (
        [r"\bleve\b", r"\blight\b", r"saudavel", r"\bfit\b", r"refrescante", r"no vapor",
         r"pouca gordura", r"fresquinh\w*"],
        [r"salada", r"legumes?", r"verduras?", r"folhas?", r"rucula", r"pepino", r"\bfresc\w+"],
    ),
    "carne_vermelha": (
        [r"carne\b", r"carnes\b", r"\bboi\b", r"bovin\w+", r"bife\w*", r"costela\w*", r"picanha",
         r"churrasc\w+", r"hamburguer\w*", r"almondega\w*", r"alcatra", r"fraldinha", r"patinho",
         r"cordeiro", r"carne moida"],
        [r"grelhad\w+", r"\bassad\w+"],
    ),
    "porco": (
        [r"porcos?\b", r"suin\w+", r"bacon", r"linguica", r"calabresa", r"presunto", r"feijoada",
         r"costelinha", r"pernil", r"torresmo"],
        [],
    ),
    "aves": ([r"frango", r"\bperu\b", r"galinha", r"\baves?\b", r"sobrecoxa", r"coxa\b"], []),
    "peixe": ([r"peixe\w*", r"tilapia", r"salmao", r"atum", r"sardinha", r"bacalhau", r"merluza",
               r"moqueca"], []),
    "frutos_do_mar": ([r"camarao", r"camaroes", r"lula", r"polvo", r"marisco\w*", r"mexilha\w*",
                       r"\bsiri\b", r"caranguejo", r"frutos do mar"], []),
    "massa": ([r"macarrao", r"espaguete", r"lasanha", r"\bmassa\b", r"nhoque", r"penne",
               r"talharim", r"fettuccine", r"ravioli"], []),
    "queijo": ([r"queijo\w*", r"mussarela", r"parmesao", r"ricota", r"gorgonzola", r"coalho",
                r"provolone"], []),
    "cremoso": (
        [r"cremos\w+", r"\bcreme\b", r"requeijao", r"\bnata\b", r"molho branco", r"catupiry",
         r"leite condensado"],
        [r"\bleite\b", r"manteiga", r"iogurte", r"queijo\w*"],
    ),
    "vegetariano": ([r"vegetarian\w*", r"vegan\w*", r"sem carne", r"plant based"], [r"legumes?", r"cogumelo\w*"]),
    "salada": ([r"salada\w*"], [r"rucula", r"alface", r"agriao", r"folhas?"]),
    "ovo": ([r"\bovos?\b", r"omelete", r"ovos mexidos"], []),
    "arroz_feijao": ([r"arroz e feijao", r"prato feito", r"baiao"], [r"\barroz\b", r"\bfeijao\b"]),
    "sopa": ([r"\bsopa\b", r"\bcaldo\b", r"canja", r"\bcreme de\b"], []),
    "grelhado": ([r"grelhad\w+", r"churrasc\w+", r"brasa", r"na chapa"], [r"\bassad\w+"]),
    "tomate": ([r"molho de tomate", r"pomodoro", r"\bsugo\b", r"molho ao sugo", r"pizza"], [r"tomates?\b"]),
    "chocolate": ([r"chocolate", r"cacau", r"brigadeiro", r"brownie"], []),
    "lanche": ([r"lanche\w*", r"sanduiche\w*", r"hamburguer\w*", r"pizza", r"hot dog", r"torrada\w*",
                r"salgad\w+", r"tapioca"], []),
    "brasileira": ([r"feijoada", r"moqueca", r"baiao", r"farofa", r"pao de queijo", r"cuscuz",
                    r"acaraje", r"vatapa", r"escondidinho", r"arroz e feijao", r"churrasc\w+"], [r"mandioca", r"macaxeira"]),
}

def _comp(padrao: str):
    """Todo padrão começa em início de palavra (\\b): 'porco' não pode casar com 'porções'."""
    return re.compile(padrao if padrao.startswith(r"\b") else r"\b" + padrao)


_COMPILADOS = {
    tag: ([_comp(p) for p in fortes], [_comp(p) for p in fracos])
    for tag, (fortes, fracos) in _PADROES.items()
}

# O que o usuário diz sobre a ocasião/clima (vira um "perfil de ocasião", separado do prato)
_OCASIOES = {
    "calor": re.compile(r"calor|verao|praia|piscina|quente demais|dia quente|refrescar"),
    "frio": re.compile(r"\bfrio\b|inverno|friozinho|noite fria|aquecer"),
    "celebracao": re.compile(r"festa|comemora\w*|celebra\w*|brinde|aniversario|ano novo|natal|formatura"),
    "romantico": re.compile(r"romantic\w*|jantar a dois|casal|namorad\w*|date"),
    "casual": re.compile(r"happy hour|churrasc\w+|amigos|petisc\w*|boteco|futebol|jogo"),
}

# Termos descritivos usados para "enriquecer" o texto antes de comparar com o catálogo
DESCRICAO_TAG = {
    "apimentado": "apimentado picante pimenta ardência",
    "frito": "frito fritura gordura crocante",
    "doce": "doce sobremesa açúcar adocicado",
    "leve": "leve fresco refrescante saudável",
    "carne_vermelha": "carne vermelha churrasco encorpado",
    "porco": "porco suíno gordura",
    "aves": "frango ave",
    "peixe": "peixe",
    "frutos_do_mar": "frutos do mar camarão",
    "massa": "massa macarrão molho",
    "queijo": "queijo",
    "cremoso": "cremoso creme",
    "vegetariano": "vegetariano legumes",
    "salada": "salada folhas",
    "ovo": "ovo",
    "arroz_feijao": "arroz feijão brasileira",
    "sopa": "sopa caldo quente",
    "grelhado": "grelhado assado brasa",
    "tomate": "tomate molho de tomate ácido",
    "chocolate": "chocolate cacau",
    "lanche": "lanche sanduíche pizza",
    "brasileira": "brasileira",
}

_PIMENTA_DO_REINO = re.compile(r"pimenta[- ]do[- ]reino|pimenta[- ]preta|pimenta[- ]branca|pimenta[- ]em[- ]po")


def _texto_limpo(texto: str) -> str:
    t = normalizar_texto(texto or "")
    return _PIMENTA_DO_REINO.sub(" ", t)  # tempero básico: não deixa o prato "apimentado"


def perfil_do_prato(texto: str) -> List[str]:
    """Tags do prato (no vocabulário do catálogo), a partir do texto da receita ou da refeição."""
    t = _texto_limpo(texto)
    tags: List[str] = []
    for tag, (fortes, fracos) in _COMPILADOS.items():
        if any(p.search(t) for p in fortes):
            tags.append(tag)
        elif sum(1 for p in fracos if p.search(t)) >= 2:
            tags.append(tag)
    return tags


def perfil_de_ocasiao(texto: str) -> List[str]:
    t = normalizar_texto(texto or "")
    return [nome for nome, rx in _OCASIOES.items() if rx.search(t)]


def texto_expandido(texto: str, tags: Sequence[str]) -> str:
    """Texto original + descrição das tags detectadas (ajuda a comparação por similaridade)."""
    extra = " ".join(DESCRICAO_TAG[t] for t in tags if t in DESCRICAO_TAG)
    return f"{texto}\n{extra}".strip()


# --------------------------------------------------------------------------- #
# Regras de harmonização
# --------------------------------------------------------------------------- #
# Cada regra: (tag do prato, teste sobre a bebida, peso, motivo). Peso negativo = evitar.
# O motivo positivo é escrito para completar "…porque …".
def _s(b, nome):
    return nome in b["sabores"]


REGRAS = [
    # ---- apimentado: doçura, gás, frio e laticínios acalmam; álcool alto e amargor realçam a pimenta
    ("apimentado", lambda b: b["docura"] >= 1, 1.0, "a doçura suave ameniza a ardência da pimenta"),
    ("apimentado", lambda b: b["temperatura"] == "gelada", 0.6, "é servida bem gelada e refresca a boca"),
    ("apimentado", lambda b: b["gas"], 0.5, "o gás ajuda a limpar o paladar"),
    ("apimentado", lambda b: _s(b, "lacteo"), 0.8, "o laticínio acalma a sensação de ardência"),
    ("apimentado", lambda b: _s(b, "gengibre"), 0.4, "o gengibre refresca e acompanha o picante"),
    ("apimentado", lambda b: b["alcool"] and b["teor"] >= 12, -1.0, "álcool alto intensifica a ardência"),
    ("apimentado", lambda b: _s(b, "amargo") and not _s(b, "refrescante"), -0.8, "o amargor realça o picante"),
    ("apimentado", lambda b: _s(b, "tanico"), -0.8, "o tanino fica áspero com pimenta"),
    # ---- frito: gás e acidez cortam a gordura; doce, cremoso e encorpado pesam
    ("frito", lambda b: b["gas"], 1.0, "as borbulhas limpam a gordura da fritura"),
    ("frito", lambda b: b["acidez"] >= 3, 0.8, "a acidez alta corta a gordura"),
    ("frito", lambda b: b["temperatura"] == "gelada", 0.4, "é servida gelada e equilibra a untuosidade do frito"),
    ("frito", lambda b: b["docura"] == 2, -0.8, "muito doce pesa junto com fritura"),
    ("frito", lambda b: b["corpo"] == 3, -0.7, "o corpo encorpado deixa a combinação pesada"),
    ("frito", lambda b: _s(b, "cremoso"), -0.5, "cremoso demais para acompanhar fritura"),
    # ---- doce: a bebida precisa ser, no mínimo, tão doce quanto o prato
    ("doce", lambda b: b["docura"] == 2, 1.2, "acompanha a doçura do prato sem parecer azeda"),
    ("doce", lambda b: b["docura"] == 1, 0.4, "a doçura moderada conversa com a sobremesa"),
    ("doce", lambda b: _s(b, "tostado"), 0.5, "as notas tostadas contrastam bem com o doce"),
    ("doce", lambda b: b["docura"] == 0 and b["acidez"] >= 2 and not _s(b, "tostado"), -1.0,
     "bebida seca e ácida parece azeda ao lado de algo doce"),
    # ---- chocolate
    ("chocolate", lambda b: _s(b, "tostado") or b["docura"] == 2, 1.0, "as notas de café/cacau combinam com chocolate"),
    # ---- leve
    ("leve", lambda b: b["corpo"] == 1, 1.0, "o corpo leve não pesa em um prato leve"),
    ("leve", lambda b: _s(b, "refrescante"), 0.6, "é refrescante, como o prato"),
    ("leve", lambda b: b["corpo"] == 3, -1.0, "encorpada demais para um prato leve"),
    ("leve", lambda b: b["docura"] == 2, -0.5, "doce demais para um prato leve"),
    # ---- carnes
    ("carne_vermelha", lambda b: b["corpo"] == 3 and _s(b, "tanico"), 1.2,
     "o corpo e os taninos dão conta da carne vermelha"),
    ("carne_vermelha", lambda b: b["corpo"] >= 2, 0.6, "tem estrutura para acompanhar carne"),
    ("carne_vermelha", lambda b: b["corpo"] == 1 and b["alcool"], -0.6, "leve demais, some diante da carne"),
    ("porco", lambda b: b["acidez"] >= 2, 0.8, "a acidez equilibra a gordura do porco"),
    ("porco", lambda b: b["gas"], 0.4, "o gás limpa o paladar entre garfadas"),
    ("aves", lambda b: b["corpo"] == 2, 0.7, "o corpo médio acompanha a carne branca"),
    ("aves", lambda b: b["acidez"] >= 2, 0.5, "a acidez realça o sabor da ave"),
    ("aves", lambda b: b["corpo"] == 3, -0.4, "encorpada demais para ave"),
    # ---- peixes e frutos do mar
    ("peixe", lambda b: b["acidez"] >= 2 and b["corpo"] == 1, 1.0, "a acidez e o corpo leve realçam o peixe"),
    ("peixe", lambda b: _s(b, "citrico"), 0.7, "o toque cítrico combina com peixe"),
    ("peixe", lambda b: _s(b, "tanico"), -1.2, "o tanino choca com o sabor delicado do peixe"),
    ("frutos_do_mar", lambda b: b["acidez"] >= 2 and b["corpo"] == 1, 1.0, "a acidez e a leveza valorizam os frutos do mar"),
    ("frutos_do_mar", lambda b: b["gas"], 0.5, "o gás deixa a boca limpa a cada garfada"),
    ("frutos_do_mar", lambda b: _s(b, "tanico"), -1.2, "o tanino choca com frutos do mar"),
    # ---- massas, molhos, queijos
    ("tomate", lambda b: b["acidez"] >= 2, 1.0, "a acidez enfrenta bem o molho de tomate"),
    ("tomate", lambda b: b["docura"] == 2, -0.5, "doce demais para um molho ácido"),
    ("massa", lambda b: b["corpo"] == 2, 0.5, "o corpo médio acompanha a massa"),
    ("queijo", lambda b: b["acidez"] >= 2, 0.7, "a acidez equilibra a gordura do queijo"),
    ("queijo", lambda b: b["gas"], 0.4, "as borbulhas refrescam entre as mordidas"),
    ("cremoso", lambda b: b["acidez"] >= 3 or b["gas"], 1.0, "a acidez/o gás corta a cremosidade do prato"),
    ("cremoso", lambda b: _s(b, "cremoso") and b["corpo"] == 3, -0.7, "dois elementos cremosos deixam a refeição pesada"),
    # ---- vegetariano / saladas / ovos
    ("salada", lambda b: b["corpo"] == 1, 0.8, "valoriza o frescor das folhas"),
    ("salada", lambda b: _s(b, "herbal") or _s(b, "citrico"), 0.6, "as notas herbais/cítricas realçam a salada"),
    ("vegetariano", lambda b: b["corpo"] <= 2, 0.5, "a leveza respeita os sabores dos vegetais"),
    ("ovo", lambda b: b["corpo"] == 1 and (_s(b, "citrico") or _s(b, "frutado")), 0.5, "a frescura frutada combina com ovos"),
    # ---- dia a dia
    ("sopa", lambda b: b["temperatura"] == "quente", 0.8, "acompanha bem uma sopa"),
    ("lanche", lambda b: b["gas"] and b["temperatura"] == "gelada", 0.8, "é gelada e com gás, o par clássico de lanche"),
    ("arroz_feijao", lambda b: b["gas"] or _s(b, "refrescante"), 0.5, "o frescor é um bom contraponto ao prato do dia a dia"),
    ("grelhado", lambda b: _s(b, "defumado") or _s(b, "tostado") or b["corpo"] >= 2, 0.4, "tem estrutura para as notas de grelhado"),
]

# Regras de ocasião: (ocasião, teste, peso, motivo)
REGRAS_OCASIAO = [
    ("calor", lambda b: b["temperatura"] == "gelada" and _s(b, "refrescante"), 0.8, "é refrescante para um dia quente"),
    ("calor", lambda b: b["corpo"] == 3, -0.6, "pesada para um dia quente"),
    ("frio", lambda b: b["temperatura"] == "quente", 0.9, "é servida quente, ideal para um dia frio"),
    ("frio", lambda b: b["corpo"] == 3, 0.4, "o corpo encorpado aquece em dias frios"),
    ("celebracao", lambda b: b["tipo"] in ("espumante", "coquetel"), 0.8, "combina com um clima de comemoração"),
    ("romantico", lambda b: b["tipo"] in ("espumante", "vinho_tinto", "vinho_branco", "vinho_rose"), 0.8, "combina com um jantar a dois"),
    ("casual", lambda b: b["tipo"] in ("cerveja", "coquetel") or b["gas"], 0.6, "é descontraída, ideal para a ocasião"),
]

# Nome de cada tag do prato, para usar nas justificativas
ROTULO_PRATO = {
    "apimentado": "pratos apimentados", "frito": "frituras", "doce": "sobremesas",
    "leve": "pratos leves", "carne_vermelha": "carne vermelha", "porco": "carne de porco",
    "aves": "aves", "peixe": "peixes", "frutos_do_mar": "frutos do mar", "massa": "massas",
    "queijo": "queijos", "cremoso": "pratos cremosos", "vegetariano": "pratos vegetarianos",
    "salada": "saladas", "ovo": "ovos", "arroz_feijao": "arroz com feijão", "sopa": "sopas",
    "grelhado": "grelhados", "tomate": "molho de tomate", "chocolate": "chocolate",
    "lanche": "lanches", "brasileira": "comida brasileira",
}

_PESO_TAG_CATALOGO = 0.5   # por tag do prato presente em 'combina' (máx. 3 tags)
_PESO_EVITA = -0.8         # por tag do prato presente em 'evita'


def avaliar_regras(
    bebida: Dict,
    tags_prato: Sequence[str],
    ocasioes: Sequence[str] = (),
    temperatura: Optional[str] = None,
) -> Tuple[float, List[str], List[str]]:
    """Devolve (pontuação, motivos_positivos, alertas).

    Motivos positivos já vêm ordenados do mais forte para o mais fraco.
    """
    total = 0.0
    positivos: List[Tuple[float, str]] = []
    alertas: List[Tuple[float, str]] = []
    explicadas = set()   # tags do prato que já têm um motivo específico (evita repetir na justificativa)

    for tag, teste, peso, motivo in REGRAS:
        if tag in tags_prato and teste(bebida):
            total += peso
            (positivos if peso > 0 else alertas).append((abs(peso), motivo))
            if peso > 0:
                explicadas.add(tag)
    for ocasiao, teste, peso, motivo in REGRAS_OCASIAO:
        if ocasiao in ocasioes and teste(bebida):
            total += peso
            (positivos if peso > 0 else alertas).append((abs(peso), motivo))

    # afinidade já registrada no catálogo
    casam = [t for t in tags_prato if t in bebida["combina"]]
    if casam:
        total += _PESO_TAG_CATALOGO * min(len(casam), 3)
        novas = [t for t in casam if t not in explicadas]
        if novas:   # só vira justificativa se disser algo que as regras ainda não disseram
            positivos.append((_PESO_TAG_CATALOGO * min(len(casam), 3) - 0.01,
                              "costuma ser servida com " + _lista_pt([ROTULO_PRATO.get(t, t) for t in novas[:3]])))
    brigam = [t for t in tags_prato if t in bebida["evita"]]
    if brigam:
        total += _PESO_EVITA * min(len(brigam), 2)
        alertas.append((abs(_PESO_EVITA) * len(brigam),
                        "costuma brigar com " + _lista_pt([ROTULO_PRATO.get(t, t) for t in brigam[:2]])))

    # preferência explícita de temperatura
    if temperatura in ("gelada", "quente"):
        if bebida["temperatura"] == temperatura:
            total += 0.8
            positivos.append((0.8, f"é servida {temperatura}, como você pediu"))
        else:
            total -= 1.0
            alertas.append((1.0, f"normalmente não é servida {temperatura}"))
    elif temperatura == "natural":
        if bebida["temperatura"] == "ambiente":
            total += 0.6
            positivos.append((0.6, "é servida em temperatura ambiente, como você pediu"))
        else:
            total -= 0.4

    positivos.sort(key=lambda x: -x[0])
    alertas.sort(key=lambda x: -x[0])
    return total, [m for _, m in positivos], [m for _, m in alertas]


def _lista_pt(itens: Sequence[str]) -> str:
    itens = list(itens)
    if len(itens) <= 1:
        return "".join(itens)
    return ", ".join(itens[:-1]) + " e " + itens[-1]


# --------------------------------------------------------------------------- #
# Filtros vindos do formulário (tipo de bebida, temperatura) e preferências em texto livre
# --------------------------------------------------------------------------- #
TIPOS_FILTRO = ("qualquer", "suco", "vitamina", "cha", "cremosa", "sem_alcool")
ROTULO_TIPO = {
    "suco": "Sucos", "vitamina": "Vitaminas", "cha": "Chás e infusões",
    "cremosa": "Bebidas cremosas", "sem_alcool": "Bebidas sem álcool",
}


def interpretar_tipo(valor: Optional[str]) -> str:
    """Aceita o código ('suco', 'sem_alcool'...) ou o texto do formulário ('Chás e infusões')."""
    t = normalizar_texto(valor or "").strip()
    if t in TIPOS_FILTRO:
        return t
    if "sem alcool" in t or "nao alcoolic" in t:
        return "sem_alcool"
    if "suco" in t:
        return "suco"
    if "vitamina" in t:
        return "vitamina"
    if t.startswith("cha") or "infus" in t:
        return "cha"
    if "cremos" in t:
        return "cremosa"
    return "qualquer"


def interpretar_temperatura(valor: Optional[str]) -> Optional[str]:
    """'Gelada' -> 'gelada' | 'Natural'/'ambiente' -> 'natural' | 'Quente' -> 'quente' | resto -> None."""
    t = normalizar_texto(valor or "")
    if "qualquer" in t or "tanto faz" in t or not t.strip():
        return None
    if "gelad" in t:
        return "gelada"
    if "quente" in t:
        return "quente"
    if "natural" in t or "ambiente" in t:
        return "natural"
    return None


_RE_SEM_ALCOOL = re.compile(r"sem alcool|nao alcoolic\w*|nao bebo|nao bebe|sem bebida alcoolica|crianca\w*")
_RE_SEM_LACTOSE = re.compile(r"sem lactose|intolera\w+ (?:a )?lactose|vegan\w*|sem leite|sem laticinio\w*|alergi\w+ (?:a |ao )?leite|zero lactose")
_RE_SEM_CAFEINA = re.compile(r"sem cafeina|descafeinad\w*|nao (?:posso|tomo|quero) cafeina|evitar cafeina")
_RE_SEM_GAS = re.compile(r"sem gas|nao gosto de gas|sem gaseific\w*|sem bolha\w*|nao gaseificad\w*")
_RE_POUCO_ACUCAR = re.compile(r"pouco acucar|baixo acucar|sem acucar|menos acucar|zero acucar|nada doce|diabet\w*")


@dataclass
class Filtros:
    """Tudo que restringe ou ajusta a lista de bebidas, antes e depois da pontuação."""
    tipo: str = "qualquer"
    sem_alcool: bool = False
    sem_lactose: bool = False
    sem_cafeina: bool = False
    sem_gas: bool = False
    pouco_acucar: bool = False

    @classmethod
    def de(cls, tipo: Optional[str] = None, alcool: str = "qualquer", preferencias: str = "") -> "Filtros":
        t = normalizar_texto(preferencias or "")
        tipo = interpretar_tipo(tipo)
        return cls(
            tipo=tipo,
            sem_alcool=(alcool == "sem" or tipo == "sem_alcool" or bool(_RE_SEM_ALCOOL.search(t))),
            sem_lactose=bool(_RE_SEM_LACTOSE.search(t)),
            sem_cafeina=bool(_RE_SEM_CAFEINA.search(t)),
            sem_gas=bool(_RE_SEM_GAS.search(t)),
            pouco_acucar=bool(_RE_POUCO_ACUCAR.search(t)),
        )

    def aceita(self, b: Dict) -> bool:
        if self.sem_alcool and b["alcool"]:
            return False
        if self.sem_lactose and b.get("lactose"):
            return False
        if self.sem_cafeina and b.get("cafeina"):
            return False
        if self.sem_gas and b["gas"]:
            return False
        if self.tipo == "suco":
            return b["tipo"] == "suco"
        if self.tipo == "vitamina":
            return b["tipo"] == "vitamina"
        if self.tipo == "cha":
            return b["tipo"] == "cha"
        if self.tipo == "cremosa":
            return "cremoso" in b["sabores"] or "lacteo" in b["sabores"]
        return True

    def ajuste(self, b: Dict) -> Tuple[float, List[str]]:
        """Pontos extras/menos por preferência branda (açúcar) e o motivo, se houver."""
        if not self.pouco_acucar:
            return 0.0, []
        if b["docura"] == 2:
            return -2.0, ["é bem doce, e você pediu pouco açúcar"]
        if b["docura"] == 1:
            return -0.6, []
        return 0.5, ["é seca, combinando com o pedido de pouco açúcar"]

    def descricao(self, alcool_exibir: bool = True) -> List[str]:
        itens = []
        if self.tipo not in ("qualquer", "sem_alcool"):
            itens.append(ROTULO_TIPO[self.tipo])
        if self.sem_alcool:
            itens.append("Sem álcool")
        if self.sem_lactose:
            itens.append("Sem lactose")
        if self.sem_cafeina:
            itens.append("Sem cafeína")
        if self.sem_gas:
            itens.append("Sem gás")
        if self.pouco_acucar:
            itens.append("Pouco açúcar")
        return itens
