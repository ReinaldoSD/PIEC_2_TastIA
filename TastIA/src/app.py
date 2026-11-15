import threading

from flask import Flask, render_template, jsonify, request, redirect, url_for, flash, session

from config import Config
from banco_dados.create_db import criar_tabelas
from servicos.modelos_servico import baixar_ou_carregar_modelos
from banco_dados.database import obter_conexao
from rotas.receita import bp_receita
from rotas.bebida import bp_bebida
from rotas.ingrediente import bp_ingrediente
from rotas.autenticacao import bp_auth
from rotas.perfil import bp_perfil
from servicos.fila import obter_fila


app = Flask(__name__)
app.config.from_object(Config)

app.register_blueprint(bp_receita)
app.register_blueprint(bp_bebida)
app.register_blueprint(bp_ingrediente)
app.register_blueprint(bp_auth)
app.register_blueprint(bp_perfil)

with app.app_context():
    criar_tabelas()
    baixar_ou_carregar_modelos()


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


@app.route('/dashboard')
def dashboard():
    if 'usuario_id' not in session:
        flash('Faça login para aceder à dashboard.', 'erro')
        return redirect(url_for('auth.login'))

    return render_template(
        'dashboard.html',
        nome_usuario=session.get('usuario_nome')
    )


@app.route('/inventario')
def inventario():
    if 'usuario_id' not in session:
        flash('Faça login para aceder ao inventário.', 'erro')
        return redirect(url_for('auth.login'))

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
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        from rotas.ingrediente import (
            _buscar_duplicado,
            _formatar_qtd_unidade,
            _somar_quantidades,
            _validade_mais_proxima,
        )
        nome = (request.form.get('nome') or '').strip()
        categoria = (request.form.get('categoria') or 'Outros').strip()
        quantidade = (request.form.get('quantidade') or '').strip()
        unidade = (request.form.get('unidade') or '').strip()
        validade = (request.form.get('validade') or '').strip() or None

        if not nome or not quantidade:
            flash('Informe o nome e a quantidade do ingrediente.', 'erro')
            return redirect(url_for('cadastrar_ingrediente'))

        qtd_final, unid_final = _formatar_qtd_unidade(quantidade, unidade)
        usuario_id = session['usuario_id']

        conn = obter_conexao()
        cursor = conn.cursor()
        duplicado = _buscar_duplicado(conn, usuario_id, nome)

        if duplicado:
            nova_qtd, nova_unid = _somar_quantidades(
                duplicado['quantidade'], duplicado.get('unidade') or '', qtd_final, unid_final
            )
            menor_val = _validade_mais_proxima(duplicado['validade'], validade)
            cursor.execute(
                '''UPDATE inventario
                   SET categoria = ?, quantidade = ?, unidade = ?, validade = ?, atualizado_em = CURRENT_TIMESTAMP
                   WHERE id = ? AND usuario_id = ?''',
                (categoria, nova_qtd, nova_unid, menor_val, duplicado['id'], usuario_id)
            )
            flash('Ingrediente já existia: quantidade somada e validade mais próxima mantida!', 'sucesso')
        else:
            cursor.execute(
                'INSERT INTO inventario (usuario_id, nome, categoria, quantidade, unidade, validade) VALUES (?, ?, ?, ?, ?, ?)',
                (usuario_id, nome, categoria, qtd_final, unid_final, validade)
            )
            flash('Ingrediente cadastrado com sucesso!', 'sucesso')

        conn.commit()
        conn.close()
        return redirect(url_for('inventario'))

    return render_template('cadastrar_ingrediente.html')


@app.route('/editar_ingrediente/<int:item_id>', methods=['POST'])
def editar_ingrediente(item_id):
    if 'usuario_id' not in session:
        flash('Faça login para continuar.', 'erro')
        return redirect(url_for('auth.login'))

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
        return redirect(url_for('auth.login'))

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
        return redirect(url_for('auth.login'))

    return render_template('receitas.html')


@app.route('/bebidas')
def bebidas():
    if 'usuario_id' not in session:
        flash('Faça login para continuar.', 'erro')
        return redirect(url_for('auth.login'))

    return render_template('bebidas.html')


@app.route('/historico')
def historico():
    if 'usuario_id' not in session:
        flash('Faça login para continuar.', 'erro')
        return redirect(url_for('auth.login'))

    return render_template('historico.html')


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
