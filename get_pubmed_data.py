# -*- coding: utf-8 -*-
import pandas as pd
import requests
import time
import re
import os
from xml.etree import ElementTree as ET
from datetime import datetime, timezone
from pymongo import MongoClient
from bs4 import BeautifulSoup
import fitz  # pip install pymupdf


# =========================
# SPM QUERIES (PROFESSOR PROVIDED) - DO NOT CHANGE
# =========================
SPM_BASE_QUERIES = {
    "MCTR1": '(MCTR1 OR (Maresin conjugate in tissue regeneration 1) AND (SPM))',
    "MCTR2": '(MCTR2 OR (Maresin conjugate in tissue regeneration 2) AND (SPM))',
    "MCTR3": '(MCTR3 OR (Maresin conjugate in tissue regeneration 3) AND (SPM))',

    "PCTR1": '(PCTR1 OR (Protectin conjugate in tissue regeneration 1) AND (SPM))',
    "PCTR2": '(PCTR2 OR (Protectin conjugate in tissue regeneration 2) AND (SPM))',
    "PCTR3": '(PCTR3 OR (Protectin conjugate in tissue regeneration 3) AND (SPM))',

    "RCTR1": '(RCTR1 OR (Resolvin conjugate in tissue regeneration 1) AND (SPM))',
    "RCTR2": '(RCTR2 OR (Resolvin conjugate in tissue regeneration 2) AND (SPM))',
    "RCTR3": '(RCTR3 OR (Resolvin conjugate in tissue regeneration 3) AND (SPM))',

    "LXA4": '(LXA4 OR (Lipoxin A4) AND (Lipoxin))',
    "LXA5": '(LXA5 OR (Lipoxin A5) AND (Lipoxin))',
    "LXB4": '(LXB4 OR (Lipoxin B4) AND (Lipoxin))',
    "LXB5": '(LXB5 OR (Lipoxin B5) AND (Lipoxin))',
    "15-epi-LXA4": '((15-epi-LXA4) OR (AT-LXA4) AND (Lipoxin))',
    "15-epi-LXB4": '((15-epi-LXB4) OR (AT-LXB4) AND (Lipoxin))',

    "7-epi-MaR1": '((7-epi-MaR1) OR (7(S)-Maresin 1) AND (Maresin))',
    "eMaR": '(eMaR OR (13,14-epoxy-maresin) OR (13S-14S-epoxy-maresin) OR (13-14-eMaR) AND (Maresin))',
    "MaR-L1": '(MaR-L1 AND (Maresin))',
    "MaR-L2": '(MaR-L2 AND (Maresin))',

    "MaR1": '((MaR1) OR (Maresin 1) OR (7(R)-Maresin 1) OR (7R-Maresin-1) AND (Maresin))',
    "MaR2": '(MaR2 AND (Maresin))',

    "MaR1 n-3 DPA": '(MaR1 n-3 DPA AND (Maresin))',
    "MaR2 n-3 DPA": '(MaR2 n-3 DPA AND (Maresin))',
    "MaR3 n-3 DPA": '(MaR3 n-3 DPA AND (Maresin))',

    "PD1 n-3 DPA": '(PD1 n-3 DPA AND (Protectin))',
    "PD2 n-3 DPA": '(PD2 n-3 DPA AND (Protectin))',

    "22-hydroxy-PD1": '((22-hydroxy-PD1 OR 22-OH-PD1 OR 22-hydroxyprotectin D1 OR 22-hydroxyneuroprotein D1) AND (Protectin))',
    "AT-PD1": '((AT-PD1 OR 17(R)-Protectin D1 OR AT-NPD1) AND (Protectin))',
    "ENT-AT-NPD1": '(ENT-AT-NPD1 AND (Protectin))',

    "PD1": '(PD1 OR NPD1 OR Protectin D1 OR Neuroprotectin D1 OR NPD-1 AND (Protectin))',
    "PDX": '(PDX OR Protectin DX AND (Protectin))',

    "18S-RvE1": '(18S-Resolvin E1 OR 18S-RvE1 AND (Resolvin))',
    "18S-RvE2": '(18S-Resolvin E2 OR 18S-RvE2 AND (Resolvin))',
    "18S-RvE3": '(18S-Resolvin E3 OR 18S-RvE3 AND (Resolvin))',

    "RvE1": '(RvE1 OR Resolvin E1 AND (Resolvin))',
    "RvE2": '(RvE2 OR Resolvin E2 AND (Resolvin))',
    "RvE3": '(RvE3 OR Resolvin E3 AND (Resolvin))',
    "RvE4": '(RvE4 OR Resolvin E4 AND (Resolvin))',

    "RvD1 n-3 DPA": '(RvD1 n-3 DPA AND (Resolvin))',
    "RvD2 n-3 DPA": '(RvD2 n-3 DPA AND (Resolvin))',
    "RvD5 n-3 DPA": '(RvD5 n-3 DPA AND (Resolvin))',

    "RvT1": '(RvT1 OR Resolvin T1 AND (Resolvin))',
    "RvT2": '(RvT2 OR Resolvin T2 AND (Resolvin))',
    "RvT3": '(RvT3 OR Resolvin T3 AND (Resolvin))',
    "RvT4": '(RvT4 OR Resolvin T4 AND (Resolvin))',

    "RvD1": '(RvD1 OR Resolvin D1 AND (Resolvin))',
    "RvD2": '(RvD2 OR Resolvin D2 AND (Resolvin))',
    "RvD3": '(RvD3 OR Resolvin D3 AND (Resolvin))',
    "RvD4": '(RvD4 OR Resolvin D4 AND (Resolvin))',
    "RvD5": '(RvD5 OR Resolvin D5 AND (Resolvin))',
    "RvD6": '(RvD6 OR Resolvin D6 AND (Resolvin))',

    "AT-RvD1": '(AT-RvD1 OR AT-Resolvin D1 AND (Resolvin))',
    "AT-RvD2": '(AT-RvD2 OR AT-Resolvin D2 AND (Resolvin))',
    "AT-RvD3": '(AT-RvD3 OR AT-Resolvin D3 AND (Resolvin))',
    "AT-RvD4": '(AT-RvD4 OR AT-Resolvin D4 AND (Resolvin))',
    "AT-RvD5": '(AT-RvD5 OR AT-Resolvin D5 OR 17(R)-Resolvin D5 OR 17(R)-RvD5 OR 17-epi-resolvin D5 AND (Resolvin))',
    "AT-RvD6": '(AT-RvD6 OR AT-Resolvin D6 OR 17(R)-Resolvin D6 OR 17(R)-RvD6 OR 17-epi-resolvin D6 AND (Resolvin))',
}


