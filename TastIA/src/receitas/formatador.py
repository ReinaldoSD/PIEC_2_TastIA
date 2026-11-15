import re
from typing import List, Optional

from receitas.validador import _eh_basico, _tokens_inventario, normalizar_texto

_RE_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)
_RE_TOKEN_ESPECIAL = re.compile(r"<\|[^|>]*\|>")
_RE_CERCA = re.compile(r"^\s*(```|~~~).*$", re.MULTILINE)
_RE_MARCADOR = re.compile(r"^(?:[-*•·+]|–|—)\s+(.*)$")
_RE_NUMERADO = re.compile(r"^\d+\s*[.)\-:]\s*(.*)$")
_RE_TITULO_MD = re.compile(r"^#{1,6}\s*")

_RE_H_ING = re.compile(r"^ingredientes?\b")
_RE_H_PREPARO = re.compile(r"^(modo de (preparo|fazer)|preparo|instrucoes|como fazer|passo a passo)\b")
_RE_TEMPO = re.compile(r"^tempo\b")
_RE_PORCOES = re.compile(r"^(porc(ao|oes)|rendimento|serve)\b")
_RE_FECHAMENTO = re.compile(
    r"^(dica|dicas|observac\w*|obs\b|nota|notas|bom apetite|espero|variac\w*|sugestao|sugestoes|"
    r"curiosidade|informac\w*)\b"
)
_RE_FIM_FRASE = re.compile(r"[.!?)\]\"']$")
# Palavras que não terminam uma frase: se o texto acaba nelas, ele foi cortado no meio.
_PALAVRAS_PENDENTES = {
    "de", "da", "do", "das", "dos", "a", "o", "as", "os", "e", "em", "com", "sem", "para", "por",
    "no", "na", "nos", "nas", "um", "uma", "ou", "ao", "aos", "alguns", "algumas", "que", "se",
    "ate", "cerca", "cada", "mais",
}


# --------------------------------------------------------------------------- #
# Limpeza de markdown
# --------------------------------------------------------------------------- #
def _limpar_enfase(linha: str) -> str:
    """Remove **negrito**, __negrito__, *itálico*, _itálico_ e `código` de uma linha."""
    linha = re.sub(r"\*\*(.+?)\*\*", r"\1", linha)
    linha = re.sub(r"__(.+?)__", r"\1", linha)
    linha = re.sub(r"(?<![\w*])\*(?!\s)([^*\n]+?)(?<!\s)\*(?![\w*])", r"\1", linha)
    linha = re.sub(r"(?<![\w_])_(?!\s)([^_\n]+?)(?<!\s)_(?![\w_])", r"\1", linha)
    linha = linha.replace("`", "")
    return linha.replace("**", "").replace("__", "")


def limpar_markdown(texto: Optional[str]) -> str:
    """Tira marcas de markdown, blocos <think> e tokens especiais, linha por linha."""
    texto = _RE_THINK.sub("", str(texto or ""))
    texto = _RE_TOKEN_ESPECIAL.sub("", texto)
    texto = _RE_CERCA.sub("", texto)
    saida: List[str] = []
    for bruta in texto.replace("\r", "").splitlines():
        s = bruta.strip()
        if not s or re.fullmatch(r"[-*_=]{3,}", s):  # linha em branco ou separador '---'
            continue
        s = _RE_TITULO_MD.sub("", s)
        s = re.sub(r"^>+\s*", "", s)
        marcador = _RE_MARCADOR.match(s)
        prefixo = ""
        if marcador and not re.match(r"^\*\*", s):
            prefixo, s = "- ", marcador.group(1)
        s = _limpar_enfase(s)
        s = re.sub(r"\s+", " ", s).strip()
        if s:
            saida.append(prefixo + s)
    return "\n".join(saida)


# --------------------------------------------------------------------------- #
# Padronização
# --------------------------------------------------------------------------- #
def _sem_marcador(linha: str) -> str:
    linha = linha.strip()
    m = _RE_MARCADOR.match(linha) or _RE_NUMERADO.match(linha)
    return (m.group(1) if m else linha).strip()


