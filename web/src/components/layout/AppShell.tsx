import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import * as RadixDialog from "@radix-ui/react-dialog";
import * as Menu from "@radix-ui/react-dropdown-menu";
import { clsx } from "clsx";
import { ChevronsUpDown, LogOut, Menu as MenuIcon, X } from "lucide-react";
import { useAuth, useUser } from "@/auth/AuthProvider";
import { useI18n } from "@/i18n/I18nProvider";
import { NAVIGATION } from "@/lib/navigation";
import { LanguageSwitch } from "./LanguageSwitch";
import { Logo } from "./Logo";

function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  const { t } = useI18n();
  const user = useUser();
  return (
    <nav aria-label={t("nav.label")} className="flex flex-col gap-1">
      {NAVIGATION[user.role].map(({ to, label, icon: Icon }) => (
        <NavLink
          key={to}
          to={to}
          end={to === "/"}
          onClick={onNavigate}
          className={({ isActive }) =>
            clsx(
              "group flex h-10 items-center gap-3 rounded-control px-3 text-sm font-medium transition-colors duration-150",
              isActive ? "bg-white/10 text-white shadow-[inset_3px_0_0_0_rgb(110_231_200)]" : "text-white/70 hover:bg-white/5 hover:text-white",
            )
          }
        >
          <Icon className="h-[18px] w-[18px] shrink-0" aria-hidden="true" />
          {t(label)}
        </NavLink>
      ))}
    </nav>
  );
}

function initials(name: string) {
  return name.split(/[\s._-]+/).filter(Boolean).slice(0, 2).map((part) => part[0]?.toUpperCase()).join("") || "?";
}

/** The user at the bottom of the menu: a click opens the account menu with the language and Log out. */
function UserMenu() {
  const { t } = useI18n();
  const { signOut } = useAuth();
  const user = useUser();
  return (
    <Menu.Root>
      <Menu.Trigger
        aria-label={t("user.menu")}
        className="flex w-full items-center gap-3 rounded-card bg-white/5 p-2.5 text-left text-white transition-colors hover:bg-white/10"
      >
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-emerald-300 to-teal-500 text-sm font-bold text-brand-950">
          {initials(user.username)}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-semibold">{user.username}</span>
          <span className="block truncate text-xs text-white/60">{t(`role.${user.role}`)}</span>
        </span>
        <ChevronsUpDown className="h-4 w-4 shrink-0 text-white/50" aria-hidden="true" />
      </Menu.Trigger>
      <Menu.Portal>
        <Menu.Content side="top" align="start" sideOffset={8}
                      className="z-50 w-[232px] rounded-card border border-line bg-surface p-1.5 shadow-pop animate-scale-in">
          <div className="px-2.5 py-2">
            <p className="text-xs font-medium text-muted">{t("lang.label")}</p>
            <LanguageSwitch className="mt-1.5" />
          </div>
          <Menu.Separator className="my-1 h-px bg-line" />
          <Menu.Item
            onSelect={signOut}
            className="flex h-9 cursor-pointer items-center gap-2 rounded-control px-2.5 text-sm font-medium text-danger outline-none data-[highlighted]:bg-danger-soft"
          >
            <LogOut className="h-4 w-4" aria-hidden="true" />
            {t("user.sign_out")}
          </Menu.Item>
        </Menu.Content>
      </Menu.Portal>
    </Menu.Root>
  );
}

function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const { t } = useI18n();
  return (
    <div className="flex h-full flex-col gap-8 px-4 py-6">
      <NavLink to="/" onClick={onNavigate} className="rounded-control px-2 text-white">
        <Logo name={t("app.name")} className="text-[17px]" markClassName="h-9 w-9 text-emerald-300" />
      </NavLink>
      <div className="flex-1">
        <NavLinks onNavigate={onNavigate} />
      </div>
      <UserMenu />
    </div>
  );
}

/** The frame of every signed-in page: the menu on the left (a drawer on small screens) and the page. */
export function AppShell() {
  const { t } = useI18n();
  const [drawer, setDrawer] = useState(false);
  const location = useLocation();

  useEffect(() => {
    setDrawer(false);
    window.scrollTo({ top: 0 });
  }, [location.pathname]);

  return (
    <div className="min-h-screen lg:pl-[248px]">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[70] focus:rounded-control focus:bg-surface focus:px-4 focus:py-2 focus:shadow-pop">
        {t("nav.skip")}
      </a>
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-[248px] bg-brand-950 lg:block">
        <SidebarContent />
      </aside>

      <header className="sticky top-0 z-20 flex h-14 items-center justify-between border-b border-line bg-surface/90 px-4 backdrop-blur lg:hidden">
        <Logo name={t("app.name")} className="text-[15px] text-brand-800" markClassName="h-7 w-7 text-brand-600" />
        <RadixDialog.Root open={drawer} onOpenChange={setDrawer}>
          <RadixDialog.Trigger aria-label={t("nav.open_menu")}
                               className="inline-flex h-10 w-10 items-center justify-center rounded-control text-ink hover:bg-brand-50">
            <MenuIcon className="h-5 w-5" aria-hidden="true" />
          </RadixDialog.Trigger>
          <RadixDialog.Portal>
            <RadixDialog.Overlay className="fixed inset-0 z-40 bg-ink/40 animate-fade-in" />
            <RadixDialog.Content aria-describedby={undefined}
                                 className="fixed inset-y-0 left-0 z-50 w-[280px] max-w-[85vw] bg-brand-950 shadow-pop animate-fade-in focus:outline-none">
              <RadixDialog.Title className="sr-only">{t("nav.label")}</RadixDialog.Title>
              <RadixDialog.Close aria-label={t("nav.close_menu")}
                                 className="absolute right-3 top-5 inline-flex h-9 w-9 items-center justify-center rounded-control text-white/70 hover:bg-white/10 hover:text-white">
                <X className="h-5 w-5" aria-hidden="true" />
              </RadixDialog.Close>
              <SidebarContent onNavigate={() => setDrawer(false)} />
            </RadixDialog.Content>
          </RadixDialog.Portal>
        </RadixDialog.Root>
      </header>

      <main id="main" tabIndex={-1} className="mx-auto w-full max-w-content px-4 py-6 outline-none sm:px-6 lg:px-10 lg:py-10">
        <Outlet />
      </main>
    </div>
  );
}
