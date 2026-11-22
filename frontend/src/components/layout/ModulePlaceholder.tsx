import { Construction } from "lucide-react";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { ButtonLink } from "@/components/ui/Button";
import { Card, CardBody } from "@/components/ui/Card";
import { MODULES, type ModuleKey } from "@/lib/modules";

/** Page shown for modules that are planned but not built yet. */
export function ModulePlaceholder({ module }: { module: ModuleKey }) {
  const info = MODULES[module];
  const Icon = info.icon;

  return (
    <>
      <PageHeader title={info.title} description={info.description} actions={<Badge tone="warning">Under development</Badge>} />
      <Card>
        <CardBody className="flex flex-col items-start gap-6 p-6 sm:p-8 md:flex-row">
          <span className="flex size-12 shrink-0 items-center justify-center rounded-xl bg-accent-soft text-accent-strong">
            <Icon aria-hidden="true" className="size-6" />
          </span>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <Construction aria-hidden="true" className="size-4 text-warning" />
              <h2 className="text-base font-semibold text-ink">This module is under development</h2>
            </div>
            <p className="mt-1.5 max-w-prose text-sm text-muted">
              {info.title} isn&apos;t available yet. The navigation and layout are ready, so it will appear here without
              any change to how the rest of the app works.
            </p>
            <h3 className="mt-5 text-sm font-semibold text-ink">Planned</h3>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-muted">
              {info.planned.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
            <div className="mt-6">
              <ButtonLink href="/dashboard" variant="secondary" size="sm">
                Back to overview
              </ButtonLink>
            </div>
          </div>
        </CardBody>
      </Card>
    </>
  );
}
