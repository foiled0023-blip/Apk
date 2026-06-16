name: Build Android APK

on:
  workflow_dispatch:
  push:
    branches: [ main, master ]

jobs:
  build:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout repo
        uses: actions/checkout@v4

      - name: Install system packages
        run: |
          sudo apt update
          sudo apt install -y git zip unzip wget openjdk-17-jdk python3-pip python3-setuptools python3-wheel build-essential libffi-dev libssl-dev

      - name: Install Buildozer
        run: |
          python3 -m pip install --upgrade pip
          python3 -m pip install buildozer cython

      - name: Install Android sdkmanager
        run: |
          SDK="$HOME/.buildozer/android/platform/android-sdk"
          mkdir -p "$SDK/cmdline-tools"
          wget -q https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip -O cmdtools.zip
          unzip -q cmdtools.zip -d "$SDK/cmdline-tools"
          mv "$SDK/cmdline-tools/cmdline-tools" "$SDK/cmdline-tools/latest"
          mkdir -p "$SDK/tools/bin"
          ln -sfn "$SDK/cmdline-tools/latest/bin/sdkmanager" "$SDK/tools/bin/sdkmanager"
          ln -sfn "$SDK/cmdline-tools/latest/bin/avdmanager" "$SDK/tools/bin/avdmanager"
          yes | "$SDK/tools/bin/sdkmanager" --sdk_root="$SDK" --licenses || true

      - name: Build APK
        run: |
          yes | buildozer -v android debug

      - name: Upload APK
        uses: actions/upload-artifact@v4
        with:
          name: BedrockBridge-APK
          path: bin/*.apk
