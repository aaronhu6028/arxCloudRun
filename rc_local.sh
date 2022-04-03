#!/bin/bash -e
sname=${HOSTNAME#*-}
sname=${sname^^}
(cd /home/aaronhu6028/arxCloudRun && git pull)
(cd /home/aaronhu6028/arxCloudRun && nohup dotnet arxServer.dll $sname >> nohup.$(date +%Y-%m-%d-%H%M).out &)
exit 0