#!/bin/bash -e

# set timezone
sudo timedatectl set-timezone Asia/Taipei

# install .net 8
wget -V || sudo apt install -y wget
wget https://packages.microsoft.com/config/ubuntu/$(lsb_release -rs)/packages-microsoft-prod.deb -O packages-microsoft-prod.deb
sudo dpkg -i packages-microsoft-prod.deb
rm packages-microsoft-prod.deb

sudo apt-get update; \
  sudo apt-get install -y apt-transport-https && \
  sudo apt-get update && \
  sudo apt-get install -y dotnet-runtime-8.0

# install python3 modules
sudo sed -i "/#\$nrconf{restart} = 'i';/s/.*/\$nrconf{restart} = 'a';/" /etc/needrestart/needrestart.conf
sudo apt-get install -y python3-websockets python3-pip

# install pip requirements
pip3 install -r requirements.txt

# unzip arx-server.zip
unzip -v || sudo apt install -y unzip
unzip -P jack1234 -o brx-server.zip
cp -f brx-server.json arx-server.json

# swap
SWAP=/swap
if [ -f "$SWAP" ]; then
  echo "$SWAP existed."
else
  echo create swap file
  sudo fallocate -l 4G "$SWAP"
  sudo chmod 600 "$SWAP"
  sudo mkswap "$SWAP"
  sudo swapon "$SWAP"
  echo "$SWAP none swap sw 0 0" | sudo tee -a /etc/fstab
fi

# create rc.local
echo "#!/bin/sh
sudo -H -u ${LOGNAME} bash ${HOME}/arxCloudRun/rc_local.sh" | sudo tee /etc/rc.local > /dev/null

sudo chmod a+x /etc/rc.local

mkdir Log

echo "----------------------------------------------"
echo "  SETUP is done. Please restart the server."
echo "----------------------------------------------"