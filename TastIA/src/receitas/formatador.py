"""Limpeza e padronização do texto da receita gerada pela IA.

O modelo de linguagem costuma devolver markdown ('# Título', '## Ingredientes', '**negrito**',
'* item'), frases soltas antes do título ('Claro! Aqui está sua receita:'), observações no
final ('Dica: ...') e, às vezes, a última frase cortada porque acabou o limite de tokens.

Este módulo transforma tudo isso em um texto simples e sempre igual:

    Título da receita
    Tempo de preparo: 20 minutos
    Porções: 2

    Ingredientes
    - 2 ovos
    - 300 g de queijo ralado

    Modo de preparo
    1. Bata os ovos.
    2. Junte o tomate.

Nada vem depois do último passo (dicas, observações e "bom apetite" são descartados).
Cada ingrediente fica só com a quantidade e o nome: nada de '(maduro)', ', picado' ou 'opcional' ao lado.
O tempo de preparo é o tempo REAL dos passos (soma dos tempos citados + preparo), nunca o tempo máximo pedido.
Roda sem modelo e sem internet, então é fácil de testar.
"""
import re
from typing import List, Optional

from receitas.unidades import corrigir_linha_ingrediente
from receitas.validador import ALIMENTOS, BASICOS, _canon, _palavras, normalizar_texto

_RE_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)
_RE_TOKEN_ESPECIAL = re.compile(r"<\|[^|>]*\|>")
_RE_CERCA = re.compile(r"^\s*(```|~~~).*$", re.MULTILINE)
_RE_MARCADOR = re.compile(r"^(?:[-•·+–—]\s*|\*\s+)(.*)$")   # '- 2 ovos', '-200 g', '• 2 ovos', '* 2 ovos'
_RE_NUMERADO = re.compile(r"^\d+\s*[.)\-:]\s*(.*)$")
_RE_TITULO_MD = re.compile(r"^#{1,6}\s*")

_RE_H_ING = re.compile(r"^ingredientes?\b")
_RE_H_PREPARO = re.compile(r"^(modo de (preparo|fazer)|preparo|instrucoes|como fazer|passo a passo)\b")
_RE_TEMPO = re.compile(r"^tempo\b")
_RE_PORCOES = re.compile(
    r"^((porc(ao|oes)|rendimento|rende|serve)\b|quantidade\s*:|para\s+\d+|\d+\s*(porc|pessoa)|"
    r"(numero|quantidade|total)\s+de\s+(porc|pessoa))"
)
_RE_OUTRA_META = re.compile(r"^(dificuldade|categoria|nivel|calorias|custo|refeicao)\b\s*:")
_RE_FECHAMENTO = re.compile(
    r"^(dica|dicas|observac\w*|obs\b|nota|notas|bom apetite|espero|variac\w*|sugestao|sugestoes|"
    r"curiosidade|informac\w*|receita completa|tempo total|nome do (prato|proto)|porcoes\s*:|"
    r"combinac\w* que fazem sentido|formato\b|exemplo\b|escreva\b|prato\s*:)\b"
)
_RE_FIM_FRASE = re.compile(r"[.!?)\]\"']$")
_PALAVRAS_PENDENTES = {
    "de", "da", "do", "das", "dos", "a", "o", "as", "os", "e", "em", "com", "sem", "para", "por",
    "no", "na", "nos", "nas", "um", "uma", "ou", "ao", "aos", "alguns", "algumas", "que", "se",
    "ate", "cerca", "cada", "mais",
}


# --------------------------------------------------------------------------- #
# Limpeza de markdown
# --------------------------------------------------------------------------- #
def _limpar_enfase(linha: str) -> str:
    """Remove **negrito**, __negrito__, *itálico*, _itálico_ e `código` de uma linha."""
    linha = re.sub(r"\*\*(.+?)\*\*", r"\1", linha)
    linha = re.sub(r"__(.+?)__", r"\1", linha)
    linha = re.sub(r"(?<![\w*])\*(?!\s)([^*\n]+?)(?<!\s)\*(?![\w*])", r"\1", linha)
    linha = re.sub(r"(?<![\w_])_(?!\s)([^_\n]+?)(?<!\s)_(?![\w_])", r"\1", linha)
    linha = linha.replace("`", "")
    return linha.replace("**", "").replace("__", "")


