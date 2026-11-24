"""PLANO B do TastIA: 30 receitas prontas, montadas pelo código com o que o usuário TEM (sem IA, sem internet).

Quando a melhor receita escrita pelo modelo ainda é inválida, tem um problema grave de combinação, quantidade fora da
realidade ou está fora do formato, o gerador (gerador.py) troca a receita por uma deste catálogo. O catálogo cobre
várias classes de alimento (carnes, laticínios, grãos e cereais, verduras e legumes, frutas) e várias refeições
(café da manhã, almoço, jantar, lanche, sobremesa):

  salgados:   lasanha à bolonhesa, abobrinha gratinada, macarrão ao forno, macarrão à bolonhesa, macarrão ao alho e
              óleo, arroz de frango, arroz de forno, frango assado, frango grelhado, escondidinho, bife com cebola,
              peixe assado, sopa de legumes, creme de abóbora, fritada, panqueca salgada, pizza de frigideira,
              misto quente, omelete, cuscuz, tapioca;
  doces:      bolo simples, bolo de cenoura, bolo de banana, pudim de leite, panqueca de banana, mingau de aveia,
              arroz-doce, doce de abóbora, fruta assada.

Como cada receita é montada:
  - cada receita tem PAPÉIS (massa, carne, queijo, legume...). O código escolhe, entre os itens do inventário, os que
    cumprem os papéis; só entra o que o usuário tem, respeitando restrições alimentares e o que o pedido nega
    ('sem cebola'). Papel obrigatório sem item = a receita não é possível com esse inventário;
  - o NOME do prato e os passos citam os itens do usuário (nunca um alimento que ele não tem);
  - cada ingrediente é só a quantidade e o nome ('- 250 g de carne moída'), sem observação ao lado, e nunca acima
    do que o usuário tem no inventário;
  - o TEMPO é o tempo real: soma dos tempos dos passos + preparo (formatador.tempo_real_dos_passos). Nunca o tempo
    máximo pedido na tela: ele só ajuda a escolher uma receita que caiba.

Se o inventário não permite NENHUMA das 30, `escolher_plano_b(..., permitir_faltas=True)` monta a receita que mais se
aproxima do pedido mesmo assim, completando os itens que faltam com um nome padrão ('queijo mussarela'...). Essa
receita sai marcada como inválida (itens fora do inventário) e o usuário decide se aprova ou não; ela nunca é
salva sozinha.

`escolher_plano_b` devolve as receitas possíveis, da que melhor responde ao pedido para a pior, como `Prato` (o mesmo
formato do esqueleto), e `unir_com_esqueleto` junta com as receitas de reserva do esqueleto. Para ensinar uma receita
nova, basta acrescentar uma `ReceitaB` em CATALOGO.
"""
import re
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Optional, Sequence, Set, Tuple

from receitas.coerencia import alimentos_proibidos
from receitas.combinacoes import (
    AVES, FOLHAS, FRIOS, FRUTAS, MASSAS, OVO, PEIXES, QUEIJOS, TUBERCULOS, VEGETAIS, _conflitos, _g,
    arquetipos_do_pedido,
)
from receitas.esqueleto import (
    AROMAS, DEFINICOES, FOLHAS_CRUAS, Item, Prato, _artigos, _cap, _disponivel, _do, _itens_do_inventario,
    _linha_item, _lista,
)
from receitas.formatador import tempo_real_dos_passos
from receitas.historico import inferir_categoria
from receitas.reparos import _baixo, _no_numero
from receitas.unidades import CONTAVEL, tipo_de_medida
from receitas.validador import _canon, normalizar_texto

MAX_CANDIDATOS = 12   # quantas receitas possíveis o gerador pode tentar, da melhor para a pior

# --------------------------------------------------------------------------- #
# Grupos de alimentos dos papéis
# --------------------------------------------------------------------------- #
FARINHAS = _g("farinha", "trigo")
_NAO_FARINHA_DE_TRIGO = r"mandioca|milho|fub|rosca|tapioca|aveia|arroz|amendoa|coco"
CARNE_BOVINA = _g("carne", "boi", "bovino")
BIFE = _g("bife", "carne", "boi", "bovino")
FRANGO = AVES
PEIXE_ASSAR = _g("peixe", "salmao")
LEGUMES_GRELHAR = _g("cenoura", "abobrinha", "brocolis", "pimentao", "tomate", "cogumelo", "champignon", "vagem",
                     "berinjela", "abobora", "chuchu")
LEGUMES_FRITADA = VEGETAIS - FOLHAS - _g("pepino", "palmito")
BASE_SOPA = (VEGETAIS | TUBERCULOS) - FOLHAS_CRUAS - AROMAS
CARNES_SOPA = AVES | CARNE_BOVINA
FRUTAS_FEMININAS = _g("maca", "banana", "pera", "manga")
FRUTAS_MINGAU = _g("banana", "maca", "pera", "manga", "mamao")
ADOCANTES = _g("acucar", "mel")
MACARRAO_B = _g("macarrao", "espaguete")
_PROTEINAS_DE_REFEICAO = (AVES | CARNE_BOVINA | PEIXES | QUEIJOS | OVO | FRIOS
                          | _g("porco", "suino", "bacon", "linguica", "calabresa", "salsicha", "camarao", "bife"))

_BASICOS = {"sal", "agua", "oleo", "azeite", "pimenta", "oregano", "colorau", "cominho", "paprica", "louro", "tempero"}


# --------------------------------------------------------------------------- #
# Estruturas
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Papel:
    chave: str
    grupo: FrozenSet[str]
    qtd: Tuple = ("padrao",)      # ("g", 250) | ("ml", 200) | ("un", 3) | ("un|g", 4, 600) | ("colher", 1)
    #                                 | ("dentes", 2) | ("gosto",) | ("padrao",)
    maximo: int = 1
    obrigatorio: bool = True
    minimo: int = 1               # quantos itens distintos o papel precisa (só vale se o papel é obrigatório)
    excluir: Optional[str] = None     # regex (texto sem acento) dos nomes que NÃO servem para o papel
    preferir: Optional[str] = None    # regex dos nomes preferidos ('carne moída')


@dataclass(frozen=True)
class Passo:
    texto: str                    # {papel} = com artigo, {papel_n} = só o nome, {papel_d} = 'do/da/de ...'
    precisa: Tuple[str, ...] = ()   # papéis que precisam estar na receita para o passo existir
    sem: Tuple[str, ...] = ()       # papéis que NÃO podem estar (versão do passo para quando faltam)


@dataclass(frozen=True)
class BasicoLinha:
    linha: str                    # 'sal a gosto'
    precisa: Tuple[str, ...] = ()
    sem: Tuple[str, ...] = ()


@dataclass(frozen=True)
class ReceitaB:
    chave: str
    titulo: str                   # {papel} = nomes; {a|b} = nomes de vários papéis; {+papel} = ' e nome' (se houver)
    refeicoes: Tuple[str, ...]    # cafe, almoco, jantar, lanche, sobremesa
    classes: Tuple[str, ...]      # classes de alimento que a receita reúne (as mesmas categorias do banco de imagens)
    palavras: Tuple[str, ...]     # palavras do pedido que escolhem esta receita ('lasanha', 'bolo'...)
    porcoes: str
    papeis: Tuple[Papel, ...]
    passos: Tuple[Passo, ...]
    basicos: Tuple[BasicoLinha, ...] = ()
    ao_menos_um: Tuple[str, ...] = ()   # pelo menos um destes papéis (opcionais) precisa existir
    extra_min: int = 0                  # minutos de espera que os passos não citam


@dataclass
class PratoB(Prato):
    """Uma receita do catálogo montada com o inventário do usuário (mesmo formato do esqueleto)."""
    chave_catalogo: str = ""
    casa_pedido: bool = False        # o pedido cita este prato ('lasanha', 'bolo'...)
    refeicoes: Tuple[str, ...] = ()
    faltando: List[str] = field(default_factory=list)   # itens que o usuário NÃO tem (só no modo permitir_faltas)


def _p(chave, grupo, qtd=("padrao",), maximo=1, obrigatorio=True, minimo=1, excluir=None, preferir=None) -> Papel:
    return Papel(chave, frozenset(grupo), tuple(qtd), maximo, obrigatorio, minimo, excluir, preferir)


def _s(texto: str, *precisa: str, sem: Tuple[str, ...] = ()) -> Passo:
    return Passo(texto, tuple(precisa), tuple(sem))


