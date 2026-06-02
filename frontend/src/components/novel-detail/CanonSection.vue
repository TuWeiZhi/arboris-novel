<!-- AIMETA P=小说圣经区_Canon条目管理|R=CanonCRUD_筛选|NR=不含生成逻辑|E=component:CanonSection|X=ui|A=Canon管理组件|D=vue|S=dom,net|RD=./README.ai -->
<template>
  <div class="canon-section flex h-full min-h-0 flex-col gap-5">
    <div class="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
      <div class="flex min-w-0 items-center gap-3">
        <div
          class="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full"
          style="background-color: var(--md-primary-container); color: var(--md-on-primary-container);"
        >
          <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M4 19.5A2.5 2.5 0 016.5 17H20" />
            <path stroke-linecap="round" stroke-linejoin="round" d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z" />
            <path stroke-linecap="round" stroke-linejoin="round" d="M9 7h6M9 11h6M9 15h3" />
          </svg>
        </div>
        <div class="min-w-0">
          <h2 class="md-title-large truncate" style="color: var(--md-on-surface);">小说圣经 / Canon</h2>
          <p class="md-body-small" style="color: var(--md-on-surface-variant);">
            {{ entries.length }} 条条目，{{ hardRuleCount }} 条硬规则
          </p>
        </div>
      </div>

      <div class="flex flex-wrap items-center gap-2">
        <button
          type="button"
          class="md-icon-btn md-ripple"
          :disabled="isLoading"
          title="刷新"
          aria-label="刷新"
          @click="fetchEntries"
        >
          <svg
            class="h-5 w-5 transition-transform"
            :class="{ 'animate-spin': isLoading }"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
        </button>
        <button
          v-if="editable"
          type="button"
          class="md-btn md-btn-filled md-ripple"
          @click="openCreateDialog"
        >
          <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M12 5v14M5 12h14" />
          </svg>
          新增条目
        </button>
      </div>
    </div>

    <form class="grid grid-cols-1 gap-3 lg:grid-cols-[1.2fr_0.8fr_0.8fr_0.7fr_auto]" @submit.prevent="fetchEntries">
      <div class="md-text-field">
        <label class="md-text-field-label" for="canon-query">搜索</label>
        <input
          id="canon-query"
          v-model="filters.query"
          class="md-text-field-input"
          type="search"
          placeholder="标题、正文、关键词"
        >
      </div>
      <div class="md-text-field">
        <label class="md-text-field-label" for="canon-category">分类</label>
        <select id="canon-category" v-model="filters.category" class="canon-select" @change="fetchEntries">
          <option value="">全部分类</option>
          <option v-for="option in categoryOptions" :key="option.value" :value="option.value">
            {{ option.label }}
          </option>
        </select>
      </div>
      <div class="md-text-field">
        <label class="md-text-field-label" for="canon-status">状态</label>
        <select id="canon-status" v-model="filters.status" class="canon-select" @change="fetchEntries">
          <option value="">全部状态</option>
          <option v-for="option in statusOptions" :key="option.value" :value="option.value">
            {{ option.label }}
          </option>
        </select>
      </div>
      <div class="md-text-field">
        <label class="md-text-field-label" for="canon-chapter">章节</label>
        <input
          id="canon-chapter"
          v-model="chapterFilterText"
          class="md-text-field-input"
          type="number"
          min="1"
          placeholder="任意"
        >
      </div>
      <div class="flex items-end gap-2">
        <button type="submit" class="md-btn md-btn-tonal md-ripple w-full lg:w-auto">
          <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M21 21l-4.35-4.35M11 19a8 8 0 100-16 8 8 0 000 16z" />
          </svg>
          筛选
        </button>
      </div>
    </form>

    <div v-if="message" class="rounded-lg border px-4 py-3 md-body-small" :class="messageClass">
      {{ message }}
    </div>

    <div v-if="isLoading" class="flex flex-1 flex-col items-center justify-center py-16">
      <div class="md-spinner"></div>
      <p class="mt-4 md-body-medium" style="color: var(--md-on-surface-variant);">加载中...</p>
    </div>

    <div v-else-if="error" class="flex flex-1 flex-col items-center justify-center gap-4 py-16">
      <div
        class="flex h-14 w-14 items-center justify-center rounded-full"
        style="background-color: var(--md-error-container); color: var(--md-error);"
      >
        <svg class="h-7 w-7" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path stroke-linecap="round" stroke-linejoin="round" d="M12 8v4m0 4h.01" />
          <path stroke-linecap="round" stroke-linejoin="round" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      </div>
      <p class="md-body-medium text-center" style="color: var(--md-error);">{{ error }}</p>
      <button type="button" class="md-btn md-btn-text md-ripple" @click="fetchEntries">重试</button>
    </div>

    <div v-else-if="entries.length === 0" class="flex flex-1 flex-col items-center justify-center gap-3 py-16 text-center">
      <div
        class="flex h-16 w-16 items-center justify-center rounded-full"
        style="background-color: var(--md-surface-container); color: var(--md-on-surface-variant);"
      >
        <svg class="h-8 w-8" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path stroke-linecap="round" stroke-linejoin="round" d="M4 19.5A2.5 2.5 0 016.5 17H20" />
          <path stroke-linecap="round" stroke-linejoin="round" d="M8 7h8M8 11h8M8 15h4" />
        </svg>
      </div>
      <p class="md-body-large" style="color: var(--md-on-surface);">暂无 Canon 条目</p>
      <button v-if="editable" type="button" class="md-btn md-btn-filled md-ripple" @click="openCreateDialog">
        新增条目
      </button>
    </div>

    <div v-else class="min-h-0 flex-1 overflow-y-auto pr-1">
      <div class="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <article
          v-for="entry in entries"
          :key="entry.id"
          class="canon-entry border border-slate-200 bg-white p-4 shadow-sm"
        >
          <div class="flex items-start justify-between gap-3">
            <div class="min-w-0">
              <div class="mb-2 flex flex-wrap items-center gap-2">
                <span class="md-chip md-chip-filter selected canon-chip">{{ getCategoryLabel(entry.category) }}</span>
                <span
                  class="md-chip md-chip-assist canon-chip"
                  :class="{ 'canon-chip-warning': entry.hard_rule }"
                >
                  {{ entry.hard_rule ? '硬规则' : getStatusLabel(entry.status || 'active') }}
                </span>
                <span v-if="entry.valid_from_chapter || entry.valid_until_chapter" class="md-chip md-chip-assist canon-chip">
                  第{{ entry.valid_from_chapter || '?' }}-{{ entry.valid_until_chapter || '今' }}章
                </span>
              </div>
              <h3 class="md-title-medium break-words" style="color: var(--md-on-surface);">{{ entry.title }}</h3>
            </div>
            <div v-if="editable" class="flex flex-shrink-0 items-center gap-1">
              <button
                type="button"
                class="md-icon-btn md-ripple"
                title="编辑"
                aria-label="编辑"
                @click="openEditDialog(entry)"
              >
                <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M16.862 3.487a2.1 2.1 0 112.97 2.97L8.5 17.79 4 19l1.21-4.5L16.862 3.487z" />
                </svg>
              </button>
              <button
                type="button"
                class="md-icon-btn md-ripple"
                title="删除"
                aria-label="删除"
                @click="deleteEntry(entry)"
              >
                <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M3 6h18M8 6V4h8v2M6 6l1 16h10l1-16" />
                </svg>
              </button>
            </div>
          </div>

          <p class="mt-3 whitespace-pre-line break-words md-body-medium" style="color: var(--md-on-surface);">
            {{ entry.content }}
          </p>

          <div v-if="getEntryTerms(entry).length" class="mt-4 flex flex-wrap gap-2">
            <span
              v-for="term in getEntryTerms(entry)"
              :key="`${entry.id}-${term}`"
              class="rounded-md bg-slate-100 px-2 py-1 text-xs text-slate-600"
            >
              {{ term }}
            </span>
          </div>
        </article>
      </div>
    </div>

    <transition
      enter-active-class="md-scale-enter-active"
      leave-active-class="md-scale-leave-active"
      enter-from-class="md-scale-enter-from"
      leave-to-class="md-scale-leave-to"
    >
      <div v-if="isDialogOpen" class="md-dialog-overlay">
        <div class="absolute inset-0" @click="closeDialog"></div>
        <form class="md-dialog canon-dialog relative mx-4 w-full max-w-3xl" @submit.prevent="saveEntry" @click.stop>
          <div class="md-dialog-header">
            <h3 class="md-dialog-title">{{ editingEntryId ? '编辑 Canon 条目' : '新增 Canon 条目' }}</h3>
          </div>
          <div class="md-dialog-content space-y-5">
            <div class="grid grid-cols-1 gap-4 md:grid-cols-3">
              <div class="md-text-field">
                <label class="md-text-field-label" for="canon-form-category">分类</label>
                <select id="canon-form-category" v-model="form.category" class="canon-select" required>
                  <option v-for="option in categoryOptions" :key="option.value" :value="option.value">
                    {{ option.label }}
                  </option>
                </select>
              </div>
              <div class="md-text-field">
                <label class="md-text-field-label" for="canon-form-status">状态</label>
                <select id="canon-form-status" v-model="form.status" class="canon-select">
                  <option v-for="option in statusOptions" :key="option.value" :value="option.value">
                    {{ option.label }}
                  </option>
                </select>
              </div>
              <div class="md-text-field">
                <label class="md-text-field-label" for="canon-form-visibility">可见性</label>
                <select id="canon-form-visibility" v-model="form.visibility" class="canon-select">
                  <option v-for="option in visibilityOptions" :key="option.value" :value="option.value">
                    {{ option.label }}
                  </option>
                </select>
              </div>
            </div>

            <div class="md-text-field">
              <label class="md-text-field-label" for="canon-form-title">标题</label>
              <input id="canon-form-title" v-model.trim="form.title" class="md-text-field-input" type="text" required>
            </div>

            <div class="md-text-field">
              <label class="md-text-field-label" for="canon-form-content">正文</label>
              <textarea id="canon-form-content" v-model.trim="form.content" class="md-textarea canon-content-input" required></textarea>
            </div>

            <div class="grid grid-cols-1 gap-4 md:grid-cols-3">
              <div class="md-text-field">
                <label class="md-text-field-label" for="canon-form-aliases">别名</label>
                <input id="canon-form-aliases" v-model="form.aliasesText" class="md-text-field-input" type="text" placeholder="用逗号分隔">
              </div>
              <div class="md-text-field">
                <label class="md-text-field-label" for="canon-form-keywords">关键词</label>
                <input id="canon-form-keywords" v-model="form.keywordsText" class="md-text-field-input" type="text" placeholder="用逗号分隔">
              </div>
              <div class="md-text-field">
                <label class="md-text-field-label" for="canon-form-tags">标签</label>
                <input id="canon-form-tags" v-model="form.tagsText" class="md-text-field-input" type="text" placeholder="用逗号分隔">
              </div>
            </div>

            <div class="grid grid-cols-1 gap-4 md:grid-cols-4">
              <div class="md-text-field">
                <label class="md-text-field-label" for="canon-form-valid-from">起始章节</label>
                <input id="canon-form-valid-from" v-model="form.validFromText" class="md-text-field-input" type="number" min="1">
              </div>
              <div class="md-text-field">
                <label class="md-text-field-label" for="canon-form-valid-until">截止章节</label>
                <input id="canon-form-valid-until" v-model="form.validUntilText" class="md-text-field-input" type="number" min="1">
              </div>
              <div class="md-text-field">
                <label class="md-text-field-label" for="canon-form-verified">核对章节</label>
                <input id="canon-form-verified" v-model="form.lastVerifiedText" class="md-text-field-input" type="number" min="1">
              </div>
              <div class="md-text-field">
                <label class="md-text-field-label" for="canon-form-source">来源</label>
                <input id="canon-form-source" v-model.trim="form.source" class="md-text-field-input" type="text">
              </div>
            </div>

            <label class="flex items-center gap-3 md-body-medium" style="color: var(--md-on-surface);">
              <input v-model="form.hardRule" type="checkbox" class="h-4 w-4">
              硬规则
            </label>
          </div>
          <div class="md-dialog-actions">
            <button type="button" class="md-btn md-btn-text md-ripple" @click="closeDialog">取消</button>
            <button type="submit" class="md-btn md-btn-filled md-ripple" :disabled="isSaving">
              {{ isSaving ? '保存中...' : '保存' }}
            </button>
          </div>
        </form>
      </div>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { NovelAPI } from '@/api/novel'
