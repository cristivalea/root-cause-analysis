import { Link } from "react-router-dom";
import { ArrowLeft, BookCheck, ClipboardCheck, FileSearch, Lightbulb, ListChecks, Microscope, PlayCircle, Search, Send } from "lucide-react";
import { useUser } from "@/auth/AuthProvider";
import { useI18n } from "@/i18n/I18nProvider";
import { PageHeader } from "@/components/ui/Card";
import { Pill } from "@/components/ui/Pills";
import { DiagramFrame } from "@/components/rca/DiagramFrame";
import { FiveWhysDiagram } from "@/components/rca/FiveWhysDiagram";
import { Claims, ProcessSteps, type Step } from "@/pages/home/HomeParts";

const PM_STEPS: Step[] = [
  { title: "home.pm.step1.title", text: "home.pm.step1.text", icon: Lightbulb },
  { title: "home.pm.step2.title", text: "home.pm.step2.text", icon: PlayCircle },
  { title: "home.pm.step3.title", text: "home.pm.step3.text", icon: Search },
  { title: "home.pm.step4.title", text: "home.pm.step4.text", icon: ListChecks },
  { title: "home.pm.step5.title", text: "home.pm.step5.text", icon: Send },
];

const TE_STEPS: Step[] = [
  { title: "home.te.step1.title", text: "home.te.step1.text", icon: ClipboardCheck },
  { title: "home.te.step2.title", text: "home.te.step2.text", icon: Microscope },
  { title: "home.te.step3.title", text: "home.te.step3.text", icon: FileSearch },
  { title: "home.te.step4.title", text: "home.te.step4.text", icon: BookCheck },
];

/** "Move from symptoms toward explanations", with a small labelled example of a 5 Whys diagram. */
function Symptoms() {
  const { t } = useI18n();
  const evidence = (id: string, label: string) => [{ id, label }];
  return (
    <section aria-labelledby="symptoms-title" className="grid grid-cols-[minmax(0,1fr)] items-center gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
      <div>
        <h2 id="symptoms-title" className="text-xl font-semibold tracking-tight text-ink">{t("home.symptoms_title")}</h2>
        <p className="mt-3 max-w-lg text-[15px] leading-relaxed text-muted">{t("home.symptoms_text")}</p>
      </div>
      <div className="relative">
        <Pill tone="brand" className="absolute left-3 top-3 z-10">{t("home.example")}</Pill>
        <DiagramFrame label={t("diagram.example_label")} maxHeight={540} className="bg-surface">
          <FiveWhysDiagram
            problem={t("home.example_problem")}
            steps={[
              { text: t("home.example_why1"), evidence: evidence("1", t("home.example_ev1")) },
              { text: t("home.example_why3"), evidence: evidence("3", t("home.example_ev3")) },
            ]}
            root={t("home.example_root")}
            rootLabel={t("diagram.root_cause")}
          />
        </DiagramFrame>
      </div>
    </section>
  );
}

/** The short explanation of the application, opened from Home: the steps of the signed-in role, the idea
 * behind an analysis with an example, and the principles every analysis follows. Home keeps only the actions. */
export function HowItWorksPage() {
  const { t } = useI18n();
  const user = useUser();
  const manager = user.role === "problem_manager";
  return (
    <>
      <Link to="/" className="mb-4 inline-flex items-center gap-1.5 text-sm font-medium text-muted hover:text-ink">
        <ArrowLeft className="h-4 w-4" aria-hidden="true" />{t("success.home")}
      </Link>
      <PageHeader title={t("guide.title")} subtitle={t("guide.subtitle")} />
      <div className="flex flex-col gap-12">
        {manager
          ? <ProcessSteps title="home.how_title" subtitle="home.how_sub" steps={PM_STEPS} />
          : <ProcessSteps title="home.te.how_title" steps={TE_STEPS} />}
        <Symptoms />
        <Claims />
      </div>
    </>
  );
}
