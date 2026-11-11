import { useId, useRef, useState, type FormEvent } from "react";
import { addIntern, patchIntern } from "@/api/client";
import type { InternOut, InternPatch, Role } from "@/api/types";
import { ROLES } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { cn } from "@/components/ui/cn";
import { Dialog } from "@/components/ui/Dialog";
import { segmented } from "@/components/ui/recipes";
import { TextField } from "@/components/ui/TextField";
import { useT } from "@/i18n";

/** Same rule as the server: 2–40 characters after collapsing spaces, nothing shaped like an email or phone. */
export function nameOk(value: string, optional = false): boolean {
  const v = value.trim().replace(/\s+/g, " ");
  if (!v) return optional;
  const digits = v.match(/[0-9٠-٩۰-۹]/g)?.length ?? 0;
  return v.length >= 2 && v.length <= 40 && !v.includes("@") && digits < 7;
}

export interface InternDialogProps {
  /** The intern to edit, or null to add one. */
  intern: Pick<InternOut, "id" | "name_ar" | "name_en" | "role"> | null;
  onClose: () => void;
  onSaved: (saved: InternOut) => void;
}

/** Add or edit an intern: Arabic name (required), English name (optional), track. */
export function InternDialog({ intern, onClose, onSaved }: InternDialogProps) {
  const t = useT();
  const uid = useId();
  const [nameAr, setNameAr] = useState(intern?.name_ar ?? "");
  const [nameEn, setNameEn] = useState(intern?.name_en ?? "");
  const [role, setRole] = useState<Role>(intern?.role ?? "Sales");
  const [touched, setTouched] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const arRef = useRef<HTMLInputElement>(null);
  const enRef = useRef<HTMLInputElement>(null);
  const arBad = !nameOk(nameAr);
  const enBad = !nameOk(nameEn, true);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (arBad || enBad) {
      (arBad ? arRef : enRef).current?.focus();
      return;
    }
    setBusy(true);
    setFailed(false);
    const en = nameEn.trim() ? nameEn.trim() : null;
    let r;
    if (intern) {
      const patch: InternPatch = {};
      if (nameAr.trim() !== intern.name_ar) patch.name_ar = nameAr.trim();
      if (en !== intern.name_en) patch.name_en = en;
      if (role !== intern.role) patch.role = role;
      if (Object.keys(patch).length === 0) {
        setBusy(false);
        onClose();
        return;
      }
      r = await patchIntern(intern.id, patch);
    } else {
      r = await addIntern({ name_ar: nameAr.trim(), name_en: en, role });
    }
    setBusy(false);
    if (!r.ok) {
      setFailed(true);
      return;
    }
    onSaved(r.value);
  }

  return (
    <Dialog open onClose={() => !busy && onClose()} title={t(intern ? "uiIntern.formEditTitle" : "uiIntern.formAddTitle")}>
      <form noValidate onSubmit={(e) => void submit(e)} className="flex flex-col gap-4" data-intern-form>
        <TextField
          ref={arRef}
          label={t("uiIntern.nameAr")}
          name="name_ar"
          lang="ar"
          dir="rtl"
          maxLength={60}
          required
          value={nameAr}
          onChange={(e) => setNameAr(e.target.value)}
          aria-invalid={(touched && arBad) || undefined}
          description={touched && arBad ? t("uiIntern.errName") : t("uiIntern.nameRule")}
          disabled={busy}
        />
        <TextField
          ref={enRef}
          label={t("uiIntern.nameEn")}
          name="name_en"
          lang="en"
          dir="ltr"
          maxLength={60}
          value={nameEn}
          onChange={(e) => setNameEn(e.target.value)}
          aria-invalid={(touched && enBad) || undefined}
          description={touched && enBad ? t("uiIntern.errName") : undefined}
          disabled={busy}
        />
        <fieldset className="m-0 flex flex-col gap-2 border-0 p-0">
          <legend className="mb-2 text-sm font-semibold text-fg-1">{t("uiIntern.track")}</legend>
          <div className={cn(segmented.track, "w-fit")}>
            {ROLES.map((r) => (
              <label key={r} className={cn(segmented.item, "da-radio-tile inline-flex min-h-11 cursor-pointer items-center px-5", role === r ? segmented.on : segmented.off)}>
                <input type="radio" name={`${uid}-role`} value={r} checked={role === r} onChange={() => setRole(r)} className="sr-only" disabled={busy} />
                {t(r === "Sales" ? "role.sales" : "role.delivery")}
              </label>
            ))}
          </div>
          {intern && role !== intern.role && <p className="m-0 text-sm text-fg-2">{t("uiIntern.trackNote")}</p>}
        </fieldset>
        {failed && (
          <p role="alert" className="m-0 text-sm font-medium text-danger">
            {t("uiIntern.saveFailed")}
          </p>
        )}
        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" icon={intern ? "check" : "plus"} loading={busy} data-testid="intern-save">
            {intern ? t("common.save") : t("uiIntern.add")}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
