"""Leitura das receitas salvas no banco para a página de histórico.

A tabela `receitas` guarda só (pedido, conteudo, criado_em). Título, tempo, porções,
ingredientes, passos e categoria são extraídos do texto da receita na hora de listar,
então não é preciso mudar o banco de ninguém.
"""
import re
from typing import Dict, List

from receitas.validador import _dividir_secoes, normalizar_texto

CATEGORIAS = ["Café da manhã", "Almoço", "Jantar", "Lanche", "Sobremesa", "Outros"]

# 1ª passada: nome explícito da refeição. 2ª passada: palavras que sugerem a categoria.
_EXPLICITAS = [
    ("Café da manhã", r"\bcafe da manha\b|\bdesjejum\b"),
    ("Almoço", r"\balmoc\w*"),
    ("Jantar", r"\bjant\w*"),
    ("Lanche", r"\blanch\w*"),
    ("Sobremesa", r"\bsobremesa\w*"),
]
_SUGERIDAS = [
    ("Sobremesa", r"\bbolo\w*|\bpudim\b|\bmousse\b|\bbrigadeiro\w*|\bsorvete\w*|(?<!batata )(?<!batatas )\bdoces?\b"),
    ("Lanche", r"\bsanduiche\w*|\bpetisco\w*|\bpao com\b|\btapioca\w*"),
    ("Café da manhã", r"\bcafe\b|\bomelete\b|\bmingau\b"),
]


def inferir_categoria(pedido: str, titulo: str = "") -> str:
    """Chuta a categoria pelo pedido (e, se faltar, pelo título). É uma heurística simples."""
    textos = [normalizar_texto(t) for t in (pedido or "", titulo or "") if t]
    for regras in (_EXPLICITAS, _SUGERIDAS):
        for texto in textos:
            for categoria, padrao in regras:
                if re.search(padrao, texto):
                    return categoria
    return "Outros"


def _limpar_item(linha: str) -> str:
    sem_marcador = re.sub(r"^\s*(?:[-*•·]+|\d+[.)])\s*", "", linha)
    return sem_marcador.replace("**", "").strip()


def _minutos(texto: str):
    """Lê '**Tempo de preparo:** 1 hora e 30 minutos' -> 90. Devolve None se não achar."""
    m = re.search(r"tempo[^\n0-9]{0,30}([^\n]*)", normalizar_texto(texto))
    if not m:
        return None
    trecho = m.group(1)
    horas = re.search(r"(\d+)\s*(?:h\b|hora)", trecho)
    minutos = re.search(r"(\d+)\s*min", trecho)
    if horas or minutos:
        return (int(horas.group(1)) * 60 if horas else 0) + (int(minutos.group(1)) if minutos else 0)
    numero = re.search(r"(\d+)", trecho)
    return int(numero.group(1)) if numero else None


def _porcoes(texto: str):
    m = re.search(r"porc(?:ao|oes)[^\n0-9]*(\d+)", normalizar_texto(texto))
    return int(m.group(1)) if m else None


def interpretar_receita(conteudo: str, pedido: str = "") -> Dict:
    """Quebra o texto da receita em partes para a página mostrar."""
    secoes = _dividir_secoes(conteudo or "")
    ingredientes: List[str] = [
        _limpar_item(l) for l in secoes["ing"] if not l.rstrip().endswith(":")
    ]
    preparo: List[str] = [_limpar_item(l) for l in secoes["prep"]]
    titulo = re.sub(r"^[#*\s]+|[*\s]+$", "", secoes["titulo"]) or (pedido or "Receita")[:60]
    return {
        "titulo": titulo,
        "tempo_min": _minutos(conteudo or ""),
        "porcoes": _porcoes(conteudo or ""),
        "ingredientes": [i for i in ingredientes if i],
        "preparo": [p for p in preparo if p],
        "categoria": inferir_categoria(pedido, titulo),
    }


def _iso_utc(criado_em) -> str:
    """O SQLite grava CURRENT_TIMESTAMP em UTC como 'AAAA-MM-DD HH:MM:SS'."""
    texto = str(criado_em or "")
    if len(texto) == 19 and "T" not in texto:
        return texto.replace(" ", "T") + "Z"
    return texto


def montar_item_historico(linha) -> Dict:
    """Converte uma linha da tabela `receitas` no JSON usado pela página de histórico."""
    item = interpretar_receita(linha["conteudo"], linha["pedido"])
    item.update({
        "id": linha["id"],
        "pedido": linha["pedido"],
        "texto": linha["conteudo"],
        "criado_em": _iso_utc(linha["criado_em"]),
    })
    return item
