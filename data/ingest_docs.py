import os
import time

import numpy as np
import psycopg
from dotenv import load_dotenv
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pgvector.psycopg import register_vector
from pypdf import PdfReader

load_dotenv()
DOCS = [
    (
        "data/docs/einvoice_guideline.pdf",
        "e-Invoice Guideline",
        "4.8 (30 Aug 2026)",
    ),
    (
        "data/docs/einvoice_specific_guidelines.pdf",
        "e-Invoice Specific Guideline",
        "4.9 (7 Sep 2026)",
    ),
]
BATCH = 90
splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)
emb = GoogleGenerativeAIEmbeddings(
    model="models/" + os.environ.get("EMBEDDING_MODEL", "gemini-embedding-001")
)

# 1. Split both PDF into chunks
rows = []
for path, title, version in DOCS:
    count = 0
    for page_no, page in enumerate(PdfReader(path).pages, start=1):
        for chunk in splitter.split_text(page.extract_text() or ""):
            rows.append((title, version, page_no, chunk))
            count += 1
        print(f"{title}: {count} chunks")

# 2. Embed in batches
vectors = []
for i in range(0, len(rows), BATCH):
    if i:
        time.sleep(65)
    batch = [r[3] for r in rows[i : i + BATCH]]
    vectors += emb.embed_documents(batch, output_dimensionality=1536)
    print(f"Embedded {len(vectors)}/{len(rows)}")

# 3. Only touch database once every embedding succeed
with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
    register_vector(conn)
    conn.execute("truncate doc_chunks")
    with conn.cursor() as cur:
        cur.executemany(
            "insert into doc_chunks (source, version, page, content, embedding) "
            "values (%s, %s, %s, %s, %s)",
            [(*r, np.array(v)) for r, v in zip(rows, vectors)],
        )
print(f"Done: {len(rows)} chunks saved")
