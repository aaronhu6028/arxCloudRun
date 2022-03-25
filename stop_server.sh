#!/bin/bash

pkill -SIGINT dotnet
ps ax | grep dotnet
tail -f nohup.out
