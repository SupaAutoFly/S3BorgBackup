# S3BorgBackup: BorgBackup of S3 buckets to S3 storage

This repository defines a Docker image that facilitates the backup of S3
buckets to S3 storage using BorgBackup.

## Features
- **BorgBackup**: Utilizes BorgBackup for efficient and secure backups:
  - Deduplication
  - Compression
  - Client-side Encryption (using repokey/repokey-blake2)
- **Fully S3**: Supports backing up data *from* S3 buckets *to* S3-compatible
  storage using TigrisFS.
- **Lightweight**: Built on a minimal `python:3-alpine` base image to reduce
  overhead.
- **Easy Configuration**: Simple environment variable configuration for quick
  setup and integration into environments like docker-compose or fly.io.

## Usage
1. **Build the Docker Image**:
   ```shell
   docker build -t s3borgbackup .
   ```
2. **Configure**:
   ```shell
   cp example.env .env
   ```
   Edit the `.env` file to set your source and target S3 configurations,
   including access keys, endpoints, and backup parameters (see below).

3. **Run the Container**:
   ```shell
   docker run --rm --env-file .env --device /dev/fuse:/dev/fuse --cap-add SYS_ADMIN --security-opt apparmor:unconfined s3borgbackup
   ```
   This will perform a single backup run and then quit, backing up the source bucket to each of the target buckets. Elevated privileges are required for TigrisFS/FUSE to mount the S3 buckets.

   The following warning is expected and not serious, see [this comment](https://github.com/borgbackup/borg/issues/3591#issuecomment-1280047984) by the BorgBackup maintainer:
   ```
   Failed to securely erase old repository config file (hardlinks not supported). Old repokey data, if any, might persist on physical storage.
   ```

4. **Scheduling**:
   For regular backups, consider using a cron job or container orchestration.

## Environment Variables
- `BACKUP_LABEL`: Label for the backup (used in Borg archive names).
- `SOURCE_*`: Configuration for the source S3 bucket (endpoint, path, access keys). `SOURCE_PATH` is either `<bucket>` or `<bucket>:<prefix>`.
- `TARGETS`: JSON object defining multiple backup targets with their
  configurations.
- `TARGET_SECRETS`: JSON object containing access keys and borg passphrases for
  each target.

As Docker does not support multi-line environment variables, the JSON
must be single-line without (outer) quotes.

### Target Configuration
Each target in the `TARGETS` JSON can have the following fields:
- `endpoint`: S3 endpoint URL.
- `path`: Path to the Borg repo, either `<bucket>` or `<bucket>:<path>`.
- `prune`: (Optional) Borg prune options (e.g., `--keep-daily=7 --keep-weekly=4 --keep-monthly=6`). Will not prune if omitted.
- `encryption`: (Optional) Encryption method for Borg (default is `repokey-blake2`).
- `compression`: (Optional) Compression method for Borg (default is `auto,zstd,22`).

### Target Secret Configuration
Each target in the `TARGET_SECRETS` JSON must have the following fields:
- `access_key_id`: Access key ID for the target S3 storage.
- `secret_access_key`: Secret access key for the target S3 storage.
- `borg_passphrase`: Passphrase for Borg encryption. Keep the borg
   passphrases in a secure place. You could use `openssl rand -base64 64` to
   generate a secure passphrase (remove newlines).

## Borg Key Management
- The first time you run the backup, a new Borg repository will be
  initialized at the target location. This includes generating a new
  encryption key which is stored in the target S3 bucket, encrypted
  with the provided `borg_passphrase`.
- Ensure that the `borg_passphrase` is securely stored, as it is
  required for accessing the backup data.
- Consider exporting the Borg repository key to a secure location for
  recovery purposes, see [borg key export](https://borgbackup.readthedocs.io/en/stable/usage/key.html#borg-key-export).

## Manual mode
You can run the container in an interactive mode to manually execute
commands. This is useful for maintenance and recovery tasks.

```shell
docker run -it --rm --env-file .env --device /dev/fuse:/dev/fuse --cap-add SYS_ADMIN --security-opt apparmor:unconfined s3borgbackup ash
```

You can then start a manual backup run using:
```shell
backup.py
```

Or, you can manually mount the source S3 bucket using TigrisFS:
```shell
backup.py mount source
ls /data/source
```
and the target S3 bucket(s):
```shell
backup.py mount target-first
ls /data/target-first
```

With a target mounted, you can run Borg commands directly:
```shell
borg check -v /data/target-first
```
You'll need to set the `BORG_PASSPHRASE` environment variable to
access the repository or enter it when prompted.

## Disclaimer
This project is provided "as is" without any warranties. Use at your own risk.

As of yet, this project has been tested on Linux hosts only. If you use it on
Windows hosts, please let me know how you need to adjust the `docker run`
command to make it work.

## Why not `rclone` for mounting S3?
While `rclone` is a popular tool for syncing files to and from S3 and my first
attempt was using `rclone mount`, see the `rclone` branch, I found the
workarounds, I had to implement to make it work with BorgBackup too hacky to
feel comfortable with:

For using an `rclone` mount as a Borg repository, the mount needs to use at
least `--vfs-cache-mode writes` which requires great care to wait for the write
cache to flush before unmounting, else the repository gets corrupted. Also, on
mount, the mount process needs to be run in the background which makes it
necessary to explicitly wait for the mount to be ready.

Then, I came across [TigrisFS](https://www.tigrisdata.com/docs/training/tigrisfs/),
tried it and was positively surprised how well it worked out of the box. I did
only try it with Tigris S3 yet but it should work with any S3-compatible storage.

But of course, `rclone` might still be valuable for other backup targets that
you might want to extend this project with.
