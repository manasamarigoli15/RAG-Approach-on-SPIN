import os
import json
import re
import pickle
import csv
from datetime import datetime
import pandas as pd
import faiss
import numpy as np
from dotenv import load_dotenv
from mistralai import Mistral
from sentence_transformers import SentenceTransformer
from pymongo import MongoClient

# MongoDB configuration
MONGO_URI = "mongodb://localhost:27017"
MONGO_DB = "spm_rag"
MONGO_Interactions = "interactions"

OUT_DIR = "outputs"

def load_canonical_spms_from_excel(
    path=os.path.join(OUT_DIR, "Types_of_SPMs_with_synonyms.xlsx"),
    col="Name"
):
    df = pd.read_excel(path)
    spms = sorted(df[col].dropna().astype(str).str.strip().unique().tolist())
    return spms

load_dotenv()

INDEX_DIR = "index_store"
EMBED_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
TOP_K = 15  # retrieved chunks per query

MODEL_NAME = "mistral-large-latest"
API_KEY = os.getenv("MISTRAL_API_KEY", "")

os.makedirs(OUT_DIR, exist_ok=True)

def load_store():
    index = faiss.read_index(os.path.join(INDEX_DIR, "faiss.index"))
    try:
        index.nprobe = 10
    except Exception:
        pass

    metas = pickle.load(open(os.path.join(INDEX_DIR, "metas.pkl"), "rb"))
    texts = pickle.load(open(os.path.join(INDEX_DIR, "texts.pkl"), "rb"))
    return index, metas, texts

def retrieve(query, embed_model, index, metas, texts, k=TOP_K):
    q_emb = embed_model.encode([query], convert_to_numpy=True, normalize_embeddings=True)
    scores, ids = index.search(q_emb.astype(np.float32), k)

    hits = []
    for score, row_id in zip(scores[0], ids[0]):
        if row_id == -1:
            continue
        hits.append((float(score), metas[row_id], texts[row_id]))
    return hits

def build_extraction_prompt(spm_name, retrieved):
    blocks = []
    for i, (score, meta, chunk) in enumerate(retrieved, start=1):
        pmid = meta.get("PMID", "")
        title = meta.get("Title", "")
        chunk_index = meta.get("chunk_index", "")
        blocks.append(
            f"[{i}] PMID:{pmid} | chunk:{chunk_index} | title:{title}\n{chunk}"
        )
    context = "\n\n".join(blocks)

    prompt = f"""
You are extracting SPM–target protein interactions from scientific text.

Task:
From the CONTEXT, extract interaction where the SPM is "{spm_name}".

Return ONLY valid JSON in this exact schema:
{{
  "spm": "{spm_name}",
  "interactions": [
    {{
      "protein": "string",
      "relation": "activates|inhibits|binds|upregulates|downregulates|modulates|unknown",
      "evidence": "1-2 exact sentences copied from the context that support the relation",
      "pmid": "string",
      "chunk_index": "number or string",
      "source_id": "the bracket id like [1] or [2]"
    }}
  ]
}}

Rules:
- Evidence MUST be copied from the context (verbatim or near-verbatim).
- If no interaction is stated, return empty interactions list.
- Do not guess proteins. Do not invent.
- Prefer receptor/protein names (e.g., GPR18, ALX/FPR2, ChemR23/CMKLR1, BLT1, BLT2, ALOX5, PTGS2).

CONTEXT:
{context}
""".strip()

    return prompt

def safe_json(text):
    # Extract JSON if model adds extra text
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None

def main():

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    if not API_KEY:
        raise RuntimeError("Missing MISTRAL_API_KEY in .env")

    llm = Mistral(api_key=API_KEY)
    embed_model = SentenceTransformer(EMBED_MODEL_NAME)
    index, metas, texts = load_store()

    client = MongoClient(MONGO_URI)
    db = client[MONGO_DB]
    interactions_col = db[MONGO_Interactions]

    # Unique key so re-runs update instead of duplicating
    interactions_col.create_index(
        [("SPM", 1), ("Protein", 1), ("Relation", 1), ("PMID", 1), ("ChunkIndex", 1)],
        unique=True
    )

    # ---- Put your SPM list here (start small) ----
    spms = load_canonical_spms_from_excel("Types_of_SPMs_with_synonyms.xlsx", col="Name")
    print("Canonical SPMs loaded:", len(spms))

    all_rows = []
    for spm in spms:
        retrieved = retrieve(spm, embed_model, index, metas, texts, k=TOP_K)
        prompt = build_extraction_prompt(spm, retrieved)

        resp = llm.chat.complete(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}]
        )
        out = resp.choices[0].message.content
        data = safe_json(out)

        if not data:
            print("Failed to parse JSON for", spm)
            continue

        for it in data.get("interactions", []):
            row = {
                "SPM": spm,
                "Protein": it.get("protein", "").strip(),
                "Relation": it.get("relation", "").strip(),
                "Evidence": it.get("evidence", "").strip(),
                "PMID": it.get("pmid", "").strip(),
                "ChunkIndex": str(it.get("chunk_index", "")).strip(),
                "SourceID": it.get("source_id", "").strip(),
                "created_at": datetime.utcnow().isoformat(),
                "run_id": run_id,
            }

            # Save for CSV
            all_rows.append({k: row[k] for k in ["SPM","Protein","Relation","Evidence","PMID","ChunkIndex","SourceID"]})

            # Save to MongoDB (upsert = no duplicates across reruns)
            interactions_col.update_one(
                {
                    "SPM": row["SPM"],
                    "Protein": row["Protein"],
                    "Relation": row["Relation"],
                    "PMID": row["PMID"],
                    "ChunkIndex": row["ChunkIndex"],
                },
                {"$set": row},
                upsert=True
            )


        print(f"{spm}: extracted {len(data.get('interactions', []))} interactions")

    out_path = os.path.join(OUT_DIR, f"interactions_with_evidence_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["SPM","Protein","Relation","Evidence","PMID","ChunkIndex","SourceID"])
        w.writeheader()
        w.writerows(all_rows)

    print("Saved:", out_path)

if __name__ == "__main__":
    main()
