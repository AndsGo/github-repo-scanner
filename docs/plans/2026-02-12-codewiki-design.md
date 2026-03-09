# CodeWiki Feature Design

> 为 github-repo-scanner 增加知识沉淀能力，将每次代码分析的理解持久化为结构化 wiki。

## 核心问题

代码库的知识是昂贵的（需要时间去阅读、理解、建立心智模型），但在当前架构中是"一次性"的。每次新对话都要重新探索同一个仓库的架构、关键模块、设计决策。

## 设计决策

| 维度 | 决策 | 第一性原理 |
|------|------|-----------|
| 核心目标 | 知识沉淀 | 消除重复理解的成本 |
| 生成策略 | L1 自动骨架 + L2-L3 对话增量 | 80% 起点 + 涌现式深化 |
| 存储形态 | JSON 索引 + Markdown 内容 | 关注点分离：导航 vs 内容 |
| 失效策略 | 乐观标记（stale flag） | 大多数变更不影响架构 |
| 消费模式 | 问题驱动按需加载 | 惰性求值，节省 context |
| 回流机制 | 对话结束时提议保存 | 分离探索模式与归档模式 |
| 存放位置 | 仓库缓存目录内部 `.codewiki/` | 就近原则，知识与代码共存 |

## 知识分层

| 层级 | 内容 | 生成方式 | 变化频率 |
|------|------|---------|---------|
| L0 | 文件结构、语言统计 | `repo_overview.py`（已有） | 随提交变化 |
| L1 | 模块职责、入口点、API 表面 | `generate_wiki.py` 自动静态分析 | 较稳定 |
| L2 | 架构设计、模块间关系、数据流 | 对话增量沉淀 | 稳定 |
| L3 | 设计决策的"为什么"、历史演变 | 对话增量沉淀 | 很稳定 |

## 目录结构与文件格式

```
D:\git\facebook\react\          <- 克隆的仓库
└── .codewiki\
    ├── index.json              <- 结构化索引（模块关系、stale 标记、元数据）
    ├── overview.md             <- 全局架构概述（L1 自动生成）
    └── modules\
        ├── react-reconciler.md <- 模块级文档（L1 自动 + L2/L3 增量）
        ├── react-dom.md
        └── scheduler.md
```

### index.json 结构

```json
{
  "version": 1,
  "repo": "facebook/react",
  "generated_at": "2026-02-12T10:00:00Z",
  "code_commit": "a1b2c3d",
  "modules": {
    "react-reconciler": {
      "path": "packages/react-reconciler",
      "file": "modules/react-reconciler.md",
      "summary": "Fiber 架构的核心协调器，负责 diff 和调度",
      "stale": false,
      "last_updated": "2026-02-12T10:00:00Z",
      "source": "auto"
    }
  },
  "architecture": {
    "patterns": ["monorepo", "workspace"],
    "entry_points": ["packages/react/index.js"],
    "key_relationships": [
      { "from": "react", "to": "react-reconciler", "type": "depends" }
    ]
  }
}
```

### 模块 Markdown 模板

```markdown
# <module-name>

> 自动生成于 YYYY-MM-DD | commit: <hash> | source: auto

## 职责
[一句话描述这个模块做什么]

## 关键文件
- `file.js` -- 描述

## 对外 API
[导出的公共接口列表]

## 对话补充（L2/L3）
[后续对话中沉淀的深层知识，带时间戳和主题标签]
```

## L1 自动生成流程

**触发时机：** 用户首次对一个仓库执行分析时，如果 `.codewiki/` 不存在，自动提议生成。

**脚本：** `scripts/generate_wiki.py`

**步骤：**

1. **识别模块边界**
   - monorepo -> `packages/*/`、`apps/*/` 各为一个模块
   - 单体项目 -> `src/` 下的一级目录各为一个模块
   - 回退策略 -> 顶层目录中包含代码文件的目录

2. **对每个模块静态分析提取**
   - 入口文件（index.js/main.py/__init__.py 等）
   - 导出的公共 API（export/module.exports/__all__）
   - 内部导入关系（模块间的 import/require）
   - 关键文件（按大小和导入频率排序）

3. **生成 index.json** -- 记录 commit hash，填充 modules 和 key_relationships

4. **生成 overview.md** -- 仓库用途、技术栈摘要、模块列表及一句话职责

