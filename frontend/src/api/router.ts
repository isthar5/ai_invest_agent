import type { AgentType } from "@/types/chat";

interface RouterResponse {
  workflow: AgentType;
}

const API_BASE = "";

/**
 * POST /api/router — classify query intent and return target workflow id.
 * Falls back to the provided agentType when the backend is unreachable.
 */
export async function classifyIntent(query: string, fallback: AgentType): Promise<AgentType> {
  try {
    const res = await fetch(`${API_BASE}/api/router`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
      // short timeout: router should be fast (no LLM call)
      signal: AbortSignal.timeout(3000),
    });

    if (!res.ok) {
      console.warn("[Router API] non-ok response:", res.status);
      return fallback;
    }

    const data: RouterResponse = await res.json();
    console.log("[Router API] classified:", query.slice(0, 40), "→", data.workflow);
    return data.workflow;
  } catch (err) {
    console.warn("[Router API] unreachable, using fallback:", fallback, err instanceof Error ? err.message : "");
    return fallback;
  }
}
