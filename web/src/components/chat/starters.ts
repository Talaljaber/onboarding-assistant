// Starter questions (plan D2.3). Arabic data strings: they are sent to the server as typed text,
// so they stay Arabic in both UI languages.
import type { Role } from "@/api/types";

export const STARTERS: Record<Role, readonly string[]> = {
  Sales: [
    "ما قيم الشركة الخمس؟",
    "كيف أقدم طلب إجازة؟",
    "ما العلامات التجارية للشركة؟",
    "تدريب: زبون يسأل عن ميزة غير مؤكدة",
    "ماذا أفعل في اليوم 30؟",
  ],
  Delivery: [
    "متى تأسست مجموعة الدادا؟",
    "كم مدة فترة التجربة؟",
    "هل يمكنني مشاركة ملفات الشركة مع شخص خارجي؟",
    "تدريب: العميل منزعج من تأخر التسليم",
    "ماذا أفعل في اليوم 30؟",
  ],
};

/** Fixed label of a scenario card started on the client (contract section 7). */
export const SCENARIO_START_LABEL_AR = "تدريب عملي، ليس تقييماً";
