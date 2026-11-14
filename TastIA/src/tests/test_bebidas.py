"""Testes do módulo de bebidas (catálogo, regras gastronômicas, recomendador e rotas).

Usam a base comum do tests/conftest.py e rodam SEM baixar modelos e SEM internet:
  - o banco é um SQLite temporário (fixtures `banco_temporario`, `conn`);
  - o recomendador usa o motor léxico ou o MotorFalso (fixtures `recomendador_lexico`
    e `recomendador_falso`), nunca o MiniLM;
  - as rotas são testadas com o `client` / `client_logado` e com `injetar_recomendador`.

Como rodar (na raiz do projeto):
  python -m pytest tests/test_bebidas.py -v
"""
import time
from collections import Counter

import pytest

from bebidas.catalogo import (
    CATALOGO, PRATOS, SABORES, TEMPERATURAS, TIPOS, _b, listar_bebidas, validar_catalogo,
)
from bebidas.recomendador import (
    MAX_MESMO_TIPO, MotorLexico, Recomendador, documento_da_bebida,
)
from bebidas.regras import (
    Filtros, avaliar_regras, interpretar_temperatura, interpretar_tipo,
    perfil_de_ocasiao, perfil_do_prato, texto_expandido,
)


# --------------------------------------------------------------------------- #
# Apoio
# --------------------------------------------------------------------------- #
def _bebida(id="x", nome="Bebida X", tipo="suco", corpo=1, docura=1, acidez=2, gas=False,
            temperatura="gelada", sabores=("citrico", "refrescante"), combina=(), evita=(),
            descricao="Bebida de teste.", **extra):
    """Cria uma bebida válida para testes isolados das regras."""
    b = _b(id, nome, tipo, corpo, docura, acidez, gas, temperatura,
           list(sabores), list(combina), list(evita), descricao)
    b.update(extra)
    return b


def _recomendador_pequeno(bebidas):
    """Recomendador real (motor léxico) sobre um catálogo reduzido."""
    motor = MotorLexico([documento_da_bebida(b) for b in bebidas])
    return Recomendador(motor=motor, catalogo=bebidas)


class EspiaoRecomendador:
    """Guarda os argumentos recebidos e devolve uma resposta fixa (para testar a rota)."""

    def __init__(self, resposta=None, erro=None):
        self.chamadas = []
        self.resposta = resposta or {
            "bebidas": [{"id": "suco_laranja", "nome": "Suco de Laranja Natural",
                         "justificativa": "Combina com o prato."}],
            "perfil_prato": [], "ocasioes": [], "filtros": [], "aviso": None, "motor": "espiao",
        }
        self.erro = erro

    def sugerir(self, **kwargs):
        self.chamadas.append(kwargs)
        if self.erro:
            raise self.erro
        return self.resposta


def _inserir_receita(conn, usuario_id, pedido="almoço", conteudo="# Receita de teste"):
    cur = conn.execute(
        "INSERT INTO receitas (usuario_id, pedido, conteudo) VALUES (?, ?, ?)",
        (usuario_id, pedido, conteudo),
    )
    conn.commit()
    return cur.lastrowid


def _bebidas_salvas(conn, usuario_id=None):
    sql = "SELECT * FROM bebidas_sugeridas"
    args = ()
    if usuario_id is not None:
        sql += " WHERE usuario_id = ?"
        args = (usuario_id,)
    return conn.execute(sql + " ORDER BY id", args).fetchall()


# =========================================================================== #
# 1. CATÁLOGO
# =========================================================================== #
def test_catalogo_tem_40_bebidas():
    assert len(CATALOGO) == 40


def test_catalogo_passa_na_validacao_propria():
    assert validar_catalogo() == []


def test_catalogo_ids_unicos_e_nomes_unicos():
    ids = [b["id"] for b in CATALOGO]
    nomes = [b["nome"] for b in CATALOGO]
    assert len(ids) == len(set(ids))
    assert len(nomes) == len(set(nomes))


CAMPOS_OBRIGATORIOS = (
    "id", "nome", "tipo", "alcool", "teor", "corpo", "docura", "acidez", "gas",
    "temperatura", "sabores", "combina", "evita", "descricao", "lactose", "cafeina",
)


@pytest.mark.parametrize("bebida", CATALOGO, ids=lambda b: b["id"])
def test_cada_bebida_tem_campos_padronizados(bebida):
    for campo in CAMPOS_OBRIGATORIOS:
        assert campo in bebida, f"{bebida['id']} sem o campo '{campo}'"
    assert bebida["tipo"] in TIPOS
    assert bebida["temperatura"] in TEMPERATURAS
    assert bebida["nome"].strip() and bebida["descricao"].strip()
    assert bebida["corpo"] in (1, 2, 3)
    assert bebida["docura"] in (0, 1, 2)


@pytest.mark.parametrize("bebida", CATALOGO, ids=lambda b: b["id"])
def test_tags_da_bebida_usam_vocabulario_padrao(bebida):
    assert set(bebida["sabores"]) <= set(SABORES), "sabor fora do vocabulário"
    assert set(bebida["combina"]) <= set(PRATOS), "tag 'combina' fora do vocabulário"
    assert set(bebida["evita"]) <= set(PRATOS), "tag 'evita' fora do vocabulário"
    assert bebida["sabores"], "toda bebida precisa de ao menos um sabor"
    assert not (set(bebida["combina"]) & set(bebida["evita"])), "combina e evita ao mesmo tempo"


def test_catalogo_atual_e_so_sem_alcool():
    assert all(not b["alcool"] and b["teor"] == 0 for b in CATALOGO)


def test_catalogo_cobre_os_tipos_e_temperaturas():
    assert {b["tipo"] for b in CATALOGO} >= {"suco", "cha", "agua", "vitamina"}
    assert {b["temperatura"] for b in CATALOGO} >= {"gelada", "quente"}


def test_validar_catalogo_detecta_problemas():
    ok = _bebida(id="a")
    repetida = _bebida(id="a", nome="Outra")
    tipo_ruim = _bebida(id="b", tipo="cerveja")
    temp_ruim = _bebida(id="c", temperatura="fervendo")
    alcoolica = _bebida(id="d", alcool=True, teor=5)
    erros = validar_catalogo([ok, repetida, tipo_ruim, temp_ruim, alcoolica])
    texto = " | ".join(erros)
    assert "a: id repetido" in texto
    assert "b: tipo inválido" in texto
    assert "c: temperatura inválida" in texto
    assert "d: catálogo restrito" in texto


