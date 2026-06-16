# BedrockBridge

A free Python/Kivy Bedrock LAN relay prototype. It tries to act like a BedrockTogether-style LAN announcer and UDP relay.

## Important

This is a prototype relay, not a full official Bedrock proxy. Some servers/networks/consoles may not work.

## How to use the APK

1. Install the APK on an Android phone on the same Wi-Fi as your console.
2. Start your Minecraft Bedrock/Geyser server on your PC.
3. In the app, type the PC's LAN IP, for example `192.168.0.50`.
4. Use port `19132` unless you changed your Geyser/Bedrock port.
5. Press START.
6. Open Minecraft on console and check Friends/LAN Games.

Do not use `127.0.0.1` in the Android app unless the server is running on the phone itself.

## Build APK using WSL/Ubuntu

```bash
sudo apt update
sudo apt install -y git zip unzip openjdk-17-jdk python3-pip python3-venv autoconf libtool pkg-config zlib1g-dev libncurses5-dev libncursesw5-dev libtinfo6 cmake libffi-dev libssl-dev
python3 -m pip install --user buildozer cython
cd BedrockBridgeProject
buildozer -v android debug
```

APK output:

```bash
bin/bedrockbridge-0.1.0-arm64-v8a_armeabi-v7a-debug.apk
```

## Build APK with GitHub Actions

Upload this folder to a GitHub repo, then run the included workflow. It will upload the debug APK as an artifact.
