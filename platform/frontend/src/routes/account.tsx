import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { ShieldCheck, Trash2, UserPlus } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { AppShell } from "@/components/AppShell";
import { Badge, Card, day, Empty, money, Select, STATUS_TONE, Table, Td, TextField } from "@/components/biz";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  cancelInvitation, changePassword, getAccount, getTeam, inviteMember, mfaDisable, mfaEnable, mfaSetup,
  myInvoices, removeMember, updateProfile, type Role,
} from "@/lib/api-biz";
import { useI18n } from "@/lib/i18n";

export const Route = createFileRoute("/account")({
  head: () => ({ meta: [{ title: "حسابي · Mon compte" }] }),
  component: AccountPage,
});

const fail = (fallback: string) => (e: unknown) => toast.error(e instanceof Error ? e.message : fallback);

function AccountPage() {
  const { t, lang, num, status } = useI18n();
  const acc = useQuery({ queryKey: ["account"], queryFn: getAccount });
  const a = acc.data;
  const isHolder = a?.user.role === "client_admin";

  return (
    <AppShell title={t("acc.title")} description={a?.org?.name ?? a?.user.email}>
      <div className="grid gap-4 lg:grid-cols-2">
        {a?.org && (
          <Card title={t("acc.subscription")} className="lg:col-span-2">
            {a.subscription ? (
              <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
                <span className="font-medium">{lang === "fr" ? a.subscription.plan_name_fr : a.subscription.plan_name_ar}</span>
                <Badge tone={STATUS_TONE[a.access]}>{status(a.access === "ok" ? a.subscription.status : a.access)}</Badge>
                <span>{t("acc.until")} {day(a.subscription.ends_on)}</span>
                {a.seats && <span>{num(a.seats.used)} / {num(a.seats.total)} {t("pub.seats")}</span>}
                {a.quota !== undefined && <span>{num(a.quota)} {t("pub.downloadsDay")}</span>}
              </div>
            ) : <p className="text-sm text-muted-foreground">{t("acc.noSubscription")}</p>}
            {a.access !== "ok" && (
              <p className="mt-3 rounded-lg bg-destructive/10 p-3 text-sm text-destructive">
                {t("acc.lapsed")} <Link to="/support" className="underline">{t("nav.support")}</Link>
              </p>
            )}
          </Card>
        )}
        {a && <Profile key={a.user.email} initial={a.user} />}
        <Password />
        {a && <TwoFactor enabled={a.user.mfa} required={a.mfa_required} />}
        {isHolder && <Team />}
        {isHolder && <Invoices />}
      </div>
    </AppShell>
  );
}

function Profile({ initial }: { initial: { full_name: string; phone: string; language: "ar" | "fr"; email: string } }) {
  const { t } = useI18n();
  const qc = useQueryClient();
  const [f, setF] = useState({ full_name: initial.full_name, phone: initial.phone, language: initial.language });
  const save = useMutation({
    mutationFn: () => updateProfile(f),
    onSuccess: () => { toast.success(t("adm.saved")); void qc.invalidateQueries({ queryKey: ["account"] }); },
    onError: fail(t("adm.failed")),
  });
  return (
    <Card title={t("acc.profile")}>
      <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        <p className="text-sm text-muted-foreground" dir="ltr">{initial.email}</p>
        <TextField label={t("pub.name")} value={f.full_name} onChange={(v) => setF({ ...f, full_name: v })} />
        <TextField label={t("pub.phone")} value={f.phone} onChange={(v) => setF({ ...f, phone: v })} dir="ltr" />
        <div className="space-y-1.5">
          <p className="text-xs text-muted-foreground">{t("acc.emailLanguage")}</p>
          <Select value={f.language} onChange={(v) => setF({ ...f, language: v as "ar" | "fr" })}
                  options={[{ value: "ar", label: "العربية" }, { value: "fr", label: "Français" }]} />
        </div>
        <Button type="submit" size="sm" disabled={save.isPending}>{t("adm.save")}</Button>
      </form>
    </Card>
  );
}

