import { Navigate, Route, Routes } from 'react-router-dom';

import { AppShell } from './components/AppShell';
import { DailyReportPage } from './pages/DailyReportPage';
import { PaperExplorePage } from './pages/PaperExplorePage';
import { SettingsPage } from './pages/SettingsPage';

export default function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/daily-report" element={<DailyReportPage />} />
        <Route path="/paper-explore" element={<PaperExplorePage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/daily-report" replace />} />
      </Routes>
    </AppShell>
  );
}
