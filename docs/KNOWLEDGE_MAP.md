# 概念知识图谱

2026-11-03：根据用户纠正，首页改为实体与语义关系的探索界面。领域术语见 [CONTEXT.md](../CONTEXT.md)。

## 数据模型

知识实体是可独立定义的概念、方法、工具或应用，例如“向量”“梯度下降”“NumPy”。实体包含名称、类型、别名、定义、具体例子、学习理由和来源标记。

关系表达明确的有向语义，例如“梯度下降—优化→损失函数”“线性回归—依赖→向量”“线性回归—应用于→房价预测”。支持 is_a 是一种、part_of 属于、requires 依赖、uses 使用、optimizes 优化、measures 衡量、applied_to 应用于、contrasts 区别于。每条关系独立保存解释及来源，允许多对多、同一对实体的不同关系和语义环。前置知识只是其中一种关系。

## 存储与查询

数据库版本为 `0007_concept_graph`，新增 `concept_graphs`（主题及中心实体）、`knowledge_entities`（实体身份、属性、别名）、`knowledge_relations`（源实体、类型、目标实体、解释与来源）。

这是属性图模型，使用项目现有 SQLite / PostgreSQL 持久化。查询层从带索引的实体与关系表计算邻域及最短关联路径。实体身份限定在各自图谱，不同图谱尚未自动消歧合并。创建在事务中完成并支持幂等回执；校验实体引用、重复实体或关系、孤立节点、文本合法性及多种关系类型。

| 接口 | 用途 |
| --- | --- |
| `POST /api/graphs` | 只输入 `{"topic":"机器学习"}`，构建并保存图谱，支持幂等键 |
| `GET /api/graphs` | 已保存图谱摘要与实体/关系计数 |
| `GET /api/graphs/{id}` | 完整实体、关系、属性、别名及来源 |
| `GET /api/graphs/{id}/entities?q=GD&kind=method` | 按名称、键或别名搜索，可筛选类型 |
| `GET /api/graphs/{id}/neighbors/{entity_id}?depth=1&direction=both&relation=requires` | 1–3 度邻域，支持入边、出边、双向及关系筛选 |
| `GET /api/graphs/{id}/path?source=...&target=...&direction=both` | 最短关联路径，返回经过的实体与关系 ID |

relation 参数可重复；不存在的路径返回 found:false。查询不允许混入其他图谱的实体。双向路径按连接查找，但每条边仍保留事实的原始方向，不等于因果路径或学习顺序。

## 前端交互

Cytoscape.js 3.34.4 提供画布、COSE 力导向布局与交互。圆形实体按类型着色，边显示语义标签和箭头，前置依赖用虚线。

支持节点拖拽、缩放、键盘平移、重新布局、实体/别名搜索、实体类型与关系类型筛选、节点与关系详情、聚焦一度邻域、展开隐藏邻居、关联路径高亮、实体列表及 JSON 图数据导出。展开邻居读取已经保存的关系，不产生新知识事实。实体列表提供键盘可达入口，手机上下排列图和详情，网络代码按需加载。

## 来源和范围

内置示例包含机器学习（31 实体 / 45 关系）、Python、前端和 AI Agent，标为“内置知识库 · 示例”。不匹配的主题保留输入并提示。配置模型后通过现有兼容接口生成其他主题，标为“AI 生成 · 待核验”，不声称已经检索或验证事实。当前没有外部知识源自动检索，真实模型尚未付费联调，协议和 schema 使用 mock HTTP 验证。

浏览图谱不会增加掌握度；当前未自动把实体转换为学习单元。课程学习和其证据保留在原有页面。

## 旧版及本地预览

旧版 roadmaps 表、API 和 0006 结构定义保留用于恢复旧课程路线。旧的流程图 UI 和布局代码已移除。打开旧路线 URL 会明确提示，填入原主题，允许重新构建概念图谱。

demo 服务运行在 8000 / 5173。升级前备份为 `.cache/local/demo-before-concept-graph-20261103.db`，正式学习库未改动。机器学习预览 ID：`996e8534-00b2-4bee-b788-496d19fee3e0`，通过 `/#/map/{id}` 打开。

## 实现入口

- `backend/app/services/concept_graph.py`：实体与关系 schema、语义校验、模型请求。
- `backend/app/services/concept_catalog.py`：内置实体与关系。
- `backend/app/graph_store.py`：属性图持久化、搜索、邻域与路径。
- `frontend/src/components/KnowledgeGraphView.vue`：探索、查询和详情。
- `frontend/src/components/ConceptNetwork.vue`：Cytoscape.js 画布。
- `backend/tests/test_concept_graph.py`、`tests/browser/knowledge-graph.spec.ts`：数据与实际画布交互验证。
