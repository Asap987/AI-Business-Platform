import { cn, initials } from "@/lib/utils";

interface AvatarProps {
  name: string | null | undefined;
  size?: "sm" | "md" | "lg";
  className?: string;
}

const SIZES = {
  sm: "size-7 text-xs",
  md: "size-9 text-sm",
  lg: "size-11 text-base",
} as const;

/** Initials avatar. Decorative: the person's name is always rendered nearby. */
export function Avatar({ name, size = "md", className }: AvatarProps) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-full bg-secondary font-semibold text-on-primary",
        SIZES[size],
        className,
      )}
    >
      {initials(name)}
    </span>
  );
}
