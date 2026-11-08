import threading
import os
import secrets
import hashlib
import hmac
import json
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone

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


def gerar_hash_codigo(codigo):
    valor = f"{codigo}:{app.config['SECRET_KEY']}"
    return hashlib.sha256(valor.encode('utf-8')).hexdigest()


def enviar_codigo_recuperacao(destinatario, codigo):
    chave_api = os.environ.get('BREVO_API_KEY')
    remetente = os.environ.get('BREVO_SENDER_EMAIL')
    nome_remetente = os.environ.get('BREVO_SENDER_NAME', 'TastIA')

    if not chave_api or not remetente:
        raise RuntimeError(
            'Configuração da API Brevo não encontrada no arquivo .env.'
        )

    assunto = 'Código de recuperação de senha - TastIA'

    texto = f'''Olá!

Recebemos uma solicitação para recuperar a senha da sua conta no TastIA.

Seu código de recuperação é:

{codigo}

Esse código é válido por 10 minutos e pode ser utilizado apenas uma vez.

Se você não solicitou a recuperação de senha, ignore este e-mail.

Equipe TastIA
'''

    html = f'''
    <html>
        <body>
            <h2>Recuperação de senha - TastIA</h2>
            <p>Olá!</p>
            <p>Recebemos uma solicitação para recuperar a senha da sua conta no TastIA.</p>
            <p>Seu código de recuperação é:</p>
            <h1>{codigo}</h1>
            <p>Esse código é válido por 10 minutos e pode ser utilizado apenas uma vez.</p>
            <p>Se você não solicitou a recuperação de senha, ignore este e-mail.</p>
            <p>Equipe TastIA</p>
        </body>
    </html>
    '''

    dados = {
        'sender': {
            'name': nome_remetente,
            'email': remetente
        },
        'to': [
            {
                'email': destinatario
            }
        ],
        'subject': assunto,
        'textContent': texto,
        'htmlContent': html
    }

    requisicao = urllib.request.Request(
        'https://api.brevo.com/v3/smtp/email',
        data=json.dumps(dados).encode('utf-8'),
        headers={
            'accept': 'application/json',
            'api-key': chave_api,
            'content-type': 'application/json'
        },
        method='POST'
    )

    try:
        with urllib.request.urlopen(requisicao, timeout=20) as resposta:
            if resposta.status not in (200, 201, 202):
                raise RuntimeError(
                    f'A Brevo retornou o status {resposta.status}.'
                )

    except urllib.error.HTTPError as erro:
        raise RuntimeError(
            f'A Brevo recusou o envio do e-mail. Código HTTP: {erro.code}.'
        ) from None

    except urllib.error.URLError:
        raise RuntimeError(
            'Não foi possível conectar à API da Brevo.'
        ) from None


@app.errorhandler(400)
def erro_requisicao_invalida(e):
    return jsonify({
        "erro": "Requisição inválida",
        "detalhes": str(e)
    }), 400


@app.errorhandler(404)
def erro_nao_encontrado(e):
    return jsonify({
        "erro": "Recurso ou rota não encontrada",
        "detalhes": str(e)
    }), 404


@app.errorhandler(500)
def erro_interno_servidor(e):
    return jsonify({
        "erro": "Erro interno no servidor",
        "detalhes": str(e)
    }), 500


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

        usuario_existente = cursor.execute(
            'SELECT id FROM usuarios WHERE email = ?',
            (email,)
        ).fetchone()

        if usuario_existente:
            flash('Este e-mail já está registado.', 'erro')
            conn.close()
            return redirect(url_for('cadastro'))

        senha_hash = generate_password_hash(senha)

        cursor.execute(
            'INSERT INTO usuarios (nome, email, senha_hash) VALUES (?, ?, ?)',
            (nome, email, senha_hash)
        )

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

        usuario = cursor.execute(
            'SELECT * FROM usuarios WHERE email = ?',
            (email,)
        ).fetchone()

        conn.close()

        if usuario and check_password_hash(usuario['senha_hash'], senha):
            session['usuario_id'] = usuario['id']
            session['usuario_nome'] = usuario['nome']
            session['usuario_email'] = usuario['email']

            flash('Login efetuado com sucesso!', 'sucesso')
            return redirect(url_for('dashboard'))

        flash('E-mail ou senha incorretos.', 'erro')
        return redirect(url_for('login'))

    return render_template('login.html')


