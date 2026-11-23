# Arquitetura do TastIA

**Projeto Interdisciplinar em Engenharia da Computação 2 (UAB00073)**, UABJ/UFRPE
**Professora:** Camila Ascendina
**Equipe:** Everton Guilherme Marinho Silva, José Ednaldo dos Santos Filho, Luiz Eduardo Cordeiro Araujo e Reinaldo Sergio Dias da Silva

---

## 1. Resumo

O TastIA é uma aplicação web em **Python com Flask**. O usuário cadastra os ingredientes que tem em casa (por foto ou à mão) e o sistema gera receitas e sugere bebidas. Tudo roda em um único programa: não há vários servidores nem serviços separados.

## 2. Visão em blocos

```
┌──────────────────────────────────────────────┐
│  Navegador (HTML + CSS + JavaScript)         │
└───────────────────────┬──────────────────────┘
                        │ páginas e requisições JSON
┌───────────────────────▼──────────────────────┐
│  Flask: app.py (páginas) + rotas/ (API)      │
└──┬──────────────┬──────────────┬─────────────┘
   │              │              │
┌──▼───────┐ ┌────▼─────┐ ┌──────▼─────┐   ┌──────────────┐
│percepcao/│ │receitas/ │ │ bebidas/   │   │ banco_dados/ │
│ foto →   │ │ pedido → │ │ prato →    │   │   SQLite     │
│ itens    │ │ receita  │ │ 3 bebidas  │   │              │
└──────────┘ └──────────┘ └────────────┘   └──────────────┘
        (servicos/ dá apoio: fila, imagem, e-mail, modelos)
```

## 3. Os módulos

### 3.1 Percepção: da foto aos ingredientes

1. A foto é validada e reduzida (`servicos/imagem_servico.py`).
2. O **Florence-2** localiza os objetos na imagem.
3. Cada objeto é recortado e o **CLIP** diz qual alimento é, comparando o recorte com descrições de ingredientes.
4. Se nada aproveitável for encontrado, o sistema tenta de novo com a imagem inteira e com partes dela (o "plano B" da percepção).
5. O resultado vai para a tela. Itens com baixa confiança aparecem **desmarcados**, e o usuário confere tudo antes de salvar.

### 3.2 Receitas: do pedido à receita

O modelo de linguagem usado é pequeno e erra com facilidade, então o sistema não confia só nele. O processo tem camadas:

1. **Inventário.** Itens vencidos são ignorados. Os que vencem em até 3 dias têm prioridade.
2. **Esqueleto.** O código escolhe o prato e escreve título, tempo, porções e ingredientes com quantidades coerentes. O **SmolLM3** escreve só o modo de preparo.
3. **Limpeza e reparos.** O texto é limpo e corrigido (ingredientes esquecidos, quantidades absurdas, unidades erradas).
4. **Validação.** Confere o formato, se só usa ingredientes do inventário, se os alimentos combinam e se respeita as restrições pedidas. Se falhar, o sistema tenta de novo (até 2 tentativas por padrão).
5. **Plano B.** Se a receita continuar ruim, ela é trocada por uma de **30 receitas prontas**, montadas com o que o usuário tem.
6. **Aprovação.** O usuário pode aprovar a receita antes de ela entrar no histórico.

### 3.3 Bebidas: do prato às sugestões

- O catálogo tem **40 bebidas sem álcool**.
- O **MiniLM** transforma o texto do prato e as descrições das bebidas em números e compara as semelhanças.
- Regras gastronômicas (por exemplo, evitar algo muito doce com um prato doce) e os filtros do usuário (sem lactose, sem gás, etc.) escolhem as **3 melhores**, cada uma com justificativa.
- Se o MiniLM não estiver disponível, existe uma alternativa mais simples, baseada em palavras (motor "léxico").

### 3.4 Serviços de apoio (`servicos/`)

| Arquivo | O que faz |
|---|---|
| `fila.py` | Fila de tarefas em segundo plano, para detecção e geração demoradas |
| `imagem_servico.py` | Valida e reduz as fotos |
| `modelos_servico.py` | Baixa e prepara os modelos |
| `gerador_receita.py` | Carrega o SmolLM3 (quantização int8) para rodar em CPU |
| `email_servico.py` | Envia o código de recuperação de senha pela Brevo |
| `autenticacao_servico.py` | Apoio ao login e cadastro |

## 4. Modelos de IA

| Finalidade | Modelo |
|---|---|
| Detectar objetos | Florence-2-base |
| Classificar ingredientes | CLIP ViT-B/32 |
| Gerar receitas | SmolLM3-3B |
| Comparar textos de bebidas | paraphrase-multilingual-MiniLM-L12-v2 |

Os modelos são baixados na primeira execução para `modelos_huggingface/` e rodam **localmente, em CPU**. Detalhes das licenças em `LICENSES.md`.

## 5. Dados

Usa **SQLite**, em `banco_dados/tastia.db`, criado automaticamente. Guarda usuários, códigos de recuperação de senha, inventário, receitas e bebidas escolhidas. Cada usuário só acessa os próprios dados. Veja `BANCO_DE_DADOS.md`.

## 6. Como as tarefas demoradas funcionam

Detectar ingredientes e gerar receitas podem demorar. Por isso, a API aceita o modo assíncrono:

1. O navegador envia o pedido com `assincrono: true`.
2. O servidor responde na hora com um `tarefa_id` (código **202**).
3. A tarefa roda na fila, **uma por vez**.
4. O navegador pergunta de tempos em tempos à rota `status` até a tarefa terminar.

Cada usuário pode ter **uma receita sendo gerada por vez**. A fila fica **na memória**: se o servidor reiniciar, as tarefas em andamento e os resultados se perdem.

## 7. Pastas do projeto

| Pasta | Responsabilidade |
|---|---|
| `banco_dados/` | Conexão e criação das tabelas |
| `percepcao/` | Foto → ingredientes |
| `receitas/` | Geração, validação e histórico de receitas |
| `bebidas/` | Catálogo, regras e recomendador de bebidas |
| `rotas/` | API (ingredientes, receitas, bebidas), login e perfil |
| `servicos/` | Fila, imagens, e-mail e modelos |
| `templates/` | Páginas HTML |
| `static/` | CSS, JavaScript e imagens |
| `tests/` | Testes automatizados |
| `resultados_avaliacao/` | Relatórios das avaliações |

## 8. Tecnologias

- **Python e Flask:** backend e rotas
- **HTML, Jinja2, JavaScript e Tailwind CSS:** interface
- **SQLite:** dados
- **PyTorch, Transformers e Sentence-Transformers:** modelos de IA
- **Brevo:** e-mail de recuperação de senha
- **pytest:** testes

## 9. Limitações e cuidados

- A foto gera **sugestões**, que o usuário precisa conferir. A quantidade é uma contagem de objetos, não um peso.
- As receitas são geradas por IA e devem ser revisadas pelo usuário.
- As bebidas são sempre sem álcool.
- As tarefas em segundo plano se perdem ao reiniciar o servidor.
- As chaves estrangeiras do SQLite não são aplicadas automaticamente. A integridade (por exemplo, apagar as bebidas de uma receita excluída) é feita pelo código das rotas.
- Para colocar o sistema no ar é preciso: definir uma `SECRET_KEY` forte, proteger as chaves da Brevo, desativar o `debug` e resolver a licença dos pesos do CLIP.
