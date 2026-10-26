"""Catálogo de bebidas do TastIA - Apenas bebidas Não Alcoólicas.

Todas as opções de bebidas possuem teor alcoólico zero e álcool desativado.
"""
from typing import Dict, List

TIPOS = (
    "suco", "vitamina", "agua", "cha", "cafe", "refrigerante", "fermentado", "lacteo",
)

SABORES = (
    "citrico", "frutado", "herbal", "amargo", "tostado", "floral", "adocicado", "mineral",
    "cremoso", "defumado", "picante", "fermentado", "refrescante", "mentolado",
    "gengibre", "lacteo",
)

PRATOS = (
    "apimentado", "frito", "doce", "leve", "carne_vermelha", "porco", "aves", "peixe",
    "frutos_do_mar", "massa", "queijo", "cremoso", "vegetariano", "salada", "ovo",
    "arroz_feijao", "sopa", "grelhado", "tomate", "chocolate", "lanche", "brasileira",
)

TEMPERATURAS = ("gelada", "ambiente", "quente")


def _b(id, nome, tipo, corpo, docura, acidez, gas, temperatura,
       sabores, combina, evita, descricao, lactose=False, cafeina=False):
    return {
        "id": id, "nome": nome, "tipo": tipo, "alcool": False, "teor": 0,
        "corpo": corpo, "docura": docura, "acidez": acidez, "gas": gas,
        "temperatura": temperatura, "sabores": sabores, "combina": combina,
        "evita": evita, "descricao": descricao, "lactose": lactose, "cafeina": cafeina,
    }


