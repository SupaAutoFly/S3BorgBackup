#!/usr/bin/env python3
import os
import pathlib
import subprocess
import json
import pathlib
import shutil
import time

class TigrisfsMount:
  def __init__(self, name, path, access_key_id, secret_access_key, endpoint_url):
    for arg in ['path', 'access_key_id', 'secret_access_key', 'endpoint_url']:
      if not locals()[arg]:
        raise ValueError(f"{arg} is required for TigrisFS mount '{name}'.")

    self.name = name
    self.path = path
    self.mountpoint = f'/data/{name}'
    self.mount_source = path
    self.access_key_id = access_key_id
    self.secret_access_key = secret_access_key
    self.endpoint_url = endpoint_url
    self.was_mounted = False

  def is_mounted(self):
    with open('/proc/mounts', 'r') as mounts_file:
      mounts = mounts_file.read()
      return self.mountpoint in mounts

  def __enter__(self):
    if self.is_mounted():
      self.was_mounted = True
      return self
    self.mount()
    return self

  def __exit__(self, exc_type, exc_val, exc_tb):
    if not self.was_mounted:
      self.unmount()
    return False

  def mount(self):
    if self.is_mounted():
      return
    pathlib.Path(self.mountpoint).mkdir(parents=True, exist_ok=True)
    tigrisfs_env = os.environ | {
      'AWS_ENDPOINT_URL': self.endpoint_url,
      'AWS_ACCESS_KEY_ID': self.access_key_id,
      'AWS_SECRET_ACCESS_KEY': self.secret_access_key,
    }
    subprocess.run(
      ['/usr/local/bin/tigrisfs',
       '--no-tigris-prefetch',
       self.mount_source, self.mountpoint ],
      stdout=subprocess.DEVNULL,
      stderr=subprocess.DEVNULL,
      env=tigrisfs_env,
      check=True,
    )
    while True:
      if self.is_mounted():
        break
      print(f"Waiting for {self.name} to mount...")
      time.sleep(1)

  def unmount(self):
    subprocess.run(['/usr/bin/fusermount3', '-u', self.mountpoint], check=True)

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
  with target_mount(target_name, target_config, target_secrets) as mounted_target:
    borg_repo = mounted_target.mountpoint
    if not is_borg_repo(borg_repo):
      init_borg_repo(borg_repo, borg_passphrase)

    borg_env = os.environ | {'BORG_PASSPHRASE': borg_passphrase}
    compression = target_config.get('compression', 'auto,zstd,22')
    subprocess.run(['/usr/bin/borg',
                    'create',
                    '--stats',
                    '--files-cache', 'ctime,size',
                    '--compression', compression,
                    f'{borg_repo}::{backup_label}-{{now:%Y-%m-%dT%H:%M:%S}}',
                    '/data/source'], env=borg_env, check=True)

    prune_config = target_config.get('prune', '')
    if prune_config:
        subprocess.run(['/usr/bin/borg', 'prune', '--list', borg_repo] + prune_config.split(), env=borg_env, check=True)

  print(f"Backup to {target_name} completed successfully.")

def source_mount():
  return TigrisfsMount(
      'source',
      os.getenv('SOURCE_PATH'),
      access_key_id=os.getenv('SOURCE_ACCESS_KEY_ID'),
      secret_access_key=os.getenv('SOURCE_SECRET_ACCESS_KEY'),
      endpoint_url=os.getenv('SOURCE_ENDPOINT'))

def target_mount(target_name, target_config, target_secrets):
  return TigrisfsMount(
      f'target-{target_name}',
      target_config.get('path'),
      access_key_id=target_secrets.get('access_key_id'),
      secret_access_key=target_secrets.get('secret_access_key'),
      endpoint_url=target_config.get('endpoint'))

def run_backups():
  pathlib.Path('/run/backup').mkdir(parents=True, exist_ok=True)

  backup_label = os.getenv('BACKUP_LABEL', 'backup')
  targets = json.loads(os.getenv('TARGETS', '{}'))
  target_secrets = json.loads(os.getenv('TARGET_SECRETS', '{}'))

  with source_mount():
    for target_name, target_config in targets.items():
      secrets = target_secrets.get(target_name, {})
      run_backup(backup_label, target_name, target_config, secrets)

def mount(name):
  if name == 'source':
    source_mount().mount()
    return
  if not name.startswith('target-'):
    raise ValueError(f"Invalid mount name: {name}. Must be 'source' or 'target-<target_name>'.")
  name = name[len('target-'):]
  if name not in json.loads(os.getenv('TARGETS', '{}')):
    raise ValueError(f"Target '{name}' not found in TARGETS environment variable.")
  target_config = json.loads(os.getenv('TARGETS', '{}')).get(name, {})
  target_secrets = json.loads(os.getenv('TARGET_SECRETS', '{}')).get(name, {})
  target_mount(name, target_config, target_secrets).mount()

if __name__ == "__main__":
  if len(os.sys.argv) > 1 and os.sys.argv[1] == 'mount':
    if len(os.sys.argv) < 3:
      print("Usage: backup.py mount [source|target-<target_name>]")
      exit(1)
    mount(os.sys.argv[2])
    exit(0)

  try:
    run_backups()
  except Exception as e:
    print(f"Error during backup process: {e}")
    exit(1)
  print("All backups completed successfully.")

