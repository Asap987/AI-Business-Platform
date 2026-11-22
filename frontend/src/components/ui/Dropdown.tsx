"use client";

import Link from "next/link";
import { useEffect, useRef, type KeyboardEvent, type ReactNode } from "react";
import { Popover, type PopoverTriggerProps } from "@/components/ui/Popover";
import { cn } from "@/lib/utils";

export interface DropdownItem {
  id: string;
  label: string;
  icon?: ReactNode;
  /** Renders a link. Provide either href or onSelect. */
  href?: string;
  onSelect?: () => void;
  tone?: "default" | "danger";
  /** Draws a divider above this item. */
  separatorBefore?: boolean;
}

interface DropdownProps {
  renderTrigger: (props: PopoverTriggerProps) => ReactNode;
  items: DropdownItem[];
  label: string;
  align?: "left" | "right";
  header?: ReactNode;
  panelClassName?: string;
}

const ITEM_CLASSES =
  "flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left text-sm transition-colors focus-visible:outline-offset-[-2px]";

function MenuItems({ items, close }: { items: DropdownItem[]; close: () => void }) {
  const listRef = useRef<HTMLDivElement>(null);

  // Move focus into the menu when it opens, as the menu pattern expects.
  useEffect(() => {
    listRef.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus();
  }, []);

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const nodes = Array.from(listRef.current?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? []);
    if (nodes.length === 0) return;
    const index = nodes.indexOf(document.activeElement as HTMLElement);

    if (event.key === "ArrowDown") {
      event.preventDefault();
      nodes[(index + 1) % nodes.length].focus();
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      nodes[(index - 1 + nodes.length) % nodes.length].focus();
    } else if (event.key === "Home") {
      event.preventDefault();
      nodes[0].focus();
    } else if (event.key === "End") {
      event.preventDefault();
      nodes[nodes.length - 1].focus();
    }
  };

  return (
    <div ref={listRef} onKeyDown={onKeyDown} className="p-1.5">
      {items.map((item) => {
        const classes = cn(
          ITEM_CLASSES,
          item.tone === "danger" ? "text-danger hover:bg-danger-soft" : "text-ink hover:bg-surface-muted",
        );
        return (
          <div key={item.id}>
            {item.separatorBefore ? <div role="separator" className="my-1.5 h-px bg-border" /> : null}
            {item.href ? (
              <Link href={item.href} role="menuitem" className={classes} onClick={close}>
                {item.icon}
                {item.label}
              </Link>
            ) : (
              <button
                type="button"
                role="menuitem"
                className={classes}
                onClick={() => {
                  close();
                  item.onSelect?.();
                }}
              >
                {item.icon}
                {item.label}
              </button>
            )}
          </div>
        );
      })}
    </div>
  );
}

export function Dropdown({ renderTrigger, items, label, align = "right", header, panelClassName }: DropdownProps) {
  return (
    <Popover
      renderTrigger={renderTrigger}
      label={label}
      align={align}
      role="menu"
      panelClassName={cn("min-w-56", panelClassName)}
    >
      {(close) => (
        <>
          {header ? <div className="border-b border-border px-4 py-3">{header}</div> : null}
          <MenuItems items={items} close={close} />
        </>
      )}
    </Popover>
  );
}
