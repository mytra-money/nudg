import { ref } from 'vue'
import { call } from 'frappe-ui'
import { errorText } from '@/utils/format'
import type { IntegrationStatus } from '@/types'

export function isLiveDesk() {
  return Boolean(window.csrf_token)
}

export function normalizeIntegration(value: unknown): IntegrationStatus | null {
  if (!value || typeof value !== 'object') return null
  const row = value as Record<string, unknown>
  if (typeof row.whatsapp_installed !== 'boolean') return null
  if (typeof row.doctypes_ready !== 'boolean') return null
  if (!Array.isArray(row.missing_dependencies)) return null
  if (!row.missing_dependencies.every((item) => typeof item === 'string')) return null
  if (!(row.default_account === null || typeof row.default_account === 'string')) return null
  if (!(row.active_account_count === null || typeof row.active_account_count === 'number')) return null
  if (typeof row.detail !== 'string') return null
  return {
    whatsapp_installed: row.whatsapp_installed,
    doctypes_ready: row.doctypes_ready,
    missing_dependencies: row.missing_dependencies as string[],
    default_account: row.default_account,
    active_account_count: row.active_account_count,
    detail: row.detail,
  }
}

export function bootIntegration(): IntegrationStatus | null {
  if (!isLiveDesk()) return null
  return normalizeIntegration(window.integration)
}

export function useIntegrationStatus() {
  const live = ref(isLiveDesk())
  const status = ref<IntegrationStatus | null>(bootIntegration())
  const loading = ref(live.value)
  const error = ref<string | null>(null)
  const bootInstalled = ref<boolean | null>(
    live.value && typeof window.whatsapp_installed === 'boolean' ? window.whatsapp_installed : null,
  )

  async function load() {
    live.value = isLiveDesk()
    if (!live.value) {
      status.value = null
      error.value = null
      loading.value = false
      bootInstalled.value = null
      return
    }
    bootInstalled.value = typeof window.whatsapp_installed === 'boolean' ? window.whatsapp_installed : null
    if (!status.value) loading.value = true
    try {
      const next = normalizeIntegration(await call('nudg.api.get_integration_status'))
      if (!next) {
        status.value = null
        error.value = 'Integration status did not match the expected response.'
        return
      }
      status.value = next
      error.value = null
    } catch (caught) {
      status.value = null
      error.value = errorText(caught)
    } finally {
      loading.value = false
    }
  }

  return { live, status, loading, error, bootInstalled, load }
}
