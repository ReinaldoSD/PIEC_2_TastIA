"""Pós-processamento da Percepção: filtros, NMS, duplicatas, agregação e mescla de origens.

Funções puras (sem modelos, sem torch), fáceis de testar.

Vocabulário:
  objeto     = caixa vinda do detector: {"bbox": [...], "label_florence": str}
  candidato  = objeto já classificado: {"bbox", "nome", "categoria", "confianca",
               "revisar", "alternativas"}
  item       = resultado final que vai para a API (sem bbox)
"""

import re
from typing import Dict, List, Optional

from percepcao.catalogo import PALAVRAS_LABEL_IGNORADAS
from percepcao.parametros import (
    DEDUP_IOU,
    DET_AREA_MAX_REL,
    DET_AREA_MIN_REL,
    GRUPO_CONTENCAO,
    GRUPO_MIN_FILHOS,
    MAX_ITENS,
    NMS_IOU,
)
from percepcao.recortes import area, contencao, iou


# --------------------------------------------------------------------------- #
# Antes do CLIP: filtrar e remover caixas repetidas
# --------------------------------------------------------------------------- #
def label_ignorado(label: Optional[str]) -> bool:
    """True se o label do Florence indica algo que não é comida (mesa, geladeira, pessoa...)."""
    palavras = re.findall(r"[a-z]+", str(label or "").lower())
    return any(p in PALAVRAS_LABEL_IGNORADAS for p in palavras)


def filtrar_caixas(objetos: List[Dict], largura: int, altura: int) -> List[Dict]:
    """Descarta caixas gigantes (prateleira, tigela, cena), minúsculas e labels que não são comida.

    Se um alimento ocupa a foto quase toda, a caixa dele é descartada aqui, mas a varredura
    em blocos (que inclui a foto inteira) o recupera.
    """
    area_foto = float(max(1, largura * altura))
    mantidos: List[Dict] = []
    for obj in objetos:
        proporcao = area(obj["bbox"]) / area_foto
        if proporcao > DET_AREA_MAX_REL or proporcao < DET_AREA_MIN_REL:
            continue
        if label_ignorado(obj.get("label_florence")):
            continue
        mantidos.append(obj)
    return mantidos


def aplicar_nms(objetos: List[Dict], iou_max: float = NMS_IOU) -> List[Dict]:
    """Remove caixas que cobrem o mesmo objeto (IoU alto), mantendo a maior."""
    ordenados = sorted(objetos, key=lambda o: -area(o["bbox"]))
    mantidos: List[Dict] = []
    for obj in ordenados:
        if all(iou(obj["bbox"], m["bbox"]) < iou_max for m in mantidos):
            mantidos.append(obj)
    return mantidos


# --------------------------------------------------------------------------- #
# Depois do CLIP: duplicatas e agrupamento
# --------------------------------------------------------------------------- #
def remover_caixas_de_grupo(candidatos: List[Dict]) -> List[Dict]:
    """Descarta a caixa que engloba várias caixas do MESMO item (ex.: a tigela com 6 maçãs).

    As caixas menores são as unidades reais; a grande só inflaria ou confundiria a contagem.
    """
    descartar = set()
    for i, a in enumerate(candidatos):
        filhos = 0
        for j, b in enumerate(candidatos):
            if i == j or b["nome"] != a["nome"]:
                continue
            if area(b["bbox"]) < area(a["bbox"]) and contencao(b["bbox"], a["bbox"]) >= GRUPO_CONTENCAO:
                filhos += 1
        if filhos >= GRUPO_MIN_FILHOS:
            descartar.add(i)
    return [c for i, c in enumerate(candidatos) if i not in descartar]


def deduplicar_classificados(candidatos: List[Dict], iou_min: float = DEDUP_IOU) -> List[Dict]:
    """Une duplicatas: mesmo ingrediente e caixas quase iguais contam uma vez só (fica a mais confiante)."""
    sem_grupo = remover_caixas_de_grupo(candidatos)
    ordenados = sorted(sem_grupo, key=lambda c: -c["confianca"])
    mantidos: List[Dict] = []
    for cand in ordenados:
        repetido = any(
            m["nome"] == cand["nome"] and iou(m["bbox"], cand["bbox"]) >= iou_min
            for m in mantidos
        )
        if not repetido:
            mantidos.append(cand)
    return mantidos


# --------------------------------------------------------------------------- #
# Montagem dos itens finais
# --------------------------------------------------------------------------- #
def _texto_quantidade(qtd: int) -> str:
    return f"{qtd} {'unidade' if qtd == 1 else 'unidades'}"


def _montar_item(melhor: Dict, quantidade: int, origem: str) -> Dict:
    revisar = bool(melhor.get("revisar", False))
    return {
        "nome": melhor["nome"],
        "categoria": melhor["categoria"],
        "quantidade": _texto_quantidade(max(1, quantidade)),
        "confianca": float(melhor["confianca"]),
        "selecionado": not revisar,
        "revisar": revisar,
        "alternativas": list(melhor.get("alternativas", [])),
        "origem": origem,
    }


def agregar_itens(candidatos: List[Dict], origem: str = "detector", contar: bool = True) -> List[Dict]:
    """Agrupa por nome. `contar=True` usa o número de caixas como quantidade; senão, 1 unidade.

    A confiança do item é a do seu melhor candidato.
    """
    grupos: Dict[str, List[Dict]] = {}
    for cand in candidatos:
        grupos.setdefault(cand["nome"], []).append(cand)

    itens = []
    for membros in grupos.values():
        melhor = max(membros, key=lambda m: m["confianca"])
        itens.append(_montar_item(melhor, len(membros) if contar else 1, origem))
    return itens


def mesclar_origens(itens_detector: List[Dict], itens_blocos: List[Dict]) -> List[Dict]:
    """Junta detector + blocos sem duplicar: o detector manda, os blocos só acrescentam o que faltou."""
    nomes = {i["nome"] for i in itens_detector}
    return list(itens_detector) + [i for i in itens_blocos if i["nome"] not in nomes]


def ordenar_e_limitar(itens: List[Dict], maximo: int = MAX_ITENS) -> List[Dict]:
    """Itens seguros primeiro (maior confiança antes), os de conferência depois."""
    ordenados = sorted(itens, key=lambda i: (i["revisar"], -i["confianca"], i["nome"]))
    return ordenados[:maximo]