def test_listar_bebidas_devolve_copia_do_catalogo():
    lista = listar_bebidas()
    assert len(lista) == len(CATALOGO)
    lista.pop()
    assert len(CATALOGO) == 40, "alterar a lista devolvida não pode mexer no catálogo"


def test_documento_da_bebida_descreve_a_bebida():
    b = _bebida(nome="Suco Teste", gas=True, combina=["frito"], temperatura="gelada")
    doc = documento_da_bebida(b)
    assert "Suco Teste" in doc
    assert "sem álcool" in doc
    assert "gaseificada" in doc
    assert "combina com frito" in doc
    assert "gelada" in doc


# =========================================================================== #
# 2. PERFIL DO PRATO E DA OCASIÃO
# =========================================================================== #
@pytest.mark.parametrize("texto, esperadas", [
    ("frango apimentado com pimenta malagueta", {"apimentado", "aves"}),
    ("pastel frito", {"frito"}),
    ("bolo de chocolate", {"doce", "chocolate"}),
    ("salada leve de folhas", {"leve", "salada"}),
    ("feijoada", {"porco", "brasileira"}),
    ("macarrão ao molho de tomate", {"massa", "tomate"}),
    ("peixe grelhado", {"peixe", "grelhado"}),
    ("lanche leve", {"leve", "lanche"}),
    ("omelete com tomate", {"ovo"}),
])
def test_perfil_do_prato_detecta_as_tags(texto, esperadas):
    assert esperadas <= set(perfil_do_prato(texto))


def test_perfil_do_prato_ignora_acento_e_maiuscula():
    assert "apimentado" in perfil_do_prato("FRANGO APIMENTADO")
    assert "frito" in perfil_do_prato("Frango Frito")


def test_pimenta_do_reino_nao_deixa_o_prato_apimentado():
    assert "apimentado" not in perfil_do_prato("arroz temperado com pimenta do reino")
    assert "apimentado" in perfil_do_prato("arroz com pimenta malagueta")
    assert "apimentado" not in perfil_do_prato("tempero de sal e pimenta-do-reino")


def test_palavra_porcoes_nao_vira_porco():
    assert "porco" not in perfil_do_prato("receita de 4 porções")


def test_perfil_do_prato_texto_vazio_ou_nulo():
    assert perfil_do_prato("") == []
    assert perfil_do_prato(None) == []


def test_perfil_do_prato_nao_repete_tags():
    tags = perfil_do_prato("frango frito, frito de novo e pastel frito")
    assert len(tags) == len(set(tags))


@pytest.mark.parametrize("texto, ocasiao", [
    ("dia de calor na praia", "calor"),
    ("noite fria de inverno", "frio"),
    ("festa de aniversário", "celebracao"),
    ("jantar romântico", "romantico"),
    ("happy hour com amigos", "casual"),
])
def test_perfil_de_ocasiao(texto, ocasiao):
    assert ocasiao in perfil_de_ocasiao(texto)


def test_perfil_de_ocasiao_sem_pistas():
    assert perfil_de_ocasiao("almoço de terça") == []
    assert perfil_de_ocasiao("") == []


def test_texto_expandido_acrescenta_descricao_das_tags():
    texto = texto_expandido("frango", ["apimentado"])
    assert texto.startswith("frango")
    assert "pimenta" in texto
    assert texto_expandido("frango", []) == "frango"
    assert texto_expandido("frango", ["tag_inexistente"]) == "frango"


# =========================================================================== #
# 3. REGRAS GASTRONÔMICAS
# =========================================================================== #
def test_regra_apimentado_favorece_doce_e_gelada():
    b = _bebida(docura=1, temperatura="gelada")
    pontos, motivos, alertas = avaliar_regras(b, ["apimentado"])
    assert pontos > 0
    assert "a doçura suave ameniza a ardência da pimenta" in motivos
    assert alertas == []


def test_motivos_vem_ordenados_do_mais_forte_para_o_mais_fraco():
    b = _bebida(docura=1, temperatura="gelada")
    _, motivos, _ = avaliar_regras(b, ["apimentado"])
    assert motivos[0] == "a doçura suave ameniza a ardência da pimenta"   # peso 1.0
    assert motivos.index("é servida bem gelada e refresca a boca") > 0     # peso 0.6


def test_afinidade_do_catalogo_soma_pontos():
    com = _bebida(combina=["peixe"])
    sem = _bebida(combina=[])
    p_com, _, _ = avaliar_regras(com, ["peixe"])
    p_sem, _, _ = avaliar_regras(sem, ["peixe"])
    assert round(p_com - p_sem, 6) == 0.5


def test_afinidade_do_catalogo_vira_justificativa_quando_nenhuma_regra_a_explica():
    # "brasileira" não tem regra específica: a única explicação é a afinidade do catálogo
    b = _bebida(combina=["brasileira"])
    _, motivos, _ = avaliar_regras(b, ["brasileira"])
    assert "costuma ser servida com comida brasileira" in motivos


def test_afinidade_do_catalogo_tem_limite_de_3_tags():
    tags = ["peixe", "massa", "queijo", "salada", "ovo"]
    com = _bebida(combina=tags)
    sem = _bebida(combina=[])
    for n in (1, 2, 3, 4, 5):
        p_com, _, _ = avaliar_regras(com, tags[:n])
        p_sem, _, _ = avaliar_regras(sem, tags[:n])
        assert round(p_com - p_sem, 6) == 0.5 * min(n, 3)


def test_evita_gera_penalidade_e_alerta():
    com_evita = _bebida(evita=["doce"])
    sem_evita = _bebida(evita=[])
    p1, _, alertas = avaliar_regras(com_evita, ["doce"])
    p2, _, _ = avaliar_regras(sem_evita, ["doce"])
    assert round(p2 - p1, 6) == 0.8
    assert any(a.startswith("costuma brigar com") and "sobremesas" in a for a in alertas)


