import pandas as pd
import requests
import time
import re
from xml.etree import ElementTree as ET
from datetime import datetime


# FILES
INPUT_FILE = "Types_of_SPMs_with_synonyms.xlsx"

ts = datetime.now().strftime("%Y%m%d_%H%M%S")
OUTPUT_FILE = f"SPMs_PubMed_AllArticles_Abstract_FullPaper_{ts}.xlsx"
# OUTPUT_FILE = "SPMs_PubMed_AllArticles_Abstract_FullPaper.xlsx"

# INPUT columns
COL_NAME = "Name"
COL_PUBCHEM_SYNONYMS = "PubChem Synonyms"
COL_SPM_CLASS = "SPM Class"
COL_REFERENCE = "Reference"
COL_PUBCHEM_ID = "PubChem ID"
COL_PUBCHEM_LINK = "PubChem Link"


#NCBI Settings
NCBI_EMAIL = "manasamarigoli15@gmail.com"
NCBI_TOOL = "spm_pubmed"
#NCBI_API_KEY = ""

#REQS_PER_SEC = 10 if NCBI_API_KEY else 3
#SLEEP_SEC = 1.0 / REQS_PER_SEC

ESEARCH_PAGE = 5000
EFETCH_BATCH = 200


#Session 
session = requests.Session()
adapter = requests.adapters.HTTPAdapter(max_retries=3, pool_connections=20, pool_maxsize=20)
session.mount("https://", adapter)

def safe_get(url, params, timeout=60, tries=3):
    last_err = None
    for _ in range(tries):
        try:
            r = session.get(url, params=params, timeout=timeout)
            r.raise_for_status()
            return r
        except Exception as e:
            last_err = e
            time.sleep(1.0)
    raise last_err

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

def xml_text(el):
    """Safe XML text: handles nested tags."""
    if el is None:
        return ""
    return clean("".join(el.itertext()))


#Synonym filter
CAS_RE = re.compile(r"^\d{2,7}-\d{2}-\d$")
CHEBI_RE = re.compile(r"^CHEBI:\d+$", re.IGNORECASE)

def looks_like_junk_synonym(s):
    if not s:
        return True
    s = s.strip()

    if len(s) < 3:
        return True
    if len(s) > 60:              # huge IUPAC names -> noisy
        return True
    if CAS_RE.match(s):
        return True
    if CHEBI_RE.match(s):
        return True
    if s.isdigit():
        return True
    if sum(ch.isalpha() for ch in s) <= 1:
        return True
    return False

def parse_pubchem_synonyms(raw):
    raw = clean(raw)
    if not raw:
        return []
    parts = [clean(p) for p in raw.split(";")]
    parts = [p for p in parts if p and not looks_like_junk_synonym(p)]

    #Dedupe but keep order
    seen = set()
    out = []
    for p in parts:
        k = p.lower()
        if k not in seen:
            seen.add(k)
            out.append(p)
    return out


#PUBMED: ESEARCH all PMIDs for one term
def pubmed_esearch_all_pmids(term):
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    term = clean(term)

    # 1) first request: get count
    p0 = {
        "db": "pubmed",
        "term": f"{term}[Title/Abstract]",
        "retmode": "json",
        "retstart": 0,
        "retmax": 0,
        "email": NCBI_EMAIL,
        "tool": NCBI_TOOL,
    }
    if NCBI_API_KEY:
        p0["api_key"] = NCBI_API_KEY

    data0 = safe_get(base, p0, timeout=30).json()
    count = int(data0.get("esearchresult", {}).get("count", 0))
    if count == 0:
        return []

    # 2) page through all
    pmids = []
    for start in range(0, count, ESEARCH_PAGE):
        p = dict(p0)
        p["retstart"] = start
        p["retmax"] = ESEARCH_PAGE
        data = safe_get(base, p, timeout=30).json()
        pmids.extend(data.get("esearchresult", {}).get("idlist", []))
        time.sleep(SLEEP_SEC)

    # dedupe keep order
    seen = set()
    out = []
    for x in pmids:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


#PUBMED: EFETCH details
def pubmed_efetch_details(pmids):
    if not pmids:
        return []

    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    p = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "xml",
        "email": NCBI_EMAIL,
        "tool": NCBI_TOOL,
    }
    #if NCBI_API_KEY:
     #   p["api_key"] = NCBI_API_KEY

    xml_raw = safe_get(base, p, timeout=90).text

    try:
        root = ET.fromstring(xml_raw)
    except ET.ParseError:
        return []

    rows = []
    for art in root.findall(".//PubmedArticle"):
        pmid = clean(art.findtext(".//PMID"))
        title = xml_text(art.find(".//ArticleTitle"))
        journal = clean(art.findtext(".//Journal/Title"))
        year = clean(art.findtext(".//PubDate/Year"))

        abs_parts = []
        for ab in art.findall(".//Abstract/AbstractText"):
            t = xml_text(ab)
            if t:
                label = ab.attrib.get("Label")
                abs_parts.append(f"{label}: {t}" if label else t)
        abstract = "\n".join(abs_parts).strip()

        rows.append({
            "PMID": pmid,
            "Title": title,
            "Journal": journal,
            "Year": year,
            "Abstract": abstract,
            "PubMed URL": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else ""
        })
    return rows


