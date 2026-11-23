"""Geração de receitas do TastIA: prompt -> modelo -> limpeza do texto -> validação -> nova tentativa se preciso.

Camadas de proteção (cada uma roda sem modelo e sem internet):

  1. ESQUELETO (esqueleto.py): quando o pedido permite, o código escolhe o prato e escreve título, tempo, porções e
     ingredientes com quantidades certas; o modelo só continua nos passos. Sem prato possível, o modelo escreve tudo.
  2. FORMATADOR e REPAROS: limpam o texto, completam a lista de ingredientes e LIMITAM QUANTIDADES ABSURDAS
     ('10 kg de bacon' -> teto realista, nunca acima do inventário).
  3. VALIDAÇÃO: ingredientes do inventário, coerência (coerencia.py), combinações (combinacoes.py) e a base
     obrigatória do prato (regras.py: lanche sempre com pão, macarrão com massa...).
  4. PLANO B (plano_b.py): se, depois das tentativas, a melhor receita ainda é inválida, tem um problema GRAVE
     (quantidade absurda, mistura sem sentido...) ou está fora do formato, ela é trocada por uma
     das 30 receitas prontas do catálogo (lasanha, bolo, sopa, doces...), montada só com o que o usuário tem; se
     nenhuma servir, pela receita de reserva do esqueleto. O usuário não recebe receita sem sentido.
     Se o inventário não permite nenhuma das 30, o plano B gera a mais próxima do pedido mesmo assim, com os itens
     que faltam na lista (`itens_faltando`, `sugestao_para_aprovar`): sai como inválida, nunca é salva sozinha e o
     usuário aprova ou não.
  5. TEMPO REAL: o tempo escrito na receita é o tempo verdadeiro dos passos (formatador.tempo_verdadeiro); o tempo
     máximo escolhido na tela nunca é copiado para a receita.
"""
import time
from dataclasses import dataclass, field, asdict, replace
from datetime import date
from typing import Dict, List, Optional, Sequence, Tuple, Union

from receitas.coerencia import alimentos_proibidos, pedido_especifico, verificar_qualidade
from receitas.formatador import campos_ausentes, formatar_receita
from receitas.esqueleto import MAX_TOKENS_PASSOS, Prato, eh_receita_completa, escolher_pratos, juntar
from receitas.prompt import dias_para_vencer, montar_prompt
from receitas.regras import eh_grave, problemas_de_base
from receitas.garantia import formato_perfeito, resgatar_formato
from receitas.plano_b import escolher_plano_b, unir_com_esqueleto
from receitas.reparos import completar_lista_de_ingredientes, limitar_quantidades
from receitas.validador import (
    ALIMENTOS, ResultadoValidacao, _palavras, _subtokens, _tokens_inventario,
    normalizar_texto, validar_receita,
)

MAX_TOKENS_PADRAO = 600
MAX_TENTATIVAS_PADRAO = 2
LIMITE_URGENTE_DIAS = 3   # itens que vencem em até 3 dias DEVEM aparecer na receita
MAX_URGENTES = 3          # acompanha (informa) os 3 que vencem primeiro
MAX_OBRIGATORIOS = 1      # só em pedido genérico exige o que vence primeiro; o pedido do usuário sempre manda
USAR_ESQUELETO = True     # False = o modelo escreve a receita inteira, como antes
USAR_PLANO_B = True       # troca a receita com problema grave pela do esqueleto, quando houver
MIN_PASSOS_DO_MODELO = 2  # no modo esqueleto, menos passos que isso = o modelo não escreveu a receita (formato quebrado)

# defeitos que só o modelo pode consertar (ficam nos passos); o resto vem do esqueleto escolhido pelo código
_DEFEITOS_DOS_PASSOS = (
    "estes ingredientes estão na lista mas não aparecem no modo de preparo",
    "estes itens são usados no modo de preparo mas NÃO estão na lista",
    "o modo de preparo tem poucos passos",
)


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
    urgentes_usados: List[str] = field(default_factory=list)
    urgentes_nao_usados: List[str] = field(default_factory=list)
    avisos_qualidade: List[str] = field(default_factory=list)
    # plano B com itens que o usuário não tem: a receita é só uma sugestão e o usuário decide se aprova
    itens_faltando: List[str] = field(default_factory=list)
    sugestao_para_aprovar: bool = False

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
    inicio = texto.find("\nIngredientes")
    usados = _tokens_da_receita(texto[inicio:] if inicio >= 0 else texto)
    faltando = []
    for nome in urgentes:
        tokens = _tokens_inventario(nome)
        chave = {t for t in tokens if t in ALIMENTOS} or tokens
        if chave and not (chave & usados):
            faltando.append(nome)
    return faltando


