<!-- AIMETA P=写作台_章节编辑主页面|R=写作界面_章节管理|NR=不含详情展示|E=route:/novel/:id#component:WritingDesk|X=ui|A=写作台|D=vue|S=dom,net|RD=./README.ai -->
<template>
  <div class="m3-shell h-screen flex flex-col overflow-hidden">
    <WDHeader
      :project="project"
      :progress="progress"
      :completed-chapters="completedChapters"
      :total-chapters="totalChapters"
      @go-back="goBack"
      @view-project-detail="viewProjectDetail"
      @toggle-sidebar="toggleSidebar"
    />

    <!-- 主要内容区域 -->
    <div class="flex-1 w-full px-4 sm:px-6 lg:px-8 py-6 overflow-hidden">
      <!-- 加载状态 -->
      <div v-if="novelStore.isLoading" class="h-full flex justify-center items-center">
        <div class="text-center">
          <div class="md-spinner mx-auto mb-4"></div>
          <p class="md-body-medium md-on-surface-variant">正在加载项目数据...</p>
        </div>
      </div>

      <!-- 错误状态 -->
      <div v-else-if="novelStore.error" class="text-center py-20">
        <div class="md-card md-card-outlined p-8 max-w-md mx-auto" style="border-radius: var(--md-radius-xl);">
          <div class="w-12 h-12 rounded-full mx-auto mb-4 flex items-center justify-center" style="background-color: var(--md-error-container);">
            <svg class="w-6 h-6" style="color: var(--md-error);" fill="currentColor" viewBox="0 0 20 20">
              <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clip-rule="evenodd"></path>
            </svg>
          </div>
          <h3 class="md-title-large mb-2" style="color: var(--md-on-surface);">加载失败</h3>
          <p class="md-body-medium mb-4" style="color: var(--md-error);">{{ novelStore.error }}</p>
          <button @click="loadProject" class="md-btn md-btn-tonal md-ripple">重新加载</button>
        </div>
      </div>

      <!-- 主要内容 -->
      <div v-else-if="project" class="h-full flex gap-6">
        <WDSidebar
          :project="project"
          :sidebar-open="sidebarOpen"
          :selected-chapter-number="selectedChapterNumber"
          :generating-chapter="generatingChapter"
          :evaluating-chapter="evaluatingChapter"
          :is-generating-outline="isGeneratingOutline"
          @close-sidebar="closeSidebar"
          @select-chapter="selectChapter"
          @generate-chapter="generateChapter"
          @edit-chapter="openEditChapterModal"
          @delete-chapter="deleteChapter"
          @generate-outline="generateOutline"
        />

        <div class="flex-1 min-w-0">
          <WDWorkspace
            :project="project"
            :selected-chapter-number="selectedChapterNumber"
          :generating-chapter="generatingChapter"
          :evaluating-chapter="evaluatingChapter"
          :show-version-selector="showVersionSelector"
          :chapter-generation-result="chapterGenerationResult"
          :selected-version-index="selectedVersionIndex"
          :available-versions="availableVersions"
          :is-selecting-version="isSelectingVersion"
          @regenerate-chapter="regenerateChapter"
          @evaluate-chapter="evaluateChapter"
          @hide-version-selector="hideVersionSelector"
          @update:selected-version-index="selectedVersionIndex = $event"
          @show-version-detail="showVersionDetail"
          @confirm-version-selection="confirmVersionSelection"
          @generate-chapter="generateChapter"
          @show-evaluation-detail="showEvaluationDetailModal = true"
          @fetch-chapter-status="fetchChapterStatus"
          @edit-chapter="editChapterContent"
          />
        </div>
      </div>
    </div>
    <WDVersionDetailModal
      :show="showVersionDetailModal"
      :detail-version-index="detailVersionIndex"
      :version="availableVersions[detailVersionIndex]"
      :is-current="isCurrentVersion(detailVersionIndex)"
      @close="closeVersionDetail"
      @select-version="selectVersionFromDetail"
    />
    <WDEvaluationDetailModal
      :show="showEvaluationDetailModal"
      :evaluation="selectedChapter?.evaluation || null"
      @close="showEvaluationDetailModal = false"
    />
    <WDEditChapterModal
      :show="showEditChapterModal"
      :chapter="editingChapter"
      @close="showEditChapterModal = false"
      @save="saveChapterChanges"
    />
    <WDGenerateOutlineModal
      :show="showGenerateOutlineModal"
      @close="showGenerateOutlineModal = false"
      @generate="handleGenerateOutline"
    />
  </div>
</template>

