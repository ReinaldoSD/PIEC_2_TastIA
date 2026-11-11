"""Depuração da percepção (opcional).

Ligue com a variável de ambiente  TASTIA_DEBUG_PERCEPCAO=1  e, a cada foto analisada, o
sistema salva em  <pasta temporária>/tastia_percepcao_debug/<data-hora>/ :
  - 00_caixas.jpg     a foto com as caixas desenhadas e o que o CLIP decidiu em cada uma
  - recorte_NN.jpg    cada recorte enviado ao CLIP
  - blocos_NN.jpg     cada bloco da varredura complementar
  - resumo.txt        lista de caixas, labels do Florence, top-3 e itens finais
Desligado (padrão), não faz nada e não custa tempo. Nunca derruba o pipeline.
"""

import os
import tempfile
import time
from typing import Dict, List, Optional

from PIL import Image, ImageDraw

from percepcao.parametros import DEPURACAO


def ativo() -> bool:
    return bool(DEPURACAO)


def _nova_pasta() -> str:
    base = os.path.join(tempfile.gettempdir(), "tastia_percepcao_debug")
    pasta = os.path.join(base, time.strftime("%Y%m%d-%H%M%S") + f"-{int(time.time() * 1000) % 1000:03d}")
    os.makedirs(pasta, exist_ok=True)
    return pasta


def salvar_execucao(
    imagem: Image.Image,
    objetos: List[Dict],
    recortes: List[Image.Image],
    classificados: List[Optional[Dict]],
    blocos: List[Image.Image],
    classificados_blocos: List[Optional[Dict]],
    itens_finais: List[Dict],
) -> Optional[str]:
    """Salva os arquivos de depuração e devolve a pasta (ou None se desligado/falhou)."""
    if not ativo():
        return None
    try:
        pasta = _nova_pasta()

        desenho = imagem.copy()
        pincel = ImageDraw.Draw(desenho)
        linhas = ["== Caixas do detector =="]
        for i, (obj, cls) in enumerate(zip(objetos, classificados), start=1):
            x1, y1, x2, y2 = obj["bbox"]
            if cls:
                marca = f"{cls['nome']} {cls['confianca']:.2f}" + (" ?" if cls["revisar"] else "")
                cor = "orange" if cls["revisar"] else "lime"
            else:
                marca, cor = "descartado", "red"
            pincel.rectangle([x1, y1, x2, y2], outline=cor, width=3)
            pincel.text((x1 + 4, y1 + 4), f"{i}:{marca}", fill=cor)
            alt = ", ".join(f"{a['nome']} {a['confianca']:.2f}" for a in (cls or {}).get("alternativas", []))
            linhas.append(f"{i:02d} bbox={obj['bbox']} florence='{obj.get('label_florence')}' -> {marca} | alt: {alt}")
            if i - 1 < len(recortes):
                recortes[i - 1].save(os.path.join(pasta, f"recorte_{i:02d}.jpg"), quality=90)
        desenho.save(os.path.join(pasta, "00_caixas.jpg"), quality=90)

        linhas.append("")
        linhas.append("== Blocos (varredura complementar) ==")
        for i, (bloco, cls) in enumerate(zip(blocos, classificados_blocos), start=1):
            bloco.save(os.path.join(pasta, f"blocos_{i:02d}.jpg"), quality=90)
            resultado = f"{cls['nome']} {cls['confianca']:.2f}" if cls else "descartado"
            linhas.append(f"bloco {i:02d} -> {resultado}")

        linhas.append("")
        linhas.append("== Itens finais ==")
        for item in itens_finais:
            linhas.append(
                f"{item['nome']} | {item['quantidade']} | conf={item['confianca']:.2f} | "
                f"revisar={item['revisar']} | origem={item['origem']}"
            )

        with open(os.path.join(pasta, "resumo.txt"), "w", encoding="utf-8") as arq:
            arq.write("\n".join(linhas))
        print(f"-> [Percepção] Depuração salva em: {pasta}")
        return pasta
    except Exception as erro:  # a depuração nunca pode derrubar a detecção
        print(f"-> [Percepção] Aviso: falha ao salvar a depuração: {erro}")
        return None
