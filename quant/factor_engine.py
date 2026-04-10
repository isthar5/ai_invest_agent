import os
import pandas as pd
import numpy as np
from typing import List, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class FactorEngineV2:
    """
    工业级因子引擎（支持：
    - 横截面因子
    - 行业因子
    - 收益标签
    - 本地缓存
    - 每日复盘
    """

    def __init__(
        self,
        start_date: str = "2020-01-01",
        end_date: str = None,
        cache_dir: str = "./data_cache"
    ):
        self.start_date = start_date
        self.end_date = end_date or datetime.today().strftime("%Y-%m-%d")
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)

    # ======================
    # 1. 数据层（带缓存）
    # ======================
    def _get_cache_path(self, code: str):
        return os.path.join(self.cache_dir, f"{code}.parquet")

    def download_data(self, stock_codes: List[str]) -> pd.DataFrame:
        import akshare as ak

        all_dfs = []

        for code in stock_codes:
            cache_path = self._get_cache_path(code)

            if os.path.exists(cache_path):
                df = pd.read_parquet(cache_path)
                logger.info(f"读取缓存: {code}")
            else:
                try:
                    df = ak.stock_zh_a_hist(
                        symbol=code,
                        period="daily",
                        start_date=self.start_date.replace('-', ''),
                        end_date=self.end_date.replace('-', ''),
                        adjust="qfq"
                    )

                    if df.empty:
                        continue

                    df = df.rename(columns={
                        '日期': 'date',
                        '开盘': 'open',
                        '最高': 'high',
                        '最低': 'low',
                        '收盘': 'close',
                        '成交量': 'volume'
                    })

                    df['date'] = pd.to_datetime(df['date'])
                    df['tic'] = code

                    df = df[['date', 'tic', 'open', 'high', 'low', 'close', 'volume']]
                    df.to_parquet(cache_path)

                    logger.info(f"下载并缓存: {code}")

                except Exception as e:
                    logger.error(f"{code} 下载失败: {e}")
                    continue

            all_dfs.append(df)

        if not all_dfs:
            raise ValueError("没有下载到任何数据")

        return pd.concat(all_dfs, ignore_index=True)

    # ======================
    # 2. 行业数据（关键）
    # ======================
    def add_industry(self, df: pd.DataFrame) -> pd.DataFrame:
        import akshare as ak

        try:
            industry_df = ak.stock_board_industry_cons_em()

            industry_df = industry_df.rename(columns={
                "代码": "tic",
                "板块名称": "industry"
            })

            df = df.merge(industry_df[['tic', 'industry']], on='tic', how='left')

        except Exception as e:
            logger.warning(f"行业数据获取失败: {e}，使用默认")
            df['industry'] = 'unknown'

        return df

    # ======================
    # 3. 技术因子（优化版）
    # ======================
    def add_technical_factors(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.sort_values(['tic', 'date']).copy()

        # MA
        for p in [5, 10, 20, 60]:
            df[f'ma{p}'] = df.groupby('tic')['close'].transform(lambda x: x.rolling(p, min_periods=1).mean())

        # 连续型特征（替代信号）
        df['ma_diff'] = (df['ma5'] - df['ma20']) / (df['ma20'] + 1e-6)

        # 波动率
        df['volatility'] = df.groupby('tic')['close'].transform(lambda x: x.rolling(20, min_periods=1).std())

        # 量能zscore
        vol_ma = df.groupby('tic')['volume'].transform(lambda x: x.rolling(5, min_periods=1).mean())
        vol_std = df.groupby('tic')['volume'].transform(lambda x: x.rolling(20, min_periods=1).std())

        df['volume_z'] = (df['volume'] - vol_ma) / (vol_std + 1e-6)

        return df

    # ======================
    # 4. 动量因子
    # ======================
    def add_momentum_factors(self, df: pd.DataFrame) -> pd.DataFrame:
        for p in [5, 10, 20, 60]:
            df[f'return_{p}d'] = df.groupby('tic')['close'].pct_change(p)

        return df

    # ======================
    # 5. 横截面因子（核心）
    # ======================
    def add_cross_section_factors(self, df: pd.DataFrame) -> pd.DataFrame:
        # 确保 return_20d 存在
        if 'return_20d' not in df.columns:
            df['return_20d'] = df.groupby('tic')['close'].pct_change(20)

        # 全市场排名
        df['return_rank'] = df.groupby('date')['return_20d'].rank(pct=True)

        # 行业内排名（关键）
        df['industry_rank'] = df.groupby(['date', 'industry'])['return_20d'].rank(pct=True)

        return df

    # ======================
    # 6. 行业强度（核心）
    # ======================
    def add_industry_strength(self, df: pd.DataFrame) -> pd.DataFrame:
        industry_strength = (
            df.groupby(['date', 'industry'])['return_20d']
            .mean()
            .rename("industry_strength")
            .reset_index()
        )

        df = df.merge(industry_strength, on=['date', 'industry'], how='left')

        return df

    # ======================
    # 7. 标签（用于训练）
    # ======================
    def add_labels(self, df: pd.DataFrame, horizon: int = 5) -> pd.DataFrame:
        df[f'target_{horizon}d'] = (
            df.groupby('tic')['close']
            .shift(-horizon) / df['close'] - 1
        )
        return df

    # ======================
    # 8. 主流程
    # ======================
    def build_features(self, stock_codes: List[str]) -> pd.DataFrame:
        logger.info("开始构建因子...")
        logger.info(f"股票数量: {len(stock_codes)}")

        df = self.download_data(stock_codes)
        logger.info(f"下载完成，数据量: {len(df)}")

        df = self.add_industry(df)
        df = self.add_technical_factors(df)
        df = self.add_momentum_factors(df)

        df = self.add_cross_section_factors(df)
        df = self.add_industry_strength(df)

        df = self.add_labels(df)

        # 将 industry 字符串转成数值编码（LightGBM 需要）
        if 'industry' in df.columns:
            df['industry_code'] = df['industry'].astype('category').cat.codes
            df = df.drop('industry', axis=1)

        before_drop = len(df)
        df = df.dropna()
        logger.info(f"删除空值: {before_drop} -> {len(df)}")

        logger.info(f"最终数据量: {len(df)}")
        logger.info(f"特征列: {df.columns.tolist()[:10]}...")

        return df


# ======================
# 9. 投研接口
# ======================
def analyze_stock_pool(df: pd.DataFrame, target_stock: str):
    """
    用于每日复盘（核心函数）
    """
    latest_date = df['date'].max()
    latest_df = df[df['date'] == latest_date]

    pool_rank = latest_df.sort_values('return_rank', ascending=False)

    target = latest_df[latest_df['tic'] == target_stock]

    result = {
        "date": latest_date,
        "target": target.to_dict(orient="records") if len(target) > 0 else [],
        "top_stocks": pool_rank.head(10).to_dict(orient="records"),
    }

    return result


# ======================
# 10. 兼容旧接口
# ======================
def build_features(stock_codes: List[str]) -> pd.DataFrame:
    """兼容旧接口"""
    engine = FactorEngineV2()
    return engine.build_features(stock_codes)