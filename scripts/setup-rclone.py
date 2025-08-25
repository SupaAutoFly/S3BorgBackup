#!/usr/bin/env python3
import os
import subprocess
import json

def setup_source():
  provider = os.getenv('SOURCE_PROVIDER', 'Other')
  access_key_id = os.getenv('SOURCE_ACCESS_KEY_ID')
  secret_access_key = os.getenv('SOURCE_SECRET_ACCESS_KEY')
  endpoint = os.getenv('SOURCE_ENDPOINT')
  region = os.getenv('SOURCE_REGION', '')

  if not access_key_id or not secret_access_key or not endpoint:
    raise ValueError("SOURCE_ACCESS_KEY_ID, SOURCE_SECRET_ACCESS_KEY, and SOURCE_ENDPOINT must be set.")

  subprocess.run(['rclone', 'config', 'create', 'source', 's3',
                  f'provider={provider}',
                  'env_auth=false',
                  'acl=private',
                  f'access_key_id={access_key_id}',
                  f'secret_access_key={secret_access_key}',
                  f'endpoint={endpoint}',
                  f'region={region}'],
                 stdout=subprocess.DEVNULL, check=True)

def setup_targets():
  targets = json.loads(os.getenv('TARGETS', '{}'))
  target_secrets = json.loads(os.getenv('TARGET_SECRETS', '{}'))

  for name, config in targets.items():
    provider = config.get('provider', 'Other')
    endpoint = config.get('endpoint')
    secrets = target_secrets.get(name, {})
    access_key_id = secrets.get('access_key_id')
    secret_access_key = secrets.get('secret_access_key')
    region = secrets.get('region', '')

    for key in ['access_key_id', 'secret_access_key', 'endpoint']:
      if not locals()[key]:
        raise ValueError(f"Missing {key} for target {name}.")

    subprocess.run(['rclone', 'config', 'create', f'target-{name}', 's3',
                    f'provider={provider}',
                    'env_auth=false',
                    'acl=private',
                    f'access_key_id={access_key_id}',
                    f'secret_access_key={secret_access_key}',
                    f'endpoint={endpoint}',
                    f'region={region}'],
                   stdout=subprocess.DEVNULL, check=True)

if __name__ == "__main__":
  try:
    setup_source()
  except Exception as e:
    print(f"Error setting up rclone source: {e}")
    exit(1)
  try:
    setup_targets()
  except Exception as e:
    print(f"Error setting up rclone targets: {e}")
    exit(1)
  print("Rclone configured successfully.")

