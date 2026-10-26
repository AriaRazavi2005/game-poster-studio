FROM python:3.12-slim AS lite

WORKDIR /app
COPY . /app

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -e ".[bot,api,persian]"

EXPOSE 8000
CMD ["poster-studio", "--help"]

FROM lite AS pro
RUN pip install --no-cache-dir -e ./poster_studio_pro
