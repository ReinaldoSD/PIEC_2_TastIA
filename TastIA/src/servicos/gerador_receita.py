"""Módulo de carregamento e execução do modelo de geração de receitas do TastIA.

Aplica Quantização Dinâmica PyTorch em 8-bits (int8) para otimização de memória RAM e CPU[cite: 17].
"""
import os
import re
import threading
import time
from dataclasses import asdict, dataclass
from typing import Iterator, List, Optional

from config import MODELS_DIR

REPO_ORIGINAL = "HuggingFaceTB/SmolLM3-3B"
PASTA_ORIGINAL = os.path.join(MODELS_DIR, "geracao_receita")

PROMPT_SISTEMA = (
    "/no_think\n"
    "Você é o TastIA, um assistente de culinária. Responda sempre em português do Brasil. "
    "Crie UMA receita usando principalmente os ingredientes que o usuário possui "
    "(pode assumir sal, água, óleo e temperos básicos). "
    "Formato: título; tempo de preparo; porções; seção 'Ingredientes' em lista; "
    "seção 'Modo de preparo' em passos numerados. Seja objetivo e não repita informações."
)

PREENCHER_THINK_VAZIO = True
TEMPERATURA = 0.6
TOP_P = 0.95
REPEAT_PENALTY = 1.1


def montar_prompt(ingredientes: List[str], pedido: str) -> str:
    lista = ", ".join(ingredientes)
    usuario = f"Ingredientes disponíveis: {lista}.\nPedido: {pedido}"
    prompt = (
        f"<|im_start|>system\n{PROMPT_SISTEMA}<|im_end|>\n"
        f"<|im_start|>user\n{usuario}<|im_end|>\n"
        f"<|im_start|>assistant\n"
    )
    if PREENCHER_THINK_VAZIO:
        prompt += "<think>\n\n</think>\n"
    return prompt


def limpar_saida(texto: str) -> str:
    texto = re.sub(r"<think>.*?</think>", "", texto, flags=re.DOTALL)
    return texto.replace("<|im_end|>", "").strip()


def threads_padrao() -> int:
    env = os.environ.get("RECEITA_THREADS")
    if env and env.isdigit():
        return int(env)
    try:
        import psutil
        fisicos = psutil.cpu_count(logical=False)
        if fisicos:
            return fisicos
    except ImportError:
        pass
    return max(1, (os.cpu_count() or 2) // 2)


@dataclass
class ResultadoGeracao:
    texto: str
    tokens: int
    tempo_total_s: float
    ttft_s: float
    tokens_por_s: float
    backend: str

    def como_dict(self) -> dict:
        return asdict(self)


class GeradorReceita:
    nome = "base"

    def __init__(self):
        self._trava = threading.Lock()

    def carregar(self) -> None:
        raise NotImplementedError

    def gerar_stream(self, prompt: str, max_tokens: int) -> Iterator[str]:
        raise NotImplementedError

    def contar_tokens(self, texto: str, n_pedacos: int) -> int:
        return n_pedacos

    def gerar(self, ingredientes: List[str], pedido: str, max_tokens: int = 400) -> ResultadoGeracao:
        return self.gerar_de_prompt(montar_prompt(ingredientes, pedido), max_tokens)

    def gerar_de_prompt(self, prompt: str, max_tokens: int = 400) -> ResultadoGeracao:
        with self._trava:
            inicio = time.perf_counter()
            ttft = None
            partes: List[str] = []
            n_pedacos = 0
            for pedaco in self.gerar_stream(prompt, max_tokens):
                if not pedaco:
                    continue
                if ttft is None:
                    ttft = time.perf_counter() - inicio
                partes.append(pedaco)
                n_pedacos += 1
            total = time.perf_counter() - inicio

        bruto = "".join(partes)
        n_tokens = self.contar_tokens(bruto, n_pedacos)
        ttft = ttft if ttft is not None else total
        tempo_decodificando = max(total - ttft, 1e-9)
        tps = (n_tokens - 1) / tempo_decodificando if n_tokens > 1 else 0.0
        return ResultadoGeracao(
            texto=limpar_saida(bruto),
            tokens=n_tokens,
            tempo_total_s=total,
            ttft_s=ttft,
            tokens_por_s=tps,
            backend=self.nome,
        )


class GeradorTransformersQuantizado(GeradorReceita):
    """Backend Hugging Face Transformers com Quantização Dinâmica PyTorch em 8 bits para CPU[cite: 17]."""

    def __init__(self, n_threads: Optional[int] = None):
        super().__init__()
        self.n_threads = n_threads or threads_padrao()
        self.modelo = None
        self.tokenizer = None
        self.nome = "transformers:pytorch_int8_dinamico"

    def carregar(self) -> None:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        torch.set_num_threads(self.n_threads)
        origem = PASTA_ORIGINAL if os.path.exists(os.path.join(PASTA_ORIGINAL, "config.json")) else REPO_ORIGINAL

        print("-> [TastIA] Carregando tokenizer do modelo...")
        self.tokenizer = AutoTokenizer.from_pretrained(origem)

        print("-> [TastIA] Carregando modelo base e aplicando quantização dinâmica PyTorch (int8)...")
        modelo_base = AutoModelForCausalLM.from_pretrained(
            origem,
            torch_dtype=torch.float32,
            low_cpu_mem_usage=True
        )

        # Aplicação explícita da Quantização Dinâmica PyTorch nas camadas lineares (qint8)[cite: 17]
        self.modelo = torch.ao.quantization.quantize_dynamic(
            modelo_base,
            {torch.nn.Linear},
            dtype=torch.qint8
        )
        self.modelo.eval()
        print("-> [TastIA] Modelo quantizado em 8-bits carregado e pronto para execução em CPU!")

    def contar_tokens(self, texto: str, n_pedacos: int) -> int:
        return len(self.tokenizer(texto, add_special_tokens=False)["input_ids"])

    def gerar_stream(self, prompt: str, max_tokens: int) -> Iterator[str]:
        from transformers import TextIteratorStreamer

        entradas = self.tokenizer(prompt, return_tensors="pt", add_special_tokens=False)
        device = next(self.modelo.parameters()).device
        entradas = {k: v.to(device) for k, v in entradas.items()}

        streamer = TextIteratorStreamer(self.tokenizer, skip_prompt=True, skip_special_tokens=True)
        kwargs = dict(
            **entradas,
            max_new_tokens=max_tokens,
            do_sample=True,
            temperature=TEMPERATURA,
            top_p=TOP_P,
            repetition_penalty=REPEAT_PENALTY,
            streamer=streamer,
            pad_token_id=self.tokenizer.eos_token_id,
        )
        thread = threading.Thread(target=self.modelo.generate, kwargs=kwargs, daemon=True)
        thread.start()
        for pedaco in streamer:
            yield pedaco
        thread.join()


def criar_gerador() -> GeradorReceita:
    return GeradorTransformersQuantizado()


_gerador_unico: Optional[GeradorReceita] = None
_trava_singleton = threading.Lock()


def obter_gerador() -> GeradorReceita:
    global _gerador_unico
    with _trava_singleton:
        if _gerador_unico is None:
            g = criar_gerador()
            g.carregar()
            _gerador_unico = g
    return _gerador_unico