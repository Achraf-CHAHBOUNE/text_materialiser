// The administrator's own tabs: who works here, what is sold, and what was emailed.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";

import {
  Badge,
  Card,
  day,
  Empty,
  money,
  Select,
  STATUS_TONE,
  Table,
  Td,
  TextField,
  when,
} from "@/components/biz";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import {
  adminPlans,
  createStaff,
  outbox,
  savePlan,
  staffList,
  updateUser,
  type Plan,
  type Role,
} from "@/lib/api-biz";
import { useStore } from "@/lib/app-store";
import { useI18n } from "@/lib/i18n";

const fail = (fallback: string) => (e: unknown) =>
  toast.error(e instanceof Error ? e.message : fallback);

export function StaffPanel() {
  const { t, status } = useI18n();
  const { email: me } = useStore();
  const qc = useQueryClient();
  const list = useQuery({ queryKey: ["staff"], queryFn: staffList });
  const blank = { email: "", role: "editor" as Role, full_name: "", password: "" };
  const [f, setF] = useState(blank);
  const refresh = () => void qc.invalidateQueries({ queryKey: ["staff"] });
  const add = useMutation({
    mutationFn: () => createStaff(f),
    onSuccess: () => {
      setF(blank);
      refresh();
      toast.success(t("adm.clientCreated"));
    },
    onError: fail(t("adm.failed")),
  });
  const change = useMutation({
    mutationFn: (x: { email: string; role?: Role; status?: "active" | "suspended" }) =>
      updateUser(x.email, x),
    onSuccess: refresh,
    onError: fail(t("adm.failed")),
  });
  const roles: Role[] = ["admin", "editor", "sales"];
  return (
    <div className="space-y-4">
      <Card title={t("staff.new")}>
        <form
          className="grid gap-2 sm:grid-cols-5"
          onSubmit={(e) => {
            e.preventDefault();
            add.mutate();
          }}
        >
          <TextField
            label={t("pub.name")}
            value={f.full_name}
            onChange={(v) => setF({ ...f, full_name: v })}
          />
          <TextField
            label={t("adm.colEmail")}
            value={f.email}
            onChange={(v) => setF({ ...f, email: v })}
            type="email"
            required
            dir="ltr"
          />
          <div className="space-y-1.5">
            <p className="text-xs text-muted-foreground">{t("settings.role")}</p>
            <Select
              value={f.role}
              onChange={(v) => setF({ ...f, role: v as Role })}
              className="w-full"
              options={roles.map((r) => ({ value: r, label: t(`role.${r}` as "role.admin") }))}
            />
          </div>
          <TextField
            label={t("adm.password")}
            value={f.password}
            onChange={(v) => setF({ ...f, password: v })}
            type="password"
            required
          />
          <Button type="submit" className="self-end" disabled={add.isPending}>
            {t("adm.create")}
          </Button>
        </form>
        <p className="mt-2 text-xs text-muted-foreground">{t("staff.rolesHint")}</p>
      </Card>
      <Card>
        <Table
          head={[
            t("pub.name"),
            t("adm.colEmail"),
            t("settings.role"),
            t("mfa.title"),
            t("adm.colStatus"),
            t("adm.colLastLogin"),
          ]}
        >
          {(list.data ?? []).map((u) => (
            <tr key={u.email}>
              <Td>{u.full_name || "—"}</Td>
              <Td>
                <span dir="ltr">{u.email}</span>
              </Td>
              <Td>
                {u.email === me ? (
                  t(`role.${u.role}` as "role.admin")
                ) : (
                  <Select
                    value={u.role}
                    onChange={(v) => change.mutate({ email: u.email, role: v as Role })}
                    className="h-8 text-xs"
                    label={t("settings.role")}
                    options={roles.map((r) => ({
                      value: r,
                      label: t(`role.${r}` as "role.admin"),
                    }))}
                  />
                )}
              </Td>
              <Td>
                {u.mfa ? (
                  <Badge tone="good">{t("mfa.onShort")}</Badge>
                ) : (
                  <Badge tone="warn">{t("mfa.offShort")}</Badge>
                )}
              </Td>
              <Td>
                {u.email === me ? (
                  <Badge tone="good">{status("active")}</Badge>
                ) : (
                  <Switch
                    checked={u.status === "active"}
                    aria-label={t("adm.colStatus")}
                    onCheckedChange={(on) =>
                      change.mutate({ email: u.email, status: on ? "active" : "suspended" })
                    }
                  />
                )}
              </Td>
              <Td className="text-xs">{day(u.last_login)}</Td>
            </tr>
          ))}
        </Table>
      </Card>
    </div>
  );
}

export function PlansPanel() {
  const { t } = useI18n();
  const list = useQuery({ queryKey: ["admin-plans"], queryFn: adminPlans });
  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">{t("plans.hint")}</p>
      {(list.data ?? []).map((p) => (
        <PlanEditor key={p.code} plan={p} />
      ))}
    </div>
  );
}

