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

/** File-name words that say nothing about the content ("doc_dress.txt" is a dress-code document). */
const NOISE = /^(?:doc|docs|document|file|final|draft|copy|new|v\d+|\d{6,8})$/i;

/**
 * The default document name, a readable title from the file name (P16.4): no folder or extension,
 * "_", "-" and camelCase as spaces, filler words ("doc", "final", "v2") dropped, first letter upper
 * case, at most 80 chars. The admin can still change it; the field is required.
 */
export function defaultDocName(name: string): string {
  const base = name.replace(/^.*[\\/]/, "").replace(/\.[^.]+$/, "");
  const words = base.replace(/([a-z])([A-Z])/g, "$1 $2").split(/[\s_\-.]+/).filter(Boolean);
  const kept = words.filter((w) => !NOISE.test(w));
  const title = (kept.length > 0 ? kept : words).join(" ").slice(0, 80).trim();
  return title.charAt(0).toUpperCase() + title.slice(1);
}

/**
 * The heading of a .txt / .md file: its first non-empty line ("# " stripped) when that line is short
 * (2–80 chars) and does not end a sentence; otherwise null and the file-name title stays.
 */
export async function headingOf(file: Blob & { name: string }): Promise<string | null> {
  const ext = extOf(file.name);
  if ((ext !== "txt" && ext !== "md") || file.size === 0 || typeof file.text !== "function") return null;
  const text = await file.slice(0, 4096).text();
  const line = text.replace(/^﻿/, "").split(/\r?\n/).map((l) => l.replace(/^#+\s*/, "").trim()).find(Boolean);
  if (!line || line.length < 2 || line.length > 80 || /[.!?؟。:]$/.test(line)) return null;
  return line;
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
