import React, { useState } from 'react';
import { NavLink } from 'react-router-dom';
import {
  BarChart3,
  CheckCircle,
  Eye,
  FileSpreadsheet,
  FileText,
  GitBranch,
  History,
  LayoutDashboard,
  Layers,
  PlayCircle,
  Shield,
  Zap,
} from 'lucide-react';
import { apiClient } from '../../api/client';
import { useAuth } from '../../context/AuthContext';
import { Badge } from '../common/Badge';

export const Sidebar: React.FC = () => {
  const { hasRole } = useAuth();
  const [testingTarget, setTestingTarget] = useState(false);
  const [targetStatus, setTargetStatus] = useState<string | null>(null);

  const navItems = [
    { to: '/', label: 'Dashboard', icon: <LayoutDashboard className="w-4 h-4" /> },
    { to: '/migration', label: 'Topia → Equus Migration', icon: <Layers className="w-4 h-4" /> },
    { to: '/sources', label: 'Workbooks & Sources', icon: <FileSpreadsheet className="w-4 h-4" /> },
    { to: '/profiling', label: 'Data Profiling', icon: <BarChart3 className="w-4 h-4" /> },
    { to: '/mappings', label: 'Field Mapping', icon: <GitBranch className="w-4 h-4" /> },
    { to: '/approvals', label: 'Mapping Approvals', icon: <CheckCircle className="w-4 h-4" /> },
    { to: '/preview', label: 'Transformation Preview', icon: <Eye className="w-4 h-4" /> },
    { to: '/jobs', label: 'Background Jobs', icon: <PlayCircle className="w-4 h-4" /> },
    { to: '/reports', label: 'Reports & Reconciliation', icon: <FileText className="w-4 h-4" /> },
    {
      to: '/audit',
      label: 'Audit Events',
      icon: <History className="w-4 h-4" />,
      adminOnly: true,
    },
  ];

  const handleTestTarget = async () => {
    setTestingTarget(true);
    setTargetStatus(null);
    try {
      const res = await apiClient.testMockTarget();
      setTargetStatus(`${res.target}: Connected (Writes: ${res.writes_allowed ? 'Enabled' : 'Disabled'})`);
    } catch {
      setTargetStatus('Connector check failed');
    } finally {
      setTestingTarget(false);
    }
  };

  return (
    <aside className="w-64 bg-slate-900 text-slate-300 flex flex-col shrink-0 min-h-[calc(100vh-4rem)]">
      {/* Navigation */}
      <nav className="flex-1 px-3 py-4 space-y-1">
        <div className="px-3 pb-2 text-[11px] font-bold uppercase tracking-wider text-slate-400">
          Migration Lifecycle
        </div>

        {navItems.map((item) => {
          if (item.adminOnly && !hasRole('admin')) {
            return null;
          }

          return (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/'}
              className={({ isActive }) =>
                `flex items-center justify-between px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-blue-700 text-white font-semibold'
                    : 'text-slate-300 hover:bg-slate-800 hover:text-white'
                }`
              }
            >
              <div className="flex items-center gap-3">
                {item.icon}
                <span>{item.label}</span>
              </div>
              {item.adminOnly && (
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-700 text-slate-300 uppercase font-mono">
                  Admin
                </span>
              )}
            </NavLink>
          );
        })}
      </nav>

      {/* Target Boundary Card at Bottom */}
      <div className="p-4 border-t border-slate-800 bg-slate-950/40">
        <div className="flex items-center gap-2 mb-2 text-xs font-semibold text-slate-300">
          <Shield className="w-4 h-4 text-amber-400" />
          <span>Equus Target Boundary</span>
        </div>
        <p className="text-[11px] text-slate-400 leading-relaxed mb-3">
          Direct target execution is strictly isolated. All operations run in deterministic preview / dry-run mode.
        </p>

        <button
          onClick={handleTestTarget}
          disabled={testingTarget}
          className="w-full flex items-center justify-center gap-1.5 px-2.5 py-1.5 text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-200 rounded border border-slate-700 transition-colors disabled:opacity-50"
        >
          <Zap className="w-3.5 h-3.5 text-blue-400" />
          {testingTarget ? 'Verifying...' : 'Check Target Boundary'}
        </button>

        {targetStatus && (
          <div className="mt-2 text-[10px] text-slate-400 font-mono bg-slate-900 p-2 rounded border border-slate-800 break-words">
            {targetStatus}
          </div>
        )}
      </div>
    </aside>
  );
};
