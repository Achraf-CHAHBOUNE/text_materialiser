import { useQuery } from "@tanstack/react-query";

import { getAccount } from "./api-biz";
import { useStore } from "./app-store";

/** Whether the signed-in person is a firm member whose plan includes the cabinet. */
export function usePractice(): boolean {
  const { authed, ready, isStaff } = useStore();
  const acc = useQuery({ queryKey: ["account"], queryFn: getAccount, enabled: ready && authed && !isStaff });
  return !isStaff && !!acc.data?.practice;
}
