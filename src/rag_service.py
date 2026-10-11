from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import chromadb
from sentence_transformers import SentenceTransformer

PROJECT_ROOT = Path(__file__).resolve().parents[1]

DOCUMENTS_DIRECTORY = PROJECT_ROOT / "data" / "documents"
CHROMA_DIRECTORY = PROJECT_ROOT / "data" / "processed" / "chroma_data"
LOG_FILE = PROJECT_ROOT / "data" / "processed" / "rag_queries.jsonl"

EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
GENERATION_VERSION = "extractive-grounded-v1"
DEFAULT_TENANT_ID = "TENANT-LOCAL"

PROMPT_INJECTION_PATTERNS = [
    r"ignore previous instructions",
    r"ignore all instructions",
    r"reveal system secrets",
    r"show the system prompt",
    r"execute this command",
    r"override system rules",
]

@dataclass
class DocumentChunk:
    chunk_id: str
    document_id: str
    title: str
    section: str
    version: str
    tenant_id: str
    source_file: str
    content: str
    contains_prompt_injection: bool = False

def contains_prompt_injection(text: str) -> bool:
    lower_text = text.lower()

    return any(
        re.search(pattern, lower_text)
        for pattern in PROMPT_INJECTION_PATTERNS
    )

def parse_front_matter(
    content: str,
) -> tuple[dict[str, str], str]:
    if not content.startswith("---"):
        return {}, content

    parts = content.split("---", 2)

    if len(parts) != 3:
        return {}, content

    metadata_text = parts[1].strip()
    document_text = parts[2].strip()

    metadata: dict[str, str] = {}

    for line in metadata_text.splitlines():
        if ":" not in line:
            continue

        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip()

    return metadata, document_text

def split_into_chunks(
    file_path: Path,
) -> list[DocumentChunk]:
    content = file_path.read_text(encoding="utf-8")

    metadata, document_text = parse_front_matter(content)

    document_id = metadata.get(
        "document_id",
        file_path.stem.upper(),
    )

    title = metadata.get(
        "title",
        file_path.stem,
    )

    version = metadata.get("version", "v1")
    tenant_id = metadata.get(
        "tenant_id",
        DEFAULT_TENANT_ID,
    )

    chunks: list[DocumentChunk] = []
    current_section = "General"
    chunk_number = 1
    paragraph_buffer: list[str] = []

    def add_buffered_chunk() -> None:
        nonlocal chunk_number

        if not paragraph_buffer:
            return

        text = " ".join(paragraph_buffer).strip()

        if not text:
            paragraph_buffer.clear()
            return

        chunk_id = f"{document_id}-CHUNK-{chunk_number:03d}"

        chunks.append(
            DocumentChunk(
                chunk_id=chunk_id,
                document_id=document_id,
                title=title,
                section=current_section,
                version=version,
                tenant_id=tenant_id,
                source_file=file_path.name,
                content=text,
                contains_prompt_injection=contains_prompt_injection(
                    text
                ),
            )
        )

        chunk_number += 1
        paragraph_buffer.clear()

    for line in document_text.splitlines():
        stripped_line = line.strip()

        if stripped_line.startswith("## "):
            add_buffered_chunk()
            current_section = stripped_line[3:].strip()
            continue

        if stripped_line.startswith("# "):
            continue

        if not stripped_line:
            add_buffered_chunk()
            continue

        paragraph_buffer.append(stripped_line)

    add_buffered_chunk()

    return chunks

def load_all_chunks(
    documents_directory: Path,
) -> list[DocumentChunk]:
    chunks: list[DocumentChunk] = []

    for file_path in sorted(documents_directory.glob("*.md")):
        chunks.extend(split_into_chunks(file_path))

    return chunks

def get_collection() -> Any:
    CHROMA_DIRECTORY.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(
        path=str(CHROMA_DIRECTORY)
    )

    return client.get_or_create_collection(
        name="audit_knowledge",
        metadata={"hnsw:space": "cosine"},
    )

def create_embeddings(
    model: SentenceTransformer,
    texts: list[str],
) -> list[list[float]]:
    embeddings = model.encode(
        texts,
        normalize_embeddings=True,
    )

    return embeddings.tolist()

def index_documents() -> int:
    chunks = load_all_chunks(DOCUMENTS_DIRECTORY)

    if not chunks:
        raise ValueError(
            "No Markdown documents were found."
        )

    model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    collection = get_collection()

    texts = [chunk.content for chunk in chunks]
    embeddings = create_embeddings(model, texts)

    collection.upsert(
        ids=[chunk.chunk_id for chunk in chunks],
        documents=texts,
        embeddings=embeddings,
        metadatas=[
            {
                "document_id": chunk.document_id,
                "title": chunk.title,
                "section": chunk.section,
                "version": chunk.version,
                "tenant_id": chunk.tenant_id,
                "source_file": chunk.source_file,
                "contains_prompt_injection": (
                    chunk.contains_prompt_injection
                ),
            }
            for chunk in chunks
        ],
    )

    print(f"Indexed chunks: {len(chunks)}")
    print(f"Vector store: {CHROMA_DIRECTORY}")

    return len(chunks)

