"""Montagem do prompt de receitas do TastIA (formato ChatML do SmolLM3).

O prompt faz três coisas:
  1. diz ao modelo para usar SOMENTE os ingredientes do inventário (+ básicos de despensa);
  2. dá prioridade aos ingredientes que vencem primeiro;
  3. exige um formato fixo, para o validador conseguir ler a receita com segurança.

O prompt é CURTO de propósito (~3.000 caracteres): o modelo pequeno ecoava as regras e copiava o exemplo quando o
prompt tinha mais de 7.000. No modo esqueleto (esqueleto.py) a resposta do assistente já vem começada no prompt.
"""
import re
from datetime import date
from typing import Dict, Iterable, List, Optional

from receitas.coerencia import alimentos_proibidos
from receitas.combinacoes import texto_orientacao
from receitas.unidades import dica_de_unidade, quantidade_natural
from receitas.validador import normalizar_texto

BASICOS_TEXTO = (
    "sal, água, óleo, azeite, pimenta-do-reino e temperos secos básicos "
    "(orégano, colorau, cominho)"
)

PROMPT_SISTEMA = (
    "/no_think\n"
    "Você é o TastIA, um assistente de culinária. Responda sempre em português do Brasil.\n"
    "Crie UMA única receita seguindo estas regras OBRIGATÓRIAS:\n"
    f"1. Use SOMENTE os ingredientes da lista 'Ingredientes disponíveis' e os básicos de despensa: {BASICOS_TEXTO}. "
    "Nunca cite outro ingrediente, nem como opcional, substituição ou acompanhamento. Não precisa usar todos.\n"
    "2. O PEDIDO DO USUÁRIO MANDA: o prato, os alimentos citados, o tempo, a dificuldade e as restrições vêm "
    "SEMPRE em primeiro lugar. A validade serve só para DESEMPATAR: entre ingredientes que combinam com o pedido, "
    "prefira os marcados com 'VENCE LOGO' ou 'priorize'. Se um item não combina com o pedido, deixe-o de fora.\n"
    "3. COERÊNCIA: faça UM prato real e conhecido, só com ingredientes que combinam. Lanche ou sanduíche = pão + "
    "recheio. Massa = macarrão + molho, queijo ou carne. Almoço ou jantar = proteína + base (arroz, batata, "
    "macarrão) + legume. Salada = folhas e legumes. Doce com doce, salgado com salgado. Nunca junte duas bases "
    "pesadas (arroz com macarrão, pão com arroz), peixe com leite, frango com carne de boi nem fruta doce com carne. "
    "Se vier a linha 'Combinações que fazem sentido', escolha uma delas.\n"
    "4. Respeite o tempo, a dificuldade e as restrições alimentares pedidos. Com poucos ingredientes, faça a "
    "receita mais simples possível.\n"
    "5. TÉCNICA: carnes, ovos, massas, arroz, batata e grãos secos são sempre cozidos antes de servir. Grão seco "
    "(feijão, soja, lentilha, grão-de-bico) com tempo curto: o molho e o cozimento são pré-preparo no 1º passo, "
    "fora do tempo contado.\n"
    "6. QUANTIDADES realistas para as porções (ex.: 50 g a 100 g de bacon, 100 g a 300 g de queijo, uma pitada de "
    "sal), NUNCA quilos para poucas porções e nunca maiores que a quantidade disponível. Unidade certa: queijo, "
    "carnes, presunto, bacon, arroz, macarrão, farinha e manteiga em g; leite, suco, água e óleo em ml ou colheres; "
    "só ovos, frutas, pão e legumes inteiros em unidades.\n"
    "7. Texto simples: sem markdown, '#', asteriscos nem emojis. Frases completas terminadas em ponto. Nada antes "
    "do nome e nada depois do último passo.\n"
    "8. FORMATO (exatamente assim):\n"
    "<Nome do prato real, só com alimentos da lista, sem rótulo>\n"
    "Tempo de preparo: <tempo real em minutos>\n"
    "Porções: <número>\n"
    "Ingredientes\n"
    "- <quantidade> <unidade> de <ingrediente>\n"
    "Modo de preparo\n"
    "1. <passo>\n"
    "9. INGREDIENTES: um por linha, começando com '- ' e SEMPRE com quantidade, no formato "
    "'- <quantidade> <unidade> de <ingrediente>'. Exemplos: '- 300 g de queijo ralado', '- 2 ovos', "
    "'- 1 colher de sopa de azeite', '- sal a gosto'. Só quantidade e NOME: nada entre parênteses, nada depois "
    "de vírgula, nenhuma observação ao lado. Tudo o que aparecer no preparo tem que estar na lista.\n"
    "10. MODO DE PREPARO: de 4 a 7 passos numerados, na ordem real, com fogo e tempo quando fizer sentido. "
    "O 'Tempo de preparo' é o tempo REAL do prato (soma dos tempos dos passos), nunca o tempo máximo pedido. "
    "Cada ingrediente da lista aparece em algum passo.\n"
    "Seja objetivo e não repita informações."
)

