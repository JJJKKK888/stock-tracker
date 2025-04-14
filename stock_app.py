import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import os
import base64
import io
import numpy as np
import requests
from bs4 import BeautifulSoup

# 設定資料儲存的路徑
DATA_PATH = "portfolio_data.csv"

st.set_page_config(page_title="台股投資追蹤器", layout="wide")
st.title("台股投資追蹤器")

# 計算 RSI
def calculate_rsi(data, periods=14):
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=periods).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=periods).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

# 計算 MACD
def calculate_macd(data, fast=12, slow=26, signal=9):
    exp1 = data.ewm(span=fast, adjust=False).mean()
    exp2 = data.ewm(span=slow, adjust=False).mean()
    macd = exp1 - exp2
    signal_line = macd.ewm(span=signal, adjust=False).mean()
    histogram = macd - signal_line
    return macd, signal_line, histogram

# 計算布林帶
def calculate_bollinger_bands(data, window=20):
    middle_band = data.rolling(window=window).mean()
    std_dev = data.rolling(window=window).std()
    upper_band = middle_band + (std_dev * 2)
    lower_band = middle_band - (std_dev * 2)
    return upper_band, middle_band, lower_band

# 從 CSV 檔案讀取資料
def load_portfolio():
    if os.path.exists(DATA_PATH):
        return pd.read_csv(DATA_PATH)
    return pd.DataFrame(columns=[
        '股票代碼', '股票名稱', '買入價格', '持股數量', 
        '現價', '市值', '損益', '報酬率(%)'
    ])

# 取得技術分析指標
def get_technical_indicators(stock_code):
    stock = yf.Ticker(stock_code)
    hist = stock.history(period="1y")
    
    # 計算技術指標
    if len(hist) > 0:
        # 移動平均線
        hist['MA5'] = hist['Close'].rolling(window=5).mean()
        hist['MA20'] = hist['Close'].rolling(window=20).mean()
        hist['MA60'] = hist['Close'].rolling(window=60).mean()
        
        # RSI
        hist['RSI'] = calculate_rsi(hist['Close'])
        
        # MACD
        hist['MACD'], hist['Signal'], hist['Hist'] = calculate_macd(hist['Close'])
        
        # 布林通道
        hist['Upper'], hist['Middle'], hist['Lower'] = calculate_bollinger_bands(hist['Close'])
        
        return hist
    return None

# 取得三大法人資料
def get_institutional_investors(stock_code):
    stock_code = stock_code.replace('.TW', '')
    url = f"https://www.twse.com.tw/zh/trading/fund/T86?response=json&date={datetime.now().strftime('%Y%m%d')}&selectType=ALL"
    try:
        response = requests.get(url)
        data = response.json()
        if 'data' in data:
            df = pd.DataFrame(data['data'], columns=[
                '證券代號', '證券名稱', '外陸資買進股數', '外陸資賣出股數', 
                '投信買進股數', '投信賣出股數',
                '自營商買進股數', '自營商賣出股數'
            ])
            df = df[df['證券代號'] == stock_code]
            if not df.empty:
                return {
                    '外資': int(df['外陸資買進股數'].iloc[0].replace(',', '')) - int(df['外陸資賣出股數'].iloc[0].replace(',', '')),
                    '投信': int(df['投信買進股數'].iloc[0].replace(',', '')) - int(df['投信賣出股數'].iloc[0].replace(',', '')),
                    '自營商': int(df['自營商買進股數'].iloc[0].replace(',', '')) - int(df['自營商賣出股數'].iloc[0].replace(',', ''))
                }
    except:
        pass
    return None

# 儲存資料到 CSV 檔案
def save_portfolio(portfolio):
    portfolio.to_csv(DATA_PATH, index=False)

# 下載 CSV 檔案的功能
def get_csv_download_link(df):
    csv = df.to_csv(index=False)
    b64 = base64.b64encode(csv.encode()).decode()
    href = f'<a href="data:file/csv;base64,{b64}" download="portfolio.csv">下載 CSV 檔案</a>'
    return href

# 初始化 session state
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = load_portfolio()
if 'editing_index' not in st.session_state:
    st.session_state.editing_index = None

