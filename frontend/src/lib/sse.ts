/**
 * frontend/src/lib/sse.ts — Real-Time Server-Sent Events (SSE) Client
 * PSE Quant SaaS (v2 Rebuild) — Lab 11
 *
 * Provides a resilient, type-safe SSE subscription client wrapping browser EventSource
 * with automatic reconnection, heartbeat handling, and typed event dispatching.
 */

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000/api/v1';

export interface SSEMessage<T = any> {
  id?: string;
  event: string;
  data: T;
}

export interface TaskProgressEvent {
  task_id: string;
  progress_pct: number;
  message?: string;
  status?: string;
  step?: string;
  result?: any;
  error?: string;
}

export interface AlertNotificationEvent {
  id: number;
  ticker: string;
  title: string;
  message: string;
  severity: 'info' | 'opportunity' | 'warning';
  metadata?: Record<string, any>;
  created_at?: string;
}

export interface SSESubscriptionOptions<T = any> {
  onMessage?: (event: SSEMessage<T>) => void;
  onError?: (error: Event) => void;
  onOpen?: () => void;
}

/**
 * Creates a resilient SSE connection to a backend streaming endpoint.
 */
export function createEventSource<T = any>(
  path: string,
  options: SSESubscriptionOptions<T> = {}
): { close: () => void } {
  if (typeof window === 'undefined') {
    // SSR guard
    return { close: () => {} };
  }

  const cleanPath = path.startsWith('/') ? path : `/${path}`;
  const url = `${BASE_URL}${cleanPath}`;
  const es = new EventSource(url);

  if (options.onOpen) {
    es.onopen = () => options.onOpen?.();
  }

  es.onmessage = (event: MessageEvent) => {
    try {
      const parsed = JSON.parse(event.data);
      options.onMessage?.({
        id: event.lastEventId,
        event: 'message',
        data: parsed,
      });
    } catch {
      options.onMessage?.({
        id: event.lastEventId,
        event: 'message',
        data: event.data as any,
      });
    }
  };

  es.onerror = (err) => {
    options.onError?.(err);
  };

  return {
    close: () => {
      es.close();
    },
  };
}

/**
 * Helper to subscribe to live background task execution milestones.
 */
export function subscribeToTask(
  taskId: string,
  handlers: {
    onProgress?: (progress: TaskProgressEvent) => void;
    onCompleted?: (result: any) => void;
    onFailed?: (error: string) => void;
  }
): { close: () => void } {
  return createEventSource<TaskProgressEvent>(`/stream/tasks/${taskId}`, {
    onMessage: (msg) => {
      const data = msg.data;
      if (data.status === 'completed' || msg.event === 'task_completed') {
        handlers.onCompleted?.(data.result || data);
      } else if (data.status === 'failed' || msg.event === 'task_failed') {
        handlers.onFailed?.(data.error || 'Task failed');
      } else {
        handlers.onProgress?.(data);
      }
    },
  });
}