def test_penalidade_de_evita_tem_limite_de_2_tags():
    tags = ["doce", "frito", "peixe"]
    com = _bebida(evita=tags)
    sem = _bebida(evita=[])
    for n in (1, 2, 3):
        p_com, _, _ = avaliar_regras(com, tags[:n])
        p_sem, _, _ = avaliar_regras(sem, tags[:n])
        assert round(p_sem - p_com, 6) == 0.8 * min(n, 2)


@pytest.mark.parametrize("pedida, temp_bebida, esperado", [
    ("gelada", "gelada", 0.8),
    ("gelada", "quente", -1.0),
    ("quente", "quente", 0.8),
    ("quente", "gelada", -1.0),
    ("natural", "ambiente", 0.6),
    ("natural", "gelada", -0.4),
    (None, "gelada", 0.0),
])
def test_preferencia_de_temperatura(pedida, temp_bebida, esperado):
    b = _bebida(temperatura=temp_bebida)
    pontos, _, _ = avaliar_regras(b, [], temperatura=pedida)
    assert round(pontos, 6) == esperado


def test_temperatura_pedida_gera_motivo_ou_alerta():
    _, motivos, _ = avaliar_regras(_bebida(temperatura="gelada"), [], temperatura="gelada")
    assert "é servida gelada, como você pediu" in motivos
    _, _, alertas = avaliar_regras(_bebida(temperatura="gelada"), [], temperatura="quente")
    assert "normalmente não é servida quente" in alertas


def test_ocasiao_calor_favorece_gelada_refrescante_e_pune_encorpada():
    leve = _bebida(temperatura="gelada", sabores=["refrescante"], corpo=1)
    pesada = _bebida(temperatura="ambiente", sabores=["tostado"], corpo=3)
    p_leve, motivos, _ = avaliar_regras(leve, [], ocasioes=["calor"])
    p_pesada, _, alertas = avaliar_regras(pesada, [], ocasioes=["calor"])
    assert p_leve > 0 and "é refrescante para um dia quente" in motivos
    assert p_pesada < 0 and "pesada para um dia quente" in alertas


def test_ocasiao_frio_favorece_bebida_quente():
    quente = _bebida(temperatura="quente")
    pontos, motivos, _ = avaliar_regras(quente, [], ocasioes=["frio"])
    assert pontos >= 0.9
    assert "é servida quente, ideal para um dia frio" in motivos


def test_sem_pistas_a_pontuacao_e_zero():
    pontos, motivos, alertas = avaliar_regras(_bebida(), [])
    assert pontos == 0 and motivos == [] and alertas == []


# =========================================================================== #
# 4. INTERPRETAÇÃO DOS CAMPOS DO FORMULÁRIO
# =========================================================================== #
@pytest.mark.parametrize("valor, esperado", [
    ("suco", "suco"),
    ("Sucos", "suco"),
    ("vitamina", "vitamina"),
    ("Vitaminas", "vitamina"),
    ("cha", "cha"),
    ("Chás e infusões", "cha"),
    ("cremosa", "cremosa"),
    ("Bebidas cremosas", "cremosa"),
    ("qualquer", "qualquer"),
    ("", "qualquer"),
    (None, "qualquer"),
    ("coisa estranha", "qualquer"),
])
def test_interpretar_tipo(valor, esperado):
    assert interpretar_tipo(valor) == esperado


@pytest.mark.parametrize("valor, esperado", [
    ("Gelada", "gelada"),
    ("gelado", "gelada"),
    ("Quente", "quente"),
    ("Natural", "natural"),
    ("temperatura ambiente", "natural"),
    ("Qualquer", None),
    ("tanto faz", None),
    ("", None),
    (None, None),
    ("morna", None),
])
def test_interpretar_temperatura(valor, esperado):
    assert interpretar_temperatura(valor) == esperado


# =========================================================================== #
# 5. FILTROS
# =========================================================================== #
@pytest.mark.parametrize("preferencias, campo", [
    ("sem lactose", "sem_lactose"),
    ("sou vegano", "sem_lactose"),
    ("intolerante a lactose", "sem_lactose"),
    ("sem cafeína", "sem_cafeina"),
    ("descafeinado por favor", "sem_cafeina"),
    ("sem gás", "sem_gas"),
    ("não gosto de gás", "sem_gas"),
    ("pouco açúcar", "pouco_acucar"),
    ("sou diabético", "pouco_acucar"),
])
def test_filtros_entendem_preferencias_em_texto_livre(preferencias, campo):
    assert getattr(Filtros.de(preferencias=preferencias), campo) is True


def test_filtros_sem_preferencias_nao_restringem_nada():
    f = Filtros.de()
    assert (f.tipo, f.sem_lactose, f.sem_cafeina, f.sem_gas, f.pouco_acucar) == \
        ("qualquer", False, False, False, False)
    assert all(f.aceita(b) for b in CATALOGO)


def test_filtros_aceita_respeita_cada_restricao():
    assert Filtros(sem_lactose=True).aceita(_bebida(lactose=True)) is False
    assert Filtros(sem_cafeina=True).aceita(_bebida(cafeina=True)) is False
    assert Filtros(sem_gas=True).aceita(_bebida(gas=True)) is False
    assert Filtros(sem_lactose=True, sem_cafeina=True, sem_gas=True).aceita(_bebida()) is True


@pytest.mark.parametrize("tipo, bebida, aceita", [
    ("suco", _bebida(tipo="suco"), True),
    ("suco", _bebida(tipo="cha"), False),
    ("vitamina", _bebida(tipo="vitamina"), True),
    ("vitamina", _bebida(tipo="suco"), False),
    ("cha", _bebida(tipo="cha"), True),
    ("cha", _bebida(tipo="cafe"), False),
    ("cremosa", _bebida(sabores=["cremoso"]), True),
    ("cremosa", _bebida(sabores=["lacteo"]), True),
    ("cremosa", _bebida(sabores=["citrico"]), False),
])
def test_filtros_aceita_por_tipo(tipo, bebida, aceita):
    assert Filtros(tipo=tipo).aceita(bebida) is aceita