def _norm(linha: str) -> str:
    return normalizar_texto(_sem_marcador(linha)).strip(" :")


def _eh_cabecalho_ing(linha: str) -> bool:
    return not linha.startswith("- ") and len(linha) < 60 and bool(_RE_H_ING.match(_norm(linha)))


def _eh_cabecalho_preparo(linha: str) -> bool:
    n = _norm(linha)
    return (not linha.startswith("- ") and not linha[:1].isdigit() and len(linha) < 40
            and bool(_RE_H_PREPARO.match(n)))


def _eh_meta(linha: str) -> bool:
    n = normalizar_texto(linha).strip()
    return bool(_RE_TEMPO.match(n) or _RE_PORCOES.match(n))


def _valor_apos_dois_pontos(linha: str) -> str:
    return linha.split(":", 1)[1].strip() if ":" in linha else ""


def _cortado(passo: str) -> bool:
    """True se o passo parece interrompido no meio da frase."""
    if _RE_FIM_FRASE.search(passo):
        return False
    palavras = normalizar_texto(passo).strip(" ,;:-").split()
    return passo.rstrip().endswith((",", ";", ":", "-")) or (bool(palavras) and palavras[-1] in _PALAVRAS_PENDENTES)


def _capitalizar(texto: str) -> str:
    for i, c in enumerate(texto):
        if c.isalpha():
            return texto[:i] + c.upper() + texto[i + 1:]
    return texto


# Se o modelo copiar o modelo do prompt ("<Título da receita>") em vez de inventar o nome, não vale como título.
_TITULOS_VAZIOS = {"titulo da receita", "nome da receita", "titulo", "nome", "receita", "titulo da receita aqui",
                  "nome do prato", "prato", "nome da receita aqui"}

_UNIDADES = (
    r"kg|g|mg|ml|l|litros?|xicaras?|xic|copos?|colheres?|colher|c\.?\s*s\.?|c\.?\s*c\.?|sopa|cha|sobremesa|"
    r"unidades?|unid|dentes?|pitadas?|fatias?|latas?|pacotes?|caixas?|maos?|punhados?|talos?|folhas?|ramos?|"
    r"pedacos?|cubos?|a gosto"
)

# Saudações e vocativos: "Olá!", "Bom dia, chef!", "Caro usuário,", "Pessoal,".
_RE_SAUDACAO = re.compile(
    r"^(?:"
    r"(?:ola|oi+e?|opa|e ai|eai|fala|salve|hey|hello|hi|bom dia|boa tarde|boa noite|boa madrugada|"
    r"bem[- ]vind[oa]s?|seja bem[- ]vind[oa]|tudo bem|tudo certo|tudo joia|como vai|como esta|"
    r"saudacoes|cumprimentos|prezad[oa]s?|querid[oa]s?|caro usuario|cara usuaria|caro cliente|"
    r"cara cliente|meu amigo|minha amiga|meus amigos)\b"
    r"|(?:amig[oa]s?|pessoal|galera|gente|chef|cozinheir[oa]s?|usuari[oa]s?|cliente|senhor[a]?|sr|sra|"
    r"doutor[a]?)(?=[,!:;.?]|$)"
    r")"
)