# 側邊欄：功能選擇
with st.sidebar:
    st.header("功能選單")
    operation = st.radio("選擇操作", ["新增股票", "編輯/刪除股票", "匯入/匯出資料"])

    if operation == "新增股票":
        st.subheader("新增股票")
        stock_code = st.text_input("股票代碼（例如：2330.TW）")
        buy_price = st.number_input("買入價格", min_value=0.0, format="%.2f")
        quantity = st.number_input("持股數量", min_value=0, step=1)
        
        if st.button("新增"):
            if stock_code and buy_price > 0 and quantity > 0:
                try:
                    stock = yf.Ticker(stock_code)
                    info = stock.info
                    current_price = info.get('regularMarketPrice', 0)
                    
                    market_value = current_price * quantity
                    profit_loss = (current_price - buy_price) * quantity
                    roi = ((current_price - buy_price) / buy_price) * 100
                    
                    new_stock = pd.DataFrame({
                        '股票代碼': [stock_code],
                        '股票名稱': [info.get('longName', stock_code)],
                        '買入價格': [buy_price],
                        '持股數量': [quantity],
                        '現價': [current_price],
                        '市值': [market_value],
                        '損益': [profit_loss],
                        '報酬率(%)': [roi]
                    })
                    
                    st.session_state.portfolio = pd.concat([st.session_state.portfolio, new_stock], ignore_index=True)
                    save_portfolio(st.session_state.portfolio)
                    st.success("成功新增股票！")
                except Exception as e:
                    st.error(f"錯誤：無法獲取股票資訊。請確認股票代碼是否正確。")

    elif operation == "編輯/刪除股票":
        if not st.session_state.portfolio.empty:
            st.subheader("編輯/刪除股票")
            for idx, row in st.session_state.portfolio.iterrows():
                col1, col2, col3 = st.columns([2,1,1])
                with col1:
                    st.write(f"{row['股票代碼']} - {row['股票名稱']}")
                with col2:
                    if st.button("編輯", key=f"edit_{idx}"):
                        st.session_state.editing_index = idx
                with col3:
                    if st.button("刪除", key=f"delete_{idx}"):
                        st.session_state.portfolio = st.session_state.portfolio.drop(idx).reset_index(drop=True)
                        save_portfolio(st.session_state.portfolio)
                        st.experimental_rerun()

            if st.session_state.editing_index is not None:
                st.subheader("編輯股票資料")
                row = st.session_state.portfolio.iloc[st.session_state.editing_index]
                new_price = st.number_input("新買入價格", value=float(row['買入價格']), format="%.2f")
                new_quantity = st.number_input("新持股數量", value=int(row['持股數量']), min_value=0, step=1)
                
                if st.button("儲存修改"):
                    st.session_state.portfolio.at[st.session_state.editing_index, '買入價格'] = new_price
                    st.session_state.portfolio.at[st.session_state.editing_index, '持股數量'] = new_quantity
                    save_portfolio(st.session_state.portfolio)
                    st.session_state.editing_index = None
                    st.experimental_rerun()
                
                if st.button("取消編輯"):
                    st.session_state.editing_index = None
                    st.experimental_rerun()

    elif operation == "匯入/匯出資料":
        st.subheader("匯入/匯出資料")
        
        # 匯出功能
        st.markdown(get_csv_download_link(st.session_state.portfolio), unsafe_allow_html=True)
        
        # 匯入功能
        uploaded_file = st.file_uploader("選擇要匯入的 CSV 檔案", type="csv")
        if uploaded_file is not None:
            try:
                imported_df = pd.read_csv(uploaded_file)
                if st.button("確認匯入"):
                    st.session_state.portfolio = imported_df
                    save_portfolio(st.session_state.portfolio)
                    st.success("成功匯入資料！")
                    st.experimental_rerun()
            except Exception as e:
                st.error("匯入失敗：請確認檔案格式是否正確。")

# 主要內容：投資組合表格
st.header("投資組合")

