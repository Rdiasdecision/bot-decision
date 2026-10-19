# Chatbot SQL com Sabiazinho e PostgreSQL

Prototipo de terminal que converte perguntas em portugues para SQL, valida a
consulta, executa somente `SELECT` em views PostgreSQL autorizadas e usa o
Sabiazinho para transformar o resultado em uma resposta natural.

## Fluxo

```text
pergunta -> Sabiazinho -> SQL -> validador AST -> PostgreSQL read-only
                                                    |
resposta <- Sabiazinho <- resultado JSON <----------+
```

A seguranca usa varias camadas: allowlist de views no aplicativo, parser AST com
`sqlglot`, `LIMIT`, timeout, transacao `READ ONLY` e um usuario PostgreSQL que
recebe `SELECT` apenas nas views explicitamente escolhidas. O role do banco e a
barreira de seguranca principal; nao use uma conta administrativa na aplicacao.

## Requisitos

- Python 3.11 ou superior recomendado (Python 3.10 chegou ao fim do suporte)
- PostgreSQL acessivel pela aplicacao
- Chave da API Maritaca
- Views de consulta ja criadas no banco

## Instalacao

```bash
cd chatbot-sql
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Execute o script conectado ao banco correto como administrador. Ele solicita a
senha sem exibi-la e aceita a lista de views por parametro:

```bash
psql -U postgres -d seu_banco \
  --set=db_user=chatbot_reader \
  --set=allowed_views=public.vw_vendas,public.vw_clientes \
  -f sql/create_readonly_role.sql
```

Depois configure `.env` com `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`,
`DB_PASSWORD` e `DB_SSLMODE`. Como alternativa, defina `DATABASE_URL`; ela tem
prioridade sobre os campos separados. `ALLOWED_VIEWS` e a barreira global e deve
conter exatamente o conjunto liberado para o role, sempre em `schema.view`.

Associe cada tela a um subconjunto dessa allowlist usando JSON:

```env
ALLOWED_VIEWS=public.vw_vendas,public.vw_clientes
SCREEN_VIEWS={"vendas":["public.vw_vendas"],"clientes":["public.vw_clientes"]}
```

Uma consulta feita com `screen=vendas` nao consegue acessar a view da tela
`clientes`, pois recebe schema e validador proprios.

## Executar

Na raiz `chatbot-sql`:

```bash
python -m app.main
```

Use `/schema` para recarregar os metadados das views e `sair` para encerrar. Com
`SHOW_SQL=true`, o SQL validado aparece antes da resposta.

## API HTTP

Inicie a API localmente:

```bash
uvicorn app.api:app --host 127.0.0.1 --port 8000
```

Envie uma pergunta:

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"usuario-123","screen":"vendas","session_id":"conversa-1","question":"Quantos registros existem?"}'
```

A resposta inclui `user_id`, `screen`, `session_id`, `answer`, o `generated_sql`
original, o `sql` validado e efetivamente executado, as `columns`, as `rows` e a
quantidade de mensagens na janela. Reutilize as mesmas tags nas perguntas
seguintes. Se `session_id` for omitido, a API cria um UUID e o devolve.

Por padrao, as ultimas 8 mensagens ficam em memoria. Configure com
`CONVERSATION_WINDOW_MESSAGES`; `MAX_CONVERSATION_SESSIONS` limita quantas
sessoes sao mantidas por processo. Esse historico e temporario e desaparece ao
reiniciar a API.

Endpoints disponíveis:

- `POST /chat`: executa o pipeline completo;
- `DELETE /users/{user_id}/screens/{screen}/sessions/{session_id}`: limpa uma conversa;
- `GET /health`: verifica a conexao com o PostgreSQL;
- `GET /docs`: documentacao Swagger interativa;
- `GET /openapi.json`: contrato OpenAPI.

O comando acima publica apenas em `127.0.0.1`. Antes de expor a API em rede,
adicione autenticacao, TLS, rate limiting e controles de acesso adequados aos
dados consultados. `user_id` e `screen` sao tags fornecidas pelo cliente e nao
provam identidade nem autorizacao; em producao, derive ambas de uma sessao ou
token autenticado, em vez de confiar diretamente no corpo da requisicao.

