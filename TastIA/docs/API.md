# API do TastIA

Resumo das rotas **como estão implementadas**. Para o desenho geral, veja `ARQUITETURA.md`.

## Regras gerais

- **Login:** a autenticação usa sessão (cookie). Todas as rotas `/api/...` exigem login. Sem login, a resposta é **401** com `{"erro": "Faça login para continuar."}`.
- **Formato:** as requisições enviam JSON (`Content-Type: application/json`). Só o envio de foto usa `multipart/form-data`.
- **Erros:** sempre no formato `{"erro": "mensagem"}`. Alguns trazem também `detalhes` ou `codigo`.
- **Dados privados:** cada usuário só vê e altera os próprios dados. Acessar o registro de outra pessoa devolve **404**.
- **Tarefas demoradas:** com `"assincrono": true` a resposta é **202** com `{"tarefa_id", "status": "pendente"}`. Depois, consulte a rota `status`. Estados possíveis: `pendente`, `processando`, `concluido` e `erro`.

---

## 1. Páginas (HTML)

As páginas protegidas levam para `/login` quando não há sessão.

| Método | Rota | O que faz | Exige login |
|---|---|---|---|
| GET | `/` | Página inicial | Não |
| GET, POST | `/cadastro` | Criar conta | Não |
| GET, POST | `/login` | Entrar | Não |
| GET, POST | `/esqueci_senha` | Pede o código de recuperação por e-mail | Não |
| GET, POST | `/redefinir_senha` | Informa o código e define a nova senha | Não |
| GET | `/logout` | Sai da conta | Sim |
| GET | `/dashboard` | Painel inicial | Sim |
| GET | `/inventario` | Lista os ingredientes | Sim |
| GET, POST | `/cadastrar_ingrediente` | Foto, seleção dos itens e cadastro manual | Sim |
| POST | `/editar_ingrediente/<id>` | Edita um item (formulário) | Sim |
| POST | `/excluir_ingrediente/<id>` | Exclui um item (formulário) | Sim |
| GET | `/receitas` | Tela de gerar receita | Sim |
| GET | `/bebidas` | Tela de sugerir bebida | Sim |
| GET | `/historico` | Histórico de receitas e bebidas | Sim |
| GET | `/perfil` | Dados do usuário | Sim |
| POST | `/perfil/confirmar` | Confirma a senha atual para liberar a edição | Sim |
| POST | `/perfil/atualizar_nome` | Altera o nome | Sim |
| POST | `/perfil/senha` | Altera a senha (mínimo de 8 caracteres) | Sim |

---

## 2. Ingredientes: `/api/ingredientes`

| Método | Rota | O que faz |
|---|---|---|
| GET | `/sugestoes?q=texto` | Autocomplete de nomes (até 8). **Não exige login** |
| POST | `/reduzir` | Valida e reduz a foto, devolvendo só os dados da imagem |
| POST | `/detectar` | Detecta os ingredientes de uma foto |
| GET | `/status/<tarefa_id>` | Estado de uma detecção assíncrona |
| POST | `/confirmar` ou `/salvar_lote` | Salva os itens marcados após a foto (os dois nomes são o mesmo endpoint) |
| POST | `/adicionar` | Cadastro manual de um ingrediente |
| GET | `/` ou `/listar` | Lista os ingredientes do usuário |
| PUT ou PATCH | `/<id>` | Edita um ingrediente |
| DELETE | `/<id>` | Exclui um ingrediente |

### Detectar ingredientes: `POST /api/ingredientes/detectar`

Envie a foto no campo `imagem`. O campo `assincrono=true` é opcional.
Formatos aceitos: `png`, `jpg`, `jpeg`, `webp`, `bmp`, com até **10 MB**.

Resposta de sucesso (**200**, ou **202** no modo assíncrono):

```json
{
  "ingredientes": [
    { "nome": "Tomate", "categoria": "Legumes", "quantidade": "3 unidades",
      "confianca": 0.82, "selecionado": true, "revisar": false }
  ],
  "total_detectado": 3,
  "usou_plano_b": false,
  "tempo_s": 12.4,
  "aviso": null
}
```

- `revisar: true` indica confiança baixa. Nesse caso `selecionado` vem `false`, para o usuário conferir.
- `aviso` traz uma mensagem quando nada foi encontrado ou quando há itens para revisar.
- Erros: **400** (sem imagem, imagem vazia ou inválida) e **500** (falha nos modelos).

### Salvar itens após a foto: `POST /api/ingredientes/confirmar`

```json
{ "itens": [
  { "nome": "Tomate", "categoria": "Legumes", "quantidade": "3",
    "unidade": "unidade", "validade": "2026-11-30", "marcado": true }
] }
```

Regras:
- Itens com `marcado: false` são ignorados.
- A **validade é obrigatória**, no formato `AAAA-MM-DD`.
- Se o ingrediente já existe, a quantidade é **somada** e vale a **validade mais próxima**. Não duplica.

Respostas: **200** com `{"salvos", "inseridos", "atualizados", "ignorados"}` ou **400** (lista vazia, validade ausente ou inválida).

### Cadastro manual: `POST /api/ingredientes/adicionar`

Campos: `nome` (obrigatório, até 100 caracteres), `quantidade` (obrigatória), `unidade`, `categoria` (padrão "Outros") e `validade` (opcional). Se já existir, soma a quantidade.

### Editar e excluir

- `PUT` ou `PATCH /api/ingredientes/<id>`: corrige nome, quantidade, unidade, validade ou categoria. Erros: **400** (dado inválido), **404** (item não encontrado) e **409** (já existe outro ingrediente com esse nome).
- `DELETE /api/ingredientes/<id>`: **200** ou **404**.

