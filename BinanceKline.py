import asyncio
import json
import websockets
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone
import time
import os
from pathlib import Path
from flask import Flask, request, jsonify
from flask_cors import CORS
import threading
import queue
from concurrent.futures import ThreadPoolExecutor

import logging
logfile = './Log/BinanceKline.log'
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    handlers=[
        logging.FileHandler(logfile),
        logging.StreamHandler()
    ])

log = logging.getLogger('')

def logit(*args, **kwargs):
    log.info(*args, **kwargs)

# 創建 Flask 應用
app = Flask(__name__)
CORS(app)  # 允許跨域請求

SYMBOLS = ['BTC', 'ETH', 'BNB', 'ADA', 'SOL', 'XRP', 'DOGE']

# 全局隊列和處理器
request_queue = queue.Queue()
processing = False

def queue_processor():
    """隊列處理器 - 順序處理所有請求"""
    global processing
    
    logit("隊列處理器啟動")
    
    while True:
        try:
            # 從隊列獲取請求
            request_data = request_queue.get(timeout=1)
            if request_data is None:  # 停止信號
                break
                
            request_id, symbol, hours, response_queue = request_data
            logit(f"處理請求 {request_id}: {symbol} {hours}小時")
            
            # 處理請求
            try:
                result = process_klines_request(symbol, hours)
                response_queue.put((request_id, result))
                logit(f"請求 {request_id} 處理完成")
            except Exception as e:
                error_response = {
                    'success': False,
                    'error': str(e)
                }
                response_queue.put((request_id, error_response))
                logit(f"請求 {request_id} 處理失敗: {e}")
            
            request_queue.task_done()
            
        except queue.Empty:
            continue
        except Exception as e:
            logit(f"隊列處理器錯誤: {e}")
    
    logit("隊列處理器停止")

def process_klines_request(symbol, hours):
    """處理K線請求的核心邏輯"""
    # 驗證參數
    if symbol not in SYMBOLS:
        return jsonify({
            'success': False,
            'error': f'Invalid symbol. Must be one of: {", ".join(SYMBOLS)}.'
        }), 400
    
    if not isinstance(hours, int) or hours <= 0 or hours > 200:
        return jsonify({
            'success': False,
            'error': 'Invalid hours. Must be between 1 and 200.'
        }), 400
    
    # 檢查是否有本地數據庫
    kline_dir = Path(f"Kline/{symbol}")
    has_local_data = kline_dir.exists() and any(kline_dir.glob(f"{symbol}_*.csv"))
    
    if not has_local_data:
        logit(f"檢測到{symbol}沒有本地數據庫，開始初始化...")
        init_df = initialize_local_database(symbol)
        if init_df.empty:
            return jsonify({
                'success': False,
                'error': f'Failed to initialize local database for {symbol}'
            }), 500
    
    # 從本地文件讀取歷史數據
    local_df = get_klines_from_local_files(symbol, hours)
    
    # 獲取最新的增量數據
    latest_df = get_klines_with_incremental_update(symbol, hours=hours)
    
    # 合併數據
    if not local_df.empty and not latest_df.empty:
        combined_df = pd.concat([local_df, latest_df], ignore_index=True)
        combined_df = combined_df.drop_duplicates(subset=['open_time'], keep='last')
        combined_df = combined_df.sort_values('open_time')
        
        logit(f"合併本地數據({len(local_df)}行)和最新數據({len(latest_df)}行)，總計{len(combined_df)}行")
        
    elif not local_df.empty:
        combined_df = local_df
        logit(f"只使用本地數據，共{len(combined_df)}行")
        
    elif not latest_df.empty:
        combined_df = latest_df
        logit(f"只使用最新數據，共{len(combined_df)}行")
        
    else:
        return jsonify({
            'success': False,
            'error': f'No data available for {symbol}'
        }), 404
    
    # 轉換為JSON格式
    df_filtered = combined_df[['open_time', 'open', 'high', 'low', 'close', 'volume']].copy()
    df_filtered.rename(columns={'open_time': 'time'}, inplace=True)
    df_filtered['time'] = df_filtered['time'].dt.strftime('%Y-%m-%d %H:%M:%S')
    
    klines_data = df_filtered.to_dict('records')
    
    # 構建響應數據
    response_data = {
        'success': True,
        'symbol': symbol,
        'hours': hours,
        'count': len(klines_data),
        'data': klines_data,
        'time_range': {
            'start': df_filtered['time'].iloc[0],
            'end': df_filtered['time'].iloc[-1]
        },
        'data_source': {
            'local_files': len(local_df),
            'latest_api': len(latest_df),
            'total_combined': len(combined_df)
        }
    }
    
    if not has_local_data:
        response_data['database_initialized'] = True
        response_data['initialization_message'] = f'Local database for {symbol} has been initialized with 200 hours of historical data'
    
    return response_data

