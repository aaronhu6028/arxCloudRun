#!/bin/bash

git pull
pkill -SIGINT dotnet
ps ax | grep dotnet
tail -f $(ls nohup.*.out | tail -n 1)
