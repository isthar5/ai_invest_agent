Executor 必须：

Stateless

Idempotent

Independent

统一接口：

async execute(payload) -> Result

禁止：

Executor 调 Runtime

Executor 调 Workflow

Executor 修改 Task