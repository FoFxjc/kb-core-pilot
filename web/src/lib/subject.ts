// The dev role picker's state: the subject every API call runs as (X-KB-Subject; docs/round-2-w3-access.md section
// 3). Kept in localStorage when it is available; without it the choice lasts for the page's lifetime only.
// The picker exists only when the server says so (GET /v1/admin/config role_picker: auth mode none, development).
// Behind the SSO gateway it is hidden and no subject is ever sent: the server rejects X-KB-Subject there.
import { useSyncExternalStore } from 'react';

export const SUBJECT_KEY = 'kb-core.subject';
/** The roles in config/access_roles.yaml; public is the server's default subject. */
export const ROLES = ['public', 'finance_analyst', 'finance_confidential', 'full_access'] as const;
export type Role = (typeof ROLES)[number];
export const DEFAULT_ROLE: Role = 'public';

const isRole = (v: unknown): v is Role => typeof v === 'string' && (ROLES as readonly string[]).includes(v);

function load(): Role {
  try {
    const v = window.localStorage.getItem(SUBJECT_KEY);
    return isRole(v) ? v : DEFAULT_ROLE;
  } catch {
    return DEFAULT_ROLE;
  }
}

let current: Role | null = null;
let pickerEnabled = false;
const listeners = new Set<() => void>();

export function getSubject(): Role {
  if (current === null) current = load();
  return current;
}

export function setSubject(role: Role): void {
  current = role;
  try {
    window.localStorage.setItem(SUBJECT_KEY, role);
  } catch {
    // no storage: keep the choice in memory
  }
  listeners.forEach((l) => l());
}

/** Forget the in-memory choice so the next read goes back to storage (tests). */
export function resetSubject(): void {
  current = null;
  pickerEnabled = false;
}

function subscribe(l: () => void): () => void {
  listeners.add(l);
  return () => listeners.delete(l);
}

export function useSubject(): Role {
  return useSyncExternalStore(subscribe, getSubject);
}

const pickerListeners = new Set<() => void>();

/** Turn the dev role picker on or off (from GET /v1/admin/config role_picker). Off by default (fail closed). */
export function setPickerEnabled(on: boolean): void {
  pickerEnabled = on;
  pickerListeners.forEach((l) => l());
  listeners.forEach((l) => l());
}

export function isPickerEnabled(): boolean {
  return pickerEnabled;
}

export function usePickerEnabled(): boolean {
  return useSyncExternalStore((l) => {
    pickerListeners.add(l);
    return () => pickerListeners.delete(l);
  }, isPickerEnabled);
}

/** The subject to send with a request: the picked role while the picker is on, otherwise none. */
export function sentSubject(): Role | null {
  return pickerEnabled ? getSubject() : null;
}
