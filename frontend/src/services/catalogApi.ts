import { call } from 'frappe-ui'

export async function listCatalogs(account?: string) {
  return call<any[]>('nudg.desk_api.list_catalogs', { account })
}

export async function listCatalogItems(catalog?: string) {
  return call<any[]>('nudg.desk_api.list_catalog_items', { catalog, status: 'Active' })
}

export async function syncCatalog(catalog: string) {
  return call<any>('nudg.desk_api.sync_catalog', { catalog })
}

export async function createCatalog(payload: {
  catalog_name: string
  whatsapp_account?: string
  description?: string
  status?: string
}) {
  return call<any>('nudg.desk_api.create_catalog', payload)
}

export async function updateCatalog(payload: {
  name: string
  catalog_name?: string
  whatsapp_account?: string
  description?: string
  status?: string
}) {
  return call<any>('nudg.desk_api.update_catalog', payload)
}

export async function createCatalogItem(payload: {
  catalog: string
  item_name: string
  sku?: string
  description?: string
  price?: string | number
  currency?: string
  status?: string
}) {
  return call<any>('nudg.desk_api.create_catalog_item', payload)
}

export async function updateCatalogItem(payload: {
  name: string
  item_name: string
  sku?: string
  description?: string
  price?: string | number
  currency?: string
  status?: string
}) {
  return call<any>('nudg.desk_api.update_catalog_item', payload)
}

export async function sendCatalogProduct(payload: {
  profile: string
  item: string
  body_text?: string
  footer_text?: string
}) {
  return call<any>('nudg.desk_api.send_catalog_product', payload)
}

export async function listQuickReplies(account?: string) {
  return call<any[]>('nudg.desk_api.list_quick_replies', { account })
}

export async function useQuickReply(name: string) {
  return call<{ body: string; title: string; name: string }>('nudg.desk_api.use_quick_reply', { name })
}

export async function listAssignableUsers(txt = '') {
  return call<Array<{ value: string; label: string; description?: string }>>(
    'nudg.desk_api.list_assignable_users',
    { txt },
  )
}

export async function assignConversation(profile: string, user: string) {
  return call<any>('nudg.desk_api.assign_conversation', { profile, user })
}

export async function unassignConversation(profile: string) {
  return call<any>('nudg.desk_api.unassign_conversation', { profile })
}

export async function listCampaigns(account?: string) {
  return call<any[]>('nudg.desk_api.list_campaigns', { account })
}

export async function getCampaign(name: string) {
  return call<any>('nudg.desk_api.get_campaign', { name })
}

export async function runCampaign(name: string) {
  return call<any>('nudg.desk_api.run_campaign', { name })
}

export async function createCampaign(payload: {
  name: string
  campaign_description?: string
  whatsapp_account?: string
  whatsapp_template?: string
}) {
  return call<any>('nudg.desk_api.create_campaign', payload)
}

export async function updateCampaign(payload: {
  name: string
  campaign_name?: string
  campaign_description?: string
  whatsapp_account?: string
  whatsapp_template?: string
}) {
  return call<any>('nudg.desk_api.update_campaign', payload)
}

export async function listAutomationRules(account?: string) {
  return call<any[]>('nudg.desk_api.list_automation_rules', { account })
}

export async function listAutomationRuns(rule?: string) {
  return call<any[]>('nudg.desk_api.list_automation_runs', { rule })
}

export async function createAutomationRule(payload: {
  rule_name: string
  trigger: string
  action: string
  action_reference?: string
  whatsapp_account?: string
  status?: string
}) {
  return call<any>('nudg.desk_api.create_automation_rule', payload)
}

export async function updateAutomationRule(payload: {
  name: string
  rule_name?: string
  trigger?: string
  action?: string
  action_reference?: string
  whatsapp_account?: string
  status?: string
}) {
  return call<any>('nudg.desk_api.update_automation_rule', payload)
}

export async function getAnalytics(account?: string) {
  return call<{ latest: any; refreshing: any; history: any[] }>('nudg.desk_api.get_analytics', {
    account,
  })
}

export async function refreshAnalytics(account?: string) {
  return call<any>('nudg.desk_api.refresh_analytics', { account })
}

export async function updateWhatsappAccount(payload: {
  name: string
  status?: string
  auto_read_receipts?: number
}) {
  return call<any>('nudg.desk_api.update_whatsapp_account', payload)
}

export async function saveQuickReply(payload: {
  title: string
  body: string
  shortcut?: string
  whatsapp_account?: string
  status?: string
  name?: string
}) {
  return call<any>('nudg.desk_api.save_quick_reply', payload)
}

export async function saveWhatsappTemplate(payload: {
  template_label: string
  message: string
  whatsapp_account: string
  template_type?: string
  language?: string
  footer?: string
  header_text?: string
  name?: string
}) {
  return call<any>('nudg.desk_api.save_whatsapp_template', payload)
}

export function deskForm(doctype: string, name?: string) {
  const slug = encodeURIComponent(doctype.toLowerCase().replace(/ /g, '-'))
  if (name) return `/app/${slug}/${encodeURIComponent(name)}`
  return `/app/${slug}/new`
}
