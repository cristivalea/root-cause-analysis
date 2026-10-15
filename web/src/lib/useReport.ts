import { useCallback } from "react";
import { ApiError } from "@/api/client";
import { useI18n } from "@/i18n/I18nProvider";
import type { MessageKey } from "@/i18n/en";
import { useToast } from "@/components/ui/Toast";

/** Feedback after a change: success, the warnings the server returned, or why it refused. A refusal of a
 * business rule (400/409) carries a message written for the user by rca/problems.py or rca/store.py. */
export function useReport() {
  const { t } = useI18n();
  const notify = useToast();

  const failure = useCallback(
    (error: unknown, title: MessageKey = "problem.change_failed") => {
      const text = error instanceof ApiError
        ? error.unreachable ? t("login.unreachable") : error.detail
        : String(error);
      notify({ tone: "error", title: t(title), text });
    },
    [notify, t],
  );

  const success = useCallback(
    (title: string, warnings: string[] = [], action?: { label: string; onClick: () => void }, warningsOnly = false) => {
      // warningsOnly: the success itself is shown elsewhere (a confirmation dialog); only the warnings are added
      if (!warningsOnly) notify({ tone: "success", title, action });
      for (const warning of warnings) notify({ tone: "warning", title: t("problem.warning"), text: warning });
    },
    [notify, t],
  );

  return { success, failure };
}
