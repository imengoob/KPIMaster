
"""
RAG (Retrieval-Augmented Generation) service.

Architecture:

    Question
        ↓
    Language Detection
        ↓
    Intent Detection
        ↓
    ChromaDB
        ↓
    Context
        ↓
    Gemini
        ↓
    Answer

IMPORTANT:
- Every question goes through ChromaDB and Gemini.
- Python does NOT generate the final answer.
- For ticket aggregate questions, all tickets are retrieved
  from ChromaDB and Gemini performs the counting from the context.
- Conversation history is NOT used.
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from typing import Any

import httpx

from app.config import settings
from app.infrastructure.vector_store.chroma_store import chroma_store


# ============================================================
# GEMINI
# ============================================================

GEMINI_API_URL = (
    "https://generativelanguage.googleapis.com"
    "/v1beta/models/{model}:generateContent"
)


# ============================================================
# RAG STATISTICS
# ============================================================

class RAGStats:

    def __init__(self) -> None:
        self.total_questions = 0
        self.no_data_count = 0
        self.error_count = 0

        self._gemini_latencies_ms: list[float] = []

        self.questions_by_intent: dict[str, int] = (
            defaultdict(int)
        )

    def record_question(self, intent: str) -> None:
        self.total_questions += 1
        self.questions_by_intent[intent] += 1

    def record_no_data(self) -> None:
        self.no_data_count += 1

    def record_error(self) -> None:
        self.error_count += 1

    def record_gemini_latency(self, ms: float) -> None:
        self._gemini_latencies_ms.append(ms)

        if len(self._gemini_latencies_ms) > 500:
            self._gemini_latencies_ms.pop(0)

    def snapshot(self) -> dict[str, Any]:

        if self._gemini_latencies_ms:
            avg_latency = (
                sum(self._gemini_latencies_ms)
                / len(self._gemini_latencies_ms)
            )
        else:
            avg_latency = 0.0

        no_data_rate = (
            self.no_data_count / self.total_questions
            if self.total_questions
            else 0.0
        )

        return {
            "total_questions": self.total_questions,
            "no_data_count": self.no_data_count,
            "no_data_rate": round(no_data_rate, 4),
            "error_count": self.error_count,
            "avg_gemini_latency_ms": round(
                avg_latency,
                1,
            ),
            "questions_by_intent": dict(
                self.questions_by_intent
            ),
        }


rag_stats = RAGStats()


# ============================================================
# RAG SERVICE
# ============================================================

class RAGService:

    def __init__(self) -> None:
        self.api_key = settings.gemini_api_key
        self.model = settings.gemini_model

    # ========================================================
    # LANGUAGE DETECTION
    # ========================================================

    def _detect_language(self, text: str) -> str:

        lower = text.lower().strip()

        french_words = (
            "quel",
            "quels",
            "quelle",
            "quelles",
            "combien",
            "où",
            "pourquoi",
            "comment",
            "donne",
            "donner",
            "quoi",
            "les",
            "des",
            "sont",
            "est",
            "du",
            "de",
            "la",
            "le",
            "une",
            "un",
            "avec",
            "dans",
            "pour",
            "sur",
            "ticket",
            "tickets",
            "bloqué",
            "bloqués",
            "bloquée",
            "bloquées",
            "terminé",
            "terminés",
            "complété",
            "complétés",
            "en cours",
            "pas commencé",
            "sprint actuel",
            "équipe",
            "progression",
            "avancement",
            "qualité",
            "développeur",
            "vélocité",
        )

        french_accents = set(
            "éèêëàâäùûüçîïô"
        )

        french_score = 0

        if any(
            char in french_accents
            for char in lower
        ):
            french_score += 2

        padded = f" {lower} "

        for word in french_words:
            if f" {word} " in padded:
                french_score += 1

        english_words = (
            "which",
            "what",
            "who",
            "where",
            "when",
            "why",
            "how",
            "how many",
            "how much",
            "give me",
            "show me",
            "tell me",
            "can you",
            "could you",
            "please",
            "the",
            "are",
            "is",
            "do",
            "does",
            "with",
            "from",
            "for",
            "in",
            "on",
            "ticket",
            "tickets",
            "blocked",
            "completed",
            "complete",
            "done",
            "in progress",
            "not started",
            "sprint",
            "progress",
            "quality",
            "developer",
            "developers",
            "team",
            "velocity",
        )

        english_score = 0

        for word in english_words:
            if f" {word} " in padded:
                english_score += 1

        if french_score > english_score:
            return "fr"

        return "en"

    # ========================================================
    # INTENT DETECTION
    # ========================================================

    def _detect_intent(self, query: str) -> str:

        q = query.lower().strip()

        # ----------------------------------------------------
        # BLOCKERS
        # ----------------------------------------------------

        blocker_phrases = (
            "what is blocking",
            "what's blocking",
            "what are the blockers",
            "explain the blocker",
            "explain blockers",
            "cause du blocage",
            "causes du blocage",
            "qu'est-ce qui bloque",
            "qu est ce qui bloque",
            "qu'est ce qui bloque",
            "raison du blocage",
            "raisons du blocage",
            "pourquoi le ticket",
            "pourquoi t-",
        )

        if any(
            phrase in q
            for phrase in blocker_phrases
        ):
            return "blockers"

        # ----------------------------------------------------
        # TICKETS
        # ----------------------------------------------------

        ticket_words = (
            "ticket",
            "tickets",
            "task",
            "tasks",
            "tâche",
            "tâches",
            "issue",
            "issues",
            "carte",
        )

        if any(
            word in q
            for word in ticket_words
        ):
            return "tickets"

        # ----------------------------------------------------
        # DEVELOPERS
        # ----------------------------------------------------

        developer_words = (
            "developer",
            "developers",
            "développeur",
            "développeurs",
            "dev",
            "équipe",
            "team",
            "assignee",
            "assignees",
            "membre",
            "membres",
        )

        if any(
            word in q
            for word in developer_words
        ):
            return "developers"

        # ----------------------------------------------------
        # SPRINT
        # ----------------------------------------------------

        sprint_words = (
            "sprint",
            "vélocité",
            "velocity",
            "burndown",
            "progression",
            "avancement",
            "sprint progress",
            "sprint velocity",
        )

        if any(
            word in q
            for word in sprint_words
        ):
            return "sprint"

        # ----------------------------------------------------
        # KPI
        # ----------------------------------------------------

        kpi_words = (
            "kpi",
            "kpis",
            "métrique",
            "métriques",
            "metric",
            "metrics",
            "performance",
        )

        if any(
            word in q
            for word in kpi_words
        ):
            return "kpis"

        # ----------------------------------------------------
        # ACTIONS
        # ----------------------------------------------------

        action_words = (
            "action",
            "actions",
            "recommendation",
            "recommendations",
            "recommandation",
            "recommandations",
            "todo",
            "à faire",
        )

        if any(
            word in q
            for word in action_words
        ):
            return "actions"

        return "general"

    # ========================================================
    # CHROMADB GET ALL
    # ========================================================

    async def _get_all(
        self,
        entity_type: str,
        project_id: int,
    ) -> list[dict[str, Any]]:

        return await asyncio.to_thread(
            chroma_store.get_all,
            entity_type,
            project_id,
        )

    # ========================================================
    # RETRIEVAL
    # ========================================================

    async def _retrieve(
        self,
        query: str,
        project_id: int,
        intent: str,
    ) -> list[dict[str, Any]]:

        print(
            f"[RAG] Retrieval intent={intent}",
            flush=True,
        )

        # ----------------------------------------------------
        # TICKETS
        # ----------------------------------------------------

        if intent == "tickets":

            results = await self._get_all(
                "tickets",
                project_id,
            )

            print(
                f"[RAG] ChromaDB tickets count="
                f"{len(results)}",
                flush=True,
            )

            for item in results:

                metadata = (
                    item.get("metadata")
                    or {}
                )

                print(
                    f"  ticket="
                    f"{metadata.get('ticket_id')} "
                    f"status="
                    f"{metadata.get('status')}",
                    flush=True,
                )

            return results

        # ----------------------------------------------------
        # BLOCKERS
        # ----------------------------------------------------

        if intent == "blockers":

            blockers, tickets = await asyncio.gather(

                self._get_all(
                    "blockers",
                    project_id,
                ),

                self._get_all(
                    "tickets",
                    project_id,
                ),
            )

            results = blockers + tickets

            print(
                f"[RAG] blockers={len(blockers)} "
                f"tickets={len(tickets)} "
                f"total={len(results)}",
                flush=True,
            )

            return results

        # ----------------------------------------------------
        # DEVELOPERS
        # ----------------------------------------------------

        if intent == "developers":

            results = await self._get_all(
                "developers",
                project_id,
            )

            print(
                f"[RAG] developers count="
                f"{len(results)}",
                flush=True,
            )

            return results

        # ----------------------------------------------------
        # SPRINT
        # ----------------------------------------------------

        if intent == "sprint":

            results = await self._get_all(
                "sprints",
                project_id,
            )

            print(
                f"[RAG] sprints count="
                f"{len(results)}",
                flush=True,
            )

            return results

        # ----------------------------------------------------
        # KPI
        # ----------------------------------------------------

        if intent == "kpis":

            kpis, sprints = await asyncio.gather(

                self._get_all(
                    "kpis",
                    project_id,
                ),

                self._get_all(
                    "sprints",
                    project_id,
                ),
            )

            results = kpis + sprints

            print(
                f"[RAG] kpis={len(kpis)} "
                f"sprints={len(sprints)} "
                f"total={len(results)}",
                flush=True,
            )

            return results

        # ----------------------------------------------------
        # ACTIONS
        # ----------------------------------------------------

        if intent == "actions":

            results = await self._get_all(
                "actions",
                project_id,
            )

            print(
                f"[RAG] actions count="
                f"{len(results)}",
                flush=True,
            )

            return results

        # ----------------------------------------------------
        # GENERAL
        # ----------------------------------------------------

        entity_types = [
            "tickets",
            "blockers",
            "developers",
            "sprints",
            "kpis",
            "actions",
        ]

        print(
            f"[RAG] semantic search "
            f"collections={entity_types}",
            flush=True,
        )

        results = await asyncio.to_thread(
            chroma_store.search,
            query,
            project_id,
            20,
            entity_types,
        )

        return results or []

    # ========================================================
    # CONTEXT
    # ========================================================

    def _build_context(
        self,
        results: list[dict[str, Any]],
    ) -> str:

        if not results:
            return ""

        parts: list[str] = []

        for index, item in enumerate(
            results,
            start=1,
        ):

            item_type = item.get(
                "type",
                "unknown",
            )

            metadata = (
                item.get("metadata")
                or {}
            )

            record_id = str(
                item.get("id", "")
            )

            content = (
                item.get("content")
                or item.get("text")
                or item.get("document")
                or ""
            )

            # ------------------------------------------------
            # TICKETS
            # ------------------------------------------------

            if item_type == "tickets":

                ticket_id = (
                    metadata.get("ticket_id")
                    or record_id
                )

                status = (
                    metadata.get("status")
                    or ""
                )

                priority = (
                    metadata.get("priority")
                    or ""
                )

                quality_score = (
                    metadata.get(
                        "quality_score"
                    )
                )

                assignee_id = (
                    metadata.get(
                        "assignee_id"
                    )
                    or ""
                )

                parts.append(
                    f"[TICKET {index}]\n"
                    f"ticket_id={ticket_id}\n"
                    f"status={status}\n"
                    f"priority={priority}\n"
                    f"quality_score={quality_score}\n"
                    f"assignee_id={assignee_id}\n"
                    f"content={content}"
                )

                continue

            # ------------------------------------------------
            # OTHER ENTITIES
            # ------------------------------------------------

            header = (
                f"[CONTEXT {index}]\n"
                f"type={item_type}"
            )

            if record_id:
                header += (
                    f"\nid={record_id}"
                )

            for key, value in metadata.items():

                if key == "raw_json":
                    continue

                header += (
                    f"\n{key}={value}"
                )

            parts.append(
                f"{header}\n"
                f"content={content}"
            )

        return "\n\n".join(parts)

    # ========================================================
    # SOURCES
    # ========================================================

    def _build_sources(
        self,
        results: list[dict[str, Any]],
    ) -> list[str]:

        sources: list[str] = []

        for result in results:

            metadata = (
                result.get("metadata")
                or {}
            )

            source = (
                metadata.get("ticket_id")
                or metadata.get("name")
                or result.get("id")
            )

            if source:

                source = str(source)

                if source not in sources:
                    sources.append(source)

        return sources

    # ========================================================
    # CONFIDENCE
    # ========================================================

    def _calculate_confidence(
        self,
        results: list[dict[str, Any]],
    ) -> float:

        if not results:
            return 0.0

        distances = [
            result.get("distance")
            for result in results
            if isinstance(
                result.get("distance"),
                (int, float),
            )
        ]

        if not distances:
            return 0.5

        average_distance = (
            sum(distances)
            / len(distances)
        )

        confidence = 1.0 / (
            1.0 + average_distance
        )

        return round(
            max(
                0.0,
                min(
                    1.0,
                    confidence,
                ),
            ),
            2,
        )

    # ========================================================
    # GEMINI RETRY DELAY
    # ========================================================

    def _get_retry_delay(
        self,
        response: httpx.Response,
        attempt: int,
    ) -> float:

        retry_after = response.headers.get(
            "Retry-After"
        )

        if retry_after:

            try:
                return min(
                    float(retry_after),
                    10.0,
                )
            except ValueError:
                pass

        try:

            data = response.json()

            details = (
                data
                .get("error", {})
                .get("details", [])
            )

            for detail in details:

                if (
                    detail.get("@type", "")
                    .endswith("RetryInfo")
                ):

                    retry_delay = detail.get(
                        "retryDelay",
                        "",
                    )

                    if retry_delay.endswith("s"):

                        seconds = float(
                            retry_delay[:-1]
                        )

                        return min(
                            seconds,
                            10.0,
                        )

        except Exception:
            pass

        return min(
            2 ** attempt,
            8.0,
        )

    # ========================================================
    # GEMINI QUOTA ERROR
    # ========================================================

    def _is_daily_quota_error(
        self,
        response: httpx.Response,
    ) -> bool:

        try:

            data = response.json()

            text = str(data)

            return (
                "PerDay" in text
                or "perDay" in text
                or "daily" in text.lower()
                or "GenerateRequestsPerDay"
                in text
            )

        except Exception:

            return False

    # ========================================================
    # GEMINI RESPONSE PARSER
    # ========================================================

    def _extract_gemini_answer(
        self,
        data: dict[str, Any],
    ) -> str:

        candidates = data.get(
            "candidates",
            [],
        )

        if not candidates:
            return ""

        candidate = candidates[0]

        parts = (
            candidate
            .get("content", {})
            .get("parts", [])
        )

        answer_parts: list[str] = []

        for part in parts:

            text = part.get("text")

            if isinstance(text, str):
                answer_parts.append(text)

        return "".join(
            answer_parts
        ).strip()

    # ========================================================
    # GEMINI GENERATION
    # ========================================================

    async def _generate(
        self,
        query: str,
        context: str,
        language: str,
        intent: str,
    ) -> str:

        if not self.api_key:

            raise RuntimeError(
                "GEMINI_API_KEY is not configured"
            )

        # ----------------------------------------------------
        # SYSTEM PROMPT
        # ----------------------------------------------------

        if language == "fr":

            system_prompt = """
