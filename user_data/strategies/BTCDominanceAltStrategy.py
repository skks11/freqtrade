# pragma pylint: disable=missing-docstring, invalid-name, pointless-string-statement
# flake8: noqa: F401
# isort: skip_file
# --- Do not remove these libs ---
import numpy as np
import pandas as pd
from pandas import DataFrame
from datetime import datetime
from typing import Optional, Union

from freqtrade.strategy import (BooleanParameter, CategoricalParameter, DecimalParameter,
                                IntParameter, IStrategy, merge_informative_pair)

# --------------------------------
# Add your lib to import here
import talib.abstract as ta
import pandas_ta as pta
from technical import qtpylib


class BTCDominanceAltStrategy(IStrategy):
    """
    基于Bitcoin Dominance Cheat Sheet的山寨币交易策略
    
    策略逻辑：
    1. 绿色区域（看涨山寨币）：BTC.D下跌 + BTC上涨 = 山寨币季节
    2. 黄色区域（中性）：BTC.D稳定 + BTC稳定 = 观望
    3. 红色区域（看跌山寨币）：BTC.D上涨 + BTC下跌 = 避险
    """

    INTERFACE_VERSION = 3

    # 可选参数优化
    timeframe = '30m'
    
    # ROI table
    minimal_roi = {
        "0": 0.15,    # 15%利润
        "30": 0.10,   # 30分钟后降至10%
        "60": 0.05,   # 1小时后降至5%
        "120": 0.02   # 2小时后降至2%
    }

    # Stoploss
    stoploss = -0.08  # 8%止损

    # Trailing stop
    trailing_stop = True
    trailing_stop_positive = 0.02
    trailing_stop_positive_offset = 0.05
    trailing_only_offset_is_reached = True

    # 只做多
    can_short = False

    # 运行时仓位调整
    process_only_new_candles = True
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    startup_candle_count: int = 200

    # 策略参数
    buy_btcd_trend_period = IntParameter(10, 30, default=20, space='buy', optimize=True)
    buy_btc_trend_period = IntParameter(10, 30, default=20, space='buy', optimize=True)
    
    # BTC.D和BTC趋势判断阈值
    btcd_down_threshold = DecimalParameter(-0.015, -0.001, default=-0.005, decimals=4, space='buy', optimize=True)
    btcd_stable_upper = DecimalParameter(0.001, 0.010, default=0.005, decimals=4, space='buy', optimize=True)
    btcd_stable_lower = DecimalParameter(-0.010, -0.001, default=-0.005, decimals=4, space='buy', optimize=True)
    
    btc_up_threshold = DecimalParameter(0.001, 0.015, default=0.005, decimals=4, space='buy', optimize=True)
    btc_stable_upper = DecimalParameter(0.001, 0.010, default=0.005, decimals=4, space='buy', optimize=True)
    btc_stable_lower = DecimalParameter(-0.010, -0.001, default=-0.005, decimals=4, space='buy', optimize=True)

    # RSI参数
    buy_rsi_period = IntParameter(10, 20, default=14, space='buy', optimize=True)
    buy_rsi = IntParameter(20, 40, default=35, space='buy', optimize=True)
    sell_rsi = IntParameter(60, 80, default=70, space='sell', optimize=True)

    # 交易量确认
    volume_check = BooleanParameter(default=True, space='buy', optimize=False)

    def informative_pairs(self):
        """
        定义需要的额外交易对数据
        """
        pairs = []
        # BTC/USDT用于BTC价格趋势
        pairs.append(('BTC/USDT', self.timeframe))
        # BTC.D/USDT用于BTC市场占有率（如果交易所支持）
        # 注意：大多数交易所不直接提供BTC.D，可能需要通过API单独获取
        return pairs

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        添加技术指标
        """
        # === 基础指标 ===
        # RSI
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        
        # EMA
        dataframe['ema_20'] = ta.EMA(dataframe, timeperiod=20)
        dataframe['ema_50'] = ta.EMA(dataframe, timeperiod=50)
        dataframe['ema_100'] = ta.EMA(dataframe, timeperiod=100)
        
        # MACD
        macd = ta.MACD(dataframe)
        dataframe['macd'] = macd['macd']
        dataframe['macdsignal'] = macd['macdsignal']
        dataframe['macdhist'] = macd['macdhist']
        
        # Bollinger Bands
        bollinger = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=20, stds=2)
        dataframe['bb_lowerband'] = bollinger['lower']
        dataframe['bb_middleband'] = bollinger['mid']
        dataframe['bb_upperband'] = bollinger['upper']
        
        # 交易量指标
        dataframe['volume_mean'] = dataframe['volume'].rolling(window=20).mean()
        
        # === BTC信息对指标 ===
        if self.dp:
            # 获取BTC/USDT数据
            btc_dataframe = self.dp.get_pair_dataframe(pair='BTC/USDT', timeframe=self.timeframe)
            
            if not btc_dataframe.empty:
                # BTC价格变化率
                btc_dataframe['btc_change'] = btc_dataframe['close'].pct_change(periods=self.buy_btc_trend_period.value)
                
                # BTC趋势判断
                btc_dataframe['btc_trend'] = 'STABLE'
                btc_dataframe.loc[btc_dataframe['btc_change'] > self.btc_up_threshold.value, 'btc_trend'] = 'UP'
                btc_dataframe.loc[btc_dataframe['btc_change'] < self.btc_stable_lower.value, 'btc_trend'] = 'DOWN'
                
                # BTC EMA
                btc_dataframe['btc_ema_20'] = ta.EMA(btc_dataframe, timeperiod=20)
                btc_dataframe['btc_ema_50'] = ta.EMA(btc_dataframe, timeperiod=50)
                
                # 合并到主dataframe
                dataframe = merge_informative_pair(dataframe, btc_dataframe, self.timeframe, self.timeframe, ffill=True)
        
        # === 模拟BTC.D指标 ===
        # 注意：真实环境中需要从外部API获取BTC.D数据
        # 这里使用BTC相对强度作为代理指标
        if 'close_BTC/USDT' in dataframe.columns:
            # 山寨币相对BTC的强度
            dataframe['alt_btc_ratio'] = dataframe['close'] / dataframe['close_BTC/USDT']
            trend_period = max(int(self.buy_btcd_trend_period.value / 2), 5)
            dataframe['alt_btc_ratio_change'] = dataframe['alt_btc_ratio'].pct_change(periods=trend_period)
            
            # 反向模拟BTC.D趋势（山寨币强则BTC.D弱）
            dataframe['btcd_change'] = -dataframe['alt_btc_ratio_change']
            
            # BTC.D趋势判断
            dataframe['btcd_trend'] = 'STABLE'
            dataframe.loc[dataframe['btcd_change'] > self.btcd_stable_upper.value, 'btcd_trend'] = 'UP'
            dataframe.loc[dataframe['btcd_change'] < self.btcd_down_threshold.value, 'btcd_trend'] = 'DOWN'
        else:
            # 如果没有BTC数据，使用默认值
            dataframe['btcd_trend'] = 'STABLE'
            dataframe['btc_trend_BTC/USDT'] = 'STABLE'
        
        # === 市场阶段判断 ===
        dataframe['market_phase'] = 'NEUTRAL'
        
        # 绿色区域 - ALT SEASON（最佳买入）
        dataframe.loc[
            (dataframe['btcd_trend'] == 'DOWN') & 
            (dataframe['btc_trend_BTC/USDT'] == 'UP'),
            'market_phase'
        ] = 'ALT_SEASON'
        
        # 黄色区域 - 中性（谨慎交易）
        dataframe.loc[
            (dataframe['btcd_trend'] == 'STABLE') & 
            (dataframe['btc_trend_BTC/USDT'].isin(['STABLE', 'UP'])),
            'market_phase'
        ] = 'NEUTRAL'
        
        # 红色区域 - 避险（不买入/卖出）
        dataframe.loc[
            (dataframe['btcd_trend'] == 'UP') & 
            (dataframe['btc_trend_BTC/USDT'] == 'DOWN'),
            'market_phase'
        ] = 'RISK_OFF'
        
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        买入信号
        """
        conditions = []
        
        # 条件1：RSI超卖但未过度超卖
        conditions.append(
            (dataframe['rsi'] < self.buy_rsi.value) &
            (dataframe['rsi'] > 15)  # 避免接飞刀
        )
        
        # 条件2：价格在上升趋势
        conditions.append(
            (dataframe['close'] > dataframe['ema_20']) |
            (dataframe['close'] > dataframe['ema_50'])
        )
        
        # 条件3：MACD看涨
        conditions.append(dataframe['macd'] > dataframe['macdsignal'])
        
        # 条件4：交易量确认
        if self.volume_check.value:
            conditions.append(dataframe['volume'] > dataframe['volume_mean'] * 0.3)
        
        # 条件5：价格未显著突破上轨（避免追高）
        conditions.append(dataframe['close'] < dataframe['bb_upperband'] * 1.05)
        
        if conditions:
            dataframe.loc[
                reduce(lambda x, y: x & y, conditions),
                'enter_long'] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        卖出信号
        """
        conditions = []
        
        # 条件1：进入风险规避阶段
        risk_off = dataframe['market_phase'] == 'RISK_OFF'
        
        # 条件2：RSI超买
        rsi_overbought = dataframe['rsi'] > self.sell_rsi.value
        
        # 条件3：MACD死叉
        macd_cross = qtpylib.crossed_below(dataframe['macd'], dataframe['macdsignal'])
        
        # 条件4：价格跌破EMA20
        price_below_ema = qtpylib.crossed_below(dataframe['close'], dataframe['ema_20'])
        
        # 任何一个强卖出信号触发
        dataframe.loc[
            risk_off | 
            (rsi_overbought & macd_cross) |
            (price_below_ema & (dataframe['rsi'] > 65)),
            'exit_long'] = 1

        return dataframe


# 辅助函数
def reduce(func, iterable, initializer=None):
    """简化的reduce函数"""
    it = iter(iterable)
    if initializer is None:
        value = next(it)
    else:
        value = initializer
    for element in it:
        value = func(value, element)
    return value
