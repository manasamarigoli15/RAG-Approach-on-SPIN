import pandas as pd
import requests
import time
import re
import os
from xml.etree import ElementTree as ET
from datetime import datetime
from pymongo import MongoClient
from bs4 import BeautifulSoup
import fitz  # pip install pymupdf


# =========================
# FILES
# =========================
OUTPUT_DIR = "rag_app/outputs"
INPUT_FILE = os.path.join(OUTPUT_DIR, "Types_of_SPMs_with_synonyms.xlsx")

ts = datetime.now().strftime("%Y%m%d_%H%M%S")
OUTPUT_FILE = f"SPMs_PubMed_AllArticles_Abstract_FullPaper_{ts}.xlsx"

# Turn Excel export ON/OFF
EXPORT_EXCEL = False  # <- set True only if you want a snapshot file


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
NCBI_EMAIL = "your_email@example.com"
NCBI_TOOL = "spm_pubmed"
# NCBI_API_KEY = ""  # optional

UNPAYWALL_EMAIL = NCBI_EMAIL


# =========================
# MONGODB SETTINGS
# =========================
MONGO_URI = "mongodb://localhost:27017"
MONGO_DB = "spm_rag"
MONGO_SPMS = "spms"
MONGO_PAPERS = "papers"
MONGO_MENTIONS = "mentions"


# =========================
# RATE LIMITING
# =========================
REQS_PER_SEC = 1
SLEEP_SEC = 1.0 / REQS_PER_SEC

ESEARCH_PAGE = 5000
EFETCH_BATCH = 200


# =========================
# HTTP SESSION
# =========================
session = requests.Session()
adapter = requests.adapters.HTTPAdapter(max_retries=3, pool_connections=20, pool_maxsize=20)
session.mount("https://", adapter)


# =========================
# HELPERS
# =========================
def clean(x):
    """Safe string cleaner for Excel NaN/floats."""
    if x is None:
        return ""
    try:
        if pd.isna(x):
            return ""
    except Exception:
        pass
    return re.sub(r"\s+", " ", str(x).strip())


def clean_xml_text(s: str) -> str:
    """Remove invalid XML 1.0 control characters (except tab/newline/carriage return)."""
    if not s:
        return ""
    return re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F]", "", s)


def xml_text(el):
    """Safe XML text: handles nested tags."""
    if el is None:
        return ""
    return clean("".join(el.itertext()))


def safe_get(url, params=None, timeout=60, tries=3):
    """Requests wrapper with retries + UA header."""
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


# =========================
# SYNONYM FILTER (CLEAN DATA)
# =========================
CAS_RE = re.compile(r"^\d{2,7}-\d{2}-\d$")
CHEBI_RE = re.compile(r"^CHEBI:\d+$", re.IGNORECASE)

def looks_like_junk_synonym(s):
    if not s:
        return True
    s = s.strip()

    if len(s) < 3:
        return True
    if CAS_RE.match(s):
        return True
    if CHEBI_RE.match(s):
        return True
    if s.lower().startswith(("cid:", "sid:", "inchikey:", "inchi=")):
        return True
    if re.fullmatch(r"[\d\W_]+", s):
        return True

    return False


def parse_synonyms(cell_value):
    """
    Input like: "syn1; syn2; syn3"
    Output: list[str] cleaned, filtered, unique
    """
    raw = clean(cell_value)
    if not raw:
        return []
    parts = [p.strip() for p in raw.split(";")]
    good = []
    for p in parts:
        if not p:
            continue
        if looks_like_junk_synonym(p):
            continue
        good.append(p)
    # unique but stable-ish
    seen = set()
    out = []
    for g in good:
        key = g.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(g)
    return out