import type { CanonEntry, CanonEntryPayload, CanonListParams } from '@/api/novel'

const props = defineProps<{
  projectId: string
  editable?: boolean
}>()

const categoryOptions = [
  { value: 'rule', label: '规则' },
  { value: 'character', label: '人物' },
  { value: 'location', label: '地点' },
  { value: 'item', label: '物品' },
  { value: 'faction', label: '势力' },
  { value: 'event', label: '事件' },
  { value: 'clue', label: '线索' },
  { value: 'style', label: '文风' },
  { value: 'other', label: '其他' }
]

const statusOptions = [
  { value: 'active', label: '生效' },
  { value: 'changed', label: '已变化' },
  { value: 'draft', label: '草稿' },
  { value: 'archived', label: '归档' }
]

const visibilityOptions = [
  { value: 'pov_safe', label: '视角安全' },
  { value: 'global', label: '全局' },
  { value: 'hidden', label: '隐藏' }
]

const entries = ref<CanonEntry[]>([])
const isLoading = ref(false)
const isSaving = ref(false)
const error = ref<string | null>(null)
const message = ref('')
const messageType = ref<'success' | 'error'>('success')
const isDialogOpen = ref(false)
const editingEntryId = ref<number | null>(null)
const chapterFilterText = ref('')

const filters = reactive({
  query: '',
  category: '',
  status: ''
})

