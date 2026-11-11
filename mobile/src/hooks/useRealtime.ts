import { useEffect, useState } from "react";
import { getWebSocketBaseUrl } from "../config/env";

export type RealtimeStatus = "disabled" | "connecting" | "connected" | "closed" | "error";

interface UseRealtimeOptions {
  token: string | null;
  projectId: number | null | undefined;
  onMessage: () => void;
}

export function useRealtime({ token, projectId, onMessage }: UseRealtimeOptions): RealtimeStatus {
  const [status, setStatus] = useState<RealtimeStatus>("disabled");

  useEffect(() => {
    if (!token || !projectId) {
      setStatus("disabled");
      return;
    }

    const url = `${getWebSocketBaseUrl()}/api/v1/ws/projects/${projectId}?token=${encodeURIComponent(token)}`;
    setStatus("connecting");
    const ws = new WebSocket(url);

    ws.onopen = () => setStatus("connected");
    ws.onerror = () => setStatus("error");
    ws.onclose = () => setStatus("closed");
    ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(String(event.data)) as { type?: string };
        if (payload.type && payload.type !== "heartbeat" && payload.type !== "connection.established") {
          onMessage();
        }
      } catch {
        onMessage();
      }
    };

    return () => {
      ws.close();
    };
  }, [onMessage, projectId, token]);

  return status;
}