def _b(linha: str, *precisa: str, sem: Tuple[str, ...] = ()) -> BasicoLinha:
    return BasicoLinha(linha, tuple(precisa), tuple(sem))


SAL = _b("sal a gosto")
AGUA = _b("água o suficiente")
OLEO = _b("1 colher de sopa de óleo")
AZEITE = _b("1 colher de sopa de azeite")

# --------------------------------------------------------------------------- #
# O catálogo: 30 receitas
# --------------------------------------------------------------------------- #
CATALOGO: Tuple[ReceitaB, ...] = (
    # ----------------------------------------------------------------- 1
    ReceitaB(
        "lasanha_bolonhesa", "Lasanha à bolonhesa", ("almoco", "jantar"),
        ("graos_e_cereais", "carnes", "laticinios", "verduras_e_legumes"), ("lasanha",), "4",
        (_p("massa", _g("lasanha"), ("g", 250)),
         _p("carne", CARNE_BOVINA, ("g", 300), preferir=r"moid"),
         _p("queijo", QUEIJOS, ("g", 200)),
         _p("tomate", _g("tomate"), ("un", 3)),
         _p("frio", FRIOS, ("g", 100), obrigatorio=False),
         _p("aromas", AROMAS, maximo=2, obrigatorio=False)),
        (_s("Cozinhe {massa} em água fervente com sal por 8 minutos, escorra e reserve.", "massa"),
         _s("@aromas", "aromas"), _s("@tomate", "tomate"),
         _s("Em uma panela, aqueça um fio de óleo, refogue {aromas} por 3 minutos e junte {carne}, mexendo por 10 "
            "minutos, até cozinhar por completo.", "aromas", "carne"),
         _s("Em uma panela, aqueça um fio de óleo e doure {carne}, mexendo por 10 minutos, até cozinhar por "
            "completo.", "carne", sem=("aromas",)),
         _s("Junte {tomate} à carne, com sal a gosto, e cozinhe por 10 minutos, até formar um molho.", "tomate"),
         _s("Em um refratário untado com um fio de óleo, espalhe um pouco do molho, cubra com {massa} e {queijo}, "
            "e repita as camadas.", "massa", "queijo"),
         _s("Distribua {frio} entre as camadas.", "frio"),
         _s("Leve ao forno preaquecido a 200 graus por 25 minutos, até gratinar, e sirva quente.")),
        (SAL, AGUA, OLEO),
    ),
    # ----------------------------------------------------------------- 2
    ReceitaB(
        "abobrinha_gratinada", "Abobrinha gratinada com {queijo} e {tomate}", ("almoco", "jantar"),
        ("verduras_e_legumes", "laticinios"), ("lasanha", "abobrinha", "gratinado", "gratinada"), "2",
        (_p("abobrinha", _g("abobrinha"), ("un", 2)),
         _p("queijo", QUEIJOS, ("g", 150)),
         _p("tomate", _g("tomate"), ("un", 2)),
         _p("frio", FRIOS, ("g", 100), obrigatorio=False)),
        (_s("Lave {abobrinha} e corte em fatias finas, no sentido do comprimento.", "abobrinha"),
         _s("@tomate", "tomate"),
         _s("Aqueça uma frigideira com um fio de óleo e doure as fatias {abobrinha_d} por 2 minutos de cada "
            "lado, com sal a gosto.", "abobrinha"),
         _s("Em um refratário, alterne camadas de {abobrinha}, {tomate} e {queijo}.", "abobrinha", "tomate", "queijo"),
         _s("Distribua {frio} entre as camadas.", "frio"),
         _s("Leve ao forno preaquecido a 200 graus por 20 minutos, até gratinar, e sirva em seguida.")),
        (SAL, OLEO),
    ),
    # ----------------------------------------------------------------- 3
    ReceitaB(
        "macarrao_forno", "{massa} ao forno com {queijo}{+frio}", ("almoco", "jantar"),
        ("graos_e_cereais", "laticinios", "carnes"), ("macarrao", "espaguete", "massa", "forno", "gratinado"), "3",
        (_p("massa", MACARRAO_B, ("g", 250)),
         _p("queijo", QUEIJOS, ("g", 150)),
         _p("frio", FRIOS, ("g", 100), obrigatorio=False),
         _p("tomate", _g("tomate"), ("un", 2), obrigatorio=False)),
        (_s("Cozinhe {massa} em água fervente com sal por 10 minutos e escorra.", "massa"),
         _s("@tomate", "tomate"),
         _s("Em uma panela, aqueça um fio de óleo e cozinhe {tomate} por 8 minutos, com sal a gosto, até formar um "
            "molho.", "tomate"),
         _s("Em um refratário, misture {massa} cozido com o molho e metade {queijo_d}.", "massa", "tomate", "queijo"),
         _s("Em um refratário, misture {massa} cozido com metade {queijo_d}.", "massa", "queijo", sem=("tomate",)),
         _s("Acrescente {frio} e misture.", "frio"),
         _s("Cubra com o restante {queijo_d} e leve ao forno preaquecido a 200 graus por 15 minutos, até gratinar.",
            "queijo")),
        (SAL, AGUA, _b("1 colher de sopa de óleo", "tomate")),
    ),
    # ----------------------------------------------------------------- 4
    ReceitaB(
        "macarrao_bolonhesa", "{massa} à bolonhesa", ("almoco", "jantar"),
        ("graos_e_cereais", "carnes", "verduras_e_legumes"), ("macarrao", "espaguete", "massa", "bolonhesa"), "2",
        (_p("massa", MACARRAO_B, ("g", 250)),
         _p("carne", CARNE_BOVINA, ("g", 250), preferir=r"moid"),
         _p("tomate", _g("tomate"), ("un", 3)),
         _p("aromas", AROMAS, maximo=2, obrigatorio=False)),
        (_s("Cozinhe {massa} em água fervente com sal por 10 minutos, escorra e reserve.", "massa"),
         _s("@aromas", "aromas"), _s("@tomate", "tomate"),
         _s("Em uma panela, aqueça um fio de óleo, refogue {aromas} por 3 minutos e junte {carne}, mexendo por 10 "
            "minutos, até cozinhar por completo.", "aromas", "carne"),
         _s("Em uma panela, aqueça um fio de óleo e doure {carne}, mexendo por 10 minutos, até cozinhar por "
            "completo.", "carne", sem=("aromas",)),
         _s("Junte {tomate}, com sal a gosto, e cozinhe por 10 minutos, até formar um molho.", "tomate"),
         _s("Misture {massa} ao molho, deixe no fogo por 2 minutos e sirva quente.", "massa")),
        (SAL, AGUA, OLEO),
    ),
    # ----------------------------------------------------------------- 5
    ReceitaB(
        "macarrao_alho_oleo", "{massa} ao alho e óleo", ("almoco", "jantar"),
        ("graos_e_cereais", "verduras_e_legumes", "laticinios"), ("macarrao", "espaguete", "massa", "alho"), "2",
        (_p("massa", MACARRAO_B, ("g", 200)),
         _p("alho", _g("alho"), ("dentes", 4)),
         _p("queijo", QUEIJOS, ("g", 50), obrigatorio=False)),
        (_s("Cozinhe {massa} em água fervente com sal por 10 minutos, reserve um pouco da água e escorra.", "massa"),
         _s("Descasque e fatie {alho}.", "alho"),
         _s("Em uma frigideira grande, aqueça 3 colheres de sopa de óleo em fogo baixo e doure {alho} por 2 "
            "minutos, sem deixar queimar.", "alho"),
         _s("Junte {massa} cozido à frigideira e misture por 2 minutos, com um pouco da água do cozimento.", "massa"),
         _s("Finalize com {queijo}, acerte o sal e sirva em seguida.", "queijo"),
         _s("Acerte o sal e sirva em seguida.", sem=("queijo",))),
        (SAL, AGUA, _b("3 colheres de sopa de óleo")),
    ),
    # ----------------------------------------------------------------- 6
    ReceitaB(
        "arroz_frango", "Arroz de {frango}", ("almoco", "jantar"),
        ("graos_e_cereais", "carnes", "verduras_e_legumes"), ("arroz", "frango"), "3",
        (_p("arroz", _g("arroz"), ("g", 200)),
         _p("frango", FRANGO, ("g", 350)),
         _p("tomate", _g("tomate"), ("un", 1), obrigatorio=False),
         _p("aromas", AROMAS, maximo=2, obrigatorio=False)),
        (_s("@aromas", "aromas"), _s("@tomate", "tomate"),
         _s("Corte {frango} em cubos pequenos e tempere com sal.", "frango"),
         _s("Em uma panela, aqueça um fio de óleo, refogue {aromas} por 3 minutos e junte {frango}, mexendo por 10 "
            "minutos, até dourar.", "aromas", "frango"),
         _s("Em uma panela, aqueça um fio de óleo e doure {frango}, mexendo por 10 minutos.", "frango",
            sem=("aromas",)),
         _s("Junte {tomate} e cozinhe por 3 minutos.", "tomate"),
         _s("Lave {arroz}, junte à panela e mexa por 1 minuto.", "arroz"),
         _s("Acrescente o dobro de água quente, tampe e cozinhe em fogo baixo por 20 minutos, até secar a água e o "
            "arroz ficar macio.", "arroz"),
         _s("Acerte o sal e sirva quente.")),
        (SAL, AGUA, _b("2 colheres de sopa de óleo")),
    ),
    # ----------------------------------------------------------------- 7
    ReceitaB(
        "arroz_forno", "Arroz de forno com {queijo}{+frio}", ("almoco", "jantar"),
        ("graos_e_cereais", "laticinios", "carnes"), ("arroz", "forno", "gratinado"), "3",
        (_p("arroz", _g("arroz"), ("g", 200)),
         _p("queijo", QUEIJOS, ("g", 150)),
         _p("frio", FRIOS, ("g", 100), obrigatorio=False),
         _p("tomate", _g("tomate"), ("un", 2), obrigatorio=False)),
        (_s("Em uma panela, aqueça um fio de óleo, junte {arroz} lavado e mexa por 1 minuto.", "arroz"),
         _s("Adicione o dobro de água e sal a gosto, tampe e cozinhe em fogo baixo por 18 minutos.", "arroz"),
         _s("@tomate", "tomate"),
         _s("Em um refratário, misture {arroz} cozido com metade {queijo_d}.", "arroz", "queijo"),
         _s("Acrescente {tomate} e misture.", "tomate"),
         _s("Acrescente {frio} e misture.", "frio"),
         _s("Cubra com o restante {queijo_d} e leve ao forno preaquecido a 200 graus por 15 minutos, até gratinar.",
            "queijo")),
        (SAL, AGUA, OLEO),
    ),
    # ----------------------------------------------------------------- 8
    ReceitaB(
        "frango_assado", "Frango assado com {batata}", ("almoco", "jantar"),
        ("carnes", "verduras_e_legumes"), ("frango", "assado", "batata"), "3",
        (_p("frango", FRANGO, ("g", 450)),
         _p("batata", TUBERCULOS, ("un|g", 4, 600)),
         _p("aromas", AROMAS, maximo=2, obrigatorio=False)),
        (_s("Preaqueça o forno a 200 graus.", "frango"),
         _s("@batata", "batata"), _s("@aromas", "aromas"),
         _s("Em uma tigela, tempere {frango} com sal e misture {aromas}.", "frango", "aromas"),
         _s("Em uma tigela, tempere {frango} com sal.", "frango", sem=("aromas",)),
         _s("Em uma assadeira, distribua {batata} e {frango}, e regue com um fio de azeite.", "batata", "frango"),
         _s("Asse por 45 minutos, virando na metade do tempo, até {frango} dourar e {batata} ficar macia.",
            "frango", "batata"),
         _s("Sirva quente.")),
        (SAL, AZEITE),
    ),
    # ----------------------------------------------------------------- 9
    ReceitaB(
        "frango_grelhado", "Frango grelhado com {legumes}", ("almoco", "jantar"),
        ("carnes", "verduras_e_legumes"), ("frango", "grelhado"), "2",
        (_p("frango", FRANGO, ("g", 300)),
         _p("legumes", LEGUMES_GRELHAR, maximo=2)),
        (_s("Corte {frango} em fatias finas e tempere com sal.", "frango"),
         _s("@legumes", "legumes"),
         _s("Aqueça uma frigideira com um fio de óleo e grelhe {frango} por 6 minutos de cada lado, até cozinhar "
            "por completo.", "frango"),
         _s("Na mesma frigideira, refogue {legumes} por 6 minutos, até ficarem macios.", "legumes"),
         _s("Sirva {frango} com {legumes}.", "frango", "legumes")),
        (SAL, OLEO),
    ),
    # ----------------------------------------------------------------- 10
    ReceitaB(
        "escondidinho_carne", "Escondidinho de {carne}", ("almoco", "jantar"),
        ("carnes", "verduras_e_legumes", "laticinios"), ("escondidinho", "carne", "batata"), "4",
        (_p("carne", CARNE_BOVINA, ("g", 300), preferir=r"moid"),
         _p("batata", TUBERCULOS, ("un|g", 4, 600)),
         _p("queijo", QUEIJOS, ("g", 100), obrigatorio=False),
         _p("aromas", AROMAS, maximo=2, obrigatorio=False)),
        (_s("@batata", "batata"),
         _s("Cozinhe {batata} em água com sal por 20 minutos, até ficar bem macia, e escorra.", "batata"),
         _s("Amasse {batata} até formar um purê, com sal a gosto.", "batata"),
         _s("@aromas", "aromas"),
         _s("Em uma panela, aqueça um fio de óleo, refogue {aromas} por 3 minutos e junte {carne}, mexendo por 10 "
            "minutos, até cozinhar por completo.", "aromas", "carne"),
         _s("Em uma panela, aqueça um fio de óleo e doure {carne}, mexendo por 10 minutos, até cozinhar por "
            "completo.", "carne", sem=("aromas",)),
         _s("Em um refratário, espalhe {carne} e cubra com o purê.", "carne", "batata"),
         _s("Polvilhe {queijo} e leve ao forno preaquecido a 200 graus por 15 minutos, até dourar.", "queijo"),
         _s("Leve ao forno preaquecido a 200 graus por 15 minutos, até dourar.", sem=("queijo",))),
        (SAL, AGUA, OLEO),
    ),
    # ----------------------------------------------------------------- 11
    ReceitaB(
        "bife_cebola", "{carne} com {cebola}{+arroz}", ("almoco", "jantar"),
        ("carnes", "verduras_e_legumes", "graos_e_cereais"), ("bife", "carne", "acebolado", "cebola"), "2",
        (_p("carne", BIFE, ("g", 300), excluir=r"moid"),
         _p("cebola", _g("cebola"), ("un", 2)),
         _p("arroz", _g("arroz"), ("g", 150), obrigatorio=False)),
        (_s("Lave {arroz}, refogue por 1 minuto em um fio de óleo, junte o dobro de água e sal, tampe e cozinhe em "
            "fogo baixo por 18 minutos.", "arroz"),
         _s("Descasque e corte {cebola} em rodelas.", "cebola"),
         _s("Tempere {carne} com sal.", "carne"),
         _s("Aqueça uma frigideira com um fio de óleo e frite {carne} por 5 minutos de cada lado, até cozinhar por "
            "completo.", "carne"),
         _s("Junte {cebola} à frigideira e refogue por 5 minutos, até murchar.", "cebola"),
         _s("Sirva {carne} com {cebola} e {arroz}.", "carne", "cebola", "arroz"),
         _s("Sirva {carne} com {cebola}.", "carne", "cebola", sem=("arroz",))),
        (SAL, OLEO, _b("água o suficiente", "arroz")),
    ),
    # ----------------------------------------------------------------- 12
    ReceitaB(
        "peixe_assado", "{peixe} assado com {batata}", ("almoco", "jantar"),
        ("carnes", "verduras_e_legumes"), ("peixe", "salmao", "assado"), "2",
        (_p("peixe", PEIXE_ASSAR, ("g", 300)),
         _p("batata", TUBERCULOS, ("un|g", 3, 450)),
         _p("limao", _g("limao"), ("un", 1), obrigatorio=False)),
        (_s("Preaqueça o forno a 200 graus.", "peixe"),
         _s("@batata", "batata"),
         _s("Cozinhe {batata} em água com sal por 10 minutos e escorra.", "batata"),
         _s("Tempere {peixe} com sal e o suco {limao_d}.", "peixe", "limao"),
         _s("Tempere {peixe} com sal.", "peixe", sem=("limao",)),
         _s("Em uma assadeira untada com um fio de azeite, coloque {batata} e {peixe}.", "batata", "peixe"),
         _s("Asse por 25 minutos, até {peixe} ficar firme e dourado.", "peixe"),
         _s("Sirva em seguida.")),
        (SAL, AGUA, AZEITE),
    ),
    # ----------------------------------------------------------------- 13
    ReceitaB(
        "sopa_legumes", "Sopa de {base|proteina}", ("almoco", "jantar"),
        ("verduras_e_legumes", "carnes"), ("sopa", "caldo", "legumes"), "4",
        (_p("base", BASE_SOPA, maximo=3, minimo=2),
         _p("proteina", CARNES_SOPA, ("g", 200), obrigatorio=False, excluir=r"costela|charque"),
         _p("aromas", AROMAS, maximo=2, obrigatorio=False)),
        (_s("@base", "base"), _s("@aromas", "aromas"),
         _s("Em uma panela, aqueça um fio de óleo, refogue {aromas} por 3 minutos e junte {proteina}, mexendo por 10 "
            "minutos, até dourar.", "aromas", "proteina"),
         _s("Em uma panela, aqueça um fio de óleo e doure {proteina} por 10 minutos, mexendo de vez em quando.",
            "proteina", sem=("aromas",)),
         _s("Em uma panela, aqueça um fio de óleo e refogue {aromas} por 3 minutos.", "aromas", sem=("proteina",)),
         _s("Acrescente {base}, cubra com água e cozinhe em fogo médio por 25 minutos, até ficar macio.", "base"),
         _s("Acerte o sal e sirva quente.")),
        (SAL, AGUA, OLEO),
    ),
    # ----------------------------------------------------------------- 14
    ReceitaB(
        "creme_abobora", "Creme de {abobora}", ("almoco", "jantar"),
        ("verduras_e_legumes",), ("creme", "sopa", "abobora"), "4",
        (_p("abobora", _g("abobora"), ("g", 500)),
         _p("aromas", AROMAS, maximo=2, obrigatorio=False)),
        (_s("@abobora", "abobora"), _s("@aromas", "aromas"),
         _s("Em uma panela, aqueça um fio de óleo e refogue {aromas} por 3 minutos.", "aromas"),
         _s("Junte {abobora}, cubra com água e cozinhe por 25 minutos, até ficar bem macia.", "abobora"),
         _s("Bata tudo no liquidificador até obter um creme liso.", "abobora"),
         _s("Volte à panela, aqueça por 5 minutos, acerte o sal e sirva quente.")),
        (SAL, AGUA, OLEO),
    ),
    # ----------------------------------------------------------------- 15
    ReceitaB(
        "fritada_legumes", "Fritada de {legumes}{+queijo}", ("cafe", "almoco", "jantar", "lanche"),
        ("verduras_e_legumes", "laticinios", "outros"), ("fritada", "frittata", "ovo", "legumes"), "3",
        (_p("ovo", OVO, ("un", 4)),
         _p("legumes", LEGUMES_FRITADA, maximo=2),
         _p("queijo", QUEIJOS, ("g", 80), obrigatorio=False)),
        (_s("@legumes", "legumes"),
         _s("Quebre {ovo} em uma tigela, junte uma pitada de sal e bata com um garfo.", "ovo"),
         _s("Aqueça uma frigideira antiaderente com um fio de óleo e refogue {legumes} por 5 minutos, até ficarem "
            "macios.", "legumes"),
         _s("Despeje os ovos batidos sobre os legumes, espalhe {queijo} e cozinhe em fogo baixo, com a frigideira "
            "tampada, por 8 minutos.", "ovo", "queijo"),
         _s("Despeje os ovos batidos sobre os legumes e cozinhe em fogo baixo, com a frigideira tampada, por 8 "
            "minutos.", "ovo", sem=("queijo",)),
         _s("Vire com a ajuda de um prato e deixe por mais 2 minutos, até dourar.", "ovo")),
        (SAL, OLEO),
    ),
    # ----------------------------------------------------------------- 16
    ReceitaB(
        "panqueca_salgada", "Panqueca de {recheio}", ("almoco", "jantar", "lanche"),
        ("graos_e_cereais", "laticinios", "outros"), ("panqueca", "crepe"), "3",
        (_p("farinha", FARINHAS, ("g", 150), excluir=_NAO_FARINHA_DE_TRIGO),
         _p("ovo", OVO, ("un", 2)),
         _p("leite", _g("leite"), ("ml", 250)),
         _p("recheio", QUEIJOS | FRIOS, ("g", 100), maximo=2)),
        (_s("Em uma tigela, misture {farinha}, {ovo}, {leite} e uma pitada de sal, até obter uma massa lisa.",
            "farinha", "ovo", "leite"),
         _s("Aqueça uma frigideira antiaderente untada com um fio de óleo.", "farinha"),
         _s("Despeje uma concha da massa, espalhe e doure por 2 minutos de cada lado. Repita com o restante.",
            "farinha"),
         _s("Recheie cada panqueca com {recheio}, enrole e leve à frigideira por mais 2 minutos, para derreter.",
            "recheio"),
         _s("Sirva quente.")),
        (SAL, OLEO),
    ),
    # ----------------------------------------------------------------- 17
    ReceitaB(
        "pizza_frigideira", "Pizza de frigideira com {queijo|frio}", ("almoco", "jantar", "lanche"),
        ("graos_e_cereais", "laticinios", "verduras_e_legumes"), ("pizza",), "2",
        (_p("farinha", FARINHAS, ("g", 200), excluir=_NAO_FARINHA_DE_TRIGO),
         _p("queijo", QUEIJOS, ("g", 150)),
         _p("tomate", _g("tomate"), ("un", 2)),
         _p("frio", FRIOS, ("g", 100), obrigatorio=False)),
        (_s("Em uma tigela, misture {farinha}, uma pitada de sal, 2 colheres de sopa de óleo e água morna aos "
            "poucos, até formar uma massa que desgruda das mãos.", "farinha"),
         _s("Abra a massa com as mãos, formando um disco do tamanho da frigideira.", "farinha"),
         _s("@tomate", "tomate"),
         _s("Aqueça uma frigideira antiaderente e doure a massa por 4 minutos de um lado.", "farinha"),
         _s("Vire a massa, cubra com {tomate}, {queijo} e {frio}, tampe e deixe em fogo baixo por 8 minutos, até o "
            "queijo derreter.", "tomate", "queijo", "frio"),
         _s("Vire a massa, cubra com {tomate} e {queijo}, tampe e deixe em fogo baixo por 8 minutos, até o queijo "
            "derreter.", "tomate", "queijo", sem=("frio",))),
        (SAL, AGUA, _b("2 colheres de sopa de óleo")),
    ),
    # ----------------------------------------------------------------- 18
    ReceitaB(
        "misto_quente", "Misto quente de {queijo|frio}", ("cafe", "lanche"),
        ("graos_e_cereais", "laticinios", "carnes"), ("misto", "sanduiche", "lanche", "pao"), "2",
        (_p("pao", _g("pao"), ("un", 4)),
         _p("queijo", QUEIJOS, ("g", 100)),
         _p("frio", FRIOS, ("g", 100), obrigatorio=False),
         _p("manteiga", _g("manteiga", "margarina"), ("g", 10), obrigatorio=False)),
        (_s("Corte {queijo} em fatias finas.", "queijo"),
         _s("Passe {manteiga} de um lado das fatias {pao_d}.", "manteiga"),
         _s("Monte os sanduíches: coloque {queijo} e {frio} entre as fatias {pao_d}.", "queijo", "frio"),
         _s("Monte os sanduíches: coloque {queijo} entre as fatias {pao_d}.", "queijo", sem=("frio",)),
         _s("Aqueça uma frigideira em fogo médio e doure cada sanduíche por 3 minutos de cada lado, até o queijo "
            "derreter.", "pao"),
         _s("Sirva em seguida.")),
    ),
    # ----------------------------------------------------------------- 19
    ReceitaB(
        "omelete_recheada", "Omelete de {recheio}", ("cafe", "almoco", "jantar", "lanche"),
        ("outros", "laticinios", "verduras_e_legumes"), ("omelete", "ovo", "ovos"), "2",
        (_p("ovo", OVO, ("un", 3)),
         _p("recheio", QUEIJOS | FRIOS | (LEGUMES_FRITADA - _g("cebola")), maximo=2)),
        (_s("@recheio", "recheio"),
         _s("Quebre {ovo} em uma tigela, junte uma pitada de sal e bata com um garfo.", "ovo"),
         _s("Aqueça uma frigideira antiaderente com um fio de óleo em fogo médio.", "ovo"),
         _s("Despeje os ovos e distribua {recheio} por cima. Tampe e cozinhe por 4 minutos.", "ovo", "recheio"),
         _s("Dobre a omelete ao meio, deixe mais 1 minuto no fogo e sirva em seguida.", "ovo")),
        (SAL, OLEO),
    ),
    # ----------------------------------------------------------------- 20
    ReceitaB(
        "cuscuz_recheado", "Cuscuz com {ovo|queijo|frio}", ("cafe", "lanche", "jantar"),
        ("graos_e_cereais", "outros", "laticinios"), ("cuscuz",), "2",
        (_p("cuscuz", _g("cuscuz"), ("g", 150)),
         _p("ovo", OVO, ("un", 2), obrigatorio=False),
         _p("queijo", QUEIJOS, ("g", 80), obrigatorio=False),
         _p("frio", FRIOS, ("g", 60), obrigatorio=False)),
        (_s("Em uma tigela, misture {cuscuz} com uma pitada de sal e um pouco de água, até hidratar bem.", "cuscuz"),
         _s("Deixe descansar por 5 minutos.", "cuscuz"),
         _s("Cozinhe no vapor, em panela com peneira ou cuscuzeira, por 12 minutos.", "cuscuz"),
         _s("Em uma frigideira com um fio de óleo, frite {ovo} por 3 minutos.", "ovo"),
         _s("Corte {queijo} em fatias.", "queijo"),
         _s("Sirva {cuscuz} quente, com {ovo|queijo|frio}.", "cuscuz")),
        (SAL, AGUA, _b("1 colher de sopa de óleo", "ovo")),
        ao_menos_um=("ovo", "queijo", "frio"),
    ),
    # ----------------------------------------------------------------- 21
    ReceitaB(
        "tapioca_recheada", "Tapioca de {queijo|frio|ovo}", ("cafe", "lanche"),
        ("graos_e_cereais", "laticinios", "outros"), ("tapioca",), "1",
        (_p("tapioca", _g("tapioca"), ("g", 80)),
         _p("queijo", QUEIJOS, ("g", 50), obrigatorio=False),
         _p("frio", FRIOS, ("g", 40), obrigatorio=False),
         _p("ovo", OVO, ("un", 1), obrigatorio=False)),
        (_s("Em uma frigideira com um fio de óleo, frite {ovo} por 3 minutos e reserve.", "ovo"),
         _s("Aqueça uma frigideira antiaderente em fogo médio.", "tapioca"),
         _s("Espalhe {tapioca} na frigideira, formando uma camada fina, e deixe por 2 minutos, até firmar.",
            "tapioca"),
         _s("Coloque {queijo|frio|ovo} sobre metade da tapioca e dobre ao meio.", "tapioca"),
         _s("Deixe mais 1 minuto no fogo e sirva em seguida.", "tapioca")),
        (_b("1 colher de sopa de óleo", "ovo"),),
        ao_menos_um=("queijo", "frio", "ovo"),
    ),
    # ----------------------------------------------------------------- 22
    ReceitaB(
        "bolo_simples", "Bolo simples", ("cafe", "lanche", "sobremesa"),
        ("graos_e_cereais", "outros", "laticinios"), ("bolo",), "8",
        (_p("farinha", FARINHAS, ("g", 250), excluir=_NAO_FARINHA_DE_TRIGO),
         _p("acucar", _g("acucar"), ("g", 150)),
         _p("ovo", OVO, ("un", 3)),
         _p("fermento", _g("fermento"), ("colher", 1)),
         _p("leite", _g("leite"), ("ml", 200), obrigatorio=False)),
        (_s("Preaqueça o forno a 180 graus e unte uma forma pequena com óleo.", "farinha"),
         _s("Em uma tigela, bata {ovo}, {acucar} e o óleo até formar um creme claro.", "ovo", "acucar"),
         _s("Junte {leite} aos poucos, mexendo.", "leite"),
         _s("Junte 100 ml de água aos poucos, mexendo.", sem=("leite",)),
         _s("Acrescente {farinha} peneirada aos poucos e misture até a massa ficar lisa.", "farinha"),
         _s("Por último, junte {fermento} e misture delicadamente.", "fermento"),
         _s("Despeje a massa na forma e asse por 35 minutos, até dourar e um palito sair limpo.", "farinha"),
         _s("Espere 10 minutos antes de desenformar.")),
        (_b("100 ml de óleo"), _b("100 ml de água", sem=("leite",))),
    ),
    # ----------------------------------------------------------------- 23
    ReceitaB(
        "bolo_cenoura", "Bolo de cenoura", ("cafe", "lanche", "sobremesa"),
        ("verduras_e_legumes", "graos_e_cereais", "outros"), ("bolo", "cenoura"), "8",
        (_p("cenoura", _g("cenoura"), ("un", 3)),
         _p("ovo", OVO, ("un", 3)),
         _p("farinha", FARINHAS, ("g", 250), excluir=_NAO_FARINHA_DE_TRIGO),
         _p("acucar", _g("acucar"), ("g", 200)),
         _p("fermento", _g("fermento"), ("colher", 1))),
        (_s("@cenoura", "cenoura"),
         _s("Preaqueça o forno a 180 graus e unte uma forma com óleo.", "farinha"),
         _s("No liquidificador, bata {cenoura}, {ovo} e o óleo até obter um creme liso.", "cenoura", "ovo"),
         _s("Em uma tigela, misture {farinha} e {acucar}.", "farinha", "acucar"),
         _s("Junte o creme do liquidificador e misture bem.", "farinha"),
         _s("Acrescente {fermento} e misture delicadamente.", "fermento"),
         _s("Despeje a massa na forma e asse por 40 minutos, até dourar e um palito sair limpo.", "farinha"),
         _s("Espere 10 minutos antes de desenformar.")),
        (_b("100 ml de óleo"),),
    ),
    # ----------------------------------------------------------------- 24
    ReceitaB(
        "bolo_banana", "Bolo de banana", ("cafe", "lanche", "sobremesa"),
        ("frutas", "graos_e_cereais", "outros"), ("bolo", "banana"), "8",
        (_p("banana", _g("banana"), ("un", 3)),
         _p("ovo", OVO, ("un", 2)),
         _p("farinha", FARINHAS, ("g", 200), excluir=_NAO_FARINHA_DE_TRIGO),
         _p("acucar", _g("acucar"), ("g", 100), obrigatorio=False),
         _p("fermento", _g("fermento"), ("colher", 1))),
        (_s("@banana", "banana"),
         _s("Preaqueça o forno a 180 graus e unte uma forma pequena com óleo.", "farinha"),
         _s("Amasse {banana} com um garfo.", "banana"),
         _s("Em uma tigela, misture {banana}, {ovo}, {acucar} e o óleo.", "banana", "ovo", "acucar"),
         _s("Em uma tigela, misture {banana}, {ovo} e o óleo.", "banana", "ovo", sem=("acucar",)),
         _s("Junte {farinha} aos poucos e mexa até a massa ficar lisa.", "farinha"),
         _s("Acrescente {fermento} e misture delicadamente.", "fermento"),
         _s("Despeje na forma e asse por 35 minutos, até dourar e um palito sair limpo.", "farinha"),
         _s("Espere 10 minutos antes de desenformar.")),
        (_b("80 ml de óleo"),),
    ),
    # ----------------------------------------------------------------- 25
    ReceitaB(
        "pudim_leite", "Pudim de leite", ("sobremesa",),
        ("laticinios", "outros"), ("pudim",), "6",
        (_p("leite", _g("leite"), ("ml", 500)),
         _p("ovo", OVO, ("un", 3)),
         _p("acucar", _g("acucar"), ("g", 200))),
        (_s("Em uma panela, derreta 100 g {acucar_d} em fogo médio, sem mexer, por 5 minutos, até virar uma calda "
            "dourada. Despeje em uma forma e reserve.", "acucar"),
         _s("No liquidificador, bata {leite}, {ovo} e o restante {acucar_d} por 2 minutos.", "leite", "ovo", "acucar"),
         _s("Despeje a mistura na forma com a calda e cubra com papel-alumínio.", "leite"),
         _s("Cozinhe em banho-maria, no forno a 180 graus, por 50 minutos, até firmar.", "leite"),
         _s("Espere esfriar e leve à geladeira por 3 horas antes de desenformar.", "leite")),
    ),
    # ----------------------------------------------------------------- 26
    ReceitaB(
        "panqueca_banana", "Panqueca de banana", ("cafe", "lanche", "sobremesa"),
        ("frutas", "graos_e_cereais", "outros"), ("panqueca", "banana"), "2",
        (_p("banana", _g("banana"), ("un", 2)),
         _p("ovo", OVO, ("un", 2)),
         _p("farinha", FARINHAS | _g("aveia"), ("g", 100), excluir=_NAO_FARINHA_DE_TRIGO.replace("|aveia", "")),
         _p("leite", _g("leite"), ("ml", 100), obrigatorio=False)),
        (_s("@banana", "banana"),
         _s("Amasse {banana} com um garfo.", "banana"),
         _s("Em uma tigela, misture {banana}, {ovo}, {farinha} e {leite}, até formar uma massa lisa.",
            "banana", "ovo", "farinha", "leite"),
         _s("Em uma tigela, misture {banana}, {ovo} e {farinha}, até formar uma massa lisa.",
            "banana", "ovo", "farinha", sem=("leite",)),
         _s("Aqueça uma frigideira antiaderente com um fio de óleo.", "banana"),
         _s("Despeje porções da massa e doure por 2 minutos de cada lado.", "banana"),
         _s("Sirva em seguida.")),
        (OLEO,),
    ),
    # ----------------------------------------------------------------- 27
    ReceitaB(
        "mingau_aveia", "Mingau de {aveia|fruta}", ("cafe", "lanche", "sobremesa"),
        ("graos_e_cereais", "laticinios", "frutas"), ("mingau", "aveia"), "2",
        (_p("aveia", _g("aveia"), ("g", 60)),
         _p("leite", _g("leite"), ("ml", 500)),
         _p("fruta", FRUTAS_MINGAU, ("un", 1), obrigatorio=False),
         _p("adocante", ADOCANTES, ("colher", 1), obrigatorio=False)),
        (_s("@fruta", "fruta"),
         _s("Em uma panela, misture {aveia} e {leite}.", "aveia", "leite"),
         _s("Leve ao fogo médio e cozinhe por 8 minutos, mexendo sempre, até engrossar.", "aveia"),
         _s("Adoce com {adocante} e misture.", "adocante"),
         _s("Sirva quente com {fruta} por cima.", "fruta"),
         _s("Sirva quente.", sem=("fruta",))),
    ),
    # ----------------------------------------------------------------- 28
    ReceitaB(
        "arroz_doce", "Arroz-doce", ("sobremesa",),
        ("graos_e_cereais", "laticinios"), ("arroz doce", "arroz-doce"), "6",
        (_p("arroz", _g("arroz"), ("g", 150)),
         _p("leite", _g("leite"), ("ml", 750)),
         _p("acucar", _g("acucar"), ("g", 100)),
         _p("canela", _g("canela"), ("gosto",), obrigatorio=False)),
        (_s("Cozinhe {arroz} em 2 xícaras de água por 10 minutos, até quase secar.", "arroz"),
         _s("Junte {leite} e {acucar} e cozinhe em fogo baixo por 25 minutos, mexendo de vez em quando, até ficar "
            "cremoso.", "arroz", "leite", "acucar"),
         _s("Polvilhe {canela} e sirva morno ou gelado.", "canela"),
         _s("Sirva morno ou gelado.", sem=("canela",))),
        (AGUA,),
    ),
    # ----------------------------------------------------------------- 29
    ReceitaB(
        "doce_abobora", "Doce de {abobora}", ("sobremesa",),
        ("verduras_e_legumes", "outros"), ("doce", "abobora", "jerimum"), "6",
        (_p("abobora", _g("abobora"), ("g", 500)),
         _p("acucar", _g("acucar"), ("g", 200)),
         _p("canela", _g("canela", "cravo"), ("gosto",), obrigatorio=False)),
        (_s("@abobora", "abobora"),
         _s("Em uma panela, misture {abobora} e {acucar} e deixe descansar por 20 minutos, até soltar líquido.",
            "abobora", "acucar"),
         _s("Leve ao fogo médio e cozinhe por 35 minutos, mexendo de vez em quando, até a abóbora desmanchar e "
            "formar uma calda grossa.", "abobora"),
         _s("Acrescente {canela} e misture.", "canela"),
         _s("Deixe esfriar e sirva.")),
    ),
    # ----------------------------------------------------------------- 30
    ReceitaB(
        "fruta_assada", "{fruta} assada", ("sobremesa", "lanche", "cafe"),
        ("frutas",), ("assada", "assado", "fruta"), "2",
        (_p("fruta", FRUTAS_FEMININAS, ("un", 2)),
         _p("adocante", ADOCANTES, ("colher", 1), obrigatorio=False),
         _p("canela", _g("canela"), ("gosto",), obrigatorio=False)),
        (_s("Preaqueça o forno a 180 graus.", "fruta"),
         _s("@fruta", "fruta"),
         _s("Disponha {fruta} em um refratário.", "fruta"),
         _s("Polvilhe {adocante} e {canela} por cima.", "adocante", "canela"),
         _s("Polvilhe {adocante} por cima.", "adocante", sem=("canela",)),
         _s("Polvilhe {canela} por cima.", "canela", sem=("adocante",)),
         _s("Asse por 25 minutos, até ficar macia e dourada.", "fruta"),
         _s("Sirva morna.")),
    ),
)