## Azure Functions

O arquivo `function_app.py` adapta a mesma FastAPI ao modelo Python v2 do Azure
Functions. Nao existe uma segunda implementacao dos endpoints: Azure e Uvicorn
usam o mesmo objeto `app.api:app`.

Arquivos do empacotamento:

- `function_app.py`: entrada descoberta pelo runtime Python v2;
- `host.json`: runtime v4, sem prefixo adicional para preservar as mesmas rotas;
- `local.settings.json.example`: modelo para execucao com Core Tools;
- `.funcignore`: impede o envio de segredos, testes e ambientes virtuais.

Para testar como FastAPI offline:

```bash
uvicorn app.api:app --host 127.0.0.1 --port 8000
```

Nesse modo, use `http://127.0.0.1:8000/chat` e `/docs`.

Para testar com o runtime do Azure Functions, instale o Azure Functions Core
Tools, copie o modelo local e preencha as credenciais somente no arquivo local:

```bash
cp local.settings.json.example local.settings.json
func start
```

O valor `UseDevelopmentStorage=true` pressupoe que o Azurite esteja em
execucao. Como alternativa, informe uma conexao valida em `AzureWebJobsStorage`.

Nesse modo, as rotas permanecem iguais às usadas pelo Uvicorn:

```text
http://localhost:7071/chat
http://localhost:7071/health
http://localhost:7071/docs
```

Para publicar em uma Function App Python ja criada:

```bash
func azure functionapp publish NOME_DA_FUNCTION_APP --python
```

Cadastre todas as variaveis de `local.settings.json.example` como Application
Settings da Function App. Nao publique `.env` nem `local.settings.json`. No
Azure, `AuthLevel.FUNCTION` exige uma Function Key (`?code=...` ou header
`x-functions-key`) para chamar os endpoints.

Observacao: a memoria de conversa continua em RAM. Em Azure Functions, um cold
start ou escalonamento para outra instancia perde/separa esse historico. Para
memoria consistente em producao, substitua-a por Redis ou PostgreSQL.

## Testes

Os testes unitarios nao precisam de banco nem de chave da Maritaca:

```bash
pytest -q
```

## Avaliacoes no seu banco

Edite `evals/questions.jsonl`, uma pergunta por linha. Cada caso pode ter um ou
mais dos campos:

- `expected_sql`: SQL esperado, comparado depois de normalizacao pelo `sqlglot`;
- `expected_result`: lista JSON exata esperada do banco;
- `expected_answer_contains`: trecho que deve aparecer na resposta final.

Execute:

```bash
python -m evals.run_evals
```

O arquivo fornecido e apenas um modelo e precisa ser adaptado aos nomes e dados
reais das suas views.

## Estrutura

```text
chatbot-sql/
├── .env.example
├── requirements.txt
├── README.md
├── sql/create_readonly_role.sql
├── app/
│   ├── config.py
│   ├── llm/{client.py,prompts.py}
│   ├── db/{connection.py,schema.py,executor.py}
│   ├── agent/{sql_generator.py,sql_validator.py,answer_generator.py,pipeline.py}
│   └── main.py
├── evals/{questions.jsonl,run_evals.py}
└── tests/{test_sql_validator.py,test_pipeline.py}
```

## Limites conhecidos do prototipo

- O contexto de schema e mantido em memoria; use `/schema` apos alterar views.
- A janela de conversa e local a cada processo e nao persiste reinicializacoes.
- Os resultados retornados (ate `MAX_ROWS`) sao enviados a Maritaca. Avalie
  requisitos de privacidade antes de expor dados sensiveis.
- SQL gerado por LLM nunca deve ser considerado confiavel. Preserve todas as
  camadas de seguranca e audite consultas em producao.

## Integracao Maritaca

O cliente usa a SDK OpenAI apontada para o endpoint compativel da Maritaca. Os
padroes atuais sao `https://chat.maritaca.ai/api` e `sabiazinho-4`, mas ambos
podem ser trocados por variaveis de ambiente.