5. **生成 modules/*.md** -- 用固定模板填充，标记 source: "auto"，「对话补充」留空

**关键设计：** L1 完全基于静态分析（AST 解析 + 正则匹配），不依赖 AI 推理。保证速度快、可重复、无 API 成本。

**命令接口：**

```bash
PYTHONIOENCODING=utf-8 python scripts/generate_wiki.py <clone_path>
# --force        覆盖已有 wiki
# --modules-only 只重新生成模块文件，保留对话补充
```

## Stale 标记机制

**集成到 `clone_repo.py` 的 git pull 流程：**

```
git pull 完成后:
1. 获取 pull 前后的 commit diff（git diff --name-only old_hash..new_hash）
2. 将变化的文件路径映射到 index.json 中的模块
3. 对受影响模块设置 stale: true
4. 更新 index.json 的 code_commit
5. 输出摘要: "Wiki: N 个模块被标记为 stale"
```

不自动重新生成。不删除已有内容。只标记。

## 对话消费流程

```
用户提问 -> AI 读取 index.json（<50行）
         -> 从问题识别相关模块
         -> 按需加载 modules/*.md
         -> 如有 stale 标记，告知用户并结合源码验证
         -> 回答问题
```

**降级策略：** 无 `.codewiki/` 时退回纯源码分析，分析完成后提议生成。

## 对话知识回流

### 触发时机

对话接近尾声时（用户表示结束、切换话题），AI 自动提议。

### 流程

1. AI 回顾对话中的新发现，分类为模块级/架构级/无归属
2. 格式化提议，列出具体要写入的内容和目标文件
3. 用户确认后写入

### 回流过滤规则

**只沉淀关于目标仓库本身的客观知识。** 对比性结论、业务决策、主观评价不写入 codewiki。

这在用户将 GitHub 仓库与自己的业务项目对比分析时尤为重要：
- "React 的 Scheduler 用 MessageChannel 实现时间切片" -> 写入 wiki
- "React 的调度策略比我们项目的方案更高效" -> 不写入 wiki

### 对话补充格式

```markdown
## 对话补充（L2/L3）

### 2026-02-12 -- 调度机制分析
- Scheduler 使用 MessageChannel 而非 setTimeout 实现时间切片，
  因为 MessageChannel 不受 4ms 最小延迟限制
- 优先级队列基于小顶堆（SchedulerMinHeap.js），支持 5 个优先级层级
```

每条补充必须是具体事实，带时间戳和主题标签，只追加不覆盖 L1 内容。

### 写入脚本

`scripts/update_wiki.py`

```bash
# 追加对话补充到指定模块
PYTHONIOENCODING=utf-8 python scripts/update_wiki.py <clone_path> \
    --module scheduler \
    --topic "调度机制分析" \
    --content "Scheduler 使用 MessageChannel..."

# 追加架构关系
PYTHONIOENCODING=utf-8 python scripts/update_wiki.py <clone_path> \
    --add-relationship "scheduler->react-reconciler:depends"

# 标记模块为 enriched
PYTHONIOENCODING=utf-8 python scripts/update_wiki.py <clone_path> \
    --module scheduler \
    --mark-enriched
```

## 工作流集成

```
Step 1: Discover/Clone      （不变）
Step 2: Overview             （不变）
Step 3: Wiki Check           （新增）
    +-- .codewiki/ 存在？
    |   +-- 是 -> 读取 index.json，告知用户 wiki 可用（含 stale 提示）
    |   +-- 否 -> 提议生成 codewiki
    |            +-- 同意 -> 运行 generate_wiki.py
    |            +-- 拒绝 -> 跳过，正常分析
Step 4: Analyze              （增强：优先查 wiki 索引定位模块）
Step 5: Knowledge Harvest    （新增：对话结束时提议回流）
```

## 新增/修改文件清单

| 文件 | 操作 | 职责 |
|------|------|------|
| `scripts/generate_wiki.py` | 新增 | L1 自动生成 |
| `scripts/update_wiki.py` | 新增 | 回流写入、关系更新、标记 |
| `scripts/clone_repo.py` | 修改 | git pull 后追加 stale 标记逻辑 |
| `references/analysis-guide.md` | 修改 | 新增 wiki 辅助分析章节 |
| `SKILL.md` | 修改 | 更新工作流，加入 Step 3 和 Step 5 |

## 不改的部分

- `scripts/search_repos.py` -- 不涉及 wiki
- `scripts/repo_overview.py` -- 保持独立，wiki 是更上层的知识
