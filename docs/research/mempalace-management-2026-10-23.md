# mysoul 的 MemPalace 原生管理接入调查

核查时间：2026-10-23（Asia/Shanghai）。本次只读检查代码、运行状态和索引元数据，没有修改运行中的记忆或应用代码。

## 实际实现

应用位于 `C:/Users/Administrator/.codex/worktrees/mysoul-v01/mysoul`，分支 `codex/mysoul-v01`。Desktop 下的主检出仍是规划文件，不能据其 README 判断当前实现。应用工作树有其他未提交改动，后续实施须保留。

- `src/mysoul/mempalace.py` 启动完整 `mempalace.mcp_server`，检查固定提交 `f41e8e75ddaadf5588d5127715fa531d79eadb45`，动态读取 MCP schema。
- 适配层仅使用 `mempalace_add_drawer`、`mempalace_search`、`mempalace_get_drawer`。
- `wing(scope)` 使用权限范围的散列；写入 room 使用 evidence ID 的散列。目的之一是避免相同正文、不同来源被上游去重成同一条记录。
- 搜索将远端命中映射回本地 evidence，并检查 scope；get 验证远端正文与本地原文完全一致。
- `src/mysoul/api.py` 只开放 memory/search；长期记忆 UI 只有状态与搜索，没有原生结构浏览。
- `service.memory_status()` 的 delivered 统计本地 memory_ref 映射，并非原生索引抽屉数量。

## 运行验证

读取 `http://127.0.0.1:8767/api/status`：backend 为 mempalace，状态 connected，pending 为 0，模型为 embeddinggemma，revision 为上述固定提交。

使用 SQLite `mode=ro` 读取当前 palace 的 metadata segment，仅聚合结构计数，没有加载向量引擎或修改数据库。该次快照有 1 个 wing、439 个 room、439 个按 parent_drawer_id 合并的逻辑抽屉、669 个物理行；669 行的 room 均以 `evidence-` 开头。计数随正在运行的服务写入变化，不同时间的 API 与数据库读数不是同一事务快照。

## 上游现成能力

在本地固定提交源码中确认：

| 工具 | 可接入的管理能力 |
| --- | --- |
| mempalace_get_taxonomy / list_wings / list_rooms | 真实 wing/room 结构和计数 |
| mempalace_list_drawers | 按 wing/room/日期过滤，offset/limit 分页；合并逻辑抽屉并给出预览 |
| mempalace_get_drawer | 逻辑抽屉全文和元数据 |
| mempalace_status | 索引状态；不能把其中协议提示直接作为页面文案 |
| mempalace_update_drawer | 修改正文、wing 或 room |
| mempalace_delete_drawer(s) | 删除抽屉 |
| graph_stats / list_hallways / list_tunnels | 关联结构检查，数据存在时才有实际内容 |

注意 taxonomy 的行计数与 list_drawers 合并后的逻辑数量口径不同，UI 必须明确标注。上游原生概念是 people/projects 为 wings、topics 为 rooms、内容位于 drawers；目前 mysoul 使用了不同的映射策略。

上游说明：https://github.com/MemPalace/mempalace

## 可选实施范围（待用户选择）

### A：原生结构浏览与诊断，建议先做

- 长期记忆页加入“宫殿浏览”，左侧 wing/room，右侧抽屉分页列表和详情；窄屏顺序展示。
- 保留真实 ID，将可确定的 scope 显示为可读名称；room 明确标为按证据划分，可用来源/预览辅助识别，不伪造主题分类。
- 列表只显示预览、来源、入库时间；详情显示全文、位置、逻辑 ID、分块信息及本地来源映射。
- 区分已同步证据、逻辑记忆、存储分块；提供手动刷新及明确的连接失败、能力不支持、空库和筛选无结果状态。
- 沿用现有 operator API 鉴权。全库结构与详情限管理端，不把全库工具开放给群聊或模型。
- 从当前进程的原生 MCP 接口取数据，不另造数据库分类树。
- 首期不改变已有写入、来源映射和存储位置。

### B：同时做主题分类和写入管理

在 A 上增加主题房间、移动、修改、删除，但必须一并实现：

- 持久化目标位置，让新写入、重试和重新同步使用同一位置；否则移动后重试会向旧房间再写一份。
- 保留同文不同事件的来源映射；不能直接删除当前“每条证据独立 room”的策略而忽视上游按 wing+room+content 去重。
- 修订正文时定义原始证据与修订内容的关系；否则现有 get 的完全一致性校验会拒绝读取。
- 删除时定义本地映射、同步队列及历史证据的处理，防止删除后重新回填。
- wing 绑定权限边界；主题组织不能打破私有与群聊的隔离。
- 旧数据迁移应有预览、恢复方案和重复执行验证。

## 后续修改点与验证

A 主要修改 `mempalace.py` 的管理读取接口、`api.py` 的管理路由、`web/index.html` / `web/app.js` / 页面样式。优先把新增浏览状态放到独立模块，避免继续扩大 app.js。

验证应覆盖原生响应字段、逻辑抽屉分页与分块计数、未知 ID 与权限边界、未接入/断开状态、筛选切换时过期响应不覆盖新结果、真实上游合成数据的列表到详情链路，以及桌面/窄屏。当前没有产品改动，因此没有声称这些实现测试已完成。
