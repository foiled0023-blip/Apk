[app]
title = BedrockBridge
package.name = bedrockbridge
package.domain = org.freebedrockbridge

source.dir = .
source.include_exts = py,png,jpg,jpeg,kv,atlas,txt,md
version = 0.1.0

requirements = python3,kivy,pyjnius
orientation = portrait
fullscreen = 0

android.permissions = INTERNET,ACCESS_WIFI_STATE,CHANGE_WIFI_MULTICAST_STATE,ACCESS_NETWORK_STATE,WAKE_LOCK
android.api = 35
android.minapi = 23
android.ndk = 25b
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True
android.build_tools_version = 35.0.0
android.allow_backup = True
android.logcat_filters = *:S python:D

[buildozer]
log_level = 2
warn_on_root = 1