# =========================
# PUBMED: ESEARCH (JSON) => ALL PMIDS
# =========================
def pubmed_esearch_all_pmids(term):
    """
    Returns list of PMIDs for a query using ESearch XML with pagination.
    This avoids JSONDecodeError when NCBI returns non-JSON responses.
    """
    if not term:
        return []

    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"

    safe_term = term.replace('"', "")
    SPM_CONTEXT_TERMS = [
    "resolvin", "maresin", "protectin", "lipoxin",
    "\"specialized pro-resolving\"", "\"pro-resolving\"",
    "\"resolution of inflammation\"", "\"inflammation resolution\"",
    "\"lipid mediator\"", "\"specialized lipid mediator\"",
    "omega-3",
    "ALX", "FPR2", "GPR18", "GPR32", "ChemR23"
    ]

    context_query = " OR ".join(SPM_CONTEXT_TERMS)

    query = f"(\"{safe_term}\"[Title/Abstract]) AND ({context_query})"

    # First request: get Count
    params0 = {
        "db": "pubmed",
        "term": query,
        "retmode": "xml",
        "retmax": 0,
        "tool": NCBI_TOOL,
        "email": NCBI_EMAIL,
    }

    r0 = safe_get(base, params0, timeout=60)
    xml0 = clean_xml_text(r0.text)

    try:
        root0 = ET.fromstring(xml0)
    except ET.ParseError:
        # if NCBI returned HTML/error text, just skip this term
        return []

    count_el = root0.find(".//Count")
    count = int(count_el.text) if count_el is not None and count_el.text else 0
    if count == 0:
        return []

    pmids = []
    retstart = 0

    while retstart < count:
        params = dict(params0)
        params["retstart"] = retstart
        params["retmax"] = min(ESEARCH_PAGE, count - retstart)

        r = safe_get(base, params, timeout=60)
        xml = clean_xml_text(r.text)

        try:
            root = ET.fromstring(xml)
        except ET.ParseError:
            # skip this page if response is broken
            break

        idlist = [clean(x.text) for x in root.findall(".//IdList/Id") if x is not None and x.text]
        pmids.extend(idlist)

        retstart += params["retmax"]

    # unique, stable order
    seen = set()
    out = []
    for p in pmids:
        if p in seen:
            continue
        seen.add(p)
        out.append(p)
    return out



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

            # DOI
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

    # pmc ids returned are numeric like 1234567, need prefix "PMC"
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

    text = clean(" ".join(body.itertext()))
    return text


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
        # remove scripts/styles
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        return clean(soup.get_text(" "))
    except Exception:
        return ""


