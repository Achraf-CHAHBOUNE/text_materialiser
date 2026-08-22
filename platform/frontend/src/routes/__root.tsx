import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  Outlet,
  Link,
  createRootRouteWithContext,
  useRouter,
  HeadContent,
  Scripts,
} from "@tanstack/react-router";
import { useEffect, type ReactNode } from "react";

import appCss from "../styles.css?url";
import { reportLovableError } from "../lib/lovable-error-reporting";
import { AppStoreProvider } from "../lib/app-store";
import { Toaster } from "../components/ui/sonner";

function NotFoundComponent() {
  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-background px-4">
      <div className="grad-brand-soft pointer-events-none absolute inset-0" aria-hidden />
      <div className="relative max-w-md rounded-2xl border bg-card p-10 text-center shadow-lg">
        <span className="grad-brand mx-auto mb-6 grid size-12 place-items-center rounded-xl text-primary-foreground shadow-md">
          <svg viewBox="0 0 24 24" className="size-6" fill="none" aria-hidden>
            <path d="M12 2.6 4.8 5.4v6.2c0 4.6 3 8.1 7.2 9.8 4.2-1.7 7.2-5.2 7.2-9.8V5.4L12 2.6Z" stroke="currentColor" strokeWidth="1.4" opacity="0.5" />
            <path d="M9.1 16.1 12 8.4l2.9 7.7M10.3 13.6h3.4" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </span>
        <h1 className="text-display font-semibold tabular-nums text-foreground">404</h1>
        <h2 className="mt-4 text-xl font-semibold text-foreground">Page not found</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          The page you're looking for doesn't exist or has been moved.
        </p>
        <div className="mt-6">
          <Link
            to="/"
            className="inline-flex h-11 items-center justify-center rounded-xl bg-primary px-5 text-sm font-medium text-primary-foreground shadow-sm transition-colors duration-200 hover:bg-primary/90"
          >
            Go home
          </Link>
        </div>
      </div>
    </div>
  );
}

function ErrorComponent({ error, reset }: { error: Error; reset: () => void }) {
  console.error(error);
  const router = useRouter();
  useEffect(() => {
    reportLovableError(error, { boundary: "tanstack_root_error_component" });
  }, [error]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="max-w-md text-center">
        <h1 className="text-xl font-semibold tracking-tight text-foreground">
          This page didn't load
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Something went wrong on our end. You can try refreshing or head back home.
        </p>
        <div className="mt-6 flex flex-wrap justify-center gap-2">
          <button
            onClick={() => {
              router.invalidate();
              reset();
            }}
            className="inline-flex items-center justify-center rounded-xl bg-primary px-5 py-2.5 text-sm font-medium text-primary-foreground shadow-sm transition-colors duration-200 hover:bg-primary/90"
          >
            Try again
          </button>
          <a
            href="/"
            className="inline-flex items-center justify-center rounded-xl border border-input bg-background px-5 py-2.5 text-sm font-medium text-foreground transition-colors hover:bg-accent"
          >
            Go home
          </a>
        </div>
      </div>
    </div>
  );
}

export const Route = createRootRouteWithContext<{ queryClient: QueryClient }>()({
  head: () => ({
    meta: [
      { charSet: "utf-8" },
      { name: "viewport", content: "width=device-width, initial-scale=1" },
      { title: "Anonymize — PII redaction for Arabic court rulings" },
      {
        name: "description",
        content:
          "Sign in to Anonymize: automatic PII redaction for Arabic court rulings and case-trajectory linking across first instance, appeal and cassation.",
      },
      { name: "author", content: "Anonymize" },
      { property: "og:title", content: "Anonymize — PII redaction for Arabic court rulings" },
      {
        property: "og:description",
        content: "Sign in to Anonymize: automatic PII redaction for Arabic court rulings and case-trajectory linking across first instance, appeal and cassation.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
      { name: "twitter:title", content: "Anonymize — PII redaction for Arabic court rulings" },
      { name: "twitter:description", content: "Sign in to Anonymize: automatic PII redaction for Arabic court rulings and case-trajectory linking across first instance, appeal and cassation." },
      { property: "og:image", content: "https://pub-bb2e103a32db4e198524a2e9ed8f35b4.r2.dev/89766d91-7052-4e3a-a18c-b62e0b68f1e4/id-preview-c4bd9bf2--48a42f76-ecc5-4273-853c-f2b1401f025f.lovable.app-1785949009650.png" },
      { name: "twitter:image", content: "https://pub-bb2e103a32db4e198524a2e9ed8f35b4.r2.dev/89766d91-7052-4e3a-a18c-b62e0b68f1e4/id-preview-c4bd9bf2--48a42f76-ecc5-4273-853c-f2b1401f025f.lovable.app-1785949009650.png" },
    ],
    links: [
      { rel: "stylesheet", href: appCss },
      { rel: "preconnect", href: "https://fonts.googleapis.com" },
      { rel: "preconnect", href: "https://fonts.gstatic.com", crossOrigin: "anonymous" },
      {
        rel: "stylesheet",
        href: "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=IBM+Plex+Sans+Arabic:wght@400;500;600;700&display=swap",
      },
      { rel: "icon", type: "image/png", href: "/favicon.png" },
    ],
  }),
  shellComponent: RootShell,
  component: RootComponent,
  notFoundComponent: NotFoundComponent,
  errorComponent: ErrorComponent,
});

function RootShell({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <head>
        <HeadContent />
      </head>
      <body>
        {children}
        <Scripts />
      </body>
    </html>
  );
}

function RootComponent() {
  const { queryClient } = Route.useRouteContext();

  return (
    <QueryClientProvider client={queryClient}>
      <AppStoreProvider>
        {/* Required: nested routes render here. Removing <Outlet /> breaks all child routes. */}
        <Outlet />
        <Toaster position="top-center" richColors />
      </AppStoreProvider>
    </QueryClientProvider>
  );
}