assert len(CATALOGO) == 30, "o plano B deve ter exatamente 30 receitas"
assert len({r.chave for r in CATALOGO}) == 30


# --------------------------------------------------------------------------- #
# Texto
# --------------------------------------------------------------------------- #
_RE_SEM_PREPARO = re.compile(r"\b(molho|extrato|polpa|enlatad\w*|lata|pronto|pronta|seco|seca|desidratad\w*)\b")


def _precisa_preparo(item: Item) -> bool:
    return not _RE_SEM_PREPARO.search(normalizar_texto(item.nome))


def _frase_preparo(itens: Sequence[Item]) -> str:
    """'Descasque e pique a cebola. Lave e corte o tomate em cubos.' Itens prontos (molho, extrato) não têm preparo."""
    itens = [i for i in itens if _precisa_preparo(i)]
    descascar_picar = [i for i in itens if i.conjunto & _g("cebola", "alho")]
    descascar_cortar = [i for i in itens if i.conjunto & (_g("cenoura", "abobora", "beterraba", "chuchu") | TUBERCULOS)]
    frutas = [i for i in itens if i.conjunto & FRUTAS]
    folhas = [i for i in itens if i.conjunto & FOLHAS]
    usados = {id(i) for g in (descascar_picar, descascar_cortar, frutas, folhas) for i in g}
    lavar_cortar = [i for i in itens if id(i) not in usados and i.conjunto & VEGETAIS]
    frases: List[str] = []
    if descascar_picar:
        frases.append(f"Descasque e pique {_artigos(descascar_picar)}.")
    if descascar_cortar:
        frases.append(f"Descasque e corte {_artigos(descascar_cortar)} em cubos.")
    if frutas:
        frases.append(f"Lave, descasque e corte {_artigos(frutas)} em fatias.")
    if folhas:
        frases.append(f"Lave e rasgue {_artigos(folhas)}.")
    if lavar_cortar:
        frases.append(f"Lave e corte {_artigos(lavar_cortar)} em pedaços.")
    return " ".join(frases)


