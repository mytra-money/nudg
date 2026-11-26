<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import TemplateMessageBubble from '@/components/templates/TemplateMessageBubble.vue'
import TemplateVariableEditor from '@/components/templates/TemplateVariableEditor.vue'
import { initials, formatTime } from '@/utils/format'
import { fillVariables, previewVariableNames, resolveSampleValues } from '@/utils/templatePreview'
import type { Template } from '@/types'

const props = withDefaults(
  defineProps<{
    template: Template
    sampleValues?: Record<string, string>
    editable?: boolean
    large?: boolean
    chrome?: 'plain' | 'phone' | 'desktop' | 'stage'
  }>(),
  { editable: true, large: false, chrome: 'plain' },
)

const emit = defineEmits<{ 'update:sampleValues': [Record<string, string>] }>()

const internal = ref<Record<string, string>>({})
const time = ref(formatTime(new Date().toISOString()))

const signature = computed(() =>
  [
    props.template.name,
    props.template.header_text,
    props.template.message,
    ...(props.template.buttons || []).map((button) => button.url || ''),
    JSON.stringify(props.template.template_variables || []),
  ].join('|'),
)

watch(
  signature,
  () => {
    time.value = formatTime(new Date().toISOString())
    if (!props.sampleValues) internal.value = resolveSampleValues(props.template)
  },
  { immediate: true },
)

const names = computed(() => previewVariableNames(props.template))
const hints = computed(() => {
  const map: Record<string, string> = {}
  for (const row of props.template.template_variables || []) {
    if (row.variable_field) map[row.variable_name] = row.variable_field
  }
  return map
})
const samples = computed(() => props.sampleValues ?? internal.value)
const businessName = computed(() => props.template.whatsapp_account || 'Business')
const headerText = computed(() => {
  if (props.template.header_type && props.template.header_type !== 'Text') return ''
  return fillVariables(props.template.header_text, samples.value)
})
const body = computed(() => fillVariables(props.template.message, samples.value))

function onSample(name: string, value: string) {
  const next = { ...samples.value, [name]: value }
  if (props.sampleValues) emit('update:sampleValues', next)
  else internal.value = next
}
</script>

