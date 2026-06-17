# CR Agent

基于 Google ADK 的自动化代码 Review 系统，支持 GitLab MR。

## 快速开始

```bash
# 安装依赖
uv sync

# 配置环境变量
cp .env.example .env  # 填写 GITLAB_TOKEN、GITLAB_URL、CR_MODEL、REPOS_DIR

# 运行（指定 repo）
python -m adk.run --pr <MR_URL> --repo <本地仓库路径>

# 运行（配置 REPOS_DIR 后可省略 --repo，自动从 PR URL 推断项目名）
python -m adk.run --pr https://gitlab.shalltry.com/inputmethod/latincore/-/merge_requests/78
```

**`REPOS_DIR` 自动检测规则**：从 PR URL 提取项目名（`latincore`），拼接为 `$REPOS_DIR/latincore`。目录名须与 GitLab 项目名一致。

## ADK Pipeline 流程

```
PR URL
  │
  ▼
[git_client]  — Python, 0 token
  • GitLab API 拉取 diff
  • 过滤非代码文件（.xml/.json/.md/.png 等）
  • 按 ~40K chars 切分为多个 batch
  产物：List[str] batches

  │
  ▼（每个 batch 独立处理）
[_filter_test_files]  — Python, 0 token
  • 过滤测试文件（/test/、Test.kt、_test.go 等）
  • 支持 "diff --git" 和 GitLab API "--- path" 两种格式
  • 若 batch 全是测试文件 → 整个 batch 跳过
  产物：filtered_diff（仅生产代码）

  │
  ▼
[diff_reader_agent]  — LLM
  • 将 raw diff 解析为结构化 JSON
  产物：session["diff_summary"] = { "pr_url", "hunks": [{"file", "lang", "diff_text"}] }

  │
  ▼
[planner_agent]  — LLM
  • 分析 diff_summary，判断本 batch 涉及哪些风险域
  产物：session["active_domains"] = ["android", "security", ...]
  可选域：android / security / concurrency / caching / db_schema / backend

  │
  ▼
[ParallelAgent(6 reviewers)]
  每个 reviewer：
  ├─ before_agent_callback  — Python, 0 token
  │    domain 不在 active_domains → 直接返回 {"findings": []}，跳过 LLM
  │
  └─ domain 在 active_domains → LLM 执行
       可调用 file_read / grep 查询上下文
       产物：session["xxx_findings"] = {"findings": [...]}

  │
  ▼
[_merge()]  — Python, 0 token
  • 合并所有 batch 的 findings
  • 按 (file, line_start, category) 去重，保留高严重级别
  产物：CRReport { findings, summary, verdict }
```

## Token 优化

| 阶段 | 优化手段 | 效果 |
|------|---------|------|
| git_client | 40K chars 切 batch | 避免超上下文 |
| filter | Python 层过滤测试文件 | 减少输入量 |
| gateway callback | inactive reviewer 完全跳过 | 0 token |
| per-batch planner | 每个 batch 独立判断域 | 精准激活相关 reviewer |

**实测数据：**

| MR | 文件数 | Token | Reviewers/batch |
|----|--------|-------|-----------------|
| latinime/562（真实业务）| 20+ | 143K | 2/6 |
| latincore/78（含 4 个 bug）| 2 | 10K | 3/6 |
| latinime/591（全测试文件）| 2 | 0 | 全跳过 |

## 项目结构

```
cr-agent/
├── adk/
│   ├── agents/
│   │   ├── diff_reader.py          # 解析 diff → diff_summary
│   │   ├── planner.py              # 判断 active_domains
│   │   ├── gate.py                 # before_agent_callback domain gate
│   │   ├── instruction_builder.py  # 将 diff_summary 注入 reviewer prompt
│   │   ├── android_reviewer.py
│   │   ├── backend_reviewer.py
│   │   ├── security_reviewer.py
│   │   ├── concurrency_reviewer.py
│   │   ├── caching_reviewer.py
│   │   ├── db_schema_reviewer.py
│   │   └── root_agent.py           # 组装完整 pipeline
│   ├── prompts.py                  # 所有 reviewer 的 instruction
│   └── run.py                      # CLI 入口，batch 管理，结果合并
├── shared/
│   ├── git_client.py               # GitLab API，diff 拉取与切分
│   ├── schemas.py                  # Finding / CRReport 数据模型
│   └── tools.py                    # file_read / grep 工具
└── benchmark/                      # 评测 fixtures 与评分脚本
```

## 关键实现说明

**`make_instruction()` callable**：reviewer 使用 callable instruction 而非字符串，在运行时将 `diff_summary` 注入 system prompt。原因：ADK 的 `inject_session_state()` 用 `{var}` 模板替换，与 prompt 中的 JSON 花括号（`{"findings": []}` 等）冲突，导致 prompt 损坏。

**`_parse_active_domains()`**：planner 通过 `output_key` 将输出存为原始 JSON 字符串，gate 读取时需解析后再判断 domain 成员。

**Session 隔离**：每个 batch 使用独立的 `InMemoryRunner` + session，batch 间不共享状态，findings 由 Python 层合并。
