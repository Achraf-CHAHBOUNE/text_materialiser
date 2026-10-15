import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  clearAuth,
  getCategories,
  getEmail,
  getRole,
  isAuthed as apiIsAuthed,
  login as apiLogin,
  logoutRemote,
} from "./api";

type Theme = "light" | "dark";

type Store = {
  theme: Theme;
  toggleTheme: () => void;
  // auth
  email: string;
  role: string;
  authed: boolean;
  /** false until the saved session has been read (nothing is known before that) */
  ready: boolean;
  /** the rulings' tools: import, correct, publish (admin and editor) */
  isAdmin: boolean;
  isSuper: boolean;          // admin
  isSales: boolean;          // admin or sales: the CRM
  isStaff: boolean;          // admin, editor or sales
  isClientAdmin: boolean;    // a customer's account holder
  login: (email: string, password: string, code?: string) => Promise<string>; // resolves to role
  logout: () => void;
  // reference data
  categories: string[];
  refreshCategories: () => Promise<void>;
};

const Ctx = createContext<Store | null>(null);

export function AppStoreProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>("light");
  // Empty to start, even in the browser: the server renders the page first and
  // cannot see the saved session, so reading it here made the two disagree and
  // React threw the whole page away and drew it again. It is read after mount.
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("");
  const [authed, setAuthed] = useState(false);
  const [ready, setReady] = useState(false);
  const [categories, setCategories] = useState<string[]>([]);

  useEffect(() => {
    setEmail(getEmail());
    setRole(getRole());
    setAuthed(apiIsAuthed());
    setReady(true);
  }, []);

  useEffect(() => {
    const stored = (typeof window !== "undefined" && localStorage.getItem("theme")) as Theme | null;
    if (stored) setTheme(stored);
  }, []);

  useEffect(() => {
    document.documentElement.dataset["theme"] = theme;
    if (typeof window !== "undefined") localStorage.setItem("theme", theme);
  }, [theme]);

  const toggleTheme = useCallback(() => setTheme((t) => (t === "light" ? "dark" : "light")), []);

  const refreshCategories = useCallback(async () => {
    try {
      setCategories(await getCategories());
    } catch {
      /* not authed yet */
    }
  }, []);

  const login = useCallback(
    async (mail: string, password: string, code = "") => {
      const data = await apiLogin(mail, password, code);
      setEmail(data.email);
      setRole(data.role);
      setAuthed(true);
      return data.role;
    },
    [],
  );

  // A session ended elsewhere (signed in on another device, suspended, password
  // reset) arrives as a 401: forget it here too.
  useEffect(() => {
    const ended = () => {
      setEmail("");
      setRole("");
      setAuthed(false);
    };
    window.addEventListener("session-ended", ended);
    return () => window.removeEventListener("session-ended", ended);
  }, []);

  const logout = useCallback(() => {
    void logoutRemote();
    clearAuth();
    setEmail("");
    setRole("");
    setAuthed(false);
  }, []);

  const value = useMemo<Store>(
    () => ({
      theme,
      toggleTheme,
      email,
      role,
      authed,
      ready,
      isAdmin: role === "admin" || role === "editor",
      isSuper: role === "admin",
      isSales: role === "admin" || role === "sales",
      isStaff: role === "admin" || role === "editor" || role === "sales",
      isClientAdmin: role === "client_admin",
      login,
      logout,
      categories,
      refreshCategories,
    }),
    [theme, toggleTheme, email, role, authed, ready, login, logout, categories, refreshCategories],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useStore(): Store {
  const v = useContext(Ctx);
  if (!v) throw new Error("useStore must be used within StoreProvider");
  return v;
}
