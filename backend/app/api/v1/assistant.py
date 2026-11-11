
"""
Assistant API endpoint — real backend RAG (ChromaDB + Gemini).

Architecture:

    Question
        ↓
    Language
        ↓
    Intent
        ↓
    ChromaDB
        ↓
    Context
        ↓
    Gemini
        ↓
    Answer

IMPORTANT:
- No conversation history is sent to the backend.
- Every question is independent.
- Every question goes through ChromaDB and Gemini.
- The frontend sends only the current question.
- /stats exposes in-process RAG observability counters.
"""

from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from pydantic import BaseModel

from app.api.dependencies import get_current_user
from app.models.user import User
from app.services.rag_service import rag_service, rag_stats
from app.infrastructure.vector_store.chroma_store import chroma_store


router = APIRouter(tags=["AI Assistant"])


# ============================================================
# MODELS
# ============================================================


class AskRequest(BaseModel):
    """
    Request for the AI assistant.

    No conversation history is accepted.
    Each question is independent.
    """

    question: str
    project_id: int
    language: str = "auto"


class AskResponse(BaseModel):
    answer: str
    sources: list[str]
    confidence: float
    intent: str


class IndexRequest(BaseModel):
    project_id: int
    tickets: list[dict] = []
    blockers: list[dict] = []
    developers: list[dict] = []
    sprint: Optional[dict] = None
    kpis: Optional[dict] = None


class StatsResponse(BaseModel):
    total_questions: int
    no_data_count: int
    no_data_rate: float
    error_count: int
    avg_gemini_latency_ms: float
    questions_by_intent: dict[str, int]


# ============================================================
# ASK
# ============================================================


@router.post(
    "/ask",
    response_model=AskResponse,
)
async def ask_question(
    request: AskRequest,
    current_user: User = Depends(get_current_user),
) -> AskResponse:
    """
    Pose une question à l'assistant IA sur le projet.

    Chaque question est indépendante.

    Flux:

        question
            ↓
        language
            ↓
        intent
            ↓
        ChromaDB
            ↓
        context
            ↓
        Gemini
            ↓
        answer
    """

    try:

        # ----------------------------------------------------
        # DEBUG
        # ----------------------------------------------------

        print(
            "========== ASK DEBUG ==========",
            flush=True,
        )

        print(
            "QUESTION:",
            repr(request.question),
            flush=True,
        )

        print(
            "PROJECT_ID:",
            request.project_id,
            flush=True,
        )

        print(
            "LANGUAGE:",
            request.language,
            flush=True,
        )

        print(
            "HISTORY: DISABLED",
            flush=True,
        )

        # ----------------------------------------------------
        # RAG
        # ----------------------------------------------------

        result = await rag_service.answer(
            query=request.question,
            project_id=request.project_id,
            language=request.language,
        )

        # ----------------------------------------------------
        # DEBUG RESULT
        # ----------------------------------------------------

        print(
            "RAG ANSWER:",
            repr(result.get("answer")),
            flush=True,
        )

        print(
            "RAG INTENT:",
            result.get("intent"),
            flush=True,
        )

        print(
            "RAG CONFIDENCE:",
            result.get("confidence"),
            flush=True,
        )

        print(
            "RAG SOURCES:",
            result.get("sources"),
            flush=True,
        )

        print(
            "===============================",
            flush=True,
        )

        return AskResponse(**result)

    except Exception as exc:

        print(
            "========== ASK ERROR ==========",
            flush=True,
        )

        print(
            "ERROR:",
            repr(exc),
            flush=True,
        )

        print(
            "===============================",
            flush=True,
        )

        raise HTTPException(
            status_code=500,
            detail=f"Erreur RAG: {exc}",
        ) from exc


# ============================================================
# INDEX PROJECT DATA
# ============================================================


@router.post("/index")
async def index_project_data(
    request: IndexRequest,
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    Indexe ou ré-indexe les données du projet dans ChromaDB.
    """

    try:

        def _do_index() -> None:

            # ------------------------------------------------
            # DELETE OLD PROJECT DATA
            # ------------------------------------------------

            chroma_store.delete_project_data(
                request.project_id
            )

            # ------------------------------------------------
            # TICKETS
            # ------------------------------------------------

            chroma_store.add_tickets(
                request.tickets,
                request.project_id,
            )

            # ------------------------------------------------
            # BLOCKERS
            # ------------------------------------------------

            chroma_store.add_blockers(
                request.blockers,
                request.project_id,
            )

            # ------------------------------------------------
            # DEVELOPERS
            # ------------------------------------------------

            chroma_store.add_developers(
                request.developers,
                request.project_id,
            )

            # ------------------------------------------------
            # SPRINT
            # ------------------------------------------------

            if request.sprint:

                chroma_store.add_sprint(
                    request.sprint,
                    request.project_id,
                )

            # ------------------------------------------------
            # KPIS
            # ------------------------------------------------

            if request.kpis:

                chroma_store.add_kpis(
                    request.kpis,
                    request.project_id,
                )

        await asyncio.to_thread(
            _do_index
        )

        return {
            "status": "indexed",
            "project_id": request.project_id,
        }

    except Exception as exc:

        raise HTTPException(
            status_code=500,
            detail=f"Erreur d'indexation: {exc}",
        ) from exc


# ============================================================
# STATS
# ============================================================


@router.get(
    "/stats",
    response_model=StatsResponse,
)
async def get_assistant_stats(
    current_user: User = Depends(get_current_user),
) -> StatsResponse:
    """
    Retourne les statistiques du RAG.

    Les compteurs sont en mémoire et sont
    réinitialisés lors du redémarrage de l'API.
    """

    return StatsResponse(
        **rag_stats.snapshot()
    )


# ============================================================
# VOICE CHAT
# ============================================================


@router.post("/voice-chat")
async def voice_chat(
    audio: UploadFile = File(...),
    project_id: int = Form(...),
    language: str = Form("fr"),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    Chat vocal complet :

    audio
        ↓
    transcription Gemini
        ↓
    RAG
        ↓
    réponse texte
        ↓
    ElevenLabs
        ↓
    audio
    """

    try:

        from app.core.voice.synthesizer import synthesizer
        from app.core.voice.transcriber import transcriber

        # ----------------------------------------------------
        # READ AUDIO
        # ----------------------------------------------------

        audio_bytes = await audio.read()

        # ----------------------------------------------------
        # TRANSCRIPTION
        # ----------------------------------------------------

        transcription = await transcriber.transcribe(
            audio_bytes,
            language=language,
        )

        # ----------------------------------------------------
        # RAG
        # ----------------------------------------------------

        result = await rag_service.answer(
            query=transcription.text,
            project_id=project_id,
            language=language,
        )

        # ----------------------------------------------------
        # TEXT -> SPEECH
        # ----------------------------------------------------

        speech = await synthesizer.synthesize(
            result["answer"],
            language=language,
        )

        # ----------------------------------------------------
        # RESPONSE
        # ----------------------------------------------------

        return {
            "user_text": transcription.text,
            "ai_text": result["answer"],
            "audio_base64": synthesizer.to_base64(
                speech
            ),
            "sources": result["sources"],
            "confidence": result["confidence"],
        }

    except Exception as exc:

        raise HTTPException(
            status_code=500,
            detail=f"Erreur voice chat: {exc}",
        ) from exc
