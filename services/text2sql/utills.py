from typing import Dict, Any
from datetime import datetime, date
from decimal import Decimal

def escape_sample_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """
    安全转义示例行，防止 Prompt 注入
    """
    escaped = {}
    for k, v in row.items():
        if v is None:
            escaped[k] = "NULL"
        elif isinstance(v, str):
            # 转义双引号，替换换行符
            escaped[k] = v.replace('"', '\\"').replace("\n", " ").replace("\r", " ")
        elif isinstance(v, (datetime, date)):
            escaped[k] = v.isoformat()
        elif isinstance(v, Decimal):
            escaped[k] = float(v)
        elif isinstance(v, (bytes, bytearray)):
            escaped[k] = v.hex()[:50] + "..."
        elif isinstance(v, (int, float, bool)):
            escaped[k] = v
        else:
            escaped[k] = str(v)[:100]
    return escaped

def sanitize_table_name(table_name: str) -> str:
    """
    清洗表名，防止 SQL 注入
    """
    import re
    # 只允许字母、数字、下划线
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', table_name):
        raise ValueError(f"Invalid table name: {table_name}")
    return table_name