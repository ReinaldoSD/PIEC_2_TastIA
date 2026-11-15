import json
import os
import urllib.request
import urllib.error

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
