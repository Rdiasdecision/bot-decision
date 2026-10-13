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

- Python 3.10 ou superior
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
prioridade sobre os campos separados. `ALLOWED_VIEWS` deve conter exatamente o
conjunto liberado para o role, sempre no formato `schema.view`.

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
  -d '{"question":"Quantos registros existem?"}'
```

A resposta inclui `answer`, o `generated_sql` original, o `sql` validado e
efetivamente executado, as `columns` e as `rows`. Endpoints disponíveis:

- `POST /chat`: executa o pipeline completo;
- `GET /health`: verifica a conexao com o PostgreSQL;
- `GET /docs`: documentacao Swagger interativa;
- `GET /openapi.json`: contrato OpenAPI.

O comando acima publica apenas em `127.0.0.1`. Antes de expor a API em rede,
adicione autenticacao, TLS, rate limiting e controles de acesso adequados aos
dados consultados.

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
- Os resultados retornados (ate `MAX_ROWS`) sao enviados a Maritaca. Avalie
  requisitos de privacidade antes de expor dados sensiveis.
- SQL gerado por LLM nunca deve ser considerado confiavel. Preserve todas as
  camadas de seguranca e audite consultas em producao.

## Integracao Maritaca

O cliente usa a SDK OpenAI apontada para o endpoint compativel da Maritaca. Os
padroes atuais sao `https://chat.maritaca.ai/api` e `sabiazinho-4`, mas ambos
podem ser trocados por variaveis de ambiente.
