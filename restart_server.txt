cd $HOME/arxCloudRun
pkill -SIGINT dotnet
git pull
sname=${HOSTNAME#*-}
sname=${sname^^}
nohup dotnet arxServer.dll $sname &