CATALOGO: List[Dict] = [
    _b("suco_laranja", "Suco de Laranja Natural", "suco", 1, 1, 2, False, "gelada",
       ["citrico", "frutado", "refrescante"], ["ovo", "lanche", "leve", "salada"],
       ["peixe", "carne_vermelha"],
       "Suco natural, doce e cítrico. Excelente para refeições leves e café da manhã."),

    _b("limonada_suica", "Limonada Suíça", "suco", 1, 1, 3, False, "gelada",
       ["citrico", "refrescante", "cremoso"], ["frito", "peixe", "frutos_do_mar", "grelhado", "brasileira", "porco"],
       ["doce", "chocolate"],
       "Limão batido com a casca e leite condensado. Ácida e cremosa, corta a gordura do prato.", lactose=True),

    _b("suco_maracuja", "Suco de Maracujá", "suco", 1, 1, 3, False, "gelada",
       ["frutado", "citrico", "refrescante"], ["apimentado", "frito", "frutos_do_mar", "arroz_feijao", "doce"],
       ["chocolate", "carne_vermelha"],
       "Suco agridoce e aromático. A acidez acalma pratos picantes e mais intensos."),

    _b("suco_uva", "Suco de Uva Integral", "suco", 3, 1, 2, False, "gelada",
       ["frutado", "adocicado"], ["carne_vermelha", "massa", "grelhado", "queijo", "tomate"],
       ["peixe", "leve", "salada"],
       "Suco encorpado e aromático, excelente alternativa não alcoólica para acompanhar carnes e massas."),

    _b("agua_gas_limao", "Água com Gás e Limão", "agua", 1, 0, 2, True, "gelada",
       ["mineral", "citrico", "refrescante"],
       ["frito", "leve", "peixe", "frutos_do_mar", "salada", "arroz_feijao", "queijo", "porco"],
       [],
       "Água com gás, gelo e limão. Neutra e refrescante, limpa o paladar com qualquer refeição."),

    _b("agua_coco", "Água de Coco", "agua", 1, 1, 1, False, "gelada",
       ["adocicado", "refrescante", "mineral"], ["apimentado", "leve", "frutos_do_mar", "salada", "peixe", "vegetariano"],
       ["carne_vermelha", "chocolate"],
       "Água de coco natural, levemente adocicada. Hidrata e ameniza a ardência da pimenta."),

    _b("cha_verde", "Chá Verde Gelado", "cha", 1, 0, 1, False, "gelada",
       ["herbal", "amargo", "refrescante"], ["peixe", "salada", "leve", "vegetariano", "frito", "frutos_do_mar"],
       ["doce", "chocolate"],
       "Chá verde frio, herbal e levemente amargo. Combina perfeitamente com peixes e saladas.", cafeina=True),

    _b("cha_preto_limao", "Chá Preto Gelado com Limão", "cha", 2, 0, 2, False, "gelada",
       ["citrico", "refrescante"], ["frito", "carne_vermelha", "lanche", "grelhado", "porco"],
       ["peixe"],
       "Chá preto frio com limão. Equilibra pratos gordurosos e refeições mais pesadas.", cafeina=True),

    _b("cha_hibisco", "Chá de Hibisco Gelado", "cha", 1, 0, 3, False, "gelada",
       ["floral", "frutado", "refrescante"], ["leve", "salada", "vegetariano", "arroz_feijao", "frutos_do_mar"],
       ["chocolate"],
       "Chá de hibisco frio, floral e ácido. Refrescante e sem calorias."),

    _b("cha_camomila", "Chá de Camomila Quente", "cha", 1, 0, 1, False, "quente",
       ["floral", "herbal"], ["sopa", "leve", "doce", "ovo", "vegetariano"],
       ["frito", "apimentado"],
       "Infusão quente, suave e calmante. Ideal para acompanhar sopas e lanches leves."),

    _b("cafe_expresso", "Café Expresso", "cafe", 3, 0, 2, False, "quente",
       ["tostado", "amargo"], ["doce", "chocolate", "lanche"],
       ["leve", "peixe", "frutos_do_mar", "apimentado"],
       "Café forte e quente. Acompanha sobremesas e lanches no final da refeição.", cafeina=True),

    _b("guarana", "Refrigerante de Guaraná", "refrigerante", 1, 2, 1, True, "gelada",
       ["adocicado", "frutado"], ["frito", "lanche", "brasileira", "arroz_feijao", "grelhado", "apimentado"],
       ["peixe", "leve"],
       "Refrigerante doce e borbulhante. Acompanhamento clássico para salgados, lanches e pratos do dia a dia.", cafeina=True),

    _b("kombucha", "Kombucha de Limão e Gengibre", "fermentado", 1, 0, 3, True, "gelada",
       ["fermentado", "citrico", "gengibre", "refrescante"], ["salada", "leve", "frito", "vegetariano", "frutos_do_mar", "peixe"],
       ["doce", "chocolate"],
       "Chá fermentado não alcoólico, levemente gaseificado e azedinho. Auxilia na digestão.", cafeina=True),

    _b("ginger_ale", "Ginger Ale Não Alcoólico", "refrigerante", 1, 1, 1, True, "gelada",
       ["gengibre", "picante", "refrescante"], ["apimentado", "frito", "aves", "porco", "frutos_do_mar"],
       ["chocolate"],
       "Bebida gaseificada de gengibre. Refresca o paladar e harmoniza com pratos picantes."),

    _b("vitamina_banana", "Vitamina de Banana com Aveia", "vitamina", 3, 2, 1, False, "gelada",
       ["cremoso", "adocicado", "lacteo"], ["doce", "lanche", "ovo"],
       ["frutos_do_mar", "peixe", "apimentado"],
       "Vitamina cremosa de banana e leite. Nutritiva para lanches e opções doces.", lactose=True),

    _b("lassi_manga", "Lassi de Manga", "lacteo", 2, 2, 2, False, "gelada",
       ["lacteo", "frutado", "cremoso", "refrescante"], ["apimentado", "doce", "arroz_feijao"],
       ["peixe", "leve"],
       "Iogurte batido com manga. O toque lácteo reduz a ardência de alimentos picantes.", lactose=True),

    _b("vitamina_morango", "Vitamina de Morango", "vitamina", 3, 2, 2, False, "gelada",
       ["cremoso", "frutado", "adocicado", "lacteo"], ["doce", "lanche", "ovo"],
       ["frutos_do_mar", "peixe", "apimentado"],
       "Vitamina de morango com leite. Doce, levemente ácida e cremosa.", lactose=True),

    _b("suco_verde", "Suco Verde Detox", "suco", 1, 0, 2, False, "gelada",
       ["herbal", "citrico", "gengibre", "refrescante"], ["salada", "leve", "vegetariano", "ovo", "peixe"],
       ["doce", "chocolate", "frito"],
       "Couve, limão, gengibre e maçã. Fresco, leve e bem nutritivo."),
]


def validar_catalogo(catalogo: List[Dict] = None) -> List[str]:
    catalogo = CATALOGO if catalogo is None else catalogo
    erros: List[str] = []
    ids = set()
    for b in catalogo:
        i = b.get("id", "?")
        if i in ids:
            erros.append(f"{i}: id repetido")
        ids.add(i)
        if b["tipo"] not in TIPOS:
            erros.append(f"{i}: tipo inválido '{b['tipo']}'")
        if b["temperatura"] not in TEMPERATURAS:
            erros.append(f"{i}: temperatura inválida '{b['temperatura']}'")
        if b["alcool"] or b["teor"] > 0:
            erros.append(f"{i}: catálogo restrito a bebidas não alcoólicas")
    return erros


def listar_bebidas(alcool: str = "sem") -> List[Dict]:
    return list(CATALOGO)