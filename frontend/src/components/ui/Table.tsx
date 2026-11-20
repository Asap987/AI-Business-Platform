import type { HTMLAttributes, TdHTMLAttributes, ThHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

/**
 * Table primitives. The wrapper scrolls horizontally on narrow screens so a
 * wide table never forces the whole page to overflow.
 */
export function Table({ className, caption, ...rest }: HTMLAttributes<HTMLTableElement> & { caption?: string }) {
  return (
    <div className="relative w-full overflow-x-auto">
      <table className={cn("w-full min-w-max border-collapse text-left text-sm", className)} {...rest}>
        {caption ? <caption className="sr-only">{caption}</caption> : null}
        {rest.children}
      </table>
    </div>
  );
}

export function TableHead({ className, ...rest }: HTMLAttributes<HTMLTableSectionElement>) {
  return <thead className={cn("border-b border-border bg-surface-muted", className)} {...rest} />;
}

export function TableBody({ className, ...rest }: HTMLAttributes<HTMLTableSectionElement>) {
  return <tbody className={cn("divide-y divide-border", className)} {...rest} />;
}

export function TableRow({ className, ...rest }: HTMLAttributes<HTMLTableRowElement>) {
  return <tr className={cn("hover:bg-surface-muted/60", className)} {...rest} />;
}

export function TableHeader({ className, scope = "col", ...rest }: ThHTMLAttributes<HTMLTableCellElement>) {
  return (
    <th
      scope={scope}
      className={cn("px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-muted", className)}
      {...rest}
    />
  );
}

export function TableCell({ className, ...rest }: TdHTMLAttributes<HTMLTableCellElement>) {
  return <td className={cn("px-4 py-3 align-middle text-ink", className)} {...rest} />;
}
