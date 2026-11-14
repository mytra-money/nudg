import { createRouter, createWebHistory } from 'vue-router'
import { isManager } from '@/desk'
import AnalyticsView from '@/components/AnalyticsView.vue'
import AutomationView from '@/components/AutomationView.vue'
import CatalogsView from '@/components/CatalogsView.vue'
import InboxView from '@/components/InboxView.vue'
import IntegrationsView from '@/components/IntegrationsView.vue'
import LogsView from '@/components/LogsView.vue'
import MarketingView from '@/components/MarketingView.vue'
import OverviewView from '@/components/OverviewView.vue'
import PlaceholderView from '@/components/PlaceholderView.vue'
import SettingsView from '@/components/SettingsView.vue'
import TemplatesView from '@/components/TemplatesView.vue'

export interface NavItem {
  to: string
  label: string
  icon: string
  managerOnly?: boolean
}

export const shellNav: NavItem[] = [
  { to: '/', label: 'Overview', icon: 'lucide-layout-dashboard' },
  { to: '/conversations', label: 'Conversations', icon: 'lucide-inbox' },
  { to: '/marketing', label: 'Marketing', icon: 'lucide-megaphone', managerOnly: true },
  { to: '/template-studio', label: 'Template Studio', icon: 'lucide-layout-template' },
  { to: '/automation', label: 'Automation', icon: 'lucide-workflow', managerOnly: true },
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
    { path: '/marketing', component: MarketingView, meta: { title: 'Marketing', desk: true, manager: true } },
    { path: '/template-studio', component: TemplatesView, meta: { title: 'Template Studio', desk: true } },
    { path: '/automation', component: AutomationView, meta: { title: 'Automation', desk: true, manager: true } },
    { path: '/analytics', component: AnalyticsView, meta: { title: 'Analytics', desk: true } },
    { path: '/integrations', component: IntegrationsView, meta: { title: 'Integrations', desk: true, manager: true } },
    {
      path: '/integrations/catalogs',
      component: CatalogsView,
      meta: {
        title: 'Catalogs',
        desk: true,
        manager: true,
        parent: { label: 'Integrations', to: '/integrations' },
      },
    },
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
    { path: '/catalogs', redirect: '/integrations/catalogs' },
  ],
})

router.beforeEach((to) => {
  if (!to.matched.some((record) => record.meta.manager)) return true
  if (isManager.value) return true
  return { path: '/conversations' }
})