# Apresentação da receita sem ambiguidade (nunca começa um nome de receita nem um passo).
_RE_APRES_FORTE = re.compile(
    r"^(?:"
    r"aqui (?:esta|estao|vai|vem|tem|temos|segue|seguem|fica|ficam|vao)|ai (?:esta|vai|vem)|la vai|eis\b|"
    r"segue\b|seguem\b|"
    r"vou (?:te |lhe )?(?:criar|fazer|preparar|sugerir|montar|elaborar|gerar|ajudar|cozinhar|desenvolver|"
    r"apresentar|compartilhar|trazer|passar|escrever|dar|mostrar|propor|indicar|buscar|pensar|usar|utilizar)|"
    r"vamos (?:la|comecar|cozinhar|preparar|fazer|criar|começar)|bora\b|mao na massa|pronto para|"
    r"irei\b|posso (?:te |lhe )?(?:sugerir|criar|fazer|preparar|ajudar|apresentar|montar)|"
    r"deixa eu|deixe-me|permita-me|gostaria de|"
    r"preparei|criei|montei|gerei|elaborei|desenvolvi|preparamos|criamos|escolhi|selecionei|pensei|separei|"
    r"sugiro|recomendo|proponho|minha (?:sugestao|receita|ideia|proposta)|sugestao de receita|"
    r"espero\b|tomara|desejo\b|"
    r"como (?:assistente|tastia|ia\b|um assistente|uma ia|chef|modelo)|sou (?:o|a|um|uma) |eu sou|me chamo|meu nome|"
    r"voce (?:pediu|solicitou|quer|queria|gostaria|tem|possui|disse|informou|forneceu)|"
    r"here (?:is|are|s)\b|here's|below is|this is\b|let me|let's|i (?:will|ll|can|have|would)|i'll|"
    r"obrigad[oa]|agradeco|valeu|desculp\w*|perdao|lamento|sinto muito|peco desculpas|"
    r"entendo\b|compreendo|percebi|notei|corrigindo|refiz|refeita|nova versao|versao corrigida|correcao"
    r")"
)

# Apresentação mais genérica: vale para o TÍTULO, mas não para linhas do preparo
_RE_APRES_FRACA = re.compile(
    r"^(?:"
    r"a seguir|abaixo|logo abaixo|veja\b|confira|olha\b|vamos\b|"
    r"com (?:base|os ingredientes|o que|as informacoes|esses|estes|aquilo|tudo)|de acordo|conforme|"
    r"como (?:solicitado|pedido|combinado|requisitado|desejado|sugerido|voce|ha|nao|so|tem|esta)|"
    r"considerando|usando|utilizando|baseado|baseada|baseando|pensando|levando em|tendo em|dado que|dados os|"
    r"partindo|a partir|seguindo|respeitando|atendendo|apenas com|somente com|so com|ja que|visto que|"
    r"uma vez que|"
    r"para (?:voce|voces|atender|aproveitar|usar|utilizar|seguir|cumprir|o seu|a sua|os seus|as suas|"
    r"seu |sua |o pedido|resolver)|"
    r"que tal|uma (?:receita|sugestao|opcao|ideia|proposta|otima|deliciosa|boa)|essa receita|esta receita|"
    r"sua receita|a receita (?:de hoje|abaixo|a seguir|sugerida|que|e a|ficou)|"
    r"receita (?:sugerida|para voce|personalizada|abaixo|a seguir|pronta|de hoje)|"
    r"importante|atencao|aviso\b|nota\b|notas\b|observacao|observacoes|obs\b|lembre|lembrando|lembrete|"
    r"vale (?:lembrar|ressaltar|destacar)|cabe (?:lembrar|ressaltar)|ressalto|informo|"
    r"primeiro(?:,| vou| preciso)|vamos ver|deixa ver|analisando|analisei|verificando|"
    r"pedido\b|resposta\b|resultado\b|saida\b|assistente\b|tastia\b|system\b|user\b|assistant\b"
    r")"
)

# Interjeições coladas na frente da frase: "Claro! ...", "Com certeza, ...", "Ótima escolha! ...".
_RE_INTERJEICAO = re.compile(
    r"^\s*(?:"
    r"claro(?: que sim)?|certo|ok|okay|perfeito|[oó]timo|excelente|entendi|entendido|beleza|combinado|"
    r"com certeza|certamente|sem problemas?|pois n[aã]o|tudo bem|sim|l[oó]gico|show|legal|maravilha|"
    r"fant[aá]stic[oa]|pronto|feito|uau|hum+|hmm+|bem|ent[aã]o|bom|adorei|"
    r"sure|of course|certainly|great|thanks|thank you|"
    r"[oó]tim[ao] (?:escolha|ideia|id[eé]ia|pedido)|boa (?:escolha|ideia|id[eé]ia)|"
    r"excelente (?:escolha|ideia|id[eé]ia)|que (?:legal|[oó]timo|bom|del[ií]cia)"
    r")\s*(?:[!,.:;…\-–—]+|$)\s*",
    re.I,
)

