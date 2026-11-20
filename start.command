#!/bin/bash
# QuantFlow 一键启动脚本 (macOS)
# 双击运行即可启动 Web UI

cd "$(dirname "$0")" || exit 1

echo "正在启动 QuantFlow Web UI..."
echo "项目目录: $(pwd)"

# 激活虚拟环境
source .venv/bin/activate

# --- 前端编译检查 -----------------------------------------------------------
# 浏览器加载已提交的 app.js 和 utils.js。若文件缺失或 TypeScript 更新，
# 此处尝试用本机 tsc 重新编译。可重复的构建和校验命令见 README。
STATIC_DIR="src/quantflow/web/static"
if ! command -v tsc >/dev/null 2>&1; then
    echo "⚠️  未找到 tsc，跳过前端编译检查（若按钮失效请安装: npm i -g typescript）"
else
    NEED_BUILD=0
    [ ! -f "$STATIC_DIR/utils.js" ] && NEED_BUILD=1
    [ "$STATIC_DIR/app.ts" -nt "$STATIC_DIR/app.js" ] && NEED_BUILD=1
    [ "$STATIC_DIR/utils.ts" -nt "$STATIC_DIR/utils.js" ] && NEED_BUILD=1
    if [ "$NEED_BUILD" -eq 1 ]; then
        echo "检测到前端源码缺失或过期，正在编译 TypeScript..."
        tsc --target ES2020 --module ES2020 --lib ES2020,DOM,DOM.Iterable \
            --strict false --skipLibCheck --removeComments \
            --outDir "$STATIC_DIR" \
            "$STATIC_DIR/app.ts" "$STATIC_DIR/utils.ts" && echo "前端编译完成 ✓"
    else
        echo "前端构建已是最新 ✓"
    fi
fi
# ---------------------------------------------------------------------------

# 启动 Web 服务
python -m quantflow.cli web

# 若服务被关闭，保持终端窗口以便查看日志
echo ""
echo "QuantFlow 已停止。"
read -r -p "按回车键关闭窗口..."
