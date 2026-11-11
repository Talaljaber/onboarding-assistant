/** The user's turn: a teal bubble at the end of the line; its tail corner points at the user's side. */
export function UserBubble({ text }: { text: string }) {
  return (
    <li className="da-rise-in flex justify-end ps-8 sm:ps-16" data-kind="user">
      <p
        dir="auto"
        className="min-w-0 whitespace-pre-wrap break-words rounded-xl rounded-ee-sm bg-accent px-4 py-2.5 text-base leading-[1.75] text-on-accent shadow-1"
      >
        {text}
      </p>
    </li>
  );
}
