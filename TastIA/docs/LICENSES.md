# Licenças dos modelos de IA do TastIA

**Projeto Interdisciplinar em Engenharia da Computação 2 (UAB00073)**
**Professora:** Camila Ascendina
**Equipe:** Everton Guilherme Marinho Silva, José Ednaldo dos Santos Filho, Luiz Eduardo Cordeiro Araujo e Reinaldo Sergio Dias da Silva
**Consulta às licenças:** novembro de 2026

---

## 1. Para que serve este documento

O TastIA usa **4 modelos de IA prontos**, baixados do Hugging Face Hub. O grupo **não treinou nem alterou** nenhum deles: eles são usados como estão, apenas para gerar resultados.

Este documento resume a licença de cada modelo e o que o grupo se compromete a fazer. Ele **não substitui** os textos oficiais das licenças, que devem ser consultados nos links indicados.

## 2. Resumo

| Modelo | Quem fez | Licença | Para que serve no TastIA |
|---|---|---|---|
| `florence-community/Florence-2-base` | Microsoft | MIT | Achar os alimentos na foto |
| `openai/clip-vit-base-patch32` | OpenAI | MIT (código); **pesos sem licença declarada** | Dizer qual alimento é cada recorte |
| `HuggingFaceTB/SmolLM3-3B` | Hugging Face | Apache 2.0 | Escrever as receitas |
| `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | UKP Lab / Sentence-Transformers | Apache 2.0 | Comparar textos para sugerir bebidas |

Os modelos são baixados na primeira execução para a pasta `modelos_huggingface/`, que **não deve ser enviada ao GitHub**.

---

## 3. Cada modelo

### 3.1 Florence-2-base (MIT)

- **Página:** https://huggingface.co/florence-community/Florence-2-base
- **Licença:** https://opensource.org/license/mit
- **Onde é usado:** `percepcao/deteccao.py`
- **O que faz:** encontra a região da foto onde cada alimento aparece. Cada região é recortada e enviada ao CLIP.
- **O que a licença permite:** uso comercial e acadêmico, modificação e distribuição.
- **O que exige:** manter o aviso de copyright e o texto da licença.
- **Garantia:** nenhuma. É fornecido "como está".

### 3.2 CLIP ViT-B/32 (MIT no código, pesos sem licença declarada)

- **Página:** https://huggingface.co/openai/clip-vit-base-patch32
- **Código:** https://github.com/openai/CLIP (licença MIT)
- **Onde é usado:** `percepcao/classificacao.py` e `percepcao/catalogo.py`
- **O que faz:** identifica cada alimento recortado, comparando a imagem com descrições de ingredientes em inglês. Ele só escolhe entre a lista de ingredientes definida no código.

**Este é o único modelo com restrição importante.**

- O **código** do CLIP é MIT.
- Os **pesos** publicados no Hugging Face **não trazem licença declarada** na página do modelo. Existe uma sugestão externa para marcá-los como MIT, mas ela não foi aceita oficialmente.
- O *model card* diz que o modelo é um resultado de pesquisa e que **usos em produção estão fora do escopo**. Ele também não recomenda usos fora de ambiente restrito sem testes e sem uma lista fixa de classes, e informa que o modelo foi pensado para o inglês.

**Por que o uso no TastIA é aceitável:**
- O TastIA é um **protótipo acadêmico**, sem venda e sem uso em produção.
- O CLIP trabalha com uma **lista fixa** de ingredientes e foi testado com fotos reais (veja `resultados_avaliacao/`).
- Os textos enviados ao CLIP estão em **inglês**. A interface em português usa tabelas do próprio sistema.
- Não há reconhecimento facial nem vigilância, e o usuário **sempre confere** os itens antes de salvar.

**O que o grupo se compromete a não fazer:**
- Não afirmar que os pesos do CLIP são liberados para uso comercial.
- Não colocar o TastIA em produção nem oferecê-lo ao público enquanto a licença dos pesos não for confirmada com a OpenAI ou o modelo não for trocado por outro com licença clara.

### 3.3 SmolLM3-3B (Apache 2.0)

- **Página:** https://huggingface.co/HuggingFaceTB/SmolLM3-3B
- **Licença:** https://www.apache.org/licenses/LICENSE-2.0
- **Onde é usado:** `receitas/gerador.py` e `receitas/prompt.py`
- **O que faz:** escreve o modo de preparo das receitas. O texto passa por validação antes de chegar ao usuário.
- **O que a licença permite:** uso comercial e acadêmico, modificação, distribuição e uso de patentes.
- **O que exige:** incluir a licença, manter os avisos de copyright e indicar alterações feitas nos arquivos.
- **Garantia:** nenhuma.
- **Cuidado:** como todo modelo de linguagem, ele pode errar. O usuário deve **revisar quantidades, tempos e temperaturas**. O sistema não substitui orientação nutricional ou de segurança alimentar.

### 3.4 paraphrase-multilingual-MiniLM-L12-v2 (Apache 2.0)

- **Página:** https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
- **Licença:** https://www.apache.org/licenses/LICENSE-2.0
- **Onde é usado:** `bebidas/recomendador.py`
- **O que faz:** transforma o texto do prato e as descrições das 40 bebidas do catálogo em números, para medir o quanto se parecem. Como é multilíngue, funciona com receitas em português.
- **Permissões e obrigações:** as mesmas do item 3.3.

---

## 4. MIT e Apache 2.0, lado a lado

| | MIT | Apache 2.0 |
|---|---|---|
| Uso comercial | Permitido | Permitido |
| Modificar e distribuir | Permitido | Permitido |
| Concessão de patentes | Não menciona | Sim |
| Manter aviso de copyright e licença | Obrigatório | Obrigatório |
| Indicar alterações | Não exigido | Obrigatório |

As duas licenças são compatíveis e podem ser usadas juntas no mesmo projeto.

## 5. O que o grupo se compromete a fazer

1. Manter este arquivo e os links das licenças no repositório.
2. Citar os modelos e seus autores no relatório final e na apresentação.
3. Não alterar nem redistribuir os pesos. Cada usuário os baixa direto do Hugging Face.
4. Não enviar a pasta `modelos_huggingface/` ao GitHub.
5. Registrar no relatório final as limitações do CLIP (item 3.2).
6. Manter o TastIA como protótipo acadêmico enquanto a licença dos pesos do CLIP não for confirmada.

## 6. Limitações

- As licenças valem para o **código e os pesos** dos modelos. Elas **não esclarecem a origem nem a licença dos dados de treinamento**.
- Os modelos podem errar e ter vieses. Por isso o usuário confere os ingredientes da foto e as receitas passam por validação.
- Os autores podem atualizar as licenças. Reconfira os links antes da entrega final.

## 7. Referências

- MICROSOFT; FLORENCE-2 COMMUNITY. *Florence-2-base*. https://huggingface.co/florence-community/Florence-2-base
- XIAO, B. et al. *Florence-2: Advancing a Unified Representation for a Variety of Vision Tasks*. CVPR, 2024.
- OPENAI. *CLIP*. https://github.com/openai/CLIP
- RADFORD, A. et al. *Learning Transferable Visual Models From Natural Language Supervision*. ICML, 2021.
- HUGGING FACE. *SmolLM3-3B*. https://huggingface.co/HuggingFaceTB/SmolLM3-3B
- SENTENCE-TRANSFORMERS. *paraphrase-multilingual-MiniLM-L12-v2*. https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
- REIMERS, N.; GUREVYCH, I. *Sentence-BERT: Sentence Embeddings using Siamese BERT-Networks*. EMNLP, 2019.
- OPEN SOURCE INITIATIVE. *The MIT License*. https://opensource.org/license/mit
- APACHE SOFTWARE FOUNDATION. *Apache License, Version 2.0*. https://www.apache.org/licenses/LICENSE-2.0
