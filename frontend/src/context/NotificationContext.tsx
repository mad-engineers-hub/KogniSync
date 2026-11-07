/**
 * frontend/src/context/NotificationContext.tsx
 *
 * Reusable application-level notification system (Milestone M3.4.1).
 * Supports success, error, warning, and info notifications with:
 * - Top-of-viewport overlay presentation (zero layout shift).
 * - Auto-dismiss for transient success toasts (4.5s).
 * - Persistent error toasts with explicit dismiss control.
 * - Deduplication for identical repeated errors.
 * - Category-based replacement (e.g. new GPS success replaces obsolete GPS errors).
 * - ARIA live-region accessibility.
 */
import React, { createContext, useContext, useState, useCallback, useRef, useEffect } from 'react';

export type NotificationType = 'success' | 'error' | 'warning' | 'info';

export interface NotificationItem {
  id: string;
  type: NotificationType;
  message: string;
  duration?: number; // ms. If 0 or undefined, remains until dismissed.
  category?: string; // e.g. 'gps' to allow category-level deduplication / replacement.
  createdAt: number;
}

export interface ShowNotificationOptions {
  id?: string;
  type?: NotificationType;
  category?: string;
  duration?: number;
}

export interface NotificationContextType {
  notifications: NotificationItem[];
  showNotification: (message: string, options?: ShowNotificationOptions) => string;
  showSuccess: (message: string, options?: Omit<ShowNotificationOptions, 'type'>) => string;
  showError: (message: string, options?: Omit<ShowNotificationOptions, 'type'>) => string;
  showWarning: (message: string, options?: Omit<ShowNotificationOptions, 'type'>) => string;
  showInfo: (message: string, options?: Omit<ShowNotificationOptions, 'type'>) => string;
  dismissNotification: (id: string) => void;
  dismissCategory: (category: string) => void;
  clearAll: () => void;
}

const defaultContextValue: NotificationContextType = {
  notifications: [],
  showNotification: () => '',
  showSuccess: () => '',
  showError: () => '',
  showWarning: () => '',
  showInfo: () => '',
  dismissNotification: () => {},
  dismissCategory: () => {},
  clearAll: () => {},
};

export const NotificationContext = createContext<NotificationContextType>(defaultContextValue);

export const useNotification = () => useContext(NotificationContext);

let idCounter = 0;

export const NotificationProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const timersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

  const clearTimer = useCallback((id: string) => {
    const timer = timersRef.current.get(id);
    if (timer) {
      clearTimeout(timer);
      timersRef.current.delete(id);
    }
  }, []);

  const dismissNotification = useCallback(
    (id: string) => {
      clearTimer(id);
      setNotifications((prev) => prev.filter((item) => item.id !== id));
    },
    [clearTimer]
  );

  const dismissCategory = useCallback(
    (category: string) => {
      setNotifications((prev) => {
        const remaining: NotificationItem[] = [];
        for (const item of prev) {
          if (item.category === category) {
            clearTimer(item.id);
          } else {
            remaining.push(item);
          }
        }
        return remaining;
      });
    },
    [clearTimer]
  );

  const clearAll = useCallback(() => {
    timersRef.current.forEach((timer) => clearTimeout(timer));
    timersRef.current.clear();
    setNotifications([]);
  }, []);

  const showNotification = useCallback(
    (message: string, options?: ShowNotificationOptions): string => {
      const type: NotificationType = options?.type || 'info';
      const category = options?.category;
      // Default duration: 4500ms for success, 0 (persistent until dismissed) for error/warning/info
      const duration =
        options?.duration !== undefined
          ? options.duration
          : type === 'success'
          ? 4500
          : 0;

      let notificationId = options?.id || `notif-${Date.now()}-${++idCounter}`;

      setNotifications((prev) => {
        // 1. Duplicate check: if identical message + type already exists, do not duplicate
        const existingDuplicate = prev.find(
          (item) => item.type === type && item.message === message
        );
        if (existingDuplicate) {
          notificationId = existingDuplicate.id;
          // Refresh timer if applicable
          if (duration > 0) {
            clearTimer(existingDuplicate.id);
            const timer = setTimeout(() => {
              dismissNotification(existingDuplicate.id);
            }, duration);
            timersRef.current.set(existingDuplicate.id, timer);
          }
          return prev;
        }

        // 2. Category replacement: if category is specified (e.g. 'gps'), replace any older notifications of same category
        let cleaned = prev;
        if (category) {
          cleaned = prev.filter((item) => {
            if (item.category === category) {
              clearTimer(item.id);
              return false;
            }
            return true;
          });
        }

        const newItem: NotificationItem = {
          id: notificationId,
          type,
          message,
          duration,
          category,
          createdAt: Date.now(),
        };

        // 3. Set auto-dismiss timer if duration > 0
        if (duration > 0) {
          const timer = setTimeout(() => {
            dismissNotification(notificationId);
          }, duration);
          timersRef.current.set(notificationId, timer);
        }

        return [...cleaned, newItem];
      });

      return notificationId;
    },
    [clearTimer, dismissNotification]
  );

  const showSuccess = useCallback(
    (message: string, options?: Omit<ShowNotificationOptions, 'type'>) =>
      showNotification(message, { ...options, type: 'success' }),
    [showNotification]
  );

  const showError = useCallback(
    (message: string, options?: Omit<ShowNotificationOptions, 'type'>) =>
      showNotification(message, { ...options, type: 'error' }),
    [showNotification]
  );

  const showWarning = useCallback(
    (message: string, options?: Omit<ShowNotificationOptions, 'type'>) =>
      showNotification(message, { ...options, type: 'warning' }),
    [showNotification]
  );

  const showInfo = useCallback(
    (message: string, options?: Omit<ShowNotificationOptions, 'type'>) =>
      showNotification(message, { ...options, type: 'info' }),
    [showNotification]
  );

  // Clean up all timers on unmount
  useEffect(() => {
    const currentTimers = timersRef.current;
    return () => {
      currentTimers.forEach((timer) => clearTimeout(timer));
      currentTimers.clear();
    };
  }, []);

  return (
    <NotificationContext.Provider
      value={{
        notifications,
        showNotification,
        showSuccess,
        showError,
        showWarning,
        showInfo,
        dismissNotification,
        dismissCategory,
        clearAll,
      }}
    >
      {children}
    </NotificationContext.Provider>
  );
};
