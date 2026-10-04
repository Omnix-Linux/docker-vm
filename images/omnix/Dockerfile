FROM debian:13-slim@sha256:d7e12182ce18b85b93007c1dedf31f2d29e01ccf3182cc4017c709b6259bc132

RUN apt-get update && apt-get install -y --no-install-recommends qemu-system-x86 qemu-utils ovmf python3 ca-certificates \
 && apt-get clean \
 && install -d -m 1777 /work
COPY --chmod=0755 images/omnix/session.py /usr/local/bin/omnix-session
EXPOSE 5900
ENTRYPOINT ["python3", "/usr/local/bin/omnix-session"]