Tu es KPIMaster AI, un assistant d'analyse
de performance de projet.

Tu dois répondre uniquement à partir des
DONNÉES DU PROJET fournies.

RÈGLES OBLIGATOIRES :

1. N'invente aucune information.

2. N'utilise aucune connaissance externe.

3. Les données du projet sont la seule
   source de vérité.

4. Pour une question de comptage, compte
   directement les enregistrements présents
   dans les DONNÉES DU PROJET.

5. Pour les tickets, les champs officiels sont :
   ticket_id
   status
   priority
   quality_score
   assignee_id

6. Le contenu détaillé du ticket peut être
   utilisé pour expliquer son titre,
   son problème ou son contexte.

7. Pour une question demandant tous les tickets,
   utilise tous les tickets présents.

8. Normalise les statuts en :
   completed
   in_progress
   not_started
   blocked

9. Si aucune donnée pertinente n'est présente,
   indique simplement que les données du projet
   ne permettent pas de répondre.

10. Ne complète jamais avec des informations
    provenant d'Internet ou de connaissances générales.

11. Donne directement la réponse.

12. Sois concis et professionnel.

13. Réponds uniquement en français.

14. Ne mentionne jamais :
    RAG
    ChromaDB
    embeddings
    vector database
    retrieval
    prompt
    traitement interne
    contexte interne
