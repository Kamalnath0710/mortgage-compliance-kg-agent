import json
import os
import pickle
import sqlite3
from pathlib import Path
from typing import Dict, List
import networkx as nx
from fastembed import TextEmbedding
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from app.regulatory_corpus import REGULATORY_DOCUMENTS
from app.schemas import RegulatorySection

DATA_DIR = Path("storage")
DB_PATH = DATA_DIR / "compliance_store.db"
QDRANT_PATH = DATA_DIR / "qdrant_local"
GRAPH_PATH = DATA_DIR / "knowledge_graph.gpickle"


def init_sqlite() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS source_sections (
            section_id TEXT PRIMARY KEY,
            agency TEXT,
            program TEXT,
            title TEXT,
            effective_date TEXT,
            superseded_by TEXT,
            overlay_priority INTEGER,
            verbatim_text TEXT,
            cross_references TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_logs (
            audit_id TEXT PRIMARY KEY,
            timestamp TEXT,
            loan_id TEXT,
            status TEXT,
            payload_json TEXT,
            assessment_json TEXT,
            hitl_override_status TEXT,
            hitl_reviewer TEXT,
            hitl_notes TEXT
        )
        """
    )
    conn.commit()
    return conn


def run_offline_ingestion() -> Dict[str, int]:
    """
    Executes Part A (Stages 1 -> 2A & 2B -> 3):
    1. Ingests regulatory sections
    2. Stores verbatim text & temporal metadata in SQLite Source Store
    3. Builds NetworkX Knowledge Graph (SPO triplets + cross-references + supersedes edges)
    4. Embeds sections with FastEmbed (CPU ONNX) into local Qdrant
    """
    conn = init_sqlite()
    kg = nx.DiGraph()

    embedder = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
    qdrant = QdrantClient(path=str(QDRANT_PATH))

    collection_name = "mortgage_guidelines"
    if qdrant.collection_exists(collection_name):
        qdrant.delete_collection(collection_name)

    qdrant.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(size=384, distance=Distance.COSINE),
    )

    texts = [
        f"{doc.agency} {doc.section_id} - {doc.title}: {doc.verbatim_text}"
        for doc in REGULATORY_DOCUMENTS
    ]
    embeddings = list(embedder.embed(texts))

    points: List[PointStruct] = []
    for idx, (doc, vector) in enumerate(zip(REGULATORY_DOCUMENTS, embeddings), start=1):
        # Stage 2A & 3: Persist verbatim source text & temporal metadata
        conn.execute(
            """
            INSERT OR REPLACE INTO source_sections
            (section_id, agency, program, title, effective_date, superseded_by, overlay_priority, verbatim_text, cross_references)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                doc.section_id,
                doc.agency,
                doc.program,
                doc.title,
                doc.effective_date.isoformat(),
                doc.superseded_by,
                doc.overlay_priority,
                doc.verbatim_text,
                json.dumps(doc.cross_references),
            ),
        )

        # Stage 2B & 3: Build Knowledge Graph nodes & edges
        kg.add_node(
            doc.section_id,
            node_type="RegulatorySection",
            agency=doc.agency,
            title=doc.title,
            effective_date=doc.effective_date.isoformat(),
            superseded_by=doc.superseded_by,
            overlay_priority=doc.overlay_priority,
        )

        if doc.superseded_by:
            kg.add_edge(doc.superseded_by, doc.section_id, relation="SUPERSEDES")

        for ref in doc.cross_references:
            kg.add_edge(doc.section_id, ref, relation="CROSS_REFERENCES")

        for subj, pred, obj in doc.triplets:
            kg.add_node(subj, node_type="Entity")
            kg.add_node(obj, node_type="ValueOrEntity")
            kg.add_edge(subj, obj, relation=pred, source_section=doc.section_id)
            kg.add_edge(doc.section_id, subj, relation="DEFINES_RULE_FOR")

        # Stage 3: Vector DB Point with payload metadata
        points.append(
            PointStruct(
                id=idx,
                vector=vector.tolist(),
                payload={
                    "section_id": doc.section_id,
                    "agency": doc.agency,
                    "program": doc.program,
                    "title": doc.title,
                    "effective_date": doc.effective_date.isoformat(),
                    "superseded_by": doc.superseded_by,
                    "overlay_priority": doc.overlay_priority,
                    "verbatim_text": doc.verbatim_text,
                },
            )
        )

    conn.commit()
    conn.close()

    qdrant.upsert(collection_name=collection_name, points=points)
    qdrant.close()

    with open(GRAPH_PATH, "wb") as f:
        pickle.dump(kg, f)

    return {
        "sections_ingested": len(REGULATORY_DOCUMENTS),
        "kg_nodes": kg.number_of_nodes(),
        "kg_edges": kg.number_of_edges(),
        "qdrant_vectors": len(points),
    }