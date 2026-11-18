import { computed } from 'vue'
import { defineStore } from 'pinia'

export function isLiveSession() {
  return Boolean(typeof window !== 'undefined' && window.csrf_token)
}

export function computeIsManager() {
  if (typeof window === 'undefined') return true
  if (window.is_manager !== undefined) return Boolean(window.is_manager)
  if (Array.isArray(window.roles)) {
    return (
      window.roles.includes('WhatsApp Manager') ||
      window.roles.includes('System Manager') ||
      window.user === 'Administrator'
    )
  }
  if (!window.csrf_token) return true
  return false
}

/** Standalone computed for router guards and templates that import `isManager` directly. */
export const isManager = computed(() => computeIsManager())

/** Administrator or System Manager. Site-wide WA Settings is not a WhatsApp Manager setting. */
export function computeIsSiteAdmin() {
  if (typeof window === 'undefined') return false
  if (window.is_system_manager !== undefined) return Boolean(window.is_system_manager)
  if (Array.isArray(window.roles)) {
    return window.roles.includes('System Manager') || window.user === 'Administrator'
  }
  return window.user === 'Administrator'
}

export const isSiteAdmin = computed(() => computeIsSiteAdmin())

export const useSessionStore = defineStore('nudg-session', () => {
  const isLive = computed(() => isLiveSession())
  const manager = computed(() => computeIsManager())
  const user = computed(() => window.user || '')
  const site = computed(() => window.site_name || window.sitename || '')
  const roles = computed(() => (Array.isArray(window.roles) ? window.roles : []))

  return {
    isLive,
    isManager: manager,
    isSiteAdmin: computed(() => computeIsSiteAdmin()),
    user,
    site,
    roles,
  }
})
