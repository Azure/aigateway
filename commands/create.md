---
description: Create an Azure AI Gateway, optionally with explicitly requested RG and Foundry bootstrap.
argument-hint: <gateway-name> <resource-group> <region> [bootstrap scope]
---

# /aigateway:create

Read and follow `skills/manage-ai-gateway/SKILL.md` and its lifecycle recipe.
Use `$ARGUMENTS` to resolve explicit subscription, RG, region/name and requested
settings. Use native `az aigateway create`; refuse overwrite or legacy-family
collision and verify exact identity and bounded provisioning completion.

RG creation is allowed only when explicitly requested. Selected Foundry
onboarding needs specific approval of gateway identity and account-level
Foundry User effects; bulk provider import also needs approval of every current
deployment. Do not provision unrelated prerequisites or unrequested assets.
Data-plane checks use the consumer workflow with separate authorization.