# =========================
# FILES
# =========================
OUTPUT_DIR = "rag_app/outputs"
INPUT_FILE = os.path.join(OUTPUT_DIR, "Types_of_SPMs_with_synonyms.xlsx")

ts = datetime.now().strftime("%Y%m%d_%H%M%S")
OUTPUT_FILE = f"SPMs_PubMed_AllArticles_Abstract_FullPaper_{ts}.xlsx"
EXPORT_EXCEL = False


# =========================
# EXCEL COLUMNS
# =========================
COL_NAME = "Name"
COL_PUBCHEM_SYNONYMS = "PubChem Synonyms"
COL_SPM_CLASS = "SPM Class"
COL_REFERENCE = "Reference"
COL_PUBCHEM_ID = "PubChem ID"
COL_PUBCHEM_LINK = "PubChem Link"


# =========================
# NCBI / UNPAYWALL SETTINGS
# =========================
NCBI_EMAIL = "manasamarigoli15@gmail.com"
NCBI_TOOL = "spm_pubmed"
UNPAYWALL_EMAIL = NCBI_EMAIL


# =========================
# MONGODB SETTINGS
# =========================
MONGO_URI = "mongodb://localhost:27017"
MONGO_DB = "spm_rag"
MONGO_SPMS = "newspms"
MONGO_PAPERS = "newpapers"
MONGO_MENTIONS = "newmentions"