def test_filtros_ajuste_pouco_acucar():
    f = Filtros(pouco_acucar=True)
    assert f.ajuste(_bebida(docura=2)) == (-2.0, ["é bem doce, e você pediu pouco açúcar"])
    assert f.ajuste(_bebida(docura=1)) == (-0.6, [])
    pontos, motivos = f.ajuste(_bebida(docura=0))
    assert pontos == 0.5 and motivos == ["é seca, combinando com o pedido de pouco açúcar"]
    assert Filtros().ajuste(_bebida(docura=2)) == (0.0, [])


def test_filtros_descricao_lista_o_que_esta_ativo():
    f = Filtros.de(tipo="suco", preferencias="sem lactose, sem gás, pouco açúcar, sem cafeína")
    assert f.descricao() == ["Sucos", "Sem lactose", "Sem cafeína", "Sem gás", "Pouco açúcar"]
    assert Filtros().descricao() == []


# =========================================================================== #
# 6. MOTORES DE SIMILARIDADE
# =========================================================================== #
def test_motor_lexico_devolve_uma_similaridade_por_bebida():
    motor = MotorLexico([documento_da_bebida(b) for b in CATALOGO])
    sims = motor.similaridades("algo cítrico e refrescante")
    assert len(sims) == len(CATALOGO)
    assert all(0.0 <= s <= 1.0 + 1e-9 for s in sims)


def test_motor_lexico_acha_a_bebida_mais_parecida_com_o_texto():
    docs = ["suco de laranja cítrico", "café expresso tostado amargo", "chá de hortelã herbal"]
    motor = MotorLexico(docs)
    sims = motor.similaridades("quero um café tostado")
    assert sims.index(max(sims)) == 1


def test_motor_lexico_consulta_sem_palavras_conhecidas_nao_quebra():
    motor = MotorLexico(["suco de laranja", "chá verde"])
    assert motor.similaridades("zzz qqq") == [0.0, 0.0]
    assert motor.similaridades("") == [0.0, 0.0]


def test_motor_falso_do_conftest_e_decrescente_e_deterministico(recomendador_falso):
    sims = recomendador_falso.motor.similaridades("qualquer coisa")
    assert sims == recomendador_falso.motor.similaridades("outra coisa")
    assert sims == sorted(sims, reverse=True)
    assert sims[0] == 0.9


# =========================================================================== #
# 7. RECOMENDADOR (sem modelo)
# =========================================================================== #
def test_recomendador_usa_o_motor_que_recebeu(recomendador_lexico, recomendador_falso):
    assert recomendador_lexico.sugerir("almoço")["motor"] == "lexico"
    assert recomendador_falso.sugerir("almoço")["motor"] == "falso"


def test_sugerir_devolve_3_bebidas_com_a_estrutura_esperada(recomendador_lexico):
    r = recomendador_lexico.sugerir("frango apimentado")
    assert len(r["bebidas"]) == 3
    for chave in ("bebidas", "perfil_prato", "ocasioes", "filtros", "aviso", "motor"):
        assert chave in r
    for b in r["bebidas"]:
        for campo in ("id", "nome", "tipo", "alcool", "teor", "temperatura", "descricao",
                      "tags", "pontuacao", "justificativa", "alerta"):
            assert campo in b
        assert b["justificativa"].strip()
        assert b["nome"] in b["justificativa"]


def test_sugerir_nao_repete_bebida_e_so_usa_bebidas_do_catalogo(recomendador_lexico):
    r = recomendador_lexico.sugerir("peixe grelhado com salada")
    ids = [b["id"] for b in r["bebidas"]]
    assert len(ids) == len(set(ids))
    assert set(ids) <= {b["id"] for b in CATALOGO}


def test_sugerir_ordena_da_melhor_para_a_pior(recomendador_lexico):
    r = recomendador_lexico.sugerir("feijoada")
    pontos = [b["pontuacao"] for b in r["bebidas"]]
    assert pontos == sorted(pontos, reverse=True)


def test_sugerir_e_deterministico(recomendador_lexico):
    a = recomendador_lexico.sugerir("macarrão ao molho de tomate", preferencias="dia de calor")
    b = recomendador_lexico.sugerir("macarrão ao molho de tomate", preferencias="dia de calor")
    assert a == b


def test_sugerir_no_maximo_2_bebidas_do_mesmo_tipo(recomendador_lexico):
    for prato in ("frango apimentado", "pastel frito", "bolo de chocolate", "salada leve", "feijoada"):
        tipos = Counter(b["tipo"] for b in recomendador_lexico.sugerir(prato)["bebidas"])
        assert max(tipos.values()) <= MAX_MESMO_TIPO, prato


def test_sugerir_aceita_so_ingredientes(recomendador_lexico):
    r = recomendador_lexico.sugerir("", ingredientes="frango, pimenta, arroz")
    assert len(r["bebidas"]) == 3
    assert "apimentado" in r["perfil_prato"]


def test_sugerir_junta_refeicao_e_ingredientes(recomendador_lexico):
    r = recomendador_lexico.sugerir("almoço", ingredientes="peixe grelhado")
    assert {"peixe", "grelhado"} <= set(r["perfil_prato"])


@pytest.mark.parametrize("refeicao, ingredientes", [("", ""), ("   ", ""), ("", "   "), (None, None)])
def test_sugerir_sem_refeicao_nem_ingredientes_da_erro(recomendador_lexico, refeicao, ingredientes):
    with pytest.raises(ValueError, match="Informe a refeição"):
        recomendador_lexico.sugerir(refeicao, ingredientes=ingredientes)


# ---- pratos pedidos no planejamento (semana 3): apimentado, frito, doce e leve ----
def test_prato_apimentado_recebe_bebida_doce_e_gelada(recomendador_lexico):
    r = recomendador_lexico.sugerir("frango apimentado")
    assert "apimentado" in r["perfil_prato"]
    assert any(b["temperatura"] == "gelada" for b in r["bebidas"])
    assert any("pimenta" in b["justificativa"] or "ardência" in b["justificativa"]
               or "gelada" in b["justificativa"] or "refresca" in b["justificativa"]
               for b in r["bebidas"])


def test_prato_frito_recebe_bebida_que_corta_a_gordura(recomendador_lexico):
    r = recomendador_lexico.sugerir("batata frita e pastel")
    assert "frito" in r["perfil_prato"]
    escolhidas = {b["id"] for b in r["bebidas"]}
    com_afinidade = {b["id"] for b in CATALOGO if "frito" in b["combina"]}
    assert escolhidas & com_afinidade, "ao menos uma bebida deve combinar com fritura"


