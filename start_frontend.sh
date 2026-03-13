#!/bin/bash

# 启动前端服务器

echo "=================================="
echo "  启动前端服务器"
echo "=================================="

cd "$(dirname "$0")/frontend"

# 检查是否有 Python
if command -v python3 &> /dev/null; then
    echo "前端地址: http://localhost:3000"
    echo ""
    python3 -m http.server 3000
elif command -v python &> /dev/null; then
    echo "前端地址: http://localhost:3000"
    echo ""
    python -m http.server 3000
else
    echo "错误: 未找到 Python"
    echo "请手动打开 frontend/index.html"
    exit 1
fi
