<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { api, ApiError } from '../api'
import { acknowledgeWrite, sendWrite } from '../writes'
import { useDrafts } from '../persistence'
import ConceptNetwork from './ConceptNetwork.vue'
import Icon from './Icon.vue'
import { entityColors, entityLabels, relationLabels } from '../knowledgeGraph'
import type {
  EntityKind,
  GraphNeighborhood,
  GraphPath,
  GraphSummary,
  KnowledgeEntity,
  KnowledgeGraph,
  RelationKind,
} from '../knowledgeGraph'

const props = defineProps<{ mapId?: string; mode?: string }>()
const emit = defineEmits<{ open: [id: string]; settings: []; saving: [value: boolean] }>()
const topic = ref('')
const graph = ref<KnowledgeGraph | null>(null)
const history = ref<GraphSummary[]>([])
const loading = ref(false)
const generating = ref(false)
const querying = ref(false)
const error = ref('')
const historyError = ref('')
const legacyTopic = ref('')
const selectedId = ref('')
const selectedEdgeId = ref('')
const visibleIds = ref<Set<string> | null>(null)
const query = ref('')
const kind = ref<EntityKind | ''>('')
const searchResults = ref<KnowledgeEntity[]>([])
const searchError = ref('')
const enabledRelations = ref<RelationKind[]>(Object.keys(relationLabels) as RelationKind[])
const labels = ref(true)
const view = ref<'network' | 'entities'>('network')
const pathTarget = ref('')
const path = ref<GraphPath | null>(null)
const detail = ref<HTMLElement | null>(null)
const network = ref<InstanceType<typeof ConceptNetwork> | null>(null)
const input = ref<HTMLInputElement | null>(null)
const drafts = useDrafts()
drafts.bind(
  () => 'concept-graph',
  () => ({ topic: topic.value }),
  (value) => {
    topic.value = String(value.topic)
  }
)
let mounted = true
let version = 0
let selectionVersion = 0
let searchTimer = 0
let searchController: AbortController | null = null
const entities = computed(() => graph.value?.entities || [])
const relations = computed(() => graph.value?.relations || [])
const selected = computed(() => entities.value.find((node) => node.id === selectedId.value))
const selectedEdge = computed(() =>
  relations.value.find((edge) => edge.id === selectedEdgeId.value)
)
const localRelations = computed(() =>
  relations.value.filter(
    (edge) => edge.source === selectedId.value || edge.target === selectedId.value
  )
)
const visibleEntities = computed(() =>
  entities.value.filter(
    (node) =>
      (!visibleIds.value || visibleIds.value.has(node.id)) &&
      (!kind.value || node.kind === kind.value)
  )
)
const visibleRelations = computed(() => {
  const ids = new Set(visibleEntities.value.map((node) => node.id))
  return relations.value.filter(
    (edge) =>
      enabledRelations.value.includes(edge.kind) && ids.has(edge.source) && ids.has(edge.target)
  )
})
const availableKinds = computed(() => [...new Set(relations.value.map((edge) => edge.kind))])
const availableNeighbors = computed(() => {
  if (!visibleIds.value) return 0
  return new Set(
    localRelations.value
      .filter((edge) => enabledRelations.value.includes(edge.kind))
      .flatMap((edge) => [edge.source, edge.target])
      .filter((id) => !visibleIds.value!.has(id))
  ).size
})
const lookup = (id: string) => entities.value.find((node) => node.id === id)
const relationParams = () => enabledRelations.value.map((value) => `relation=${value}`).join('&')

function chooseTopic(value: string) {
  topic.value = value
  input.value?.focus()
}

async function loadHistory() {
  try {
    const result = await api<GraphSummary[]>('/graphs')
    if (mounted) {
      history.value = result
      historyError.value = ''
    }
  } catch {
    if (mounted) historyError.value = '已保存图谱暂时无法读取。'
  }
}

async function load(id?: string) {
  const sequence = ++version
  selectionVersion++
  searchController?.abort()
  graph.value = null
  error.value = ''
  legacyTopic.value = ''
  query.value = ''
  kind.value = ''
  path.value = null
  pathTarget.value = ''
  selectedEdgeId.value = ''
  visibleIds.value = null
  if (!id) {
    loading.value = false
    return
  }
  loading.value = true
  try {
    const result = await api<KnowledgeGraph>(`/graphs/${encodeURIComponent(id)}`)
    if (!mounted || sequence !== version) return
    graph.value = result
    selectedId.value = result.focus_id
    enabledRelations.value = [...new Set(result.relations.map((edge) => edge.kind))]
    searchResults.value = result.entities
  } catch (e) {
    if (!mounted || sequence !== version) return
    if (e instanceof ApiError && e.status === 404) {
      try {
        const old = await api<{ topic: string }>(`/roadmaps/${encodeURIComponent(id)}`)
        if (mounted && sequence === version) {
          legacyTopic.value = old.topic
          topic.value = old.topic
        }
      } catch {
        if (mounted && sequence === version) error.value = (e as Error).message
      }
    } else error.value = (e as Error).message
  } finally {
    if (mounted && sequence === version) loading.value = false
  }
}

