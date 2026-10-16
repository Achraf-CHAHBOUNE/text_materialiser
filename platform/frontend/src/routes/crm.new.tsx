import { useMutation, useQuery } from "@tanstack/react-query";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { AppShell } from "@/components/AppShell";
import { Card, money, Select, TextField } from "@/components/biz";
import { CrmNav } from "@/components/CrmNav";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { adminPlans, createClient, uploadContractFile, uploadProof, type Role } from "@/lib/api-biz";
import { useI18n } from "@/lib/i18n";

type Search = { name?: string; email?: string; phone?: string; city?: string };

export const Route = createFileRoute("/crm/new")({
  head: () => ({ meta: [{ title: "Nouveau client · CRM" }] }),
  validateSearch: (s: Record<string, unknown>): Search => ({
    ...(typeof s["name"] === "string" ? { name: s["name"] as string } : {}),
    ...(typeof s["email"] === "string" ? { email: s["email"] as string } : {}),
    ...(typeof s["phone"] === "string" ? { phone: s["phone"] as string } : {}),
    ...(typeof s["city"] === "string" ? { city: s["city"] as string } : {}),
  }),
  component: NewClientPage,
});

const iso = (d: Date) => d.toISOString().slice(0, 10);
const cents = (v: string) => Math.round(parseFloat((v || "0").replace(",", ".")) * 100);

/** A client arrives the way it happens: the transfer, the contract, the accounts --
 *  entered once, here. Without a transfer the accounts are made but stay closed. */
