<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Badge, Button, Dialog, toast } from 'frappe-ui'
import EmptyState from '@/components/EmptyState.vue'
import ErrorState from '@/components/ErrorState.vue'
import LoadingState from '@/components/LoadingState.vue'
import { errorText } from '@/utils/format'
import { useDesk } from '@/stores/desk'
import {
  createCatalog,
  createCatalogItem,
  deleteCatalog,
  deleteCatalogItem,
  listCatalogItems,
  listCatalogs,
  sendCatalogProduct,
  syncCatalog,
  updateCatalog,
  updateCatalogItem,
} from '@/services/catalogApi'

const desk = useDesk()

const loading = ref(true)
const error = ref<string | null>(null)
const catalogs = ref<any[]>([])
const items = ref<any[]>([])
const selectedCatalogName = ref<string | null>(null)
const busy = ref(false)
const searchQuery = ref('')
const itemSearchQuery = ref('')
const itemStatusFilter = ref<'all' | 'Active' | 'Inactive'>('all')

// Interactive SPM Modal State
const showSendModal = ref(false)
const selectedItemToSend = ref<any | null>(null)
const recipientProfile = ref('')
const customBodyText = ref('')
const customFooterText = ref('Tap below to view details in WhatsApp')
const isSendingProduct = ref(false)

// Sample Demo Data Fallbacks
const sampleCatalogs: any[] = [
  {
    name: 'CAT-SPICE-01',
    catalog_name: 'Sundarban Signature Spices',
    whatsapp_account: 'Sundarban Sales',
    status: 'Active',
    meta_catalog_id: 'meta_cat_8829104812',
    sync_status: 'Error',
    sync_error:
      'Meta Commerce Catalog sync is not enabled in this build. Catalog data is stored on this site only.',
    description: 'Single-origin spices, hand-harvested green cardamom, Tellicherry pepper, and saffron from organic reserves.',
    modified: new Date(Date.now() - 3600_000 * 2).toISOString(),
  },
  {
    name: 'CAT-GIFT-02',
    catalog_name: 'Festive Hampers & Spice Trunks',
    whatsapp_account: 'Sundarban Dispatch',
    status: 'Active',
    meta_catalog_id: 'meta_cat_9931849102',
    sync_status: 'Error',
    sync_error:
      'Meta Commerce Catalog sync is not enabled in this build. Catalog data is stored on this site only.',
    description: 'Curated wooden gift boxes, handcrafted brass spice boxes, and festive corporate allocations.',
    modified: new Date(Date.now() - 3600_000 * 24).toISOString(),
  },
]

const sampleItemsByCatalog: Record<string, any[]> = {
  'CAT-SPICE-01': [
    {
      name: 'ITEM-001',
      catalog: 'CAT-SPICE-01',
      item_name: 'Royal Green Cardamom (500g)',
      sku: 'SPI-CRD-01',
      description: 'Extra-bold 8mm green cardamom pods, shade-dried to lock in essential oils and pungent aroma.',
      price: 850,
      currency: 'INR',
      image: '',
      meta_retailer_id: 'ret_crd_01',
      status: 'Active',
      sort_order: 1,
    },
    {
      name: 'ITEM-002',
      catalog: 'CAT-SPICE-01',
      item_name: 'Tellicherry Black Pepper (250g)',
      sku: 'SPI-PEP-02',
      description: 'Sun-dried jumbo Tellicherry peppercorns from ancient vines with rich heat and citrus undertones.',
      price: 420,
      currency: 'INR',
      image: '',
      meta_retailer_id: 'ret_pep_02',
      status: 'Active',
      sort_order: 2,
    },
    {
      name: 'ITEM-003',
      catalog: 'CAT-SPICE-01',
      item_name: 'Organic Kashmiri Mongra Saffron (1g)',
      sku: 'SPI-SAF-03',
      description: 'Grade-A pure red stigma threads with intense floral aroma and natural crimson color release.',
      price: 650,
      currency: 'INR',
      image: '',
      meta_retailer_id: 'ret_saf_03',
      status: 'Active',
      sort_order: 3,
    },
    {
      name: 'ITEM-004',
      catalog: 'CAT-SPICE-01',
      item_name: 'Ceylon Sweet Cinnamon Quills (200g)',
      sku: 'SPI-CIN-04',
      description: 'Delicate paper-thin layered true cinnamon quills with soft floral sweetness and zero bitter cassia.',
      price: 310,
      currency: 'INR',
      image: '',
      meta_retailer_id: 'ret_cin_04',
      status: 'Active',
      sort_order: 4,
    },
  ],
  'CAT-GIFT-02': [
    {
      name: 'ITEM-005',
      catalog: 'CAT-GIFT-02',
      item_name: 'Artisanal Spice Trunk (6 Jars Assortment)',
      sku: 'GFT-TRK-01',
      description: 'Handcrafted teak wood chest holding 6 signature reserve whole spices with brass spoon.',
      price: 2400,
      currency: 'INR',
      image: '',
      meta_retailer_id: 'ret_trk_01',
      status: 'Active',
      sort_order: 1,
    },
    {
      name: 'ITEM-006',
      catalog: 'CAT-GIFT-02',
      item_name: 'Heritage Brass Spice Dabba (7 Compartments)',
      sku: 'GFT-DBA-02',
      description: 'Traditional heavy-gauge hammered brass masala box with airtight lid and master measure.',
      price: 1750,
      currency: 'INR',
      image: '',
      meta_retailer_id: 'ret_dba_02',
      status: 'Active',
      sort_order: 2,
    },
  ],
}

function showToast(message: string, isError = false) {
  if (isError) {
    toast.error(message)
  } else {
    toast.success(message)
  }
}

