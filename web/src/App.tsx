import { lazy, Suspense, type ReactNode } from "react";
import { Route, Routes } from "react-router-dom";
import { RequireAuth, RequireRole } from "@/auth/guards";
import { AppShell } from "@/components/layout/AppShell";
import { SkeletonList } from "@/components/ui/States";
import { LoginPage } from "@/pages/LoginPage";
import { NotFoundPage } from "@/pages/NotFoundPage";
import { HomePage } from "@/pages/home/HomePage";

// Every page but the first ones is loaded when it is opened: the first visit downloads only the shell, the
// login and Home, and the diagrams and charts come with the pages that draw them.
const ProblemsPage = lazy(() => import("@/pages/problems/ProblemsPage").then((m) => ({ default: m.ProblemsPage })));
const ProblemDetailPage = lazy(() => import("@/pages/problems/ProblemDetailPage").then((m) => ({ default: m.ProblemDetailPage })));
const ProposalsPage = lazy(() => import("@/pages/proposals/ProposalsPage").then((m) => ({ default: m.ProposalsPage })));
const InvestigationPage = lazy(() => import("@/pages/investigation/InvestigationPage").then((m) => ({ default: m.InvestigationPage })));
const HistoryPage = lazy(() => import("@/pages/history/HistoryPage").then((m) => ({ default: m.HistoryPage })));
const CasePage = lazy(() => import("@/pages/history/CasePage").then((m) => ({ default: m.CasePage })));
const ReviewQueuePage = lazy(() => import("@/pages/review/ReviewQueuePage").then((m) => ({ default: m.ReviewQueuePage })));
const ReviewPage = lazy(() => import("@/pages/review/ReviewPage").then((m) => ({ default: m.ReviewPage })));
const HowItWorksPage = lazy(() => import("@/pages/guide/HowItWorksPage").then((m) => ({ default: m.HowItWorksPage })));
const KpisPage = lazy(() => import("@/pages/kpis/KpisPage").then((m) => ({ default: m.KpisPage })));

const loading = <div className="pt-2"><SkeletonList rows={4} /></div>;
const pm = (element: ReactNode) => <RequireRole role="problem_manager"><Suspense fallback={loading}>{element}</Suspense></RequireRole>;
const te = (element: ReactNode) => <RequireRole role="technical_expert"><Suspense fallback={loading}>{element}</Suspense></RequireRole>;

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<RequireAuth><AppShell /></RequireAuth>}>
        <Route index element={<HomePage />} />
        <Route path="how-it-works" element={<Suspense fallback={loading}><HowItWorksPage /></Suspense>} />
        <Route path="problems" element={pm(<ProblemsPage />)} />
        <Route path="problems/:problemId" element={pm(<ProblemDetailPage />)} />
        <Route path="proposals" element={pm(<ProposalsPage />)} />
        <Route path="investigation" element={pm(<InvestigationPage />)} />
        <Route path="investigation/:rcaId" element={pm(<InvestigationPage />)} />
        <Route path="history" element={pm(<HistoryPage />)} />
        <Route path="history/:rcaId" element={pm(<CasePage />)} />
        <Route path="kpis" element={pm(<KpisPage />)} />
        <Route path="review" element={te(<ReviewQueuePage />)} />
        <Route path="review/:rcaId" element={te(<ReviewPage />)} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
