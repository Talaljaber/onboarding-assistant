// K-row topic names (P16.4): the knowledge base stores them in English; the Arabic UI shows Arabic
// names for the official topics and any other topic (an imported one) as it is.
import { translate, type DictKey, type Lang } from "@/i18n";

const TOPIC_KEY: Record<string, DictKey> = {
  Company: "p16.topicCompany",
  Values: "p16.topicValues",
  Onboarding: "p16.topicOnboarding",
  Policy: "p16.topicPolicy",
};

export function topicLabel(topic: string, lang: Lang): string {
  const key = TOPIC_KEY[topic.trim()];
  return key ? translate(lang, key) : topic;
}

/** The first words of a row's text, for pickers and headings (never the keyword, which can go stale). */
export function rowStart(text: string, max = 48): string {
  const s = text.trim().replace(/\s+/g, " ");
  if (s.length <= max) return s;
  const cut = s.slice(0, max);
  const sp = cut.lastIndexOf(" ");
  return `${(sp > max / 2 ? cut.slice(0, sp) : cut).replace(/[\s،,.:؛]+$/u, "")}…`;
}
