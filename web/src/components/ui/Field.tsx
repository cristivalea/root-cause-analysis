import { forwardRef, useId, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";
import { clsx } from "clsx";

const CONTROL =
  "w-full rounded-control border border-line bg-surface px-3 text-sm text-ink shadow-card placeholder:text-muted/70 " +
  "transition-colors hover:border-brand-600/40 focus:border-brand-600 disabled:cursor-not-allowed disabled:bg-neutral-soft";

interface FieldProps {
  label: ReactNode;
  hint?: ReactNode;
  error?: string | null;
  required?: boolean;
  id?: string;
  hideLabel?: boolean;
  className?: string;
}

function FieldShell({ label, hint, error, required, id, hideLabel, className, children }: FieldProps & { id: string; children: ReactNode }) {
  return (
    <div className={clsx("flex flex-col gap-1.5", className)}>
      <label htmlFor={id} className={clsx("text-sm font-medium text-ink", hideLabel && "sr-only")}>
        {label}
        {required && <span className="ml-0.5 text-danger" aria-hidden="true">*</span>}
      </label>
      {children}
      {hint && !error && <p id={`${id}-hint`} className="text-xs text-muted">{hint}</p>}
      {error && (
        <p id={`${id}-error`} role="alert" className="text-xs font-medium text-danger">
          {error}
        </p>
      )}
    </div>
  );
}

function describedBy(id: string, hint: unknown, error: unknown) {
  return [error ? `${id}-error` : null, hint && !error ? `${id}-hint` : null].filter(Boolean).join(" ") || undefined;
}

export const TextInput = forwardRef<HTMLInputElement, FieldProps & InputHTMLAttributes<HTMLInputElement> & { trailing?: ReactNode }>(
  function TextInput({ label, hint, error, required, id, hideLabel, className, trailing, ...rest }, ref) {
    const generated = useId();
    const fieldId = id ?? generated;
    return (
      <FieldShell {...{ label, hint, error, required, hideLabel, className }} id={fieldId}>
        <div className="relative">
          <input
            ref={ref}
            id={fieldId}
            aria-invalid={error ? true : undefined}
            aria-required={required || undefined}
            aria-describedby={describedBy(fieldId, hint, error)}
            className={clsx(CONTROL, "h-10", trailing && "pr-10", error && "border-danger")}
            {...rest}
          />
          {trailing && <div className="absolute inset-y-0 right-1 flex items-center">{trailing}</div>}
        </div>
      </FieldShell>
    );
  },
);

export const TextArea = forwardRef<HTMLTextAreaElement, FieldProps & TextareaHTMLAttributes<HTMLTextAreaElement>>(
  function TextArea({ label, hint, error, required, id, hideLabel, className, ...rest }, ref) {
    const generated = useId();
    const fieldId = id ?? generated;
    return (
      <FieldShell {...{ label, hint, error, required, hideLabel, className }} id={fieldId}>
        <textarea
          ref={ref}
          id={fieldId}
          aria-invalid={error ? true : undefined}
          aria-required={required || undefined}
          aria-describedby={describedBy(fieldId, hint, error)}
          className={clsx(CONTROL, "min-h-[80px] py-2 leading-relaxed", error && "border-danger")}
          {...rest}
        />
      </FieldShell>
    );
  },
);

export const Select = forwardRef<HTMLSelectElement, FieldProps & SelectHTMLAttributes<HTMLSelectElement>>(
  function Select({ label, hint, error, required, id, hideLabel, className, children, ...rest }, ref) {
    const generated = useId();
    const fieldId = id ?? generated;
    return (
      <FieldShell {...{ label, hint, error, required, hideLabel, className }} id={fieldId}>
        <select
          ref={ref}
          id={fieldId}
          aria-describedby={describedBy(fieldId, hint, error)}
          className={clsx(CONTROL, "h-10 cursor-pointer pr-8")}
          {...rest}
        >
          {children}
        </select>
      </FieldShell>
    );
  },
);
