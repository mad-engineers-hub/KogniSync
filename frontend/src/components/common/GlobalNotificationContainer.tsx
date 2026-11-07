/**
 * frontend/src/components/common/GlobalNotificationContainer.tsx
 *
 * Reusable application-level notification viewport overlay (Milestone M3.4.1).
 * Features:
 * - Fixed top-of-viewport overlay that never pushes, resizes, or shifts Planner content.
 * - Single-line layout on desktop whenever practical with clean responsive wrapping on mobile.
 * - Small status icons, subtle borders, rounded corners, and restrained elevation.
 * - Dismissible via mouse, touch, keyboard (Enter/Space on button, or global Escape key).
 * - ARIA live-region semantics (role="status" for success/info/warning, role="alert" for error).
 */
import React, { useEffect, useCallback } from 'react';
import { CheckCircle2, AlertCircle, AlertTriangle, Info, X } from 'lucide-react';
import { useNotification, NotificationItem, NotificationType } from '../../context/NotificationContext';

const NOTIFICATION_STYLES: Record<
  NotificationType,
  {
    container: string;
    icon: React.ComponentType<{ className?: string }>;
    iconColor: string;
    role: 'alert' | 'status';
  }
> = {
  success: {
    container:
      'bg-emerald-50/95 text-emerald-900 border-emerald-200/90 shadow-emerald-950/5',
    icon: CheckCircle2,
    iconColor: 'text-emerald-600',
    role: 'status',
  },
  error: {
    container:
      'bg-rose-50/95 text-rose-900 border-rose-200/90 shadow-rose-950/5',
    icon: AlertCircle,
    iconColor: 'text-rose-600',
    role: 'alert',
  },
  warning: {
    container:
      'bg-amber-50/95 text-amber-900 border-amber-200/90 shadow-amber-950/5',
    icon: AlertTriangle,
    iconColor: 'text-amber-600',
    role: 'status',
  },
  info: {
    container:
      'bg-blue-50/95 text-blue-900 border-blue-200/90 shadow-blue-950/5',
    icon: Info,
    iconColor: 'text-blue-600',
    role: 'status',
  },
};

export const NotificationToast: React.FC<{
  item: NotificationItem;
  onDismiss: () => void;
}> = ({ item, onDismiss }) => {
  const config = NOTIFICATION_STYLES[item.type] || NOTIFICATION_STYLES.info;
  const IconComponent = config.icon;

  return (
    <div
      role={config.role}
      className={`flex items-center justify-between gap-2.5 sm:gap-3 px-3.5 py-2.5 sm:px-4 sm:py-2.5 rounded-xl border shadow-md pointer-events-auto backdrop-blur-xs w-full animate-toast-in transition-all duration-200 ${config.container}`}
      data-testid={`notification-toast-${item.type}`}
      data-category={item.category}
    >
      <div className="flex items-center gap-2.5 min-w-0 flex-1">
        <IconComponent className={`w-4 h-4 shrink-0 ${config.iconColor}`} />
        <span className="text-xs sm:text-sm font-medium leading-snug break-words sm:break-normal">
          {item.message}
        </span>
      </div>

      <button
        type="button"
        onClick={onDismiss}
        className="p-1 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-200/50 transition-colors shrink-0 cursor-pointer focus:outline-hidden focus:ring-2 focus:ring-blue-500"
        aria-label="Dismiss notification"
        title="Dismiss notification"
      >
        <X className="w-3.5 h-3.5" />
      </button>
    </div>
  );
};

export const GlobalNotificationContainer: React.FC = () => {
  const { notifications, dismissNotification } = useNotification();

  // Keyboard shortcut: dismiss latest notification on Escape key
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'Escape' && notifications.length > 0) {
        const latest = notifications[notifications.length - 1];
        dismissNotification(latest.id);
      }
    },
    [notifications, dismissNotification]
  );

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

  if (notifications.length === 0) return null;

  return (
    <div
      className="fixed top-3 sm:top-4 left-1/2 -translate-x-1/2 z-[60] w-full max-w-[calc(100vw-2rem)] sm:max-w-xl md:max-w-2xl px-2 flex flex-col items-center pointer-events-none gap-2"
      aria-live="polite"
      aria-atomic="true"
      data-testid="global-notification-container"
    >
      {notifications.map((item) => (
        <NotificationToast
          key={item.id}
          item={item}
          onDismiss={() => dismissNotification(item.id)}
        />
      ))}
    </div>
  );
};
