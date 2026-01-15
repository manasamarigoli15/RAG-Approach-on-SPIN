### 1. `get_pubchem_synonyms.py`
**Purpose:**  
Fetches PubChem synonyms for each canonical SPM.

**Input:**  
- `Types_of_SPMs.xlsx`

**Output:**  
- `Types_of_SPMs_with_synonyms.xlsx`

---

### 2. `get_pubmed_data.py`
**Purpose:**  
Core ingestion script that:
- searches PubMed using SPM names + synonyms,
- retrieves metadata (PMID, title, abstract, DOI, PMCID),
- fetches full text legally:
  - **PMC XML** when PMCID exists,
  - **Open-Access DOI** via Unpaywall API when PMC is unavailable,
- stores all results in MongoDB.

**MongoDB Collections Created:**
- `spm_rag.papers` – paper metadata + full text (when available)
- `spm_rag.mentions` –  SPM ↔ synonym ↔ PMID mapping

---

### 3. `rag_app/utils.py`
**Purpose:**  
Shared helper functions.
- Formats documents consistently for RAG ingestion (`make_doc`).

Used by all indexing scripts.

---

### 4. `rag_app/build_index_mongo_chunks.py` ⭐
**Purpose:**  
Builds the **RAG index**.

Steps:
- reads papers from MongoDB,
- selects text (full text if available, else abstract),
- chunks text into overlapping segments,
- filters for interaction-relevant chunks,
- embeds chunks using Sentence Transformers,
- builds a FAISS vector index.

**Output:**
- `index_store/faiss.index`
- `index_store/metas.pkl`
- `index_store/texts.pkl`

This is the **main indexing script** used by both the chatbot and extraction.

---

### 5. `rag_app/app.py`
**Purpose:**  
Interactive **Streamlit RAG chatbot**.

Features:
- semantic retrieval from FAISS
- LLM-generated answers (Mistral AI)
- transparent citation display (“Sources used”).

Used for **exploration and qualitative validation**.

---

### 6. `rag_app/extract_triplets.py`
**Purpose:**  
LLM-based **relation extraction**.

For each single SPM:
- retrieves relevant chunks via FAISS,
- prompts the LLM to extract:
  - SPM
  - Protein
  - Relation
  - **Evidence sentence(s)** (verbatim from text)
  - PMID and chunk index,
- deduplicates results,
- saves output to CSV and optionally MongoDB.

**Output:**
- `outputs/triplets_with_evidence_YYYYMMDD.csv`

This is the **main scientific output** of the project.

---

## Key Design Decisions

### Canonical SPMs vs Synonyms
- **57 canonical SPMs** are fixed and reported.
- **Synonyms are used only for retrieval**, not treated as separate entities.
- Final interaction tables always reference canonical SPM names.

### Evidence-First Extraction
- Interactions are extracted **only if explicitly stated** in text.
- Each interaction includes **sentence-level evidence**.
- This avoids hallucination and ensures scientific traceability.

### Legal Full-Text Access
- Full text is fetched **only when available**:
  - PMC
  - Open-Access DOI
- Paywalled papers fall back to abstracts.

---

## Requirements

- Python 3.9+
- MongoDB (local)
- Mistral API key

Install dependencies:
```bash
pip install -r rag_app/requirements.txt
