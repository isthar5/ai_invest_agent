# app/config/stock_pool.py

# 统一股票池配置
CHEMICAL_STOCK_POOL = {
    "600309": {"name": "万华化学", "sector": "Chemical", "tag": "MDI/Polyurethane"},
    "000792": {"name": "盐湖股份", "sector": "Chemical", "tag": "Potash/Lithium"},
    "000408": {"name": "藏格矿业", "sector": "Chemical", "tag": "Potash/Lithium"},
    "002709": {"name": "天赐材料", "sector": "Chemical", "tag": "LiPF6/Battery"},
    "600160": {"name": "巨化股份", "sector": "Chemical", "tag": "Fluorochemicals"},
    "600346": {"name": "恒力石化", "sector": "Chemical", "tag": "Refining/PTA"},
    "600426": {"name": "华鲁恒升", "sector": "Chemical", "tag": "Coal_Chemical"},
    "600989": {"name": "宝丰能源", "sector": "Chemical", "tag": "Coal_to_Olefin"},
    "600096": {"name": "云天化", "sector": "Chemical", "tag": "Phosphate"},
    "600143": {"name": "金发科技", "sector": "Chemical", "tag": "Modified_Plastics"},
    "000703": {"name": "恒逸石化", "sector": "Chemical", "tag": "Polyester/PTA"},
    "300231": {"name": "川发龙蟒", "sector": "Chemical", "tag": "Phosphate"},
    "002648": {"name": "卫星化学", "sector": "Chemical", "tag": "Ethylene/PDH"},
    "600331": {"name": "宏达股份", "sector": "Chemical", "tag": "Zinc/Phosphate"},
    "002096": {"name": "易普力", "sector": "Chemical", "tag": "Civil_Explosives"},
    "002601": {"name": "龙佰集团", "sector": "Chemical", "tag": "Titanium_Dioxide"},
    "002493": {"name": "荣盛石化", "sector": "Chemical", "tag": "Refining"},
    "000301": {"name": "东方盛虹", "sector": "Chemical", "tag": "Refining/Fiber"},
    "002683": {"name": "广东宏大", "sector": "Chemical", "tag": "Civil_Explosives"},
    "300699": {"name": "光威复材", "sector": "Chemical", "tag": "Carbon_Fiber"},
    "688065": {"name": "凯赛生物", "sector": "Chemical", "tag": "Synthetic_Biology"},
    "300037": {"name": "新宙邦", "sector": "Chemical", "tag": "Electrolyte"},
    "002812": {"name": "恩捷股份", "sector": "Chemical", "tag": "Separator"},
    "000893": {"name": "亚钾国际", "sector": "Chemical", "tag": "Potash"},
    "000818": {"name": "航锦科技", "sector": "Chemical", "tag": "Chlor-alkali/Chip"},
    "603826": {"name": "坤彩科技", "sector": "Chemical", "tag": "Pearlescent_Pigment"},
    "002407": {"name": "多氟多", "sector": "Chemical", "tag": "Fluoride/Battery"},
    "603260": {"name": "合盛硅业", "sector": "Chemical", "tag": "Silicon"},
    "301035": {"name": "润丰股份", "sector": "Chemical", "tag": "Pesticide"},
    "688639": {"name": "华恒生物", "sector": "Chemical", "tag": "Amino_Acid"},
    "603033": {"name": "三维股份", "sector": "Chemical", "tag": "BDO/Rubber"},
    "605589": {"name": "圣泉集团", "sector": "Chemical", "tag": "Phenolic_Resin"},
    "300487": {"name": "蓝晓科技", "sector": "Chemical", "tag": "Adsorption_Resin"},
}

# 方便 DataEngine 获取代码列表
STOCK_LIST = list(CHEMICAL_STOCK_POOL.keys())

# 存储路径配置 (Windows 上指向你的高性能盘)
DATA_DIR = "./data/chemical_sector"
MODEL_PATH = "./models/lgb_chem_30.pkl"
SIGNAL_OUTPUT = "./output/latest_signals.json"
