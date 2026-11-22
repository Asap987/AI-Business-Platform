import type { ReactNode } from "react";

interface AuthFormLayoutProps {
  title: string;
  description: string;
  children: ReactNode;
  footer?: ReactNode;
}

/** Heading, form area and footer link shared by the three auth screens. */
export function AuthFormLayout({ title, description, children, footer }: AuthFormLayoutProps) {
  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight text-ink">{title}</h1>
      <p className="mt-2 text-sm text-muted">{description}</p>
      <div className="mt-8">{children}</div>
      {footer ? <p className="mt-6 text-center text-sm text-muted">{footer}</p> : null}
    </div>
  );
}
