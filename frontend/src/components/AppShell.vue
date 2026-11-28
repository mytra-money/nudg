<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'
import { useMediaQuery } from '@vueuse/core'
import {
  Avatar,
  Badge,
  BottomSheet,
  Button,
  call,
  DesktopShell,
  Dialog,
  KeyboardShortcutsDialog,
  MobileNav,
  MobileNavItem,
  MobileShell,
  PageHeader,
  Popover,
  Sidebar,
  SidebarHeader,
  SidebarItem,
  SidebarRail,
  SidebarRailItem,
  SidebarSection,
  TextInput,
  useKeyboardShortcut,
} from 'frappe-ui'
import type { DropdownOptions } from 'frappe-ui'
import AccountSelect from '@/components/AccountSelect.vue'
import DeskGate from '@/components/DeskGate.vue'
import EmbeddedSignup from '@/components/EmbeddedSignup.vue'
import ManualConnectDialog from '@/components/ManualConnectDialog.vue'
import NudgSettingsDialog, { type SettingsDialogTab } from '@/components/NudgSettingsDialog.vue'
import EmptyState from '@/components/EmptyState.vue'
import { isManager, useDesk } from '@/stores/desk'
import { shellNav } from '@/router'
import { canOpenContacts } from '@/utils/directoryAccess'
import { sessionUser as readSessionUser } from '@/utils/frappeSession'
import logoUrl from '@/assets/logo.svg'

const desk = useDesk()
const route = useRoute()
const router = useRouter()
const isDesktop = useMediaQuery('(min-width: 768px)')
if (typeof document !== 'undefined') {
  document.documentElement.removeAttribute('data-theme')
}
if (typeof localStorage !== 'undefined') {
  localStorage.removeItem('theme')
}

const sessionLive = Boolean(window.csrf_token)
const sessionUser = readSessionUser()
const sessionSite = window.sitename || ''

const visibleNav = computed(() =>
  shellNav.filter((link) => {
    if (link.managerOnly && !isManager.value) return false
    if (link.requiresDirectory && !canOpenContacts()) return false
    return true
  }),
)

const messagingNav = computed(() =>
  visibleNav.value.filter((link) => ['/', '/conversations', '/contacts'].includes(link.to)),
)
const studioNav = computed(() =>
  visibleNav.value.filter((link) =>
    ['/marketing', '/catalogs', '/template-studio'].includes(link.to),
  ),
)
const operationsNav = computed(() => {
  const base = visibleNav.value.filter((link) => ['/analytics', '/integrations', '/automation'].includes(link.to))
  if (isManager.value) {
    return [
      ...base,
      { to: '/external-sites', label: 'External Sites', icon: 'lucide-globe' },
      { to: '/integrations/logs', label: 'Logs', icon: 'lucide-scroll-text' },
    ]
  }
  return base
})

type NavDomain = 'messaging' | 'studio' | 'operations'

const domainForRoute = computed<NavDomain>(() => {
  const p = route.path
  if (['/marketing', '/catalogs', '/template-studio'].some((r) => p.startsWith(r))) {
    return 'studio'
  }
  if (['/analytics', '/integrations', '/external-sites', '/automation'].some((r) => p.startsWith(r))) {
    return 'operations'
  }
  return 'messaging'
})

const selectedDomain = ref<NavDomain>(domainForRoute.value)
watch(domainForRoute, (next) => {
  selectedDomain.value = next
})

const domainGroups = computed(() =>
  [
    {
      id: 'messaging' as const,
      label: 'Messaging',
      icon: 'lucide-message-square',
      items: messagingNav.value,
      badge: unreadConversationsCount.value || undefined,
    },
    {
      id: 'studio' as const,
      label: 'Growth & Studio',
      icon: 'lucide-sparkles',
      items: studioNav.value,
      badge: undefined,
    },
    {
      id: 'operations' as const,
      label: 'Operations',
      icon: 'lucide-bar-chart-2',
      items: operationsNav.value,
      badge: undefined,
    },
  ].filter((g) => g.items.length > 0),
)

const activeDomainGroup = computed(
  () => domainGroups.value.find((g) => g.id === selectedDomain.value) || domainGroups.value[0],
)

