import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { Lock, Mail } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Wordmark } from "@/components/Brand";
import { useStore } from "@/lib/app-store";
import { toast } from "sonner";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Anonymize — PII redaction for Arabic court rulings" },
      {
        name: "description",
        content:
          "Sign in to Anonymize: automatic PII redaction for Arabic court rulings and case-trajectory linking across first instance, appeal and cassation.",
      },
    ],
  }),
  component: LoginPage,
});

function LoginPage() {
  const navigate = useNavigate();
  const { login } = useStore();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      <div className="flex items-center justify-center px-4 py-12 sm:px-8">
        <div className="w-full max-w-sm animate-rise-in">
          <Wordmark className="mb-8" />
          <h1 className="text-h1 font-semibold">Sign in to your workspace</h1>
          <p className="mt-1.5 text-sm text-muted-foreground">
            Anonymize Arabic court rulings and map case trajectories.
          </p>

          <form
            className="mt-8 space-y-4"
            onSubmit={async (e) => {
              e.preventDefault();
              setErr(null);
              setBusy(true);
              try {
                const role = await login(email, password);
                toast.success("Welcome back", { description: email });
                navigate({ to: role === "admin" ? "/admin" : "/dashboard" });
              } catch (ex) {
                setErr(ex instanceof Error ? ex.message : "Login failed");
              } finally {
                setBusy(false);
              }
            }}
          >
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <div className="relative">
                <Mail
                  className="pointer-events-none absolute start-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
                  aria-hidden
                />
                <Input
                  id="email"
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="h-11 ps-9"
                  placeholder="you@firm.ma"
                />
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
              <div className="relative">
                <Lock
                  className="pointer-events-none absolute start-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
                  aria-hidden
                />
                <Input
                  id="password"
                  type="password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="h-11 ps-9"
                  placeholder="••••••••"
                />
              </div>
            </div>

            {err && (
              <p className="rounded-lg border border-destructive/30 bg-destructive/8 px-3 py-2 text-sm text-destructive">
                {err}
              </p>
            )}

            <Button type="submit" disabled={busy} className="h-11 w-full shadow-sm">
              {busy ? "Signing in…" : "Sign in"}
            </Button>
          </form>
        </div>
      </div>

      <div className="relative hidden overflow-hidden border-s bg-sidebar lg:flex lg:items-center lg:justify-center">
        <div className="grad-brand absolute inset-0 opacity-[0.10]" aria-hidden />
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 opacity-[0.5] [background-image:linear-gradient(to_right,var(--color-border)_1px,transparent_1px),linear-gradient(to_bottom,var(--color-border)_1px,transparent_1px)] [background-size:56px_56px] [mask-image:radial-gradient(ellipse_at_center,black,transparent_75%)]"
        />
        <div dir="rtl" className="relative m-10 max-w-md rounded-2xl border bg-card p-7 shadow-lg">
          <p className="font-ar text-xs font-medium text-teal">معاينة النص المجهول</p>
          <p className="font-ar mt-4 text-[15px] leading-loose">
            ينوب عنها الأساتذة{" "}
            <mark className="rounded bg-teal/15 px-1 text-teal">XXXXXXX</mark> و
            <mark className="rounded bg-teal/15 px-1 text-teal">XXXXXXX</mark> و
            <mark className="rounded bg-teal/15 px-1 text-teal">XXXXXXX</mark>. المحامون بهيئة
            الدار البيضاء بواسطة الأستاذ{" "}
            <mark className="rounded bg-teal/15 px-1 text-teal">XXXXXXX</mark> المقبول للترافع
            أمام محكمة النقض.
          </p>
          <div className="font-ar mt-6 flex flex-wrap gap-2 text-xs">
            <span className="rounded-full bg-muted px-3 py-1">ابتدائي</span>
            <span className="rounded-full bg-muted px-3 py-1">استئناف</span>
            <span className="rounded-full bg-teal/12 px-3 py-1 text-teal">نقض</span>
          </div>
        </div>
      </div>
    </div>
  );
}
