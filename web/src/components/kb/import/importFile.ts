// Client-side helpers for the document import (P12.1): read a File as base64 for the JSON upload,
// check type / size / emptiness against the server's capabilities, default document name, and map the
// server's error to our own wording (its messages are English developer text).
import type { ApiError } from "@/api/client";
import type { ImportCapabilities, OrganizeSummary } from "@/api/types";
import type { DictKey } from "@/i18n";

export const ACCEPT = ".txt,.md,.markdown,.csv,.docx,.pdf";

/** Lower-case extension without the dot ("markdown" counts as "md"). */
export function extOf(name: string): string {
  const m = /\.([A-Za-z0-9]+)$/.exec(name.trim());
  const ext = m ? m[1]!.toLowerCase() : "";
  return ext === "markdown" ? "md" : ext;
}

/** The default document name: the file name without its extension, underscores as spaces, ≤ 80 chars. */
export function defaultDocName(name: string): string {
  const base = name.replace(/^.*[\\/]/, "").replace(/\.[^.]+$/, "").replace(/_/g, " ").trim();
  return base.slice(0, 80).trim();
}

export function mb(bytes: number): number {
  return Math.round(bytes / (1024 * 1024));
}

export interface FileProblem {
  key: DictKey;
  vars?: Record<string, string | number>;
}

/** Why this file cannot be uploaded (checked before reading it), or null. */
export function fileProblem(file: { name: string; size: number }, caps: ImportCapabilities): FileProblem | null {
  const ext = extOf(file.name);
  if (ext === "pdf" && !caps.pdf) return { key: "kbImport.errPdf" };
  if (!(caps.types as string[]).includes(ext)) return { key: "kbImport.errType", vars: { types: typesLabel(caps) } };
  if (file.size === 0) return { key: "kbImport.errEmpty" };
  if (file.size > caps.max_bytes) return { key: "kbImport.errSize", vars: { mb: mb(caps.max_bytes) } };
  return null;
}

export function typesLabel(caps: ImportCapabilities): string {
  return caps.types.map((t) => `.${t}`).join(" ");
}

/** Base64 of the file's bytes (chunked so large files do not overflow the call stack). */
export async function fileToBase64(file: Blob): Promise<string> {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = "";
  const step = 0x8000;
  for (let i = 0; i < bytes.length; i += step) {
    binary += String.fromCharCode(...bytes.subarray(i, i + step));
  }
  return btoa(binary);
}

/** Our wording for a failed upload. */
export function uploadProblem(e: ApiError, caps: ImportCapabilities | null): FileProblem {
  const detail = e.kind === "http" && typeof e.detail === "object" ? e.detail : null;
  if (e.status === 413) return { key: "kbImport.errSize", vars: { mb: mb(caps?.max_bytes ?? 2 * 1024 * 1024) } };
  if (e.status === 503) return { key: "kbImport.errUnavailable" };
  if (detail?.code === "validation_error") {
    if (detail.field === "filename")
      return /pypdf/i.test(detail.message)
        ? { key: "kbImport.errPdf" }
        : { key: "kbImport.errType", vars: { types: caps ? typesLabel(caps) : ".txt .md .csv .docx" } };
    if (detail.field === "passages") return { key: "kbImport.errMany", vars: { n: caps?.max_passages ?? 200 } };
    if (detail.field === "content_b64") return { key: "kbImport.errEmpty" };
    if (detail.field === "document_name") return { key: "kbImport.errName" };
  }
  return { key: "kbImport.errFailed" };
}

/** The organize summary of the last upload, shown once on its review screen (GET does not repeat it). */
type UploadSummary = Pick<OrganizeSummary, "organized" | "fallback" | "used" | "titles">;
const summaries = new Map<string, UploadSummary>();
export const rememberSummary = (id: string, s: UploadSummary) => summaries.set(id, s);
export const takeSummary = (id: string) => summaries.get(id) ?? null;
