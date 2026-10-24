import React from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { MainLayout } from './components/layout/MainLayout';
import { AuthProvider } from './context/AuthContext';
import { ApprovalsPage } from './pages/ApprovalsPage';
import { AuditPage } from './pages/AuditPage';
import { DashboardPage } from './pages/DashboardPage';
import { JobsPage } from './pages/JobsPage';
import { MappingsPage } from './pages/MappingsPage';
import { MigrationPage } from './pages/MigrationPage';
import { PreviewPage } from './pages/PreviewPage';
import { ProfilingPage } from './pages/ProfilingPage';
import { ReportsPage } from './pages/ReportsPage';
import { SourcesPage } from './pages/SourcesPage';

export const App: React.FC = () => {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<MainLayout />}>
            <Route index element={<DashboardPage />} />
            <Route path="migration" element={<MigrationPage />} />
            <Route path="sources" element={<SourcesPage />} />
            <Route path="profiling" element={<ProfilingPage />} />
            <Route path="mappings" element={<MappingsPage />} />
            <Route path="approvals" element={<ApprovalsPage />} />
            <Route path="preview" element={<PreviewPage />} />
            <Route path="jobs" element={<JobsPage />} />
            <Route path="reports" element={<ReportsPage />} />
            <Route path="audit" element={<AuditPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
};

export default App;