def limpar_markdown(texto: Optional[str]) -> str:
    """Tira marcas de markdown, blocos <think> e tokens especiais, linha por linha."""
    texto = _RE_THINK.sub("", str(texto or ""))
    texto = _RE_TOKEN_ESPECIAL.sub("", texto)
    texto = _RE_CERCA.sub("", texto)
    saida: List[str] = []
    for bruta in texto.replace("\r", "").splitlines():
        s = bruta.strip()
        if not s or re.fullmatch(r"[-*_=]{3,}", s):
            continue
        s = _RE_TITULO_MD.sub("", s)
        s = re.sub(r"^>+\s*", "", s)
        marcador = _RE_MARCADOR.match(s)
        prefixo = ""
        if marcador and not re.match(r"^\*\*", s):
            prefixo, s = "- ", marcador.group(1)
        s = _limpar_enfase(s)
        s = re.sub(r"\s+", " ", s).strip()
        if s:
            saida.append(prefixo + s)
    return "\n".join(saida)


# --------------------------------------------------------------------------- #
# Padronização
# --------------------------------------------------------------------------- #
def _sem_marcador(linha: str) -> str:
    linha = linha.strip()
    m = _RE_MARCADOR.match(linha) or _RE_NUMERADO.match(linha)
    return (m.group(1) if m else linha).strip()


def _norm(linha: str) -> str:
    return normalizar_texto(_sem_marcador(linha)).strip(" :")


def _eh_cabecalho_ing(linha: str) -> bool:
    return not linha.startswith("- ") and len(linha) < 60 and bool(_RE_H_ING.match(_norm(linha)))


def _eh_cabecalho_preparo(linha: str) -> bool:
    n = _norm(linha)
    return (not linha.startswith("- ") and not linha[:1].isdigit() and len(linha) < 40
            and bool(_RE_H_PREPARO.match(n)))


def _eh_meta(linha: str) -> bool:
    n = normalizar_texto(linha).strip()
    return bool(_RE_TEMPO.match(n) or _RE_PORCOES.match(n))


def _valor_apos_dois_pontos(linha: str) -> str:
    return linha.split(":", 1)[1].strip() if ":" in linha else ""


def _numero_porcoes(valor: str) -> str:
    """'4 pessoas' -> '4'; '4 a 6 porções' -> '4 a 6'. Sem número, devolve o texto como veio."""
    m = re.search(r"\d+(?:\s*(?:a|ou|-|–)\s*\d+)?", valor)
    return re.sub(r"\s+", " ", m.group(0)).strip() if m else valor.strip()


PORCOES_PADRAO = "2"
MINUTOS_POR_PASSO = 3


