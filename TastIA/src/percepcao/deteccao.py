"""Serviço de Detecção (Florence-2): localiza onde estão os objetos na foto."""

import os
from typing import Any, Dict, List

from PIL import Image

from config import Config, MODELS_DIR
from percepcao.parametros import (
    DET_AREA_MIN_REL,
    DET_LADO_MIN_PX,
    DET_MAX_NEW_TOKENS,
    DET_NUM_BEAMS,
)


class ServicoDeteccao:
    """Localiza objetos na imagem com o Florence-2 (tarefa <OD>)."""

    def __init__(self, device: str = "cpu"):
        self.device = device
        self.modelo: Any = None
        self.processador: Any = None

    def carregar(self) -> None:
        from transformers import AutoProcessor, Florence2ForConditionalGeneration

        pasta_local = os.path.join(MODELS_DIR, "deteccao_objetos")
        origem = (
            pasta_local
            if os.path.exists(os.path.join(pasta_local, "config.json"))
            else Config.MODELOS["deteccao_objetos"]
        )
        print(f"-> [Percepção] Carregando Florence-2 de: {origem}...")
        modelo: Any = Florence2ForConditionalGeneration.from_pretrained(origem)
        self.modelo = modelo.to(self.device).eval()
        self.processador = AutoProcessor.from_pretrained(origem)

    def detectar(self, imagem: Image.Image) -> List[Dict]:
        """Devolve [{"bbox": [x1, y1, x2, y2], "label_florence": str}] na escala da imagem recebida.

        Já descarta ruído: caixas minúsculas em pixels ou em proporção da foto.
        """
        import torch

        if self.modelo is None or self.processador is None:
            self.carregar()

        assert self.modelo is not None and self.processador is not None

        tarefa = "<OD>"
        entradas = self.processador(text=tarefa, images=imagem, return_tensors="pt").to(self.device)

        with torch.no_grad():
            ids_gerados = self.modelo.generate(
                **entradas,
                max_new_tokens=DET_MAX_NEW_TOKENS,
                num_beams=DET_NUM_BEAMS,
            )

        texto = self.processador.batch_decode(ids_gerados, skip_special_tokens=False)[0]
        resultado = self.processador.post_process_generation(
            texto, task=tarefa, image_size=(imagem.width, imagem.height)
        )

        bboxes = resultado.get(tarefa, {}).get("bboxes", [])
        labels = resultado.get(tarefa, {}).get("labels", [])

        area_foto = float(imagem.width * imagem.height)
        objetos: List[Dict] = []
        for bbox, label in zip(bboxes, labels):
            x1, y1, x2, y2 = (int(v) for v in bbox)
            largura, altura = x2 - x1, y2 - y1
            if largura < DET_LADO_MIN_PX or altura < DET_LADO_MIN_PX:
                continue
            if (largura * altura) / area_foto < DET_AREA_MIN_REL:
                continue
            objetos.append({"bbox": [x1, y1, x2, y2], "label_florence": str(label)})
        return objetos
