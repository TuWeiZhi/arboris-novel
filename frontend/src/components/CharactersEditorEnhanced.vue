<!-- AIMETA P=增强角色编辑器_增强版角色编辑|R=增强角色编辑|NR=不含基础功能|E=component:CharactersEditorEnhanced|X=internal|A=增强编辑器|D=vue|S=dom|RD=./README.ai -->
<template>
  <div class="space-y-4 max-h-[600px] overflow-y-auto p-1">
    <div v-for="(character, index) in localCharacters" :key="index" class="p-4 border border-gray-200 rounded-lg bg-gray-50 relative">
      <button @click="removeCharacter(index)" class="absolute top-2 right-2 text-red-400 hover:text-red-600 transition-colors p-1">
        <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
          <path fill-rule="evenodd" d="M9 2a1 1 0 00-.894.553L7.382 4H4a1 1 0 000 2v10a2 2 0 002 2h8a2 2 0 002-2V6a1 1 0 100-2h-3.382l-.724-1.447A1 1 0 0011 2H9zM7 8a1 1 0 012 0v6a1 1 0 11-2 0V8zm4 0a1 1 0 012 0v6a1 1 0 11-2 0V8z" clip-rule="evenodd" />
        </svg>
      </button>
      
      <!-- 基础信息 -->
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label class="block text-sm font-medium text-gray-600 mb-1">姓名</label>
          <input type="text" v-model="character.name" class="w-full p-1 border-b-2 border-gray-300 focus:border-indigo-500 outline-none transition bg-transparent" />
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-600 mb-1">身份</label>
          <input type="text" v-model="character.identity" class="w-full p-1 border-b-2 border-gray-300 focus:border-indigo-500 outline-none transition bg-transparent" />
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-600 mb-1">性格</label>
          <input type="text" v-model="character.personality" class="w-full p-1 border-b-2 border-gray-300 focus:border-indigo-500 outline-none transition bg-transparent" />
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-600 mb-1">目标</label>
          <input type="text" v-model="character.goals" class="w-full p-1 border-b-2 border-gray-300 focus:border-indigo-500 outline-none transition bg-transparent" />
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-600 mb-1">能力</label>
          <input type="text" v-model="character.abilities" class="w-full p-1 border-b-2 border-gray-300 focus:border-indigo-500 outline-none transition bg-transparent" />
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-600 mb-1">与主角关系</label>
          <input type="text" v-model="character.relationship_to_protagonist" class="w-full p-1 border-b-2 border-gray-300 focus:border-indigo-500 outline-none transition bg-transparent" />
        </div>
      </div>

      <!-- DNA档案展开按钮 + AI 生成 -->
      <div class="mt-4 border-t border-gray-200 pt-3 flex items-center justify-between">
        <button 
          @click="toggleDNA(index)" 
          class="flex items-center gap-2 text-sm font-medium text-purple-600 hover:text-purple-800 transition-colors"
        >
          <svg 
            xmlns="http://www.w3.org/2000/svg" 
            class="h-4 w-4 transition-transform" 
            :class="{ 'rotate-90': expandedDNA[index] }"
            fill="none" 
            viewBox="0 0 24 24" 
            stroke="currentColor"
          >
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
          </svg>
          <span>🧬 角色DNA档案</span>
          <span class="text-xs text-gray-400">(让角色更立体)</span>
        </button>
        <button
          v-if="props.projectId"
          @click="generateDNA(index)"
          :disabled="!!generatingDNA[index]"
          class="text-xs px-2 py-1 rounded-md bg-purple-600 text-white hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {{ generatingDNA[index] ? '生成中...' : '✨ AI 生成' }}
        </button>
      </div>

      <!-- DNA档案内容 -->
      <transition name="slide">
        <div v-if="expandedDNA[index]" class="mt-3 p-4 bg-purple-50 rounded-lg border border-purple-200">
          <div class="grid grid-cols-1 gap-4">
            <!-- 童年经历 -->
            <div>
              <label class="block text-sm font-medium text-purple-700 mb-1">
                童年经历/创伤
                <span class="text-xs text-gray-500 font-normal ml-1">影响角色的防御机制和情感触发点</span>
              </label>
              <textarea 
                v-model="getDNAProfile(character).childhood_trauma" 
                @input="updateDNA(character, 'childhood_trauma', ($event.target as HTMLTextAreaElement).value)"
                placeholder="例如：父母离异后由祖母抚养，从小学会察言观色，害怕被抛弃"
                class="w-full p-2 border border-purple-200 rounded-md focus:border-purple-500 focus:ring-1 focus:ring-purple-500 outline-none transition bg-white text-sm"
                rows="2"
              ></textarea>
            </div>

            <!-- 核心恐惧 -->
            <div>
              <label class="block text-sm font-medium text-purple-700 mb-1">
                核心恐惧
                <span class="text-xs text-gray-500 font-normal ml-1">驱动角色行为的深层恐惧</span>
              </label>
              <input 
                type="text"
                v-model="getDNAProfile(character).core_fear"
                @input="updateDNA(character, 'core_fear', ($event.target as HTMLInputElement).value)"
                placeholder="例如：害怕被抛弃、害怕失控、害怕不被爱"
                class="w-full p-2 border border-purple-200 rounded-md focus:border-purple-500 focus:ring-1 focus:ring-purple-500 outline-none transition bg-white text-sm"
              />
            </div>

            <!-- 内心渴望 -->
            <div>
              <label class="block text-sm font-medium text-purple-700 mb-1">
                内心渴望
                <span class="text-xs text-gray-500 font-normal ml-1">角色真正想要的，可能连自己都不清楚</span>
              </label>
              <input 
                type="text"
                v-model="getDNAProfile(character).inner_desire"
                @input="updateDNA(character, 'inner_desire', ($event.target as HTMLInputElement).value)"
                placeholder="例如：渴望被认可、渴望归属感、渴望证明自己"
                class="w-full p-2 border border-purple-200 rounded-md focus:border-purple-500 focus:ring-1 focus:ring-purple-500 outline-none transition bg-white text-sm"
              />
            </div>

            <!-- 说话习惯 -->
            <div>
              <label class="block text-sm font-medium text-purple-700 mb-1">
                说话习惯
                <span class="text-xs text-gray-500 font-normal ml-1">口头禅、语气词、紧张时的变化</span>
              </label>
              <textarea 
                v-model="getDNAProfile(character).speech_habits"
                @input="updateDNA(character, 'speech_habits', ($event.target as HTMLTextAreaElement).value)"
                placeholder="例如：喜欢用反问句，紧张时语速加快，常说'怎么说呢...'"
                class="w-full p-2 border border-purple-200 rounded-md focus:border-purple-500 focus:ring-1 focus:ring-purple-500 outline-none transition bg-white text-sm"
                rows="2"
              ></textarea>
            </div>

            <!-- 身体语言 -->
            <div>
              <label class="block text-sm font-medium text-purple-700 mb-1">
                身体语言
                <span class="text-xs text-gray-500 font-normal ml-1">紧张时的小动作、特有的姿态</span>
              </label>
              <textarea 
                v-model="getDNAProfile(character).body_language"
                @input="updateDNA(character, 'body_language', ($event.target as HTMLTextAreaElement).value)"
                placeholder="例如：紧张时会摸耳朵，思考时喜欢转笔，说谎时不敢直视对方"
                class="w-full p-2 border border-purple-200 rounded-md focus:border-purple-500 focus:ring-1 focus:ring-purple-500 outline-none transition bg-white text-sm"
                rows="2"
              ></textarea>
            </div>

            <!-- 思维模式 -->
            <div>
              <label class="block text-sm font-medium text-purple-700 mb-1">
                思维模式
                <span class="text-xs text-gray-500 font-normal ml-1">理性/感性、乐观/悲观</span>
              </label>
              <select 
                v-model="getDNAProfile(character).thinking_pattern"
                @change="updateDNA(character, 'thinking_pattern', ($event.target as HTMLSelectElement).value)"
                class="w-full p-2 border border-purple-200 rounded-md focus:border-purple-500 focus:ring-1 focus:ring-purple-500 outline-none transition bg-white text-sm"
              >
                <option value="">请选择...</option>
                <option value="理性分析型，遇事先冷静思考">理性分析型</option>
                <option value="直觉感受型，跟着感觉走">直觉感受型</option>
                <option value="乐观主义者，总能看到希望">乐观主义者</option>
                <option value="悲观主义者，习惯做最坏打算">悲观主义者</option>
                <option value="全局思考型，喜欢从大局出发">全局思考型</option>
                <option value="细节关注型，注重每个细节">细节关注型</option>
              </select>
            </div>

            <!-- 决策方式 -->
            <div>
              <label class="block text-sm font-medium text-purple-700 mb-1">
                决策方式
                <span class="text-xs text-gray-500 font-normal ml-1">如何做出选择</span>
              </label>
              <select 
                v-model="getDNAProfile(character).decision_style"
                @change="updateDNA(character, 'decision_style', ($event.target as HTMLSelectElement).value)"
                class="w-full p-2 border border-purple-200 rounded-md focus:border-purple-500 focus:ring-1 focus:ring-purple-500 outline-none transition bg-white text-sm"
              >
                <option value="">请选择...</option>
                <option value="快速决断，不喜欢犹豫">快速决断型</option>
                <option value="反复权衡，考虑各种可能">深思熟虑型</option>
                <option value="依赖逻辑，用数据说话">逻辑驱动型</option>
                <option value="依赖情感，跟着心走">情感驱动型</option>
                <option value="喜欢独立决策，不爱听别人意见">独立决策型</option>
                <option value="喜欢征求他人意见再做决定">群策群力型</option>
              </select>
            </div>

            <!-- 隐藏的秘密 -->
            <div>
              <label class="block text-sm font-medium text-purple-700 mb-1">
                隐藏的秘密
                <span class="text-xs text-gray-500 font-normal ml-1">不愿让人知道的事</span>
              </label>
              <textarea 
                v-model="getDNAProfile(character).hidden_secret"
                @input="updateDNA(character, 'hidden_secret', ($event.target as HTMLTextAreaElement).value)"
                placeholder="例如：曾经因为自己的失误导致好友受伤，一直心怀愧疚"
                class="w-full p-2 border border-purple-200 rounded-md focus:border-purple-500 focus:ring-1 focus:ring-purple-500 outline-none transition bg-white text-sm"
                rows="2"
              ></textarea>
            </div>
          </div>

          <!-- DNA完成度提示 -->
          <div class="mt-4 flex items-center gap-2">
            <div class="flex-1 bg-gray-200 rounded-full h-2">
              <div 
                class="bg-purple-500 h-2 rounded-full transition-all duration-300"
                :style="{ width: getDNACompleteness(character) + '%' }"
              ></div>
            </div>
            <span class="text-xs text-gray-500">{{ getDNACompleteness(character) }}% 完成</span>
          </div>
          <p class="mt-2 text-xs text-gray-500">
            💡 提示：DNA档案越完整，AI生成的角色行为和对话就越真实立体
          </p>
        </div>
      </transition>
    </div>
    
    <button @click="addCharacter" class="w-full mt-4 px-4 py-2 text-sm font-medium text-indigo-600 bg-indigo-50 border border-indigo-200 rounded-md hover:bg-indigo-100 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500">
      + 添加新角色
    </button>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, reactive, nextTick } from 'vue';