const catalogEditorOpen = ref(false)
const catalogEditorMode = ref<'create' | 'edit'>('create')
const editingCatalogName = ref('')
const catalogForm = ref({ catalog_name: '', whatsapp_account: '', description: '', status: 'Draft' })
const itemEditorOpen = ref(false)
const itemEditorMode = ref<'create' | 'edit'>('create')
const editingItemName = ref('')
const itemForm = ref({ item_name: '', sku: '', description: '', price: '', currency: 'INR', status: 'Active', image: '' })
const savingCatalog = ref(false)

const accountOptions = computed(() => desk.inbox.value?.accounts || [])

function startCatalog(existing?: any) {
  catalogEditorMode.value = existing ? 'edit' : 'create'
  editingCatalogName.value = existing?.name || ''
  catalogForm.value = {
    catalog_name: existing?.catalog_name || '',
    whatsapp_account: existing?.whatsapp_account || accountOptions.value[0]?.name || '',
    description: existing?.description || '',
    status: existing?.status || 'Draft',
  }
  catalogEditorOpen.value = true
}

function startItem(existing?: any) {
  if (!selectedCatalogName.value && !existing) {
    showToast('Choose a catalog first.')
    return
  }
  itemEditorMode.value = existing ? 'edit' : 'create'
  editingItemName.value = existing?.name || ''
  itemForm.value = {
    item_name: existing?.item_name || '',
    sku: existing?.sku || '',
    description: existing?.description || '',
    price: existing?.price != null ? String(existing.price) : '',
    currency: existing?.currency || 'INR',
    status: existing?.status || 'Active',
    image: existing?.image || '',
  }
  itemEditorOpen.value = true
}

async function saveCatalogForm() {
  const catalogName = catalogForm.value.catalog_name.trim()
  if (!catalogName) {
    showToast('Catalog name is required.', true)
    return
  }
  savingCatalog.value = true
  const isLive = Boolean(window.csrf_token)
  try {
    if (!isLive) {
      if (catalogEditorMode.value === 'edit') {
        const index = catalogs.value.findIndex((row) => row.name === editingCatalogName.value)
        if (index >= 0) {
          catalogs.value[index] = {
            ...catalogs.value[index],
            name: catalogName,
            catalog_name: catalogName,
            whatsapp_account: catalogForm.value.whatsapp_account,
            description: catalogForm.value.description.trim(),
            status: catalogForm.value.status,
          }
        }
        selectedCatalogName.value = catalogName
      } else {
        catalogs.value = [
          {
            name: catalogName,
            catalog_name: catalogName,
            whatsapp_account: catalogForm.value.whatsapp_account,
            description: catalogForm.value.description.trim(),
            status: catalogForm.value.status,
            sync_status: 'Not Synced',
          },
          ...catalogs.value,
        ]
        selectedCatalogName.value = catalogName
        items.value = []
      }
      catalogEditorOpen.value = false
      showToast(catalogEditorMode.value === 'edit' ? 'Catalog updated' : 'Catalog created')
      return
    }
    const saved =
      catalogEditorMode.value === 'edit'
        ? await updateCatalog({
            name: editingCatalogName.value,
            catalog_name: catalogName,
            whatsapp_account: catalogForm.value.whatsapp_account || undefined,
            description: catalogForm.value.description.trim(),
            status: catalogForm.value.status,
          })
        : await createCatalog({
            catalog_name: catalogName,
            whatsapp_account: catalogForm.value.whatsapp_account || undefined,
            description: catalogForm.value.description.trim(),
            status: catalogForm.value.status,
          })
    catalogEditorOpen.value = false
    showToast(catalogEditorMode.value === 'edit' ? 'Catalog updated' : 'Catalog created')
    selectedCatalogName.value = saved?.name || catalogName
    await load()
  } catch (caught) {
    showToast(errorText(caught), true)
  } finally {
    savingCatalog.value = false
  }
}

async function removeCatalog() {
  if (catalogEditorMode.value !== 'edit' || !editingCatalogName.value) return
  if (!window.confirm(`Delete catalog “${catalogForm.value.catalog_name || editingCatalogName.value}” and its items?`)) return
  savingCatalog.value = true
  const isLive = Boolean(window.csrf_token)
  try {
    if (isLive) await deleteCatalog(editingCatalogName.value)
    catalogs.value = catalogs.value.filter((row) => row.name !== editingCatalogName.value)
    if (selectedCatalogName.value === editingCatalogName.value) {
      selectedCatalogName.value = catalogs.value[0]?.name || null
      items.value = []
    }
    catalogEditorOpen.value = false
    showToast('Catalog deleted')
  } catch (caught) {
    showToast(errorText(caught), true)
  } finally {
    savingCatalog.value = false
  }
}

async function removeItem() {
  if (itemEditorMode.value !== 'edit' || !editingItemName.value) return
  if (!window.confirm(`Delete item “${itemForm.value.item_name || editingItemName.value}”?`)) return
  savingCatalog.value = true
  const isLive = Boolean(window.csrf_token)
  try {
    if (isLive) await deleteCatalogItem(editingItemName.value)
    items.value = items.value.filter((row) => row.name !== editingItemName.value)
    itemEditorOpen.value = false
    showToast('Item deleted')
  } catch (caught) {
    showToast(errorText(caught), true)
  } finally {
    savingCatalog.value = false
  }
}

