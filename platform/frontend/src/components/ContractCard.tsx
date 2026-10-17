// One contract and the money received against it, with what can be done to it:
// record a transfer, attach the signed contract or a transfer's proof, make an invoice.
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { Banknote, FileCheck2, FileText, Paperclip, Receipt } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Badge, day, money } from "@/components/biz";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  addTransfer,
  cancelContract,
  downloadWithSession,
  invoiceFromTransfer,
  uploadContractFile,
  uploadProof,
  type ContractRow,
} from "@/lib/api-biz";
import { useI18n } from "@/lib/i18n";

const TONE = {
  awaiting_payment: "warn",
  upcoming: "info",
  active: "good",
  ended: "muted",
  cancelled: "muted",
  unassigned: "muted",
} as const;

export function ContractCard({ c, onChange }: { c: ContractRow; onChange: () => void }) {
  const { t, lang, num } = useI18n();
  const qc = useQueryClient();
  const [paying, setPaying] = useState(false);
  const [f, setF] = useState({
    amount: "",
    paid_on: new Date().toISOString().slice(0, 10),
    bank: "",
    bank_ref: "",
  });
  // money moved: every figure that counts it is read again
  const refresh = () => {
    onChange();
    for (const k of [
      "contracts",
      "transfers",
      "money",
      "overview",
      "crm-alerts",
      "orgs",
      "readers",
    ])
      void qc.invalidateQueries({ queryKey: [k] });
  };
  const fail = (e: unknown) => toast.error(e instanceof Error ? e.message : t("adm.failed"));
  const pay = useMutation({
    mutationFn: () =>
      addTransfer(c.id!, {
        ...f,
        amount: Math.round(parseFloat(f.amount.replace(",", ".") || "0") * 100),
      }),
    onSuccess: () => {
      toast.success(c.status === "awaiting_payment" ? t("con.activated") : t("con.transferSaved"));
      setPaying(false);
      refresh();
    },
    onError: fail,
  });
  const invoice = useMutation({
    mutationFn: invoiceFromTransfer,
    onSuccess: refresh,
    onError: fail,
  });
  const cancel = useMutation({
    mutationFn: () => cancelContract(c.id!),
    onSuccess: refresh,
    onError: fail,
  });
  const attach = async (fn: () => Promise<unknown>) => {
    try {
      await fn();
      toast.success(t("con.fileSaved"));
      refresh();
    } catch (e) {
      fail(e);
    }
  };
  if (c.id === null) {
    return (
      <div className="rounded-xl border border-dashed p-3 text-sm">
        <p className="font-medium">{t("con.unassigned")}</p>
        {c.transfers.map((x) => (
          <p key={x.id} className="text-muted-foreground">
            {day(x.paid_on)} · {money(x.amount, lang)} · {x.bank_ref}
          </p>
        ))}
      </div>
    );
  }
  return (
    <div className="rounded-xl border p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="font-medium">
            <span className="me-2 font-mono text-sm" dir="ltr">
              {c.number}
            </span>
            {lang === "fr" ? c.plan_name_fr : c.plan_name_ar} · {num(c.seats)} {t("pub.seats")}
          </p>
          <p className="text-sm text-muted-foreground">
            {day(c.starts_on)} → {day(c.ends_on)}
            {c.status === "active" && ` · ${num(c.days_left)} ${t("crm.days")}`}
          </p>
        </div>
        <Badge tone={TONE[c.status]}>{t(`con.st.${c.status}` as "con.st.active")}</Badge>
      </div>
      <div className="mt-3 grid grid-cols-3 gap-2 text-sm">
        <div>
          <p className="text-xs text-muted-foreground">{t("con.price")}</p>
          <p className="tabular-nums">{money(c.amount_ttc, lang)}</p>
        </div>
        <div>
          <p className="text-xs text-muted-foreground">{t("con.received")}</p>
          <p className="tabular-nums text-teal">{money(c.received, lang)}</p>
        </div>
        <div>
          <p className="text-xs text-muted-foreground">{t("bill.balance")}</p>
          <p className={`tabular-nums ${c.balance ? "text-destructive" : ""}`}>
            {money(c.balance, lang)}
          </p>
        </div>
      </div>
      {c.notes && (
        <p className="mt-2 whitespace-pre-wrap text-xs text-muted-foreground">{c.notes}</p>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-2 text-sm">
        {c.has_file ? (
          <Button
            size="sm"
            variant="outline"
            onClick={() =>
              void downloadWithSession(
                `/api/crm/contracts/${c.id}/file`,
                c.file_name || `${c.number}.pdf`,
              ).catch(fail)
            }
          >
            <FileCheck2 className="size-4 text-teal" />
            {t("con.signedContract")}
          </Button>
        ) : (
          <label className="inline-flex h-8 cursor-pointer items-center gap-1 rounded-md border border-amber-500/50 px-3 text-sm text-amber-700 hover:bg-accent dark:text-amber-300">
            <Paperclip className="size-4" />
            {t("con.attachContract")}
            <input
              type="file"
              accept=".pdf,image/*"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                e.target.value = "";
                if (file) void attach(() => uploadContractFile(c.id!, file));
              }}
            />
          </label>
        )}
        {c.status !== "cancelled" && !paying && (
          <Button
            size="sm"
            onClick={() => {
              setPaying(true);
              setF({ ...f, amount: String(c.balance / 100 || "") });
            }}
          >
            <Banknote className="size-4" />
            {t("con.recordTransfer")}
          </Button>
        )}
        {c.status === "awaiting_payment" && c.transfers.length === 0 && (
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              if (window.confirm(t("con.cancelConfirm"))) cancel.mutate();
            }}
          >
            {t("team.cancel")}
          </Button>
        )}
      </div>

      {paying && (
        <form
          className="mt-3 flex flex-wrap gap-2 rounded-lg bg-muted/50 p-2"
          onSubmit={(e) => {
            e.preventDefault();
            pay.mutate();
          }}
        >
          <Input
            required
            value={f.amount}
            onChange={(e) => setF({ ...f, amount: e.target.value })}
            placeholder={`${t("bill.amount")} (MAD TTC)`}
            className="h-9 w-36"
            dir="ltr"
            inputMode="decimal"
            aria-label={t("bill.amount")}
          />
          <Input
            type="date"
            value={f.paid_on}
            onChange={(e) => setF({ ...f, paid_on: e.target.value })}
            className="h-9 w-40"
            aria-label={t("con.paidOn")}
          />
          <Input
            value={f.bank}
            onChange={(e) => setF({ ...f, bank: e.target.value })}
            placeholder={t("con.bank")}
            className="h-9 w-32"
            aria-label={t("con.bank")}
          />
          <Input
            value={f.bank_ref}
            onChange={(e) => setF({ ...f, bank_ref: e.target.value })}
            placeholder={t("con.bankRef")}
            className="h-9 w-40"
            dir="ltr"
            aria-label={t("con.bankRef")}
          />
          <Button size="sm" type="submit" disabled={pay.isPending}>
            {t("adm.save")}
          </Button>
          <Button size="sm" type="button" variant="ghost" onClick={() => setPaying(false)}>
            ×
          </Button>
          {c.status === "awaiting_payment" && (
            <p className="w-full text-xs text-muted-foreground">{t("con.opensAccess")}</p>
          )}
        </form>
      )}

      {c.transfers.length > 0 && (
        <ul className="mt-3 divide-y rounded-lg border text-sm">
          {c.transfers.map((x) => (
            <li key={x.id} className="flex flex-wrap items-center gap-2 px-3 py-2">
              <Banknote className="size-4 text-teal" aria-hidden />
              <span className="tabular-nums font-medium">{money(x.amount, lang)}</span>
              <span className="text-muted-foreground">
                {day(x.paid_on)}
                {x.bank ? ` · ${x.bank}` : ""}
                {x.bank_ref ? ` · ` : ""}
                <span dir="ltr">{x.bank_ref}</span>
              </span>
              <span className="ms-auto flex flex-wrap gap-1">
                {x.has_proof ? (
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-7"
                    onClick={() =>
                      void downloadWithSession(
                        `/api/crm/transfers/${x.id}/proof`,
                        x.proof_name || `virement-${x.id}`,
                      ).catch(fail)
                    }
                  >
                    <FileText className="size-3.5" />
                    {t("con.proof")}
                  </Button>
                ) : (
                  <label className="inline-flex h-7 cursor-pointer items-center gap-1 rounded-md px-2 text-xs text-muted-foreground hover:bg-accent">
                    <Paperclip className="size-3.5" />
                    {t("con.attachProof")}
                    <input
                      type="file"
                      accept=".pdf,image/*"
                      className="hidden"
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        e.target.value = "";
                        if (file) void attach(() => uploadProof(x.id, file));
                      }}
                    />
                  </label>
                )}
                {x.invoice_id ? (
                  <Link
                    to="/invoice/$invoiceId"
                    params={{ invoiceId: String(x.invoice_id) }}
                    className="inline-flex h-7 items-center gap-1 rounded-md px-2 text-xs text-teal hover:underline"
                  >
                    <Receipt className="size-3.5" />
                    {t("bill.invoice")}
                  </Link>
                ) : (
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-7 text-xs"
                    onClick={() => invoice.mutate(x.id)}
                    disabled={invoice.isPending}
                  >
                    <Receipt className="size-3.5" />
                    {t("con.makeInvoice")}
                  </Button>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
