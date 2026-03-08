const API_BASE =
  import.meta.env.VITE_API_BASE ||
  `${window.location.protocol}//${window.location.hostname}:8001`;

export interface LoginStep1Result {
  temp_token: string;
  requires_totp: boolean;
  setup_required: boolean;
  qr_image?: string;   // base64 PNG, present on first-time setup
  secret?: string;     // plain-text TOTP key for manual entry
}

export async function loginStep1Api(
  username: string,
  password: string
): Promise<LoginStep1Result> {
  const res = await fetch(`${API_BASE}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error((data as { detail?: string }).detail || "Invalid credentials");
  }
  return res.json();
}

export async function verifyTotpApi(
  temp_token: string,
  code: string
): Promise<string> {
  const res = await fetch(`${API_BASE}/api/auth/verify-totp`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ temp_token, code }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error((data as { detail?: string }).detail || "Invalid code");
  }
  const data = await res.json();
  return (data as { token: string }).token;
}
