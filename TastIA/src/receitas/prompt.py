"""Montagem do prompt de receitas do TastIA (formato ChatML do SmolLM3).

O prompt faz três coisas:
  1. diz ao modelo para usar SOMENTE os ingredientes do inventário (+ básicos de despensa);
  2. dá prioridade aos ingredientes que vencem primeiro;
  3. exige um formato fixo, para o validador conseguir ler a receita com segurança.
"""
from datetime import date
from typing import Dict, Iterable, List, Optional

# Lista legível usada no prompt. O validador (validador.py) tem a versão "técnica" da mesma lista.
BASICOS_TEXTO = (
    "sal, água, óleo, azeite, pimenta-do-reino e temperos secos básicos "
    "(orégano, colorau, cominho)"
)

# "/no_think" desliga o modo de raciocínio do SmolLM3 (mais rápido).
PROMPT_SISTEMA = (
    "/no_think\n"
    "Você é o TastIA, um assistente de culinária. Responda sempre em português do Brasil.\n"
    "Crie UMA única receita seguindo estas regras OBRIGATÓRIAS:\n"
    f"1. Use SOMENTE os ingredientes da lista 'Ingredientes disponíveis' e os básicos de despensa: {BASICOS_TEXTO}.\n"
    "2. NUNCA cite nenhum outro ingrediente, nem no preparo, nem como opcional, substituição "
    "ou acompanhamento. Não é necessário usar todos os ingredientes disponíveis.\n"
    "3. Dê preferência aos ingredientes que vencem primeiro.\n"
    "4. Respeite o tempo, a dificuldade e as restrições alimentares pedidos.\n"
    "5. Se houver poucos ingredientes, faça a receita mais simples possível com eles.\n"
    "FORMATO (siga exatamente, sem texto antes do título nem depois do último passo):\n"
    "# <Título da receita>\n"
    "**Tempo de preparo:** <número> minutos\n"
    "**Porções:** <número>\n"
    "## Ingredientes\n"
    "- <quantidade> <ingrediente>\n"
    "## Modo de preparo\n"
    "1. <passo>\n"
    "Seja objetivo e não repita informações."
)

# O template do SmolLM3 insere um bloco de pensamento vazio quando /no_think está ativo.
PREENCHER_THINK_VAZIO = True

MAX_ITENS_NO_PROMPT = 40

_TEMPOS = {
    "15": "até 15 minutos",
    "30": "até 30 minutos",
    "45": "até 45 minutos",
    "60": "até 1 hora",
}
_DIFICULDADES = {"facil": "fácil", "media": "média", "dificil": "difícil"}


def _limpar(texto: Optional[str], limite: int) -> str:
    """Remove tokens especiais do ChatML e quebras de linha do texto digitado pelo usuário."""
    if not texto:
        return ""
    texto = str(texto).replace("<|", "").replace("|>", "")
    texto = " ".join(texto.split())
    return texto[:limite]


def descrever_validade(validade, hoje: Optional[date] = None) -> Optional[str]:
    """Devolve 'vence hoje', 'vence em 3 dias'... só para itens que vencem em até 7 dias."""
    if not validade:
        return None
    hoje = hoje or date.today()
    try:
        data = date.fromisoformat(str(validade)[:10])
    except ValueError:
        return None
    dias = (data - hoje).days
    if dias < 0:
        return "vencido"
    if dias == 0:
        return "vence hoje"
    if dias == 1:
        return "vence amanhã"
    if dias <= 7:
        return f"vence em {dias} dias"
    return None


def _chave_ordenacao(item: Dict) -> tuple:
    validade = str(item.get("validade") or "9999-12-31")[:10]
    return (validade, str(item.get("nome", "")).lower())


def _linha_ingrediente(item: Dict, hoje: date) -> str:
    nome = _limpar(item.get("nome"), 60)
    detalhes: List[str] = []
    quantidade = _limpar(item.get("quantidade"), 30)
    if quantidade:
        detalhes.append(f"quantidade: {quantidade}")
    venc = descrever_validade(item.get("validade"), hoje)
    if venc and venc != "vencido":
        detalhes.append(f"{venc} - priorize")
    return f"- {nome}" + (f" ({'; '.join(detalhes)})" if detalhes else "")


def montar_mensagem_usuario(
    inventario: Iterable[Dict],
    pedido: str,
    tempo: Optional[str] = None,
    dificuldade: Optional[str] = None,
    restricoes: Optional[str] = None,
    evitar: Optional[str] = None,
    correcao: Optional[str] = None,
    hoje: Optional[date] = None,
) -> str:
    hoje = hoje or date.today()
    itens = sorted(inventario, key=_chave_ordenacao)[:MAX_ITENS_NO_PROMPT]
    linhas = ["Ingredientes disponíveis:"]
    linhas += [_linha_ingrediente(i, hoje) for i in itens]
    linhas.append(f"Pedido: {_limpar(pedido, 500)}")
    if tempo in _TEMPOS:
        linhas.append(f"Tempo máximo de preparo: {_TEMPOS[tempo]}")
    if dificuldade in _DIFICULDADES:
        linhas.append(f"Dificuldade: {_DIFICULDADES[dificuldade]}")
    restricoes = _limpar(restricoes, 300)
    if restricoes:
        linhas.append(f"Preferências ou restrições alimentares: {restricoes}")
    evitar = _limpar(evitar, 120)
    if evitar:
        linhas.append(f"Crie uma receita DIFERENTE desta: {evitar}")
    if correcao:
        linhas.append("")
        linhas.append(f"CORREÇÃO: {correcao}")
    return "\n".join(linhas)


def montar_prompt(
    inventario: Iterable[Dict],
    pedido: str,
    tempo: Optional[str] = None,
    dificuldade: Optional[str] = None,
    restricoes: Optional[str] = None,
    evitar: Optional[str] = None,
    correcao: Optional[str] = None,
    hoje: Optional[date] = None,
) -> str:
    """Monta o prompt completo (ChatML) pronto para o modelo.

    inventario: lista de dicts {"nome": str, "quantidade": str|None, "validade": "AAAA-MM-DD"|None}
    """
    usuario = montar_mensagem_usuario(
        inventario, pedido, tempo, dificuldade, restricoes, evitar, correcao, hoje
    )
    prompt = (
        f"<|im_start|>system\n{PROMPT_SISTEMA}<|im_end|>\n"
        f"<|im_start|>user\n{usuario}<|im_end|>\n"
        f"<|im_start|>assistant\n"
    )
    if PREENCHER_THINK_VAZIO:
        prompt += "<think>\n\n</think>\n"
    return prompt
