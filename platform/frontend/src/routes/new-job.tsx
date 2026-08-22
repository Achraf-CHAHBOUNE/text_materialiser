import { createFileRoute, redirect } from "@tanstack/react-router";

// Retired: clients never upload here. Anonymization happens in the offline pipeline
// (Project 1); admins import its output via /admin.
export const Route = createFileRoute("/new-job")({
  beforeLoad: () => {
    throw redirect({ to: "/dashboard" });
  },
  component: () => null,
});
