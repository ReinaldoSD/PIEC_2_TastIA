import math
import os
import re
import threading
from collections import Counter
from typing import Dict, List, Optional, Sequence

from bebidas.catalogo import CATALOGO, listar_bebidas
from bebidas.regras import (
    Filtros, avaliar_regras, interpretar_temperatura, perfil_de_ocasiao, perfil_do_prato, texto_expandido,
)
from receitas.validador import normalizar_texto

ID_MODELO = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
PESO_SIMILARIDADE = 1.5   # a similaridade (0..1 depois de normalizada) vale até 1,5 ponto
QTD_PADRAO = 3
MAX_MESMO_TIPO = 2        # no máximo 2 bebidas do mesmo tipo entre as 3 sugeridas


# --------------------------------------------------------------------------- #
# Texto de cada bebida (o que é comparado com a receita)
# --------------------------------------------------------------------------- #
def documento_da_bebida(b: Dict) -> str:
    partes = [
        b["nome"], b["descricao"], b["tipo"].replace("_", " "),
        " ".join(b["sabores"]),
        "combina com " + " ".join(t.replace("_", " ") for t in b["combina"]),
        "alcoólica" if b["alcool"] else "sem álcool",
        "gaseificada com gás" if b["gas"] else "",
        b["temperatura"],
    ]
    return ". ".join(p for p in partes if p)


# --------------------------------------------------------------------------- #
# Motores de similaridade
# --------------------------------------------------------------------------- #
class MotorLexico:
    """TF-IDF simples sobre palavras normalizadas (sem acento, singular). Sem dependências."""
    nome = "lexico"

    _STOP = set(
        "de da do das dos a o as os e em com sem para por no na nos nas um uma ou ao que se "
        "ser servida servido como mais muito bem boa bom ideal".split()
    )

    def __init__(self, documentos: Sequence[str]):
        self.docs = [self._vetor_tf(d) for d in documentos]
        n = len(documentos)
        df = Counter(p for d in self.docs for p in d)
        self.idf = {p: math.log((1 + n) / (1 + c)) + 1.0 for p, c in df.items()}

    @classmethod
    def _tokens(cls, texto: str) -> List[str]:
        saida = []
        for p in re.findall(r"[a-z]+", normalizar_texto(texto)):
            if len(p) < 3 or p in cls._STOP:
                continue
            if p.endswith("s") and len(p) > 4:
                p = p[:-1]
            saida.append(p)
        return saida

    @classmethod
    def _vetor_tf(cls, texto: str) -> Counter:
        return Counter(cls._tokens(texto))

    def _norma(self, tf: Counter) -> float:
        return math.sqrt(sum((c * self.idf.get(p, 1.0)) ** 2 for p, c in tf.items())) or 1.0

    def similaridades(self, consulta: str) -> List[float]:
        q = self._vetor_tf(consulta)
        nq = self._norma(q)
        saida = []
        for d in self.docs:
            dot = sum(c * d[p] * self.idf.get(p, 1.0) ** 2 for p, c in q.items() if p in d)
            saida.append(dot / (nq * self._norma(d)))
        return saida


class MotorMiniLM:
    """Embeddings do paraphrase-multilingual-MiniLM-L12-v2 (entende português)."""
    nome = "minilm"

    def __init__(self, documentos: Sequence[str], caminho: Optional[str] = None):
        from sentence_transformers import SentenceTransformer  # import tardio (é pesado)
        self.modelo = SentenceTransformer(caminho or ID_MODELO, device="cpu")
        self.vetores = self.modelo.encode(
            list(documentos), normalize_embeddings=True, show_progress_bar=False
        )

    def similaridades(self, consulta: str) -> List[float]:
        q = self.modelo.encode([consulta], normalize_embeddings=True, show_progress_bar=False)[0]
        return [float(v) for v in self.vetores @ q]


def _criar_motor(documentos: Sequence[str], preferido: str = "auto"):
    preferido = (preferido or "auto").lower()
    if preferido != "lexico":
        try:
            from config import MODELS_DIR
            local = os.path.join(MODELS_DIR, "recomendacao_bebida")
            caminho = local if os.path.exists(os.path.join(local, "config.json")) else None
            return MotorMiniLM(documentos, caminho)
        except Exception as e:   # sem pacote, sem modelo, sem internet, sem RAM...
            if preferido == "minilm":
                raise
            print(f"[bebidas] MiniLM indisponível ({type(e).__name__}); usando o motor léxico.")
    return MotorLexico(documentos)