def _de_artigo(itens: Sequence[Item]) -> str:
    return _lista([_do(i.nome) for i in itens])


_RE_MARCA = re.compile(r"\{([^}]+)\}")


def _render_passo(texto: str, escolhidos: Dict[str, List[Item]]) -> str:
    if texto.startswith("@"):           # passo só de preparo: '@tomate'
        texto = "{" + texto + "}"

    def trocar(m):
        chave = m.group(1)
        if chave.startswith("@"):
            return _frase_preparo(escolhidos.get(chave[1:], []))
        if "|" in chave:
            return _lista([i.nome for c in chave.split("|") for i in escolhidos.get(c, [])])
        if chave.endswith("_n"):
            return _lista([i.nome for i in escolhidos.get(chave[:-2], [])])
        if chave.endswith("_d"):
            return _de_artigo(escolhidos.get(chave[:-2], []))
        return _artigos(escolhidos.get(chave, []))
    return re.sub(r"\s+", " ", _RE_MARCA.sub(trocar, texto)).strip()


def _render_titulo(fmt: str, escolhidos: Dict[str, List[Item]]) -> str:
    def trocar(m):
        expr = m.group(1)
        mais = expr.startswith("+")
        nomes = [i.nome for c in expr.lstrip("+").split("|") for i in escolhidos.get(c, [])]
        if not nomes:
            return ""
        return (" e " if mais else "") + _lista(nomes)
    return _cap(re.sub(r"\s+", " ", _MARCA_TITULO.sub(trocar, fmt)).strip())


