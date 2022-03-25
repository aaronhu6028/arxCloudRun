#!/bin/bash

git pull
sname=${HOSTNAME#*-} | tr '[:upper:]' '[:lower:]'
nohup dotnet arxServer.dll $sname &
ps ax | grep dotnet
