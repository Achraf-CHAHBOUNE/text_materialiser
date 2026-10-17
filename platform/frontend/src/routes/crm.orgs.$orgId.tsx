import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { Ban, CheckCircle2, FilePlus2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { AppShell } from "@/components/AppShell";
import {
  Badge,
  Card,
  day,
  Empty,
  money,
  Select,
  Stat,
  STATUS_TONE,
  Table,
  Td,
  TextField,
  when,
} from "@/components/biz";
import { ContractCard } from "@/components/ContractCard";
import { CrmNav } from "@/components/CrmNav";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import {
  addContract,
  adminPlans,
  orgDetail,
  orgInvite,
  updateOrg,
  updateUser,
  type Org,
  type OrgDetail,
  type Role,
} from "@/lib/api-biz";
import { useI18n } from "@/lib/i18n";

export const Route = createFileRoute("/crm/orgs/$orgId")({
  component: ClientPage,
});

const fail = (fallback: string) => (e: unknown) =>
  toast.error(e instanceof Error ? e.message : fallback);

function ClientPage() {
  const { orgId } = Route.useParams();
  const id = Number(orgId);
  const { t, lang, num, status } = useI18n();
  const q = useQuery({ queryKey: ["org", id], queryFn: () => orgDetail(id) });
  const o = q.data;
  const current = o?.contracts.find((c) => c.status === "active") ?? o?.contracts[0];
  return (
    <AppShell
      title={o?.name ?? t("crm.client")}
      description={o ? `${t(`kind.${o.kind}` as "kind.firm")}${o.city ? ` · ${o.city}` : ""}` : ""}
      action={
        o && (
          <Badge tone={o.access === "ok" ? "good" : "warn"}>
            {o.access === "ok" ? t("con.accessOpen") : t("con.accessClosed")}
          </Badge>
        )
      }
    >
      <CrmNav />
      {o && (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat
              label={t("con.contract")}
              value={current ? t(`con.st.${current.status}` as "con.st.active") : "—"}
              hint={current ? `${day(current.starts_on)} → ${day(current.ends_on)}` : undefined}
              tone={
                current?.status === "awaiting_payment"
                  ? "warn"
                  : current?.status === "active"
                    ? "good"
                    : "default"
              }
            />
            <Stat
              label={t("con.accounts")}
              value={`${num(o.seats.used)} / ${num(current?.seats ?? o.seats.total)}`}
            />
            <Stat
              label={t("trk.paid")}
              value={money(o.paid, lang)}
              tone="good"
              hint={
                o.owed ? (
                  <span className="text-destructive">
                    {t("trk.owes")} {money(o.owed, lang)}
                  </span>
                ) : undefined
              }
            />
            <Stat
              label={t("crm.health")}
              value={status(o.health)}
              hint={`${num(o.activity_30d)} ${t("crm.actions30")}`}
              tone={o.health === "at_risk" ? "bad" : o.health === "quiet" ? "warn" : "good"}
            />
          </div>
          <Tabs defaultValue="contracts" className="mt-4">
            <TabsList className="flex-wrap">
              <TabsTrigger value="contracts">{t("con.title")}</TabsTrigger>
              <TabsTrigger value="people">
                {t("con.accounts")} ({num(o.members.length + o.invitations.length)})
              </TabsTrigger>
              <TabsTrigger value="info">{t("crm.tabOverview")}</TabsTrigger>
              <TabsTrigger value="history">{t("crm.tabHistory")}</TabsTrigger>
            </TabsList>
            <TabsContent value="contracts" className="mt-4">
              <Contracts o={o} />
            </TabsContent>
            <TabsContent value="people" className="mt-4">
              <People o={o} />
            </TabsContent>
            <TabsContent value="info" className="mt-4">
              <Info key={o.id} o={o} />
            </TabsContent>
            <TabsContent value="history" className="mt-4">
              <Card>
                {o.audit.length === 0 ? (
                  <Empty>{t("history.empty")}</Empty>
                ) : (
                  <ul className="divide-y text-sm">
                    {o.audit.map((a, i) => (
                      <li key={i} className="py-2">
                        <span className="text-xs text-muted-foreground">
                          {when(a.ts)} · {a.actor}
                        </span>
                        <p>
                          {a.action}
                          {a.field ? ` · ${a.field}` : ""}
                          {a.new ? ` → ${a.new}` : ""}
                        </p>
                      </li>
                    ))}
                  </ul>
                )}
              </Card>
            </TabsContent>
          </Tabs>
        </>
      )}
    </AppShell>
  );
}

function useRefresh(id: number) {
  const qc = useQueryClient();
  return () => {
    void qc.invalidateQueries({ queryKey: ["org", id] });
    void qc.invalidateQueries({ queryKey: ["orgs"] });
  };
}

function Contracts({ o }: { o: OrgDetail }) {
  const { t, lang } = useI18n();
  const refresh = useRefresh(o.id);
  const plans = useQuery({ queryKey: ["admin-plans"], queryFn: adminPlans });
  const [open, setOpen] = useState(false);
  const last = o.contracts.find((c) => c.id !== null && c.status !== "cancelled");
  const [f, setF] = useState({
    plan_code: last?.plan_code ?? "individual",
    seats: String(last?.seats ?? 1),
    price: last ? String(last.amount_ht / 100) : "",
    vat: "20",
    notes: "",
  });
  const add = useMutation({
    mutationFn: () =>
      addContract(o.id, {
        plan_code: f.plan_code,
        seats: Number(f.seats) || undefined,
        amount_ht: Math.round(parseFloat(f.price.replace(",", ".") || "0") * 100),
        vat_rate: Math.round(Number(f.vat || 0) * 100),
        notes: f.notes,
      }),
    onSuccess: () => {
      toast.success(t("con.renewalCreated"));
      setOpen(false);
      refresh();
    },
    onError: fail(t("adm.failed")),
  });
  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <Button size="sm" variant="outline" onClick={() => setOpen(!open)}>
          <FilePlus2 className="size-4" />
          {t("con.renew")}
        </Button>
      </div>
      {open && (
        <Card title={t("con.renew")}>
          <form
            className="flex flex-wrap items-end gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              add.mutate();
            }}
          >
            <Select
              value={f.plan_code}
              onChange={(v) => setF({ ...f, plan_code: v })}
              label={t("crm.plan")}
              options={(plans.data ?? [])
                .filter((p) => p.code !== "trial")
                .map((p) => ({ value: p.code, label: lang === "fr" ? p.name_fr : p.name_ar }))}
            />
            <Input
              value={f.seats}
              onChange={(e) => setF({ ...f, seats: e.target.value.replace(/\D/g, "") })}
              className="h-10 w-20"
              aria-label={t("con.accounts")}
            />
            <Input
              value={f.price}
              onChange={(e) => setF({ ...f, price: e.target.value })}
              placeholder={`${t("con.priceHt")} MAD`}
              className="h-10 w-36"
              dir="ltr"
              aria-label={t("con.priceHt")}
            />
            <Input
              value={f.vat}
              onChange={(e) => setF({ ...f, vat: e.target.value })}
              className="h-10 w-16"
              dir="ltr"
              aria-label={t("bill.vat")}
            />
            <span className="pb-2 text-sm text-muted-foreground">%</span>
            <Textarea
              value={f.notes}
              onChange={(e) => setF({ ...f, notes: e.target.value })}
              rows={1}
              placeholder={t("con.notes")}
              className="min-h-10 flex-1"
              aria-label={t("con.notes")}
            />
            <Button type="submit" disabled={add.isPending}>
              {t("adm.create")}
            </Button>
          </form>
          <p className="mt-2 text-xs text-muted-foreground">{t("con.renewHint")}</p>
        </Card>
      )}
      {o.contracts.length === 0 ? (
        <Empty>{t("con.none")}</Empty>
      ) : (
        o.contracts.map((c) => <ContractCard key={c.id ?? "loose"} c={c} onChange={refresh} />)
      )}
      {o.invoices.length > 0 && (
        <Card title={t("bill.invoices")}>
          <ul className="divide-y text-sm">
            {o.invoices.map((i) => (
              <li key={i.id} className="flex justify-between gap-2 py-1.5">
                <Link
                  to="/invoice/$invoiceId"
                  params={{ invoiceId: String(i.id) }}
                  className="font-mono text-teal hover:underline"
                  dir="ltr"
                >
                  {i.number}
                </Link>
                <span className="tabular-nums">{money(i.amount_ttc, lang)}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}

function People({ o }: { o: OrgDetail }) {
  const { t, lang, status } = useI18n();
  const refresh = useRefresh(o.id);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("client");
  const invite = useMutation({
    mutationFn: () => orgInvite(o.id, email, role, o.language || lang),
    onSuccess: () => {
      toast.success(t("team.invited"));
      setEmail("");
      refresh();
    },
    onError: fail(t("adm.failed")),
  });
  const change = useMutation({
    mutationFn: (x: { email: string; role?: Role; status?: "active" | "suspended" }) =>
      updateUser(x.email, x),
    onSuccess: refresh,
    onError: fail(t("adm.failed")),
  });
  return (
    <Card>
      <form
        className="mb-3 flex flex-wrap gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          invite.mutate();
        }}
      >
        <Input
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="avocat@cabinet.ma"
          className="h-10 max-w-xs"
          dir="ltr"
          aria-label={t("adm.colEmail")}
        />
        <Select
          value={role}
          onChange={(v) => setRole(v as Role)}
          label={t("settings.role")}
          options={[
            { value: "client", label: t("role.client") },
            { value: "client_admin", label: t("role.client_admin") },
          ]}
        />
        <Button type="submit" disabled={invite.isPending}>
          {t("con.addAccount")}
        </Button>
      </form>
      <Table
        head={[t("trk.reader"), t("settings.role"), t("adm.colStatus"), t("adm.colLastLogin"), ""]}
      >
        {o.members.map((m) => (
          <tr key={m.email}>
            <Td>
              <Link
                to="/crm/users/$email"
                params={{ email: m.email }}
                className="text-teal hover:underline"
                dir="ltr"
              >
                {m.email}
              </Link>
              <p className="text-xs text-muted-foreground">{m.full_name || "—"}</p>
            </Td>
            <Td>
              <Select
                value={m.role}
                onChange={(v) => change.mutate({ email: m.email, role: v as Role })}
                className="h-8 text-xs"
                label={t("settings.role")}
                options={[
                  { value: "client", label: t("role.client") },
                  { value: "client_admin", label: t("role.client_admin") },
                ]}
              />
            </Td>
            <Td>
              <Badge tone={STATUS_TONE[m.status]}>{status(m.status)}</Badge>
            </Td>
            <Td className="text-xs">{day(m.last_login)}</Td>
            <Td>
              <Button
                size="sm"
                variant="ghost"
                aria-label={m.status === "active" ? t("adm.suspend") : t("adm.activate")}
                onClick={() =>
                  change.mutate({
                    email: m.email,
                    status: m.status === "active" ? "suspended" : "active",
                  })
                }
              >
                {m.status === "active" ? (
                  <Ban className="size-4" />
                ) : (
                  <CheckCircle2 className="size-4" />
                )}
              </Button>
            </Td>
          </tr>
        ))}
        {o.invitations.map((i) => (
          <tr key={`i${i.id}`} className="text-muted-foreground">
            <Td>
              <span dir="ltr">{i.email}</span>
            </Td>
            <Td>{t(`role.${i.role}` as "role.client")}</Td>
            <Td>
              <Badge tone="info">{t("team.pending")}</Badge>
            </Td>
            <Td className="text-xs">
              {t("team.until")} {day(i.expires_at)}
            </Td>
            <Td />
          </tr>
        ))}
      </Table>
      {o.access !== "ok" && (
        <p className="mt-2 text-xs text-amber-700 dark:text-amber-300">
          {t("con.closedUntilPaid")}
        </p>
      )}
    </Card>
  );
}

function Info({ o }: { o: OrgDetail }) {
  const { t } = useI18n();
  const refresh = useRefresh(o.id);
  const [f, setF] = useState<Partial<Org>>({
    name: o.name,
    kind: o.kind,
    city: o.city,
    ice: o.ice,
    address: o.address,
    phone: o.phone,
    email: o.email,
    language: o.language,
    notes: o.notes,
  });
  const set = (k: keyof Org) => (v: string) => setF({ ...f, [k]: v });
  const save = useMutation({
    mutationFn: () => updateOrg(o.id, f),
    onSuccess: () => {
      toast.success(t("adm.saved"));
      refresh();
    },
    onError: fail(t("adm.failed")),
  });
  return (
    <Card>
      <form
        className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <TextField label={t("crm.orgName")} value={f.name ?? ""} onChange={set("name")} required />
        <div className="space-y-1.5">
          <p className="text-xs text-muted-foreground">{t("crm.kind")}</p>
          <Select
            value={f.kind ?? "individual"}
            onChange={set("kind")}
            className="w-full"
            options={["individual", "firm", "company", "institution"].map((k) => ({
              value: k,
              label: t(`kind.${k}` as "kind.firm"),
            }))}
          />
        </div>
        <TextField label="ICE" value={f.ice ?? ""} onChange={set("ice")} dir="ltr" />
        <TextField label={t("col.city")} value={f.city ?? ""} onChange={set("city")} />
        <TextField label={t("crm.address")} value={f.address ?? ""} onChange={set("address")} />
        <TextField
          label={t("adm.colEmail")}
          value={f.email ?? ""}
          onChange={set("email")}
          dir="ltr"
        />
        <TextField label={t("pub.phone")} value={f.phone ?? ""} onChange={set("phone")} dir="ltr" />
        <div className="space-y-1.5">
          <p className="text-xs text-muted-foreground">{t("acc.emailLanguage")}</p>
          <Select
            value={f.language ?? "ar"}
            onChange={set("language")}
            className="w-full"
            options={[
              { value: "ar", label: "العربية" },
              { value: "fr", label: "Français" },
            ]}
          />
        </div>
        <div className="sm:col-span-2 lg:col-span-3">
          <Textarea
            value={f.notes ?? ""}
            onChange={(e) => set("notes")(e.target.value)}
            rows={3}
            placeholder={t("crm.notes")}
            aria-label={t("crm.notes")}
          />
        </div>
        <Button type="submit" size="sm" className="w-fit" disabled={save.isPending}>
          {t("adm.save")}
        </Button>
      </form>
    </Card>
  );
}