def test_prato_doce_nao_recebe_bebida_que_evita_doce(recomendador_lexico):
    r = recomendador_lexico.sugerir("bolo de chocolate")
    assert {"doce", "chocolate"} <= set(r["perfil_prato"])
    evitam = {b["id"] for b in CATALOGO if {"doce", "chocolate"} & set(b["evita"])}
    assert not ({b["id"] for b in r["bebidas"]} & evitam)


def test_prato_leve_recebe_bebida_leve(recomendador_lexico):
    r = recomendador_lexico.sugerir("salada leve")
    assert {"leve", "salada"} <= set(r["perfil_prato"])
    escolhidas = {b["id"] for b in r["bebidas"]}
    leves = {b["id"] for b in CATALOGO if {"leve", "salada"} & set(b["combina"])}
    assert escolhidas & leves
    evitam = {b["id"] for b in CATALOGO if {"leve", "salada"} & set(b["evita"])}
    assert not (escolhidas & evitam)


# ---- filtros ----
def test_filtro_sem_lactose_nao_sugere_bebida_com_lactose(recomendador_lexico):
    com_lactose = {b["id"] for b in CATALOGO if b["lactose"]}
    assert com_lactose, "o catálogo precisa ter bebidas com lactose para este teste fazer sentido"
    for prato in ("almoço", "sobremesa", "lanche"):
        r = recomendador_lexico.sugerir(prato, preferencias="sem lactose")
        assert not ({b["id"] for b in r["bebidas"]} & com_lactose)
        assert "Sem lactose" in r["filtros"]


def test_filtro_sem_cafeina_e_sem_gas(recomendador_lexico):
    r = recomendador_lexico.sugerir("almoço", preferencias="sem cafeína e sem gás")
    por_id = {b["id"]: b for b in CATALOGO}
    for b in r["bebidas"]:
        assert not por_id[b["id"]]["cafeina"]
        assert not por_id[b["id"]]["gas"]
    assert "Sem cafeína" in r["filtros"] and "Sem gás" in r["filtros"]


@pytest.mark.parametrize("tipo", ["suco", "vitamina", "cha"])
def test_filtro_de_tipo_so_devolve_aquele_tipo_e_pode_repetir(recomendador_lexico, tipo):
    r = recomendador_lexico.sugerir("almoço", tipo=tipo)
    assert len(r["bebidas"]) == 3
    assert {b["tipo"] for b in r["bebidas"]} == {tipo}


def test_filtro_cremosa_so_devolve_bebidas_cremosas_ou_lacteas(recomendador_lexico):
    por_id = {b["id"]: b for b in CATALOGO}
    r = recomendador_lexico.sugerir("sobremesa", tipo="cremosa")
    assert r["bebidas"]
    for b in r["bebidas"]:
        sabores = set(por_id[b["id"]]["sabores"])
        assert sabores & {"cremoso", "lacteo"}


def test_filtro_de_tipo_aceita_o_texto_do_formulario(recomendador_lexico):
    r = recomendador_lexico.sugerir("almoço", tipo="Chás e infusões")
    assert {b["tipo"] for b in r["bebidas"]} == {"cha"}
    assert "Chás e infusões" in r["filtros"]


def test_filtro_de_temperatura_aparece_na_resposta(recomendador_lexico):
    r = recomendador_lexico.sugerir("feijoada", temperatura="Quente")
    assert "Quente" in r["filtros"]
    assert any(b["temperatura"] == "quente" for b in r["bebidas"])
    r2 = recomendador_lexico.sugerir("feijoada", temperatura="Qualquer")
    assert "Quente" not in r2["filtros"] and "Gelada" not in r2["filtros"]


def test_pouco_acucar_evita_as_bebidas_mais_doces(recomendador_falso):
    por_id = {b["id"]: b for b in CATALOGO}
    r = recomendador_falso.sugerir("almoço", preferencias="sou diabético")
    assert "Pouco açúcar" in r["filtros"]
    assert all(por_id[b["id"]]["docura"] < 2 for b in r["bebidas"])


def test_ocasiao_de_calor_e_detectada_e_favorece_bebida_gelada(recomendador_lexico):
    r = recomendador_lexico.sugerir("almoço", preferencias="dia de calor na praia")
    assert "calor" in r["ocasioes"]
    assert all(b["temperatura"] == "gelada" for b in r["bebidas"])


def test_filtros_impossiveis_dao_erro_claro(recomendador_lexico):
    pequeno = _recomendador_pequeno([_bebida(id="a", lactose=True)])
    with pytest.raises(ValueError, match="Nenhuma bebida do catálogo atende"):
        pequeno.sugerir("almoço", preferencias="sem lactose")


def test_aviso_quando_o_catalogo_tem_menos_bebidas_que_o_pedido():
    pequeno = _recomendador_pequeno([_bebida(id="a", nome="A"), _bebida(id="b", nome="B", tipo="cha")])
    r = pequeno.sugerir("almoço")
    assert len(r["bebidas"]) == 2
    assert r["aviso"] == "Só 2 bebida(s) do catálogo atendem a esses filtros."


def test_sem_aviso_quando_ha_bebidas_suficientes(recomendador_lexico):
    assert recomendador_lexico.sugerir("almoço")["aviso"] is None


def test_qtd_personalizada(recomendador_lexico):
    assert len(recomendador_lexico.sugerir("almoço", qtd=2)["bebidas"]) == 2
    assert len(recomendador_lexico.sugerir("almoço", qtd=1)["bebidas"]) == 1


def test_prato_com_poucas_pistas_prefere_bebida_versatil(recomendador_falso):
    versateis = {b["id"] for b in CATALOGO if len(b["combina"]) >= 6}
    assert versateis
    r = recomendador_falso.sugerir("ovo")
    assert any(b["id"] in versateis for b in r["bebidas"])


# ---- justificativa ----
def test_justificativa_com_motivos():
    texto = Recomendador._justificativa(_bebida(nome="Suco X"), [], ["motivo um", "motivo dois", "motivo três"], 50)
    assert texto == "Suco X combina porque motivo um e motivo dois."


