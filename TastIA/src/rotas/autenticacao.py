import hmac
import secrets
from datetime import datetime, timedelta, timezone

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from werkzeug.security import generate_password_hash, check_password_hash

from banco_dados.database import obter_conexao
from servicos.autenticacao_servico import gerar_hash_codigo
from servicos.email_servico import enviar_codigo_recuperacao

bp_auth = Blueprint("auth", __name__)


@bp_auth.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
    if request.method == 'POST':
        nome = request.form.get('nome')
        email = request.form.get('email')
        senha = request.form.get('senha')

        if not nome or not email or not senha:
            flash('Por favor, preencha todos os campos.', 'erro')
            return redirect(url_for('auth.cadastro'))

        conn = obter_conexao()
        cursor = conn.cursor()

        usuario_existente = cursor.execute(
            'SELECT id FROM usuarios WHERE email = ?',
            (email,)
        ).fetchone()

        if usuario_existente:
            flash('Este e-mail já está registado.', 'erro')
            conn.close()
            return redirect(url_for('auth.cadastro'))

        senha_hash = generate_password_hash(senha)

        cursor.execute(
            'INSERT INTO usuarios (nome, email, senha_hash) VALUES (?, ?, ?)',
            (nome, email, senha_hash)
        )

        conn.commit()
        conn.close()

        flash('Conta criada com sucesso! Faça login para continuar.', 'sucesso')
        return redirect(url_for('auth.login'))

    return render_template('cadastro.html')


@bp_auth.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        senha = request.form.get('senha')

        if not email or not senha:
            flash('Por favor, preencha o e-mail e a senha.', 'erro')
            return redirect(url_for('auth.login'))

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
        return redirect(url_for('auth.login'))

    return render_template('login.html')


@bp_auth.route('/esqueci_senha', methods=['GET', 'POST'])
def recuperar_senha():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()

        if not email:
            flash('Por favor, informe o seu e-mail.', 'erro')
            return redirect(url_for('auth.recuperar_senha'))

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

                current_app.logger.error(
                    'Falha ao enviar código de recuperação: %s',
                    erro
                )

        conn.close()

        flash(
            'Se o e-mail estiver cadastrado, você receberá um código de recuperação. Verifique também a caixa de spam.',
            'sucesso'
        )

        return redirect(url_for('auth.redefinir_senha'))

    return render_template('esqueci_senha.html')


@bp_auth.route('/redefinir_senha', methods=['GET', 'POST'])
def redefinir_senha():
    email = session.get('email_recuperacao')

    if not email:
        flash('Solicite primeiro um código de recuperação.', 'erro')
        return redirect(url_for('auth.recuperar_senha'))

    if request.method == 'POST':
        codigo = request.form.get('codigo', '').strip()
        nova_senha = request.form.get('nova_senha', '')
        confirmar_senha = request.form.get('confirmar_senha', '')

        if not codigo or not nova_senha or not confirmar_senha:
            flash('Preencha todos os campos.', 'erro')
            return redirect(url_for('auth.redefinir_senha'))

        if not codigo.isdigit() or len(codigo) != 6:
            flash('Informe o código de seis dígitos enviado ao seu e-mail.', 'erro')
            return redirect(url_for('auth.redefinir_senha'))

        if len(nova_senha) < 8:
            flash('A nova senha deve ter pelo menos 8 caracteres.', 'erro')
            return redirect(url_for('auth.redefinir_senha'))

        if nova_senha != confirmar_senha:
            flash('As senhas informadas não são iguais.', 'erro')
            return redirect(url_for('auth.redefinir_senha'))

        conn = obter_conexao()

        usuario = conn.execute(
            'SELECT id FROM usuarios WHERE email = ?',
            (email,)
        ).fetchone()

        if not usuario:
            conn.close()
            session.pop('email_recuperacao', None)
            flash('Não foi possível validar a recuperação. Solicite um novo código.', 'erro')
            return redirect(url_for('auth.recuperar_senha'))

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
            return redirect(url_for('auth.recuperar_senha'))

        if registro['tentativas'] >= 5:
            conn.execute(
                'UPDATE codigos_recuperacao SET usado = 1 WHERE id = ?',
                (registro['id'],)
            )
            conn.commit()
            conn.close()

            flash('Limite de tentativas atingido. Solicite um novo código.', 'erro')
            return redirect(url_for('auth.recuperar_senha'))

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
            return redirect(url_for('auth.recuperar_senha'))

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
            return redirect(url_for('auth.redefinir_senha'))

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
        return redirect(url_for('auth.login'))

    return render_template('redefinir_senha.html', email=email)


@bp_auth.route('/logout')
def logout():
    session.clear()
    flash('Sessão encerrada com sucesso.', 'sucesso')
    return redirect(url_for('index'))