# --------------------------------------------------------------------------- #
# Recomendador
# --------------------------------------------------------------------------- #
class Recomendador:
    def __init__(self, motor=None, catalogo: Optional[List[Dict]] = None):
        self.catalogo = catalogo if catalogo is not None else CATALOGO
        docs = [documento_da_bebida(b) for b in self.catalogo]
        self.motor = motor if motor is not None else _criar_motor(
            docs, os.environ.get("BEBIDAS_MOTOR", "auto"))
        self._indice = {b["id"]: i for i, b in enumerate(self.catalogo)}

    # ---- justificativa ---------------------------------------------------- #
    @staticmethod
    def _justificativa(b: Dict, tags: Sequence[str], motivos: List[str], sim_pct: int) -> str:
        if motivos:
            principais = motivos[:2]
            texto = f"{b['nome']} combina porque {principais[0]}"
            if len(principais) > 1:
                texto += f" e {principais[1]}"
            texto += "."
        else:
            texto = f"{b['nome']} tem afinidade de sabor com o seu prato ({sim_pct}% de similaridade)."
        return texto

    # ---- pontuação -------------------------------------------------------- #
    def pontuar(
        self,
        texto: str,
        temperatura: Optional[str] = None,
        filtros: Optional[Filtros] = None,
        texto_ocasiao: str = "",
    ) -> Dict:
        """texto = o prato (refeição/receita/ingredientes); texto_ocasiao = refeição + preferências."""
        filtros = filtros or Filtros()
        tags = perfil_do_prato(texto)
        ocasioes = perfil_de_ocasiao(texto_ocasiao or texto)
        consulta = texto_expandido(texto, tags)
        sims = self.motor.similaridades(consulta)

        # normaliza a similaridade para 0..1 (relativa ao catálogo inteiro)
        lo, hi = min(sims), max(sims)
        amplitude = (hi - lo) or 1.0

        itens = []
        for b, s in zip(self.catalogo, sims):
            if not filtros.aceita(b):
                continue
            s_norm = (s - lo) / amplitude
            pontos_regras, motivos, alertas = avaliar_regras(b, tags, ocasioes, temperatura)
            if len(tags) < 2 and len(b["combina"]) >= 6:
                # prato com poucas pistas (ex.: só "ovo"): bebidas versáteis são a aposta mais segura
                pontos_regras += 0.8
                motivos.append("é versátil e acompanha bem muitos tipos de prato")
            extra, motivos_extra = filtros.ajuste(b)
            (motivos if extra > 0 else alertas).extend(motivos_extra)
            itens.append({
                "bebida": b,
                "pontuacao": round(PESO_SIMILARIDADE * s_norm + pontos_regras + extra, 3),
                "similaridade": round(float(s), 3),
                "motivos": motivos,
                "alertas": alertas,
            })
        itens.sort(key=lambda x: (-x["pontuacao"], x["bebida"]["nome"]))
        return {"tags": tags, "ocasioes": ocasioes, "itens": itens}

    # ---- escolha final ---------------------------------------------------- #
    @staticmethod
    def _escolher(itens: List[Dict], qtd: int, alcool: str, max_mesmo_tipo: int = MAX_MESMO_TIPO) -> List[Dict]:
        escolhidas: List[Dict] = []
        por_tipo: Counter = Counter()
        for it in itens:
            tipo = it["bebida"]["tipo"]
            if por_tipo[tipo] >= max_mesmo_tipo:
                continue
            escolhidas.append(it)
            por_tipo[tipo] += 1
            if len(escolhidas) == qtd:
                break
        # "qualquer": garante pelo menos 1 opção sem álcool (e 1 com álcool) quando houver
        if alcool == "qualquer" and qtd >= 3 and len(escolhidas) == qtd:
            ids = {id(e) for e in escolhidas}
            if all(e["bebida"]["alcool"] for e in escolhidas):
                extra = next((i for i in itens if not i["bebida"]["alcool"] and id(i) not in ids), None)
                if extra:
                    escolhidas[-1] = extra
            elif not any(e["bebida"]["alcool"] for e in escolhidas):
                extra = next((i for i in itens if i["bebida"]["alcool"] and id(i) not in ids), None)
                if extra:
                    escolhidas[-1] = extra
            escolhidas.sort(key=lambda x: -x["pontuacao"])
        return escolhidas

    def sugerir(
        self,
        refeicao: str,
        ingredientes: str = "",
        preferencias: str = "",
        alcool: str = "qualquer",
        temperatura: Optional[str] = None,
        qtd: int = QTD_PADRAO,
        tipo: str = "qualquer",
    ) -> Dict:
        """Devolve {'bebidas': [...até 3 itens...], 'perfil_prato': [...], 'motor': 'minilm|lexico', ...}.

        refeicao/ingredientes descrevem o PRATO; preferencias é texto livre ("sem lactose", "dia de
        calor") e vira filtros e ocasião, sem influenciar o perfil do prato.
        tipo: qualquer | suco | vitamina | cha | cremosa | sem_alcool (ou o texto do formulário).
        temperatura: gelada | natural | quente | None (ou o texto do formulário).
        """
        prato = " ".join(p for p in (refeicao, ingredientes) if p and p.strip())
        if not prato.strip():
            raise ValueError("Informe a refeição ou escolha uma receita.")
        if alcool not in ("qualquer", "sem", "com"):
            alcool = "qualquer"
        temperatura = interpretar_temperatura(temperatura)
        filtros = Filtros.de(tipo, alcool, preferencias)
        so_com_alcool = alcool == "com" and not filtros.sem_alcool

        r = self.pontuar(prato, temperatura, filtros, texto_ocasiao=f"{refeicao} {preferencias}")
        itens = r["itens"]
        if so_com_alcool:
            itens = [i for i in itens if i["bebida"]["alcool"]]
        if not itens:
            raise ValueError("Nenhuma bebida do catálogo atende a todos esses filtros. "
                             "Tente remover alguma preferência.")
        # a mistura "1 com + 1 sem álcool" só vale quando o usuário não restringiu nada
        restrito = so_com_alcool or filtros.sem_alcool or filtros.tipo != "qualquer"
        # se o usuário já escolheu UM tipo (só sucos, só chás...), não faz sentido limitar a 2 do mesmo tipo
        limite_tipo = qtd if filtros.tipo in ("suco", "vitamina", "cha") else MAX_MESMO_TIPO
        escolhidas = self._escolher(itens, qtd, "restrito" if restrito else "qualquer", limite_tipo)

        saida = []
        for it in escolhidas:
            b = it["bebida"]
            sim_pct = max(0, min(100, round(it["similaridade"] * 100)))
            saida.append({
                "id": b["id"],
                "nome": b["nome"],
                "tipo": b["tipo"],
                "alcool": b["alcool"],
                "teor": b["teor"],
                "temperatura": b["temperatura"],
                "descricao": b["descricao"],
                "tags": sorted(set(b["sabores"])),
                "pontuacao": it["pontuacao"],
                "justificativa": self._justificativa(b, r["tags"], it["motivos"], sim_pct),
                "alerta": it["alertas"][0] if it["alertas"] else None,
            })
        filtros_txt = filtros.descricao()
        if alcool == "com":
            filtros_txt.append("Com álcool")
        if temperatura:
            filtros_txt.append({"gelada": "Gelada", "quente": "Quente", "natural": "Temperatura ambiente"}[temperatura])
        aviso = None
        if len(saida) < qtd:
            aviso = f"Só {len(saida)} bebida(s) do catálogo atendem a esses filtros."
        return {
            "bebidas": saida,
            "perfil_prato": r["tags"],
            "ocasioes": r["ocasioes"],
            "filtros": filtros_txt,
            "aviso": aviso,
            "motor": getattr(self.motor, "nome", "?"),
        }


# --------------------------------------------------------------------------- #
# Singleton (o MiniLM só deve carregar uma vez por processo)
# --------------------------------------------------------------------------- #
_unico: Optional[Recomendador] = None
_trava = threading.Lock()


def obter_recomendador() -> Recomendador:
    global _unico
    with _trava:
        if _unico is None:
            _unico = Recomendador()
    return _unico


def definir_recomendador(r: Optional[Recomendador]) -> None:
    """Usado nos testes para injetar um recomendador específico."""
    global _unico
    with _trava:
        _unico = r
