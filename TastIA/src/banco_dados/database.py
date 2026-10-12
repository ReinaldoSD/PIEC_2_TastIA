import sqlite3
import os
from config import DB_PATH, DB_DIR

def garantir_diretorio_banco():
    if not os.path.exists(DB_DIR):
        os.makedirs(DB_DIR)

def obter_conexao():
    garantir_diretorio_banco()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn
