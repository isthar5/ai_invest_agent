
# ChemInvest Agent —— 化工行业 RAG + 量化投研 Agent

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)

## 📖 项目简介

ChemInvest Agent 是一个面向化工行业的智能投研 Agent 系统。它基于 **LangGraph** 构建，集成 RAG 混合检索、LightGBM 量化预测、Text-to-SQL 结构化查询，支持 Multi-Agent 协作与流式交互。能够自动分析上市公司财报、行业地位并生成结构化投研报告。

> 🎯 本项目作为个人独立开发的 AI Agent 工程实践作品，展示了从数据解析、向量检索、量化建模到 Agent 调度与前端交互的完整技术栈。

## ✨ 核心功能

- **Multi-Agent 协作**：Router 模式多智能体，含财报分析、行业对标、结构化查询、RAG 检索四个子 Agent
- **混合检索**：Dense + Sparse 双路召回 + Cross-Encoder 重排序 + MMR 多样性重排
- **Text-to-SQL**：自研 Schema Linking 模块，自然语言转 SQL 准确率 85%+
- **量化预测**：LightGBM 多因子模型，SHAP 特征归因，每日生成 Top-5 机会池
- **Go 工具调度层**：Go + Gin 工具服务，Schema 自动发现，并发调用降低延迟 45%
- **分层记忆**：Redis 短期会话记忆 + 长期用户偏好存储
- **CI/CD**：GitHub Actions 自动化测试流水线（单元/集成/端到端）
- **前端**：React 流式聊天界面，支持推理过程与工具调用可视化

## 🚀 快速开始


# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境变量
cp .env.example .env  # 编辑填入 API Key

# 3. 启动服务
docker-compose up -d       # Qdrant + Redis + PostgreSQL

cd app/go-agent && go run main.go  # Go 工具层

python main.py             # FastAPI 网关

cd frontend && npm run dev # React 前端


## 📊 检索评估

在 277 份化工年报测试集上，检索效果如下：

| 指标 | 基线 (Hybrid) | + Rerank |
| :--- | :---: | :---: |
| Recall@10 | 0.65 | 0.84 |
| MRR | 0.42 | 0.61 |


## 📝 License

本项目采用 [MIT License](LICENSE)。

## 📧 联系方式

- **GitHub**：[@isthar5](https://github.com/isthar5)
- **Issues**：欢迎提交问题与建议

