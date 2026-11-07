import threading
from flask import Flask, render_template, jsonify, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from config import Config
from banco_dados.create_db import criar_tabelas
from servicos.modelos_servico import baixar_ou_carregar_modelos
from banco_dados.database import obter_conexao
from rotas.receita import bp_receita
from rotas.bebida import bp_bebida
from rotas.ingrediente import bp_ingrediente
from servicos.fila import obter_fila

app = Flask(__name__)
app.config.from_object(Config)

app.register_blueprint(bp_receita)
app.register_blueprint(bp_bebida)
app.register_blueprint(bp_ingrediente)

with app.app_context():
    criar_tabelas()
    baixar_ou_carregar_modelos()


@app.errorhandler(400)
def erro_requisicao_invalida(e):
    return jsonify({"erro": "Requisição inválida", "detalhes": str(e)}), 400


@app.errorhandler(404)
def erro_nao_encontrado(e):
    return jsonify({"erro": "Recurso ou rota não encontrada", "detalhes": str(e)}), 404


@app.errorhandler(500)
def erro_interno_servidor(e):
    return jsonify({"erro": "Erro interno no servidor", "detalhes": str(e)}), 500


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
    if request.method == 'POST':
        nome = request.form.get('nome')
        email = request.form.get('email')
        senha = request.form.get('senha')

        if not nome or not email or not senha:
            flash('Por favor, preencha todos os campos.', 'erro')
            return redirect(url_for('cadastro'))

        conn = obter_conexao()
        cursor = conn.cursor()
        
        usuario_existente = cursor.execute('SELECT id FROM usuarios WHERE email = ?', (email,)).fetchone()
        if usuario_existente:
            flash('Este e-mail já está registado.', 'erro')
            conn.close()
            return redirect(url_for('cadastro'))

        senha_hash = generate_password_hash(senha)
        cursor.execute('INSERT INTO usuarios (nome, email, senha_hash) VALUES (?, ?, ?)', (nome, email, senha_hash))
        conn.commit()
        conn.close()

        flash('Conta criada com sucesso! Faça login para continuar.', 'sucesso')
        return redirect(url_for('login'))

    return render_template('cadastro.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        senha = request.form.get('senha')

        if not email or not senha:
            flash('Por favor, preencha o e-mail e a senha.', 'erro')
            return redirect(url_for('login'))

        conn = obter_conexao()
        cursor = conn.cursor()
        usuario = cursor.execute('SELECT * FROM usuarios WHERE email = ?', (email,)).fetchone()
        conn.close()

        if usuario and check_password_hash(usuario['senha_hash'], senha):
            session['usuario_id'] = usuario['id']
            session['usuario_nome'] = usuario['nome']
            session['usuario_email'] = usuario['email']
            flash('Login efetuado com sucesso!', 'sucesso')
            return redirect(url_for('dashboard'))
        else:
            flash('E-mail ou senha incorretos.', 'erro')
            return redirect(url_for('login'))

    return render_template('login.html')


@app.route('/esqueci_senha', methods=['GET', 'POST'])
def recuperar_senha():
    if request.method == 'POST':
        email = request.form.get('email')
        if not email:
            flash('Por favor, informe o seu e-mail.', 'erro')
            return redirect(url_for('recuperar_senha'))
        
        flash('Se o e-mail estiver registado, receberá instruções de recuperação.', 'sucesso')
        return redirect(url_for('login'))
        
    return render_template('esqueci_senha.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('Sessão encerrada com sucesso.', 'sucesso')
    return redirect(url_for('index'))


@app.route('/dashboard')
def dashboard():
    if 'usuario_id' not in session:
        flash('Faça login para aceder à dashboard.', 'erro')
        return redirect(url_for('login'))
    return render_template('dashboard.html', nome_usuario=session.get('usuario_nome'))


@app.route('/inventario')
def inventario():
    if 'usuario_id' not in session:
        flash('Faça login para aceder ao inventário.', 'erro')
        return redirect(url_for('login'))
    
    conn = obter_conexao()
    itens = conn.execute(
        'SELECT * FROM inventario WHERE usuario_id = ? ORDER BY nome COLLATE NOCASE',
        (session['usuario_id'],)
    ).fetchall()
    conn.close()

    return render_template('inventario.html', itens=itens)


@app.route('/cadastrar_ingrediente', methods=['GET', 'POST'])
def cadastrar_ingrediente():
    if 'usuario_id' not in session:
        flash('Faça login para continuar.', 'erro')
        return redirect(url_for('login'))

    if request.method == 'POST':
        from rotas.ingrediente import _formatar_qtd_unidade, _buscar_duplicado
        nome = (request.form.get('nome') or '').strip()
        categoria = (request.form.get('categoria') or 'Outros').strip()
        quantidade = (request.form.get('quantidade') or '').strip()
        unidade = (request.form.get('unidade') or '').strip()
        validade = request.form.get('validade') or None

        if not nome or not quantidade:
            flash('Informe o nome e a quantidade do ingrediente.', 'erro')
            return redirect(url_for('cadastrar_ingrediente'))

        conn = obter_conexao()
        duplicado = _buscar_duplicado(conn, session['usuario_id'], nome)
        if duplicado:
            conn.close()
            flash(f"O ingrediente '{duplicado['nome']}' já está cadastrado no seu inventário.", 'erro')
            return redirect(url_for('cadastrar_ingrediente'))

        qtd_final, unid_final = _formatar_qtd_unidade(quantidade, unidade)
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO inventario (usuario_id, nome, categoria, quantidade, unidade, validade) VALUES (?, ?, ?, ?, ?, ?)',
            (session['usuario_id'], nome, categoria, qtd_final, unid_final, validade)
        )
        conn.commit()
        conn.close()

        flash('Ingrediente cadastrado com sucesso!', 'sucesso')
        return redirect(url_for('inventario'))

    return render_template('cadastrar_ingrediente.html')
@app.route('/editar_ingrediente/<int:item_id>', methods=['POST'])
def editar_ingrediente(item_id):
    if 'usuario_id' not in session:
        flash('Faça login para continuar.', 'erro')
        return redirect(url_for('login'))

    from rotas.ingrediente import _formatar_qtd_unidade, _buscar_duplicado
    nome = (request.form.get('nome') or '').strip()
    categoria = (request.form.get('categoria') or 'Outros').strip()
    quantidade = (request.form.get('quantidade') or '').strip()
    unidade = (request.form.get('unidade') or '').strip()
    validade = request.form.get('validade') or None

    if not nome or not quantidade:
        flash('Nome e quantidade são obrigatórios.', 'erro')
        return redirect(url_for('inventario'))

    conn = obter_conexao()
    conflito = _buscar_duplicado(conn, session['usuario_id'], nome, ignorar_id=item_id)
    if conflito:
        conn.close()
        flash(f"Já existe outro ingrediente com o nome '{conflito['nome']}' no seu inventário.", 'erro')
        return redirect(url_for('inventario'))

    qtd_final, unid_final = _formatar_qtd_unidade(quantidade, unidade)
    conn.execute(
        '''UPDATE inventario
           SET nome = ?, categoria = ?, quantidade = ?, unidade = ?, validade = ?, atualizado_em = CURRENT_TIMESTAMP
           WHERE id = ? AND usuario_id = ?''',
        (nome, categoria, qtd_final, unid_final, validade, item_id, session['usuario_id'])
    )
    conn.commit()
    conn.close()
    flash('Ingrediente atualizado com sucesso!', 'sucesso')
    return redirect(url_for('inventario'))


@app.route('/excluir_ingrediente/<int:item_id>', methods=['POST'])
def excluir_ingrediente(item_id):
    if 'usuario_id' not in session:
        flash('Faça login para continuar.', 'erro')
        return redirect(url_for('login'))

    conn = obter_conexao()
    conn.execute(
        'DELETE FROM inventario WHERE id = ? AND usuario_id = ?',
        (item_id, session['usuario_id'])
    )
    conn.commit()
    conn.close()
    flash('Ingrediente removido com sucesso!', 'sucesso')
    return redirect(url_for('inventario'))


@app.route('/receitas')
def receitas():
    if 'usuario_id' not in session:
        flash('Faça login para continuar.', 'erro')
        return redirect(url_for('login'))
    return render_template('receitas.html')


@app.route('/bebidas')
def bebidas():
    if 'usuario_id' not in session:
        flash('Faça login para continuar.', 'erro')
        return redirect(url_for('login'))
    return render_template('bebidas.html')


@app.route('/historico')
def historico():
    if 'usuario_id' not in session:
        flash('Faça login para continuar.', 'erro')
        return redirect(url_for('login'))
    return render_template('historico.html')


# --------------------------------------------------------------------------- #
# ROTAS DO PERFIL COM VALIDAÇÃO E ATUALIZAÇÃO NO BANCO DE DADOS
# --------------------------------------------------------------------------- #
@app.route('/perfil')
def perfil():
    if 'usuario_id' not in session:
        flash('Faça login para continuar.', 'erro')
        return redirect(url_for('login'))
    
    conn = obter_conexao()
    usuario = conn.execute('SELECT nome FROM usuarios WHERE id = ?', (session['usuario_id'],)).fetchone()
    conn.close()
    
    return render_template('perfil.html', usuario=usuario)


@app.route('/perfil/confirmar', methods=['POST'])
def confirmar_identidade():
    if 'usuario_id' not in session:
        flash('Faça login para continuar.', 'erro')
        return redirect(url_for('login'))
        
    senha = request.form.get('senha_confirmacao', '')
    if not senha:
        flash('Por favor, informe a sua senha atual para confirmar.', 'erro')
        return redirect(url_for('perfil'))
        
    conn = obter_conexao()
    cursor = conn.cursor()
    usuario = cursor.execute('SELECT senha_hash FROM usuarios WHERE id = ?', (session['usuario_id'],)).fetchone()
    conn.close()
    
    if usuario and check_password_hash(usuario['senha_hash'], senha):
        session['perfil_autorizado'] = True
        flash('Identidade confirmada! Agora você pode alterar seu nome de usuário ou senha.', 'sucesso')
    else:
        flash('Senha incorreta. Confirmação negada.', 'erro')
        
    return redirect(url_for('perfil'))


@app.route('/perfil/atualizar_nome', methods=['POST'])
def atualizar_nome():
    if 'usuario_id' not in session:
        flash('Faça login para continuar.', 'erro')
        return redirect(url_for('login'))
        
    if not session.get('perfil_autorizado'):
        flash('Você precisa confirmar sua senha antes de alterar os dados.', 'erro')
        return redirect(url_for('perfil'))
    
    novo_nome = request.form.get('nome', '').strip()
    
    if not novo_nome:
        flash('O nome de usuário não pode estar vazio.', 'erro')
        return redirect(url_for('perfil'))
        
    conn = obter_conexao()
    cursor = conn.cursor()
    cursor.execute(
        'UPDATE usuarios SET nome = ? WHERE id = ?', 
        (novo_nome, session['usuario_id'])
    )
    conn.commit()
    conn.close()
    
    session['usuario_nome'] = novo_nome
    session.pop('perfil_autorizado', None)  # Revoga a autorização por segurança após guardar no BD
    
    flash('Nome de usuário atualizado com sucesso no banco de dados!', 'sucesso')
    return redirect(url_for('perfil'))


@app.route('/perfil/senha', methods=['POST'])
def alterar_senha():
    if 'usuario_id' not in session:
        flash('Faça login para continuar.', 'erro')
        return redirect(url_for('login'))
        
    if not session.get('perfil_autorizado'):
        flash('Você precisa confirmar sua senha antes de alterar a senha.', 'erro')
        return redirect(url_for('perfil'))
        
    nova_senha = request.form.get('nova_senha', '')
    
    if not nova_senha or len(nova_senha) < 8:
        flash('A nova senha deve ter pelo menos 8 caracteres.', 'erro')
        return redirect(url_for('perfil'))
        
    conn = obter_conexao()
    cursor = conn.cursor()
    novo_hash = generate_password_hash(nova_senha)
    cursor.execute('UPDATE usuarios SET senha_hash = ? WHERE id = ?', (novo_hash, session['usuario_id']))
    conn.commit()
    conn.close()
    
    session.pop('perfil_autorizado', None)  # Revoga a autorização por segurança após guardar no BD
    
    flash('Senha alterada com sucesso no banco de dados!', 'sucesso')
    return redirect(url_for('perfil'))


def _aquecer_gerador():
    try:
        from servicos.gerador_receita import obter_gerador
        obter_gerador()
        print("-> [TastIA] Gerador de receitas pronto para utilização.")
    except Exception as e:
        print(f"-> [TastIA] Aviso: não foi possível pré-carregar o gerador de receitas: {e}")


if __name__ == '__main__':
    obter_fila()
    threading.Thread(target=_aquecer_gerador, daemon=True).start()
    app.run(debug=True, use_reloader=False, host='0.0.0.0', port=5000)
