"""
季度财务数据下载器 — 使用列位置索引避免编码问题。

AKShare stock_yjbb_em 列顺序(已验证 v1.14.x):
  [0] 序号, [1] 股票代码, [2] 股票简称, [3] 每股收益,
  [4] 营业收入-营业收入, [5] 营业收入-同比增长,
  [6] 营业收入-季度环比增长,
  [7] 净利润-净利润, [8] 净利润-同比增长,
  [9] 净利润-季度环比增长,
  [10] 每股净资产, [11] 净资产收益率,
  [12] 每股经营现金流量, [13] 销售毛利率,
  [14] 所属行业, [15] 公告日期

用法:
    python scripts/download_finance.py          # CSV + SQLite
    python scripts/download_finance.py --csv    # 仅 CSV
"""

import logging
import sqlite3
import sys
import time
from pathlib import Path

import akshare as ak
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("download_finance")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = Path(r"E:\text2sql_data\output\financials.csv")
DB_PATH = PROJECT_ROOT / "data" / "chemical_stocks.db"

# 8 只代表性化工股
STOCK_POOL = {
    "600309": "万华化学",   # MDI/聚氨酯 龙头
    "600160": "巨化股份",   # 氟化工
    "600426": "华鲁恒升",   # 煤化工
    "002648": "卫星化学",   # 乙烯/PDH
    "002709": "天赐材料",   # 电解液/电池
    "002601": "龙佰集团",   # 钛白粉
    "600346": "恒力石化",   # 炼化/PTA
    "300699": "光威复材",   # 碳纤维
}

# 2021Q1 ~ 2025Q4
REPORT_DATES = [
    "20210331", "20210630", "20210930", "20211231",
    "20220331", "20220630", "20220930", "20221231",
    "20230331", "20230630", "20230930", "20231231",
    "20240331", "20240630", "20240930", "20241231",
    "20250331", "20250630", "20250930", "20251231",
]

STOCK_CODES = set(STOCK_POOL.keys())


def download_all() -> pd.DataFrame:
    """按报告期批量下载，用列位置索引避免中文编码问题。"""
    all_rows = []

    for report_date in REPORT_DATES:
        year = int(report_date[:4])
        mmdd = report_date[4:8]
        if mmdd == "0331": quarter = 1
        elif mmdd == "0630": quarter = 2
        elif mmdd == "0930": quarter = 3
        else: quarter = 4

        logger.info(f"下载 {report_date} ({year}Q{quarter}) ...")

        try:
            df = ak.stock_yjbb_em(date=report_date)
        except Exception as e:
            logger.warning(f"  API 失败: {e}")
            continue

        if df.empty:
            logger.warning("  空数据")
            continue

        # 列位置索引 (AKShare v1.14.x 固定顺序)
        # [0]序号 [1]股票代码 [2]股票简称 [3]每股收益
        # [4]营业收入 [5]营收同比 [6]营收环比
        # [7]净利润 [8]净利润同比 [9]净利润环比
        # [10]每股净资产 [11]ROE [12]每股经营现金流
        # [13]毛利率 [14]所属行业 [15]公告日期
        cols = df.columns
        code_col = cols[1]   # 股票代码
        name_col = cols[2]   # 股票简称

        # 过滤化工股
        mask = df[code_col].astype(str).str.strip().str[:6].isin(STOCK_CODES)
        sub = df[mask].copy()
        if sub.empty:
            logger.info("  无化工股")
            continue

        # 提取数据
        out = pd.DataFrame()
        out["stock_code"] = sub[code_col].astype(str).str.strip().str[:6]
        out["company_name"] = sub[name_col].astype(str).str.strip()
        out["fiscal_year"] = year
        out["quarter"] = quarter
        out["revenue"] = pd.to_numeric(sub[cols[4]], errors="coerce")
        out["revenue_yoy"] = pd.to_numeric(sub[cols[5]], errors="coerce")
        out["net_profit"] = pd.to_numeric(sub[cols[7]], errors="coerce")
        out["net_profit_yoy"] = pd.to_numeric(sub[cols[8]], errors="coerce")
        out["eps"] = pd.to_numeric(sub[cols[3]], errors="coerce")
        out["roe"] = pd.to_numeric(sub[cols[11]], errors="coerce")
        out["gross_margin"] = pd.to_numeric(sub[cols[13]], errors="coerce")
        # 净利率 = 净利润/营收
        out["net_margin"] = out["net_profit"] / out["revenue"]
        # 营业利润 从 cols 中没有直接字段，用 None
        out["operating_profit"] = None

        all_rows.append(out)
        logger.info(f"  {len(out)} 只股票")

        time.sleep(0.3)

    if not all_rows:
        raise RuntimeError("未下载到任何数据")

    result = pd.concat(all_rows, ignore_index=True)
    return result[
        ["stock_code", "company_name", "fiscal_year", "quarter",
         "revenue", "revenue_yoy", "net_profit", "net_profit_yoy",
         "eps", "roe", "gross_margin", "net_margin", "operating_profit"]
    ]


