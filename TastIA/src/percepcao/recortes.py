"""Funções de geometria e recorte da Percepção (sem modelos, sem torch).

Caixas ("bbox") são sempre [x1, y1, x2, y2] em pixels.
"""

from typing import List, Sequence, Tuple

from PIL import Image

from percepcao.parametros import (
    BLOCOS_GRADE,
    BLOCOS_SOBREPOSICAO,
    LADO_DETECCAO,
    MARGEM_RECORTE,
)

# Cor média do CLIP: preenchimento neutro ao quadrar recortes.
_COR_NEUTRA = (122, 116, 104)

BBox = Sequence[float]


def area(bbox: BBox) -> float:
    return max(0.0, bbox[2] - bbox[0]) * max(0.0, bbox[3] - bbox[1])


def _intersecao(a: BBox, b: BBox) -> float:
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)


def iou(a: BBox, b: BBox) -> float:
    """Interseção sobre união (0 a 1)."""
    inter = _intersecao(a, b)
    uniao = area(a) + area(b) - inter
    return inter / uniao if uniao > 0 else 0.0


def contencao(menor: BBox, maior: BBox) -> float:
    """Fração da caixa `menor` que está dentro da caixa `maior` (0 a 1)."""
    a = area(menor)
    return _intersecao(menor, maior) / a if a > 0 else 0.0


def limitar_bbox(bbox: BBox, largura: int, altura: int) -> List[int]:
    """Mantém a caixa dentro da imagem, garantindo ao menos 1 px de largura e altura."""
    x1 = int(max(0, min(bbox[0], largura - 1)))
    y1 = int(max(0, min(bbox[1], altura - 1)))
    x2 = int(max(x1 + 1, min(bbox[2], largura)))
    y2 = int(max(y1 + 1, min(bbox[3], altura)))
    return [x1, y1, x2, y2]


def escalar_bbox(bbox: BBox, fator_x: float, fator_y: float) -> List[float]:
    """Converte uma caixa entre imagens de tamanhos diferentes."""
    return [bbox[0] * fator_x, bbox[1] * fator_y, bbox[2] * fator_x, bbox[3] * fator_y]


def reduzir_para_deteccao(
    imagem: Image.Image, lado_max: int = LADO_DETECCAO
) -> Tuple[Image.Image, float, float]:
    """Cópia menor para o detector. Devolve (imagem, fator_x, fator_y) para voltar à escala original."""
    largura, altura = imagem.size
    if max(largura, altura) <= lado_max:
        return imagem, 1.0, 1.0
    copia = imagem.copy()
    copia.thumbnail((lado_max, lado_max), Image.Resampling.LANCZOS)
    return copia, largura / copia.width, altura / copia.height


def recortar_com_margem(
    imagem: Image.Image, bbox: BBox, margem: float = MARGEM_RECORTE
) -> Image.Image:
    """Recorta o objeto com uma folga ao redor (contexto ajuda o CLIP)."""
    largura, altura = imagem.size
    folga_x = (bbox[2] - bbox[0]) * margem
    folga_y = (bbox[3] - bbox[1]) * margem
    caixa = limitar_bbox(
        [bbox[0] - folga_x, bbox[1] - folga_y, bbox[2] + folga_x, bbox[3] + folga_y],
        largura,
        altura,
    )
    return imagem.crop(tuple(caixa))


def tornar_quadrado(imagem: Image.Image) -> Image.Image:
    """Completa o recorte com cor neutra até ficar quadrado.

    O CLIP corta o centro da imagem para deixá-la quadrada; sem isto, objetos compridos
    (banana, garrafa, foto inteira de 4:3) perderiam as pontas antes de serem classificados.
    """
    largura, altura = imagem.size
    if largura == altura:
        return imagem
    lado = max(largura, altura)
    tela = Image.new("RGB", (lado, lado), _COR_NEUTRA)
    tela.paste(imagem, ((lado - largura) // 2, (lado - altura) // 2))
    return tela


def gerar_blocos(
    largura: int,
    altura: int,
    grade: int = BLOCOS_GRADE,
    sobreposicao: float = BLOCOS_SOBREPOSICAO,
) -> List[List[int]]:
    """Divide a foto em `grade` x `grade` blocos com sobreposição.

    Não inclui a foto inteira (o pipeline a acrescenta). Imagens pequenas devolvem lista vazia.
    """
    if grade < 2 or largura < 100 or altura < 100:
        return []
    sobreposicao = min(max(sobreposicao, 0.0), 0.5)
    fator = grade - (grade - 1) * sobreposicao
    tam_x, tam_y = largura / fator, altura / fator
    passo_x, passo_y = tam_x * (1 - sobreposicao), tam_y * (1 - sobreposicao)

    blocos: List[List[int]] = []
    for linha in range(grade):
        for coluna in range(grade):
            x1 = coluna * passo_x
            y1 = linha * passo_y
            blocos.append(limitar_bbox([x1, y1, x1 + tam_x, y1 + tam_y], largura, altura))
    return blocos