async function generate() {
  if (generating.value || !topic.value.trim()) return
  const sequence = version,
    original = topic.value
  generating.value = true
  error.value = ''
  emit('saving', true)
  try {
    const { result, entry } = await sendWrite<KnowledgeGraph>(
      '/graphs',
      { topic: original.trim() },
      'concept-graph',
      '构建概念知识图谱'
    )
    drafts.clearSubmitted('concept-graph', { topic: original })
    acknowledgeWrite(entry)
    if (mounted && sequence === version) emit('open', result.id)
  } catch (e) {
    if (mounted && sequence === version) error.value = (e as Error).message
  } finally {
    generating.value = false
    if (mounted) emit('saving', false)
  }
}

async function search() {
  const sequence = version
  searchController?.abort()
  searchError.value = ''
  if (!graph.value) return
  const controller = new AbortController()
  searchController = controller
  try {
    const result = await api<KnowledgeEntity[]>(
      `/graphs/${graph.value.id}/entities?q=${encodeURIComponent(query.value)}${kind.value ? `&kind=${kind.value}` : ''}`,
      { signal: controller.signal }
    )
    if (mounted && sequence === version && !controller.signal.aborted) searchResults.value = result
  } catch (e) {
    if (mounted && sequence === version && !controller.signal.aborted) {
      searchError.value = (e as Error).message
      searchResults.value = []
    }
  }
}

async function select(id: string, locate = false) {
  selectionVersion++
  selectedId.value = id
  selectedEdgeId.value = ''
  path.value = null
  pathTarget.value = ''
  if (locate) {
    if (visibleIds.value && !visibleIds.value.has(id))
      visibleIds.value = new Set([...visibleIds.value, id])
    kind.value = ''
    await nextTick()
    network.value?.locate(id)
  }
}

async function neighbors(expand: boolean, id = selectedId.value) {
  if (!graph.value || !id || querying.value) return
  if (!enabledRelations.value.length) {
    visibleIds.value = new Set([id])
    return
  }
  const sequence = version,
    choice = ++selectionVersion
  querying.value = true
  error.value = ''
  path.value = null
  selectedEdgeId.value = ''
  try {
    const result = await api<GraphNeighborhood>(
      `/graphs/${graph.value.id}/neighbors/${id}?depth=1&${relationParams()}`
    )
    if (!mounted || sequence !== version || choice !== selectionVersion) return
    selectedId.value = id
    kind.value = ''
    visibleIds.value = new Set([
      ...(expand ? visibleIds.value || entities.value.map((node) => node.id) : []),
      ...result.entities.map((node) => node.id),
    ])
  } catch (e) {
    if (mounted && sequence === version) error.value = (e as Error).message
  } finally {
    if (mounted && sequence === version) querying.value = false
  }
}

async function findPath() {
  if (!graph.value || !pathTarget.value || !selectedId.value || querying.value) return
  const sequence = version,
    choice = ++selectionVersion
  querying.value = true
  error.value = ''
  selectedEdgeId.value = ''
  path.value = null
  try {
    const result = enabledRelations.value.length
      ? await api<GraphPath>(
          `/graphs/${graph.value.id}/path?source=${selectedId.value}&target=${pathTarget.value}&direction=both&${relationParams()}`
        )
      : { found: false, entity_ids: [], relation_ids: [], direction: 'both' }
    if (!mounted || sequence !== version || choice !== selectionVersion) return
    path.value = result
    if (result.found) {
      visibleIds.value = null
      kind.value = ''
    }
  } catch (e) {
    if (mounted && sequence === version) error.value = (e as Error).message
  } finally {
    if (mounted && sequence === version) querying.value = false
  }
}

function showRelation(id: string) {
  selectionVersion++
  selectedEdgeId.value = id
  path.value = null
}
function fullGraph() {
  visibleIds.value = null
  kind.value = ''
  path.value = null
  selectedId.value = graph.value?.focus_id || ''
  selectedEdgeId.value = ''
}
function exportGraph() {
  if (!graph.value) return
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(graph.value, null, 2)], { type: 'application/json;charset=utf-8' })
  )
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `${graph.value.topic.replace(/[<>:"/\\|?*\x00-\x1f]/g, '_')}-knowledge-graph.json`
  anchor.click()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}
watch(
  () => props.mapId,
  (id) => {
    void load(id)
  },
  { immediate: true }
)
watch([query, kind], () => {
  window.clearTimeout(searchTimer)
  searchTimer = window.setTimeout(search, 220)
})
watch(
  enabledRelations,
  () => {
    selectionVersion++
    path.value = null
    selectedEdgeId.value = ''
  },
  { deep: true }
)
onMounted(() => {
  void loadHistory()
})
onUnmounted(() => {
  if (generating.value) emit('saving', false)
  mounted = false
  version++
  searchController?.abort()
  window.clearTimeout(searchTimer)
})
</script>

