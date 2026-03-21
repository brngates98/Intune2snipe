"""Optional loaders for credentials from external secret stores.

Imports for AWS, Vault, and Azure Key Vault are deferred inside each function so
``pip install -r requirements.txt`` stays minimal unless those backends are used.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any

log = logging.getLogger("intune2snipe")


def apply_secrets_to_env(secrets: dict[str, Any]) -> None:
    """Set environment variables from *secrets* only when not already set."""
    for key, value in secrets.items():
        if value is None:
            continue
        if not os.getenv(key):
            os.environ[key] = str(value)


def load_from_aws_secrets_manager(secret_name: str, region_name: str = "us-east-1") -> dict[str, Any]:
    try:
        import boto3  # type: ignore[import-not-found]
        from botocore.exceptions import ClientError  # type: ignore[import-not-found]
    except ImportError as e:
        raise RuntimeError(
            "boto3 is required for AWS Secrets Manager. Install with: pip install boto3"
        ) from e

    log.info(
        "Loading secrets from AWS Secrets Manager: %s (region: %s)",
        secret_name,
        region_name,
    )
    try:
        client = boto3.client("secretsmanager", region_name=region_name)
        response = client.get_secret_value(SecretId=secret_name)
    except ClientError as e:
        raise RuntimeError(f"Failed to retrieve secret from AWS Secrets Manager: {e}") from e

    if "SecretString" in response:
        return json.loads(response["SecretString"])
    raise RuntimeError("Binary secrets are not supported")


def load_from_vault(vault_addr: str, vault_path: str, vault_token: str | None = None) -> dict[str, Any]:
    try:
        import hvac  # type: ignore[import-not-found]
    except ImportError as e:
        raise RuntimeError(
            "hvac is required for HashiCorp Vault. Install with: pip install hvac"
        ) from e

    token = vault_token or os.getenv("VAULT_TOKEN")
    if not token:
        raise RuntimeError("VAULT_TOKEN environment variable is required for HashiCorp Vault")

    log.info("Loading secrets from HashiCorp Vault: %s -> %s", vault_addr, vault_path)
    client = hvac.Client(url=vault_addr, token=token)
    if not client.is_authenticated():
        raise RuntimeError("Failed to authenticate with HashiCorp Vault")

    try:
        response = client.secrets.kv.v2.read_secret_version(path=vault_path)
        return response["data"]["data"]
    except Exception:
        log.info("KV v2 read failed, trying v1")
        response = client.secrets.kv.v1.read_secret(path=vault_path)
        return response["data"]


def load_from_azure_keyvault(vault_url: str, credential: Any | None = None) -> dict[str, Any]:
    try:
        from azure.identity import DefaultAzureCredential
        from azure.keyvault.secrets import SecretClient  # type: ignore[import-not-found]
    except ImportError as e:
        raise RuntimeError(
            "azure-identity and azure-keyvault-secrets are required for Azure Key Vault. "
            "Install with: pip install azure-keyvault-secrets"
        ) from e

    if credential is None:
        credential = DefaultAzureCredential()

    log.info("Loading secrets from Azure Key Vault: %s", vault_url)
    client = SecretClient(vault_url=vault_url, credential=credential)

    secret_names = [
        "AZURE-TENANT-ID",
        "AZURE-CLIENT-ID",
        "AZURE-COMBINED-CERT-KEY",
        "AZURE-CERTIFICATE-PEM",
        "AZURE-PRIVATE-KEY-PEM",
        "AZURE-CLIENT-SECRET",
        "SNIPEIT-URL",
        "SNIPEIT-API-TOKEN",
        "SNIPEIT-DEFAULT-STATUS",
        "AZURE-GROUP-IDS",
    ]
    secrets: dict[str, str] = {}
    for name in secret_names:
        try:
            secret = client.get_secret(name)
            env_var = name.replace("-", "_")
            secrets[env_var] = secret.value
        except Exception:
            pass
    return secrets
