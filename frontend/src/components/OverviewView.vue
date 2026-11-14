<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { Avatar, Badge, Button } from 'frappe-ui'
import EmptyState from '@/components/EmptyState.vue'
import ErrorState from '@/components/ErrorState.vue'
import LoadingState from '@/components/LoadingState.vue'
import { isManager, useDesk } from '@/desk'
import { formatRemaining, formatTime, initials, previewText } from '@/format'
import { useIntegrationStatus } from '@/integration'
import { router } from '@/router'

const { live, status, loading, error, bootInstalled, load } = useIntegrationStatus()
const desk = useDesk()

onMounted(() => {
  void load()
  if (!desk.inbox.value) void desk.load()
  else void desk.refresh()
})

function accountCount(value: number | null) {
  return value === null ? 'Not reported' : String(value)
}

function channelPath() {
  return isManager.value ? '/integrations' : '/settings'
}

function navigateTo(path: string) {
  try {
    if (router && typeof router.push === 'function') {
      void router.push(path)
      return
    }
  } catch {
    /* headless/mock fallback */
  }
  if (typeof window !== 'undefined' && window.location) {
    window.location.href = path
  }
}

function handleOpenProfile(name: string) {
  void desk.openProfile(name)
  navigateTo('/conversations')
}

const selectedAccount = computed(() => desk.account.value)
const conversations = computed(() => {
  const rows = desk.inbox.value?.conversations ?? []
  if (!selectedAccount.value || selectedAccount.value === 'all') return rows
  return rows.filter((item) => item.profile.whatsapp_account === selectedAccount.value)
})
const accounts = computed(() => desk.inbox.value?.accounts ?? [])
const templates = computed(() => {
  const rows = desk.inbox.value?.templates ?? []
  if (!selectedAccount.value || selectedAccount.value === 'all') return rows
  return rows.filter((item) => !item.whatsapp_account || item.whatsapp_account === selectedAccount.value)
})
const logs = computed(() => desk.logs.value ?? [])

const needsReplyList = computed(() =>
  conversations.value.filter((item) => item.needs_reply || item.conversation_status === 'needs_reply'),
)
const needsReplyCount = computed(() => needsReplyList.value.length)

const openWindowsList = computed(() =>
  conversations.value.filter((item) => item.window?.status === 'open'),
)
const openWindowsCount = computed(() => openWindowsList.value.length)

const approvedTemplatesCount = computed(() =>
  templates.value.filter((item) => item.status === 'Approved').length,
)

const activeAccounts = computed(() => accounts.value.filter((item) => item.status === 'Active'))
const activeAccountsCount = computed(() => activeAccounts.value.length)

const selectedAccountRow = computed(() =>
  accounts.value.find((item) => item.name === selectedAccount.value) || null,
)
const defaultAccountRow = computed(
  () => accounts.value.find((item) => item.is_default) || activeAccounts.value[0] || accounts.value[0] || null,
)
const shownAccountName = computed(() => {
  const row = selectedAccountRow.value || defaultAccountRow.value
  return row?.account_name || row?.name || 'No account'
})
const defaultAccountName = computed(
  () => defaultAccountRow.value?.account_name || defaultAccountRow.value?.name || 'No account',
)
const channelConnected = computed(() => activeAccountsCount.value > 0)

const priorityQueue = computed(() => {
  if (needsReplyList.value.length > 0) {
    return needsReplyList.value.slice(0, 4)
  }
  return conversations.value.slice(0, 4)
})

const recentLogs = computed(() => logs.value.slice(0, 4))
</script>

