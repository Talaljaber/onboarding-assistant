export function UserBubble({ text }: { text: string }) {
  return (
    <li className="flex justify-end" data-kind="user">
      <p
        dir="auto"
        className="max-w-[85%] whitespace-pre-wrap break-words rounded-2xl rounded-ee-md bg-accent px-4 py-2.5 text-base leading-7 text-on-accent shadow-1"
      >
        {text}
      </p>
    </li>
  );
}
