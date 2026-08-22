import { createFileRoute, redirect } from "@tanstack/react-router";

// Not part of the consultation platform.
export const Route = createFileRoute("/billing")({
  beforeLoad: () => {
    throw redirect({ to: "/dashboard" });
  },
  component: () => null,
});
