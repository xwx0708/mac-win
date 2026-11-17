#!/bin/bash
# run_all.sh — 编码三段动画、检查、在 WKWebView 和 Safari 里实测，输出写到 results/log.txt
#
# 用法（在任意目录）: bash tools/run_all.sh
# 某一步失败不会中断，最后统一汇总；有失败时退出码为 1。

set -u

cd "$(dirname "$0")/.." || { echo "run_all: cannot cd to project root" >&2; exit 1; }

PORT=8766
BASE="http://127.0.0.1:${PORT}"

mkdir -p out results results/wk || { echo "run_all: mkdir failed" >&2; exit 1; }

main() {
    local failures=""
    local failure_count=0
    local server_pid=""

    record_failure() {
        failures="${failures}  - $1"$'\n'
        failure_count=$((failure_count + 1))
    }

    # step <名字> <命令...>：运行一步，失败只记录不退出
    step() {
        local name="$1"
        shift
        echo
        echo "=== [${name}] $*"
        "$@" </dev/null
        local rc=$?
        if [ "$rc" -ne 0 ]; then
            echo "!!! [${name}] FAILED (exit ${rc})"
            record_failure "${name} (exit ${rc})"
        else
            echo "--- [${name}] ok"
        fi
        return 0
    }

    wait_for_server() {
        local i=0
        while [ "$i" -lt 50 ]; do
            if curl -s -o /dev/null -m 2 "${BASE}/tools/test.html"; then
                echo "server is ready on ${BASE}"
                return 0
            fi
            if [ -n "$server_pid" ] && ! kill -0 "$server_pid" 2>/dev/null; then
                echo "server process exited early; see results/serve.log:"
                cat results/serve.log 2>/dev/null
                return 1
            fi
            sleep 0.2
            i=$((i + 1))
        done
        echo "server did not become ready within 10s"
        return 1
    }

    # wait_for_file <路径> <秒>
    wait_for_file() {
        local path="$1"
        local limit="$2"
        local waited=0
        while [ "$waited" -lt "$limit" ]; do
            if [ -f "$path" ]; then
                echo "${path} appeared after ~${waited}s"
                return 0
            fi
            sleep 1
            waited=$((waited + 1))
        done
        echo "${path} did not appear within ${limit}s"
        return 1
    }

    stop_server() {
        curl -s -m 5 "${BASE}/quit" || return 1
        local i=0
        while [ "$i" -lt 25 ]; do
            if [ -z "$server_pid" ] || ! kill -0 "$server_pid" 2>/dev/null; then
                return 0
            fi
            sleep 0.2
            i=$((i + 1))
        done
        echo "server still running after /quit; killing pid ${server_pid}"
        kill "$server_pid" 2>/dev/null
        return 1
    }

    print_json() {
        local path="$1"
        echo
        echo "=== ${path}"
        if [ -f "$path" ]; then
            cat "$path"
            echo
            echo "--- summary of ${path}:"
            python3 -c 'import json, sys; print(json.load(open(sys.argv[1], encoding="utf-8")).get("summary"))' "$path" \
                || echo "(could not parse ${path})"
        else
            echo "(missing)"
            record_failure "${path} missing"
        fi
    }

    trap 'if [ -n "$server_pid" ]; then kill "$server_pid" 2>/dev/null; fi' EXIT INT TERM

    echo "run_all: started $(date '+%Y-%m-%d %H:%M:%S') in $(pwd)"
    sw_vers 2>/dev/null
    swift --version 2>&1 | head -n 2

    # 上一次的结果先删掉，否则"等 JSON 出现"没有意义
    rm -f results/wkwebview.json results/safari.json results/serve.log

    # 2. 编码
    step "encode intro" swift tools/encode.swift frames/intro out/intro.mov
    step "encode loop"  swift tools/encode.swift frames/loop  out/loop.mov
    step "encode outro" swift tools/encode.swift frames/outro out/outro.mov

    # 3. 检查 + 衔接比较（前者最后一帧 vs 后者第一帧）
    step "inspect intro, compare intro->loop" swift tools/inspect.swift out/intro.mov --compare out/loop.mov
    step "inspect loop, compare loop->loop"   swift tools/inspect.swift out/loop.mov  --compare out/loop.mov
    step "compare loop->outro"                swift tools/inspect.swift out/loop.mov  --compare out/outro.mov
    step "inspect outro"                      swift tools/inspect.swift out/outro.mov

    # 4. 服务器（如果上次的还活着，先让它退出）
    curl -s -o /dev/null -m 2 "${BASE}/quit" && sleep 1
    echo
    echo "=== [start server] python3 tools/serve.py ${PORT}"
    python3 tools/serve.py "${PORT}" >results/serve.log 2>&1 </dev/null &
    server_pid=$!
    step "wait for server" wait_for_server

    # 5. WKWebView
    step "wkwebview playback" swift tools/wkplay.swift "${BASE}/tools/test.html?name=wkwebview" results/wk 70

    # 6. Safari
    step "open Safari" open -a Safari "${BASE}/tools/test.html?name=safari"
    step "wait for results/safari.json" wait_for_file results/safari.json 70

    # 7. 关服务器，打印结果
    step "stop server" stop_server
    server_pid=""

    print_json results/wkwebview.json
    print_json results/safari.json

    echo
    echo "=== files"
    ls -l out results results/wk 2>&1

    echo
    echo "=== SUMMARY ($(date '+%Y-%m-%d %H:%M:%S'))"
    if [ "$failure_count" -eq 0 ]; then
        echo "all steps succeeded"
        return 0
    fi
    echo "${failure_count} step(s) failed:"
    printf '%s' "$failures"
    return 1
}

main 2>&1 | tee results/log.txt
exit "${PIPESTATUS[0]}"
