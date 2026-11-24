"""Regras de combinação "duras" do TastIA (sem IA, roda sem modelo e sem internet).

O módulo combinacoes.py descreve o que combina com o quê e o coerencia.py aponta os problemas de uma receita. Duas
coisas ficavam de fora e deixavam passar receitas sem sentido:

  1. BASE OBRIGATÓRIA PELO PEDIDO. Se o usuário pede 'um lanche', a receita precisa ter pão (ou tapioca) mesmo que o
     modelo dê outro nome ao prato ('Bolinho de queijo'). O mesmo vale para 'macarrão' (precisa de massa), 'risoto'
     (arroz), 'omelete' (ovo), 'salada' (folhas ou legumes), 'sopa' (base de legumes ou grãos) etc. Antes só o NOME da
     receita era conferido, então um pedido de lanche sem pão passava.
  2. O QUE É GRAVE. Quantidade em quilos, doce com carne, arroz com macarrão, restrição alimentar violada ou prato sem
     a base dele não são detalhes: a receita não pode ser entregue assim. `eh_grave` separa esses problemas dos
     avisos leves (falta de quantidade em um item, ordem dos passos...), e o gerador troca a receita por uma montada
     pelo esqueleto (esqueleto.py) quando a melhor tentativa do modelo ainda tem um problema grave.

Cada problema vira uma frase em português pronta para o campo CORREÇÃO do prompt da nova tentativa.
"""
from typing import Dict, Iterable, List, Sequence, Union

from receitas.coerencia import _prato_pedido_ausente_no_titulo
from receitas.combinacoes import (
    _alimentos_da_lista, _exemplos, _itens_do_inventario, _lista_em_texto, arquetipos_do_pedido,
    arquetipos_do_titulo,
)

# início das frases de coerencia.py e combinacoes.py que indicam uma receita sem sentido ou perigosa
MARCAS_GRAVES = (
    "estes ingredientes têm quantidades fora da faixa ideal",     # 10 kg de bacon
    "a receita mistura ",                                         # arroz com macarrão, peixe com leite, fruta com carne
    "a receita é de ",                                            # bolo, vitamina ou sobremesa com carne ou cebola
    "o prato é salgado",                                          # sopa ou omelete com fruta doce
    "o pedido foi café da manhã, mas a receita leva",
    "o pedido foi uma refeição",
    "a receita precisa ser ",                                     # restrição alimentar (vegana, sem lactose...)
    "o nome da receita é de ",                                    # omelete sem ovo, sanduíche sem pão
    "o prato é ",                                                 # lanche sem recheio, almoço sem proteína, sem a base
)


def eh_grave(problema: str) -> bool:
    """True se o problema de qualidade deixa a receita sem sentido ou perigosa (não é um detalhe a ajustar)."""
    p = str(problema or "").strip().lower()
    return any(p.startswith(m) for m in MARCAS_GRAVES)


def problemas_graves(problemas: Iterable[str]) -> List[str]:
    return [p for p in problemas if eh_grave(p)]


def problemas_de_base(
    pedido: str,
    titulo: str,
    ingredientes: Sequence[str],
    inventario: Sequence[Union[str, Dict]],
    proibidos: Iterable[str] = (),
) -> List[str]:
    """Falta a base do prato: lanche sem pão, macarrão sem massa, risoto sem arroz, omelete sem ovo...

    Confere o prato pelo NOME da receita e também pelo PEDIDO (quando o nome não cita o prato pedido). Só aponta
    partes obrigatórias que não estão em nenhum ingrediente. Lista vazia = tudo certo.
    """
    presentes = set(_alimentos_da_lista(ingredientes))
    if not presentes:
        return []
    proibidos = set(proibidos)
    itens = _itens_do_inventario(inventario)

    do_titulo = [a for a in arquetipos_do_titulo(titulo) if a.checa_partes]
    conferir = [(a, True) for a in do_titulo]     # True: o título já cobra as partes marcadas como `coberta`
    if _prato_pedido_ausente_no_titulo(pedido, titulo):
        # o nome da receita não é do prato pedido: confere o que o pedido exige (lanche precisa de pão)
        for a in arquetipos_do_pedido(pedido):
            if (a.no_titulo or a.no_pedido) and a.checa_partes and all(a.chave != t.chave for t, _ in conferir):
                conferir.append((a, False))

    problemas: List[str] = []
    for arq, pelo_titulo in conferir:
        for parte in arq.partes:
            if not parte.obrigatoria or (presentes & parte.grupo):
                continue
            if pelo_titulo and not parte.coberta:
                continue    # combinacoes.verificar_combinacoes já aponta estas
            exemplos = _exemplos(parte.grupo, itens, proibidos)
            dica = f" Use {_lista_em_texto(exemplos)} (que você tem) como {parte.rotulo}." if exemplos else ""
            problemas.append(
                f"o prato é {arq.rotulo}, mas a receita não tem {parte.rotulo}.{dica} "
                f"Refaça um prato de {arq.rotulo} de verdade, com {parte.rotulo} na lista de ingredientes."
            )
    vistos: List[str] = []
    return [p for p in problemas if not (p in vistos or vistos.append(p))]
