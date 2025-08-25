FROM python:3-alpine
RUN apk add --no-cache \
  borgbackup \
  ca-certificates \
  fuse3 \
  openssh-client \
  rclone \
  tzdata
RUN echo "user_allow_other" >> /etc/fuse.conf
RUN addgroup -g 1009 rclone && adduser -u 1009 -Ds /bin/sh -G rclone rclone

COPY --chmod=755 scripts/setup-rclone.py /usr/local/bin/setup-rclone.py
COPY --chmod=755 scripts/backup.py /usr/local/bin/backup.py

COPY --chmod=755 <<-"EOF" /usr/local/bin/docker-entrypoint.sh
#!/bin/sh
set -e
/usr/local/bin/setup-rclone.py

exec "$@"
EOF

VOLUME /config
VOLUME /cache
ENV XDG_CONFIG_HOME=/config
ENV XDG_CACHE_HOME=/cache
WORKDIR /data
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["/usr/local/bin/backup.py"]
