#!/bin/bash

git pull
chmod a+x *.sh
sname=${HOSTNAME#*-} 
sname=${sname^^}
nohup dotnet arxServer.dll $sname &
ps ax | grep dotnet
tail -f nohup.out
