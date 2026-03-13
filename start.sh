#!/bin/bash

# 智能客服系统启动脚本

echo "=================================="
echo "  智能客服系统 - 启动脚本"
echo "=================================="

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}错误: 未找到 Python3${NC}"
    exit 1
fi

# 进入项目目录
cd "$(dirname "$0")"
PROJECT_DIR=$(pwd)

echo -e "${YELLOW}项目目录: ${PROJECT_DIR}${NC}"

# 检查虚拟环境
if [ ! -d ".venv" ]; then
    echo -e "${YELLOW}创建虚拟环境...${NC}"
    python3 -m venv .venv
fi

# 激活虚拟环境
source .venv/bin/activate

# 安装依赖
echo -e "${YELLOW}检查依赖...${NC}"
pip install -q fastapi uvicorn python-dotenv pydantic boto3

# 检查 strands-agents（可选）
if pip show strands-agents &> /dev/null; then
    echo -e "${GREEN}strands-agents 已安装${NC}"
else
    echo -e "${YELLOW}strands-agents 未安装，将使用模拟模式${NC}"
    echo -e "${YELLOW}如需完整功能，请运行: pip install strands-agents${NC}"
fi

# 复制环境变量文件
if [ ! -f ".env" ] && [ -f ".env.example" ]; then
    cp .env.example .env
    echo -e "${YELLOW}已创建 .env 文件，请根据需要修改配置${NC}"
fi

# 启动后端
echo ""
echo -e "${GREEN}启动后端 API (http://localhost:8000)...${NC}"
echo ""

cd backend
python3 -c "
import sys
sys.path.insert(0, '..')
from api import app
import uvicorn
uvicorn.run(app, host='0.0.0.0', port=8000)
"