<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useNovelStore } from '@/stores/novel'
import { useWritingDeskStore } from '@/stores/writingDesk'
import type { ChapterOutline } from '@/api/novel'
import { globalAlert } from '@/composables/useAlert'
import WDHeader from '@/components/writing-desk/WDHeader.vue'
import WDSidebar from '@/components/writing-desk/WDSidebar.vue'
import WDWorkspace from '@/components/writing-desk/WDWorkspace.vue'
import WDVersionDetailModal from '@/components/writing-desk/WDVersionDetailModal.vue'
import WDEvaluationDetailModal from '@/components/writing-desk/WDEvaluationDetailModal.vue'
import WDEditChapterModal from '@/components/writing-desk/WDEditChapterModal.vue'
import WDGenerateOutlineModal from '@/components/writing-desk/WDGenerateOutlineModal.vue'

interface Props {
  id: string
}

const props = defineProps<Props>()
const router = useRouter()
const novelStore = useNovelStore()
const writingDeskStore = useWritingDeskStore()

const editingChapter = ref<ChapterOutline | null>(null)

const {
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
} = storeToRefs(writingDeskStore)

const { isCurrentVersion, canGenerateChapter, isChapterFailed, hasChapterInProgress } = writingDeskStore


// 方法
const goBack = () => {
  router.push('/workspace')
}

const viewProjectDetail = () => {
  if (project.value) {
    router.push(`/detail/${project.value.id}`)
  }
}

const toggleSidebar = () => {
  writingDeskStore.toggleSidebar()
}

const closeSidebar = () => {
  writingDeskStore.closeSidebar()
}

const loadProject = async () => {
  try {
    await writingDeskStore.loadProject(props.id)
  } catch (error) {
    console.error('加载项目失败:', error)
  }
}

const fetchChapterStatus = async () => {
  try {
    await writingDeskStore.fetchChapterStatus()
    console.log('Chapter status polled and updated.')
  } catch (error) {
    console.error('轮询章节状态失败:', error)
  }
}

const showVersionDetail = (versionIndex: number) => {
  writingDeskStore.showVersionDetail(versionIndex)
}

const closeVersionDetail = () => {
  writingDeskStore.closeVersionDetail()
}

const hideVersionSelector = () => {
  writingDeskStore.hideVersionSelector()
}

const selectChapter = (chapterNumber: number) => {
  writingDeskStore.selectChapter(chapterNumber)
}

const generateChapter = async (chapterNumber: number) => {
  if (!canGenerateChapter(chapterNumber) && !isChapterFailed(chapterNumber) && !hasChapterInProgress(chapterNumber)) {
    globalAlert.showError('请按顺序生成章节，先完成前面的章节', '生成受限')
    return
  }

  try {
    await writingDeskStore.generateChapter(props.id, chapterNumber)
  } catch (error) {
    console.error('生成章节失败:', error)
    globalAlert.showError(`生成章节失败: ${error instanceof Error ? error.message : '未知错误'}`, '生成失败')
  }
}

const regenerateChapter = async () => {
  if (selectedChapterNumber.value !== null) {
    await generateChapter(selectedChapterNumber.value)
  }
}

const selectVersion = async (versionIndex: number) => {
  if (selectedChapterNumber.value === null || !availableVersions.value?.[versionIndex]?.content) {
    return
  }

  try {
    await writingDeskStore.selectVersion(selectedChapterNumber.value, versionIndex)
    await writingDeskStore.loadProject(props.id, true)
    globalAlert.showSuccess('版本已确认', '操作成功')
  } catch (error) {
    console.error('选择章节版本失败:', error)
    globalAlert.showError(`选择章节版本失败: ${error instanceof Error ? error.message : '未知错误'}`, '选择失败')
  }
}

// 从详情弹窗中选择版本
const selectVersionFromDetail = async () => {
  await selectVersion(detailVersionIndex.value)
  closeVersionDetail()
}

const confirmVersionSelection = async () => {
  await selectVersion(selectedVersionIndex.value)
}

const openEditChapterModal = (chapter: ChapterOutline) => {
  editingChapter.value = chapter
  showEditChapterModal.value = true
}

const saveChapterChanges = async (updatedChapter: ChapterOutline) => {
  try {
    await novelStore.updateChapterOutline(updatedChapter)
    globalAlert.showSuccess('章节大纲已更新', '保存成功')
  } catch (error) {
    console.error('更新章节大纲失败:', error)
    globalAlert.showError(`更新章节大纲失败: ${error instanceof Error ? error.message : '未知错误'}`, '保存失败')
  } finally {
    showEditChapterModal.value = false
  }
}

const evaluateChapter = async () => {
  if (selectedChapterNumber.value === null) {
    return
  }

  try {
    await writingDeskStore.evaluateChapter(selectedChapterNumber.value)
    globalAlert.showSuccess('章节评审结果已生成', '评审成功')
  } catch (error) {
    console.error('评审章节失败:', error)
    globalAlert.showError(`评审章节失败: ${error instanceof Error ? error.message : '未知错误'}`, '评审失败')
  }
}

