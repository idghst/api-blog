create schema if not exists blog;

grant usage on schema blog to anon, authenticated, service_role;

alter default privileges in schema blog
  grant all on tables to service_role;

alter default privileges in schema blog
  grant all on sequences to service_role;

alter default privileges in schema blog
  grant execute on routines to service_role;
