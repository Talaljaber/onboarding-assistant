// Starter questions (plan D2.3). The texts live in the dictionaries (`uiUat.starter*`): the Arabic
// ones are the questions the server was tuned on; in English the chip shows and sends the English
// question (the server still answers in Arabic).
import type { Role } from "@/api/types";
import type { DictKey } from "@/i18n";

export const STARTERS: Record<Role, readonly DictKey[]> = {
  Sales: [
    "uiUat.starterSales1",
    "uiUat.starterSales2",
    "uiUat.starterSales3",
    "uiUat.starterSales4",
    "uiUat.starterSales5",
  ],
  Delivery: [
    "uiUat.starterDelivery1",
    "uiUat.starterDelivery2",
    "uiUat.starterDelivery3",
    "uiUat.starterDelivery4",
    "uiUat.starterDelivery5",
  ],
};

/** Fixed label of a scenario card started on the client (contract section 7). */
export const SCENARIO_START_LABEL_AR = "تدريب عملي، ليس تقييماً";
