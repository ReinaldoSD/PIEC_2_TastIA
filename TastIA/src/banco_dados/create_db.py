from banco_dados.database import obter_conexao


def criar_tabelas():
    conn = obter_conexao()
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            senha_hash TEXT NOT NULL,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS codigos_recuperacao (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            codigo_hash TEXT NOT NULL,
            expira_em TEXT NOT NULL,
            tentativas INTEGER NOT NULL DEFAULT 0,
            usado INTEGER NOT NULL DEFAULT 0,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (usuario_id) REFERENCES usuarios (id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS inventario (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            nome TEXT NOT NULL,
            categoria TEXT NOT NULL,
            quantidade TEXT NOT NULL,
            unidade TEXT DEFAULT 'unidade',
            validade DATE,
            atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (usuario_id) REFERENCES usuarios (id)
        )
    ''')

    # Garante a coluna 'unidade' mesmo se o arquivo tastia.db já existia antes
    colunas_inv = [
        linha["name"]
        for linha in cursor.execute("PRAGMA table_info(inventario)").fetchall()
    ]
    if "unidade" not in colunas_inv:
        cursor.execute("ALTER TABLE inventario ADD COLUMN unidade TEXT DEFAULT 'unidade'")

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS receitas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            pedido TEXT NOT NULL,
            conteudo TEXT NOT NULL,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (usuario_id) REFERENCES usuarios (id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bebidas_sugeridas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            receita_id INTEGER,
            nome_bebida TEXT NOT NULL,
            justificativa TEXT NOT NULL,
            refeicao TEXT,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (usuario_id) REFERENCES usuarios (id),
            FOREIGN KEY (receita_id) REFERENCES receitas (id)
        )
    ''')

    # Garante a coluna 'refeicao' (usada pelas bebidas salvas sem receita) em bancos já existentes
    colunas_beb = [
        linha["name"]
        for linha in cursor.execute("PRAGMA table_info(bebidas_sugeridas)").fetchall()
    ]
    if "refeicao" not in colunas_beb:
        cursor.execute("ALTER TABLE bebidas_sugeridas ADD COLUMN refeicao TEXT")

    conn.commit()
    conn.close()


if __name__ == '__main__':
    criar_tabelas()
    print("Base de dados e tabelas criadas com sucesso!")
