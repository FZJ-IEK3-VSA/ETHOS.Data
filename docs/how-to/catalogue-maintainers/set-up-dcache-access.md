# Set up dCache access

Prepare an authorised catalogue maintainer account for uploads and folder
operations. Use Bash on Linux/macOS or inside WSL on Windows. You need membership
of the intended storage VO; the example profile and remote are both `HIFIS`.

## 1. Install and start the agent

In the active conda environment:

```bash
conda install -c conda-forge oidc-agent rclone
eval "$(oidc-agent-service use)"
```

If the service reports `/bin/oidc-agent: No such file`, set
`export OIDC_AGENT="$CONDA_PREFIX/bin/oidc-agent"` and retry.

## 2. Register a profile once

For the DESY client used by this catalogue:

```bash
oidc-gen HIFIS --flow=code --client-id=desy-public --client-secret='' \
  --scope="openid profile offline_access" \
  --iss=https://keycloak.desy.de/auth/realms/production/ \
  --redirect-uri=http://localhost:8080
```

Open the authorization URL and choose Helmholtz ID. On a remote machine, forward
port 8080 to your browser's machine. Choose and retain an encryption password for
the local profile. If the provider rejects the client or redirect, confirm the
current registration with the storage administrator.

The profile is created once and loaded into the agent for subsequent sessions.
See the [oidc-gen documentation](https://indigo-dc.gitbook.io/oidc-agent/user/oidc-gen)
for other providers.

## 3. Configure rclone

Locate the config with `rclone config file` and add:

```ini
[HIFIS]
type = webdav
url = https://hifis-storage-ht.desy.de:2880/Helmholtz/FZJ-ICE2
vendor = other
bearer_token_command = oidc-token HIFIS
```

The URL must name the authorised VO. The command obtains tokens on demand;
do not paste one into the file.
See [rclone WebDAV authentication](https://rclone.org/webdav/#openid-connect).

```bash
rclone lsd HIFIS:
```

Expect a directory listing without an authentication error.

## 4. Resume in a new shell

```bash
eval "$(oidc-agent-service use)"
oidc-add HIFIS
rclone lsd HIFIS:
```

If authentication fails, check the active environment, loaded profile, and VO
membership. Keep credentials out of issue reports.

Continue with [Upload a public dataset](upload-a-dataset.md),
[Manage dCache folders](manage-dcache-folders.md), or
[Bootstrap a catalogue](bootstrap-a-catalogue.md).