@app.route('/esqueci_senha', methods=['GET', 'POST'])
def recuperar_senha():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()

        if not email:
            flash('Por favor, informe o seu e-mail.', 'erro')
            return redirect(url_for('recuperar_senha'))

        session.pop('email_recuperacao', None)
        session['email_recuperacao'] = email

        conn = obter_conexao()

        usuario = conn.execute(
            'SELECT id, email FROM usuarios WHERE email = ?',
            (email,)
        ).fetchone()

        if usuario:
            codigo = f"{secrets.randbelow(1000000):06d}"
            codigo_hash = gerar_hash_codigo(codigo)

            expira_em = (
                datetime.now(timezone.utc) + timedelta(minutes=10)
            ).isoformat()

            conn.execute(
                '''
                UPDATE codigos_recuperacao
                SET usado = 1
                WHERE usuario_id = ? AND usado = 0
                ''',
                (usuario['id'],)
            )

            conn.execute(
                '''
                INSERT INTO codigos_recuperacao
                (usuario_id, codigo_hash, expira_em)
                VALUES (?, ?, ?)
                ''',
                (usuario['id'], codigo_hash, expira_em)
            )

            conn.commit()

            try:
                enviar_codigo_recuperacao(usuario['email'], codigo)
            except Exception as erro:
                conn.execute(
                    '''
                    UPDATE codigos_recuperacao
                    SET usado = 1
                    WHERE usuario_id = ? AND codigo_hash = ?
                    ''',
                    (usuario['id'], codigo_hash)
                )
                conn.commit()

                app.logger.error(
                    'Falha ao enviar código de recuperação: %s',
                    erro
                )

        conn.close()

        flash(
            'Se o e-mail estiver cadastrado, você receberá um código de recuperação. Verifique também a caixa de spam.',
            'sucesso'
        )

        return redirect(url_for('redefinir_senha'))

    return render_template('esqueci_senha.html')


@app.route('/redefinir_senha', methods=['GET', 'POST'])
def redefinir_senha():
    email = session.get('email_recuperacao')

    if not email:
        flash('Solicite primeiro um código de recuperação.', 'erro')
        return redirect(url_for('recuperar_senha'))

    if request.method == 'POST':
        codigo = request.form.get('codigo', '').strip()
        nova_senha = request.form.get('nova_senha', '')
        confirmar_senha = request.form.get('confirmar_senha', '')

        if not codigo or not nova_senha or not confirmar_senha:
            flash('Preencha todos os campos.', 'erro')
            return redirect(url_for('redefinir_senha'))

        if not codigo.isdigit() or len(codigo) != 6:
            flash('Informe o código de seis dígitos enviado ao seu e-mail.', 'erro')
            return redirect(url_for('redefinir_senha'))

        if len(nova_senha) < 8:
            flash('A nova senha deve ter pelo menos 8 caracteres.', 'erro')
            return redirect(url_for('redefinir_senha'))

        if nova_senha != confirmar_senha:
            flash('As senhas informadas não são iguais.', 'erro')
            return redirect(url_for('redefinir_senha'))

        conn = obter_conexao()

        usuario = conn.execute(
            'SELECT id FROM usuarios WHERE email = ?',
            (email,)
        ).fetchone()

        if not usuario:
            conn.close()
            session.pop('email_recuperacao', None)
            flash('Não foi possível validar a recuperação. Solicite um novo código.', 'erro')
            return redirect(url_for('recuperar_senha'))

        registro = conn.execute(
            '''
            SELECT id, codigo_hash, expira_em, tentativas
            FROM codigos_recuperacao
            WHERE usuario_id = ? AND usado = 0
            ORDER BY id DESC
            LIMIT 1
            ''',
            (usuario['id'],)
        ).fetchone()

        if not registro:
            conn.close()
            flash('Código inválido ou expirado. Solicite um novo código.', 'erro')
            return redirect(url_for('recuperar_senha'))

        if registro['tentativas'] >= 5:
            conn.execute(
                'UPDATE codigos_recuperacao SET usado = 1 WHERE id = ?',
                (registro['id'],)
            )
            conn.commit()
            conn.close()

            flash('Limite de tentativas atingido. Solicite um novo código.', 'erro')
            return redirect(url_for('recuperar_senha'))

        try:
            data_expiracao = datetime.fromisoformat(registro['expira_em'])
            expirado = datetime.now(timezone.utc) > data_expiracao
        except (TypeError, ValueError):
            expirado = True

        if expirado:
            conn.execute(
                'UPDATE codigos_recuperacao SET usado = 1 WHERE id = ?',
                (registro['id'],)
            )
            conn.commit()
            conn.close()

            flash('O código expirou. Solicite um novo código.', 'erro')
            return redirect(url_for('recuperar_senha'))

        hash_informado = gerar_hash_codigo(codigo)

        if not hmac.compare_digest(hash_informado, registro['codigo_hash']):
            conn.execute(
                '''
                UPDATE codigos_recuperacao
                SET tentativas = tentativas + 1
                WHERE id = ?
                ''',
                (registro['id'],)
            )
            conn.commit()
            conn.close()

            flash('Código incorreto. Confira o e-mail e tente novamente.', 'erro')
            return redirect(url_for('redefinir_senha'))

        novo_hash = generate_password_hash(nova_senha)

        conn.execute(
            'UPDATE usuarios SET senha_hash = ? WHERE id = ?',
            (novo_hash, usuario['id'])
        )

        conn.execute(
            '''
            UPDATE codigos_recuperacao
            SET usado = 1
            WHERE usuario_id = ?
            ''',
            (usuario['id'],)
        )

        conn.commit()
        conn.close()

        session.pop('email_recuperacao', None)

        flash('Senha alterada com sucesso! Faça login com sua nova senha.', 'sucesso')
        return redirect(url_for('login'))

    return render_template('redefinir_senha.html', email=email)


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

    return render_template(
        'dashboard.html',
        nome_usuario=session.get('usuario_nome')
    )


