# Intune → Snipe-IT Sync

A Python script to sync Microsoft Intune managed devices into Snipe-IT, with the ability to filter by device platform and Azure AD group membership.

## Features

- Fetch Intune managed devices via Microsoft Graph API
- Filter devices by Azure AD group membership (to sync only devices you're responsible for)
- Normalize Android-Enterprise UPNs
- Auto-create Snipe-IT categories, manufacturers, and models
- Import devices into Snipe-IT with correct `manufacturer_id`, `model_id`, `category_id`, and status label
- Check out assets to existing Snipe-IT users
- `--dry-run` mode to preview actions without writing
- `--platform` flag to limit sync to one of: `windows`, `android`, `ios`, `macos`, or `all`
- `--groups` flag or `AZURE_GROUP_IDS` environment variable to filter by group membership

## Prerequisites

- Python 3.7+
- Azure AD App Registration with **Application** permissions:
  - `DeviceManagementManagedDevices.Read.All`
  - `Group.Read.All` (required if using group filtering)
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
   pip install -r requirements.txt
   ```
   Or install manually:
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
# Optional: Filter devices by Azure AD group membership (comma-separated group object IDs)
export AZURE_GROUP_IDS="<group-id-1>,<group-id-2>"
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

### Filtering by Group Membership

To sync only devices that are members of specific Azure AD groups (useful when your organization is part of a larger tenant):

**Using environment variable:**
```bash
export AZURE_GROUP_IDS="<group-object-id-1>,<group-object-id-2>"
python3 app.py --platform windows
```

**Using command-line argument:**
```bash
python3 app.py --platform windows --groups "<group-object-id-1>,<group-object-id-2>"
```

**Find your group object IDs:**
- In Azure Portal: Azure Active Directory → Groups → Select your group → Overview → Object ID
- Or use: `az ad group list --display-name "Your Group Name" --query "[].id"`

**Note:** Group filtering requires devices to be Azure AD registered/joined. Devices that are only Intune-managed without Azure AD registration will not be matched.

## Deployment

This project includes a `Dockerfile` and Kubernetes manifest (`k8s/cronjob.yaml`) that you can use to automate the sync process. **It's recommended to test the script directly using Python first**, and once you've verified it works correctly, deploy it using Docker or Kubernetes.

### Docker

Build and run the Docker container:

```bash
# Build the image
docker build -t intune2snipe:latest .

# Run the container
docker run --rm \
  -e AZURE_TENANT_ID="<your-tenant-id>" \
  -e AZURE_CLIENT_ID="<your-client-id>" \
  -e AZURE_CLIENT_SECRET="<your-client-secret>" \
  -e SNIPEIT_URL="<your-snipeit-url>" \
  -e SNIPEIT_API_TOKEN="<your-token>" \
  intune2snipe:latest \
  --platform windows --dry-run
```

### Kubernetes

The Kubernetes manifest includes a CronJob that runs the sync on a schedule (default: daily at 2:00 AM UTC).

1. **Edit the Kubernetes manifest** (`k8s/cronjob.yaml`):
   - Update the Secret values with your actual credentials
   - Update the image name to match your container registry
   - Customize the schedule if needed (cron format)
   - Adjust resource limits if necessary

2. **Apply the manifest**:
   ```bash
   kubectl apply -f k8s/cronjob.yaml
   ```

3. **Check the CronJob status**:
   ```bash
   kubectl get cronjob intune2snipe-sync
   kubectl get jobs -l app=intune2snipe-sync
   ```

### GitHub Actions

The repository includes a GitHub Actions workflow (`.github/workflows/docker-build.yml`) that automatically builds and pushes Docker images to GitHub Container Registry (ghcr.io) on push to main/master branches. Update the image name in the Kubernetes manifest to match your repository path.

## How it works

1. **Fetch** Azure AD device IDs from specified groups (if `--groups` or `AZURE_GROUP_IDS` is set).  
2. **Fetch** Intune managed devices via Graph API (filtering by `--platform` and optionally by group membership).  
3. **Ensure** Snipe-IT has an `Intune` category, the default status label exists, and models/manufacturers are created.  
4. **Create** hardware assets in Snipe-IT and **check them out** to users if assigned.  

## Troubleshooting

- **403 Forbidden**: Ensure your Azure AD app has appropriate Graph permissions and admin consent. If using group filtering, ensure `Group.Read.All` permission is granted.  
- **No devices found in groups**: Verify the group object IDs are correct and that devices are actually members of those groups in Azure AD.  
- **Missing fields**: Verify your Snipe-IT instance has categories, models, and status labels enabled.  
- **Status label not found**: Check `SNIPEIT_DEFAULT_STATUS` matches exactly an existing label.  
- **Group filtering not working**: Ensure devices are Azure AD registered/joined (not just Intune-managed). The script matches devices using their Azure AD device object ID.  

## Contributing

Feel free to open issues or submit PRs.
