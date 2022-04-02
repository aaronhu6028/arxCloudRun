#!/bin/bash -e

# set timezone
sudo timedatectl set-timezone Asia/Taipei

# install .net
wget -V || sudo apt install -y wget 
wget https://packages.microsoft.com/config/ubuntu/18.04/packages-microsoft-prod.deb -O packages-microsoft-prod.deb
sudo dpkg -i packages-microsoft-prod.deb
rm packages-microsoft-prod.deb

sudo apt-get update; \
  sudo apt-get install -y apt-transport-https && \
  sudo apt-get update && \
  sudo apt-get install -y dotnet-runtime-6.0
  
# create rc.local
sname=${HOSTNAME#*-}
sname=${sname^^}
printf '#!/bin/sh -e
(cd /home/aaronhu6028/arxCloudRun && nohup dotnet arxServer.dll %s >> nohup.$(date --iso).out &)
exit 0' $sname | sudo tee /etc/rc.local > /dev/null
sudo chmod a+x /etc/rc.local

echo "----------------------------------------------"
echo "  SETUP is done. Please restart the server."
echo "----------------------------------------------"
