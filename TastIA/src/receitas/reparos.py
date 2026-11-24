"""Reparos automáticos da receita gerada (sem IA, roda sem modelo e sem internet).

Modelos pequenos esquecem de listar o que usam no preparo ("Aqueça o óleo..." sem 'óleo' nos ingredientes, ou
"junte o queijo" sem o queijo na lista). Repetir a geração nem sempre resolve, então este módulo conserta o que
tem certeza:

  - alimento que o preparo usa, que o usuário TEM no inventário e que ficou fora da lista -> entra na lista com
    uma quantidade típica na unidade certa ('100 g de queijo');
  - básico de despensa usado no preparo e fora da lista (sal, óleo, azeite, água, pimenta, temperos) -> entra na
    lista ('sal a gosto', '1 colher de sopa de óleo');
  - QUANTIDADE ABSURDA na lista ('10 kg de bacon', '600 g de pão', '2 colheres de sopa de sal') -> limitada a um
    teto realista para o alimento e para o número de porções, e nunca acima do que o usuário tem
    (`limitar_quantidades`). Isso não depende de uma nova tentativa do modelo: é um conserto direto.

O que NÃO está no inventário nunca é adicionado aqui: continua sendo apontado pelo validador, para a IA refazer.
"""
import re
from typing import List, Optional, Sequence

from receitas.coerencia import BASICOS_DE_LISTA, usados_no_preparo_fora_da_lista
from receitas.formatador import _estruturar, montar_texto
from receitas.unidades import (
    _TABELA, _plural, CONTAVEL, PESO, VOLUME, alimento_principal, quantidade_natural, quantidade_padrao,
)
from receitas.validador import ALIMENTOS, _canon, _palavras, _subtokens, _tokens_inventario, normalizar_texto

_LINHA_BASICO = {
    "sal": "sal a gosto",
    "agua": "água o suficiente",
    "oleo": "1 colher de sopa de óleo",
    "azeite": "1 colher de sopa de azeite",
    "pimenta": "pimenta-do-reino a gosto",
    "oregano": "orégano a gosto",
    "colorau": "colorau a gosto",
    "cominho": "cominho a gosto",
    "paprica": "páprica a gosto",
    "louro": "1 folha de louro",
    "tempero": "tempero a gosto",
}
_LINHA_BASICO = {_canon(k): v for k, v in _LINHA_BASICO.items()}

_SINONIMOS_DE_BUSCA = {
    "queijo": ("mussarela", "parmesao", "ricota", "requeijao", "coalho"),
    "carne": ("boi", "bovino", "bife", "costela", "charque"),
    "cheiro": ("salsa", "salsinha", "cebolinha", "coentro"),
}


def _item_do_inventario(token: str, inventario: Sequence[str]):
    """Nome do inventário que corresponde ao alimento `token` (ou None se o usuário não tem)."""
    candidatos = {token} | {_canon(t) for t in _SINONIMOS_DE_BUSCA.get(token, ())}
    for pai, filhos in _SINONIMOS_DE_BUSCA.items():
        if token in {_canon(f) for f in filhos}:
            candidatos.add(_canon(pai))
    for nome in inventario:
        if candidatos & _tokens_inventario(nome):
            return nome
    return None