15. Pour toute question demandant une répartition des statuts,
    donne TOUJOURS les quatre statuts :
    completed
    in_progress
    not_started
    blocked

16. Ne supprime jamais un statut, même si son nombre est 0.

17. Avant de répondre à une question de comptage, vérifie silencieusement
    les nombres à partir des DONNÉES DU PROJET.

18. Pour une répartition des statuts, vérifie que les quatre nombres
    sont complets et cohérents avec le nombre total de tickets.

19. Ne termine jamais la réponse au milieu d'une phrase, d'un élément
    de liste ou d'un nombre.

20. Termine toujours la réponse complètement.

21. N'utilise pas les symboles Markdown tels que **, *, _, # ou `.
 Utilise uniquement du texte simple.
""".strip()

        else:

            system_prompt = """
You are KPIMaster AI, a project performance
analysis assistant.

You must answer only from the provided
PROJECT DATA.

MANDATORY RULES:

1. Never invent information.

2. Never use external knowledge.

3. The PROJECT DATA is the only source of truth.

4. For counting questions, count the records
   directly from the PROJECT DATA.

5. For tickets, the authoritative fields are:
   ticket_id
   status
   priority
   quality_score
   assignee_id

6. The ticket content can be used to explain
   its title, problem, or context.

7. For questions asking about all tickets,
   use all ticket records present.

