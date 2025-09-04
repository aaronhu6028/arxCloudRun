#!/bin/bash -e
sname=$HOSTNAME
sname=${sname%%.*}
sname=${sname#*-}
sname=${sname^^}
(cd ${HOME}/arxCloudRun && git pull)
(cd ${HOME}/arxCloudRun && python3 CoinbaseSocket.py &)
(cd ${HOME}/arxCloudRun && python3 BinanceKline.py &)
(cd ${HOME}/arxCloudRun && nohup dotnet arxServer.dll $sname >> nohup.$(date +%Y-%m-%d-%H%M).out &)
exit 0