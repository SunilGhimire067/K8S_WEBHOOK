import type { ChatMessage, Skill } from "../types/chat";

const API_BASE =
  import.meta.env.VITE_API_BASE ||
  `${window.location.protocol}//${window.location.hostname}:8001`;

function authHeaders(): HeadersInit {
  const token = localStorage.getItem("auth_token");
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

export interface StreamEvent {
  type: "progress" | "tool_start" | "message" | "token" | "done";
  level?: string;
  message?: string;
  current?: number;
  total?: number;
  tool?: string;
  args?: Record<string, unknown>;
  data?: ChatMessage;
  content?: string;
}

export async function sendChat(messages: ChatMessage[]): Promise<ChatMessage[]> {
  const response = await fetch(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({ messages }),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Chat API error ${response.status}: ${text}`);
  }
  const data = await response.json();
  return data.new_messages;
}

export async function sendChatStream(
  messages: ChatMessage[],
  onEvent: (event: StreamEvent) => void,
): Promise<void> {
  const response = await fetch(`${API_BASE}/api/chat/stream`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({ messages }),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Chat API error ${response.status}: ${text}`);
  }

  const reader = response.body?.getReader();
  if (!reader) throw new Error("No response body");

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    // Parse SSE lines
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (line.startsWith("data: ")) {
        try {
          const event: StreamEvent = JSON.parse(line.slice(6));
          onEvent(event);
        } catch {
          // skip malformed events
        }
      }
    }
  }
}

export async function fetchSkills(): Promise<Skill[]> {
  const token = localStorage.getItem("auth_token");
  const response = await fetch(`${API_BASE}/api/skills`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!response.ok) {
    throw new Error(`Skills API error: ${response.status}`);
  }
  const data = await response.json();
  return data.skills;
}