def get_binance_futures_klines(symbol, interval, start_time, end_time, limit=1000):
    """
    從 Binance Futures API 獲取 K線數據
    
    參數:
    - symbol: 交易對 (例如: 'BTCUSDT')
    - interval: 時間間隔 (例如: '1m')
    - start_time: 開始時間 (毫秒時間戳)
    - end_time: 結束時間 (毫秒時間戳)
    - limit: 每次請求的最大K線數量 (最大1000)
    
    返回:
    - DataFrame: 包含K線數據的DataFrame
    """
    base_url = "https://fapi.binance.com/fapi/v1/klines"
    
    all_klines = []
    current_start = start_time
    
    while current_start < end_time:
        params = {
            'symbol': symbol,
            'interval': interval,
            'startTime': current_start,
            'endTime': min(current_start + (limit - 1) * 60 * 1000, end_time),  # 轉換為毫秒
            'limit': limit
        }
        
        try:
            response = requests.get(base_url, params=params)
            response.raise_for_status()
            klines = response.json()
            
            if not klines:
                break
                
            all_klines.extend(klines)
            
            # 更新下一次請求的開始時間
            current_start = klines[-1][0] + 1  # 最後一根K線的時間 + 1毫秒
            
            logit(f"已獲取 {len(klines)} 根K線，總計 {len(all_klines)} 根")
            
            # 避免請求過於頻繁
            time.sleep(0.1)
            
        except requests.exceptions.RequestException as e:
            logit(f"API請求錯誤: {e}")
            break
    
    # 轉換為DataFrame
    if all_klines:
        df = pd.DataFrame(all_klines, columns=[
            'open_time', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_volume', 'trades', 'taker_buy_base_volume',
            'taker_buy_quote_volume', 'ignore'
        ])
        
        # 轉換數據類型 - 使用UTC時間
        df['open_time'] = pd.to_datetime(df['open_time'], unit='ms', utc=True)
        df['close_time'] = pd.to_datetime(df['close_time'], unit='ms', utc=True)
        
        numeric_columns = ['open', 'high', 'low', 'close', 'volume', 'quote_volume', 
                          'trades', 'taker_buy_base_volume', 'taker_buy_quote_volume']
        for col in numeric_columns:
            df[col] = pd.to_numeric(df[col])
        
        return df
    else:
        return pd.DataFrame()

def get_latest_data_time(symbol):
    """
    獲取本地最新數據的時間
    
    參數:
    - symbol: 交易對 (例如: 'BTC' 或 'ETH')
    
    返回:
    - datetime: 最新數據的時間，如果沒有數據則返回None
    """
    kline_dir = Path(f"Kline/{symbol}")
    if not kline_dir.exists():
        return None
    
    latest_time = None
    for csv_file in kline_dir.glob(f"{symbol}_*.csv"):
        try:
            df = pd.read_csv(csv_file)
            if not df.empty and 'time' in df.columns:
                # 轉換時間欄位為datetime（假設時間格式為 yyyy-MM-dd HH:mm:ss）
                df['time'] = pd.to_datetime(df['time'], format='%Y-%m-%d %H:%M:%S')
                file_latest_time = df['time'].max()
                if latest_time is None or file_latest_time > latest_time:
                    latest_time = file_latest_time
        except Exception as e:
            logit(f"讀取文件 {csv_file} 時發生錯誤: {e}")
    
    return latest_time