def _nome_para_lista(nome_inventario: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\(.*?\)", "", nome_inventario)).strip()


def completar_lista_de_ingredientes(texto: str, inventario: Sequence[str]) -> str:
    """Devolve a receita com a lista de Ingredientes completada. Sem nada a consertar, devolve o texto igual."""
    _, d = _estruturar(texto)
    if d is None:
        return texto
    faltando = usados_no_preparo_fora_da_lista(d["ingredientes"], d["passos"])
    if not faltando:
        return texto

    novos: List[str] = []
    for token in faltando:
        if token in BASICOS_DE_LISTA:
            novos.append("- " + _LINHA_BASICO.get(token, f"{token} a gosto"))
            continue
        if token not in ALIMENTOS:
            continue
        nome = _item_do_inventario(token, inventario)
        if nome is None:
            continue
        nome = _nome_para_lista(nome)
        novos.append("- " + (quantidade_padrao(nome) or f"{nome.lower()} a gosto"))

    if not novos:
        return texto
    ingredientes = list(d["ingredientes"])
    chaves = {normalizar_texto(i) for i in ingredientes}
    for linha in novos:
        if normalizar_texto(linha) not in chaves:
            ingredientes.append(linha)
    titulo = d["titulo"]
    if not titulo:
        return texto
    return montar_texto(titulo, d["tempo"], d["porcoes"], ingredientes, d["passos"])


# --------------------------------------------------------------------------- #
# Quantidades absurdas
# --------------------------------------------------------------------------- #
TETO_ABSOLUTO = 3000.0         # g ou ml: nenhum ingrediente de uma receita caseira passa disso
MAX_FATOR_PORCOES = 4.0        # as quantidades da tabela são para 2 porções; para 8 ou mais, o teto quadruplica
FATOR_TETO_PESO = 3.0          # teto = 3 x a porção típica de 2 pessoas (bacon: 50 g -> 150 g; queijo: 100 g -> 300 g)
FATOR_TETO_UNIDADES = 3.0      # teto em unidades = 3 x a porção típica (ovo: 2 -> 6; pão: 2 -> 6)

# peso médio de uma unidade (g), para comparar 'g' com unidades em itens contáveis
_PESO_DA_UNIDADE = {
    "pao": 50, "tomate": 120, "cebola": 120, "batata": 150, "cenoura": 100, "banana": 100, "maca": 150,
    "laranja": 150, "limao": 80, "pimentao": 150, "abobrinha": 200, "pepino": 200, "beterraba": 150,
    "abacate": 300, "manga": 300, "ovo": 50, "bife": 150, "linguica": 100, "salsicha": 50, "calabresa": 200,
}
_PESO_DA_UNIDADE = {_canon(k): v for k, v in _PESO_DA_UNIDADE.items()}

# temperos secos: em receita caseira vão sempre 'a gosto' ou em pitadas, nunca em colheres de sopa ou gramas
_TEMPEROS_SECOS = {
    "sal": "sal", "pimenta": "pimenta-do-reino", "oregano": "orégano", "colorau": "colorau",
    "cominho": "cominho", "paprica": "páprica",
}
_RE_TEMPERO_SECO = re.compile(r"\b(sal|pimenta|oregano|colorau|cominho|paprica)\b")
_RE_QUANTIDADE_DE_TEMPERO = re.compile(
    r"\b(colheres?\s+de\s+sopa|colheres?\s+de\s+sobremesa|xicaras?|copos?|kg|g|gr|gramas?|ml)\b"
)
_RE_MEDIDAS_CASEIRAS = re.compile(
    r"^(colher|colheres|xicara|xicaras|copo|copos|dente|dentes|pitada|pitadas|fatia|fatias|folha|folhas|lata|latas|"
    r"pacote|pacotes|caixa|caixas|talo|talos|ramo|ramos|maco|macos|punhado|punhados|pedaco|pedacos|cubo|cubos|"
    r"gota|gotas|fio|fios|porcao|porcoes|cabeca|cabecas|sache|saches)\b"
)
_RE_LINHA_QTD = re.compile(
    r"^-\s*(?P<n>\d+(?:[.,]\d+)?|\d+\s*/\s*\d+)\s*(?P<un>kg|g|gr|gramas?|ml|l|litros?|unidades?)?\b\.?\s*"
    r"(?:de\s+)?(?P<resto>.*)$",
    re.IGNORECASE,
)
_RE_DISPONIVEL = re.compile(r"^(\d+(?:[.,]\d+)?)\s*(kg|g|ml|L|unidades?)\b")


def _numero(texto: str) -> float:
    t = texto.replace(" ", "")
    if "/" in t:
        a, b = t.split("/", 1)
        return float(a) / float(b) if float(b) else 1.0
    return float(t.replace(",", "."))


def _baixo(n: float) -> int:
    """Arredonda PARA BAIXO para um número 'de cozinha' (de 5 em 5 até 100, de 10 em 10 até 500, depois de 50 em 50)."""
    passo = 5 if n <= 100 else 10 if n <= 500 else 50
    return max(1, int(n // passo) * passo) if n >= passo else max(1, int(n))


def disponivel(nome: str, quantidade: Optional[str]):
    """O que o usuário tem de um item, como (valor, 'g'|'ml'|'unidades'). None se não houver quantidade legível."""
    if not quantidade:
        return None
    m = _RE_DISPONIVEL.match(quantidade_natural(nome, quantidade))
    if not m:
        return None
    valor = float(m.group(1).replace(",", "."))
    un = m.group(2)
    if valor <= 0:
        return None
    if un == "kg":
        return valor * 1000, "g"
    if un == "L":
        return valor * 1000, "ml"
    return valor, ("unidades" if un.startswith("unidade") else un)


def _no_numero(nome: str, quantidade: int) -> str:
    """Põe o nome no plural ('pão' -> 'pães') ou no singular ('ovos' -> 'ovo') conforme a quantidade."""
    if quantidade != 1:
        return _plural(nome)
    primeira, _, resto = nome.partition(" ")
    if primeira.endswith(("ães", "ões")):
        primeira = primeira[:-3] + "ão"
    elif primeira.endswith("s") and len(primeira) > 3:
        primeira = primeira[:-1]
    return f"{primeira} {resto}".strip()


def _porcoes_da_receita(valor: str) -> float:
    m = re.search(r"\d+(?:[.,]\d+)?", str(valor or ""))
    try:
        return float(m.group(0).replace(",", ".")) if m else 2.0
    except ValueError:
        return 2.0


def teto_do_alimento(alimento: str, porcoes: float = 2.0):
    """(teto, 'g'|'ml'|'unidades') realista para o alimento numa receita de `porcoes`. None se a tabela não conhece."""
    if alimento not in _TABELA:
        return None
    tipo, _, porcao = _TABELA[alimento]
    fator = min(max(porcoes, 2.0), 8.0) / 2.0
    fator = min(fator, MAX_FATOR_PORCOES)
    if tipo == CONTAVEL:
        return max(4.0, porcao * FATOR_TETO_UNIDADES) * fator, "unidades"
    return min(porcao * FATOR_TETO_PESO * fator, TETO_ABSOLUTO), ("g" if tipo == PESO else "ml")


def _inventario_por_nome(inventario: Sequence) -> dict:
    nomes = {}
    for item in inventario:
        if isinstance(item, dict):
            nomes[str(item.get("nome", ""))] = item.get("quantidade")
        else:
            nomes[str(item)] = None
    return nomes


def _consertar_linha(linha: str, porcoes: float, estoque: dict) -> str:
    """Devolve a linha de ingrediente com a quantidade limitada. Linha sem problema volta igual."""
    original = re.sub(r"^-\s*", "", linha.strip())
    item = re.sub(r"\bpacotes?\s+de\s+sopa\b", "colher de sopa", original, flags=re.I)
    padrao = linha if item == original else "- " + item   # o que devolver quando só há esse conserto (ou nenhum)
    norm = normalizar_texto(item)

    # temperos secos: 'a gosto' em vez de colheres de sopa, xícaras ou gramas
    tempero = _RE_TEMPERO_SECO.search(norm)
    if tempero and re.match(r"^[\d½¼¾/., ]", norm) and _RE_QUANTIDADE_DE_TEMPERO.search(norm):
        if not alimento_principal(item) or tempero.group(1) in _TEMPEROS_SECOS:
            return f"- {_TEMPEROS_SECOS[tempero.group(1)]} a gosto"

    m = _RE_LINHA_QTD.match("- " + item)
    if not m:
        return padrao
    try:
        n = _numero(m.group("n"))
    except (ValueError, ZeroDivisionError):
        return padrao
    un = normalizar_texto(m.group("un") or "")
    resto = m.group("resto").strip()
    if not un and _RE_MEDIDAS_CASEIRAS.match(normalizar_texto(resto)):
        return padrao
    alimento = alimento_principal(resto)
    if alimento is None or alimento not in _TABELA:
        return padrao
    tipo = _TABELA[alimento][0]

    # estoque do usuário para este alimento
    nome_estoque = next((nome for nome in estoque if alimento in _tokens_inventario(nome)), None)
    tem = disponivel(nome_estoque, estoque[nome_estoque]) if nome_estoque else None

    if un in ("kg", "g", "gr", "grama", "gramas", "ml", "l", "litro", "litros"):
        valor = n * 1000 if un in ("kg", "l", "litro", "litros") else n
        base = "ml" if un in ("ml", "l", "litro", "litros") else "g"
        if tipo == CONTAVEL:
            por_unidade = _PESO_DA_UNIDADE.get(alimento, 150)
            unidades = valor / por_unidade
            if alimento == "pao" or alimento == "ovo":   # pão e ovo se contam, nunca se pesam
                valor_un = max(1, round(unidades))
                teto, _ = teto_do_alimento(alimento, porcoes)
                valor_un = min(valor_un, int(teto))
                if tem and tem[1] == "unidades":
                    valor_un = max(1, min(valor_un, int(tem[0])))
                return f"- {valor_un} {_no_numero(resto, valor_un)}"
            teto, _ = teto_do_alimento(alimento, porcoes)
            if unidades > teto:
                valor = teto * por_unidade
            if tem and tem[1] == "unidades" and unidades > tem[0]:
                valor = min(valor, tem[0] * por_unidade)
            novo = _baixo(valor) if valor != n else None
            if novo is None or abs(novo - valor) < 1e-9 and valor == (n * 1000 if un in ("kg", "l") else n):
                return padrao
            return f"- {novo} g de {resto}"
        teto, un_teto = teto_do_alimento(alimento, porcoes)
        novo = valor
        if novo > teto:
            novo = teto
        if tem and tem[1] == base and novo > tem[0]:
            novo = tem[0]
        if novo == valor and un in ("g", "ml"):
            return padrao
        if novo == valor:   # só a unidade mudou (1 kg -> 1000 g): mantém o texto original
            return padrao
        return f"- {_baixo(novo)} {base} de {resto}"

    if tipo == CONTAVEL and un in ("", "unidade", "unidades"):
        teto, _ = teto_do_alimento(alimento, porcoes)
        novo = n
        if novo > teto:
            novo = teto
        if tem and tem[1] == "unidades" and novo > tem[0]:
            novo = tem[0]
        if novo == n:
            return padrao
        novo = max(1, int(novo))
        return f"- {novo} {_no_numero(resto, novo)}"
    return padrao


def limitar_quantidades(texto: str, inventario: Sequence = ()) -> str:
    """Corrige quantidades absurdas na lista de Ingredientes. Sem nada a consertar, devolve o texto igual.

    - peso e volume (g, kg, ml, L) acima do teto realista do alimento para o número de porções são reduzidos
      ('10 kg de bacon' -> '250 g de bacon'); pão e ovo escritos em gramas viram unidades ('600 g de pão' -> '6 pães');
    - nunca fica acima do que o usuário tem no inventário;
    - temperos secos em colheres de sopa, xícaras ou gramas viram 'a gosto' ('2 colheres de sopa de sal');
    - 'pacote de sopa' (erro comum do modelo) vira 'colher de sopa'.

    inventario: itens como dict {'nome', 'quantidade'} ou só nomes. O resto da receita não é alterado.
    """
    _, d = _estruturar(texto)
    if d is None or not d["titulo"]:
        return texto
    porcoes = _porcoes_da_receita(d["porcoes"])
    estoque = _inventario_por_nome(inventario)
    novos: List[str] = []
    mudou = False
    for linha in d["ingredientes"]:
        if linha.endswith(":"):
            novos.append(linha)
            continue
        nova = _consertar_linha(linha, porcoes, estoque)
        if nova != linha:
            mudou = True
        novos.append(nova)
    if not mudou:
        return texto
    return montar_texto(d["titulo"], d["tempo"], d["porcoes"], novos, d["passos"])
