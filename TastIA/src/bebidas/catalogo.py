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

    _b("suco_abacaxi_hortela", "Suco de Abacaxi com Hortelã", "suco", 1, 1, 3, False, "gelada",
       ["frutado", "citrico", "mentolado", "refrescante"], ["porco", "grelhado", "frito", "brasileira", "arroz_feijao"],
       ["chocolate", "cremoso"],
       "Abacaxi batido com folhas de hortelã. Ácido e fresco, ajuda a equilibrar carnes gordurosas e grelhados."),

    _b("suco_melancia", "Suco de Melancia", "suco", 1, 1, 1, False, "gelada",
       ["frutado", "adocicado", "refrescante"], ["leve", "salada", "frito", "lanche", "vegetariano"],
       ["carne_vermelha", "tomate"],
       "Suco leve e hidratante, de doçura suave. Ótimo para dias quentes e refeições leves."),

    _b("suco_acerola", "Suco de Acerola", "suco", 1, 1, 3, False, "gelada",
       ["citrico", "frutado", "refrescante"], ["frito", "brasileira", "arroz_feijao", "grelhado", "aves"],
       ["chocolate", "cremoso"],
       "Suco bem ácido e rico em vitamina C. A acidez corta a gordura e refresca pratos do dia a dia."),

    _b("suco_caju", "Suco de Caju", "suco", 2, 1, 2, False, "gelada",
       ["frutado", "adocicado"], ["brasileira", "grelhado", "aves", "arroz_feijao", "apimentado"],
       ["peixe", "chocolate"],
       "Suco de sabor marcante, doce e levemente adstringente. Combina com a culinária brasileira."),

    _b("suco_tomate", "Suco de Tomate Temperado", "suco", 2, 0, 2, False, "gelada",
       ["picante", "herbal", "refrescante"], ["ovo", "peixe", "frutos_do_mar", "vegetariano", "salada"],
       ["doce", "chocolate"],
       "Suco de tomate com limão, sal e pimenta suave. Saboroso e sem açúcar, acompanha pratos leves e ovos."),

    _b("suco_goiaba", "Suco de Goiaba", "suco", 2, 1, 1, False, "gelada",
       ["frutado", "adocicado"], ["doce", "brasileira", "queijo", "lanche", "ovo"],
       ["peixe", "apimentado"],
       "Suco aromático e de corpo médio. Clássico com queijos e lanches da tarde."),

    _b("vitamina_abacate", "Vitamina de Abacate", "vitamina", 3, 2, 1, False, "gelada",
       ["cremoso", "adocicado", "lacteo"], ["doce", "lanche"],
       ["frutos_do_mar", "peixe", "apimentado", "frito"],
       "Abacate batido com leite. Muito cremosa e energética, boa para lanches e sobremesas.", lactose=True),

    _b("smoothie_acai", "Smoothie de Açaí com Banana", "vitamina", 3, 1, 2, False, "gelada",
       ["frutado", "cremoso", "adocicado"], ["doce", "lanche", "ovo"],
       ["peixe", "frutos_do_mar", "apimentado"],
       "Açaí batido com banana, sem leite. Espesso, frutado e energético."),

    _b("vitamina_mamao", "Vitamina de Mamão", "vitamina", 2, 1, 1, False, "gelada",
       ["cremoso", "frutado", "adocicado", "lacteo"], ["doce", "lanche", "ovo", "vegetariano"],
       ["peixe", "frutos_do_mar", "frito"],
       "Mamão batido com leite. Suave e de corpo médio, ótima no café da manhã.", lactose=True),

    _b("agua_mineral", "Água Mineral Natural", "agua", 1, 0, 1, False, "ambiente",
       ["mineral"], ["apimentado", "leve", "salada", "peixe", "vegetariano", "sopa", "ovo", "massa"],
       [],
       "Água sem gás em temperatura ambiente. Neutra, não interfere no sabor de nenhum prato."),

    _b("agua_pepino_hortela", "Água Saborizada com Pepino e Hortelã", "agua", 1, 0, 1, False, "gelada",
       ["mineral", "mentolado", "herbal", "refrescante"], ["leve", "salada", "vegetariano", "peixe", "frutos_do_mar", "ovo"],
       ["chocolate"],
       "Água gelada com fatias de pepino e folhas de hortelã. Sutil e refrescante."),

    _b("agua_gas_natural", "Água Mineral com Gás", "agua", 1, 0, 1, True, "gelada",
       ["mineral", "refrescante"], ["frito", "queijo", "porco", "massa", "tomate", "grelhado", "carne_vermelha", "lanche"],
       [],
       "Água com gás natural, bem gelada. As borbulhas limpam o paladar entre uma garfada e outra."),

    _b("cha_mate_gelado", "Chá Mate Gelado", "cha", 2, 0, 1, False, "gelada",
       ["tostado", "herbal", "refrescante"], ["lanche", "frito", "brasileira", "grelhado", "arroz_feijao"],
       ["doce", "chocolate"],
       "Chá mate frio, levemente defumado e herbal. Companheiro clássico de lanches e salgados.", cafeina=True),

    _b("cha_gengibre_limao", "Chá de Gengibre e Limão Quente", "cha", 1, 0, 2, False, "quente",
       ["gengibre", "picante", "citrico", "herbal"], ["sopa", "aves", "vegetariano", "leve", "ovo"],
       ["doce", "chocolate"],
       "Infusão quente de gengibre fresco com limão. Aquece, ajuda na digestão e combina com sopas."),

    _b("chai_latte", "Chai Latte Quente", "cha", 2, 1, 1, False, "quente",
       ["picante", "adocicado", "gengibre", "lacteo", "cremoso"], ["doce", "chocolate", "lanche", "sopa"],
       ["peixe", "frutos_do_mar", "salada"],
       "Chá preto com especiarias e leite. Aconchegante e levemente adocicado, ideal para dias frios.",
       lactose=True, cafeina=True),

    _b("cha_branco_pessego", "Chá Branco Gelado com Pêssego", "cha", 1, 1, 1, False, "gelada",
       ["floral", "frutado", "refrescante"], ["leve", "salada", "peixe", "vegetariano", "doce"],
       ["apimentado", "carne_vermelha"],
       "Chá branco frio com toque de pêssego. Delicado e floral, não cobre o sabor de pratos leves.", cafeina=True),

    _b("cafe_com_leite", "Café com Leite", "cafe", 2, 1, 1, False, "quente",
       ["tostado", "cremoso", "lacteo"], ["lanche", "ovo", "doce", "chocolate", "queijo", "brasileira"],
       ["peixe", "frutos_do_mar", "apimentado", "leve"],
       "Café coado com leite quente. Tradição do café da manhã e dos lanches da tarde.",
       lactose=True, cafeina=True),

    _b("cafe_gelado", "Café Gelado com Leite", "cafe", 2, 1, 1, False, "gelada",
       ["tostado", "cremoso", "lacteo", "refrescante"], ["doce", "chocolate", "lanche"],
       ["peixe", "frutos_do_mar", "apimentado", "leve"],
       "Café frio com leite e gelo. Refrescante, bom para sobremesas em dias quentes.",
       lactose=True, cafeina=True),

    _b("refri_limao", "Refrigerante de Limão", "refrigerante", 1, 2, 2, True, "gelada",
       ["citrico", "adocicado", "refrescante"], ["frito", "lanche", "brasileira", "porco", "grelhado"],
       ["peixe", "leve", "salada"],
       "Refrigerante cítrico e borbulhante. A acidez e o gás ajudam com pratos gordurosos e lanches."),

    _b("soda_frutas_vermelhas", "Soda Italiana de Frutas Vermelhas", "refrigerante", 1, 1, 2, True, "gelada",
       ["frutado", "adocicado", "refrescante"], ["lanche", "frito", "doce", "queijo"],
       ["carne_vermelha", "peixe"],
       "Água com gás e xarope de frutas vermelhas, sem álcool. Frutada e leve, boa com queijos e lanches."),

    _b("kefir_agua", "Kefir de Água com Frutas", "fermentado", 1, 1, 3, True, "gelada",
       ["fermentado", "frutado", "refrescante"], ["salada", "leve", "vegetariano", "frito", "aves"],
       ["doce", "chocolate"],
       "Bebida fermentada, levemente gaseificada e azedinha. Refresca e combina com pratos leves."),

    _b("ayran", "Ayran (Iogurte Salgado com Hortelã)", "lacteo", 2, 0, 2, False, "gelada",
       ["lacteo", "cremoso", "mentolado", "refrescante"], ["carne_vermelha", "grelhado", "apimentado", "arroz_feijao", "porco"],
       ["doce", "chocolate", "peixe"],
       "Iogurte batido com água, sal e hortelã. Refrescante e sem açúcar, equilibra carnes grelhadas e temperos fortes.",
       lactose=True),
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