# Palavras que não aparecem em nome de receita, mas aparecem em conversa.
_PALAVRAS_DE_CONVERSA = {
    "voce", "voces", "seu", "sua", "seus", "suas", "eu", "vou", "vamos", "posso", "podemos", "espero",
    "aqui", "obrigado", "obrigada", "tastia", "assistente", "pedido", "ingredientes", "disponiveis",
    "inventario", "prezado", "prezada", "ola", "oi", "favor", "gostaria", "desculpe", "desculpa",
    "te", "lhe", "hello", "here", "sure", "please",
}

_MAX_PALAVRAS_TITULO = 10
_MAX_CHARS_TITULO = 70


def _tirar_interjecao(texto: str) -> str:
    """'Claro! Omelete de tomate' -> 'Omelete de tomate'. Repete caso venha mais de uma ('Ok, claro! ...')."""
    for _ in range(3):
        novo = _RE_INTERJEICAO.sub("", texto, count=1)
        if novo == texto:
            break
        texto = novo
    return texto


def _resto_normalizado(linha: str) -> str:
    texto = _tirar_interjecao(_sem_marcador(linha))
    return normalizar_texto(texto).strip(" ,.!?:;-–—…\"'*<>")


def _casa_listas(resto: str, fraca: bool) -> bool:
    return bool(
        _RE_SAUDACAO.match(resto)
        or _RE_APRES_FORTE.match(resto)
        or (fraca and _RE_APRES_FRACA.match(resto))
    )


def eh_conversa_do_modelo(linha: str, estrito: bool = True) -> bool:
    resto = _resto_normalizado(linha)
    if not resto:   # só tinha 'Claro!' / 'Ok.'
        return True
    if _casa_listas(resto, fraca=estrito):
        return True
    if "," in resto:   # vocativo + frase: "Maria, aqui está sua receita"
        depois = resto.split(",", 1)[1].strip(" ,")
        if depois and _casa_listas(depois, fraca=estrito):
            return True
    if not estrito:
        return False
    palavras = re.findall(r"[a-z]+", resto)
    if _PALAVRAS_DE_CONVERSA.intersection(palavras):
        return True
    # frase longa terminada em ponto não é nome de receita
    return len(palavras) >= 8 and _sem_marcador(linha).rstrip().endswith(".")


def _conversa_solta(linha: str) -> bool:
    """Linha SEM marcador/numeração dentro de 'Ingredientes' ou 'Modo de preparo' que é só conversa."""
    return (not linha.startswith("- ") and not linha[:1].isdigit()
            and eh_conversa_do_modelo(linha, estrito=False))


def _titulo_limpo(linha: str) -> str:
    original = _sem_marcador(linha).strip()
    uteis = []
    for trecho in re.split(r"(?<=[.!?:…])\s+", original):
        trecho = trecho.strip()
        if not trecho or trecho.endswith(("!", "?")) or eh_conversa_do_modelo(trecho):
            continue
        uteis.append(trecho)
    t = " ".join(uteis).strip(" \"'<>*")
    # tira rótulos como "Título:", "Nome da receita:", "Receita:" (com ou sem acento)
    m = re.match(r"^(nome da receita|receita|t[ií]tulo)\s*:\s*(.*)$", t, flags=re.I)
    if m:
        t = m.group(2).strip(" \"'<>*")
    if not t or t.endswith(":") or re.search(r"[!?]", t):
        return ""
    t = t.rstrip(". ")
    nt = normalizar_texto(t).strip()
    if nt in _TITULOS_VAZIOS or nt.startswith(("nome do prato", "nome da receita", "titulo da receita")):
        return ""   # copiou o modelo do prompt
    if len(t.split()) > _MAX_PALAVRAS_TITULO or len(t) > _MAX_CHARS_TITULO:
        return ""   # parágrafo, não título
    if eh_conversa_do_modelo(t):   # ex.: "Título: aqui está a receita"
        return ""
    return _padronizar_titulo(t)


