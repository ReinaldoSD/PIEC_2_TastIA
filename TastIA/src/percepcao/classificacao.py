"""Serviço de Classificação (CLIP): identifica qual ingrediente é cada recorte.

Melhorias em relação à versão anterior:
  - os textos do catálogo são codificados UMA vez, ao carregar o modelo (média de 3 a 5
    frases por ingrediente + vários "negativos" que significam "isto não é ingrediente");
  - cada recorte é completado até ficar quadrado (o CLIP não corta mais as pontas);
  - a decisão usa probabilidade mínima, margem entre o 1º e o 2º colocado (maior quando
    são ingredientes parecidos) e comparação com os negativos;
  - devolve alternativas (top-3) e a marca "revisar" para o usuário conferir.

A decisão (`decidir_classificacao`) é uma função pura em numpy, testável sem baixar modelos.
"""

import os
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
from PIL import Image

from config import Config, MODELS_DIR
from percepcao.catalogo import (
    CATALOGO,
    NEGATIVOS,
    NOMES_RECONHECIVEIS,
    categoria_de,
    par_confundivel,
)
from percepcao.parametros import (
    CLF_ALT_MAX,
    CLF_ALT_PROB_MIN,
    CLF_CONF_REVISAR,
    CLF_MARGEM,
    CLF_MARGEM_CONFUNDIVEL,
    CLF_PROB_MIN,
    CLF_TAMANHO_LOTE,
    PLANO_B_PROB_MIN,
    PLANO_B_TOP_K,
)
from percepcao.recortes import tornar_quadrado


def decidir_classificacao(
    probs_ingredientes: Sequence[float],
    prob_negativos: float,
    nomes: Sequence[str],
    prob_min: Optional[float] = None,
) -> Optional[Dict]:
    """Decide o que fazer com UM recorte, a partir das probabilidades do CLIP.

    probs_ingredientes: probabilidade de cada ingrediente (mesma ordem de `nomes`).
    prob_negativos:     soma das probabilidades das frases "não é ingrediente".

    Devolve None (descartar) ou um dicionário com nome, categoria, confianca, revisar e
    alternativas. `revisar=True` quando a certeza é baixa ou há outro ingrediente parecido
    quase empatado: nesses casos o usuário deve conferir antes de salvar.
    """
    limiar = CLF_PROB_MIN if prob_min is None else prob_min
    probs = np.asarray(probs_ingredientes, dtype=float)
    if probs.size == 0:
        return None

    ordem = np.argsort(-probs)
    i1 = int(ordem[0])
    p1 = float(probs[i1])

    # Parece mais com "não é ingrediente" do que com o melhor ingrediente, ou é incerto demais.
    if p1 < limiar or prob_negativos >= p1:
        return None

    p2 = float(probs[ordem[1]]) if probs.size > 1 else 0.0
    i2 = int(ordem[1]) if probs.size > 1 else None

    margem_exigida = CLF_MARGEM
    if i2 is not None and par_confundivel(nomes[i1], nomes[i2]):
        margem_exigida = CLF_MARGEM_CONFUNDIVEL

    margem_ok = (p1 - p2) >= margem_exigida
    revisar = (not margem_ok) or p1 < CLF_CONF_REVISAR

    alternativas: List[Dict] = []
    for j in ordem[1:1 + CLF_ALT_MAX]:
        pj = float(probs[int(j)])
        if pj < CLF_ALT_PROB_MIN:
            break
        alternativas.append({
            "nome": nomes[int(j)],
            "categoria": categoria_de(nomes[int(j)]),
            "confianca": round(pj, 3),
        })

    nome = nomes[i1]
    return {
        "nome": nome,
        "categoria": categoria_de(nome),
        "confianca": round(p1, 3),
        "revisar": bool(revisar),
        "alternativas": alternativas,
    }


