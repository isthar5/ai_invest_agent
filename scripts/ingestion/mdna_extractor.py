import re


MDNA_START = [
    "管理层讨论与分析",
    "经营情况讨论与分析",
    "董事会报告",
]

MDNA_END = [
    "公司治理",
    "财务报表",
    "重要事项",
    "风险提示",
]


def extract_mdna(text: str) -> str | None:
    start_idx = -1
    for key in MDNA_START:
        idx = text.find(key)
        if idx != -1:
            start_idx = idx
            break

    if start_idx == -1:
        return None

    end_idx = len(text)
    for key in MDNA_END:
        idx = text.find(key, start_idx + 100)
        if idx != -1:
            end_idx = min(end_idx, idx)

    mdna = text[start_idx:end_idx].strip()
    return mdna if mdna else None


def extract_mdna_robust(text: str) -> str | None:
    pattern = r"(管理层讨论与分析|经营情况讨论与分析|董事会报告)(.*?)(公司治理|财务报表|重要事项|风险提示)"
    match = re.search(pattern, text, re.S)
    if match:
        mdna = match.group(0).strip()
        return mdna if mdna else None
    return None

