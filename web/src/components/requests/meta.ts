// Shared labels, icons and checks for mentor requests (P13.2) and their reply threads (P15).
import type { RequestKind, RequestStatus } from "@/api/types";
import { COMMENT_LIMITS, REQUEST_LIMITS } from "@/api/types";
import type { DictKey } from "@/i18n";
import type { IconName } from "../ui/Icon";

export const KIND: Record<RequestKind, { key: DictKey; icon: IconName }> = {
  learn: { key: "mentorReq.kindLearn", icon: "graduation" },
  do: { key: "mentorReq.kindDo", icon: "target" },
  read: { key: "mentorReq.kindRead", icon: "book" },
};

export const STATUS: Record<RequestStatus, { key: DictKey; tone: "neutral" | "info" | "ok" }> = {
  new: { key: "mentorReq.statusNew", tone: "neutral" },
  in_progress: { key: "mentorReq.statusInProgress", tone: "info" },
  done: { key: "mentorReq.statusDone", tone: "ok" },
};

/** Same contact rule as the server (the verifier's): no email, link or phone-shaped digit run. */
const CONTACT = /@|https?:\/\/|www\.|\+962|\b0[67]\d{7,8}\b|\b(?:\d[\s-]?){7,}\b/i;

function asciiDigits(s: string): string {
  return s.replace(/[٠-٩]/g, (d) => String(d.charCodeAt(0) - 0x0660)).replace(/[۰-۹]/g, (d) => String(d.charCodeAt(0) - 0x06f0));
}

export function hasContact(text: string): boolean {
  return CONTACT.test(asciiDigits(text));
}

export function titleOk(v: string): boolean {
  const s = v.trim().replace(/\s+/g, " ");
  return s.length >= 1 && s.length <= REQUEST_LIMITS.titleMax && !hasContact(s);
}

export function noteOk(v: string): boolean {
  return v.trim().length <= REQUEST_LIMITS.noteMax && !hasContact(v);
}

// ---- P15 reply threads: the server's cheap checks, mirrored (the server checks again, magic bytes included)

export interface Problem {
  key: DictKey;
  vars?: Record<string, string | number>;
}

/** Lower-case extension without the dot. */
export function fileExt(name: string): string {
  const m = /\.([A-Za-z0-9]+)$/.exec(name.trim());
  return m ? m[1]!.toLowerCase() : "";
}

/** Why these files cannot be attached (type, empty, over 5 MB, more than 3), or null. */
export function filesProblem(files: readonly { name: string; size: number }[]): Problem | null {
  if (files.length > COMMENT_LIMITS.filesMax) return { key: "requestThread.errCount" };
  for (const f of files) {
    if (!(COMMENT_LIMITS.extensions as readonly string[]).includes(fileExt(f.name)))
      return { key: "requestThread.errType", vars: { name: f.name } };
    if (f.size === 0) return { key: "requestThread.errEmptyFile", vars: { name: f.name } };
    if (f.size > COMMENT_LIMITS.fileMaxBytes) return { key: "requestThread.errSize", vars: { name: f.name } };
  }
  return null;
}

/** Why this reply cannot be sent (too long, a contact, neither text nor a file), or null. */
export function replyProblem(body: string, fileCount: number): Problem | null {
  if (body.trim().length > COMMENT_LIMITS.bodyMax) return { key: "requestThread.errLong", vars: { max: COMMENT_LIMITS.bodyMax } };
  if (hasContact(body)) return { key: "requestThread.errContact" };
  if (!body.trim() && fileCount === 0) return { key: "requestThread.errEmpty" };
  return null;
}

/** "320 KB" / "1.4 MB" (ASCII digits in both languages). */
export function fileSize(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
