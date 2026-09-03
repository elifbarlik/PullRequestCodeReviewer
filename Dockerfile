FROM python:3.11-slim as builder

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.11-slim

WORKDIR /app

# Semgrep bazı işlemlerde git'e ihtiyaç duyar; slim imajda yok.
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Faz 4.4: Semgrep ruleset'lerini build sırasında indirip image katmanına göm.
# Aksi halde ilk PR analizinde semgrep.dev'den indirme 5-30 sn sürer ve
# GitHub webhook timeout'una takılabilir. ALLOWED_SEMGREP_CONFIGS'teki
# tüm ruleset'ler önceden çekilir; runtime'da ağ indirmesi olmaz.
RUN mkdir -p /tmp/warm && echo "x = 1" > /tmp/warm/warm.py && \
    semgrep scan --config p/default --config p/python --config p/security-audit \
      --config p/secrets --config p/owasp-top-ten --config p/javascript \
      --config p/typescript --config p/golang --config p/java \
      --config p/command-injection --config p/sql-injection --config p/xss \
      --metrics=off --disable-version-check --quiet /tmp/warm || true && \
    rm -rf /tmp/warm

COPY app/ ./app/

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
