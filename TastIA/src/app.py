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
        nome = request.form.get('nome')
        categoria = request.form.get('categoria')
        quantidade = request.form.get('quantidade')
        validade = request.form.get('validade') or None

        conn = obter_conexao()
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO inventario (usuario_id, nome, categoria, quantidade, validade) VALUES (?, ?, ?, ?, ?)',
            (session['usuario_id'], nome, categoria, quantidade, validade)
        )
        conn.commit()
        conn.close()
        flash('Ingrediente cadastrado com sucesso!', 'sucesso')
        return redirect(url_for('inventario'))

    return render_template('cadastrar_ingrediente.html')

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


@app.route('/perfil')
def perfil():
    if 'usuario_id' not in session:
        flash('Faça login para continuar.', 'erro')
        return redirect(url_for('login'))
    return render_template('perfil.html')


def _aquecer_gerador():
    try:
        from servicos.gerador_receita import obter_gerador
        obter_gerador()
        print("-> [TastIA] Gerador de receitas pronto para utilização.")
    except Exception as e:
        print(f"-> [TastIA] Aviso: não foi possível pré-carregar o gerador de receitas: {e}")


if __name__ == '__main__':
    threading.Thread(target=_aquecer_gerador, daemon=True).start()
    app.run(debug=True, use_reloader=False, host='0.0.0.0', port=5000)
