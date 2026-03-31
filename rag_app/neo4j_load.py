from neo4j import GraphDatabase
from pymongo import MongoClient
import hashlib

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASS = "neo4j123"

MONGO_URI = "mongodb://localhost:27017"
DB = "spm_rag"
PAPERS = "newpapers"
# If you have interactions in another collection, use that:
INTERACTIONS = "interactions"  # change to your actual collection name

def evidence_id(pmid: str, spm: str, protein: str, text: str) -> str:
    raw = f"{pmid}||{spm}||{protein}||{text}".encode("utf-8", errors="ignore")
    return hashlib.md5(raw).hexdigest()

def main():
    mongo = MongoClient(MONGO_URI)[DB]
    papers_col = mongo[PAPERS]
    inter_col = mongo[INTERACTIONS]

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))

    # Helpful constraints/indexes
    with driver.session() as s:
        s.run("CREATE CONSTRAINT IF NOT EXISTS FOR (p:Paper) REQUIRE p.pmid IS UNIQUE")
        s.run("CREATE CONSTRAINT IF NOT EXISTS FOR (s:SPM) REQUIRE s.name IS UNIQUE")
        s.run("CREATE CONSTRAINT IF NOT EXISTS FOR (pr:Protein) REQUIRE pr.name IS UNIQUE")
        s.run("CREATE CONSTRAINT IF NOT EXISTS FOR (e:Evidence) REQUIRE e.id IS UNIQUE")

    with driver.session() as session:
        # 1) Load papers
        for p in papers_col.find({}, {"pmid": 1, "title": 1, "year": 1, "journal": 1, "pubmed_url": 1}):
            pmid = p.get("pmid")
            if not pmid:
                continue
            session.run(
                """
                MERGE (paper:Paper {pmid:$pmid})
                SET paper.title=$title,
                    paper.year=$year,
                    paper.journal=$journal,
                    paper.url=$url
                """,
                pmid=str(pmid),
                title=p.get("title",""),
                year=str(p.get("year","")),
                journal=p.get("journal",""),
                url=p.get("pubmed_url",""),
            )

        # 2) Load interactions (SPM–Protein–Paper + Evidence)
        # Expected doc structure in inter_col:
        # {spm_name, protein, pmid, evidence_text, relation_type?, score?}
        for it in inter_col.find({}):
            spm = it.get("SPM")
            protein = it.get("Protein")
            pmid = it.get("PMID")

            ev = it.get("Evidence") or []
            ev_text = " ".join(ev) if isinstance(ev, list) else str(ev)

            rel_type = it.get("Relation") or "INTERACTS_WITH"
            score = it.get("score")

            if not (spm and protein and pmid):
                continue

            eid = evidence_id(str(pmid), spm, protein, ev_text)

            session.run(
                """
                MERGE (s:SPM {name:$spm})
                MERGE (pr:Protein {name:$protein})
                MERGE (p:Paper {pmid:$pmid})

                MERGE (s)-[:MENTIONED_IN]->(p)
                MERGE (pr)-[:MENTIONED_IN]->(p)

                MERGE (s)-[r:INTERACTS_WITH {pmid:$pmid}]->(pr)
                SET r.relation_type=$rel_type
                FOREACH (_ IN CASE WHEN $score IS NULL THEN [] ELSE [1] END |
                    SET r.score = $score
                )

                MERGE (e:Evidence {id:$eid})
                SET e.text=$ev_text

                MERGE (e)-[:FROM_PAPER]->(p)
                MERGE (s)-[:EVIDENCED_BY]->(e)
                MERGE (pr)-[:EVIDENCED_BY]->(e)
                """,
                spm=spm,
                protein=protein,
                pmid=str(pmid),
                eid=eid,
                ev_text=ev_text,
                rel_type=rel_type,
                score=score,
            )

    driver.close()
    print("✅ Loaded graph into Neo4j")

if __name__ == "__main__":
    main()
