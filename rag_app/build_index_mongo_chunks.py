# build_index_mongo_chunks.py (PATCHED)

import os
import pickle
import re
import faiss
import numpy as np
from pymongo import MongoClient
from sentence_transformers import SentenceTransformer
from utils import make_doc
import csv


def load_jif_csv(path="journal_impact_factors.csv"):
    """
    CSV format:
    Journal,ImpactFactor
    Nature,64.8
    """
    lookup = {}
    if not os.path.exists(path):
        print("WARNING: JIF file not found, JIF will be 0")
        return lookup

    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            lookup[row["Journal"].strip().lower()] = float(row["ImpactFactor"])
    return lookup

JIF_LOOKUP = load_jif_csv()

PROTEIN_HINTS = re.compile(
    r"\b(receptor|gpcr|kinase|enzyme|cytokine|chemokine|interleukin|tnf|nf-?kb|"
    r"gpr\d+|fpr\d+|cxcr\d+|il-\d+|tgf-?b|stat\d+|mapk|erk|akt|pi3k|cox|ptgs|alox|"
    r"tlr\d+|cd\d+)\b",
    re.IGNORECASE
)

INTERACTION_HINTS = re.compile(
    r"\b(bind|binding|activate|activated|inhibit|inhibited|regulate|regulated|"
    r"agonist|antagonist|phosphorylat|signal|pathway|upregulat|downregulat)\b",
    re.IGNORECASE
)

OUT_DIR = "outputs"

MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "spm_rag"
PAPERS_COL = "newpapers"
MENTIONS_COL = "newmentions"

INDEX_DIR = "index_store"
EMBED_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

MIN_CHUNK_LEN = 200

def clean(x):
    x = "" if x is None else str(x)
    return re.sub(r"\s+", " ", x).strip()

def choose_rag_text(paper: dict) -> str:
    status = clean(paper.get("full_text_status", ""))
    full_text = clean(paper.get("full_text", ""))
    abstract = clean(paper.get("abstract", ""))
    title = clean(paper.get("title", ""))

    if status == "OK" and full_text:
        return full_text
    if abstract:
        return abstract
    return title


def chunk_by_paragraph(text: str, min_chars=MIN_CHUNK_LEN, max_chars=1800):
    text = clean(text)
    if not text:
        return []

    paras = [p.strip() for p in re.split(r"\n\s*\n+", text) if p.strip()]
    chunks = []
    buf = ""

    for p in paras:
        if not buf:
            buf = p
            continue

        if len(buf) + 2 + len(p) <= max_chars:
            buf = buf + "\n\n" + p
        else:
            chunks.append(buf)
            buf = p

    if buf:
        chunks.append(buf)

    return [c for c in chunks if len(c) >= min_chars]


def is_useful_chunk(chunk: str) -> bool:
    c = chunk.lower()
    if len(c) < MIN_CHUNK_LEN:
        return False
    if "references" in c[:200] or "bibliography" in c[:200]:
        return False
    return bool(PROTEIN_HINTS.search(c) or INTERACTION_HINTS.search(c))

def main():
    os.makedirs(INDEX_DIR, exist_ok=True)

    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    papers = db[PAPERS_COL]
    mentions = db[MENTIONS_COL]

    texts = []
    metas = []

    for p in papers.find({}):
        pmid = clean(p.get("pmid"))
        if not pmid:
            continue

        ms = list(mentions.find({"pmid": pmid}))
        spm_names = sorted({clean(m.get("spm_name")) for m in ms if clean(m.get("spm_name"))})

        rag_text = choose_rag_text(p)
        chunks = chunk_by_paragraph(rag_text)

        journal = clean(p.get("journal"))
        jif = JIF_LOOKUP.get(journal.lower(), 0.0)

        for ci, chunk in enumerate(chunks):
            if not is_useful_chunk(chunk):
                continue

            text, meta = make_doc(
                spm=", ".join(spm_names),
                synonym="",
                pmid=pmid,
                title=clean(p.get("title")),
                journal=journal,
                year=clean(p.get("year")),
                abstract=clean(p.get("abstract")),
                full_paper=chunk
            )

            meta["JIF"] = jif
            meta["chunk_index"] = ci
            meta["chunk_size"] = len(chunk)

            texts.append(text)
            metas.append(meta)

    model = SentenceTransformer(EMBED_MODEL_NAME)
    emb = model.encode(texts, convert_to_numpy=True, normalize_embeddings=True).astype(np.float32)

    dim = emb.shape[1]
    index = faiss.IndexIVFFlat(faiss.IndexFlatIP(dim), dim, 4096, faiss.METRIC_INNER_PRODUCT)
    index.train(emb)
    index.add(emb)
    index.nprobe = 10

    faiss.write_index(index, os.path.join(INDEX_DIR, "faiss.index"))
    pickle.dump(metas, open(os.path.join(INDEX_DIR, "metas.pkl"), "wb"))
    pickle.dump(texts, open(os.path.join(INDEX_DIR, "texts.pkl"), "wb"))

    print("Done: paragraph chunks + JIF indexed")

if __name__ == "__main__":
    main()