def save_csv(df: pd.DataFrame):
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(CSV_PATH, index=False, encoding="utf-8-sig")
    logger.info(f"CSV: {CSV_PATH} ({len(df)} 行, {CSV_PATH.stat().st_size/1024:.1f} KB)")


def write_sqlite(df: pd.DataFrame):
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    c.execute("DROP TABLE IF EXISTS financials")
    c.execute("""
        CREATE TABLE financials (
            stock_code TEXT, company_name TEXT,
            fiscal_year INTEGER, quarter INTEGER,
            revenue REAL, revenue_yoy REAL,
            net_profit REAL, net_profit_yoy REAL,
            eps REAL, roe REAL, gross_margin REAL,
            net_margin REAL, operating_profit REAL
        )
    """)
    cols = ["stock_code", "company_name", "fiscal_year", "quarter",
            "revenue", "revenue_yoy", "net_profit", "net_profit_yoy",
            "eps", "roe", "gross_margin", "net_margin", "operating_profit"]
    ph = ", ".join(["?"] * len(cols))
    sql = f'INSERT INTO financials ({", ".join(cols)}) VALUES ({ph})'

    rows = []
    for _, row in df.iterrows():
        vals = []
        for col in cols:
            v = row[col]
            if pd.isna(v):
                vals.append(None)
            elif col in ("stock_code", "company_name"):
                vals.append(str(v))
            elif col in ("fiscal_year", "quarter"):
                vals.append(int(v))
            else:
                vals.append(float(v))
        rows.append(tuple(vals))

    c.executemany(sql, rows)
    c.execute("CREATE INDEX IF NOT EXISTS idx_fin_code ON financials(stock_code)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_fin_year ON financials(fiscal_year)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_fin_q ON financials(stock_code, fiscal_year, quarter)")
    conn.commit()
    conn.close()
    logger.info(f"SQLite: {len(rows)} 行 → {DB_PATH}")


def main():
    csv_only = "--csv" in sys.argv
    logger.info(f"{len(STOCK_POOL)} 只股票 × {len(REPORT_DATES)} 个报告期")
    df = download_all()

    for code, name in STOCK_POOL.items():
        sub = df[df["stock_code"] == code]
        non_null = sub["revenue"].notna().sum()
        years = sorted(sub["fiscal_year"].unique())
        logger.info(f"  {code} {name}: {len(sub)}条 ({non_null}条有营收), 年份 {years}")

    save_csv(df)

    if not csv_only:
        write_sqlite(df)

        # 验证
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.cursor()
        cur.execute("""
            SELECT company_name, fiscal_year, quarter,
                   printf('%.2f', revenue/100000000.0)
            FROM financials
            WHERE stock_code='600309' AND revenue IS NOT NULL
            ORDER BY fiscal_year, quarter LIMIT 8
        """)
        print("\n万华化学 季度营收 (亿):")
        for r in cur.fetchall():
            print(f"  {r[0]} {r[1]}Q{r[2]}: {r[3]}亿")
        conn.close()
        logger.info("✅ 完成")


if __name__ == "__main__":
    main()
