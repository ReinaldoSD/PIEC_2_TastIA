import hashlib

from flask import current_app

def gerar_hash_codigo(codigo):
    valor = f"{codigo}:{current_app.config['SECRET_KEY']}"
    return hashlib.sha256(valor.encode('utf-8')).hexdigest()
