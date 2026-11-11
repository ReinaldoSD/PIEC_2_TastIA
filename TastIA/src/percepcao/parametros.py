"""Parâmetros da Percepção Computacional do TastIA.

Todos os números que influenciam a precisão ficam AQUI, num só lugar.
Cada valor pode ser sobrescrito por variável de ambiente (prefixo TASTIA_), por exemplo:

    TASTIA_CLF_PROB_MIN=0.40
    TASTIA_BLOCOS_GRADE=3

Os valores padrão são pontos de partida: ajuste-os com fotos reais da sua cozinha.
Regra prática: se aparecem ingredientes que não existem na foto, SUBA os limiares;
se faltam ingredientes que estavam na foto, DESÇA os limiares um pouco por vez.
"""

import os


def _ler_float(nome: str, padrao: float) -> float:
    try:
        return float(os.environ.get(f"TASTIA_{nome}", padrao))
    except (TypeError, ValueError):
        return float(padrao)


def _ler_int(nome: str, padrao: int) -> int:
    try:
        return int(float(os.environ.get(f"TASTIA_{nome}", padrao)))
    except (TypeError, ValueError):
        return int(padrao)


def _ler_bool(nome: str, padrao: bool = False) -> bool:
    valor = os.environ.get(f"TASTIA_{nome}")
    if valor is None:
        return padrao
    return valor.strip().lower() in {"1", "true", "sim", "yes", "on"}


# --------------------------------------------------------------------------- #
# Imagem
# --------------------------------------------------------------------------- #
# Maior lado da foto guardada para recortes (era 1024). O Florence-2 reduz a foto
# para 768x768 de qualquer forma; a resolução maior só ajuda os recortes do CLIP.
LADO_MAX_IMAGEM = _ler_int("LADO_MAX_IMAGEM", 1600)
# Lado da cópia enviada ao detector (mais leve; as caixas voltam à escala original).
LADO_DETECCAO = _ler_int("LADO_DETECCAO", 1024)

# --------------------------------------------------------------------------- #
# Detecção (Florence-2)
# --------------------------------------------------------------------------- #
DET_MAX_NEW_TOKENS = _ler_int("DET_MAX_NEW_TOKENS", 512)
DET_NUM_BEAMS = _ler_int("DET_NUM_BEAMS", 3)
DET_LADO_MIN_PX = _ler_int("DET_LADO_MIN_PX", 12)           # caixa com lado menor que isso é ruído
DET_AREA_MIN_REL = _ler_float("DET_AREA_MIN_REL", 0.004)    # < 0,4% da foto: descarta
DET_AREA_MAX_REL = _ler_float("DET_AREA_MAX_REL", 0.60)     # > 60% da foto: prateleira/tigela/cena

# --------------------------------------------------------------------------- #
# Caixas: NMS, duplicatas e recortes
# --------------------------------------------------------------------------- #
NMS_IOU = _ler_float("NMS_IOU", 0.50)                 # caixas com IoU >= isto são o mesmo objeto
DEDUP_IOU = _ler_float("DEDUP_IOU", 0.45)             # após classificar: mesmo nome + IoU >= isto = duplicata
GRUPO_CONTENCAO = _ler_float("GRUPO_CONTENCAO", 0.85) # fração de uma caixa dentro de outra para ser "filha"
GRUPO_MIN_FILHOS = _ler_int("GRUPO_MIN_FILHOS", 2)    # caixa que engloba N+ caixas do mesmo item é "grupo"
MARGEM_RECORTE = _ler_float("MARGEM_RECORTE", 0.10)   # folga ao redor do objeto (10%)

# --------------------------------------------------------------------------- #
# Classificação (CLIP)
# --------------------------------------------------------------------------- #
CLF_PROB_MIN = _ler_float("CLF_PROB_MIN", 0.35)                    # abaixo disso: descarta
CLF_MARGEM = _ler_float("CLF_MARGEM", 0.10)                        # 1º - 2º colocado mínimo
CLF_MARGEM_CONFUNDIVEL = _ler_float("CLF_MARGEM_CONFUNDIVEL", 0.15)  # idem quando o 2º é parecido
CLF_CONF_REVISAR = _ler_float("CLF_CONF_REVISAR", 0.60)            # abaixo disso: "confira este item"
CLF_ALT_PROB_MIN = _ler_float("CLF_ALT_PROB_MIN", 0.03)            # alternativa só aparece se >= isto
CLF_ALT_MAX = _ler_int("CLF_ALT_MAX", 3)
CLF_TAMANHO_LOTE = _ler_int("CLF_TAMANHO_LOTE", 16)                # recortes por passada (controla RAM)

# --------------------------------------------------------------------------- #
# Varredura em blocos e Plano B
# --------------------------------------------------------------------------- #
BLOCOS_GRADE = _ler_int("BLOCOS_GRADE", 2)                     # 2 => 2x2 blocos (+ a foto inteira)
BLOCOS_SOBREPOSICAO = _ler_float("BLOCOS_SOBREPOSICAO", 0.25)
BLOCOS_PROB_MIN = _ler_float("BLOCOS_PROB_MIN", 0.50)          # mais exigente que o detector
PLANO_B_PROB_MIN = _ler_float("PLANO_B_PROB_MIN", 0.30)
PLANO_B_TOP_K = _ler_int("PLANO_B_TOP_K", 3)

# --------------------------------------------------------------------------- #
# Saída
# --------------------------------------------------------------------------- #
MAX_ITENS = _ler_int("MAX_ITENS", 40)

# Depuração: salva caixas e recortes em uma pasta temporária (TASTIA_DEBUG_PERCEPCAO=1).
DEPURACAO = _ler_bool("DEBUG_PERCEPCAO", False)
