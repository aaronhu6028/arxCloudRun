#!/bin/bash -e
sname=${HOSTNAME#*-}
sname=${sname^^}
(cd ${HOME}/arxCloudRun && git pull)
(cd ${HOME}/arxCloudRun && nohup dotnet arxServer.dll $sname >> nohup.$(date +%Y-%m-%d-%H%M).out &)
exit 0