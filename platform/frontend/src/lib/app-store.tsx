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
} from "./api";

type Theme = "light" | "dark";

type Store = {
  theme: Theme;
  toggleTheme: () => void;
  // auth
  email: string;
  role: string;
  authed: boolean;
  isAdmin: boolean;
  login: (email: string, password: string) => Promise<string>; // resolves to role
  logout: () => void;
  // reference data
  categories: string[];
  refreshCategories: () => Promise<void>;
};

const Ctx = createContext<Store | null>(null);

export function AppStoreProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>("light");
  const [email, setEmail] = useState<string>(getEmail());
  const [role, setRole] = useState<string>(getRole());
  const [authed, setAuthed] = useState<boolean>(apiIsAuthed());
  const [categories, setCategories] = useState<string[]>([]);

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
    async (mail: string, password: string) => {
      const data = await apiLogin(mail, password);
      setEmail(data.email);
      setRole(data.role);
      setAuthed(true);
      return data.role;
    },
    [],
  );

  const logout = useCallback(() => {
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
      isAdmin: role === "admin",
      login,
      logout,
      categories,
      refreshCategories,
    }),
    [theme, toggleTheme, email, role, authed, login, logout, categories, refreshCategories],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useStore(): Store {
  const v = useContext(Ctx);
  if (!v) throw new Error("useStore must be used within StoreProvider");
  return v;
}
