# Goals

Workflow Framework 用于统一管理系统中的任务编排。

主要目标：

- 配置化 Workflow
- DAG 执行
- 与 Runtime 解耦
- Executor 可扩展
- PromptRegistry 无侵入
- SkillRegistry 无侵入
- Runtime 无侵入

Workflow Framework 不负责任务执行。

真正执行任务的是 Runtime。

第二章 Non Goals
# Non Goals

Workflow Framework 不负责：

- Retry
- ThreadPool
- EventLoop
- Scheduler
- LLM 调用
- Prompt 渲染

第三章 Architecture
WorkflowRegistry

↓

WorkflowLoader

↓

WorkflowDefinition

↓

TaskBuilder

↓

ExecutionPlan

↓

ExecutionRuntime

↓

DefaultTaskExecutor

↓

ExecutorRegistry

↓

Executor
- Skill 实现
- SQL 执行
- Session 管理