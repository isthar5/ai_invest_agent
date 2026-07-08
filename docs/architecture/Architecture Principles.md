## Single Responsibility

任何组件只能有一个核心职责。

---

## Runtime Owns Execution

Workflow 描述 What

Runtime 实现 How

---

## Registry Pattern

所有可扩展对象必须通过 Registry。

禁止 if-else。

---

## Immutable Definition

WorkflowDefinition

PromptDefinition

TaskDefinition

必须 immutable。

---

## Declarative Configuration

Workflow YAML 只能描述：

Task

Edge

Input

Output

Retry

Timeout

不得出现业务代码。

---

## Composition over Inheritance

优先组合。

避免复杂继承。

---

## Context First

所有运行状态进入 RuntimeContext。

WorkflowDefinition 永远不保存状态。