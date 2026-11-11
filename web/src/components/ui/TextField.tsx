import { forwardRef, useId, type InputHTMLAttributes, type ReactNode, type TextareaHTMLAttributes } from "react";
import { cn } from "./cn";

/** Shared look of every text control (inputs, textareas, selects). Exported for screen-local controls. */
export const CONTROL =
  "w-full rounded-md border border-line-strong bg-input px-3.5 text-base text-fg-1 placeholder:text-fg-3 " +
  "transition-[border-color,box-shadow] duration-(--da-motion-fast) ease-da hover:border-accent focus-visible:border-accent " +
  "disabled:cursor-not-allowed disabled:bg-surface-1 disabled:opacity-60";

/** Shared label look. */
export const LABEL = "text-sm font-semibold text-fg-1";

interface FieldShellProps {
  label: string;
  /** Helper or error text shown under the control and tied to it with `aria-describedby`. */
  description?: ReactNode;
  className?: string;
}

/** Props for {@link TextField}: every native input attribute plus a required visible label. */
export interface TextFieldProps extends FieldShellProps, Omit<InputHTMLAttributes<HTMLInputElement>, "className"> {}

/**
 * Labelled single-line input. The label is a real `<label>` (visible, so voice-control and
 * screen-reader users share one name), the control is at least 44px tall, and the focus
 * ring comes from the global `:focus-visible` rule.
 */
export const TextField = forwardRef<HTMLInputElement, TextFieldProps>(function TextField(
  { label, description, className, id, ...rest },
  ref,
) {
  const auto = useId();
  const inputId = id ?? auto;
  const descId = description ? `${inputId}-desc` : undefined;
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <label htmlFor={inputId} className={LABEL}>
        {label}
      </label>
      <input ref={ref} id={inputId} aria-describedby={descId} className={cn(CONTROL, "min-h-12")} {...rest} />
      {description && (
        <p id={descId} className="text-sm text-fg-3">
          {description}
        </p>
      )}
    </div>
  );
});

/** Props for {@link TextArea}. */
export interface TextAreaProps extends FieldShellProps, Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, "className"> {
  /** Hide the visible label (it is still read by assistive technology). */
  hideLabel?: boolean;
}

/** Labelled multi-line input, same contract as {@link TextField}. Direction follows the typed text with `dir="auto"`. */
export const TextArea = forwardRef<HTMLTextAreaElement, TextAreaProps>(function TextArea(
  { label, description, className, id, hideLabel = false, rows = 3, ...rest },
  ref,
) {
  const auto = useId();
  const areaId = id ?? auto;
  const descId = description ? `${areaId}-desc` : undefined;
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <label htmlFor={areaId} className={hideLabel ? "sr-only" : LABEL}>
        {label}
      </label>
      <textarea
        ref={ref}
        id={areaId}
        rows={rows}
        dir="auto"
        aria-describedby={descId}
        className={cn(CONTROL, "min-h-12 py-2.5")}
        {...rest}
      />
      {description && (
        <p id={descId} className="text-sm text-fg-3">
          {description}
        </p>
      )}
    </div>
  );
});
