import { computed, type ComputedRef, type Ref } from 'vue'
import { useDesk } from '@/stores/desk'
import { isManager } from '@/stores/session'

export type AccountOption = { label: string; value: string }

/**
 * Shared WhatsApp-account gate for manager pages.
 * Use `hasAccount` + DeskEmpty kind="account", and `accountOptions` for selects.
 */
export function useAccountGate(options?: {
  /** Include an "All accounts" option for filters. */
  includeAll?: boolean
  allLabel?: string
  /** Local account ref to keep in sync with desk.account when possible. */
  account?: Ref<string>
}) {
  const desk = useDesk()

  const accounts = computed(() => desk.inbox.value?.accounts || [])
  const hasAccount = computed(() => accounts.value.length > 0)

  const accountOptions: ComputedRef<AccountOption[]> = computed(() => {
    const rows = accounts.value.map((row: { name: string; account_name?: string }) => ({
      label: row.account_name || row.name,
      value: row.name,
    }))
    if (options?.includeAll) {
      return [{ label: options.allLabel || 'All accounts', value: 'all' }, ...rows]
    }
    return rows
  })

  const accountGateDescription = computed(() =>
    isManager.value
      ? 'Connect a WhatsApp number before using this page.'
      : 'No WhatsApp account is assigned to you yet. Ask a WhatsApp manager to link one.',
  )

  /** Prefer desk.account when it is a real linked number; else first account. */
  function pickAccount(): string {
    const names = accounts.value.map((row: { name: string }) => row.name)
    const selected = desk.account.value
    if (selected && selected !== 'all' && names.includes(selected)) return selected
    const current = options?.account?.value
    if (current && names.includes(current)) return current
    return names[0] || ''
  }

  function syncAccount() {
    if (!options?.account) return
    const next = pickAccount()
    if (options.account.value !== next) options.account.value = next
  }

  return {
    desk,
    accounts,
    hasAccount,
    accountOptions,
    accountGateDescription,
    pickAccount,
    syncAccount,
    isManager,
  }
}
