import { forwardRef, useId, type ReactNode, type SelectHTMLAttributes } from "react";
import { cn } from "./cn";
import { CONTROL, LABEL } from "./TextField";

/** One choice of a {@link Select}. */
export interface SelectOption {
  value: string;
  label: string;
}

/** Props for {@link Select}: every native select attribute plus a required label and the options. */
export interface SelectProps extends Omit<SelectHTMLAttributes<HTMLSelectElement>, "className" | "children"> {
  label: string;
  options: readonly SelectOption[];
  /** Hide the visible label (it is still read by assistive technology). */
  hideLabel?: boolean;
  /** Helper text under the control, tied to it with `aria-describedby`. */
  description?: ReactNode;
  className?: string;
}

/**
 * Labelled native `<select>`. The browser's own control gives keyboard and screen-reader
 * behaviour for free; the wrapper adds the label, a 44px target (36px when `compact`
 * is wanted through `className`) and the shared focus ring.
 */
export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { label, options, hideLabel = false, description, className, id, ...rest },
  ref,
) {
  const auto = useId();
  const selectId = id ?? auto;
  const descId = description ? `${selectId}-desc` : undefined;
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <label htmlFor={selectId} className={hideLabel ? "sr-only" : LABEL}>
        {label}
      </label>
      <select
        ref={ref}
        id={selectId}
        aria-describedby={descId}
        className={cn(CONTROL, "min-h-12")}
        {...rest}
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      {description && (
        <p id={descId} className="text-sm text-fg-3">
          {description}
        </p>
      )}
    </div>
  );
});
