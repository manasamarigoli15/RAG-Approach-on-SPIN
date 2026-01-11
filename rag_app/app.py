import os
import pickle
from datetime import datetime

import faiss
import numpy as np
import streamlit as st
from dotenv import load_dotenv
from mistralai import Mistral
from sentence_transformers import SentenceTransformer


#load .env file containing MISTRAL_API_KEY
load_dotenv()

INDEX_DIR = "index_store"
EMBED_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

#Here limiting the sources retrieved from FAISS for each questions.
#FAISS uses cosine similarity to pick top 10 sources. 
#If we retrieve all matching sources from FAISS, the UI will crash and the LLM token limits will hit too. 
#Top few relevant chunks should work for getting good results.
TOP_K = 10


#Helpers for FAISS store
def load_store():
    #Building Index
    index_path = os.path.join(INDEX_DIR, "faiss.index")
    metas_path = os.path.join(INDEX_DIR, "metas.pkl")
    texts_path = os.path.join(INDEX_DIR, "texts.pkl")

    index = faiss.read_index(index_path)

    #metas = list of dicts (PMID, title, etc)
    #texts = list of chunks (strings)
    with open(metas_path, "rb") as f:
        metas = pickle.load(f)

    with open(texts_path, "rb") as f:
        texts = pickle.load(f)

    return index, metas, texts


def retrieve(query, embed_model, index, metas, texts, k=5):
    #Embed query -> search in FAISS
    q_emb = embed_model.encode(
        [query],
        convert_to_numpy=True,
        normalize_embeddings=True
    )

    scores, ids = index.search(q_emb, k)

    hits = []
    for score, row_id in zip(scores[0], ids[0]):
        if row_id == -1:
            continue
        hits.append((float(score), metas[row_id], texts[row_id]))
    return hits


def build_prompt(question, retrieved):
    #Build a context that the model is allowed to use
    #Add [1], [2], ... citations
    blocks = []
    for i, (score, meta, chunk) in enumerate(retrieved, start=1):
        title = meta.get("Title", "")
        pmid = meta.get("PMID", "")
        blocks.append(f"[{i}] PMID: {pmid} | {title}\n{chunk}")

    context = "\n\n".join(blocks)

    prompt = f"""
You are a scientific assistant.
Answer the question using ONLY the context.
If the context is not enough, say you don't know.
Cite sources like [1], [2], etc.

QUESTION:
{question}

CONTEXT:
{context}
""".strip()

    return prompt



# Streamlit setup
st.set_page_config(page_title="SPM RAG", layout="wide")
st.title("SPM RAG Pipeline")


#Get API key from .env
api_key = os.getenv("MISTRAL_API_KEY", "")
if not api_key:
    st.error("Missing MISTRAL_API_KEY in .env")
    st.stop()


@st.cache_resource
def init_everything():
    #Load embedding model once
    embed_model = SentenceTransformer(EMBED_MODEL_NAME)

    #Load FAISS store once
    index, metas, texts = load_store()

    #init Mistral client once
    llm = Mistral(api_key=api_key)

    return embed_model, index, metas, texts, llm


embed_model, index, metas, texts, llm = init_everything()


# Chat state (simple multi-chat)
if "chats" not in st.session_state:
    # chats dict looks like:{chat_id: {"title": "some title", "messages": [{"role": "user", ...}, ...]}}
    st.session_state.chats = {}

if "active_chat_id" not in st.session_state:
    st.session_state.active_chat_id = None


def new_chat():
    #Timestamp-based id is good enough for this app
    chat_id = f"chat_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    st.session_state.chats[chat_id] = {"title": "New chat", "messages": []}
    st.session_state.active_chat_id = chat_id


#First time load -> create a chat
if st.session_state.active_chat_id is None:
    new_chat()

active_chat = st.session_state.chats[st.session_state.active_chat_id]


# Sidebar: list of chats
with st.sidebar:
    st.title("💬 Chats")

    if st.button("➕ New chat", use_container_width=True):
        new_chat()

    st.divider()

    #Show latest chat first
    for chat_id, chat in list(st.session_state.chats.items())[::-1]:
        label = chat["title"] or "New chat"

        if st.button(label, key=f"select_{chat_id}", use_container_width=True):
            st.session_state.active_chat_id = chat_id
            st.rerun()

# Main: render messages
for msg in active_chat["messages"]:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

        #If assistant saved sources, show them (collapsed)
        if msg["role"] == "assistant" and msg.get("sources"):
            with st.expander("Sources used"):
                for i, s in enumerate(msg["sources"], start=1):
                    st.write(f"**[{i}] {s.get('Title','')}**")
                    st.write(f"- SPM: {s.get('SPM Name','')}")
                    st.write(f"- Synonyms matched: {s.get('Synonyms','')}")
                    st.write(f"- PMID: {s.get('PMID','')}")
                    st.write(f"- URL: {s.get('PubMed URL','')}")
                    st.write(f"- Similarity score: {s.get('score', 0):.4f}")
                    st.divider()

# User input -> retrieval -> answer
user_text = st.chat_input("Ask a question about SPMs...")

if user_text and user_text.strip():
    user_text = user_text.strip()

    #Store user message
    active_chat["messages"].append({"role": "user", "content": user_text})

    #Update chat title using the first user message
    if active_chat["title"] == "New chat":
        active_chat["title"] = (user_text[:35] + "...") if len(user_text) > 35 else user_text

    #Do retrieval
    with st.spinner("Retrieving relevant papers..."):
        retrieved = retrieve(user_text, embed_model, index, metas, texts, k=TOP_K)

    #Build prompt for the LLM
    prompt = build_prompt(user_text, retrieved)

    #Ask mistral for response
    with st.spinner("Generating answer with Mistral..."):
        resp = llm.chat.complete(
            model="mistral-large-latest",
            messages=[{"role": "user", "content": prompt}]
        )
        answer = resp.choices[0].message.content

    #Prepare sources for UI
    sources_for_ui = []
    for score, meta, _chunk in retrieved:
        m = dict(meta)
        m["score"] = score
        sources_for_ui.append(m)

    #Store assistant message
    active_chat["messages"].append({
        "role": "assistant",
        "content": answer,
        "sources": sources_for_ui
    })

    #Refresh UI so new messages show immediately
    st.rerun()
