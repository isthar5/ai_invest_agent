import qlib
from qlib.data import D
import akshare as ak
import pandas as pd

qlib.init(provider_uri="~/.qlib/qlib_data/cn_data", region="cn")

def load_data(stock_list, start="2018-01-01", end="2025-01-01"):
    df = D.features(
        instruments=stock_list,
        fields=["$close", "$volume"],
        start_time=start,
        end_time=end
    )
    df = df.reset_index()
    df.columns = ["date", "tic", "close", "volume"]
    return df
def get_margin_data(stock_list, start_date, end_date):
    """
    获取个股两融明细并转化为标准格式
    """
    all_margin = []
    for ticker in stock_list:
        # 获取个股两融数据 (以同花顺接口为例)
        df = ak.stock_margin_detail_szh_ths(symbol=ticker)
        # 统一列名并过滤日期
        df = df[['日期', '股票代码', '融资余额', '融资买入额']]
        df.columns = ['date', 'tic', 'margin_balance', 'margin_buy']
        all_margin.append(df)
    
    margin_df = pd.concat(all_margin)
    margin_df['date'] = pd.to_datetime(margin_df['date'])
    return margin_df