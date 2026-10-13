-- Execute conectado ao banco correto como administrador.
-- Cria/atualiza o usuario e concede SELECT somente nas views listadas.
-- Nao use GRANT SELECT ON ALL TABLES: isso liberaria tabelas base tambem.

\set ON_ERROR_STOP on

\if :{?db_user}
\else
  \set db_user chatbot_reader
\endif

\if :{?allowed_views}
\else
  \set allowed_views 'public.vw_vendas,public.vw_clientes'
\endif

SELECT format(
    'CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION',
    :'db_user'
)
WHERE NOT EXISTS (
    SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = :'db_user'
)
\gexec

-- Tambem atualiza configuracoes e senha caso o role ja exista.
-- O proprio psql solicita e confirma a senha sem exibi-la.
\password :db_user

SELECT format('ALTER ROLE %I SET default_transaction_read_only = on', :'db_user')
\gexec
SELECT format('ALTER ROLE %I SET statement_timeout = %L', :'db_user', '10s')
\gexec

SELECT format('GRANT CONNECT ON DATABASE %I TO %I', current_database(), :'db_user')
\gexec

-- Interrompe antes dos GRANTs se algum item nao estiver em schema.view.
SELECT bool_and(
    trim(view_name) ~ '^[A-Za-z_][A-Za-z0-9_$]*\.[A-Za-z_][A-Za-z0-9_$]*$'
) AS views_validas
FROM unnest(string_to_array(:'allowed_views', ',')) AS item(view_name)
\gset

\if :views_validas
\else
  \echo 'ERRO: allowed_views deve usar schema.view separado por virgulas'
  \quit 3
\endif

SELECT DISTINCT format(
    'GRANT USAGE ON SCHEMA %I TO %I',
    split_part(trim(view_name), '.', 1),
    :'db_user'
)
FROM unnest(string_to_array(:'allowed_views', ',')) AS item(view_name)
\gexec

SELECT format(
    'GRANT SELECT ON TABLE %I.%I TO %I',
    split_part(trim(view_name), '.', 1),
    split_part(trim(view_name), '.', 2),
    :'db_user'
)
FROM unnest(string_to_array(:'allowed_views', ',')) AS item(view_name)
\gexec

\echo 'Role criado/atualizado:' :db_user
\echo 'Views liberadas:' :allowed_views