const form = reactive({
  category: 'rule',
  title: '',
  content: '',
  aliasesText: '',
  keywordsText: '',
  tagsText: '',
  status: 'active',
  visibility: 'pov_safe',
  source: '',
  validFromText: '',
  validUntilText: '',
  lastVerifiedText: '',
  hardRule: false
})

const hardRuleCount = computed(() => entries.value.filter(entry => entry.hard_rule).length)

const messageClass = computed(() => {
  return messageType.value === 'success'
    ? 'border-green-200 bg-green-50 text-green-700'
    : 'border-red-200 bg-red-50 text-red-700'
})

const getCategoryLabel = (value: string) => categoryOptions.find(option => option.value === value)?.label || value
const getStatusLabel = (value: string) => statusOptions.find(option => option.value === value)?.label || value

const parseList = (value: string) => {
  return value
    .split(/[,，、\n]/)
    .map(item => item.trim())
    .filter(Boolean)
}

const joinList = (value?: string[] | null) => (value || []).join('，')

const parseOptionalNumber = (value: string | number | null | undefined) => {
  const trimmed = String(value ?? '').trim()
  if (!trimmed) return null
  const parsed = Number(trimmed)
  return Number.isFinite(parsed) && parsed > 0 ? Math.floor(parsed) : null
}

