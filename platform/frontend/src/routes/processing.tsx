import { createFileRoute, redirect } from "@tanstack/react-router";

// Retired with the old job flow. See /admin for import + review.
export const Route = createFileRoute("/processing")({
  beforeLoad: () => {
    throw redirect({ to: "/dashboard" });
  },
  component: () => null,
});