async function saveItemForm() {
  const itemName = itemForm.value.item_name.trim()
  if (!itemName) {
    showToast('Item name is required.', true)
    return
  }
  const catalogName = selectedCatalogName.value
  if (!catalogName) {
    showToast('Choose a catalog first.', true)
    return
  }
  savingCatalog.value = true
  const isLive = Boolean(window.csrf_token)
  try {
    if (!isLive) {
      const row = {
        name: itemEditorMode.value === 'edit' ? editingItemName.value : `item-${Date.now()}`,
        catalog: catalogName,
        item_name: itemName,
        sku: itemForm.value.sku.trim(),
        description: itemForm.value.description.trim(),
        price: Number(itemForm.value.price || 0),
        currency: itemForm.value.currency || 'INR',
        status: itemForm.value.status,
        image: itemForm.value.image.trim(),
      }
      const bucket = sampleItemsByCatalog[catalogName] || (sampleItemsByCatalog[catalogName] = [])
      if (itemEditorMode.value === 'edit') {
        const index = bucket.findIndex((item) => item.name === editingItemName.value)
        if (index >= 0) bucket[index] = { ...bucket[index], ...row }
      } else {
        bucket.unshift(row)
      }
      items.value = [...bucket]
      itemEditorOpen.value = false
      showToast(itemEditorMode.value === 'edit' ? 'Item updated' : 'Item added')
      return
    }
    if (itemEditorMode.value === 'edit') {
      await updateCatalogItem({
        name: editingItemName.value,
        item_name: itemName,
        sku: itemForm.value.sku.trim(),
        description: itemForm.value.description.trim(),
        price: itemForm.value.price,
        currency: itemForm.value.currency,
        status: itemForm.value.status,
        image: itemForm.value.image.trim(),
      })
    } else {
      await createCatalogItem({
        catalog: catalogName,
        item_name: itemName,
        sku: itemForm.value.sku.trim(),
        description: itemForm.value.description.trim(),
        price: itemForm.value.price,
        currency: itemForm.value.currency,
        status: itemForm.value.status,
        image: itemForm.value.image.trim(),
      })
    }
    itemEditorOpen.value = false
    showToast(itemEditorMode.value === 'edit' ? 'Item updated' : 'Item added')
    await open(catalogName)
  } catch (caught) {
    showToast(errorText(caught), true)
  } finally {
    savingCatalog.value = false
  }
}

async function load() {
  loading.value = true
  error.value = null
  const isLive = Boolean(window.csrf_token)
  try {
    if (!isLive) {
      catalogs.value = sampleCatalogs
      if (!selectedCatalogName.value && catalogs.value.length) {
        selectedCatalogName.value = catalogs.value[0].name
      }
      if (selectedCatalogName.value) {
        items.value = sampleItemsByCatalog[selectedCatalogName.value] || []
      }
      return
    }
    const result = await listCatalogs()
    catalogs.value = result || []
    if (!selectedCatalogName.value && catalogs.value.length) {
      selectedCatalogName.value = catalogs.value[0].name
    }
    if (selectedCatalogName.value) {
      await open(selectedCatalogName.value)
    }
  } catch (caught) {
    if (!isLive) {
      catalogs.value = sampleCatalogs
      if (catalogs.value.length) {
        selectedCatalogName.value = catalogs.value[0].name
        if (selectedCatalogName.value) {
          items.value = sampleItemsByCatalog[selectedCatalogName.value] || []
        }
      }
    } else {
      error.value = errorText(caught)
    }
  } finally {
    loading.value = false
  }
}

async function open(name: string) {
  selectedCatalogName.value = name
  const isLive = Boolean(window.csrf_token)
  try {
    if (!isLive) {
      items.value = sampleItemsByCatalog[name] || []
      return
    }
    const result = await listCatalogItems(name)
    items.value = result || []
  } catch (caught) {
    if (!isLive) {
      items.value = sampleItemsByCatalog[name] || []
    } else {
      showToast(errorText(caught))
    }
  }
}

async function sync(name: string) {
  busy.value = true
  const isLive = Boolean(window.csrf_token)
  try {
    if (!isLive) {
      const target = catalogs.value.find((c) => c.name === name)
      const message =
        'Meta Commerce Catalog sync is not enabled in this build. Catalog data is stored on this site only.'
      if (target) {
        target.sync_status = 'Error'
        target.sync_error = message
      }
      showToast(message, true)
      return
    }
    const result = await syncCatalog(name)
    if (result.sync_error || result.sync_status === 'Error') {
      showToast(result.sync_error || 'Catalog sync is not available.', true)
    } else {
      showToast(result.sync_status || 'Sync requested successfully.')
    }
    await load()
    if (selectedCatalogName.value === name) await open(name)
  } catch (caught) {
    showToast(errorText(caught))
  } finally {
    busy.value = false
  }
}

function openSendModal(item: any) {
  selectedItemToSend.value = item
  customBodyText.value = `Hello! Check out our ${item.item_name}. It's in stock and ready to ship:`
  const defaultConv = desk.inbox.value?.conversations?.[0]
  recipientProfile.value = defaultConv?.profile.name || ''
  showSendModal.value = true
}

async function handleSendProduct() {
  if (!selectedItemToSend.value || !recipientProfile.value) {
    showToast('Please select a recipient to send this product message to.')
    return
  }
  isSendingProduct.value = true
  const isLive = Boolean(window.csrf_token)
  try {
    if (!isLive) {
      await new Promise((resolve) => setTimeout(resolve, 500))
      showToast(`Product "${selectedItemToSend.value.item_name}" sent to customer!`)
      showSendModal.value = false
      return
    }
    await sendCatalogProduct({
      profile: recipientProfile.value,
      item: selectedItemToSend.value.name,
      body_text: customBodyText.value,
      footer_text: customFooterText.value,
    })
    showToast(`Single-Product Message dispatched successfully!`)
    showSendModal.value = false
  } catch (caught) {
    showToast(errorText(caught))
  } finally {
    isSendingProduct.value = false
  }
}

const selectedCatalog = computed(() => {
  return catalogs.value.find((c) => c.name === selectedCatalogName.value) || null
})

