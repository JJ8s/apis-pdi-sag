alter table public.declaraciones enable row level security;

drop policy if exists "permitir_insert_declaraciones" on public.declaraciones;
drop policy if exists "permitir_select_declaraciones" on public.declaraciones;
drop policy if exists "permitir_update_declaraciones" on public.declaraciones;

create policy "permitir_insert_declaraciones"
on public.declaraciones
for insert
to anon
with check (true);

create policy "permitir_select_declaraciones"
on public.declaraciones
for select
to anon
using (true);

create policy "permitir_update_declaraciones"
on public.declaraciones
for update
to anon
using (true)
with check (true);
