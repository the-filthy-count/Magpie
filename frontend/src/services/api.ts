export let csrf = "";
export function setCsrf(value: string) {
  csrf = value;
}
export async function api<T = any>(
  path: string,
  method = "GET",
  body?: unknown,
  extra: Record<string, string> = {},
): Promise<T> {
  const form = body instanceof FormData;
  const response = await fetch("/api" + path, {
    method,
    credentials: "same-origin",
    headers: {
      ...(body && !form ? { "Content-Type": "application/json" } : {}),
      "X-CSRF-Token": csrf,
      ...extra,
    },
    body: body ? (form ? body : JSON.stringify(body)) : undefined,
  });
  const data = await response.json();
  if (!response.ok) {
    if (response.status === 401)
      window.dispatchEvent(new Event("magpie-unauthorized"));
    throw new Error(data.error?.message || "Request failed");
  }
  return data;
}
export type Job = {
  id: string;
  url: string;
  website: string;
  destination_id: string;
  destination_name: string;
  destination_path: string;
  status: string;
  files: number;
  total_files?: number | null;
  skipped: number;
  bytes: number;
  speed: number | null;
  current_filename: string | null;
  file_bytes: number | null;
  file_total: number | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  error: string | null;
  attempts: number;
};
export type Destination = {
  id: string;
  name: string;
  path: string;
  description: string;
  icon: string;
  is_default: boolean;
  accessible: boolean;
  writable: boolean;
};
export function bytes(n: number | null | undefined) {
  if (n == null) return "—";
  if (n < 1024) return n + " B";
  const unit = Math.min(Math.floor(Math.log(n) / Math.log(1024)), 4);
  return (
    (n / 1024 ** unit).toFixed(1) + " " + ["B", "KB", "MB", "GB", "TB"][unit]
  );
}
export const date = (value: string | null) =>
  value ? new Date(value).toLocaleString() : "—";
