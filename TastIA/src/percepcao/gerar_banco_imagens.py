"""Gera o banco de dados de 50 FOTOS REAIS cobrindo todas as 7 categorias de percepcao/catalogo.py."""

import io
import json
import os
import sys
import time
from typing import Dict, List, Optional, Tuple
import urllib.parse
import urllib.request
from PIL import Image

RAIZ_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if RAIZ_SRC not in sys.path:
    sys.path.insert(0, RAIZ_SRC)

from banco_dados.database import obter_conexao
from percepcao.catalogo import CATALOGO, CATEGORIAS_VALIDAS, normalizar

PASTA_BANCO_IMAGENS = os.path.join(RAIZ_SRC, "banco_dados", "banco_50_imagens")

HEADERS_WIKI = {
    "User-Agent": "TastIA_AcademicProject_UFRPE/1.0 (https://ufrpe.br; contato@ufrpe.br) Python-urllib/3.14",
    "Accept": "application/json, image/*;q=0.9",
}

# Mapeamento dos 50 ingredientes -> Lista de candidatos (idioma_wiki, titulo_artigo) + termo Commons
MAPA_50_INGREDIENTES_REAIS: Dict[str, Tuple[List[Tuple[str, str]], str]] = {
    # 1. Verduras e legumes (13)
    "Tomate": ([("en", "Tomato"), ("pt", "Tomate")], "fresh red tomato"),
    "Cebola": ([("en", "Onion"), ("pt", "Cebola")], "onion bulb"),
    "Alho": ([("pt", "Alho"), ("en", "Garlic")], "garlic bulb"),
    "Batata": ([("en", "Potato"), ("pt", "Batata")], "potato tuber"),
    "Cenoura": ([("en", "Carrot"), ("pt", "Cenoura")], "carrot root"),
    "Pimentão": ([("en", "Bell pepper"), ("pt", "Pimentão")], "bell pepper"),
    "Alface": ([("en", "Lettuce"), ("pt", "Alface")], "lettuce leaf"),
    "Brócolis": ([("en", "Broccoli"), ("pt", "Brócolis")], "broccoli"),
    "Abóbora": ([("en", "Pumpkin"), ("pt", "Abóbora")], "pumpkin squash"),
    "Abobrinha": ([("en", "Zucchini"), ("pt", "Abobrinha")], "zucchini"),
    "Beterraba": ([("en", "Beetroot"), ("pt", "Beterraba")], "beetroot"),
    "Couve": ([("en", "Kale"), ("pt", "Couve")], "kale leaf"),
    "Pepino": ([("en", "Cucumber"), ("pt", "Pepino")], "cucumber"),
    # 2. Frutas (10)
    "Banana": ([("en", "Banana"), ("pt", "Banana")], "banana fruit"),
    "Maçã": ([("en", "Apple"), ("pt", "Maçã")], "red apple"),
    "Laranja": ([("en", "Orange (fruit)"), ("pt", "Laranja")], "orange citrus"),
    "Limão": ([("en", "Lime (fruit)"), ("pt", "Limão")], "green lime"),
    "Abacaxi": ([("en", "Pineapple"), ("pt", "Abacaxi")], "pineapple"),
    "Abacate": ([("pt", "Abacate"), ("en", "Avocado")], "avocado"),
    "Coco": ([("en", "Coconut"), ("pt", "Coco")], "coconut"),
    "Mamão": ([("en", "Papaya"), ("pt", "Mamão")], "papaya"),
    "Manga": ([("en", "Mango"), ("pt", "Manga")], "mango fruit"),
    "Melancia": ([("pt", "Melancia"), ("en", "Watermelon")], "watermelon"),
    # 3. Laticínios (7)
    "Leite": ([("en", "Milk"), ("pt", "Leite")], "glass of milk"),
    "Queijo": ([("en", "Cheese"), ("pt", "Queijo")], "cheese wheel"),
    "Queijo mussarela": ([("en", "Mozzarella"), ("pt", "Muçarela")], "mozzarella cheese"),
    "Manteiga": ([("en", "Butter"), ("pt", "Manteiga")], "butter block"),
    "Iogurte": ([("en", "Yogurt"), ("pt", "Iogurte")], "yogurt bowl"),
    "Requeijão": ([("pt", "Requeijão"), ("en", "Requeijão"), ("en", "Cream cheese")], "requeijao"),
    "Creme de leite": ([("pt", "Creme de leite"), ("en", "Cream")], "heavy cream"),
    # 4. Carnes (8)
    "Frango": ([("en", "Chicken as food"), ("pt", "Carne de frango")], "raw chicken meat"),
    "Carne bovina": ([("en", "Beef"), ("pt", "Carne bovina")], "raw beef steak"),
    "Carne moída": ([("en", "Ground beef"), ("pt", "Carne moída")], "minced beef"),
    "Linguiça": ([("pt", "Linguiça"), ("en", "Linguiça")], "linguica sausage"),
    "Calabresa": ([("pt", "Linguiça calabresa"), ("en", "Pepperoni"), ("en", "Chorizo")], "linguica calabresa"),
    "Bacon": ([("en", "Bacon"), ("pt", "Bacon")], "bacon strips"),
    "Presunto": ([("en", "Ham"), ("pt", "Presunto")], "sliced ham"),
    "Peixe": ([("en", "Fish as food"), ("pt", "Peixe (alimento)"), ("en", "Tilapia")], "fish fillet"),
    # 5. Grãos e cereais (5)
    "Arroz": ([("en", "White rice"), ("pt", "Arroz")], "white rice"),
    "Feijão": ([("pt", "Feijão"), ("en", "Common bean")], "common beans"),
    "Macarrão": ([("en", "Spaghetti"), ("pt", "Espaguete"), ("pt", "Macarrão")], "spaghetti pasta"),
    "Pão": ([("en", "Bread"), ("pt", "Pão")], "loaf of bread"),
    "Milho": ([("pt", "Milho"), ("en", "Maize")], "sweet corn"),
    # 6. Bebidas (4)
    "Refrigerante": ([("en", "Soft drink"), ("pt", "Refrigerante")], "soft drink soda"),
    "Suco": ([("en", "Orange juice"), ("pt", "Suco de laranja")], "orange juice"),
    "Água": ([("en", "Bottled water"), ("pt", "Água mineral")], "water bottle"),
    "Café": ([("en", "Roasted coffee"), ("pt", "Café (bebida)"), ("en", "Coffee bean")], "coffee beans"),
    # 7. Outros (3)
    "Ovo": ([("en", "Egg as food"), ("pt", "Ovo (alimento)"), ("en", "Egg")], "chicken eggs"),
    "Biscoito": ([("en", "Biscuit"), ("pt", "Biscoito"), ("en", "Cookie")], "biscuits cookies"),
    "Molho de tomate": ([("en", "Tomato sauce"), ("pt", "Molho de tomate"), ("en", "Marinara sauce")], "tomato sauce"),
}


