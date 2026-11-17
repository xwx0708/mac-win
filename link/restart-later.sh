#!/bin/sh
# Mac：8 秒后重启互联服务（LaunchAgent com.macwin.link）。
# 给跑在这个服务下面的智能体用：先安排好再回复，回复送出去之后服务才重启。
# 用法：nohup sh ~/macwin-link/restart-later.sh >/dev/null 2>&1 &
sleep 8
launchctl kickstart -k "gui/$(id -u)/com.macwin.link"
