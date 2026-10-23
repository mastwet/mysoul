# 自动归档、按需回忆实施计划

Goal: 自动归档与内部向量索引保留，取消隐式召回；模型按需调用只读记忆工具。
Architecture: ContextAssembler不执行search；共享MemoryTools负责scope、分页、输出预算；聊天使用ActivityDecision.memory_call有界循环，工作复用dispatcher。
Constraints: Python3.12/uv；保留既有未提交改动；不向网关发送额外私有诊断回放；真实测试使用临时索引。

- [ ] Task1: 写入不发生隐式检索的失败测试；实现memory_search(query,limit=5,max10,preview<=300)及memory_get(ref,offset=0,length=2000,max4000)，明确分页/故障/无权限及预算状态；聚焦验证并提交。
- [ ] Task2: 用失败测试覆盖search/get/答复、零额外调用、3次读取后收尾、整轮超时及epoch打断；实现共享聊天/自主循环与工作工具；读取结果不进入memory_queue或认知来源，重放不重复追加；聚焦验证并提交。
- [ ] Task3: 覆盖群聊隐私、候选隔离、自动归档、重启、手动检索；真实完整引擎和公开合成模型验证；全量Python/UI/Ruff/构建；独立只读最终审查及修复；完整停机备份并部署，记录结果。

Default: 工作读取继续服从Goal步骤/时间/token限制；普通聊天/心跳最多3次读取+1次收尾；源范围由运行时注入，返回保留时间/来源/截断标记；无自动fallback。
