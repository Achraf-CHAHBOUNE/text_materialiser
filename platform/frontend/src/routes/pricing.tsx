import { useMutation, useQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { Check, Send } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { money, TextField } from "@/components/biz";
import { PublicShell } from "@/components/PublicShell";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { publicPlans, requestDemo, type Plan } from "@/lib/api-biz";
import { useI18n } from "@/lib/i18n";

export const Route = createFileRoute("/pricing")({
  head: () => ({ meta: [{ title: "العروض · Offres" }] }),
  component: Pricing,
});

function Pricing() {
  const { t, lang } = useI18n();
  const plans = useQuery({ queryKey: ["public-plans"], queryFn: publicPlans });
  return (
    <PublicShell>
      <section className="text-center">
        <h1 className="text-display font-semibold">{t("pub.title")}</h1>
        <p className="mx-auto mt-3 max-w-2xl text-muted-foreground">{t("pub.subtitle")}</p>
      </section>

      <section className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {(plans.data ?? []).map((p) => <PlanCard key={p.code} plan={p} />)}
      </section>

      <section id="demo" className="mx-auto mt-14 max-w-2xl rounded-2xl border bg-card p-6 shadow-soft">
        <h2 className="text-h2 font-semibold">{t("pub.demoTitle")}</h2>
        <p className="mt-1 text-sm text-muted-foreground">{t("pub.demoSubtitle")}</p>
        <DemoForm lang={lang} />
      </section>
    </PublicShell>
  );
}

function PlanCard({ plan }: { plan: Plan }) {
  const { t, lang, num } = useI18n();
  const name = lang === "fr" ? plan.name_fr : plan.name_ar;
  const blurb = lang === "fr" ? plan.blurb_fr : plan.blurb_ar;
  const price = plan.period === "quote" ? t("pub.onQuote")
    : plan.price === 0 ? t("pub.free")
    : `${money(plan.price, lang)} ${plan.period === "year" ? t("pub.perYear") : t("pub.perMonth")}`;
  return (
    <div className={`flex flex-col rounded-2xl border bg-card p-5 shadow-soft ${plan.code === "firm" ? "ring-2 ring-teal" : ""}`}>
      <h3 className="font-semibold">{name}</h3>
      <p className="mt-2 text-xl font-semibold tabular-nums">{price}</p>
      {plan.price > 0 && <p className="text-xs text-muted-foreground">{t("pub.exclVat")}</p>}
      <p className="mt-3 text-sm text-muted-foreground">{blurb}</p>
      <ul className="mt-4 space-y-1.5 text-sm">
        <li className="flex gap-2"><Check className="size-4 text-teal" aria-hidden />{num(plan.seats)} {t("pub.seats")}</li>
        <li className="flex gap-2"><Check className="size-4 text-teal" aria-hidden />{num(plan.daily_downloads)} {t("pub.downloadsDay")}</li>
        <li className="flex gap-2"><Check className="size-4 text-teal" aria-hidden />{t("pub.bilingual")}</li>
      </ul>
      <Button asChild variant={plan.code === "firm" ? "default" : "outline"} className="mt-auto pt-0">
        <a href="#demo" className="mt-5">{plan.code === "trial" ? t("pub.startTrial") : t("pub.askDemo")}</a>
      </Button>
    </div>
  );
}

function DemoForm({ lang }: { lang: "ar" | "fr" }) {
  const { t } = useI18n();
  const [f, setF] = useState({ full_name: "", email: "", phone: "", company: "", city: "", message: "", website: "" });
  const set = (k: keyof typeof f) => (v: string) => setF({ ...f, [k]: v });
  const send = useMutation({
    mutationFn: () => requestDemo({ ...f, language: lang }),
    onSuccess: () => setF({ full_name: "", email: "", phone: "", company: "", city: "", message: "", website: "" }),
    onError: (e) => toast.error(e instanceof Error ? e.message : t("adm.failed")),
  });
  if (send.isSuccess) {
    return <p className="mt-6 rounded-xl bg-teal/10 p-4 text-sm text-teal">{t("pub.demoThanks")}</p>;
  }
  return (
    <form className="mt-5 grid gap-3 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); send.mutate(); }}>
      <TextField label={t("pub.name")} value={f.full_name} onChange={set("full_name")} required />
      <TextField label={t("adm.colEmail")} value={f.email} onChange={set("email")} type="email" required dir="ltr" />
      <TextField label={t("pub.phone")} value={f.phone} onChange={set("phone")} dir="ltr" />
      <TextField label={t("pub.company")} value={f.company} onChange={set("company")} />
      <TextField label={t("col.city")} value={f.city} onChange={set("city")} />
      {/* a field no person sees: a robot that fills it is quietly ignored */}
      <input tabIndex={-1} autoComplete="off" aria-hidden className="hidden" value={f.website}
             onChange={(e) => set("website")(e.target.value)} name="website" />
      <div className="sm:col-span-2">
        <Textarea value={f.message} onChange={(e) => set("message")(e.target.value)}
                  placeholder={t("pub.message")} aria-label={t("pub.message")} rows={3} />
      </div>
      <Button type="submit" disabled={send.isPending} className="sm:col-span-2">
        <Send className="size-4" aria-hidden />{t("pub.send")}
      </Button>
    </form>
  );
}