PREENCHER_THINK_VAZIO = True

MAX_ITENS_NO_PROMPT = 40
LIMITE_PRIORIDADE_ALTA_DIAS = 3   # itens que vencem em até 3 dias recebem o rótulo VENCE LOGO

_TEMPOS = {
    "15": "até 15 minutos",
    "30": "até 30 minutos",
    "45": "até 45 minutos",
    "60": "até 1 hora",
}
_DIFICULDADES = {"facil": "fácil", "media": "média", "dificil": "difícil"}

_GRAOS_SECOS = ("soja", "feijao", "feijão", "lentilha", "grao-de-bico", "grão-de-bico", "grao de bico",
                "grão de bico", "ervilha")


def _aviso_preparo(nome: str) -> str:
    n = nome.lower()
    if any(g in n for g in _GRAOS_SECOS) and not any(w in n for w in ("cozid", "lata", "enlatad")):
        return "grão seco: faça o molho e o cozimento como pré-preparo no 1º passo (fora do tempo contado); nunca cru nem batido"
    return ""


def _limpar(texto: Optional[str], limite: int) -> str:
    if not texto:
        return ""
    texto = str(texto).replace("<|", "").replace("|>", "")
    texto = " ".join(texto.split())
    return texto[:limite]


def dias_para_vencer(validade, hoje: Optional[date] = None) -> Optional[int]:
    if not validade:
        return None
    hoje = hoje or date.today()
    try:
        return (date.fromisoformat(str(validade)[:10]) - hoje).days
    except ValueError:
        return None


def descrever_validade(validade, hoje: Optional[date] = None) -> Optional[str]:
    dias = dias_para_vencer(validade, hoje)
    if dias is None:
        return None
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
    quantidade = _limpar(quantidade_natural(nome, item.get("quantidade")), 30)
    if quantidade:
        detalhes.append(f"quantidade disponível (limite máx.): {quantidade}")
    dica = dica_de_unidade(nome)
    if dica and quantidade:
        detalhes.append(dica)
    venc = descrever_validade(item.get("validade"), hoje)
    if venc and venc != "vencido":
        dias = dias_para_vencer(item.get("validade"), hoje)
        if dias is not None and dias <= LIMITE_PRIORIDADE_ALTA_DIAS:
            detalhes.append(f"VENCE LOGO: {venc} - use só se combinar com o pedido")
        else:
            detalhes.append(f"{venc} - priorize se combinar com o pedido")
    aviso = _aviso_preparo(nome)
    if aviso:
        detalhes.append(aviso)
    return f"- {nome}" + (f" ({'; '.join(detalhes)})" if detalhes else "")