def estimar_tempo(passos: List[str]) -> str:
    """'cerca de 25 minutos', calculado pelos passos: soma os tempos citados ('por 10 minutos', '1 hora')
    + 3 min por passo, arredondado para cima de 5 em 5 (mínimo 10). Usado só se o modelo não informou o tempo."""
    citados = 0
    for passo in passos:
        for valor, unidade in re.findall(r"(\d+)\s*(horas?|h|minutos?|min)\b", normalizar_texto(passo)):
            citados += int(valor) * (60 if unidade.startswith("h") else 1)
    total = citados + MINUTOS_POR_PASSO * len(passos)
    total = max(10, -(-total // 5) * 5)
    return f"cerca de {total} minutos"


# --------------------------------------------------------------------------- #
# Tempo REAL de preparo
# --------------------------------------------------------------------------- #
MINUTOS_DE_PREPARO_POR_PASSO = 2
_RE_TEMPO_CITADO = re.compile(r"(\d+(?:[.,]\d+)?)\s*(horas?|h|minutos?|min)\b")
_RE_DOIS_LADOS = re.compile(r"\bde cada lado\b|\bdos dois lados\b")


def minutos_citados(passos: List[str]) -> int:
    """Soma dos tempos escritos nos passos ('por 10 minutos', '1 hora', 'meia hora', '2 minutos de cada lado')."""
    total = 0.0
    for passo in passos:
        t = normalizar_texto(passo)
        achado = 0.0
        for valor, unidade in _RE_TEMPO_CITADO.findall(t):
            numero = float(valor.replace(",", "."))
            achado += numero * (60 if unidade.startswith("h") else 1)
        if re.search(r"\bhora e meia\b", t):
            achado += 30
        if re.search(r"\bmeia hora\b", t):
            achado += 30
        if achado and _RE_DOIS_LADOS.search(t):
            achado *= 2
        total += achado
    return int(round(total))


def tempo_real_dos_passos(passos: List[str], extra: int = 0) -> int:
    """Minutos REAIS da receita: tempos citados nos passos + 2 min de preparo por passo (+ extra), de 5 em 5."""
    total = minutos_citados(passos) + MINUTOS_DE_PREPARO_POR_PASSO * len(passos) + max(0, int(extra))
    return max(5, -(-total // 5) * 5)


def _minutos_escritos(tempo: str) -> Optional[int]:
    t = normalizar_texto(tempo or "")
    horas = re.search(r"(\d+)\s*(?:h\b|hora)", t)
    minutos = re.search(r"(\d+)\s*min", t)
    if horas or minutos:
        return (int(horas.group(1)) * 60 if horas else 0) + (int(minutos.group(1)) if minutos else 0)
    numero = re.search(r"\d+", t)
    return int(numero.group(0)) if numero else None


def tempo_verdadeiro(tempo: str, passos: List[str], tempo_pedido: Optional[str] = None) -> str:
    """O tempo que vai para a receita: o escrito, se for possível; senão o tempo REAL calculado pelos passos.

    Troca o tempo escrito quando (1) falta, (2) é menor que a soma dos tempos dos próprios passos (impossível) ou
    (3) é igual ao tempo máximo escolhido na tela e o cálculo pelos passos dá outro valor (o modelo copiou o pedido).
    """
    real = tempo_real_dos_passos(passos)
    escrito = _minutos_escritos(tempo)
    if escrito is None or escrito <= 0:
        return f"{real} minutos"
    if escrito < minutos_citados(passos):
        return f"{real} minutos"
    if tempo_pedido and str(tempo_pedido).strip().isdigit() and escrito == int(str(tempo_pedido).strip()) \
            and abs(escrito - real) > 5:
        return f"{real} minutos"
    return tempo


# --------------------------------------------------------------------------- #
# Ingrediente = quantidade + nome (sem observação ao lado)
# --------------------------------------------------------------------------- #
_RE_PAREN_INGREDIENTE = re.compile(r"\s*\([^)]*\)?")
_RE_NOTA_COM_TRACO = re.compile(r"\s+[-–—]\s+\S.*$")
_RE_NOTA_DE_USO = re.compile(
    r"\s+(?:para|pra)\s+(?:untar|decorar|enfeitar|servir|polvilhar|fritar|regar|temperar|finalizar|acompanhar|"
    r"cobrir|empanar|rechear|a massa|o molho|a cobertura|o recheio)\b.*$", re.IGNORECASE)
_RE_OPCIONAL = re.compile(r"\s*,?\s*\b(?:opcional|se quiser|se preferir|se gostar|se desejar|a sua escolha)\b.*$", re.IGNORECASE)
_RE_QUANTIDADE_NA_NOTA = re.compile(r"^(a gosto|ao gosto|o suficiente|quanto baste|q\.?\s?b\.?)\b", re.IGNORECASE)


def _nota_tem_alimento(nota: str) -> bool:
    """True se o trecho depois da vírgula cita outro alimento ou básico ('sal, pimenta e orégano')."""
    return any(sub in ALIMENTOS or sub in BASICOS for p in _palavras(nota) for sub in [_canon(x) for x in p.split("-")])


def limpar_observacao_ingrediente(item: str) -> str:
    """'- 2 tomates (maduros), picados' -> '- 2 tomates'; '- 1 cebola - para refogar' -> '- 1 cebola'.

    Fica só a quantidade e o nome. Preserva 'a gosto' e linhas que listam mais de um alimento
    ('sal, pimenta e orégano'), que o validador confere item por item.
    """
    s = item.strip()
    if not s or s.endswith(":"):
        return s
    prefixo = "- " if s.startswith("- ") else ""
    corpo = s[2:] if prefixo else s
    corpo = _RE_PAREN_INGREDIENTE.sub("", corpo)
    corpo = _RE_NOTA_COM_TRACO.sub("", corpo)
    corpo = _RE_OPCIONAL.sub("", corpo)
    corpo = _RE_NOTA_DE_USO.sub("", corpo)
    if "," in corpo:
        antes, depois = corpo.split(",", 1)
        depois = depois.strip()
        if _RE_QUANTIDADE_NA_NOTA.match(depois):
            corpo = f"{antes.strip()} {depois}"
        elif not _nota_tem_alimento(depois) and not re.match(r"^\d", depois):
            corpo = antes
    corpo = re.sub(r"\s+", " ", corpo).strip(" ,;.-–—")
    return prefixo + corpo if corpo else ""



def cortar_apos_ultimo_passo(linhas: List[str]) -> List[str]:
    """Das linhas depois de 'Modo de preparo', fica só com os passos: nada pode vir depois do último.

    Corta na primeira linha de fechamento ('Dica:', 'Observação:', 'Bom apetite!'...) ou, se os passos
    são numerados, no primeiro texto solto depois do último passo numerado.
    """
    linhas = [l for l in linhas if l.strip()]
    corte = None
    for i, l in enumerate(linhas):
        n = normalizar_texto(_sem_marcador(l)).strip(" :")
        if (
            _RE_FECHAMENTO.match(n)
            or _RE_H_ING.match(n)
            or _RE_H_PREPARO.match(n)
            or _RE_TEMPO.match(n)
            or _RE_PORCOES.match(n)
        ):
            corte = i
            break
    if corte is None:
        numeradas = [i for i, l in enumerate(linhas) if _RE_NUMERADO.match(l.strip())]
        if numeradas and numeradas[-1] + 1 < len(linhas):
            corte = numeradas[-1] + 1
    return linhas if corte is None else linhas[:corte]


def _cortado(passo: str) -> bool:
    """True se o passo parece interrompido no meio da frase."""
    if _RE_FIM_FRASE.search(passo):
        return False
    palavras = normalizar_texto(passo).strip(" ,;:-").split()
    return passo.rstrip().endswith((",", ";", ":", "-")) or (bool(palavras) and palavras[-1] in _PALAVRAS_PENDENTES)


def _capitalizar(texto: str) -> str:
    for i, c in enumerate(texto):
        if c.isalpha():
            return texto[:i] + c.upper() + texto[i + 1:]
    return texto


_RE_TITULO_INVALIDO = re.compile(
    r"^(numero de|quantidade de|total de|tempo\b|porc|dificuldade|ingredientes?\b|modo de|escreva|aqui esta|aqui vai|"
    r"claro|segue|formato|combinac|exemplo|prato\s*:|foi feito)"
)
MAX_CHARS_TITULO = 90
MAX_INGREDIENTES = 25   # o modelo às vezes entra em loop e repete temperos e variações sem parar

_TITULOS_VAZIOS = {"titulo da receita", "nome da receita", "titulo", "nome", "receita", "titulo da receita aqui"}

_UNIDADES = (
    r"kg|g|mg|ml|l|litros?|xicaras?|xic|copos?|colheres?|colher|c\.?\s*s\.?|c\.?\s*c\.?|sopa|cha|sobremesa|"
    r"unidades?|unid|dentes?|pitadas?|fatias?|latas?|pacotes?|caixas?|maos?|punhados?|talos?|folhas?|ramos?|"
    r"pedacos?|cubos?|a gosto"
)

_RE_ROTULO_TITULO = re.compile(
    r"^\s*(?:nome(?:\s+d[aeo]s?\s+(?:receita|prato|proto))?|t[ií]tulo(?:\s+d[aeo]s?\s+(?:receita|prato))?|receita|prato)"
    r"\s*[:\-–—]\s*",
    re.IGNORECASE,
)


def limpar_titulo(texto: Optional[str]) -> str:
    """'Nome: Omelete de tomate' -> 'Omelete de tomate'. Devolve '' se sobrar só um rótulo vazio ('Nome da receita')."""
    if str(texto or "").rstrip().endswith(":"):   # 'Escreva a receita solicitada:' não é nome de prato
        return ""
    t = str(texto or "").strip(" :.\"'<>*#")
    for _ in range(3):
        novo = _RE_ROTULO_TITULO.sub("", t).strip(" :.\"'<>*#")
        if novo == t:
            break
        t = novo
    n = normalizar_texto(t).strip()
    if n in _TITULOS_VAZIOS or _RE_TITULO_INVALIDO.match(n) or len(t) > MAX_CHARS_TITULO:
        return ""
    return _capitalizar(t)


def _titulo_limpo(linha: str) -> str:
    return limpar_titulo(_sem_marcador(linha))


def _nome_do_ingrediente(item: str) -> str:
    """'- 2 colheres de sopa de azeite' -> 'azeite' (tira marcador, quantidade e unidade)."""
    s = re.sub(r"^[-*•]\s*", "", item).strip()
    s = re.sub(r"\(.*?\)", "", s)
    s = re.sub(r"^[\d½¼¾⅓⅔/.,\s]+", "", s)
    s = s.split(",")[0].strip()
    for _ in range(3):
        novo = re.sub(rf"^(?:{_UNIDADES})\b\.?\s*(?:de |do |da |d')?", "", s, flags=re.I).strip()
        if novo == s:
            break
        s = novo
    return s.strip(" .-")


_RE_PESO_VOLUME = re.compile(r"^(\d+(?:[.,]\d+)?)\s*(kg|g|mg|ml|l)\b\.?\s*(?:de\s+)?(?=[^\W\d_])", re.I)


def _padronizar_quantidade(item: str) -> str:
    """'300g queijo ralado' -> '300 g de queijo ralado' (peso/volume sempre com espaço e 'de')."""
    return _RE_PESO_VOLUME.sub(lambda m: f"{m.group(1)} {m.group(2).lower()} de ", item.strip())


def _titulo_pelos_ingredientes(ingredientes: List[str]) -> str:
    """Título de reserva quando o modelo não escreve o nome: 'Receita com ovos e tomate'."""
    nomes: List[str] = []
    for item in ingredientes:
        if item.endswith(":"):
            continue
        nome = _nome_do_ingrediente(item)
        if nome and normalizar_texto(nome) not in {normalizar_texto(n) for n in nomes}:
            nomes.append(nome.lower())
        if len(nomes) == 3:
            break
    if not nomes:
        return "Receita do dia"
    if len(nomes) == 1:
        return f"Receita com {nomes[0]}"
    return "Receita com " + ", ".join(nomes[:-1]) + " e " + nomes[-1]


def _estruturar(texto: Optional[str], corrigir_unidades: bool = True):
    """Lê o texto da receita. Devolve (texto_limpo, dados); dados é None se faltar 'Ingredientes' ou 'Modo de preparo'."""
    limpo = limpar_markdown(texto)
    linhas = limpo.splitlines()

    idx_ing = next((i for i, l in enumerate(linhas) if _eh_cabecalho_ing(l)), None)
    if idx_ing is None:
        return limpo, None
    idx_prep = next((i for i, l in enumerate(linhas) if i > idx_ing and _eh_cabecalho_preparo(l)), None)
    if idx_prep is None:
        return limpo, None

    titulo, tempo, porcoes = "", "", ""
    for j in range(idx_ing - 1, -1, -1):
        n = normalizar_texto(linhas[j]).strip()
        if _RE_TEMPO.match(n):
            tempo = tempo or _valor_apos_dois_pontos(linhas[j]) or _sem_marcador(linhas[j])
        elif _RE_PORCOES.match(n):
            porcoes = porcoes or _valor_apos_dois_pontos(linhas[j]) or _sem_marcador(linhas[j])
        elif _RE_OUTRA_META.match(n):
            continue
        else:
            candidato = _titulo_limpo(linhas[j])
            if candidato or idx_ing - j >= 4:
                titulo = candidato
                break

    ingredientes: List[str] = []
    vistos = set()
    for l in linhas[idx_ing + 1:idx_prep]:
        n = normalizar_texto(l).strip()
        if _RE_TEMPO.match(n) and ":" in l:
            tempo = tempo or _valor_apos_dois_pontos(l)
            continue
        if _RE_PORCOES.match(n) and ":" in l:
            porcoes = porcoes or _valor_apos_dois_pontos(l)
            continue
        item = _sem_marcador(l)
        if not item.endswith(":"):
            item = limpar_observacao_ingrediente(item)
        chave = normalizar_texto(item)
        if not item or chave in vistos:
            continue
        vistos.add(chave)
        if not item.endswith(":"):
            nome = normalizar_texto(_nome_do_ingrediente(item))
            if nome and ("nome", nome) in vistos:
                continue                      # o mesmo ingrediente de novo (outra quantidade): fica o primeiro
            if nome:
                vistos.add(("nome", nome))
            if sum(1 for i in ingredientes if not i.endswith(":")) >= MAX_INGREDIENTES:
                break
            item = _padronizar_quantidade(item)
            if corrigir_unidades:
                item = corrigir_linha_ingrediente(item)
        ingredientes.append(item if item.endswith(":") else "- " + item)

    linhas_passos = cortar_apos_ultimo_passo(linhas[idx_prep + 1:])
    passos: List[str] = []
    vistos = set()
    for l in linhas_passos:
        passo = re.sub(r":\.+$", ":", _sem_marcador(l)).strip()
        if not passo or passo.endswith(":"):
            continue
        chave = normalizar_texto(passo)
        if chave in vistos or " = " in passo or chave == normalizar_texto(titulo).strip():
            continue
        vistos.add(chave)
        passos.append(passo)

    if len(passos) > 1 and _cortado(passos[-1]):
        passos.pop()
    passos = [_capitalizar(p if _RE_FIM_FRASE.search(p) else p + ".") for p in passos]

    if not ingredientes or not passos:
        return limpo, None
    return limpo, {
        "titulo": titulo,
        "tempo": tempo.strip(),
        "porcoes": _numero_porcoes(porcoes) if porcoes else "",
        "ingredientes": ingredientes,
        "passos": passos,
    }


def formatar_receita(texto: Optional[str], tempo_pedido: Optional[str] = None) -> str:
    """Devolve a receita em texto simples e padronizado (veja o exemplo no topo do arquivo).

    tempo_pedido: o tempo máximo escolhido na tela ('15', '30'...). Serve só para NÃO deixar o modelo copiá-lo como se
    fosse o tempo da receita: o tempo escrito é sempre o tempo real dos passos.
    """
    limpo, d = _estruturar(texto)
    if d is None:
        return limpo

    titulo = d["titulo"] or _titulo_pelos_ingredientes(d["ingredientes"])
    tempo = tempo_verdadeiro(d["tempo"], d["passos"], tempo_pedido)
    return montar_texto(titulo, tempo, d["porcoes"], d["ingredientes"], d["passos"])


def montar_texto(titulo: str, tempo: str, porcoes: str, ingredientes: List[str], passos: List[str]) -> str:
    """Monta o texto padrão da receita (título, tempo, porções, ingredientes com '- ' e passos numerados)."""
    if re.fullmatch(r"\d+", tempo):
        tempo += " minutos"
    partes = [titulo, "Tempo de preparo: " + tempo, "Porções: " + (porcoes or PORCOES_PADRAO)]
    partes += ["", "Ingredientes"] + ingredientes
    partes += ["", "Modo de preparo"] + [f"{i}. {p}" for i, p in enumerate(passos, 1)]
    return "\n".join(partes)


def campos_ausentes(texto: Optional[str]) -> List[str]:
    """Campos do cabeçalho que o MODELO não escreveu: 'título', 'tempo de preparo', 'porções'."""
    _, d = _estruturar(texto)
    if d is None:
        return []
    return [nome for nome, chave in (("título", "titulo"), ("tempo de preparo", "tempo"), ("porções", "porcoes"))
            if not d[chave]]