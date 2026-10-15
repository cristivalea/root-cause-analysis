/** The one way the interface talks to the FastAPI backend (api.py). Every request carries the token of the
 * signed-in user; the backend checks the role on each request, so nothing here is a security boundary. */

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
  ) {
    super(detail || `HTTP ${status}`);
    this.name = "ApiError";
  }

  /** The server could not be reached at all (status 0). */
  get unreachable(): boolean {
    return this.status === 0;
  }
}

const TOKEN_KEY = "rca.token";
let onUnauthorized: (() => void) | null = null;

export const tokenStore = {
  get(): string | null {
    try {
      return sessionStorage.getItem(TOKEN_KEY);
    } catch {
      return null;
    }
  },
  set(token: string | null) {
    try {
      if (token) sessionStorage.setItem(TOKEN_KEY, token);
      else sessionStorage.removeItem(TOKEN_KEY);
    } catch {
      // storage blocked: the session lasts until the page is reloaded
    }
  },
};

/** Called once by the auth provider: what happens when the token is refused (expired, account disabled). */
export function setUnauthorizedHandler(handler: (() => void) | null) {
  onUnauthorized = handler;
}

function detailOf(body: unknown): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) return detail.map((item) => (item as { msg?: string }).msg ?? "").filter(Boolean).join("; ");
  }
  return "";
}

export async function apiFetch<T>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const { json, headers, ...rest } = init;
  const token = tokenStore.get();
  let response: Response;
  try {
    response = await fetch(`/api/v1${path}`, {
      ...rest,
      headers: {
        Accept: "application/json",
        ...(json !== undefined ? { "Content-Type": "application/json" } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...headers,
      },
      body: json !== undefined ? JSON.stringify(json) : rest.body,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError(0, error instanceof Error ? error.message : String(error));
  }
  const body: unknown = response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401 && token && path !== "/auth/login") onUnauthorized?.();
    throw new ApiError(response.status, detailOf(body) || response.statusText);
  }
  return body as T;
}

export const get = <T>(path: string, signal?: AbortSignal) => apiFetch<T>(path, { signal });
export const post = <T>(path: string, json: unknown) => apiFetch<T>(path, { method: "POST", json });
export const put = <T>(path: string, json: unknown) => apiFetch<T>(path, { method: "PUT", json });
