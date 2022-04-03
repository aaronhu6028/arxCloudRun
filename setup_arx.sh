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
  
# unzip arx-server.zip
unzip -v || sudo apt install -y unzip 
unzip arx-server.zip
  
# create rc.local
printf 'sudo -H -u aaronhu6028 /home/aaronhu6028/rc_local.sh start' | sudo tee /etc/rc.local > /dev/null

chmod a+x rc_local.sh
sudo chmod a+x /etc/rc.local

echo "----------------------------------------------"
echo "  SETUP is done. Please restart the server."
echo "----------------------------------------------"