def _montar_correcao(
    val: ResultadoValidacao, urgentes_faltando: Sequence[str] = (), ausentes: Sequence[str] = (),
    qualidade: Sequence[str] = (),
) -> str:
    partes = []
    if not val.estrutura_ok:
        partes.append(
            "sua versão anterior não seguiu o formato exigido; refaça com título, "
            "'Tempo de preparo', 'Porções', 'Ingredientes' e 'Modo de preparo', em texto simples, "
            "sem markdown, sem '#' e sem asteriscos."
        )
    if ausentes:
        partes.append(
            "sua versão anterior não escreveu: " + ", ".join(ausentes) + ". Comece pelo NOME da receita na primeira linha, "
            "depois 'Tempo de preparo: <número> minutos' e 'Porções: <número>' (use exatamente a palavra 'Porções', "
            "não 'Quantidade')."
        )
    if val.problemas:
        partes.append(
            "sua versão anterior citou ingredientes que NÃO estão disponíveis: "
            + ", ".join(val.problemas)
            + ". Refaça a receita completa sem usar nem mencionar esses itens."
        )
    if urgentes_faltando:
        partes.append(
            "sua versão anterior não usou o ingrediente que vence primeiro: "
            + ", ".join(urgentes_faltando)
            + ". Refaça a receita usando esse item, preparado do jeito certo. Os outros ingredientes só "
            "entram se combinarem com o prato; deixe de fora os que não combinam."
        )
    for problema in qualidade:
        partes.append("sua versão anterior tinha um problema: " + problema)
    return " ".join(partes)


def _chave_qualidade(
    val: ResultadoValidacao, urgentes_faltando: Sequence[str] = (), ausentes: Sequence[str] = (),
    obrigatorios_faltando: Sequence[str] = (), qualidade: Sequence[str] = (),
) -> tuple:
    return (not val.estrutura_ok, len(val.problemas), len(obrigatorios_faltando), len(ausentes),
            len(qualidade), len(urgentes_faltando))


def _defeitos_dos_passos(val: ResultadoValidacao, qualidade: Sequence[str]) -> List[str]:
    """Problemas que uma nova geração dos PASSOS pode resolver (o resto está no esqueleto, feito pelo código)."""
    achados = [p for p in qualidade if p.startswith(_DEFEITOS_DOS_PASSOS) or "nenhum passo cozinha" in p]
    return achados


def _avaliar(texto, bruto, nomes, ativos, urgentes, obrigatorios, pedido, tempo, restricoes, proibidos,
             exigir_passos=False):
    """Valida um texto já formatado e devolve (val, falta, falta_obrig, ausentes, qualidade, chave).

    exigir_passos: no modo esqueleto, o texto só vale se o modelo escreveu passos de verdade.
    """
    val = validar_receita(texto, nomes)
    if exigir_passos and val.estrutura_ok:
        from receitas.formatador import _estruturar as _est
        _, dados = _est(texto, corrigir_unidades=False)
        if dados is None or len(dados["passos"]) < MIN_PASSOS_DO_MODELO:
            val = replace(val, valido=False, estrutura_ok=False)
    falta = _urgentes_nao_usados(texto, urgentes) if val.estrutura_ok else list(urgentes)
    ausentes = campos_ausentes(bruto)
    falta_obrig = [n for n in falta if n in obrigatorios]
    qualidade: List[str] = []
    if val.estrutura_ok:
        qualidade = verificar_qualidade(texto, pedido, nomes, tempo, restricoes)
        from receitas.formatador import _estruturar
        _, d = _estruturar(texto, corrigir_unidades=False)
        if d is not None:
            qualidade += [p for p in problemas_de_base(pedido, d["titulo"], d["ingredientes"], ativos, proibidos)
                          if p not in qualidade]
    chave = _chave_qualidade(val, falta, ausentes, falta_obrig, qualidade)
    return val, falta, falta_obrig, ausentes, qualidade, chave


