import { Dialog } from 'frappe-ui'
import { h, reactive, ref } from 'vue'

type DialogOptions = {
  title?: string
  message?: string
  size?: string
  actions?: unknown[]
  show?: boolean
  [key: string]: unknown
}

const dialogs = ref<DialogOptions[]>([])

export const Dialogs = {
  name: 'Dialogs',
  render() {
    return dialogs.value.map((dialog) =>
      h(Dialog, {
        title: dialog.title,
        message: dialog.message,
        size: dialog.size,
        actions: dialog.actions,
        open: dialog.show,
        'onUpdate:open': (val: boolean) => {
          dialog.show = val
        },
      }),
    )
  },
}

export function createDialog(options: DialogOptions) {
  const dialog = reactive({ ...options, show: true })
  dialogs.value.push(dialog)
  return dialog
}

export function isDialogOpen() {
  return dialogs.value.some((dialog) => dialog.show)
}