class ServicoClassificacao:
    """Classifica recortes (ou a imagem toda, no Plano B) usando o CLIP."""

    def __init__(self, device: str = "cpu"):
        self.device = device
        self.modelo: Any = None
        self.processador: Any = None
        self.nomes_pt: List[str] = list(NOMES_RECONHECIVEIS)
        self._emb_texto: Any = None  # tensor [n_ingredientes + n_negativos, dim]

    # ------------------------------------------------------------------ #
    # Carregamento
    # ------------------------------------------------------------------ #
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
        self._preparar_texto()

    @staticmethod
    def _como_tensor(saida: Any, projecao: Any, dim_projecao: int) -> Any:
        """Aceita tanto um tensor quanto um objeto de saída (versões novas do transformers)."""
        import torch

        if torch.is_tensor(saida):
            return saida
        base = getattr(saida, "pooler_output", None)
        if base is None:
            base = saida[0]
        if base.shape[-1] != dim_projecao:
            base = projecao(base)
        return base

    def _codificar_texto(self, frases: List[str]) -> Any:
        import torch

        entradas = self.processador(text=frases, return_tensors="pt", padding=True).to(self.device)
        with torch.no_grad():
            saida = self.modelo.get_text_features(
                input_ids=entradas["input_ids"],
                attention_mask=entradas["attention_mask"],
            )
        emb = self._como_tensor(saida, self.modelo.text_projection, self.modelo.config.projection_dim)
        return emb / emb.norm(dim=-1, keepdim=True)

    def _codificar_imagens(self, imagens: List[Image.Image]) -> Any:
        import torch

        entradas = self.processador(images=imagens, return_tensors="pt").to(self.device)
        with torch.no_grad():
            saida = self.modelo.get_image_features(pixel_values=entradas["pixel_values"])
        emb = self._como_tensor(saida, self.modelo.visual_projection, self.modelo.config.projection_dim)
        return emb / emb.norm(dim=-1, keepdim=True)

    def _preparar_texto(self) -> None:
        """Codifica os textos do catálogo uma única vez (média das frases de cada ingrediente)."""
        import torch

        frases: List[str] = []
        faixas: List[tuple] = []
        for nome in self.nomes_pt:
            prompts = list(CATALOGO[nome]["prompts"])
            faixas.append((len(frases), len(frases) + len(prompts)))
            frases.extend(prompts)
        inicio_neg = len(frases)
        frases.extend(NEGATIVOS)

        emb = self._codificar_texto(frases)

        classes = []
        for ini, fim in faixas:
            media = emb[ini:fim].mean(dim=0)
            classes.append(media / media.norm())
        negativos = emb[inicio_neg:]
        self._emb_texto = torch.cat([torch.stack(classes), negativos], dim=0).to(self.device)

    # ------------------------------------------------------------------ #
    # Inferência
    # ------------------------------------------------------------------ #
    def _probabilidades(self, imagens: List[Image.Image]) -> np.ndarray:
        """Matriz [n_imagens, n_ingredientes + n_negativos] de probabilidades (softmax)."""
        import torch

        blocos = []
        escala = self.modelo.logit_scale.exp()
        for i in range(0, len(imagens), max(1, CLF_TAMANHO_LOTE)):
            lote = imagens[i:i + CLF_TAMANHO_LOTE]
            emb_img = self._codificar_imagens(lote)
            with torch.no_grad():
                logits = escala * emb_img @ self._emb_texto.T
                probs = logits.softmax(dim=-1)
            blocos.append(probs.float().cpu().numpy())
        return np.concatenate(blocos, axis=0)

    def classificar_recortes(
        self, recortes: List[Image.Image], limiar: Optional[float] = None
    ) -> List[Optional[Dict]]:
        """Classifica todos os recortes (em lotes). None = descartado (fundo, incerto ou não-comida)."""
        if not recortes:
            return []
        if self.modelo is None or self.processador is None or self._emb_texto is None:
            self.carregar()

        assert self.modelo is not None and self.processador is not None

        quadrados = [tornar_quadrado(r.convert("RGB")) for r in recortes]
        probs = self._probabilidades(quadrados)

        n = len(self.nomes_pt)
        return [
            decidir_classificacao(linha[:n], float(linha[n:].sum()), self.nomes_pt, prob_min=limiar)
            for linha in probs
        ]

    def classificar_plano_b(
        self,
        imagem: Image.Image,
        top_k: int = PLANO_B_TOP_K,
        limiar: Optional[float] = None,
    ) -> List[Dict]:
        """PLANO B: quando nada foi achado, analisa a foto inteira e os 4 quadrantes.

        Os itens voltam sempre marcados para revisão (evidência fraca).
        """
        limiar = PLANO_B_PROB_MIN if limiar is None else limiar
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
                    "selecionado": False,
                    "revisar": True,
                    "alternativas": item["alternativas"],
                    "origem": "plano_b",
                }

        lista_ordenada = sorted(achados.values(), key=lambda x: -x["confianca"])
        return lista_ordenada[:top_k]
