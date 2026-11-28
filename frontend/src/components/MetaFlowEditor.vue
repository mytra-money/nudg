<script setup lang="ts">
import { FlowBuilder, useFlowBuilder } from '@whatsapp/ui/components/FlowBuilder'

const props = defineProps<{
  name: string
}>()

const emit = defineEmits<{
  close: []
  copied: [name: string]
}>()

const controller = useFlowBuilder({
  name: props.name,
  canWrite: true,
})
</script>

<template>
  <FlowBuilder
    :controller="controller"
    @close="emit('close')"
    @copied="emit('copied', $event)"
  />
</template>
