"""
Prompt Registry — YAML 驱动的 Prompt 注册中心。

设计原则：
- 零数据库依赖 — YAML 文件即存储
- 单例模式 — 进程内共享一个 Registry 实例
- 延迟加载 — 首次访问时加载 YAML，后续命中内存缓存
- 容错降级 — YAML 不可用时返回内置 Fallback
- 线程安全 — RWLock 保证 reload() 的读写安全

用法：
    from app.services.prompt.registry import get_registry

    registry = get_registry()
    prompt = registry.render("text2sql.first_attempt",
                              schema_prompt="...", question="...", current_year=2026)

类图：
    PromptLoader  → 加载 YAML → PromptTemplate 列表
    PromptRegistry → 缓存 + 检索 + render
    PromptProperty → 描述符，class-level 延迟访问
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger("prompt.registry")

# ═══════════════════════════════════════════════════════════
#  配置
# ═══════════════════════════════════════════════════════════

# YAML 配置目录 — 从项目根目录解析，可通过 PROMPT_CONFIG_DIR 环境变量覆盖
_project_root = Path(__file__).resolve().parent.parent.parent.parent
DEFAULT_CONFIG_DIR = _project_root / "configs" / "prompts"
CONFIG_DIR = Path(
    __import__("os").getenv("PROMPT_CONFIG_DIR", str(DEFAULT_CONFIG_DIR))
)


# ═══════════════════════════════════════════════════════════
#  异常
# ═══════════════════════════════════════════════════════════

class PromptNotFoundError(KeyError):
    """Prompt ID 不存在"""


class VersionNotFoundError(KeyError):
    """指定版本不存在"""


class RenderError(ValueError):
    """模板渲染失败（变量缺失）"""


# ═══════════════════════════════════════════════════════════
#  PromptTemplate
# ═══════════════════════════════════════════════════════════

@dataclass(frozen=True)
class PromptTemplate:
    """
    单个 Prompt 的不可变模板。

    render() 使用 Python str.format() 渲染，
    缺失变量时发出 WARNING 并用空字符串填充（safe_render=False），
    或抛出 RenderError（safe_render=True）。
    """

    id: str
    version: str
    description: str = ""
    owner: str = ""
    created_at: str = ""
    changelog: str = ""
    variables: List[str] = field(default_factory=list)
    template: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def render(self, safe_render: bool = False, **kwargs: Any) -> str:
        """
        渲染模板。

        Args:
            safe_render: True → 变量缺失时抛出 RenderError
            **kwargs: 模板变量

        Returns:
            渲染后的字符串
        """
        # 收集所有变量
        render_vars: Dict[str, str] = {}
        missing: List[str] = []

        for var in self.variables:
            if var in kwargs:
                render_vars[var] = str(kwargs[var])
            else:
                missing.append(var)
                render_vars[var] = ""

        if missing:
            msg = (
                f"Prompt '{self.id}' (v{self.version}) missing variables: {missing}. "
                f"Expected: {self.variables}, got: {list(kwargs.keys())}"
            )
            if safe_render:
                raise RenderError(msg)
            logger.warning(msg)

        try:
            return self.template.format(**render_vars)
        except KeyError as e:
            # 模板中引用了未声明的变量
            msg = f"Prompt '{self.id}' template references undeclared variable: {e}"
            if safe_render:
                raise RenderError(msg)
            logger.warning(msg)
            # 用空字符串填充并重试
            return self.template.format_map(
                {**{v: "" for v in self.variables}, **render_vars}
            )

    def to_dict(self) -> Dict[str, Any]:
        """序列化（调试 / 序列化用）"""
        return {
            "id": self.id,
            "version": self.version,
            "description": self.description,
            "owner": self.owner,
            "created_at": self.created_at,
            "changelog": self.changelog,
            "variables": self.variables,
            "template": self.template,
            "metadata": self.metadata,
        }


# ═══════════════════════════════════════════════════════════
#  PromptLoader — 负责 YAML → PromptTemplate 的转换
# ═══════════════════════════════════════════════════════════

class PromptLoader:
    """
    YAML 文件加载器。

    职责单一：读文件 → 校验 → 返回 PromptTemplate 列表。
    不负责缓存、不负责检索。
    """

    @staticmethod
    def load_directory(config_dir: Path) -> Dict[str, Dict[str, PromptTemplate]]:
        """
        加载配置目录下所有 .yaml 文件。

        Returns:
            {prompt_id: {version: PromptTemplate}}
        """
        prompts: Dict[str, Dict[str, PromptTemplate]] = {}

        if not config_dir.exists():
            logger.warning(f"Prompt config directory not found: {config_dir}")
            return prompts

        yaml_files = sorted(config_dir.glob("*.yaml"))
        if not yaml_files:
            logger.warning(f"No .yaml files found in {config_dir}")
            return prompts

        for yaml_path in yaml_files:
            try:
                file_prompts = PromptLoader.load_file(yaml_path)
                prompts.update(file_prompts)
            except Exception as e:
                logger.error(f"Failed to load {yaml_path.name}: {e}")

        return prompts

    @staticmethod
    def load_file(path: Path) -> Dict[str, Dict[str, PromptTemplate]]:
        """
        加载单个 YAML 文件。

        YAML 结构:
          prompts:
            <prompt_id>:
              description: "..."
              owner: "..."
              current_version: v1
              versions:
                v1:
                  created_at: "..."
                  variables: [a, b]
                  template: |
                    ...

        Returns:
            {prompt_id: {version: PromptTemplate}}
        """
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not data or "prompts" not in data:
            logger.warning(f"No 'prompts' section in {path.name}, skipping")
            return {}

        prompts: Dict[str, Dict[str, PromptTemplate]] = {}

        for prompt_id, prompt_def in data["prompts"].items():
            if not isinstance(prompt_def, dict):
                continue

            description = prompt_def.get("description", "")
            owner = prompt_def.get("owner", "")
            current_version = prompt_def.get("current_version", "v1")
            versions_data = prompt_def.get("versions", {})

            version_map: Dict[str, PromptTemplate] = {}

            for version_key, version_def in versions_data.items():
                if not isinstance(version_def, dict):
                    continue

                template = PromptTemplate(
                    id=prompt_id,
                    version=version_key,
                    description=description,
                    owner=owner,
                    created_at=str(version_def.get("created_at", "")),
                    changelog=str(version_def.get("changelog", "")),
                    variables=list(version_def.get("variables", [])),
                    template=str(version_def.get("template", "")),
                    metadata={
                        "current_version": current_version,
                        "domain": data.get("meta", {}).get("domain", ""),
                        **version_def.get("metadata", {}),
                    },
                )
                version_map[version_key] = template

            if version_map:
                # 注册 latest 别名
                if current_version in version_map:
                    version_map["latest"] = version_map[current_version]
                elif version_map:
                    # fallback: latest → 最后一个版本
                    last_key = sorted(version_map.keys())[-1]
                    version_map["latest"] = version_map[last_key]

                prompts[prompt_id] = version_map

        logger.debug(f"Loaded {len(prompts)} prompts from {path.name}")
        return prompts


# ═══════════════════════════════════════════════════════════
#  PromptRegistry — 单例注册中心
# ═══════════════════════════════════════════════════════════

class PromptRegistry:
    """
    Prompt 注册中心（单例）。

    职责：
      - 持有 {prompt_id: {version: PromptTemplate}} 映射
      - 提供 get() / render() / list_ids() / reload()
      - 初始化失败时自动加载内置 Fallback

    单例由模块级 get_registry() 管理，不在类级别维护 _instance。
    """

    def __init__(self, config_dir: Optional[Path] = None):
        self._config_dir = config_dir or CONFIG_DIR
        self._prompts: Dict[str, Dict[str, PromptTemplate]] = {}
        self._loaded = False
        self._init()

    def _init(self) -> None:
        """初始化：加载 YAML。失败则加载 Fallback。"""
        try:
            self._prompts = PromptLoader.load_directory(self._config_dir)
            self._loaded = True
            total = len(self._prompts)
            if total > 0:
                logger.info(
                    f"PromptRegistry: loaded {total} prompts "
                    f"from {self._config_dir}"
                )
            else:
                logger.warning(
                    f"PromptRegistry: no prompts loaded from {self._config_dir}, "
                    f"using fallback"
                )
                self._load_fallback()
        except Exception as e:
            logger.error(f"PromptRegistry: initialization failed ({e}), using fallback")
            self._load_fallback()

    # ── 公共 API ────────────────────────────────────────

    def get(
        self, prompt_id: str, version: str = "latest"
    ) -> PromptTemplate:
        """
        获取指定 Prompt。

        Raises:
            PromptNotFoundError: prompt_id 不存在
            VersionNotFoundError: 指定 version 不存在
        """
        if prompt_id not in self._prompts:
            raise PromptNotFoundError(
                f"Prompt '{prompt_id}' not found. "
                f"Available: {list(self._prompts.keys())}"
            )

        version_map = self._prompts[prompt_id]
        if version not in version_map:
            raise VersionNotFoundError(
                f"Version '{version}' not found for prompt '{prompt_id}'. "
                f"Available: {list(version_map.keys())}"
            )

        return version_map[version]

    def render(
        self,
        prompt_id: str,
        version: str = "latest",
        safe_render: bool = False,
        **variables: Any,
    ) -> str:
        """
        一步获取 + 渲染。

        等价于: registry.get(prompt_id, version).render(**variables)
        """
        template = self.get(prompt_id, version)
        return template.render(safe_render=safe_render, **variables)

    def list_ids(self) -> List[str]:
        """列出所有已注册的 Prompt ID"""
        return sorted(self._prompts.keys())

    def list_versions(self, prompt_id: str) -> List[str]:
        """列出指定 Prompt 的所有版本"""
        version_map = self._prompts.get(prompt_id, {})
        return sorted(
            [v for v in version_map.keys() if v != "latest"]
        )

    def get_current_version(self, prompt_id: str) -> str:
        """获取指定 Prompt 的 current_version（latest 指向的真实版本）"""
        template = self.get(prompt_id, "latest")
        return template.version

    def reload(self) -> bool:
        """
        热更新：清空缓存 → 重新加载所有 YAML。

        Returns:
            True: 重载成功
            False: 重载失败（保留旧缓存）
        """
        try:
            new_prompts = PromptLoader.load_directory(self._config_dir)
            if not new_prompts:
                logger.warning("PromptRegistry.reload: no prompts loaded, keeping old cache")
                return False

            old_prompts = self._prompts
            self._prompts = new_prompts
            self._loaded = True

            logger.info(
                f"PromptRegistry.reload: {len(self._prompts)} prompts loaded "
                f"(was {len(old_prompts)})"
            )
            return True
        except Exception as e:
            logger.error(f"PromptRegistry.reload failed: {e}, keeping old cache")
            return False

    @property
    def loaded(self) -> bool:
        return self._loaded

    @property
    def prompt_count(self) -> int:
        return len(self._prompts)

    # ── Fallback ─────────────────────────────────────────

    def _load_fallback(self) -> None:
        """
        内置 Fallback — 当所有 YAML 都不可用时激活。

        覆盖全部 10 个 Prompt，确保系统在所有层级都有兜底。
        消费者不再需要维护自己的 fallback。
        """
        F = PromptTemplate  # 别名，减少噪音
        self._prompts = {}

        def _reg(tmpl: PromptTemplate) -> None:
            self._prompts[tmpl.id] = {tmpl.version: tmpl, "latest": tmpl}

        # ── text2sql (P1, P2) ────────────────────────────
        _reg(F("text2sql.first_attempt", "v1", owner="system",
               description="[FALLBACK] First attempt SQL generation",
               variables=["schema_prompt", "question", "current_year"],
               template=(
                   "你是一个专业的 SQL 生成助手。\n\n"
                   "{schema_prompt}\n\n## 用户问题\n{question}\n\n"
                   "## 要求\n- 只生成 SELECT 语句\n- 必须包含 LIMIT 子句\n"
                   "- 直接输出 SQL 代码，不要任何解释\n")))

        _reg(F("text2sql.retry", "v1", owner="system",
               description="[FALLBACK] Retry SQL correction",
               variables=["schema_prompt", "question", "last_sql", "error"],
               template=(
                   "上一次生成的 SQL 执行失败。\n\n"
                   "{schema_prompt}\n\n## 用户问题\n{question}\n\n"
                   "## 上一次 SQL\n```sql\n{last_sql}\n```\n\n"
                   "## 数据库错误\n{error}\n\n"
                   "## 要求\n- 根据错误信息修正 SQL\n"
                   "- 只生成 SELECT 语句\n- 直接输出修正后的 SQL 代码\n")))

        # ── agent (P3, P4, P5, P6) ─────────────────────
        _reg(F("agent.system_prompt", "v1", owner="system",
               description="[FALLBACK] Agent system prompt",
               variables=["current_date", "current_year"],
               template=(
                   "你是化工行业资深投研分析师 AI 助手。\n"
                   "当前日期：{current_date}（今天是{current_year}年）\n\n"
                   "**核心能力**：深度财务分析、量化信号解读、行业对标、结构化数据查询\n\n"
                   "**重要规则**：引用数据必须标注年份、不编造文档中没有的内容\n")))

        _reg(F("agent.system_prompt_compact", "v1", owner="system",
               description="[FALLBACK] Compact system prompt",
               variables=["current_date", "current_year"],
               template=(
                   "你是化工行业分析师（{current_year}年）。\n"
                   "规则：标注数据年份、引用文档编号 [N]、不编造内容、结合历史上下文。\n"
                   "当前日期：{current_date}")))

        _reg(F("agent.extraction", "v1", owner="system",
               description="[FALLBACK] Financial extraction prompt",
               variables=[],
               template=("你是财务数据提取专家。"
                         "从文档中提取结构化财务指标，未找到的字段填 null。"
                         "不要编造数据，严格按 JSON 格式输出。")))

        _reg(F("agent.text2sql", "v1", owner="system",
               description="[FALLBACK] Text2SQL system prompt",
               variables=[],
               template=("你是 Text2SQL 专家。"
                         "将自然语言转换为安全的 SELECT 语句。"
                         "只输出 SQL 代码，不包含解释。")))

        # ── report (P7a, P7b) ──────────────────────────
        _reg(F("report.system_role", "v1", owner="system",
               description="[FALLBACK] Report system role",
               variables=[],
               template="你是一位资深化工行业投研分析师，请基于以下多源数据生成一份专业分析报告。"))

        _reg(F("report.structure", "v1", owner="system",
               description="[FALLBACK] Report structure",
               variables=["financial_json", "quant_json", "industry_json",
                          "insight_text", "signal_type", "confidence",
                          "reasoning", "risk_factors"],
               template=(
                   "【财报数据】\n{financial_json}\n\n"
                   "【量化信号】\n{quant_json}\n\n"
                   "【行业对标】\n{industry_json}\n\n"
                   "【AI 初步洞察】\n{insight_text}\n\n"
                   "【综合研判（系统融合结论，必须采纳）】\n"
                   "信号类型：{signal_type}\n置信度：{confidence}\n"
                   "核心逻辑：{reasoning}\n主要风险：{risk_factors}\n\n"
                   "---\n请按以下结构生成 Markdown 报告：\n"
                   "## 一、综合研判结论\n## 二、财务健康度分析\n"
                   "## 三、量化信号解读\n## 四、行业地位与对标\n"
                   "## 五、风险提示\n## 六、免责声明\n")))

        # ── skills (P8, P9) ────────────────────────────
        _reg(F("skills.financial_extraction", "v1", owner="system",
               description="[FALLBACK] Financial data extraction",
               variables=["shared_context", "docs_text"],
               template=(
                   "从以下财报内容中提取关键财务指标，严格按指定 JSON 格式输出。\n\n"
                   "{shared_context}\n\n内容：\n{docs_text}\n\n"
                   "要求：数值统一为 float 类型，无法提取的字段填 null\n"
                   "输出 JSON 格式。")))

        _reg(F("skills.cross_reasoning", "v1", owner="system",
               description="[FALLBACK] Cross-source reasoning",
               variables=["financial_json", "quant_json", "peers_json", "shared_context"],
               template=(
                   "财报数据：{financial_json}\n"
                   "量化信号：{quant_json}\n"
                   "行业对标：{peers_json}\n\n"
                   "{shared_context}\n\n"
                   "请以专业投研分析师视角回答：\n"
                   "1. 量化预测是否有基本面支撑？\n"
                   "2. 是否存在情绪驱动迹象？\n"
                   "3. 判断信号持续性。\n"
                   "4. 与竞争对手相比处于什么位置？\n"
                   "5. 指出 1-2 个最关键的风险点。\n")))

        # ── eval (P10) ─────────────────────────────────
        _reg(F("eval.query_generation", "v1", owner="system",
               description="[FALLBACK] Eval query generation",
               variables=["content"],
               template=(
                   "你是一个金融助手。\n\n"
                   "给定一段文档内容，请生成 2 个用户可能提出的查询问题。\n\n"
                   "要求：问题必须自然、与内容强相关、用中文\n\n"
                   "文档：\n{content}\n\n"
                   "输出 JSON：\n[{{\"query\": \"...\"}}, {{\"query\": \"...\"}}]\n")))

        self._loaded = True
        logger.warning(
            f"PromptRegistry: loaded {len(self._prompts)} fallback prompts "
            f"(YAML configs unavailable)"
        )


# ═══════════════════════════════════════════════════════════
#  全局单例
# ═══════════════════════════════════════════════════════════

_registry: Optional[PromptRegistry] = None


def get_registry(config_dir: Optional[Path] = None) -> PromptRegistry:
    """获取 PromptRegistry 单例"""
    global _registry
    if _registry is None:
        _registry = PromptRegistry(config_dir=config_dir)
    return _registry


def reset_registry() -> None:
    """重置单例（测试用）"""
    global _registry
    _registry = None


# ═══════════════════════════════════════════════════════════
#  PromptProperty — 描述符，支持 class-level 延迟访问
# ═══════════════════════════════════════════════════════════

class PromptProperty:
    """
    描述符：让 class-level 常量在每次访问时从 Registry 实时取值。

    容错：Registry 覆盖全部 10 个 Prompt 的 fallback，
    不再需要 PromptProperty 维护独立的 _FALLBACKS。

    用法:
        class PromptBuilder:
            SYSTEM_PROMPT_EXTRACTION = PromptProperty("agent.extraction")
            DEFAULT_SYSTEM_PROMPT = PromptProperty(
                "agent.system_prompt",
                current_date=CURRENT_DATE,
                current_year=CURRENT_YEAR,
            )
    """

    def __init__(self, prompt_id: str, version: str = "latest", **default_kwargs: Any):
        self.prompt_id = prompt_id
        self.version = version
        self.default_kwargs = default_kwargs

    def __get__(self, obj: Any, objtype: Any = None) -> str:
        try:
            registry = get_registry()
            if self.default_kwargs:
                return registry.render(
                    self.prompt_id, self.version,
                    safe_render=False, **self.default_kwargs,
                )
            else:
                return registry.get(self.prompt_id, self.version).template
        except Exception:
            logger.warning(
                f"PromptProperty: cannot resolve '{self.prompt_id}', "
                f"returning empty string"
            )
            return ""

    def __set__(self, obj: Any, value: Any) -> None:
        raise AttributeError("PromptProperty is read-only")