def _aplicar_plano_b(melhor_texto, melhor_val, melhor_falta, melhor_chave, melhor_qualidade, ativos, pratos, nomes,
                     urgentes, obrigatorios, pedido, tempo, restricoes, proibidos, evitar):
    """Troca a melhor receita por uma do plano B se ela for realmente melhor (válida, sem problema grave).

    Ordem de tentativa: receitas do catálogo que são o prato pedido, depois o resto do catálogo e as reservas do
    esqueleto (plano_b.unir_com_esqueleto). A receita do plano B tem o tempo REAL dos passos, nunca o tempo pedido.
    """
    catalogo = escolher_plano_b(ativos, pedido, tempo, restricoes, urgentes, evitar)
    for candidato in unir_com_esqueleto(catalogo, pratos, pedido):
        texto_b = limitar_quantidades(formatar_receita(candidato.texto_reserva), ativos)
        val_b, falta_b, _, ausentes_b, qualidade_b, chave_b = _avaliar(
            texto_b, candidato.texto_reserva, nomes, ativos, urgentes, obrigatorios, pedido, tempo, restricoes, proibidos)
        if (val_b.valido and formato_perfeito(texto_b) and not any(eh_grave(q) for q in qualidade_b)
                and chave_b < melhor_chave):
            return texto_b, val_b, falta_b, chave_b, qualidade_b
    return melhor_texto, melhor_val, melhor_falta, melhor_chave, melhor_qualidade