def save_klines_by_date(df, symbol):
    """
    按日期將K線數據保存到不同的CSV文件
    
    參數:
    - df: 包含K線數據的DataFrame
    - symbol: 交易對 (例如: 'BTC' 或 'ETH')
    """
    if df.empty:
        return
    
    # 只保留需要的欄位
    df_filtered = df[['open_time', 'open', 'high', 'low', 'close', 'volume']].copy()
    df_filtered.rename(columns={'open_time': 'time'}, inplace=True)
    
    # 將時間格式轉換為 yyyy-MM-dd HH:mm:ss 格式（不包含時區信息）
    df_filtered['time'] = df_filtered['time'].dt.strftime('%Y-%m-%d %H:%M:%S')
    
    # 創建目錄
    kline_dir = Path(f"Kline/{symbol}")
    kline_dir.mkdir(parents=True, exist_ok=True)
    
    # 按日期分組並保存
    df_filtered['date'] = pd.to_datetime(df_filtered['time']).dt.date
    grouped = df_filtered.groupby('date')
    
    for date, group in grouped:
        # 移除date欄位，只保留需要的欄位
        group_to_save = group[['time', 'open', 'high', 'low', 'close', 'volume']].copy()
        
        # 生成文件名
        date_str = date.strftime('%Y-%m-%d')
        filename = kline_dir / f"{symbol}_{date_str}.csv"
        
        # 檢查文件是否已存在
        if filename.exists():
            try:
                # 讀取現有文件
                existing_df = pd.read_csv(filename)
                existing_df['time'] = pd.to_datetime(existing_df['time'], format='%Y-%m-%d %H:%M:%S')
                
                # 將新數據的時間也轉換為datetime格式以便比較
                group_to_save_temp = group_to_save.copy()
                group_to_save_temp['time'] = pd.to_datetime(group_to_save_temp['time'], format='%Y-%m-%d %H:%M:%S')
                
                # 合併數據，去重
                combined_df = pd.concat([existing_df, group_to_save_temp], ignore_index=True)
                combined_df = combined_df.drop_duplicates(subset=['time'], keep='last')
                combined_df = combined_df.sort_values('time')
                
                # 將時間格式轉換為 yyyy-MM-dd HH:mm:ss 格式
                combined_df['time'] = combined_df['time'].dt.strftime('%Y-%m-%d %H:%M:%S')
                
                # 保存
                combined_df.to_csv(filename, index=False)
                logit(f"更新文件: {filename}, 新增 {len(group_to_save)} 行數據")
            except Exception as e:
                logit(f"更新文件 {filename} 時發生錯誤: {e}")
        else:
            # 新文件，直接保存
            group_to_save.to_csv(filename, index=False)
            logit(f"創建新文件: {filename}, 保存 {len(group_to_save)} 行數據")

def get_klines_with_incremental_update(symbol, hours=200):
    """
    獲取K線數據，支持增量更新
    
    參數:
    - symbol: 交易對 (例如: 'BTC' 或 'ETH')
    - hours: 要獲取的小時數
    
    返回:
    - DataFrame: 包含K線數據的DataFrame
    """
    # 獲取本地最新數據時間
    latest_local_time = get_latest_data_time(symbol)
    
    # 計算時間範圍
    end_time = datetime.now(timezone.utc)  # 使用UTC時間
    start_time = end_time - timedelta(hours=hours)
    
    # 如果有本地數據，從最新數據時間開始獲取
    if latest_local_time is not None:
        # 轉換為UTC時間
        if latest_local_time.tzinfo is None:
            latest_local_time = latest_local_time.replace(tzinfo=timezone.utc)
        
        # 從最新數據時間後1分鐘開始獲取
        actual_start_time = latest_local_time + timedelta(minutes=1)
        
        # 如果實際開始時間晚於計算的開始時間，使用實際開始時間
        if actual_start_time > start_time:
            start_time = actual_start_time
            logit(f"檢測到本地已有數據，從 {start_time} 開始增量更新")
        else:
            logit(f"本地數據較舊，重新獲取過去 {hours} 小時的數據")
    else:
        logit(f"本地無數據，獲取過去 {hours} 小時的數據")
    
    # 轉換為毫秒時間戳
    start_timestamp = int(start_time.timestamp() * 1000)
    end_timestamp = int(end_time.timestamp() * 1000)
    
    logit(f"開始獲取{symbol} 1分鐘K線數據")
    logit(f"時間範圍: {start_time} 到 {end_time}")
    
    # 獲取K線數據
    symbol_pair = f"{symbol}USDT"
    df = get_binance_futures_klines(symbol_pair, '1m', start_timestamp, end_timestamp)
    
    if not df.empty:
        logit(f"成功獲取 {len(df)} 根{symbol} K線數據")
        logit(f"數據時間範圍: {df['open_time'].min()} 到 {df['open_time'].max()}")
        
        # 按日期保存數據
        save_klines_by_date(df, symbol)
        
        return df
    else:
        logit(f"未能獲取到{symbol} K線數據")
        return pd.DataFrame()  # 返回空的DataFrame而不是None

