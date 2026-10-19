import os

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
splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)
emb = GoogleGenerativeAIEmbeddings(
    model="models/" + os.environ.get("EMBEDDING_MODEL", "gemini-embedding-001")
)

with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
    register_vector(conn)
    conn.execute("truncate doc_chunks")
    for path, title, version in DOCS:
        rows = []
        for page_no, page in enumerate(PdfReader(path).pages, start=1):
            for chunk in splitter.split_text(page.extract_text() or ""):
                rows.append((title, version, page_no, chunk))
        vectors = emb.embed_documents([r[3] for r in rows], output_dimensionality=1536)
        with conn.cursor() as cur:
            cur.executemany(
                "insert into doc_chunks (source, version, page, content, embedding) "
                "values (%s, %s, %s, %s, %s)",
                [(*r, np.array(v)) for r, v in zip(rows, vectors)],
            )
        print(f"{title}: {len(rows)} chunks")
