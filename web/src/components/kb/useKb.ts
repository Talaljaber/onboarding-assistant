// Loads GET /api/kb and wraps the three writes. Every call returns the server's answer; a write
// that succeeds reloads the list so the badges always come from the server (never guessed).
import { useCallback, useEffect, useState } from "react";
import { getKb, postKb, putKb, resetKb, type ApiError, type Result } from "@/api/client";
import type { KbListResponse, KbNewRow, KbPatch, KbResetResponse, KbWriteResponse } from "@/api/types";

export type KbStatusState = "loading" | "ready" | "error";

export interface UseKb {
  status: KbStatusState;
  data: KbListResponse | null;
  reload: () => Promise<void>;
  edit: (id: string, patch: KbPatch) => Promise<Result<KbWriteResponse>>;
  add: (row: KbNewRow) => Promise<Result<KbWriteResponse>>;
  reset: () => Promise<Result<KbResetResponse>>;
}

/** The server's `error.code` and `field` of an http error, when it sent them. */
export function errorInfo(e: ApiError): { status?: number; code?: string; field?: string | null } {
  if (e.kind !== "http") return {};
  const d = e.detail;
  return typeof d === "object" && d !== null ? { status: e.status, code: d.code, field: d.field } : { status: e.status };
}

export function useKb(): UseKb {
  const [status, setStatus] = useState<KbStatusState>("loading");
  const [data, setData] = useState<KbListResponse | null>(null);

  const reload = useCallback(async () => {
    const r = await getKb();
    if (r.ok) {
      setData(r.value);
      setStatus("ready");
    } else {
      setStatus((s) => (s === "ready" ? s : "error"));
    }
  }, []);

  useEffect(() => {
    let live = true;
    void getKb().then((r) => {
      if (!live) return;
      if (r.ok) {
        setData(r.value);
        setStatus("ready");
      } else setStatus("error");
    });
    return () => {
      live = false;
    };
  }, []);

  const after = useCallback(
    async <T,>(p: Promise<Result<T>>, alsoOnError = false) => {
      const r = await p;
      if (r.ok || alsoOnError) await reload();
      return r;
    },
    [reload],
  );

  return {
    status,
    data,
    reload,
    edit: (id, patch) => after(putKb(id, patch)),
    // A 409 means the list is stale (someone added the id first): refresh it too.
    add: (row) => after(postKb(row), true),
    reset: () => after(resetKb()),
  };
}