<template>
  <div class="kg-page">
    <section class="kg-input" :class="{ compact: graph }">
      <p v-if="!graph" class="kg-eyebrow">KNOWLEDGE IS CONNECTED</p>
      <h1>{{ graph ? '继续探索你的好奇心' : '看见知识之间的联系。' }}</h1>
      <p v-if="!graph" class="kg-intro-text">
        输入想学的领域，发现其中的概念、方法、工具，以及它们如何相互关联。
      </p>
      <form @submit.prevent="generate">
        <Icon name="graph" :size="22" /><label class="sr-only" for="concept-topic"
          >你想学什么？</label
        ><input
          id="concept-topic"
          ref="input"
          v-model="topic"
          :disabled="generating"
          maxlength="200"
          required
          placeholder="例如：我想学习机器学习"
        /><button class="button primary" :disabled="generating || !topic.trim()">
          <span v-if="generating" class="spinner"></span
          >{{ generating ? '正在构建…' : '构建知识图谱'
          }}<Icon v-if="!generating" name="arrow" :size="16" />
        </button>
      </form>
      <div v-if="!graph" class="kg-suggestions">
        <span>从这些领域开始</span
        ><button
          v-for="example in ['机器学习', 'Python', 'AI Agent', '前端开发']"
          :key="example"
          :disabled="generating"
          @click="chooseTopic(example)"
        >
          {{ example }} ↗
        </button>
      </div>
      <p v-if="generating" class="kg-progress" role="status">
        正在识别概念、建立语义关系并保存到知识库。你可以离开页面，完成后在历史中查看。
      </p>
      <div v-if="legacyTopic" class="kg-legacy" role="status">
        「{{
          legacyTopic
        }}」是上一版课程路线。主题已填入上方，点击“构建知识图谱”生成新的概念关系网络。
      </div>
      <div v-if="error" class="alert error" role="alert">
        <span>{{ error }}</span
        ><button v-if="mode === 'demo'" class="text-button" @click="emit('settings')">
          模型设置</button
        ><button v-if="mapId && !graph && !legacyTopic" class="text-button" @click="load(mapId)">
          重试读取
        </button>
      </div>
    </section>
    <div v-if="loading" class="kg-loading" role="status">
      <span class="spinner"></span>正在读取知识实体与关系…
    </div>

    <template v-else-if="graph">
      <header class="kg-heading">
        <div>
          <p class="kg-eyebrow">EXPLORE THE CONNECTIONS</p>
          <h2>{{ graph.topic }}</h2>
          <p>{{ graph.summary }}</p>
        </div>
        <button class="button secondary" @click="exportGraph">
          <Icon name="download" :size="16" />导出图数据
        </button>
        <div class="kg-stats">
          <span
            ><b>{{ graph.entity_count }}</b> 个实体</span
          ><span
            ><b>{{ graph.relation_count }}</b> 条关系</span
          ><span
            ><b>{{ availableKinds.length }}</b> 种语义关系</span
          ><span class="kg-provenance"><i></i>{{ graph.provenance.label }}</span>
        </div>
      </header>

      <section class="kg-explorer" aria-label="概念知识图谱">
        <div class="kg-toolbar">
          <div class="kg-tabs" role="group" aria-label="图谱展示方式">
            <button
              :class="{ active: view === 'network' }"
              :aria-pressed="view === 'network'"
              @click="view = 'network'"
            >
              <Icon name="graph" :size="15" />关系网络</button
            ><button
              :class="{ active: view === 'entities' }"
              :aria-pressed="view === 'entities'"
              @click="view = 'entities'"
            >
              <Icon name="list" :size="15" />实体与关系
            </button>
          </div>
          <div class="kg-search">
            <Icon name="search" :size="16" /><label class="sr-only" for="entity-search"
              >搜索知识实体或别名</label
            ><input
              id="entity-search"
              v-model="query"
              placeholder="搜索概念 / 别名，如 GD"
            /><button
              v-if="query"
              class="icon-button"
              aria-label="清除实体搜索"
              @click="query = ''"
            >
              <Icon name="close" :size="13" />
            </button>
          </div>
          <label class="kg-kind"
            ><span class="sr-only">筛选实体类型</span
            ><select v-model="kind">
              <option value="">全部实体</option>
              <option v-for="(label, key) in entityLabels" :key="key" :value="key">
                {{ label }}
              </option>
            </select></label
          >
        </div>
        <div class="kg-filterbar">
          <span>关系</span
          ><label
            v-for="key in availableKinds"
            :key="key"
            :class="{ checked: enabledRelations.includes(key) }"
            ><input
              v-model="enabledRelations"
              type="checkbox"
              :value="key"
              :aria-label="`显示${relationLabels[key]}关系`"
            />{{ relationLabels[key] }}</label
          ><label class="kg-labels"><input v-model="labels" type="checkbox" />关系标签</label>
        </div>
        <div class="kg-body">
          <div class="kg-main">
            <div v-if="query || searchError" class="kg-results" aria-label="实体搜索结果">
              <p v-if="searchError" role="alert">{{ searchError }}</p>
              <p v-else-if="!searchResults.length">没有匹配的实体，试试中文名或英文别名。</p>
              <button
                v-for="node in searchResults"
                :key="node.id"
                :class="{ selected: selectedId === node.id }"
                @click="select(node.id, true)"
              >
                <i :style="{ background: entityColors[node.kind] }"></i>{{ node.name
                }}<small>{{ node.aliases.join(' · ') || entityLabels[node.kind] }}</small
                ><Icon name="arrow" :size="13" />
              </button>
            </div>
            <template v-if="view === 'network'"
              ><ConceptNetwork
                ref="network"
                :entities="visibleEntities"
                :relations="visibleRelations"
                :focus-id="graph.focus_id"
                :selected-id="selectedId"
                :selected-edge="selectedEdgeId"
                :path-nodes="path?.entity_ids || []"
                :path-edges="path?.relation_ids || []"
                :labels="labels"
                @select="select($event)"
                @relation="showRelation"
                @expand="neighbors(true, $event)"
              />
              <div class="kg-network-footer">
                <div>
                  <span v-for="(label, key) in entityLabels" :key="key"
                    ><i :style="{ background: entityColors[key] }"></i>{{ label }}</span
                  >
                </div>
                <span>显示 {{ visibleEntities.length }} / {{ graph.entity_count }} 个实体</span
                ><button class="text-button" @click="fullGraph">恢复全图</button>
              </div></template
            >
            <div v-else class="kg-entity-list" aria-label="知识实体列表">
              <p>按知识实体浏览。选择一个概念，查看它与其他知识的语义关系。</p>
              <button
                v-for="node in query ? searchResults : visibleEntities"
                :key="node.id"
                :class="{ selected: selectedId === node.id }"
                @click="select(node.id)"
              >
                <i :style="{ background: entityColors[node.kind] }"></i
                ><span
                  ><strong>{{ node.name }}</strong
                  ><small>{{ node.description }}</small></span
                ><span class="kg-list-kind">{{ entityLabels[node.kind] }}</span
                ><Icon name="arrow" :size="15" />
              </button>
            </div>
            <div v-if="path" class="kg-path-result" role="status">
              <template v-if="path.found"
                ><strong>关联路径 · {{ path.relation_ids.length }} 跳</strong>
                <p>按连接查找，以下语义方向保留原始事实：</p>
                <button
                  v-for="edgeId in path.relation_ids"
                  :key="edgeId"
                  @click="showRelation(edgeId)"
                >
                  <template
                    v-for="edge in relations.filter((item) => item.id === edgeId)"
                    :key="edge.id"
                    >{{ lookup(edge.source)?.name }} <b>—{{ edge.label }}→</b>
                    {{ lookup(edge.target)?.name }}</template
                  >
                </button></template
              >
              <p v-else>在当前关系筛选下，两个实体之间没有关联路径。</p>
            </div>
          </div>

          <aside ref="detail" class="kg-detail" aria-label="知识详情" aria-live="polite">
            <template v-if="selectedEdge"
              ><div class="kg-detail-caption">
                关系详情<button class="text-button" @click="selectedEdgeId = ''">返回实体</button>
              </div>
              <div class="kg-triple">
                <button @click="select(selectedEdge.source, true)">
                  {{ lookup(selectedEdge.source)?.name }}</button
                ><span>— {{ selectedEdge.label }} →</span
                ><button @click="select(selectedEdge.target, true)">
                  {{ lookup(selectedEdge.target)?.name }}
                </button>
              </div>
              <h4>这条关系说明了什么</h4>
              <p>{{ selectedEdge.explanation }}</p>
              <h4>关系类型</h4>
              <p>
                {{ selectedEdge.label }} <code>{{ selectedEdge.kind }}</code>
              </p>
              <p class="kg-source">{{ selectedEdge.provenance.label }}</p></template
            >
            <template v-else-if="selected"
              ><div class="kg-detail-caption">
                <span
                  ><i :style="{ background: entityColors[selected.kind] }"></i
                  >{{ entityLabels[selected.kind] }}</span
                ><span>{{ localRelations.length }} 条关联</span>
              </div>
              <h3>{{ selected.name }}</h3>
              <p v-if="selected.aliases.length" class="kg-aliases">
                {{ selected.aliases.join(' / ') }}
              </p>
              <p class="kg-definition">{{ selected.description }}</p>
              <div class="kg-example">
                <span>一个例子</span>
                <p>{{ selected.properties.example }}</p>
              </div>
              <h4>为什么要理解它</h4>
              <p>{{ selected.properties.learning_reason }}</p>
              <div class="kg-detail-actions">
                <button :disabled="querying" @click="neighbors(false)">
                  <Icon name="target" :size="14" />聚焦一度关系</button
                ><button :disabled="querying || !availableNeighbors" @click="neighbors(true)">
                  展开邻居{{ availableNeighbors ? ` +${availableNeighbors}` : '' }}
                </button>
              </div>
              <h4>
                知识关系 <span>{{ localRelations.length }}</span>
              </h4>
              <div class="kg-assertions">
                <button
                  v-for="edge in localRelations"
                  :key="edge.id"
                  :class="{ incoming: edge.target === selected.id }"
                  @click="showRelation(edge.id)"
                >
                  <span>{{ edge.source === selected.id ? edge.label : `← ${edge.label}` }}</span
                  ><strong>{{
                    lookup(edge.source === selected.id ? edge.target : edge.source)?.name
                  }}</strong
                  ><Icon name="arrow" :size="12" />
                </button>
              </div>
              <div class="kg-find-path">
                <h4>它与另一个概念如何关联？</h4>
                <label class="sr-only" for="path-target">关联路径终点</label
                ><select id="path-target" v-model="pathTarget">
                  <option value="">选择另一个知识实体</option>
                  <option
                    v-for="node in entities.filter((item) => item.id !== selectedId)"
                    :key="node.id"
                    :value="node.id"
                  >
                    {{ node.name }}
                  </option></select
                ><button :disabled="querying || !pathTarget" @click="findPath">
                  {{ querying ? '正在查询…' : '查找关联路径' }}<Icon name="arrow" :size="14" />
                </button>
              </div>
              <p class="kg-source">
                {{ selected.provenance.label
                }}<span v-if="selected.provenance.model"> · {{ selected.provenance.model }}</span>
              </p>
            </template>
          </aside>
        </div>
      </section>
      <p class="kg-footnote">
        箭头表示关系的语义方向；虚线表示前置依赖。关联路径用于理解知识联系，不表示学习顺序。
      </p>
    </template>
    <section v-if="!graph && !loading && !mapId" class="kg-start-note">
      <Icon name="graph" :size="34" />
      <div>
        <h2>围绕一个概念，向外发现更多。</h2>
        <p>
          每个实体有定义、别名和例子；每条连线有明确含义。点开概念、追踪联系，逐步理解整个知识领域。
        </p>
      </div>
    </section>
    <section v-if="history.length || historyError" class="kg-history">
      <h2>
        已保存的知识图谱 <span>{{ history.length }}</span
        ><button v-if="graph" class="text-button" @click="emit('open', '')">
          探索新的主题 <Icon name="plus" :size="14" />
        </button>
      </h2>
      <p v-if="historyError">
        {{ historyError }}<button class="text-button" @click="loadHistory">重试</button>
      </p>
      <div>
        <button
          v-for="item in history"
          :key="item.id"
          :class="{ active: item.id === graph?.id }"
          @click="emit('open', item.id)"
        >
          <Icon name="graph" :size="23" /><span
            ><strong>{{ item.topic }}</strong
            ><small>{{ item.entity_count }} 个实体 · {{ item.relation_count }} 条关系</small></span
          ><Icon name="arrow" :size="15" />
        </button>
      </div>
    </section>
    <p v-if="!graph && mode === 'demo'" class="kg-footnote">
      当前使用内置示例知识库。<button class="text-button" @click="emit('settings')">
        接入 AI 构建其他领域
      </button>
    </p>
  </div>
