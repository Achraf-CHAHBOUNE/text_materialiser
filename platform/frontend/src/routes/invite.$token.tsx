import { useMutation, useQuery } from "@tanstack/react-query";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { toast } from "sonner";

import { TextField } from "@/components/biz";
import { PublicShell } from "@/components/PublicShell";
import { Button } from "@/components/ui/button";
import { acceptInvitation, invitationInfo } from "@/lib/api-biz";
import { useStore } from "@/lib/app-store";
import { useI18n } from "@/lib/i18n";

export const Route = createFileRoute("/invite/$token")({
  head: () => ({
    meta: [{ title: "دعوة · Invitation" }, { name: "referrer", content: "no-referrer" }],
  }),
  component: AcceptInvite,
});

function AcceptInvite() {
  const { token } = Route.useParams();
  const { t } = useI18n();
  const { login } = useStore();
  const navigate = useNavigate();
  const info = useQuery({
    queryKey: ["invitation", token],
    queryFn: () => invitationInfo(token),
    retry: false,
  });
  const [name, setName] = useState("");
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const accept = useMutation({
    mutationFn: async () => {
      if (pw !== pw2) throw new Error(t("acc.pwMismatch"));
      const r = await acceptInvitation(token, pw, name);
      await login(r.email, pw);
    },
    onSuccess: () => navigate({ to: "/browse" }),
    onError: (e) => toast.error(e instanceof Error ? e.message : t("adm.failed")),
  });

  return (
    <PublicShell>
      <div className="mx-auto max-w-md rounded-2xl border bg-card p-6 shadow-soft">
        {info.isError ? (
          <p className="text-sm text-destructive">{t("inv.invalid")}</p>
        ) : !info.data ? (
          <p className="text-sm text-muted-foreground">{t("adm.loading")}</p>
        ) : (
          <>
            <h1 className="text-h2 font-semibold">
              {t("inv.title")} {info.data.org}
            </h1>
            <p className="mt-1 text-sm text-muted-foreground" dir="ltr">
              {info.data.email}
            </p>
            <form
              className="mt-5 space-y-3"
              onSubmit={(e) => {
                e.preventDefault();
                accept.mutate();
              }}
            >
              <TextField label={t("pub.name")} value={name} onChange={setName} />
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
              <Button type="submit" className="w-full" disabled={accept.isPending}>
                {t("inv.accept")}
              </Button>
            </form>
          </>
        )}
      </div>
    </PublicShell>
  );
}
