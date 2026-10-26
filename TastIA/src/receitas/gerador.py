"""Geração de receitas do TastIA: prompt -> modelo -> validação -> nova tentativa se preciso[cite: 14]."""
import time
from dataclasses import dataclass, field, asdict
from datetime import date
from typing import Dict, List, Optional, Sequence, Tuple, Union

from receitas.prompt import montar_prompt
from receitas.validador import ResultadoValidacao, normalizar_texto, validar_receita

MAX_TOKENS_PADRAO = 500
MAX_TENTATIVAS_PADRAO = 2


class InventarioVazioError(ValueError):
    """Não há ingredientes (válidos) para gerar a receita[cite: 14]."""


@dataclass
class ReceitaGerada:
    texto: str
    valida: bool
    fora_do_inventario: List[str]
    estrutura_ok: bool
    tentativas: int
    tempo_total_s: float
    backend: str
    vencidos_ignorados: List[str] = field(default_factory=list)

    def como_dict(self) -> dict:
        return asdict(self)


def preparar_inventario(
    itens: Sequence[Union[str, Dict]], hoje: Optional[date] = None
) -> Tuple[List[Dict], List[str]]:
    hoje = hoje or date.today()
    ativos: List[Dict] = []
    vencidos: List[str] = []
    vistos = set()
    for item in itens:
        d = {"nome": item} if isinstance(item, str) else dict(item)
        nome = str(d.get("nome", "")).strip()
        chave = normalizar_texto(nome)
        if not nome or chave in vistos:
            continue
        vistos.add(chave)
        d["nome"] = nome
        validade = d.get("validade")
        try:
            vencido = bool(validade) and date.fromisoformat(str(validade)[:10]) < hoje
        except ValueError:
            vencido = False
        (vencidos if vencido else ativos).append(nome if vencido else d)
    return ativos, vencidos


def _extrair_receita(texto: str) -> str:
    linhas = texto.strip().splitlines()
    for i, linha in enumerate(linhas):
        if linha.lstrip().startswith("#"):
            return "\n".join(linhas[i:]).strip()
    return texto.strip()


def _montar_correcao(val: ResultadoValidacao) -> str:
    partes = []
    if not val.estrutura_ok:
        partes.append(
            "sua versão anterior não seguiu o formato exigido; refaça com título, "
            "'## Ingredientes' e '## Modo de preparo'."
        )
    if val.problemas:
        partes.append(
            "sua versão anterior citou ingredientes que NÃO estão disponíveis: "
            + ", ".join(val.problemas)
            + ". Refaça a receita completa sem usar nem mencionar esses itens."
        )
    return " ".join(partes)


def _chave_qualidade(val: ResultadoValidacao) -> tuple:
    return (not val.estrutura_ok, len(val.problemas))


def gerar_receita(
    inventario: Sequence[Union[str, Dict]],
    pedido: str,
    tempo: Optional[str] = None,
    dificuldade: Optional[str] = None,
    restricoes: Optional[str] = None,
    evitar: Optional[str] = None,
    max_tentativas: int = MAX_TENTATIVAS_PADRAO,
    max_tokens: int = MAX_TOKENS_PADRAO,
    gerador=None,
    hoje: Optional[date] = None,
) -> ReceitaGerada:
    pedido = (pedido or "").strip()
    if not pedido:
        raise ValueError("Descreva o que você gostaria de preparar.")

    ativos, vencidos = preparar_inventario(inventario, hoje)
    if not ativos:
        if vencidos:
            raise InventarioVazioError("Todos os ingredientes informados estão vencidos.")
        raise InventarioVazioError("Nenhum ingrediente disponível. Cadastre itens no inventário.")

    if gerador is None:
        from servicos.gerador_receita import obter_gerador
        gerador = obter_gerador()

    nomes = [i["nome"] for i in ativos]
    inicio = time.perf_counter()
    melhor_texto, melhor_val, correcao, feitas = "", None, None, 0

    for _ in range(max(1, max_tentativas)):
        feitas += 1
        prompt = montar_prompt(ativos, pedido, tempo, dificuldade, restricoes, evitar, correcao, hoje)
        resultado = gerador.gerar_de_prompt(prompt, max_tokens)
        texto = _extrair_receita(resultado.texto)
        val = validar_receita(texto, nomes)
        if melhor_val is None or _chave_qualidade(val) < _chave_qualidade(melhor_val):
            melhor_texto, melhor_val = texto, val
        if val.valido:
            break
        correcao = _montar_correcao(val)

    return ReceitaGerada(
        texto=melhor_texto,
        valida=melhor_val.valido,
        fora_do_inventario=melhor_val.problemas,
        estrutura_ok=melhor_val.estrutura_ok,
        tentativas=feitas,
        tempo_total_s=round(time.perf_counter() - inicio, 1),
        backend=getattr(resultado, "backend", "?"),
        vencidos_ignorados=vencidos,
    )