_MARCA_TITULO = _RE_MARCA


# --------------------------------------------------------------------------- #
# Quantidades (nunca acima do que o usuário tem)
# --------------------------------------------------------------------------- #
def _linha(item: Item, qtd: Tuple) -> Tuple[Optional[str], float]:
    """(linha '- 250 g de carne moída', fração do necessário que o usuário tem). Fração < 1 = quantidade reduzida."""
    tipo = qtd[0]
    medida = tipo_de_medida(item.nome)
    if tipo == "gosto":
        return f"- {item.nome} a gosto", 1.0
    if tipo == "colher":
        n = int(qtd[1])
        return f"- {n} {'colher' if n == 1 else 'colheres'} de sopa de {item.nome}", 1.0
    if tipo == "dentes":
        return f"- {int(qtd[1])} dentes de {item.nome}", 1.0
    if tipo == "padrao":
        return _linha_item(item), 1.0
    if tipo == "un|g":   # contável (batata) ou peso (mandioca, inhame)
        if medida == CONTAVEL:
            return _linha(item, ("un", qtd[1]))
        return _linha(item, ("g", qtd[2]))
    disp = _disponivel(item)
    if tipo == "un":
        if medida != CONTAVEL:    # 'molho de tomate', 'berinjela'...: a quantidade típica da tabela
            return _linha_item(item), 1.0
        n = int(qtd[1])
        fracao = 1.0
        if disp and disp[1] == "unidades" and disp[0] < n:
            fracao, n = disp[0] / n, max(1, int(disp[0]))
        return (f"- {n} {item.nome}" if n == 1 else f"- {n} {_no_numero(item.nome, n)}"), fracao
    # g / ml
    if medida == CONTAVEL:        # 'bife', 'pão': contável, não se pesa
        return _linha_item(item), 1.0
    n = float(qtd[1])
    fracao = 1.0
    if disp and disp[1] == tipo and disp[0] < n:
        fracao, n = disp[0] / n, _baixo(disp[0])
    return f"- {int(n)} {tipo} de {item.nome}", fracao