const buildParams = (): CanonListParams => {
  return {
    query: filters.query,
    category: filters.category || undefined,
    status: filters.status || undefined,
    chapter_number: parseOptionalNumber(chapterFilterText.value)
  }
}

const showMessage = (text: string, type: 'success' | 'error' = 'success') => {
  message.value = text
  messageType.value = type
  window.setTimeout(() => {
    if (message.value === text) message.value = ''
  }, 2500)
}

const fetchEntries = async () => {
  if (!props.projectId) return
  isLoading.value = true
  error.value = null
  try {
    const response = await NovelAPI.listCanonEntries(props.projectId, buildParams())
    entries.value = response.entries || []
  } catch (err) {
    console.error('Canon 加载失败:', err)
    error.value = err instanceof Error ? err.message : '加载失败'
  } finally {
    isLoading.value = false
  }
}

const resetForm = () => {
  form.category = 'rule'
  form.title = ''
  form.content = ''
  form.aliasesText = ''
  form.keywordsText = ''
  form.tagsText = ''
  form.status = 'active'
  form.visibility = 'pov_safe'
  form.source = ''
  form.validFromText = ''
  form.validUntilText = ''
  form.lastVerifiedText = ''
  form.hardRule = false
}

const openCreateDialog = () => {
  resetForm()
  editingEntryId.value = null
  isDialogOpen.value = true
}