def test_justificativa_com_um_so_motivo():
    assert Recomendador._justificativa(_bebida(nome="Suco X"), [], ["motivo um"], 50) == \
        "Suco X combina porque motivo um."


def test_justificativa_sem_motivos_usa_a_similaridade():
    texto = Recomendador._justificativa(_bebida(nome="Suco X"), [], [], 73)
    assert "Suco X" in texto and "73%" in texto


# ---- escolha final ----
def _item(bebida, pontos):
    return {"bebida": bebida, "pontuacao": pontos, "similaridade": 0.5, "motivos": [], "alertas": []}


def test_escolher_limita_o_mesmo_tipo():
    itens = [_item(_bebida(id=f"s{i}", tipo="suco"), 10 - i) for i in range(4)] + \
            [_item(_bebida(id="c1", tipo="cha"), 1)]
    escolhidas = Recomendador._escolher(itens, 3, "restrito")
    tipos = Counter(e["bebida"]["tipo"] for e in escolhidas)
    assert tipos["suco"] == 2 and tipos["cha"] == 1


def test_escolher_com_limite_maior_permite_repetir_tipo():
    itens = [_item(_bebida(id=f"s{i}", tipo="suco"), 10 - i) for i in range(4)]
    escolhidas = Recomendador._escolher(itens, 3, "restrito", max_mesmo_tipo=3)
    assert [e["bebida"]["id"] for e in escolhidas] == ["s0", "s1", "s2"]


def test_escolher_lista_vazia():
    assert Recomendador._escolher([], 3, "qualquer") == []


# ---- desempenho (planejamento, semana 7: tempo de resposta das bebidas) ----
def test_tempo_de_resposta_do_recomendador_lexico(recomendador_lexico):
    inicio = time.perf_counter()
    for _ in range(20):
        recomendador_lexico.sugerir("frango apimentado com arroz", preferencias="dia de calor")
    medio = (time.perf_counter() - inicio) / 20
    assert medio < 0.5, f"resposta média de {medio:.3f}s é lenta demais para o motor léxico"


# =========================================================================== #
# 8. ROTA POST /api/bebida/sugerir
# =========================================================================== #
def test_sugerir_exige_login(client):
    r = client.post("/api/bebida/sugerir", json={"refeicao": "almoço"})
    assert r.status_code == 401
    assert "login" in r.get_json()["erro"].lower()


def test_sugerir_so_aceita_post(client_logado):
    assert client_logado.get("/api/bebida/sugerir").status_code == 405


def test_sugerir_sem_refeicao_nem_ingredientes_da_400(client_logado, injetar_recomendador):
    injetar_recomendador(EspiaoRecomendador())
    r = client_logado.post("/api/bebida/sugerir", json={})
    assert r.status_code == 400
    assert "refeição" in r.get_json()["erro"]


@pytest.mark.parametrize("corpo", [{"refeicao": "   "}, {"refeicao": "", "ingredientes": ""}, None])
def test_sugerir_com_corpo_vazio_ou_invalido_da_400(client_logado, injetar_recomendador, corpo):
    injetar_recomendador(EspiaoRecomendador())
    if corpo is None:
        r = client_logado.post("/api/bebida/sugerir", data="isto não é json",
                               content_type="application/json")
    else:
        r = client_logado.post("/api/bebida/sugerir", json=corpo)
    assert r.status_code == 400


def test_sugerir_devolve_o_resultado_do_recomendador(client_logado, injetar_recomendador):
    espiao = injetar_recomendador(EspiaoRecomendador())
    r = client_logado.post("/api/bebida/sugerir", json={"refeicao": "almoço"})
    assert r.status_code == 200
    assert r.get_json() == espiao.resposta


def test_sugerir_repassa_os_campos_ao_recomendador(client_logado, injetar_recomendador):
    espiao = injetar_recomendador(EspiaoRecomendador())
    client_logado.post("/api/bebida/sugerir", json={
        "refeicao": "  frango  ", "ingredientes": "arroz", "preferencias": "sem lactose",
        "temperatura": "Gelada", "tipo": "suco",
    })
    chamada = espiao.chamadas[0]
    assert chamada["refeicao"] == "frango"
    assert chamada["ingredientes"] == "arroz"
    assert chamada["preferencias"] == "sem lactose"
    assert chamada["temperatura"] == "Gelada"
    assert chamada["tipo"] == "suco"
    assert chamada["qtd"] == 3


def test_sugerir_aceita_so_ingredientes(client_logado, injetar_recomendador):
    espiao = injetar_recomendador(EspiaoRecomendador())
    r = client_logado.post("/api/bebida/sugerir", json={"ingredientes": "frango, arroz"})
    assert r.status_code == 200
    assert espiao.chamadas[0]["ingredientes"] == "frango, arroz"


def test_sugerir_temperatura_vazia_vira_none_e_tipo_padrao_e_qualquer(client_logado, injetar_recomendador):
    espiao = injetar_recomendador(EspiaoRecomendador())
    client_logado.post("/api/bebida/sugerir", json={"refeicao": "almoço"})
    assert espiao.chamadas[0]["temperatura"] is None
    assert espiao.chamadas[0]["tipo"] == "qualquer"


def test_sugerir_erro_de_valor_vira_400_com_a_mensagem(client_logado, injetar_recomendador):
    injetar_recomendador(EspiaoRecomendador(erro=ValueError("Nenhuma bebida atende.")))
    r = client_logado.post("/api/bebida/sugerir", json={"refeicao": "almoço"})
    assert r.status_code == 400
    assert r.get_json() == {"erro": "Nenhuma bebida atende."}


def test_sugerir_erro_inesperado_vira_500(client_logado, injetar_recomendador):
    injetar_recomendador(EspiaoRecomendador(erro=RuntimeError("falha interna")))
    r = client_logado.post("/api/bebida/sugerir", json={"refeicao": "almoço"})
    assert r.status_code == 500
    assert r.get_json()["erro"] == "Erro ao sugerir bebida."


