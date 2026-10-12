from flask import Flask, render_template, jsonify
from config import Config
from banco_dados.create_db import criar_tabelas
from servicos.modelos_servico import baixar_ou_carregar_modelos

app = Flask(__name__)
app.config.from_object(Config)

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

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)