# Arquitetura TastIA

**Projeto Interdisciplinar em Engenharia da Computação 2 (UAB00073)**  
**Professora:** Camila Ascendina

**Integrantes:** Everton Guilherme Marinho Silva, José Ednaldo dos Santos Filho, Luiz Eduardo Cordeiro Araujo e Reinaldo Sergio Dias da Silva.

---

## 1. Resumo do projeto

O TastIA é uma aplicação web que ajuda o usuário a decidir o que cozinhar com o que já tem em casa e a reduzir o desperdício de alimentos. O usuário fotografa seus ingredientes; o sistema localiza e identifica cada alimento, e o usuário confirma ou corrige o resultado antes de salvar no inventário.

Depois, ao pedir algo em linguagem livre (por exemplo, "lanche leve em 15 minutos"), recebe uma receita executável que usa apenas os ingredientes do estoque, priorizando os que vencem primeiro, e sugestões de bebidas, alcoólicas ou não, que combinam com o prato.

O sistema tem quatro módulos: Sistema (aplicação web), Percepção Computacional (visão), API (integração REST/JSON) e IA (receitas e bebidas, com modelos distintos dos da percepção).

---

## 2. Estrutura de pastas

A estrutura de diretórios do projeto está organizada da seguinte forma:

```text
tastia/
├── app.py
├── config.py
├── requirements.txt
├── README
├── LICENSES
├── banco_dados/
├── modelos_huggingface/
├── percepcao/
├── receitas/
├── bebidas/
├── rotas/
├── servicos/
├── templates/
├── static/
│   ├── js/
│   └── css/
└── tests/
```

---

## 3. O que cada parte faz

| Pasta ou arquivo | Função |
|---|---|
| `tastia/` (raiz) | Pasta do projeto e do repositório Git. Reúne o ponto de entrada (`app.py`), a configuração central (`config.py`), as dependências, o README, o arquivo de licenças e a chave secreta dos tokens (gerada na primeira execução, fora do Git). É daqui que o usuário executa o sistema. |
| `banco_dados/` | Camada de persistência. Cria o esquema SQLite, concentra todas as funções de acesso ao banco (usuários, inventário, receitas e bebidas sugeridas) e guarda o arquivo `tastia.db`, criado automaticamente na primeira execução e fora do Git. É o único lugar que fala com o banco. |
| `modelos_huggingface/` | Pasta única com os pesos e tokenizadores dos quatro modelos, sem subdivisão. Preenchida automaticamente na primeira execução de `python app.py` e não vai para o Git. |
| `percepcao/` | Módulo de Percepção Computacional (visão): detecta os alimentos na foto, classifica cada recorte, normaliza os nomes, calcula a confiança e estima a quantidade. Transforma uma foto em lista de ingredientes. |
| `receitas/` | Módulo de IA 1: carrega o modelo de linguagem, monta o prompt com o inventário e o pedido e valida que a receita usa só os ingredientes do estoque. |
| `bebidas/` | Módulo de IA 2: mantém o catálogo de 40 bebidas, calcula a similaridade com a receita ou a ocasião e aplica regras gastronômicas para sugerir três bebidas com justificativa. |
| `rotas/` | Camada da API REST. Um arquivo por grupo de endpoints (autenticação, ingredientes, inventário, receita, bebida, histórico, saúde), mais as páginas HTML. Valida a entrada, chama serviços, banco ou módulos de IA e devolve JSON. |
| `servicos/` | Regras de negócio compartilhadas: autenticação (hash de senha e token), tratamento da imagem enviada, fila de tarefas em segundo plano e registro do estado dos modelos carregados. |
| `templates/` | Páginas HTML (Jinja2): inicial, login, cadastro, dashboard, inventário, cadastrar ingredientes, gerar receita, sugerir bebidas, histórico, além do modelo base. |
| `static/` | Arquivos que o navegador baixa diretamente. |
| `static/js/` | Scripts de cada tela, que chamam a API, e o `api.js`, que centraliza o envio do token e o tratamento de erro de autenticação. |
| `static/css/` | Estilos: Tailwind pré-compilado, para funcionar offline, e ajustes próprios. |
| `tests/` | Testes automatizados (pytest) do banco, da percepção, do validador, das regras, da autenticação, da fila e das rotas. Rodam sem baixar modelos e sem internet. |

---

## 4. Modelos usados

| Função | Modelo | Módulo | O que faz |
|---|---|---|---|
| Detecção de objetos na foto | `florence-community/Florence-2-base` | Percepção | Localiza onde estão os alimentos na foto. |
| Classificação dos ingredientes | `openai/clip-vit-base-patch32` | Percepção | Identifica qual é cada alimento encontrado, comparando-o com a lista de ingredientes definida no código. |
| Geração de receitas | `HuggingFaceTB/SmolLM3-3B` | IA 1 | Cria a receita a partir do pedido do usuário e dos ingredientes que ele tem em casa. |
| Recomendação de bebidas | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | IA 2 | Sugere bebidas que combinam com a receita ou com a ocasião. |
