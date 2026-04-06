import { BrowserRouter, Routes, Route } from "react-router-dom"
import { AppLayout } from "@/components/layout/AppLayout"
import { ProtectedRoute } from "@/components/layout/ProtectedRoute"
import { ErrorBoundary } from "@/components/shared/ErrorBoundary"
import { TooltipProvider } from "@/components/ui/tooltip"
import DashboardPage from "@/pages/DashboardPage"
import ProfilePage from "@/pages/ProfilePage"
import RunsListPage from "@/pages/RunsListPage"
import RunDetailPage from "@/pages/RunDetailPage"
import ResultsPage from "@/pages/OpportunitiesPage"
import CoverLettersPage from "@/pages/CoverLettersPage"
import PoliciesPage from "@/pages/PoliciesPage"
import GuidePage from "@/pages/GuidePage"
import NotFoundPage from "@/pages/NotFoundPage"
import LoginPage from "@/pages/LoginPage"
import RegisterPage from "@/pages/RegisterPage"
import ForgotPasswordPage from "@/pages/ForgotPasswordPage"
import ResetPasswordPage from "@/pages/ResetPasswordPage"
import VerifyEmailPage from "@/pages/VerifyEmailPage"
import AdminPage from "@/pages/AdminPage"

export default function App() {
  return (
    <ErrorBoundary>
      <TooltipProvider delayDuration={0}>
      <BrowserRouter>
        <Routes>
          {/* Public routes (no sidebar) */}
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />
          <Route path="/reset-password" element={<ResetPasswordPage />} />
          <Route path="/verify-email" element={<VerifyEmailPage />} />

          {/* Protected routes (with sidebar) */}
          <Route element={<ProtectedRoute><AppLayout /></ProtectedRoute>}>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/profiles/:profileId" element={<ProfilePage />} />
            <Route path="/profiles/:profileId/runs" element={<RunsListPage />} />
            <Route path="/profiles/:profileId/runs/:runId" element={<RunDetailPage />} />
            <Route path="/profiles/:profileId/results" element={<ResultsPage />} />
            <Route path="/profiles/:profileId/cover-letters" element={<CoverLettersPage />} />
            <Route path="/policies" element={<PoliciesPage />} />
            <Route path="/guide" element={<GuidePage />} />
            <Route path="/admin" element={<ProtectedRoute requireAdmin><AdminPage /></ProtectedRoute>} />
            <Route path="*" element={<NotFoundPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
      </TooltipProvider>
    </ErrorBoundary>
  )
}
