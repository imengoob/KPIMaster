
/**
 * Hook pour utiliser le vrai assistant backend (RAG + LLM).
 *
 * Architecture :
 *
 * Frontend
 *    ↓
 * Backend
 *    ↓
 * Language Detection
 *    ↓
 * Intent Detection
 *    ↓
 * ChromaDB
 *    ↓
 * Gemini
 *    ↓
 * Answer
 *
 * IMPORTANT :
 * - Le frontend n'effectue aucune recherche vectorielle.
 * - Le frontend ne génère aucune réponse.
 * - Aucune conversation précédente n'est envoyée au backend.
 * - Chaque question est indépendante.
 */

import { useCallback, useState } from "react";
import { useProject } from "@/contexts/ProjectContext";

const API_BASE = (
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000"
).replace(/\/$/, "");

// ============================================================
// TYPES
// ============================================================

interface AssistantMessage {
  role: "user" | "assistant";
  content: string;
  sources?: string[];
  confidence?: number;
}

interface AssistantResponse {
  answer: string;
  sources?: string[];
  confidence?: number;
  intent?: string;
  language?: string;
  no_data?: boolean;
}

// ============================================================
// AUTH
// ============================================================

function authHeaders(): HeadersInit {
  const token = localStorage.getItem("kpimaster.authToken");

  if (!token) {
    return {};
  }

  return {
    Authorization: `Bearer ${token}`,
  };
}

// ============================================================
// ERROR MESSAGE
// ============================================================

async function getErrorMessage(
  response: Response,
): Promise<string> {
  const defaultMessage = `Erreur serveur (${response.status})`;

  try {
    const text = await response.text();

    if (!text) {
      return defaultMessage;
    }

    try {
      const json = JSON.parse(text);

      if (typeof json.detail === "string") {
        return json.detail;
      }

      if (typeof json.message === "string") {
        return json.message;
      }

      if (typeof json.error === "string") {
        return json.error;
      }

      if (json.detail) {
        return JSON.stringify(json.detail);
      }

      return text;
    } catch {
      return text;
    }
  } catch {
    return defaultMessage;
  }
}

// ============================================================
// HOOK
// ============================================================

export function useAssistant() {
  const [messages, setMessages] = useState<AssistantMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  const { currentProject } = useProject();

  /**
   * IMPORTANT :
   * On utilise uniquement l'ID du projet.
   *
   * Cela évite de recréer les callbacks lorsque
   * l'objet currentProject change de référence.
   */
  const projectId = currentProject?.id;

  // ==========================================================
  // SEND MESSAGE
  // ==========================================================

  const sendMessage = useCallback(
    async (
      question: string,
      language: "auto" | "fr" | "en" = "auto",
    ): Promise<AssistantResponse> => {
      if (!projectId) {
        throw new Error("Aucun projet sélectionné.");
      }

      const cleanQuestion = question.trim();

      if (!cleanQuestion) {
        throw new Error("La question ne peut pas être vide.");
      }

      setIsLoading(true);

      // ------------------------------------------------------
      // UI uniquement
      //
      // IMPORTANT :
      // Les anciens messages ne sont PAS envoyés au backend.
      // ------------------------------------------------------

      setMessages((prev) => [
        ...prev,
        {
          role: "user",
          content: cleanQuestion,
        },
      ]);

      try {
        const response = await fetch(
          `${API_BASE}/api/v1/assistant/ask`,
          {
            method: "POST",

            headers: {
              "Content-Type": "application/json",
              ...authHeaders(),
            },

            body: JSON.stringify({
              question: cleanQuestion,
              project_id: projectId,
              language,
            }),
          },
        );

        // ----------------------------------------------------
        // AUTH
        // ----------------------------------------------------

        if (response.status === 401) {
          throw new Error(
            "Session expirée. Veuillez vous reconnecter.",
          );
        }

        // ----------------------------------------------------
        // HTTP ERROR
        // ----------------------------------------------------

        if (!response.ok) {
          const errorMessage =
            await getErrorMessage(response);

          throw new Error(errorMessage);
        }

        // ----------------------------------------------------
        // JSON
        // ----------------------------------------------------

        const data: AssistantResponse =
          await response.json();

        if (
          !data ||
          typeof data.answer !== "string"
        ) {
          throw new Error(
            "Le backend a retourné une réponse invalide.",
          );
        }

        // ----------------------------------------------------
        // ADD ASSISTANT MESSAGE
        // ----------------------------------------------------

        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: data.answer,
            sources: data.sources,
            confidence: data.confidence,
          },
        ]);

        return data;
      } catch (error) {
        const errorMessage =
          error instanceof Error
            ? error.message
            : "Une erreur inconnue est survenue.";

        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: `⚠️ ${errorMessage}`,
          },
        ]);

        throw error;
      } finally {
        setIsLoading(false);
      }
    },
    [projectId],
  );

  // ==========================================================
  // INDEX PROJECT DATA
  // ==========================================================

  const indexProjectData = useCallback(
    async (data: {
      tickets: unknown[];
      blockers: unknown[];
      developers: unknown[];
      sprint?: unknown;
      kpis?: unknown;
      actions?: unknown[];
    }) => {
      if (!projectId) {
        throw new Error("Aucun projet sélectionné.");
      }

      const response = await fetch(
        `${API_BASE}/api/v1/assistant/index`,
        {
          method: "POST",

          headers: {
            "Content-Type": "application/json",
            ...authHeaders(),
          },

          body: JSON.stringify({
            project_id: projectId,
            ...data,
          }),
        },
      );

      // ------------------------------------------------------
      // AUTH
      // ------------------------------------------------------

      if (response.status === 401) {
        throw new Error(
          "Session expirée. Veuillez vous reconnecter.",
        );
      }

      // ------------------------------------------------------
      // ERROR
      // ------------------------------------------------------

      if (!response.ok) {
        const errorMessage =
          await getErrorMessage(response);

        throw new Error(errorMessage);
      }

      // ------------------------------------------------------
      // SUCCESS
      // ------------------------------------------------------

      return await response.json();
    },
    [projectId],
  );

  // ==========================================================
  // CLEAR CHAT
  // ==========================================================

  const clearMessages = useCallback(() => {
    setMessages([]);
  }, []);

  // ==========================================================
  // RETURN
  // ==========================================================

  return {
    messages,
    isLoading,
    sendMessage,
    indexProjectData,
    clearMessages,
  };
}
