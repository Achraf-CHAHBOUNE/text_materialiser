import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { Ban, CheckCircle2, Download, Eye, FilePlus2, LogIn, LogOut, Mail, Search, SearchX } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { AppShell } from "@/components/AppShell";
import { Bars } from "@/components/Bars";
import { Badge, Card, day, Empty, money, Select, Stat, STATUS_TONE, Table, Td, when } from "@/components/biz";
import { ContractCard } from "@/components/ContractCard";
import { CrmNav } from "@/components/CrmNav";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { addNote, emailReader, exportActivity, forceLogout, readerDetail, updateUser, type ReaderDetail } from "@/lib/api-biz";
import { useI18n } from "@/lib/i18n";

export const Route = createFileRoute("/crm/users/$email")({
  component: ReaderPage,
});

const ICON: Record<string, typeof Eye> = { view: Eye, download: Download, search: Search, search_empty: SearchX, login: LogIn, translate: Eye };

function ReaderPage() {
  const { email } = Route.useParams();
  const { t, lang, num, status, chamber } = useI18n();
  const qc = useQueryClient();
  const [days, setDays] = useState("30");
  const [filter, setFilter] = useState("");
  const q = useQuery({ queryKey: ["reader", email, days], queryFn: () => readerDetail(email, Number(days)) });
  const refresh = () => { void qc.invalidateQueries({ queryKey: ["reader", email] }); void qc.invalidateQueries({ queryKey: ["readers"] }); };
  const logout = useMutation({ mutationFn: () => forceLogout(email), onSuccess: (r) => { toast.success(`${t("trk.loggedOut")} (${r.ended})`); refresh(); } });
  const suspend = useMutation({ mutationFn: (s: "active" | "suspended") => updateUser(email, { status: s }), onSuccess: refresh,
    onError: (e) => toast.error(e instanceof Error ? e.message : t("adm.failed")) });
  const d = q.data;
  // why a session ended, as the server records it, in the page's language
  const why = (w: string) => w === "signed in elsewhere" ? t("trk.why.elsewhere")
    : w === "signed out" ? t("trk.why.signedOut")
    : w.startsWith("password") ? t("trk.why.password")
    : w === "suspended" ? t("st.suspended")
    : w.startsWith("signed out by") ? `${t("trk.why.byAdmin")} ${w.slice(14)}` : w;
  const timeline = (d?.timeline ?? []).filter((x) => !filter || x.action === filter || (filter === "search" && x.action === "search_empty"));
  return (
    <AppShell title={d?.user.full_name || email} description={d ? `${email}${d.org ? ` · ${d.org.name}` : ""}` : email}
              action={d && (
                <div className="flex flex-wrap gap-2">
                  {d.org && <Button asChild size="sm"><Link to="/crm/orgs/$orgId" params={{ orgId: String(d.org.id) }}><FilePlus2 className="size-4" />{t("con.renew")}</Link></Button>}
                  <Button size="sm" variant="outline" onClick={() => void exportActivity(Number(days), email).catch(() => toast.error(t("adm.failed")))}>
                    <Download className="size-4" />{t("trk.export")}</Button>
                  <Button size="sm" variant="outline" onClick={() => logout.mutate()}><LogOut className="size-4" />{t("trk.forceLogout")}</Button>
                  <Button size="sm" variant="outline" className={d.user.status === "active" ? "text-destructive" : ""}
                          onClick={() => suspend.mutate(d.user.status === "active" ? "suspended" : "active")}>
                    {d.user.status === "active" ? <><Ban className="size-4" />{t("adm.suspend")}</> : <><CheckCircle2 className="size-4" />{t("adm.activate")}</>}
                  </Button>
                </div>
              )}>
      <CrmNav />
      {d && (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
            <Stat label={`${t("trk.reads")} (${num(d.days)} ${t("crm.days")})`} value={num(d.recent.view ?? 0)} hint={`${num(d.totals.view ?? 0)} ${t("trk.inTotal")}`} />
            <Stat label={t("trk.downloads")} value={num(d.recent.download ?? 0)} hint={`${t("trk.today")} ${num(d.downloads_today)} / ${num(d.quota)}`} />
            <Stat label={t("trk.searches")} value={num((d.recent.search ?? 0) + (d.recent.search_empty ?? 0))}
                  hint={d.recent.search_empty ? `${num(d.recent.search_empty)} ${t("trk.empty")}` : undefined} />
            <Stat label={t("trk.paid")} value={money(d.money.paid, lang)} tone="good"
                  hint={d.money.owed ? <span className="text-destructive">{t("trk.owes")} {money(d.money.owed, lang)}</span> : undefined} />
            <Stat label={t("acc.subscription")} value={d.subscription ? (lang === "fr" ? d.subscription.plan_name_fr : d.subscription.plan_name_ar) : "—"}
                  hint={<Badge tone={STATUS_TONE[d.access]}>{status(d.access)}{d.subscription ? ` · ${day(d.subscription.ends_on)}` : ""}</Badge>} />
          </div>

          <div className="mt-4 grid gap-4 lg:grid-cols-3">
            <Reading d={d} />
            <Notes email={email} d={d} onChange={refresh} />
            <EmailForm email={email} onSent={refresh} />
          </div>

          <Card className="mt-4" title={t("trk.activity")}
                action={<Select value={days} onChange={setDays} label={t("cab.period")} className="h-9"
                                options={[{ value: "7", label: `7 ${t("crm.days")}` }, { value: "30", label: `30 ${t("crm.days")}` }, { value: "90", label: `90 ${t("crm.days")}` }]} />}>
            <Bars rows={d.series} days={Number(days)} />
          </Card>

          <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
            <Card title={t("trk.timeline")} action={
              <Select value={filter} onChange={setFilter} label={t("trk.show")} className="h-9" options={[
                { value: "", label: t("trk.showAll") }, { value: "view", label: t("trk.reads") },
                { value: "download", label: t("trk.downloads") }, { value: "search", label: t("trk.searches") },
                { value: "login", label: t("trk.logins") }]} />}>
              {timeline.length === 0 ? <Empty>{t("hist.empty")}</Empty> : (
                <ul className="max-h-[32rem] divide-y overflow-auto text-sm">
                  {timeline.map((x, i) => {
                    const I = ICON[x.action] ?? Eye;
                    return (
                      <li key={i} className="flex items-start gap-3 py-2">
                        <I className={`mt-0.5 size-4 shrink-0 ${x.action === "search_empty" ? "text-destructive" : "text-muted-foreground"}`} aria-hidden />
                        <span className="w-32 shrink-0 text-xs tabular-nums text-muted-foreground">{when(x.ts)}</span>
                        <span className="min-w-0">
                          {x.action === "login" && t("trk.loggedIn")}
                          {(x.action === "search" || x.action === "search_empty") && <>{t("hist.searched")} « {x.query} »{x.action === "search_empty" && <span className="text-destructive"> — {t("trk.noResult")}</span>}</>}
                          {x.doc_id && (
                            <Link to="/ruling/$docId" params={{ docId: x.doc_id }} className="hover:text-teal">
                              {x.action === "download" ? t("hist.downloaded") : x.action === "translate" ? t("trk.translated") : t("hist.read")} {t("ruling.decisionOf")} {num(x.decision_no ?? "")}
                              <span className="text-muted-foreground"> · {x.date} · {chamber(x.chamber ?? "")}</span>
                            </Link>
                          )}
                        </span>
                      </li>
                    );
                  })}
                </ul>
              )}
            </Card>
            <div className="space-y-4">
              <Card title={t("trk.profile")}>
                <dl className="space-y-1.5 text-sm">
                  <div className="flex justify-between gap-2"><dt className="text-muted-foreground">{t("settings.role")}</dt><dd>{t(`role.${d.user.role}` as "role.client")}</dd></div>
                  <div className="flex justify-between gap-2"><dt className="text-muted-foreground">{t("adm.colStatus")}</dt><dd><Badge tone={STATUS_TONE[d.user.status]}>{status(d.user.status)}</Badge></dd></div>
                  <div className="flex justify-between gap-2"><dt className="text-muted-foreground">{t("pub.phone")}</dt><dd dir="ltr">{d.user.phone || "—"}</dd></div>
                  <div className="flex justify-between gap-2"><dt className="text-muted-foreground">{t("acc.emailLanguage")}</dt><dd>{d.user.language === "fr" ? "Français" : "العربية"}</dd></div>
                  <div className="flex justify-between gap-2"><dt className="text-muted-foreground">{t("mfa.title")}</dt><dd>{d.user.mfa ? t("mfa.onShort") : t("mfa.offShort")}</dd></div>
                  <div className="flex justify-between gap-2"><dt className="text-muted-foreground">{t("trk.since")}</dt><dd>{day(d.user.created_at)}</dd></div>
                  {d.org && <div className="flex justify-between gap-2"><dt className="text-muted-foreground">{t("crm.org")}</dt>
                    <dd><Link to="/crm/orgs/$orgId" params={{ orgId: String(d.org.id) }} className="text-teal hover:underline">{d.org.name}</Link></dd></div>}
                </dl>
              </Card>
              <Card title={t("trk.chambers")}>
                {d.chambers.length === 0 ? <Empty>{t("hist.empty")}</Empty> : (
                  <ul className="space-y-1.5 text-sm">
                    {d.chambers.map((c) => {
                      const top = d.chambers[0]?.count ?? 1;
                      return (
                        <li key={c.chamber}>
                          <div className="flex justify-between"><span>{chamber(c.chamber)}</span><span className="tabular-nums">{num(c.count)}</span></div>
                          <div className="mt-0.5 h-1.5 rounded bg-muted"><div className="h-1.5 rounded bg-teal" style={{ width: `${(c.count / top) * 100}%` }} /></div>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </Card>
              <Card title={t("trk.devices")}>
                {d.sessions.length === 0 ? <Empty>{t("trk.never")}</Empty> : (
                  <ul className="divide-y text-xs">
                    {d.sessions.slice(0, 8).map((x, i) => (
                      <li key={i} className="py-1.5">
                        <p className="flex justify-between gap-2"><span dir="ltr">{x.ip}</span>
                          {x.ended ? <span className="text-muted-foreground">{t("trk.ended")}</span> : <Badge tone="good">{t("trk.signedIn")}</Badge>}</p>
                        <p className="truncate text-muted-foreground" title={x.device}>{x.device || "—"}</p>
                        <p className="text-muted-foreground">{when(x.created_at)}{x.why ? ` · ${why(x.why)}` : ""}</p>
                      </li>
                    ))}
                  </ul>
                )}
              </Card>
            </div>
          </div>

          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <Card title={t("trk.downloadsList")}>
              {d.downloads.length === 0 ? <Empty>{t("hist.empty")}</Empty> : (
                <Table head={[t("trk.downloadedOn"), t("ruling.decisionOf"), t("trk.ref")]} minWidth="24rem">
                  {d.downloads.slice(0, 50).map((x) => (
                    <tr key={x.ref}>
                      <Td className="text-xs">{when(x.at)}</Td>
                      <Td><Link to="/ruling/$docId" params={{ docId: x.doc_id }} className="hover:text-teal">{num(x.decision_no ?? "")} · {chamber(x.chamber ?? "")}</Link></Td>
                      <Td><code className="text-xs" dir="ltr">{x.ref}</code></Td>
                    </tr>
                  ))}
                </Table>
              )}
              <p className="mt-2 text-xs text-muted-foreground">{t("trk.refHint")}</p>
            </Card>
            <div className="space-y-3">
              {d.contracts.length === 0 ? <Card title={t("con.contracts")}><Empty>{t("con.none")}</Empty></Card>
                : d.contracts.map((c) => <ContractCard key={c.id ?? "loose"} c={c} onChange={refresh} />)}
            {d.money.invoices.length > 0 && <Card title={t("bill.invoices")}>
              {(
                <Table head={[t("bill.number"), t("bill.issued"), t("bill.total"), t("bill.balance"), t("adm.colStatus")]} minWidth="28rem">
                  {d.money.invoices.map((i) => (
                    <tr key={i.id}>
                      <Td><Link to="/invoice/$invoiceId" params={{ invoiceId: String(i.id) }} className="font-mono text-teal hover:underline" dir="ltr">{i.number}</Link></Td>
                      <Td>{day(i.issued_on)}</Td><Td className="tabular-nums">{money(i.amount_ttc, lang)}</Td>
                      <Td className="tabular-nums">{money(i.balance, lang)}</Td>
                      <Td><Badge tone={STATUS_TONE[i.status]}>{status(i.status)}</Badge></Td>
                    </tr>
                  ))}
                </Table>
              )}
            </Card>}
            </div>
          </div>
        </>
      )}
    </AppShell>
  );
}

/** How long the reader stays on the rulings, in which language, and on which ones longest. */
function Reading({ d }: { d: ReaderDetail }) {
  const { t, num, chamber } = useI18n();
  const r = d.reading;
  return (
    <Card title={t("trk.readingTime")}>
      <p className="text-2xl font-semibold tabular-nums">{num(r.minutes)} <span className="text-sm font-normal text-muted-foreground">{t("trk.min")}</span></p>
      <p className="text-xs text-muted-foreground">{num(d.days)} {t("crm.days")} · {num(r.french_share)}% {t("trk.inFrench")} · {num(100 - r.french_share)}% {t("trk.inArabic")}</p>
      {r.longest.length > 0 && (
        <ul className="mt-2 divide-y text-xs">
          {r.longest.slice(0, 5).map((x) => (
            <li key={x.doc_id} className="flex justify-between gap-2 py-1">
              <Link to="/ruling/$docId" params={{ docId: x.doc_id }} className="truncate hover:text-teal">{num(x.decision_no ?? "")} · {chamber(x.chamber ?? "")}</Link>
              <span className="shrink-0 tabular-nums">{num(x.minutes)} {t("trk.min")}</span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

/** What the team knows about this reader, for the team only. */
function Notes({ email, d, onChange }: { email: string; d: ReaderDetail; onChange: () => void }) {
  const { t } = useI18n();
  const [body, setBody] = useState("");
  const add = useMutation({ mutationFn: () => addNote(email, body), onSuccess: () => { setBody(""); onChange(); },
    onError: (e) => toast.error(e instanceof Error ? e.message : t("adm.failed")) });
  return (
    <Card title={t("trk.notes")}>
      <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (body.trim()) add.mutate(); }}>
        <Input value={body} onChange={(e) => setBody(e.target.value)} placeholder={t("trk.notePlaceholder")} className="h-9" aria-label={t("trk.notes")} />
        <Button type="submit" size="sm" disabled={add.isPending || !body.trim()}>{t("trk.addNote")}</Button>
      </form>
      {d.notes.length > 0 && (
        <ul className="mt-2 max-h-48 divide-y overflow-auto text-sm">
          {d.notes.map((n) => (
            <li key={n.id} className="py-1.5"><p className="whitespace-pre-wrap">{n.body}</p>
              <p className="text-xs text-muted-foreground">{n.author} · {when(n.at)}</p></li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function EmailForm({ email, onSent }: { email: string; onSent: () => void }) {
  const { t } = useI18n();
  const [f, setF] = useState({ subject: "", body: "" });
  const send = useMutation({ mutationFn: () => emailReader(email, f.subject, f.body),
    onSuccess: () => { toast.success(t("trk.emailQueued")); setF({ subject: "", body: "" }); onSent(); },
    onError: (e) => toast.error(e instanceof Error ? e.message : t("adm.failed")) });
  return (
    <Card title={t("trk.writeEmail")}>
      <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); send.mutate(); }}>
        <Input required value={f.subject} onChange={(e) => setF({ ...f, subject: e.target.value })} placeholder={t("sup.subject")} className="h-9" aria-label={t("sup.subject")} />
        <Textarea required value={f.body} onChange={(e) => setF({ ...f, body: e.target.value })} rows={3} aria-label={t("trk.writeEmail")} />
        <Button type="submit" size="sm" disabled={send.isPending}><Mail className="size-4" />{t("trk.send")}</Button>
      </form>
    </Card>
  );
}
