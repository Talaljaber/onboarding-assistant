// `#/admin`: admin sign-in. The admin shell (Interns, Knowledge base) opens only after it. Interns
// never come here: they pick their name on the sign-in screen "#/".
import { useEffect, useRef, useState, type FormEvent } from "react";
import { adminLogin } from "@/api/client";
import { useT } from "@/i18n";
import { navigate } from "@/router";
import { useAppState } from "@/state/useAppState";
import { Button } from "../ui/Button";
import { Icon } from "../ui/Icon";
import { Notice } from "../ui/Notice";
import { Page, PageHeader } from "../ui/Page";
import { link, surface } from "../ui/recipes";
import { TextField } from "../ui/TextField";

type Problem = "required" | "wrong" | "tooMany" | "failed" | null;

export default function AdminScreen() {
  const t = useT();
  const { role } = useAppState();
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<Problem>(null);
  const field = useRef<HTMLInputElement>(null);
  const live = useRef(true);

  useEffect(() => {
    live.current = true;
    return () => {
      live.current = false;
    };
  }, []);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (busy) return;
    if (!password.trim()) {
      setProblem("required");
      field.current?.focus();
      return;
    }
    setBusy(true);
    setProblem(null);
    const r = await adminLogin(password);
    if (!live.current) return;
    setBusy(false);
    if (r.ok) {
      setPassword("");
      navigate("/admin/interns");
      return;
    }
    const status = r.error.kind === "http" ? r.error.status : undefined;
    setProblem(status === 401 ? "wrong" : status === 429 ? "tooMany" : "failed");
    field.current?.select();
  }

  const message = problem === null ? null : t(`uiAuth.${problem}`);
  return (
    <section data-screen="admin" className="min-w-0">
      <Page width="narrow">
        <PageHeader icon="lock" title={t("uiAuth.title")} description={t("uiAuth.intro")} />
        <form noValidate onSubmit={(e) => void submit(e)} className={`${surface.card} flex flex-col gap-4 p-5 sm:p-6`}>
          <div className="flex flex-col gap-2">
            <TextField
              ref={field}
              label={t("uiAuth.password")}
              type={show ? "text" : "password"}
              name="admin-password"
              autoComplete="current-password"
              dir="ltr"
              maxLength={64}
              value={password}
              onChange={(e) => {
                setPassword(e.target.value);
                if (problem) setProblem(null);
              }}
              aria-invalid={problem !== null || undefined}
              description={message ?? undefined}
              disabled={busy}
            />
            <label className="flex min-h-11 w-fit cursor-pointer items-center gap-2 text-sm text-fg-2">
              <input type="checkbox" className="size-5 accent-(--da-accent)" checked={show} onChange={(e) => setShow(e.target.checked)} />
              <Icon name="eye" size={16} className="text-fg-3" />
              {t("uiAuth.show")}
            </label>
          </div>
          <Button type="submit" icon="lock" loading={busy} block>
            {t("uiAuth.submit")}
          </Button>
        </form>
        <Notice tone="neutral">{t("uiAuth.employeeNote")}</Notice>
        <p>
          <a href={role ? "#/chat" : "#/"} className={link}>
            {t("uiAuth.back")}
          </a>
        </p>
      </Page>
    </section>
  );
}
