#!/usr/bin/env python3
import os
import pathlib
import subprocess
import json
import pathlib
import shutil
import time

class RcloneMount:
  def __init__(self, name, path):
    self.name = name
    self.path = path
    self.mountpoint = f'/data/{name}'
    self.mount_source = f'{name}:{path}'
    self.socket = f'/run/backup/{name}.sock'
    self.rclone_process = None

  def is_mounted(self):
    with open('/proc/mounts', 'r') as mounts_file:
      mounts = mounts_file.read()
      return self.mountpoint in mounts

  def __enter__(self):
    if self.is_mounted():
      raise RuntimeError(f"{self.name} is already mounted at {self.mountpoint}.")
    try:
      os.remove(self.socket)
    except FileNotFoundError:
      pass
    pathlib.Path(self.mountpoint).mkdir(parents=True, exist_ok=True)
    self.rclone_process = subprocess.Popen(
      ['rclone', 'mount', self.mount_source, self.mountpoint,
       '--rc',
       '--rc-addr', self.socket,
       '--vfs-cache-mode=full'],
      stdout=subprocess.DEVNULL,
      stderr=subprocess.DEVNULL,
    )
    while True:
      if self.rclone_process.poll() is not None:
        raise RuntimeError(f"Rclone mount process for {self.name} failed to start.")
      if self.is_mounted():
        break
      print(f"Waiting for {self.name} to mount...")
      time.sleep(1)
    return self

  def __exit__(self, exc_type, exc_val, exc_tb):
    self.unmount()
    return False

  def rc(self, command, **kwargs):
    cmd = ['rclone', 'rc', '--unix-socket', self.socket, command]
    for key, value in kwargs.items():
      cmd.append(f'{key}={value}')
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(result.stdout)

  def unmount(self):
    while True:
      vfs_stats = self.rc('vfs/stats', fs=self.mount_source)
      disk_cache = vfs_stats.get('diskCache', None)
      if disk_cache is None:
        # read-only or uncached mount
        break
      if 0 == disk_cache.get('uploadsInProgress', 0) \
          and 0 == disk_cache.get('uploadsQueued', 0):
        break
      print(f"Waiting for cache to flush on {self.name}...")
      time.sleep(1)

    if self.rclone_process:
      self.rc('core/quit')
      exit_code = self.rclone_process.wait(timeout=10)
      if exit_code != 0:
        raise RuntimeError(f"rclone mount for {self.name} exit with code {exit_code}.")
      self.rclone_process = None

def is_borg_repo(target_path):
  try:
    with open(f'{target_path}/README', 'r') as readme_file:
      readme_content = readme_file.read()
      return 'Borg Backup repository' in readme_content
  except FileNotFoundError:
    return False

def init_borg_repo(target_path, passphrase):
  encryption = os.getenv('BORG_ENCRYPTION', 'repokey-blake2')
  env = os.environ | {'BORG_PASSPHRASE': passphrase}
  subprocess.run(['/usr/bin/borg', 'init', '--encryption', encryption, target_path], env = env, check =True)
  if not is_borg_repo(target_path):
    raise ValueError(f"Failed to initialize Borg repository at {target_path}.")

def run_backup(backup_label, target_name, target_config, target_secrets):
  borg_passphrase = target_secrets.get('borg_passphrase')
  if not borg_passphrase:
    raise ValueError(f"No borg_passphrase provided for target {target_name}.")

  print(f"Starting backup to {target_name}...")
  with RcloneMount(f'target-{target_name}', target_config.get('path', '/')) as target_mount:
    borg_repo = target_mount.mountpoint
    if not is_borg_repo(borg_repo):
      init_borg_repo(borg_repo, borg_passphrase)

    borg_env = os.environ | {'BORG_PASSPHRASE': borg_passphrase}
    compression = target_config.get('compression', 'auto,zstd,22')
    subprocess.run(['/usr/bin/borg', 'create', '--stats',
                    '--compression', compression,
                    f'{borg_repo}::{backup_label}-{{now:%Y-%m-%dT%H:%M:%S}}',
                    '/data/source'], env=borg_env, check=True)

    prune_config = target_config.get('prune', '')
    if prune_config:
        subprocess.run(['/usr/bin/borg', 'prune', '--list', borg_repo] + prune_config.split(), env=borg_env, check=True)

  print(f"Backup to {target_name} completed successfully.")

def run_backups():
  pathlib.Path('/run/backup').mkdir(parents=True, exist_ok=True)

  backup_label = os.getenv('BACKUP_LABEL', 'backup')
  targets = json.loads(os.getenv('TARGETS', '{}'))
  target_secrets = json.loads(os.getenv('TARGET_SECRETS', '{}'))

  with RcloneMount('source', os.getenv('SOURCE_PATH', '/')):
    for target_name, target_config in targets.items():
      secrets = target_secrets.get(target_name, {})
      run_backup(backup_label, target_name, target_config, secrets)

if __name__ == "__main__":
  try:
    run_backups()
  except Exception as e:
    print(f"Error during backup process: {e}")
    exit(1)
  print("All backups completed successfully.")