def get_klines_from_local_files(symbol, hours):
    """
    從本地文件讀取指定小時數的K線數據（優化版：只讀取必要的文件）
    
    參數:
    - symbol: 交易對 (例如: 'BTC' 或 'ETH')
    - hours: 要獲取的小時數
    
    返回:
    - DataFrame: 包含K線數據的DataFrame
    """
    kline_dir = Path(f"Kline/{symbol}")
    if not kline_dir.exists():
        return pd.DataFrame()
    
    # 計算時間範圍
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=hours)
    
    logit(f"從本地文件讀取{symbol}數據，時間範圍: {start_time} 到 {end_time}")
    
    # 計算需要讀取的日期範圍
    start_date = start_time.date()
    end_date = end_time.date()
    
    logit(f"需要讀取的日期範圍: {start_date} 到 {end_date}")
    
    all_data = []
    files_to_read = []
    
    # 根據檔名日期篩選需要讀取的文件
    for csv_file in kline_dir.glob(f"{symbol}_*.csv"):
        try:
            # 從檔名提取日期 (格式: BTC_2025-09-04.csv)
            filename = csv_file.stem  # 移除 .csv 後綴
            date_str = filename.replace(f"{symbol}_", "")  # 移除 BTC_ 前綴
            
            # 解析日期
            file_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            
            # 檢查日期是否在需要的範圍內
            if start_date <= file_date <= end_date:
                files_to_read.append(csv_file)
                logit(f"需要讀取文件: {csv_file.name} (日期: {file_date})")
                
        except Exception as e:
            logit(f"解析文件 {csv_file.name} 日期時發生錯誤: {e}")
    
    logit(f"總共需要讀取 {len(files_to_read)} 個文件")
    
    # 只讀取必要的文件
    for csv_file in files_to_read:
        try:
            df = pd.read_csv(csv_file)
            logit(f"讀取文件 {csv_file.name}")
            
            if not df.empty and 'time' in df.columns:
                # 轉換時間欄位為datetime，並設置時區為UTC
                df['time'] = pd.to_datetime(df['time'], format='%Y-%m-%d %H:%M:%S', utc=True)
                
                # 過濾時間範圍內的數據
                mask = (df['time'] >= start_time) & (df['time'] <= end_time)
                filtered_df = df[mask].copy()
                
                if not filtered_df.empty:
                    # 轉換為與API格式一致的格式
                    filtered_df['open_time'] = filtered_df['time']
                    filtered_df = filtered_df[['open_time', 'open', 'high', 'low', 'close', 'volume']]
                    all_data.append(filtered_df)
                    
                    logit(f"從文件 {csv_file.name} 讀取 {len(filtered_df)} 行數據")
                else:
                    logit(f"文件 {csv_file.name} 沒有符合時間範圍的數據")
                    
        except Exception as e:
            logit(f"讀取文件 {csv_file} 時發生錯誤: {e}")
    
    if all_data:
        # 合併所有數據
        combined_df = pd.concat(all_data, ignore_index=True)
        
        # 去重並排序
        combined_df = combined_df.drop_duplicates(subset=['open_time'], keep='last')
        combined_df = combined_df.sort_values('open_time')
        
        logit(f"從本地文件總共讀取 {len(combined_df)} 行{symbol}數據")
        return combined_df
    else:
        logit(f"本地文件中沒有找到{symbol}的數據")
        return pd.DataFrame()

def initialize_local_database(symbol):
    """
    初始化本地數據庫：獲取200小時的歷史數據並存檔
    
    參數:
    - symbol: 交易對 (例如: 'BTC' 或 'ETH')
    
    返回:
    - DataFrame: 包含歷史數據的DataFrame
    """
    logit(f"初始化{symbol}本地數據庫，獲取200小時歷史數據")
    
    try:
        # 獲取200小時的歷史數據
        df = get_klines_with_incremental_update(symbol, hours=200)
        
        if not df.empty:
            logit(f"成功初始化{symbol}本地數據庫，獲取{len(df)}行歷史數據")
            return df
        else:
            logit(f"初始化{symbol}本地數據庫失敗，未能獲取歷史數據")
            return pd.DataFrame()
            
    except Exception as e:
        logit(f"初始化{symbol}本地數據庫時發生錯誤: {e}")
        return pd.DataFrame()

