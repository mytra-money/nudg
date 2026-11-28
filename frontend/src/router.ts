import { createRouter, createWebHistory } from 'vue-router'
import { isManager } from '@/stores/desk'
import { canOpenContacts } from '@/utils/directoryAccess'
import AnalyticsView from '@/pages/Analytics.vue'
import AutomationView from '@/pages/Automation.vue'
import CatalogsView from '@/pages/Catalogs.vue'
import ExternalSitesView from '@/pages/ExternalSites.vue'
import ContactsView from '@/pages/Contacts.vue'
import InboxView from '@/pages/Inbox.vue'
import IntegrationsView from '@/pages/Integrations.vue'
import LogsView from '@/pages/Logs.vue'
import MarketingView from '@/pages/Marketing.vue'
import OverviewView from '@/pages/Overview.vue'
import SettingsView from '@/pages/Settings.vue'
import TemplatesView from '@/pages/Templates.vue'

export interface NavItem {
  to: string
  label: string
  icon: string
  managerOnly?: boolean
  /** Hidden unless Role Permission Manager grants read on contacts or recipient lists. */
  requiresDirectory?: boolean
}

export const shellNav: NavItem[] = [
  { to: '/', label: 'Overview', icon: 'lucide-layout-dashboard' },
  { to: '/conversations', label: 'Conversations', icon: 'lucide-inbox' },
  { to: '/contacts', label: 'Contacts', icon: 'lucide-users', requiresDirectory: true },
  { to: '/marketing', label: 'Marketing', icon: 'lucide-megaphone', managerOnly: true },
  { to: '/catalogs', label: 'Catalogs', icon: 'lucide-shopping-bag', managerOnly: true },
  { to: '/template-studio', label: 'Template Studio', icon: 'lucide-layout-template' },
  { to: '/automation', label: 'Automation', icon: 'lucide-bot', managerOnly: true },
  { to: '/analytics', label: 'Analytics', icon: 'lucide-chart-column' },
  { to: '/integrations', label: 'Integrations', icon: 'lucide-plug', managerOnly: true },
  { to: '/settings', label: 'Settings', icon: 'lucide-settings' },
]

declare module 'vue-router' {
  interface RouteMeta {
    title?: string
    desk?: boolean
    manager?: boolean
    parent?: { label: string; to: string }
  }
}

export const router = createRouter({
  history: createWebHistory(import.meta.env.VITE_ROUTER_BASE || '/'),
  routes: [
    { path: '/', component: OverviewView, meta: { title: 'Overview' } },
    { path: '/conversations', component: InboxView, meta: { title: 'Conversations', desk: true } },
    { path: '/contacts', component: ContactsView, meta: { title: 'Contacts', desk: true } },
    { path: '/marketing', component: MarketingView, meta: { title: 'Marketing', desk: true, manager: true } },
    { path: '/catalogs', component: CatalogsView, meta: { title: 'Catalogs', desk: true, manager: true } },
    { path: '/template-studio', component: TemplatesView, meta: { title: 'Template Studio', desk: true } },
    { path: '/automation', component: AutomationView, meta: { title: 'Automation', desk: true, manager: true } },
    { path: '/analytics', component: AnalyticsView, meta: { title: 'Analytics', desk: true } },
    { path: '/integrations', component: IntegrationsView, meta: { title: 'Integrations', desk: true, manager: true } },
    {
      path: '/external-sites',
      component: ExternalSitesView,
      meta: {
        title: 'External Sites',
        desk: true,
        manager: true,
      },
    },
    { path: '/integrations/erpnext', redirect: '/external-sites' },
    { path: '/integrations/catalogs', redirect: '/catalogs' },
    {
      path: '/integrations/logs',
      component: LogsView,
      meta: {
        title: 'Logs',
        desk: true,
        manager: true,
        parent: { label: 'Integrations', to: '/integrations' },
      },
    },
    { path: '/settings', component: SettingsView, meta: { title: 'Settings', desk: true } },
    { path: '/templates', redirect: '/template-studio' },
    { path: '/accounts', redirect: '/integrations' },
    { path: '/logs', redirect: '/integrations/logs' },
  ],
})

router.beforeEach((to) => {
  if (to.path === '/contacts' && !canOpenContacts()) return { path: '/conversations' }
  if (!to.matched.some((record) => record.meta.manager)) return true
  if (isManager.value) return true
  return { path: '/conversations' }
})