_RE_EMOJI = re.compile("[\U00010000-\U0010ffff\u2600-\u27bf\u2b50\ufe0f]")


def _padronizar_titulo(t: str) -> str:
    t = _RE_EMOJI.sub("", t)
    t = re.sub(r"\s+", " ", t).strip(" -–—,;")
    # 'Receita de bolo de cenoura' -> 'Bolo de cenoura' (só tira se sobrar algo; 'Receita com ovos' fica)
    m = re.match(r"^receita\s+(?:de|da|do|das|dos)\s+(.+)$", t, flags=re.I)
    if m:
        t = m.group(1)
    palavras = [w for w in t.split() if any(c.isalpha() for c in w)]
    if palavras and (t.isupper() or (len(palavras) >= 2 and all(w[:1].isupper() for w in palavras))):
        t = t.lower()   # 'OMELETE DE TOMATE' / 'Omelete De Tomate' -> 'Omelete de tomate'
    return _capitalizar(t)


def _nome_do_ingrediente(item: str) -> str:
    s = re.sub(r"^[-*•]\s*", "", item).strip()
    s = re.sub(r"\(.*?\)", "", s)
    s = re.sub(r"^[\d½¼¾⅓⅔/.,\s]+", "", s)
    s = s.split(",")[0].strip()
    for _ in range(3):  # "colheres de sopa de azeite": tira unidade e "de" repetidos
        novo = re.sub(rf"^(?:{_UNIDADES})\b\.?\s*(?:de |do |da |d')?", "", s, flags=re.I).strip()
        if novo == s:
            break
        s = novo
    return s.strip(" .-")


# Tipo de prato citado no pedido -> (rótulo, gênero). Usado só no título de reserva.
_TIPOS_DE_PRATO = [
    (r"\bcafe da manha\b|\bdesjejum\b", "Café da manhã", "m"),
    (r"\balmoc\w*", "Almoço", "m"),
    (r"\bjant\w*", "Jantar", "m"),
    (r"\blanch\w*", "Lanche", "m"),
    (r"\bsobremesa\w*", "Sobremesa", "f"),
    (r"\bsopa\w*|\bcaldo\w*", "Sopa", "f"),
    (r"\bsalada\w*", "Salada", "f"),
    (r"\bomelete\w*", "Omelete", "m"),
    (r"\bbolo\w*", "Bolo", "m"),
    (r"\bpanqueca\w*", "Panqueca", "f"),
    (r"\bsanduiche\w*", "Sanduíche", "m"),
    (r"\bvitamina\w*", "Vitamina", "f"),
]
# adjetivo citado no pedido -> (masculino, feminino)
_ADJETIVOS_DO_PEDIDO = [
    (r"\bleve\b|\bleves\b", "leve", "leve"),
    (r"\brapid[oa]s?\b", "rápido", "rápida"),
    (r"\bsimples\b", "simples", "simples"),
    (r"\bsaudavel\b|\bsaudaveis\b", "saudável", "saudável"),
]


def _rotulo_do_pedido(pedido: Optional[str]) -> str:
    """'lanche leve em 15 minutos' -> 'Lanche leve'. Devolve '' se o pedido não diz o tipo de prato."""
    n = normalizar_texto(pedido or "")
    for padrao, rotulo, genero in _TIPOS_DE_PRATO:
        if re.search(padrao, n):
            for pad_adj, masc, fem in _ADJETIVOS_DO_PEDIDO:
                if re.search(pad_adj, n):
                    return f"{rotulo} {masc if genero == 'm' else fem}"
            return rotulo
    return ""


def _titulo_pelos_ingredientes(ingredientes: List[str], pedido: Optional[str] = None) -> str:
    def coletar(pular_basicos: bool) -> List[str]:
        achados: List[str] = []
        for item in ingredientes:
            if item.endswith(":"):
                continue
            nome = _nome_do_ingrediente(item)
            if not nome or normalizar_texto(nome) in {normalizar_texto(n) for n in achados}:
                continue
            if pular_basicos and _eh_basico(_tokens_inventario(nome)):
                continue   # 'Receita com sal, água e óleo' não ajuda ninguém
            achados.append(nome.lower())
            if len(achados) == 3:
                break
        return achados

    prefixo = _rotulo_do_pedido(pedido) or "Receita"
    nomes = coletar(True) or coletar(False)
    if not nomes:
        return prefixo if prefixo != "Receita" else "Receita do dia"
    if len(nomes) == 1:
        return f"{prefixo} com {nomes[0]}"
    return f"{prefixo} com " + ", ".join(nomes[:-1]) + " e " + nomes[-1]