def submit_request_to_queue(symbol, hours):
    """將請求提交到隊列並等待響應"""
    # 生成請求ID
    request_id = f"{symbol}_{hours}_{int(time.time() * 1000)}"
    
    # 創建響應隊列
    response_queue = queue.Queue()
    
    # 提交請求到隊列
    request_data = (request_id, symbol, hours, response_queue)
    request_queue.put(request_data)
    
    logit(f"請求已提交到隊列: {request_id}")
    
    # 等待響應（最多60秒）
    try:
        response_id, result = response_queue.get(timeout=60)
        if response_id == request_id:
            return result
        else:
            return jsonify({
                'success': False,
                'error': 'Response ID mismatch'
            }), 500
    except queue.Empty:
        return jsonify({
            'success': False,
            'error': 'Request timeout'
        }), 504

@app.route('/kline', methods=['GET'])
def kline_endpoint():
    """
    K線數據API端點（隊列模式）
    
    參數:
    - symbol: 交易對 (BTC 或 ETH)
    - hours: 小時數 (1-200)
    
    示例:
    GET /kline?symbol=BTC&hours=20
    """
    try:
        # 獲取參數
        symbol = request.args.get('symbol', '').upper()
        hours = request.args.get('hours', type=int)
        
        # 驗證必要參數
        if not symbol:
            return jsonify({
                'success': False,
                'error': 'Missing required parameter: symbol'
            }), 400
        
        if hours is None:
            return jsonify({
                'success': False,
                'error': 'Missing required parameter: hours'
            }), 400
        
        # 提交請求到隊列
        return submit_request_to_queue(symbol, hours)
        
    except Exception as e:
        logit(f"端點錯誤: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/health', methods=['GET'])
def health_check():
    """
    健康檢查端點
    """
    return jsonify({
        'status': 'healthy',
        'service': 'Binance Kline API (Queue Mode)',
        'timestamp': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'),
        'queue_status': {
            'queue_size': request_queue.qsize(),
            'processing': processing
        }
    })

@app.route('/', methods=['GET'])
def root():
    """
    根端點，顯示API信息
    """
    return jsonify({
        'service': 'Binance Kline API Server (Queue Mode)',
        'version': '2.0.0',
        'endpoints': {
            'GET /': 'API信息',
            'GET /health': '健康檢查',
            'GET /kline?symbol=BTC&hours=20': '獲取K線數據'
        },
        'supported_symbols': SYMBOLS,
        'parameters': {
            'symbol': f'交易對 (支持: {", ".join(SYMBOLS)})',
            'hours': '小時數 (1-200)'
        },
        'processing_mode': 'Queue-based sequential processing',
        'features': {
            'queue_processing': '隊列順序處理，避免並發衝突',
            'auto_initialization': '自動初始化本地數據庫（200小時歷史數據）',
            'incremental_update': '增量更新機制',
            'local_file_optimization': '智能文件讀取（只讀取必要文件）',
            'data_merging': '本地數據與最新API數據合併'
        },
        'performance': {
            'max_concurrent_requests': 'Unlimited (queued)',
            'request_timeout': '60秒',
            'processing_order': 'FIFO (First In, First Out)'
        },
        'example': '/kline?symbol=BTC&hours=20'
    })

def start_server(host='0.0.0.0', port=5000):
    """
    啟動Flask服務器（隊列模式）
    """
    global processing
    
    logit(f"=== 啟動 Binance Kline API Server (Queue Mode) ===")
    logit(f"服務器地址: http://{host}:{port}")
    logit(f"API端點: http://{host}:{port}/kline")
    logit(f"健康檢查: http://{host}:{port}/health")
    logit(f"處理模式: 隊列順序處理")
    
    # 啟動隊列處理器
    processing = True
    queue_thread = threading.Thread(target=queue_processor, daemon=True)
    queue_thread.start()
    
    try:
        app.run(host=host, port=port, debug=False, threaded=True)
    finally:
        # 停止隊列處理器
        processing = False
        request_queue.put(None)  # 發送停止信號
        queue_thread.join(timeout=5)

async def main():
    """
    主函數：啟動API服務器
    """
    logit("=== 開始執行 Binance Futures K線數據API服務器 (Queue Mode) ===")
    
    try:
        # 啟動Flask服務器
        start_server()
            
    except Exception as e:
        logit(f"執行過程中發生錯誤: {e}")

if __name__ == "__main__":
    asyncio.run(main())
