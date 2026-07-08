import { useCallback, useRef, useState } from "react";
import type { AgentType } from "@/types/chat";
import type { WorkflowNode, WorkflowStatus } from "@/types/dashboard";
import { agentWorkflows, defaultWorkflow } from "@/mock/workflow";

const API_BASE = "";

/** Map backend TaskStatus string → frontend WorkflowStatus */
function toWorkflowStatus(s: string): WorkflowStatus {
  switch (s) {
    case "COMPLETED": return "success";
    case "FAILED": case "TIMEOUT": case "CANCELLED": return "failed";
    default: return "running";
  }
}

/** Format milliseconds to human-readable string */
function fmtMs(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

/** Format unix timestamp to HH:MM:SS.mmm */
function fmtTime(ts: number | null | undefined): string {
  if (!ts) return "--";
  const d = new Date(ts * 1000);
  return d.toISOString().slice(11, 23);
}

interface SSEEvent {
  type: string;
  task_id?: string;
  skill?: string;
  status?: string;
  duration_ms?: number;
  started_at?: number;
  finished_at?: number;
  error?: string;
  workflow_id?: string;
}

export function useWorkflowStream() {
  const [nodes, setNodes] = useState<WorkflowNode[]>(defaultWorkflow);
  const [isRunning, setIsRunning] = useState(false);
  const [answer, setAnswer] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const startWorkflow = useCallback(async (query: string, agentType: AgentType) => {
    // Abort previous run
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    // Start with mock template — all pending
    const template = agentWorkflows[agentType] ?? defaultWorkflow;
    setNodes(template.map(n => ({ ...n, status: "pending" as WorkflowStatus })));
    setIsRunning(true);
    setAnswer(null);

    try {
      const res = await fetch(`${API_BASE}/api/workflow/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query }),
        signal: controller.signal,
      });

      if (!res.ok || !res.body) {
        console.warn("[Workflow SSE] request failed:", res.status);
        setIsRunning(false);
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const event: SSEEvent = JSON.parse(line.slice(6));
            handleEvent(event, setNodes, setAnswer);
          } catch {
            // skip malformed lines
          }
        }
      }
    } catch (err: any) {
      if (err.name !== "AbortError") {
        console.warn("[Workflow SSE] connection error:", err.message);
      }
    } finally {
      setIsRunning(false);
    }
  }, []);

  const cancelWorkflow = useCallback(() => {
    abortRef.current?.abort();
    setIsRunning(false);
  }, []);

  return { nodes, isRunning, answer, startWorkflow, cancelWorkflow };
}

function handleEvent(
  event: SSEEvent,
  setNodes: React.Dispatch<React.SetStateAction<WorkflowNode[]>>,
  setAnswer: (a: string | null) => void,
) {
  switch (event.type) {
    case "task_started": {
      const name = event.skill ?? event.task_id ?? "";
      const timestamp = fmtTime(event.started_at);
      setNodes(prev =>
        prev.map(n =>
          matchNode(n, event)
            ? { ...n, status: "running" as WorkflowStatus, startTime: timestamp }
            : n,
        ),
      );
      break;
    }

    case "task_completed": {
      const duration = fmtMs(event.duration_ms ?? 0);
      const startTime = fmtTime(event.started_at);
      const endTime = fmtTime(event.finished_at);
      setNodes(prev =>
        prev.map(n =>
          matchNode(n, event)
            ? { ...n, status: "success", duration, startTime, endTime }
            : n,
        ),
      );
      break;
    }

    case "task_failed": {
      setNodes(prev =>
        prev.map(n =>
          matchNode(n, event)
            ? { ...n, status: "failed", duration: "--" }
            : n,
        ),
      );
      break;
    }

    case "workflow_complete": {
      const ans = event.answer ?? event.outputs
        ? JSON.stringify(event.outputs ?? event.answer, null, 2)
        : `Workflow "${event.workflow_id}" completed.`;
      setAnswer(ans);
      break;
    }
  }
}

/** Check if a frontend node matches a backend SSE event.
 *  Matches on skill name (underscore → hyphen normalized). */
function matchNode(node: WorkflowNode, event: SSEEvent): boolean {
  const skill = (event.skill ?? event.task_id ?? "").replace(/_/g, "-");
  const taskId = (event.task_id ?? "").replace(/_\d+$/, "").replace(/_/g, "-");
  return node.id === skill || node.id === taskId || node.name.toLowerCase().replace(/\s+/g, "-") === skill;
}