def fetch_full_text_from_doi_oa(doi):
    """
    Mandatory DOI attempt:
    - If Unpaywall finds OA PDF/HTML -> fetch and extract
    - Else -> NO_OA_FOUND
    """
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

    # Try PDF first
    if url_for_pdf:
        try:
            pdf = safe_get(url_for_pdf, params=None, timeout=90).content
            txt = extract_pdf_text(pdf)
            if txt:
                return (txt, "OK", "DOI_OA_PDF", url_for_pdf)
        except Exception:
            pass

    # Try HTML landing page text
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
    # --- Load SPM list ---
    df = pd.read_excel(INPUT_FILE)
    df[COL_NAME] = df[COL_NAME].apply(clean)

    # --- MongoDB init ---
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
            {"$setOnInsert": {"created_at": datetime.utcnow()},
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

    # For each SPM, use [canonical name + synonyms] to retrieve PMIDs
    for _, row in df.iterrows():
        name = clean(row.get(COL_NAME))
        if not name:
            continue

        spm_class = clean(row.get(COL_SPM_CLASS))
        reference = clean(row.get(COL_REFERENCE))
        pubchem_id = clean(row.get(COL_PUBCHEM_ID))
        pubchem_link = clean(row.get(COL_PUBCHEM_LINK))
        pubchem_syn_raw = clean(row.get(COL_PUBCHEM_SYNONYMS))

        synonyms = parse_synonyms(pubchem_syn_raw)

        # Include canonical name as a search term
        terms = [name] + synonyms

        # Retrieve PMIDs for each term, merge unique
        all_pmids = []
        seen_pmids = set()

        for term in terms:
            pmids = pubmed_esearch_all_pmids(term)
            for p in pmids:
                if p in seen_pmids:
                    continue
                seen_pmids.add(p)
                all_pmids.append(p)

        if not all_pmids:
            print(f"{name}: no PMIDs found")
            continue

        details = pubmed_efetch_details(all_pmids)

        # For each paper metadata result, upsert into papers + mention mapping
        for art in details:
            pmid = clean(art.get("PMID"))
            if not pmid:
                continue

            key = (name, pmid)

            if key not in merged:
                merged[key] = {
                    "Name": name,
                    "Synonyms": set(),  # matched terms that found this paper
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

            # Determine which term matched this PMID (best-effort):
            # If the canonical name was searched, include it; and we also store each synonym attempt via mentions.
            # We'll record mentions for canonical + every synonym regardless, so later we can see exactly what retrieved it.
            # For merged summary we just keep a set of all attempted terms for that SPM+PMID.
            # (You can refine this to true "hit term", but it's not required for correctness.)
            # We'll at least add canonical name so it is never empty.
            merged[key]["Synonyms"].add(name)

            # 1) Upsert paper METADATA only (full text is added later)
            papers_col.update_one(
                {"pmid": pmid},
                {"$setOnInsert": {"created_at": datetime.utcnow()},
                 "$set": {
                     "pmid": pmid,
                     "title": art.get("Title", ""),
                     "journal": art.get("Journal", ""),
                     "year": art.get("Year", ""),
                     "abstract": art.get("Abstract", ""),
                     "pubmed_url": art.get("PubMed URL", ""),
                     "doi": art.get("DOI", ""),
                     "doi_url": art.get("DOI URL", ""),

                     # placeholders, filled later
                     "pmcid": papers_col.find_one({"pmid": pmid}, {"pmcid": 1}).get("pmcid", "") if papers_col.find_one({"pmid": pmid}, {"pmcid": 1}) else "",
                     "pmc_url": papers_col.find_one({"pmid": pmid}, {"pmc_url": 1}).get("pmc_url", "") if papers_col.find_one({"pmid": pmid}, {"pmc_url": 1}) else "",
                     "full_text": papers_col.find_one({"pmid": pmid}, {"full_text": 1}).get("full_text", "") if papers_col.find_one({"pmid": pmid}, {"full_text": 1}) else "",
                     "full_text_source": papers_col.find_one({"pmid": pmid}, {"full_text_source": 1}).get("full_text_source", "NONE") if papers_col.find_one({"pmid": pmid}, {"full_text_source": 1}) else "NONE",
                     "full_text_status": papers_col.find_one({"pmid": pmid}, {"full_text_status": 1}).get("full_text_status", "PENDING") if papers_col.find_one({"pmid": pmid}, {"full_text_status": 1}) else "PENDING",
                     "full_text_url": papers_col.find_one({"pmid": pmid}, {"full_text_url": 1}).get("full_text_url", "") if papers_col.find_one({"pmid": pmid}, {"full_text_url": 1}) else "",
                 }},
                upsert=True
            )

            # 2) Mention mapping rows (canonical name + each synonym)
            # Insert canonical mention
            mentions_col.update_one(
                {"spm_name": name, "synonym_matched": name, "pmid": pmid},
                {"$setOnInsert": {"created_at": datetime.utcnow()},
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

            # Insert synonym mentions (so you can track synonym usage)
            for syn in synonyms:
                if not syn:
                    continue
                mentions_col.update_one(
                    {"spm_name": name, "synonym_matched": syn, "pmid": pmid},
                    {"$setOnInsert": {"created_at": datetime.utcnow()},
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

        print(f"{name}: papers captured = {len({k for k in merged.keys() if k[0] == name})}")

    print("\n=== Step 3: Fetch full papers (PMC first, DOI OA fallback) and update MongoDB ===")

    # We fetch full text per unique PMID
    unique_pmids = sorted({v["PMID"] for v in merged.values() if v.get("PMID")})

    for idx, pmid in enumerate(unique_pmids, start=1):
        recs_for_pmid = [k for k in merged.keys() if k[1] == pmid]
        if not recs_for_pmid:
            continue

        # try PMCID
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

            # update merged summary status for all SPMs linked to this PMID
            for key in recs_for_pmid:
                merged[key]["PMCID"] = pmcid
                merged[key]["Full Paper Status"] = status

        else:
            # DOI fallback (MANDATORY attempt)
            # Take DOI from the paper metadata already stored in merged (any one record is fine)
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
    print(f"- {MONGO_DB}.{MONGO_SPMS}  (canonical SPM master)")
    print(f"- {MONGO_DB}.{MONGO_PAPERS} (papers + metadata + full text status)")
    print(f"- {MONGO_DB}.{MONGO_MENTIONS} (SPM ? synonym ? PMID mappings)")

    # OPTIONAL Excel snapshot (summary only, no full text)
    if EXPORT_EXCEL:
        out_rows = []
        for key, v in merged.items():
            v = dict(v)
            v["Synonyms"] = "; ".join(sorted(v["Synonyms"]))
            out_rows.append(v)

        out_df = pd.DataFrame(out_rows)
        out_df.to_excel(OUTPUT_FILE, index=False)
        print("\nExcel snapshot saved:", OUTPUT_FILE)


if __name__ == "__main__":
    main()