import { NovelAPI } from '@/api/novel';
import { globalAlert } from '@/composables/useAlert';

interface DNAProfile {
  childhood_trauma: string;
  core_fear: string;
  inner_desire: string;
  speech_habits: string;
  body_language: string;
  thinking_pattern: string;
  decision_style: string;
  hidden_secret: string;
}

interface Character {
  name: string;
  identity: string;
  personality: string;
  goals: string;
  abilities: string;
  relationship_to_protagonist: string;
  extra?: {
    dna_profile?: DNAProfile;
    [key: string]: any;
  };
}

const props = defineProps({
  modelValue: {
    type: Array as () => Character[],
    default: () => []
  },
  projectId: {
    type: String,
    default: ''
  }
});

const emit = defineEmits(['update:modelValue']);

const localCharacters = ref<Character[]>([]);
const expandedDNA = reactive<Record<number, boolean>>({});
const generatingDNA = reactive<Record<number, boolean>>({});
let syncing = false;

// 初始化DNA档案
const initDNAProfile = (): DNAProfile => ({
  childhood_trauma: '',
  core_fear: '',
  inner_desire: '',
  speech_habits: '',
  body_language: '',
  thinking_pattern: '',
  decision_style: '',
  hidden_secret: ''
});

// 获取角色的DNA档案
const getDNAProfile = (character: Character): DNAProfile => {
  if (!character.extra) {
    character.extra = {};
  }
  if (!character.extra.dna_profile) {
    character.extra.dna_profile = initDNAProfile();
  }
  return character.extra.dna_profile;
};

