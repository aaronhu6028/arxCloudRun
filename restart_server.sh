#!/bin/bash

cd $HOME/arxCloudRun
pkill -SIGINT dotnet
git pull
sleep 10
sname=${HOSTNAME#*-}
sname=${sname^^}
nohup dotnet arxServer.dll $sname &
ps ax | grep dotnet
