<template>
  <div id="input-wrapper">
    <div id="file-preview-bar" v-if="selectedFiles.length">
      <div class="preview-chip" v-for="(f, i) in selectedFiles" :key="i">
        <span class="material-symbols-outlined" style="font-size:16px;">attach_file</span>
        <span>{{ f.name }}</span>
        <button class="close-btn" @click="selectedFiles.splice(i, 1)" title="移除附件">
          <span class="material-symbols-outlined" style="font-size:16px;">close</span>
        </button>
      </div>
    </div>

    <div id="input-area">
      <div
        v-if="methodMenuOpen"
        id="method-command-menu"
        class="method-menu"
        role="listbox"
        aria-label="可复用工作流"
      >
        <div v-if="loadingMethods" class="method-menu-state">正在加载工作流…</div>
        <div v-else-if="methodLoadError" class="method-menu-state error">
          {{ methodLoadError }}
        </div>
        <div v-else-if="!methodOptions.length" class="method-menu-state">
          没有匹配的工作流
        </div>
        <template v-else>
          <button
            v-for="(method, index) in methodOptions"
            :id="`method-option-${index}`"
            :key="method.name"
            type="button"
            class="method-option"
            :class="{ active: index === activeMethodIndex }"
            role="option"
            :aria-selected="index === activeMethodIndex"
            @mouseenter="activeMethodIndex = index"
            @mousedown.prevent="selectMethod(method)"
          >
            <span class="method-option-heading">
              <span class="method-command">/method:{{ method.name }}</span>
            </span>
          </button>
        </template>
      </div>

      <label class="btn" for="file-upload"><span class="material-symbols-outlined">attach_file</span></label>
      <input type="file" id="file-upload" multiple @change="onFileSelected">

      <textarea
        id="chat-input"
        v-model="inputText"
        rows="1"
        placeholder="问问 HaiTun"
        aria-autocomplete="list"
        :aria-expanded="methodMenuOpen"
        :aria-controls="methodMenuOpen ? 'method-command-menu' : undefined"
        :aria-activedescendant="activeMethodDescendant"
        @focus="restoreMethodMenu"
        @blur="dismissMethodMenu"
        @keydown="handleInputKeydown"
        @input="autoResizeInput"
      ></textarea>

      <ModelPanel
        @select-backend="$emit('select-backend', $event)"
        @delete-ai="$emit('delete-ai', $event)"
        @delete-router="$emit('delete-router', $event)"
      />

      <button v-if="streaming" class="send stop" @click="stopMessage" title="停止生成">
        <span class="material-symbols-outlined">stop</span>
      </button>
      <button v-else class="send" @click="submitMessage" title="发送消息">
        <span class="material-symbols-outlined">send</span>
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onUnmounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { listWorkspaceMethods } from '../api.js'
import { useChatStore } from '../stores/chat.js'
import { useSessionStore } from '../stores/session.js'
import { useUiStore } from '../stores/ui.js'
import { sendMessage, stopMessage } from '../composables/useChat.js'
import { resolveSessionWorkspace } from '../sessionList.js'
import {
  filterMethodOptions,
  formatMethodCommand,
  getMethodCommandQuery,
  moveMethodSelection,
  parseMethodCommand,
} from '../methodCommands.js'
import ModelPanel from './ModelPanel.vue'

const chat = useChatStore()
const { selectedFiles, inputText, uploadResetToken, streaming } = storeToRefs(chat)
const session = useSessionStore()
const {
  draftSession,
  gatewayCwd,
  selectedSessionId,
  selectedWorkspacePath,
  sessions,
} = storeToRefs(session)
const ui = useUiStore()

const methods = ref([])
const loadingMethods = ref(false)
const methodLoadError = ref('')
const activeMethodIndex = ref(0)
const dismissedMethodText = ref(null)
let methodRequestVersion = 0

defineEmits(['select-backend', 'delete-ai', 'delete-router'])

const activeWorkspacePath = computed(() => {
  if (draftSession.value?.workspace) return draftSession.value.workspace
  if (selectedSessionId.value) {
    const selectedSession = sessions.value.find(item => item.id === selectedSessionId.value)
    if (!selectedSession) return ''
    return resolveSessionWorkspace(selectedSession, gatewayCwd.value)
  }
  return selectedWorkspacePath.value || gatewayCwd.value
})

