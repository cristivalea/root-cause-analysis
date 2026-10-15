import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import { clsx } from "clsx";
import { Loader2 } from "lucide-react";

type Variant = "primary" | "secondary" | "ghost" | "danger" | "danger-ghost";
type Size = "sm" | "md";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-brand-600 text-white shadow-card hover:bg-brand-700 disabled:bg-brand-600/50",
  secondary: "border border-line bg-surface text-ink shadow-card hover:border-brand-600/40 hover:bg-brand-50",
  ghost: "text-brand-700 hover:bg-brand-50",
  danger: "bg-danger text-white shadow-card hover:bg-danger/90 disabled:bg-danger/50",
  "danger-ghost": "text-danger hover:bg-danger-soft",
};

const SIZES: Record<Size, string> = {
  sm: "h-8 gap-1.5 px-3 text-sm",
  md: "h-10 gap-2 px-4 text-sm",
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  icon?: ReactNode;
  /** Busy: the button is disabled and shows a spinner, so a second click cannot send the request again. */
  loading?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "secondary", size = "md", icon, loading = false, disabled, className, children, type = "button", ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={clsx(
        "inline-flex shrink-0 items-center justify-center whitespace-nowrap rounded-control font-medium transition-colors duration-150",
        "disabled:cursor-not-allowed disabled:opacity-60",
        VARIANTS[variant],
        SIZES[size],
        className,
      )}
      {...rest}
    >
      {loading ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : icon}
      {children}
    </button>
  );
});

export interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** Read by screen readers and shown as the tooltip: an icon alone says nothing. */
  label: string;
  variant?: "ghost" | "danger-ghost";
  children: ReactNode;
}

export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(function IconButton(
  { label, variant = "ghost", className, children, type = "button", ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      aria-label={label}
      title={label}
      className={clsx(
        "inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-control transition-colors duration-150",
        "disabled:cursor-not-allowed disabled:opacity-40",
        variant === "ghost" ? "text-muted hover:bg-brand-50 hover:text-brand-700" : "text-muted hover:bg-danger-soft hover:text-danger",
        className,
      )}
      {...rest}
    >
      {children}
    </button>
  );
});
