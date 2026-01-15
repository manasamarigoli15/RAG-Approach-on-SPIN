import os
import pickle
import re
import faiss
import numpy as np
from pymongo import MongoClient
from sentence_transformers import SentenceTransformer
from utils import make_doc

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

def is_useful_chunk(chunk: str) -> bool:
    c = chunk.lower()
    if len(c) < MIN_CHUNK_LEN:
        return False
    if "references" in c[:200] or "bibliography" in c[:200]:
        return False
    return bool(PROTEIN_HINTS.search(c) or INTERACTION_HINTS.search(c))

OUT_DIR = "outputs"

#CONFIG for MongoDB
MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "spm_rag"
PAPERS_COL = "papers"
MENTIONS_COL = "mentions"

INDEX_DIR = "index_store"
EMBED_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

# Chunking settings
CHUNK_SIZE = 1200      # characters
CHUNK_OVERLAP = 200    # characters
MIN_CHUNK_LEN = 200    # skip tiny chunks

def clean(x):
    x = "" if x is None else str(x)
    return re.sub(r"\s+", " ", x).strip()

def choose_rag_text(paper: dict) -> str:
    """
    Use full text only when it is truly available, otherwise fallback to abstract.
    """
    status = clean(paper.get("full_text_status", ""))
    full_text = clean(paper.get("full_text", ""))
    abstract = clean(paper.get("abstract", ""))
    title = clean(paper.get("title", ""))

    if status == "OK" and full_text:
        return full_text
    if abstract:
        return abstract
    return title

def chunk_text(text: str, size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    text = clean(text)
    if not text:
        return []
    chunks = []
    i = 0
    step = max(1, size - overlap)
    while i < len(text):
        chunk = text[i:i + size]
        if len(chunk) >= MIN_CHUNK_LEN:
            chunks.append(chunk)
        i += step
    return chunks

def main():
    os.makedirs(INDEX_DIR, exist_ok=True)

    print("Connecting to MongoDB...")
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    papers = db[PAPERS_COL]
    mentions = db[MENTIONS_COL]

    print("Reading papers from MongoDB...")
    cursor = papers.find({}, {
        "pmid": 1, "title": 1, "journal": 1, "year": 1,
        "abstract": 1, "full_text": 1, "full_text_status": 1,
        "pmcid": 1, "doi": 1, "doi_url": 1, "pubmed_url": 1, "pmc_url": 1,
        "full_text_source": 1, "full_text_url": 1
    })

    texts = []
    metas = []

    doc_count = 0
    chunk_count = 0

    for p in cursor:
        pmid = clean(p.get("pmid"))
        if not pmid:
            continue

        # All SPM names/synonyms for this PMID
        ms = list(mentions.find({"pmid": pmid}, {"spm_name": 1, "synonym_matched": 1, "spm_class": 1}))
        spm_names = sorted({clean(m.get("spm_name")) for m in ms if clean(m.get("spm_name"))})
        syns = sorted({clean(m.get("synonym_matched")) for m in ms if clean(m.get("synonym_matched"))})
        spm_classes = sorted({clean(m.get("spm_class")) for m in ms if clean(m.get("spm_class"))})
        spm_class = ", ".join([c for c in spm_classes if c])

        rag_text = choose_rag_text(p)
        chunks = chunk_text(rag_text)

        if not chunks:
            continue

        for ci, chunk in enumerate(chunks):

            if not is_useful_chunk(chunk):
                continue
      
            # Put the chunk into "full_paper" field so it becomes the main searchable body
            text, meta = make_doc(
                spm=", ".join(spm_names),
                synonym=", ".join(syns),
                pmid=pmid,
                title=clean(p.get("title")),
                journal=clean(p.get("journal")),
                year=clean(p.get("year")),
                abstract=clean(p.get("abstract")),
                full_paper=chunk
            )

            # Add chunk metadata
            meta["SPM Class"] = spm_class
            meta["PMCID"] = clean(p.get("pmcid"))
            meta["PMC URL"] = clean(p.get("pmc_url"))
            meta["DOI"] = clean(p.get("doi"))
            meta["DOI URL"] = clean(p.get("doi_url"))
            meta["FullText_Status"] = clean(p.get("full_text_status"))
            meta["FullText_Source"] = clean(p.get("full_text_source"))
            meta["FullText_URL"] = clean(p.get("full_text_url"))

            meta["chunk_index"] = ci
            meta["chunk_size"] = len(chunk)

            texts.append(text)
            metas.append(meta)
            chunk_count += 1

        doc_count += 1
        if doc_count % 200 == 0:
            print(f"  papers processed: {doc_count}, chunks prepared: {chunk_count}")

    print(f"Total papers used: {doc_count}")
    print(f"Total chunks to embed: {len(texts)}")

    print("Loading embedding model...")
    model = SentenceTransformer(EMBED_MODEL_NAME)

    print("Embedding chunks...")
    emb = model.encode(
        texts,
        show_progress_bar=True,
        convert_to_numpy=True,
        normalize_embeddings=True
    ).astype(np.float32)

    dim = emb.shape[1]
    print("Creating FAISS index...")
    nlist = 4096  # number of clusters (good for ~100k-500k vectors)
    quantizer = faiss.IndexFlatIP(dim)
    index = faiss.IndexIVFFlat(quantizer, dim, nlist, faiss.METRIC_INNER_PRODUCT)

    index.train(emb)
    index.add(emb)

    #During retrieval controlling speed/accuracy
    index.nprobe = 10


    faiss.write_index(index, os.path.join(INDEX_DIR, "faiss.index"))

    with open(os.path.join(INDEX_DIR, "metas.pkl"), "wb") as f:
        pickle.dump(metas, f)

    with open(os.path.join(INDEX_DIR, "texts.pkl"), "wb") as f:
        pickle.dump(texts, f)

    print("Done. Chunk-based index saved in index_store/")

if __name__ == "__main__":
    main()
