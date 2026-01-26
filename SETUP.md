# InfraMinds Setup Guide (Real Execution Mode)

Since you chose the **Real Execution** path for the Self-Healing Terraform Agent, you need to set up the local environment.

## Prerequisites

1.  **Docker Desktop**: Must be installed and running.
    - [Download Docker Desktop for Mac](https://docs.docker.com/desktop/install/mac-install/)

2.  **Terraform CLI**: The infrastructure-as-code tool.
    ```bash
    brew tap hashicorp/tap
    brew install hashicorp/tap/terraform
    ```

3.  **LocalStack & tflocal**: Local AWS emulation and the terraform wrapper.
    ```bash
    pip install terraform-local localstack awscli-local
    ```
    *(Note: `terraform-local` installs the `tflocal` command wrapper)*

## Start LocalStack

Open a separate terminal tab/window and run:
```bash
localstack start -d
```
Verify it's running:
```bash
localstack status services
```

## Verify Installation

Run this in your main terminal to confirm everything is ready:
```bash
terraform --version
tflocal --version
docker ps
```

Once these commands succeed, the InfraMinds agent can generate and deploy real infrastructure locally!
