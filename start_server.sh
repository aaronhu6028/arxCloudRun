#!/bin/bash

git pull
sname=${HOSTNAME#*-} | tr '[:upper:]' '[:lower:]'
sname=${sname^^}
nohup dotnet arxServer.dll $sname &
ps ax | grep dotnet