def _requisitar_json(url: str) -> dict:
    req = urllib.request.Request(url, headers=HEADERS_WIKI)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _baixar_e_salvar_jpeg(url_imagem: str, destino: str) -> bool:
    req = urllib.request.Request(url_imagem, headers=HEADERS_WIKI)
    with urllib.request.urlopen(req, timeout=15) as resp:
        dados_bytes = resp.read()
    img = Image.open(io.BytesIO(dados_bytes)).convert("RGB")
    if img.width < 80 or img.height < 80:
        return False
    img.thumbnail((800, 800), Image.Resampling.LANCZOS)
    img.save(destino, format="JPEG", quality=92)
    return True


def _buscar_url_wikipedia_pageimages(idioma: str, titulo_artigo: str) -> Optional[str]:
    """Busca a foto principal do artigo na Wikipedia (en ou pt)."""
    url = (
        f"https://{idioma}.wikipedia.org/w/api.php?action=query"
        f"&titles={urllib.parse.quote(titulo_artigo)}"
        "&prop=pageimages&piprop=original|thumbnail&pithumbsize=800&redirects=1&format=json"
    )
    dados = _requisitar_json(url)
    paginas = dados.get("query", {}).get("pages", {})
    for p in paginas.values():
        thumb = p.get("thumbnail", {}).get("source")
        orig = p.get("original", {}).get("source")
        for candidato in (thumb, orig):
            if candidato and not candidato.lower().endswith((".svg", ".pdf", ".ogg", ".webm", ".gif")):
                return candidato
    return None


def _buscar_url_commons_namespace_file(termo_busca: str) -> Optional[str]:
    """Busca no namespace 6 (File:) da Wikimedia Commons."""
    q = urllib.parse.quote(termo_busca)
    url = (
        "https://commons.wikimedia.org/w/api.php?action=query"
        f"&generator=search&gsrnamespace=6&gsrsearch={q}&gsrlimit=8"
        "&prop=imageinfo&iiprop=url&iiurlwidth=800&format=json"
    )
    dados = _requisitar_json(url)
    paginas = dados.get("query", {}).get("pages", {})
    for p in paginas.values():
        for info in p.get("imageinfo", []):
            candidato = info.get("thumburl") or info.get("url")
            if candidato and not candidato.lower().endswith((".svg", ".pdf", ".ogg", ".webm", ".gif", ".tif")):
                return candidato
    return None


