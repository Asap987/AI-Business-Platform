import type { ReactNode } from "react";
import { ErrorMessage } from "@/components/ui/ErrorMessage";
import type { ApiResource } from "@/hooks/useApiResource";

interface ResourceViewProps<T> {
  resource: ApiResource<T>;
  /** Decide whether a successful response should show the empty state. */
  isEmpty?: (data: T) => boolean;
  /** Shown while the first response is pending. */
  skeleton: ReactNode;
  /** Shown when the request succeeds but there is nothing to display. */
  empty?: ReactNode;
  /** Render the data. Only called for a non-empty success. */
  children: (data: T) => ReactNode;
  compact?: boolean;
}

/**
 * Handles every state a data-driven section can be in, so no section can
 * end up as a blank box: loading, API failure (including permission denied
 * and expired session), empty, and success.
 */
export function ResourceView<T>({
  resource,
  isEmpty,
  skeleton,
  empty,
  children,
  compact = true,
}: ResourceViewProps<T>) {
  if (resource.status === "loading") {
    return (
      <div aria-busy="true" aria-live="polite">
        {skeleton}
      </div>
    );
  }

  if (resource.status === "error" && resource.error) {
    return <ErrorMessage error={resource.error} onRetry={resource.reload} compact={compact} />;
  }

  if (resource.data === null || (isEmpty && isEmpty(resource.data))) {
    return <>{empty}</>;
  }

  return <>{children(resource.data)}</>;
}
