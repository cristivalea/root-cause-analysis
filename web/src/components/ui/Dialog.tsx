import { useEffect, useId, useState, type ReactNode } from "react";
import * as RadixDialog from "@radix-ui/react-dialog";
import { clsx } from "clsx";
import { CheckCircle2, X } from "lucide-react";
import { useI18n } from "@/i18n/I18nProvider";
import { Button } from "./Button";
import { TextArea } from "./Field";

/** A modal dialog: focus stays inside, Esc and the close button close it, the page behind is inert (Radix). */
export function Dialog({ open, onOpenChange, title, description, children, footer, size = "md" }: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: ReactNode;
  description?: ReactNode;
  children?: ReactNode;
  footer?: ReactNode;
  size?: "md" | "lg" | "xl";
}) {
  const { t } = useI18n();
  return (
    <RadixDialog.Root open={open} onOpenChange={onOpenChange}>
      <RadixDialog.Portal>
        <RadixDialog.Overlay className="fixed inset-0 z-40 bg-ink/40 backdrop-blur-[2px] animate-fade-in" />
        <RadixDialog.Content
          className={clsx(
            "fixed left-1/2 top-1/2 z-50 flex max-h-[min(88vh,820px)] w-[calc(100vw-2rem)] -translate-x-1/2 -translate-y-1/2 flex-col",
            "rounded-card border border-line bg-surface shadow-pop animate-scale-in focus:outline-none",
            size === "md" && "max-w-lg",
            size === "lg" && "max-w-2xl",
            size === "xl" && "max-w-4xl",
          )}
          {...(description ? {} : { "aria-describedby": undefined })}
        >
          {/* a dialog with only a question and its buttons has no separators: they would frame an empty space */}
          <div className={clsx("flex items-start justify-between gap-4 px-6 py-4", children && "border-b border-line")}>
            <div className="min-w-0">
              <RadixDialog.Title className="text-lg font-semibold text-ink">{title}</RadixDialog.Title>
              {description && <RadixDialog.Description className="mt-1 text-sm text-muted">{description}</RadixDialog.Description>}
            </div>
            <RadixDialog.Close
              aria-label={t("common.close")}
              className="-mr-2 inline-flex h-8 w-8 items-center justify-center rounded-control text-muted hover:bg-brand-50 hover:text-ink"
            >
              <X className="h-4 w-4" aria-hidden="true" />
            </RadixDialog.Close>
          </div>
          {children && <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">{children}</div>}
          {footer && <div className={clsx("flex flex-wrap justify-end gap-2 px-6 py-4", children ? "border-t border-line" : "pt-1")}>{footer}</div>}
        </RadixDialog.Content>
      </RadixDialog.Portal>
    </RadixDialog.Root>
  );
}

/** "Are you sure?" with, when the backend keeps a reason, a reason field that must be filled in.
 * onConfirm returns a promise: the dialog stays open and busy until it settles, and closes only on success. */
export function ConfirmDialog({ open, onOpenChange, title, description, confirmLabel, onConfirm, tone = "primary",
  reason, children }: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: ReactNode;
  description?: ReactNode;
  confirmLabel: string;
  onConfirm: (reason: string) => Promise<unknown>;
  tone?: "primary" | "danger";
  reason?: { label: string; required: boolean; placeholder?: string; requiredMessage: string };
  children?: ReactNode;
}) {
  const { t } = useI18n();
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const fieldId = useId();

  useEffect(() => {
    if (open) {
      setText("");
      setError(null);
    }
  }, [open]);

  const confirm = async () => {
    if (reason?.required && !text.trim()) {
      setError(reason.requiredMessage);
      return;
    }
    setBusy(true);
    try {
      await onConfirm(text.trim());
      onOpenChange(false);
    } catch {
      // the caller already reported the failure; the dialog stays open so nothing typed is lost
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => !busy && onOpenChange(next)}
      title={title}
      description={description}
      footer={
        <>
          <Button onClick={() => onOpenChange(false)} disabled={busy}>{t("common.cancel")}</Button>
          <Button variant={tone === "danger" ? "danger" : "primary"} onClick={confirm} loading={busy}>{confirmLabel}</Button>
        </>
      }
    >
      {children || reason ? (
        <>
          {children}
          {reason && (
            <TextArea
              id={fieldId}
              label={reason.label}
              required={reason.required}
              value={text}
              placeholder={reason.placeholder}
              onChange={(event) => {
                setText(event.target.value);
                if (error) setError(null);
              }}
              error={error}
              rows={3}
              autoFocus
            />
          )}
        </>
      ) : undefined}
    </Dialog>
  );
}

/** The confirmation that an important action went through: a centred dialog over a blurred page, with what
 * happened and the two next steps (see the result, or go back home). Closing it keeps the current page. */
export function SuccessDialog({ open, onOpenChange, title, text, primary, secondary }: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  text: ReactNode;
  primary: { label: string; onClick: () => void };
  secondary?: { label: string; onClick: () => void };
}) {
  const { t } = useI18n();
  return (
    <RadixDialog.Root open={open} onOpenChange={onOpenChange}>
      <RadixDialog.Portal>
        <RadixDialog.Overlay className="fixed inset-0 z-40 bg-ink/30 backdrop-blur-md animate-fade-in" />
        <RadixDialog.Content
          aria-describedby={undefined}
          className="fixed left-1/2 top-1/2 z-50 w-[calc(100vw-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-[20px] border border-line bg-surface px-6 pb-6 pt-8 text-center shadow-pop animate-scale-in focus:outline-none"
        >
          <RadixDialog.Close aria-label={t("common.close")}
                             className="absolute right-3 top-3 inline-flex h-8 w-8 items-center justify-center rounded-control text-muted hover:bg-brand-50 hover:text-ink">
            <X className="h-4 w-4" aria-hidden="true" />
          </RadixDialog.Close>
          <span className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-success-soft ring-8 ring-success-soft/40">
            <CheckCircle2 className="h-7 w-7 text-success" aria-hidden="true" />
          </span>
          <RadixDialog.Title className="mt-5 text-xl font-semibold text-ink">{title}</RadixDialog.Title>
          <div className="mt-2 text-sm leading-relaxed text-muted">{text}</div>
          <div className="mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-center">
            {secondary && <Button onClick={secondary.onClick}>{secondary.label}</Button>}
            <Button variant="primary" onClick={primary.onClick} autoFocus>{primary.label}</Button>
          </div>
        </RadixDialog.Content>
      </RadixDialog.Portal>
    </RadixDialog.Root>
  );
}
