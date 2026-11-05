---
description: Create an Azure AI Gateway for an authorized administrator and verify provisioning.
argument-hint: <gateway-name> <resource-group> <region>
---

# /ai-gateway:create

Follow `skills/manage-ai-gateway/SKILL.md`, especially **Prerequisites and target
resolution** and **Create a gateway**.

Use `$ARGUMENTS` to resolve the gateway name, resource group, and supported Azure
region. Confirm the subscription, permissions, intended changes, and possible
costs before creation. Do not create a resource group unless requested.
Use `az aigateway create`, then `az aigateway show` to verify provisioning.
Do not overwrite an existing gateway or configure additional assets without
the user's approval. Report resource identity and state without credentials.