def baixar_foto_real_ingrediente(nome_pt: str, destino: str) -> str:
    artigos_wiki, termo_commons = MAPA_50_INGREDIENTES_REAIS[nome_pt]

    # 1. Tenta cada candidato de artigo na Wikipedia (PT e EN)
    for idioma, titulo in artigos_wiki:
        try:
            url = _buscar_url_wikipedia_pageimages(idioma, titulo)
            if url and _baixar_e_salvar_jpeg(url, destino):
                return f"wikipedia_{idioma}"
        except Exception as e:
            print(f"   [Aviso Wiki {idioma}:{titulo}] {e}")

    # 2. Tenta busca direta de arquivos na Wikimedia Commons
    for termo in (termo_commons, nome_pt):
        try:
            url = _buscar_url_commons_namespace_file(termo)
            if url and _baixar_e_salvar_jpeg(url, destino):
                return "wikimedia_commons"
        except Exception as e:
            print(f"   [Aviso Commons {termo}] {e}")

    raise RuntimeError(f"Não foi possível baixar foto real para '{nome_pt}'. Verifique sua conexão.")


def _ja_eh_foto_real(caminho: str) -> bool:
    """Verifica se o arquivo já existe e não é um quadrado de cor única (fallback antigo)."""
    if not os.path.exists(caminho) or os.path.getsize(caminho) < 5000:
        return False
    try:
        img = Image.open(caminho).convert("RGB")
        # Um quadrado sintético tem pouquíssimas cores; uma foto real tem milhares
        cores = img.getcolors(maxcolors=256)
        return cores is None
    except Exception:
        return False


def construir_banco_50_imagens() -> List[Dict]:
    assert len(MAPA_50_INGREDIENTES_REAIS) == 50, "A seleção deve conter exatamente 50 ingredientes."
    os.makedirs(PASTA_BANCO_IMAGENS, exist_ok=True)

    conn = obter_conexao()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS banco_imagens_ingredientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome_ingrediente TEXT NOT NULL,
            categoria TEXT NOT NULL,
            prompt_clip TEXT NOT NULL,
            caminho_arquivo TEXT NOT NULL,
            origem TEXT NOT NULL
        )
    """)
    conn.execute("DELETE FROM banco_imagens_ingredientes")

    manifesto: List[Dict] = []

    print("Verificando e baixando as 50 fotos reais de ingredientes...\n")
    for idx, nome in enumerate(MAPA_50_INGREDIENTES_REAIS.keys(), start=1):
        info = CATALOGO[nome]
        categoria = info["categoria"]
        prompt_principal = info["prompts"][0]

        pasta_cat = os.path.join(PASTA_BANCO_IMAGENS, normalizar(categoria).replace(" ", "_"))
        os.makedirs(pasta_cat, exist_ok=True)

        nome_arq = f"{idx:02d}_{normalizar(nome).replace(' ', '_')}.jpg"
        caminho_completo = os.path.join(pasta_cat, nome_arq)

        if _ja_eh_foto_real(caminho_completo):
            origem = "cache_local_real"
            print(f"[{idx:02d}/50] JÁ EXISTE -> {nome} ({categoria}) mantido.")
        else:
            origem = baixar_foto_real_ingrediente(nome, caminho_completo)
            print(f"[{idx:02d}/50] OK -> {nome} ({categoria}) salvo de [{origem}]")
            time.sleep(0.25)

        registro = {
            "id": idx,
            "nome": nome,
            "categoria": categoria,
            "prompts_clip": list(info["prompts"]),
            "arquivo": os.path.relpath(caminho_completo, RAIZ_SRC),
            "origem": origem,
        }
        manifesto.append(registro)

        conn.execute(
            """INSERT INTO banco_imagens_ingredientes
               (nome_ingrediente, categoria, prompt_clip, caminho_arquivo, origem)
               VALUES (?, ?, ?, ?, ?)""",
            (nome, categoria, prompt_principal, registro["arquivo"], origem),
        )

    conn.commit()
    conn.close()

    caminho_manifesto = os.path.join(PASTA_BANCO_IMAGENS, "manifesto_50_imagens.json")
    with open(caminho_manifesto, "w", encoding="utf-8") as f:
        json.dump(
            {
                "total_imagens": len(manifesto),
                "categorias_cobertas": list(CATEGORIAS_VALIDAS),
                "imagens": manifesto,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    print(f"\n[SUCESSO] Todas as 50 fotos reais estão prontas em: {PASTA_BANCO_IMAGENS}")
    return manifesto


if __name__ == "__main__":
    construir_banco_50_imagens()