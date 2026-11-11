"""
ChromaDB vector store for KPIMaster.

Handles:
- embeddings
- indexing
- semantic search
- exact retrieval for counts / aggregations

Requires:
    chromadb>=0.5,<0.6
"""

from __future__ import annotations

import json
import logging
import re
import zlib
from typing import Any

import chromadb
import httpx
from chromadb.config import Settings as ChromaSettings

from app.config import settings

logger = logging.getLogger(__name__)


# ============================================================================
# GEMINI EMBEDDING API
# ============================================================================

GEMINI_EMBED_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "text-embedding-004:batchEmbedContents"
)


# ============================================================================
# DETERMINISTIC HASHING EMBEDDING
# ============================================================================

class HashingEmbeddingFunction:
    """
    Deterministic offline embedding function.

    This is a fallback when Gemini embeddings are unavailable.

    IMPORTANT:
    Do NOT use Python's built-in hash(), because its result can change
    between processes.

    zlib.crc32() is deterministic across processes and machines.
    """

    def __init__(self, dim: int = 384) -> None:
        self.dim = dim

    def name(self) -> str:
        return "kpimaster-hashing-embedding-v2"

    def __call__(self, input: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in input]

    def _embed_one(self, text: str) -> list[float]:
        vec = [0.0] * self.dim

        tokens = re.findall(
            r"[a-zA-Z0-9À-ÿ]+",
            text.lower(),
        )

        for token in tokens:
            index = zlib.crc32(
                token.encode("utf-8")
            ) % self.dim

            vec[index] += 1.0

        norm = sum(value * value for value in vec) ** 0.5

        if norm > 0:
            vec = [value / norm for value in vec]

        return vec


# ============================================================================
# GEMINI EMBEDDING FUNCTION
# ============================================================================

class GeminiEmbeddingFunction:
    """
    Gemini embedding function with a safe fallback.

    Behaviour:
    1. Try Gemini once.
    2. If Gemini works, use Gemini embeddings.
    3. If Gemini fails, permanently switch to deterministic hashing
       for this process.

    This prevents indexing with Gemini and searching with hashing,
    which would create incompatible vectors.
    """

    def __init__(self, dim: int = 384) -> None:
        self.dim = dim

        self.api_key = settings.gemini_api_key

        self._client = httpx.Client(
            timeout=15.0
        )

        self._fallback = HashingEmbeddingFunction(
            dim=dim
        )

        # None = not tested yet
        # True = Gemini available
        # False = use hashing
        self._use_gemini: bool | None = None

    def name(self) -> str:
        return "kpimaster-gemini-embedding-v1"

    def __call__(
        self,
        input: list[str],
    ) -> list[list[float]]:

        if self._use_gemini is None:
            self._use_gemini = self._healthcheck()

        if self._use_gemini:

            try:
                return self._embed_via_gemini(input)

            except Exception as exc:
                logger.warning(
                    "gemini_embedding_attempt_failed error=%s",
                    exc,
                )

                # Stop trying Gemini for this process.
                self._use_gemini = False

                return self._fallback(input)

        return self._fallback(input)

    def _healthcheck(self) -> bool:

        if not self.api_key:
            logger.warning(
                "gemini_embedding_api_key_missing_using_hashing"
            )
            return False

        try:

            self._embed_via_gemini(
                ["healthcheck"]
            )

            logger.info(
                "gemini_embedding_healthcheck_success"
            )

            return True

        except Exception as exc:

            logger.warning(
                "gemini_embeddings_healthcheck_failed_using_hashing "
                "error=%s",
                exc,
            )

            return False

    def _embed_via_gemini(
        self,
        texts: list[str],
    ) -> list[list[float]]:

        requests_payload = []

        for text in texts:

            requests_payload.append(
                {
                    "model": "models/text-embedding-004",
                    "content": {
                        "parts": [
                            {
                                "text": text[:2000]
                            }
                        ]
                    },
                    "task_type": "RETRIEVAL_DOCUMENT",
                }
            )

        response = self._client.post(
            GEMINI_EMBED_URL,
            headers={
                "x-goog-api-key": self.api_key,
                "Content-Type": "application/json",
            },
            json={
                "requests": requests_payload
            },
        )

        response.raise_for_status()

        data = response.json()

        embeddings = data.get(
            "embeddings",
            []
        )

        if len(embeddings) != len(texts):

            raise RuntimeError(
                f"Gemini returned "
                f"{len(embeddings)} embeddings "
                f"for {len(texts)} inputs"
            )

        return [
            embedding["values"]
            for embedding in embeddings
        ]