# =========================
# RATE LIMITING / CHUNKING
# =========================
REQS_PER_SEC = 0.34  # ~1 request every 3 seconds
SLEEP_SEC = 1.0 / REQS_PER_SEC

EFETCH_BATCH = 200
SYN_CHUNK_SIZE = 50  # avoids overlong URLs

# USER REQUIREMENT:
# If papers (unique PMIDs) for an SPM > 2000, keep ONLY most recent 2000.
RECENT_CAP = 2000


# =========================
# HTTP SESSION
# =========================
session = requests.Session()
adapter = requests.adapters.HTTPAdapter(max_retries=3, pool_connections=20, pool_maxsize=20)
session.mount("https://", adapter)


# =========================
# HELPERS
# =========================
def now_utc():
    return datetime.now(timezone.utc)


def clean(x):
    if x is None:
        return ""
    try:
        if pd.isna(x):
            return ""
    except Exception:
        pass
    return re.sub(r"\s+", " ", str(x).strip())


def clean_xml_text(s: str) -> str:
    if not s:
        return ""
    return re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F]", "", s)


def xml_text(el):
    if el is None:
        return ""
    return clean("".join(el.itertext()))


def safe_get(url, params=None, timeout=60, tries=3):
    last_err = None
    for attempt in range(tries):
        try:
            r = session.get(
                url,
                params=params,
                timeout=timeout,
                headers={"User-Agent": "Mozilla/5.0"}
            )
            r.raise_for_status()
            time.sleep(SLEEP_SEC)
            return r
        except Exception as e:
            last_err = e
            time.sleep(1.0 + attempt)
    raise last_err


def chunk_list(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i+n]


# =========================
# QUERY BUILDING (SYNONYMS INCLUDED WITH OR; KEEP AND-CONTEXT SAFE)
# =========================
def quote_if_needed(s: str) -> str:
    s = clean(s)
    if not s:
        return ""
    if re.search(r"\s|\(|\)|-|/|,|:|\[|\]|\{|\}", s):
        s = s.replace('"', '\\"')
        return f"\"{s}\""
    return s


def parse_synonyms(cell_value):
    raw = clean(cell_value)
    if not raw:
        return []
    parts = [p.strip() for p in raw.split(";") if p.strip()]
    seen = set()
    out = []
    for p in parts:
        k = p.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(p)
    return out


def split_top_level_and(q: str):
    """
    Split at FIRST top-level AND (depth==0).
    If none, returns (q, "").
    """
    q = clean(q)
    depth = 0
    i = 0
    while i < len(q):
        ch = q[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)

        if depth == 0 and q[i:i+5].upper() == " AND ":
            return q[:i].strip(), q[i+5:].strip()
        i += 1
    return q, ""


def add_synonyms_keep_context(base_query: str, synonyms: list[str]) -> str:
    """
    Professor requirement: add synonyms with OR.
    Important: keep synonyms inside the same AND-context if base query has top-level AND.
    """
    base_query = clean(base_query)
    if not synonyms:
        return base_query

    syn_terms = [quote_if_needed(s) for s in synonyms if clean(s)]
    syn_terms = [s for s in syn_terms if s]
    if not syn_terms:
        return base_query

    left, right = split_top_level_and(base_query)

    if right:
        left_str = left.strip()
        if left_str.startswith("(") and left_str.endswith(")"):
            left_str = left_str[1:-1].strip()
        new_left = f"({left_str} OR " + " OR ".join(syn_terms) + ")"
        return f"(({new_left}) AND ({right}))"

    # no top-level AND: just OR-append
    q = base_query.strip()
    if q.startswith("(") and q.endswith(")"):
        inner = q[1:-1].strip()
        inner = inner + " OR " + " OR ".join(syn_terms)
        return f"({inner})"
    return f"({q} OR " + " OR ".join(syn_terms) + ")"


