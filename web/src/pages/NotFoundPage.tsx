import { Link } from "react-router-dom";
import { Compass } from "lucide-react";
import { EmptyState } from "@/components/ui/States";
import { useI18n } from "@/i18n/I18nProvider";

export function NotFoundPage() {
  const { t } = useI18n();
  return (
    <EmptyState
      icon={<Compass className="h-6 w-6" aria-hidden="true" />}
      title={t("error.not_found")}
      action={<Link to="/" className="font-semibold text-brand-700 hover:underline">{t("error.go_home")}</Link>}
    />
  );
}