function Password() {
  const { t } = useI18n();
  const [cur, setCur] = useState("");
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const save = useMutation({
    mutationFn: async () => {
      if (pw !== pw2) throw new Error(t("acc.pwMismatch"));
      return changePassword(cur, pw);
    },
    onSuccess: () => { toast.success(t("acc.pwChanged")); setCur(""); setPw(""); setPw2(""); },
    onError: fail(t("adm.failed")),
  });
  return (
    <Card title={t("acc.password")}>
      <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        <TextField label={t("acc.currentPassword")} value={cur} onChange={setCur} type="password" required />
        <TextField label={t("acc.newPassword")} value={pw} onChange={setPw} type="password" required />
        <TextField label={t("acc.confirmPassword")} value={pw2} onChange={setPw2} type="password" required />
        <p className="text-xs text-muted-foreground">{t("acc.pwRule")} {t("acc.pwOthers")}</p>
        <Button type="submit" size="sm" disabled={save.isPending}>{t("adm.save")}</Button>
      </form>
    </Card>
  );
}

function TwoFactor({ enabled, required }: { enabled: boolean; required: boolean }) {
  const { t } = useI18n();
  const qc = useQueryClient();
  const [setup, setSetup] = useState<{ secret: string; uri: string } | null>(null);
  const [code, setCode] = useState("");
  const done = () => { setSetup(null); setCode(""); void qc.invalidateQueries({ queryKey: ["account"] }); };
  const start = useMutation({ mutationFn: mfaSetup, onSuccess: setSetup, onError: fail(t("adm.failed")) });
  const enable = useMutation({ mutationFn: () => mfaEnable(code), onSuccess: () => { toast.success(t("mfa.on")); done(); }, onError: fail(t("login.wrongCode")) });
  const disable = useMutation({ mutationFn: () => mfaDisable(code), onSuccess: () => { toast.success(t("mfa.off")); done(); }, onError: fail(t("login.wrongCode")) });
  return (
    <Card title={<span className="flex items-center gap-2"><ShieldCheck className="size-4 text-teal" />{t("mfa.title")}</span>}>
      <p className="text-sm text-muted-foreground">{enabled ? t("mfa.isOn") : t("mfa.explain")}</p>
      {required && !enabled && <p className="mt-2 text-sm text-amber-700 dark:text-amber-300">{t("mfa.required")}</p>}
      {!enabled && !setup && (
        <Button size="sm" className="mt-3" onClick={() => start.mutate()} disabled={start.isPending}>{t("mfa.enable")}</Button>
      )}
      {setup && (
        <div className="mt-3 space-y-2 text-sm">
          <p>{t("mfa.scan")}</p>
          <code className="block break-all rounded bg-muted p-2 text-xs" dir="ltr">{setup.secret}</code>
          <a href={setup.uri} className="text-xs text-teal underline" dir="ltr">{t("mfa.openApp")}</a>
        </div>
      )}
      {(setup || enabled) && (
        <form className="mt-3 flex gap-2" onSubmit={(e) => { e.preventDefault(); (enabled ? disable : enable).mutate(); }}>
          <Input value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} maxLength={6}
                 inputMode="numeric" placeholder="123456" className="h-9 w-32 tracking-widest" dir="ltr"
                 aria-label={t("login.code")} />
          <Button size="sm" type="submit" variant={enabled ? "outline" : "default"}>
            {enabled ? t("mfa.disable") : t("mfa.confirm")}
          </Button>
        </form>
      )}
    </Card>
  );
}