def _sugerir_com_itens_faltando(ativos, nomes, urgentes, obrigatorios, pedido, tempo, restricoes, proibidos, evitar):
    """Última opção do plano B: uma receita do catálogo com itens que o usuário não tem, para ele aprovar ou não.

    Devolve (texto, validação, falta, chave, qualidade, itens que faltam) ou None. A receita fica no formato
    perfeito e sem problema grave de combinação; o validador a marca como inválida por causa dos itens de fora.
    """
    for candidato in escolher_plano_b(ativos, pedido, tempo, restricoes, urgentes, evitar, permitir_faltas=True):
        texto_b = limitar_quantidades(formatar_receita(candidato.texto_reserva), ativos)
        val_b, falta_b, _, _, qualidade_b, chave_b = _avaliar(
            texto_b, candidato.texto_reserva, nomes, ativos, urgentes, obrigatorios, pedido, tempo, restricoes, proibidos)
        if val_b.estrutura_ok and formato_perfeito(texto_b) and not any(eh_grave(q) for q in qualidade_b):
            return texto_b, val_b, falta_b, chave_b, qualidade_b, list(candidato.faltando)
    return None


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
    if pedido_especifico(pedido, nomes):
        obrigatorios = []
    else:
        proibidos = alimentos_proibidos(pedido, restricoes)
        permitidos = [n for n in urgentes if not (_tokens_inventario(n) & proibidos)]
        obrigatorios = permitidos[:MAX_OBRIGATORIOS]
    proibidos = alimentos_proibidos(pedido, restricoes)
    pratos: List[Prato] = []
    if USAR_ESQUELETO:
        pratos = escolher_pratos(ativos, pedido, tempo, restricoes, urgentes, evitar)
    prato = pratos[0] if pratos else None

    inicio = time.perf_counter()
    melhor_texto, melhor_val, melhor_falta, melhor_chave, correcao, feitas = "", None, [], None, None, 0
    melhor_qualidade: List[str] = []
    melhor_so_passos = False
    resultado = None
    brutos: List[str] = []

    limite, extra_formato = max(1, max_tentativas), 1
    while feitas < limite:
        feitas += 1
        prompt = montar_prompt(ativos, pedido, tempo, dificuldade, restricoes, evitar, correcao, hoje, prato=prato)
        resultado = gerador.gerar_de_prompt(prompt, min(max_tokens, MAX_TOKENS_PASSOS) if prato else max_tokens)
        bruto = resultado.texto
        so_passos = prato is not None and not eh_receita_completa(bruto)   # o modelo continuou o esqueleto
        if so_passos:
            bruto = juntar(prato, bruto)
        brutos.append(bruto)
        texto = formatar_receita(bruto, tempo)
        texto = completar_lista_de_ingredientes(texto, nomes)
        texto = limitar_quantidades(texto, ativos)
        val, falta, falta_obrig, ausentes, qualidade, chave = _avaliar(
            texto, bruto, nomes, ativos, urgentes, obrigatorios, pedido, tempo, restricoes, proibidos,
            exigir_passos=so_passos)
        if melhor_chave is None or chave < melhor_chave:
            melhor_texto, melhor_val, melhor_falta, melhor_chave = texto, val, falta, chave
            melhor_qualidade, melhor_so_passos = qualidade, so_passos
        if val.valido and not falta_obrig and not ausentes and not qualidade:
            break
        if so_passos:
            # lista, título e tempo vêm do esqueleto: só vale repetir se o defeito está nos passos
            pendentes = _defeitos_dos_passos(val, qualidade)
            if val.estrutura_ok and not val.problemas and not pendentes:
                break
            correcao = _montar_correcao(val, [], [], pendentes)
        else:
            correcao = _montar_correcao(val, falta_obrig, ausentes, qualidade)
        if not val.estrutura_ok and feitas == limite and extra_formato:
            limite, extra_formato = limite + 1, 0

    # PLANO B: receita inválida, problema GRAVE, defeito de formato ou passos inválidos escritos pelo modelo -> uma das
    # 30 receitas do catálogo (plano_b.py), montada só com o inventário do usuário, ou a reserva do esqueleto. Uma
    # receita INTEIRA inválida sem nenhuma alternativa continua sendo devolvida como inválida (e não é salva).
    passos_ruins = melhor_so_passos and (
        not melhor_val.valido or bool(_defeitos_dos_passos(melhor_val, melhor_qualidade)))
    precisa_b = (passos_ruins or not melhor_val.valido or any(eh_grave(q) for q in melhor_qualidade)
                 or not (melhor_val.estrutura_ok and formato_perfeito(melhor_texto)))
    if USAR_PLANO_B and precisa_b:
        melhor_texto, melhor_val, melhor_falta, melhor_chave, melhor_qualidade = _aplicar_plano_b(
            melhor_texto, melhor_val, melhor_falta, melhor_chave, melhor_qualidade, ativos, pratos, nomes, urgentes,
            obrigatorios, pedido, tempo, restricoes, proibidos, evitar)

    # Sem nenhuma receita possível com o inventário: gera a mais próxima do pedido com os itens que faltam, para o
    # usuário aprovar ou não (a receita sai como inválida e não é salva sozinha).
    itens_faltando: List[str] = []
    if USAR_PLANO_B and (not melhor_val.valido or any(eh_grave(q) for q in melhor_qualidade)):
        sugestao = _sugerir_com_itens_faltando(
            ativos, nomes, urgentes, obrigatorios, pedido, tempo, restricoes, proibidos, evitar)
        if sugestao:
            melhor_texto, melhor_val, melhor_falta, melhor_chave, melhor_qualidade, itens_faltando = sugestao

    # GARANTIA DE FORMATO: se ainda não está no formato padrão, remonta a receita a partir do que o modelo escreveu.
    # Só vale se ficar no formato e sem ingrediente de fora.
    if not (melhor_val.estrutura_ok and formato_perfeito(melhor_texto)):
        for bruto in reversed(brutos):
            resgatado = resgatar_formato([bruto], pedido, tempo)
            if not resgatado:
                continue
            texto_r = limitar_quantidades(completar_lista_de_ingredientes(formatar_receita(resgatado), nomes), ativos)
            val_r, falta_r, _, _, qualidade_r, chave_r = _avaliar(
                texto_r, resgatado, nomes, ativos, urgentes, obrigatorios, pedido, tempo, restricoes, proibidos)
            if val_r.estrutura_ok and formato_perfeito(texto_r) and chave_r < melhor_chave:
                melhor_texto, melhor_val, melhor_falta, melhor_chave = texto_r, val_r, falta_r, chave_r
                melhor_qualidade = qualidade_r
                break

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
        avisos_qualidade=melhor_qualidade,
        itens_faltando=itens_faltando,
        sugestao_para_aprovar=bool(itens_faltando),
    )
