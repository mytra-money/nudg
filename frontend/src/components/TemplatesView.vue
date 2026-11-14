<script setup lang="ts">
import { computed, ref } from 'vue'
import { Badge, Button, Dialog, Select, TextInput, toast } from 'frappe-ui'
import DeskTemplatePreview from '@/components/DeskTemplatePreview.vue'
import { deskRoute, formatDay, initials } from '@/format'
import { isManager, useDesk } from '@/desk'
import type { Template } from '@/types'

const desk = useDesk()
const live = Boolean(window.csrf_token)

const query = ref('')
const selectedCategory = ref<'all' | 'Utility' | 'Marketing' | 'Authentication'>('all')
const selectedStatus = ref<string>('All')
const selectedAccount = ref<string>('all')

const selected = ref<string | null>(null)
const studioMode = ref<'preview' | 'raw'>('preview')

const sending = ref<Template | null>(null)
const recipient = ref('')
const recipientSearch = ref('')

const statuses = ['All', 'Approved', 'Pending', 'Rejected', 'Deleted']
const theme: Record<string, 'green' | 'amber' | 'red' | 'gray'> = {
  Approved: 'green',
  Pending: 'amber',
  Rejected: 'red',
  Deleted: 'gray',
}

const templates = computed(() => desk.inbox.value?.templates || [])

// KPI metrics
const countTotal = computed(() => templates.value.length)
const countApproved = computed(() => templates.value.filter((t) => t.status === 'Approved').length)
const countPending = computed(() => templates.value.filter((t) => t.status === 'Pending').length)
const countUtility = computed(() => templates.value.filter((t) => t.template_type === 'Utility').length)
const countMarketing = computed(() => templates.value.filter((t) => t.template_type === 'Marketing').length)

// Account options
const accountOptions = computed(() => {
  const accs = desk.inbox.value?.accounts || []
  return [
    { label: 'All Accounts', value: 'all' },
    ...accs.map((a) => ({ label: a.account_name || a.name, value: a.name })),
  ]
})

// Filtered templates list
const visible = computed(() =>
  templates.value.filter((template) => {
    // Search
    if (query.value.trim()) {
      const q = query.value.toLowerCase()
      const haystack = `${template.template_label} ${template.template_name || ''} ${template.message} ${template.reference_doctype || ''}`.toLowerCase()
      if (!haystack.includes(q)) return false
    }

    // Category
    if (selectedCategory.value !== 'all' && template.template_type !== selectedCategory.value) {
      return false
    }

    // Status
    if (selectedStatus.value !== 'All' && template.status !== selectedStatus.value) {
      return false
    }

    // Account
    if (selectedAccount.value !== 'all' && template.whatsapp_account && template.whatsapp_account !== selectedAccount.value) {
      return false
    }

    return true
  }),
)

const current = computed(
  () => visible.value.find((template) => template.name === selected.value) || visible.value[0] || null,
)

const recipients = computed(() =>
  (desk.inbox.value?.conversations || [])
    .filter((row) => desk.account.value === 'all' || row.profile.whatsapp_account === desk.account.value)
    .map((row) => ({
      label: `${row.profile.profile_name} · ${row.profile.phone_number}`,
      value: row.profile.name,
      phone: row.profile.phone_number,
      name: row.profile.profile_name,
    })),
)

const filteredRecipients = computed(() => {
  if (!recipientSearch.value.trim()) return recipients.value
  const q = recipientSearch.value.toLowerCase()
  return recipients.value.filter(
    (r) => r.label.toLowerCase().includes(q) || r.phone.toLowerCase().includes(q),
  )
})

function startSending(template: Template) {
  sending.value = template
  recipient.value = recipients.value[0]?.value || ''
  recipientSearch.value = ''
}

async function send() {
  if (!sending.value || !recipient.value) return
  await desk.openProfile(recipient.value)
  await desk.sendTemplate(sending.value)
  sending.value = null
  toast.success('Template sent to conversation!')
}

function selectTemplate(t: Template) {
  selected.value = t.name
}

function openDesk(name = 'new') {
  window.location.href = deskRoute('WA Template', name)
}

function clearFilters() {
  query.value = ''
  selectedCategory.value = 'all'
  selectedStatus.value = 'All'
  selectedAccount.value = 'all'
}
</script>

