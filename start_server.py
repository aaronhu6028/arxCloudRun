#!/usr/bin/env python3
"""
啟動腳本：啟動 Binance Kline API Server
"""

import sys
import os
from pathlib import Path

# 添加當前目錄到Python路徑
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from BinanceKline import start_server

def main():
    """
    主函數：啟動API服務器
    """
    print("=== Binance Kline API Server 啟動腳本 ===")
    print("正在啟動服務器...")
    
    try:
        # 啟動服務器
        start_server(host='0.0.0.0', port=5000)
    except KeyboardInterrupt:
        print("\n服務器已停止")
    except Exception as e:
        print(f"啟動服務器時發生錯誤: {e}")

if __name__ == "__main__":
    main()
