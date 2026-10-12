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
        CREATE TABLE IF NOT EXISTS inventario (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            nome TEXT NOT NULL,
            categoria TEXT NOT NULL,
            quantidade TEXT NOT NULL,
            validade DATE,
            atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (usuario_id) REFERENCES usuarios (id)
        )
    ''')

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
            receita_id INTEGER NOT NULL,
            nome_bebida TEXT NOT NULL,
            justificativa TEXT NOT NULL,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (receita_id) REFERENCES receitas (id)
        )
    ''')

    conn.commit()
    conn.close()

if __name__ == '__main__':
    criar_tabelas()
    print("Base de dados e tabelas criadas com sucesso!")
    