8. Normalize ticket statuses as:
   completed
   in_progress
   not_started
   blocked

9. If no relevant project data is present,
   simply say that the project data does not
   provide enough information to answer.

10. Never use Internet or general knowledge
    to complete missing project information.

11. Give the direct answer first.

12. Be concise and professional.

13. Answer only in English.

14. Never mention:
    RAG
    ChromaDB
    embeddings
    vector database
    retrieval
    prompt
    internal processing
    internal context
15. For status breakdown questions, ALWAYS provide all four statuses:
    completed
    in_progress
    not_started
    blocked

16. Never omit a status, even when its count is 0.

17. Before answering a counting question, silently verify the counts
    against the PROJECT DATA.

18. For a status breakdown, make sure the four status counts are complete
    and consistent with the total number of tickets.

19. Never stop in the middle of a sentence, list item, number, or answer.

20. Return a complete answer before ending the response.

21. Do not use Markdown symbols such as **, *, _, #, or backticks.
Use plain text only.
    
""".strip()

        # ----------------------------------------------------
        # INTENT INSTRUCTION
        # ----------------------------------------------------

        intent_instruction = {

            "tickets": (
                "Focus on ticket IDs, statuses, "
                "priorities, quality scores and "
                "ticket details."
            ),

            "blockers": (
                "Focus on blockers and the related "
                "ticket information."
            ),

            "developers": (
                "Focus on developer information."
            ),

            "sprint": (
                "Focus on sprint information, "
                "progress and velocity."
            ),

            "kpis": (
                "Focus on KPI and sprint information."
            ),

            "actions": (
                "Focus on actions and recommendations."
            ),

            "general": (
                "Use only project information that "
                "is directly relevant to the question."
            ),

        }.get(
            intent,
            "Use only relevant project information.",
        )

        # ----------------------------------------------------
        # EMPTY CONTEXT
        # ----------------------------------------------------

        if context.strip():

            project_context = context

        else:

            project_context = (
                "NO RELEVANT PROJECT DATA WAS "
                "RETRIEVED FROM THE PROJECT DATABASE."
            )

        # ----------------------------------------------------
        # USER PROMPT
        # ----------------------------------------------------

        if language == "fr":

            user_prompt = f"""
{intent_instruction}

