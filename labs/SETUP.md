[AI Gateway labs](README.md) › Setup guide <!-- gh -->

# Setup guide

The tasks that the labs share, in one place. Do each one once: every lab lists the ones it needs under **Before you
begin** and links back here, so the labs themselves stay short. On the labs site, set **Your values** first, and the
commands below fill in your subscription, tenant, and region. The site also opens this guide in a panel from any lab,
and you can mark each task **Done**: the labs then stop listing it. Your browser keeps the marks.

| Task | When you need it |
| :-- | :-- |
| [Check your subscription and permissions](#check-your-subscription-and-permissions) | Before your first lab |
| [Choose where to run commands](#choose-where-to-run-commands) | Every track except the portal |
| [Sign in to Azure](#sign-in-to-azure) | On your own machine. Cloud Shell is already signed in. |
| [Install the `aigateway` extension](#install-the-aigateway-extension) | The Azure CLI tracks and the **Verify** steps |
| [Register the resource providers](#register-the-resource-providers) | Once per subscription, before you create a gateway with the Azure CLI |
| [Find the available regions](#find-the-available-regions) | Before you choose a location |
| [Clone the labs repo](#clone-the-labs-repo) | The Bicep + azd tracks, the notebooks, and the code samples |
| [Deploy a lab with azd](#deploy-a-lab-with-azd) | The Bicep + azd tracks |

## Check your subscription and permissions

You need an Azure subscription where you can create resources. For the gateway's pricing, see the
[AI Gateway documentation](https://ai.gateway.azure.com/docs). Connected services, such as Foundry inference and
Application Insights, are billed normally.

| To | You need, for example |
| :-- | :-- |
| Create a gateway in the portal or with the Azure CLI | **Contributor** on the resource group, or on the subscription if you create a new resource group. In the portal, you also need write access to `Microsoft.Web/connectorGateways`, because the portal creates a connector gateway with the same name for connector-based MCP tools. |
| Change a gateway that already exists | **Contributor** on its resource group |
| Give the gateway a role on a Foundry account, as most Bicep + azd tracks do | **Owner**, or **Contributor** plus **Role Based Access Control Administrator**, on the subscription. The templates create a resource group and role assignments, so that the gateway can call your models with its own identity. |

Each lab lists any other role that it needs under **Before you begin**. In the portal, a subscription where you
can't create gateways shows as disabled in the subscription picker.

## Choose where to run commands

[Azure Cloud Shell](https://shell.azure.com) is the quickest way. Open it in Bash or PowerShell: it's already signed
in, and it has the Azure CLI, the Azure Developer CLI (`azd`), Git, `jq`, `curl`, Python, Node.js, and .NET. Add
the [`aigateway` extension](#install-the-aigateway-extension), and you're ready for every track.

To work on your own machine, install the tools for the tracks you plan to follow:

| Tool | Used by |
| :-- | :-- |
| [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) 2.75 or later | The Azure CLI tracks, the **Verify** steps, and `azd env new` in the Bicep + azd tracks |
| The [`aigateway` extension](#install-the-aigateway-extension) | The `az aigateway` commands |
| [Azure Developer CLI (`azd`)](https://aka.ms/azd-install) | The Bicep + azd tracks. It installs Bicep the first time it needs it. |
| [Git](https://git-scm.com/downloads) | Cloning the labs repo |
| [`jq`](https://jqlang.org/download/) | The Bash snippets that build or read JSON. The PowerShell snippets don't need it. |
| Python, Node.js, or the .NET 8 SDK | The code samples, depending on the language. Each lab lists the versions it needs. |

Every command comes in a Bash and a PowerShell variant, unless it's the same in both shells. The PowerShell commands
need PowerShell 7 or later, as Cloud Shell has; Windows PowerShell 5.1 doesn't run them.

On macOS, the Terminal runs zsh, which treats a pasted `# comment` line as a command unless the
`interactive_comments` option is on. Turn it on, now and in every new terminal, before you paste the Bash snippets:

```bash
setopt interactive_comments
grep -qx 'setopt interactive_comments' ~/.zshrc 2>/dev/null || echo 'setopt interactive_comments' >> ~/.zshrc
echo "✅ zsh accepts the comments in pasted commands"
```

Paste each block when the prompt is back. If you paste while a command still runs, the shell reads the block line by
line, and add-ons such as oh-my-zsh's URL quoting can change the lines.

## Sign in to Azure

Cloud Shell is already signed in, so skip this step there. On your own machine, sign in to the Azure CLI, select the
subscription for the labs, and sign in to `azd` for the Bicep + azd tracks:

```bash title="Bash or PowerShell"
# Sign in to the Azure CLI in your browser, with the account that has access to your subscription
az login &&
  echo "👤 Signed in to the Azure CLI"

# Select the subscription for the labs, so that every later command creates resources in it
az account set --subscription "<subscription-id>" &&
  echo "🆔 Subscription <subscription-id> is selected"

# Sign in to the Azure Developer CLI (azd) too, for the Bicep + azd tracks
azd auth login &&
  echo "👤 Signed in to azd"
```

If your account belongs to more than one tenant, sign in to the tenant that has the subscription instead:

```bash title="Bash or PowerShell"
# Sign in to the Azure CLI in the tenant that has your subscription
az login --tenant "<tenant-id>" &&
  echo "👤 Signed in to the Azure CLI in tenant <tenant-id>"

# Sign in to azd in the same tenant
azd auth login --tenant-id "<tenant-id>" &&
  echo "👤 Signed in to azd in tenant <tenant-id>"
```

> **Checkpoint**
> `az account show --query name -o tsv` prints the name of the subscription you selected.

## Install the `aigateway` extension

The labs manage gateways with the `aigateway` extension of the Azure CLI. Install or upgrade it, then check that the
CLI loads it. The installer downloads the published release, verifies it, and needs no Azure sign-in.

<details open><summary>Bash</summary> <!-- gh -->

```bash title="Bash"
# Install or upgrade the aigateway extension of the Azure CLI: the installer downloads and verifies the release
curl -fsSL https://aka.ms/aigateway-cli-install | sh &&
  echo "📦 aigateway extension $(az extension show --name aigateway --query version --output tsv) is installed"

# Check that the Azure CLI loads the extension: it prints the extension version and the API version it calls
echo "📦 The aigateway extension reports:"
az aigateway version
```
</details> <!-- gh -->

<details><summary>PowerShell</summary> <!-- gh -->

```powershell title="PowerShell"
# Install or upgrade the aigateway extension of the Azure CLI: the installer downloads and verifies the release
irm https://aka.ms/aigateway-cli-install-ps | iex
if ($?) { Write-Host "📦 aigateway extension $(az extension show --name aigateway --query version --output tsv) is installed" }

# Check that the Azure CLI loads the extension: it prints the extension version and the API version it calls
Write-Host "📦 The aigateway extension reports:"
az aigateway version
```
</details> <!-- gh -->

> **Checkpoint**
> The installer printed `📦 aigateway extension … is installed`, and `az aigateway version` prints the extension
> version and the API version it calls, `2025-09-01-preview`. The labs need version `1.0.0b22` or later; run the
> installer again to upgrade an older one.

> [!NOTE]
> The labs use `az aigateway` commands wherever the extension covers an operation. A few operations, such as
> an MCP server's tool rules, aren't in the extension yet. For those, the labs call the Azure Resource Manager
> REST API with `az rest` and say why.

## Register the resource providers

The gateway lives in the `Microsoft.ApiManagement` resource provider. Most labs also create a Foundry account, in
`Microsoft.CognitiveServices`. Register them once per subscription. Registering returns quickly when a provider is
already registered. The portal registers the providers it needs when you create a gateway there, including
`Microsoft.Web` for its connector gateway.

<details open><summary>Bash</summary> <!-- gh -->

```bash title="Bash"
# Register the resource providers for AI Gateway and Foundry (once per subscription)
# --wait returns when each provider is registered, and right away if it already is
for ns in Microsoft.ApiManagement Microsoft.CognitiveServices; do
  az provider register --namespace "$ns" --wait && echo "📦 $ns is registered"
done
```
</details> <!-- gh -->

<details><summary>PowerShell</summary> <!-- gh -->

```powershell title="PowerShell"
# Register the resource providers for AI Gateway and Foundry (once per subscription)
# --wait returns when each provider is registered, and right away if it already is
foreach ($ns in "Microsoft.ApiManagement", "Microsoft.CognitiveServices") {
  az provider register --namespace $ns --wait
  if ($?) { Write-Host "📦 $ns is registered" }
}
```
</details> <!-- gh -->

A few labs use more providers. Register them the same way before you start those labs:

| Provider | Used by |
| :-- | :-- |
| `Microsoft.Insights` and `Microsoft.OperationalInsights` | [13 · Monitoring](13-monitoring/README.md) and [21 · Enterprise reference](21-enterprise-reference/README.md) |
| `Microsoft.Network` | [18 · Private networking](18-private-networking/README.md) |

> **Checkpoint**
> The loop printed a line such as `📦 Microsoft.ApiManagement is registered` for each provider, and
> `az provider show --namespace Microsoft.ApiManagement --query registrationState -o tsv` prints `Registered`.

Registering a provider needs a role such as **Contributor** on the subscription. If you don't have it, ask your
subscription administrator to register the providers.

## Find the available regions

AI Gateway keeps adding regions. List the current ones: the first command reads the regions of the
`Microsoft.ApiManagement/aigateways` resource type, and the second matches them to the region names that
`--location` takes.

<details open><summary>Bash</summary> <!-- gh -->

```bash title="Bash"
# Read the regions of the aigateways resource type, where you can create a gateway
regions=$(az provider show --namespace Microsoft.ApiManagement \
  --query "resourceTypes[?resourceType=='aigateways'].locations | [0]" -o json)

# Match them to the region names that --location takes, and print both as a table
echo "📍 Regions where you can create a gateway:"
az account list-locations -o json |
  jq -r --argjson regions "$regions" '
    ["Display Name", "Name"],
    (.[] | select(.displayName as $d | $regions | index($d)) | [.displayName, .name])
    | @tsv
  ' | column -t -s $'\t'
```
</details> <!-- gh -->

<details><summary>PowerShell</summary> <!-- gh -->

```powershell title="PowerShell"
# Read the regions of the aigateways resource type, where you can create a gateway
$regions = az provider show --namespace Microsoft.ApiManagement `
  --query "resourceTypes[?resourceType=='aigateways'].locations | [0]" -o json | ConvertFrom-Json

# Match them to the region names that --location takes, and print both as a table
Write-Host "📍 Regions where you can create a gateway:"
az account list-locations -o json | ConvertFrom-Json |
  Where-Object { $regions -contains $_.displayName } |
  Format-Table @{ Label = 'Display Name'; Expression = { $_.displayName } }, @{ Label = 'Name'; Expression = { $_.name } }
```
</details> <!-- gh -->

Expected output: the `📍 Regions where you can create a gateway:` line, then one row per region, such as
`East US 2   eastus2`. Use a value from the **Name** column wherever a lab asks for a location. The portal lists the
regions where it can create gateways, which can be fewer. To use a region that it doesn't list, create the gateway
with the Azure CLI or Bicep + azd track.

Most labs also deploy Foundry models, and their templates put the Foundry account in the gateway's region, so pick a
region where those models are available too. Each lab names its models. For example, this command prints the
deployment types of `gpt-5-mini` in a region, and prints nothing if the model isn't available there:

<details open><summary>Bash</summary> <!-- gh -->

```bash title="Bash"
# List the deployment types of gpt-5-mini in a region, such as GlobalStandard: no output means it isn't there
echo "✨ Deployment types of gpt-5-mini in <location>:"
az cognitiveservices model list --location "<location>" \
  --query "[?model.name=='gpt-5-mini'].model.skus[].name" -o tsv
```
</details> <!-- gh -->

<details><summary>PowerShell</summary> <!-- gh -->

```powershell title="PowerShell"
# List the deployment types of gpt-5-mini in a region, such as GlobalStandard: no output means it isn't there
Write-Host "✨ Deployment types of gpt-5-mini in <location>:"
az cognitiveservices model list --location "<location>" `
  --query "[?model.name=='gpt-5-mini'].model.skus[].name" -o tsv
```
</details> <!-- gh -->

## Clone the labs repo

The Bicep + azd tracks, the notebooks, and the code samples run from the
[labs repo](https://github.com/Azure/aigateway/tree/main/labs). Clone it once into your home folder:

```bash title="Bash or PowerShell"
# Clone the labs repo into your home folder, as ~/aigateway, where every lab expects it
cd ~
git clone https://github.com/Azure/aigateway.git &&
  echo "📂 The labs are in ~/aigateway/labs"
```

Each lab then moves into its own folder, for example `cd ~/aigateway/labs/06-token-limits`. If you cloned the repo
before, get the latest labs with `git -C ~/aigateway pull` instead. If you cloned it somewhere else, use that path
instead of `~/aigateway`.

## Deploy a lab with azd

Each Bicep + azd track is a small azd project in its lab's folder: an `azure.yaml` file and an `infra/` folder with
the Bicep templates. It creates its own resource group, gateway, and whatever else the lab needs, so it doesn't
depend on other labs or on **Your values**. Every track follows the same steps:

1. Move into the lab's folder.
2. Create an azd environment. Its name also names the resource group, `rg-<environment name>`. `--location` sets the
   region of every resource, and `--subscription` selects the Azure CLI's current subscription, so azd doesn't
   prompt you.
3. Run `azd up` to deploy the templates. It ends with `SUCCESS`.
4. Read the outputs that the next steps use with `azd env get-value <NAME>`, or list them all with
   `azd env get-values`.

For example, for [lab 06](06-token-limits/README.md):

<details open><summary>Bash</summary> <!-- gh -->

```bash title="Bash"
# Move into the lab's folder, which holds its azure.yaml file and its infra/ templates
cd ~/aigateway/labs/06-token-limits &&
  echo "📂 Lab folder: $(pwd)"

# Create an azd environment in your current subscription and region, so that azd doesn't prompt you
azd env new aigw-lab06 --location "<location>" --subscription "$(az account show --query id --output tsv)" &&
  echo "📝 azd environment aigw-lab06 deploys to <location>"

# Deploy the templates: the resource group rg-aigw-lab06, the gateway, and whatever else the lab needs
azd up &&
  echo "🚀 Lab deployed to rg-aigw-lab06"

# Read one of the outputs that the next steps use: the gateway's runtime URL
echo "🌐 Runtime URL:"
azd env get-value AI_GATEWAY_URL
```
</details> <!-- gh -->

<details><summary>PowerShell</summary> <!-- gh -->

```powershell title="PowerShell"
# Move into the lab's folder, which holds its azure.yaml file and its infra/ templates
cd ~/aigateway/labs/06-token-limits
if ($?) { Write-Host "📂 Lab folder: $(Get-Location)" }

# Create an azd environment in your current subscription and region, so that azd doesn't prompt you
azd env new aigw-lab06 --location "<location>" --subscription (az account show --query id --output tsv)
if ($?) { Write-Host "📝 azd environment aigw-lab06 deploys to <location>" }

# Deploy the templates: the resource group rg-aigw-lab06, the gateway, and whatever else the lab needs
azd up
if ($?) { Write-Host "🚀 Lab deployed to rg-aigw-lab06" }

# Read one of the outputs that the next steps use: the gateway's runtime URL
Write-Host "🌐 Runtime URL:"
azd env get-value AI_GATEWAY_URL
```
</details> <!-- gh -->

Each lab gives its environment name, such as `aigw-lab06`, and a region that its models support, usually `eastus2`.
For another region, use a name from [Find the available regions](#find-the-available-regions) where the lab's models
are available. To change a template parameter later, run `azd env set <NAME> <value>`, then `azd provision`.

### Delete what azd created

When you finish a lab, run this from its folder. It deletes the environment's resource group and everything in it,
usually within ten minutes:

```bash title="Bash or PowerShell"
# Delete everything that azd up created, purge the soft-deleted Foundry account, and skip the confirmation prompt
azd down --purge --force &&
  echo "🚮 Everything that azd up created is deleted"
```

`--purge` also purges soft-deleted resources such as the Foundry account, which would otherwise stay soft-deleted
for 48 hours and keep counting against your quota. `--force` skips the confirmation prompt.

## Troubleshooting

For sign-in, extension, resource provider, region, and azd errors, with their likely causes and fixes, see
[Troubleshooting](TROUBLESHOOTING.md#setup-and-deployment).
