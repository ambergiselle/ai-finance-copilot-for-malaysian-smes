create extension if not exists vector;

create table businesses (
  id uuid primary key default gen_random_uuid(), -- unique business ID
  owner_id uuid references auth.users(id), -- the user who owns this business
  name text not null,
  industry text,
  created_at timestamptz default now()
);

create table customers (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references businesses(id) on delete cascade, -- the business this customer belongs to
  name text not null,
  email text
);

create table invoices (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references businesses(id) on delete cascade,
  customer_id uuid references customers(id),
  invoice_no text not null,
  issue_date date not null,
  due_date date not null,
  paid_date date,                       -- null means unpaid
  subtotal numeric(12,2) not null,
  tax numeric(12,2) default 0,
  total numeric(12,2) not null,
  status text check (status in ('issued','paid','overdue','cancelled'))
);

create table transactions (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references businesses(id) on delete cascade,
  txn_date date not null,
  type text check (type in ('income','expense')),
  category text,                        -- sales, rent, salaries, supplies...
  description text,
  amount numeric(12,2) not null,
  invoice_id uuid references invoices(id)
);

create table doc_chunks (
  id bigserial primary key,
  source text not null,                 -- guideline title
  version text,                         -- e.g. 4.9 (7 Sep 2026)
  page int,
  content text not null,
  embedding vector(1536)                -- must match your embedding model
);

create index on invoices (business_id, status);
create index on transactions (business_id, txn_date);
create index on doc_chunks using hnsw (embedding vector_cosine_ops);