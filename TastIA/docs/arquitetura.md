# Arquitetura do TastIA

**Projeto:** Projeto Interdisciplinar em Engenharia da Computação 2 (UAB00073)  
**Instituição:** UABJ/UFRPE  
**Professora:** Camila Ascendina  
**Integrantes:** Everton Guilherme Marinho Silva, José Ednaldo dos Santos Filho, Luiz Eduardo Cordeiro Araujo e Reinaldo Sergio Dias da Silva.

---

## 1. Visão geral

O TastIA é uma aplicação web que utiliza inteligência artificial para ajudar o usuário a aproveitar os alimentos que já possui em casa. O sistema permite cadastrar ingredientes manualmente ou por fotografias, organizar um inventário com quantidades e datas de validade, gerar receitas personalizadas e recomendar bebidas que combinem com as refeições.

A identificação dos ingredientes por imagem é apresentada ao usuário para conferência antes de ser adicionada ao inventário. Na geração de receitas, o sistema considera os ingredientes disponíveis e prioriza aqueles que estão próximos do vencimento.

## 2. Organização do sistema

O TastIA utiliza uma arquitetura modular desenvolvida em Python com Flask. Seus módulos fazem parte da mesma aplicação e trabalham em conjunto.

As principais partes são:

- **Interface web:** permite acessar as funcionalidades do sistema por meio de páginas HTML, estilos CSS e JavaScript.
- **Backend e API:** recebe as solicitações da interface, aplica as regras do sistema e coordena os módulos.
- **Percepção computacional:** analisa fotografias para localizar e classificar possíveis ingredientes.
- **Geração de receitas:** utiliza as informações do inventário e o pedido do usuário para produzir receitas, que passam por validação.
- **Recomendação de bebidas:** compara as características da refeição com um catálogo e apresenta opções compatíveis.
- **Banco de dados:** armazena usuários, ingredientes, receitas, bebidas escolhidas e informações de recuperação de senha.

## 3. Funcionamento dos principais módulos

### 3.1. Identificação de ingredientes

Quando o usuário envia uma fotografia, o sistema valida e prepara a imagem para análise. Em seguida, utiliza o Florence-2 para localizar objetos e o CLIP para classificar os recortes identificados. Caso a primeira análise não produza resultados aproveitáveis, o sistema também pode analisar a imagem completa e partes dela.

Os ingredientes identificados são apresentados ao usuário, que pode revisar as sugestões antes de confirmar o cadastro no inventário.

### 3.2. Geração de receitas

O sistema consulta o inventário do usuário e considera as quantidades e datas de validade dos ingredientes. Os itens vencidos são desconsiderados, enquanto os que estão próximos do vencimento recebem prioridade.

Essas informações, junto com o pedido do usuário, são utilizadas para montar a solicitação enviada ao modelo de linguagem. A receita gerada passa por verificações de estrutura e compatibilidade com os ingredientes disponíveis. Quando necessário, o sistema pode solicitar uma nova geração com orientações de correção.

### 3.3. Recomendação de bebidas

O módulo de bebidas utiliza um catálogo com 40 opções não alcoólicas. A recomendação considera características da refeição, similaridade entre descrições e regras de harmonização.

O sistema utiliza o MiniLM para comparar os textos. Quando esse modelo não está disponível e a configuração permite, pode utilizar uma alternativa baseada em TF-IDF. Ao final, apresenta até três sugestões com suas justificativas.

## 4. Modelos de inteligência artificial

| Finalidade | Modelo | Função |
|---|---|---|
| Detecção de objetos | Florence-2-base | Localiza possíveis ingredientes na fotografia. |
| Classificação de imagens | CLIP ViT-Base-Patch32 | Compara os recortes da imagem com descrições de ingredientes. |
| Geração de receitas | SmolLM3-3B | Gera receitas a partir do pedido e do inventário. |
| Similaridade de bebidas | paraphrase-multilingual-MiniLM-L12-v2 | Compara semanticamente a refeição com as descrições das bebidas. |

Os modelos são obtidos do Hugging Face e utilizados localmente pela aplicação após sua preparação. A execução depende dos recursos disponíveis no computador e das bibliotecas necessárias.

## 5. Armazenamento de dados

O projeto utiliza SQLite para armazenar as informações da aplicação. O banco contempla dados relacionados a:

- usuários e autenticação;
- códigos de recuperação de senha;
- ingredientes do inventário;
- receitas geradas e salvas;
- bebidas escolhidas pelos usuários.

As informações de cada usuário são associadas à sua conta, permitindo consultar e administrar seu próprio inventário e histórico.

## 6. Organização geral do projeto

O código está dividido em pastas que agrupam responsabilidades semelhantes:

| Diretório | Responsabilidade |
|---|---|
| `banco_dados/` | Criação do banco e operações de persistência. |
| `percepcao/` | Identificação e classificação de ingredientes por imagem. |
| `receitas/` | Geração, preparação e validação de receitas. |
| `bebidas/` | Catálogo e recomendação de bebidas. |
| `rotas/` | Endpoints da API utilizados pela aplicação. |
| `servicos/` | Serviços compartilhados, processamento de imagens, modelos e tarefas em segundo plano. |
| `templates/` | Páginas da interface web. |
| `static/` | Estilos, scripts e imagens utilizados pela interface. |
| `tests/` | Testes automatizados do projeto. |

## 7. Tecnologias utilizadas

- **Python e Flask:** desenvolvimento do backend e das rotas da aplicação.
- **HTML, CSS, JavaScript e Jinja2:** construção da interface web.
- **SQLite:** armazenamento dos dados.
- **PyTorch e Transformers:** execução dos modelos de inteligência artificial.
- **Hugging Face:** disponibilização dos modelos utilizados pelo projeto.
- **Brevo:** envio de e-mails utilizados no processo de recuperação de senha.

## 8. Considerações e limitações

A identificação por fotografia é uma sugestão automática e deve ser conferida pelo usuário. A quantidade estimada pelo processo de percepção corresponde à contagem de objetos identificados, não a uma medição precisa de peso ou volume.

Atualmente, as recomendações disponibilizadas pela aplicação são de bebidas não alcoólicas. Além disso, as tarefas executadas em segundo plano são mantidas em memória; por isso, tarefas em andamento e seus resultados podem ser perdidos quando a aplicação é reiniciada.

Para disponibilizar o sistema em produção, é necessário configurar uma chave secreta segura, proteger as credenciais de serviços externos e desativar o modo de depuração.