# --------------------------------------------------------------------------- #
# Itens que faltam (modo "gerar para o usuário aprovar")
# --------------------------------------------------------------------------- #
MAX_FALTANDO = 4
_ORDEM_FALTA = ("lasanha", "macarrao", "carne", "bife", "queijo", "frango", "peixe", "ovo", "leite", "farinha", "acucar",
                "fermento", "tomate", "cebola", "alho", "batata", "abobrinha", "cenoura", "abobora", "banana", "maca",
                "arroz", "pao", "cuscuz", "tapioca", "aveia", "presunto", "brocolis")
_NOME_FALTA = {
    "lasanha": "massa de lasanha", "macarrao": "macarrão", "carne": "carne moída", "bife": "bife",
    "queijo": "queijo mussarela", "frango": "frango", "peixe": "peixe", "ovo": "ovo", "leite": "leite",
    "farinha": "farinha de trigo", "acucar": "açúcar", "fermento": "fermento", "tomate": "tomate", "cebola": "cebola",
    "alho": "alho", "batata": "batata", "abobrinha": "abobrinha", "cenoura": "cenoura", "abobora": "abóbora",
    "banana": "banana", "maca": "maçã", "arroz": "arroz", "pao": "pão", "cuscuz": "cuscuz", "tapioca": "tapioca",
    "aveia": "aveia", "presunto": "presunto", "brocolis": "brócolis",
}


