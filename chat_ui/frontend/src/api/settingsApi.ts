const API_BASE =
  import.meta.env.VITE_API_BASE ||
  `${window.location.protocol}//${window.location.hostname}:8001`;

function authHeaders(): HeadersInit {
  const token = localStorage.getItem("auth_token");
  return token ? { Authorization: `Bearer ${token}`, "Content-Type": "application/json" } : { "Content-Type": "application/json" };
}

export interface LlmSettings {
  litellm_base_url: string;
  litellm_model: string;
  litellm_api_key: string;
}

export async function fetchSettings(): Promise<LlmSettings> {
  const res = await fetch(`${API_BASE}/api/settings`, {
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`Settings API error: ${res.status}`);
  return res.json();
}

export async function updateSettings(settings: Partial<LlmSettings>): Promise<{ updated: string[] }> {
  const res = await fetch(`${API_BASE}/api/settings`, {
    method: "PUT",
    headers: authHeaders(),
    body: JSON.stringify(settings),
  });
  if (!res.ok) throw new Error(`Settings API error: ${res.status}`);
  return res.json();
}
