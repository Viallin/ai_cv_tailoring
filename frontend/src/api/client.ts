// Thin fetch wrapper. Every path is relative ("/candidates", "/jobs", ...)
// and gets an "/api" prefix — Vite's dev-server proxy (vite.config.ts)
// forwards /api/* to the FastAPI backend, so the browser never makes a
// cross-origin request. See vite.config.ts for why this is preferred over
// CORSMiddleware.
//
// Every non-2xx response from the backend carries the same envelope
// (api/errors.py): {"error": {"category": "...", "message": "..."}} —
// ApiError is the single place that gets parsed and re-thrown as a typed
// error every hook's error state flows through.

const API_PREFIX = "/api";

export class ApiError extends Error {
  readonly category: string;
  readonly status: number;

  constructor(category: string, message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.category = category;
    this.status = status;
  }
}

interface ErrorEnvelope {
  error: { category: string; message: string };
}

async function throwApiError(response: Response): Promise<never> {
  let body: ErrorEnvelope | null = null;
  try {
    body = (await response.json()) as ErrorEnvelope;
  } catch {
    // Response wasn't JSON (e.g. a proxy/network-level failure) — fall
    // through to the generic error below instead of throwing a parse error.
  }
  if (body?.error) {
    throw new ApiError(body.error.category, body.error.message, response.status);
  }
  throw new ApiError("UnknownError", response.statusText || "Request failed", response.status);
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_PREFIX}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    await throwApiError(response);
  }
  // 204 No Content (every DELETE route — api/routes/entity_crud.py's
  // factory-generated ones included) has no body at all; calling
  // response.json() on it throws. Never hit until Phase 15b-i's
  // useEntityMutations added the first frontend DELETE call.
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

// Version 4, Phase 4.5: the multipart-upload counterpart to apiFetch, for
// POST /jobs/ingest-upload. Deliberately does NOT set Content-Type the way
// apiFetch always does — a multipart body needs a "multipart/form-data;
// boundary=..." header the browser computes from the FormData itself, and
// setting it explicitly (or omitting the boundary) breaks the backend's
// parsing. fetch() sets that header correctly on its own only when no
// Content-Type is passed at all.
export async function apiFetchUpload<T>(path: string, formData: FormData): Promise<T> {
  const response = await fetch(`${API_PREFIX}${path}`, { method: "POST", body: formData });
  if (!response.ok) {
    await throwApiError(response);
  }
  return (await response.json()) as T;
}

export interface BlobResult {
  blob: Blob;
  filename: string;
}

function filenameFromContentDisposition(header: string | null): string {
  const match = header?.match(/filename="?([^"]+)"?/);
  return match?.[1] ?? "download";
}

// A separate function rather than a generic-over-response-type apiFetch:
// success here is a Blob, failure is still the JSON {error:...} envelope,
// so the branch on response.ok has to happen before deciding how to parse
// the body at all.
export async function apiFetchBlob(path: string, init?: RequestInit): Promise<BlobResult> {
  const response = await fetch(`${API_PREFIX}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    await throwApiError(response);
  }
  const blob = await response.blob();
  const filename = filenameFromContentDisposition(response.headers.get("Content-Disposition"));
  return { blob, filename };
}
