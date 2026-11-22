/**
 * Authentication and tenant types.
 *
 * The backend has no auth implementation yet, so these shapes are the
 * contract the frontend expects. See documentation/frontend-api-contract.md.
 */

export interface Business {
  id: string;
  name: string;
  slug: string;
}

export interface Role {
  id: string;
  name: string;
  /** e.g. "cases:write", or "*" for everything. Used only to hide actions; the backend enforces them. */
  permissions: string[];
}

export interface SessionUser {
  id: string;
  email: string;
  full_name: string;
  status: "active" | "invited" | "disabled";
  role: Role;
  email_verified?: boolean;
  /** True only when email sending is switched on and this address is not yet confirmed. */
  email_verification_required?: boolean;
}

/** Returned by login, register and GET /auth/me. */
export interface SessionResponse {
  user: SessionUser;
  /** The business the session is currently acting for. */
  business: Business;
  /** Present only when the account can access more than one business. */
  businesses?: Business[];
}

export interface LoginPayload {
  email: string;
  password: string;
}

export interface RegisterPayload {
  business_name: string;
  full_name: string;
  email: string;
  password: string;
}

export interface ForgotPasswordPayload {
  email: string;
}
