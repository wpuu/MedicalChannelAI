import { HashRouter, Navigate, Route, Routes } from "react-router-dom";
import { ToastProvider } from "@/context/ToastContext";
import OpportunityDetailPage from "@/pages/OpportunityDetailPage";
import TodayPage from "@/pages/TodayPage";

export default function App() {
  return (
    <HashRouter>
      <ToastProvider>
        <div className="min-h-dvh bg-[#F3F4F2] text-stone-900">
          <Routes>
            <Route path="/" element={<Navigate to="/today" replace />} />
            <Route path="/today" element={<TodayPage />} />
            <Route path="/opportunity/:id" element={<OpportunityDetailPage />} />
            <Route path="*" element={<Navigate to="/today" replace />} />
          </Routes>
        </div>
      </ToastProvider>
    </HashRouter>
  );
}