const methodQuery = computed(() => getMethodCommandQuery(inputText.value))
const methodOptions = computed(() => filterMethodOptions(methods.value, methodQuery.value ?? ''))
const methodMenuOpen = computed(() => (
  methodQuery.value !== null && dismissedMethodText.value !== inputText.value
))
const activeMethodDescendant = computed(() => {
  if (!methodMenuOpen.value || !methodOptions.value.length) return undefined
  return `method-option-${activeMethodIndex.value}`
})

function onFileSelected(e) {
  const files = Array.from(e.target.files || [])
  selectedFiles.value.push(...files)
}

function selectMethod(method) {
  const command = formatMethodCommand(method)
  inputText.value = command
  dismissedMethodText.value = command
  activeMethodIndex.value = 0
  nextTick(() => document.getElementById('chat-input')?.focus())
}

function dismissMethodMenu() {
  dismissedMethodText.value = inputText.value
}

function restoreMethodMenu() {
  dismissedMethodText.value = null
}

async function submitMessage() {
  const parsed = parseMethodCommand(inputText.value)
  if (parsed.kind === 'invalid') {
    ui.showAlert(parsed.error)
    return
  }
  if (parsed.kind === 'method' && selectedFiles.value.length) {
    ui.showAlert('工作流指令暂不支持同时发送附件；请先移除附件')
    return
  }
  dismissedMethodText.value = inputText.value
  await sendMessage()
}

function handleInputKeydown(event) {
  if (event.isComposing || event.keyCode === 229) return

  if (methodMenuOpen.value) {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      if (methodOptions.value.length) {
        event.preventDefault()
        const delta = event.key === 'ArrowDown' ? 1 : -1
        activeMethodIndex.value = moveMethodSelection(
          activeMethodIndex.value,
          methodOptions.value.length,
          delta,
        )
      }
      return
    }
    if (event.key === 'Escape') {
      event.preventDefault()
      dismissMethodMenu()
      return
    }
    if (
      event.key === 'Enter'
      && !event.shiftKey
      && !event.altKey
      && !event.ctrlKey
      && !event.metaKey
      && methodOptions.value.length
    ) {
      event.preventDefault()
      selectMethod(methodOptions.value[activeMethodIndex.value] || methodOptions.value[0])
      return
    }
  }

  if (
    event.key === 'Enter'
    && !event.shiftKey
    && !event.altKey
    && !event.ctrlKey
    && !event.metaKey
  ) {
    event.preventDefault()
    submitMessage()
  }
}

function autoResizeInput() {
  const el = document.getElementById('chat-input')
  if (!el) return
  el.style.height = 'auto'
  const borders = el.offsetHeight - el.clientHeight
  el.style.height = el.scrollHeight + borders + 'px'
}

watch(inputText, () => nextTick(autoResizeInput))

watch(methodOptions, () => {
  activeMethodIndex.value = methodOptions.value.length ? 0 : -1
})

watch(
  [methodQuery, activeWorkspacePath],
  async ([query, workspacePath], [previousQuery, previousWorkspacePath] = []) => {
    if (query === null || !workspacePath) {
      methodRequestVersion++
      loadingMethods.value = false
      methodLoadError.value = ''
      methods.value = []
      return
    }
    if (previousQuery !== null && previousWorkspacePath === workspacePath) return

    const requestVersion = ++methodRequestVersion
    loadingMethods.value = true
    methodLoadError.value = ''
    methods.value = []
    try {
      const result = await listWorkspaceMethods(workspacePath)
      if (requestVersion === methodRequestVersion) methods.value = result
    } catch (error) {
      if (requestVersion === methodRequestVersion) {
        methodLoadError.value = error.message || '工作流加载失败'
      }
    } finally {
      if (requestVersion === methodRequestVersion) loadingMethods.value = false
    }
  },
  { immediate: true },
)

watch(uploadResetToken, () => {
  const el = document.getElementById('file-upload')
  if (el) el.value = ''
})