def build_final_query(name: str, base_query: str, syn_chunk: list[str]) -> str:
    # No extra assumptions; only synonym OR insertion with safe AND-context.
    return add_synonyms_keep_context(base_query, syn_chunk)


# =========================
# PUBMED RETRIEVAL
# Rule: If unique PMIDs for SPM > 2000 -> keep most recent 2000
# =========================
def pubmed_esearch_count(term: str) -> int:
    esearch = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    term = clean(term)

    params = {
        "db": "pubmed",
        "term": term,
        "retmode": "json",
        "retmax": 0,
        "email": NCBI_EMAIL,
        "tool": NCBI_TOOL,
    }

    r = safe_get(esearch, params=params, timeout=60)
    txt = (r.text or "").strip()
    if not txt.startswith("{"):
        return 0

    j = r.json()
    return int(j.get("esearchresult", {}).get("count", 0))


def pubmed_esearch_recent_pmids(term: str, max_n: int):
    """
    Returns up to max_n PMIDs sorted by most recent pub date.
    """
    esearch = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    term = clean(term)

    params = {
        "db": "pubmed",
        "term": term,
        "retmode": "json",
        "retstart": 0,
        "retmax": max_n,
        "sort": "pub+date",
        "email": NCBI_EMAIL,
        "tool": NCBI_TOOL,
    }

    r = safe_get(esearch, params=params, timeout=90)
    txt = (r.text or "").strip()
    if not txt.startswith("{"):
        print("\n[NCBI ESEARCH ERROR] Non-JSON response.")
        print("HTTP:", r.status_code)
        print("Query (first 200):", term[:200])
        print("Preview:", txt[:500])
        return []

    j = r.json()
    pmids = j.get("esearchresult", {}).get("idlist", []) or []

    seen = set()
    out = []
    for p in pmids:
        p = clean(p)
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return out


def pubmed_esummary_pubdates(pmids: list[str]):
    """
    Get pubdate strings for PMIDs using esummary (json).
    Returns dict pmid -> pubdate_str
    """
    if not pmids:
        return {}

    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
    out = {}

    # keep batches reasonable
    batch_size = 200
    for i in range(0, len(pmids), batch_size):
        batch = pmids[i:i+batch_size]
        params = {
            "db": "pubmed",
            "id": ",".join(batch),
            "retmode": "json",
            "email": NCBI_EMAIL,
            "tool": NCBI_TOOL,
        }
        r = safe_get(base, params=params, timeout=60)
        txt = (r.text or "").strip()
        if not txt.startswith("{"):
            continue
        j = r.json()
        res = j.get("result", {}) or {}
        for pmid in batch:
            rec = res.get(str(pmid)) or {}
            # pubdate can be like "2024 Jan 15"
            pd_str = clean(rec.get("pubdate", ""))
            if pd_str:
                out[str(pmid)] = pd_str
    return out


def _pubdate_sort_key(pubdate_str: str):
    """
    Convert pubdate string to sortable key.
    Handles formats like:
    - "2025 Dec 03"
    - "2024 Jan"
    - "2023"
    Fallback keeps it low.
    """
    s = clean(pubdate_str)
    if not s:
        return (0, 0, 0)

    # common: "YYYY Mon DD" or "YYYY Mon" or "YYYY"
    parts = s.split()
    year = 0
    month = 0
    day = 0

    try:
        year = int(parts[0])
    except Exception:
        year = 0

    mon_map = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12
    }

    if len(parts) >= 2:
        m = parts[1].lower()[:3]
        month = mon_map.get(m, 0)

    if len(parts) >= 3:
        try:
            day = int(re.sub(r"\D+", "", parts[2]))
        except Exception:
            day = 0

    return (year, month, day)


