import { useSyncExternalStore } from "react";

const JWT_KEY = "conduit_jwt";
const PARTNER_TOKEN_KEY = "conduit_partner_token";
const PARTNER_SLUG_KEY = "conduit_partner_slug";

type Listener = () => void;
const listeners = new Set<Listener>();

function emit() {
  listeners.forEach((l) => l());
}

function subscribe(l: Listener) {
  listeners.add(l);
  return () => {
    listeners.delete(l);
  };
}

export function getJwt(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(JWT_KEY);
}

export function setJwt(token: string) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(JWT_KEY, token);
  emit();
}

export function clearJwt() {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(JWT_KEY);
  window.localStorage.removeItem(PARTNER_TOKEN_KEY);
  window.localStorage.removeItem(PARTNER_SLUG_KEY);
  emit();
}

export function getPartnerToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(PARTNER_TOKEN_KEY);
}

export function setPartnerToken(token: string, slug: string) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(PARTNER_TOKEN_KEY, token);
  window.localStorage.setItem(PARTNER_SLUG_KEY, slug);
  emit();
}

export function getPartnerSlug(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(PARTNER_SLUG_KEY);
}

export function clearPartner() {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(PARTNER_TOKEN_KEY);
  window.localStorage.removeItem(PARTNER_SLUG_KEY);
  emit();
}

export function useAuth() {
  const jwt = useSyncExternalStore(
    subscribe,
    () => getJwt(),
    () => null,
  );
  return { jwt, isAuthenticated: !!jwt };
}

export function usePartner() {
  const token = useSyncExternalStore(subscribe, () => getPartnerToken(), () => null);
  const slug = useSyncExternalStore(subscribe, () => getPartnerSlug(), () => null);
  return { token, slug, isConfigured: !!(token && slug) };
}
