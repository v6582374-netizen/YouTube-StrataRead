"""Real host and Vault adapter, with only the external Vault CLI replaced."""
# ruff: noqa: E402 -- isolated environment must precede host imports.
import json
import os
import socket
import sys
from pathlib import Path

root = Path(sys.argv[1])
native_mode = len(sys.argv) > 2 and sys.argv[2] == 'native'
os.environ.update(COWORKER_STATE_DIR=str(root / 'host'),
                  COWORKER_API_TOKEN='youtube-connection-e2e')
os.environ.pop('YOUTUBE_WORKBENCH_WORKSPACE', None)
vault = root / 'av'
vault.write_text('''#!'''+sys.executable+'''
import pathlib, sys
root = pathlib.Path(__file__).parent
keys = {'YOUTUBE_WORKBENCH_OAUTH_CLIENT_ID': 'fixture-client',
        'YOUTUBE_WORKBENCH_OAUTH_CLIENT_SECRET': 'fixture-secret',
        'YOUTUBE_WORKBENCH_OAUTH_ACCESS_TOKEN': 'legacy-account'}
if (root / 'missing').exists(): keys = {}
if (root / 'unavailable').exists(): sys.exit(1)
if (root / 'native').exists():
    import hashlib
    prefix = 'EDISON_' + hashlib.sha256(str((root / 'host/youtube').resolve()).encode()).hexdigest()[:16] + '_'
    keys.update({prefix + 'YOUTUBE_WORKBENCH_OAUTH_ACCESS_TOKEN':'access', prefix + 'YOUTUBE_WORKBENCH_OAUTH_REFRESH_TOKEN':'refresh',prefix + 'YOUTUBE_WORKBENCH_OAUTH_EXPIRES_AT':'9999999999'})
if sys.argv[1] == 'list': print('\\n'.join(keys)); sys.exit(0)
if sys.argv[1] == 'inject':
    (root / 'injected').touch()
    selected = sys.argv[sys.argv.index('edison-credential-migration') + 1:]
    if any(key not in keys for key in selected): sys.exit(1)
    print('\\n'.join(keys[key] for key in selected)); sys.exit(0)
sys.exit(1)
''')
vault.chmod(0o700)
os.environ['YOUTUBE_WORKBENCH_AUTOMIC_VAULT'] = str(vault)
import uvicorn

from coworker.server import SessionManager, create_app, youtube

# No external YouTube calls or model calls in connection inspection.
youtube.YouTubeWorkbench._run = lambda self: None
class Credentials:
    values = {'YOUTUBE_WORKBENCH_OAUTH_CLIENT_ID':'fixture-client', 'YOUTUBE_WORKBENCH_OAUTH_CLIENT_SECRET':'fixture-secret', 'YOUTUBE_WORKBENCH_OAUTH_ACCESS_TOKEN':'access', 'YOUTUBE_WORKBENCH_OAUTH_REFRESH_TOKEN':'refresh', 'YOUTUBE_WORKBENCH_OAUTH_EXPIRES_AT':'9999999999'} if native_mode else {}
    def keys(self): return set(self.values)
    def load(self, key): return self.values.get(key)
    def save(self, key, value): self.values[key] = value
    def save_many(self, values): self.values.update(values)
youtube.NativeKeychainVault = lambda **kwargs: Credentials()
if native_mode:
    (root / 'native').touch()
    from youtube_strataread.workbench.connection import OAuthCredentials, SubscriptionSource
    from youtube_strataread.workbench.discovery import Candidate
    from youtube_strataread.workbench.workspace import LocalWorkspace
    workspace = LocalWorkspace.open(root / 'host/youtube')
    workspace.set_meta('youtube_oauth_configured', '1')
    workspace.set_meta('youtube_oauth_authorized', '1')
    workspace.replace_subscription_sources([SubscriptionSource('a','Alpha'), SubscriptionSource('b','Beta')])
    workspace.add_candidate(Candidate('saved','b','Beta','Retained document','https://youtube.com/watch?v=saved','2026-09-20',1))
    workspace.save_manuscript('saved', '# Retained document', generator='fixture', transcript_characters=0)
    workspace.set_preparation_state('saved','ready')
    class Google:
        def list_subscriptions(self, credentials):
            (root / 'synced').touch()
            if (root / 'offline').exists():
                from youtube_strataread.workbench.connection import ConnectionError
                raise ConnectionError('YouTube subscriptions could not be imported')
            return [SubscriptionSource('a','Alpha')] if (root / 'unfollowed').exists() else [SubscriptionSource('a','Alpha'), SubscriptionSource('b','Beta')]
        def refresh(self, configuration, refresh_token):
            return OAuthCredentials('access','refresh',9999999999)
    youtube.GoogleOAuthGateway = Google
manager = SessionManager(data_dir=root / 'host')
app = create_app(manager)
sock = socket.socket()
sock.bind(('127.0.0.1', 0))
print(json.dumps({'port': sock.getsockname()[1]}), flush=True)
uvicorn.Server(uvicorn.Config(app, log_level='error')).run(sockets=[sock])