</template>

<style scoped>
.kg-page {
  max-width: 1450px;
  margin: auto;
  padding-bottom: 20px;
}
.kg-input {
  max-width: 960px;
  margin: 20px auto 38px;
}
.kg-eyebrow {
  font-size: 9px;
  letter-spacing: 2.5px;
  color: #91a382;
  margin: 0 0 14px;
}
.kg-input h1 {
  font-family: 'SimSun', serif;
  font-size: clamp(27px, 3vw, 40px);
  letter-spacing: 1px;
  font-weight: 600;
  margin: 0 0 18px;
}
.kg-intro-text {
  font-size: 13px;
  line-height: 1.9;
  color: #85947a;
  margin-bottom: 27px;
}
.kg-input form {
  display: flex;
  align-items: center;
  gap: 14px;
  border: 1px solid #bdcdb3;
  border-radius: 10px;
  padding: 9px 10px 9px 20px;
  background: #fff;
  box-shadow: 0 3px 18px #3d581e07;
}
.kg-input form > svg {
  flex-shrink: 0;
  color: #8a9f78;
}
.kg-input input {
  min-width: 0;
  flex: 1;
  padding: 12px 0;
  border: 0;
  outline: none;
  box-shadow: none;
  background: transparent;
  font-size: 13px;
}
.kg-input input:focus {
  box-shadow: none;
}
.kg-input input::placeholder {
  color: #a1ab97;
}
.kg-input form:focus-within {
  outline: 2px solid #bdcdb335;
  border-color: #759766;
}
.kg-input .button {
  white-space: nowrap;
  font-size: 12px;
  padding: 13px 18px;
}
.kg-input.compact {
  max-width: none;
  margin: 0 0 24px;
}
.compact h1 {
  font-family: inherit;
  font-size: 15px;
  font-weight: 500;
  color: #8a977e;
  margin-bottom: 14px;
}
.kg-suggestions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 16px;
  align-items: center;
  font-size: 10px;
  color: #9ba58f;
}
.kg-suggestions button {
  border: 1px solid #e1e8d4;
  background: #f0f4e7;
  border-radius: 5px;
  color: #859875;
  padding: 7px 12px;
  font-size: 11px;
}
.kg-progress,
.kg-legacy {
  padding: 15px;
  font-size: 12px;
  color: #7a8d69;
  background: #edf3e4;
  border-radius: 8px;
  line-height: 1.9;
}
.kg-input .alert {
  margin-top: 18px;
  flex-wrap: wrap;
}
.kg-loading {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 15px;
  min-height: 200px;
  color: #88987a;
  font-size: 13px;
}
.kg-heading {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 18px;
  padding: 23px 0;
  border-top: 1px solid #e1e7d8;
}
.kg-heading h2 {
  font-size: 25px;
  line-height: 1.5;
  margin: 0 0 9px;
  overflow-wrap: anywhere;
}
.kg-heading p:not(.kg-eyebrow) {
  color: #87957b;
  font-size: 12px;
  line-height: 1.8;
  margin: 0;
}
.kg-heading > button {
  align-self: center;
  font-size: 11px;
}
.kg-stats {
  grid-column: 1 / -1;
  display: flex;
  align-items: center;
  gap: 25px;
  color: #8e9b80;
  font-size: 11px;
}
.kg-stats b {
  color: #4e6b40;
  font-size: 18px;
  font-weight: 500;
  margin-right: 3px;
}
.kg-provenance {
  margin-left: auto;
  font-size: 10px;
  display: flex;
  align-items: center;
  gap: 6px;
}
.kg-provenance i {
  background: #a3b58c;
  width: 5px;
  height: 5px;
  border-radius: 50%;
}
.kg-explorer {
  background: white;
  border: 1px solid #dce4d2;
  border-radius: 12px;
  overflow: hidden;
}
.kg-toolbar {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 13px 16px;
  border-bottom: 1px solid #e4e9dc;
}
.kg-tabs {
  display: flex;
  gap: 2px;
  background: #f2f5ec;
  padding: 3px;
  border-radius: 6px;
  flex-shrink: 0;
}
.kg-tabs button {
  padding: 8px 11px;
  background: transparent;
  border: 0;
  border-radius: 4px;
  display: flex;
  align-items: center;
  gap: 6px;
  color: #8d9b7d;
  font-size: 11px;
}
.kg-tabs button.active {
  background: white;
  color: #54784a;
  box-shadow: 0 1px 4px #2c401212;
}
.kg-search {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
  background: #f8faf5;
  border: 1px solid #e5ebdc;
  border-radius: 6px;
  padding: 0 10px;
  min-width: 0;
  width: 245px;
}
.kg-search > svg {
  color: #a2b18f;
  flex-shrink: 0;
}
.kg-search input {
  border: 0;
  box-shadow: none;
  background: transparent;
  padding: 9px 0;
  font-size: 10px;
  min-width: 0;
  width: 100%;
}
.kg-search .icon-button {
  width: 20px;
  height: 20px;
  padding: 0;
}
.kg-kind select {
  border-color: #e2e9d7;
  background: #fff;
  border-radius: 6px;
  font-size: 10px;
  color: #8a9a78;
  padding: 8px;
  min-height: 34px;
}
.kg-filterbar {
  display: flex;
  align-items: center;
  gap: 7px;
  flex-wrap: wrap;
  padding: 12px 17px;
  border-bottom: 1px solid #e7ecdf;
}
.kg-filterbar > span {
  font-size: 10px;
  color: #a0ac92;
  margin-right: 4px;
}
.kg-filterbar label {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
  border: 1px solid #edf0e8;
  color: #a1ad94;
  background: #fafbf8;
  padding: 5px 8px;
  border-radius: 5px;
  font-size: 9px;
}
.kg-filterbar label.checked {
  border-color: #dce6d1;
  background: #f0f5e9;
  color: #7c9663;
}
.kg-filterbar input {
  width: 11px;
  height: 11px;
  margin: 0;
  accent-color: #7f9c6c;
}
.kg-filterbar .kg-labels {
  margin-left: auto;
  border: 0;
  background: transparent;
}
.kg-body {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 274px;
}
.kg-main {
  min-width: 0;
  position: relative;
  background: #f8faf6;
}
.kg-results {
  padding: 10px 15px;
  border-bottom: 1px solid #e5ebdc;
  background: #fff;
  max-height: 200px;
  overflow: auto;
}
.kg-results button {
  display: flex;
  gap: 9px;
  align-items: center;
  width: 100%;
  text-align: left;
  padding: 11px;
  border: 0;
  background: #fafcf7;
  color: #5d7848;
  font-size: 12px;
  border-radius: 6px;
  margin-bottom: 4px;
}
.kg-results button.selected {
  background: #ecf3e2;
}
.kg-results i,
.kg-detail-caption i {
  height: 7px;
  width: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}
