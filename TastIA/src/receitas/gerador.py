"""Geração de receitas do TastIA: prompt -> modelo -> limpeza do texto -> validação -> nova tentativa se preciso."""
import time
from dataclasses import dataclass, field, asdict
from datetime import date
from typing import Dict, List, Optional, Sequence, Tuple, Union

from receitas.formatador import formatar_receita
from receitas.prompt import dias_para_vencer, montar_prompt
from receitas.validador import (
    ALIMENTOS, ResultadoValidacao, _palavras, _subtokens, _tokens_inventario,
    normalizar_texto, validar_receita,
)

MAX_TOKENS_PADRAO = 650
MAX_TENTATIVAS_PADRAO = 2
LIMITE_URGENTE_DIAS = 3   # itens que vencem em até 3 dias DEVEM aparecer na receita
MAX_URGENTES = 3          # exige no máximo os 3 que vencem primeiro (evita pedir o impossível)


class InventarioVazioError(ValueError):
    """Não há ingredientes (válidos) para gerar a receita."""


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
    urgentes_usados: List[str] = field(default_factory=list)       # vencem logo e entraram na receita
    urgentes_nao_usados: List[str] = field(default_factory=list)   # vencem logo e ficaram de fora

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
    # quem vence primeiro vem primeiro (itens sem validade válida ficam no fim)
    ativos.sort(key=_chave_validade)
    return ativos, vencidos


def _chave_validade(item: Dict) -> tuple:
    dias = dias_para_vencer(item.get("validade"))
    return (dias is None, dias if dias is not None else 0, str(item.get("nome", "")).lower())


def _urgentes(ativos: Sequence[Dict], hoje: Optional[date] = None) -> List[str]:
    """Nomes dos itens que vencem em até LIMITE_URGENTE_DIAS dias, do mais próximo ao mais distante."""
    achados = []
    for item in ativos:
        dias = dias_para_vencer(item.get("validade"), hoje)
        if dias is not None and 0 <= dias <= LIMITE_URGENTE_DIAS:
            achados.append((dias, item["nome"]))
    achados.sort()
    return [nome for _, nome in achados[:MAX_URGENTES]]


def _tokens_da_receita(texto: str) -> set:
    return {sub for p in _palavras(texto) for sub in _subtokens(p)}


def _urgentes_nao_usados(texto: str, urgentes: Sequence[str]) -> List[str]:
    """Quais itens urgentes a receita NÃO menciona (compara pelo alimento principal do nome)."""
    # só conta o que aparece em 'Ingredientes' e 'Modo de preparo' (o título pode citar um item sem usá-lo)
    inicio = texto.find("\nIngredientes")
    usados = _tokens_da_receita(texto[inicio:] if inicio >= 0 else texto)
    faltando = []
    for nome in urgentes:
        tokens = _tokens_inventario(nome)
        chave = {t for t in tokens if t in ALIMENTOS} or tokens
        if chave and not (chave & usados):
            faltando.append(nome)
    return faltando


def _montar_correcao(val: ResultadoValidacao, urgentes_faltando: Sequence[str] = ()) -> str:
    partes = []
    if not val.estrutura_ok:
        partes.append(
            "sua versão anterior não seguiu o formato exigido; refaça com título, "
            "'Tempo de preparo', 'Porções', 'Ingredientes' e 'Modo de preparo', em texto simples, "
            "sem markdown, sem '#' e sem asteriscos."
        )
    if val.problemas:
        partes.append(
            "sua versão anterior citou ingredientes que NÃO estão disponíveis: "
            + ", ".join(val.problemas)
            + ". Refaça a receita completa sem usar nem mencionar esses itens."
        )
    if urgentes_faltando:
        partes.append(
            "sua versão anterior não usou ingredientes que vencem em breve: "
            + ", ".join(urgentes_faltando)
            + ". Refaça a receita usando obrigatoriamente esses itens."
        )
    return " ".join(partes)


def _chave_qualidade(val: ResultadoValidacao, urgentes_faltando: Sequence[str] = ()) -> tuple:
    return (not val.estrutura_ok, len(val.problemas), len(urgentes_faltando))


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
    urgentes = _urgentes(ativos, hoje)
    inicio = time.perf_counter()
    melhor_texto, melhor_val, melhor_falta, correcao, feitas = "", None, [], None, 0

    for _ in range(max(1, max_tentativas)):
        feitas += 1
        prompt = montar_prompt(ativos, pedido, tempo, dificuldade, restricoes, evitar, correcao, hoje)
        resultado = gerador.gerar_de_prompt(prompt, max_tokens)
        texto = formatar_receita(resultado.texto)   # sem '##', '**', observações soltas etc.
        val = validar_receita(texto, nomes)
        falta = _urgentes_nao_usados(texto, urgentes) if val.estrutura_ok else list(urgentes)
        if melhor_val is None or _chave_qualidade(val, falta) < _chave_qualidade(melhor_val, melhor_falta):
            melhor_texto, melhor_val, melhor_falta = texto, val, falta
        if val.valido and not falta:
            break
        correcao = _montar_correcao(val, falta)

    return ReceitaGerada(
        texto=melhor_texto,
        valida=melhor_val.valido,
        fora_do_inventario=melhor_val.problemas,
        estrutura_ok=melhor_val.estrutura_ok,
        tentativas=feitas,
        tempo_total_s=round(time.perf_counter() - inicio, 1),
        backend=getattr(resultado, "backend", "?"),
        vencidos_ignorados=vencidos,
        urgentes_usados=[n for n in urgentes if n not in melhor_falta],
        urgentes_nao_usados=melhor_falta,
    )