onUnmounted(() => {
  methodRequestVersion++
})
</script>

<style scoped>
#input-wrapper {
  background: transparent; border-top: none;
  display: flex; flex-direction: column;
  padding: 0 16px 16px; align-items: center;
  transition: background 0.25s, border-color 0.25s;
}
#file-preview-bar { display: flex; width: 100%; max-width: 820px; padding: 0 0 8px; }
.preview-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: var(--md-surface-container-high);
  border: 1px solid var(--md-primary);
  border-radius: 8px;
  padding: 4px 10px;
  font-size: 12px;
  color: var(--md-primary);
}
.preview-chip .close-btn {
  background: none; border: none; color: var(--md-text-secondary);
  cursor: pointer; display: flex; align-items: center; padding: 2px; border-radius: 50%;
}
.preview-chip .close-btn:hover { background: rgba(0,0,0,0.05); color: var(--md-text-error); }

#input-area {
  width: 100%; max-width: 820px;
  position: relative;
  display: flex; gap: 8px; align-items: center;
  background: var(--md-surface-container);
  border: 1px solid var(--md-outline-variant);
  border-radius: var(--g-pill-radius);
  padding: 8px 10px 8px 14px;
}
#input-area textarea {
  flex: 1; background: transparent; border: none; outline: none;
  color: var(--md-text-primary); font-size: 16px; font-family: inherit;
  resize: none; min-height: 28px; max-height: 160px; padding: 6px 4px;
}
#input-area textarea:focus { border: none; }
#input-area label.btn {
  background: transparent; color: var(--md-primary); border: none; border-radius: var(--md-shape-full);
  width: 40px; height: 40px; display: flex; align-items: center; justify-content: center;
  cursor: pointer; transition: background 0.2s;
}
#input-area label.btn:hover { background: var(--md-surface-variant); }
#input-area input[type=file] { display: none; }
#input-area button.send {
  background: var(--md-primary); color: var(--md-on-primary); border: none; border-radius: var(--md-shape-full);
  width: 40px; height: 40px; display: flex; align-items: center; justify-content: center;
  cursor: pointer; transition: all 0.2s; box-shadow: 0 1px 3px rgba(0,0,0,0.1); flex-shrink: 0;
}
#input-area button.send:hover:not(:disabled) { filter: brightness(1.1); transform: scale(1.05); }
#input-area button.send:disabled { opacity: .4; cursor: default; box-shadow: none; }
#input-area button.send.stop { background: var(--md-text-error, #d32f2f); color: #fff; }

.method-menu {
  position: absolute;
  left: 0;
  right: 0;
  bottom: calc(100% + 8px);
  z-index: 30;
  max-height: 320px;
  overflow-y: auto;
  padding: 6px;
  border: 1px solid var(--md-outline-variant);
  border-radius: var(--md-shape-large);
  background: var(--md-surface-container-high);
  box-shadow: var(--md-elevation-2);
}
.method-option {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 10px 12px;
  border: none;
  border-radius: var(--md-shape-medium);
  background: transparent;
  color: var(--md-text-primary);
  font: inherit;
  text-align: left;
  cursor: pointer;
}
.method-option:hover,
.method-option.active {
  background: var(--md-surface-variant);
}
.method-option-heading {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.method-command {
  color: var(--md-primary);
  font-family: monospace;
  font-weight: 600;
}
.method-menu-state {
  color: var(--md-text-secondary);
  font-size: 12px;
}
.method-menu-state {
  padding: 14px 12px;
}
.method-menu-state.error {
  color: var(--md-text-error);
}

@media (max-width: 768px) {
  #input-wrapper {
    position: fixed;
    left: 0; right: 0;
    bottom: 0;
    z-index: 25;
    background: var(--md-surface-container);
    border-top: 1px solid var(--md-outline-variant);
  }
  #input-area {
    padding: 8px 12px;
    padding-bottom: calc(8px + env(safe-area-inset-bottom));
    gap: 8px;
  }
  #file-preview-bar { padding: 6px 12px 0; }
}

@media (max-width: 400px) {
  #input-area { gap: 6px; }
}
</style>
