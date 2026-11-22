import { api } from "@/lib/api";
import type {
  ForgotPasswordPayload,
  LoginPayload,
  RegisterPayload,
  SessionResponse,
} from "@/types/auth";

/**
 * Authentication endpoints. None of these exist in the backend yet; they are
 * the contract documented in documentation/frontend-api-contract.md. They are
 * isolated here so changing a route or payload touches only this file.
 */

export const AUTH_ENDPOINTS = {
  login: "/auth/login",
  register: "/auth/register",
  logout: "/auth/logout",
  session: "/auth/me",
  forgotPassword: "/auth/forgot-password",
  inviteInfo: "/auth/invite-info",
  acceptInvite: "/auth/accept-invite",
  resetPassword: "/auth/reset-password",
  verifyEmail: "/auth/verify-email",
  resendVerification: "/auth/resend-verification",
} as const;

export function loginRequest(payload: LoginPayload): Promise<SessionResponse> {
  return api.post<SessionResponse>(AUTH_ENDPOINTS.login, payload, {
    skipUnauthorizedHandler: true,
  });
}

export function registerRequest(payload: RegisterPayload): Promise<SessionResponse> {
  return api.post<SessionResponse>(AUTH_ENDPOINTS.register, payload, {
    skipUnauthorizedHandler: true,
  });
}

export function logoutRequest(): Promise<void> {
  return api.post<void>(AUTH_ENDPOINTS.logout, undefined, {
    skipUnauthorizedHandler: true,
  });
}

export function fetchSession(signal?: AbortSignal): Promise<SessionResponse> {
  return api.get<SessionResponse>(AUTH_ENDPOINTS.session, {
    signal,
    skipUnauthorizedHandler: true,
  });
}

export function forgotPasswordRequest(payload: ForgotPasswordPayload): Promise<void> {
  return api.post<void>(AUTH_ENDPOINTS.forgotPassword, payload, {
    skipUnauthorizedHandler: true,
  });
}

export interface InviteInfo {
  email: string;
  business_name: string;
  role_name: string;
  suggested_name: string | null;
}

export function inviteInfoRequest(token: string): Promise<InviteInfo> {
  return api.post<InviteInfo>(AUTH_ENDPOINTS.inviteInfo, { token }, { skipUnauthorizedHandler: true });
}

export function acceptInviteRequest(payload: { token: string; password: string; full_name?: string }): Promise<SessionResponse> {
  return api.post<SessionResponse>(AUTH_ENDPOINTS.acceptInvite, payload, { skipUnauthorizedHandler: true });
}

export function resetPasswordRequest(payload: { token: string; password: string }): Promise<void> {
  return api.post<void>(AUTH_ENDPOINTS.resetPassword, payload, { skipUnauthorizedHandler: true });
}

export function verifyEmailRequest(token: string): Promise<void> {
  return api.post<void>(AUTH_ENDPOINTS.verifyEmail, { token }, { skipUnauthorizedHandler: true });
}

export function resendVerificationRequest(): Promise<void> {
  return api.post<void>(AUTH_ENDPOINTS.resendVerification, {});
}
