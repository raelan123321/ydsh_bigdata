FROM python:3.10-slim

WORKDIR /opt/project/app

# 使用 pure-sasl（纯 Python SASL 实现）替代需 C++ 编译的 sasl 包，无需任何编译工具链
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    -i https://pypi.tuna.tsinghua.edu.cn/simple

COPY streamlit_app.py screen_api.py ./
COPY data ./data
COPY screen ./screen

EXPOSE 8501 8080
CMD ["streamlit", "run", "streamlit_app.py", "--server.port=8501", "--server.address=0.0.0.0"]
