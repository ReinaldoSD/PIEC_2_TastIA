from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from werkzeug.security import generate_password_hash, check_password_hash

from banco_dados.database import obter_conexao

bp_perfil = Blueprint("perfil", __name__)


@bp_perfil.route('/perfil')
def perfil():
    if 'usuario_id' not in session:
        flash('Faça login para continuar.', 'erro')
        return redirect(url_for('auth.login'))

    conn = obter_conexao()

    usuario = conn.execute(
        'SELECT nome FROM usuarios WHERE id = ?',
        (session['usuario_id'],)
    ).fetchone()

    conn.close()

    return render_template('perfil.html', usuario=usuario)


@bp_perfil.route('/perfil/confirmar', methods=['POST'])
def confirmar_identidade():
    if 'usuario_id' not in session:
        flash('Faça login para continuar.', 'erro')
        return redirect(url_for('auth.login'))

    senha = request.form.get('senha_confirmacao', '')

    if not senha:
        flash('Por favor, informe a sua senha atual para confirmar.', 'erro')
        return redirect(url_for('perfil.perfil'))

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

    return redirect(url_for('perfil.perfil'))


@bp_perfil.route('/perfil/atualizar_nome', methods=['POST'])
def atualizar_nome():
    if 'usuario_id' not in session:
        flash('Faça login para continuar.', 'erro')
        return redirect(url_for('auth.login'))

    if not session.get('perfil_autorizado'):
        flash('Você precisa confirmar sua senha antes de alterar os dados.', 'erro')
        return redirect(url_for('perfil.perfil'))

    novo_nome = request.form.get('nome', '').strip()

    if not novo_nome:
        flash('O nome de usuário não pode estar vazio.', 'erro')
        return redirect(url_for('perfil.perfil'))

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
    return redirect(url_for('perfil.perfil'))


@bp_perfil.route('/perfil/senha', methods=['POST'])
def alterar_senha():
    if 'usuario_id' not in session:
        flash('Faça login para continuar.', 'erro')
        return redirect(url_for('auth.login'))

    if not session.get('perfil_autorizado'):
        flash('Você precisa confirmar sua senha antes de alterar a senha.', 'erro')
        return redirect(url_for('perfil.perfil'))

    nova_senha = request.form.get('nova_senha', '')

    if not nova_senha or len(nova_senha) < 8:
        flash('A nova senha deve ter pelo menos 8 caracteres.', 'erro')
        return redirect(url_for('perfil.perfil'))

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
    return redirect(url_for('perfil.perfil'))
