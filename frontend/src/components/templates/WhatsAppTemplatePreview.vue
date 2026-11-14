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
  }>(),
  { editable: true, large: false },
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
  <div class="space-y-3" data-template-preview>
    <div
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
    <TemplateVariableEditor v-if="editable" :names="names" :values="samples" @update="onSample" />
  </div>
</template>

<style scoped>
.wa-wallpaper {
  background-color: #efe7dc;
  background-image: radial-gradient(rgba(84, 66, 46, 0.09) 0.7px, transparent 0.7px);
  background-size: 14px 14px;
}
</style>
