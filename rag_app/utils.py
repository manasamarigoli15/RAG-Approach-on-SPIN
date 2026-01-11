import re

def clean_text(x: str) -> str:
    x = "" if x is None else str(x)
    x = re.sub(r"\s+", " ", x).strip()
    return x

def make_doc(spm, synonym, pmid, title, journal, year, abstract, full_paper):
    # Prefer Full Paper if it exists; else use Abstract; else use Title
    body = clean_text(full_paper)
    if not body:
        body = clean_text(abstract)
    if not body:
        body = clean_text(title)

    meta = {
        "SPM Name": clean_text(spm),
        "Synonyms": clean_text(synonym),
        "PMID": clean_text(pmid),
        "Title": clean_text(title),
        "Journal": clean_text(journal),
        "Year": clean_text(year),
        "PubMed URL": f"https://pubmed.ncbi.nlm.nih.gov/{clean_text(pmid)}/" if pmid else ""
    }

    # Store one text string per row/document
    text = (
        f"SPM Name: {meta['SPM Name']}\n"
        f"Synonyms: {meta['Synonyms']}\n"
        f"Title: {meta['Title']}\n"
        f"Journal: {meta['Journal']} ({meta['Year']})\n"
        f"PMID: {meta['PMID']}\n\n"
        f"Content:\n{body}"
    )

    return text, meta