<template>
  <div class="flex h-full min-w-0 flex-col overflow-hidden bg-surface-gray-1">
    <!-- Top Action Header -->
    <header class="flex flex-col gap-3 border-b border-outline-gray-2 bg-white px-4 py-3 sm:flex-row sm:items-center sm:justify-between shrink-0">
      <div>
        <div class="flex items-center gap-2">
          <span class="rounded bg-[#075E54]/10 px-2 py-0.5 text-[11px] font-bold uppercase tracking-wider text-[#075E54]">
            Meta Cloud API
          </span>
          <span class="text-xs text-ink-gray-5">·</span>
          <span class="text-xs font-medium text-ink-gray-6">Template Studio & Library</span>
        </div>
        <h1 class="mt-1 text-xl font-bold tracking-tight text-ink-gray-9">
          WhatsApp Message Templates
        </h1>
      </div>
      <Button
        v-if="isManager"
        variant="solid"
        size="sm"
        class="bg-[#075E54] text-white hover:bg-[#128C7E]"
        icon-left="lucide-plus"
        label="New Template"
        @click="openDesk()"
      />
    </header>

    <!-- Top KPI Performance Bar -->
    <section class="border-b border-outline-gray-2 bg-white px-4 py-3 shrink-0">
      <div class="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <!-- Approved -->
        <div class="rounded-lg border border-outline-gray-2 bg-surface-gray-1/50 p-2.5">
          <span class="text-[11px] font-medium uppercase tracking-wider text-ink-gray-5">Approved Templates</span>
          <div class="mt-1 flex items-baseline gap-1.5">
            <span class="text-xl font-bold text-emerald-700">{{ countApproved }}</span>
            <span class="text-[11px] text-ink-gray-5">/ {{ countTotal }} total</span>
          </div>
        </div>

        <!-- Pending Meta Review -->
        <div class="rounded-lg border border-outline-gray-2 bg-surface-gray-1/50 p-2.5">
          <span class="text-[11px] font-medium uppercase tracking-wider text-ink-gray-5">Pending Review</span>
          <div class="mt-1 flex items-baseline gap-1.5">
            <span class="text-xl font-bold text-amber-700">{{ countPending }}</span>
            <span class="text-[11px] text-amber-600 font-medium">with Meta</span>
          </div>
        </div>

        <!-- Utility -->
        <div class="rounded-lg border border-outline-gray-2 bg-surface-gray-1/50 p-2.5">
          <span class="text-[11px] font-medium uppercase tracking-wider text-ink-gray-5">Utility Alerts</span>
          <div class="mt-1 flex items-baseline gap-1.5">
            <span class="text-xl font-bold text-[#075E54]">{{ countUtility }}</span>
            <span class="text-[11px] text-ink-gray-5">operational</span>
          </div>
        </div>

        <!-- Marketing -->
        <div class="rounded-lg border border-outline-gray-2 bg-surface-gray-1/50 p-2.5">
          <span class="text-[11px] font-medium uppercase tracking-wider text-ink-gray-5">Marketing Broadcasts</span>
          <div class="mt-1 flex items-baseline gap-1.5">
            <span class="text-xl font-bold text-purple-700">{{ countMarketing }}</span>
            <span class="text-[11px] text-ink-gray-5">promotional</span>
          </div>
        </div>
      </div>
    </section>

    <!-- Filters & Search Toolbar -->
    <section class="border-b border-outline-gray-2 bg-white px-4 py-2.5 space-y-2 shrink-0">
      <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2.5">
        <!-- Search Input -->
        <div class="relative flex-1 max-w-sm">
          <TextInput
            v-model="query"
            placeholder="Search templates by label, body, or doctype…"
            class="w-full text-xs"
          />
          <button
            v-if="query"
            type="button"
            class="absolute right-2.5 top-1/2 -translate-y-1/2 text-ink-gray-4 hover:text-ink-gray-7"
            @click="query = ''"
          >
            <span class="lucide-x size-3" />
          </button>
        </div>

        <div class="flex flex-wrap items-center gap-2">
          <!-- Category Tabs -->
          <div class="flex items-center gap-1 rounded-lg bg-surface-gray-2 p-0.5 text-xs">
            <button
              type="button"
              class="rounded-md px-2.5 py-1 font-medium transition-colors"
              :class="selectedCategory === 'all' ? 'bg-white text-ink-gray-9 shadow-xs' : 'text-ink-gray-6 hover:text-ink-gray-9'"
              @click="selectedCategory = 'all'"
            >
              All Categories
            </button>
            <button
              type="button"
              class="rounded-md px-2.5 py-1 font-medium transition-colors"
              :class="selectedCategory === 'Utility' ? 'bg-white text-[#075E54] shadow-xs' : 'text-ink-gray-6 hover:text-ink-gray-9'"
              @click="selectedCategory = 'Utility'"
            >
              Utility ({{ countUtility }})
            </button>
            <button
              type="button"
              class="rounded-md px-2.5 py-1 font-medium transition-colors"
              :class="selectedCategory === 'Marketing' ? 'bg-white text-purple-700 shadow-xs' : 'text-ink-gray-6 hover:text-ink-gray-9'"
              @click="selectedCategory = 'Marketing'"
            >
              Marketing ({{ countMarketing }})
            </button>
          </div>

          <!-- Status Select -->
          <Select
            class="w-32 text-xs"
            :model-value="selectedStatus"
            :options="statuses"
            @update:model-value="(val) => (selectedStatus = String(val || 'All'))"
          />

          <!-- Account Select -->
          <Select
            class="w-36 text-xs"
            :model-value="selectedAccount"
            :options="accountOptions"
            @update:model-value="(val) => (selectedAccount = String(val || 'all'))"
          />
        </div>
      </div>
    </section>

    <!-- Master-Detail Studio Grid -->
    <div class="grid min-h-0 flex-1 grid-cols-1 md:grid-cols-[minmax(0,1fr)_480px] overflow-hidden">
      <!-- Left Column: Template Library List -->
      <aside class="flex flex-col border-r border-outline-gray-2 bg-white min-h-0 overflow-y-auto divide-y divide-outline-gray-1">
        <div v-if="visible.length === 0" class="p-8 text-center text-xs text-ink-gray-5">
          <div class="mx-auto grid size-10 place-items-center rounded-full bg-surface-gray-2 text-ink-gray-4">
            <span class="lucide-layout-template size-5" />
          </div>
          <p class="mt-2 text-sm font-semibold text-ink-gray-8">No templates found</p>
          <p class="mt-1 text-ink-gray-5">No templates match your search query or selected filters.</p>
          <button
            type="button"
            class="mt-3 text-xs font-semibold text-[#075E54] hover:underline"
            @click="clearFilters"
          >
            Clear all filters
          </button>
        </div>

        <button
          v-for="template in visible"
          :key="template.name"
          type="button"
          class="flex w-full flex-col gap-2 p-4 text-left transition-all hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[#128C7E]"
          :class="
            current?.name === template.name
              ? 'border-l-4 border-l-[#075E54] bg-teal-50/70 shadow-2xs'
              : 'border-l-4 border-l-transparent'
          "
          @click="selectTemplate(template)"
        >
          <div class="flex items-start justify-between gap-2">
            <div>
              <span class="font-bold text-sm text-ink-gray-9 leading-tight">
                {{ template.template_label || template.name }}
              </span>
              <p class="font-mono text-xs text-ink-gray-5 mt-0.5">
                {{ template.template_name || template.name }}
              </p>
            </div>
            <Badge
              :label="template.status"
              :theme="theme[template.status] || 'gray'"
              size="sm"
            />
          </div>

          <!-- Body preview with styled variable chips -->
          <p class="line-clamp-2 text-xs text-ink-gray-7 leading-relaxed">
            {{ template.message }}
          </p>

          <div class="flex flex-wrap items-center gap-1.5 text-[11px] pt-1">
            <span
              class="rounded px-1.5 py-0.2 font-medium"
              :class="template.template_type === 'Utility' ? 'bg-teal-50 text-[#075E54]' : 'bg-purple-50 text-purple-700'"
            >
              {{ template.template_type }}
            </span>
            <span class="rounded bg-surface-gray-2 px-1.5 py-0.2 font-mono text-ink-gray-6">
              {{ template.language }}
            </span>
            <span v-if="template.header_type" class="rounded bg-surface-gray-2 px-1.5 py-0.2 text-ink-gray-6">
              Header: {{ template.header_type }}
            </span>
            <span v-if="template.buttons?.length" class="rounded bg-blue-50 text-blue-700 px-1.5 py-0.2 font-medium">
              {{ template.buttons.length }} CTA buttons
            </span>
            <span v-if="template.reference_doctype" class="text-ink-gray-4 text-[10px] ml-auto">
              DocType: {{ template.reference_doctype }}
            </span>
          </div>
        </button>
      </aside>

      <!-- Right Column: Interactive Studio Inspector Canvas -->
      <main class="flex flex-col bg-white min-h-0 overflow-y-auto p-5 sm:p-6 space-y-5">
        <div v-if="current" class="space-y-5">
          <!-- Template Header & Metadata -->
          <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-outline-gray-2 pb-4">
            <div>
              <div class="flex items-center gap-2">
                <Badge
                  :label="current.status"
                  :theme="theme[current.status] || 'gray'"
                />
                <span class="rounded bg-surface-gray-2 px-2 py-0.5 text-xs font-medium text-ink-gray-7">
                  {{ current.template_type }}
                </span>
                <span class="rounded bg-surface-gray-2 px-2 py-0.5 text-xs font-mono text-ink-gray-6">
                  {{ current.language }}
                </span>
              </div>
              <h2 class="mt-2 text-xl font-bold text-ink-gray-9 leading-tight">
                {{ current.template_label || current.name }}
              </h2>
              <p class="font-mono text-xs text-ink-gray-5 mt-0.5">
                {{ current.template_name || current.name }}
                <span v-if="current.whatsapp_account"> · Channel: {{ current.whatsapp_account }}</span>
              </p>
            </div>

            <div class="flex items-center gap-2 shrink-0">
              <Button
                v-if="isManager"
                variant="subtle"
                label="Edit in Desk"
                icon-left="lucide-pencil"
                @click="openDesk(current.name)"
              />
              <Button
                variant="solid"
                class="bg-[#075E54] text-white hover:bg-[#128C7E]"
                label="Send to Customer"
                icon-left="lucide-send"
                :disabled="current.status !== 'Approved'"
                @click="startSending(current)"
              />
            </div>
          </div>

          <!-- Mode Toggle (Preview vs Technical Raw Payload) -->
          <div class="flex items-center justify-between border-b border-outline-gray-2 pb-3">
            <div class="flex items-center gap-1 text-xs">
              <button
                type="button"
                class="rounded-lg px-3 py-1 font-semibold transition-colors"
                :class="studioMode === 'preview' ? 'bg-[#075E54] text-white' : 'bg-surface-gray-2 text-ink-gray-7 hover:bg-surface-gray-3'"
                @click="studioMode = 'preview'"
              >
                Interactive Preview
              </button>
              <button
                type="button"
                class="rounded-lg px-3 py-1 font-semibold transition-colors"
                :class="studioMode === 'raw' ? 'bg-[#075E54] text-white' : 'bg-surface-gray-2 text-ink-gray-7 hover:bg-surface-gray-3'"
                @click="studioMode = 'raw'"
              >
                Raw Meta Specification
              </button>
            </div>

            <span class="text-[11px] text-ink-gray-5">
              {{ current.status === 'Approved' ? '✅ Ready for 24h & outbound broadcast' : '⚠️ Requires Meta approval before sending' }}
            </span>
          </div>

          <!-- Interactive WhatsApp Canvas Bubble -->
          <div class="rounded-xl border border-outline-gray-2 bg-[#efeae2]/40 p-4 shadow-inner">
            <p class="text-[11px] font-bold uppercase tracking-wider text-ink-gray-5 mb-3 flex items-center gap-1.5">
              <span class="lucide-smartphone size-3.5 text-[#075E54]" />
              WhatsApp Message Preview
            </p>
            <DeskTemplatePreview :template="current" :mode="studioMode" :editable="true" />
          </div>

          <!-- Variable Inspector (if parameters exist) -->
          <div v-if="current.template_variables?.length" class="rounded-xl border border-outline-gray-2 p-4 bg-white space-y-2.5">
            <h3 class="text-xs font-bold uppercase tracking-wider text-ink-gray-6 flex items-center gap-1.5">
              <span class="lucide-variable size-3.5 text-[#075E54]" />
              Dynamic Parameters & Sample Values
            </h3>
            <p class="text-xs text-ink-gray-5">
              These placeholders are dynamically replaced by Frappe DocType fields or API arguments:
            </p>
            <div class="divide-y divide-outline-gray-1 border rounded-lg border-outline-gray-2 overflow-hidden text-xs">
              <div
                v-for="v in current.template_variables"
                :key="v.variable_name"
                class="flex items-center justify-between p-2.5 bg-white"
              >
                <span class="font-mono font-bold text-[#075E54]">&#123;&#123;{{ v.variable_name }}&#125;&#125;</span>
                <span class="text-ink-gray-7">
                  Example: <strong>{{ v.variable_example || 'Sample Value' }}</strong>
                </span>
                <span v-if="v.variable_field" class="rounded bg-surface-gray-2 px-1.5 py-0.5 font-mono text-[11px] text-ink-gray-6">
                  {{ v.variable_field }}
                </span>
              </div>
            </div>
          </div>

          <!-- Interactive Action Buttons Specification -->
          <div v-if="current.buttons?.length" class="rounded-xl border border-outline-gray-2 p-4 bg-white space-y-2">
            <h3 class="text-xs font-bold uppercase tracking-wider text-ink-gray-6 flex items-center gap-1.5">
              <span class="lucide-mouse-pointer-click size-3.5 text-blue-600" />
              Quick Action Buttons ({{ current.buttons.length }})
            </h3>
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
              <div
                v-for="btn in current.buttons"
                :key="btn.button_text"
                class="rounded-lg border border-outline-gray-2 p-2.5 bg-surface-gray-1/40"
              >
                <div class="flex items-center justify-between">
                  <span class="font-semibold text-ink-gray-9">{{ btn.button_text }}</span>
                  <span class="rounded bg-blue-50 text-blue-700 px-1.5 py-0.2 text-[10px] font-medium">
                    {{ btn.button_type }}
                  </span>
                </div>
                <p v-if="btn.url" class="mt-1 font-mono text-[11px] text-ink-gray-5 truncate">
                  {{ btn.url }}
                </p>
                <p v-if="btn.phone_number" class="mt-1 font-mono text-[11px] text-ink-gray-5">
                  {{ btn.phone_number }}
                </p>
              </div>
            </div>
          </div>
        </div>

        <div v-else class="grid flex-1 place-items-center p-8 text-center text-xs text-ink-gray-5">
          Select a template from the library on the left.
        </div>
      </main>
    </div>

    <!-- Send Template Modal Dialog -->
    <Dialog
      :open="Boolean(sending)"
      title="Send WhatsApp Template"
      size="lg"
      @update:open="(open) => !open && (sending = null)"
    >
      <div v-if="sending" class="space-y-4 py-2 text-xs">
        <div class="rounded-xl border border-teal-200 bg-teal-50 p-3.5 text-[#075E54] leading-relaxed">
          <p class="font-bold flex items-center gap-1.5">
            <span class="lucide-send size-4" /> Initiating Template Message
          </p>
          <p class="mt-1 text-ink-gray-7">
            Sending template <strong>{{ sending.template_label || sending.name }}</strong> ({{ sending.template_type }}). Templates can be delivered even when the customer's 24-hour service window is closed.
          </p>
        </div>

        <!-- Recipient Search & Selector -->
        <div>
          <label class="block text-xs font-semibold text-ink-gray-7 mb-1">Select Customer Recipient *</label>
          <TextInput
            v-model="recipientSearch"
            placeholder="Search customer by name or phone…"
            class="w-full mb-2"
          />

          <div class="max-h-48 overflow-y-auto divide-y divide-outline-gray-1 border border-outline-gray-2 rounded-lg bg-white">
            <button
              v-for="r in filteredRecipients"
              :key="r.value"
              type="button"
              class="flex items-center justify-between w-full p-2.5 text-left transition-colors hover:bg-surface-gray-1"
              :class="recipient === r.value ? 'bg-teal-50/70 text-[#075E54] font-semibold' : 'text-ink-gray-8'"
              @click="recipient = r.value"
            >
              <div class="flex items-center gap-2 min-w-0">
                <span class="grid size-7 shrink-0 place-items-center rounded-full bg-teal-100 text-[10px] font-bold text-[#075E54]">
                  {{ initials(r.name) }}
                </span>
                <div class="min-w-0">
                  <p class="truncate text-xs">{{ r.name }}</p>
                  <p class="text-[11px] font-mono text-ink-gray-5">{{ r.phone }}</p>
                </div>
              </div>
              <span v-if="recipient === r.value" class="lucide-check size-4 text-[#075E54] shrink-0" />
            </button>
          </div>
        </div>

        <!-- Message Preview Bubble in Modal -->
        <div class="rounded-lg border border-outline-gray-2 bg-[#efeae2]/40 p-3">
          <p class="text-[10px] font-bold uppercase tracking-wider text-ink-gray-5 mb-2">Message Content</p>
          <DeskTemplatePreview :template="sending" mode="preview" :editable="false" />
        </div>
      </div>

      <template #actions>
        <div class="flex justify-between w-full">
          <Button label="Cancel" @click="sending = null" />
          <Button
            v-if="sending?.status === 'Approved'"
            variant="solid"
            class="bg-[#075E54] text-white hover:bg-[#128C7E]"
            label="Confirm & Send Template"
            icon-left="lucide-send"
            :disabled="!recipient"
            :loading="desk.sending.value"
            @click="send"
          />
        </div>
      </template>
    </Dialog>
  </div>
</template>