// 更新DNA字段
const updateDNA = (character: Character, field: keyof DNAProfile, value: string) => {
  const profile = getDNAProfile(character);
  profile[field] = value;
  // 触发更新
  emit('update:modelValue', JSON.parse(JSON.stringify(localCharacters.value)));
};

// 计算DNA完成度
const getDNACompleteness = (character: Character): number => {
  const profile = getDNAProfile(character);
  const fields = Object.values(profile);
  const filledFields = fields.filter(v => v && v.trim().length > 0);
  return Math.round((filledFields.length / fields.length) * 100);
};

// 切换DNA展开状态
const toggleDNA = (index: number) => {
  expandedDNA[index] = !expandedDNA[index];
};

// 调用后端生成角色 DNA 档案
const generateDNA = async (index: number) => {
  const character = localCharacters.value[index];
  if (!character || !character.name.trim()) {
    globalAlert.showError('请先填写角色姓名');
    return;
  }
  if (!props.projectId) return;

  generatingDNA[index] = true;
  try {
    const updatedProject = await NovelAPI.generateCharacterDNA(props.projectId, character.name);
    const returnedChar = (updatedProject.blueprint?.characters || []).find(
      (item: any) => item.name === character.name
    ) as any;
    const dna = returnedChar?.extra?.dna_profile;
    if (dna) {
      character.extra = character.extra || {};
      character.extra.dna_profile = dna;
      expandedDNA[index] = true;
      emit('update:modelValue', JSON.parse(JSON.stringify(localCharacters.value)));
      globalAlert.showSuccess(`角色「${character.name}」的 DNA 档案生成完成`);
    } else {
      globalAlert.showError('生成完成，但未返回有效 DNA 档案');
    }
  } catch (error) {
    console.error('生成角色 DNA 失败:', error);
    globalAlert.showError(`生成角色 DNA 失败：${error instanceof Error ? error.message : '未知错误'}`);
  } finally {
    generatingDNA[index] = false;
  }
};

watch(() => props.modelValue, (newVal) => {
  syncing = true;
  localCharacters.value = JSON.parse(JSON.stringify(newVal || []));
  nextTick(() => {
    syncing = false;
  });
}, { immediate: true });

watch(localCharacters, (newVal) => {
  if (syncing) return;
  emit('update:modelValue', JSON.parse(JSON.stringify(newVal)));
}, { deep: true });

const addCharacter = () => {
  localCharacters.value.push({ 
    name: '', 
    identity: '', 
    personality: '', 
    goals: '', 
    abilities: '', 
    relationship_to_protagonist: '',
    extra: {
      dna_profile: initDNAProfile()
    }
  });
};

const removeCharacter = (index: number) => {
  localCharacters.value.splice(index, 1);
  delete expandedDNA[index];
};
</script>

<style scoped>
.slide-enter-active,
.slide-leave-active {
  transition: all 0.3s ease;
}

.slide-enter-from,
.slide-leave-to {
  opacity: 0;
  max-height: 0;
  overflow: hidden;
}

.slide-enter-to,
.slide-leave-from {
  opacity: 1;
  max-height: 1000px;
}
</style>
