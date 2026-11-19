"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { ApiError, isAbortError, setApiBusinessId, setUnauthorizedHandler } from "@/lib/api";
import { fetchSession, loginRequest, logoutRequest, registerRequest } from "@/lib/auth";
import type {
  Business,
  LoginPayload,
  RegisterPayload,
  SessionResponse,
  SessionUser,
} from "@/types/auth";

type AuthStatus = "loading" | "authenticated" | "unauthenticated" | "error";

interface AuthContextValue {
  status: AuthStatus;
  user: SessionUser | null;
  business: Business | null;
  /** Businesses the account can switch between. Empty or single = no switcher. */
  businesses: Business[];
  /** True when the last sign-out was caused by an expired session. */
  sessionExpired: boolean;
  /** True right after the person chose to sign out (so no "return to" path is kept). */
  signedOut: boolean;
  /** Set when the initial session check failed for a reason other than 401. */
  error: ApiError | null;
  /**
   * Changes whenever the active business changes. The dashboard layout uses
   * it as a React key so all business-specific UI state is discarded.
   */
  tenantKey: string;
  login: (payload: LoginPayload) => Promise<void>;
  register: (payload: RegisterPayload) => Promise<void>;
  logout: () => Promise<void>;
  retrySession: () => void;
  switchBusiness: (businessId: string) => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

interface SessionState {
  status: AuthStatus;
  user: SessionUser | null;
  business: Business | null;
  businesses: Business[];
  sessionExpired: boolean;
  signedOut: boolean;
  error: ApiError | null;
  tenantKey: string;
}

const INITIAL: SessionState = {
  status: "loading",
  user: null,
  business: null,
  businesses: [],
  sessionExpired: false,
  signedOut: false,
  error: null,
  tenantKey: "none",
};

function fromSession(session: SessionResponse): Pick<
  SessionState,
  "status" | "user" | "business" | "businesses" | "sessionExpired" | "signedOut" | "error" | "tenantKey"
> {
  return {
    status: "authenticated",
    user: session.user,
    business: session.business,
    businesses: session.businesses ?? [],
    sessionExpired: false,
    signedOut: false,
    error: null,
    tenantKey: session.business.id,
  };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<SessionState>(INITIAL);
  const [checkToken, setCheckToken] = useState(0);

  // Initial session check (and retry after a connection failure).
  useEffect(() => {
    const controller = new AbortController();

    fetchSession(controller.signal)
      .then((session) => {
        setApiBusinessId(null);
        setState(fromSession(session));
      })
      .catch((error: unknown) => {
        if (isAbortError(error)) return;
        if (error instanceof ApiError && error.kind === "unauthorized") {
          setState({ ...INITIAL, status: "unauthenticated", tenantKey: "none" });
          return;
        }
        const apiError =
          error instanceof ApiError
            ? error
            : new ApiError({ status: 0, kind: "unknown", message: "Something unexpected happened." });
        setState({ ...INITIAL, status: "error", error: apiError });
      });

    return () => controller.abort();
  }, [checkToken]);

  // Any 401 from a data request means the session ended.
  useEffect(() => {
    setUnauthorizedHandler(() => {
      setApiBusinessId(null);
      setState({ ...INITIAL, status: "unauthenticated", sessionExpired: true });
    });
    return () => setUnauthorizedHandler(null);
  }, []);

  const login = useCallback(async (payload: LoginPayload) => {
    const session = await loginRequest(payload);
    setApiBusinessId(null);
    setState(fromSession(session));
  }, []);

  const register = useCallback(async (payload: RegisterPayload) => {
    const session = await registerRequest(payload);
    setApiBusinessId(null);
    setState(fromSession(session));
  }, []);

  const logout = useCallback(async () => {
    try {
      await logoutRequest();
    } catch {
      // Even if the server can't be reached, drop the local session state.
    }
    setApiBusinessId(null);
    setState({ ...INITIAL, status: "unauthenticated", signedOut: true });
  }, []);

  const retrySession = useCallback(() => {
    setState(INITIAL);
    setCheckToken((n) => n + 1);
  }, []);

  const switchBusiness = useCallback(
    async (businessId: string) => {
      const previous = state.business?.id ?? null;
      if (businessId === previous) return;

      setApiBusinessId(businessId);
      try {
        // Re-read the session under the new business so role and name are
        // whatever the backend says they are, not whatever we guess.
        const session = await fetchSession();
        setState(fromSession(session));
      } catch (error) {
        setApiBusinessId(previous);
        throw error;
      }
    },
    [state.business?.id],
  );

  const value = useMemo<AuthContextValue>(
    () => ({
      status: state.status,
      user: state.user,
      business: state.business,
      businesses: state.businesses,
      sessionExpired: state.sessionExpired,
      signedOut: state.signedOut,
      error: state.error,
      tenantKey: state.tenantKey,
      login,
      register,
      logout,
      retrySession,
      switchBusiness,
    }),
    [state, login, register, logout, retrySession, switchBusiness],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside <AuthProvider>.");
  return context;
}
