FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /code
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN python -m grpc_tools.protoc -I. -I/usr/local/lib/python3.11/site-packages/grpc_tools/_proto --python_out=. --grpc_python_out=. \
    contracts/tutoring.proto contracts/integration.proto
CMD ["python", "-m", "pytest", "-q"]
