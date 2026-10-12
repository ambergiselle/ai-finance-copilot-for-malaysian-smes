alter table businesses enable row level security;
alter table customers enable row level security;
alter table invoices enable row level security;
alter table transactions enable row level security;
alter table doc_chunks enable row level security;

create policy agent_business on businesses for select to agent_reader
    using (id = current_setting('app.business_id', true)::uuid);
create policy agent_customers on customers for select to agent_reader
    using (business_id = current_setting('app.business_id', true)::uuid);
create policy agent_invoices on invoices for select to agent_reader
    using (business_id = current_setting('app.business_id', true)::uuid);
create policy agent_transactions on transactions for select to agent_reader
    using (business_id = current_setting('app.business_id', true)::uuid);

