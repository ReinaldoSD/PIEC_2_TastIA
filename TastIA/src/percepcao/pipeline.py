"""Módulo de Percepção Computacional do TastIA:
Serviço de Detecção (Florence-2), Serviço de Classificação (CLIP) e Pipeline com Plano B.
"""

import os
import threading
import time
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple
from PIL import Image

from config import Config, MODELS_DIR

# Dicionário de ingredientes: Nome em PT -> (Prompt em EN para o CLIP, Categoria do Sistema)
CATALOGO_INGREDIENTES: Dict[str, Tuple[str, str]] = {
    "Tomate": ("a photo of a tomato", "Verduras e legumes"),
    "Cebola": ("a photo of an onion", "Verduras e legumes"),
    "Alho": ("a photo of garlic", "Verduras e legumes"),
    "Batata": ("a photo of a potato", "Verduras e legumes"),
    "Cenoura": ("a photo of a carrot", "Verduras e legumes"),
    "Pimentão": ("a photo of a bell pepper", "Verduras e legumes"),
    "Alface": ("a photo of lettuce or green leaves", "Verduras e legumes"),
    "Brócolis": ("a photo of broccoli", "Verduras e legumes"),
    "Banana": ("a photo of a banana", "Frutas"),
    "Maçã": ("a photo of an apple", "Frutas"),
    "Laranja": ("a photo of an orange", "Frutas"),
    "Limão": ("a photo of a lemon or lime", "Frutas"),
    "Ovo": ("a photo of an egg or egg carton", "Outros"),
    "Leite": ("a carton or bottle of milk", "Laticínios"),
    "Queijo": ("a photo of cheese", "Laticínios"),
    "Manteiga": ("a tub or block of butter or margarine", "Laticínios"),
    "Iogurte": ("a cup or bottle of yogurt", "Laticínios"),
    "Frango": ("raw or cooked chicken meat", "Carnes"),
    "Carne bovina": ("raw or cooked beef meat", "Carnes"),
    "Linguiça": ("a photo of sausage", "Carnes"),
    "Arroz": ("a bag or bowl of rice", "Grãos e cereais"),
    "Feijão": ("a bag or bowl of beans", "Grãos e cereais"),
    "Macarrão": ("a packet or bowl of pasta or spaghetti", "Grãos e cereais"),
    "Pão": ("a photo of bread", "Grãos e cereais"),
    "Biscoito": ("a packet of biscuits or cookies", "Outros"),
    "Molho de tomate": ("a jar, bottle or sachet of tomato sauce", "Outros"),
    "Refrigerante": ("a soda can or bottle", "Bebidas"),
    "Suco": ("a juice bottle or carton", "Bebidas"),
    "Água": ("a bottle of water", "Bebidas"),
}

PROMPT_FUNDO = "empty background, kitchen counter, shelf, appliance or empty plastic bag"


class ServicoDeteccao:
    """Serviço responsável por localizar objetos na imagem usando Florence-2."""

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
        import torch

        if self.modelo is None or self.processador is None:
            self.carregar()

        assert self.modelo is not None and self.processador is not None

        tarefa = "<OD>"
        entradas = self.processador(text=tarefa, images=imagem, return_tensors="pt").to(self.device)

        with torch.no_grad():
            ids_gerados = self.modelo.generate(
                **entradas,
                max_new_tokens=1024,
                num_beams=3,
            )

        texto = self.processador.batch_decode(ids_gerados, skip_special_tokens=False)[0]
        resultado = self.processador.post_process_generation(
            texto, task=tarefa, image_size=(imagem.width, imagem.height)
        )

        bboxes = resultado.get(tarefa, {}).get("bboxes", [])
        labels = resultado.get(tarefa, {}).get("labels", [])

        objetos = []
        for bbox, label in zip(bboxes, labels):
            x1, y1, x2, y2 = map(int, bbox)
            if (x2 - x1) >= 10 and (y2 - y1) >= 10:
                objetos.append({"bbox": [x1, y1, x2, y2], "label_florence": label})
        return objetos


