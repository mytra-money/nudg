<script setup lang="ts">
import { computed } from 'vue'
import WhatsAppTemplatePreview from '@/components/templates/WhatsAppTemplatePreview.vue'
import type { Template } from '@/types'

const props = withDefaults(
  defineProps<{
    template: Template
    mode?: 'preview' | 'raw'
    editable?: boolean
    large?: boolean
    chrome?: 'plain' | 'phone' | 'desktop'
  }>(),
  { mode: 'preview', editable: true, large: false, chrome: 'plain' },
)

const rawRows = computed(() => {
  const template = props.template
  const buttons = (template.buttons || [])
    .map((button) => {
      const extra = [button.url, button.phone_number].filter(Boolean).join(' ')
      return extra ? `${button.button_type}: ${button.button_text} (${extra})` : `${button.button_type}: ${button.button_text}`
    })
    .join('\n')
  const variables = (template.template_variables || [])
    .map((row) => `${row.variable_name} = ${row.variable_example || ''}${row.variable_field ? ` [${row.variable_field}]` : ''}`)
    .join('\n')
  return [
    { label: 'Header type', value: template.header_type || 'Text' },
    { label: 'Header text', value: template.header_text || '—' },
    { label: 'Header media', value: template.header_media || '—' },
    { label: 'MIME type', value: template.mime_type || '—' },
    { label: 'Message', value: template.message || '—' },
    { label: 'Footer', value: template.footer || '—' },
    { label: 'Buttons', value: buttons || '—' },
    { label: 'Variable format', value: template.variable_format || '—' },
    { label: 'Variables', value: variables || '—' },
  ]
})
</script>

<template>
  <div v-if="mode === 'raw'" class="space-y-2">
    <p class="text-xs font-medium uppercase tracking-wide text-ink-gray-5">Raw template</p>
    <dl class="space-y-2 text-xs">
      <div v-for="row in rawRows" :key="row.label">
        <dt class="text-ink-gray-5">{{ row.label }}</dt>
        <dd class="mt-0.5 whitespace-pre-wrap break-words font-mono text-[12px] text-ink-gray-9">{{ row.value }}</dd>
      </div>
    </dl>
  </div>
  <WhatsAppTemplatePreview v-else :template="template" :editable="editable" :large="large" :chrome="chrome" />
</template>
