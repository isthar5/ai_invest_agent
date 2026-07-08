Application
    │
Workflow
    │
Runtime
    │
Executor
    │
Infrastructure

Application	提供业务接口
Workflow	描述执行计划
Runtime	调度任务
Executor	执行业务
Infrastructure	数据库、LLM、缓存等
下层永远不能依赖上层。