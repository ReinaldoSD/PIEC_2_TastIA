"""Catálogo único de ingredientes do TastIA.

FONTE ÚNICA DA VERDADE: o CLIP (percepção), o autocomplete (rotas/ingrediente.py) e as
categorias do inventário leem tudo daqui. Para ensinar um ingrediente novo ao sistema,
acrescente UMA linha em `_ITENS`.

Cada ingrediente tem:
  categoria              única categoria do item (a mesma usada no front e no banco)
  sinonimos              nomes alternativos (ajudam o autocomplete)
  prompts                3 a 5 frases em inglês para o CLIP (o modelo usa a MÉDIA delas)
  confundiveis           itens parecidos: se o 2º colocado do CLIP estiver aqui, exige-se
                         uma margem maior sobre o 1º antes de marcar o item como "certo"
  reconhecivel_por_foto  False = a câmera não distingue (pó, farinha, açúcar...). O item
                         continua no autocomplete e na adição manual, mas fica fora do CLIP
                         para não gerar chute errado.
"""

import unicodedata
from typing import Dict, FrozenSet, List, Optional, Set, Tuple

CATEGORIAS_VALIDAS: Tuple[str, ...] = (
    "Frutas",
    "Verduras e legumes",
    "Laticínios",
    "Grãos e cereais",
    "Carnes",
    "Bebidas",
    "Outros",
)

# Frases que representam "NÃO é um ingrediente": se o recorte se parece mais com uma
# delas do que com qualquer ingrediente, ele é descartado.
NEGATIVOS: Tuple[str, ...] = (
    "a person's hand holding something",
    "an empty refrigerator shelf",
    "an empty kitchen counter or table",
    "an empty plate, bowl or container",
    "a label or text on a package",
    "a kitchen appliance",
    "an empty plastic bag",
    "a cooking pan, pot or kitchen utensil",
)

# Palavras de labels do Florence-2 que indicam que o objeto NÃO é comida
# (a caixa é descartada antes de chegar ao CLIP).
PALAVRAS_LABEL_IGNORADAS: FrozenSet[str] = frozenset({
    "refrigerator", "fridge", "freezer", "table", "countertop", "counter", "kitchen",
    "person", "man", "woman", "boy", "girl", "child", "face", "head", "hand", "arm",
    "shelf", "cabinet", "cupboard", "drawer", "door", "window", "wall", "floor",
    "oven", "microwave", "stove", "sink", "dishwasher", "chair", "lamp", "clock",
})

# --------------------------------------------------------------------------- #
# Modelos de frase (formato consistente para todos os ingredientes)
# --------------------------------------------------------------------------- #
_MODELOS = {
    "fresco": (
        "a photo of {x}",
        "a close-up photo of {x}",
        "{x} on a kitchen counter",
    ),
    "embalado": (
        "a photo of {x}",
        "{x} on a supermarket shelf",
        "a close-up photo of {x}",
    ),
}