def _item_que_falta(papel: Papel, selecionados: Set[str], vetados: Set[str], ja: Set[str]) -> Optional[Item]:
    """Um item padrão para o papel (ex.: 'queijo mussarela'), que o usuário não tem. None se nada serve."""
    from receitas.esqueleto import _tokens_linha
    for token in _ORDEM_FALTA:
        if token not in papel.grupo or token in vetados or token in selecionados:
            continue
        nome = _NOME_FALTA[token]
        if token == "carne" and papel.excluir and "moid" in papel.excluir:
            nome = "bife"
        if nome in ja or _conflitos(selecionados | set(_tokens_linha(nome))):
            continue
        return Item(nome, nome, tuple(_tokens_linha(nome)), None, None)
    return None


# --------------------------------------------------------------------------- #
# Montagem
# --------------------------------------------------------------------------- #
def _rank_item(papel: Papel, item: Item) -> int:
    return 0 if papel.preferir and re.search(papel.preferir, normalizar_texto(item.nome)) else 1


def _escolher_papeis(receita: ReceitaB, itens: Sequence[Item], vetados: Set[str], preferidos: Set[str],
                     permitir_faltas: bool = False):
    """(itens de cada papel, tokens usados, nomes dos itens que faltam). Papéis None = o inventário não permite.

    Com permitir_faltas, o papel obrigatório sem item no inventário recebe um item padrão (e entra em 'faltando').
    """
    faltando: List[str] = []
    usados: Set[int] = set()
    selecionados: Set[str] = set()
    escolhidos: Dict[str, List[Item]] = {}
    for papel in receita.papeis:
        candidatos = []
        for i, it in enumerate(itens):
            if i in usados or not (it.conjunto & papel.grupo) or it.conjunto & vetados:
                continue
            if it.conjunto - papel.grupo:       # 'pão de queijo' não é queijo; 'molho de tomate' é tomate
                continue
            nome = normalizar_texto(it.nome)
            if papel.excluir and re.search(papel.excluir, nome):
                continue
            candidatos.append(i)
        candidatos.sort(key=lambda i: (
            not (itens[i].conjunto & preferidos),
            _rank_item(papel, itens[i]),
            not (itens[i].dias is not None and itens[i].dias <= 7),
            i))
        pegos: List[Item] = []
        for i in candidatos:
            if len(pegos) >= papel.maximo:
                break
            novos = selecionados | itens[i].conjunto
            if _conflitos(novos):
                continue
            usados.add(i)
            selecionados = novos
            pegos.append(itens[i])
        if papel.obrigatorio and permitir_faltas:
            while len(pegos) < papel.minimo:
                falta = _item_que_falta(papel, selecionados, vetados, {i.nome for i in pegos})
                if falta is None:
                    break
                selecionados = selecionados | falta.conjunto
                pegos.append(falta)
                faltando.append(falta.nome)
        if papel.obrigatorio and len(pegos) < papel.minimo:
            return None, set(), []
        if pegos:
            escolhidos[papel.chave] = pegos
    if receita.ao_menos_um and not any(c in escolhidos for c in receita.ao_menos_um):
        if not permitir_faltas:
            return None, set(), []
        for chave in receita.ao_menos_um:
            papel = next(x for x in receita.papeis if x.chave == chave)
            falta = _item_que_falta(papel, selecionados, vetados, set())
            if falta is not None:
                escolhidos[chave] = [falta]
                selecionados = selecionados | falta.conjunto
                faltando.append(falta.nome)
                break
        else:
            return None, set(), []
    return escolhidos, selecionados, faltando


