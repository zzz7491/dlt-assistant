#!/usr/bin/env bash
# ============================================================
# scripts/check-production.sh
# 生产环境自动检查脚本（只读，不修改任何线上资源）
#
# 用途：
#   验证 https://500wan.mootlsv.com/ 是否处于 production-stable-v1.0
#   基线状态，捕获「代码已修但部署未生效 / 残留旧引用」类异常。
#
# 退出码：
#   0 = PASS（生产正常）
#   1 = FAIL（生产异常，需人工介入）
# 便于接入 CI 或定时任务（cron）做自动验收。
#
# 用法：
#   bash scripts/check-production.sh            # 默认检查正式域名
#   bash scripts/check-production.sh -q         # 静默模式（仅输出结果行）
#   PROD_URL=https://xxx.yyy bash scripts/check-production.sh
# ============================================================

set -uo pipefail

# ---------- 可配置参数 ----------
PROD_URL="${PROD_URL:-https://500wan.mootlsv.com}"
CHECK_TITLE="大乐透综合数据分析平台"   # index.html 必须包含的平台标识
FORBIDDEN="final_recommendation"      # 基线后不应再出现的旧引用关键词
TIMEOUT=15

# ---------- 颜色（终端友好，CI 环境无 TTY 时自动降级） ----------
if [ -t 1 ]; then
  GREEN='\033[0;32m'; RED='\033[0;31m'; YEL='\033[0;33m'; NC='\033[0m'
else
  GREEN=''; RED=''; YEL=''; NC=''
fi
pass(){ printf "${GREEN}PASS${NC}"; }
fail(){ printf "${RED}FAIL${NC}"; }

QUIET=0
[ "${1:-}" = "-q" ] && QUIET=1

# 内容子串检查：优先用 python3（UTF-8 安全，跨 locale 稳定），
# 缺失 python3 时回退到 grep -F（固定串）。
contains() {  # $1=文本  $2=子串
  if command -v python3 >/dev/null 2>&1; then
    printf '%s' "$1" | python3 -c "import sys; s=sys.stdin.read(); sys.exit(0 if s.find(sys.argv[1]) >= 0 else 1)" "$2"
  else
    printf '%s' "$1" | grep -qF -- "$2"
  fi
}

TIME=$(date '+%Y-%m-%d %H:%M:%S %Z')
RESULT=PASS

# ---------- 工具函数 ----------
http_code() {
  # $1 = 相对路径（可为空，表示首页）
  curl -s -o /dev/null -w '%{http_code}' --max-time "$TIMEOUT" "${PROD_URL%/}/$1"
}

# ---------- 1. 首页 HTTP 状态 ----------
HTTP=$(http_code "")
if [ "$HTTP" = "200" ]; then
  HTTP_R=PASS
else
  HTTP_R=FAIL; RESULT=FAIL
fi

# ---------- 2. 关键资源 ----------
ASSETS=("app.js" "data/dlt_history.json" "data/recommendations.json")
ASSETS_DETAIL=""
ASSETS_OK=1
for a in "${ASSETS[@]}"; do
  C=$(http_code "$a")
  if [ "$C" = "200" ]; then
    ASSETS_DETAIL="${ASSETS_DETAIL}  /$a -> $C [PASS]\n"
  else
    ASSETS_DETAIL="${ASSETS_DETAIL}  /$a -> $C [FAIL]\n"
    ASSETS_OK=0; RESULT=FAIL
  fi
done
[ "$ASSETS_OK" = "1" ] && ASSETS_R=PASS || ASSETS_R=FAIL

# ---------- 3. index.html 内容 ----------
HTML=$(curl -s --max-time "$TIMEOUT" "${PROD_URL%/}/")
if contains "$HTML" "$CHECK_TITLE"; then
  TITLE_R=PASS
else
  TITLE_R=FAIL; RESULT=FAIL
fi
if contains "$HTML" "$FORBIDDEN"; then
  HTML_FORBID_R=FAIL; RESULT=FAIL
else
  HTML_FORBID_R=PASS
fi

# ---------- 4. app.js 内容 ----------
JS=$(curl -s --max-time "$TIMEOUT" "${PROD_URL%/}/app.js")
if contains "$JS" "$FORBIDDEN"; then
  JS_R=FAIL; RESULT=FAIL
else
  JS_R=PASS
fi

# ---------- 5. recommendations.json 内容 ----------
JSON=$(curl -s --max-time "$TIMEOUT" "${PROD_URL%/}/data/recommendations.json")
if contains "$JSON" "$FORBIDDEN"; then
  JSON_FORBID_R=FAIL; RESULT=FAIL
else
  JSON_FORBID_R=PASS
fi
# 尝试 JSON 解析（best-effort，缺失 python3 时不阻塞）
if command -v python3 >/dev/null 2>&1; then
  if echo "$JSON" | python3 -c "import sys,json; json.load(sys.stdin)" 2>/dev/null; then
    JSON_PARSE_R=PASS
  else
    JSON_PARSE_R=FAIL; RESULT=FAIL
  fi
else
  JSON_PARSE_R="SKIP"
fi

# ---------- 输出报告 ----------
if [ "$QUIET" = "0" ]; then
  echo "=============================================="
  echo " Production Check"
  echo "=============================================="
  echo "Time:   $TIME"
  echo "URL:    $PROD_URL"
  echo ""
  printf "HTTP:   %s  [" "$HTTP"; [ "$HTTP_R" = PASS ] && pass || fail; echo "]"
  echo ""
  echo "Assets:"
  printf "%b" "$ASSETS_DETAIL"
  printf "        -> %s\n" "$([ "$ASSETS_R" = PASS ] && echo PASS || echo FAIL)"
  echo ""
  printf "JS:     app.js 不含 %s  [" "$FORBIDDEN"; [ "$JS_R" = PASS ] && pass || fail; echo "]"
  echo ""
  printf "JSON:   recommendations.json 不含 %s  [" "$FORBIDDEN"; [ "$JSON_FORBID_R" = PASS ] && pass || fail; echo "]"
  printf "        recommendations.json 可解析  ["; [ "$JSON_PARSE_R" = PASS ] && pass || { [ "$JSON_PARSE_R" = SKIP ] && printf "${YEL}SKIP${NC}" || fail; }; echo "]"
  echo ""
  echo "Content(index):"
  printf "        含平台标识 [%s]  " "$CHECK_TITLE"; [ "$TITLE_R" = PASS ] && pass || fail; echo ""
  printf "        不含 %s  [" "$FORBIDDEN"; [ "$HTML_FORBID_R" = PASS ] && pass || fail; echo "]"
  echo ""
  echo "=============================================="
  printf "Result: "; [ "$RESULT" = PASS ] && pass || fail; echo ""
  echo "=============================================="
else
  echo "PROD_CHECK $(date '+%Y-%m-%dT%H:%M:%S%z') RESULT=$RESULT HTTP=$HTTP ASSETS=$ASSETS_R JS=$JS_R JSON=$JSON_FORBID_R"
fi

[ "$RESULT" = PASS ] && exit 0 || exit 1
