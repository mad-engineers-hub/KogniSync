const BACKEND_URL = (typeof import.meta !== 'undefined' && import.meta.env?.VITE_API_URL) || 'http://127.0.0.1:8000';
export const USE_MOCK_FALLBACK = (typeof import.meta !== 'undefined' && import.meta.env?.VITE_USE_MOCK === 'false') ? false : true;

export class ApiError extends Error {
  status: number;
  data: any;

  constructor(message: string, status: number, data?: any) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
  }
}

export function getAuthToken(): string | null {
  if (typeof window !== 'undefined' && window.localStorage) {
    return window.localStorage.getItem('kognisync_auth_token');
  }
  return null;
}

export function setAuthToken(token: string | null): void {
  if (typeof window !== 'undefined' && window.localStorage) {
    if (token) {
      window.localStorage.setItem('kognisync_auth_token', token);
    } else {
      window.localStorage.removeItem('kognisync_auth_token');
    }
  }
}

export async function ensureDemoToken(): Promise<string | null> {
  const existing = getAuthToken();
  if (existing) return existing;

  try {
    const res = await fetch(`${BACKEND_URL.replace(/\/$/, '')}/api/v1/auth/demo-token`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: 'usr_demo_traveler' }),
    });
    if (res.ok) {
      const data = await res.json();
      if (data.access_token) {
        setAuthToken(data.access_token);
        return data.access_token;
      }
    }
  } catch {
    // Offline or fallback handling
  }
  return null;
}

export async function apiClient<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${BACKEND_URL.replace(/\/$/, '')}/${endpoint.replace(/^\//, '')}`;
  
  let token = getAuthToken();
  if (!token && (endpoint.includes('holds') || endpoint.includes('bookings'))) {
    token = await ensureDemoToken();
  }

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(options.headers as Record<string, string>),
  };

  try {
    const response = await fetch(url, {
      ...options,
      headers,
    });

    if (!response.ok) {
      let errorData;
      try {
        errorData = await response.json();
      } catch {
        errorData = await response.text();
      }
      throw new ApiError(
        errorData?.detail || `API request failed with status ${response.status}`,
        response.status,
        errorData
      );
    }

    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }
    throw new ApiError((error as Error).message || 'Network request failed', 0);
  }
}
