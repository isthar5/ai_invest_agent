"""
将 text2sql_data/output 下的 CSV 文件导入到 chemical_stocks.db（SQLite）

用法：
    cd E:\ai_invest_agent
    python scripts/import_csv_to_text2sql.py

CSV → 数据库表映射（与 schema.json 一致）：
    financials.csv      → financials
    balance_sheet.csv   → balance_sheet
    cash_flow.csv       → cash_flow
    industry_metrics.csv → industry_metrics
    stock_basic.csv     → stock_basic
"""

import csv
import os
import sqlite3
import sys
from pathlib import Path

# 配置
CSV_DIR = Path(r"E:\text2sql_data\output")
DB_PATH = Path(r"E:\ai_invest_agent\data\chemical_stocks.db")

# CSV 文件名 → 表名
TABLE_MAP = {
    "financials.csv": "financials",
    "balance_sheet.csv": "balance_sheet",
    "cash_flow.csv": "cash_flow",
    "industry_metrics.csv": "industry_metrics",
    "stock_basic.csv": "stock_basic",
}

# 数值列（需要在 SQLite 中存为 REAL 而非 TEXT）
NUMERIC_COLUMNS = {
    "financials": [
        "revenue", "revenue_yoy", "net_profit", "net_profit_yoy",
        "gross_profit", "gross_margin", "net_margin", "roe", "roa",
        "eps", "operating_profit", "rd_expense",
    ],
    "balance_sheet": [
        "total_assets", "total_liabilities", "equity",
        "current_assets", "current_liabilities", "debt_ratio",
        "current_ratio", "fixed_assets", "construction_in_progress",
    ],
    "cash_flow": [
        "operating_cf", "investing_cf", "financing_cf",
        "free_cash_flow", "capex", "dividend_paid",
    ],
    "industry_metrics": [
        "industry_rank", "industry_avg_revenue", "industry_avg_roe",
        "industry_avg_gross_margin", "relative_strength",
        "peer_count", "market_share",
    ],
    "stock_basic": [
        "market_cap",
    ],
}


def infer_column_type(col_name: str, table_name: str) -> str:
    """推断列类型：NUMERIC 列用 REAL，否则用 TEXT"""
    if col_name in NUMERIC_COLUMNS.get(table_name, []):
        return "REAL"
    if col_name in ("fiscal_year", "quarter"):
        return "INTEGER"
    return "TEXT"


def import_csv_to_sqlite():
    if not CSV_DIR.exists():
        print(f"[ERROR] CSV dir not found: {CSV_DIR}")
        sys.exit(1)

    # 确保目标目录存在
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    # 如果已有旧数据库，先删除
    if DB_PATH.exists():
        DB_PATH.unlink()
        print(f"[CLEAN] 已删除旧数据库: {DB_PATH}")

    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    total_rows = 0

    for csv_file, table_name in TABLE_MAP.items():
        csv_path = CSV_DIR / csv_file
        if not csv_path.exists():
            print(f"[SKIP] {csv_file} 不存在")
            continue

        with open(csv_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames

            if not headers:
                print(f"[SKIP] {csv_file} 为空")
                continue

            # 构造 CREATE TABLE
            col_defs = []
            for col in headers:
                col_type = infer_column_type(col.strip(), table_name)
                col_defs.append(f'"{col.strip()}" {col_type}')

            create_sql = f'CREATE TABLE IF NOT EXISTS "{table_name}" ({", ".join(col_defs)})'
            cursor.execute(create_sql)

            # 插入数据
            placeholders = ", ".join(["?" for _ in headers])
            insert_sql = f'INSERT INTO "{table_name}" ({", ".join(f'"{h.strip()}"' for h in headers)}) VALUES ({placeholders})'

            rows = []
            for row in reader:
                values = []
                for col_name in headers:
                    raw = row[col_name].strip()
                    col_type = infer_column_type(col_name.strip(), table_name)
                    if col_type in ("REAL", "INTEGER"):
                        try:
                            values.append(float(raw) if raw else 0.0)
                        except ValueError:
                            values.append(0.0)
                    else:
                        values.append(raw)
                rows.append(tuple(values))

            if rows:
                cursor.executemany(insert_sql, rows)

            print(f"[OK] {csv_file} -> {table_name}: {len(rows)} rows")
            total_rows += len(rows)

    conn.commit()

    # 创建索引以加速查询
    for table_name in TABLE_MAP.values():
        try:
            cursor.execute(f'CREATE INDEX IF NOT EXISTS idx_{table_name}_code ON "{table_name}" (stock_code)')
        except sqlite3.OperationalError:
            pass  # 表可能没有 stock_code 列
        try:
            if table_name != "stock_basic":
                cursor.execute(f'CREATE INDEX IF NOT EXISTS idx_{table_name}_year ON "{table_name}" (fiscal_year)')
        except sqlite3.OperationalError:
            pass

    conn.commit()
    conn.close()

    print(f"\n[DONE] Import complete! Total {total_rows} rows -> {DB_PATH}")
    print(f"   数据库大小: {DB_PATH.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    import_csv_to_sqlite()
