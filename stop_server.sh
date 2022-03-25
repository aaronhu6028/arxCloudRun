#!/bin/bash

ps ax | grep dotnet
cd $HOME/arxCloudRun
pkill -SIGINT dotnet
while :
do
    ps ax | grep dotnet
    sleep 1s
done

