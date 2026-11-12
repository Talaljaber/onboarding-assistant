// #/quiz: the intern's practice quizzes (P20.2). `#/quiz` lists them (the official sample quiz and the sets the
// admin assigned); `#/quiz?set=<id>` takes one, one question at a time (QuizRunner). Practice only: the admin
// never sees an intern's answers or results.
import { useEffect, useRef } from "react";
import { QuizList } from "./QuizList";
import { QuizRunner } from "./QuizRunner";
import { useQuizSetParam } from "./hashParam";

export default function QuizScreen() {
  const setId = useQuizSetParam();
  // Switching between the list and a quiz keeps the route ("/quiz"), so move focus to the new heading here.
  const first = useRef(true);
  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    if (typeof window.scrollTo === "function" && window.scrollY > 0) window.scrollTo({ top: 0, left: 0, behavior: "instant" });
    const h1 = document.querySelector<HTMLElement>("[data-screen=quiz] h1");
    if (h1) {
      if (!h1.hasAttribute("tabindex")) h1.tabIndex = -1;
      h1.focus({ preventScroll: true });
    }
  }, [setId]);
  return setId ? <QuizRunner key={setId} setId={setId} /> : <QuizList />;
}