function Team() {
  const { t, lang, num, status } = useI18n();
  const qc = useQueryClient();
  const team = useQuery({ queryKey: ["team"], queryFn: getTeam });
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("client");
  const refresh = () => { void qc.invalidateQueries({ queryKey: ["team"] }); void qc.invalidateQueries({ queryKey: ["account"] }); };
  const invite = useMutation({
    mutationFn: () => inviteMember(email, role, lang),
    onSuccess: () => { toast.success(t("team.invited")); setEmail(""); refresh(); },
    onError: (e) => toast.error(e instanceof Error && e.message.includes("seats") ? t("team.noSeat") : e instanceof Error ? e.message : t("adm.failed")),
  });
  const remove = useMutation({ mutationFn: removeMember, onSuccess: refresh, onError: fail(t("adm.failed")) });
  const cancel = useMutation({ mutationFn: cancelInvitation, onSuccess: refresh, onError: fail(t("adm.failed")) });
  const d = team.data;
  return (
    <Card title={t("team.title")} className="lg:col-span-2"
          action={d && <span className="text-xs text-muted-foreground">{num(d.seats.used)} / {num(d.seats.total)} {t("pub.seats")}</span>}>
      <form className="mb-4 flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); invite.mutate(); }}>
        <Input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="collegue@cabinet.ma"
               className="h-10 max-w-xs" dir="ltr" aria-label={t("adm.colEmail")} />
        <Select value={role} onChange={(v) => setRole(v as Role)} label={t("settings.role")}
                options={[{ value: "client", label: t("role.client") }, { value: "client_admin", label: t("role.client_admin") }]} />
        <Button type="submit" disabled={invite.isPending}><UserPlus className="size-4" />{t("team.invite")}</Button>
      </form>
      <Table head={[t("pub.name"), t("adm.colEmail"), t("settings.role"), t("adm.colStatus"), t("adm.colLastLogin"), ""]}>
        {(d?.members ?? []).map((m) => (
          <tr key={m.email}>
            <Td>{m.full_name || "—"}</Td>
            <Td><span dir="ltr">{m.email}</span></Td>
            <Td>{t(`role.${m.role}` as "role.client")}</Td>
            <Td><Badge tone={STATUS_TONE[m.status]}>{status(m.status)}</Badge></Td>
            <Td>{day(m.last_login)}</Td>
            <Td>{m.status === "active" && m.role !== "client_admin" && (
              <Button size="sm" variant="ghost" className="text-destructive" onClick={() => remove.mutate(m.email)}
                      aria-label={t("team.remove")}><Trash2 className="size-4" /></Button>
            )}</Td>
          </tr>
        ))}
        {(d?.invitations ?? []).map((i) => (
          <tr key={`i${i.id}`} className="text-muted-foreground">
            <Td>—</Td><Td><span dir="ltr">{i.email}</span></Td><Td>{t(`role.${i.role}` as "role.client")}</Td>
            <Td><Badge tone="info">{t("team.pending")}</Badge></Td><Td>{t("team.until")} {day(i.expires_at)}</Td>
            <Td><Button size="sm" variant="ghost" onClick={() => cancel.mutate(i.id)}>{t("team.cancel")}</Button></Td>
          </tr>
        ))}
      </Table>
    </Card>
  );
}

function Invoices() {
  const { t, lang, status } = useI18n();
  const inv = useQuery({ queryKey: ["my-invoices"], queryFn: myInvoices });
  return (
    <Card title={t("bill.invoices")} className="lg:col-span-2">
      {(inv.data ?? []).length === 0 ? <Empty>{t("bill.none")}</Empty> : (
        <Table head={[t("bill.number"), t("bill.issued"), t("bill.due"), t("bill.total"), t("bill.balance"), t("adm.colStatus")]}>
          {(inv.data ?? []).map((i) => (
            <tr key={i.id}>
              <Td><Link to="/invoice/$invoiceId" params={{ invoiceId: String(i.id) }} className="text-teal underline-offset-4 hover:underline" dir="ltr">{i.number}</Link></Td>
              <Td>{day(i.issued_on)}</Td><Td>{day(i.due_on)}</Td>
              <Td className="tabular-nums">{money(i.amount_ttc, lang)}</Td>
              <Td className="tabular-nums">{money(i.balance, lang)}</Td>
              <Td><Badge tone={STATUS_TONE[i.status]}>{status(i.status)}</Badge></Td>
            </tr>
          ))}
        </Table>
      )}
    </Card>
  );
}
