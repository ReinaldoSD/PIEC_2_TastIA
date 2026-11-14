"""Testes unitários do módulo de Percepção Computacional (catálogo, geometria, filtros, decisão e pipeline).
Rodar com:
  pytest TastIA/src/tests/test_percepcao.py
"""

from PIL import Image
from percepcao.catalogo import (
    CATALOGO,
    CATEGORIAS_VALIDAS,
    NOMES_RECONHECIVEIS,
    par_confundivel,
    resolver_nome,
    validar_catalogo,
)
from percepcao.classificacao import decidir_classificacao
from percepcao.pipeline import PipelinePercepcao
from percepcao.pos_processamento import (
    agregar_itens,
    aplicar_nms,
    deduplicar_classificados,
    filtrar_caixas,
    remover_caixas_de_grupo,
)
from percepcao.recortes import gerar_blocos, iou, tornar_quadrado


# --------------------------------------------------------------------------- #
# Catálogo de ingredientes, categorias e sinônimos
# --------------------------------------------------------------------------- #
def test_consistencia_catalogo_categorias_e_sinonimos():
    validar_catalogo()
    categorias_no_catalogo = {info["categoria"] for info in CATALOGO.values()}
    assert categorias_no_catalogo == set(CATEGORIAS_VALIDAS)
    assert len(NOMES_RECONHECIVEIS) >= 50
    assert resolver_nome("macaxeira") == "Mandioca"
    assert resolver_nome("jerimum") == "Abóbora"
    assert par_confundivel("Tomate", "Maçã") is True


# --------------------------------------------------------------------------- #
# Geometria de caixas delimitadoras, preenchimento quadrado e blocos
# --------------------------------------------------------------------------- #
def test_calculo_iou_preenchimento_quadrado_e_grade_de_blocos():
    assert round(iou([0, 0, 100, 100], [0, 0, 100, 100]), 2) == 1.0
    assert iou([0, 0, 50, 50], [100, 100, 150, 150]) == 0.0

    retangular = Image.new("RGB", (200, 80), color=(255, 0, 0))
    quadrada = tornar_quadrado(retangular)
    assert quadrada.size == (200, 200)

    blocos = gerar_blocos(400, 400, grade=2, sobreposicao=0.25)
    assert len(blocos) == 4


# --------------------------------------------------------------------------- #
# Pós-processamento: filtros de ruído, NMS, caixas de grupo e contagem
# --------------------------------------------------------------------------- #
def test_filtragem_caixas_nms_e_remocao_de_caixa_de_grupo():
    caixas = [
        {"bbox": [10, 10, 100, 100], "label_florence": "tomato"},
        {"bbox": [12, 12, 98, 98], "label_florence": "tomato"},        # Sobreposta (removida pelo NMS)
        {"bbox": [0, 0, 990, 990], "label_florence": "refrigerator"},  # Gigante e label não-comida
        {"bbox": [5, 5, 8, 8], "label_florence": "food"},              # Ruído minúsculo
    ]
    filtradas = aplicar_nms(filtrar_caixas(caixas, 1000, 1000))
    assert len(filtradas) == 1
    assert filtradas[0]["label_florence"] == "tomato"

    candidatos = [
        {"nome": "Maçã", "categoria": "Frutas", "confianca": 0.90, "bbox": [0, 0, 300, 300], "revisar": False, "alternativas": []},
        {"nome": "Maçã", "categoria": "Frutas", "confianca": 0.85, "bbox": [10, 10, 100, 100], "revisar": False, "alternativas": []},
        {"nome": "Maçã", "categoria": "Frutas", "confianca": 0.82, "bbox": [120, 120, 220, 220], "revisar": False, "alternativas": []},
    ]
    sem_grupo = deduplicar_classificados(remover_caixas_de_grupo(candidatos))
    agregados = agregar_itens(sem_grupo, contar=True)
    assert len(agregados) == 1
    assert agregados[0]["quantidade"] == "2 unidades"


# --------------------------------------------------------------------------- #
# Regra de decisão do classificador: limiar, negativos e pares confundíveis
# --------------------------------------------------------------------------- #
def test_decisao_classificador_com_negativos_e_margem_de_confusao():
    nomes = ["Tomate", "Maçã", "Banana"]

    # Descarta quando a soma das classes negativas supera a melhor classe de alimento
    assert decidir_classificacao([0.40, 0.10, 0.05], prob_negativos=0.45, nomes=nomes) is None

    # Marca para revisão quando o 1º e o 2º colocados são confundíveis e têm pouca margem
    res_duvida = decidir_classificacao([0.50, 0.42, 0.02], prob_negativos=0.06, nomes=nomes)
    assert res_duvida is not None
    assert res_duvida["nome"] == "Tomate"
    assert res_duvida["revisar"] is True

    # Aprova sem revisão quando há alta confiança e margem folgada
    res_certo = decidir_classificacao([0.80, 0.05, 0.05], prob_negativos=0.10, nomes=nomes)
    assert res_certo is not None
    assert res_certo["revisar"] is False


# --------------------------------------------------------------------------- #
# Execução do pipeline e acionamento automático do Plano B
# --------------------------------------------------------------------------- #
def test_execucao_pipeline_aciona_plano_b_quando_detector_nao_acha_objetos():
    class DetectorVazio:
        def detectar(self, img):
            return []

    class ClassificadorPlanoBMock:
        def classificar_recortes(self, recortes, limiar=None):
            return [None for _ in recortes]

        def classificar_plano_b(self, img):
            return [{
                "nome": "Banana",
                "categoria": "Frutas",
                "quantidade": "1 unidade",
                "confianca": 0.62,
                "selecionado": False,
                "revisar": True,
                "alternativas": [],
                "origem": "plano_b",
            }]

    pipe = PipelinePercepcao(detector=DetectorVazio(), classificador=ClassificadorPlanoBMock(), device="cpu")
    res = pipe.executar(Image.new("RGB", (300, 300), color=(255, 255, 0)))
    assert res["usou_plano_b"] is True
    assert res["total_detectado"] == 1
    assert res["ingredientes"][0]["nome"] == "Banana"