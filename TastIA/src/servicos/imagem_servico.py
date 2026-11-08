import io
from typing import Dict, Tuple
from PIL import Image, ImageOps, UnidentifiedImageError

EXTENSOES_PERMITIDAS = {"png", "jpg", "jpeg", "webp", "bmp"}
TAMANHO_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
LADO_MAX_PADRAO = 1024  # Reduz fotos grandes de celular para no máximo 1024px


def extensao_valida(nome_arquivo: str) -> bool:
    return (
        bool(nome_arquivo)
        and "." in nome_arquivo
        and nome_arquivo.rsplit(".", 1)[1].lower() in EXTENSOES_PERMITIDAS
    )


def receber_e_reduzir_imagem(
    conteudo_bytes: bytes,
    nome_arquivo: str = "foto.jpg",
    lado_max: int = LADO_MAX_PADRAO,
) -> Tuple[Image.Image, Dict]:
    """Valida os bytes da imagem enviada, corrige orientação EXIF e reduz suas dimensões."""
    if not nome_arquivo or not nome_arquivo.strip():
        raise ValueError("Arquivo de imagem vazio ou não selecionado.")

    if not extensao_valida(nome_arquivo):
        raise ValueError("Formato de imagem inválido. Envie PNG, JPG, JPEG ou WEBP.")

    if not conteudo_bytes:
        raise ValueError("O arquivo enviado está vazio (0 bytes).")

    if len(conteudo_bytes) > TAMANHO_MAX_BYTES:
        raise ValueError("A imagem excede o tamanho máximo permitido de 10 MB.")

    try:
        verificador = Image.open(io.BytesIO(conteudo_bytes))
        verificador.verify()
        imagem = Image.open(io.BytesIO(conteudo_bytes))
        imagem = ImageOps.exif_transpose(imagem).convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError) as e:
        raise ValueError("Arquivo inválido ou imagem corrompida.") from e

    largura_orig, altura_orig = imagem.size
    reduzida = False

    if max(largura_orig, altura_orig) > lado_max:
        imagem.thumbnail((lado_max, lado_max), Image.Resampling.LANCZOS)
        reduzida = True

    largura_final, altura_final = imagem.size
    metadados = {
        "largura_original": largura_orig,
        "altura_original": altura_orig,
        "largura": largura_final,
        "altura": altura_final,
        "foi_reduzida": reduzida,
        "bytes_originais": len(conteudo_bytes),
    }
    return imagem, metadados