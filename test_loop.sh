while true; do
    date '+%F %T'
    python3 TestBinance.py --market futures --symbol BTCUSDT --count 3 --timeout 10 && break
    echo "failed, retry in 10s..."
    sleep 10
done
echo "success, stop retry."
 