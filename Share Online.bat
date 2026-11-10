@echo off
rem Double-click to put ZU Advisor online with a free temporary public link.
rem The link works while this window stays open and your PC is on.
title ZU Advisor - sharing online
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0share-online.ps1"
