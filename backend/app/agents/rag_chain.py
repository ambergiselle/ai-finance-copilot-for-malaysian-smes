import time
import re

import numpy as np
import psycopg
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from pgvector.psycopg import register_vector

from ..config import settings
from ..llm import make_llm

RAG_PROMPT = """You answer questions about Malaysia's e-invoicing rules for small business owners.
Use ONLY the numbered context passages. After each claim, cite the passage like [1].
If the context does not cover the question, say it is not covered in the LHDN guidelines.
Keep answers short and plain. End with: General guidance only, not tax advice."""

llm = make_llm()
emb = GoogleGenerativeAIEmbeddings(model="models/" + settings.embedding_model)


def retrieve(question: str, k: int = 5) -> list[dict]:
    qvec = np.array(emb.embed_query(question, output_dimensionality=1536))
    with psycopg.connect(settings.database_url) as conn:
        register_vector(conn)
        rows = conn.execute(
            "select source, version, page, content, 1 - (embedding <=> %s) as score "
            "from doc_chunks order by embedding <=> %s limit %s",
            (qvec, qvec, k),
        ).fetchall()
    return [
        {
            "source": r[0],
            "version": r[1],
            "page": r[2],
            "content": r[3],
            "score": float(r[4]),
        }
        for r in rows
    ]


def ask_docs(question: str) -> dict:
    start = time.time()
    chunks = retrieve(question)
    context = "\n\n".join(
        f"[{i}] {c['source']} v{c['version']}, page {c['page']}:\n{c['content']}"
        for i, c in enumerate(chunks, start=1)
    )
    answer = llm.invoke(
        [
            ("system", RAG_PROMPT),
            ("human", f"Context:\n{context}\n\nQuestion: {question}"),
        ]
    ).text
    # Normalise gpt-oss citation styles like 【2†L1-L4】 or [2†L1-L4] to [2]
    answer = re.sub(r"[【\[](\d+)†[^】\]]*[】\]]", r"[\1]", answer)
    answer = answer.replace("【", "[").replace("】", "]").replace(" .", ".")
    citations = [
        {"n": i, "source": c["source"], "version": c["version"], "page": c["page"]}
        for i, c in enumerate(chunks, start=1)
    ]
    return {
        "answer": answer,
        "citations": citations,
        "chunks": chunks,
        "latency_s": round(time.time() - start, 2),
    }
