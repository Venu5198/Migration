import React from 'react';
import { FolderOpen } from 'lucide-react';

interface EmptyStateProps {
  icon?: React.ReactNode;
  title: string;
  description: string;
  action?: React.ReactNode;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  icon = <FolderOpen className="w-10 h-10 text-slate-400" />,
  title,
  description,
  action,
}) => {
  return (
    <div className="py-12 px-4 text-center flex flex-col items-center justify-center">
      <div className="p-3 bg-slate-100 rounded-full mb-3 text-slate-500">{icon}</div>
      <h3 className="text-base font-semibold text-slate-800">{title}</h3>
      <p className="text-sm text-slate-500 max-w-sm mt-1 mb-4 leading-relaxed">{description}</p>
      {action && <div>{action}</div>}
    </div>
  );
};
