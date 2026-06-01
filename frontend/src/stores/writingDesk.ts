import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import type { AdvancedGenerateResponse, Chapter, ChapterVersion, NovelProject } from '@/api/novel'
import { useNovelStore } from '@/stores/novel'
import { buildVersionsFromVariants, normalizeChapterContent, normalizeChapterVersions } from '@/utils/chapter'

function createPendingChapter(chapterNumber: number, project: NovelProject): Chapter {
  const outline = project.blueprint?.chapter_outline?.find((item) => item.chapter_number === chapterNumber)
  return {
    chapter_number: chapterNumber,
    title: outline?.title || '加载中...',
    summary: outline?.summary || '',
    real_summary: null,
    content: '',
    versions: [],
    evaluation: null,
    generation_status: 'generating',
    word_count: 0,
  }
}

export const useWritingDeskStore = defineStore('writingDesk', () => {
  const novelStore = useNovelStore()

  const selectedChapterNumber = ref<number | null>(null)
  const chapterGenerationResult = ref<AdvancedGenerateResponse | null>(null)
  const selectedVersionIndex = ref(0)
  const generatingChapter = ref<number | null>(null)
  const sidebarOpen = ref(false)
  const showVersionDetailModal = ref(false)
  const detailVersionIndex = ref(0)
  const showEvaluationDetailModal = ref(false)
  const showEditChapterModal = ref(false)
  const isGeneratingOutline = ref(false)
  const showGenerateOutlineModal = ref(false)

  const project = computed<NovelProject | null>(() => novelStore.currentProject)

  const selectedChapter = computed<Chapter | null>(() => {
    if (!project.value || selectedChapterNumber.value === null) {
      return null
    }
    return project.value.chapters.find((chapter) => chapter.chapter_number === selectedChapterNumber.value) || null
  })

  const selectedChapterOutline = computed(() => {
    if (!project.value?.blueprint?.chapter_outline || selectedChapterNumber.value === null) {
      return null
    }
    return project.value.blueprint.chapter_outline.find((chapter) => chapter.chapter_number === selectedChapterNumber.value) || null
  })

  const showVersionSelector = computed(() => {
    const status = selectedChapter.value?.generation_status
    return status === 'waiting_for_confirm' || status === 'evaluating' || status === 'evaluation_failed' || status === 'selecting'
  })

  const evaluatingChapter = computed(() => {
    if (selectedChapter.value?.generation_status === 'evaluating') {
      return selectedChapter.value.chapter_number
    }
    return null
  })

  const isSelectingVersion = computed(() => selectedChapter.value?.generation_status === 'selecting')

  const totalChapters = computed(() => project.value?.blueprint?.chapter_outline?.length || 0)
  const completedChapters = computed(() => project.value?.chapters?.filter((chapter) => chapter.content)?.length || 0)
  const progress = computed(() => {
    if (!totalChapters.value) {
      return 0
    }
    return Math.round((completedChapters.value / totalChapters.value) * 100)
  })

  const availableVersions = computed<ChapterVersion[]>(() => {
    if (chapterGenerationResult.value?.variants) {
      return buildVersionsFromVariants(chapterGenerationResult.value.variants)
    }
    return normalizeChapterVersions(selectedChapter.value?.versions)
  })

  function cleanVersionContent(content: string): string {
    return normalizeChapterContent(content)
  }

  function isCurrentVersion(versionIndex: number): boolean {
    const version = availableVersions.value[versionIndex]
    if (!selectedChapter.value?.content || !version?.content) {
      return false
    }

    if (version.is_selected) {
      return true
    }

    return cleanVersionContent(selectedChapter.value.content) === cleanVersionContent(version.content)
  }

  function ensureProject(): NovelProject {
    if (!project.value) {
      throw new Error('没有当前项目')
    }
    return project.value
  }

  function selectChapter(chapterNumber: number): void {
    selectedChapterNumber.value = chapterNumber
    chapterGenerationResult.value = null
    selectedVersionIndex.value = 0
    sidebarOpen.value = false
  }

  function toggleSidebar(): void {
    sidebarOpen.value = !sidebarOpen.value
  }

  function closeSidebar(): void {
    sidebarOpen.value = false
  }

  function showVersionDetail(versionIndex: number): void {
    detailVersionIndex.value = versionIndex
    showVersionDetailModal.value = true
  }

  function closeVersionDetail(): void {
    showVersionDetailModal.value = false
  }

  function hideVersionSelector(): void {
    chapterGenerationResult.value = null
    selectedVersionIndex.value = 0
  }

  function canGenerateChapter(chapterNumber: number): boolean {
    const currentProject = project.value
    if (!currentProject?.blueprint?.chapter_outline) {
      return false
    }

    const outlines = [...currentProject.blueprint.chapter_outline].sort((a, b) => a.chapter_number - b.chapter_number)
    for (const outline of outlines) {
      if (outline.chapter_number >= chapterNumber) {
        break
      }
      const chapter = currentProject.chapters.find((item) => item.chapter_number === outline.chapter_number)
      if (!chapter || chapter.generation_status !== 'successful') {
        return false
      }
    }

    return true
  }

  function isChapterFailed(chapterNumber: number): boolean {
    return project.value?.chapters?.some((chapter) => chapter.chapter_number === chapterNumber && chapter.generation_status === 'failed') || false
  }

  function hasChapterInProgress(chapterNumber: number): boolean {
    return project.value?.chapters?.some((chapter) => chapter.chapter_number === chapterNumber && chapter.generation_status === 'waiting_for_confirm') || false
  }

  async function loadProject(projectId: string, silent = false): Promise<void> {
    await novelStore.loadProject(projectId, silent)
  }

  async function fetchChapterStatus(): Promise<void> {
    if (selectedChapterNumber.value === null) {
      return
    }
    await novelStore.loadChapter(selectedChapterNumber.value)
  }

  async function generateChapter(projectId: string, chapterNumber: number): Promise<AdvancedGenerateResponse> {
    ensureProject()
    generatingChapter.value = chapterNumber
    selectedChapterNumber.value = chapterNumber

    const existingChapter = project.value?.chapters.find((chapter) => chapter.chapter_number === chapterNumber)
    if (existingChapter) {
      novelStore.updateChapterLocal(chapterNumber, { generation_status: 'generating' })
    } else {
      novelStore.addChapterLocal(createPendingChapter(chapterNumber, project.value!))
    }

    try {
      const result = await novelStore.generateChapter(chapterNumber)
      chapterGenerationResult.value = result
      await novelStore.loadProject(projectId, true)
      selectedVersionIndex.value = Math.max(result.best_version_index || 0, 0)
      return result
    } catch (error) {
      novelStore.updateChapterLocal(chapterNumber, { generation_status: 'failed' })
      throw error
    } finally {
      generatingChapter.value = null
    }
  }

  async function selectVersion(chapterNumber: number, versionIndex: number): Promise<void> {
    const version = availableVersions.value[versionIndex]
    if (!version?.content) {
      return
    }

    novelStore.updateChapterLocal(chapterNumber, { generation_status: 'selecting' })
    selectedVersionIndex.value = versionIndex

    try {
      await novelStore.selectChapterVersion(chapterNumber, versionIndex)
      chapterGenerationResult.value = null
      detailVersionIndex.value = versionIndex
    } catch (error) {
      novelStore.updateChapterLocal(chapterNumber, { generation_status: 'waiting_for_confirm' })
      throw error
    }
  }

  async function evaluateChapter(chapterNumber: number): Promise<void> {
    novelStore.updateChapterLocal(chapterNumber, { generation_status: 'evaluating' })

    try {
      await novelStore.evaluateChapter(chapterNumber)
    } catch (error) {
      novelStore.updateChapterLocal(chapterNumber, { generation_status: 'waiting_for_confirm' })
      throw error
    }
  }

  async function deleteChapter(chapterNumbers: number | number[]): Promise<void> {
    await novelStore.deleteChapter(chapterNumbers)
    const numbers = Array.isArray(chapterNumbers) ? chapterNumbers : [chapterNumbers]
    if (selectedChapterNumber.value !== null && numbers.includes(selectedChapterNumber.value)) {
      selectedChapterNumber.value = null
    }
  }

  async function generateChapterOutline(startChapter: number, numChapters: number): Promise<void> {
    isGeneratingOutline.value = true
    try {
      await novelStore.generateChapterOutline(startChapter, numChapters)
    } finally {
      isGeneratingOutline.value = false
    }
  }

  return {
    project,
    selectedChapter,
    selectedChapterOutline,
    selectedChapterNumber,
    chapterGenerationResult,
    selectedVersionIndex,
    generatingChapter,
    sidebarOpen,
    showVersionDetailModal,
    detailVersionIndex,
    showEvaluationDetailModal,
    showEditChapterModal,
    isGeneratingOutline,
    showGenerateOutlineModal,
    showVersionSelector,
    evaluatingChapter,
    isSelectingVersion,
    totalChapters,
    completedChapters,
    progress,
    availableVersions,
    cleanVersionContent,
    isCurrentVersion,
    selectChapter,
    toggleSidebar,
    closeSidebar,
    showVersionDetail,
    closeVersionDetail,
    hideVersionSelector,
    canGenerateChapter,
    isChapterFailed,
    hasChapterInProgress,
    loadProject,
    fetchChapterStatus,
    generateChapter,
    selectVersion,
    evaluateChapter,
    deleteChapter,
    generateChapterOutline,
  }
})
