
# ChemInvest Agent —— 化工行业 RAG + 量化投研 Agent

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)

## 📖 项目简介

ChemInvest Agent 是一个面向化工行业的智能投研 Agent 系统。它基于 **LangGraph** 构建，采用**多技能插件化架构**，整合了**混合检索（RAG）**、**量化因子模型（LightGBM）** 与**跨源融合决策引擎**，能够自动分析上市公司财报、行业地位并生成结构化投研报告。

> 🎯 本项目作为个人独立开发的 AI Agent 工程实践作品，展示了从数据解析、向量检索、量化建模到 Agent 调度与前端交互的完整技术栈。

## ✨ 核心功能

- **Agent Skills 架构**：基于 LangGraph 状态机，实现技能插件化注册与动态调度。内置「财报分析」「行业对标」等可插拔 Skill，技能间通过 Pydantic Schema 强约束保证数据契约。
- **混合检索与重排序**：稠密向量（BGE）与稀疏向量（BM25）双路召回，结合 RRF 融合与 Cross-Encoder 重排序，引入 MMR 多样性重排与时效性衰减机制。
- **量化预测引擎**：自研技术面、动量、横截面、行业强度四类因子，基于 LightGBM 滚动预测 5 日收益率，SHAP 输出特征归因，每日生成 Top-5 机会池与个股行业排名。
- **跨源融合决策**：设计连续评分引擎，将财务、量化、行业三维信号融合为统一投资决策（信号类型 + 置信度 + 风险评分），替代传统硬规则。
- **前端交互与可观测性**：基于 Streamlit 构建交互式分析界面，支持决策轨迹追踪；集成 FastAPI 异步流式 API，全链路请求追踪与节点级 JSONL 日志。

## 🚀 快速开始

### 环境要求

- Python 3.10+
- Docker（用于运行 Qdrant）
- Windows / Linux / macOS

### 安装步骤

1. **克隆仓库**
   ```bash
   git clone https://github.com/isthar5/ai_invest_agent.git
   cd ai_invest_agent
   ```

2. **安装依赖**
   ```bash
   pip install -r requirements.txt
   ```

3. **配置环境变量**
   ```bash
   cp .env.example .env
   # 编辑 .env 文件，填入你的 DeepSeek API Key 等配置
   ```

4. **启动 Qdrant 向量数据库**
   ```bash
   docker run -d -p 6333:6333 --name qdrant_rag qdrant/qdrant
   ```

5. **入库年报数据（可选，需准备 PDF 文件）**
   ```bash
   python app/ingestion/ingest_to_qdrant.py --action ingest
   ```

6. **启动前端界面**
   ```bash
   streamlit run streamlit_app.py
   ```

7. **启动 API 服务（可选）**
   ```bash
   uvicorn main:app --reload
   ```


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

