create role agent_reader login password '<yourPassword>';
grant usage on schema public to agent_reader;
grant select on businesses, customers, invoices, transactions to agent_reader;
-- No access to doc_chunks, the auth schema, or any write permission.