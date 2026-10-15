import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import * as RadixToast from "@radix-ui/react-toast";
import { clsx } from "clsx";
import { AlertTriangle, CheckCircle2, Info, X } from "lucide-react";
import { useI18n } from "@/i18n/I18nProvider";

type ToastTone = "success" | "error" | "warning" | "info";

interface ToastItem {
  id: number;
  tone: ToastTone;
  title: string;
  text?: string;
  action?: { label: string; onClick: () => void };
}

type Notify = (toast: Omit<ToastItem, "id">) => void;

const ToastContext = createContext<Notify | null>(null);

const ICONS: Record<ToastTone, ReactNode> = {
  success: <CheckCircle2 className="h-5 w-5 text-success" aria-hidden="true" />,
  error: <AlertTriangle className="h-5 w-5 text-danger" aria-hidden="true" />,
  warning: <AlertTriangle className="h-5 w-5 text-warning" aria-hidden="true" />,
  info: <Info className="h-5 w-5 text-info" aria-hidden="true" />,
};

/** Short feedback after an action: what happened, and at most one next step. Read by screen readers. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const { t } = useI18n();
  const [items, setItems] = useState<ToastItem[]>([]);
  const notify = useCallback<Notify>((toast) => {
    setItems((current) => [...current, { ...toast, id: Date.now() + Math.random() }]);
  }, []);
  const remove = (id: number) => setItems((current) => current.filter((item) => item.id !== id));
  const value = useMemo(() => notify, [notify]);

  return (
    <ToastContext.Provider value={value}>
      <RadixToast.Provider swipeDirection="right" duration={6000}>
        {children}
        {items.map((item) => (
          <RadixToast.Root
            key={item.id}
            type={item.tone === "error" ? "foreground" : "background"}
            duration={item.tone === "error" || item.action ? 10000 : 5000}
            onOpenChange={(open) => !open && remove(item.id)}
            className={clsx(
              "flex w-full items-start gap-3 rounded-card border border-line bg-surface p-4 shadow-pop animate-fade-up",
              "data-[swipe=end]:animate-fade-in",
            )}
          >
            {ICONS[item.tone]}
            <div className="min-w-0 flex-1">
              <RadixToast.Title className="text-sm font-semibold text-ink">{item.title}</RadixToast.Title>
              {item.text && <RadixToast.Description className="mt-0.5 text-sm text-muted">{item.text}</RadixToast.Description>}
              {item.action && (
                <RadixToast.Action altText={item.action.label} asChild>
                  <button type="button" onClick={item.action.onClick} className="mt-2 text-sm font-semibold text-brand-700 hover:underline">
                    {item.action.label}
                  </button>
                </RadixToast.Action>
              )}
            </div>
            <RadixToast.Close aria-label={t("common.close")} className="text-muted hover:text-ink">
              <X className="h-4 w-4" aria-hidden="true" />
            </RadixToast.Close>
          </RadixToast.Root>
        ))}
        <RadixToast.Viewport className="fixed right-4 top-4 z-[60] flex w-[min(380px,calc(100vw-2rem))] flex-col gap-2 outline-none" />
      </RadixToast.Provider>
    </ToastContext.Provider>
  );
}

export function useToast(): Notify {
  const context = useContext(ToastContext);
  if (!context) throw new Error("useToast is used outside ToastProvider");
  return context;
}