def enforce_recent_cap_if_needed(unique_pmids: list[str]):
    """
    USER RULE:
    If unique_pmids > 2000, keep the most recent 2000 (by pubdate).
    """
    if len(unique_pmids) <= RECENT_CAP:
        return unique_pmids

    print(f"[RECENT CAP] Unique PMIDs={len(unique_pmids)} > {RECENT_CAP}. Keeping most recent {RECENT_CAP}.")

    pubdates = pubmed_esummary_pubdates(unique_pmids)
    # If some PMIDs have no pubdate, they’ll sort to the bottom.
    sorted_pmids = sorted(
        unique_pmids,
        key=lambda p: _pubdate_sort_key(pubdates.get(str(p), "")),
        reverse=True
    )
    return sorted_pmids[:RECENT_CAP]


# =========================
# PUBMED: EFETCH (XML) => METADATA + ABSTRACT + DOI
# =========================
def pubmed_efetch_details(pmids):
    if not pmids:
        return []

    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    rows = []

    for i in range(0, len(pmids), EFETCH_BATCH):
        batch = pmids[i:i + EFETCH_BATCH]

        params = {
            "db": "pubmed",
            "id": ",".join(batch),
            "retmode": "xml",
            "tool": NCBI_TOOL,
            "email": NCBI_EMAIL,
        }

        xml_raw = safe_get(base, params, timeout=90).text
        xml_raw = clean_xml_text(xml_raw)

        try:
            root = ET.fromstring(xml_raw)
        except ET.ParseError:
            continue

        for art in root.findall(".//PubmedArticle"):
            pmid = xml_text(art.find(".//PMID"))
            title = xml_text(art.find(".//ArticleTitle"))
            journal = xml_text(art.find(".//Journal/Title"))
            year = xml_text(art.find(".//PubDate/Year"))

            abs_parts = []
            for abs_el in art.findall(".//Abstract/AbstractText"):
                abs_parts.append(xml_text(abs_el))
            abstract = clean(" ".join(abs_parts))

            doi = ""
            for aid in art.findall(".//ArticleId"):
                if aid.get("IdType", "").lower() == "doi":
                    doi = clean(aid.text)
                    break

            rows.append({
                "PMID": pmid,
                "Title": title,
                "Journal": journal,
                "Year": year,
                "Abstract": abstract,
                "PubMed URL": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
                "DOI": doi,
                "DOI URL": f"https://doi.org/{doi}" if doi else ""
            })

    return rows


# =========================
# PMID -> PMCID (ELINK)
# =========================
def pmid_to_pmcid(pmid):
    if not pmid:
        return ""

    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/elink.fcgi"
    params = {
        "dbfrom": "pubmed",
        "db": "pmc",
        "id": pmid,
        "retmode": "xml",
        "tool": NCBI_TOOL,
        "email": NCBI_EMAIL,
    }

    xml_raw = safe_get(base, params, timeout=60).text
    xml_raw = clean_xml_text(xml_raw)

    try:
        root = ET.fromstring(xml_raw)
    except ET.ParseError:
        return ""

    id_el = root.find(".//LinkSetDb/Link/Id")
    if id_el is None or not id_el.text:
        return ""

    return "PMC" + clean(id_el.text)


# =========================
# FULL TEXT FROM PMC (XML)
# =========================
def fetch_full_text_from_pmc(pmcid):
    if not pmcid:
        return ""

    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    params = {
        "db": "pmc",
        "id": pmcid,
        "retmode": "xml",
        "tool": NCBI_TOOL,
        "email": NCBI_EMAIL,
    }

    xml_raw = safe_get(base, params, timeout=90).text
    xml_raw = clean_xml_text(xml_raw)

    try:
        root = ET.fromstring(xml_raw)
    except ET.ParseError:
        return ""

    body = root.find(".//body")
    if body is None:
        return ""

    return clean(" ".join(body.itertext()))


# =========================
# DOI OA FULL TEXT (UNPAYWALL + PDF/HTML)
# =========================
def extract_pdf_text(pdf_bytes):
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        pages = []
        for p in doc:
            pages.append(p.get_text("text"))
        return clean("\n".join(pages))
    except Exception:
        return ""