#PMID -> PMCID 
def pmid_to_pmcid(pmid):
    if not pmid:
        return ""

    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/elink.fcgi"
    p = {
        "dbfrom": "pubmed",
        "db": "pmc",
        "id": pmid,
        "retmode": "xml",
        "email": NCBI_EMAIL,
        "tool": NCBI_TOOL,
    }
    #if NCBI_API_KEY:
    #   p["api_key"] = NCBI_API_KEY

    xml_raw = safe_get(base, p, timeout=60).text
    try:
        root = ET.fromstring(xml_raw)
    except ET.ParseError:
        return ""

    id_el = root.find(".//LinkSetDb/Link/Id")
    if id_el is None or not id_el.text:
        return ""

    num = id_el.text.strip()
    if num.upper().startswith("PMC"):
        return num.upper()
    if num.isdigit():
        return "PMC" + num
    return ""


# PMC full text 
def fetch_full_text_from_pmc(pmcid):
    if not pmcid:
        return ""

    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    p = {
        "db": "pmc",
        "id": pmcid,
        "retmode": "xml",
        "email": NCBI_EMAIL,
        "tool": NCBI_TOOL,
    }
    #if NCBI_API_KEY:
    #   p["api_key"] = NCBI_API_KEY

    xml_raw = safe_get(base, p, timeout=120).text

    #Strip XML tags -> big plain text
    txt = re.sub(r"<[^>]+>", " ", xml_raw)
    txt = re.sub(r"\s+", " ", txt).strip()
    return txt


# MAIN
df = pd.read_excel(INPUT_FILE)

#Ensure cols exist (so it never crashes)
for c in [COL_NAME, COL_PUBCHEM_SYNONYMS, COL_SPM_CLASS, COL_REFERENCE, COL_PUBCHEM_ID, COL_PUBCHEM_LINK]:
    if c not in df.columns:
        df[c] = ""

#Store one row per (Name, PMID)
merged = {}

for idx, row in df.iterrows():
    name = clean(row.get(COL_NAME, ""))
    if not name:
        continue

    spm_class = clean(row.get(COL_SPM_CLASS, ""))
    reference = clean(row.get(COL_REFERENCE, ""))
    pubchem_id = clean(row.get(COL_PUBCHEM_ID, ""))
    pubchem_link = clean(row.get(COL_PUBCHEM_LINK, ""))
    pubchem_syn_raw = clean(row.get(COL_PUBCHEM_SYNONYMS, ""))

    syns = parse_pubchem_synonyms(pubchem_syn_raw)

    #Search each term separately + track which term matched
    search_terms = [name] + [s for s in syns if s.lower() != name.lower()]

    print(f"\n[{idx+1}/{len(df)}] {name} | search terms = {len(search_terms)}")

    for term in search_terms:
        term = clean(term)
        if not term:
            continue

        try:
            pmids = pubmed_esearch_all_pmids(term)
        except Exception as e:
            print(f"  ESEARCH failed term='{term}': {e}")
            continue

        if not pmids:
            continue

        #Fetch metadata in efetch batches
        for start in range(0, len(pmids), EFETCH_BATCH):
            batch = pmids[start:start + EFETCH_BATCH]

            try:
                details = pubmed_efetch_details(batch)
            except Exception as e:
                print(f"  EFETCH failed term='{term}' batch={start}: {e}")
                continue

            for art in details:
                pmid = clean(art.get("PMID", ""))
                if not pmid:
                    continue

                key = (name, pmid)
                if key not in merged:
                    merged[key] = {
                        "Name": name,
                        "Synonyms": set([term]),
                        "SPM Class": spm_class,
                        "Reference": reference,
                        "PubChem ID": pubchem_id,
                        "PubChem Link": pubchem_link,
                        "Downloaded": "3D",  
                        "PubChem Synonyms": pubchem_syn_raw,
                        "PMID": pmid,
                        "PMCID": "",
                        "Title": art.get("Title", ""),
                        "Journal": art.get("Journal", ""),
                        "Year": art.get("Year", ""),
                        "Abstract": art.get("Abstract", ""),
                        "PubMed URL": art.get("PubMed URL", ""),
                        "Full Paper": "",
                        "Full Paper Status": "NO_PMCID"
                    }
                else:
                    merged[key]["Synonyms"].add(term)

            time.sleep(SLEEP_SEC)

print("\nCollected rows:", len(merged))

#Now fetch PMCID + full paper
print("\nFetching PMCID + full papers (PMC only)...")
for i, rec in enumerate(merged.values(), start=1):
    pmid = rec["PMID"]

    try:
        pmcid = pmid_to_pmcid(pmid)
    except Exception:
        pmcid = ""

    if not pmcid:
        rec["PMCID"] = ""
        rec["Full Paper"] = ""
        rec["Full Paper Status"] = "NO_PMCID"
    else:
        rec["PMCID"] = pmcid
        try:
            txt = fetch_full_text_from_pmc(pmcid)
            rec["Full Paper"] = txt
            rec["Full Paper Status"] = "OK" if txt else "FETCH_ERROR"
        except Exception:
            rec["Full Paper"] = ""
            rec["Full Paper Status"] = "FETCH_ERROR"

    if i % 200 == 0:
        print(f"  processed {i}/{len(merged)}")
    time.sleep(SLEEP_SEC)

#Final dataframe
final_rows = []
for rec in merged.values():
    rec["Synonyms"] = "; ".join(sorted(rec["Synonyms"]))
    final_rows.append(rec)

out_df = pd.DataFrame(final_rows)

final_cols = [
    "Name", "Synonyms", "SPM Class", "Reference", "PubChem ID", "PubChem Link",
    "Downloaded", "PubChem Synonyms",
    "PMID", "PMCID", "Title", "Journal", "Year", "Abstract", "PubMed URL",
    "Full Paper", "Full Paper Status"
]

for c in final_cols:
    if c not in out_df.columns:
        out_df[c] = ""

out_df = out_df[final_cols]
out_df.to_excel(OUTPUT_FILE, index=False)

print("\nDONE. Saved:", OUTPUT_FILE)