<template>
  <div class="h-full overflow-y-auto bg-surface-gray-1">
    <div class="mx-auto flex min-h-full w-full max-w-7xl flex-col px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
      <!-- Top Header / Brand Hero -->
      <header class="flex flex-col gap-4 border-b border-outline-gray-2 pb-6 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div class="flex items-center gap-2">
            <span class="rounded bg-[#075E54]/10 px-2 py-0.5 text-[11px] font-bold tracking-wider uppercase text-[#075E54]">
              Meta Cloud API
            </span>
            <span class="text-xs text-ink-gray-5">·</span>
            <span class="text-xs font-medium text-ink-gray-6">Omnichannel NUDG</span>
          </div>
          <h1 class="mt-1.5 text-2xl font-bold tracking-tight text-ink-gray-9 sm:text-3xl">
            NUDG Overview
          </h1>
          <p class="mt-1 text-sm text-ink-gray-6">
            Real-time customer conversation SLAs, 24-hour service windows, and WhatsApp Business infrastructure.
          </p>
        </div>

        <div class="flex flex-wrap items-center gap-2.5">
          <!-- Live / Demo Indicator -->
          <div
            class="inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium shadow-xs"
            :class="
              error
                ? 'border-red-200 bg-red-50 text-red-700'
                : status?.whatsapp_installed
                  ? 'border-emerald-200 bg-emerald-50 text-emerald-800'
                  : !live
                    ? 'border-teal-200 bg-teal-50 text-[#075E54]'
                    : 'border-amber-200 bg-amber-50 text-amber-800'
            "
          >
            <span
              class="size-2 rounded-full"
              :class="
                error
                  ? 'bg-red-500'
                  : status?.whatsapp_installed
                    ? 'animate-pulse bg-emerald-500'
                    : !live
                      ? 'bg-[#128C7E]'
                      : 'bg-amber-500'
              "
            />
            <span>
              {{
                error
                  ? 'Connection Issue'
                  : status?.whatsapp_installed
                    ? 'Cloud API Active'
                    : !live
                      ? 'Demo Preview Mode'
                      : 'Setup Required'
              }}
            </span>
          </div>

          <Button
            v-if="live"
            variant="subtle"
            size="sm"
            :loading="loading"
            icon-left="lucide-refresh-cw"
            label="Refresh"
            @click="load"
          />

          <Button
            variant="solid"
            size="sm"
            class="bg-[#075E54] text-white hover:bg-[#128C7E]"
            icon-left="lucide-inbox"
            label="Open Inbox"
            @click="navigateTo('/conversations')"
          />
        </div>
      </header>

      <!-- Error State (when status load fails in live mode) -->
      <div v-if="error" class="mt-8">
        <ErrorState
          title="Could not load integration status"
          :message="error"
          allow-retry
          @retry="load"
        />
      </div>

      <!-- Main Dashboard Content (when no fatal error) -->
      <div v-else class="mt-6 flex flex-1 flex-col gap-6">
        <!-- Interactive Preview Mode Callout Banner -->
        <div
          v-if="!live"
          class="flex flex-col gap-3 rounded-xl border border-teal-200/80 bg-teal-50/60 p-4 text-xs text-[#075E54] sm:flex-row sm:items-center sm:justify-between"
        >
          <div class="flex items-center gap-3">
            <div class="grid size-8 shrink-0 place-items-center rounded-lg bg-[#075E54] text-white shadow-xs">
              <span class="lucide-sparkles size-4" aria-hidden="true" />
            </div>
            <div>
              <p class="font-semibold text-ink-gray-9">Demo Environment Active</p>
              <p class="text-ink-gray-6">
                You are currently previewing NUDG with simulated WhatsApp data. Conversations, templates, and logs can be tested interactively.
              </p>
            </div>
          </div>
          <a
            href="/conversations"
            class="inline-flex shrink-0 items-center gap-1.5 font-semibold text-[#075E54] hover:underline"
            @click.prevent="navigateTo('/conversations')"
          >
            Explore Inbox threads <span class="lucide-arrow-right size-3.5" aria-hidden="true" />
          </a>
        </div>

        <!-- Metric KPI Cards -->
        <section aria-labelledby="kpi-heading">
          <h2 id="kpi-heading" class="sr-only">Key Performance Indicators</h2>
          <div class="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <!-- Card 1: Needs Reply -->
            <a
              href="/conversations?tab=needs_reply"
              class="group relative flex flex-col justify-between rounded-xl border border-outline-gray-2 bg-white p-4.5 shadow-xs transition-all hover:border-[#128C7E] hover:shadow-sm"
              @click.prevent="navigateTo('/conversations?tab=needs_reply')"
            >
              <div class="flex items-center justify-between">
                <span class="text-xs font-medium uppercase tracking-wider text-ink-gray-6">Needs Reply</span>
                <span
                  class="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium"
                  :class="needsReplyCount > 0 ? 'bg-red-100 text-red-700' : 'bg-emerald-100 text-emerald-700'"
                >
                  {{ needsReplyCount > 0 ? `${needsReplyCount} urgent` : 'All caught up' }}
                </span>
              </div>
              <div class="mt-3 flex items-baseline gap-2">
                <span class="text-3xl font-extrabold tracking-tight text-ink-gray-9">
                  {{ needsReplyCount }}
                </span>
                <span class="text-xs text-ink-gray-5">pending response</span>
              </div>
              <p class="mt-2 text-[11px] text-ink-gray-5 group-hover:text-[#075E54]">
                Customer messages waiting for agent reply &rarr;
              </p>
            </a>

            <!-- Card 2: 24h Windows Active -->
            <a
              href="/conversations?tab=window_open"
              class="group relative flex flex-col justify-between rounded-xl border border-outline-gray-2 bg-white p-4.5 shadow-xs transition-all hover:border-[#128C7E] hover:shadow-sm"
              @click.prevent="navigateTo('/conversations?tab=window_open')"
            >
              <div class="flex items-center justify-between">
                <span class="text-xs font-medium uppercase tracking-wider text-ink-gray-6">Open 24h Windows</span>
                <span class="inline-flex items-center rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-700">
                  {{ openWindowsCount > 0 ? 'Free-form' : 'Template only' }}
                </span>
              </div>
              <div class="mt-3 flex items-baseline gap-2">
                <span class="text-3xl font-extrabold tracking-tight text-ink-gray-9">
                  {{ openWindowsCount }}
                </span>
                <span class="text-xs text-ink-gray-5">active sessions</span>
              </div>
              <p class="mt-2 text-[11px] text-ink-gray-5 group-hover:text-[#075E54]">
                Sessions eligible for free-form replies &rarr;
              </p>
            </a>

            <!-- Card 3: Approved Templates -->
            <a
              href="/template-studio"
              class="group relative flex flex-col justify-between rounded-xl border border-outline-gray-2 bg-white p-4.5 shadow-xs transition-all hover:border-[#128C7E] hover:shadow-sm"
              @click.prevent="navigateTo('/template-studio')"
            >
              <div class="flex items-center justify-between">
                <span class="text-xs font-medium uppercase tracking-wider text-ink-gray-6">Templates</span>
                <span class="inline-flex items-center rounded-full bg-sky-100 px-2 py-0.5 text-xs font-medium text-sky-700">
                  {{ approvedTemplatesCount }} approved
                </span>
              </div>
              <div class="mt-3 flex items-baseline gap-2">
                <span class="text-3xl font-extrabold tracking-tight text-ink-gray-9">
                  {{ approvedTemplatesCount }}
                </span>
                <span class="text-xs text-ink-gray-5">/ {{ templates.length }} total</span>
              </div>
              <p class="mt-2 text-[11px] text-ink-gray-5 group-hover:text-[#075E54]">
                Meta-approved templates ready to broadcast &rarr;
              </p>
            </a>

            <!-- Card 4: Active Accounts -->
            <a
              :href="channelPath()"
              class="group relative flex flex-col justify-between rounded-xl border border-outline-gray-2 bg-white p-4.5 shadow-xs transition-all hover:border-[#128C7E] hover:shadow-sm"
              @click.prevent="navigateTo(channelPath())"
            >
              <div class="flex items-center justify-between">
                <span class="text-xs font-medium uppercase tracking-wider text-ink-gray-6">WABA Channels</span>
                <span
                  class="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium"
                  :class="channelConnected ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'"
                >
                  {{ channelConnected ? 'Connected' : 'Setup' }}
                </span>
              </div>
              <div class="mt-3 flex items-baseline gap-2">
                <span class="text-3xl font-extrabold tracking-tight text-ink-gray-9">
                  {{ activeAccountsCount }}
                </span>
                <span class="text-xs text-ink-gray-5">phone lines</span>
              </div>
              <p class="mt-2 truncate text-[11px] text-ink-gray-5 group-hover:text-[#075E54]">
                {{ selectedAccountRow ? shownAccountName : `Default: ${defaultAccountName}` }} &rarr;
              </p>
            </a>
          </div>
        </section>

        <!-- Quick Launchpad Navigation Tiles -->
        <section aria-labelledby="launchpad-heading">
          <h2 id="launchpad-heading" class="text-sm font-semibold tracking-wide text-ink-gray-8 uppercase">
            Workspaces & Launchpad
          </h2>
          <div class="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <a
              href="/conversations"
              class="flex items-start gap-3 rounded-xl border border-outline-gray-2 bg-white p-4 shadow-xs transition-all hover:border-[#128C7E] hover:bg-surface-gray-2"
              @click.prevent="navigateTo('/conversations')"
            >
              <div class="grid size-9 shrink-0 place-items-center rounded-lg bg-teal-50 text-[#075E54]">
                <span class="lucide-inbox size-5" aria-hidden="true" />
              </div>
              <div class="min-w-0">
                <p class="text-sm font-semibold text-ink-gray-9">Conversations</p>
                <p class="mt-0.5 text-xs text-ink-gray-6">Live chats, agent assignment, media messages, and replies.</p>
              </div>
            </a>

            <a
              href="/marketing"
              class="flex items-start gap-3 rounded-xl border border-outline-gray-2 bg-white p-4 shadow-xs transition-all hover:border-[#128C7E] hover:bg-surface-gray-2"
              @click.prevent="navigateTo('/marketing')"
            >
              <div class="grid size-9 shrink-0 place-items-center rounded-lg bg-emerald-50 text-emerald-700">
                <span class="lucide-megaphone size-5" aria-hidden="true" />
              </div>
              <div class="min-w-0">
                <p class="text-sm font-semibold text-ink-gray-9">Marketing & Broadcasts</p>
                <p class="mt-0.5 text-xs text-ink-gray-6">Launch outbound WhatsApp campaigns to customer groups.</p>
              </div>
            </a>

            <a
              href="/template-studio"
              class="flex items-start gap-3 rounded-xl border border-outline-gray-2 bg-white p-4 shadow-xs transition-all hover:border-[#128C7E] hover:bg-surface-gray-2"
              @click.prevent="navigateTo('/template-studio')"
            >
              <div class="grid size-9 shrink-0 place-items-center rounded-lg bg-sky-50 text-sky-700">
                <span class="lucide-layout-template size-5" aria-hidden="true" />
              </div>
              <div class="min-w-0">
                <p class="text-sm font-semibold text-ink-gray-9">Template Studio</p>
                <p class="mt-0.5 text-xs text-ink-gray-6">Design message templates with dynamic params & quick replies.</p>
              </div>
            </a>

            <a
              :href="channelPath()"
              class="flex items-start gap-3 rounded-xl border border-outline-gray-2 bg-white p-4 shadow-xs transition-all hover:border-[#128C7E] hover:bg-surface-gray-2"
              @click.prevent="navigateTo(channelPath())"
            >
              <div class="grid size-9 shrink-0 place-items-center rounded-lg bg-amber-50 text-amber-700">
                <span class="lucide-plug size-5" aria-hidden="true" />
              </div>
              <div class="min-w-0">
                <p class="text-sm font-semibold text-ink-gray-9">Integrations & WABA</p>
                <p class="mt-0.5 text-xs text-ink-gray-6">Configure WhatsApp Cloud API tokens, webhooks, and catalogs.</p>
              </div>
            </a>
          </div>
        </section>

        <!-- Priority Attention Queue / Recent Active Conversations -->
        <section class="rounded-xl border border-outline-gray-2 bg-white p-5 shadow-xs" aria-labelledby="priority-queue-heading">
              <div class="flex items-center justify-between border-b border-outline-gray-1 pb-4">
                <div>
                  <h3 id="priority-queue-heading" class="text-base font-semibold text-ink-gray-9">
                    Conversations Needing Attention
                  </h3>
                  <p class="text-xs text-ink-gray-5">
                    Threads requiring prompt agent reply or nearing 24-hour window closure.
                  </p>
                </div>
                <a
                  href="/conversations"
                  class="inline-flex items-center gap-1 text-xs font-semibold text-[#075E54] hover:underline"
                  @click.prevent="navigateTo('/conversations')"
                >
                  View all ({{ conversations.length }}) &rarr;
                </a>
              </div>

              <!-- List of priority threads -->
              <div v-if="priorityQueue.length" class="mt-3 divide-y divide-outline-gray-1">
                <div
                  v-for="item in priorityQueue"
                  :key="item.profile.name"
                  class="flex flex-col gap-3 py-3.5 sm:flex-row sm:items-center sm:justify-between"
                >
                  <div class="flex min-w-0 items-center gap-3">
                    <Avatar
                      :label="item.profile.profile_name || item.profile.phone_number"
                      size="lg"
                    />
                    <div class="min-w-0">
                      <div class="flex items-center gap-2">
                        <p class="truncate text-sm font-semibold text-ink-gray-9">
                          {{ item.profile.profile_name || item.profile.phone_number }}
                        </p>
                        <Badge
                          v-if="item.needs_reply"
                          theme="red"
                          variant="subtle"
                          size="sm"
                          label="Needs Reply"
                        />
                        <Badge
                          v-else-if="item.window?.status === 'open'"
                          theme="green"
                          variant="subtle"
                          size="sm"
                          :label="formatRemaining(item.window.expires_at)"
                        />
                      </div>
                      <p class="truncate text-xs text-ink-gray-6">
                        <span class="font-medium text-ink-gray-5">{{ item.profile.phone_number }}</span>
                        <span class="mx-1">·</span>
                        <span>{{ previewText(item.preview) }}</span>
                      </p>
                    </div>
                  </div>

                  <div class="flex shrink-0 items-center gap-2">
                    <span v-if="item.preview?.creation" class="text-[11px] text-ink-gray-5">
                      {{ formatTime(item.preview.creation) }}
                    </span>
                    <Button
                      variant="subtle"
                      size="sm"
                      class="text-[#075E54] font-medium"
                      label="Reply"
                      @click="handleOpenProfile(item.profile.name)"
                    />
                  </div>
                </div>
              </div>

              <!-- Empty state when all caught up -->
              <div v-else class="py-8 text-center">
                <div class="mx-auto grid size-10 place-items-center rounded-full bg-emerald-50 text-emerald-600">
                  <span class="lucide-check-circle-2 size-5" aria-hidden="true" />
                </div>
                <p class="mt-2 text-sm font-medium text-ink-gray-9">All customer messages are handled!</p>
                <p class="text-xs text-ink-gray-5">No active conversations currently require immediate reply.</p>
              </div>
            </section>

        <!-- Logs and policy share the row and grow into leftover width; health and channels sit beside each other below. -->
        <div class="grid flex-1 grid-cols-1 items-stretch gap-6 lg:grid-cols-2 lg:grid-rows-[minmax(11rem,1fr)_auto]">
            <section class="flex h-full min-h-0 flex-col rounded-xl border border-outline-gray-2 bg-white p-5 shadow-xs" aria-labelledby="activity-feed-heading">
              <div class="flex shrink-0 items-center justify-between border-b border-outline-gray-1 pb-4">
                <div>
                  <h3 id="activity-feed-heading" class="text-base font-semibold text-ink-gray-9">
                    Recent Message Stream
                  </h3>
                  <p class="text-xs text-ink-gray-5">
                    Latest incoming inquiries, outgoing replies, and delivery status updates.
                  </p>
                </div>
                <a
                  href="/integrations/logs"
                  class="inline-flex items-center gap-1 text-xs font-semibold text-[#075E54] hover:underline"
                  @click.prevent="navigateTo('/integrations/logs')"
                >
                  Audit logs &rarr;
                </a>
              </div>

              <div v-if="recentLogs.length" class="mt-3 min-h-0 flex-1 divide-y divide-outline-gray-1 overflow-y-auto">
                <div
                  v-for="log in recentLogs"
                  :key="log.name"
                  class="flex items-start justify-between gap-3 py-3"
                >
                  <div class="min-w-0">
                    <div class="flex items-center gap-2">
                      <span class="text-xs font-semibold text-ink-gray-8">{{ log.event_type }}</span>
                      <span
                        class="inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium"
                        :class="
                          log.level === 'Error'
                            ? 'bg-red-100 text-red-700'
                            : log.level === 'Warning'
                              ? 'bg-amber-100 text-amber-700'
                              : 'bg-gray-100 text-gray-700'
                        "
                      >
                        {{ log.level }}
                      </span>
                      <span v-if="log.account" class="text-[11px] text-ink-gray-5">
                        {{ log.account }}
                      </span>
                    </div>
                    <p class="mt-1 truncate text-xs text-ink-gray-6">{{ log.message }}</p>
                  </div>
                  <span class="shrink-0 text-[11px] text-ink-gray-5">
                    {{ formatTime(log.timestamp) }}
                  </span>
                </div>
              </div>
              <div v-else class="flex flex-1 items-center justify-center py-6 text-center text-xs text-ink-gray-5">
                No recent message logs recorded.
              </div>
            </section>

            <section class="flex h-full min-h-0 flex-col rounded-xl border border-teal-200/60 bg-gradient-to-br from-teal-50/70 to-emerald-50/40 p-5 text-sm text-ink-gray-7 shadow-xs">
              <h4 class="flex shrink-0 items-center gap-1.5 font-semibold text-[#075E54]">
                <span class="lucide-shield-check size-4" aria-hidden="true" />
                WhatsApp SLA & Policy Rules
              </h4>
              <ul class="mt-3 flex min-h-0 flex-1 flex-col gap-3 leading-relaxed">
                <li class="flex flex-1 items-center gap-2.5 rounded-lg bg-white/75 px-3.5 py-3">
                  <span class="font-bold text-[#075E54]">•</span>
                  <span><strong>24-Hour Rule:</strong> Free-form messages can only be sent within 24 hours of the customer's last incoming message.</span>
                </li>
                <li class="flex flex-1 items-center gap-2.5 rounded-lg bg-white/75 px-3.5 py-3">
                  <span class="font-bold text-[#075E54]">•</span>
                  <span><strong>Templates Required:</strong> To initiate conversations or reply after 24h, you must use an approved WhatsApp Template.</span>
                </li>
                <li class="flex flex-1 items-center gap-2.5 rounded-lg bg-white/75 px-3.5 py-3">
                  <span class="font-bold text-[#075E54]">•</span>
                  <span><strong>Read Receipts:</strong> Incoming messages automatically update read markers when configured in account settings.</span>
                </li>
              </ul>
            </section>

            <section class="flex h-full flex-col rounded-xl border border-outline-gray-2 bg-white p-5 shadow-xs" aria-labelledby="integration-status-heading">
              <div class="flex items-center justify-between border-b border-outline-gray-1 pb-3">
                <h3 id="integration-status-heading" class="text-sm font-semibold text-ink-gray-9">
                  Integration & System Health
                </h3>
                <span
                  class="size-2 rounded-full"
                  :class="status?.whatsapp_installed || !live ? 'bg-emerald-500' : 'bg-amber-500'"
                />
              </div>

              <p v-if="status?.detail" class="mt-2 text-xs leading-relaxed text-ink-gray-6">
                {{ status.detail }}
              </p>

              <dl class="mt-3 flex-1 divide-y divide-outline-gray-1 text-xs">
                <div class="flex items-center justify-between py-2.5">
                  <dt class="text-ink-gray-5">WhatsApp App</dt>
                  <dd class="font-medium" :class="status?.whatsapp_installed || !live ? 'text-emerald-700' : 'text-amber-700'">
                    {{ status ? (status.whatsapp_installed ? 'Installed' : 'Not installed') : (!live ? 'Simulated' : 'Checking…') }}
                  </dd>
                </div>

                <div class="flex items-center justify-between py-2.5">
                  <dt class="text-ink-gray-5">DocTypes</dt>
                  <dd class="font-medium text-ink-gray-8">
                    {{ status ? (status.doctypes_ready ? 'Ready' : 'Not ready') : (!live ? 'Ready' : 'Checking…') }}
                  </dd>
                </div>

                <div class="flex items-center justify-between py-2.5">
                  <dt class="text-ink-gray-5">Default Account</dt>
                  <dd class="font-medium text-ink-gray-8">
                    {{ defaultAccountName }}
                  </dd>
                </div>

                <div class="flex items-center justify-between py-2.5">
                  <dt class="text-ink-gray-5">Active Accounts</dt>
                  <dd class="font-medium text-ink-gray-8">
                    {{ accountCount(activeAccountsCount) }}
                  </dd>
                </div>

                <div class="py-2.5">
                  <dt class="text-ink-gray-5">Missing Dependencies</dt>
                  <dd class="mt-1 font-medium text-ink-gray-8">
                    <ul v-if="status?.missing_dependencies?.length" class="list-disc space-y-0.5 pl-4 text-red-600">
                      <li v-for="item in status.missing_dependencies" :key="item">{{ item }}</li>
                    </ul>
                    <span v-else class="text-emerald-600">None · All dependencies satisfied</span>
                  </dd>
                </div>
              </dl>
            </section>

            <!-- Configured WhatsApp Channels / Phone Lines -->
            <section class="flex h-full flex-col rounded-xl border border-outline-gray-2 bg-white p-5 shadow-xs" aria-labelledby="channels-heading">
              <div class="flex items-center justify-between border-b border-outline-gray-1 pb-3">
                <h3 id="channels-heading" class="text-sm font-semibold text-ink-gray-9">
                  Configured Channels
                </h3>
                <a
                  :href="channelPath()"
                  class="text-xs font-medium text-[#075E54] hover:underline"
                  @click.prevent="navigateTo(channelPath())"
                >
                  Manage &rarr;
                </a>
              </div>

              <div class="mt-3 flex-1 space-y-2.5">
                <div
                  v-for="acc in accounts"
                  :key="acc.name"
                  class="flex items-center justify-between rounded-lg border border-outline-gray-1 bg-surface-gray-1/70 px-3 py-2 text-xs"
                >
                  <div>
                    <p class="font-semibold text-ink-gray-9">{{ acc.account_name || acc.name }}</p>
                    <p class="text-[11px] text-ink-gray-5">
                      {{ acc.is_default ? 'Primary default line' : 'Secondary channel' }}
                    </p>
                  </div>
                  <span
                    class="inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium"
                    :class="acc.status === 'Active' ? 'bg-emerald-100 text-emerald-700' : 'bg-gray-100 text-gray-700'"
                  >
                    {{ acc.status }}
                  </span>
                </div>
              </div>
            </section>
        </div>
      </div>
    </div>
  </div>
</template>
