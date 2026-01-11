import os
import pickle
import pandas as pd
import faiss
from sentence_transformers import SentenceTransformer
from utils import make_doc

# ===== CONFIG =====
INPUT_EXCEL = r"..\SPMs_PubMed_AllArticles_Abstract_FullPaper.xlsx"  # adjust if your file name differs
INDEX_DIR = "index_store"
EMBED_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

# Column names expected in your Excel
COLS = {
    "spm": "SPM Name",
    "syn": "Synonyms",
    "pmid": "PMID",
    "title": "Title",
    "journal": "Journal",
    "year": "Year",
    "abstract": "Abstract",
    "full": "Full Paper"
}

def main():
    os.makedirs(INDEX_DIR, exist_ok=True)

    print("Reading Excel...")
    df = pd.read_excel(INPUT_EXCEL)

    print("Building documents...")
    texts = []
    metas = []

    for _, row in df.iterrows():
        text, meta = make_doc(
            row.get(COLS["spm"]),
            row.get(COLS["syn"]),
            row.get(COLS["pmid"]),
            row.get(COLS["title"]),
            row.get(COLS["journal"]),
            row.get(COLS["year"]),
            row.get(COLS["abstract"]),
            row.get(COLS["full"]),
        )
        if text.strip():
            texts.append(text)
            metas.append(meta)

    print(f"Total docs: {len(texts)}")

    print("Loading embedding model...")
    model = SentenceTransformer(EMBED_MODEL_NAME)

    print("Embedding documents (this may take time)...")
    emb = model.encode(texts, show_progress_bar=True, convert_to_numpy=True, normalize_embeddings=True)

    dim = emb.shape[1]
    print("Creating FAISS index...")
    index = faiss.IndexFlatIP(dim)  # cosine if embeddings normalized
    index.add(emb)

    faiss.write_index(index, os.path.join(INDEX_DIR, "faiss.index"))

    with open(os.path.join(INDEX_DIR, "metas.pkl"), "wb") as f:
        pickle.dump(metas, f)

    with open(os.path.join(INDEX_DIR, "texts.pkl"), "wb") as f:
        pickle.dump(texts, f)

    print("✅ Done. Index saved in index_store/")

if __name__ == "__main__":
    main()