# nome, categoria, tipo, descritores em inglês, sinônimos, confundíveis, reconhecível por foto
_ITENS: List[Tuple[str, str, str, List[str], List[str], List[str], bool]] = [
    # ----------------------------- Verduras e legumes ----------------------------- #
    ("Tomate", "Verduras e legumes", "fresco", ["a tomato", "tomatoes"],
     ["tomate cereja", "tomate italiano"], ["Maçã", "Pimentão", "Morango"], True),
    ("Cebola", "Verduras e legumes", "fresco", ["an onion", "onions"],
     ["cebola roxa"], ["Alho", "Batata", "Beterraba"], True),
    ("Alho", "Verduras e legumes", "fresco", ["garlic", "a head of garlic"],
     ["cabeça de alho", "dente de alho"], ["Cebola", "Gengibre"], True),
    ("Batata", "Verduras e legumes", "fresco", ["a potato", "potatoes"],
     ["batata inglesa"], ["Cebola", "Mandioca", "Gengibre"], True),
    ("Cenoura", "Verduras e legumes", "fresco", ["a carrot", "carrots"],
     [], [], True),
    ("Pimentão", "Verduras e legumes", "fresco", ["a bell pepper", "bell peppers"],
     ["pimentao vermelho", "pimentão verde", "pimentão amarelo"], ["Tomate"], True),
    ("Alface", "Verduras e legumes", "fresco", ["lettuce", "a head of lettuce"],
     ["alface crespa", "alface americana", "alface roxa"],
     ["Couve", "Repolho", "Espinafre", "Cheiro-verde", "Manjericão"], True),
    ("Brócolis", "Verduras e legumes", "fresco", ["broccoli", "a head of broccoli"],
     ["brocolis"], ["Couve"], True),
    ("Abóbora", "Verduras e legumes", "fresco", ["a pumpkin", "a squash"],
     ["jerimum", "moranga"], ["Abobrinha", "Mamão"], True),
    ("Abobrinha", "Verduras e legumes", "fresco", ["a zucchini", "zucchinis"],
     ["abobrinha italiana"], ["Pepino", "Abóbora"], True),
    ("Beterraba", "Verduras e legumes", "fresco", ["a beet", "beetroots"],
     [], ["Cebola"], True),
    ("Couve", "Verduras e legumes", "fresco", ["kale", "collard greens"],
     ["couve manteiga"], ["Alface", "Espinafre", "Repolho", "Brócolis"], True),
    ("Espinafre", "Verduras e legumes", "fresco", ["spinach", "fresh spinach leaves"],
     [], ["Couve", "Alface"], True),
    ("Repolho", "Verduras e legumes", "fresco", ["a head of cabbage", "cabbage"],
     ["repolho roxo"], ["Alface", "Couve"], True),
    ("Pepino", "Verduras e legumes", "fresco", ["a cucumber", "cucumbers"],
     [], ["Abobrinha"], True),
    ("Gengibre", "Verduras e legumes", "fresco", ["a ginger root", "fresh ginger"],
     [], ["Alho", "Batata", "Mandioca"], True),
    ("Mandioca", "Verduras e legumes", "fresco", ["a cassava root", "cassava"],
     ["aipim", "macaxeira"], ["Batata", "Gengibre"], True),
    ("Cheiro-verde", "Verduras e legumes", "fresco", ["a bunch of fresh parsley and chives", "fresh herbs"],
     ["salsinha", "cebolinha", "salsa", "coentro"], ["Manjericão", "Couve"], True),
    ("Manjericão", "Verduras e legumes", "fresco", ["fresh basil leaves", "a basil plant"],
     ["manjericao"], ["Cheiro-verde"], True),
    # --------------------------------------- Frutas -------------------------------- #
    ("Banana", "Frutas", "fresco", ["a banana", "bananas"],
     ["banana prata", "banana nanica"], [], True),
    ("Maçã", "Frutas", "fresco", ["an apple", "apples"],
     ["maca", "maçã fuji", "maçã gala"], ["Tomate"], True),
    ("Laranja", "Frutas", "fresco", ["an orange", "oranges"],
     ["laranja pera", "mexerica", "tangerina"], ["Limão", "Manga"], True),
    ("Limão", "Frutas", "fresco", ["a lemon or a lime", "limes"],
     ["limão taiti", "limão siciliano", "limao"], ["Laranja"], True),
    ("Abacaxi", "Frutas", "fresco", ["a pineapple", "pineapples"],
     [], [], True),
    ("Abacate", "Frutas", "fresco", ["an avocado", "avocados"],
     [], ["Pepino"], True),
    ("Coco", "Frutas", "fresco", ["a coconut", "coconuts"],
     ["coco verde", "coco seco"], [], True),
    ("Mamão", "Frutas", "fresco", ["a papaya", "papayas"],
     ["mamao", "papaia"], ["Manga", "Abóbora"], True),
    ("Manga", "Frutas", "fresco", ["a mango", "mangoes"],
     [], ["Mamão", "Laranja"], True),
    ("Melancia", "Frutas", "fresco", ["a watermelon", "a slice of watermelon"],
     [], [], True),
    ("Morango", "Frutas", "fresco", ["strawberries", "a strawberry"],
     [], ["Tomate"], True),
    ("Uva", "Frutas", "fresco", ["grapes", "a bunch of grapes"],
     ["uva verde", "uva roxa"], [], True),
    # --------------------------------------- Laticínios ---------------------------- #
    ("Leite", "Laticínios", "embalado", ["a carton or bottle of milk", "a milk carton"],
     ["leite integral", "leite desnatado"], ["Iogurte", "Creme de leite", "Leite condensado"], True),
    ("Queijo", "Laticínios", "fresco", ["cheese", "a piece of cheese"],
     ["queijo prato", "queijo minas", "queijo coalho"],
     ["Manteiga", "Requeijão", "Queijo mussarela", "Queijo parmesão"], True),
    ("Queijo mussarela", "Laticínios", "fresco", ["mozzarella cheese", "sliced mozzarella"],
     ["mussarela", "muçarela", "mucarela"], ["Queijo", "Queijo parmesão"], True),
    ("Queijo parmesão", "Laticínios", "fresco", ["parmesan cheese", "a wedge of parmesan"],
     ["parmesao"], ["Queijo", "Queijo mussarela"], True),
    ("Manteiga", "Laticínios", "embalado", ["a block or tub of butter", "a stick of butter"],
     [], ["Margarina", "Queijo", "Requeijão"], True),
    ("Margarina", "Laticínios", "embalado", ["a tub of margarine", "a margarine container"],
     [], ["Manteiga", "Requeijão", "Iogurte"], True),
    ("Iogurte", "Laticínios", "embalado", ["a cup or bottle of yogurt", "a yogurt pot"],
     ["iogurte natural"], ["Leite", "Requeijão", "Creme de leite"], True),
    ("Requeijão", "Laticínios", "embalado", ["a jar of cream cheese spread", "a cream cheese cup"],
     ["requeijao"], ["Manteiga", "Margarina", "Iogurte", "Maionese"], True),
    ("Creme de leite", "Laticínios", "embalado", ["a carton or can of cream", "a cooking cream box"],
     [], ["Leite", "Leite condensado", "Iogurte"], True),
    ("Leite condensado", "Laticínios", "embalado", ["a can of condensed milk", "a condensed milk box"],
     [], ["Leite", "Creme de leite"], True),
    # --------------------------------------- Carnes -------------------------------- #
    ("Frango", "Carnes", "fresco", ["raw or cooked chicken meat", "chicken pieces"],
     ["peito de frango", "coxa de frango", "sobrecoxa"], ["Peixe"], True),
    ("Carne bovina", "Carnes", "fresco", ["raw or cooked beef meat", "a beef steak"],
     ["carne", "bife", "acém", "patinho", "alcatra"], ["Carne moída"], True),
    ("Carne moída", "Carnes", "fresco", ["ground beef", "minced meat"],
     ["carne moida"], ["Carne bovina"], True),
    ("Linguiça", "Carnes", "fresco", ["raw sausages", "fresh sausage links"],
     ["linguica", "linguiça toscana"], ["Calabresa", "Salsicha"], True),
    ("Calabresa", "Carnes", "fresco", ["calabresa smoked sausage", "pepperoni sausage"],
     [], ["Linguiça", "Salsicha", "Bacon"], True),
    ("Salsicha", "Carnes", "fresco", ["hot dog sausages", "frankfurters"],
     [], ["Linguiça", "Calabresa"], True),
    ("Bacon", "Carnes", "fresco", ["bacon strips", "sliced bacon"],
     [], ["Presunto", "Calabresa"], True),
    ("Presunto", "Carnes", "fresco", ["sliced ham", "ham slices"],
     ["fiambre"], ["Bacon", "Queijo"], True),
    ("Peixe", "Carnes", "fresco", ["raw or cooked fish", "a fish fillet"],
     ["filé de peixe", "tilápia", "salmão"], ["Atum", "Sardinha", "Camarão"], True),
    ("Camarão", "Carnes", "fresco", ["shrimp", "raw shrimp"],
     ["camarao"], ["Peixe"], True),
    ("Atum", "Carnes", "embalado", ["a can of tuna", "canned tuna"],
     [], ["Sardinha", "Peixe"], True),
    ("Sardinha", "Carnes", "embalado", ["a can of sardines", "canned sardines"],
     [], ["Atum", "Peixe"], True),
    # ----------------------------------- Grãos e cereais --------------------------- #
    ("Arroz", "Grãos e cereais", "embalado", ["a bag or bowl of rice", "uncooked white rice"],
     ["arroz branco", "arroz integral"], ["Cuscuz", "Lentilha"], True),
    ("Feijão", "Grãos e cereais", "embalado", ["a bag or bowl of beans", "dried beans"],
     ["feijao", "feijão preto", "feijão carioca"], ["Lentilha", "Ervilha"], True),
    ("Macarrão", "Grãos e cereais", "embalado", ["a packet or bowl of pasta or spaghetti", "dry pasta"],
     ["macarrao", "massa", "espaguete"], [], True),
    ("Pão", "Grãos e cereais", "fresco", ["bread", "a loaf of bread"],
     ["pao", "pão francês", "pão de forma"], [], True),
    ("Lentilha", "Grãos e cereais", "embalado", ["lentils", "a bowl of dried lentils"],
     [], ["Feijão", "Ervilha"], True),
    ("Ervilha", "Grãos e cereais", "embalado", ["green peas", "a can of green peas"],
     [], ["Feijão", "Lentilha", "Milho"], True),
    ("Milho", "Grãos e cereais", "fresco", ["corn on the cob", "corn kernels"],
     ["milho verde", "espiga de milho"], ["Ervilha"], True),
    ("Aveia", "Grãos e cereais", "embalado", ["a package of rolled oats", "oat flakes"],
     ["aveia em flocos"], ["Arroz"], True),
    ("Cuscuz", "Grãos e cereais", "embalado", ["a package of cuscuz cornmeal flakes", "couscous"],
     ["flocão", "flocao"], ["Arroz", "Farinha de mandioca"], False),
    ("Farinha de mandioca", "Grãos e cereais", "embalado", ["a bag of cassava flour", "farofa flour"],
     ["farinha", "farofa"], ["Farinha de trigo", "Fubá", "Tapioca"], False),
    ("Farinha de trigo", "Grãos e cereais", "embalado", ["a bag of wheat flour", "white flour"],
     ["farinha"], ["Fubá", "Farinha de mandioca", "Açúcar"], False),
    ("Fubá", "Grãos e cereais", "embalado", ["a bag of cornmeal", "corn flour"],
     ["fuba", "farinha de milho"], ["Farinha de trigo", "Farinha de mandioca"], False),
    ("Tapioca", "Grãos e cereais", "embalado", ["a bag of tapioca starch", "tapioca pearls"],
     ["goma de tapioca", "polvilho"], ["Farinha de mandioca", "Farinha de trigo"], False),
    # --------------------------------------- Bebidas ------------------------------- #
    ("Refrigerante", "Bebidas", "embalado", ["a soda can or bottle", "a soft drink bottle"],
     ["refri"], ["Suco", "Água"], True),
    ("Suco", "Bebidas", "embalado", ["a juice bottle or carton", "a box of fruit juice"],
     ["suco de laranja", "suco de uva"], ["Refrigerante", "Leite"], True),
    ("Água", "Bebidas", "embalado", ["a bottle of water", "a water bottle"],
     ["agua", "água mineral", "água com gás"], ["Refrigerante", "Suco"], True),
    ("Café", "Bebidas", "embalado", ["a package or jar of coffee", "a bag of ground coffee"],
     ["cafe", "café em pó"], [], True),
    # --------------------------------------- Outros -------------------------------- #
    ("Ovo", "Outros", "fresco", ["eggs", "a carton of eggs"],
     ["ovos", "ovo de galinha"], [], True),
    ("Biscoito", "Outros", "embalado", ["a packet of biscuits or cookies", "a package of crackers"],
     ["bolacha", "bolacha recheada", "bolacha de água e sal"], ["Chocolate"], True),
    ("Chocolate", "Outros", "embalado", ["a chocolate bar", "chocolate wrapped in foil"],
     ["barra de chocolate"], ["Biscoito"], True),
    ("Molho de tomate", "Outros", "embalado", ["a jar, bottle or sachet of tomato sauce", "tomato sauce packaging"],
     ["extrato de tomate", "molho", "catchup", "ketchup"], ["Maionese", "Mostarda"], True),
    ("Maionese", "Outros", "embalado", ["a jar of mayonnaise", "a mayonnaise bottle"],
     [], ["Mostarda", "Requeijão", "Molho de tomate"], True),
    ("Mostarda", "Outros", "embalado", ["a bottle of mustard", "a mustard squeeze bottle"],
     [], ["Maionese", "Molho de tomate"], True),
    ("Azeite", "Outros", "embalado", ["a bottle of olive oil", "olive oil bottle"],
     ["azeite de oliva", "óleo"], ["Suco"], True),
    ("Açúcar", "Outros", "embalado", ["a bag of sugar", "white sugar"],
     ["acucar", "açúcar refinado", "açúcar cristal"], ["Farinha de trigo"], False),
]