def test_sugerir_de_ponta_a_ponta_com_o_recomendador_real(client_logado, injetar_recomendador,
                                                           recomendador_lexico):
    injetar_recomendador(recomendador_lexico)
    r = client_logado.post("/api/bebida/sugerir", json={
        "refeicao": "frango apimentado", "preferencias": "sem lactose", "tipo": "qualquer",
    })
    assert r.status_code == 200
    dados = r.get_json()
    assert len(dados["bebidas"]) == 3
    por_id = {b["id"]: b for b in CATALOGO}
    assert not any(por_id[b["id"]]["lactose"] for b in dados["bebidas"])
    assert dados["motor"] == "lexico"


def test_sugerir_filtro_impossivel_na_rota_da_400(client_logado, injetar_recomendador):
    injetar_recomendador(_recomendador_pequeno([_bebida(id="a", lactose=True)]))
    r = client_logado.post("/api/bebida/sugerir", json={"refeicao": "almoço", "preferencias": "sem lactose"})
    assert r.status_code == 400
    assert "Nenhuma bebida" in r.get_json()["erro"]


# =========================================================================== #
# 9. ROTA POST /api/bebida/escolher (grava a sugestão)
# =========================================================================== #
def test_escolher_exige_login(client):
    r = client.post("/api/bebida/escolher", json={"nome_bebida": "Suco"})
    assert r.status_code == 401


def test_escolher_sem_nome_da_400_e_nao_grava(client_logado, conn):
    for corpo in ({}, {"nome_bebida": ""}, {"nome_bebida": "   "}):
        r = client_logado.post("/api/bebida/escolher", json=corpo)
        assert r.status_code == 400
        assert r.get_json()["erro"] == "Nenhuma bebida foi informada."
    assert _bebidas_salvas(conn) == []


def test_escolher_grava_a_bebida_sozinha(client_logado, usuario, conn):
    r = client_logado.post("/api/bebida/escolher", json={
        "nome_bebida": "Suco de Maracujá", "justificativa": "A acidez acalma pratos picantes.",
        "refeicao": "frango apimentado",
    })
    assert r.status_code == 200
    dados = r.get_json()
    assert dados["vinculada"] is False and dados["receita_id"] is None
    assert dados["bebida_id"]

    linhas = _bebidas_salvas(conn, usuario["id"])
    assert len(linhas) == 1
    assert linhas[0]["nome_bebida"] == "Suco de Maracujá"
    assert linhas[0]["justificativa"] == "A acidez acalma pratos picantes."
    assert linhas[0]["refeicao"] == "frango apimentado"
    assert linhas[0]["receita_id"] is None
    assert linhas[0]["id"] == dados["bebida_id"]


def test_escolher_vincula_a_bebida_a_receita_do_usuario(client_logado, usuario, conn):
    receita_id = _inserir_receita(conn, usuario["id"])
    r = client_logado.post("/api/bebida/escolher", json={
        "nome_bebida": "Suco de Uva Integral", "justificativa": "Encorpado.", "receita_id": receita_id,
    })
    assert r.status_code == 200
    dados = r.get_json()
    assert dados["vinculada"] is True and dados["receita_id"] == receita_id
    assert "junto com a receita" in dados["mensagem"]
    assert _bebidas_salvas(conn, usuario["id"])[0]["receita_id"] == receita_id


def test_escolher_aceita_receita_id_como_texto(client_logado, usuario, conn):
    receita_id = _inserir_receita(conn, usuario["id"])
    r = client_logado.post("/api/bebida/escolher", json={"nome_bebida": "Suco", "receita_id": str(receita_id)})
    assert r.get_json()["vinculada"] is True


def test_escolher_usa_o_mesmo_id_devolvido_pela_receita(client_logado, usuario, conn):
    """Integração Ednaldo/Reinaldo: o receita_id gravado em `receitas` é o mesmo usado na bebida."""
    receita_id = _inserir_receita(conn, usuario["id"], pedido="lanche leve")
    client_logado.post("/api/bebida/escolher", json={"nome_bebida": "Suco", "receita_id": receita_id})
    juntos = conn.execute(
        "SELECT r.pedido, b.nome_bebida FROM bebidas_sugeridas b "
        "JOIN receitas r ON r.id = b.receita_id WHERE b.usuario_id = ?", (usuario["id"],)
    ).fetchall()
    assert [(j["pedido"], j["nome_bebida"]) for j in juntos] == [("lanche leve", "Suco")]


def test_escolher_receita_de_outro_usuario_guarda_a_bebida_sozinha(client_logado, usuario, criar_usuario, conn):
    outro = criar_usuario(nome="Outra Pessoa")
    receita_alheia = _inserir_receita(conn, outro["id"])
    r = client_logado.post("/api/bebida/escolher", json={"nome_bebida": "Suco", "receita_id": receita_alheia})
    assert r.status_code == 200
    assert r.get_json()["vinculada"] is False
    assert _bebidas_salvas(conn, usuario["id"])[0]["receita_id"] is None


def test_escolher_receita_inexistente_guarda_a_bebida_sozinha(client_logado, conn):
    r = client_logado.post("/api/bebida/escolher", json={"nome_bebida": "Suco", "receita_id": 9999})
    assert r.status_code == 200 and r.get_json()["vinculada"] is False
    assert len(_bebidas_salvas(conn)) == 1


@pytest.mark.parametrize("receita_id", ["abc", [1], {"a": 1}])
def test_escolher_receita_id_invalido_da_400(client_logado, conn, receita_id):
    r = client_logado.post("/api/bebida/escolher", json={"nome_bebida": "Suco", "receita_id": receita_id})
    assert r.status_code == 400
    assert r.get_json()["erro"] == "Receita inválida."
    assert _bebidas_salvas(conn) == []


def test_escolher_receita_id_vazio_e_ignorado(client_logado, conn):
    for vazio in (None, ""):
        r = client_logado.post("/api/bebida/escolher", json={"nome_bebida": "Suco", "receita_id": vazio})
        assert r.status_code == 200 and r.get_json()["vinculada"] is False


def test_escolher_a_mesma_bebida_na_mesma_receita_nao_duplica(client_logado, usuario, conn):
    receita_id = _inserir_receita(conn, usuario["id"])
    corpo = {"nome_bebida": "Suco de Uva", "justificativa": "x", "receita_id": receita_id}
    primeira = client_logado.post("/api/bebida/escolher", json=corpo).get_json()
    segunda = client_logado.post("/api/bebida/escolher", json=corpo)
    assert segunda.status_code == 200
    assert segunda.get_json()["bebida_id"] == primeira["bebida_id"]
    assert "já estava guardada" in segunda.get_json()["mensagem"]
    assert len(_bebidas_salvas(conn, usuario["id"])) == 1