def formatar_receita(texto: Optional[str], pedido: Optional[str] = None) -> str:
    limpo = limpar_markdown(texto)
    linhas = limpo.splitlines()

    idx_ing = next((i for i, l in enumerate(linhas) if _eh_cabecalho_ing(l)), None)
    if idx_ing is None:
        return limpo
    idx_prep = next((i for i, l in enumerate(linhas) if i > idx_ing and _eh_cabecalho_preparo(l)), None)
    if idx_prep is None:
        return limpo

    # Título = primeira linha antes de 'Ingredientes' que seja um nome de receita de verdade.
    # Saudações, vocativos ("Olá!", "Claro! Aqui está sua receita:") e frases soltas são descartados;
    # se nada sobrar, o título vem do fallback pelos ingredientes (mais abaixo).
    titulo, tempo, porcoes = "", "", ""
    for l in linhas[:idx_ing]:
        n = normalizar_texto(l).strip()
        if _RE_TEMPO.match(n):
            tempo = tempo or _valor_apos_dois_pontos(l) or _sem_marcador(l)
        elif _RE_PORCOES.match(n):
            porcoes = porcoes or _valor_apos_dois_pontos(l) or _sem_marcador(l)
        elif not titulo:
            titulo = _titulo_limpo(l)
    # Tempo/porções também podem vir depois do título, dentro do bloco de ingredientes.
    ingredientes: List[str] = []
    vistos = set()
    for l in linhas[idx_ing + 1:idx_prep]:
        n = normalizar_texto(l).strip()
        if _RE_TEMPO.match(n) and ":" in l:
            tempo = tempo or _valor_apos_dois_pontos(l)
            continue
        if _RE_PORCOES.match(n) and ":" in l:
            porcoes = porcoes or _valor_apos_dois_pontos(l)
            continue
        if _conversa_solta(l):   # 'Aqui estão os ingredientes:' não é ingrediente
            continue
        item = _sem_marcador(l)
        chave = normalizar_texto(item)
        if not item or chave in vistos:
            continue
        vistos.add(chave)
        ingredientes.append(item if item.endswith(":") else "- " + item)

    # Modo de preparo: descarta fechamentos ('Dica:', 'Bom apetite!') e repetições.
    passos: List[str] = []
    vistos = set()
    for l in linhas[idx_prep + 1:]:
        if _conversa_solta(l):   # 'Vamos lá!' / 'Aqui estão os passos:' não é passo
            continue
        passo = _sem_marcador(l)
        if _RE_FECHAMENTO.match(normalizar_texto(passo)):
            break
        chave = normalizar_texto(passo)
        if not passo or chave in vistos:
            continue
        vistos.add(chave)
        passos.append(passo)

    # Última frase cortada pelo limite de tokens (acaba no meio, ex.: "... por alguns"): remove.
    if len(passos) > 1 and _cortado(passos[-1]):
        passos.pop()
    passos = [_capitalizar(p if _RE_FIM_FRASE.search(p) else p + ".") for p in passos]

    if not ingredientes or not passos:
        return limpo
    if not titulo:   # o modelo esqueceu o nome (ou copiou o "<Título da receita>" do prompt)
        titulo = _titulo_pelos_ingredientes(ingredientes, pedido)

    partes = [titulo]
    if tempo:
        partes.append("Tempo de preparo: " + tempo)
    if porcoes:
        partes.append("Porções: " + porcoes)
    partes += ["", "Ingredientes"] + ingredientes
    partes += ["", "Modo de preparo"] + [f"{i}. {p}" for i, p in enumerate(passos, 1)]
    return "\n".join(partes)