function NewClientPage() {
  const { t, lang } = useI18n();
  const navigate = useNavigate();
  const pre = Route.useSearch();
  const plans = useQuery({ queryKey: ["admin-plans"], queryFn: adminPlans });
  const today = new Date();
  const [org, setOrg] = useState({ name: pre.name ?? "", kind: "individual", ice: "", address: "", city: pre.city ?? "",
    phone: pre.phone ?? "", email: pre.email ?? "", language: lang as "ar" | "fr" });
  const [con, setCon] = useState({ plan_code: "individual", seats: "1", starts_on: iso(today),
    ends_on: iso(new Date(today.getTime() + 364 * 86400000)), price: "", vat: "20", notes: "" });
  const [paid, setPaid] = useState(true);
  const [tr, setTr] = useState({ amount: "", paid_on: iso(today), bank: "", bank_ref: "" });
  const [people, setPeople] = useState<{ email: string; role: Role }[]>([{ email: pre.email ?? "", role: "client_admin" }]);
  const [contractFile, setContractFile] = useState<File | null>(null);
  const [proofFile, setProofFile] = useState<File | null>(null);
  const ht = cents(con.price);
  const ttc = ht + Math.round(ht * Number(con.vat || 0) / 100);
  const seats = Number(con.seats) || 1;

  const save = useMutation({
    mutationFn: async () => {
      const out = await createClient({
        org,
        contract: { plan_code: con.plan_code, seats, starts_on: con.starts_on, ends_on: con.ends_on, amount_ht: ht,
          vat_rate: Math.round(Number(con.vat || 0) * 100), notes: con.notes },
        transfer: paid ? { amount: cents(tr.amount), paid_on: tr.paid_on, bank: tr.bank, bank_ref: tr.bank_ref } : undefined,
        accounts: people.filter((p) => p.email.trim()),
      });
      if (contractFile) await uploadContractFile(out.contract.id, contractFile);
      if (proofFile && out.transfer) await uploadProof(out.transfer.id, proofFile);
      return out;
    },
    onSuccess: (out) => {
      toast.success(out.active ? t("con.createdActive") : t("con.createdWaiting"), { description: out.invited.join(", ") });
      navigate({ to: "/crm/orgs/$orgId", params: { orgId: String(out.org_id) } });
    },
    onError: (e) => toast.error(e instanceof Error ? e.message : t("adm.failed")),
  });

  const pick = (code: string) => {
    const p = plans.data?.find((x) => x.code === code);
    setCon({ ...con, plan_code: code, seats: String(p?.seats ?? 1),
      price: p && p.period !== "quote" ? String((p.price * (p.period === "month" ? 12 : 1)) / 100) : con.price });
  };
  const step = (n: number, title: string) => (
    <span className="flex items-center gap-2"><span className="grid size-6 place-items-center rounded-full bg-primary text-xs text-primary-foreground">{n}</span>{title}</span>
  );

  return (
    <AppShell title={t("con.newClient")} description={t("con.newClientSubtitle")}>
      <CrmNav />
      <form className="grid gap-4 lg:grid-cols-2" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        <Card title={step(1, t("con.stepClient"))}>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5"><p className="text-xs text-muted-foreground">{t("crm.kind")}</p>
              <Select value={org.kind} onChange={(v) => setOrg({ ...org, kind: v })} className="w-full"
                      options={["individual", "firm", "company", "institution"].map((k) => ({ value: k, label: t(`kind.${k}` as "kind.firm") }))} /></div>
            <TextField label={org.kind === "individual" ? t("pub.name") : t("crm.orgName")} value={org.name} onChange={(v) => setOrg({ ...org, name: v })} required />
            <TextField label="ICE" value={org.ice} onChange={(v) => setOrg({ ...org, ice: v })} dir="ltr" />
            <TextField label={t("adm.colEmail")} value={org.email} onChange={(v) => setOrg({ ...org, email: v })} type="email" dir="ltr" />
            <TextField label={t("pub.phone")} value={org.phone} onChange={(v) => setOrg({ ...org, phone: v })} dir="ltr" />
            <TextField label={t("col.city")} value={org.city} onChange={(v) => setOrg({ ...org, city: v })} />
            <div className="sm:col-span-2"><TextField label={t("crm.address")} value={org.address} onChange={(v) => setOrg({ ...org, address: v })} /></div>
            <div className="space-y-1.5"><p className="text-xs text-muted-foreground">{t("acc.emailLanguage")}</p>
              <Select value={org.language} onChange={(v) => setOrg({ ...org, language: v as "ar" | "fr" })} className="w-full"
                      options={[{ value: "ar", label: "العربية" }, { value: "fr", label: "Français" }]} /></div>
          </div>
        </Card>

        <Card title={step(2, t("con.stepContract"))}>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5"><p className="text-xs text-muted-foreground">{t("crm.plan")}</p>
              <Select value={con.plan_code} onChange={pick} className="w-full"
                      options={(plans.data ?? []).filter((p) => p.code !== "trial").map((p) => ({ value: p.code, label: lang === "fr" ? p.name_fr : p.name_ar }))} /></div>
            <TextField label={t("con.accounts")} value={con.seats} onChange={(v) => setCon({ ...con, seats: v.replace(/\D/g, "") })} />
            <TextField label={t("crm.from")} value={con.starts_on} onChange={(v) => setCon({ ...con, starts_on: v })} type="date" />
            <TextField label={t("acc.until")} value={con.ends_on} onChange={(v) => setCon({ ...con, ends_on: v })} type="date" />
            <TextField label={`${t("con.priceHt")} (MAD)`} value={con.price} onChange={(v) => setCon({ ...con, price: v })} dir="ltr" />
            <TextField label={`${t("bill.vat")} (%)`} value={con.vat} onChange={(v) => setCon({ ...con, vat: v })} dir="ltr" />
            <p className="text-sm sm:col-span-2">{t("bill.total")} : <b className="tabular-nums">{money(ttc, lang)}</b></p>
            <div className="sm:col-span-2"><Textarea value={con.notes} onChange={(e) => setCon({ ...con, notes: e.target.value })} rows={2}
                                                      placeholder={t("con.notes")} aria-label={t("con.notes")} /></div>
            <label className="text-sm sm:col-span-2">{t("con.signedContract")} (PDF)
              <input type="file" accept=".pdf,image/*" className="mt-1 block text-sm" onChange={(e) => setContractFile(e.target.files?.[0] ?? null)} /></label>
          </div>
        </Card>

        <Card title={step(3, t("con.stepTransfer"))}>
          <label className="mb-3 flex items-center gap-2 text-sm"><input type="checkbox" checked={paid} onChange={(e) => setPaid(e.target.checked)} />{t("con.transferReceived")}</label>
          {paid ? (
            <div className="grid gap-3 sm:grid-cols-2">
              <TextField label={`${t("bill.amount")} (MAD TTC)`} value={tr.amount} onChange={(v) => setTr({ ...tr, amount: v })} dir="ltr" required placeholder={ttc ? String(ttc / 100) : ""} />
              <TextField label={t("con.paidOn")} value={tr.paid_on} onChange={(v) => setTr({ ...tr, paid_on: v })} type="date" />
              <TextField label={t("con.bank")} value={tr.bank} onChange={(v) => setTr({ ...tr, bank: v })} />
              <TextField label={t("con.bankRef")} value={tr.bank_ref} onChange={(v) => setTr({ ...tr, bank_ref: v })} dir="ltr" />
              <label className="text-sm sm:col-span-2">{t("con.proof")}
                <input type="file" accept=".pdf,image/*" className="mt-1 block text-sm" onChange={(e) => setProofFile(e.target.files?.[0] ?? null)} /></label>
            </div>
          ) : <p className="text-sm text-amber-700 dark:text-amber-300">{t("con.noTransferYet")}</p>}
        </Card>

        <Card title={step(4, t("con.stepAccounts"))}>
          <div className="space-y-2">
            {people.map((p, i) => (
              <div key={i} className="flex gap-2">
                <Input type="email" value={p.email} placeholder="avocat@cabinet.ma" dir="ltr" className="h-10 flex-1" aria-label={t("adm.colEmail")}
                       onChange={(e) => setPeople(people.map((x, j) => (j === i ? { ...x, email: e.target.value } : x)))} />
                <Select value={p.role} label={t("settings.role")} onChange={(v) => setPeople(people.map((x, j) => (j === i ? { ...x, role: v as Role } : x)))}
                        options={[{ value: "client_admin", label: t("role.client_admin") }, { value: "client", label: t("role.client") }]} />
                {people.length > 1 && <Button type="button" size="icon" variant="ghost" onClick={() => setPeople(people.filter((_, j) => j !== i))} aria-label={t("lib.delete")}><Trash2 className="size-4" /></Button>}
              </div>
            ))}
            {people.length < seats && (
              <Button type="button" size="sm" variant="ghost" onClick={() => setPeople([...people, { email: "", role: "client" }])}><Plus className="size-4" />{t("con.addAccount")}</Button>
            )}
            <p className="text-xs text-muted-foreground">{t("con.accountsHint")}</p>
          </div>
        </Card>

        <div className="lg:col-span-2 flex items-center justify-end gap-3">
          <p className="text-sm text-muted-foreground">{paid ? t("con.willOpen") : t("con.willWait")}</p>
          <Button type="submit" size="lg" disabled={save.isPending}>{t("con.create")}</Button>
        </div>
      </form>
    </AppShell>
  );
}