const syncStatusLabel = computed(() => selectedCatalog.value?.sync_status || 'Not synced')
const syncStatusDetail = computed(() => {
  if (selectedCatalog.value?.sync_error) return selectedCatalog.value.sync_error
  return 'Catalog data is stored on this site. Meta catalog import is not available.'
})

const filteredCatalogs = computed(() => {
  if (!searchQuery.value) return catalogs.value
  const query = searchQuery.value.toLowerCase()
  return catalogs.value.filter(
    (c) =>
      c.catalog_name?.toLowerCase().includes(query) ||
      c.name?.toLowerCase().includes(query) ||
      c.whatsapp_account?.toLowerCase().includes(query),
  )
})

const filteredItems = computed(() => {
  return items.value.filter((item) => {
    const matchesSearch =
      !itemSearchQuery.value ||
      item.item_name?.toLowerCase().includes(itemSearchQuery.value.toLowerCase()) ||
      item.sku?.toLowerCase().includes(itemSearchQuery.value.toLowerCase())
    if (!matchesSearch) return false

    if (itemStatusFilter.value === 'all') return true
    return item.status === itemStatusFilter.value
  })
})

const totalProductsCount = computed(() => {
  return items.value.length
})

function formatCurrency(price?: number, currency = 'INR') {
  if (price === undefined || price === null) return ''
  if (currency === 'INR') {
    return new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' }).format(price)
  }
  return `${currency} ${price.toFixed(2)}`
}

onMounted(() => {
  desk.load()
  load()
})
</script>

