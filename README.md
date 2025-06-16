# Intune → Snipe-IT Sync

A Python script to sync Microsoft Intune managed devices into Snipe-IT, create necessary categories, manufacturers, models, and check out hardware to users.

## Features

- Fetch all Intune managed devices via Microsoft Graph API
- Normalize Android-Enterprise UPNs
- Auto-create Snipe-IT categories, manufacturers, and models
- Import devices into Snipe-IT with correct `manufacturer_id`, `model_id`, and `category_id`
- Assign device status by label (e.g., "Ready to Deploy")
- Check out assets to existing Snipe-IT users
- `--dry-run` mode to preview actions without writing

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

The script reads config from environment variables. Create a `.env` or export manually:

```bash
export AZURE_TENANT_ID="<your-tenant-guid>"
export AZURE_CLIENT_ID="<your-client-id>"
export AZURE_CLIENT_SECRET="<your-client-secret>"
export SNIPEIT_URL="https://my-snipeit.example.com/api/v1"
export SNIPEIT_API_TOKEN="<your-snipeit-api-token>"
export SNIPEIT_DEFAULT_STATUS="Ready to Deploy"
```

## Usage

Run a dry run to preview operations without writing to Snipe-IT:

```bash
python3 app.py --dry-run
```

Perform actual sync:

```bash
python3 app.py
```

The script will:

1. Fetch all Intune devices
2. Ensure a "Intune" category exists
3. Ensure the default status label (e.g., "Ready to Deploy") exists
4. Create manufacturers and models (using Intune model number as both name and model_number)
5. Create hardware assets and optionally check them out to users

## Troubleshooting

- **403 Forbidden** when fetching devices: ensure your Azure AD app has `DeviceManagementManagedDevices.Read.All` application permission and is granted admin consent.
- **Missing Snipe-IT fields**: check API token scope, and confirm the Snipe-IT instance supports categories, models, and status labels endpoints.
- **Status label not found**: verify `SNIPEIT_DEFAULT_STATUS` matches exactly an existing status label name.

## Contributing

Feel free to open issues or submit PRs for enhancements and bug fixes.