---

## 3. Receitas: `/api/receita`

| Método | Rota | O que faz |
|---|---|---|
| GET | `/inventario` | Itens usáveis do usuário e lista dos vencidos |
| POST | `/gerar` | Gera uma receita |
| POST | `/aprovar` | Salva no histórico uma receita gerada com `"salvar": false` |
| GET | `/status/<tarefa_id>` | Estado de uma geração assíncrona |
| GET | `/historico` | Receitas e bebidas salvas |
| DELETE | `/historico/<id>` | Exclui a receita e as bebidas ligadas a ela |

### Gerar receita: `POST /api/receita/gerar`

| Campo | Observação |
|---|---|
| `pedido` | **Obrigatório**, até 500 caracteres |
| `ingredientes` | Opcional. Se vazio, usa todo o inventário. Separe os nomes por vírgula |
| `tempo` | Opcional: `15`, `30`, `45`, `60` ou `qualquer` |
| `dificuldade` | Opcional: `facil`, `media`, `dificil` ou `qualquer` |
| `restricoes` | Opcional, até 300 caracteres |
| `evitar` | Opcional, até 120 caracteres |
| `salvar` | `false` = só entra no histórico depois de `/aprovar`. Omitido ou `true` = salva sozinha se a receita for válida |
| `assincrono` | `true` = responde 202 e roda na fila |

Resposta **200** (principais campos):

```json
{
  "receita": "texto limpo da receita",
  "detalhes": { "titulo": "...", "tempo": "...", "porcoes": "...", "ingredientes": [], "passos": [] },
  "receita_id": 12,
  "salva": true,
  "aguardando_aprovacao": false,
  "valida": true,
  "estrutura_ok": true,
  "fora_do_inventario": [],
  "tentativas": 1,
  "tempo_total_s": 41.2,
  "vencidos_ignorados": [],
  "urgentes_usados": ["Leite"],
  "urgentes_nao_usados": [],
  "avisos_qualidade": [],
  "itens_faltando": [],
  "sugestao_para_aprovar": false
}
```

- `sugestao_para_aprovar: true` aparece quando o plano B precisou usar itens que o usuário não tem. A receita vem como **sugestão**, nunca é salva sozinha, e `itens_faltando` mostra o que falta.

Erros:
- **400**: pedido vazio ou longo demais, inventário vazio (com `"codigo": "inventario_vazio"`) ou todos os itens vencidos.
- **429**: no modo assíncrono, o usuário já tem uma receita sendo gerada.
- **503**: modelo de receitas indisponível.
- **500**: falha na geração.

### Aprovar: `POST /api/receita/aprovar`

Corpo: `{pedido, receita, ingredientes}`. Aprovar duas vezes a mesma receita devolve o mesmo `receita_id`, sem duplicar. Uma receita com itens fora do inventário **pode** ser aprovada, pois o usuário já viu o aviso.
Respostas: **200**, **400** (receita vazia ou grande demais), **422** (formato inesperado) e **500**.

### Histórico

`GET /api/receita/historico` devolve `{"total", "total_bebidas", "receitas": [...], "bebidas": [...]}`, da mais nova para a mais antiga. Cada receita traz as suas bebidas, e o campo `bebidas` da raiz traz só as bebidas salvas **sem** receita.

---

## 4. Bebidas: `/api/bebida`

| Método | Rota | O que faz |
|---|---|---|
| POST | `/sugerir` | Sugere 3 bebidas sem álcool |
| POST | `/escolher` | Salva a bebida escolhida |
| DELETE | `/historico/<id>` | Exclui uma bebida do histórico |

### Sugerir: `POST /api/bebida/sugerir`

| Campo | Observação |
|---|---|
| `refeicao` | Prato ou refeição. Obrigatório se não houver `ingredientes` |
| `ingredientes` | Texto com ingredientes. Obrigatório se não houver `refeicao` |
| `preferencias` | Texto livre, como "sem lactose", "sem cafeína", "sem gás", "dia de calor" |
| `temperatura` | "Gelada", "Quente", "Natural" ou "Qualquer" |
| `tipo` | `suco`, `vitamina`, `cha`, `cremosa` ou `qualquer` |

Resposta **200** (resumida):

```json
{
  "bebidas": [
    { "id": "suco_maracuja", "nome": "Suco de Maracujá", "tipo": "suco",
      "temperatura": "gelada", "descricao": "...", "pontuacao": 2.31,
      "justificativa": "Suco de Maracujá combina porque ...", "alerta": null }
  ],
  "filtros": ["Sem lactose"],
  "aviso": null,
  "motor": "minilm"
}
```

- `motor` é `minilm` ou `lexico`, conforme o método de comparação usado.
- `aviso` aparece quando há menos de 3 bebidas que atendem aos filtros.
- Erros: **400** (sem refeição nem ingredientes, ou nenhuma bebida atende aos filtros) e **500**.

### Escolher: `POST /api/bebida/escolher`

Corpo: `nome_bebida` (obrigatório), `justificativa`, `refeicao` (até 300 caracteres) e `receita_id` (opcional).

- Com `receita_id` válido e do próprio usuário, a bebida fica **ligada à receita** (`"vinculada": true`).
- Se a receita não existir ou for de outro usuário, a bebida é salva **sozinha**.
- A mesma bebida na mesma receita não duplica.

Respostas: **200** com `{"bebida_id", "receita_id", "vinculada", "mensagem"}` ou **400**.

### Excluir: `DELETE /api/bebida/historico/<id>`

**200** `{"ok": true, "id"}` ou **404** (bebida não encontrada, ou de outro usuário).
