import { computed, type Ref } from 'vue'
import { accountArg as toAccountArg, chooseAccount, labelForAccount } from '@/utils/accountSelection'
import { useDesk } from '@/stores/desk'
import { isManager } from '@/stores/session'

/**
 * Shared WhatsApp-account gate for manager pages.
 * The only account switcher is the top-bar AccountSelect; pages read desk.account.
 */
export function useAccountGate(options?: {
  /** Local account ref to keep in sync with desk.account when possible. */
  account?: Ref<string>
}) {
  const desk = useDesk()

  const accounts = computed(() => desk.inbox.value?.accounts || [])
  const hasAccount = computed(() => accounts.value.length > 0)
  const selectedAccount = computed(() => toAccountArg(desk.account.value) || '')
  const selectedAccountLabel = computed(() => labelForAccount(accounts.value, selectedAccount.value))

  const accountGateDescription = computed(() =>
    isManager.value
      ? 'Connect a WhatsApp number before using this page.'
      : 'No WhatsApp account is assigned to you yet. Ask a WhatsApp manager to link one.',
  )

  /** Prefer desk.account when it is a real linked number; else default / first account. */
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
    selectedAccountLabel,
    accountGateDescription,
    pickAccount,
    syncAccount,
    isManager,
  }
}
