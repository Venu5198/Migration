import React, { useEffect, useState } from 'react';
import { Database, Key, Shield, ShieldCheck, User } from 'lucide-react';
import { apiClient } from '../../api/client';
import { useAuth } from '../../context/AuthContext';
import { HealthResponse } from '../../types';
import { Badge } from '../common/Badge';
import { Button } from '../common/Button';
import { Modal } from '../common/Modal';

export const Navbar: React.FC = () => {
  const { session, setSession, isCustomToken, logout } = useAuth();
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [isAuthModalOpen, setIsAuthModalOpen] = useState(false);
  const [inputToken, setInputToken] = useState(session.token || '');
  const [inputSubject, setInputSubject] = useState(session.subject || 'developer');
  const [inputRoles, setInputRoles] = useState(session.roles.join(', '));

  const checkHealth = async () => {
    try {
      const res = await apiClient.getHealth();
      setHealth(res);
    } catch {
      setHealth({ status: 'degraded', database: 'not_configured_or_unavailable', equus_writes: 'disabled' });
    }
  };

  useEffect(() => {
    checkHealth();
    const interval = setInterval(checkHealth, 30000);
    return () => clearInterval(interval);
  }, []);

  const handleSaveAuth = (e: React.FormEvent) => {
    e.preventDefault();
    const rolesArray = inputRoles
      .split(',')
      .map((r) => r.trim())
      .filter(Boolean);
    setSession({
      token: inputToken.trim(),
      subject: inputSubject.trim() || 'user',
      roles: rolesArray.length > 0 ? rolesArray : ['viewer'],
    });
    setIsAuthModalOpen(false);
  };

  const handlePreset = (preset: { subject: string; token: string; roles: string[] }) => {
    setInputSubject(preset.subject);
    setInputToken(preset.token);
    setInputRoles(preset.roles.join(', '));
  };

  return (
    <>
      <header className="h-16 bg-white border-b border-slate-200 px-6 flex items-center justify-between sticky top-0 z-40">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded bg-blue-900 text-white flex items-center justify-center font-bold text-sm tracking-wide">
              EM
            </div>
            <div>
              <span className="font-semibold text-slate-900 tracking-tight text-sm">
                Excel Migration Platform
              </span>
              <span className="ml-2 text-xs text-slate-400 font-mono">v0.1.0</span>
            </div>
          </div>

          <div className="h-5 w-px bg-slate-200 mx-1 hidden sm:block" />

          {/* Safety & Health Badges */}
          <div className="hidden md:flex items-center gap-2 text-xs">
            <span
              className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border ${
                health?.database === 'connected'
                  ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                  : 'bg-amber-50 text-amber-700 border-amber-200'
              }`}
            >
              <Database className="w-3.5 h-3.5" />
              {health?.database === 'connected' ? 'MongoDB Connected' : 'DB Degraded'}
            </span>

            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-rose-50 text-rose-800 border border-rose-200">
              <ShieldCheck className="w-3.5 h-3.5 text-rose-600" />
              Equus Writes: Disabled (Safe Mode)
            </span>
          </div>
        </div>

        {/* User and Role Indicator */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2.5 bg-slate-50 border border-slate-200 rounded-md px-3 py-1.5">
            <User className="w-4 h-4 text-slate-500" />
            <div className="text-left text-xs">
              <div className="font-semibold text-slate-800 leading-none">{session.subject}</div>
              <div className="text-[10px] text-slate-500 mt-0.5 capitalize">
                {session.roles.slice(0, 2).join(', ')}
                {session.roles.length > 2 && ` +${session.roles.length - 2}`}
              </div>
            </div>
          </div>

          <Button
            variant="outline"
            size="sm"
            icon={<Key className="w-3.5 h-3.5 text-blue-700" />}
            onClick={() => setIsAuthModalOpen(true)}
            title="Configure Authentication Token & Roles"
          >
            {isCustomToken ? 'Switch Token' : 'Auth / Roles'}
          </Button>
        </div>
      </header>

      {/* Auth / Role Switcher Modal */}
      <Modal
        isOpen={isAuthModalOpen}
        onClose={() => setIsAuthModalOpen(false)}
        title="Authentication & Role Simulator"
      >
        <form onSubmit={handleSaveAuth} className="space-y-4">
          <p className="text-xs text-slate-600 leading-relaxed">
            Configure Bearer credentials or test separation-of-duties role enforcement. In development mode without backend auth tokens configured, any subject/role can be simulated locally.
          </p>

          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1">
              Actor Subject (Username / ID)
            </label>
            <input
              type="text"
              value={inputSubject}
              onChange={(e) => setInputSubject(e.target.value)}
              className="w-full text-sm px-3 py-2 border border-slate-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:outline-none"
              placeholder="e.g. data_architect_1"
              required
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1">
              Roles (comma separated: viewer, executor, approver, admin)
            </label>
            <input
              type="text"
              value={inputRoles}
              onChange={(e) => setInputRoles(e.target.value)}
              className="w-full text-sm px-3 py-2 border border-slate-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:outline-none"
              placeholder="e.g. executor, viewer"
              required
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1">
              Bearer Token (Optional if MIGRATION_AUTH_REQUIRED=false)
            </label>
            <input
              type="password"
              value={inputToken}
              onChange={(e) => setInputToken(e.target.value)}
              className="w-full text-sm px-3 py-2 border border-slate-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:outline-none font-mono"
              placeholder="Leave empty for local dev fallback"
            />
          </div>

          <div className="pt-2">
            <span className="text-xs font-medium text-slate-500 block mb-2">Quick Presets:</span>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() =>
                  handlePreset({
                    subject: 'executor_user',
                    token: '',
                    roles: ['executor', 'viewer'],
                  })
                }
                className="text-xs px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded transition-colors"
              >
                Executor Only
              </button>
              <button
                type="button"
                onClick={() =>
                  handlePreset({
                    subject: 'approver_user',
                    token: '',
                    roles: ['approver', 'viewer'],
                  })
                }
                className="text-xs px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded transition-colors"
              >
                Approver Only
              </button>
              <button
                type="button"
                onClick={() =>
                  handlePreset({
                    subject: 'auditor_admin',
                    token: '',
                    roles: ['admin', 'approver', 'executor', 'viewer'],
                  })
                }
                className="text-xs px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded transition-colors"
              >
                Full Admin
              </button>
            </div>
          </div>

          <div className="flex justify-between items-center pt-4 border-t border-slate-200">
            {isCustomToken ? (
              <Button type="button" variant="ghost" size="sm" onClick={logout}>
                Reset to Dev Default
              </Button>
            ) : (
              <div />
            )}
            <div className="flex gap-2">
              <Button type="button" variant="outline" size="sm" onClick={() => setIsAuthModalOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" variant="primary" size="sm">
                Apply Session
              </Button>
            </div>
          </div>
        </form>
      </Modal>
    </>
  );
};
