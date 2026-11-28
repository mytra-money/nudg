<script setup lang="ts">
import { ref } from 'vue'
import { FlowList, NewFlowDialog, useFlowList } from '@whatsapp/ui/components/FlowBuilder'
import MetaFlowEditor from '@/components/MetaFlowEditor.vue'

const props = defineProps<{
  account?: string
}>()

const openFlowName = ref<string | null>(null)
const newOpen = ref(false)
const listController = useFlowList({ account: props.account })

function handleClose() {
  openFlowName.value = null
  void listController.load()
}
</script>

<template>
  <div class="min-h-0 flex-1">
    <MetaFlowEditor
      v-if="openFlowName"
      :key="openFlowName"
      :name="openFlowName"
      @close="handleClose"
      @copied="openFlowName = $event"
    />
    <template v-else>
      <FlowList
        :controller="listController"
        :can-write="true"
        @open="openFlowName = $event"
        @new="newOpen = true"
      />
      <NewFlowDialog
        v-model:open="newOpen"
        :account="account || ''"
        :controller="listController"
        @created="openFlowName = $event"
      />
    </template>
  </div>
</template>
