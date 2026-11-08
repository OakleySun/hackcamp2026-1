// Accounts: sign-up/login against the FastAPI backend, session token kept in localStorage.
// Account state is browser-only; SSR always renders the signed-out view and hydrates from here.
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { API_URL, request } from "./api";
import type { Topic } from "./events";

export const GENDERS = [
  { key: "woman", label: "Woman" },
  { key: "man", label: "Man" },
  { key: "non-binary", label: "Non-binary" },
  { key: "self-describe", label: "Prefer to self-describe" },
  { key: "prefer-not", label: "Prefer not to say" },
] as const;
export type Gender = (typeof GENDERS)[number]["key"];
export const genderLabel = (g: string | null, detail?: string | null) =>
  g === "self-describe" && detail
    ? detail
    : (GENDERS.find((x) => x.key === g)?.label ?? "Not shared");

export type User = {
  user_id: string;
  email: string;
  created_at: string;
  onboarded: boolean;
  onboarded_at: string | null;
  birthday: string | null;
  major: string | null;
  gender: Gender | null;
  gender_detail: string | null;
  interests: Topic[];
  hobbies: string[];
};

export type Profile = Pick<
  User,
  "birthday" | "major" | "gender" | "gender_detail" | "interests" | "hobbies"
>;

const TOKEN_KEY = "quad:session";
const readToken = () => {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
};
const writeToken = (t: string | null) => {
  try {
    if (t) localStorage.setItem(TOKEN_KEY, t);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage blocked: the session lasts until the tab closes */
  }
};
const authed = (token: string | null, init: RequestInit = {}): RequestInit => ({
  ...init,
  headers: {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  },
});

type AuthState = {
  user: User | null;
  /** false until the stored session has been checked in the browser */
  ready: boolean;
  signup: (email: string, password: string) => Promise<User>;
  login: (email: string, password: string) => Promise<User>;
  /** Finish "Continue with Google": trade the one-time code from /auth/callback for a session. */
  redeemGoogle: (code: string) => Promise<User>;
  logout: () => Promise<void>;
  saveProfile: (p: Profile) => Promise<User>;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const t = readToken();
    if (!t) return setReady(true);
    request<User>("/api/me", authed(t))
      .then((u) => {
        setToken(t);
        setUser(u);
      })
      .catch(() => writeToken(null)) // expired or revoked
      .finally(() => setReady(true));
  }, []);

  const start = useCallback((out: { token: string; user: User }) => {
    writeToken(out.token);
    setToken(out.token);
    setUser(out.user);
    return out.user;
  }, []);

  const value = useMemo<AuthState>(
    () => ({
      user,
      ready,
      signup: async (email, password) =>
        start(
          await request(
            "/api/auth/signup",
            authed(null, { method: "POST", body: JSON.stringify({ email, password }) }),
          ),
        ),
      login: async (email, password) =>
        start(
          await request(
            "/api/auth/login",
            authed(null, { method: "POST", body: JSON.stringify({ email, password }) }),
          ),
        ),
      redeemGoogle: async (code) =>
        start(
          await request(
            "/api/auth/google/redeem",
            authed(null, { method: "POST", body: JSON.stringify({ code }) }),
          ),
        ),
      logout: async () => {
        await fetchLogout(token);
        writeToken(null);
        setToken(null);
        setUser(null);
      },
      saveProfile: async (p) => {
        const u = await request<User>(
          "/api/me/profile",
          authed(token, { method: "PUT", body: JSON.stringify(p) }),
        );
        setUser(u);
        return u;
      },
    }),
    [user, ready, token, start],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

/** Full-page navigation to the backend, which sends the browser on to Google's sign-in screen. */
export const googleSignInUrl = (next = "/") =>
  `${API_URL}/api/auth/google/start?next=${encodeURIComponent(next)}`;

/** Whether the backend has Google sign-in configured (the button is hidden otherwise). */
export const fetchAuthProviders = () => request<{ google: boolean }>("/api/auth/providers");

async function fetchLogout(token: string | null) {
  // 204 has no body, so this can't go through request(); a failed logout still clears the browser.
  if (!token) return;
  await fetch(`${API_URL}/api/auth/logout`, authed(token, { method: "POST" })).catch(
    () => undefined,
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
