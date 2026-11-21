<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import { Avatar, Badge, Button } from 'frappe-ui'
import { NumberCard } from 'frappe-ui/charts'
import DeskCard from '@/components/desk/DeskCard.vue'
import EmptyState from '@/components/EmptyState.vue'
import ErrorState from '@/components/ErrorState.vue'
import LoadingState from '@/components/LoadingState.vue'
import { isManager, useDesk } from '@/stores/desk'
import { formatRemaining, formatTime, initials, previewText } from '@/utils/format'
import { userFacingError } from '@/utils/errors'
import { useIntegrationStatus } from '@/utils/integration'
import { router } from '@/router'

const { live, status, loading, error, bootInstalled, load } = useIntegrationStatus()
const desk = useDesk()

onMounted(() => {
  void load()
  if (!desk.inbox.value) void desk.load()
  else void desk.refresh()
  if (desk.mode.value === 'live') void desk.loadLogs()
})

watch(
  () => desk.account.value,
  () => {
    if (desk.mode.value === 'live') void desk.loadLogs()
  },
)

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
            <span class="text-xs font-medium text-ink-gray-6">Omnichannel Nudg</span>
          </div>
          <h1 class="mt-1.5 text-2xl font-bold tracking-tight text-ink-gray-9 sm:text-3xl">
            Nudg Overview
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
                You are currently previewing Nudg with simulated WhatsApp data. Conversations, templates, and logs can be tested interactively.
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

        <!-- Metric KPI Cards (frappe-ui NumberCard) -->
        <section aria-labelledby="kpi-heading">
          <h2 id="kpi-heading" class="sr-only">Key Performance Indicators</h2>
          <div class="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <a
              href="/conversations?tab=needs_reply"
              class="block min-w-0"
              @click.prevent="navigateTo('/conversations?tab=needs_reply')"
            >
              <NumberCard
                title="Needs reply"
                :value="needsReplyCount"
                :color="needsReplyCount > 0 ? '#B91C1C' : '#047857'"
                :delta-caption="needsReplyCount > 0 ? 'pending response' : 'all caught up'"
              />
            </a>
            <a
              href="/conversations?tab=window_open"
              class="block min-w-0"
              @click.prevent="navigateTo('/conversations?tab=window_open')"
            >
              <NumberCard
                title="Open 24h windows"
                :value="openWindowsCount"
                color="#075E54"
                :delta-caption="openWindowsCount > 0 ? 'free-form eligible' : 'template only'"
              />
            </a>
            <a href="/template-studio" class="block min-w-0" @click.prevent="navigateTo('/template-studio')">
              <NumberCard
                title="Templates"
                :value="approvedTemplatesCount"
                :target="templates.length"
                color="#0369A1"
                delta-caption="approved for send"
              />
            </a>
            <a :href="channelPath()" class="block min-w-0" @click.prevent="navigateTo(channelPath())">
              <NumberCard
                title="WABA channels"
                :value="activeAccountsCount"
                :color="channelConnected ? '#047857' : '#B45309'"
                :delta-caption="selectedAccountRow ? shownAccountName : `Default: ${defaultAccountName}`"
              />
            </a>
          </div>
        </section>

        <!-- Quick Launchpad Navigation Tiles -->
        <section aria-labelledby="launchpad-heading">
          <h2 id="launchpad-heading" class="text-sm font-semibold uppercase tracking-wide text-ink-gray-8">
            Workspaces & Launchpad
          </h2>
          <div class="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <DeskCard
              as="a"
              href="/conversations"
              interactive
              padding
              class="!p-4"
              @click.prevent="navigateTo('/conversations')"
            >
              <div class="flex items-start gap-3">
                <div class="grid size-9 shrink-0 place-items-center rounded-lg bg-teal-50 text-[#075E54]">
                  <span class="lucide-inbox size-5" aria-hidden="true" />
                </div>
                <div class="min-w-0">
                  <p class="text-sm font-semibold text-ink-gray-9">Conversations</p>
                  <p class="mt-0.5 text-xs text-ink-gray-6">Live chats, agent assignment, media messages, and replies.</p>
                </div>
              </div>
            </DeskCard>

            <DeskCard
              as="a"
              href="/marketing"
              interactive
              class="!p-4"
              @click.prevent="navigateTo('/marketing')"
            >
              <div class="flex items-start gap-3">
                <div class="grid size-9 shrink-0 place-items-center rounded-lg bg-emerald-50 text-emerald-700">
                  <span class="lucide-megaphone size-5" aria-hidden="true" />
                </div>
                <div class="min-w-0">
                  <p class="text-sm font-semibold text-ink-gray-9">Marketing & Broadcasts</p>
                  <p class="mt-0.5 text-xs text-ink-gray-6">Launch outbound WhatsApp campaigns to customer groups.</p>
                </div>
              </div>
            </DeskCard>

            <DeskCard
              as="a"
              href="/catalogs"
              interactive
              class="!p-4"
              @click.prevent="navigateTo('/catalogs')"
            >
              <div class="flex items-start gap-3">
                <div class="grid size-9 shrink-0 place-items-center rounded-lg bg-orange-50 text-orange-700">
                  <span class="lucide-shopping-bag size-5" aria-hidden="true" />
                </div>
                <div class="min-w-0">
                  <p class="text-sm font-semibold text-ink-gray-9">Catalogs</p>
                  <p class="mt-0.5 text-xs text-ink-gray-6">Products, prices, and the Meta catalog id for this number.</p>
                </div>
              </div>
            </DeskCard>

            <DeskCard
              as="a"
              href="/template-studio"
              interactive
              class="!p-4"
              @click.prevent="navigateTo('/template-studio')"
            >
              <div class="flex items-start gap-3">
                <div class="grid size-9 shrink-0 place-items-center rounded-lg bg-sky-50 text-sky-700">
                  <span class="lucide-layout-template size-5" aria-hidden="true" />
                </div>
                <div class="min-w-0">
                  <p class="text-sm font-semibold text-ink-gray-9">Template Studio</p>
                  <p class="mt-0.5 text-xs text-ink-gray-6">Design message templates with dynamic params & quick replies.</p>
                </div>
              </div>
            </DeskCard>

            <DeskCard
              as="a"
              :href="channelPath()"
              interactive
              class="!p-4"
              @click.prevent="navigateTo(channelPath())"
            >
              <div class="flex items-start gap-3">
                <div class="grid size-9 shrink-0 place-items-center rounded-lg bg-amber-50 text-amber-700">
                  <span class="lucide-plug size-5" aria-hidden="true" />
                </div>
                <div class="min-w-0">
                  <p class="text-sm font-semibold text-ink-gray-9">Integrations & WABA</p>
                  <p class="mt-0.5 text-xs text-ink-gray-6">Configure WhatsApp Cloud API tokens, webhooks, and ERPNext.</p>
                </div>
              </div>
            </DeskCard>
          </div>
        </section>

        <DeskCard
          title="Conversations Needing Attention"
          description="Threads requiring prompt agent reply or nearing 24-hour window closure."
          aria-labelledby="priority-queue-heading"
        >
          <template #actions>
            <a
              href="/conversations"
              class="inline-flex items-center gap-1 text-xs font-semibold text-[#075E54] hover:underline"
              @click.prevent="navigateTo('/conversations')"
            >
              View all ({{ conversations.length }}) &rarr;
            </a>
          </template>

          <div v-if="priorityQueue.length" class="divide-y divide-outline-gray-1">
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
                  class="font-medium text-[#075E54]"
                  label="Reply"
                  @click="handleOpenProfile(item.profile.name)"
                />
              </div>
            </div>
          </div>

          <div v-else class="py-8 text-center">
            <div class="mx-auto grid size-10 place-items-center rounded-full bg-emerald-50 text-emerald-600">
              <span class="lucide-check-circle-2 size-5" aria-hidden="true" />
            </div>
            <p class="mt-2 text-sm font-medium text-ink-gray-9">All customer messages are handled!</p>
            <p class="text-xs text-ink-gray-5">No active conversations currently require immediate reply.</p>
          </div>
        </DeskCard>

        <div class="grid flex-1 grid-cols-1 items-stretch gap-6 lg:grid-cols-2 lg:grid-rows-[minmax(11rem,1fr)_auto]">
          <DeskCard
            class="flex h-full min-h-0 flex-col"
            title="Recent Message Stream"
            description="Latest incoming inquiries, outgoing replies, and delivery status updates."
          >
            <template #actions>
              <a
                href="/integrations/logs"
                class="inline-flex items-center gap-1 text-xs font-semibold text-[#075E54] hover:underline"
                @click.prevent="navigateTo('/integrations/logs')"
              >
                Audit logs &rarr;
              </a>
            </template>

            <div v-if="recentLogs.length" class="min-h-0 flex-1 divide-y divide-outline-gray-1 overflow-y-auto">
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
                  <p class="mt-1 truncate text-xs text-ink-gray-6">
                    {{ userFacingError(log.message, log.level === 'Error' ? 'Something went wrong.' : 'Activity recorded.') }}
                  </p>
                </div>
                <span class="shrink-0 text-[11px] text-ink-gray-5">
                  {{ formatTime(log.timestamp) }}
                </span>
              </div>
            </div>
            <div v-else class="flex flex-1 items-center justify-center py-6 text-center text-xs text-ink-gray-5">
              No recent message logs recorded.
            </div>
          </DeskCard>

          <DeskCard tone="accent" class="flex h-full min-h-0 flex-col text-sm text-ink-gray-7">
            <template #header>
              <h4 class="flex items-center gap-1.5 font-semibold text-[#075E54]">
                <span class="lucide-shield-check size-4" aria-hidden="true" />
                WhatsApp SLA & Policy Rules
              </h4>
            </template>
            <ul class="flex min-h-0 flex-1 flex-col gap-3 leading-relaxed">
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
          </DeskCard>

          <DeskCard title="Integration & System Health" class="flex h-full flex-col">
            <template #actions>
              <span
                class="size-2 rounded-full"
                :class="status?.whatsapp_installed || !live ? 'bg-emerald-500' : 'bg-amber-500'"
              />
            </template>

            <p v-if="status?.detail" class="text-xs leading-relaxed text-ink-gray-6">
              {{ status.detail }}
            </p>

            <dl class="mt-1 flex-1 divide-y divide-outline-gray-1 text-xs">
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
                <dd class="font-medium text-ink-gray-8">{{ defaultAccountName }}</dd>
              </div>
              <div class="flex items-center justify-between py-2.5">
                <dt class="text-ink-gray-5">Active Accounts</dt>
                <dd class="font-medium text-ink-gray-8">{{ accountCount(activeAccountsCount) }}</dd>
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
          </DeskCard>

          <DeskCard title="Configured Channels" class="flex h-full flex-col">
            <template #actions>
              <a
                :href="channelPath()"
                class="text-xs font-medium text-[#075E54] hover:underline"
                @click.prevent="navigateTo(channelPath())"
              >
                Manage &rarr;
              </a>
            </template>

            <div class="flex-1 space-y-2.5">
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
          </DeskCard>
        </div>
      </div>
    </div>
  </div>
</template>
