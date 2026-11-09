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
    - 1 tomate

    Modo de preparo
    1. Bata os ovos.
    2. Junte o tomate.

Roda sem modelo e sem internet, então é fácil de testar.
"""
import re
from typing import List, Optional

from receitas.validador import normalizar_texto

_RE_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)
_RE_TOKEN_ESPECIAL = re.compile(r"<\|[^|>]*\|>")
_RE_CERCA = re.compile(r"^\s*(```|~~~).*$", re.MULTILINE)
_RE_MARCADOR = re.compile(r"^(?:[-*•·+]|–|—)\s+(.*)$")
_RE_NUMERADO = re.compile(r"^\d+\s*[.)\-:]\s*(.*)$")
_RE_TITULO_MD = re.compile(r"^#{1,6}\s*")

_RE_H_ING = re.compile(r"^ingredientes?\b")
_RE_H_PREPARO = re.compile(r"^(modo de (preparo|fazer)|preparo|instrucoes|como fazer|passo a passo)\b")
_RE_TEMPO = re.compile(r"^tempo\b")
_RE_PORCOES = re.compile(r"^(porc(ao|oes)|rendimento|serve)\b")
_RE_FECHAMENTO = re.compile(
    r"^(dica|dicas|observac\w*|obs\b|nota|notas|bom apetite|espero|variac\w*|sugestao|sugestoes|"
    r"curiosidade|informac\w*)\b"
)
_RE_FIM_FRASE = re.compile(r"[.!?)\]\"']$")
# Palavras que não terminam uma frase: se o texto acaba nelas, ele foi cortado no meio.
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
        if not s or re.fullmatch(r"[-*_=]{3,}", s):  # linha em branco ou separador '---'
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


# Se o modelo copiar o modelo do prompt ("<Título da receita>") em vez de inventar o nome, não vale como título.
_TITULOS_VAZIOS = {"titulo da receita", "nome da receita", "titulo", "nome", "receita", "titulo da receita aqui"}

_UNIDADES = (
    r"kg|g|mg|ml|l|litros?|xicaras?|xic|copos?|colheres?|colher|c\.?\s*s\.?|c\.?\s*c\.?|sopa|cha|sobremesa|"
    r"unidades?|unid|dentes?|pitadas?|fatias?|latas?|pacotes?|caixas?|maos?|punhados?|talos?|folhas?|ramos?|"
    r"pedacos?|cubos?|a gosto"
)


def _titulo_limpo(linha: str) -> str:
    t = _sem_marcador(linha).strip(" :.\"'<>")
    t = re.sub(r"^(nome da receita|receita|titulo)\s*:\s*", "", t, flags=re.I)
    t = t.strip(" :.\"'<>")
    if normalizar_texto(t).strip() in _TITULOS_VAZIOS:
        return ""
    return _capitalizar(t)


def _nome_do_ingrediente(item: str) -> str:
    """'- 2 colheres de sopa de azeite' -> 'azeite' (tira marcador, quantidade e unidade)."""
    s = re.sub(r"^[-*•]\s*", "", item).strip()
    s = re.sub(r"\(.*?\)", "", s)
    s = re.sub(r"^[\d½¼¾⅓⅔/.,\s]+", "", s)
    s = s.split(",")[0].strip()
    for _ in range(3):  # "colheres de sopa de azeite": tira unidade e "de" repetidos
        novo = re.sub(rf"^(?:{_UNIDADES})\b\.?\s*(?:de |do |da |d')?", "", s, flags=re.I).strip()
        if novo == s:
            break
        s = novo
    return s.strip(" .-")


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


def formatar_receita(texto: Optional[str]) -> str:
    """Devolve a receita em texto simples e padronizado (veja o exemplo no topo do arquivo).

    Se não achar as seções 'Ingredientes' e 'Modo de preparo', devolve só o texto limpo,
    para o validador acusar o formato incorreto e o gerador tentar de novo.
    """
    limpo = limpar_markdown(texto)
    linhas = limpo.splitlines()

    idx_ing = next((i for i, l in enumerate(linhas) if _eh_cabecalho_ing(l)), None)
    if idx_ing is None:
        return limpo
    idx_prep = next((i for i, l in enumerate(linhas) if i > idx_ing and _eh_cabecalho_preparo(l)), None)
    if idx_prep is None:
        return limpo

    # Título = linha mais próxima antes de 'Ingredientes' que não seja tempo/porções.
    titulo, tempo, porcoes = "", "", ""
    for j in range(idx_ing - 1, -1, -1):
        n = normalizar_texto(linhas[j]).strip()
        if _RE_TEMPO.match(n):
            tempo = tempo or _valor_apos_dois_pontos(linhas[j]) or _sem_marcador(linhas[j])
        elif _RE_PORCOES.match(n):
            porcoes = porcoes or _valor_apos_dois_pontos(linhas[j]) or _sem_marcador(linhas[j])
        else:
            titulo = _titulo_limpo(linhas[j])
            break
    # Tempo/porções também podem vir depois do título, dentro do bloco de ingredientes.
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
        chave = normalizar_texto(item)
        if not item or chave in vistos:
            continue
        vistos.add(chave)
        ingredientes.append(item if item.endswith(":") else "- " + item)

    # Modo de preparo: descarta fechamentos ('Dica:', 'Bom apetite!') e repetições.
    passos: List[str] = []
    vistos = set()
    for l in linhas[idx_prep + 1:]:
        passo = _sem_marcador(l)
        if _RE_FECHAMENTO.match(normalizar_texto(passo)):
            break
        chave = normalizar_texto(passo)
        if not passo or chave in vistos:
            continue
        vistos.add(chave)
        passos.append(passo)

    # Última frase cortada pelo limite de tokens (acaba no meio, ex.: "... por alguns"): remove.
    if len(passos) > 1 and _cortado(passos[-1]):
        passos.pop()
    passos = [_capitalizar(p if _RE_FIM_FRASE.search(p) else p + ".") for p in passos]

    if not ingredientes or not passos:
        return limpo
    if not titulo:   # o modelo esqueceu o nome (ou copiou o "<Título da receita>" do prompt)
        titulo = _titulo_pelos_ingredientes(ingredientes)

    partes = [titulo]
    if tempo:
        partes.append("Tempo de preparo: " + tempo)
    if porcoes:
        partes.append("Porções: " + porcoes)
    partes += ["", "Ingredientes"] + ingredientes
    partes += ["", "Modo de preparo"] + [f"{i}. {p}" for i, p in enumerate(passos, 1)]
    return "\n".join(partes)
