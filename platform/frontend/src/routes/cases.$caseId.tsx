import { createFileRoute, redirect } from "@tanstack/react-router";

// The ruling page does everything this one did -- and in both languages, with the
// headnote and reporting -- so an old link to a case lands there.
export const Route = createFileRoute("/cases/$caseId")({
  beforeLoad: ({ params }) => {
    throw redirect({ to: "/ruling/$docId", params: { docId: params.caseId } });
  },
  component: () => null,
});