function selectDomain(group: (typeof domainGroups.value)[number]) {
  selectedDomain.value = group.id
  if (sidebarCollapsed.value) {
    sidebarCollapsed.value = false
  }
  const alreadyInGroup = group.items.some((item) => isActive(item.to))
  if (!alreadyInGroup && group.items[0]) {
    void router.push(group.items[0].to)
  }
}

const railAccounts = computed(() => desk.inbox.value?.accounts || [])

const unreadConversationsCount = computed(() => {
  const rows = desk.inbox.value?.conversations || []
  const selected = desk.account.value
  return rows.reduce((sum, row) => {
    if (selected && row.profile.whatsapp_account !== selected) return sum
    return Number(row.unread_count || 0) > 0 ? sum + 1 : sum
  }, 0)
})

const accounts = ref<Array<{ name: string; account_name: string }>>([])
const selectedAccountLabel = computed(() => {
  const selected = desk.account.value
  if (!selected || selected === 'all') return ''
  const fromInbox = desk.inbox.value?.accounts?.find((row) => row.name === selected)
  if (fromInbox) return fromInbox.account_name || fromInbox.name
  const fromList = accounts.value.find((row) => row.name === selected)
  return fromList?.account_name || fromList?.name || ''
})

const SIDEBAR_KEY = 'nudg.sidebar_collapsed_v2'
const sidebarCollapsed = ref(
  typeof localStorage !== 'undefined' ? localStorage.getItem(SIDEBAR_KEY) === '1' : false,
)
watch(sidebarCollapsed, (value) => {
  try {
    localStorage.setItem(SIDEBAR_KEY, value ? '1' : '0')
  } catch {
    /* ignore quota / private mode */
  }
})

async function loadAccounts() {
  if (!sessionLive) return
  try {
    const list = await call<Array<{ name: string; account_name: string }>>(
      'nudg.desk_api.list_user_accounts',
    )
    if (Array.isArray(list)) {
      accounts.value = list
    }
  } catch {
    /* fallback quietly if not logged in or endpoint unavailable */
  }
}

async function signOut() {
  await call('logout')
  window.location.href = '/login'
}

const title = computed(() => route.meta.title || 'Nudg')
const breadcrumb = computed(() => route.meta.parent || null)
const userLabel = sessionLive ? sessionUser || 'Signed in' : 'Local preview'

const userMenu = computed<DropdownOptions>(() =>
  sessionLive
    ? [
        {
          group: 'Session',
          hideLabel: true,
          options: [
            { label: sessionUser || 'Signed in', description: 'Session user', disabled: true },
            ...(desk.account.value && selectedAccountLabel.value
              ? [{ label: selectedAccountLabel.value, description: 'Account', disabled: true }]
              : []),
            ...(sessionSite ? [{ label: sessionSite, description: 'Site', disabled: true }] : []),
            {
              label: 'Sign out',
              onClick: () => {
                void signOut()
              },
            },
          ],
        },
      ]
    : [
        {
          group: 'Session',
          hideLabel: true,
          options: [
            {
              label: 'Not signed in',
              description: 'Open the desk on a Frappe site to use your session.',
              disabled: true,
            },
          ],
        },
      ],
)

function isActive(path: string) {
  if (path === '/') return route.path === '/'
  return route.path === path || route.path.startsWith(`${path}/`)
}

const showAccountModal = ref(false)
const showCredentialsModal = ref(false)
const settingsOpen = ref(false)
const settingsTab = ref<SettingsDialogTab>('profile')
const shortcutsOpen = ref(false)
const quickJumpOpen = ref(false)
const quickJumpQuery = ref('')
const moreOpen = ref(false)
const keyboardOpen = ref(false)

function openSettings(tab: SettingsDialogTab = 'profile') {
  settingsTab.value = tab
  settingsOpen.value = true
  moreOpen.value = false
}