.kg-results small {
  margin-left: auto;
  font-size: 9px;
  color: #9cae8b;
}
.kg-results p {
  color: #9ba98e;
  font-size: 11px;
}
.kg-network-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px;
  padding: 13px 16px;
  border-top: 1px solid #e6ebde;
  font-size: 9px;
  color: #95a287;
  background: #fbfcf8;
}
.kg-network-footer > div {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.kg-network-footer > div span {
  display: flex;
  align-items: center;
  gap: 4px;
}
.kg-network-footer i {
  width: 7px;
  height: 7px;
  border-radius: 50%;
}
.kg-network-footer .text-button {
  font-size: 9px;
}
.kg-detail {
  border-left: 1px solid #e0e7d5;
  padding: 21px 19px;
  max-height: 695px;
  overflow: auto;
  overflow-wrap: anywhere;
}
.kg-detail-caption {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  color: #9fac90;
  font-size: 10px;
}
.kg-detail-caption > span:first-child {
  display: flex;
  align-items: center;
  gap: 6px;
}
.kg-detail-caption .text-button {
  font-size: 10px;
}
.kg-detail h3 {
  font-size: 22px;
  margin: 17px 0 8px;
  line-height: 1.5;
}
.kg-detail p {
  font-size: 11px;
  line-height: 1.9;
  color: #849578;
  margin: 10px 0;
}
.kg-detail .kg-aliases {
  font-size: 10px;
  color: #a9b59a;
  margin: 0 0 13px;
}
.kg-definition {
  margin-top: 17px !important;
}
.kg-example {
  background: #f4f7ed;
  border-radius: 7px;
  padding: 12px;
  margin: 18px 0;
}
.kg-example > span {
  font-size: 9px;
  letter-spacing: 1px;
  color: #9caf87;
}
.kg-example p {
  margin-bottom: 0;
  font-size: 10px;
}
.kg-detail h4 {
  color: #647c50;
  font-size: 11px;
  font-weight: 500;
  margin: 20px 0 8px;
}
.kg-detail h4 > span {
  color: #a3b28d;
  font-size: 10px;
  margin-left: 4px;
}
.kg-detail-actions {
  display: flex;
  gap: 7px;
  margin: 18px 0;
}
.kg-detail-actions button {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  background: #f0f5e7;
  color: #7d9864;
  border: 1px solid #dce7ce;
  font-size: 9px;
  border-radius: 5px;
  padding: 9px 6px;
  flex: 1;
  white-space: nowrap;
}
.kg-detail-actions button:disabled {
  opacity: 0.5;
  cursor: default;
}
.kg-assertions {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.kg-assertions button {
  display: flex;
  align-items: center;
  gap: 7px;
  width: 100%;
  text-align: left;
  border: 1px solid #e8eddf;
  background: #fff;
  border-radius: 5px;
  padding: 9px 8px;
  color: #819b68;
  font-size: 10px;
}
.kg-assertions button:hover {
  border-color: #bacda5;
  background: #f8fbf2;
}
.kg-assertions button > span {
  background: #f1f5eb;
  color: #97ab80;
  padding: 3px 5px;
  font-size: 8px;
  border-radius: 3px;
  white-space: nowrap;
}
.kg-assertions strong {
  font-weight: 400;
}
.kg-assertions svg {
  flex-shrink: 0;
  margin-left: auto;
}
.kg-find-path {
  border-top: 1px solid #e8eddf;
  margin-top: 20px;
  padding-top: 1px;
}
.kg-find-path select {
  width: 100%;
  font-size: 10px;
  color: #859c6b;
  border-color: #e2e9d7;
  border-radius: 5px;
  padding: 8px;
}
.kg-find-path button {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  margin-top: 9px;
  border: 1px solid #e0e8d5;
  color: #7d9666;
  background: #f5f8ee;
  font-size: 10px;
  padding: 9px;
  border-radius: 5px;
}
.kg-find-path button:disabled {
  opacity: 0.5;
}
.kg-detail .kg-source {
  margin-top: 19px;
  font-size: 9px;
  color: #a8b499;
}
.kg-triple {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 13px;
  margin: 28px 0;
}
.kg-triple button {
  padding: 10px 12px;
  border: 1px solid #dce6d0;
  border-radius: 7px;
  font-size: 15px;
  background: #f7faf1;
  color: #5f7f47;
}
.kg-triple > span {
  color: #b79b72;
  font-size: 12px;
}
.kg-detail code {
  font-size: 10px;
  color: #a4b58f;
  margin-left: 8px;
}
.kg-entity-list {
  max-height: 695px;
  overflow: auto;
  padding: 18px;
}
.kg-entity-list > p {
  font-size: 11px;
  color: #9aab8b;
  margin: 0 0 15px;
  line-height: 1.8;
}
.kg-entity-list button {
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 16px;
  border: 1px solid #e1e9d5;
  background: #fff;
  margin-bottom: 8px;
  border-radius: 7px;
  width: 100%;
  text-align: left;
  color: #597c40;
}
.kg-entity-list button.selected {
  border-color: #a1bb8a;
  background: #f3f8eb;
}
.kg-entity-list i {
  width: 13px;
  height: 13px;
  border-radius: 50%;
  flex-shrink: 0;
}
.kg-entity-list strong {
  font-size: 12px;
  font-weight: 500;
  display: block;
}
.kg-entity-list small {
  font-size: 10px;
  line-height: 1.9;
  display: block;
  color: #8fa27b;
  margin-top: 6px;
}
.kg-list-kind {
  margin-left: auto;
  font-size: 9px;
  color: #a1b28c;
  white-space: nowrap;
}
.kg-entity-list svg {
  flex-shrink: 0;
}
.kg-path-result {
  background: #fffaf0;
  border-top: 1px solid #eaddc2;
  padding: 18px;
  font-size: 11px;
  color: #9d895f;
}
.kg-path-result strong {
  font-weight: 500;
}
.kg-path-result p {
  font-size: 10px;
  line-height: 1.8;
}
.kg-path-result button {
  display: block;
  border: 0;
  background: transparent;
  color: #99845d;
  font-size: 11px;
  padding: 8px 0;
  text-align: left;
}
.kg-path-result b {
  font-weight: 400;
  color: #ba9b64;
  font-size: 10px;
}
.kg-footnote {
  color: #a1af92;
  font-size: 10px;
  line-height: 1.9;
  margin: 17px 0;
}
.kg-footnote .text-button {
  font-size: 10px;
}
.kg-start-note {
  display: flex;
  align-items: center;
  gap: 25px;
  padding: 37px;
  background: #eef3e4;
  border: 1px solid #e4ebd7;
  border-radius: 12px;
  color: #9db08a;
}
.kg-start-note > svg {
  flex-shrink: 0;
}
.kg-start-note h2 {
  color: #6d8757;
  font-weight: 500;
  font-size: 18px;
  margin: 0 0 13px;
}
.kg-start-note p {
  font-size: 12px;
  line-height: 1.9;
  margin: 0;
  max-width: 600px;
}
.kg-history {
  margin-top: 30px;
}
.kg-history h2 {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 14px;
  font-weight: 500;
  margin-bottom: 15px;
}
.kg-history h2 > span {
  font-size: 10px;
  color: #b0bda0;
}
.kg-history h2 > button {
  margin-left: auto;
  font-size: 10px;
}
.kg-history > p {
  font-size: 11px;
  color: #ac946f;
}
.kg-history > div {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}
.kg-history > div button {
  display: flex;
  align-items: center;
  gap: 13px;
  padding: 19px;
  border: 1px solid #e1e8d6;
  background: #fcfdf8;
  border-radius: 8px;
  text-align: left;
  color: #96ad7b;
}
.kg-history > div button.active {
  border-color: #b1c29e;
  background: #f2f7e9;
}
.kg-history > div button > span {
  min-width: 0;
}
.kg-history > div button > svg {
  flex-shrink: 0;
}
.kg-history strong {
  font-size: 12px;
  color: #718d57;
  font-weight: 400;
  display: block;
  overflow-wrap: anywhere;
}
.kg-history small {
  font-size: 9px;
  color: #a0b18c;
  display: block;
  margin-top: 6px;
}
.kg-history > div button > svg:last-child {
  margin-left: auto;
}
@media (max-width: 1150px) {
  .kg-body {
    grid-template-columns: minmax(0, 1fr) 245px;
  }
  .kg-detail {
    padding: 18px 15px;
  }
  .kg-search {
    width: 210px;
  }
  .kg-toolbar {
    gap: 8px;
  }
  .kg-kind select {
    max-width: 100px;
  }
  .kg-history > div {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 760px) {
  .kg-input {
    margin: 12px 0 28px;
  }
  .kg-input h1 {
    font-size: 28px;
    line-height: 1.5;
  }
  .kg-input .kg-intro-text {
    font-size: 12px;
    margin-bottom: 20px;
  }
  .kg-input form {
    display: grid;
    grid-template-columns: 22px minmax(0, 1fr);
    padding: 12px;
    gap: 7px;
  }
  .kg-input .button {
    grid-column: 1 / -1;
    justify-content: center;
  }
  .compact h1 {
    font-size: 14px;
  }
  .kg-suggestions {
    gap: 7px;
  }
  .kg-suggestions > span {
    display: none;
  }
  .kg-suggestions button {
    font-size: 10px;
    padding: 7px 10px;
  }
  .kg-heading {
    grid-template-columns: minmax(0, 1fr);
    gap: 15px;
  }
  .kg-heading h2 {
    font-size: 22px;
  }
  .kg-heading > button {
    justify-self: start;
    padding: 9px 12px;
  }
  .kg-stats {
    flex-wrap: wrap;
    gap: 16px;
    font-size: 10px;
  }
  .kg-provenance {
    margin-left: 0;
  }
  .kg-stats b {
    font-size: 16px;
  }
  .kg-toolbar {
    flex-wrap: wrap;
    padding: 12px;
  }
  .kg-tabs {
    order: 0;
  }
  .kg-kind {
    order: 1;
    margin-left: auto;
  }
  .kg-search {
    order: 2;
    margin-left: 0;
    width: 100%;
    margin-top: 4px;
  }
  .kg-filterbar {
    gap: 5px;
    padding: 10px 12px;
  }
  .kg-filterbar label {
    font-size: 9px;
    padding: 5px 6px;
  }
  .kg-filterbar .kg-labels {
    margin-left: 0;
  }
  .kg-body {
    grid-template-columns: minmax(0, 1fr);
  }
  .kg-detail {
    border-left: 0;
    border-top: 1px solid #e0e7d5;
    max-height: none;
    padding: 23px;
  }
  .kg-network-footer {
    font-size: 8px;
    padding: 12px;
  }
  .kg-network-footer > div {
    gap: 10px;
  }
  .kg-results small {
    max-width: 110px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .kg-entity-list {
    padding: 13px;
    max-height: 420px;
  }
  .kg-entity-list button {
    padding: 13px 10px;
    gap: 9px;
  }
  .kg-list-kind {
    display: none;
  }
  .kg-start-note {
    padding: 25px;
    gap: 16px;
    align-items: flex-start;
  }
  .kg-start-note h2 {
    font-size: 16px;
    line-height: 1.8;
  }
  .kg-start-note p {
    font-size: 11px;
  }
  .kg-history > div {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
