import { Dialog, type DialogAction, type DialogSize } from 'frappe-ui'
import { h, reactive, ref } from 'vue'

const DIALOG_SIZES = new Set<DialogSize>([
  'xs',
  'sm',
  'md',
  'lg',
  'xl',
  '2xl',
  '3xl',
  '4xl',
  '5xl',
  '6xl',
  '7xl',
])

type DialogOptions = {
  title?: string
  message?: string
  size?: string
  actions?: DialogAction[]
  show?: boolean
}

const dialogs = ref<DialogOptions[]>([])

function dialogSize(size: string | undefined): DialogSize | undefined {
  if (size && DIALOG_SIZES.has(size as DialogSize)) return size as DialogSize
  return undefined
}

export const Dialogs = {
  name: 'Dialogs',
  render() {
    return dialogs.value.map((dialog) => {
      const props: {
        title?: string
        message?: string
        size?: DialogSize
        actions?: DialogAction[]
        open: boolean
        'onUpdate:open': (val: boolean) => void
      } = {
        open: Boolean(dialog.show),
        'onUpdate:open': (val: boolean) => {
          dialog.show = val
        },
      }
      if (dialog.title) props.title = dialog.title
      if (dialog.message) props.message = dialog.message
      const size = dialogSize(dialog.size)
      if (size) props.size = size
      if (dialog.actions) props.actions = dialog.actions
      return h(Dialog, props)
    })
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
