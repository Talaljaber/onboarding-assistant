// Shared labels, icons and checks for mentor requests (P13.2). Text only: no files, no replies.
import type { RequestKind, RequestStatus } from "@/api/types";
import { REQUEST_LIMITS } from "@/api/types";
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
