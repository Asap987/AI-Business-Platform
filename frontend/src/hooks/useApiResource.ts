"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError, isAbortError, type RequestOptions } from "@/lib/api";

export type ResourceStatus = "loading" | "success" | "error";

export interface ApiResource<T> {
  status: ResourceStatus;
  data: T | null;
  error: ApiError | null;
  reload: () => void;
}

interface Settled<T> {
  key: string;
  data: T | null;
  error: ApiError | null;
}

/**
 * Loads a GET endpoint and exposes loading / success / error state plus a
 * reload function for retry buttons.
 *
 * Pass null as the path to skip fetching. There is deliberately no shared
 * cache: every mount fetches fresh, so one business's data can never be
 * shown to another through client state.
 */
export function useApiResource<T>(
  path: string | null,
  query?: RequestOptions["query"],
): ApiResource<T> {
  const [reloadToken, setReloadToken] = useState(0);
  const [settled, setSettled] = useState<Settled<T> | null>(null);

  const queryKey = query ? JSON.stringify(query) : "";
  const key = path === null ? "" : `${path}?${queryKey}#${reloadToken}`;

  useEffect(() => {
    if (path === null) return;

    const controller = new AbortController();
    api
      .get<T>(path, { query, signal: controller.signal })
      .then((data) => {
        setSettled({ key, data, error: null });
      })
      .catch((error: unknown) => {
        if (isAbortError(error)) return;
        const apiError =
          error instanceof ApiError
            ? error
            : new ApiError({
                status: 0,
                kind: "unknown",
                message: "Something unexpected happened. Please try again.",
              });
        setSettled({ key, data: null, error: apiError });
      });

    return () => controller.abort();
    // `query` is represented by `queryKey`; `key` already folds in path and reload.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  const reload = useCallback(() => setReloadToken((n) => n + 1), []);

  // A result only counts if it belongs to the current key, which makes the
  // loading state derive from props instead of being set inside the effect.
  const current = settled && settled.key === key ? settled : null;
  const status: ResourceStatus = path === null || !current ? "loading" : current.error ? "error" : "success";

  return {
    status,
    data: current?.data ?? null,
    error: current?.error ?? null,
    reload,
  };
}
