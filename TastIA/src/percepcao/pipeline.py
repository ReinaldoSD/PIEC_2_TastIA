"""Módulo de Percepção Computacional do TastIA: orquestrador do pipeline.

Fluxo (foto -> lista de ingredientes):
  1. detecção (Florence-2) numa cópia reduzida; as caixas voltam à foto original;
  2. filtros: caixas gigantes/minúsculas e labels que não são comida; NMS;
  3. recorte de cada objeto (com margem) na foto em resolução maior;
  4. classificação (CLIP) com margem, negativos e alternativas;
  5. remoção de duplicatas e contagem de unidades;
  6. varredura complementar em blocos (foto inteira + blocos com sobreposição) para
     recuperar o que o detector perdeu, com limiar mais exigente;
  7. Plano B (foto inteira + quadrantes) se ainda não houver nenhum item;
  8. resposta com `selecionado`, `revisar`, `alternativas` e `origem` em cada item.

Os detalhes ficam nos módulos: parametros, catalogo, deteccao, classificacao, recortes,
pos_processamento e depuracao. Este arquivo só costura as etapas.
"""

import threading
import time
from typing import Any, Dict, List, Optional

from PIL import Image

from percepcao import depuracao
from percepcao.catalogo import CATALOGO_INGREDIENTES  # reexportado (rotas e testes importam daqui)
from percepcao.classificacao import ServicoClassificacao
from percepcao.deteccao import ServicoDeteccao
from percepcao.parametros import BLOCOS_PROB_MIN
from percepcao.pos_processamento import (
    agregar_itens,
    aplicar_nms,
    deduplicar_classificados,
    filtrar_caixas,
    mesclar_origens,
    ordenar_e_limitar,
)
from percepcao.recortes import (
    escalar_bbox,
    gerar_blocos,
    recortar_com_margem,
    reduzir_para_deteccao,
)

__all__ = [
    "CATALOGO_INGREDIENTES",
    "ServicoDeteccao",
    "ServicoClassificacao",
    "PipelinePercepcao",
    "obter_pipeline",
]

AVISO_PLANO_B = (
    "Não foi possível delimitar objetos com segurança; usamos a identificação global da imagem "
    "(Plano B). Confira os itens antes de salvar."
)
AVISO_VAZIO = "Não conseguimos identificar alimentos claros na foto. Você pode adicioná-los manualmente abaixo."
AVISO_REVISAR = (
    "Os itens com o selo \"Confira este item\" tiveram baixa certeza e vieram desmarcados: "
    "corrija ou confirme antes de salvar."
)


class PipelinePercepcao:
    """Orquestra Detecção -> Filtros -> Classificação -> Blocos -> Plano B -> Agrupamento."""

    def __init__(
        self,
        detector: Optional[Any] = None,
        classificador: Optional[Any] = None,
        device: Optional[str] = None,
    ):
        # `detector` e `classificador` podem ser injetados (ex.: testes com modelos falsos).
        if device is None and (detector is None or classificador is None):
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = device or "cpu"
        self.detector = detector if detector is not None else ServicoDeteccao(self.device)
        self.classificador = classificador if classificador is not None else ServicoClassificacao(self.device)
        self._trava = threading.Lock()

    def aquecer(self) -> None:
        """Carrega os modelos antes da primeira foto (a primeira análise deixa de demorar)."""
        with self._trava:
            for servico in (self.detector, self.classificador):
                if hasattr(servico, "carregar") and getattr(servico, "modelo", None) is None:
                    servico.carregar()

    def executar(self, imagem: Image.Image) -> Dict:
        with self._trava:
            t0 = time.perf_counter()
            imagem_rgb = imagem.convert("RGB")
            largura, altura = imagem_rgb.size

            # 1) Detecção numa cópia reduzida; caixas convertidas para a foto original.
            copia_det, fator_x, fator_y = reduzir_para_deteccao(imagem_rgb)
            objetos_brutos = self.detector.detectar(copia_det)
            objetos = [
                {
                    "bbox": escalar_bbox(obj["bbox"], fator_x, fator_y),
                    "label_florence": obj.get("label_florence", ""),
                }
                for obj in objetos_brutos
            ]

            # 2) Filtros e NMS.
            objetos = aplicar_nms(filtrar_caixas(objetos, largura, altura))

            # 3) e 4) Recortes com margem + classificação.
            recortes = [recortar_com_margem(imagem_rgb, obj["bbox"]) for obj in objetos]
            classificados = self.classificador.classificar_recortes(recortes)

            # 5) Duplicatas e contagem.
            candidatos: List[Dict] = [
                {**cls, "bbox": obj["bbox"]}
                for obj, cls in zip(objetos, classificados)
                if cls is not None
            ]
            itens_detector = agregar_itens(
                deduplicar_classificados(candidatos), origem="detector", contar=True
            )

            # 6) Varredura complementar: foto inteira + blocos com sobreposição.
            caixas_blocos = [[0, 0, largura, altura]] + gerar_blocos(largura, altura)
            imagens_blocos = [imagem_rgb.crop(tuple(c)) for c in caixas_blocos]
            classificados_blocos = self.classificador.classificar_recortes(
                imagens_blocos, limiar=BLOCOS_PROB_MIN
            )
            candidatos_blocos: List[Dict] = [
                {**cls, "bbox": caixa}
                for caixa, cls in zip(caixas_blocos, classificados_blocos)
                if cls is not None
            ]
            itens_blocos = agregar_itens(candidatos_blocos, origem="blocos", contar=False)

            itens_finais = mesclar_origens(itens_detector, itens_blocos)

            # 7) Plano B: só quando nada foi encontrado.
            usou_plano_b = False
            if not itens_finais:
                usou_plano_b = True
                itens_finais = self.classificador.classificar_plano_b(imagem_rgb)

            itens_finais = ordenar_e_limitar(itens_finais)

            depuracao.salvar_execucao(
                imagem_rgb, objetos, recortes, classificados,
                imagens_blocos, classificados_blocos, itens_finais,
            )

            tempo_total = round(time.perf_counter() - t0, 2)

            if not itens_finais:
                aviso: Optional[str] = AVISO_VAZIO
            elif usou_plano_b:
                aviso = AVISO_PLANO_B
            elif any(i["revisar"] for i in itens_finais):
                aviso = AVISO_REVISAR
            else:
                aviso = None

            return {
                "ingredientes": itens_finais,
                "total_detectado": len(itens_finais),
                "usou_plano_b": usou_plano_b,
                "recortes_brutos": len(objetos_brutos),
                "recortes_validos": len(objetos),
                "tempo_s": tempo_total,
                "aviso": aviso,
            }


_pipeline_unico: Optional[PipelinePercepcao] = None
_trava_singleton = threading.Lock()


def obter_pipeline() -> PipelinePercepcao:
    global _pipeline_unico
    with _trava_singleton:
        if _pipeline_unico is None:
            _pipeline_unico = PipelinePercepcao()
    return _pipeline_unico