const openEditDialog = (entry: CanonEntry) => {
  editingEntryId.value = entry.id
  form.category = entry.category || 'rule'
  form.title = entry.title || ''
  form.content = entry.content || ''
  form.aliasesText = joinList(entry.aliases)
  form.keywordsText = joinList(entry.keywords)
  form.tagsText = joinList(entry.tags)
  form.status = entry.status || 'active'
  form.visibility = entry.visibility || 'pov_safe'
  form.source = entry.source || ''
  form.validFromText = entry.valid_from_chapter ? String(entry.valid_from_chapter) : ''
  form.validUntilText = entry.valid_until_chapter ? String(entry.valid_until_chapter) : ''
  form.lastVerifiedText = entry.last_verified_chapter ? String(entry.last_verified_chapter) : ''
  form.hardRule = Boolean(entry.hard_rule)
  isDialogOpen.value = true
}

const closeDialog = () => {
  if (isSaving.value) return
  isDialogOpen.value = false
}

const buildPayload = (): CanonEntryPayload => {
  return {
    category: form.category,
    title: form.title.trim(),
    content: form.content.trim(),
    aliases: parseList(form.aliasesText),
    keywords: parseList(form.keywordsText),
    tags: parseList(form.tagsText),
    status: form.status,
    visibility: form.visibility,
    source: form.source.trim() || null,
    valid_from_chapter: parseOptionalNumber(form.validFromText),
    valid_until_chapter: parseOptionalNumber(form.validUntilText),
    last_verified_chapter: parseOptionalNumber(form.lastVerifiedText),
    hard_rule: form.hardRule
  }
}

const saveEntry = async () => {
  if (!props.editable || !props.projectId) return
  const payload = buildPayload()
  if (!payload.title || !payload.content) {
    showMessage('标题和正文不能为空', 'error')
    return
  }

  isSaving.value = true
  try {
    if (editingEntryId.value) {
      await NovelAPI.updateCanonEntry(props.projectId, editingEntryId.value, payload)
      showMessage('Canon 条目已更新')
    } else {
      await NovelAPI.createCanonEntry(props.projectId, payload)
      showMessage('Canon 条目已新增')
    }
    isDialogOpen.value = false
    await fetchEntries()
  } catch (err) {
    console.error('Canon 保存失败:', err)
    showMessage(err instanceof Error ? err.message : '保存失败', 'error')
  } finally {
    isSaving.value = false
  }
}

const deleteEntry = async (entry: CanonEntry) => {
  if (!props.editable || !props.projectId) return
  if (!window.confirm(`删除「${entry.title}」？`)) return

  try {
    await NovelAPI.deleteCanonEntry(props.projectId, entry.id)
    showMessage('Canon 条目已删除')
    await fetchEntries()
  } catch (err) {
    console.error('Canon 删除失败:', err)
    showMessage(err instanceof Error ? err.message : '删除失败', 'error')
  }
}

const getEntryTerms = (entry: CanonEntry) => {
  return [
    ...(entry.aliases || []).map(item => `别名:${item}`),
    ...(entry.keywords || []).map(item => `关键词:${item}`),
    ...(entry.tags || []).map(item => `标签:${item}`)
  ].slice(0, 10)
}

onMounted(() => {
  fetchEntries()
})
</script>

<style scoped>
.canon-section {
  color: var(--md-on-surface);
}

.canon-select {
  width: 100%;
  height: 56px;
  padding: 0 14px;
  border: 1px solid var(--md-outline);
  border-radius: var(--md-radius-xs);
  background-color: transparent;
  color: var(--md-on-surface);
  font: inherit;
  outline: none;
}

.canon-select:focus {
  border-color: var(--md-primary);
  border-width: 2px;
}

.canon-entry {
  border-radius: var(--md-radius-sm);
}

.canon-chip {
  height: 28px;
  padding: 0 10px;
  cursor: default;
  font-size: 12px;
}

.canon-chip-warning {
  border-color: transparent;
  background-color: var(--md-warning-container);
  color: var(--md-on-warning-container);
}

.canon-dialog {
  max-height: calc(100vh - 64px);
}

.canon-content-input {
  min-height: 180px;
}
</style>
