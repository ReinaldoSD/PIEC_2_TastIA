"""Garantia de formato das receitas do TastIA (sem IA, roda sem modelo e sem internet).

Mesmo com o esqueleto e o plano B, uma receita pode chegar ao fim sem estrutura (por exemplo, no modo livre, quando
o modelo escreve tudo e divaga). Este módulo é a ÚLTIMA rede de segurança:

  1. `formato_perfeito(texto)`: confere o contrato fixo da receita (título, 'Tempo de preparo: ...', 'Porções: N',
     'Ingredientes' com itens '- ', 'Modo de preparo' com passos '1. ...' e nenhum markdown).
  2. `resgatar_formato(brutos, pedido, tempo)`: reconstrói a receita a partir do que o modelo escreveu, mesmo que
     bagunçado: pega os itens de lista como ingredientes e as linhas numeradas como passos, e remonta o texto padrão.
     Se não houver ingredientes e passos suficientes, devolve None (melhor erro claro do que texto quebrado).
"""
import re
from typing import Iterable, List, Optional

from receitas.formatador import (
    _RE_MARCADOR, _RE_NUMERADO, _sem_marcador, limpar_markdown, limpar_titulo, montar_texto, tempo_real_dos_passos,
)

MIN_INGREDIENTES = 1
MIN_PASSOS = 2

_RE_TEMPO_OK = re.compile(r"^Tempo de preparo: .*\d.*$")
_RE_PORCOES_OK = re.compile(r"^Porções: \d+.*$")
_RE_PASSO_OK = re.compile(r"^\d{1,2}\. \S.*$")
_RE_LIXO_MD = re.compile(r"[*#`_]{1,}\s*\S|\*\*")


def formato_perfeito(texto: Optional[str]) -> bool:
    """True se o texto segue exatamente o formato padrão da receita."""
    linhas = [l.rstrip() for l in str(texto or "").strip().splitlines()]
    if len(linhas) < 8 or _RE_LIXO_MD.search("\n".join(linhas)):
        return False
    titulo = linhas[0].strip()
    if not titulo or titulo.startswith("-") or titulo.lower().startswith(("ingredientes", "modo de")):
        return False
    if not _RE_TEMPO_OK.match(linhas[1]) or not _RE_PORCOES_OK.match(linhas[2]):
        return False
    try:
        i_ing = linhas.index("Ingredientes")
        i_prep = linhas.index("Modo de preparo")
    except ValueError:
        return False
    itens = [l for l in linhas[i_ing + 1:i_prep] if l.strip()]
    passos = [l for l in linhas[i_prep + 1:] if l.strip()]
    if i_prep < i_ing or len(itens) < MIN_INGREDIENTES or not all(l.startswith("- ") for l in itens):
        return False
    return len(passos) >= MIN_PASSOS and all(_RE_PASSO_OK.match(l) for l in passos)


def _titulo_do_bruto(linhas: List[str], pedido: str) -> str:
    for l in linhas[:6]:
        t = limpar_titulo(l)
        if t and not _RE_NUMERADO.match(l.strip()) and not _RE_MARCADOR.match(l.strip()) and len(t) <= 80 \
                and ":" not in t and not t.lower().startswith(("aqui", "taste", "como um", "foi feito")):
            return t
    p = (pedido or "receita").strip()
    return p[:1].upper() + p[1:]


def resgatar_formato(brutos: Iterable[str], pedido: str, tempo: Optional[str] = None) -> Optional[str]:
    """Remonta o texto padrão a partir de qualquer saída do modelo que tenha itens de lista e passos numerados."""
    for bruto in brutos:
        linhas = [l.strip() for l in limpar_markdown(bruto).splitlines() if l.strip()]
        ingredientes, passos = [], []
        for l in linhas:
            m_num = _RE_NUMERADO.match(l)
            if m_num and m_num.group(1).strip():
                passos.append(m_num.group(1).strip())
            elif _RE_MARCADOR.match(l):
                item = _sem_marcador(l).strip()
                if item and not item.endswith(":"):
                    ingredientes.append("- " + item)
        if len(ingredientes) < MIN_INGREDIENTES or len(passos) < MIN_PASSOS:
            continue
        passos = [p if p[-1] in ".!?" else p + "." for p in passos]
        tempo_txt = f"{tempo_real_dos_passos(passos)} minutos"   # tempo REAL dos passos, nunca o tempo pedido
        return montar_texto(_titulo_do_bruto(linhas, pedido), tempo_txt, "2", ingredientes, passos)
    return None
