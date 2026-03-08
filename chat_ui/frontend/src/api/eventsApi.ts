import type { K8sEvent, EventStats } from "../types/events";

const API_BASE =
  import.meta.env.VITE_API_BASE ||
  `${window.location.protocol}//${window.location.hostname}:8001`;

function authHeaders(): HeadersInit {
  const token = localStorage.getItem("auth_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function fetchEvents(params: {
  severity?: string;
  namespace?: string;
  search?: string;
  limit?: number;
  offset?: number;
}): Promise<{ events: K8sEvent[]; total: number }> {
  const q = new URLSearchParams();
  if (params.severity && params.severity !== "all") q.set("severity", params.severity);
  if (params.namespace && params.namespace !== "all") q.set("namespace", params.namespace);
  if (params.search) q.set("search", params.search);
  if (params.limit) q.set("limit", String(params.limit));
  if (params.offset) q.set("offset", String(params.offset));

  const res = await fetch(`${API_BASE}/api/events?${q}`, {
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`Events API error: ${res.status}`);
  return res.json();
}

export async function fetchEventStats(): Promise<EventStats> {
  const res = await fetch(`${API_BASE}/api/events/stats`, {
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`Stats API error: ${res.status}`);
  return res.json();
}

export async function fetchEventById(eventId: string): Promise<K8sEvent> {
  const res = await fetch(`${API_BASE}/api/events/${eventId}`, {
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`Event API error: ${res.status}`);
  return res.json();
}

export function createEventSource(): EventSource {
  const token = localStorage.getItem("auth_token");
  return new EventSource(`${API_BASE}/api/events/stream?token=${token}`);
}
