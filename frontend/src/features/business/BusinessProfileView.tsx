"use client";

import { Plus, Trash2 } from "lucide-react";
import { useState, type ReactNode } from "react";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { FormError } from "@/components/ui/ErrorMessage";
import { Input } from "@/components/ui/Input";
import { Skeleton } from "@/components/ui/LoadingSpinner";
import { ResourceView } from "@/components/ui/ResourceView";
import { Select, Textarea } from "@/components/ui/Select";
import { HoursEditor, fromWeek, toWeek, type WeekState } from "@/features/departments/HoursEditor";
import { errorText } from "@/features/org/shared";
import { useApiResource } from "@/hooks/useApiResource";
import { usePermission } from "@/hooks/usePermission";
import { api } from "@/lib/api";
import { useAuth } from "@/providers/AuthProvider";
import type { BusinessProfile, ServiceTone } from "@/types/org";

const ZONES = ["Africa/Accra", "Africa/Lagos", "Africa/Nairobi", "Africa/Johannesburg", "Europe/London", "UTC"];
const COMMON_LANGUAGES = ["English", "Twi", "Ga", "Ewe", "Hausa", "French"];

function Section({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return (
    <Card className="p-5">
      <h2 className="text-base font-semibold text-ink">{title}</h2>
      {hint ? <p className="mt-1 text-sm text-muted">{hint}</p> : null}
      <div className="mt-4 space-y-4">{children}</div>
    </Card>
  );
}

function Form({ initial, canWrite }: { initial: BusinessProfile; canWrite: boolean }) {
  const { refreshSession } = useAuth();
  const [name, setName] = useState(initial.name);
  const [industry, setIndustry] = useState(initial.industry ?? "");
  const [country, setCountry] = useState(initial.country ?? "");
  const [timezone, setTimezone] = useState(initial.timezone);
  const [description, setDescription] = useState(initial.description ?? "");
  const [phone, setPhone] = useState(initial.contact_phone ?? "");
  const [email, setEmail] = useState(initial.contact_email ?? "");
  const [website, setWebsite] = useState(initial.website ?? "");
  const [address, setAddress] = useState(initial.address ?? "");
  const [branches, setBranches] = useState(initial.branches.map((b) => ({ name: b.name, address: b.address ?? "", phone: b.phone ?? "" })));
  const [showHours, setShowHours] = useState(initial.hours !== null);
  const [week, setWeek] = useState<WeekState>(toWeek(initial.hours));
  const [policies, setPolicies] = useState(initial.policies);
  const [languages, setLanguages] = useState(initial.languages);
  const [otherLanguage, setOtherLanguage] = useState("");
  const [greeting, setGreeting] = useState(initial.preferences.greeting ?? "");
  const [tone, setTone] = useState<ServiceTone | "">(initial.preferences.tone ?? "");
  const [afterHours, setAfterHours] = useState(initial.preferences.after_hours_message ?? "");
  const [escalation, setEscalation] = useState(initial.preferences.escalation_note ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const touch = () => setSaved(false);
  const toggleLanguage = (l: string) => { touch(); setLanguages((cur) => (cur.includes(l) ? cur.filter((x) => x !== l) : [...cur, l])); };
  const addOther = () => {
    const v = otherLanguage.trim();
    if (v && !languages.some((l) => l.toLowerCase() === v.toLowerCase())) { touch(); setLanguages([...languages, v]); }
    setOtherLanguage("");
  };
  const zones = ZONES.includes(timezone) ? ZONES : [timezone, ...ZONES];

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null); setSaved(false);
    try {
      const orNull = (v: string) => v.trim() || null;
      await api.put("/business/profile", {
        name: name.trim(), industry: orNull(industry), country: orNull(country), timezone,
        description: orNull(description), contact_phone: orNull(phone), contact_email: orNull(email),
        website: orNull(website), address: orNull(address),
        branches: branches.filter((b) => b.name.trim() || b.address.trim() || b.phone.trim()).map((b) => ({ name: b.name.trim(), address: orNull(b.address), phone: orNull(b.phone) })),
        hours: showHours ? fromWeek(week) : null,
        policies: policies.filter((p) => p.title.trim() || p.text.trim()).map((p) => ({ title: p.title.trim(), text: p.text.trim() })),
        languages,
        preferences: { greeting: orNull(greeting), tone: tone || null, after_hours_message: orNull(afterHours), escalation_note: orNull(escalation) },
      });
      await refreshSession();
      setSaved(true);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={save} onChange={touch} className="space-y-5">
      <fieldset disabled={!canWrite || busy} className="min-w-0 space-y-5 border-0 p-0">
        <Section title="Your business" hint="The basics your assistants use when they introduce the business.">
          <Input label="Business name" value={name} onChange={(e) => setName(e.target.value)} required minLength={2} maxLength={120} />
          <div className="grid gap-4 sm:grid-cols-2">
            <Input label="Industry" value={industry} onChange={(e) => setIndustry(e.target.value)} placeholder="Retail, healthcare, education…" maxLength={80} />
            <Input label="Country" value={country} onChange={(e) => setCountry(e.target.value)} maxLength={80} />
          </div>
          <Select label="Time zone" value={timezone} onChange={(e) => setTimezone(e.target.value)} hint="Used for opening hours when a department has no time zone of its own.">
            {zones.map((z) => <option key={z} value={z}>{z}</option>)}
          </Select>
          <Textarea label="What your business does" value={description} onChange={(e) => setDescription(e.target.value)} maxLength={2000} rows={4} hint="A few plain sentences. Assistants use this to understand who they speak for." />
        </Section>

        <Section title="Contact details" hint="How customers can reach you. Only your own team and assistants see this.">
          <div className="grid gap-4 sm:grid-cols-2">
            <Input label="Phone" type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+233 24 000 0000" />
            <Input label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
          <Input label="Website" value={website} onChange={(e) => setWebsite(e.target.value)} placeholder="https://" />
          <Input label="Main address" value={address} onChange={(e) => setAddress(e.target.value)} maxLength={300} />
        </Section>

        <Section title="Branches and locations" hint="Add each place customers can visit or call.">
          {branches.length === 0 ? <p className="text-sm text-muted">No branches added.</p> : null}
          {branches.map((b, i) => (
            <div key={i} className="grid gap-3 rounded-lg border border-border p-3 sm:grid-cols-[1fr_1.5fr_1fr_auto] sm:items-end">
              <Input label="Branch name" value={b.name} onChange={(e) => setBranches(branches.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)))} />
              <Input label="Address" value={b.address} onChange={(e) => setBranches(branches.map((x, j) => (j === i ? { ...x, address: e.target.value } : x)))} />
              <Input label="Phone" value={b.phone} onChange={(e) => setBranches(branches.map((x, j) => (j === i ? { ...x, phone: e.target.value } : x)))} />
              <Button type="button" variant="ghost" aria-label={`Remove branch ${b.name || i + 1}`} onClick={() => { touch(); setBranches(branches.filter((_, j) => j !== i)); }}><Trash2 aria-hidden="true" className="size-4" /></Button>
            </div>
          ))}
          {branches.length < 20 ? <Button type="button" variant="secondary" onClick={() => { touch(); setBranches([...branches, { name: "", address: "", phone: "" }]); }}><Plus aria-hidden="true" className="size-4" /> Add a branch</Button> : null}
        </Section>

        <Section title="Opening hours" hint="When the business as a whole is open. Each department can also have its own hours.">
          <label className="flex items-center gap-2 text-sm text-ink">
            <input type="checkbox" checked={showHours} onChange={(e) => setShowHours(e.target.checked)} /> We have set opening hours
          </label>
          {showHours ? <HoursEditor week={week} onChange={(w) => { touch(); setWeek(w); }} /> : <p className="text-sm text-muted">Opening hours are not stated, so assistants will not quote any.</p>}
        </Section>

        <Section title="Business policies" hint="Rules assistants should state correctly, such as refunds, delivery or payment terms.">
          {policies.length === 0 ? <p className="text-sm text-muted">No policies added.</p> : null}
          {policies.map((p, i) => (
            <div key={i} className="space-y-3 rounded-lg border border-border p-3">
              <Input label="Policy name" value={p.title} onChange={(e) => setPolicies(policies.map((x, j) => (j === i ? { ...x, title: e.target.value } : x)))} placeholder="Refunds" />
              <Textarea label="What it says" rows={3} value={p.text} onChange={(e) => setPolicies(policies.map((x, j) => (j === i ? { ...x, text: e.target.value } : x)))} maxLength={2000} />
              <Button type="button" variant="ghost" onClick={() => { touch(); setPolicies(policies.filter((_, j) => j !== i)); }}><Trash2 aria-hidden="true" className="size-4" /> Remove policy</Button>
            </div>
          ))}
          {policies.length < 30 ? <Button type="button" variant="secondary" onClick={() => { touch(); setPolicies([...policies, { title: "", text: "" }]); }}><Plus aria-hidden="true" className="size-4" /> Add a policy</Button> : null}
        </Section>

        <Section title="Languages" hint="Languages your customers use. Whether an assistant can speak a language well depends on the voice and AI services in use.">
          <div className="flex flex-wrap gap-3">
            {COMMON_LANGUAGES.map((l) => (
              <label key={l} className="flex items-center gap-2 text-sm text-ink"><input type="checkbox" checked={languages.includes(l)} onChange={() => toggleLanguage(l)} /> {l}</label>
            ))}
          </div>
          {languages.filter((l) => !COMMON_LANGUAGES.includes(l)).length ? (
            <ul className="flex flex-wrap gap-2">
              {languages.filter((l) => !COMMON_LANGUAGES.includes(l)).map((l) => (
                <li key={l}><button type="button" className="rounded-full border border-border px-3 py-1 text-sm text-ink" onClick={() => toggleLanguage(l)} aria-label={`Remove ${l}`}>{l} ×</button></li>
              ))}
            </ul>
          ) : null}
          <div className="flex items-end gap-2 sm:w-96">
            <div className="flex-1"><Input label="Another language" value={otherLanguage} onChange={(e) => setOtherLanguage(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addOther(); } }} /></div>
            <Button type="button" variant="secondary" onClick={addOther}>Add</Button>
          </div>
        </Section>

        <Section title="Customer service preferences" hint="How your assistants should sound and what to do when nobody can help.">
          <Select label="Tone" value={tone} onChange={(e) => setTone(e.target.value as ServiceTone | "")}>
            <option value="">No preference</option>
            <option value="friendly">Friendly and relaxed</option>
            <option value="professional">Professional</option>
            <option value="formal">Formal</option>
          </Select>
          <Input label="Greeting" value={greeting} onChange={(e) => setGreeting(e.target.value)} maxLength={300} placeholder="Akwaaba! Thank you for calling…" />
          <Textarea label="Message when we are closed" rows={2} value={afterHours} onChange={(e) => setAfterHours(e.target.value)} maxLength={500} />
          <Textarea label="When to bring in a person" rows={2} value={escalation} onChange={(e) => setEscalation(e.target.value)} maxLength={500} hint="For example: always offer a person for complaints or payment disputes." />
        </Section>
      </fieldset>

      {error ? <FormError message={error} /> : null}
      {canWrite ? (
        <div className="flex items-center gap-3">
          <Button type="submit" disabled={busy}>{busy ? "Saving…" : "Save changes"}</Button>
          {saved ? <p role="status" className="text-sm text-success">Saved.</p> : null}
        </div>
      ) : <p className="text-sm text-muted">You can view these details. Only an administrator can change them.</p>}
    </form>
  );
}

export function BusinessProfileView() {
  const canWrite = usePermission("business:write");
  const resource = useApiResource<BusinessProfile>("/business/profile");
  return (
    <>
      <PageHeader title="Business details" description="What your assistants and team should know about your organisation." />
      <ResourceView resource={resource} skeleton={<Skeleton className="h-64 w-full" />}>
        {(data) => <Form initial={data} canWrite={canWrite} />}
      </ResourceView>
    </>
  );
}