# --------------------------------------------------------------------------- #
# Construção das estruturas
# --------------------------------------------------------------------------- #
def normalizar(texto: str) -> str:
    """Minúsculas e sem acentos (mesma regra de receitas.validador.normalizar_texto)."""
    t = unicodedata.normalize("NFD", str(texto).lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def _montar_prompts(tipo: str, descritores: List[str]) -> Tuple[str, ...]:
    modelos = _MODELOS[tipo]
    frases = [m.format(x=descritores[0]) for m in modelos]
    for extra in descritores[1:]:
        frases.append(modelos[0].format(x=extra))
    return tuple(frases[:5])


CATALOGO: Dict[str, Dict] = {}
for _nome, _cat, _tipo, _desc, _sin, _conf, _reconhece in _ITENS:
    CATALOGO[_nome] = {
        "categoria": _cat,
        "sinonimos": list(_sin),
        "prompts": _montar_prompts(_tipo, _desc),
        "confundiveis": list(_conf),
        "reconhecivel_por_foto": bool(_reconhece),
    }

# Itens que o CLIP realmente reconhece, na ordem do catálogo.
NOMES_RECONHECIVEIS: List[str] = [
    n for n, info in CATALOGO.items() if info["reconhecivel_por_foto"]
]

# Compatibilidade com o formato antigo: nome -> (prompt, categoria).
CATALOGO_INGREDIENTES: Dict[str, Tuple[str, str]] = {
    n: (info["prompts"][0], info["categoria"]) for n, info in CATALOGO.items()
}

# Lista do autocomplete: todos os itens (inclusive os que a câmera não distingue).
LISTA_OFICIAL_INGREDIENTES: List[Dict[str, str]] = sorted(
    ({"nome": n, "categoria": info["categoria"]} for n, info in CATALOGO.items()),
    key=lambda x: normalizar(x["nome"]),
)

# nome -> sinônimos já normalizados (sem acento, minúsculos)
SINONIMOS_NORMALIZADOS: Dict[str, List[str]] = {
    n: [normalizar(s) for s in info["sinonimos"]] for n, info in CATALOGO.items()
}

# Pares parecidos (relação simétrica).
_PARES_CONFUNDIVEIS: Set[FrozenSet[str]] = set()
for _n, _info in CATALOGO.items():
    for _c in _info["confundiveis"]:
        _PARES_CONFUNDIVEIS.add(frozenset((_n, _c)))


def par_confundivel(a: str, b: str) -> bool:
    """True se os dois ingredientes costumam ser confundidos entre si."""
    return frozenset((a, b)) in _PARES_CONFUNDIVEIS


def categoria_de(nome: str, padrao: str = "Outros") -> str:
    info = CATALOGO.get(nome)
    return info["categoria"] if info else padrao


def resolver_nome(texto: str) -> Optional[str]:
    """Converte um nome ou sinônimo digitado no nome oficial (ou None se não existir)."""
    chave = normalizar(texto).strip()
    if not chave:
        return None
    for nome in CATALOGO:
        if normalizar(nome) == chave or chave in SINONIMOS_NORMALIZADOS[nome]:
            return nome
    return None


def validar_catalogo() -> None:
    """Confere a consistência do catálogo; levanta ValueError se algo estiver errado."""
    if len(CATALOGO) != len(_ITENS):
        raise ValueError("Catálogo com nomes de ingredientes duplicados.")
    for nome, info in CATALOGO.items():
        if info["categoria"] not in CATEGORIAS_VALIDAS:
            raise ValueError(f"Categoria inválida em '{nome}': {info['categoria']}")
        for c in info["confundiveis"]:
            if c not in CATALOGO:
                raise ValueError(f"'{nome}' cita confundível inexistente: '{c}'")
            if c == nome:
                raise ValueError(f"'{nome}' não pode ser confundível dele mesmo.")
        if info["reconhecivel_por_foto"] and len(info["prompts"]) < 3:
            raise ValueError(f"'{nome}' precisa de ao menos 3 prompts.")
    if len(NOMES_RECONHECIVEIS) < 2:
        raise ValueError("O catálogo precisa de ao menos 2 itens reconhecíveis por foto.")


validar_catalogo()
