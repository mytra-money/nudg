import type { App } from 'vue'
import { getConfig } from 'frappe-ui'

export default function translationPlugin(app: App) {
  app.config.globalProperties.__ = translate
  window.__ = translate
}

function format(message: string, replace: unknown[]) {
  return message.replace(/{(\d+)}/g, (match, number) => {
    const index = Number(number)
    return typeof replace[index] !== 'undefined' ? String(replace[index]) : match
  })
}

function readTranslatedMessages(): Record<string, string> {
  const value = (getConfig as (key: string) => unknown)('translatedMessages')
  if (!value || typeof value !== 'object') return {}
  return value as Record<string, string>
}

function translate(message: string, replace?: unknown[], context: string | null = null) {
  const translatedMessages = readTranslatedMessages()
  let translatedMessage = ''

  if (context) {
    const key = `${message}:${context}`
    if (translatedMessages[key]) translatedMessage = translatedMessages[key]
  }

  if (!translatedMessage) {
    translatedMessage = translatedMessages[message] || message
  }

  if (!replace || !/{\d+}/.test(message)) return translatedMessage
  return format(translatedMessage, replace)
}