def _mensagem_esqueleto(prato, pedido, tempo, dificuldade, restricoes, correcao) -> str:
    """Mensagem curta do modo esqueleto: o código já escolheu o prato e escreveu a receita até 'Modo de preparo'."""
    linhas = [
        f"PEDIDO DO USUÁRIO (prioridade máxima): {_limpar(pedido, 500)}",
        f"Prato escolhido: {prato.titulo}",
        "Ingredientes da receita (use todos e SOMENTE eles, mais sal, água e óleo): "
        + ", ".join(_limpar(n, 60) for n in prato.originais) + ".",
    ]
    if tempo in _TEMPOS:
        linhas.append(f"Tempo máximo de preparo: {_TEMPOS[tempo]}")
    if dificuldade in _DIFICULDADES:
        linhas.append(f"Dificuldade: {_DIFICULDADES[dificuldade]}")
    restricoes = _limpar(restricoes, 300)
    if restricoes:
        linhas.append(f"Preferências ou restrições alimentares (obrigatórias): {restricoes}")
    linhas.append(
        "A receita já está escrita até 'Modo de preparo'. Continue a partir do passo 1 e escreva SÓ os passos "
        "(de 4 a 6), numerados, em frases completas, com fogo e tempo, usando todos os ingredientes da lista."
    )
    if correcao:
        linhas += ["", f"CORREÇÃO: {correcao}"]
    return "\n".join(linhas)


def montar_mensagem_usuario(
    inventario: Iterable[Dict],
    pedido: str,
    tempo: Optional[str] = None,
    dificuldade: Optional[str] = None,
    restricoes: Optional[str] = None,
    evitar: Optional[str] = None,
    correcao: Optional[str] = None,
    hoje: Optional[date] = None,
    prato=None,
) -> str:
    if prato is not None:
        return _mensagem_esqueleto(prato, pedido, tempo, dificuldade, restricoes, correcao)
    hoje = hoje or date.today()
    itens = sorted(inventario, key=_chave_ordenacao)
    if len(itens) > MAX_ITENS_NO_PROMPT:
        ped = " " + " ".join(re.findall(r"[a-z]+", normalizar_texto(pedido or ""))) + " "
        citados = [i for i in itens if f" {normalizar_texto(str(i.get('nome', ''))).strip()} " in ped]
        resto = [i for i in itens if i not in citados]
        itens = sorted(citados + resto[:max(0, MAX_ITENS_NO_PROMPT - len(citados))], key=_chave_ordenacao)
    linhas = ["Ingredientes disponíveis (ordenados pela validade, do que vence primeiro ao que vence por último):"]
    linhas += [_linha_ingrediente(i, hoje) for i in itens]
    linhas.append(f"PEDIDO DO USUÁRIO (prioridade máxima): {_limpar(pedido, 500)}")
    if tempo in _TEMPOS:
        linhas.append(f"Tempo máximo de preparo: {_TEMPOS[tempo]}")
    if dificuldade in _DIFICULDADES:
        linhas.append(f"Dificuldade: {_DIFICULDADES[dificuldade]}")
    restricoes = _limpar(restricoes, 300)
    if restricoes:
        linhas.append(f"Preferências ou restrições alimentares (obrigatórias): {restricoes}")
    orientacao = texto_orientacao(itens, pedido, alimentos_proibidos(pedido, restricoes))
    if orientacao:
        linhas.append(orientacao)
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
    prato=None,
) -> str:
    """Monta o prompt completo (ChatML) pronto para o modelo.

    inventario: lista de dicts {"nome": str, "quantidade": str|None, "validade": "AAAA-MM-DD"|None}
    prato: (opcional) um esqueleto.Prato. Com ele, a resposta do assistente já começa escrita (título, tempo,
    porções, ingredientes e 'Modo de preparo / 1.') e o modelo só continua nos passos.
    """
    usuario = montar_mensagem_usuario(
        inventario, pedido, tempo, dificuldade, restricoes, evitar, correcao, hoje, prato
    )
    prompt = (
        f"<|im_start|>system\n{PROMPT_SISTEMA}<|im_end|>\n"
        f"<|im_start|>user\n{usuario}<|im_end|>\n"
        f"<|im_start|>assistant\n"
    )
    if PREENCHER_THINK_VAZIO:
        prompt += "<think>\n\n</think>\n"
    if prato is not None:
        prompt += prato.prefixo
    return prompt