def extract_html_text(html):
    try:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        return clean(soup.get_text(" "))
    except Exception:
        return ""


def fetch_full_text_from_doi_oa(doi):
    doi = clean(doi)
    if not doi:
        return ("", "NO_DOI", "NONE", "")

    api = f"https://api.unpaywall.org/v2/{doi}"
    params = {"email": UNPAYWALL_EMAIL}

    try:
        j = safe_get(api, params=params, timeout=60).json()
    except Exception:
        return ("", "UNPAYWALL_ERROR", "NONE", "")

    best = j.get("best_oa_location") or {}
    url_for_pdf = best.get("url_for_pdf") or ""
    url_for_landing = best.get("url") or ""

    if url_for_pdf:
        try:
            pdf = safe_get(url_for_pdf, params=None, timeout=90).content
            txt = extract_pdf_text(pdf)
            if txt:
                return (txt, "OK", "DOI_OA_PDF", url_for_pdf)
        except Exception:
            pass

    if url_for_landing:
        try:
            html = safe_get(url_for_landing, params=None, timeout=90).text
            txt = extract_html_text(html)
            if txt:
                return (txt, "OK", "DOI_OA_HTML", url_for_landing)
        except Exception:
            pass

    return ("", "NO_OA_FOUND", "NONE", "")


