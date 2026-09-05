const API_ROOT = import.meta.env.VITE_API_URL ?? "/api/v1";

let accessToken: string | null = null;
let authScope: AuthScope | null = null;

export type AuthScope = {
  tenant_id: string;
  user_id: string;
  permissions: string[];
};

export type TokenResponse = {
  access_token: string | null;
  token_type: string;
  expires_in: number;
  csrf_token: string | null;
  mfa_required: boolean;
  mfa_challenge_token: string | null;
};

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export function setAccessToken(token: string | null) {
  accessToken = token;
}

export function getAuthScope() {
  return authScope;
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (response.ok) {
    return response.status === 204 ? (undefined as T) : ((await response.json()) as T);
  }
  const body = await response.json().catch(() => ({ detail: "Request failed" }));
  const detail =
    typeof body.detail === "string"
      ? body.detail
      : typeof body.detail?.message === "string"
        ? body.detail.message
        : "Request failed";
  throw new ApiError(response.status, detail);
}

async function request<T>(path: string, init: RequestInit = {}, retry = true): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body) headers.set("Content-Type", "application/json");
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  const response = await fetch(`${API_ROOT}${path}`, {
    ...init,
    headers,
    credentials: "include",
  });
  if (response.status === 401 && retry && !path.startsWith("/auth/")) {
    const refreshed = await refreshSession();
    if (refreshed) return request<T>(path, init, false);
  }
  return parseResponse<T>(response);
}

async function requestBlob(path: string): Promise<Blob> {
  const headers = new Headers();
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  const response = await fetch(`${API_ROOT}${path}`, { headers, credentials: "include" });
  if (!response.ok) await parseResponse<never>(response);
  return response.blob();
}

export async function login(input: {
  organization: string;
  email: string;
  password: string;
  device_name: string;
}): Promise<string | null> {
  const tokens = await request<TokenResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify(input),
  });
  if (tokens.mfa_required && tokens.mfa_challenge_token) return tokens.mfa_challenge_token;
  acceptTokens(tokens);
  return null;
}

export async function verifyMfa(challengeToken: string, code: string, deviceName: string) {
  const tokens = await request<TokenResponse>("/auth/mfa/verify", {
    method: "POST",
    body: JSON.stringify({
      challenge_token: challengeToken,
      code,
      device_name: deviceName,
    }),
  });
  acceptTokens(tokens);
}

export async function refreshSession(): Promise<boolean> {
  const csrfToken = sessionStorage.getItem("erp_csrf");
  if (!csrfToken) return false;
  try {
    const tokens = await request<TokenResponse>(
      "/auth/refresh",
      { method: "POST", body: JSON.stringify({ csrf_token: csrfToken }) },
      false,
    );
    acceptTokens(tokens);
    return true;
  } catch {
    clearTokens();
    return false;
  }
}

export async function logout() {
  try {
    await request<void>("/auth/logout", { method: "POST" }, false);
  } finally {
    clearTokens();
  }
}

function acceptTokens(tokens: TokenResponse) {
  if (!tokens.access_token || !tokens.csrf_token) throw new ApiError(401, "Invalid token response");
  setAccessToken(tokens.access_token);
  authScope = decodeScope(tokens.access_token);
  sessionStorage.setItem("erp_csrf", tokens.csrf_token);
}

function clearTokens() {
  setAccessToken(null);
  authScope = null;
  sessionStorage.removeItem("erp_csrf");
}

function decodeScope(token: string): AuthScope {
  try {
    const encoded = token.split(".")[1].replaceAll("-", "+").replaceAll("_", "/");
    const payload = JSON.parse(atob(encoded.padEnd(Math.ceil(encoded.length / 4) * 4, "=")));
    if (typeof payload.tenant !== "string" || typeof payload.sub !== "string") {
      throw new Error("Token scope is missing");
    }
    const permissions = Array.isArray(payload.permissions)
      ? payload.permissions.filter((permission: unknown) => typeof permission === "string")
      : [];
    return { tenant_id: payload.tenant, user_id: payload.sub, permissions };
  } catch {
    throw new ApiError(401, "Invalid token scope");
  }
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown, headers?: HeadersInit) =>
    request<T>(path, {
      method: "POST",
      body: body === undefined ? undefined : JSON.stringify(body),
      headers,
    }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
  blob: requestBlob,
};
