import { useRef, useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { CheckCircle2, Eye, EyeOff, Info, Sparkles } from "lucide-react";
import { ApiError } from "@/api/client";
import { UnknownRoleError, useAuth } from "@/auth/AuthProvider";
import { useI18n } from "@/i18n/I18nProvider";
import { Button } from "@/components/ui/Button";
import { TextInput } from "@/components/ui/Field";
import { LanguageSwitch } from "@/components/layout/LanguageSwitch";
import { Logo, LogoMark } from "@/components/layout/Logo";

/** Where to go after signing in: the page the person asked for, if it is a page of this app. */
function nextPath(search: string): string {
  const next = new URLSearchParams(search).get("next");
  return next && next.startsWith("/") && !next.startsWith("//") && next !== "/login" ? next : "/";
}

function BrandPanel() {
  const { t } = useI18n();
  const points = ["login.brand_point_1", "login.brand_point_2", "login.brand_point_3"] as const;
  return (
    <section className="relative hidden overflow-hidden bg-brand-950 text-white lg:flex lg:flex-col lg:justify-between lg:p-12">
      {/* the subtle geometric background of the SaleSkip example: soft rings and a large mark */}
      <div aria-hidden="true" className="pointer-events-none absolute inset-0">
        <div className="absolute -left-24 -top-24 h-80 w-80 rounded-full border border-white/10" />
        <div className="absolute -left-10 -top-10 h-52 w-52 rounded-full border border-white/10" />
        <div className="absolute -bottom-32 -right-20 h-[420px] w-[420px] rounded-full bg-sky-400/10 blur-2xl" />
        <LogoMark className="absolute -bottom-16 -right-10 h-[380px] w-[380px] text-white/[0.04]" />
      </div>
      <Logo name={t("app.name")} className="relative text-lg" markClassName="h-10 w-10 text-sky-300" />
      <div className="relative max-w-md">
        <h2 className="text-[34px] font-semibold leading-tight tracking-tight">{t("login.brand_title")}</h2>
        <p className="mt-4 text-[15px] leading-relaxed text-white/75">{t("login.brand_text")}</p>
        <ul className="mt-8 flex flex-col gap-3">
          {points.map((key, index) => (
            <li key={key} className="flex items-center gap-3 text-sm text-white/90 animate-fade-up"
                style={{ animationDelay: `${150 + index * 120}ms` }}>
              <CheckCircle2 className="h-5 w-5 shrink-0 text-sky-300" aria-hidden="true" />
              {t(key)}
            </li>
          ))}
        </ul>
      </div>
      <p className="relative text-xs text-white/75">{t("app.tagline")}</p>
    </section>
  );
}

export function LoginPage() {
  const { t } = useI18n();
  const { user, signIn, sessionEnded } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [errors, setErrors] = useState<{ username?: string; password?: string }>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const usernameRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);

  if (user) return <Navigate to={nextPath(location.search)} replace />;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const found = {
      username: username.trim() ? undefined : t("login.required_username"),
      password: password ? undefined : t("login.required_password"),
    };
    setErrors(found);
    setFailure(null);
    if (found.username) return usernameRef.current?.focus();
    if (found.password) return passwordRef.current?.focus();
    setBusy(true);
    try {
      await signIn(username.trim(), password);
      navigate(nextPath(location.search), { replace: true });
    } catch (error) {
      if (error instanceof UnknownRoleError) setFailure(t("login.unknown_role"));
      else if (error instanceof ApiError && error.status === 401) setFailure(t("login.wrong"));
      else setFailure(t("login.unreachable"));
      setPassword("");
      passwordRef.current?.focus();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid min-h-screen bg-surface lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)]">
      <BrandPanel />
      <section className="relative flex flex-col px-6 py-8 sm:px-12">
        <div className="flex items-center justify-between lg:justify-end">
          <Logo name={t("app.name")} className="text-[15px] text-brand-800 lg:hidden" markClassName="h-8 w-8 text-brand-600" />
          <LanguageSwitch />
        </div>
        <div className="flex flex-1 items-center justify-center py-10">
          <div className="w-full max-w-[380px] animate-fade-up">
            <div className="mb-6 inline-flex h-12 w-12 items-center justify-center rounded-full bg-brand-100 text-brand-700">
              <Sparkles className="h-6 w-6" aria-hidden="true" />
            </div>
            <h1 className="text-[32px] font-semibold tracking-tight text-ink">{t("login.welcome")}</h1>
            <p className="mt-2 text-[15px] text-muted">{t("login.intro")}</p>

            {sessionEnded && !failure && (
              <p role="status" className="mt-6 flex items-start gap-2 rounded-control bg-info-soft px-3 py-2.5 text-sm text-info">
                <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
                {t("login.session_ended")}
              </p>
            )}
            {failure && (
              <p role="alert" className="mt-6 rounded-control bg-danger-soft px-3 py-2.5 text-sm font-medium text-danger">{failure}</p>
            )}

            <form onSubmit={submit} noValidate className="mt-8 flex flex-col gap-5">
              <TextInput
                ref={usernameRef}
                label={t("login.username")}
                name="username"
                autoComplete="username"
                autoFocus
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                error={errors.username}
                disabled={busy}
              />
              <TextInput
                ref={passwordRef}
                label={t("login.password")}
                name="password"
                type={showPassword ? "text" : "password"}
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                error={errors.password}
                disabled={busy}
                trailing={
                  <button
                    type="button"
                    onClick={() => setShowPassword((value) => !value)}
                    aria-label={showPassword ? t("login.hide_password") : t("login.show_password")}
                    aria-pressed={showPassword}
                    className="inline-flex h-8 w-8 items-center justify-center rounded-control text-muted hover:bg-brand-50 hover:text-ink"
                  >
                    {showPassword ? <EyeOff className="h-4 w-4" aria-hidden="true" /> : <Eye className="h-4 w-4" aria-hidden="true" />}
                  </button>
                }
              />
              <Button type="submit" variant="primary" loading={busy} className="mt-2 h-11 w-full text-[15px]">
                {busy ? t("login.submitting") : t("login.submit")}
              </Button>
            </form>
          </div>
        </div>
      </section>
    </div>
  );
}
