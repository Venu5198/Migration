import React, { createContext, useContext, useEffect, useState } from 'react';
import { UserSession } from '../types';

interface AuthContextType {
  session: UserSession;
  setSession: (session: UserSession) => void;
  hasRole: (role: string) => boolean;
  logout: () => void;
  isCustomToken: boolean;
}

const defaultDevSession: UserSession = {
  subject: 'development',
  token: '',
  roles: ['admin', 'approver', 'executor', 'viewer'],
};

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [session, setSessionState] = useState<UserSession>(() => {
    const saved = localStorage.getItem('migration_auth_session');
    if (saved) {
      try {
        return JSON.parse(saved);
      } catch {
        // Fallback to dev session
      }
    }
    return defaultDevSession;
  });

  const setSession = (newSession: UserSession) => {
    setSessionState(newSession);
    if (newSession.token) {
      localStorage.setItem('migration_auth_token', newSession.token);
      localStorage.setItem('migration_auth_session', JSON.stringify(newSession));
    } else {
      localStorage.removeItem('migration_auth_token');
      localStorage.removeItem('migration_auth_session');
    }
  };

  const logout = () => {
    setSession(defaultDevSession);
  };

  const hasRole = (role: string): boolean => {
    return session.roles.includes('admin') || session.roles.includes(role);
  };

  const isCustomToken = Boolean(session.token);

  return (
    <AuthContext.Provider value={{ session, setSession, hasRole, logout, isCustomToken }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
