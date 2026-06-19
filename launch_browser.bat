@echo off
REM MCloud Browser 启动脚本
REM 设置 Google API 密钥
REM 参考：https://www.chromium.org/developers/how-tos/api-keys/

REM Google API 密钥（开发用）
set GOOGLE_API_KEY=AIzaSyCgcLY25b1jTb6Z1_8VA2hjX9HGPuYwmJY

REM Google 默认客户端 ID（开发用）
set GOOGLE_DEFAULT_CLIENT_ID=77185425430.apps.googleusercontent.com

REM Google 默认客户端密钥（开发用）
set GOOGLE_DEFAULT_CLIENT_SECRET=OTJgU3nD3q0q0q0q0q0q0q0q

REM 启动浏览器
cd /d D:\wxmuma\chromium-src\src\out\mcloud
start chrome.exe --enable-logging=1 --v=1