def _montar_receita(receita: ReceitaB, itens: Sequence[Item], vetados: Set[str], preferidos: Set[str],
                    permitir_faltas: bool = False) -> Optional[PratoB]:
    escolhidos, tokens, faltando = _escolher_papeis(receita, itens, vetados, preferidos, permitir_faltas)
    if escolhidos is None:
        return None
    if len(faltando) > MAX_FALTANDO:
        return None

    linhas: List[str] = []
    ordem_itens: List[Item] = []
    for papel in receita.papeis:
        for item in escolhidos.get(papel.chave, []):
            linha, fracao = _linha(item, papel.qtd)
            if linha is None or fracao < 0.5:      # o usuário tem menos da metade do necessário
                if papel.obrigatorio:
                    return None
                escolhidos[papel.chave] = [i for i in escolhidos[papel.chave] if i is not item]
                continue
            linhas.append(linha)
            ordem_itens.append(item)
        if papel.chave in escolhidos and not escolhidos[papel.chave]:
            del escolhidos[papel.chave]
    if receita.ao_menos_um and not any(c in escolhidos for c in receita.ao_menos_um):
        return None

    passos: List[str] = []
    for passo in receita.passos:
        if any(p not in escolhidos for p in passo.precisa) or any(p in escolhidos for p in passo.sem):
            continue
        texto = _render_passo(passo.texto, escolhidos)
        if texto:
            passos.append(texto)
    if len(passos) < 3:
        return None
    for b in receita.basicos:
        if all(p in escolhidos for p in b.precisa) and not any(p in escolhidos for p in b.sem):
            linhas.append("- " + b.linha)

    titulo = _render_titulo(receita.titulo, escolhidos)
    tokens = {t for i in ordem_itens for t in i.tokens}
    return PratoB(
        chave=f"b_{receita.chave}", titulo=titulo,
        tempo_min=tempo_real_dos_passos(passos, receita.extra_min), porcoes=receita.porcoes,
        ingredientes=linhas, passos=passos, originais=[i.original for i in ordem_itens], alimentos=tokens,
        pontos=len(ordem_itens), chave_catalogo=receita.chave, refeicoes=receita.refeicoes,
        faltando=list(faltando),
    )


# --------------------------------------------------------------------------- #
# Escolha pelo pedido
# --------------------------------------------------------------------------- #
_CATEGORIA_PARA_REFEICAO = {
    "Café da manhã": "cafe", "Almoço": "almoco", "Jantar": "jantar", "Lanche": "lanche", "Sobremesa": "sobremesa",
}
_NEGACOES = {"sem", "nao", "evitar", "evite", "odeio", "alergia", "alergico", "alergica", "intolerante", "nem"}


def _pedido_cita(pedido_norm: str, palavra: str) -> bool:
    return bool(re.search(rf"\b{re.escape(palavra)}s?\b", pedido_norm))


def _preferidos_e_vetados(pedido: str, restricoes: Optional[str], itens: Sequence[Item]):
    """(alimentos pedidos que o usuário tem, alimentos vetados por restrição ou negados no pedido)."""
    from receitas.validador import ALIMENTOS
    vetados = set(alimentos_proibidos(pedido, restricoes))
    presentes = {t for i in itens for t in i.tokens}
    palavras = re.findall(r"[a-z]+", normalizar_texto(pedido or ""))
    preferidos: Set[str] = set()
    for pos, palavra in enumerate(palavras):
        c = _canon(palavra)
        if c not in ALIMENTOS:
            continue
        if any(w in _NEGACOES for w in palavras[max(0, pos - 3):pos]):
            vetados.add(c)
        elif c in presentes:
            preferidos.add(c)
    return preferidos - vetados, vetados


def escolher_plano_b(
    ativos: Sequence[Dict],
    pedido: str,
    tempo: Optional[str] = None,
    restricoes: Optional[str] = None,
    urgentes: Sequence[str] = (),
    evitar: Optional[str] = None,
    limite: int = MAX_CANDIDATOS,
    permitir_faltas: bool = False,
) -> List[PratoB]:
    """Receitas do catálogo que o inventário permite, da que melhor responde ao pedido para a pior.

    ativos: itens do inventário sem os vencidos (como devolve gerador.preparar_inventario).
    A refeição citada no pedido (café da manhã, almoço, sobremesa...) e o prato citado (lasanha, bolo...) escolhem
    as receitas; os alimentos citados e os que vencem primeiro dão pontos; o tempo máximo da tela favorece as
    receitas que realmente cabem nele (o tempo mostrado é sempre o real).

    permitir_faltas: devolve SÓ receitas que precisam de itens que o usuário não tem (cada uma com a lista em
    `faltando`), para o usuário aprovar ou não. Quanto menos itens faltam, melhor; o prato pedido vem primeiro.
    """
    itens = _itens_do_inventario(ativos)
    if not itens:
        return []
    pedido_norm = normalizar_texto(pedido or "")
    preferidos, vetados = _preferidos_e_vetados(pedido, restricoes, itens)
    refeicao = _CATEGORIA_PARA_REFEICAO.get(inferir_categoria(pedido))
    tempo_max = {"15": 15, "30": 30, "45": 45, "60": 60}.get(str(tempo or ""))
    from receitas.esqueleto import _tokens_linha
    tokens_urgentes: Set[str] = set()
    for nome in urgentes:
        tokens_urgentes |= set(_tokens_linha(nome))

    montadas: List[Tuple[int, PratoB]] = []
    for ordem, receita in enumerate(CATALOGO):
        prato = _montar_receita(receita, itens, vetados, preferidos, permitir_faltas)
        if prato is None:
            continue
        if permitir_faltas and not prato.faltando:
            continue
        prato.casa_pedido = any(_pedido_cita(pedido_norm, p) for p in receita.palavras)
        if permitir_faltas and not prato.casa_pedido and len(prato.faltando) >= len(prato.originais) + len(prato.faltando):
            continue      # sem o prato pedido, só vale se o usuário tem pelo menos um item da receita
        montadas.append((ordem, prato))

    anterior = normalizar_texto(evitar or "").strip()
    escolhidas: List[Tuple[Tuple, PratoB]] = []
    tem_da_refeicao = bool(refeicao) and any(refeicao in p.refeicoes for _, p in montadas)
    for ordem, prato in montadas:
        titulo_norm = normalizar_texto(prato.titulo)
        if anterior and (titulo_norm == anterior or titulo_norm in anterior):
            continue
        da_refeicao = refeicao in prato.refeicoes if refeicao else True
        if not da_refeicao and not prato.casa_pedido and (
                tem_da_refeicao or refeicao in ("sobremesa", "cafe")):
            continue      # sobremesa e café da manhã nunca recebem prato de almoço
        if refeicao == "lanche" and not prato.casa_pedido and not (prato.alimentos & _g("pao", "tapioca")):
            continue      # lanche pede pão ou tapioca (regras.py): os outros pratos seriam recusados
        pontos = 0
        pontos += 1000 if prato.casa_pedido else 0
        if refeicao in ("almoco", "jantar") and not (prato.alimentos & _PROTEINAS_DE_REFEICAO):
            pontos -= 300     # almoço e jantar pedem proteína; sem ela só entra se não houver outra opção
        pontos += 60 * len(prato.alimentos & preferidos) - 80 * len(preferidos - prato.alimentos)
        pontos += 40 * len(prato.alimentos & tokens_urgentes)
        pontos += 5 * prato.pontos
        pontos -= 250 * len(prato.faltando)
        if refeicao in ("almoco", "jantar") and prato.refeicoes and "lanche" in prato.refeicoes:
            pontos -= 10
        if tempo_max:
            pontos += 150 if prato.tempo_min <= tempo_max else -min(200, prato.tempo_min - tempo_max)
        escolhidas.append(((-pontos, ordem), prato))
    escolhidas.sort(key=lambda x: x[0])
    return [p for _, p in escolhidas[:max(1, limite)]]


# --------------------------------------------------------------------------- #
# Junção com as receitas de reserva do esqueleto
# --------------------------------------------------------------------------- #
def unir_com_esqueleto(catalogo: Sequence[PratoB], esqueleto: Sequence[Prato], pedido: str) -> List[Prato]:
    """Ordem de tentativa do plano B:

      1. receitas do catálogo que são o prato pedido (lasanha, bolo, pizza...);
      2. se o pedido é de um prato que só o esqueleto monta (salada, risoto, vitamina...), as dele;
      3. o resto do catálogo, da que melhor responde ao pedido para a pior;
      4. as receitas de reserva do esqueleto que sobraram.
    """
    casam = [p for p in catalogo if p.casa_pedido]
    resto = [p for p in catalogo if not p.casa_pedido]
    do_esqueleto = [a for a in arquetipos_do_pedido(pedido) if a.chave in DEFINICOES]
    ordem: List[Prato] = list(casam)
    if do_esqueleto and not casam:
        ordem += list(esqueleto)
    ordem += resto
    ordem += [p for p in esqueleto if p not in ordem]
    return ordem