@app.route('/inventario')
def inventario():
    if 'usuario_id' not in session:
        flash('Faça login para aceder ao inventário.', 'erro')
        return redirect(url_for('login'))

    conn = obter_conexao()

    itens = conn.execute(
        '''
        SELECT * FROM inventario
        WHERE usuario_id = ?
        ORDER BY nome COLLATE NOCASE
        ''',
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
            '''
            INSERT INTO inventario
            (usuario_id, nome, categoria, quantidade, validade)
            VALUES (?, ?, ?, ?, ?)
            ''',
            (
                session['usuario_id'],
                nome,
                categoria,
                quantidade,
                validade
            )
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
        '''
        DELETE FROM inventario
        WHERE id = ? AND usuario_id = ?
        ''',
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

    conn = obter_conexao()

    usuario = conn.execute(
        'SELECT nome FROM usuarios WHERE id = ?',
        (session['usuario_id'],)
    ).fetchone()

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

    usuario = conn.execute(
        'SELECT senha_hash FROM usuarios WHERE id = ?',
        (session['usuario_id'],)
    ).fetchone()

    conn.close()

    if usuario and check_password_hash(usuario['senha_hash'], senha):
        session['perfil_autorizado'] = True
        flash(
            'Identidade confirmada! Agora você pode alterar seu nome de usuário ou senha.',
            'sucesso'
        )
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

    conn.execute(
        'UPDATE usuarios SET nome = ? WHERE id = ?',
        (novo_nome, session['usuario_id'])
    )

    conn.commit()
    conn.close()

    session['usuario_nome'] = novo_nome
    session.pop('perfil_autorizado', None)

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

    novo_hash = generate_password_hash(nova_senha)

    conn.execute(
        'UPDATE usuarios SET senha_hash = ? WHERE id = ?',
        (novo_hash, session['usuario_id'])
    )

    conn.commit()
    conn.close()

    session.pop('perfil_autorizado', None)

    flash('Senha alterada com sucesso no banco de dados!', 'sucesso')
    return redirect(url_for('perfil'))


def _aquecer_gerador():
    try:
        from servicos.gerador_receita import obter_gerador
        obter_gerador()
        print("-> [TastIA] Gerador de receitas pronto para utilização.")
    except Exception as e:
        print(
            "-> [TastIA] Aviso: não foi possível pré-carregar "
            f"o gerador de receitas: {e}"
        )


if __name__ == '__main__':
    obter_fila()
    threading.Thread(target=_aquecer_gerador, daemon=True).start()
    app.run(
        debug=True,
        use_reloader=False,
        host='0.0.0.0',
        port=5000
    )