<template>
  <div
    data-template-preview
    :class="
      chrome === 'stage'
        ? 'flex h-full min-h-0 flex-col'
        : chrome === 'plain'
          ? 'space-y-3'
          : 'flex flex-col gap-4 xl:flex-row xl:items-start'
    "
  >
    <div v-if="chrome === 'stage'" class="stage-layout">
      <section class="stage-chat" aria-label="Customer view">
        <div
          class="wa-wallpaper min-h-0 flex-1 overflow-y-auto px-3 py-3"
          role="region"
          aria-label="Template conversation preview"
        >
          <TemplateMessageBubble
            :header-type="template.header_type"
            :header-text="headerText"
            :media-url="template.header_media"
            :mime-type="template.mime_type"
            :body="body"
            :footer="template.footer"
            :buttons="template.buttons"
            :samples="samples"
            :time="time"
          />
        </div>
      </section>
      <aside v-if="editable && names.length" class="stage-samples">
        <TemplateVariableEditor compact :names="names" :values="samples" :hints="hints" @update="onSample" />
      </aside>
    </div>
    <div v-else-if="chrome === 'phone'" class="iphone mx-auto w-full max-w-[340px] shrink-0" aria-label="iPhone preview">
      <div class="rounded-[2.7rem] bg-[#1c1c1e] p-[11px] shadow-xl ring-1 ring-black/30">
        <div class="relative overflow-hidden rounded-[2.15rem] bg-white">
          <div class="relative bg-[#1e3a32] text-white">
            <div class="flex h-12 items-end justify-between px-6 pb-1 text-[12px] font-semibold leading-none">
              <span>9:41</span>
              <span class="flex items-center gap-1.5" aria-hidden="true">
                <svg viewBox="0 0 18 12" class="h-3 w-4 fill-current"><rect x="0" y="7" width="3" height="5" rx="0.6" /><rect x="5" y="4" width="3" height="8" rx="0.6" /><rect x="10" y="1.5" width="3" height="10.5" rx="0.6" /><rect x="15" y="0" width="3" height="12" rx="0.6" /></svg>
                <svg viewBox="0 0 16 12" class="h-3 w-4 fill-current"><path d="M8 2.2c2.3 0 4.4.9 6 2.4l-1.2 1.3A6.6 6.6 0 0 0 8 3.8 6.6 6.6 0 0 0 3.2 5.9L2 4.6A8.4 8.4 0 0 1 8 2.2Zm0 3.2c1.3 0 2.5.5 3.4 1.4L10.2 8A3.2 3.2 0 0 0 8 7a3.2 3.2 0 0 0-2.2 1L4.6 6.8A4.8 4.8 0 0 1 8 5.4ZM8 9.2a1.1 1.1 0 1 1 0 2.2 1.1 1.1 0 0 1 0-2.2Z" /></svg>
                <svg viewBox="0 0 25 12" class="h-3 w-6"><rect x="0.5" y="0.5" width="21" height="11" rx="2.5" fill="none" stroke="currentColor" /><rect x="2" y="2" width="16" height="8" rx="1.2" fill="currentColor" /><rect x="22.5" y="3.5" width="1.5" height="5" rx="0.6" fill="currentColor" /></svg>
              </span>
            </div>
            <div class="absolute left-1/2 top-2 h-[22px] w-[96px] -translate-x-1/2 rounded-full bg-black" aria-hidden="true" />
            <header class="flex items-center gap-2.5 px-3 pb-2.5">
              <div class="flex size-8 shrink-0 items-center justify-center rounded-full bg-[#31584c] text-[11px] font-semibold">
                {{ initials(businessName) }}
              </div>
              <div class="min-w-0">
                <p class="truncate text-sm font-medium">{{ businessName }}</p>
                <p class="text-[11px] text-white/70">online</p>
              </div>
            </header>
          </div>
          <div
            class="wa-wallpaper h-[min(54vh,30rem)] min-h-[22rem] overflow-y-auto px-3 py-4"
            role="region"
            aria-label="Template conversation preview"
          >
            <TemplateMessageBubble
              :header-type="template.header_type"
              :header-text="headerText"
              :media-url="template.header_media"
              :mime-type="template.mime_type"
              :body="body"
              :footer="template.footer"
              :buttons="template.buttons"
              :samples="samples"
              :time="time"
            />
          </div>
          <div class="bg-[#f0f2f5] px-2.5 pb-1.5 pt-2" aria-hidden="true">
            <div class="flex items-center gap-2">
              <span class="grid size-7 place-items-center rounded-full text-sm text-ink-gray-5">+</span>
              <div class="h-8 flex-1 rounded-full bg-white px-3 text-[12px] leading-8 text-ink-gray-4">Message</div>
              <span class="grid size-8 place-items-center rounded-full bg-wa-teal text-white">
                <span class="lucide-mic size-4" />
              </span>
            </div>
            <div class="mt-2 flex justify-center pb-1">
              <span class="h-[5px] w-28 rounded-full bg-black/85" />
            </div>
          </div>
        </div>
      </div>
    </div>

    <div v-else-if="chrome === 'desktop'" class="min-w-0 flex-1 overflow-hidden rounded-xl border border-[#d1d7db] bg-white shadow-sm">
      <div class="flex h-9 items-center gap-1.5 border-b border-outline-gray-2 bg-[#f0f2f5] px-3">
        <span class="size-2.5 rounded-full bg-[#ff5f57]" />
        <span class="size-2.5 rounded-full bg-[#febc2e]" />
        <span class="size-2.5 rounded-full bg-[#28c840]" />
        <span class="ml-2 text-xs font-medium text-ink-gray-6">WhatsApp</span>
      </div>
      <div class="desktop-grid">
        <aside class="desktop-chats border-r border-outline-gray-2 bg-white">
          <div class="bg-wa-teal px-3 py-3 text-xs font-semibold text-white">Chats</div>
          <div class="border-b border-outline-gray-1 bg-[#f0fdf4] px-3 py-2.5">
            <p class="truncate text-xs font-semibold text-ink-gray-9">{{ businessName }}</p>
            <p class="mt-0.5 line-clamp-2 text-[11px] leading-snug text-ink-gray-5">{{ body || 'Template preview' }}</p>
          </div>
        </aside>
        <div class="flex min-h-[24rem] min-w-0 flex-col">
          <header class="flex items-center gap-2 border-b border-outline-gray-2 bg-[#f0f2f5] px-3 py-2">
            <div class="flex size-8 shrink-0 items-center justify-center rounded-full bg-[#31584c] text-[11px] font-semibold text-white">
              {{ initials(businessName) }}
            </div>
            <div class="min-w-0">
              <p class="truncate text-sm font-medium text-ink-gray-9">{{ businessName }}</p>
              <p class="text-[11px] text-ink-gray-5">online</p>
            </div>
          </header>
          <div
            class="wa-wallpaper min-h-0 flex-1 overflow-y-auto px-4 py-4"
            role="region"
            aria-label="Template conversation preview"
          >
            <TemplateMessageBubble
              :header-type="template.header_type"
              :header-text="headerText"
              :media-url="template.header_media"
              :mime-type="template.mime_type"
              :body="body"
              :footer="template.footer"
              :buttons="template.buttons"
              :samples="samples"
              :time="time"
            />
          </div>
          <div class="flex items-center gap-2 border-t border-outline-gray-2 bg-[#f0f2f5] px-3 py-2" aria-hidden="true">
            <span class="text-sm text-ink-gray-5">+</span>
            <div class="h-8 flex-1 rounded-lg bg-white px-3 text-[12px] leading-8 text-ink-gray-4">Type a message</div>
          </div>
        </div>
      </div>
    </div>

    <div
      v-else
      class="mx-auto w-full overflow-hidden rounded-2xl border border-outline-gray-2 bg-white"
      :class="large ? 'max-w-[440px]' : 'max-w-[320px]'"
    >
      <header class="flex items-center gap-2.5 bg-[#1e3a32] px-3 py-2.5 text-white">
        <div class="flex size-8 shrink-0 items-center justify-center rounded-full bg-[#31584c] text-[11px] font-semibold">
          {{ initials(businessName) }}
        </div>
        <div class="min-w-0">
          <p class="truncate text-sm font-medium">{{ businessName }}</p>
          <p class="text-[11px] text-white/70">Business message preview</p>
        </div>
      </header>
      <div
        class="wa-wallpaper overflow-y-auto px-3 py-4"
        :class="large ? 'max-h-[min(58vh,36rem)]' : 'max-h-80'"
        role="region"
        aria-label="Template conversation preview"
      >
        <TemplateMessageBubble
          :header-type="template.header_type"
          :header-text="headerText"
          :media-url="template.header_media"
          :mime-type="template.mime_type"
          :body="body"
          :footer="template.footer"
          :buttons="template.buttons"
          :samples="samples"
          :time="time"
        />
      </div>
    </div>
    <TemplateVariableEditor
      v-if="editable && chrome !== 'stage'"
      class="w-full xl:max-w-xs xl:shrink-0"
      :names="names"
      :values="samples"
      :hints="hints"
      @update="onSample"
    />
  </div>
</template>

<style scoped>
[data-template-preview] {
  container-type: inline-size;
}
.wa-wallpaper {
  background-color: #efe7dc;
  background-image: radial-gradient(rgba(84, 66, 46, 0.09) 0.7px, transparent 0.7px);
  background-size: 14px 14px;
}
.stage-layout {
  display: flex;
  min-height: 0;
  flex: 1 1 auto;
  flex-direction: column;
  overflow: hidden;
}
.stage-chat {
  display: flex;
  min-height: 0;
  min-width: 0;
  flex: 1 1 auto;
  flex-direction: column;
  overflow: hidden;
}
.stage-samples {
  flex: 0 0 auto;
  max-height: 5.25rem;
  overflow: auto;
  border-top: 1px solid var(--outline-gray-2, #e5e7eb);
  background: #f7f8f8;
  padding: 0.45rem 0.75rem;
}
.desktop-grid {
  display: grid;
  min-height: 24rem;
  grid-template-columns: minmax(0, 1fr);
}
.desktop-chats {
  display: none;
}
@container (min-width: 560px) {
  .desktop-grid {
    grid-template-columns: 9.5rem minmax(0, 1fr);
  }
  .desktop-chats {
    display: flex;
    flex-direction: column;
  }
}
</style>
