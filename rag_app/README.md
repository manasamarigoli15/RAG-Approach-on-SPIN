## Project Overview

The pipeline:
- starts from a **list of 57 SPMs**,
- expands literature search using **PubChem synonyms**,
- retrieves PubMed metadata and legally available full paper,
- stores all data in **MongoDB** as the primary data store,
- builds a **chunk-level FAISS vector index** for semantic retrieval,
- applies an **LLM (Mistral)** to extract structured interactions with **sentence-level evidence**.

---

## Repository Structure and Scripts

### 1. `get_pubchem_synonyms.py`

**Purpose**  
Fetches PubChem synonyms for each canonical SPM.

**Input**
- `Types_of_SPMs.xlsx`

**Output**
- `Types_of_SPMs_with_synonyms.xlsx`

---

### 2. `get_pubmed_data.py`

**Purpose**  
Core ingestion script that performs the following steps:
- searches PubMed using canonical SPM names and their synonyms,
- retrieves paper metadata (PMID, title, journal, year, abstract, DOI, PMCID),
- fetches full paper:
  - **PMC XML** when a PMCID exists,
  - **Open-Access DOI** via the Unpaywall API when PMC is unavailable,
- stores all results in MongoDB.

**MongoDB Collections Created**
- `spm_rag.papers`  
  Stores paper-level metadata and full text (when available).
- `spm_rag.mentions`  
  Stores mappings between each SPMs, matched synonyms, and PMIDs.

---

### 3. `rag_app/utils.py`

**Purpose**  
Shared utility functions used across the pipeline.

Key functionality:
- consistent document formatting for RAG ingestion (`make_doc`).

This ensures uniform text handling across indexing and extraction stages.

---

### 4. `rag_app/build_index_mongo_chunks.py` ⭐

**Purpose**  
Builds the **semantic RAG index** (main indexing script).

Processing steps:
- reads papers from MongoDB,
- selects text (full text if available, otherwise abstract),
- splits text into overlapping chunks,
- filters for interaction-relevant content,
- embeds chunks using Sentence Transformers,
- builds a scalable FAISS vector index.

**Output**
- `index_store/faiss.index`
- `index_store/metas.pkl`
- `index_store/texts.pkl`

This index is used by both the chatbot and the interaction extraction pipeline.

---

### 5. `rag_app/app.py`

**Purpose**  
Interactive **Streamlit-based RAG chatbot**.

Features:
- semantic retrieval using FAISS,
- LLM-generated answers (Mistral AI),
- transparent citation display (“Sources used”).

This component is primarily used for exploration, debugging, and qualitative validation of retrieval quality.

---

### 6. `rag_app/extract_interactions.py`

**Purpose**  
LLM-based **SPM–protein relation extraction**.

For each SPM, the script:
- retrieves relevant chunks via FAISS,
- prompts the LLM to extract structured interactions:
  - SPM
  - Protein
  - Relation
  - Evidence sentence(s)
  - PMID,
- deduplicates interactions,
- saves results to CSV and MongoDB.

**Output**
- `outputs/triplets_with_evidence_YYYYMMDD.csv`
- MongoDB collection: `spm_rag.interactions`
- Each interaction includes **sentence-level evidence**.
- This minimizes hallucinations and ensures scientific traceability.

---

## Requirements
- Python 3.9+
- MongoDB (local instance)
- Mistral API key (provided via `.env`)

Install dependencies:
```bash
pip install -r rag_app/requirements.txt
