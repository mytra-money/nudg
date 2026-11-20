import { computed } from 'vue'
import { defineStore } from 'pinia'
import { sessionRoles, sessionUser } from '@/utils/frappeSession'

export function isLiveSession() {
  return Boolean(typeof window !== 'undefined' && window.csrf_token)
}

export function computeIsManager() {
  if (typeof window === 'undefined') return true
  if (window.is_manager !== undefined) return Boolean(window.is_manager)
  const roles = sessionRoles()
  if (roles.length) {
    return (
      roles.includes('WhatsApp Manager') ||
      roles.includes('System Manager') ||
      sessionUser() === 'Administrator'
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
  const roles = sessionRoles()
  if (roles.length) {
    return roles.includes('System Manager') || sessionUser() === 'Administrator'
  }
  return sessionUser() === 'Administrator'
}

export const isSiteAdmin = computed(() => computeIsSiteAdmin())

export const useSessionStore = defineStore('nudg-session', () => {
  const isLive = computed(() => isLiveSession())
  const manager = computed(() => computeIsManager())
  const user = computed(() => sessionUser())
  const site = computed(() => window.site_name || window.sitename || '')
  const roles = computed(() => sessionRoles())

  return {
    isLive,
    isManager: manager,
    isSiteAdmin: computed(() => computeIsSiteAdmin()),
    user,
    site,
    roles,
  }
})