const quickJumpResults = computed(() => {
  const q = quickJumpQuery.value.trim().toLowerCase()
  const navMatches = visibleNav.value
    .filter((item) => item.to !== '/settings')
    .filter((item) => !q || item.label.toLowerCase().includes(q))
    .map((item) => ({
      id: `nav:${item.to}`,
      label: item.label,
      subtitle: 'Page',
      icon: item.icon,
      onSelect: () => {
        quickJumpOpen.value = false
        void router.push(item.to)
      },
    }))

  const convMatches = (desk.inbox.value?.conversations || [])
    .filter((row) => {
      if (!q) return true
      const name = (row.profile.profile_name || '').toLowerCase()
      const phone = (row.profile.phone_number || '').toLowerCase()
      return name.includes(q) || phone.includes(q)
    })
    .slice(0, q ? 8 : 5)
    .map((row) => ({
      id: `chat:${row.profile.name}`,
      label: row.profile.profile_name || row.profile.phone_number,
      subtitle: q ? row.profile.phone_number : 'Recent chat',
      icon: 'lucide-message-square',
      onSelect: () => {
        quickJumpOpen.value = false
        void desk.openProfile(row.profile.name)
        void router.push('/conversations')
      },
    }))

  return [...convMatches, ...navMatches]
})

const workspaceMenu = computed<DropdownOptions>(() => {
  const accountOptions = railAccounts.value.map((acc) => ({
    label: acc.account_name || acc.name,
    description: acc.is_default ? 'Default number' : acc.status || 'Active',
    onClick: () => {
      void desk.setAccount(acc.name)
    },
  }))
  return accountOptions.length
    ? [{ group: 'WhatsApp Accounts', options: accountOptions }]
    : []
})

// Global keyboard shortcuts (automatically surfaced in KeyboardShortcutsDialog)
useKeyboardShortcut({
  combo: 'Mod+K',
  description: 'Quick jump to chat or page',
  group: 'General',
  handler: () => {
    quickJumpQuery.value = ''
    quickJumpOpen.value = !quickJumpOpen.value
  },
})

useKeyboardShortcut({
  combo: 'Shift+Slash',
  description: 'Show keyboard shortcuts',
  group: 'General',
  handler: () => {
    shortcutsOpen.value = !shortcutsOpen.value
  },
})

useKeyboardShortcut({
  combo: 'Mod+B',
  description: 'Toggle navigation sidebar',
  group: 'Navigation',
  handler: () => {
    sidebarCollapsed.value = !sidebarCollapsed.value
  },
})

useKeyboardShortcut({
  combo: 'Alt+Digit1',
  description: 'Go to Overview',
  group: 'Navigation',
  handler: () => {
    void router.push('/')
  },
})

useKeyboardShortcut({
  combo: 'Alt+Digit2',
  description: 'Go to Conversations',
  group: 'Navigation',
  handler: () => {
    void router.push('/conversations')
  },
})

function syncKeyboard() {
  const viewport = window.visualViewport
  keyboardOpen.value = Boolean(viewport && window.innerHeight - viewport.height > 120)
}

const mobilePrimaryTo = ['/', '/conversations', '/template-studio', '/analytics']
const mobileShort: Record<string, string> = {
  '/': 'Home',
  '/conversations': 'Inbox',
  '/template-studio': 'Templates',
  '/analytics': 'Insights',
}
const mobilePrimary = computed(() =>
  mobilePrimaryTo
    .map((to) => visibleNav.value.find((link) => link.to === to))
    .filter((link): link is (typeof visibleNav.value)[number] => Boolean(link)),
)
const mobileMore = computed(() =>
  visibleNav.value.filter((link) => !mobilePrimaryTo.includes(link.to) && link.to !== '/settings'),
)

watch(
  () => route.path,
  () => {
    moreOpen.value = false
  },
)

async function onEmbeddedConnected() {
  await loadAccounts()
  await desk.load()
}

async function onManualConnected() {
  showCredentialsModal.value = false
  showAccountModal.value = false
  await loadAccounts()
  await desk.load()
}

onMounted(() => {
  void loadAccounts()
  syncKeyboard()
  window.visualViewport?.addEventListener('resize', syncKeyboard)
})

onUnmounted(() => {
  window.visualViewport?.removeEventListener('resize', syncKeyboard)
})
</script>

