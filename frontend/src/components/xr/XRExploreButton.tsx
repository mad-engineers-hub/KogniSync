import React from 'react';
import { Link } from 'react-router-dom';
import { Eye, Compass, Sparkles } from 'lucide-react';

interface XRExploreButtonProps {
  sceneId: string;
  label?: string;
  variant?: 'pill' | 'card' | 'outline';
  className?: string;
}

export const XRExploreButton: React.FC<XRExploreButtonProps> = ({
  sceneId,
  label = 'Explore in 360° & AR',
  variant = 'pill',
  className = '',
}) => {
  if (variant === 'card') {
    return (
      <Link
        to={`/xr/${sceneId}`}
        className={`flex items-center justify-between p-3.5 rounded-2xl bg-gradient-to-r from-blue-900/20 via-indigo-900/10 to-slate-900/30 border border-blue-500/30 hover:border-blue-500/60 hover:shadow-md transition-all group ${className}`}
      >
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-xl bg-blue-600 text-white shadow-sm shadow-blue-500/20 group-hover:scale-110 transition-transform">
            <Eye className="w-4 h-4" />
          </div>
          <div>
            <div className="text-[10px] font-mono uppercase font-bold tracking-wider text-blue-600 dark:text-blue-400">
              Interactive Spatial Preview
            </div>
            <div className="text-xs sm:text-sm font-bold text-slate-900 group-hover:text-blue-600 transition-colors">
              {label}
            </div>
          </div>
        </div>
        <div className="px-2.5 py-1 rounded-lg bg-blue-50 text-blue-700 font-semibold text-xs border border-blue-200">
          Open 360°
        </div>
      </Link>
    );
  }

  if (variant === 'outline') {
    return (
      <Link
        to={`/xr/${sceneId}`}
        className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-blue-300 bg-blue-50/80 hover:bg-blue-100 text-blue-700 text-xs font-semibold shadow-2xs transition-all active:scale-95 ${className}`}
      >
        <Compass className="w-3.5 h-3.5 text-blue-600 animate-spin-slow" />
        <span>{label}</span>
      </Link>
    );
  }

  return (
    <Link
      to={`/xr/${sceneId}`}
      className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-blue-600 hover:bg-blue-700 text-white text-[11px] font-mono font-medium shadow-xs transition-all hover:scale-105 ${className}`}
    >
      <Sparkles className="w-3 h-3 text-amber-300" />
      <span>{label}</span>
    </Link>
  );
};
