import type { EntityConfig, PaginatedResponse, Stats } from "./types";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BACKEND_URL}${path}`, {
    ...options,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, body.detail || res.statusText);
  }
  return res.json();
}

export const api = {
  login: (password: string) =>
    request<{ message: string }>("/cms/login", { method: "POST", body: JSON.stringify({ password }) }),
  logout: () => request<{ message: string }>("/cms/logout", { method: "POST" }),
  me: () => request<{ authenticated: boolean }>("/cms/me"),
  stats: () => request<Stats>("/cms/stats"),
  entities: () => request<EntityConfig[]>("/cms/entities"),
  list: (entity: string, page: number, search: string) =>
    request<PaginatedResponse>(`/cms/entities/${entity}?page=${page}&search=${encodeURIComponent(search)}`),
  get: (entity: string, id: string) => request<Record<string, unknown>>(`/cms/entities/${entity}/${id}`),
  create: (entity: string, payload: Record<string, unknown>) =>
    request<Record<string, unknown>>(`/cms/entities/${entity}`, { method: "POST", body: JSON.stringify(payload) }),
  update: (entity: string, id: string, payload: Record<string, unknown>) =>
    request<Record<string, unknown>>(`/cms/entities/${entity}/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  remove: (entity: string, id: string) =>
    request<{ deleted: string }>(`/cms/entities/${entity}/${id}`, { method: "DELETE" }),
};