def test_escolher_bebidas_diferentes_na_mesma_receita(client_logado, usuario, conn):
    receita_id = _inserir_receita(conn, usuario["id"])
    for nome in ("Suco A", "Suco B", "Suco C"):
        client_logado.post("/api/bebida/escolher", json={"nome_bebida": nome, "receita_id": receita_id})
    assert len(_bebidas_salvas(conn, usuario["id"])) == 3


def test_escolher_sem_receita_permite_repetir_a_bebida(client_logado, usuario, conn):
    for _ in range(2):
        client_logado.post("/api/bebida/escolher", json={"nome_bebida": "Suco", "justificativa": "x"})
    assert len(_bebidas_salvas(conn, usuario["id"])) == 2


def test_escolher_corta_a_refeicao_em_300_caracteres(client_logado, usuario, conn):
    client_logado.post("/api/bebida/escolher", json={"nome_bebida": "Suco", "refeicao": "a" * 500})
    assert len(_bebidas_salvas(conn, usuario["id"])[0]["refeicao"]) == 300


def test_escolher_refeicao_vazia_fica_nula(client_logado, usuario, conn):
    client_logado.post("/api/bebida/escolher", json={"nome_bebida": "Suco", "refeicao": "   "})
    assert _bebidas_salvas(conn, usuario["id"])[0]["refeicao"] is None


def test_escolher_justificativa_e_opcional(client_logado, usuario, conn):
    r = client_logado.post("/api/bebida/escolher", json={"nome_bebida": "Suco"})
    assert r.status_code == 200
    assert _bebidas_salvas(conn, usuario["id"])[0]["justificativa"] == ""


def test_escolher_grava_para_o_usuario_logado(app, logar, criar_usuario, conn):
    ana, beto = criar_usuario(nome="Ana"), criar_usuario(nome="Beto")
    c_ana, c_beto = logar(app.test_client(), ana), logar(app.test_client(), beto)
    c_ana.post("/api/bebida/escolher", json={"nome_bebida": "Suco da Ana"})
    c_beto.post("/api/bebida/escolher", json={"nome_bebida": "Suco do Beto"})
    assert [l["nome_bebida"] for l in _bebidas_salvas(conn, ana["id"])] == ["Suco da Ana"]
    assert [l["nome_bebida"] for l in _bebidas_salvas(conn, beto["id"])] == ["Suco do Beto"]


def test_fluxo_sugerir_e_depois_escolher(client_logado, usuario, conn, injetar_recomendador, recomendador_lexico):
    injetar_recomendador(recomendador_lexico)
    sugestao = client_logado.post("/api/bebida/sugerir", json={"refeicao": "pastel frito"}).get_json()
    escolhida = sugestao["bebidas"][0]
    r = client_logado.post("/api/bebida/escolher", json={
        "nome_bebida": escolhida["nome"], "justificativa": escolhida["justificativa"],
        "refeicao": "pastel frito",
    })
    assert r.status_code == 200
    salva = _bebidas_salvas(conn, usuario["id"])[0]
    assert salva["nome_bebida"] == escolhida["nome"]
    assert salva["justificativa"] == escolhida["justificativa"]


# =========================================================================== #
# 10. ROTA DELETE /api/bebida/historico/<id>
# =========================================================================== #
def _guardar(client, nome="Suco", **extra):
    return client.post("/api/bebida/escolher", json={"nome_bebida": nome, **extra}).get_json()["bebida_id"]


def test_excluir_exige_login(client):
    r = client.delete("/api/bebida/historico/1")
    assert r.status_code == 401


def test_excluir_remove_a_bebida(client_logado, usuario, conn):
    bebida_id = _guardar(client_logado)
    r = client_logado.delete(f"/api/bebida/historico/{bebida_id}")
    assert r.status_code == 200
    assert r.get_json() == {"ok": True, "id": bebida_id}
    assert _bebidas_salvas(conn, usuario["id"]) == []


def test_excluir_mantem_as_outras_bebidas(client_logado, usuario, conn):
    primeira, segunda = _guardar(client_logado, "A"), _guardar(client_logado, "B")
    client_logado.delete(f"/api/bebida/historico/{primeira}")
    assert [l["id"] for l in _bebidas_salvas(conn, usuario["id"])] == [segunda]


def test_excluir_inexistente_da_404(client_logado):
    r = client_logado.delete("/api/bebida/historico/9999")
    assert r.status_code == 404
    assert r.get_json()["erro"] == "Bebida não encontrada."


def test_excluir_duas_vezes_a_segunda_da_404(client_logado):
    bebida_id = _guardar(client_logado)
    assert client_logado.delete(f"/api/bebida/historico/{bebida_id}").status_code == 200
    assert client_logado.delete(f"/api/bebida/historico/{bebida_id}").status_code == 404


def test_excluir_bebida_de_outro_usuario_da_404_e_nao_apaga(app, logar, criar_usuario, conn):
    ana, beto = criar_usuario(nome="Ana"), criar_usuario(nome="Beto")
    c_ana, c_beto = logar(app.test_client(), ana), logar(app.test_client(), beto)
    bebida_da_ana = _guardar(c_ana, "Suco da Ana")
    r = c_beto.delete(f"/api/bebida/historico/{bebida_da_ana}")
    assert r.status_code == 404
    assert len(_bebidas_salvas(conn, ana["id"])) == 1


def test_excluir_id_nao_numerico_da_404(client_logado):
    assert client_logado.delete("/api/bebida/historico/abc").status_code == 404


def test_excluir_bebida_nao_apaga_a_receita_ligada(client_logado, usuario, conn):
    receita_id = _inserir_receita(conn, usuario["id"])
    bebida_id = _guardar(client_logado, receita_id=receita_id)
    client_logado.delete(f"/api/bebida/historico/{bebida_id}")
    assert conn.execute("SELECT id FROM receitas WHERE id = ?", (receita_id,)).fetchone() is not None
