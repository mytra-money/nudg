<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'
import {
  Button,
  call,
  Dialog,
  Popover,
  Sidebar,
  SidebarCollapseToggle,
  SidebarHeader,
  SidebarItem,
  SidebarSection,
} from 'frappe-ui'
import type { DropdownOptions } from 'frappe-ui'
import AccountSelect from '@/components/AccountSelect.vue'
import DeskGate from '@/components/DeskGate.vue'
import EmbeddedSignup from '@/components/EmbeddedSignup.vue'
import ManualConnectDialog from '@/components/ManualConnectDialog.vue'
import EmptyState from '@/components/EmptyState.vue'
import { isManager, useDesk } from '@/stores/desk'
import { shellNav } from '@/router'
import { sessionUser as readSessionUser } from '@/utils/frappeSession'
import logoUrl from '@/assets/logo.svg'

const desk = useDesk()
const route = useRoute()
const sessionLive = Boolean(window.csrf_token)
const sessionUser = readSessionUser()
const sessionSite = window.sitename || ''
const visibleNav = computed(() => shellNav.filter((link) => !link.managerOnly || isManager.value))
const accounts = ref<Array<{ name: string; account_name: string }>>([])
const selectedAccountLabel = computed(() => {
  const selected = desk.account.value
  if (!selected || selected === 'all') return ''
  const fromInbox = desk.inbox.value?.accounts?.find((row) => row.name === selected)
  if (fromInbox) return fromInbox.account_name || fromInbox.name
  const fromList = accounts.value.find((row) => row.name === selected)
  return fromList?.account_name || fromList?.name || ''
})
const SIDEBAR_KEY = 'nudg.sidebar_collapsed'
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
const moreOpen = ref(false)
const keyboardOpen = ref(false)

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
const mobileMore = computed(() => visibleNav.value.filter((link) => !mobilePrimaryTo.includes(link.to)))

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
    class="nudg-shell flex h-dvh w-screen max-w-full flex-col overflow-hidden bg-white text-ink-gray-9 md:flex-row"
    :class="keyboardOpen ? 'keyboard-open' : ''"
  >
    <div class="relative z-20 hidden h-full shrink-0 md:flex">
      <Sidebar
        v-model:collapsed="sidebarCollapsed"
        aria-label="Nudg"
        width="14rem"
        collapsed-width="3rem"
      >
        <!-- Left: profile (LYQD / LMS SidebarHeader pattern) -->
        <SidebarHeader title="Nudg" :subtitle="userLabel" :menu-items="userMenu" :logo="logoUrl" />
        <div class="min-h-0 flex-1 overflow-y-auto px-2">
          <SidebarSection>
            <SidebarItem
              v-for="link in visibleNav"
              :key="link.to"
              :label="link.label"
              :icon="link.icon"
              :route="link.to"
              :active="isActive(link.to)"
            />
          </SidebarSection>
        </div>
        <div class="px-2">
          <SidebarCollapseToggle />
        </div>
      </Sidebar>
      <!-- Same control as the Frappe desk sidebar: the border is the hit
           target, and the chevron shows while the pointer is on it. -->
      <div
        class="group/edge absolute inset-y-0 -right-1 z-30 w-2"
        :class="sidebarCollapsed ? 'cursor-e-resize' : 'cursor-w-resize'"
        @click="sidebarCollapsed = !sidebarCollapsed"
      >
        <span
          class="pointer-events-none absolute inset-y-0 left-1/2 w-0.5 -translate-x-1/2 bg-transparent transition-colors duration-150 group-hover/edge:bg-outline-gray-3"
        />
        <button
          type="button"
          class="pointer-events-none absolute bottom-4 left-1/2 flex size-6 -translate-x-1/2 items-center justify-center rounded-full border border-outline-gray-2 bg-white text-ink-gray-6 opacity-0 shadow-sm transition duration-150 hover:bg-surface-gray-2 hover:text-ink-gray-8 focus-visible:pointer-events-auto focus-visible:opacity-100 group-hover/edge:pointer-events-auto group-hover/edge:opacity-100"
          :aria-label="sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'"
          :title="sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'"
          @click.stop="sidebarCollapsed = !sidebarCollapsed"
        >
          <span
            class="lucide-chevron-left size-3 transition-transform duration-300 ease-in-out"
            :class="{ 'rotate-180': sidebarCollapsed }"
            aria-hidden="true"
          />
        </button>
      </div>
    </div>

    <div class="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
      <header class="flex min-h-12 items-center gap-3 border-b border-outline-gray-2 bg-white px-3 sm:px-4">
        <!-- Left: page title (shell owns headings — pages must not repeat them) -->
        <div class="min-w-0 flex-1">
          <nav v-if="breadcrumb" aria-label="Breadcrumb" class="mb-0.5">
            <ol class="flex min-w-0 items-center gap-1 text-xs text-ink-gray-6">
              <li>
                <RouterLink
                  :to="breadcrumb.to"
                  class="rounded hover:text-ink-gray-9 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#128C7E]"
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

        <!-- Right: WhatsApp number select (profile lives in the left sidebar) -->
        <div class="ml-auto flex shrink-0 items-center gap-1.5 sm:gap-2">
          <Popover align="end">
            <template #trigger>
              <Button variant="ghost" icon="lucide-bell" label="Notifications" />
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
          <div class="w-36 min-w-0 sm:w-48">
            <AccountSelect inline />
          </div>
        </div>
      </header>

      <div
        v-if="route.meta.desk && desk.mode.value === 'sample'"
        class="flex flex-wrap items-center justify-between gap-2 border-b border-amber-200 bg-amber-50/80 px-4 py-1.5 text-xs text-amber-800"
      >
        <span><strong>Preview Mode</strong> · Sample data shown. Connect WhatsApp in Settings to go live.</span>
      </div>
      <div
        v-else-if="sessionLive && desk.inbox.value && (!desk.inbox.value.accounts || desk.inbox.value.accounts.length === 0)"
        class="flex flex-wrap items-center justify-between gap-2 border-b border-amber-300 bg-amber-50 px-4 py-2 text-xs text-amber-900"
      >
        <div class="flex items-center gap-2">
          <span class="lucide-alert-circle size-4 text-amber-600 shrink-0" />
          <span v-if="isManager"><strong>Action required:</strong> Connect a WhatsApp number to start messaging.</span>
          <span v-else><strong>Notice:</strong> No WhatsApp Account assigned to your profile yet. Please contact your WhatsApp Manager.</span>
        </div>
        <Button
          v-if="isManager"
          size="sm"
          class="bg-[#075E54] text-white hover:bg-[#128C7E] shrink-0 font-medium"
          label="Connect WhatsApp Account"
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

      <div class="nudg-mobile-nav relative z-30 shrink-0 md:hidden">
        <button
          v-if="moreOpen"
          type="button"
          class="fixed inset-0 z-20 bg-black/30"
          aria-label="Close menu"
          @click="moreOpen = false"
        />
        <div
          v-if="moreOpen"
          class="absolute bottom-full left-0 right-0 z-30 max-h-[50dvh] overflow-y-auto border-t border-outline-gray-2 bg-white shadow-lg"
        >
          <RouterLink
            v-for="link in mobileMore"
            :key="link.to"
            :to="link.to"
            class="flex min-h-11 items-center gap-3 border-b border-outline-gray-1 px-4 py-3 text-sm font-medium text-ink-gray-8"
            :class="isActive(link.to) ? 'bg-surface-gray-2 text-ink-gray-9' : ''"
            :aria-current="isActive(link.to) ? 'page' : undefined"
          >
            <span :class="[link.icon, 'size-4 shrink-0 text-ink-gray-6']" aria-hidden="true" />
            <span class="truncate">{{ link.label }}</span>
          </RouterLink>
        </div>
        <nav
          class="grid grid-cols-5 border-t border-outline-gray-2 bg-white pb-[env(safe-area-inset-bottom)]"
          aria-label="Nudg"
        >
          <RouterLink
            v-for="link in mobilePrimary"
            :key="link.to"
            :to="link.to"
            class="flex min-h-14 min-w-0 flex-col items-center justify-center gap-0.5 px-1 py-1.5 text-[10px] font-medium leading-none"
            :class="isActive(link.to) ? 'text-[#075E54]' : 'text-ink-gray-6'"
            :aria-current="isActive(link.to) ? 'page' : undefined"
          >
            <span :class="[link.icon, 'size-5 shrink-0']" aria-hidden="true" />
            <span class="w-full truncate text-center">{{ mobileShort[link.to] || link.label }}</span>
          </RouterLink>
          <button
            type="button"
            class="flex min-h-14 min-w-0 flex-col items-center justify-center gap-0.5 px-1 py-1.5 text-[10px] font-medium leading-none"
            :class="moreOpen || mobileMore.some((link) => isActive(link.to)) ? 'text-[#075E54]' : 'text-ink-gray-6'"
            :aria-expanded="moreOpen"
            @click="moreOpen = !moreOpen"
          >
            <span class="lucide-ellipsis size-5 shrink-0" aria-hidden="true" />
            <span class="w-full truncate text-center">More</span>
          </button>
        </nav>
      </div>
    </div>

    <!-- Global Account Onboarding Dialog (No Desk Routing Required) -->
    <Dialog v-model="showAccountModal" title="Connect WhatsApp">
      <div class="py-1">
        <p class="text-sm text-ink-gray-7">Choose how to connect this number.</p>
        <div class="mt-4">
          <EmbeddedSignup @connected="onEmbeddedConnected" @manual="showCredentialsModal = true" />
        </div>
      </div>
      <template #actions>
        <div class="flex w-full justify-end">
          <Button variant="solid" class="!bg-[#e5e7eb] !text-[#111827] hover:!bg-[#d1d5db]" label="Close" @click="showAccountModal = false" />
        </div>
      </template>
    </Dialog>
    <ManualConnectDialog v-model="showCredentialsModal" @connected="onManualConnected" />
  </div>
</template>
