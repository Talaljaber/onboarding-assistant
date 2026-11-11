import { useT } from "@/i18n";

/** Starter questions as plain buttons (not radios); a click sends the question at once. */
export function StarterChips({ questions, disabled, onPick }: { questions: readonly string[]; disabled: boolean; onPick: (q: string) => void }) {
  const t = useT();
  return (
    <div data-kind="starters" className="mt-1">
      <p className="mb-2 text-sm font-semibold text-fg-2">{t("chat.starters")}</p>
      <ul className="flex flex-wrap gap-2">
        {questions.map((q) => (
          <li key={q}>
            <button
              type="button"
              disabled={disabled}
              onClick={() => onPick(q)}
              lang="ar"
              dir="rtl"
              className="min-h-11 rounded-full border border-line-strong bg-surface-0 px-4 text-sm font-medium text-fg-1 transition-colors duration-(--da-motion-fast) hover:border-accent hover:bg-surface-1 disabled:cursor-not-allowed disabled:opacity-55"
            >
              {q}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
