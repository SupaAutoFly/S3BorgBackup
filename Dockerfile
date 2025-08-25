FROM python:3-alpine
RUN apk add --no-cache \
  borgbackup \
  ca-certificates \
  fuse3 \
  tzdata
RUN wget -qO - https://github.com/tigrisdata/tigrisfs/releases/download/v1.2.1/tigrisfs_1.2.1_linux_amd64.tar.gz | tar xz -C /usr/local/bin tigrisfs

RUN echo "user_allow_other" >> /etc/fuse.conf
RUN addgroup -g 1009 backup && adduser -u 1009 -Ds /bin/sh -G backup backup

COPY --chmod=755 scripts/backup.py /usr/local/bin/backup.py

VOLUME /config
VOLUME /cache
ENV XDG_CONFIG_HOME=/config
ENV XDG_CACHE_HOME=/cache
WORKDIR /data
CMD ["/usr/local/bin/backup.py"]