if not st.session_state.portfolio.empty:
    # 更新現價和計算
    for idx, row in st.session_state.portfolio.iterrows():
        try:
            stock = yf.Ticker(row['股票代碼'])
            current_price = stock.info.get('regularMarketPrice', 0)
            
            st.session_state.portfolio.at[idx, '現價'] = current_price
            st.session_state.portfolio.at[idx, '市值'] = current_price * row['持股數量']
            st.session_state.portfolio.at[idx, '損益'] = (current_price - row['買入價格']) * row['持股數量']
            st.session_state.portfolio.at[idx, '報酬率(%)'] = ((current_price - row['買入價格']) / row['買入價格']) * 100
        except:
            pass

    # 顯示表格
    st.dataframe(st.session_state.portfolio.style.format({
        '買入價格': '{:.2f}',
        '現價': '{:.2f}',
        '市值': '{:.2f}',
        '損益': '{:.2f}',
        '報酬率(%)': '{:.2f}'
    }))

    # 總覽
    total_investment = (st.session_state.portfolio['買入價格'] * st.session_state.portfolio['持股數量']).sum()
    total_value = st.session_state.portfolio['市值'].sum()
    total_profit_loss = st.session_state.portfolio['損益'].sum()
    total_roi = (total_profit_loss / total_investment) * 100 if total_investment > 0 else 0

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("總投資金額", f"${total_investment:,.2f}")
    with col2:
        st.metric("當前總市值", f"${total_value:,.2f}")
    with col3:
        st.metric("總損益", f"${total_profit_loss:,.2f}")
    with col4:
        st.metric("總報酬率", f"{total_roi:.2f}%")

    # 繪製投資組合分布圖
    fig = go.Figure(data=[go.Pie(
        labels=st.session_state.portfolio['股票名稱'],
        values=st.session_state.portfolio['市值'],
        hole=.3
    )])
    fig.update_layout(title="投資組合分布")
    st.plotly_chart(fig)

    # 新增：技術分析和籌碼分析
    st.header("技術分析與籌碼")
    selected_stock = st.selectbox(
        "選擇要分析的股票",
        st.session_state.portfolio['股票代碼'].tolist()
    )

    if selected_stock:
        tab1, tab2 = st.tabs(["技術分析", "三大法人籌碼"])
        
        with tab1:
            st.subheader("技術分析圖表")
            hist = get_technical_indicators(selected_stock)
            if hist is not None:
                # K線圖加上技術指標
                fig = go.Figure()
                
                # K線圖
                fig.add_trace(go.Candlestick(
                    x=hist.index,
                    open=hist['Open'],
                    high=hist['High'],
                    low=hist['Low'],
                    close=hist['Close'],
                    name='K線'
                ))
                
                # 移動平均線
                fig.add_trace(go.Scatter(x=hist.index, y=hist['MA5'], name='MA5', line=dict(color='blue')))
                fig.add_trace(go.Scatter(x=hist.index, y=hist['MA20'], name='MA20', line=dict(color='orange')))
                fig.add_trace(go.Scatter(x=hist.index, y=hist['MA60'], name='MA60', line=dict(color='red')))
                
                fig.update_layout(
                    title=f'{selected_stock} 技術分析',
                    yaxis_title='價格',
                    xaxis_title='日期'
                )
                st.plotly_chart(fig)
                
                # 顯示技術指標數值
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("RSI(14)", f"{hist['RSI'].iloc[-1]:.2f}")
                with col2:
                    st.metric("MACD", f"{hist['MACD'].iloc[-1]:.2f}")
                with col3:
                    st.metric("布林帶寬度", f"{(hist['Upper'].iloc[-1] - hist['Lower'].iloc[-1]) / hist['Middle'].iloc[-1] * 100:.2f}%")
        
        with tab2:
            st.subheader("三大法人買賣超")
            inst_data = get_institutional_investors(selected_stock)
            if inst_data:
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("外資買賣超", f"{inst_data['外資']:,} 股")
                with col2:
                    st.metric("投信買賣超", f"{inst_data['投信']:,} 股")
                with col3:
                    st.metric("自營商買賣超", f"{inst_data['自營商']:,} 股")
            else:
                st.info("無法取得三大法人資料")

    # 儲存更新後的資料
    save_portfolio(st.session_state.portfolio)

else:
    st.info("尚未新增任何股票，請在左側新增股票。")

# 更新按鈕
if st.button("更新資料"):
    st.experimental_rerun() 