def retrieve_documents(
    question: str,
    tenant_id: str,
    top_k: int = 3,
) -> list[dict[str, Any]]:
    model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    collection = get_collection()

    if collection.count() == 0:
        return []

    question_embedding = create_embeddings(
        model,
        [question],
    )[0]

    result = collection.query(
        query_embeddings=[question_embedding],
        n_results=min(top_k * 2, collection.count()),
        where={"tenant_id": tenant_id},
        include=[
            "documents",
            "metadatas",
            "distances",
        ],
    )

    retrieved: list[dict[str, Any]] = []

    ids = result.get("ids", [[]])[0]
    documents = result.get("documents", [[]])[0]
    metadatas = result.get("metadatas", [[]])[0]
    distances = result.get("distances", [[]])[0]

    for chunk_id, document, metadata, distance in zip(
        ids,
        documents,
        metadatas,
        distances,
    ):
        relevance = max(0.0, 1.0 - float(distance))

        if metadata.get("contains_prompt_injection", False):
            continue

        retrieved.append(
            {
                "chunk_id": chunk_id,
                "document": document,
                "metadata": metadata,
                "distance": float(distance),
                "relevance": round(relevance, 4),
                "citation": (
                    f"[{metadata['document_id']}:"
                    f"{chunk_id}]"
                ),
            }
        )

    return retrieved[:top_k]

def select_relevant_sentences(
    question: str,
    document: str,
) -> str:
    question_words = set(
        re.findall(r"[a-zA-Z0-9]+", question.lower())
    )

    sentences = re.split(r"(?<=[.!?])\s+", document)

    scored_sentences: list[tuple[int, str]] = []

    for sentence in sentences:
        sentence_words = set(
            re.findall(r"[a-zA-Z0-9]+", sentence.lower())
        )

        score = len(question_words.intersection(sentence_words))
        scored_sentences.append((score, sentence))

    scored_sentences.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    selected = [
        sentence
        for score, sentence in scored_sentences[:2]
        if sentence.strip()
    ]

    return " ".join(selected)

def generate_grounded_response(
    question: str,
    retrieved_documents: list[dict[str, Any]],
    latency_ms: float,
) -> dict[str, Any]:
    minimum_relevance = 0.30

    relevant_documents = [
        item
        for item in retrieved_documents
        if item["relevance"] >= minimum_relevance
    ]

    correlation_id = f"query-{uuid.uuid4().hex[:12]}"

    if not relevant_documents:
        response = {
            "answer": (
                "Insufficient evidence. "
                "No relevant source was found."
            ),
            "evidence": [],
            "citations": [],
            "confidence": 0.0,
            "uncertainty": (
                "The knowledge base does not contain "
                "enough relevant information."
            ),
            "model_version": EMBEDDING_MODEL_NAME,
            "generation_version": GENERATION_VERSION,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "correlation_id": correlation_id,
            "latency_ms": round(latency_ms, 2),
        }

        return response

    evidence: list[dict[str, Any]] = []
    answer_lines: list[str] = []

    for item in relevant_documents:
        metadata = item["metadata"]

        selected_text = select_relevant_sentences(
            question,
            item["document"],
        )

        evidence.append(
            {
                "citation": item["citation"],
                "document_id": metadata["document_id"],
                "title": metadata["title"],
                "section": metadata["section"],
                "version": metadata["version"],
                "content": item["document"],
                "relevance": item["relevance"],
            }
        )

        answer_lines.append(
            f"- {selected_text} {item['citation']}"
        )

    best_relevance = max(
        item["relevance"]
        for item in relevant_documents
    )

    response = {
        "answer": (
            "Based only on the retrieved evidence:\n"
            + "\n".join(answer_lines)
        ),
        "evidence": evidence,
        "citations": [
            item["citation"]
            for item in relevant_documents
        ],
        "confidence": round(best_relevance, 4),
        "uncertainty": (
            "This is a grounded extractive response. "
            "Human review is required."
        ),
        "model_version": EMBEDDING_MODEL_NAME,
        "generation_version": GENERATION_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "correlation_id": correlation_id,
        "latency_ms": round(latency_ms, 2),
    }

    return response

def log_query(
    question: str,
    response: dict[str, Any],
) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    query_hash = hashlib.sha256(
        question.encode("utf-8")
    ).hexdigest()

    log_entry = {
        "correlation_id": response["correlation_id"],
        "query_hash": query_hash,
        "retrieved_document_ids": [
            evidence["document_id"]
            for evidence in response["evidence"]
        ],
        "model_version": response["model_version"],
        "generation_version": response["generation_version"],
        "latency_ms": response["latency_ms"],
        "timestamp": response["timestamp"],
    }

    with LOG_FILE.open("a", encoding="utf-8") as file:
        file.write(json.dumps(log_entry) + "\n")

def answer_question(
    question: str,
    tenant_id: str,
) -> dict[str, Any]:
    start_time = time.perf_counter()

    retrieved_documents = retrieve_documents(
        question=question,
        tenant_id=tenant_id,
        top_k=3,
    )

    latency_ms = (
        time.perf_counter() - start_time
    ) * 1000

    response = generate_grounded_response(
        question=question,
        retrieved_documents=retrieved_documents,
        latency_ms=latency_ms,
    )

    log_query(question, response)

    return response

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Local RAG knowledge assistant."
    )

    parser.add_argument(
        "--index",
        action="store_true",
        help="Index Markdown documents.",
    )

    parser.add_argument(
        "--question",
        help="Ask a question.",
    )

    parser.add_argument(
        "--tenant-id",
        default=DEFAULT_TENANT_ID,
    )

    args = parser.parse_args()

    if args.index:
        index_documents()

    if args.question:
        response = answer_question(
            question=args.question,
            tenant_id=args.tenant_id,
        )

        print(json.dumps(response, indent=2))

    if not args.index and not args.question:
        parser.print_help()

if __name__ == "__main__":
    main()
