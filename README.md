# Intune → Snipe-IT Sync

A Python script to sync Microsoft Intune managed devices into Snipe-IT, with the ability to filter by device platform.

## Features

- Fetch Intune managed devices via Microsoft Graph API
- Normalize Android-Enterprise UPNs
- Auto-create Snipe-IT categories, manufacturers, and models
- Import devices into Snipe-IT with correct `manufacturer_id`, `model_id`, `category_id`, and status label
- Check out assets to existing Snipe-IT users
- `--dry-run` mode to preview actions without writing
- `--platform` flag to limit sync to one of: `windows`, `android`, `ios`, `macos`, or `all`

## Prerequisites

- Python 3.7+
- Azure AD App Registration with **Application** permissions:
  - `DeviceManagementManagedDevices.Read.All`
  - `User.Read.All` (if user info is fetched)
- Snipe-IT API credentials with write access

## Installation

1. Clone this repository:
   ```bash
   git clone https://github.com/yourorg/intune-snipe-sync.git
   cd intune-snipe-sync
   ```
2. Install dependencies:
   ```bash
   pip install msal requests
   ```

## Configuration

Set environment variables (or add to `.env`):

```bash
export AZURE_TENANT_ID="<your-tenant-guid>"
export AZURE_CLIENT_ID="<your-client-id>"
export AZURE_CLIENT_SECRET="<your-client-secret>"
export SNIPEIT_URL="https://my-snipeit.example.com/api/v1"
export SNIPEIT_API_TOKEN="<your-snipeit-api-token>"
export SNIPEIT_DEFAULT_STATUS="Ready to Deploy"
```

## Usage

### Dry run

Preview actions without writing to Snipe-IT:

```bash
python3 app.py --dry-run --platform windows
```

### Actual sync

Sync devices (all platforms by default):

```bash
python3 app.py
```

Sync only Android devices:

```bash
python3 app.py --platform android
```

## How it works

1. **Fetch** Intune devices (filtering by `--platform`) via Graph API.  
2. **Ensure** Snipe-IT has an `Intune` category, the default status label exists, and models/manufacturers are created.  
3. **Create** hardware assets in Snipe-IT and **check them out** to users if assigned.  

## Troubleshooting

- **403 Forbidden**: Ensure your Azure AD app has appropriate Graph permissions and admin consent.  
- **Missing fields**: Verify your Snipe-IT instance has categories, models, and status labels enabled.  
- **Status label not found**: Check `SNIPEIT_DEFAULT_STATUS` matches exactly an existing label.  

## Contributing

Feel free to open issues or submit PRs.
