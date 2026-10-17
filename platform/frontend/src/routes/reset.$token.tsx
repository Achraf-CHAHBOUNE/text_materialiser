import { useMutation } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useState } from "react";
import { toast } from "sonner";

import { TextField } from "@/components/biz";
import { PublicShell } from "@/components/PublicShell";
import { Button } from "@/components/ui/button";
import { resetPassword } from "@/lib/api-biz";
import { useI18n } from "@/lib/i18n";

export const Route = createFileRoute("/reset/$token")({
  head: () => ({
    meta: [{ title: "كلمة المرور · Mot de passe" }, { name: "referrer", content: "no-referrer" }],
  }),
  component: Reset,
});

function Reset() {
  const { token } = Route.useParams();
  const { t } = useI18n();
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const reset = useMutation({
    mutationFn: async () => {
      if (pw !== pw2) throw new Error(t("acc.pwMismatch"));
      return resetPassword(token, pw);
    },
    onError: (e) => toast.error(e instanceof Error ? e.message : t("adm.failed")),
  });
  return (
    <PublicShell>
      <div className="mx-auto max-w-md rounded-2xl border bg-card p-6 shadow-soft">
        <h1 className="text-h2 font-semibold">{t("reset.title")}</h1>
        {reset.isSuccess ? (
          <p className="mt-4 text-sm">
            {t("reset.done")}{" "}
            <Link to="/" className="text-teal underline">
              {t("login.submit")}
            </Link>
          </p>
        ) : (
          <form
            className="mt-5 space-y-3"
            onSubmit={(e) => {
              e.preventDefault();
              reset.mutate();
            }}
          >
            <TextField
              label={t("acc.newPassword")}
              value={pw}
              onChange={setPw}
              type="password"
              required
            />
            <TextField
              label={t("acc.confirmPassword")}
              value={pw2}
              onChange={setPw2}
              type="password"
              required
            />
            <p className="text-xs text-muted-foreground">{t("acc.pwRule")}</p>
            <Button type="submit" className="w-full" disabled={reset.isPending}>
              {t("reset.submit")}
            </Button>
          </form>
        )}
      </div>
    </PublicShell>
  );
}
