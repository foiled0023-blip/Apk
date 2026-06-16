#!/usr/bin/env bash
set -e
sudo apt update
sudo apt install -y git zip unzip openjdk-17-jdk python3-pip python3-venv autoconf libtool pkg-config zlib1g-dev libncurses5-dev libncursesw5-dev libtinfo6 cmake libffi-dev libssl-dev
python3 -m pip install --user --upgrade pip
python3 -m pip install --user buildozer cython
buildozer -v android debug