const deleteChapter = async (chapterNumbers: number | number[]) => {
  const numbersToDelete = Array.isArray(chapterNumbers) ? chapterNumbers : [chapterNumbers]
  const confirmationMessage = numbersToDelete.length > 1
    ? `您确定要删除选中的 ${numbersToDelete.length} 个章节吗？这个操作无法撤销。`
    : `您确定要删除第 ${numbersToDelete[0]} 章吗？这个操作无法撤销。`

  if (window.confirm(confirmationMessage)) {
    try {
      await writingDeskStore.deleteChapter(numbersToDelete)
      globalAlert.showSuccess('章节已删除', '操作成功')
    } catch (error) {
      console.error('删除章节失败:', error)
      globalAlert.showError(`删除章节失败: ${error instanceof Error ? error.message : '未知错误'}`, '删除失败')
    }
  }
}

const generateOutline = async () => {
  showGenerateOutlineModal.value = true
}

const editChapterContent = async (data: { chapterNumber: number, content: string }) => {
  if (!project.value) return

  try {
    await novelStore.editChapterContent(project.value.id, data.chapterNumber, data.content)
    globalAlert.showSuccess('章节内容已更新', '保存成功')
  } catch (error) {
    console.error('编辑章节内容失败:', error)
    globalAlert.showError(`编辑章节内容失败: ${error instanceof Error ? error.message : '未知错误'}`, '保存失败')
  }
}

const handleGenerateOutline = async (numChapters: number) => {
  if (!project.value) return
  try {
    const startChapter = (project.value.blueprint?.chapter_outline?.length || 0) + 1
    await writingDeskStore.generateChapterOutline(startChapter, numChapters)
    globalAlert.showSuccess('新的章节大纲已生成', '操作成功')
  } catch (error) {
    console.error('生成大纲失败:', error)
    globalAlert.showError(`生成大纲失败: ${error instanceof Error ? error.message : '未知错误'}`, '生成失败')
  }
}

onMounted(() => {
  document.body.classList.add('m3-novel')
  loadProject()
})

onUnmounted(() => {
  document.body.classList.remove('m3-novel')
})
</script>

<style scoped>
@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700&family=Noto+Sans+SC:wght@400;500;600;700&display=swap');

:global(body.m3-novel) {
  --md-font-family: 'Manrope', 'Noto Sans SC', 'Noto Sans', 'PingFang SC', sans-serif;
  --md-primary: #2563eb;
  --md-primary-light: #4f7bf2;
  --md-primary-dark: #1d4ed8;
  --md-on-primary: #ffffff;
  --md-primary-container: #dbeafe;
  --md-on-primary-container: #0f172a;
  --md-secondary: #0f766e;
  --md-secondary-light: #2dd4bf;
  --md-secondary-dark: #0f766e;
  --md-on-secondary: #ffffff;
  --md-secondary-container: #ccfbf1;
  --md-on-secondary-container: #0f172a;
  --md-surface: #ffffff;
  --md-surface-dim: #f1f5f9;
  --md-surface-container-lowest: #ffffff;
  --md-surface-container-low: #f8fafc;
  --md-surface-container: #f1f5f9;
  --md-surface-container-high: #e2e8f0;
  --md-surface-container-highest: #dbe3ef;
  --md-on-surface: #0f172a;
  --md-on-surface-variant: #475569;
  --md-outline: #d7dde5;
  --md-outline-variant: #e2e8f0;
  --md-error: #dc2626;
  --md-error-container: #fee2e2;
  --md-on-error: #ffffff;
  --md-on-error-container: #7f1d1d;
  color: var(--md-on-surface);
  font-family: var(--md-font-family);
}

.m3-shell {
  background: radial-gradient(1200px 600px at 15% -20%, rgba(37, 99, 235, 0.16), transparent 60%),
    radial-gradient(900px 420px at 85% 0%, rgba(45, 212, 191, 0.12), transparent 55%),
    linear-gradient(140deg, #f8fafc 0%, #eef2ff 45%, #ecfeff 100%);
  color: var(--md-on-surface);
  font-family: var(--md-font-family);
  animation: m3-fade 0.6s ease-out both;
}

@media (prefers-reduced-motion: reduce) {
  .m3-shell {
    animation: none;
  }
}

/* 自定义样式 */
.line-clamp-1 {
  display: -webkit-box;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.line-clamp-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.line-clamp-3 {
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* 自定义滚动条 */
::-webkit-scrollbar {
  width: 6px;
}

::-webkit-scrollbar-track {
  background: var(--md-surface-container);
  border-radius: 3px;
}

::-webkit-scrollbar-thumb {
  background: var(--md-outline);
  border-radius: 3px;
}

::-webkit-scrollbar-thumb:hover {
  background: var(--md-on-surface-variant);
}

/* 动画效果 */
@keyframes m3-fade {
  from {
    opacity: 0;
    transform: translateY(18px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>
