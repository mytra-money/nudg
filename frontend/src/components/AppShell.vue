<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'
import {
  Button,
  call,
  Dialog,
  Dropdown,
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
import { isManager, useDesk } from '@/desk'
import { shellNav } from '@/router'

const desk = useDesk()
const route = useRoute()
const sessionLive = Boolean(window.csrf_token)
const sessionUser = window.user || ''
const sessionSite = window.sitename || ''
const visibleNav = computed(() => shellNav.filter((link) => !link.managerOnly || isManager.value))
const accounts = ref<Array<{ name: string; account_name: string }>>([])
const activeAccount = computed(() => accounts.value[0]?.account_name || '')
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

const subtitle = computed(() => {
  if (desk.mode.value === 'sample') return 'Local preview'
  if (activeAccount.value) return activeAccount.value
  if (desk.inbox.value && !desk.inbox.value.connected) return 'Not connected'
  return desk.inbox.value?.site || sessionSite || 'Site'
})

const title = computed(() => route.meta.title || 'NUDG')
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
            ...(activeAccount.value ? [{ label: activeAccount.value, description: 'Account', disabled: true }] : []),
            ...(sessionSite ? [{ label: sessionSite, description: 'Site', disabled: true }] : []),
            {
              label: 'Sign out',
              onClick: () => {
                window.location.href = '/api/method/logout'
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

let timer = 0
onMounted(() => {
  void loadAccounts()
  timer = window.setInterval(() => {
    if (document.visibilityState === 'visible') void desk.refresh()
  }, 15000)
})
onUnmounted(() => window.clearInterval(timer))
</script>

<template>
  <div class="flex h-dvh w-screen flex-col overflow-hidden bg-surface-gray-1 text-ink-gray-9 md:flex-row">
    <nav
      class="flex shrink-0 gap-1 overflow-x-auto border-b border-outline-gray-2 bg-white px-2 py-2 md:hidden"
      aria-label="NUDG"
    >
      <RouterLink
        v-for="link in visibleNav"
        :key="link.to"
        :to="link.to"
        class="shrink-0 rounded-full px-3 py-1.5 text-sm font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#128C7E]"
        :class="isActive(link.to) ? 'bg-[#075E54] text-white' : 'text-ink-gray-7 hover:bg-surface-gray-2'"
        :aria-current="isActive(link.to) ? 'page' : undefined"
      >
        {{ link.label }}
      </RouterLink>
    </nav>
    <div class="border-b border-outline-gray-2 bg-white px-3 py-2 md:hidden">
      <AccountSelect />
    </div>

    <div class="relative z-20 hidden h-full shrink-0 md:flex">
      <Sidebar
        v-model:collapsed="sidebarCollapsed"
        aria-label="NUDG"
        width="14rem"
        collapsed-width="3rem"
      >
        <SidebarHeader title="NUDG" :subtitle="subtitle">
          <template #prefix>
            <span class="grid size-full place-items-center rounded bg-[#075E54] text-[10px] font-bold tracking-wide text-white shadow-sm">NUDG</span>
          </template>
        </SidebarHeader>
        <AccountSelect />
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
        <div class="min-w-0">
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
        <div class="ml-auto flex shrink-0 items-center gap-2">
          <div
            v-if="activeAccount"
            class="hidden sm:inline-flex items-center gap-1.5 rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-0.5 text-xs font-medium text-emerald-800"
          >
            <span class="lucide-building-2 size-3 text-emerald-600" aria-hidden="true" />
            <span class="truncate max-w-[10rem]">{{ activeAccount }}</span>
          </div>
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
          <Dropdown :options="userMenu">
            <button
              type="button"
              class="inline-flex h-7 max-w-[11rem] items-center gap-2 rounded-md px-2 text-sm font-medium text-ink-gray-8 hover:bg-surface-gray-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#128C7E] sm:max-w-xs"
            >
              <span class="lucide-user size-4 shrink-0" aria-hidden="true" />
              <span class="truncate">{{ userLabel }}</span>
            </button>
          </Dropdown>
        </div>
      </header>

      <div
        v-if="route.meta.desk && desk.mode.value === 'sample'"
        class="flex items-center justify-between border-b border-amber-200 bg-amber-50/80 px-4 py-1.5 text-xs text-amber-800"
      >
        <span><strong>Preview Mode</strong> · Sample data shown. Connect WhatsApp in Settings to go live.</span>
      </div>
      <div
        v-else-if="sessionLive && desk.inbox.value && (!desk.inbox.value.accounts || desk.inbox.value.accounts.length === 0)"
        class="border-b border-amber-300 bg-amber-50 px-4 py-2 flex items-center justify-between text-xs text-amber-900"
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
          <Button variant="subtle" label="Close" @click="showAccountModal = false" />
        </div>
      </template>
    </Dialog>
    <ManualConnectDialog v-model="showCredentialsModal" @connected="onManualConnected" />
  </div>
</template>