# =========================
# MAIN
# =========================
def main():
    df = pd.read_excel(INPUT_FILE)
    df[COL_NAME] = df[COL_NAME].apply(clean)

    client = MongoClient(MONGO_URI)
    db = client[MONGO_DB]

    spms_col = db[MONGO_SPMS]
    papers_col = db[MONGO_PAPERS]
    mentions_col = db[MONGO_MENTIONS]

    spms_col.create_index("name", unique=True)
    papers_col.create_index("pmid", unique=True)
    mentions_col.create_index([("spm_name", 1), ("synonym_matched", 1), ("pmid", 1)], unique=True)

    merged = {}  # key=(spm_name, pmid)

    print("\n=== Step 1: Save canonical SPM master list into MongoDB ===")
    for _, row in df.iterrows():
        name = clean(row.get(COL_NAME))
        if not name:
            continue

        spm_class = clean(row.get(COL_SPM_CLASS))
        reference = clean(row.get(COL_REFERENCE))
        pubchem_id = clean(row.get(COL_PUBCHEM_ID))
        pubchem_link = clean(row.get(COL_PUBCHEM_LINK))
        pubchem_syn_raw = clean(row.get(COL_PUBCHEM_SYNONYMS))

        spms_col.update_one(
            {"name": name},
            {"$setOnInsert": {"created_at": now_utc()},
             "$set": {
                 "name": name,
                 "spm_class": spm_class,
                 "reference": reference,
                 "pubchem_id": pubchem_id,
                 "pubchem_link": pubchem_link,
                 "downloaded": "3D",
                 "pubchem_synonyms_raw": pubchem_syn_raw
             }},
            upsert=True
        )

    print("Saved SPM master list to collection:", MONGO_SPMS)

    print("\n=== Step 2: PubMed retrieval (PMIDs + metadata) and save to MongoDB ===")

    for _, row in df.iterrows():
        name = clean(row.get(COL_NAME))
        if not name:
            continue

        base_query = SPM_BASE_QUERIES.get(name)
        if not base_query:
            print(f"No base query for {name}, skipping")
            continue

        spm_class = clean(row.get(COL_SPM_CLASS))
        reference = clean(row.get(COL_REFERENCE))
        pubchem_id = clean(row.get(COL_PUBCHEM_ID))
        pubchem_link = clean(row.get(COL_PUBCHEM_LINK))
        pubchem_syn_raw = clean(row.get(COL_PUBCHEM_SYNONYMS))
        synonyms = parse_synonyms(pubchem_syn_raw)

        # build chunked queries (only to avoid overlong URLs)
        if not synonyms:
            queries = [build_final_query(name, base_query, [])]
        else:
            queries = [build_final_query(name, base_query, chunk) for chunk in chunk_list(synonyms, SYN_CHUNK_SIZE)]

        print(f"\n{name}: running {len(queries)} PubMed queries (synonyms chunked)")
        for qi, q in enumerate(queries, 1):
            print(f"  Query {qi}/{len(queries)} length={len(q)}")

        # Collect candidate PMIDs (most-recent from each query; then enforce global RECENT_CAP)
        candidate_pmids = []
        seen_pmids = set()

        for q in queries:
            cnt = pubmed_esearch_count(q)
            if cnt <= 0:
                continue

            # If this query alone is huge, we still only need recent 2000 from it.
            fetch_n = cnt if cnt <= RECENT_CAP else RECENT_CAP
            pmids = pubmed_esearch_recent_pmids(q, fetch_n)

            for p in pmids:
                if p and p not in seen_pmids:
                    seen_pmids.add(p)
                    candidate_pmids.append(p)

        if not candidate_pmids:
            print(f"{name}: no PMIDs found")
            continue

        # Enforce user rule at SPM level
        final_pmids = enforce_recent_cap_if_needed(candidate_pmids)

        details = pubmed_efetch_details(final_pmids)

        for art in details:
            pmid = clean(art.get("PMID"))
            if not pmid:
                continue

            key = (name, pmid)
            if key not in merged:
                merged[key] = {
                    "Name": name,
                    "Synonyms": set(),
                    "SPM Class": spm_class,
                    "Reference": reference,
                    "PubChem ID": pubchem_id,
                    "PubChem Link": pubchem_link,
                    "Downloaded": "3D",
                    "PubChem Synonyms": pubchem_syn_raw,
                    "PMID": pmid,
                    "PMCID": "",
                    "DOI": art.get("DOI", ""),
                    "DOI URL": art.get("DOI URL", ""),
                    "Title": art.get("Title", ""),
                    "Journal": art.get("Journal", ""),
                    "Year": art.get("Year", ""),
                    "Abstract": art.get("Abstract", ""),
                    "PubMed URL": art.get("PubMed URL", ""),
                    "Full Paper Status": "PENDING",
                }

            merged[key]["Synonyms"].add(name)

            existing = papers_col.find_one(
                {"pmid": pmid},
                {"pmcid": 1, "pmc_url": 1, "full_text": 1, "full_text_source": 1, "full_text_status": 1, "full_text_url": 1}
            ) or {}

            papers_col.update_one(
                {"pmid": pmid},
                {"$setOnInsert": {"created_at": now_utc()},
                 "$set": {
                     "pmid": pmid,
                     "title": art.get("Title", ""),
                     "journal": art.get("Journal", ""),
                     "year": art.get("Year", ""),
                     "abstract": art.get("Abstract", ""),
                     "pubmed_url": art.get("PubMed URL", ""),
                     "doi": art.get("DOI", ""),
                     "doi_url": art.get("DOI URL", ""),
                     "pmcid": existing.get("pmcid", ""),
                     "pmc_url": existing.get("pmc_url", ""),
                     "full_text": existing.get("full_text", ""),
                     "full_text_source": existing.get("full_text_source", "NONE"),
                     "full_text_status": existing.get("full_text_status", "PENDING"),
                     "full_text_url": existing.get("full_text_url", ""),
                 }},
                upsert=True
            )

            # canonical mention
            mentions_col.update_one(
                {"spm_name": name, "synonym_matched": name, "pmid": pmid},
                {"$setOnInsert": {"created_at": now_utc()},
                 "$set": {
                     "spm_name": name,
                     "spm_class": spm_class,
                     "reference": reference,
                     "synonym_matched": name,
                     "pmid": pmid,
                     "pubchem_id": pubchem_id,
                     "pubchem_link": pubchem_link,
                     "downloaded": "3D",
                     "pubchem_synonyms_raw": pubchem_syn_raw
                 }},
                upsert=True
            )

            # synonym mentions (traceability)
            for syn in synonyms:
                mentions_col.update_one(
                    {"spm_name": name, "synonym_matched": syn, "pmid": pmid},
                    {"$setOnInsert": {"created_at": now_utc()},
                     "$set": {
                         "spm_name": name,
                         "spm_class": spm_class,
                         "reference": reference,
                         "synonym_matched": syn,
                         "pmid": pmid,
                         "pubchem_id": pubchem_id,
                         "pubchem_link": pubchem_link,
                         "downloaded": "3D",
                         "pubchem_synonyms_raw": pubchem_syn_raw
                     }},
                    upsert=True
                )

        captured = len({k for k in merged.keys() if k[0] == name})
        print(f"{name}: papers captured = {captured}")

    print("\n=== Step 3: Fetch full papers (PMC first, DOI OA fallback) and update MongoDB ===")

    unique_pmids = sorted({v["PMID"] for v in merged.values() if v.get("PMID")})
    print(f"Total UNIQUE PMIDs across all SPMs = {len(unique_pmids)}")

    for idx, pmid in enumerate(unique_pmids, start=1):
        recs_for_pmid = [k for k in merged.keys() if k[1] == pmid]
        if not recs_for_pmid:
            continue

        pmcid = pmid_to_pmcid(pmid)

        if pmcid:
            try:
                txt = fetch_full_text_from_pmc(pmcid)
                papers_col.update_one(
                    {"pmid": pmid},
                    {"$set": {
                        "pmcid": pmcid,
                        "pmc_url": f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/",
                        "full_text_url": f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/",
                        "full_text": txt,
                        "full_text_source": "PMC",
                        "full_text_status": "OK" if txt else "FETCH_ERROR",
                    }},
                    upsert=True
                )
                status = "OK" if txt else "FETCH_ERROR"
            except Exception:
                papers_col.update_one(
                    {"pmid": pmid},
                    {"$set": {
                        "pmcid": pmcid,
                        "pmc_url": f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/",
                        "full_text_url": f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/",
                        "full_text": "",
                        "full_text_source": "PMC",
                        "full_text_status": "FETCH_ERROR",
                    }},
                    upsert=True
                )
                status = "FETCH_ERROR"

            for key in recs_for_pmid:
                merged[key]["PMCID"] = pmcid
                merged[key]["Full Paper Status"] = status

        else:
            doi = clean(merged[recs_for_pmid[0]].get("DOI", ""))
            txt, status, source, url = fetch_full_text_from_doi_oa(doi)

            papers_col.update_one(
                {"pmid": pmid},
                {"$set": {
                    "pmcid": "",
                    "pmc_url": "",
                    "full_text": txt,
                    "full_text_source": source,
                    "full_text_status": status,
                    "full_text_url": url,
                }},
                upsert=True
            )

            for key in recs_for_pmid:
                merged[key]["PMCID"] = ""
                merged[key]["Full Paper Status"] = status

        if idx % 100 == 0:
            print(f"  processed fulltext for {idx}/{len(unique_pmids)} PMIDs...")

    print("\nDONE. MongoDB is now fully populated.")
    print(f"- {MONGO_DB}.{MONGO_SPMS}")
    print(f"- {MONGO_DB}.{MONGO_PAPERS}")
    print(f"- {MONGO_DB}.{MONGO_MENTIONS}")

    if EXPORT_EXCEL:
        out_rows = []
        for _, v in merged.items():
            row = dict(v)
            row["Synonyms"] = "; ".join(sorted(row["Synonyms"]))
            out_rows.append(row)

        out_df = pd.DataFrame(out_rows)
        out_df.to_excel(OUTPUT_FILE, index=False)
        print("\nExcel snapshot saved:", OUTPUT_FILE)


if __name__ == "__main__":
    main()
