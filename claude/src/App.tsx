import { Navigate, Route, HashRouter as Router, Routes } from "react-router-dom";
import { ToastProvider } from "./components/Toast";
import TodayPage from "./pages/TodayPage";
import OpportunityDetailPage from "./pages/OpportunityDetailPage";

export default function App() {
  return (
    <Router>
      <ToastProvider>
        <Routes>
          <Route path="/" element={<Navigate to="/today" replace />} />
          <Route path="/today" element={<TodayPage />} />
          <Route path="/opportunity/:id" element={<OpportunityDetailPage />} />
          <Route path="*" element={<Navigate to="/today" replace />} />
        </Routes>
      </ToastProvider>
    </Router>
  );
}