class ServicoClassificacao:
    """Serviço responsável por classificar recortes (ou a imagem toda no Plano B) usando CLIP."""

    def __init__(self, device: str = "cpu"):
        self.device = device
        self.modelo: Any = None
        self.processador: Any = None
        self.nomes_pt = list(CATALOGO_INGREDIENTES.keys())
        self.prompts_en = [v[0] for v in CATALOGO_INGREDIENTES.values()] + [PROMPT_FUNDO]

    def carregar(self) -> None:
        from transformers import CLIPModel, CLIPProcessor

        pasta_local = os.path.join(MODELS_DIR, "classificacao_ingredientes")
        origem = (
            pasta_local
            if os.path.exists(os.path.join(pasta_local, "config.json"))
            else Config.MODELOS["classificacao_ingredientes"]
        )
        print(f"-> [Percepção] Carregando CLIP de: {origem}...")
        modelo: Any = CLIPModel.from_pretrained(origem)
        self.modelo = modelo.to(self.device).eval()
        self.processador = CLIPProcessor.from_pretrained(origem)

    def classificar_recortes(self, recortes: List[Image.Image], limiar: float = 0.18) -> List[Optional[Dict]]:
        """Classifica todos os recortes em um único Batch."""
        import torch

        if not recortes:
            return []
        if self.modelo is None or self.processador is None:
            self.carregar()

        assert self.modelo is not None and self.processador is not None

        entradas = self.processador(
            text=self.prompts_en, images=recortes, return_tensors="pt", padding=True
        ).to(self.device)

        with torch.no_grad():
            saidas = self.modelo(**entradas)
            probs = saidas.logits_per_image.softmax(dim=1).cpu().numpy()

        resultados: List[Optional[Dict]] = []
        idx_fundo = len(self.nomes_pt)

        for prob_recorte in probs:
            idx_max = int(prob_recorte.argmax())
            confianca = float(prob_recorte[idx_max])

            if idx_max == idx_fundo or confianca < limiar:
                resultados.append(None)
                continue

            nome = self.nomes_pt[idx_max]
            categoria = CATALOGO_INGREDIENTES[nome][1]
            resultados.append({
                "nome": nome,
                "categoria": categoria,
                "confianca": round(confianca, 3),
            })
        return resultados

    def classificar_plano_b(self, imagem: Image.Image, top_k: int = 3, limiar: float = 0.15) -> List[Dict]:
        """PLANO B: Quando o Florence-2 não detecta nada, analisa a foto inteira e os 4 quadrantes."""
        w, h = imagem.size
        regioes = [imagem]
        if w >= 100 and h >= 100:
            mx, my = w // 2, h // 2
            regioes.extend([
                imagem.crop((0, 0, mx, my)),
                imagem.crop((mx, 0, w, my)),
                imagem.crop((0, my, mx, h)),
                imagem.crop((mx, my, w, h)),
            ])

        classificacoes = self.classificar_recortes(regioes, limiar=limiar)
        achados: Dict[str, Dict] = {}

        for item in classificacoes:
            if not item:
                continue
            nome = item["nome"]
            if nome not in achados or item["confianca"] > achados[nome]["confianca"]:
                achados[nome] = {
                    "nome": nome,
                    "categoria": item["categoria"],
                    "quantidade": "1 unidade",
                    "confianca": item["confianca"],
                }

        lista_ordenada = sorted(achados.values(), key=lambda x: -x["confianca"])
        return lista_ordenada[:top_k]


class PipelinePercepcao:
    """Orquestra Detecção -> Classificação -> Plano B -> Agrupamento de Quantidades."""

    def __init__(self):
        import torch
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.detector = ServicoDeteccao(self.device)
        self.classificador = ServicoClassificacao(self.device)
        self._trava = threading.Lock()

    def executar(self, imagem: Image.Image) -> Dict:
        with self._trava:
            t0 = time.perf_counter()
            imagem_rgb = imagem.convert("RGB")

            objetos = self.detector.detectar(imagem_rgb)
            usou_plano_b = False
            itens_finais: List[Dict] = []

            if objetos:
                recortes = [
                    imagem_rgb.crop((obj["bbox"][0], obj["bbox"][1], obj["bbox"][2], obj["bbox"][3]))
                    for obj in objetos
                ]
                classificados = self.classificador.classificar_recortes(recortes)

                contagem: Counter = Counter()
                melhor_confianca: Dict[str, float] = {}
                categorias: Dict[str, str] = {}

                for item in classificados:
                    if item is None:
                        continue
                    nome = item["nome"]
                    contagem[nome] += 1
                    categorias[nome] = item["categoria"]
                    melhor_confianca[nome] = max(melhor_confianca.get(nome, 0.0), item["confianca"])

                for nome, qtd in contagem.items():
                    unid = "unidade" if qtd == 1 else "unidades"
                    itens_finais.append({
                        "nome": nome,
                        "categoria": categorias[nome],
                        "quantidade": f"{qtd} {unid}",
                        "confianca": melhor_confianca[nome],
                    })

            if not itens_finais:
                usou_plano_b = True
                itens_finais = self.classificador.classificar_plano_b(imagem_rgb)

            tempo_total = round(time.perf_counter() - t0, 2)

            return {
                "ingredientes": itens_finais,
                "total_detectado": len(itens_finais),
                "usou_plano_b": usou_plano_b,
                "recortes_brutos": len(objetos),
                "tempo_s": tempo_total,
                "aviso": (
                    "Nenhum objeto isolado foi delimitado; usamos a identificação global da imagem (Plano B). "
                    "Confira os itens antes de salvar."
                    if usou_plano_b and itens_finais
                    else (
                        "Não conseguimos identificar alimentos claros na foto. Você pode adicioná-los manualmente abaixo."
                        if not itens_finais
                        else None
                    )
                ),
            }


_pipeline_unico: Optional[PipelinePercepcao] = None
_trava_singleton = threading.Lock()


def obter_pipeline() -> PipelinePercepcao:
    global _pipeline_unico
    with _trava_singleton:
        if _pipeline_unico is None:
            _pipeline_unico = PipelinePercepcao()
    return _pipeline_unico