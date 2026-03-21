# Intune → Snipe-IT Sync

A Python script to sync Microsoft Intune managed devices into Snipe-IT, with the ability to filter by device platform and Azure AD group membership.

[![Docker Image](https://img.shields.io/badge/docker-ghcr.io-blue)](https://github.com/brngates98/intune2snipe/pkgs/container/intune2snipe)
[![Python Version](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

## Features

- ✅ Fetch Intune managed devices via Microsoft Graph API
- ✅ Filter devices by Azure AD group membership (to sync only devices you're responsible for)
- ✅ Normalize Android-Enterprise UPNs (removes GUID prefixes)
- ✅ Auto-create Snipe-IT categories, manufacturers, and models
- ✅ Import devices into Snipe-IT with correct `manufacturer_id`, `model_id`, `category_id`, and status label
- ✅ Check out assets to existing Snipe-IT users automatically
- ✅ `--dry-run` mode to preview actions without writing
- ✅ `--platform` flag to limit sync to one of: `windows`, `android`, `ios`, `macos`, or `all`
- ✅ `--groups` flag or `AZURE_GROUP_IDS` environment variable to filter by group membership
- ✅ Docker container support
- ✅ Kubernetes CronJob manifest included
- ✅ Automated CI/CD with GitHub Actions

## Prerequisites

- **Python 3.11+** (or use Docker)
- **Azure AD App Registration** with **Application** permissions:
  - `DeviceManagementManagedDevices.Read.All` (required)
  - `Group.Read.All` (required if using group filtering)
  - `User.Read.All` (required for user lookup and checkout)
- **Snipe-IT API credentials** with write access
- **Admin consent** granted for all Azure AD app permissions

## Installation

### Local Installation

1. Clone this repository:
   ```bash
   git clone https://github.com/brngates98/intune2snipe.git
   cd intune2snipe
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
   
   Or install manually:
   ```bash
   pip install msal requests
   ```

### Docker Installation

**Pull the pre-built image from GitHub Container Registry:**

```bash
# Pull the latest image
docker pull ghcr.io/brngates98/intune2snipe:latest
```

**Note:** Replace `brngates98/intune2snipe` with your GitHub organization/username and repository name. The image path format is `ghcr.io/<org-or-username>/<repo-name>:<tag>`.

**For private repositories**, authenticate first:

```bash
# Login to GHCR using your GitHub Personal Access Token
# Create a PAT with 'read:packages' permission at: https://github.com/settings/tokens
docker login ghcr.io -u YOUR_GITHUB_USERNAME
# Enter your GitHub Personal Access Token when prompted
```

**Or build locally:**

```bash
git clone https://github.com/brngates98/intune2snipe.git
cd intune2snipe
docker build -t intune2snipe:latest .
```

## Configuration

### Required Environment Variables

Set the following environment variables (or add to `.env`):

```bash
# Azure AD Configuration
export AZURE_TENANT_ID="<your-tenant-guid>"
export AZURE_CLIENT_ID="<your-client-id>"
export AZURE_CLIENT_SECRET="<your-client-secret>"

# Snipe-IT Configuration
export SNIPEIT_URL="https://my-snipeit.example.com/api/v1"  # Must end with /api/v1
export SNIPEIT_API_TOKEN="<your-snipeit-api-token>"
export SNIPEIT_DEFAULT_STATUS="Ready to Deploy"  # Must match an existing status label

# Optional: Filter devices by Azure AD group membership (comma-separated group object IDs)
export AZURE_GROUP_IDS="<group-id-1>,<group-id-2>"
```

### Azure AD App Registration Setup

1. Go to [Azure Portal](https://portal.azure.com) → Azure Active Directory → App registrations
2. Create a new app registration or select an existing one
3. Navigate to **API permissions** → **Add a permission** → **Microsoft Graph** → **Application permissions**
4. Add the following permissions:
   - `DeviceManagementManagedDevices.Read.All`
   - `Group.Read.All` (if using group filtering)
   - `User.Read.All` (for user lookup)
5. Click **Grant admin consent** for your organization
6. Navigate to **Certificates & secrets** → Create a new client secret
7. Copy the **Tenant ID**, **Application (client) ID**, and **Client secret value**

### Snipe-IT API Token Setup

1. Log into your Snipe-IT instance
2. Navigate to **My Account** → **API Tokens**
3. Create a new API token with appropriate permissions
4. Copy the token (you won't be able to see it again)

## Usage

### Command-Line Options

```bash
python3 app.py [OPTIONS]
```

**Options:**
- `--dry-run` - Preview actions without writing to Snipe-IT
- `--platform {windows,android,ios,macos,all}` - Filter devices by OS platform (default: `all`)
- `--groups "<group-id-1>,<group-id-2>"` - Filter devices by Azure AD group membership

### Examples

**Dry run (preview only):**
```bash
python3 app.py --dry-run --platform windows
```

**Sync all platforms:**
```bash
python3 app.py
```

**Sync only Windows devices:**
```bash
python3 app.py --platform windows
```

**Sync Android devices with group filtering:**
```bash
python3 app.py --platform android --groups "<group-object-id-1>,<group-object-id-2>"
```

**Using environment variable for groups:**
```bash
export AZURE_GROUP_IDS="<group-object-id-1>,<group-object-id-2>"
python3 app.py --platform windows
```

### Finding Azure AD Group Object IDs

**Method 1: Azure Portal**
1. Go to Azure Portal → Azure Active Directory → Groups
2. Select your group → Overview → Copy the **Object ID**

**Method 2: Azure CLI**
```bash
az ad group list --display-name "Your Group Name" --query "[].id" -o tsv
```

**Method 3: Microsoft Graph Explorer**
1. Go to [Graph Explorer](https://developer.microsoft.com/graph/graph-explorer)
2. Query: `GET https://graph.microsoft.com/v1.0/groups?$filter=displayName eq 'Your Group Name'`
3. Copy the `id` field from the response

**Note:** Group filtering requires devices to be Azure AD registered/joined. Devices that are only Intune-managed without Azure AD registration will not be matched.

## Deployment

This project includes a `Dockerfile` and Kubernetes manifest (`k8s/cronjob.yaml`) that you can use to automate the sync process. **It's recommended to test the script directly using Python first**, and once you've verified it works correctly, deploy it using Docker or Kubernetes.

### Docker

**Pull the image from GitHub Container Registry:**

```bash
# Pull the latest image
docker pull ghcr.io/brngates98/intune2snipe:latest

# Or pull a specific tag/version
docker pull ghcr.io/brngates98/intune2snipe:v1.0.0
docker pull ghcr.io/brngates98/intune2snipe:main
```

**Note:** If the image is private, you'll need to authenticate first:

```bash
# Login to GHCR using your GitHub Personal Access Token (PAT)
# Create a PAT with 'read:packages' permission at: https://github.com/settings/tokens
echo $GITHUB_TOKEN | docker login ghcr.io -u USERNAME --password-stdin

# Or login interactively
docker login ghcr.io -u YOUR_GITHUB_USERNAME
# Enter your GitHub Personal Access Token when prompted
```

**Run with pre-built image:**

```bash
docker run --rm \
  -e AZURE_TENANT_ID="<your-tenant-id>" \
  -e AZURE_CLIENT_ID="<your-client-id>" \
  -e AZURE_CLIENT_SECRET="<your-client-secret>" \
  -e SNIPEIT_URL="https://your-snipeit-url/api/v1" \
  -e SNIPEIT_API_TOKEN="<your-token>" \
  -e SNIPEIT_DEFAULT_STATUS="Ready to Deploy" \
  ghcr.io/brngates98/intune2snipe:latest \
  --platform windows --dry-run
```

**Build and run locally:**

```bash
# Clone the repository
git clone https://github.com/brngates98/intune2snipe.git
cd intune2snipe

# Build the image
docker build -t intune2snipe:latest .

# Run the container
docker run --rm \
  -e AZURE_TENANT_ID="<your-tenant-id>" \
  -e AZURE_CLIENT_ID="<your-client-id>" \
  -e AZURE_CLIENT_SECRET="<your-client-secret>" \
  -e SNIPEIT_URL="https://your-snipeit-url/api/v1" \
  -e SNIPEIT_API_TOKEN="<your-token>" \
  intune2snipe:latest \
  --platform windows --dry-run
```

### Kubernetes

The Kubernetes manifest includes a CronJob that runs the sync on a schedule (default: daily at 2:00 AM UTC).

**Prerequisites:**
- A Kubernetes cluster with access to pull images from GHCR
- `kubectl` configured to access your cluster

**Deployment Steps:**

1. **Edit the Kubernetes manifest** (`k8s/cronjob.yaml`):
   - Update the Secret values with your actual credentials (lines 9-15)
   - Update the image name to match your GHCR repository path (line 40):
     ```yaml
     image: ghcr.io/brngates98/intune2snipe:latest
     ```
   - Customize the schedule if needed (line 24, cron format)
   - Adjust resource limits if necessary (lines 51-57)
   - Uncomment and modify `args` if you need to override platform or group filters (lines 45-50)

2. **Create the Secret and CronJob:**
   ```bash
   kubectl apply -f k8s/cronjob.yaml
   ```

3. **Verify deployment:**
   ```bash
   # Check CronJob status
   kubectl get cronjob intune2snipe-sync
   
   # Check recent jobs
   kubectl get jobs -l app=intune2snipe-sync
   
   # View logs from the most recent job
   kubectl logs -l app=intune2snipe-sync --tail=100
   ```

4. **Manually trigger a job (for testing):**
   ```bash
   kubectl create job --from=cronjob/intune2snipe-sync intune2snipe-sync-manual-$(date +%s)
   ```

**Note:** If your GHCR image is private, you'll need to create a Kubernetes secret with your GitHub token:
```bash
kubectl create secret docker-registry ghcr-secret \
  --docker-server=ghcr.io \
  --docker-username=<your-github-username> \
  --docker-password=<your-github-token> \
  --docker-email=<your-email>
```

Then add `imagePullSecrets` to the CronJob spec (after line 35):
```yaml
imagePullSecrets:
- name: ghcr-secret
```

### CI/CD with GitHub Actions

The repository includes a GitHub Actions workflow (`.github/workflows/docker-build.yml`) that automatically:

- **Builds** Docker images on push to `main`/`master` branches
- **Pushes** images to GitHub Container Registry (GHCR) at `ghcr.io/<org>/<repo>`
- **Tags** images with:
  - Branch names (e.g., `main`, `master`)
  - Semantic version tags (e.g., `v1.0.0`, `v1.0`, `v1`)
  - Git SHA (short commit hash)
  - `latest` tag for default branch
- **Builds** (but doesn't push) on pull requests for testing

**Workflow Triggers:**
- Push to `main` or `master` branches
- Push of tags matching `v*` pattern (e.g., `v1.0.0`)
- Pull requests to `main` or `master`
- Manual trigger via `workflow_dispatch`

**Image Location:**
After pushing to the repository, your images will be available at:
```
ghcr.io/<your-github-org>/<your-repo-name>:<tag>
```

For example, if your repository is `github.com/myorg/intune2snipe`, the image would be:
```
ghcr.io/myorg/intune2snipe:latest
ghcr.io/myorg/intune2snipe:main
ghcr.io/myorg/intune2snipe:v1.0.0
```

**Pull the image:**
```bash
# Pull latest
docker pull ghcr.io/<your-github-org>/<your-repo-name>:latest

# Pull specific tag
docker pull ghcr.io/<your-github-org>/<your-repo-name>:v1.0.0
```

**Viewing Images:**
- Go to your repository → **Packages** section (right sidebar)
- Or visit: `https://github.com/<your-org>/<your-repo>/pkgs/container/<your-repo-name>`
- View all available tags and pull commands on the package page

### Dependabot

This repository includes Dependabot configuration (`.github/dependabot.yml`) that automatically:
- Checks for GitHub Actions updates weekly
- Groups Docker-related actions and GitHub actions into separate PRs
- Creates pull requests for available updates

Dependabot will automatically keep your GitHub Actions workflows up to date.

## How It Works

The sync process follows these steps:

1. **Authentication**: Authenticates with Microsoft Graph API using Azure AD app credentials
2. **Group Filtering** (optional): If `--groups` or `AZURE_GROUP_IDS` is set:
   - Fetches Azure AD device IDs from the specified groups
   - Only devices that are members of these groups will be synced
3. **Device Fetching**: Fetches Intune managed devices via Graph API:
   - Filters by operating system platform (`--platform` flag)
   - Optionally filters by Azure AD group membership
   - Handles pagination automatically
4. **Snipe-IT Setup**: Ensures required Snipe-IT resources exist:
   - Creates `Intune` category if it doesn't exist
   - Verifies the default status label exists (fails if not found)
   - Creates manufacturers and models as needed
5. **Device Import**: For each device:
   - Creates a hardware asset in Snipe-IT with:
     - Device name, serial number
     - Manufacturer, model, category
     - Status label
     - Notes indicating Intune import
   - Normalizes Android-Enterprise UPNs (removes GUID prefixes)
   - Checks out the asset to the assigned user if found in Snipe-IT

**Data Mapping:**
- Intune `deviceName` → Snipe-IT `name`
- Intune `serialNumber` → Snipe-IT `serial`
- Intune `manufacturer` → Snipe-IT `manufacturer_id`
- Intune `model` → Snipe-IT `model_id`
- Intune `userPrincipalName` → Snipe-IT user lookup → asset checkout  

## Troubleshooting

### Authentication Issues

**403 Forbidden when fetching devices:**
- Verify your Azure AD app has `DeviceManagementManagedDevices.Read.All` permission
- Ensure admin consent has been granted for your organization
- Check that the client secret hasn't expired

**403 Forbidden when accessing groups:**
- Verify `Group.Read.All` permission is granted
- Ensure admin consent has been granted
- Check that the group IDs are correct and accessible

**Failed to acquire Graph access token:**
- Verify `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, and `AZURE_CLIENT_SECRET` are correct
- Check that the client secret hasn't expired
- Ensure the app registration exists and is enabled

### Device Sync Issues

**No devices found:**
- Verify devices are actually managed by Intune
- Check that the `--platform` filter matches your devices' operating systems
- If using group filtering, verify devices are Azure AD registered/joined (not just Intune-managed)

**No devices found in groups:**
- Verify the group object IDs are correct
- Check that devices are actually members of those groups in Azure AD
- Ensure devices are Azure AD registered/joined (required for group membership matching)
- Use Azure Portal or Graph Explorer to verify group membership

**Group filtering not working:**
- Devices must be Azure AD registered/joined (not just Intune-managed)
- The script matches devices using their Azure AD device object ID (`azureActiveDeviceId` or `azureADDeviceId`)
- Verify group IDs are correct and accessible

### Snipe-IT Issues

**Status label not found:**
- Check `SNIPEIT_DEFAULT_STATUS` matches exactly an existing status label name
- Status label names are case-sensitive
- Verify the status label exists in Snipe-IT: Settings → Status Labels

**Missing fields or categories:**
- Verify your Snipe-IT instance has categories, models, and status labels enabled
- The script will auto-create categories, manufacturers, and models, but status labels must exist

**Checkout failed:**
- Verify the user exists in Snipe-IT with a matching UPN/email
- Check that the UPN normalization is working correctly (especially for Android devices)
- Ensure the Snipe-IT API token has write permissions

**API errors:**
- Verify `SNIPEIT_URL` ends with `/api/v1`
- Check that `SNIPEIT_API_TOKEN` is valid and has appropriate permissions
- Verify network connectivity to your Snipe-IT instance

### Docker/Kubernetes Issues

**Image pull errors:**
- If using private GHCR images, ensure you've created an `imagePullSecret`
- Verify the image name matches your repository path
- Check that the image tag exists (use `latest` or a specific tag)

**Container fails to start:**
- Verify all required environment variables are set
- Check container logs: `kubectl logs <pod-name>` or `docker logs <container-id>`
- Ensure the entrypoint command is correct

**CronJob not running:**
- Check CronJob status: `kubectl describe cronjob intune2snipe-sync`
- Verify the schedule is correct (cron format)
- Check recent jobs: `kubectl get jobs -l app=intune2snipe-sync`

### Debugging Tips

1. **Always test with `--dry-run` first** to preview actions
2. **Check logs** for detailed error messages
3. **Verify permissions** using Microsoft Graph Explorer
4. **Test API connectivity** to both Graph API and Snipe-IT
5. **Use verbose logging** by checking container/job logs  

## Project Structure

```
Intune2snipe/
├── app.py                          # Main application script
├── Dockerfile                       # Docker container definition
├── requirements.txt                 # Python dependencies
├── k8s/
│   └── cronjob.yaml                # Kubernetes CronJob manifest
├── .github/
│   ├── workflows/
│   │   └── docker-build.yml       # CI/CD workflow for GHCR
│   └── dependabot.yml              # Dependabot configuration
└── README.md                        # This file
```

## Contributing

Contributions are welcome! Please feel free to:

1. Open an issue to report bugs or suggest features
2. Submit a pull request with improvements
3. Update documentation as needed

**Before submitting:**
- Test your changes with `--dry-run` first
- Ensure code follows Python best practices
- Update documentation if adding new features

## License

[Add your license here]

## Support

For issues, questions, or contributions:
- Open an issue on GitHub
- Check existing issues and discussions
- Review the troubleshooting section above
