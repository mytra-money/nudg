/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_ROUTER_BASE?: string
}

interface Window {
  csrf_token?: string
  user?: string
  sitename?: string
  site_name?: string
  socketio_port?: number
  is_manager?: boolean
  is_system_manager?: boolean
  roles?: string[]
  directory?: {
    profile?: { read?: boolean; write?: boolean; create?: boolean; delete?: boolean }
    recipient_list?: { read?: boolean; write?: boolean; create?: boolean; delete?: boolean }
  }
  frappe?: {
    session?: { user?: string }
    boot?: {
      user?: { roles?: string[]; name?: string; full_name?: string }
      user_info?: Record<string, { fullname?: string; full_name?: string; image?: string; email?: string }>
    }
    realtime?: {
      on?: (event: string, handler: (data: unknown) => void) => void
      off?: (event: string, handler: (data: unknown) => void) => void
    }
  }
  whatsapp_installed?: boolean
  __?: (message: string, replace?: unknown[], context?: string | null) => string
  integration?: {
    whatsapp_installed: boolean
    doctypes_ready: boolean
    missing_dependencies: string[]
    default_account: string | null
    active_account_count: number | null
    detail: string
  }
}

declare module '@framework/ui'
declare module '@codemirror/lang-json'
declare module '@codemirror/lang-html'
declare module '@codemirror/lang-javascript'
declare module '@codemirror/lang-python'
declare module '@codemirror/lang-sql'
declare module '@codemirror/lang-markdown'
declare module '@codemirror/lang-css'
declare module '@codemirror/lang-sass'
declare module '@codemirror/lang-yaml'
declare module '@codemirror/lang-xml'