<template>
  <div class="flex h-full min-h-0 flex-col bg-surface-gray-2/60">
    <!-- Main Content Area -->
    <div class="flex min-h-0 flex-1 flex-col overflow-y-auto px-4 py-6 sm:px-8">
      <!-- Page Header & Action Bar -->
      <div class="flex flex-col gap-4 border-b border-outline-gray-2 pb-6 md:flex-row md:items-start md:justify-between">
        <div class="flex min-w-0 items-start gap-2.5">
          <div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[#075E54]/10 text-[#075E54]">
            <svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 11V7a4 4 0 00-8 0v4M5 9h14l1 12H4L5 9z" />
            </svg>
          </div>
          <div class="min-w-0">
            <div class="flex flex-wrap items-center gap-2">
              <h1 class="text-2xl font-bold tracking-tight text-ink-gray-9">WhatsApp Product Catalogs</h1>
              <span class="inline-flex h-6 items-center rounded-full bg-amber-50 px-2.5 text-xs font-medium text-amber-800 ring-1 ring-inset ring-amber-600/20">
                Stored on this site
              </span>
            </div>
            <p class="mt-1 text-xs text-ink-gray-6 sm:text-sm">
              Add products here and send them in a chat. Meta catalog import is not available in this build.
            </p>
          </div>
        </div>

        <!-- Header Actions -->
        <div class="flex shrink-0 flex-wrap items-center gap-2 md:justify-end">
          <button
            type="button"
            @click="load"
            :disabled="loading"
            class="inline-flex h-9 items-center gap-1.5 rounded-lg border border-outline-gray-2 bg-white px-3 text-xs font-semibold text-ink-gray-8 shadow-2xs hover:bg-surface-gray-2 disabled:opacity-50"
          >
            <svg
              class="h-4 w-4 text-ink-gray-6"
              :class="{ 'animate-spin': loading }"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.03 0 01-15.357-2m15.357 2H15" />
            </svg>
            <span>Refresh</span>
          </button>

          <button
            type="button"
            @click="startCatalog()"
            class="inline-flex h-9 items-center gap-1.5 rounded-lg border border-outline-gray-2 bg-white px-3 text-xs font-semibold text-ink-gray-8 shadow-2xs hover:bg-surface-gray-2"
          >
            <svg class="h-4 w-4 text-[#075E54]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
            </svg>
            <span>New Catalog</span>
          </button>

          <button
            type="button"
            @click="startItem()"
            class="inline-flex h-9 items-center gap-1.5 rounded-lg bg-[#075E54] px-3 text-xs font-semibold text-white hover:bg-[#128C7E]"
          >
            <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
            </svg>
            <span>Add Catalog Item</span>
          </button>
        </div>
      </div>

      <!-- KPI Metrics Ribbon (4 Cards) -->
      <div class="mt-6 grid grid-cols-1 items-stretch gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <div class="flex h-full flex-col rounded-xl border border-outline-gray-2 bg-white p-4 shadow-2xs">
          <div class="flex h-10 items-start justify-between gap-2">
            <span class="text-xs font-medium uppercase leading-4 tracking-wider text-ink-gray-6">Catalogs</span>
            <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-[#075E54]/10 text-[#075E54]">
              <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
              </svg>
            </div>
          </div>
          <div class="mt-3 flex min-h-8 items-end gap-2">
            <span class="text-2xl font-bold leading-none text-ink-gray-9">{{ catalogs.length }}</span>
            <span class="text-xs text-ink-gray-5">collections</span>
          </div>
          <p class="mt-2 line-clamp-2 text-xs text-ink-gray-6">
            {{ selectedCatalog ? 'Selected: ' + selectedCatalog.catalog_name : 'No catalog selected' }}
          </p>
        </div>

        <div class="flex h-full flex-col rounded-xl border border-outline-gray-2 bg-white p-4 shadow-2xs">
          <div class="flex h-10 items-start justify-between gap-2">
            <span class="text-xs font-medium uppercase leading-4 tracking-wider text-ink-gray-6">Products</span>
            <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-[#25D366]/10 text-[#075E54]">
              <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z" />
              </svg>
            </div>
          </div>
          <div class="mt-3 flex min-h-8 items-end gap-2">
            <span class="text-2xl font-bold leading-none text-ink-gray-9">{{ totalProductsCount }}</span>
            <span class="text-xs text-ink-gray-5">products</span>
          </div>
          <p class="mt-2 line-clamp-2 text-xs text-ink-gray-6">In the catalog selected on the left</p>
        </div>

        <div class="flex h-full flex-col rounded-xl border border-outline-gray-2 bg-white p-4 shadow-2xs">
          <div class="flex h-10 items-start justify-between gap-2">
            <span class="text-xs font-medium uppercase leading-4 tracking-wider text-ink-gray-6">Sync</span>
            <div
              class="flex h-8 w-8 items-center justify-center rounded-lg"
              :class="syncStatusLabel === 'Error' ? 'bg-red-50 text-red-600' : 'bg-amber-50 text-amber-700'"
            >
              <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01M10.29 3.86l-8.02 14A1 1 0 003.14 19h17.72a1 1 0 00.87-1.5l-8.02-14a1 1 0 00-1.74 0z" />
              </svg>
            </div>
          </div>
          <div class="mt-3 flex min-h-8 items-end gap-1.5">
            <span
              class="mb-1 h-2 w-2 shrink-0 rounded-full"
              :class="syncStatusLabel === 'Error' ? 'bg-red-500' : syncStatusLabel === 'Synced' ? 'bg-emerald-500' : 'bg-amber-500'"
            ></span>
            <span class="text-2xl font-bold leading-none text-ink-gray-9">{{ syncStatusLabel }}</span>
          </div>
          <p class="mt-2 line-clamp-2 text-xs text-ink-gray-6">{{ syncStatusDetail }}</p>
        </div>

        <div class="flex h-full flex-col rounded-xl border border-outline-gray-2 bg-white p-4 shadow-2xs">
          <div class="flex h-10 items-start justify-between gap-2">
            <span class="text-xs font-medium uppercase leading-4 tracking-wider text-ink-gray-6">Send</span>
            <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-50 text-blue-600">
              <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 18h.01M8 21h8a2 2 0 002-2V5a2 2 0 00-2-2H8a2 2 0 00-2 2v14a2 2 0 002 2z" />
              </svg>
            </div>
          </div>
          <div class="mt-3 flex min-h-8 items-end">
            <span class="text-2xl font-bold leading-none text-ink-gray-9">In chat</span>
          </div>
          <p class="mt-2 line-clamp-2 text-xs text-ink-gray-6">Send one product or a list from a conversation</p>
        </div>
      </div>

      <!-- State Containers (Loading / Error / Empty) -->
      <LoadingState v-if="loading" label="Loading product catalogs…" />
      <ErrorState v-else-if="error" :message="error" allow-retry @retry="load" />
      <EmptyState
        v-else-if="!catalogs.length"
        title="No Catalogs Configured"
        description="Create a catalog on this site. You can send its products in a conversation. Meta catalog import is not available yet."
      />

      <!-- Master-Detail Layout -->
      <div v-else class="nudg-split mt-6 grid min-h-0 flex-1 items-start gap-4 lg:grid-cols-[minmax(16rem,20rem)_minmax(0,1fr)]">
        <div class="flex flex-col rounded-xl border border-outline-gray-2 bg-white shadow-2xs">
          <div class="border-b border-outline-gray-2 p-4">
            <div class="flex h-9 items-center justify-between gap-3">
              <h2 class="text-sm font-semibold text-ink-gray-9">Collections ({{ catalogs.length }})</h2>
              <button
                type="button"
                class="inline-flex h-8 items-center rounded-lg px-2 text-xs font-semibold text-[#075E54] hover:bg-[#075E54]/10"
                @click="startCatalog()"
              >
                New
              </button>
            </div>
            <div class="relative mt-3">
              <svg class="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-gray-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
              <input
                v-model="searchQuery"
                type="text"
                placeholder="Search collections..."
                class="h-9 w-full rounded-lg border border-outline-gray-2 bg-surface-gray-2/50 pl-8 pr-3 text-xs text-ink-gray-9 placeholder:text-ink-gray-4 focus:border-[#128C7E] focus:outline-none focus:ring-1 focus:ring-[#128C7E]"
              />
            </div>
          </div>

          <div class="min-h-0 flex-1 divide-y divide-outline-gray-1 overflow-y-auto">
            <button
              v-for="cat in filteredCatalogs"
              :key="cat.name"
              type="button"
              class="flex w-full flex-col gap-1.5 border-l-4 px-4 py-3 text-left hover:bg-surface-gray-2/50"
              :class="selectedCatalogName === cat.name ? 'border-l-[#128C7E] bg-[#075E54]/5' : 'border-l-transparent'"
              @click="open(cat.name)"
            >
              <div class="flex items-center justify-between gap-2">
                <span class="min-w-0 truncate text-sm font-semibold text-ink-gray-9">{{ cat.catalog_name }}</span>
                <span
                  class="shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium"
                  :class="
                    cat.sync_status === 'Synced'
                      ? 'bg-emerald-50 text-emerald-700 ring-1 ring-inset ring-emerald-600/20'
                      : cat.sync_status === 'Error'
                      ? 'bg-red-50 text-red-700'
                      : 'bg-amber-50 text-amber-700'
                  "
                >
                  {{ cat.sync_status || 'Pending' }}
                </span>
              </div>
              <p class="line-clamp-2 text-xs leading-5 text-ink-gray-6">{{ cat.description || 'No catalog description provided.' }}</p>
              <div class="flex items-center justify-between gap-3 text-[11px] text-ink-gray-5">
                <span class="min-w-0 truncate">{{ cat.whatsapp_account || 'No account' }}</span>
                <span class="shrink-0 font-mono">{{ cat.name }}</span>
              </div>
            </button>
          </div>
        </div>

        <!-- Detail Column: Catalog Products & Actions -->
        <div v-if="selectedCatalog" class="flex min-w-0 flex-col rounded-xl border border-outline-gray-2 bg-white p-4 shadow-2xs sm:p-5">
          <div class="flex flex-wrap items-center gap-2">
            <h2 class="min-w-0 truncate text-lg font-bold text-ink-gray-9">{{ selectedCatalog.catalog_name }}</h2>
            <span
              class="inline-flex h-6 shrink-0 items-center rounded-full px-2.5 text-xs font-medium"
              :class="selectedCatalog.status === 'Active' ? 'bg-emerald-50 text-emerald-700' : 'bg-surface-gray-2 text-ink-gray-6'"
            >
              {{ selectedCatalog.status }}
            </span>
          </div>
          <p class="mt-1 text-xs leading-5 text-ink-gray-6">{{ selectedCatalog.description || 'No description' }}</p>
          <p v-if="selectedCatalog.sync_error" class="mt-2 text-sm text-red-700" role="alert">
            {{ selectedCatalog.sync_error }}
          </p>
          <div class="mt-3 flex flex-wrap items-center gap-2 text-xs">
            <span class="inline-flex h-7 items-center rounded-md bg-surface-gray-2 px-2 font-mono text-ink-gray-7">
              Meta ID {{ selectedCatalog.meta_catalog_id || 'Not set' }}
            </span>
            <span class="inline-flex h-7 items-center rounded-md bg-surface-gray-2 px-2 text-ink-gray-7">
              {{ selectedCatalog.whatsapp_account || 'No account' }}
            </span>
          </div>
          <div class="mt-3 flex flex-wrap items-center gap-2 border-b border-outline-gray-2 pb-4">
            <button
              type="button"
              :disabled="busy"
              class="inline-flex h-9 items-center gap-1.5 rounded-lg border border-outline-gray-2 bg-white px-3 text-xs font-semibold text-ink-gray-8 hover:bg-surface-gray-2 disabled:opacity-50"
              @click="sync(selectedCatalog.name)"
            >
                <svg
                  class="h-4 w-4 text-[#128C7E]"
                  :class="{ 'animate-spin': busy }"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.03 0 01-15.357-2m15.357 2H15" />
                </svg>
                <span>{{ busy ? 'Syncing...' : 'Sync catalog' }}</span>
              </button>

            <button
              type="button"
              class="inline-flex h-9 items-center rounded-lg border border-outline-gray-2 bg-white px-3 text-xs font-semibold text-ink-gray-8 hover:bg-surface-gray-2"
              @click="startCatalog(selectedCatalog)"
            >
              Edit catalog
            </button>
            <button
              type="button"
              class="inline-flex h-9 items-center gap-1.5 rounded-lg bg-[#075E54] px-3 text-xs font-semibold text-white hover:bg-[#128C7E]"
              @click="startItem()"
            >
                <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
                </svg>
                <span>New Item</span>
              </button>
          </div>

          <!-- Items Filter & Search -->
          <div class="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div class="relative w-full sm:max-w-xs sm:flex-1">
              <svg class="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-gray-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
              <input
                v-model="itemSearchQuery"
                type="text"
                placeholder="Search products or SKU..."
                class="h-9 w-full rounded-lg border border-outline-gray-2 bg-white pl-8 pr-3 text-xs text-ink-gray-9 placeholder:text-ink-gray-4 focus:border-[#128C7E] focus:outline-none focus:ring-1 focus:ring-[#128C7E]"
              />
            </div>
            <div class="flex h-9 shrink-0 items-center rounded-lg border border-outline-gray-2 bg-white p-0.5">
              <button
                type="button"
                class="h-8 rounded-md px-3 text-xs font-medium"
                :class="itemStatusFilter === 'all' ? 'bg-[#075E54] text-white' : 'text-ink-gray-6 hover:text-ink-gray-9'"
                @click="itemStatusFilter = 'all'"
              >
                All ({{ items.length }})
              </button>
              <button
                type="button"
                class="h-8 rounded-md px-3 text-xs font-medium"
                :class="itemStatusFilter === 'Active' ? 'bg-[#075E54] text-white' : 'text-ink-gray-6 hover:text-ink-gray-9'"
                @click="itemStatusFilter = 'Active'"
              >
                Active
              </button>
              <button
                type="button"
                class="h-8 rounded-md px-3 text-xs font-medium"
                :class="itemStatusFilter === 'Inactive' ? 'bg-[#075E54] text-white' : 'text-ink-gray-6 hover:text-ink-gray-9'"
                @click="itemStatusFilter = 'Inactive'"
              >
                Inactive
              </button>
            </div>
          </div>

          <div v-if="filteredItems.length > 0" class="mt-4 space-y-3">
            <article
              v-for="item in filteredItems"
              :key="item.name"
              class="rounded-xl border border-outline-gray-2 bg-white p-4"
            >
              <div class="flex items-start gap-3">
                <div class="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-[#25D366]/20 bg-[#25D366]/10 text-[#075E54]">
                  <svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
                  </svg>
                </div>
                <div class="min-w-0 flex-1">
                  <div class="flex items-start justify-between gap-3">
                    <h3 class="min-w-0 truncate text-sm font-semibold text-ink-gray-9">{{ item.item_name }}</h3>
                    <span class="shrink-0 text-sm font-semibold tabular-nums text-emerald-700">
                      {{ formatCurrency(item.price, item.currency) }}
                    </span>
                  </div>
                  <div class="mt-1 flex flex-wrap items-center gap-2">
                    <span class="rounded bg-surface-gray-2 px-1.5 py-0.5 font-mono text-[11px] text-ink-gray-6">{{ item.sku || 'No SKU' }}</span>
                    <Badge
                      :variant="item.status === 'Active' ? 'subtle' : 'outline'"
                      :theme="item.status === 'Active' ? 'green' : 'gray'"
                      size="sm"
                    >
                      {{ item.status }}
                    </Badge>
                  </div>
                  <p class="mt-2 line-clamp-2 text-xs leading-5 text-ink-gray-6">
                    {{ item.description || 'No product description provided.' }}
                  </p>
                </div>
              </div>
              <div class="mt-3 flex items-center justify-end gap-2 border-t border-outline-gray-1 pt-3">
                <Button variant="subtle" size="sm" icon-left="lucide-pencil" label="Edit" @click="startItem(item)" />
                <Button
                  variant="solid"
                  size="sm"
                  class="bg-[#075E54] text-white hover:bg-[#128C7E]"
                  icon-left="lucide-send"
                  label="Send to Customer"
                  @click="openSendModal(item)"
                />
              </div>
            </article>
          </div>

          <!-- Empty Items State -->
          <div
            v-else
            class="mt-6 flex flex-col items-center justify-center rounded-xl border border-dashed border-outline-gray-2 bg-white p-10 text-center"
          >
            <div class="flex h-10 w-10 items-center justify-center rounded-full bg-surface-gray-2 text-ink-gray-5">
              <svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
              </svg>
            </div>
            <h3 class="mt-2 text-sm font-semibold text-ink-gray-9">No Product Items in Collection</h3>
            <p class="mt-1 text-xs text-ink-gray-5">Add WA Catalog Item records to display products in this catalog.</p>
            <button
              type="button"
              @click="startItem()"
              class="mt-3 rounded-lg bg-[#075E54] px-3 py-1.5 text-xs font-semibold text-white hover:bg-[#128C7E]"
            >
              + Add Catalog Item
            </button>
          </div>
        </div>
      </div>
    </div>

    <Dialog v-model="catalogEditorOpen" :title="catalogEditorMode === 'edit' ? 'Edit catalog' : 'New catalog'">
      <div class="space-y-3 py-1 text-xs">
        <label class="block font-semibold text-ink-gray-7">
          Catalog name
          <input v-model="catalogForm.catalog_name" type="text" class="mt-1 block w-full rounded-lg border border-outline-gray-2 px-3 py-2 text-xs" />
        </label>
        <label class="block font-semibold text-ink-gray-7">
          WhatsApp account
          <select v-model="catalogForm.whatsapp_account" class="mt-1 block w-full rounded-lg border border-outline-gray-2 px-3 py-2 text-xs">
            <option value="">No account</option>
            <option v-for="account in accountOptions" :key="account.name" :value="account.name">
              {{ account.account_name || account.name }}
            </option>
          </select>
        </label>
        <label class="block font-semibold text-ink-gray-7">
          Description
          <textarea v-model="catalogForm.description" rows="3" class="mt-1 block w-full rounded-lg border border-outline-gray-2 px-3 py-2 text-xs" />
        </label>
        <label class="block font-semibold text-ink-gray-7">
          Status
          <select v-model="catalogForm.status" class="mt-1 block w-full rounded-lg border border-outline-gray-2 px-3 py-2 text-xs">
            <option>Draft</option>
            <option>Active</option>
            <option>Archived</option>
          </select>
        </label>
      </div>
      <template #actions>
        <div class="flex w-full items-center justify-between gap-2">
          <Button v-if="catalogEditorMode === 'edit'" label="Delete" :loading="savingCatalog" @click="removeCatalog" />
          <span v-else />
          <div class="flex gap-2">
            <Button label="Cancel" @click="catalogEditorOpen = false" />
            <Button variant="solid" class="bg-[#075E54] text-white" :label="catalogEditorMode === 'edit' ? 'Save' : 'Create catalog'" :loading="savingCatalog" @click="saveCatalogForm" />
          </div>
        </div>
      </template>
    </Dialog>

    <Dialog v-model="itemEditorOpen" :title="itemEditorMode === 'edit' ? 'Edit item' : 'New catalog item'">
      <div class="space-y-3 py-1 text-xs">
        <label class="block font-semibold text-ink-gray-7">
          Item name
          <input v-model="itemForm.item_name" type="text" class="mt-1 block w-full rounded-lg border border-outline-gray-2 px-3 py-2 text-xs" />
        </label>
        <label class="block font-semibold text-ink-gray-7">
          SKU
          <input v-model="itemForm.sku" type="text" class="mt-1 block w-full rounded-lg border border-outline-gray-2 px-3 py-2 text-xs" />
        </label>
        <label class="block font-semibold text-ink-gray-7">
          Description
          <textarea v-model="itemForm.description" rows="3" class="mt-1 block w-full rounded-lg border border-outline-gray-2 px-3 py-2 text-xs" />
        </label>
        <div class="grid grid-cols-2 gap-3">
          <label class="block font-semibold text-ink-gray-7">
            Price
            <input v-model="itemForm.price" type="number" min="0" step="0.01" class="mt-1 block w-full rounded-lg border border-outline-gray-2 px-3 py-2 text-xs" />
          </label>
          <label class="block font-semibold text-ink-gray-7">
            Currency
            <input v-model="itemForm.currency" type="text" class="mt-1 block w-full rounded-lg border border-outline-gray-2 px-3 py-2 text-xs" />
          </label>
        </div>
        <label class="block font-semibold text-ink-gray-7">
          Image
          <input v-model="itemForm.image" type="text" placeholder="https://… or /files/…" class="mt-1 block w-full rounded-lg border border-outline-gray-2 px-3 py-2 text-xs" />
        </label>
        <label class="block font-semibold text-ink-gray-7">
          Status
          <select v-model="itemForm.status" class="mt-1 block w-full rounded-lg border border-outline-gray-2 px-3 py-2 text-xs">
            <option>Active</option>
            <option>Inactive</option>
          </select>
        </label>
      </div>
      <template #actions>
        <div class="flex w-full items-center justify-between gap-2">
          <Button v-if="itemEditorMode === 'edit'" label="Delete" :loading="savingCatalog" @click="removeItem" />
          <span v-else />
          <div class="flex gap-2">
            <Button label="Cancel" @click="itemEditorOpen = false" />
            <Button variant="solid" class="bg-[#075E54] text-white" :label="itemEditorMode === 'edit' ? 'Save' : 'Add item'" :loading="savingCatalog" @click="saveItemForm" />
          </div>
        </div>
      </template>
    </Dialog>

    <!-- MODAL: Send Single-Product Message (SPM) with Live WhatsApp Preview -->
    <Dialog
      v-model="showSendModal"
      title="Send Single-Product Message (SPM)"
      size="2xl"
    >
      <div v-if="selectedItemToSend" class="space-y-4 py-1">
        <p class="text-xs text-ink-gray-6 -mt-2">
          Dispatch an interactive Meta WhatsApp product card directly to a customer thread
        </p>

        <div class="mt-3 grid items-start gap-6 md:grid-cols-2">
          <!-- Configuration Form -->
          <div class="space-y-4">
            <!-- Recipient Selection -->
            <div>
              <label class="block text-xs font-semibold text-ink-gray-7">Target Customer / Thread</label>
              <select
                v-model="recipientProfile"
                class="mt-1 block w-full rounded-lg border border-outline-gray-2 bg-white px-3 py-2 text-xs text-ink-gray-9 focus:border-[#128C7E] focus:outline-none focus:ring-1 focus:ring-[#128C7E]"
              >
                <option value="" disabled>Select customer...</option>
                <option
                  v-for="conv in desk.inbox.value?.conversations || []"
                  :key="conv.profile.name"
                  :value="conv.profile.name"
                >
                  {{ conv.profile.profile_name || conv.profile.name }} ({{ conv.profile.phone_number }})
                </option>
              </select>
            </div>

            <!-- Custom Message Body -->
            <div>
              <label class="block text-xs font-semibold text-ink-gray-7">Message Body</label>
              <textarea
                v-model="customBodyText"
                rows="3"
                class="mt-1 block w-full rounded-lg border border-outline-gray-2 bg-white p-2.5 text-xs text-ink-gray-9 focus:border-[#128C7E] focus:outline-none focus:ring-1 focus:ring-[#128C7E]"
                placeholder="Enter introductory message text..."
              ></textarea>
            </div>

            <!-- Footer Text -->
            <div>
              <label class="block text-xs font-semibold text-ink-gray-7">Footer Note</label>
              <input
                v-model="customFooterText"
                type="text"
                class="mt-1 block h-9 w-full rounded-lg border border-outline-gray-2 bg-white px-3 text-sm text-ink-gray-9 focus:border-[#128C7E] focus:outline-none focus:ring-1 focus:ring-[#128C7E]"
                placeholder="Tap below to view details"
              />
            </div>
          </div>

          <!-- Live WhatsApp Chat Bubble Preview -->
          <div class="flex flex-col rounded-xl bg-[#efeae2]/40 p-4 ring-1 ring-black/5">
            <span class="mb-2 text-center text-[10px] font-semibold text-ink-gray-5 uppercase tracking-wider">
              Customer Chat Preview
            </span>

            <div class="rounded-xl border border-[#d1d7db] bg-white p-3.5 shadow-sm">
              <p class="text-xs text-ink-gray-9 leading-relaxed whitespace-pre-wrap">{{ customBodyText }}</p>

              <!-- Interactive SPM Product Card -->
              <div class="mt-2.5 overflow-hidden rounded-lg border border-outline-gray-2 bg-surface-gray-2/40">
                <div class="flex h-24 items-center justify-center bg-gradient-to-br from-emerald-100 to-teal-50 text-[#075E54]">
                  <span class="lucide-shopping-bag size-9 text-[#075E54]" />
                </div>
                <div class="p-2.5">
                  <h4 class="text-xs font-bold text-ink-gray-9">{{ selectedItemToSend.item_name }}</h4>
                  <p class="mt-0.5 text-xs font-extrabold text-emerald-800">
                    {{ formatCurrency(selectedItemToSend.price, selectedItemToSend.currency) }}
                  </p>
                  <p class="mt-0.5 text-[10px] text-ink-gray-5 line-clamp-1">{{ selectedItemToSend.description }}</p>
                </div>
              </div>

              <div class="mt-2.5 border-t border-outline-gray-1 pt-2">
                <div
                  class="flex w-full items-center justify-center gap-1.5 rounded-md bg-surface-gray-2/80 py-1.5 text-xs font-semibold text-[#075E54]"
                >
                  <span class="lucide-eye size-3.5" />
                  <span>View Product</span>
                </div>
              </div>

              <p v-if="customFooterText" class="mt-1.5 text-right text-[10px] text-ink-gray-4">
                {{ customFooterText }}
              </p>
            </div>
          </div>
        </div>
      </div>

      <template #actions>
        <div class="flex items-center justify-between w-full">
          <Button
            variant="subtle"
            label="Cancel"
            @click="showSendModal = false"
          />
          <Button
            variant="solid"
            class="bg-[#075E54] text-white hover:bg-[#128C7E]"
            :loading="isSendingProduct"
            :disabled="!recipientProfile"
            icon-left="lucide-send"
            label="Send Message"
            @click="handleSendProduct"
          />
        </div>
      </template>
    </Dialog>
  </div>
</template>
