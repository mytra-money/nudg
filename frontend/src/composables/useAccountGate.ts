import { computed, type ComputedRef, type Ref } from 'vue'
import { accountArg as toAccountArg, chooseAccount } from '@/utils/accountSelection'
import { useDesk } from '@/stores/desk'
import { isManager } from '@/stores/session'

export type AccountOption = { label: string; value: string }

/**
 * Shared WhatsApp-account gate for manager pages.
 * Desk always has a single selected number (navbar); pages should use that.
 */
export function useAccountGate(options?: {
  /** Local account ref to keep in sync with desk.account when possible. */
  account?: Ref<string>
}) {
  const desk = useDesk()

  const accounts = computed(() => desk.inbox.value?.accounts || [])
  const hasAccount = computed(() => accounts.value.length > 0)
  const selectedAccount = computed(() => toAccountArg(desk.account.value) || '')

  const accountOptions: ComputedRef<AccountOption[]> = computed(() =>
    accounts.value.map((row: { name: string; account_name?: string }) => ({
      label: row.account_name || row.name,
      value: row.name,
    })),
  )

  const accountGateDescription = computed(() =>
    isManager.value
      ? 'Connect a WhatsApp number before using this page.'
      : 'No WhatsApp account is assigned to you yet. Ask a WhatsApp manager to link one.',
  )

  /** Prefer desk.account when it is a real linked number; else first account. */
  function pickAccount(): string {
    return chooseAccount(accounts.value, desk.account.value || null)
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
    selectedAccount,
    accountOptions,
    accountGateDescription,
    pickAccount,
    syncAccount,
    isManager,
  }
}
