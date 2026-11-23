<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { TextInput } from 'frappe-ui'
import { filterQuickReplies, type QuickReplyRow } from '@/utils/cannedReply'

const props = defineProps<{
  open: boolean
  query?: string
  replies: QuickReplyRow[]
  loading?: boolean
}>()

const emit = defineEmits<{
  select: [row: QuickReplyRow]
  close: []
  'update:query': [value: string]
}>()

const localQuery = ref(props.query || '')
const active = ref(0)

watch(
  () => props.query,
  (value) => {
    if (value !== undefined) localQuery.value = value
  },
)

watch(localQuery, (value) => emit('update:query', value))

const filtered = computed(() => filterQuickReplies(props.replies, localQuery.value))

watch(filtered, () => {
  active.value = 0
})

function pick(row: QuickReplyRow) {
  emit('select', row)
}

function onKeydown(event: KeyboardEvent) {
  if (!props.open) return
  if (event.key === 'Escape') {
    event.preventDefault()
    emit('close')
    return
  }
  if (!filtered.value.length) return
  if (event.key === 'ArrowDown') {
    event.preventDefault()
    active.value = (active.value + 1) % filtered.value.length
  } else if (event.key === 'ArrowUp') {
    event.preventDefault()
    active.value = (active.value - 1 + filtered.value.length) % filtered.value.length
  } else if (event.key === 'Enter') {
    event.preventDefault()
    const row = filtered.value[active.value]
    if (row) pick(row)
  }
}

defineExpose({ onKeydown, filtered })
</script>

<template>
  <div
    v-if="open"
    class="absolute bottom-full left-0 right-0 z-20 mb-2 flex max-h-[min(18rem,calc(100dvh-9rem))] flex-col overflow-hidden rounded-xl border border-[#E9EDEF] bg-white shadow-lg"
    role="listbox"
    aria-label="Quick replies"
  >
    <div class="shrink-0 border-b border-[#E9EDEF] px-3 py-2">
      <div class="flex items-center gap-1">
        <TextInput
          v-model="localQuery"
          class="min-w-0 flex-1"
          placeholder="Filter by shortcut, title, or body…"
          @keydown="onKeydown"
        />
        <button
          type="button"
          class="grid size-8 shrink-0 place-items-center rounded-full text-[#54656F] hover:bg-[#F0F2F5]"
          title="Close quick replies"
          aria-label="Close quick replies"
          @click="emit('close')"
        >
          <span class="lucide-x size-4" aria-hidden="true" />
        </button>
      </div>
      <p class="mt-1 text-[11px] text-[#667781]">
        Tip: type <code class="rounded bg-[#F0F2F5] px-1">/</code> in the composer to open this picker.
      </p>
    </div>
    <div class="min-h-0 flex-1 overflow-y-auto">
      <p v-if="loading" class="px-3 py-6 text-center text-xs text-[#667781]">Loading quick replies…</p>
      <p v-else-if="!filtered.length" class="px-3 py-6 text-center text-xs text-[#667781]">
        No quick replies match.
      </p>
      <button
        v-for="(row, index) in filtered"
        :key="row.name"
        type="button"
        role="option"
        class="flex w-full flex-col gap-0.5 border-b border-[#F0F2F5] px-3 py-2.5 text-left last:border-b-0"
        :class="index === active ? 'bg-[#E7F8F2]' : 'hover:bg-[#F0F2F5]'"
        @click="pick(row)"
        @mouseenter="active = index"
      >
        <span class="flex items-center gap-2 text-sm font-semibold text-[#111B21]">
          <span class="truncate">{{ row.title || row.name }}</span>
          <span
            v-if="row.shortcut"
            class="shrink-0 rounded bg-[#F0F2F5] px-1.5 py-0.5 font-mono text-[11px] font-medium text-[#075E54]"
          >
            /{{ String(row.shortcut).replace(/^\//, '') }}
          </span>
        </span>
        <span class="line-clamp-2 text-xs leading-relaxed text-[#667781]">{{ row.body }}</span>
      </button>
    </div>
  </div>
</template>
