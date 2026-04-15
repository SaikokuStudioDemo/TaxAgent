/**
 * api.ts - Shared API client for Tax-Agent backend
 *
 * Auto-injects Firebase ID token into every request.
 * Falls back to "test-token" in development bypass mode.
 */
import { auth } from '@/lib/firebase/config';

export const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

async function getAuthToken(): Promise<string> {
    const devToken = localStorage.getItem('DEV_AUTH_TOKEN');
    if (devToken) return devToken;
    const user = auth.currentUser;
    if (user) return await user.getIdToken(/* forceRefresh */ false);
    throw new Error('認証情報が取得できません。ページを再読み込みしてください。');
}

async function request<T>(
    method: string,
    path: string,
    body?: unknown,
    timeoutMs = 8000,
): Promise<T> {
    const token = await getAuthToken();
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    let res: Response;
    try {
        res = await fetch(`${API_BASE}${path}`, {
            method,
            headers: {
                'Content-Type': 'application/json',
                Authorization: `Bearer ${token}`,
            },
            body: body !== undefined ? JSON.stringify(body) : undefined,
            signal: controller.signal,
        });
    } catch (e: any) {
        if (e?.name === 'AbortError') throw new Error('サーバーへの接続がタイムアウトしました。バックエンドが起動しているか確認してください。');
        throw e;
    } finally {
        clearTimeout(timer);
    }

    if (!res.ok) {
        let detail = res.statusText;
        try {
            const err = await res.json();
            detail = err.detail || JSON.stringify(err);
        } catch (_) {}
        throw new Error(`API ${method} ${path} failed (${res.status}): ${detail}`);
    }

    // 204 No Content
    if (res.status === 204) return undefined as T;
    return res.json() as Promise<T>;
}

/**
 * オブジェクトのキー・値から URLSearchParams クエリ文字列を生成する。
 * 値が falsy な場合はそのキーをスキップする。
 */
export function buildQueryString(params?: Record<string, string | undefined>): string {
    if (!params) return '';
    const query = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
        if (value) query.append(key, value);
    }
    const qs = query.toString();
    return qs ? '?' + qs : '';
}

export const api = {
    get: <T>(path: string) => request<T>('GET', path),
    post: <T>(path: string, body: unknown) => request<T>('POST', path, body),
    put: <T>(path: string, body: unknown) => request<T>('PUT', path, body),
    patch: <T>(path: string, body: unknown) => request<T>('PATCH', path, body),
    delete: <T>(path: string) => request<T>('DELETE', path),
};