function PlanEditor({ plan }: { plan: Plan }) {
  const { t, lang } = useI18n();
  const qc = useQueryClient();
  const [p, setP] = useState(plan);
  const [price, setPrice] = useState(String(plan.price / 100));
  const save = useMutation({
    mutationFn: () =>
      savePlan({ ...p, price: Math.round(parseFloat(price.replace(",", ".") || "0") * 100) }),
    onSuccess: () => {
      toast.success(t("adm.saved"));
      void qc.invalidateQueries({ queryKey: ["admin-plans"] });
    },
    onError: fail(t("adm.failed")),
  });
  return (
    <Card
      title={
        <span>
          {lang === "fr" ? p.name_fr : p.name_ar}{" "}
          <code className="ms-2 text-xs text-muted-foreground">{p.code}</code>
        </span>
      }
    >
      <form
        className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <TextField
          label={`${t("plans.name")} (ع)`}
          value={p.name_ar}
          onChange={(v) => setP({ ...p, name_ar: v })}
          dir="rtl"
        />
        <TextField
          label={`${t("plans.name")} (FR)`}
          value={p.name_fr}
          onChange={(v) => setP({ ...p, name_fr: v })}
          dir="ltr"
        />
        <TextField
          label={`${t("plans.price")} (MAD)`}
          value={price}
          onChange={setPrice}
          dir="ltr"
        />
        <div className="space-y-1.5">
          <p className="text-xs text-muted-foreground">{t("plans.period")}</p>
          <Select
            value={p.period}
            onChange={(v) => setP({ ...p, period: v as Plan["period"] })}
            className="w-full"
            options={[
              { value: "month", label: t("pub.perMonth") },
              { value: "year", label: t("pub.perYear") },
              { value: "quote", label: t("pub.onQuote") },
            ]}
          />
        </div>
        <TextField
          label={`${t("plans.blurb")} (ع)`}
          value={p.blurb_ar}
          onChange={(v) => setP({ ...p, blurb_ar: v })}
          dir="rtl"
        />
        <TextField
          label={`${t("plans.blurb")} (FR)`}
          value={p.blurb_fr}
          onChange={(v) => setP({ ...p, blurb_fr: v })}
          dir="ltr"
        />
        <div className="space-y-1.5">
          <p className="text-xs text-muted-foreground">{t("pub.seats")}</p>
          <Input
            type="number"
            min={1}
            value={p.seats}
            onChange={(e) => setP({ ...p, seats: Number(e.target.value) })}
            className="h-10"
          />
        </div>
        <div className="space-y-1.5">
          <p className="text-xs text-muted-foreground">{t("pub.downloadsDay")}</p>
          <Input
            type="number"
            min={0}
            value={p.daily_downloads}
            onChange={(e) => setP({ ...p, daily_downloads: Number(e.target.value) })}
            className="h-10"
          />
        </div>
        <label className="flex items-center gap-2 text-sm">
          <Switch checked={p.public} onCheckedChange={(v) => setP({ ...p, public: v })} />
          {t("plans.public")}
        </label>
        <label className="flex items-center gap-2 text-sm">
          <Switch checked={p.active} onCheckedChange={(v) => setP({ ...p, active: v })} />
          {t("plans.active")}
        </label>
        <span className="self-center text-xs text-muted-foreground">
          {t("bill.vat")} {p.vat_rate / 100} % ·{" "}
          {money(Math.round(parseFloat(price.replace(",", ".") || "0") * 100), lang)}
        </span>
        <Button type="submit" size="sm" className="w-fit self-center" disabled={save.isPending}>
          {t("adm.save")}
        </Button>
      </form>
    </Card>
  );
}

export function OutboxPanel() {
  const { t } = useI18n();
  const list = useQuery({ queryKey: ["outbox"], queryFn: outbox });
  const [open, setOpen] = useState<number | null>(null);
  return (
    <Card>
      <p className="mb-3 text-sm text-muted-foreground">{t("mail.hint")}</p>
      {list.data && list.data.length === 0 ? (
        <Empty>{t("mail.empty")}</Empty>
      ) : (
        <Table head={[t("mail.to"), t("sup.subject"), t("adm.colStatus"), t("mail.created")]}>
          {(list.data ?? []).map((m) => (
            <tr
              key={m.id}
              className="cursor-pointer hover:bg-accent/40"
              onClick={() => setOpen(open === m.id ? null : m.id)}
            >
              <Td>
                <span dir="ltr">{m.to}</span>
              </Td>
              <Td>
                {m.subject}
                {open === m.id && (
                  <pre className="mt-2 whitespace-pre-wrap font-sans text-xs text-muted-foreground">
                    {m.body}
                  </pre>
                )}
                {m.error && <p className="text-xs text-destructive">{m.error}</p>}
              </Td>
              <Td>
                <Badge
                  tone={
                    STATUS_TONE[
                      m.status === "queued" ? "pending" : m.status === "sent" ? "active" : "overdue"
                    ]
                  }
                >
                  {t(`mail.${m.status}` as "mail.sent")}
                </Badge>
              </Td>
              <Td className="text-xs">{when(m.created_at)}</Td>
            </tr>
          ))}
        </Table>
      )}
    </Card>
  );
}