<template>
  <div
    class="nudg-shell h-dvh w-screen max-w-full overflow-hidden bg-surface-base text-ink-gray-9"
    :class="keyboardOpen ? 'keyboard-open' : ''"
  >
    <!-- Desktop Shell: Fixed SidebarRail (Domain Icons + Search + Profile) + Collapsible Domain Sidebar -->
    <DesktopShell v-if="isDesktop" :scroll="false">
      <template #rail>
        <SidebarRail class="border-r border-outline-gray-2">
          <SidebarRailItem label="Nudg Home" route="/" :active="route.path === '/'">
            <img :src="logoUrl" alt="Nudg" class="size-5 rounded" />
          </SidebarRailItem>

          <SidebarRailItem
            variant="ghost"
            label="Search"
            description="⌘K"
            icon="lucide-search"
            :active="quickJumpOpen"
            @click="() => { quickJumpQuery = ''; quickJumpOpen = true }"
          />

          <div class="my-1.5 h-px w-5 bg-outline-gray-2" />

          <!-- Fixed Main Domain Icons (Messaging, Growth & Studio, Operations) -->
          <div class="flex flex-col items-center gap-1.5">
            <SidebarRailItem
              v-for="group in domainGroups"
              :key="group.id"
              variant="ghost"
              :label="group.label"
              :icon="group.icon"
              :active="selectedDomain === group.id"
              :badge="group.badge"
              badge-style="count"
              @click="selectDomain(group)"
            />
          </div>

          <!-- Bottom Profile Avatar Popover -->
          <div class="mt-auto flex flex-col items-center gap-1.5">
            <Popover side="right" align="end">
              <template #trigger="{ open: profileOpen }">
                <button type="button" class="rounded-md focus:outline-none">
                  <SidebarRailItem
                    variant="ghost"
                    :label="userLabel"
                    :active="profileOpen || settingsOpen"
                  >
                    <Avatar :label="userLabel" size="sm" />
                  </SidebarRailItem>
                </button>
              </template>
              <template #default="{ close }">
                <div class="w-60 overflow-hidden rounded-lg bg-surface-base text-sm">
                  <div class="flex items-center gap-3 border-b border-outline-gray-1 px-3 py-2.5">
                    <div class="relative shrink-0">
                      <Avatar :label="userLabel" size="md" />
                      <span
                        v-if="sessionLive"
                        class="absolute -bottom-0.5 -right-0.5 size-2.5 rounded-full bg-emerald-500 ring-2 ring-white"
                      />
                    </div>
                    <div class="min-w-0 flex-1">
                      <p class="truncate font-semibold text-ink-gray-9">{{ userLabel }}</p>
                      <p class="truncate text-xs text-ink-gray-5">{{ sessionSite || 'Nudg Workspace' }}</p>
                    </div>
                  </div>

                  <div class="border-b border-outline-gray-1 p-1">
                    <button
                      type="button"
                      class="flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-left text-ink-gray-8 hover:bg-surface-gray-2"
                      @click="() => { close(); openSettings('profile') }"
                    >
                      <span class="lucide-settings size-4 text-ink-gray-6" aria-hidden="true" />
                      <span>Settings</span>
                    </button>
                    <button
                      type="button"
                      class="flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-left text-ink-gray-8 hover:bg-surface-gray-2"
                      @click="() => { close(); shortcutsOpen = true }"
                    >
                      <span class="lucide-keyboard size-4 text-ink-gray-6" aria-hidden="true" />
                      <span>Keyboard shortcuts</span>
                    </button>
                    <button
                      v-if="isManager"
                      type="button"
                      class="flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-left text-ink-gray-8 hover:bg-surface-gray-2"
                      @click="() => { close(); showAccountModal = true }"
                    >
                      <span class="lucide-plus-circle size-4 text-ink-gray-6" aria-hidden="true" />
                      <span>Connect WhatsApp</span>
                    </button>
                  </div>

                  <div v-if="sessionLive" class="p-1">
                    <button
                      type="button"
                      class="flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-left font-medium text-red-600 hover:bg-red-50"
                      @click="() => { close(); void signOut() }"
                    >
                      <span class="lucide-log-out size-4" aria-hidden="true" />
                      <span>Log out</span>
                    </button>
                  </div>
                </div>
              </template>
            </Popover>
          </div>
        </SidebarRail>
      </template>

      <template #sidebar>
        <div class="relative flex h-full shrink-0">
          <Sidebar
            v-model:collapsed="sidebarCollapsed"
            aria-label="Nudg"
            width="13.5rem"
            collapsed-width="0px"
            :class="sidebarCollapsed ? 'border-r-0' : 'border-r border-outline-gray-2'"
          >
            <SidebarHeader
              :title="selectedAccountLabel || activeDomainGroup?.label || 'Nudg'"
              :subtitle="activeDomainGroup?.label"
              :menu-items="workspaceMenu"
            />

            <div class="min-h-0 flex-1 overflow-y-auto px-2 pt-1">
              <SidebarSection v-if="activeDomainGroup">
                <SidebarItem
                  v-for="link in activeDomainGroup.items"
                  :key="link.to"
                  :label="link.label"
                  :icon="link.icon"
                  :route="link.to"
                  :active="isActive(link.to)"
                >
                  <template v-if="link.to === '/conversations' && unreadConversationsCount > 0" #suffix>
                    <Badge theme="green" variant="subtle" size="sm" :label="unreadConversationsCount" />
                  </template>
                </SidebarItem>
              </SidebarSection>
            </div>
          </Sidebar>

          <button
            type="button"
            class="group/edge absolute inset-y-0 -right-1 z-20 flex w-2 items-center justify-center focus:outline-none"
            :class="sidebarCollapsed ? 'cursor-e-resize' : 'cursor-w-resize'"
            :aria-label="sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'"
            :title="sidebarCollapsed ? 'Expand sidebar (⌘B)' : 'Collapse sidebar (⌘B)'"
            @click="sidebarCollapsed = !sidebarCollapsed"
          >
            <span class="h-full w-0.5 bg-transparent transition-colors group-hover/edge:bg-outline-gray-3" />
            <span
              class="absolute bottom-10 grid size-6 place-items-center rounded-full border border-outline-gray-2 bg-surface-base text-ink-gray-6 opacity-0 shadow-sm transition-opacity group-hover/edge:opacity-100 group-focus-visible/edge:opacity-100 hover:text-ink-gray-9"
            >
              <span
                class="lucide-chevron-left size-3.5 transition-transform duration-200"
                :class="sidebarCollapsed ? 'rotate-180' : ''"
                aria-hidden="true"
              />
            </span>
          </button>
        </div>
      </template>

      <PageHeader>
        <div class="min-w-0 flex-1">
          <nav v-if="breadcrumb" aria-label="Breadcrumb" class="mb-0.5">
            <ol class="flex min-w-0 items-center gap-1 text-xs text-ink-gray-6">
              <li>
                <RouterLink
                  :to="breadcrumb.to"
                  class="rounded hover:text-ink-gray-9 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-green-3"
                >
                  {{ breadcrumb.label }}
                </RouterLink>
              </li>
              <li aria-hidden="true">/</li>
              <li class="truncate font-medium text-ink-gray-8" aria-current="page">{{ title }}</li>
            </ol>
          </nav>
          <h1 class="truncate text-base font-semibold text-ink-gray-9">{{ title }}</h1>
        </div>

        <div class="ml-auto flex shrink-0 items-center gap-2">
          <Badge
            v-if="selectedAccountLabel"
            theme="green"
            variant="subtle"
            size="md"
            :label="selectedAccountLabel"
          />
          <Popover align="end">
            <template #trigger>
              <Button variant="ghost" icon="lucide-bell" aria-label="Notifications" />
            </template>
            <div class="w-72">
              <p class="px-3 pt-3 text-sm font-medium text-ink-gray-8">Notifications</p>
              <EmptyState
                compact
                title="Notifications are not available yet"
                description="This desk does not have a notification feed."
              />
            </div>
          </Popover>
        </div>
      </PageHeader>

      <div
        v-if="route.meta.desk && desk.mode.value === 'sample'"
        class="flex shrink-0 flex-wrap items-center justify-between gap-2 border-b border-amber-200 bg-amber-50/80 px-4 py-1.5 text-xs text-amber-800"
      >
        <span><strong>Preview Mode</strong> · Sample data shown. Connect WhatsApp in Settings to go live.</span>
      </div>
      <div
        v-else-if="sessionLive && desk.inbox.value && (!desk.inbox.value.accounts || desk.inbox.value.accounts.length === 0)"
        class="flex shrink-0 flex-wrap items-center justify-between gap-2 border-b border-amber-300 bg-amber-50 px-4 py-2 text-xs text-amber-900"
      >
        <div class="flex items-center gap-2">
          <span class="lucide-alert-circle size-4 shrink-0 text-amber-600" />
          <span v-if="isManager"><strong>Action required:</strong> Connect a WhatsApp number to start messaging.</span>
          <span v-else><strong>Notice:</strong> No WhatsApp Account assigned to your profile yet. Please contact your WhatsApp Manager.</span>
        </div>
        <Button
          v-if="isManager"
          variant="solid"
          theme="green"
          size="sm"
          label="Connect WhatsApp Account"
          class="shrink-0 font-medium"
          @click="showAccountModal = true"
        />
      </div>

      <main class="min-h-0 min-w-0 flex-1 overflow-hidden">
        <RouterView v-slot="{ Component, route: viewRoute }">
          <DeskGate v-if="viewRoute.meta.desk">
            <component :is="Component" />
          </DeskGate>
          <component :is="Component" v-else />
        </RouterView>
      </main>
    </DesktopShell>

    <!-- Mobile Shell: separate MobileShell + MobileNav + BottomSheet -->
    <MobileShell v-else>
      <PageHeader>
        <div class="min-w-0 flex-1">
          <nav v-if="breadcrumb" aria-label="Breadcrumb" class="mb-0.5">
            <ol class="flex min-w-0 items-center gap-1 text-xs text-ink-gray-6">
              <li>
                <RouterLink :to="breadcrumb.to" class="rounded hover:text-ink-gray-9">
                  {{ breadcrumb.label }}
                </RouterLink>
              </li>
              <li aria-hidden="true">/</li>
              <li class="truncate font-medium text-ink-gray-8" aria-current="page">{{ title }}</li>
            </ol>
          </nav>
          <h1 class="truncate text-base font-semibold text-ink-gray-9">{{ title }}</h1>
        </div>

        <div class="ml-auto flex shrink-0 items-center gap-2">
          <div class="w-32 max-w-[42vw] min-w-0 overflow-hidden">
            <AccountSelect inline />
          </div>
          <Button
            variant="ghost"
            size="sm"
            icon="lucide-settings"
            class="shrink-0"
            aria-label="Open Settings"
            @click="openSettings('profile')"
          />
        </div>
      </PageHeader>

      <div class="flex h-full min-h-0 flex-col overflow-hidden">
        <div
          v-if="route.meta.desk && desk.mode.value === 'sample'"
          class="flex shrink-0 flex-wrap items-center justify-between gap-2 border-b border-amber-200 bg-amber-50/80 px-4 py-1.5 text-xs text-amber-800"
        >
          <span><strong>Preview Mode</strong> · Sample data shown.</span>
        </div>
        <div
          v-else-if="sessionLive && desk.inbox.value && (!desk.inbox.value.accounts || desk.inbox.value.accounts.length === 0)"
          class="flex shrink-0 flex-wrap items-center justify-between gap-2 border-b border-amber-300 bg-amber-50 px-4 py-2 text-xs text-amber-900"
        >
          <div class="flex items-center gap-2">
            <span class="lucide-alert-circle size-4 shrink-0 text-amber-600" />
            <span v-if="isManager"><strong>Action required:</strong> Connect a WhatsApp number.</span>
            <span v-else><strong>Notice:</strong> No WhatsApp Account assigned yet.</span>
          </div>
          <Button
            v-if="isManager"
            variant="solid"
            theme="green"
            size="sm"
            label="Connect"
            class="shrink-0 font-medium"
            @click="showAccountModal = true"
          />
        </div>

        <main class="min-h-0 min-w-0 flex-1 overflow-hidden">
          <RouterView v-slot="{ Component, route: viewRoute }">
            <DeskGate v-if="viewRoute.meta.desk">
              <component :is="Component" />
            </DeskGate>
            <component :is="Component" v-else />
          </RouterView>
        </main>
      </div>

      <template #nav>
        <MobileNav v-show="!keyboardOpen" class="nudg-mobile-nav">
          <MobileNavItem
            v-for="link in mobilePrimary"
            :key="link.to"
            :label="mobileShort[link.to] || link.label"
            :icon="link.icon"
            :route="link.to"
            :active="isActive(link.to)"
          />
          <MobileNavItem
            label="More"
            icon="lucide-ellipsis"
            :active="moreOpen || mobileMore.some((link) => isActive(link.to))"
            @click="moreOpen = true"
          />
        </MobileNav>
      </template>

      <BottomSheet v-model:open="moreOpen" title="More">
        <div class="divide-y divide-outline-gray-1 pb-[max(1rem,env(safe-area-inset-bottom))]">
          <RouterLink
            v-for="link in mobileMore"
            :key="link.to"
            :to="link.to"
            class="flex min-h-12 items-center gap-3 px-5 py-3 text-sm font-medium text-ink-gray-8 hover:bg-surface-gray-1"
            :class="isActive(link.to) ? 'bg-surface-gray-2 text-ink-gray-9' : ''"
            @click="moreOpen = false"
          >
            <span :class="[link.icon, 'size-4 shrink-0 text-ink-gray-6']" aria-hidden="true" />
            <span class="truncate">{{ link.label }}</span>
          </RouterLink>
          <button
            type="button"
            class="flex min-h-12 w-full items-center gap-3 px-5 py-3 text-left text-sm font-medium text-ink-gray-8 hover:bg-surface-gray-1"
            @click="openSettings('replies')"
          >
            <span class="lucide-settings size-4 shrink-0 text-ink-gray-6" aria-hidden="true" />
            <span>Settings</span>
          </button>
        </div>
      </BottomSheet>
    </MobileShell>

    <!-- Settings Dialog (Mod+Shift+,) -->
    <NudgSettingsDialog
      v-model:open="settingsOpen"
      v-model:tab="settingsTab"
      @connect-account="() => { settingsOpen = false; showAccountModal = true }"
    />

    <!-- Quick Jump / Search Dialog (Mod+K) -->
    <Dialog v-model="quickJumpOpen" title="Quick Jump" size="lg">
      <div class="space-y-3 py-1">
        <TextInput
          v-model="quickJumpQuery"
          placeholder="Search conversations by name/phone or jump to a page..."
          autofocus
        >
          <template #prefix>
            <span class="lucide-search size-3.5 text-ink-gray-4" />
          </template>
        </TextInput>
        <div class="max-h-72 divide-y divide-outline-gray-1 overflow-y-auto rounded-lg border border-outline-gray-2">
          <button
            v-for="item in quickJumpResults"
            :key="item.id"
            type="button"
            class="flex w-full items-center justify-between gap-3 px-3.5 py-2.5 text-left hover:bg-surface-gray-1"
            @click="item.onSelect()"
          >
            <span class="flex min-w-0 items-center gap-2.5">
              <span :class="[item.icon, 'size-4 shrink-0 text-ink-gray-5']" aria-hidden="true" />
              <span class="truncate text-sm font-medium text-ink-gray-9">{{ item.label }}</span>
            </span>
            <span class="shrink-0 text-xs text-ink-gray-5">{{ item.subtitle }}</span>
          </button>
          <p v-if="!quickJumpResults.length" class="p-4 text-center text-xs text-ink-gray-5">
            No matching chats or pages.
          </p>
        </div>
      </div>
    </Dialog>

    <!-- Keyboard Shortcuts Dialog (?) -->
    <KeyboardShortcutsDialog v-model:open="shortcutsOpen" />

    <!-- Global Account Onboarding Dialog -->
    <Dialog v-model="showAccountModal" title="Connect WhatsApp">
      <div class="py-1">
        <p class="text-sm text-ink-gray-7">Choose how to connect this number.</p>
        <div class="mt-4">
          <EmbeddedSignup @connected="onEmbeddedConnected" @manual="showCredentialsModal = true" />
        </div>
      </div>
      <template #actions>
        <div class="flex w-full justify-end">
          <Button variant="subtle" label="Close" @click="showAccountModal = false" />
        </div>
      </template>
    </Dialog>
    <ManualConnectDialog v-model="showCredentialsModal" @connected="onManualConnected" />
  </div>
</template>
