import type { SpamFilter } from "./types";

export function requestHeaders(token: string): Record<string, string> {
  return token ? { authorization: `Bearer ${token}` } : {};
}

export async function operationsApi<T>(url: string, credential: string, init?: RequestInit): Promise<T> {
  const jsonBody = init?.body && !(init.body instanceof FormData);
  const response = await fetch(url, {
    ...init,
    headers: {
      authorization: `Bearer ${credential}`,
      ...(jsonBody ? { "content-type": "application/json" } : {}),
      ...init?.headers,
    },
  });
  if (!response.ok) {
    const body = await response.text();
    try {
      const parsed = JSON.parse(body) as { detail?: string };
      throw new Error(parsed.detail || "Operations request failed");
    } catch (error) {
      if (error instanceof SyntaxError) {
        throw new Error(body || "Operations request failed", { cause: error });
      }
      throw error;
    }
  }
  return response.json() as Promise<T>;
}

export function leadQuery(status: string, source: string, spam: SpamFilter, query: string): string {
  const params = new URLSearchParams({ limit: "100", spam });
  if (status) params.set("status", status);
  if (source) params.set("source", source);
  if (query) params.set("query", query);
  return params.toString();
}