DONNÉES DU PROJET :

{project_context}

QUESTION ACTUELLE :

{query}

Réponds directement à la question en français.

Si la question demande un nombre,
une répartition ou une moyenne,
utilise les enregistrements présents
dans les DONNÉES DU PROJET.

Si les données du projet ne permettent
pas de répondre, indique-le clairement
sans inventer.
""".strip()

        else:

            user_prompt = f"""
{intent_instruction}

PROJECT DATA:

{project_context}

CURRENT QUESTION:

{query}

Answer directly in English.

If the question asks for a number,
breakdown, or average, use the records
present in the PROJECT DATA.

If the project data does not provide
enough information, clearly say so
without inventing anything.
""".strip()

        # ----------------------------------------------------
        # PAYLOAD
        # ----------------------------------------------------

        url = GEMINI_API_URL.format(
            model=self.model
        )

        payload = {

            "system_instruction": {
                "parts": [
                    {
                        "text": system_prompt
                    }
                ]
            },

            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": user_prompt
                        }
                    ],
                }
            ],

            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 1000,
            },
        }

        print(
            "[GEMINI] --------------------------------",
            flush=True,
        )

        print(
            f"[GEMINI] model={self.model}",
            flush=True,
        )

        print(
            f"[GEMINI] prompt_length="
            f"{len(user_prompt)}",
            flush=True,
        )

        print(
            f"[GEMINI] context_length="
            f"{len(context)}",
            flush=True,
        )

        print(
            "[GEMINI] history=DISABLED",
            flush=True,
        )

        # ----------------------------------------------------
        # REQUEST WITH RETRIES
        # ----------------------------------------------------

        max_attempts = 3

        async with httpx.AsyncClient(
            timeout=60.0
        ) as client:

            for attempt in range(max_attempts):

                try:

                    print(
                        f"[GEMINI] attempt="
                        f"{attempt + 1}/"
                        f"{max_attempts}",
                        flush=True,
                    )

                    response = await client.post(
                        url,
                        headers={
                            "x-goog-api-key": self.api_key,
                            "Content-Type": (
                                "application/json"
                            ),
                        },
                        json=payload,
                    )

                except httpx.HTTPError as exc:

                    print(
                        "[GEMINI] HTTP ERROR:",
                        flush=True,
                    )

                    print(
                        f"{type(exc).__name__}: {exc}",
                        flush=True,
                    )

                    if attempt >= max_attempts - 1:

                        raise RuntimeError(
                            "Gemini is temporarily "
                            "unavailable."
                        ) from exc

                    delay = min(
                        2 ** attempt,
                        5.0,
                    )

                    await asyncio.sleep(delay)

                    continue

                print(
                    f"[GEMINI] status_code="
                    f"{response.status_code}",
                    flush=True,
                )

                # ------------------------------------------------
                # SUCCESS
                # ------------------------------------------------

                if response.status_code == 200:

                    try:

                        data = response.json()

                    except Exception as exc:

                        print(
                            "[GEMINI] Invalid JSON response",
                            flush=True,
                        )

                        if attempt >= max_attempts - 1:

                            raise RuntimeError(
                                "Gemini returned an "
                                "invalid response."
                            ) from exc

                        await asyncio.sleep(1)

                        continue

                    answer = (
                        self._extract_gemini_answer(
                            data
                        )
                    )

                    if answer:

                        print(
                            f"[GEMINI] answer_length="
                            f"{len(answer)}",
                            flush=True,
                        )

                        print(
                            "[GEMINI] --------------------------------",
                            flush=True,
                        )

                        return answer

                    print(
                        "[GEMINI] EMPTY ANSWER",
                        flush=True,
                    )

                    print(
                        data,
                        flush=True,
                    )

                    if attempt >= max_attempts - 1:

                        raise RuntimeError(
                            "Gemini returned an empty answer."
                        )

                    await asyncio.sleep(1)

                    continue

                # ------------------------------------------------
                # 429 QUOTA
                # ------------------------------------------------

                if response.status_code == 429:

                    print(
                        "[GEMINI] 429 RESOURCE_EXHAUSTED",
                        flush=True,
                    )

                    print(
                        response.text,
                        flush=True,
                    )

                    if self._is_daily_quota_error(
                        response
                    ):

                        raise RuntimeError(
                            "Gemini daily quota exceeded "
                            f"for model '{self.model}'. "
                            "Please wait for the quota "
                            "to reset or use another "
                            "available Gemini model."
                        )

                    if attempt >= max_attempts - 1:

                        raise RuntimeError(
                            "Gemini rate limit exceeded. "
                            "Please try again shortly."
                        )

                    delay = self._get_retry_delay(
                        response,
                        attempt,
                    )

                    print(
                        f"[GEMINI] retry in "
                        f"{delay:.1f}s",
                        flush=True,
                    )

                    await asyncio.sleep(delay)

                    continue

                # ------------------------------------------------
                # 503 TEMPORARY UNAVAILABLE
                # ------------------------------------------------

                if response.status_code == 503:

                    print(
                        "[GEMINI] 503 UNAVAILABLE",
                        flush=True,
                    )

                    print(
                        response.text,
                        flush=True,
                    )

                    if attempt >= max_attempts - 1:

                        raise RuntimeError(
                            "Gemini is temporarily "
                            "unavailable. Please try again."
                        )

                    delay = self._get_retry_delay(
                        response,
                        attempt,
                    )

                    print(
                        f"[GEMINI] retry in "
                        f"{delay:.1f}s",
                        flush=True,
                    )

                    await asyncio.sleep(delay)

                    continue

                # ------------------------------------------------
                # OTHER ERRORS
                # ------------------------------------------------

                print(
                    "[GEMINI] ERROR RESPONSE:",
                    flush=True,
                )

                print(
                    response.text,
                    flush=True,
                )

                raise RuntimeError(
                    f"Gemini API error "
                    f"{response.status_code}: "
                    f"{response.text}"
                )

        raise RuntimeError(
            "Gemini generation failed."
        )

    # ========================================================
    # MAIN ANSWER
    # ========================================================

    async def answer(
        self,
        query: str,
        project_id: int,
        language: str = "auto",
    ) -> dict[str, Any]:

        start = time.monotonic()

        print(
            "\n"
            "================================================",
            flush=True,
        )

        print(
            f"[RAG] QUESTION={query!r}",
            flush=True,
        )

        print(
            f"[RAG] PROJECT_ID={project_id}",
            flush=True,
        )

        try:

            # ------------------------------------------------
            # 1. LANGUAGE
            # ------------------------------------------------

            resolved_language = (
                self._detect_language(query)
                if language == "auto"
                else (
                    "fr"
                    if language.lower() == "fr"
                    else "en"
                )
            )

            print(
                f"[RAG] language={resolved_language}",
                flush=True,
            )

            # ------------------------------------------------
            # 2. INTENT
            # ------------------------------------------------

            intent = self._detect_intent(
                query
            )

            print(
                f"[RAG] intent={intent}",
                flush=True,
            )

            rag_stats.record_question(
                intent
            )

            # ------------------------------------------------
            # 3. CHROMADB
            # ------------------------------------------------

            retrieval_start = time.monotonic()

            results = await self._retrieve(
                query=query,
                project_id=project_id,
                intent=intent,
            )

            retrieval_ms = (
                time.monotonic()
                - retrieval_start
            ) * 1000

            print(
                f"[RAG] results={len(results)}",
                flush=True,
            )

            print(
                f"[RAG] retrieval_ms="
                f"{retrieval_ms:.2f}",
                flush=True,
            )

            # ------------------------------------------------
            # 4. CONTEXT
            #
            # IMPORTANT:
            # We DO NOT return here when there is no data.
            # Gemini must still receive the question.
            # ------------------------------------------------

            context = self._build_context(
                results
            )

            if not context:

                rag_stats.record_no_data()

                context = (
                    "NO RELEVANT PROJECT DATA "
                    "WAS RETRIEVED FROM CHROMADB."
                )

            print(
                f"[RAG] context_chars="
                f"{len(context)}",
                flush=True,
            )

            print(
                "[RAG] CONTEXT PREVIEW:",
                flush=True,
            )

            print(
                context[:6000],
                flush=True,
            )

            # ------------------------------------------------
            # 5. GEMINI
            # ------------------------------------------------

            gemini_start = time.monotonic()

            answer = await self._generate(
                query=query,
                context=context,
                language=resolved_language,
                intent=intent,
            )

            gemini_ms = (
                time.monotonic()
                - gemini_start
            ) * 1000

            rag_stats.record_gemini_latency(
                gemini_ms
            )

            print(
                f"[RAG] gemini_ms="
                f"{gemini_ms:.2f}",
                flush=True,
            )

            # ------------------------------------------------
            # 6. SOURCES
            # ------------------------------------------------

            sources = self._build_sources(
                results
            )

            # ------------------------------------------------
            # 7. CONFIDENCE
            # ------------------------------------------------

            confidence = (
                self._calculate_confidence(
                    results
                )
            )

            total_ms = (
                time.monotonic()
                - start
            ) * 1000

            print(
                f"[RAG] total_ms="
                f"{total_ms:.2f}",
                flush=True,
            )

            print(
                "[RAG] SUCCESS",
                flush=True,
            )

            print(
                "================================================\n",
                flush=True,
            )

            return {
                "answer": answer,
                "sources": sources,
                "confidence": confidence,
                "intent": intent,
                "language": resolved_language,
                "retrieval_ms": round(
                    retrieval_ms,
                    2,
                ),
                "generation_ms": round(
                    gemini_ms,
                    2,
                ),
                "total_ms": round(
                    total_ms,
                    2,
                ),
            }

        except Exception as exc:

            print(
                "[RAG] EXCEPTION:",
                flush=True,
            )

            print(
                f"{type(exc).__name__}: {exc}",
                flush=True,
            )

            rag_stats.record_error()

            print(
                "================================================\n",
                flush=True,
            )

            raise


# ============================================================
# GLOBAL INSTANCE
# ============================================================

rag_service = RAGService()
