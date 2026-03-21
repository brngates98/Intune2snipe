# Usage and CLI

## Command

```bash
python3 app.py [OPTIONS]
```

Use the same invocation when running [from source with Python](run-local-python.md). In Docker, the image entrypoint is the same (`python3 app.py`); pass CLI options after the image name.

On Windows you may use `py -3.11 app.py` or `python app.py` depending on how Python is installed.

## Options

| Option | Description |
|--------|-------------|
| `--dry-run` | Log actions only; **no writes** to Snipe-IT |
| `--platform` | One of: `windows`, `android`, `ios`, `macos`, `all` (default: `all`) |
| `--groups` | Comma-separated Azure AD **group object IDs** (overrides `AZURE_GROUP_IDS` if set) |

## Examples

**Preview Windows devices only**

```bash
python3 app.py --dry-run --platform windows
```

**Sync all platforms**

```bash
python3 app.py
```

**Sync Android devices in specific groups**

```bash
python3 app.py --platform android --groups "<group-object-id-1>,<group-object-id-2>"
```

**Groups via environment variable**

```bash
export AZURE_GROUP_IDS="<group-object-id-1>,<group-object-id-2>"
python3 app.py --platform windows
```

## Finding Azure AD group object IDs

**Azure Portal**

1. **Entra ID** → **Groups** → open the group  
2. **Overview** → copy **Object ID**

**Azure CLI**

```bash
az ad group list --display-name "Your Group Name" --query "[].id" -o tsv
```

**Graph Explorer**

1. [Graph Explorer](https://developer.microsoft.com/graph/graph-explorer)  
2. `GET https://graph.microsoft.com/v1.0/groups?$filter=displayName eq 'Your Group Name'`  
3. Use the `id` field from the response  

## Group filtering requirements

- Devices must be **Azure AD registered or joined** (not only “Intune-managed” without AAD join).  
- The tool matches Intune **managedDevice** records to Azure AD using `azureADDeviceId` (see [How it works](how-it-works.md)).  