# ============================================================================
# CHROMA VECTOR STORE
# ============================================================================

class ChromaVectorStore:
    """
    ChromaDB wrapper for KPIMaster.

    Collections:
        tickets
        blockers
        developers
        sprints
        kpis
        actions

    Important:
    - search() is for semantic questions.
    - get_all() is for exact counts and aggregations.
    """

    ENTITY_TYPES = (
        "tickets",
        "blockers",
        "developers",
        "sprints",
        "kpis",
        "actions",
    )

    def __init__(
        self,
        persist_directory: str | None = None,
    ) -> None:

        self.persist_dir = (
            persist_directory
            or settings.chroma_persist_directory
        )

        # ------------------------------------------------------------------
        # Chroma persistent client
        # ------------------------------------------------------------------

        self.client = chromadb.PersistentClient(
            path=self.persist_dir,
            settings=ChromaSettings(
                anonymized_telemetry=False
            ),
        )

        # ------------------------------------------------------------------
        # Embedding function
        # ------------------------------------------------------------------

        self._embedding_function = (
            GeminiEmbeddingFunction()
        )

        # ------------------------------------------------------------------
        # Collections
        # ------------------------------------------------------------------

        self.collections = {}

        for entity_type in self.ENTITY_TYPES:

            self.collections[entity_type] = (
                self.client.get_or_create_collection(
                    name=entity_type,
                    embedding_function=(
                        self._embedding_function
                    ),
                )
            )

        logger.info(
            "chroma_store_initialized path=%s",
            self.persist_dir,
        )

    # =========================================================================
    # ID
    # =========================================================================

    def _generate_id(
        self,
        entity_type: str,
        entity_id: str,
    ) -> str:

        return f"{entity_type}_{entity_id}"

    # =========================================================================
    # INGESTION - TICKETS
    # =========================================================================

    def add_tickets(
        self,
        tickets: list[dict[str, Any]],
        project_id: int,
    ) -> None:

        if not tickets:
            return

        collection = self.collections["tickets"]

        ids = []
        documents = []
        metadatas = []

        for ticket in tickets:

            ticket_id = str(
                ticket.get("id", "")
            )

            ids.append(
                self._generate_id(
                    "ticket",
                    ticket_id,
                )
            )

            documents.append(
                self._ticket_to_text(ticket)
            )

            metadatas.append(
                {
                    "project_id": project_id,
                    "ticket_id": ticket_id,
                    "status": str(
                        ticket.get("status", "")
                    ),
                    "priority": str(
                        ticket.get("priority", "")
                    ),
                    "assignee_id": str(
                        ticket.get(
                            "assigneeId",
                            "",
                        )
                    ),
                    "quality_score": float(
                        ticket.get(
                            "qualityScore",
                            0,
                        )
                        or 0
                    ),
                    "raw_json": json.dumps(
                        ticket,
                        ensure_ascii=False,
                    ),
                }
            )

        collection.upsert(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
        )

        logger.info(
            "tickets_indexed project_id=%s count=%s",
            project_id,
            len(tickets),
        )

    # =========================================================================
    # INGESTION - BLOCKERS
    # =========================================================================

    def add_blockers(
        self,
        blockers: list[dict[str, Any]],
        project_id: int,
    ) -> None:

        if not blockers:
            return

        collection = self.collections["blockers"]

        ids = []
        documents = []
        metadatas = []

        for blocker in blockers:

            blocker_id = str(
                blocker.get("id", "")
            )

            ticket_id = str(
                blocker.get(
                    "ticketId",
                    "",
                )
            )

            ids.append(
                self._generate_id(
                    "blocker",
                    blocker_id,
                )
            )

            documents.append(
                self._blocker_to_text(
                    blocker
                )
            )

            metadatas.append(
                {
                    "project_id": project_id,
                    "blocker_id": blocker_id,
                    "ticket_id": ticket_id,
                    "escalation_level": int(
                        blocker.get(
                            "escalationLevel",
                            1,
                        )
                        or 1
                    ),
                    "stalled_hours": float(
                        blocker.get(
                            "stalledHours",
                            0,
                        )
                        or 0
                    ),
                    "raw_json": json.dumps(
                        blocker,
                        ensure_ascii=False,
                    ),
                }
            )

        collection.upsert(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
        )

        logger.info(
            "blockers_indexed project_id=%s count=%s",
            project_id,
            len(blockers),
        )

    # =========================================================================
    # INGESTION - DEVELOPERS
    # =========================================================================

    def add_developers(
        self,
        developers: list[dict[str, Any]],
        project_id: int,
    ) -> None:

        if not developers:
            return

        collection = self.collections["developers"]

        ids = []
        documents = []
        metadatas = []

        for developer in developers:

            developer_id = str(
                developer.get("id", "")
            )

            ids.append(
                self._generate_id(
                    "dev",
                    developer_id,
                )
            )

            documents.append(
                self._developer_to_text(
                    developer
                )
            )

            metadatas.append(
                {
                    "project_id": project_id,
                    "developer_id": developer_id,
                    "name": developer.get(
                        "name",
                        "",
                    ),
                    "role": developer.get(
                        "role",
                        "",
                    ),
                    "status": developer.get(
                        "status",
                        "",
                    ),
                    "raw_json": json.dumps(
                        developer,
                        ensure_ascii=False,
                    ),
                }
            )

        collection.upsert(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
        )

    # =========================================================================
    # INGESTION - SPRINT
    # =========================================================================

    def add_sprint(
        self,
        sprint: dict[str, Any],
        project_id: int,
    ) -> None:

        if not sprint:
            return

        collection = self.collections["sprints"]

        sprint_id = str(
            sprint.get("id", "")
        )

        collection.upsert(
            ids=[
                self._generate_id(
                    "sprint",
                    sprint_id,
                )
            ],
            documents=[
                self._sprint_to_text(
                    sprint
                )
            ],
            metadatas=[
                {
                    "project_id": project_id,
                    "sprint_id": sprint_id,
                    "name": sprint.get(
                        "name",
                        "",
                    ),
                    "raw_json": json.dumps(
                        sprint,
                        ensure_ascii=False,
                    ),
                }
            ],
        )

    # =========================================================================
    # INGESTION - KPIs
    # =========================================================================

    def add_kpis(
        self,
        kpis: dict[str, Any],
        project_id: int,
    ) -> None:

        if not kpis:
            return

        collection = self.collections["kpis"]

        collection.upsert(
            ids=[
                self._generate_id(
                    "kpi",
                    str(project_id),
                )
            ],
            documents=[
                self._kpis_to_text(kpis)
            ],
            metadatas=[
                {
                    "project_id": project_id,
                    "raw_json": json.dumps(
                        kpis,
                        ensure_ascii=False,
                    ),
                }
            ],
        )

    # =========================================================================
    # SEMANTIC SEARCH
    # =========================================================================

    def search(
        self,
        query: str,
        project_id: int,
        top_k: int = 20,
        entity_types: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Semantic search.

        IMPORTANT:
        This function should NOT be used for exact counts.

        Example:
            "How many tickets are blocked?"

        For this type of question use get_all().
        """

        types_to_search = (
            entity_types
            if entity_types
            else list(self.collections.keys())
        )

        all_results: list[
            dict[str, Any]
        ] = []

        for entity_type in types_to_search:

            collection = self.collections.get(
                entity_type
            )

            if collection is None:
                continue

            try:

                total_count = collection.count()

                if total_count == 0:
                    continue

                n_results = min(
                    top_k,
                    total_count,
                )

                results = collection.query(
                    query_texts=[query],
                    n_results=n_results,
                    where={
                        "project_id": project_id
                    },
                    include=[
                        "documents",
                        "metadatas",
                        "distances",
                    ],
                )

                documents = (
                    results.get(
                        "documents"
                    )
                    or [[]]
                )

                metadatas = (
                    results.get(
                        "metadatas"
                    )
                    or [[]]
                )

                distances = (
                    results.get(
                        "distances"
                    )
                    or [[]]
                )

                ids = (
                    results.get(
                        "ids"
                    )
                    or [[]]
                )

                if not documents:
                    continue

                docs = documents[0]
                metas = (
                    metadatas[0]
                    if metadatas
                    else []
                )
                dists = (
                    distances[0]
                    if distances
                    else []
                )
                result_ids = (
                    ids[0]
                    if ids
                    else []
                )

                for index, document in enumerate(
                    docs
                ):

                    metadata = (
                        metas[index]
                        if index < len(metas)
                        else {}
                    )

                    distance = (
                        dists[index]
                        if index < len(dists)
                        else None
                    )

                    record_id = (
                        result_ids[index]
                        if index < len(result_ids)
                        else ""
                    )

                    all_results.append(
                        {
                            "type": entity_type,
                            "content": document,
                            "text": document,
                            "metadata": metadata or {},
                            "distance": distance,
                            "id": record_id,
                        }
                    )

            except Exception as exc:

                logger.exception(
                    "chroma_search_collection_failed "
                    "collection=%s project_id=%s error=%s",
                    entity_type,
                    project_id,
                    exc,
                )

        # Lower distance = more relevant.
        all_results.sort(
            key=lambda item: (
                item["distance"]
                if item["distance"] is not None
                else 999
            )
        )

        return all_results[:top_k]

    # =========================================================================
    # EXACT RETRIEVAL
    # =========================================================================

    def get_all(
        self,
        entity_type: str,
        project_id: int,
    ) -> list[dict[str, Any]]:
        """
        Return ALL records for a project.

        This is the important function for:
        - total number of tickets
        - blocked ticket count
        - status breakdown
        - quality score counts
        - complete lists

        No semantic ranking.
        No top_k.
        No information loss.
        """

        collection = self.collections.get(
            entity_type
        )

        if collection is None:
            return []

        try:

            result = collection.get(
                where={
                    "project_id": project_id
                },
                include=[
                    "documents",
                    "metadatas",
                ],
            )

            documents = (
                result.get("documents")
                or []
            )

            metadatas = (
                result.get("metadatas")
                or []
            )

            ids = (
                result.get("ids")
                or []
            )

            records = []

            for index, document in enumerate(
                documents
            ):

                metadata = (
                    metadatas[index]
                    if index < len(metadatas)
                    else {}
                )

                record_id = (
                    ids[index]
                    if index < len(ids)
                    else ""
                )

                records.append(
                    {
                        "type": entity_type,
                        "content": document,
                        "text": document,
                        "metadata": metadata or {},
                        "distance": None,
                        "id": record_id,
                    }
                )

            return records

        except Exception as exc:

            logger.exception(
                "chroma_get_all_failed "
                "collection=%s project_id=%s error=%s",
                entity_type,
                project_id,
                exc,
            )

            return []

    # =========================================================================
    # DELETE PROJECT DATA
    # =========================================================================

    def delete_project_data(
        self,
        project_id: int,
    ) -> None:
        """
        Delete all indexed data for a project.
        """

        for collection_name, collection in (
            self.collections.items()
        ):

            try:

                collection.delete(
                    where={
                        "project_id": project_id
                    }
                )

                logger.info(
                    "chroma_project_data_deleted "
                    "collection=%s project_id=%s",
                    collection_name,
                    project_id,
                )

            except Exception as exc:

                logger.warning(
                    "chroma_delete_failed "
                    "collection=%s project_id=%s error=%s",
                    collection_name,
                    project_id,
                    exc,
                )

    # =========================================================================
    # TEXT FORMATTERS
    # =========================================================================

    def _ticket_to_text(
        self,
        ticket: dict,
    ) -> str:

        labels = ticket.get(
            "labels",
            [],
        )

        if not isinstance(labels, list):
            labels = []

        parts = [
            f"Ticket {ticket.get('id', '')}",
            str(
                ticket.get(
                    "title",
                    "",
                )
            ),
            f"Status: {ticket.get('status', '')}",
            f"Priority: {ticket.get('priority', '')}",
            (
                "Story points: "
                f"{ticket.get('storyPoints', 0)}"
            ),
            (
                "Quality score: "
                f"{ticket.get('qualityScore', 0)}%"
            ),
            (
                "Assignee: "
                f"{ticket.get('assigneeName', 'unassigned')}"
            ),
            (
                "Labels: "
                f"{', '.join(map(str, labels))}"
            ),
        ]

        return ". ".join(parts)

    def _blocker_to_text(
        self,
        blocker: dict,
    ) -> str:

        parts = [
            (
                "Blocker on ticket "
                f"{blocker.get('ticketId', '')}"
            ),
            str(
                blocker.get(
                    "title",
                    "",
                )
            ),
            (
                "Reason: "
                f"{blocker.get('reason', '')}"
            ),
            (
                "Impact: "
                f"{blocker.get('impact', '')}"
            ),
            (
                "Stalled for "
                f"{blocker.get('stalledHours', 0)} hours"
            ),
            (
                "Escalation level: "
                f"{blocker.get('escalationLevel', 1)}"
            ),
        ]

        return ". ".join(parts)

    def _developer_to_text(
        self,
        developer: dict,
    ) -> str:

        parts = [
            (
                "Developer "
                f"{developer.get('name', '')}"
            ),
            (
                "Role: "
                f"{developer.get('role', '')}"
            ),
            (
                "Status: "
                f"{developer.get('status', '')}"
            ),
            (
                "Completed: "
                f"{developer.get('completedPoints', 0)}"
                "/"
                f"{developer.get('totalPoints', 0)} points"
            ),
            (
                "Tickets done: "
                f"{developer.get('ticketsCompleted', 0)}"
                "/"
                f"{developer.get('ticketsTotal', 0)}"
            ),
            (
                "Estimation accuracy: "
                f"{developer.get('estimationAccuracy', 0)}%"
            ),
            (
                "Cycle time: "
                f"{developer.get('avgCycleTime', 0)} days"
            ),
        ]

        return ". ".join(parts)

    def _sprint_to_text(
        self,
        sprint: dict,
    ) -> str:

        parts = [
            (
                "Sprint "
                f"{sprint.get('name', '')}"
            ),
            (
                "From "
                f"{sprint.get('startDate', '')}"
                " to "
                f"{sprint.get('endDate', '')}"
            ),
            (
                f"{sprint.get('daysRemaining', 0)} "
                "days remaining"
            ),
            (
                "Progress: "
                f"{sprint.get('completedTickets', 0)}"
                "/"
                f"{sprint.get('totalTickets', 0)} tickets"
            ),
            (
                "In progress: "
                f"{sprint.get('inProgressTickets', 0)}"
            ),
            (
                "Blocked: "
                f"{sprint.get('blockedTickets', 0)}"
            ),
            (
                "Velocity: "
                f"{sprint.get('velocity', 0)}"
            ),
        ]

        return ". ".join(parts)

    def _kpis_to_text(
        self,
        kpis: dict,
    ) -> str:

        parts = [
            "Project KPIs"
        ]

        for key, label in (
            (
                "velocity",
                "Velocity",
            ),
            (
                "cycleTime",
                "Cycle time",
            ),
            (
                "leadTime",
                "Lead time",
            ),
            (
                "completionRate",
                "Completion rate",
            ),
            (
                "estimationAccuracy",
                "Estimation accuracy",
            ),
        ):

            if key in kpis:

                value = kpis[key]

                if isinstance(
                    value,
                    dict,
                ):
                    value = value.get(
                        "value",
                        "N/A",
                    )

                parts.append(
                    f"{label}: {value}"
                )

        return ". ".join(parts)


# ============================================================================
# SINGLETON
# ============================================================================

chroma_store = ChromaVectorStore()