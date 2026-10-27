FROM ubuntu:22.04
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends python3 bash strace util-linux coreutils findutils grep procps && rm -rf /var/lib/apt/lists/*
COPY supervisor.py /opt/supervisor.py
COPY evaluate.py /opt/evaluate.py
COPY strict_tools.py /opt/strict_tools.py
RUN chmod 755 /opt/supervisor.py /opt/evaluate.py /opt/strict_tools.py
WORKDIR /workspace
CMD ["sleep", "infinity"]
